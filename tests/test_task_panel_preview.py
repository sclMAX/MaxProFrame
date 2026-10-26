"""Native acceptance tests for task-panel-usability T2 (S2, S4, S6)."""

import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher  # Registers the native sketch type used by saved assets.
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.custom_profile_cards import render_custom_section_thumbnail
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.ff_tools import PROFILEIMAGES_PATH, TRANSLATIONSPATH, get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.profile import Profile


class TestTaskPanelPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        language, locale = self.prefs.GetString("Language", ""), Gui.getLocale()
        default = QtCore.QLocale()
        def restore_language():
            self.prefs.SetString("Language", language)
            Gui.setLocale(locale)
            Gui.updateLocale()
            QtCore.QLocale.setDefault(default)
        self.addCleanup(restore_language)
        Gui.addLanguagePath(TRANSLATIONSPATH)
        self._language("English", "en_US")
        self.workspace = tempfile.TemporaryDirectory(prefix="mpf_panel_preview_")
        self.addCleanup(self.workspace.cleanup)
        root = self.workspace.name
        self.manager = LibraryManager(user_dir=os.path.join(root, "user"),
                                      stock_dir=os.path.join(root, "stock"),
                                      registry_path=os.path.join(root, "registry.json"))
        self.folder = os.path.join(root, "catalog")
        sizes = {}
        self.manager.create_folder_library(self.folder, "Preview Library", material="Steel",
                                          density=7.85, data={})
        os.makedirs(os.path.join(self.folder, "sections"), exist_ok=True)
        for code, width, height, weight, description in (
                ("WIDE", 80, 20, "1.25", "Wide section"),
                ("TALL", 20, 80, "2.5", "Tall section")):
            asset = App.newDocument("PreviewAsset")
            try:
                sketch = asset.addObject("Sketcher::SketchObject", "Section")
                points = [(0, 0), (width, 0), (width, height), (0, height)]
                for a, b in zip(points, points[1:] + points[:1]):
                    sketch.addGeometry(Part.LineSegment(App.Vector(*a, 0), App.Vector(*b, 0)), False)
                asset.recompute()
                relative = "sections/%s.FCStd" % code
                asset.saveAs(os.path.join(self.folder, relative))
            finally:
                App.closeDocument(asset.Name)
            sizes[code] = {"asset_path": relative, "object_name": "Section",
                           "Weight": weight, "Description": description}
        with open(os.path.join(self.folder, "sections", "broken.FCStd"), "wb") as stream:
            stream.write(b"not a FreeCAD archive")
        for code, path in (("MISSING", "sections/missing.FCStd"),
                           ("BROKEN", "sections/broken.FCStd")):
            sizes[code] = {"asset_path": path, "object_name": "Section", "Weight": "3"}
        # Publish through the same catalog writer as the library UI.
        self.manager.save_folder_library(self.folder, {
            "Custom Profile": {"canonical_family": "Custom Profile", "norm": "Custom",
                               "unit": "mm", "sizes": sizes},
            "Square Hollow": {"canonical_family": "Square Hollow", "norm": "ISO",
                              "unit": "mm", "fillet": False,
                              "sizes": {"40x40x2": {"Height": "40", "Width": "40",
                                                      "Thickness": "2", "Weight": "0.8"}}},
        })
        factory = patch("freecad.maxproframe.create_profiles_tool.LibraryManager", return_value=self.manager)
        factory.start()
        self.addCleanup(factory.stop)
        self.doc = App.newDocument("PreviewTarget")
        self.addCleanup(App.closeDocument, self.doc.Name)
        Gui.Selection.clearSelection()
        self.panels = []
        self.addCleanup(self._close_panels)

    def _language(self, language, default):
        self.prefs.SetString("Language", language)
        Gui.setLocale(language)
        Gui.updateLocale()
        QtCore.QLocale.setDefault(QtCore.QLocale(default))

    def _close_panels(self):
        for panel in self.panels:
            if hasattr(panel, "clean"):
                panel.clean()
            for form in panel.form:
                form.close()
        Gui.Selection.clearSelection()
        self.doc.abortTransaction()

    def _panel(self, obj=None):
        panel = EditProfileTaskPanel(obj) if obj is not None else CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        if obj is None:
            panel.form_proxy.combo_material.setCurrentText("Preview Library")
            panel.form_proxy.combo_family.setCurrentText("Custom Profile")
            panel.form_proxy.combo_size.setCurrentText("WIDE")
        return panel

    def _click_anchor(self, panel, ax, ay):
        widget = panel.alignment_widget
        self._show(panel)
        point = widget.anchor_position(ax, ay)
        for kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            event = QtGui.QMouseEvent(kind, point, QtCore.Qt.LeftButton,
                                     QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            self.app.sendEvent(widget, event)
        self.assertEqual(panel.get_anchor(), (ax, ay))
        self.assertEqual(widget.selected_anchor, (ax, ay))

    def test_alignment_create_clicks_apply_cancel_and_source_changes(self):
        panel = self._panel()
        panel.form_proxy.sb_length.setValue(100)
        with patch.object(panel, "on_input_changed", wraps=panel.on_input_changed) as changed:
            for ax in range(3):
                for ay in range(3):
                    count = changed.call_count
                    self._click_anchor(panel, ax, ay)
                    self.assertEqual(changed.call_count, count + 1)
                    self.assertEqual(self.doc.Objects, [])
        for ax in range(3):
            for ay in range(3):
                getattr(panel.form_proxy, "rb_anchor_%s_%s" % (ax, ay)).click()
                self.assertEqual(panel.alignment_widget.selected_anchor, (ax, ay))
        with patch.object(App, "openDocument", side_effect=AssertionError("click loaded catalog")), \
                patch.object(Gui.Selection, "clearSelection", side_effect=AssertionError("click changed selection")):
            self._click_anchor(panel, 2, 2)
        panel.form_proxy.combo_rotation.setCurrentText("37")
        panel.form_proxy.cb_mirror_h.setChecked(True)
        panel.form_proxy.cb_mirror_v.setChecked(True)
        self.assertEqual(panel.alignment_widget.rotation, 37)
        self.assertEqual(panel.alignment_widget.mirrors, (True, True))
        self.assertTrue(panel.apply())
        obj = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile")
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Right", "Top"))
        before = obj.Shape.copy()
        self._click_anchor(panel, 0, 1)
        self.assertAlmostEqual(obj.Shape.common(before).Volume, before.Volume)
        self.assertTrue(panel.apply())
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Left", "Center"))
        path_before = panel.alignment_widget.section_bounds
        panel.form_proxy.combo_size.setCurrentText("TALL")
        self.assertNotEqual(panel.alignment_widget.section_bounds, path_before)
        self.assertEqual(panel.get_anchor(), (0, 1))
        panel.reject()
        self.assertEqual(self.doc.Objects, [])

    def test_alignment_edit_live_cancel_and_create_deferred_snapshot(self):
        create = self._panel()
        create.form_proxy.sb_length.setValue(100)
        self._click_anchor(create, 2, 0)
        # Mutating real controls after accept must not alter the queued snapshot.
        with patch.object(QtCore.QTimer, "singleShot") as timer:
            self.assertTrue(create.accept(defer=True))
            callback = timer.call_args[0][1]
            create.set_anchor(0, 2)
            callback()
        obj = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile")
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Right", "Bottom"))
        original = obj.Shape.copy()
        edit = self._panel(obj)
        self.assertEqual(edit.alignment_widget.selected_anchor, (2, 0))
        with patch.object(edit, "on_input_changed", wraps=edit.on_input_changed) as changed:
            self._click_anchor(edit, 0, 2)
            self.assertEqual(changed.call_count, 1)
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Left", "Top"))
        edit.form_proxy.combo_rotation.setCurrentText("37")
        self.assertAlmostEqual(obj.RotationAngle, 37)
        edit.reject()
        obj = self.doc.getObject(obj.Name)
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Right", "Bottom"))
        self.assertAlmostEqual(obj.Shape.common(original).Volume, original.Volume)
        edit2 = self._panel(obj)
        self._click_anchor(edit2, 1, 1)
        self.assertTrue(edit2.accept())
        self.assertEqual((str(obj.AnchorX), str(obj.AnchorY)), ("Center", "Center"))

    def _create_resized_local_source(self, width=120, height=30):
        first = self._panel()
        first.form_proxy.sb_length.setValue(100)
        self.assertTrue(first.accept(defer=False))
        profile = next(o for o in App.ActiveDocument.Objects if getattr(o, "Family", None) == "Custom Profile")
        source = profile.CustomProfile
        points = [(0, 0), (width, 0), (width, height), (0, height)]
        source.Geometry = [Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0))
                           for start, end in zip(points, points[1:] + points[:1])]
        source.Document.recompute()
        self.assertAlmostEqual(source.Shape.BoundBox.XLength, width)
        self.assertAlmostEqual(source.Shape.BoundBox.YLength, height)
        return profile, source

    def test_alignment_create_matches_reused_locally_edited_source(self):
        first, source = self._create_resized_local_source()
        original_names = {o.Name for o in self.doc.Objects}
        original_source = source.Shape.exportBrepToString()
        files = self._files()
        panel = self._panel()
        panel.form_proxy.sb_length.setValue(100)
        self.assertAlmostEqual(panel.alignment_widget.section_bounds.width(), 120)
        self.assertAlmostEqual(panel.alignment_widget.section_bounds.height(), 30)
        before = self._state(panel)
        with patch.object(App, "openDocument", side_effect=AssertionError("refresh imported an asset")), \
                patch.object(App, "newDocument", side_effect=AssertionError("refresh created document")):
            panel._refresh_alignment()
        self.assertEqual(self._state(panel), before)
        self.assertEqual({o.Name for o in self.doc.Objects}, original_names)
        self.assertTrue(panel.apply())
        second = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile" and o != first)
        self.assertIs(second.CustomProfile, source)
        self.assertAlmostEqual(second.ProfileWidth, panel.alignment_widget.section_bounds.width())
        self.assertAlmostEqual(second.ProfileHeight, panel.alignment_widget.section_bounds.height())
        self.assertEqual(source.Shape.exportBrepToString(), original_source)
        self.assertEqual(self._files(), files)
        panel.reject()
        self.assertEqual({o.Name for o in self.doc.Objects}, original_names)
        self.assertIs(first.CustomProfile, source)
        self.assertEqual(source.Shape.exportBrepToString(), original_source)
        self.assertEqual(self._files(), files)

    def test_alignment_create_preserves_normalized_path_and_optional_asset_id_reuse(self):
        import copy
        first, source = self._create_resized_local_source()
        source.FF_AssetId = "local-id"
        original_names = {o.Name for o in self.doc.Objects}
        catalog = copy.deepcopy(self.manager.get_all_profiles()["Preview Library"])
        entry = catalog["Custom Profile"]["sizes"]["WIDE"]
        entry["asset_path"] = "sections/./WIDE.FCStd"
        for asset_id, reuse in ((None, True), ("local-id", True), ("different-id", False)):
            with self.subTest(asset_id=asset_id):
                entry["asset_id"] = asset_id
                self.manager.save_folder_library(self.folder, catalog)
                files = self._files()
                panel = self._panel()
                panel.form_proxy.sb_length.setValue(100)
                self.assertAlmostEqual(panel.alignment_widget.section_bounds.width(), 120 if reuse else 80)
                self.assertTrue(panel.apply())
                second = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile" and o != first)
                self.assertEqual(second.CustomProfile is source, reuse)
                self.assertAlmostEqual(second.ProfileWidth, panel.alignment_widget.section_bounds.width())
                self.assertEqual(self._files(), files)
                panel.reject()
                self.assertEqual({o.Name for o in self.doc.Objects}, original_names)

    def test_alignment_create_uses_selected_path_document_before_target_document(self):
        _first, target_source = self._create_resized_local_source()
        other = App.newDocument("SelectedSourceTarget")
        self.addCleanup(lambda: App.closeDocument(other.Name) if other.Name in App.listDocuments() else None)
        _other_first, selected_source = self._create_resized_local_source(140, 40)
        path = other.addObject("Part::Feature", "Path")
        path.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 100))
        other.recompute()
        App.setActiveDocument(self.doc.Name)
        panel = self._panel()
        panel.form_proxy.sb_length.setValue(100)
        # No selection: the session target wins, even if ActiveDocument changes.
        App.setActiveDocument(other.Name)
        panel._refresh_alignment()
        self.assertAlmostEqual(panel.alignment_widget.section_bounds.width(), 120)
        # FreeCAD only accepts GUI selection in the active document. Keep the
        # selected document active while the panel's captured target stays fixed.
        Gui.Selection.addObserver(panel)
        Gui.Selection.addSelection(other.Name, path.Name, "Edge1")
        self.assertEqual(Gui.Selection.getSelectionEx()[0].DocumentName, other.Name)
        self.assertAlmostEqual(panel.alignment_widget.section_bounds.width(), 140)
        self.assertAlmostEqual(panel.alignment_widget.section_bounds.height(), 40)
        before = self._state(panel)
        names = tuple(o.Name for o in other.Objects)
        source_before = selected_source.Shape.exportBrepToString()
        panel._refresh_alignment()
        self.assertEqual(self._state(panel), before)
        self.assertEqual(tuple(o.Name for o in other.Objects), names)
        self.assertEqual(selected_source.Shape.exportBrepToString(), source_before)
        self.assertTrue(panel.apply())
        applied = next(o for o in other.Objects if getattr(o, "Family", None) == "Custom Profile" and o != _other_first)
        self.assertIs(applied.CustomProfile, selected_source)
        self.assertIsNot(applied.CustomProfile, target_source)
        self.assertAlmostEqual(applied.ProfileWidth, panel.alignment_widget.section_bounds.width())
        panel.reject()

    def test_alignment_edit_switches_custom_family_even_when_code_is_unchanged(self):
        import copy
        create = self._panel()
        create.form_proxy.sb_length.setValue(100)
        self.assertTrue(create.accept(defer=False))
        obj = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile")
        catalog = copy.deepcopy(self.manager.get_all_profiles()["Preview Library"])
        catalog["Other Custom"] = {"canonical_family": "Custom Profile", "norm": "Custom",
                                   "unit": "mm", "sizes": {"WIDE": catalog["Custom Profile"]["sizes"]["TALL"]}}
        self.manager.save_folder_library(self.folder, catalog)
        edit = self._panel(obj)
        self.assertAlmostEqual(edit.alignment_widget.section_bounds.width(), 80)
        edit.form_proxy.combo_family.setCurrentText("Other Custom")
        self.assertEqual(obj.CatalogFamily, "Other Custom")
        self.assertEqual(obj.SizeName, "WIDE")
        self.assertAlmostEqual(edit.alignment_widget.section_bounds.width(), 20)
        self.assertAlmostEqual(edit.alignment_widget.section_bounds.height(), 80)
        edit.reject()

    def test_alignment_edit_uses_local_source_and_refreshes_holes_without_catalog(self):
        create = self._panel()
        create.form_proxy.sb_length.setValue(100)
        self.assertTrue(create.accept(defer=False))
        obj = next(o for o in self.doc.Objects if getattr(o, "Family", None) == "Custom Profile")
        obj.Material = "Unavailable Library"
        edit = self._panel(obj)
        self._show(edit)
        before_image = edit.alignment_widget.grab().toImage()
        source = obj.CustomProfile
        source.addGeometry(Part.Circle(App.Vector(20, 5, 0), App.Vector(0, 0, 1), 3), False)
        self.doc.recompute()
        source_before = source.Shape.exportBrepToString()
        edit.update_image()
        self.assertNotEqual(edit.alignment_widget.grab().toImage(), before_image)
        self.assertEqual(source.Shape.exportBrepToString(), source_before)
        self.assertGreater(edit.alignment_widget.section_bounds.width(), 0)
        before = self._state(edit)
        with patch.object(App, "openDocument", side_effect=AssertionError("paint loaded catalog")):
            edit.alignment_widget.grab()
        self.assertEqual(self._state(edit), before)
        edit.reject()

    def test_native_loader_rebinds_recycled_named_widget_aliases(self):
        native_load = Gui.PySideUic.loadUi
        items = []
        def load_with_stale_aliases(path):
            form = native_load(path)
            if form.findChild(QtWidgets.QComboBox, "combo_family") is not None:
                # Reproduce the native alias types observed after repeated GUI
                # dialog destruction, while leaving the real QObject tree intact.
                for name in ("combo_family", "groupBox_4"):
                    item = QtWidgets.QWidgetItem(QtWidgets.QWidget())
                    items.append(item)
                    setattr(form, name, item)
            return form
        with patch.object(Gui.PySideUic, "loadUi", side_effect=load_with_stale_aliases):
            panel = self._panel()
        self.assertIsInstance(panel.form_proxy.combo_family, QtWidgets.QComboBox)
        self.assertIsInstance(panel.form[0].groupBox_4, QtWidgets.QGroupBox)
        self._click_anchor(panel, 2, 1)
        self.assertEqual(self.doc.Objects, [])

    def _files(self):
        result = {}
        for directory, _, files in os.walk(self.folder):
            for name in files:
                path = os.path.join(directory, name)
                with open(path, "rb") as stream:
                    result[os.path.relpath(path, self.folder)] = hashlib.sha256(stream.read()).hexdigest()
        return result

    def _state(self, panel):
        return (App.ActiveDocument.Name, tuple(sorted(App.listDocuments())),
                tuple((s.DocumentName, s.ObjectName, tuple(s.SubElementNames))
                      for s in Gui.Selection.getSelectionEx()),
                tuple((o.Name, o.Label, tuple(o.Placement.toMatrix().A),
                       o.Shape.exportBrepToString() if hasattr(o, "Shape") else None,
                       tuple((p, repr(getattr(o, p))) for p in
                             ("Material", "Family", "CatalogFamily", "SizeName", "ProfileLength",
                              "LinearWeight", "CustomProfile") if hasattr(o, p)))
                      for o in self.doc.Objects),
                get_param_group().GetContents(), self._files(),
                panel.form_proxy.label_apply_status.text(),
                panel.form_proxy.sb_length.value())

    def _show(self, panel, width=360):
        for form in panel.form:
            form.show()
            form.resize(width, form.sizeHint().height())
        self.app.processEvents()

    def _metadata(self, panel, code, description, weight):
        text = " ".join(w.text() for form in panel.form
                        for w in form.findChildren(QtWidgets.QLabel)
                        if w.isVisibleTo(form))
        self.assertIn(code, text)
        self.assertIn(description, text)
        self.assertIn(weight, text)
        self.assertIn("kg/m", text)

    def test_s2_s3_uncached_refresh_with_registered_selection_observer(self):
        path = self.doc.addObject("Part::Feature", "TwoEdges")
        path.Shape = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(100, 0, 0),
                                       App.Vector(100, 100, 0)])
        self.doc.recompute()
        panel = self._panel()
        Gui.Selection.addObserver(panel)
        # _close_panels calls clean before documents and locale are restored.
        for sub in ("Edge1", ""):
            with self.subTest(selection=sub or "whole object"):
                Gui.Selection.clearSelection()
                if sub:
                    Gui.Selection.addSelection(self.doc.Name, path.Name, sub)
                else:
                    Gui.Selection.addSelection(self.doc.Name, path.Name)
                self.app.processEvents()
                before = self._state(panel)
                enabled = panel.form_proxy.sb_length.isEnabled()
                for _ in range(2):
                    panel._thumbnail_cache.clear()
                    # The existing thumbnail inspector restores its temporary
                    # document/selection context. The additional 2D refresh must
                    # consume its cached face without touching either context.
                    panel.update_image()
                    with patch.object(Gui.Selection, "clearSelection", wraps=Gui.Selection.clearSelection) as clear, \
                            patch.object(App, "setActiveDocument", wraps=App.setActiveDocument) as activate, \
                            patch.object(App, "openDocument", side_effect=AssertionError("2D refresh loaded catalog")):
                        panel._refresh_alignment()
                        clear.assert_not_called()
                        activate.assert_not_called()
                    self.app.processEvents()
                    self.assertEqual(self._state(panel), before)
                    self.assertEqual(panel.form_proxy.sb_length.isEnabled(), enabled)

    def test_s1_native_language_cycle_preserves_canonical_family_and_state(self):
        for language, default, library, unit, family in (
                ("English", "es_ES", "Library", "Unit", "Square Hollow"),
                ("Spanish", "en_US", "Biblioteca", "Unidad", "Tubo Cuadrado Hueco"),
                ("English", "es_ES", "Library", "Unit", "Square Hollow")):
            with self.subTest(language=language, default=default):
                self._language(language, default)
                panel = self._panel()
                try:
                    combo = panel.form_proxy.combo_family
                    combo.setCurrentText("Square Hollow")
                    self.assertEqual(panel.form[0].label_10.text(), library)
                    self.assertEqual(panel.form[0].label_13.text(), unit)
                    self.assertEqual(combo.currentText(), "Square Hollow")
                    option = QtWidgets.QStyleOptionViewItem()
                    index = combo.model().index(combo.currentIndex(), combo.modelColumn())
                    combo.itemDelegate().initStyleOption(option, index)
                    self.assertEqual(option.text, family)
                    self.assertEqual(panel.form_proxy.sb_length.value(), 0)
                    before = self._state(panel)
                    panel.update_image()
                    self.app.processEvents()
                    self.assertEqual(self._state(panel), before)
                finally:
                    panel.reject()
                    panel.clean()
                    for form in panel.form:
                        form.close()
                    self.panels.remove(panel)

    def test_s2_selected_asset_and_metadata_refresh_without_import(self):
        panel = self._panel()
        self._show(panel)
        files = self._files()
        images = []
        for code, description, weight in (("WIDE", "Wide section", "1.25"),
                                           ("TALL", "Tall section", "2.5")):
            with self.subTest(code=code):
                panel.form_proxy.combo_size.setCurrentText(code)
                self.app.processEvents()
                self._metadata(panel, code, description, weight)
                pixmap = panel.form_proxy.label_image.pixmap()
                expected = render_custom_section_thumbnail(self.folder, "sections/%s.FCStd" % code,
                                                           "Section", pixmap.width(), pixmap.height())
                self.assertEqual(pixmap.toImage(), expected.toImage())
                images.append(pixmap.toImage())
                self.assertEqual(self.doc.Objects, [])
                self.assertEqual(App.ActiveDocument, self.doc)
                self.assertEqual(self._files(), files)
        if len(images) == 2:
            self.assertNotEqual(images[0], images[1])
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        expected = QtGui.QPixmap(os.path.join(PROFILEIMAGES_PATH, "Metal", "Square_Hollow.png"))
        self.assertEqual(panel.form_proxy.label_image.pixmap().toImage(), expected.toImage())
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        self._metadata(panel, "WIDE", "Wide section", "1.25")

    @unittest.skipUnless(os.environ.get("FF_REPORTS"), "Optional native visual captures require FF_REPORTS")
    def test_s2_s4_s6_visual_captures(self):
        self._language("English", "en_US")
        panel = self._panel()
        reports = os.environ["FF_REPORTS"]
        os.makedirs(reports, exist_ok=True)
        for code in ("WIDE", "TALL", "MISSING", "BROKEN"):
            panel.form_proxy.combo_size.setCurrentText(code)
            before = self._state(panel)
            for theme, surface, ink in (("light", "#eeeeee", "#204060"),
                                        ("dark", "#303030", "#e0d090")):
                panel.form[0].setStyleSheet("QLabel { background-color: %s; color: %s; }" % (surface, ink))
                for width in (360, 600):
                    self._show(panel, width)
                    self.assertTrue(panel.form[0].grab().save(os.path.join(
                        reports, "custom-preview-en-%s-%s-%s.png" % (code, theme, width)), "PNG"))
                    self.assertEqual(self._state(panel), before)

    def test_s2_missing_and_corrupt_assets_use_existing_placeholder(self):
        panel = self._panel()
        for code, path in (("MISSING", "sections/missing.FCStd"), ("BROKEN", "sections/broken.FCStd")):
            with self.subTest(code=code):
                panel.form_proxy.combo_size.setCurrentText(code)
                before = self._state(panel)
                panel.update_image()
                pixmap = panel.form_proxy.label_image.pixmap()
                expected = render_custom_section_thumbnail(self.folder, path, "Section",
                                                           pixmap.width(), pixmap.height())
                self.assertEqual(pixmap.toImage(), expected.toImage())
                self.assertEqual(self._state(panel), before)

    def test_s2_observational_refresh_preserves_initial_pending_and_applied_states(self):
        path = self.doc.addObject("Part::Feature", "Path")
        path.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(100, 0, 0))
        self.doc.recompute()
        Gui.Selection.addSelection(self.doc.Name, path.Name, "Edge1")
        # Selection is already present when initialization inspects the asset.
        panel = self._panel()
        for state in ("initial", "pending", "applied"):
            if state == "pending":
                panel.form_proxy.sb_length.setValue(500)
            elif state == "applied":
                self.assertTrue(panel.apply())
            before = self._state(panel)
            for width in (360, 600, 360):
                panel.update_image()
                self._show(panel, width)
                panel.form_proxy.label_image.grab()
            self.assertEqual(self._state(panel), before, state)
        panel.form_proxy.combo_size.setCurrentText("TALL")
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Pending changes")

    def test_s4_whole_standard_image_fits_without_stretch_or_crop(self):
        panel = self._panel()
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        label = panel.form_proxy.label_image
        # Distinct edge markers make clipping observable without depending on
        # bundled image artwork; setPixmap/pixmap remain the public QLabel API.
        source = QtGui.QPixmap(800, 200)
        source.fill(QtGui.QColor("#c03050"))
        painter = QtGui.QPainter(source)
        painter.fillRect(0, 0, 80, 200, QtGui.QColor("#20b040"))
        painter.fillRect(720, 0, 80, 200, QtGui.QColor("#3060d0"))
        painter.end()
        label.setPixmap(source)
        label.setStyleSheet("background-color: #ececec; border: none;")
        for width in (360, 600, 360):
            self._show(panel, width)
            image = label.grab().toImage()
            points = [(x, y) for y in range(image.height()) for x in range(image.width())
                      if image.pixelColor(x, y) == QtGui.QColor("#c03050")]
            self.assertTrue(points)
            ys = [p[1] for p in points]
            colored = [(x, y) for y in range(image.height()) for x in range(image.width())
                       if image.pixelColor(x, y).name() in ("#c03050", "#20b040", "#3060d0")]
            xs = [p[0] for p in colored]
            self.assertAlmostEqual((max(xs) - min(xs) + 1) / (max(ys) - min(ys) + 1), 4, delta=0.15)
            colors = {image.pixelColor(x, y).name() for x, y in colored}
            self.assertEqual(colors, {"#c03050", "#20b040", "#3060d0"})
            self.assertEqual(image.pixelColor(0, 0).name(), "#ececec")
            self.assertEqual(label.pixmap().toImage(), source.toImage())

    def test_s6_custom_geometry_uses_live_native_foreground(self):
        panel = self._panel()
        label = panel.form_proxy.label_image
        before = self._state(panel)
        captures = []
        for surface, ink in (("#eeeeee", "#204060"), ("#303030", "#e0d090"),
                             ("#eeeeee", "#204060")):
            panel.form[0].setStyleSheet("QLabel { background-color: %s; color: %s; }" % (surface, ink))
            label.style().unpolish(label)
            label.style().polish(label)
            self._show(panel)
            image = label.grab().toImage()
            native = label.palette().color(label.foregroundRole())
            self.assertEqual(native, QtGui.QColor(ink))
            pixels = [image.pixelColor(x, y) for y in range(image.height()) for x in range(image.width())]
            self.assertGreater(sum(color == native for color in pixels), 20)
            self.assertEqual(image.pixelColor(0, 0), QtGui.QColor(surface))
            captures.append(image)
            self.assertEqual(self._state(panel), before)
        self.assertNotEqual(captures[0], captures[1])
        self.assertEqual(captures[0], captures[2])

    def test_s2_preserve_edit_available_and_missing_custom_catalog(self):
        for material in ("Preview Library", "Unavailable Library"):
            with self.subTest(material=material):
                obj = self.doc.addObject("Part::FeaturePython", "Editable")
                obj.addExtension("Part::AttachExtensionPython")
                Profile(obj, 20, 80, 0, 0, 0, 0, 500, 2.5, 0, False,
                        1, 1, material, "Custom Profile", "TALL", False,
                        catalog_family="Custom Profile")
                self.doc.recompute()
                panel = self._panel(obj)
                before = self._state(panel)
                self._show(panel)
                panel.update_image()
                self.assertEqual(self._state(panel), before)
                self.assertEqual(panel.form_proxy.combo_size.currentText(), "TALL")
                self.assertFalse(panel.form_proxy.groupBox_5.isEnabled())
                self.assertTrue(panel.form_proxy.groupBox_apply.isHidden())
                pixmap = panel.form_proxy.label_image.pixmap()
                expected = render_custom_section_thumbnail(
                    self.folder if material == "Preview Library" else None,
                    "sections/TALL.FCStd", "Section", pixmap.width(), pixmap.height())
                self.assertEqual(pixmap.toImage(), expected.toImage())
                if material == "Preview Library":
                    self._metadata(panel, "TALL", "Tall section", "2.5")
                panel.form_proxy.sb_length.setValue(650)
                self.assertEqual(obj.ProfileLength, 650)
                self.assertEqual(obj.Material, material)
                self.doc.abortTransaction()
                for form in panel.form:
                    form.close()


if __name__ == "__main__":
    unittest.main()

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
from freecad.maxproframe.ff_tools import PROFILEIMAGES_PATH, get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.profile import Profile


class TestTaskPanelPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
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
                        reports, "custom-preview-%s-%s-%s.png" % (code, theme, width)), "PNG"))
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

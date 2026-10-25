"""Native task-panel acceptance tests for task-panel-usability T1 (not T2)."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.profile import Profile


class TestTaskPanelUsability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mpf_task_panel_")
        self.env = patch.dict(os.environ, {"FRAMEFORGE_USER_PROFILES_DIR": self.temp_dir})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir)
        self.manager = LibraryManager(user_dir=self.temp_dir)
        self.manager.save_user_library("Panel Library", {
            "_metadata": {"name": "Panel Library", "material": "Aluminium", "density": 2.7},
            "Square Hollow": {
                "canonical_family": "Square Hollow", "fillet": False,
                "norm": "ISO", "unit": "mm",
                "sizes": {"40x40x2": {"Height": "40", "Width": "40",
                                       "Thickness": "2", "Weight": "0.8"}},
            },
            "Custom Profile": {
                "canonical_family": "Custom Profile", "norm": "Custom", "unit": "mm",
                "sizes": {"PGC100": {"Weight": "1.2"}},
            },
        })
        self.doc = App.newDocument("TaskPanelUsability")
        self.addCleanup(App.closeDocument, self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self._close_panels)

    def _close_panels(self):
        for panel in self.panels:
            if hasattr(panel, "clean"):
                panel.clean()
            for form in panel.form:
                form.close()

    def _create(self):
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("Panel Library")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        return panel

    def _show(self, panel):
        for form in panel.form:
            form.show()
            form.resize(360, form.sizeHint().height())
        self.app.processEvents()

    def _assert_native_theme_response(self, panel):
        # WA_SetPalette can be set by FreeCAD's native QSS. Compare receivers
        # with native siblings through the same polish and theme lifecycle.
        fields = (panel.form_proxy.label_attach, panel.form_proxy.label_apply_status,
                  panel.action_guidance, panel.form[1].label_12)
        references = []
        original_styles = [form.styleSheet() for form in panel.form]
        observed_ink = []
        try:
            for field in fields:
                reference = QtWidgets.QLabel(field.text(), field.parentWidget())
                reference.setObjectName(field.objectName())
                reference.setFont(field.font())
                reference.setAlignment(field.alignment())
                reference.setWordWrap(field.wordWrap())
                reference.setTextFormat(field.textFormat())
                reference.setMargin(field.margin())
                reference.setIndent(field.indent())
                reference.setFrameStyle(field.frameStyle())
                reference.setLineWidth(field.lineWidth())
                reference.setMidLineWidth(field.midLineWidth())
                reference.setContentsMargins(field.contentsMargins())
                reference.setEnabled(field.isEnabled())
                reference.move(-10000, -10000)
                reference.show()
                references.append(reference)
            for dark in (False, True, False):
                background, ink = (("#303030", "#eeeeee") if dark
                                   else ("#eeeeee", "#202020"))
                for form in panel.form:
                    form.setStyleSheet("QLabel { background-color: %s; color: %s; }"
                                       % (background, ink))
                # Both receivers have identical ancestor QSS before re-polish.
                for field, reference in zip(fields, references):
                    for receiver in (field, reference):
                        receiver.style().unpolish(receiver)
                        receiver.style().polish(receiver)
                        receiver.ensurePolished()
                    reference.resize(field.size())
                self.app.processEvents()
                for field, reference in zip(fields, references):
                    with self.subTest(dark=dark, field=field.objectName()):
                        self.assertEqual(field.styleSheet(), "")
                        actual = field.palette().color(field.foregroundRole())
                        native = reference.palette().color(reference.foregroundRole())
                        surface = reference.palette().color(reference.backgroundRole())
                        self.assertEqual(actual, native)
                        self.assertEqual(field.grab().toImage(), reference.grab().toImage())
                        image = reference.grab().toImage()
                        self.assertGreater(len({image.pixel(x, y)
                                                for y in range(image.height())
                                                for x in range(image.width())}), 1,
                                           "Native text must render visibly, not as a blank surface")
                        def luminance(color):
                            channels = [color.redF(), color.greenF(), color.blueF()]
                            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                                      for v in channels]
                            return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
                        light, dark_value = sorted((luminance(native), luminance(surface)), reverse=True)
                        self.assertGreaterEqual((light + 0.05) / (dark_value + 0.05), 4.5)
                observed_ink.append(fields[0].palette().color(fields[0].foregroundRole()))
            self.assertNotEqual(observed_ink[0], observed_ink[1])
            self.assertEqual(observed_ink[0], observed_ink[2])
        finally:
            for form, style in zip(panel.form, original_styles):
                form.setStyleSheet(style)
            for reference in references:
                reference.close()
                reference.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(reference, QtCore.QEvent.DeferredDelete)
            self.app.processEvents()

    def _capture_forms(self, panel, language, state):
        reports = os.environ.get("FF_REPORTS")
        if not reports:
            return
        os.makedirs(reports, exist_ok=True)
        button = panel.form[1].findChild(QtWidgets.QToolButton, "button_advanced")
        was_expanded = button.isChecked()
        try:
            for expanded in (False, True):
                button.setChecked(expanded)
                for width in (360, 600):
                    for form in panel.form:
                        form.show()
                        form.layout().activate()
                        form.resize(width, form.sizeHint().height())
                    self.app.processEvents()
                    for index, form in enumerate(panel.form):
                        name = "task-panel-%s-%s-%s-%s-%s-actual-%s.png" % (
                            language, state, "expanded" if expanded else "collapsed",
                            width, "primary" if index == 0 else "secondary", form.width())
                        self.assertTrue(form.grab().save(os.path.join(reports, name), "PNG"))
        finally:
            button.setChecked(was_expanded)

    def _labels(self, panel):
        return [label.text() for form in panel.form
                for label in form.findChildren(QtWidgets.QLabel)]

    def _object_state(self, obj):
        # dumpContent is a ZIP archive with time-dependent header metadata.
        # Compare the actual public model, exact BREP and placement instead.
        properties = ("Label", "Material", "Family", "CatalogFamily", "SizeName",
                      "ProfileWidth", "ProfileHeight", "Thickness", "ThicknessFlange",
                      "RadiusLarge", "RadiusSmall", "ProfileLength", "LinearWeight",
                      "UnitPrice", "MakeFillet", "AnchorX", "AnchorY", "RotationAngle",
                      "MirrorH", "MirrorV", "MapMode", "AttachmentSupport", "Support")
        values = tuple((name, repr(getattr(obj, name))) for name in properties if hasattr(obj, name))
        shape = obj.Shape.exportBrepToString() if hasattr(obj, "Shape") else None
        placement = tuple(obj.Placement.toMatrix().A) if hasattr(obj, "Placement") else None
        return obj.Name, values, shape, placement

    def _snapshot(self):
        return ([self._object_state(obj) for obj in self.doc.Objects],
                get_param_group().GetContents())

    def _spanish(self):
        translator = QtCore.QTranslator()
        self.assertTrue(translator.load(os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")))
        self.app.installTranslator(translator)
        self.addCleanup(self.app.removeTranslator, translator)
        return translator

    def test_s1_library_material_and_custom_profile_labels(self):
        panel = self._create()
        before = self._snapshot()
        self.assertEqual(panel.form[0].label_10.text(), "Library")
        self.assertTrue(any("Aluminium" in text for text in self._labels(panel)),
                        "Show metadata material separately from the selected library")
        self.assertEqual(panel.form_proxy.combo_material.currentText(), "Panel Library")
        self.assertEqual(panel.form[0].label_2.text(), "Size")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        self.assertEqual(panel.form[0].label_2.text(), "Profile")
        self.assertEqual(panel.form_proxy.combo_size.currentText(), "PGC100")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        self.assertEqual(panel.form[0].label_2.text(), "Size")
        self.assertEqual(self._snapshot(), before)

    def test_s1_s3_manual_length_has_units_and_missing_requirement(self):
        panel = self._create()
        panel.form_proxy.sb_length.setValue(0)
        before = self._snapshot()
        panel.update_selection()
        self.assertEqual(panel.form_proxy.label_attach.text(), "Define a length")
        self.assertTrue(panel.form_proxy.sb_length.isEnabled())
        self.assertIn("mm", panel.form_proxy.sb_length.suffix())
        panel.form_proxy.sb_length.setValue(750)
        self.assertNotEqual(panel.form_proxy.label_attach.text(), "Define a length",
                            "A positive length must clear the missing-requirement instruction")
        self.assertEqual(panel.form_proxy.sb_length.value(), 750)
        self.assertEqual(self._snapshot(), before)

    def test_s3_selection_counts_edges_not_objects_and_exposes_details(self):
        path = self.doc.addObject("Part::Feature", "ThreeEdges")
        path.Shape = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(100, 0, 0),
                                       App.Vector(100, 100, 0), App.Vector(200, 100, 0)])
        self.doc.recompute()
        panel = self._create()
        before = self._snapshot()
        for sub, count in (("Edge1", 1), ("", 3)):
            with self.subTest(selection=sub or "whole object"):
                Gui.Selection.clearSelection()
                if sub:
                    Gui.Selection.addSelection(self.doc.Name, path.Name, sub)
                else:
                    Gui.Selection.addSelection(self.doc.Name, path.Name)
                panel.update_selection()
                expected = "1 edge selected" if count == 1 else "3 edges selected"
                self.assertEqual(panel.form_proxy.label_attach.text(), expected)
                self.assertIn(path.Name, panel.form_proxy.label_attach.toolTip())
                for index in range(1, count + 1):
                    self.assertIn("Edge%d" % index, panel.form_proxy.label_attach.toolTip())
                self.assertFalse(panel.form_proxy.sb_length.isEnabled())
                self.assertEqual(panel.form_proxy.sb_length.value(), 0)
                self.assertEqual(self._snapshot(), before)
        Gui.Selection.clearSelection()
        panel.update_selection()
        self.assertTrue(panel.form_proxy.sb_length.isEnabled())
        self.assertEqual(panel.form_proxy.label_attach.text(), "Define a length")

    def test_s3_shapeless_selection_guidance_does_not_mutate_or_raise(self):
        panel = self._create()
        shapeless = self.doc.addObject("App::FeaturePython", "NoShape")
        before = self._snapshot()
        Gui.Selection.addSelection(self.doc.Name, shapeless.Name)
        self.assertEqual([item.ObjectName for item in Gui.Selection.getSelectionEx()], [shapeless.Name])
        # Observing selection must remain safe; do not call Apply on unsupported
        # geometry or change creation's existing normalization/validation.
        panel.update_selection()
        self.assertEqual(panel.form_proxy.label_attach.text(), "0 edges selected")
        self.assertIn(shapeless.Name, panel.form_proxy.label_attach.toolTip())
        self.assertFalse(panel.form_proxy.sb_length.isEnabled())
        self.assertEqual(panel.form_proxy.sb_length.value(), 0)
        self.assertEqual(self._snapshot(), before)
        Gui.Selection.clearSelection()
        panel.update_selection()
        self.assertTrue(panel.form_proxy.sb_length.isEnabled())
        self.assertEqual(panel.form_proxy.label_attach.text(), "Define a length")
        self.assertEqual(self._snapshot(), before)

    @unittest.skipUnless(os.environ.get("FF_REPORTS"), "Optional native visual captures require FF_REPORTS")
    def test_s1_s4_s5_s6_visual_captures(self):
        catalog = self.manager.get_all_profiles()["Panel Library"]
        with patch.object(LibraryManager, "get_all_profiles", return_value={"Panel Library": catalog}):
            for language in ("en", "es"):
                translator = self._spanish() if language == "es" else None
                try:
                    panel = CreateProfileTaskPanel()
                    self.panels.append(panel)
                    panel.open()
                    before = self._snapshot()
                    self._capture_forms(panel, language, "initial")
                    self.assertEqual(self._snapshot(), before)
                    panel.form_proxy.combo_family.setCurrentText("Square Hollow")
                    panel.form_proxy.sb_length.setValue(500)
                    self._capture_forms(panel, language, "valid-pending")
                    self.assertEqual(self._snapshot(), before)
                    self.assertTrue(panel.apply())
                    before_preview = self._snapshot()
                    self._capture_forms(panel, language, "preview")
                    self.assertEqual(self._snapshot(), before_preview)
                    profile = next(obj for obj in self.doc.Objects if hasattr(obj, "ProfileLength"))
                    # Preserve the preview for an independent Edit session; no
                    # accept() call, preference writes or geometry auto-apply.
                    panel.clean()
                    self.doc.commitTransaction()
                    edit = EditProfileTaskPanel(profile)
                    self.panels.append(edit)
                    edit.open()
                    before_edit = self._snapshot()
                    self._capture_forms(edit, language, "edit")
                    self.assertEqual(self._snapshot(), before_edit)
                    self.doc.abortTransaction()
                    for form in edit.form + panel.form:
                        form.close()
                    # A separate document keeps each capture language isolated.
                    if language == "en":
                        self.doc = App.newDocument("TaskPanelUsabilitySpanish")
                        self.addCleanup(App.closeDocument, self.doc.Name)
                finally:
                    if translator is not None:
                        self.app.removeTranslator(translator)

    def test_s5_english_preview_states_and_action_guidance(self):
        panel = self._create()
        panel.form_proxy.sb_length.setValue(500)
        before = self._snapshot()
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Pending changes")
        guidance = " ".join(self._labels(panel)) + " " + panel.form_proxy.btn_apply.toolTip()
        for word in ("Apply", "OK", "Cancel"):
            self.assertIn(word, guidance)
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(panel.apply())
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Preview updated")
        panel.form_proxy.sb_length.setValue(600)
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Pending changes")
        self.assertTrue(panel.reject())
        self.assertEqual(self.doc.Objects, [])

    def test_s5_spanish_states_and_action_guidance(self):
        translator = self._spanish()  # Keep translator alive throughout widget checks.
        panel = self._create()
        Gui.Selection.clearSelection()
        panel.update_selection()
        self.assertEqual(panel.form[0].label_10.text(), "Biblioteca")
        self.assertEqual(panel.form_proxy.label_attach.text(), "Definí una longitud")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        self.assertEqual(panel.form[0].label_2.text(), "Perfil")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        # Opening a fresh panel, rather than private state setters, tests initial state.
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Sin previsualización")
        panel.form_proxy.combo_material.setCurrentText("Panel Library")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        panel.form_proxy.sb_length.setValue(500)
        before = self._snapshot()
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Cambios pendientes")
        guidance = " ".join(self._labels(panel)) + " " + panel.form_proxy.btn_apply.toolTip()
        for word in ("Aplicar", "OK", "Cancelar"):
            self.assertIn(word, guidance)
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(panel.apply())
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Previsualización actualizada")
        names = [obj.Name for obj in self.doc.Objects]
        panel.form_proxy.sb_length.setValue(600)
        self.assertEqual(panel.form_proxy.label_apply_status.text(), "Cambios pendientes")
        self.assertEqual([obj.Name for obj in self.doc.Objects], names)
        self.assertTrue(panel.reject())
        self.assertEqual(self.doc.Objects, [])

    def test_s4_s6_compact_native_primary_controls_and_advanced_disclosure(self):
        panel = self._create()
        before = self._snapshot()
        self._show(panel)
        self.assertLess(panel.form_proxy.label_image.minimumHeight(), 160)
        # Catalog selectors occupy form rows, not six vertically stacked items.
        for label, combo in ((panel.form[0].label_10, panel.form_proxy.combo_material),
                             (panel.form[0].label, panel.form_proxy.combo_family),
                             (panel.form[0].label_2, panel.form_proxy.combo_size)):
            self.assertLess(abs(label.mapToGlobal(QtCore.QPoint()).y() -
                                combo.mapToGlobal(QtCore.QPoint()).y()), combo.height())
        for widget in (panel.form_proxy.group_anchor, panel.form_proxy.combo_rotation):
            self.assertTrue(widget.isVisibleTo(panel.form[0]),
                            "Alignment and rotation belong in the expanded primary panel")
        naming = panel.form_proxy.cb_sketch_in_name
        price = panel.form_proxy.sb_unitprice
        for widget in (naming, panel.form_proxy.cb_family_in_name,
                       panel.form_proxy.cb_size_in_name,
                       panel.form_proxy.cb_prefix_profile_in_name, price):
            root = widget.window()
            self.assertFalse(widget.isVisibleTo(root), "Advanced controls start collapsed")
        self.assertTrue(panel.form_proxy.groupBox_5.isAncestorOf(naming))
        button = panel.form[1].findChild(QtWidgets.QToolButton, "button_advanced")
        self.assertIsNotNone(button)
        button.click()
        self.app.processEvents()
        self.assertTrue(naming.isVisibleTo(panel.form[1]))
        self.assertTrue(price.isVisibleTo(panel.form[1]))
        button.click()
        self.app.processEvents()
        self.assertFalse(naming.isVisibleTo(panel.form[1]))
        self.assertFalse(price.isVisibleTo(panel.form[1]))
        # Price basis may be on its label, suffix or tooltip, but not a made-up currency.
        price_context = price.suffix() + price.toolTip() + " ".join(self._labels(panel))
        self.assertTrue("/m" in price_context or "per metre" in price_context)
        for form in panel.form:
            for widget in [form] + form.findChildren(QtWidgets.QWidget):
                self.assertEqual(widget.styleSheet(), "", "Use inherited native styling")
        self._assert_native_theme_response(panel)
        self.assertEqual(self._snapshot(), before)

    def test_preserve_edit_live_updates_naming_membership_and_missing_catalog(self):
        for material in ("Panel Library", "Unavailable Library"):
            with self.subTest(material=material):
                obj = self.doc.addObject("Part::FeaturePython", "Editable")
                obj.addExtension("Part::AttachExtensionPython")
                Profile(obj, 40, 40, 2, 0, 0, 0, 500, 0.8, 12, False,
                        1, 1, material, "Square Hollow", "40x40x2", False,
                        catalog_family="Square Hollow")
                self.doc.recompute()
                panel = EditProfileTaskPanel(obj)
                self.panels.append(panel)
                panel.open()
                before = self._snapshot()
                self._show(panel)
                self.assertEqual(self._snapshot(), before)
                self.assertTrue(panel.form_proxy.groupBox_apply.isHidden())
                self.assertFalse(panel.form_proxy.groupBox_5.isEnabled())
                for name in ("cb_sketch_in_name", "cb_family_in_name", "cb_size_in_name",
                             "cb_prefix_profile_in_name"):
                    widget = getattr(panel.form_proxy, name)
                    self.assertTrue(panel.form_proxy.groupBox_5.isAncestorOf(widget))
                    self.assertFalse(widget.isEnabled())
                panel.form_proxy.sb_length.setValue(650)
                self.assertEqual(obj.ProfileLength, 650)
                self.assertEqual(obj.Material, material)
                self.assertEqual(obj.CatalogFamily, "Square Hollow")
                self.assertTrue(obj.Shape.isValid())
                self.doc.abortTransaction()


if __name__ == "__main__":
    unittest.main()

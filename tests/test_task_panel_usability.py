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
        self.temp_dir = tempfile.mkdtemp(prefix="mpf_task_panel_")
        self.env = patch.dict(os.environ, {"FRAMEFORGE_USER_PROFILES_DIR": self.temp_dir})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir)
        self.manager = LibraryManager(user_dir=self.temp_dir)
        self.manager.save_user_library(
            "Panel Library",
            {
                "_metadata": {"name": "Panel Library", "material": "Aluminium", "density": 2.7},
                "Square Hollow": {
                    "canonical_family": "Square Hollow",
                    "fillet": False,
                    "norm": "ISO",
                    "unit": "mm",
                    "sizes": {"40x40x2": {"Height": "40", "Width": "40", "Thickness": "2", "Weight": "0.8"}},
                },
                "Custom Profile": {
                    "canonical_family": "Custom Profile",
                    "norm": "Custom",
                    "unit": "mm",
                    "sizes": {"PGC100": {"Weight": "1.2"}},
                },
            },
        )
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
        fields = (
            panel.form[0].label_10,
            panel.material_info,
            panel.form_proxy.label_norm,
            panel.information_values["Height"],
        )
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
                background, ink = ("#303030", "#eeeeee") if dark else ("#eeeeee", "#202020")
                for form in panel.form:
                    form.setStyleSheet("QLabel { background-color: %s; color: %s; }" % (background, ink))
                # Both receivers have identical ancestor QSS before re-polish.
                for field, reference in zip(fields, references):
                    for receiver in (field, reference):
                        receiver.style().unpolish(receiver)
                        receiver.style().polish(receiver)
                        receiver.ensurePolished()
                self.app.processEvents()
                for field, reference in zip(fields, references):
                    # L9 decision (3): measure after the layout settles, not from the pre-layout size.
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
                        self.assertGreater(
                            len({image.pixel(x, y) for y in range(image.height()) for x in range(image.width())}),
                            1,
                            "Native text must render visibly, not as a blank surface",
                        )

                        def luminance(color):
                            channels = [color.redF(), color.greenF(), color.blueF()]
                            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
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
        button = panel.advanced_button
        information = panel.information_button
        was_expanded = button.isChecked()
        info_was_expanded = information.isChecked()
        try:
            for expanded in (False, True):
                button.setChecked(expanded)
                information.setChecked(expanded)
                for width in (360, 600):
                    for form in panel.form:
                        form.show()
                        form.layout().activate()
                        form.resize(width, form.sizeHint().height())
                    self.app.processEvents()
                    for index, form in enumerate(panel.form):
                        name = "task-panel-%s-%s-%s-%s-%s-actual-%s.png" % (
                            language,
                            state,
                            "expanded" if expanded else "collapsed",
                            width,
                            "primary" if index == 0 else "secondary",
                            form.width(),
                        )
                        self.assertTrue(form.grab().save(os.path.join(reports, name), "PNG"))
        finally:
            button.setChecked(was_expanded)
            information.setChecked(info_was_expanded)

    def _labels(self, panel):
        return [label.text() for form in panel.form for label in form.findChildren(QtWidgets.QLabel)]

    def _object_state(self, obj):
        # dumpContent is a ZIP archive with time-dependent header metadata.
        # Compare the actual public model, exact BREP and placement instead.
        properties = (
            "Label",
            "Material",
            "Family",
            "CatalogFamily",
            "SizeName",
            "ProfileWidth",
            "ProfileHeight",
            "Thickness",
            "ThicknessFlange",
            "RadiusLarge",
            "RadiusSmall",
            "ProfileLength",
            "LinearWeight",
            "UnitPrice",
            "MakeFillet",
            "AnchorX",
            "AnchorY",
            "RotationAngle",
            "MirrorH",
            "MirrorV",
            "MapMode",
            "AttachmentSupport",
            "Support",
        )
        values = tuple((name, repr(getattr(obj, name))) for name in properties if hasattr(obj, name))
        shape = obj.Shape.exportBrepToString() if hasattr(obj, "Shape") else None
        placement = tuple(obj.Placement.toMatrix().A) if hasattr(obj, "Placement") else None
        return obj.Name, values, shape, placement

    def _snapshot(self):
        return ([self._object_state(obj) for obj in self.doc.Objects], get_param_group().GetContents())

    def _language(self, language, default):
        self.prefs.SetString("Language", language)
        Gui.setLocale(language)
        Gui.updateLocale()
        QtCore.QLocale.setDefault(QtCore.QLocale(default))

    def _spanish(self):
        self._language("Spanish", "es_ES")

    def test_s1_library_material_and_custom_profile_labels(self):
        panel = self._create()
        before = self._snapshot()
        self.assertEqual(panel.form[0].label_10.text(), "Library")
        self.assertTrue(
            any("Aluminium" in text for text in self._labels(panel)),
            "Show metadata material separately from the selected library",
        )
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
        self.assertNotEqual(
            panel.form_proxy.label_attach.text(),
            "Define a length",
            "A positive length must clear the missing-requirement instruction",
        )
        self.assertEqual(panel.form_proxy.sb_length.value(), 750)
        self.assertEqual(len(self.doc.Objects), 1, "Live 3D preview must be generated when length is positive")
        self.assertEqual(self.doc.Objects[0].ProfileLength, 750)
        panel.form_proxy.sb_length.setValue(0)
        self.assertEqual(self._snapshot(), before, "Setting length back to 0 must clear live preview geometry")

    def test_s3_selection_counts_edges_not_objects_and_exposes_details(self):
        path = self.doc.addObject("Part::Feature", "ThreeEdges")
        path.Shape = Part.makePolygon(
            [App.Vector(0, 0, 0), App.Vector(100, 0, 0), App.Vector(100, 100, 0), App.Vector(200, 100, 0)]
        )
        self.doc.recompute()
        panel = self._create()
        before = self._snapshot()
        for sub, count in (("Edge1", 1), ("", 3)):
            with self.subTest(selection=sub or "whole object"):
                # L9 decision (2) "Se mantienen": clearing the 3D selection keeps panel edges, so use a fresh panel.
                panel.clean()
                Gui.Selection.clearSelection()
                panel = self._create()
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
        # L9 decision (2) "Se mantienen": edges leave the panel only through explicit removal.
        for key in list(panel._edge_properties):
            panel._on_edge_removed(key)
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
                self._language("Spanish" if language == "es" else "English", "es_ES" if language == "es" else "en_US")
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
                    preview_snapshot = self._snapshot()
                    self.assertGreater(len(self.doc.Objects), 0)
                    self._capture_forms(panel, language, "preview")
                    self.assertEqual(self._snapshot(), preview_snapshot)
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
                    self._close_panels()
                    self.panels.clear()
                    self._language("English", "en_US")

    def test_s5_english_preview_states_and_action_guidance(self):
        panel = self._create()
        self.assertTrue(
            panel.form_proxy.groupBox_apply.isHidden(), "Apply group box must be hidden in live preview mode."
        )
        panel.form_proxy.sb_length.setValue(500)
        self.app.processEvents()
        self.assertEqual(len(self.doc.Objects), 1, "Setting length must immediately generate live 3D preview.")
        self.assertEqual(self.doc.Objects[0].ProfileLength, 500)
        panel.form_proxy.sb_length.setValue(600)
        self.app.processEvents()
        self.assertEqual(len(self.doc.Objects), 1, "Modifying length must update existing preview without duplicating.")
        self.assertEqual(self.doc.Objects[0].ProfileLength, 600)
        self.assertTrue(panel.reject())
        self.assertEqual(self.doc.Objects, [], "Reject/Cancel must roll back all preview geometry cleanly.")

    def test_s5_spanish_states_and_action_guidance(self):
        self._spanish()
        panel = self._create()
        Gui.Selection.clearSelection()
        panel.update_selection()
        self.assertEqual(panel.form[0].label_10.text(), "Biblioteca")
        self.assertEqual(panel.form_proxy.label_attach.text(), "Definí una longitud")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        self.assertEqual(panel.form[0].label_2.text(), "Perfil")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        panel.form_proxy.combo_material.setCurrentText("Panel Library")
        self.assertTrue(panel.form_proxy.groupBox_apply.isHidden())
        panel.form_proxy.sb_length.setValue(500)
        self.app.processEvents()
        self.assertEqual(len(self.doc.Objects), 1, "Configuración válida debe generar previsualización 3D en vivo.")
        self.assertEqual(self.doc.Objects[0].ProfileLength, 500)
        panel.form_proxy.sb_length.setValue(600)
        self.app.processEvents()
        self.assertEqual(len(self.doc.Objects), 1, "Modificación debe actualizar el perfil existente.")
        self.assertEqual(self.doc.Objects[0].ProfileLength, 600)
        self.assertTrue(panel.reject())
        self.assertEqual(self.doc.Objects, [], "Cancelar debe descartar la previsualización limpiamente.")

    def test_s4_s6_compact_native_primary_controls_and_advanced_disclosure(self):
        panel = self._create()
        before = self._snapshot()
        self._show(panel)
        self.assertLess(panel.form_proxy.label_image.minimumHeight(), 160)
        # Catalog selectors occupy form rows, not six vertically stacked items.
        for label, combo in (
            (panel.form[0].label_10, panel.form_proxy.combo_material),
            (panel.form[0].label, panel.form_proxy.combo_family),
            (panel.form[0].label_2, panel.form_proxy.combo_size),
        ):
            self.assertLess(
                abs(label.mapToGlobal(QtCore.QPoint()).y() - combo.mapToGlobal(QtCore.QPoint()).y()), combo.height()
            )
        for widget in (
            panel.alignment_widget,
            panel.form_proxy.combo_rotation,
            panel.form_proxy.cb_mirror_h,
            panel.form_proxy.cb_mirror_v,
        ):
            self.assertTrue(
                widget.isVisibleTo(panel.form[0]),
                "Alignment widget, rotation and mirrors belong in the expanded primary placement panel",
            )
        for widget in (panel.form_proxy.group_anchor, panel.form_proxy.label_image):
            self.assertFalse(
                widget.isVisibleTo(panel.form[0]), "Duplicate anchor group and top preview image must be hidden"
            )
        naming = panel.form_proxy.cb_sketch_in_name
        price = panel.form_proxy.sb_unitprice
        for widget in (
            naming,
            panel.form_proxy.cb_family_in_name,
            panel.form_proxy.cb_size_in_name,
            panel.form_proxy.cb_prefix_profile_in_name,
            price,
            panel.form_proxy.cb_combined_bevel,
        ):
            root = widget.window()
            self.assertFalse(widget.isVisibleTo(root), "Advanced controls start collapsed")
        self.assertTrue(panel.form_proxy.groupBox_5.isAncestorOf(naming))
        form = panel.form[0]
        self.assertEqual(len(panel.form), 1)
        self.assertEqual(
            form.layout().indexOf(panel.information_group), form.layout().indexOf(panel.settings_group) + 1
        )
        button = panel.advanced_button
        button.click()
        self.app.processEvents()
        self.assertTrue(naming.isVisibleTo(form))
        self.assertTrue(price.isVisibleTo(form))
        button.click()
        self.app.processEvents()
        self.assertFalse(naming.isVisibleTo(form))
        self.assertFalse(price.isVisibleTo(form))
        self.assertFalse(panel.information_button.isChecked())
        self.assertFalse(panel.information_content.isVisibleTo(form))
        panel.information_button.setFocus()
        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            self.app.sendEvent(
                panel.information_button, QtGui.QKeyEvent(kind, QtCore.Qt.Key_Space, QtCore.Qt.NoModifier)
            )
        self.app.processEvents()
        self.assertTrue(panel.information_content.isVisibleTo(form))
        self.assertEqual(panel.information_values["Height"].text(), "40 mm")
        self.assertEqual(panel.information_values["Width"].text(), "40 mm")
        self.assertEqual(panel.information_values["Main Thickness"].text(), "2 mm")
        self.assertFalse(panel.information_values["Flange Thickness"].isVisibleTo(form))
        for value in panel.information_values.values():
            self.assertIsInstance(value, QtWidgets.QLabel)
            self.assertEqual(value.styleSheet(), "")
        for name in (
            "sb_height",
            "sb_width",
            "sb_main_thickness",
            "sb_flange_thickness",
            "sb_radius1",
            "sb_radius2",
            "cb_make_fillet",
        ):
            self.assertFalse(getattr(panel.form_proxy, name).isVisible())
        # Price basis may be on its label, suffix or tooltip, but not a made-up currency.
        price_context = price.suffix() + price.toolTip() + " ".join(self._labels(panel))
        self.assertTrue("/m" in price_context or "per metre" in price_context)
        for header in (panel.profile_button, panel.placement_button, button, panel.information_button):
            self.assertIn("palette(highlight)", header.styleSheet())
        self._assert_native_theme_response(panel)
        panel.information_button.click()
        self.assertFalse(panel.information_content.isVisibleTo(form))
        self.assertEqual(self._snapshot(), before)

    def test_information_catalog_family_semantics(self):
        panel = self._create()
        before = self._snapshot()
        cases = (
            (
                "Channels",
                {
                    "Height": "80",
                    "Width": "40",
                    "Thickness": "3",
                    "Flange Thickness": "4",
                    "Radius1": "8",
                    "Radius2": "2",
                },
                {"Height": "80 mm", "Width": "40 mm", "Main Thickness": "3 mm", "Flange Thickness": "4 mm"},
            ),
            ("Flat Sections", {"Height": "3", "Width": "40"}, {"Height": "3 mm", "Width": "40 mm"}),
            (
                "Unequal Leg Angles",
                {"Height": "80", "Width": "40", "Thickness": "3", "Radius1": "4", "Radius2": "2"},
                {
                    "Height": "80 mm",
                    "Width": "40 mm",
                    "Main Thickness": "3 mm",
                    "Large Radius": "4 mm",
                    "Small Radius": "2 mm",
                },
            ),
        )
        panel.information_button.setChecked(True)
        for family, entry, expected in cases:
            with self.subTest(family=family):
                panel.profiles["Panel Library"][family] = {
                    "canonical_family": family,
                    "fillet": False,
                    "sizes": {"example": entry},
                }
                panel.form_proxy.combo_family.addItem(family)
                panel.form_proxy.combo_family.setCurrentText(family)
                for name, label in panel.information_values.items():
                    self.assertEqual(label.isVisibleTo(panel.form[0]), name in expected, name)
                    if name in expected:
                        self.assertEqual(label.text(), expected[name])
                self.assertEqual(self._snapshot(), before)

    def test_preserve_edit_live_updates_naming_membership_and_missing_catalog(self):
        for material in ("Panel Library", "Unavailable Library"):
            with self.subTest(material=material):
                obj = self.doc.addObject("Part::FeaturePython", "Editable")
                obj.addExtension("Part::AttachExtensionPython")
                Profile(
                    obj,
                    40,
                    40,
                    2,
                    0,
                    0,
                    0,
                    500,
                    0.8,
                    12,
                    False,
                    1,
                    1,
                    material,
                    "Square Hollow",
                    "40x40x2",
                    False,
                    catalog_family="Square Hollow",
                )
                self.doc.recompute()
                panel = EditProfileTaskPanel(obj)
                self.panels.append(panel)
                panel.open()
                before = self._snapshot()
                self._show(panel)
                self.assertEqual(self._snapshot(), before)
                self.assertTrue(panel.form_proxy.groupBox_apply.isHidden())
                self.assertFalse(panel.form_proxy.groupBox_5.isEnabled())
                for name in ("cb_sketch_in_name", "cb_family_in_name", "cb_size_in_name", "cb_prefix_profile_in_name"):
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

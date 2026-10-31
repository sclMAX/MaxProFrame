"""The miter panel shows Spanish text when FreeCAD runs in Spanish."""

import unittest

import FreeCAD as App
from miter_helpers import keep_auto_preview, use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture

from freecad.maxproframe.create_end_miter_tool import EndMiterTaskPanel


class TestEndMiterTranslations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.doc = App.newDocument("EndMiterTranslations")
        self.addCleanup(App.closeDocument, self.doc.Name)
        App.setActiveDocument(self.doc.Name)

    def panel(self):
        panel = EndMiterTaskPanel()
        self.addCleanup(panel.clean)
        return panel.form

    def test_panel_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        form = self.panel()
        self.assertEqual(form.windowTitle(), "Ingletes")
        self.assertEqual(form.groupBox_members.title(), "Perfiles")
        self.assertEqual(form.hint_label.text(), "Hacé clic en los perfiles a unir en inglete (dos o más).")
        self.assertEqual(form.remove_button.text(), "Quitar")
        self.assertEqual(form.groupBox_options.title(), "Inglete")
        self.assertEqual(form.cb_extend.text(), "Extender los perfiles hasta el inglete")
        self.assertEqual(form.gap_label.text(), "Separación")
        self.assertEqual(form.message_label.text(), "Seleccioná dos o más perfiles para unir en inglete.")
        self.assertEqual(form.groupBox_preview.title(), "Previsualización")
        self.assertEqual(form.cb_auto_update.text(), "Actualizar automáticamente")
        self.assertEqual(form.status_label.text(), "Sin previsualización")

    def test_panel_text_stays_english_in_english(self):
        use_language(self, "English", "en_US")
        form = self.panel()
        self.assertEqual(form.windowTitle(), "Miter Ends")
        self.assertEqual(form.groupBox_members.title(), "Profiles")
        self.assertEqual(form.cb_extend.text(), "Extend profiles up to the miter")
        self.assertEqual(form.message_label.text(), "Select two or more profiles to miter.")


class TestEditEndMiterTranslations(MiterFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_preview_status_is_spanish(self):
        keep_auto_preview(self)
        sketches = [self.make_sketch(edge) for edge in CHAINED]
        members = [self.make_profile(sketch, "Edge1", **CENTER) for sketch in sketches]
        use_language(self, "Spanish", "es_ES")
        panel = EndMiterTaskPanel(members)
        self.addCleanup(panel.reject)
        form = panel.form
        self.assertEqual(form.status_label.text(), "Previsualización actualizada")
        form.cb_auto_update.setChecked(False)
        form.sb_gap.setValue(1.0)
        self.assertEqual(form.status_label.text(), "Cambios pendientes")

    def test_edit_panel_text_is_spanish(self):
        _, (m1, m2) = self.miter_pair(CHAINED, CENTER, CENTER)
        use_language(self, "Spanish", "es_ES")
        panel = EndMiterTaskPanel(edited=m1)
        self.addCleanup(panel.clean)
        form = panel.form
        self.assertEqual(form.windowTitle(), "Editar inglete")
        self.assertEqual(form.groupBox_members.title(), "Perfiles")
        self.assertEqual(form.hint_label.text(), "Perfil y límites de este inglete.")
        self.assertEqual(form.groupBox_options.title(), "Inglete")
        self.assertEqual(form.cb_extend.text(), "Extender los perfiles hasta el inglete")
        self.assertEqual(form.gap_label.text(), "Separación")
        self.assertTrue(form.message_label.text().startswith("Extender y Separación se aplican a "))

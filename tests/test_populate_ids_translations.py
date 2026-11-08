"""The Populate IDs panel shows Spanish text when FreeCAD runs in Spanish."""

import unittest

from miter_helpers import use_language
from PySide import QtWidgets

from freecad.maxproframe.populate_ids_tool import PopulateIDsTaskPanel


def combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


class TestPopulateIDsTranslations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_panel_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        form = PopulateIDsTaskPanel().form
        self.assertEqual(form.windowTitle(), "Asignar IDs")
        self.assertEqual(form.label.text(), "Tipo de numeración")
        self.assertEqual(
            combo_items(form.cb_numbering_type),
            [
                "Todo números",
                "Todo letras",
                "Números para perfiles, letras para enlaces",
                "Números para enlaces, letras para perfiles",
            ],
        )
        self.assertEqual(form.cb_allow_duplicated.text(), "Permitir IDs duplicados")
        self.assertEqual(form.cb_group_ids_for_identical.text(), "Mismo ID para piezas idénticas")
        self.assertEqual(
            form.cb_group_ids_for_identical.toolTip(), "Los perfiles idénticos y los enlaces idénticos comparten un ID"
        )
        self.assertEqual(form.cb_include_part_count_in_pid.text(), "Agregar la cantidad de piezas al ID")
        self.assertEqual(form.cb_keep_existing.text(), "Conservar los IDs existentes")
        self.assertEqual(
            form.cb_keep_existing.toolTip(), "Las piezas que ya tienen un ID lo conservan: solo se numeran las demás"
        )
        self.assertEqual(form.label_2.text(), "Esquema de numeración")
        self.assertEqual(
            combo_items(form.cb_numbering_scheme),
            [
                "Completar huecos (dentro de la selección)",
                "Completar huecos (todo el documento)",
                "Continuar después del último ID del documento",
                "Empezar en un número o letra",
            ],
        )
        self.assertEqual(form.groupBox.title(), "Valores iniciales")
        self.assertEqual(form.label_3.text(), "Número inicial")
        self.assertEqual(form.label_4.text(), "Letra inicial")
        self.assertEqual(form.label_5.text(), "Prefijo de perfiles")
        self.assertEqual(form.label_6.text(), "Prefijo de enlaces")

    def test_panel_text_stays_english_in_english(self):
        use_language(self, "English", "en_US")
        form = PopulateIDsTaskPanel().form
        self.assertEqual(form.windowTitle(), "Populate IDs")
        self.assertEqual(form.label.text(), "Numbering Type")
        self.assertEqual(combo_items(form.cb_numbering_type)[3], "Numbers for Links, Letters for Profiles")
        self.assertEqual(form.label_2.text(), "Numbering Scheme")
        self.assertEqual(form.cb_allow_duplicated.text(), "Allow duplicated")
        self.assertEqual(form.cb_keep_existing.text(), "Keep existing IDs")


if __name__ == "__main__":
    unittest.main()

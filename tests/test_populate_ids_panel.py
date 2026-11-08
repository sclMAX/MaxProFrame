"""Populate IDs: start values the panel accepts and the numbering inside the selection."""

import unittest
from types import SimpleNamespace

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.populate_ids_tool import PopulateIDsTaskPanel

NUMBERING_TYPES = ["all_numbers", "all_letters"]
START_AT = 3  # index of "Start at specific number/letter"


def profile(pid=""):
    return SimpleNamespace(PID=pid, TypeId="Part::FeaturePython")


class TestFillSelection(unittest.TestCase):
    def fill(self, selected, document=(), reset=False):
        populate_ids(
            selected, [], [*document, *selected], [], "all_numbers", False, False, False, reset, "fill_selection"
        )
        return [o.PID for o in selected]

    def test_numbered_selection_keeps_its_numbers(self):
        self.assertEqual(self.fill([profile("1"), profile("2"), profile("3")]), ["1", "2", "3"])

    def test_reset_selection_numbers_from_one(self):
        self.assertEqual(self.fill([profile("5"), profile("9")], reset=True), ["1", "2"])

    def test_ids_outside_the_selection_are_not_reserved(self):
        outside = profile("1")
        self.assertEqual(self.fill([profile(), profile()], document=[outside]), ["1", "2"])
        self.assertEqual(outside.PID, "1")


class TestPopulateIDsPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        param = get_param_group(writable=True)
        saved = {
            "ints": {k: param.GetInt(k) for k in ("First Number ID", "IDs numbering type", "IDs numbering scheme")},
            "letter": param.GetString("First Letter ID", "A"),
        }
        stored = set(param.GetInts())

        def restore():
            for key, value in saved["ints"].items():
                if key in stored:
                    param.SetInt(key, value)
                else:
                    param.RemInt(key)
            param.SetString("First Letter ID", saved["letter"])

        self.addCleanup(restore)
        self.doc = App.newDocument("PopulateIDsPanel")
        self.addCleanup(App.closeDocument, self.doc.Name)
        App.setActiveDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        self.link = self.doc.addObject("App::Link", "Link")
        self.link.LinkedObject = box
        self.doc.recompute()
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        Gui.Selection.addSelection(self.link)

    def panel(self, numbering_type, letter="A"):
        panel = PopulateIDsTaskPanel()
        panel.form.cb_numbering_type.setCurrentIndex(NUMBERING_TYPES.index(numbering_type))
        panel.form.cb_numbering_scheme.setCurrentIndex(START_AT)
        panel.form.cb_allow_duplicated.setChecked(False)
        panel.form.cb_group_ids_for_identical.setChecked(False)
        panel.form.cb_reset_numbering.setChecked(False)
        panel.form.le_first_letter.setText(letter)
        panel.open()
        self.addCleanup(lambda: self.doc.HasPendingTransaction and self.doc.abortTransaction())
        return panel

    def test_first_number_cannot_be_zero(self):
        get_param_group(writable=True).SetInt("First Number ID", 0)
        panel = self.panel("all_numbers")
        self.assertEqual(panel.form.sp_first_number.value(), 1)
        panel.form.sp_first_number.setValue(0)
        self.assertEqual(panel.form.sp_first_number.value(), 1)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "1")
        self.assertEqual(panel.form.message_label.text(), "")

    def test_invalid_first_letter_is_refused(self):
        for letter in ("", "  "):
            with self.subTest(letter=letter):
                panel = self.panel("all_letters", letter)
                self.assertFalse(panel.accept())
                # Refused before anything is written: the link does not even get a PID.
                self.assertFalse(hasattr(self.link, "PID"))
                self.assertEqual(panel.form.message_label.text(), "Enter a first letter: A to Z only.")
                self.assertTrue(panel.form.message_label.isVisibleTo(panel.form))
                self.doc.abortTransaction()

    def test_letter_field_takes_letters_only(self):
        panel = self.panel("all_letters")
        field = panel.form.le_first_letter
        field.clear()
        for char in "A1b":
            QtWidgets.QApplication.sendEvent(field, _key_text(char))
        self.assertEqual(field.text(), "Ab")

    def test_valid_first_letter_still_numbers(self):
        panel = self.panel("all_letters", "c")
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "C")

    def test_number_is_used_when_letters_are_not(self):
        panel = self.panel("all_numbers", "")
        panel.form.sp_first_number.setValue(4)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "4")


def _key_text(text):
    from PySide import QtCore, QtGui

    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, 0, QtCore.Qt.NoModifier, text)


if __name__ == "__main__":
    unittest.main()

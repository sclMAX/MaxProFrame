"""Populate IDs: start values the panel accepts and the numbering inside the selection."""

import unittest
from types import SimpleNamespace

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.populate_ids_tool import PopulateIDsTaskPanel

NUMBERING_TYPES = ["all_numbers", "all_letters", "number_for_profiles_letters_for_links"]
PREFIXES = ("Profiles Prefix", "Links Prefix")
START_AT = 3  # index of "Start at specific number/letter"
FILL_DOCUMENT = 1  # index of "Fill when available (whole document)"


def profile(pid=""):
    return SimpleNamespace(PID=pid, TypeId="Part::FeaturePython")


class TestFillSelection(unittest.TestCase):
    def fill(self, selected, document=(), keep=False):
        populate_ids(
            selected, [], [*document, *selected], [], "all_numbers", False, False, False, keep, "fill_selection"
        )
        return [o.PID for o in selected]

    def test_numbered_selection_keeps_its_numbers(self):
        self.assertEqual(self.fill([profile("1"), profile("2"), profile("3")]), ["1", "2", "3"])

    def test_selection_is_numbered_again_from_one(self):
        self.assertEqual(self.fill([profile("5"), profile("9")]), ["1", "2"])

    def test_ids_outside_the_selection_are_not_reserved(self):
        outside = profile("1")
        self.assertEqual(self.fill([profile(), profile()], document=[outside]), ["1", "2"])
        self.assertEqual(outside.PID, "1")


def identical(pid=""):
    return SimpleNamespace(
        PID=pid, TypeId="Part::FeaturePython", CustomProfile=None, Family="Square Hollow",
        Length=SimpleNamespace(Value=100.0), Material="Metal", SizeName="20x20",
        CuttingAngleA="0", CuttingAngleB="0", Cutout=False,
    )  # fmt: skip


class TestKeepExistingIDs(unittest.TestCase):
    def populate(self, selected, scheme, document=(), links=(), grouped=False, allow_duplicated=False):
        populate_ids(
            selected, list(links), [*document, *selected], list(links), "all_numbers",
            allow_duplicated, grouped, grouped, True, scheme, start_number="1",
        )  # fmt: skip
        return [o.PID for o in selected]

    def test_only_unnumbered_pieces_are_numbered_inside_the_selection(self):
        self.assertEqual(
            self.populate([profile("1"), profile(), profile("3"), profile()], "fill_selection"), ["1", "2", "3", "4"]
        )

    def test_kept_ids_and_the_document_are_reserved(self):
        for scheme, expected in (
            ("fill_document", ["5", "1", "3"]),
            ("continue_document", ["5", "6", "7"]),
            ("start_at", ["5", "1", "3"]),
        ):
            with self.subTest(scheme=scheme):
                outside = profile("2")
                self.assertEqual(self.populate([profile("5"), profile(), profile()], scheme, [outside]), expected)
                self.assertEqual(outside.PID, "2")

    def test_links_are_kept_too(self):
        kept, empty = profile("1"), profile()
        self.populate([], "fill_selection", links=[kept, empty])
        self.assertEqual([kept.PID, empty.PID], ["1", "2"])

    def test_grouped_unnumbered_pieces_share_the_next_free_id(self):
        numbered = identical("1 x1")
        twins = [identical(), identical()]
        self.assertEqual(self.populate([numbered, *twins], "fill_selection", grouped=True), ["1 x1", "2 x2", "2 x2"])

    def test_kept_ids_stay_when_duplicates_are_allowed(self):
        self.assertEqual(self.populate([profile("1"), profile()], "fill_selection", allow_duplicated=True), ["1", "1"])


class TestPopulateIDsPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        param = get_param_group(writable=True)
        saved = {
            "ints": {k: param.GetInt(k) for k in ("First Number ID", "IDs numbering type", "IDs numbering scheme")},
            "letter": param.GetString("First Letter ID", "A"),
            "keep": param.GetBool("Keep Existing IDs", False),
            "prefixes": {k: param.GetString(k, "") for k in PREFIXES},
        }
        stored = set(param.GetInts())
        stored_strings = set(param.GetStrings())

        def restore():
            for key, value in saved["ints"].items():
                if key in stored:
                    param.SetInt(key, value)
                else:
                    param.RemInt(key)
            param.SetString("First Letter ID", saved["letter"])
            param.SetBool("Keep Existing IDs", saved["keep"])
            for key, value in saved["prefixes"].items():
                if key in stored_strings:
                    param.SetString(key, value)
                else:
                    param.RemString(key)

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
        panel.form.cb_keep_existing.setChecked(False)
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

    def test_keep_existing_ids_from_the_panel(self):
        self.link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = "7"
        panel = self.panel("all_numbers")
        panel.form.cb_keep_existing.setChecked(True)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "7")
        self.assertTrue(get_param_group().GetBool("Keep Existing IDs", False))
        self.assertTrue(PopulateIDsTaskPanel().form.cb_keep_existing.isChecked())

    def test_number_is_used_when_letters_are_not(self):
        panel = self.panel("all_numbers", "")
        panel.form.sp_first_number.setValue(4)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "4")

    def add_link(self, name, pid=None):
        link = self.doc.addObject("App::Link", name)
        link.LinkedObject = self.link.LinkedObject
        if pid is not None:
            link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = pid
        self.doc.recompute()
        return link

    def test_selection_changed_while_open_is_ignored(self):
        other = self.add_link("Other")
        panel = self.panel("all_numbers")
        panel.form.sp_first_number.setValue(1)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(other)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "1")
        self.assertFalse(hasattr(other, "PID"))
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_ok_with_an_invalid_or_empty_selection_numbers_the_opening_selection(self):
        self.doc.UndoMode = 1
        self.link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = "5"
        for name, selected in (("invalid", self.link.LinkedObject), ("empty", None)):
            with self.subTest(selection=name):
                self.doc.clearUndos()
                panel = self.panel("all_numbers")
                panel.form.sp_first_number.setValue(1)
                Gui.Selection.clearSelection()
                if selected:
                    Gui.Selection.addSelection(selected)
                self.assertTrue(panel.accept())
                self.assertEqual(self.link.PID, "1")
                self.assertFalse(self.doc.HasPendingTransaction)
                self.assertEqual(self.doc.UndoCount, 1)
                self.doc.undo()
                self.assertEqual(self.link.PID, "5")
                Gui.Selection.addSelection(self.link)

    def test_undo_restores_the_previous_ids_in_one_step(self):
        self.doc.UndoMode = 1
        self.link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = "5"
        self.doc.clearUndos()
        panel = self.panel("all_numbers")
        panel.form.sp_first_number.setValue(1)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "1")
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.link.PID, "5")

    def test_only_selected_links_get_a_pid_property(self):
        other = self.add_link("Other")
        panel = self.panel("all_numbers")
        panel.form.sp_first_number.setValue(1)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "1")
        self.assertTrue(hasattr(self.link, "MaxProFrameVersion"))
        self.assertFalse(hasattr(other, "PID"))
        self.assertFalse(hasattr(other, "MaxProFrameVersion"))

    def test_prefix_fields_are_enabled_and_trimmed(self):
        panel = self.panel("number_for_profiles_letters_for_links")
        self.assertTrue(panel.form.le_profiles_prefix.isEnabled())
        self.assertTrue(panel.form.le_links_prefix.isEnabled())
        panel.form.le_profiles_prefix.setText("P")
        panel.form.le_links_prefix.setText("  L- ")
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "L-A")

    def test_prefixes_are_remembered(self):
        panel = self.panel("all_numbers")
        panel.form.le_profiles_prefix.setText(" P-")
        panel.form.le_links_prefix.setText("L")
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "L1")
        self.assertEqual([get_param_group().GetString(k, "") for k in PREFIXES], ["P-", "L"])
        form = PopulateIDsTaskPanel().form
        self.assertEqual([form.le_profiles_prefix.text(), form.le_links_prefix.text()], ["P-", "L"])

    def test_prefix_ending_in_a_letter_or_digit_of_its_numbering_is_refused(self):
        param = get_param_group(writable=True)
        for numbering_type, profiles_prefix, links_prefix in (
            ("all_numbers", "", "L1"),
            ("all_numbers", "P7 ", "L-"),
            ("all_letters", "P-", "l"),
            ("number_for_profiles_letters_for_links", "P", "L"),
        ):
            with self.subTest(numbering_type=numbering_type, prefixes=(profiles_prefix, links_prefix)):
                for key in PREFIXES:
                    param.SetString(key, "")
                panel = self.panel(numbering_type)
                panel.form.le_profiles_prefix.setText(profiles_prefix)
                panel.form.le_links_prefix.setText(links_prefix)
                self.assertFalse(panel.accept())
                # Refused before anything is written: the link does not even get a PID.
                self.assertFalse(hasattr(self.link, "PID"))
                self.assertEqual([param.GetString(k, "") for k in PREFIXES], ["", ""])
                self.assertEqual(
                    panel.form.message_label.text(),
                    "A prefix cannot end in a letter when its IDs use letters, or in a digit when they use numbers.",
                )
                self.assertTrue(panel.form.message_label.isVisibleTo(panel.form))
                self.doc.abortTransaction()

    def test_number_prefix_ending_in_a_count_mark_is_refused(self):
        # "P x" + "3" would read back as P with a count of 3: the 3 would not be reserved.
        param = get_param_group(writable=True)
        for numbering_type, profiles_prefix, links_prefix in (
            ("all_numbers", "P x", ""),
            ("all_numbers", "P-", " L x "),
            ("number_for_profiles_letters_for_links", "P x", "L-"),
        ):
            with self.subTest(numbering_type=numbering_type, prefixes=(profiles_prefix, links_prefix)):
                for key in PREFIXES:
                    param.SetString(key, "")
                panel = self.panel(numbering_type)
                panel.form.le_profiles_prefix.setText(profiles_prefix)
                panel.form.le_links_prefix.setText(links_prefix)
                self.assertFalse(panel.accept())
                self.assertFalse(hasattr(self.link, "PID"))
                self.assertEqual([param.GetString(k, "") for k in PREFIXES], ["", ""])
                self.assertEqual(
                    panel.form.message_label.text(),
                    'A prefix cannot end in " x" when its IDs use numbers: "P x" + "3" reads back as P with a count of 3.',
                )
                self.assertTrue(panel.form.message_label.isVisibleTo(panel.form))
                self.doc.abortTransaction()

    def test_number_prefix_ending_in_a_capital_x_is_accepted(self):
        # The count is written " x3" in lowercase only: "L X3" cannot be read as a count.
        panel = self.panel("all_numbers")
        panel.form.le_links_prefix.setText("L X")
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "L X1")

    def test_ids_of_links_outside_the_selection_are_still_reserved(self):
        other = self.add_link("Other", pid="1")
        panel = self.panel("all_numbers")
        panel.form.cb_numbering_scheme.setCurrentIndex(FILL_DOCUMENT)
        self.assertTrue(panel.accept())
        self.assertEqual(self.link.PID, "2")
        self.assertEqual(other.PID, "1")


def _key_text(text):
    from PySide import QtCore, QtGui

    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, 0, QtCore.Qt.NoModifier, text)


if __name__ == "__main__":
    unittest.main()

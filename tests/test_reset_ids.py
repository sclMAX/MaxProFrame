"""Reset IDs: asks before clearing, reports what it cleared, and a cleared ID stays cleared on trims and cutouts."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import test_extruded_cutout_pid as cutout_fixture
import test_trimmed_profile_pid as trimmed_fixture

from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.populate_ids_tool import QtGui, ResetIDsCommand

QMessageBox = QtGui.QMessageBox


class ResetIDsChecks:
    def reset(self, *objs, answer=QMessageBox.Yes):
        """Run Reset IDs on ``objs``; return the confirmation texts asked and the Report view messages."""
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        for obj in objs:
            Gui.Selection.addSelection(obj)
        asked, printed = [], []

        def question(parent, title, text, *args):
            asked.append((title, text))
            return answer

        with (
            patch.object(QMessageBox, "question", side_effect=question),
            patch.object(App.Console, "PrintMessage", side_effect=printed.append),
        ):
            ResetIDsCommand().Activated()
        return asked, "".join(printed)

    def status_message(self):
        return Gui.getMainWindow().statusBar().currentMessage()

    def bom_id(self, obj):
        profiles, links = [], []
        traverse_assembly(profiles, links, obj)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(links, [])
        return profiles[0]["ID"]

    def recompute(self):
        self.base.touch()
        self.derived.touch()
        self.doc.recompute()
        self.assertEqual(self.base.getStatusString(), "Valid")
        self.assertEqual(self.derived.getStatusString(), "Valid")

    def test_reset_id_stays_cleared_after_recompute_and_in_bom(self):
        self.assertEqual(self.derived.PID, "42")
        self.reset(self.derived)
        self.assertEqual(self.derived.PID, "")
        self.assertEqual(self.bom_id(self.derived), "")
        self.recompute()
        self.assertEqual(self.derived.PID, "")
        self.assertEqual(self.bom_id(self.derived), "")
        # Cleared at the source profile, as Populate IDs sets it there.
        self.assertEqual(self.base.PID, "")

    def test_asks_before_clearing_with_the_count(self):
        asked, _ = self.reset(self.derived)
        self.assertEqual(len(asked), 1)
        title, text = asked[0]
        self.assertEqual(title, "Reset IDs")
        # The trim or cutout and its source profile both lose ID 42.
        self.assertEqual(text, "Reset the IDs of the selection?\n\nIDs to clear: 2. Undo (Ctrl+Z) restores them.")

    def test_declined_confirmation_changes_nothing(self):
        undo_count = self.doc.UndoCount
        asked, printed = self.reset(self.derived, answer=QMessageBox.No)
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.derived.PID, "42")
        self.assertEqual(self.base.PID, "42")
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertEqual(printed, "")

    def test_reports_what_it_cleared(self):
        _, printed = self.reset(self.derived)
        self.assertEqual(
            printed,
            f"Reset IDs: IDs cleared: 2.\n  {self.derived.Label}: 42\n  {self.base.Label}: 42\n",
        )
        self.assertEqual(self.status_message(), "IDs cleared: 2 (Ctrl+Z to undo)")

    def link(self, name, pid=None):
        """A link to a box; ``pid`` None leaves it without PID, as before Populate IDs ever numbered it."""
        box = self.doc.addObject("Part::Box", f"{name}Box")
        link = self.doc.addObject("App::Link", name)
        link.LinkedObject = box
        if pid is not None:
            link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = pid
        self.doc.recompute()
        return link

    def test_selected_links_are_counted_and_reported(self):
        numbered, never_numbered = self.link("Numbered", "L1"), self.link("NeverNumbered")
        undo_count = self.doc.UndoCount
        asked, printed = self.reset(self.derived, numbered, never_numbered)
        question = "Reset the IDs of the selection?\n\nIDs to clear: 3. Undo (Ctrl+Z) restores them."
        self.assertEqual(asked, [("Reset IDs", question)])
        self.assertEqual(
            printed,
            f"Reset IDs: IDs cleared: 3.\n  {self.derived.Label}: 42\n  {self.base.Label}: 42\n  {numbered.Label}: L1\n",
        )
        self.assertEqual(self.status_message(), "IDs cleared: 3 (Ctrl+Z to undo)")
        self.assertEqual([self.derived.PID, self.base.PID, numbered.PID], ["", "", ""])
        self.assertNotIn("PID", never_numbered.PropertiesList)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoCount, undo_count + 1)

    def test_selection_without_ids_neither_asks_nor_changes(self):
        self.reset(self.derived)
        undo_count = self.doc.UndoCount
        asked, printed = self.reset(self.derived)
        self.assertEqual(asked, [])
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertEqual(printed, "Reset IDs: the selection has no IDs to reset.\n")
        self.assertEqual(self.status_message(), "The selection has no IDs to reset.")

    def test_undo_restores_the_ids_in_one_step(self):
        self.reset(self.derived)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.derived.PID, "42")
        self.assertEqual(self.base.PID, "42")

    def test_plain_profile_reset_still_reaches_bom(self):
        self.reset(self.base)
        self.assertEqual(self.base.PID, "")
        self.assertEqual(self.bom_id(self.base), "")


class TestResetTrimmedID(ResetIDsChecks, unittest.TestCase):
    def setUp(self):
        trimmed_fixture.TestTrimmedProfilePID.setUp(self)
        self.derived = self.trimmed


class TestResetCutoutID(ResetIDsChecks, unittest.TestCase):
    def setUp(self):
        cutout_fixture.TestExtrudedCutoutPID.setUp(self)
        self.derived = self.cutout


if __name__ == "__main__":
    unittest.main()

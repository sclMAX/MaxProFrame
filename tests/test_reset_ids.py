"""Reset IDs: a cleared ID stays cleared on trims and cutouts, after a recompute and in the BOM."""

import unittest

import FreeCADGui as Gui
import test_extruded_cutout_pid as cutout_fixture
import test_trimmed_profile_pid as trimmed_fixture

from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.populate_ids_tool import ResetIDsCommand


class ResetIDsChecks:
    def reset(self, obj):
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        Gui.Selection.addSelection(obj)
        ResetIDsCommand().Activated()

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

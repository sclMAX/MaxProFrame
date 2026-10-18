import unittest

from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.populate_ids import populate_ids

import test_extruded_cutout_pid as cutout_fixture
import test_trimmed_profile_pid as trimmed_fixture


class DerivedPIDChecks:
    def populate(self, obj, grouped):
        populate_ids(
            [obj], [], [self.base], [], "all_numbers", False, grouped, grouped,
            False, "start_at", start_number="7",
        )

    def bom_id(self, obj):
        profiles, links = [], []
        traverse_assembly(profiles, links, obj)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(links, [])
        return profiles[0]["ID"]

    def geometry_snapshot(self):
        return [
            (obj, obj.Shape.copy(), obj.Placement.toMatrix().A, obj.Shape.exportBrepToString())
            for obj in (self.base, self.derived)
        ]

    def assert_geometry_unchanged(self, before, recomputed=False):
        for obj, shape, placement, brep in before:
            self.assertIn(obj.getStatusString(), ("Valid", "Touched"))
            self.assertTrue(obj.Shape.isValid())
            if recomputed:
                self.assertAlmostEqual(obj.Shape.Volume, shape.Volume, places=6)
                self.assertAlmostEqual(obj.Shape.Area, shape.Area, places=6)
                self.assertLess(obj.Shape.cut(shape).Volume, 1e-6)
                self.assertLess(shape.cut(obj.Shape).Volume, 1e-6)
            else:
                self.assertEqual(obj.Shape.exportBrepToString(), brep)
            self.assertEqual(obj.Placement.toMatrix().A, placement)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_grouped_pid_is_available_in_bom_without_recompute(self):
        before = self.geometry_snapshot()
        self.populate(self.derived, grouped=True)
        self.assertEqual(self.base.PID, "7 x1")
        self.assertEqual(self.derived.PID, "7 x1")
        self.assertEqual(self.bom_id(self.derived), "7 x1")
        self.assert_geometry_unchanged(before)

    def test_ungrouped_pid_survives_recompute_and_bom(self):
        before = self.geometry_snapshot()
        self.populate(self.derived, grouped=False)
        self.assertEqual(self.derived.PID, "7")
        self.assertEqual(self.bom_id(self.derived), "7")
        self.derived.touch()
        self.doc.recompute()
        self.assertEqual(self.derived.PID, "7")
        self.assertEqual(self.base.PID, "7")
        self.assertEqual(self.bom_id(self.derived), "7")
        self.assert_geometry_unchanged(before, recomputed=True)

    def test_plain_profile_assignment_still_reaches_bom(self):
        for grouped, expected in ((True, "7 x1"), (False, "7")):
            with self.subTest(grouped=grouped):
                self.populate(self.base, grouped)
                self.assertEqual(self.base.PID, expected)
                self.assertEqual(self.bom_id(self.base), expected)


class TestPopulateTrimmedPID(DerivedPIDChecks, unittest.TestCase):
    def setUp(self):
        trimmed_fixture.TestTrimmedProfilePID.setUp(self)
        self.derived = self.trimmed


class TestPopulateCutoutPID(DerivedPIDChecks, unittest.TestCase):
    def setUp(self):
        cutout_fixture.TestExtrudedCutoutPID.setUp(self)
        self.derived = self.cutout


if __name__ == "__main__":
    unittest.main()

"""KeepEnd: which piece Extend Cut and Notch keep when the target crosses the profile between its ends."""

import unittest
from unittest import mock

import FreeCAD as App
from test_end_miter_geometry import CENTER
from test_extend_cut_geometry import FAR, NEAR, ExtendCutFixture

from freecad.maxproframe.create_notch_tool import make_notch_profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile

HALF = 25.0


class TestExtendCutKeepEnd(ExtendCutFixture):
    def keep(self, obj, keep_end):
        obj.KeepEnd = keep_end
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj

    def near(self, target):
        return (self.face_towards(target, App.Vector(-1, 0, 0)),)

    def test_keep_end_defaults_to_auto_and_lists_three_values(self):
        target = self.target()
        obj = self.valid_extend_cut(self.profile(0, 500), target, self.near(target))
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(obj.getEnumerationsOfProperty("KeepEnd"), ["Auto", "Start", "End"])
        self.assert_runs(obj, 0.0, NEAR)

    def test_a_crossing_face_keeps_the_chosen_end(self):
        cases = {
            "start of a forward profile": ((0, 500), "Start", (0.0, NEAR)),
            "end of a forward profile": ((0, 500), "End", (NEAR, 500.0)),
            "start of a reversed profile": ((500, 0), "Start", (NEAR, 500.0)),
            "end of a reversed profile": ((500, 0), "End", (0.0, NEAR)),
        }
        for name, ((a, b), keep_end, (x_min, x_max)) in cases.items():
            with self.subTest(name):
                target = self.target()
                obj = self.keep(self.valid_extend_cut(self.profile(a, b), target, self.near(target)), keep_end)
                self.assert_runs(obj, x_min, x_max)

    def test_the_gap_moves_the_cut_towards_the_kept_end(self):
        target = self.target()
        obj = self.keep(self.valid_extend_cut(self.profile(0, 500), target, self.near(target), gap=5.0), "End")
        self.assert_runs(obj, NEAR + 5.0, 500.0)

    def test_a_crossed_whole_profile_target_uses_its_face_seen_from_the_kept_end(self):
        obj = self.keep(self.valid_extend_cut(self.profile(0, 500), self.target()), "End")
        self.assert_runs(obj, FAR, 500.0)

    def test_auto_with_a_whole_target_near_the_middle_moves_the_end_nearest_its_plane(self):
        # Target faces at 210 and 260 on a 0-500 profile: the end is farther from the target (240 > 210),
        # so the face seen from it is the one at 260, and the end is the one nearest that plane (240 < 260).
        target = self.make_profile(self.make_sketch(((235, -200, 0), (235, 200, 0))), "Edge1", **CENTER)
        obj = self.valid_extend_cut(self.profile(0, 500), target)
        self.assert_runs(obj, 0.0, 260.0)
        self.assert_runs(self.keep(obj, "End"), 260.0, 500.0)

    def test_a_target_that_does_not_cross_the_profile_ignores_the_choice(self):
        for keep_end in ("Start", "End"):
            with self.subTest(keep_end):
                target = self.target()
                face = self.valid_extend_cut(self.profile(0, 300), target, self.near(target))
                self.assert_runs(self.keep(face, keep_end), 0.0, NEAR)
                whole = self.valid_extend_cut(self.profile(1000, 600), self.target())
                self.assert_runs(self.keep(whole, keep_end), FAR, 1000.0)

    def test_a_trim_saved_without_keep_end_behaves_as_auto(self):
        target = self.target()
        obj = self.keep(self.valid_extend_cut(self.profile(0, 500), target, self.near(target)), "End")
        obj.removeProperty("KeepEnd")
        obj.touch()
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assert_runs(obj, 0.0, NEAR)


class TestNotchKeepEnd(ExtendCutFixture):
    def notch(self, a, b, keep_end):
        body = self.make_profile(self.make_sketch(((a, 0, 0), (b, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        obj = make_notch_profile(body, target)
        obj.KeepEnd = keep_end
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.common(target.Shape).Volume, 0.0, places=5)
        return obj

    def assert_box(self, obj, x_min, x_max):
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, x_min, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, x_max, places=5)
        self.assertAlmostEqual(obj.Length.Value, x_max - x_min, places=5)

    def test_a_crossing_target_keeps_the_chosen_end(self):
        # The target (faces at -25 and 25) crosses the profile from -100 to 300: Auto keeps the far end.
        cases = {
            "auto": ((-100, 300), "Auto", (HALF, 300.0)),
            "start": ((-100, 300), "Start", (-100.0, -HALF)),
            "end": ((-100, 300), "End", (HALF, 300.0)),
            "start of a reversed profile": ((300, -100), "Start", (HALF, 300.0)),
            "end of a reversed profile": ((300, -100), "End", (-100.0, -HALF)),
        }
        for name, ((a, b), keep_end, (x_min, x_max)) in cases.items():
            with self.subTest(name):
                self.assert_box(self.notch(a, b, keep_end), x_min, x_max)

    def test_auto_does_not_test_whether_the_target_crosses(self):
        # The crossing test is a boolean on the target: only a chosen end needs it.
        crosses = TrimmedProfile._target_crosses
        cases = {"Auto": ((HALF, 300.0), 0), "Start": ((-100.0, -HALF), 1)}
        for keep_end, ((x_min, x_max), calls) in cases.items():
            with self.subTest(keep_end):
                with mock.patch.object(TrimmedProfile, "_target_crosses", autospec=True, side_effect=crosses) as spy:
                    obj = self.notch(-100, 300, keep_end)
                self.assert_box(obj, x_min, x_max)
                self.assertEqual(spy.call_count, calls)

    def test_auto_stays_valid_when_the_crossing_test_fails(self):
        # Auto keeps the far end without the crossing test, so a failing boolean there cannot break it.
        with mock.patch.object(TrimmedProfile, "_target_crosses", side_effect=RuntimeError("boolean failed")):
            obj = self.notch(-100, 300, "Auto")
        self.assert_box(obj, HALF, 300.0)

    def test_a_target_holding_one_end_ignores_the_choice(self):
        # The start lies inside the target: there is only one piece to keep.
        for keep_end in ("Start", "End"):
            with self.subTest(keep_end):
                self.assert_box(self.notch(0, 300, keep_end), HALF, 300.0)


if __name__ == "__main__":
    unittest.main()

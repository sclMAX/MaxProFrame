"""Extend Cut: the profile end nearest the target plane ends on that plane, extended or cut."""

import unittest

import FreeCAD as App
import Part
from miter_helpers import use_language
from test_end_miter_geometry import CENTER
from test_end_trim_geometry import TrimFixture

from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile

# The target runs along Y at X = 400: its faces lie on X = 375 and X = 425.
TARGET_EDGE = ((400, -200, 0), (400, 200, 0))
NEAR, FAR = 375.0, 425.0


class ExtendCutFixture(TrimFixture):
    def setUp(self):
        super().setUp()
        # Error texts are translated: pin English whatever an earlier test left active.
        use_language(self, "English", "en_US")

    def target(self):
        return self.make_profile(self.make_sketch(TARGET_EDGE), "Edge1", **CENTER)

    def profile(self, a, b):
        """A profile on the X axis with no end offsets: its body runs exactly from a to b."""
        return self.make_profile(self.make_sketch(((a, 0, 0), (b, 0, 0))), "Edge1", extension=0.0, **CENTER)

    def extend_cut(self, body, target, subs=(), gap=0.0):
        obj = make_extend_cut_profile(body, (target, tuple(subs)), gap)
        self.doc.recompute()
        return obj

    def valid_extend_cut(self, body, target, subs=(), gap=0.0):
        obj = self.extend_cut(body, target, subs, gap)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(obj.Shape.isValid())
        return obj

    def assert_runs(self, obj, x_min, x_max):
        box = obj.Shape.BoundBox
        self.assertAlmostEqual(box.XMin, x_min, places=5)
        self.assertAlmostEqual(box.XMax, x_max, places=5)
        self.assertAlmostEqual(obj.Length.Value, x_max - x_min, places=5)
        # The volume follows the length: nothing is left past the plane.
        body = obj.TrimmedBody.Shape
        self.assertAlmostEqual(obj.Shape.Volume, body.Volume / body.BoundBox.XLength * (x_max - x_min), places=3)

    def assert_invalid(self, obj, text):
        self.assertFalse(obj.isValid())
        self.assertIn(text, obj.getStatusString())


class TestExtendCutGeometry(ExtendCutFixture):
    def test_a_short_profile_is_extended_up_to_the_face(self):
        target = self.target()
        body = self.profile(0, 300)
        obj = self.valid_extend_cut(body, target, (self.face_towards(target, App.Vector(-1, 0, 0)),))
        self.assertEqual(obj.TrimmedProfileType, "Extend Cut")
        self.assert_runs(obj, 0.0, NEAR)

    def test_a_long_profile_is_cut_at_the_face(self):
        target = self.target()
        body = self.profile(0, 500)
        obj = self.valid_extend_cut(body, target, (self.face_towards(target, App.Vector(-1, 0, 0)),))
        self.assert_runs(obj, 0.0, NEAR)

    def test_the_end_nearest_the_plane_moves_whatever_the_edge_direction(self):
        cases = {
            "end of a profile before the target": ((0, 300), App.Vector(-1, 0, 0), (0.0, NEAR)),
            "start of a reversed profile before the target": ((300, 0), App.Vector(-1, 0, 0), (0.0, NEAR)),
            "start of a profile after the target": ((600, 1000), App.Vector(1, 0, 0), (FAR, 1000.0)),
            "end of a reversed profile after the target": ((1000, 600), App.Vector(1, 0, 0), (FAR, 1000.0)),
        }
        for name, ((a, b), direction, (x_min, x_max)) in cases.items():
            with self.subTest(name):
                target = self.target()
                obj = self.valid_extend_cut(self.profile(a, b), target, (self.face_towards(target, direction),))
                self.assert_runs(obj, x_min, x_max)

    def test_the_gap_moves_the_end_back_from_the_plane(self):
        target = self.target()
        face = self.face_towards(target, App.Vector(-1, 0, 0))
        short = self.valid_extend_cut(self.profile(0, 300), target, (face,), gap=5.0)
        self.assertAlmostEqual(short.TrimGap.Value, 5.0)
        self.assert_runs(short, 0.0, NEAR - 5.0)
        long = self.valid_extend_cut(self.profile(0, 500), target, (face,), gap=5.0)
        self.assert_runs(long, 0.0, NEAR - 5.0)

    def test_a_whole_profile_target_uses_its_face_seen_from_the_far_end(self):
        cases = {
            "short profile before the target": ((0, 300), (0.0, NEAR)),
            "long profile through the target": ((0, 500), (0.0, NEAR)),
            "profile after the target": ((1000, 600), (FAR, 1000.0)),
        }
        for name, ((a, b), (x_min, x_max)) in cases.items():
            with self.subTest(name):
                obj = self.valid_extend_cut(self.profile(a, b), self.target())
                # A link to a whole object is stored with an empty sub-element name.
                self.assertEqual(obj.TrimmingBoundary, [(obj.TrimmingBoundary[0][0], ("",))])
                self.assert_runs(obj, x_min, x_max)

    def test_an_explicit_face_target_is_used_even_past_the_near_face(self):
        target = self.target()
        obj = self.valid_extend_cut(self.profile(0, 300), target, (self.face_towards(target, App.Vector(1, 0, 0)),))
        self.assert_runs(obj, 0.0, FAR)

    def test_bom_angle_and_length_of_a_square_and_a_slanted_end(self):
        target = self.target()
        square = self.valid_extend_cut(self.profile(0, 300), target, (self.face_towards(target, App.Vector(-1, 0, 0)),))
        self.assertEqual((square.CuttingAngleA, square.CuttingAngleB), ("0.0", "@ 0.0"))
        # A plain face on the plane x + y = 375, at 45 degrees to the profile axis.
        wall = self.doc.addObject("Part::Feature", "Wall")
        corners = [App.Vector(475, -100, -100), App.Vector(275, 100, -100), App.Vector(275, 100, 100)]
        corners += [App.Vector(475, -100, 100), corners[0]]
        wall.Shape = Part.Face(Part.makePolygon(corners))
        slanted = self.valid_extend_cut(self.profile(0, 300), wall, ("Face1",))
        self.assertEqual((slanted.CuttingAngleA, slanted.CuttingAngleB), ("0.0", "@ 45.0"))
        # The long side of the section reaches x = 400, the short side x = 350.
        self.assertAlmostEqual(slanted.Shape.BoundBox.XMax, 400.0, places=5)
        self.assertAlmostEqual(slanted.Length.Value, 400.0, places=5)

    def test_a_non_planar_face_target_is_an_error(self):
        tube = self.doc.addObject("Part::Feature", "Tube")
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(400, 0, -50))
        lateral = next(
            f"Face{index}"
            for index, face in enumerate(tube.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        obj = self.extend_cut(self.profile(0, 300), tube, (lateral,))
        self.assert_invalid(obj, f"the target face {lateral} of {tube.Label} is not planar")

    def test_a_target_plane_parallel_to_the_axis_is_an_error(self):
        target = self.target()
        top = self.face_towards(target, App.Vector(0, 0, 1))
        obj = self.extend_cut(self.profile(0, 300), target, (top,))
        self.assert_invalid(obj, "the target plane is parallel to the profile axis")

    def test_a_whole_profile_target_the_axis_does_not_cross_is_an_error(self):
        aside = self.make_profile(self.make_sketch(((0, 200, 0), (300, 200, 0))), "Edge1", **CENTER)
        obj = self.extend_cut(self.profile(0, 300), aside)
        self.assert_invalid(obj, f"the profile axis crosses no face of {aside.Label}")


if __name__ == "__main__":
    unittest.main()

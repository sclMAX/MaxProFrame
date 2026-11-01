"""Notch: the profile copies the target shape and keeps the piece that reaches its far end."""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, MiterFixture

from freecad.maxproframe.create_notch_tool import make_notch_profile

# A T joint: the trimmed profile runs along X through the boundary profile, which runs along Y.
TRIMMED_EDGE = ((0, 0, 0), (300, 0, 0))
BOUNDARY_EDGE = ((0, -200, 0), (0, 200, 0))
HALF = 25.0


class TrimFixture(MiterFixture):
    def t_joint(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        boundary = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
        return trimmed, boundary

    def face_towards(self, obj, direction):
        """Name of the planar face of obj whose outward normal points along direction, farthest out."""
        candidates = [
            (face.CenterOfMass.dot(direction), f"Face{index}")
            for index, face in enumerate(obj.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(direction) < 1e-6
        ]
        return max(candidates)[1]

    def notch(self, body, target):
        obj = make_notch_profile(body, target)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj


class TestNotchGeometry(TrimFixture):
    def test_notch_removes_everything_past_the_target_and_leaves_no_overlap(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)

        self.assertEqual(obj.TrimmedProfileType, "Notch")
        self.assertEqual(obj.TrimmingBoundary, [(boundary, ("",))])
        self.assertFalse(hasattr(obj, "CutType"))
        self.assertAlmostEqual(obj.Shape.common(boundary.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("0.0", "@ P"))

    def test_notch_copies_the_target_shape_when_it_is_rotated(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        diamond = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", rotation=45.0, **CENTER)
        obj = self.notch(trimmed, diamond)

        self.assertAlmostEqual(obj.Shape.common(diamond.Shape).Volume, 0.0, places=5)
        # The cut follows the diamond: the profile corners reach along its faces, short of the tip.
        tip = HALF * 2**0.5
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, tip - HALF, places=5)
        self.assertGreater(obj.Shape.distToShape(Part.Vertex(App.Vector(tip, 0, 0)))[0], 1.0)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_the_piece_reaching_the_far_end_is_kept_even_when_it_is_the_shorter_one(self):
        # The profile runs from 0 to 60; the target (outer faces at 15 and 65) holds most of it.
        # The center of gravity rule kept the 45 mm inside the target; the far end is at 0.
        body = self.make_profile(self.make_sketch(((0, 0, 0), (60, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((40, -200, 0), (40, 200, 0))), "Edge1", **CENTER)
        obj = self.notch(body, target)

        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, 15.0, places=5)
        self.assertAlmostEqual(obj.Shape.common(target.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Length.Value, 15.0, places=5)

    def test_the_far_end_is_kept_whatever_the_edge_direction(self):
        for name, edge in {"forward": TRIMMED_EDGE, "reversed": ((300, 0, 0), (0, 0, 0))}.items():
            with self.subTest(name):
                trimmed = self.make_profile(self.make_sketch(edge), "Edge1", **CENTER)
                boundary = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
                obj = self.notch(trimmed, boundary)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)

    def test_both_ends_are_two_chained_notches(self):
        trimmed, boundary = self.t_joint()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        first = self.notch(trimmed, boundary)
        obj = self.notch(first, far)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, 250 - HALF, places=5)
        self.assertAlmostEqual(obj.Length.Value, 250 - 2 * HALF, places=5)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("@ P", "@ P"))

    def test_trimmed_body_is_hidden_and_properties_follow_the_profile(self):
        trimmed, boundary = self.t_joint()
        trimmed.PID = "0042"
        obj = self.notch(trimmed, boundary)
        self.assertFalse(trimmed.ViewObject.Visibility)
        self.assertEqual(obj.PID, "0042")
        for name in ("Family", "CatalogFamily", "SizeName", "Material"):
            self.assertEqual(getattr(obj, name), getattr(trimmed, name), name)
        self.assertAlmostEqual(obj.Width.Value, 50.0)
        self.assertAlmostEqual(obj.Height.Value, 50.0)

    def test_the_joint_types_no_longer_list_end_trim(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)
        self.assertEqual(obj.getEnumerationsOfProperty("TrimmedProfileType"), ["Notch", "End Miter", "Extend Cut"])


if __name__ == "__main__":
    unittest.main()

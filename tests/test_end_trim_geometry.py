"""End Trim cuts: Simple fit cuts at the selected planar face, Perfect fit follows the boundary solid."""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, MiterFixture

from freecad.maxproframe.create_trimmed_profiles_tool import TrimProfileCommand

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

    def trim(self, body, boundaries, cut_type):
        obj = TrimProfileCommand().make_trimmed_profile(trimmedBody=body, trimmingBoundary=boundaries)
        obj.CutType = cut_type
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj


class TestEndTrimGeometry(TrimFixture):
    def test_simple_fit_cuts_at_the_selected_face_and_keeps_the_center_side(self):
        trimmed, boundary = self.t_joint()
        face = self.face_towards(boundary, App.Vector(1, 0, 0))
        obj = self.trim(trimmed, [(boundary, (face,))], "Simple fit")

        box = obj.Shape.BoundBox
        self.assertAlmostEqual(box.XMin, HALF, places=5)
        self.assertAlmostEqual(box.XMax, trimmed.Shape.BoundBox.XMax, places=5)
        self.assertAlmostEqual(obj.Length.Value, box.XMax - HALF, places=5)
        section = trimmed.Shape.Volume / trimmed.Shape.BoundBox.XLength
        self.assertAlmostEqual(obj.Shape.Volume, section * (box.XMax - HALF), places=3)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("0.0", "@ 0.0"))

    def test_simple_fit_with_a_face_on_each_side_cuts_both_ends(self):
        trimmed, boundary = self.t_joint()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        obj = self.trim(
            trimmed,
            [
                (boundary, (self.face_towards(boundary, App.Vector(1, 0, 0)),)),
                (far, (self.face_towards(far, App.Vector(-1, 0, 0)),)),
            ],
            "Simple fit",
        )
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, 250 - HALF, places=5)
        self.assertAlmostEqual(obj.Length.Value, 250 - 2 * HALF, places=5)

    def test_perfect_fit_removes_everything_past_the_boundary_and_leaves_no_overlap(self):
        trimmed, boundary = self.t_joint()
        face = self.face_towards(boundary, App.Vector(1, 0, 0))
        obj = self.trim(trimmed, [(boundary, (face,))], "Perfect fit")

        self.assertAlmostEqual(obj.Shape.common(boundary.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("0.0", "@ P"))

    def test_perfect_fit_copies_the_boundary_shape_when_it_is_rotated(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        diamond = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", rotation=45.0, **CENTER)
        obj = self.trim(trimmed, [(diamond, ("Face1",))], "Perfect fit")

        self.assertAlmostEqual(obj.Shape.common(diamond.Shape).Volume, 0.0, places=5)
        # The cut follows the diamond: the profile corners reach along its faces, short of the tip.
        tip = HALF * 2**0.5
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, tip - HALF, places=5)
        self.assertGreater(obj.Shape.distToShape(Part.Vertex(App.Vector(tip, 0, 0)))[0], 1.0)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_trimmed_body_is_hidden_and_properties_follow_the_profile(self):
        trimmed, boundary = self.t_joint()
        trimmed.PID = "0042"
        obj = self.trim(trimmed, [(boundary, (self.face_towards(boundary, App.Vector(1, 0, 0)),))], "Simple fit")
        self.assertFalse(trimmed.ViewObject.Visibility)
        self.assertEqual(obj.PID, "0042")
        for name in ("Family", "CatalogFamily", "SizeName", "Material"):
            self.assertEqual(getattr(obj, name), getattr(trimmed, name), name)
        self.assertAlmostEqual(obj.Width.Value, 50.0)
        self.assertAlmostEqual(obj.Height.Value, 50.0)


if __name__ == "__main__":
    unittest.main()

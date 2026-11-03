"""Drill Hole geometry: round holes on a planar face, placed from a vertex of that face."""

import math
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER
from test_notch_geometry import TrimFixture

from freecad.maxproframe._utils import is_extrudedcutout
from freecad.maxproframe.drill_hole import make_drill_hole

UP = App.Vector(0, 0, 1)
# The profile: a 50 x 50 x 2 square tube along X, from -50 to 350 (300 long plus 50 at each end).
PATH = ((0, 0, 0), (300, 0, 0))
WALL = 2.0
DIAMETER = 10.0
# Removed by one hole of DIAMETER through one wall.
ONE_HOLE = math.pi * (DIAMETER / 2) ** 2 * WALL


class DrillHoleFixture(TrimFixture):
    def tube(self):
        return self.make_profile(self.make_sketch(PATH), "Edge1", **CENTER)

    def vertex_at(self, obj, point):
        """Name of the vertex of ``obj`` at ``point``."""
        for index, vertex in enumerate(obj.Shape.Vertexes, start=1):
            if vertex.Point.isEqual(App.Vector(*point), 1e-6):
                return f"Vertex{index}"
        self.fail(f"no vertex at {point}")

    def hole(self, body, face, vertex, along, across, **values):
        obj = make_drill_hole((body, (face,)), vertex)
        obj.OffsetAlong = along
        obj.OffsetAcross = across
        obj.Diameter = values.pop("diameter", DIAMETER)
        for name, value in values.items():
            setattr(obj, name, value)
        self.doc.recompute()
        return obj

    def empty(self, shape, *point):
        return not shape.isInside(App.Vector(*point), 1e-7, True)


class TestDrillHoleGeometry(DrillHoleFixture):
    def test_a_hole_is_drilled_through_the_wall_under_the_face_at_the_offsets_from_the_vertex(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(obj.CutType, "One wall")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        # Hole center (-20, 0): empty in the top wall, the bottom wall is intact.
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        self.assertFalse(self.empty(obj.Shape, -20, 0, -24))
        self.assertFalse(self.empty(obj.Shape, -20 + DIAMETER, 0, 24))

    def test_offsets_go_into_the_face_from_whichever_corner_is_picked(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (350, 25, 25))
        obj = self.hole(body, top, corner, 30.0, 10.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 320, 15, 24))

    def test_a_linear_pattern_drills_count_holes_one_pitch_apart_along_the_profile(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0, Count=3, Pitch=40.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * ONE_HOLE, places=3)
        for x in (-20, 20, 60):
            self.assertTrue(self.empty(obj.Shape, x, 0, 24), x)
        self.assertFalse(self.empty(obj.Shape, 100, 0, 24))

    def test_through_all_drills_every_wall_under_the_hole(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        obj = self.hole(body, top, self.vertex_at(body, (-50, -25, 25)), 30.0, 25.0, CutType="Through All")
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, -24))

    def test_a_distance_depth_drills_that_deep_only(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0, CutType="Distance", ExtrusionLength=1.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE / 2, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24.5))
        self.assertFalse(self.empty(obj.Shape, -20, 0, 23.5))

    def test_a_curved_face_is_refused_with_the_reason(self):
        body = self.tube()
        body.Family = "Pipe"
        self.doc.recompute()
        curved = next(
            f"Face{index}"
            for index, face in enumerate(body.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        obj = self.hole(body, curved, "Vertex1", 30.0, 0.0)
        self.assertIn(f"Drill Hole: {curved} of {body.Label} is not planar.", obj.getStatusString())

    def test_a_hole_is_a_cutout_of_its_profile_for_the_cut_list(self):
        body = self.tube()
        body.PID = "P7"
        top = self.face_towards(body, UP)
        obj = self.hole(body, top, self.vertex_at(body, (-50, -25, 25)), 30.0, 25.0)
        self.assertTrue(is_extrudedcutout(obj))
        self.assertEqual((obj.PID, obj.SizeName, obj.Family), (body.PID, body.SizeName, body.Family))
        self.assertAlmostEqual(obj.Length.Value, 400.0, places=5)
        self.assertEqual(obj.Label, f"{body.Label}_Dh")


if __name__ == "__main__":
    unittest.main()

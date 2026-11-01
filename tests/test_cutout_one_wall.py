"""Cutout depth One wall: the cut stops past the wall under the picked face, whatever the profile."""

import math
import unittest

import FreeCAD as App
import Part
from test_cutout_flow import END, HOLE_RADIUS, SIDE, UP, WALL, CutoutFixture

from freecad.maxproframe import create_extruded_cutout_tool
from freecad.maxproframe.create_extruded_cutout_tool import CreateExtrudedCutoutTaskPanel, make_extruded_cutout

# A TC80x40x1.5: a rectangular hollow 80 x 40 with 1.5 walls.
TC_THICKNESS = 1.5
RADIUS = 10.0


class OneWallFixture(CutoutFixture):
    def reshape(self, body, family, width, height, thickness):
        body.Family = family
        body.ProfileWidth = width
        body.ProfileHeight = height
        body.Thickness = thickness
        self.doc.recompute()
        return body

    def tc80x40(self):
        return self.reshape(self.tube(), "Rectangular Hollow", 80.0, 40.0, TC_THICKNESS)

    def guided_cutout(self, body, face, radius=RADIUS):
        """A cutout made by the face panel, with a circle of ``radius`` drawn at the face center."""
        before = self.names()
        panel = self.run_command((body, face))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        self.close_dialog()
        self.add_circle(cutout, body.Shape.getElement(face).CenterOfMass, radius)
        self.assertEqual(cutout.getStatusString(), "Valid")
        return cutout

    def add_circle(self, cutout, center, radius):
        """A circle of ``radius`` on the sketch of ``cutout``, around the global point ``center``."""
        sketch = cutout.Sketch
        local = sketch.Placement.inverse().multVec(center)
        sketch.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), UP, radius))
        self.doc.recompute()

    def hole_axis(self, body, face):
        """(center, outward normal) of the face ``face`` of ``body``."""
        shape = body.Shape.getElement(face)
        return shape.CenterOfMass, shape.normalAt(0, 0)

    def inside(self, shape, point):
        return shape.isInside(point, 1e-7, True)


class TestOneWallDepth(OneWallFixture):
    def test_a_hole_on_the_top_wall_of_a_tc80x40_leaves_the_bottom_wall_intact(self):
        body = self.tc80x40()
        top = self.face_towards(body, UP)
        cutout = self.guided_cutout(body, top)
        self.assertEqual(cutout.CutType, "One wall")
        removed = math.pi * RADIUS**2 * TC_THICKNESS
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)
        center, normal = self.hole_axis(body, top)
        depth = body.Shape.BoundBox.ZLength
        # Mid thickness of the top wall, then of the bottom wall, under the hole center.
        self.assertFalse(self.inside(cutout.Shape, center - normal * (TC_THICKNESS / 2)))
        self.assertTrue(self.inside(cutout.Shape, center - normal * (depth - TC_THICKNESS / 2)))
        self.assertEqual(len(cutout.Shape.Solids), 1)

    def test_a_hole_on_a_side_wall_leaves_the_opposite_wall_intact(self):
        body = self.tc80x40()
        side = self.face_towards(body, SIDE)
        cutout = self.guided_cutout(body, side, radius=8.0)
        removed = math.pi * 8.0**2 * TC_THICKNESS
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)
        center, normal = self.hole_axis(body, side)
        depth = body.Shape.BoundBox.YLength
        self.assertFalse(self.inside(cutout.Shape, center - normal * (TC_THICKNESS / 2)))
        self.assertTrue(self.inside(cutout.Shape, center - normal * (depth - TC_THICKNESS / 2)))

    def test_a_hole_on_a_leg_of_an_angle_cuts_that_leg_only(self):
        body = self.reshape(self.tube(), "Equal Leg Angles", 50.0, 50.0, 5.0)
        # The outer face of a leg: the largest wall face.
        leg = max(
            (
                (face.Area, f"Face{index}")
                for index, face in enumerate(body.Shape.Faces, start=1)
                if isinstance(face.Surface, Part.Plane) and abs(face.normalAt(0, 0).x) < 1e-9
            )
        )[1]
        cutout = self.guided_cutout(body, leg, radius=6.0)
        removed = math.pi * 6.0**2 * 5.0
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)

    def test_each_region_of_the_sketch_cuts_its_own_wall(self):
        body = self.tc80x40()
        top = self.face_towards(body, UP)
        cutout = self.guided_cutout(body, top, radius=5.0)
        self.add_circle(cutout, body.Shape.getElement(top).CenterOfMass + END * 50, 5.0)
        removed = 2 * math.pi * 5.0**2 * TC_THICKNESS
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)

    def test_a_larger_hole_over_an_older_one_still_cuts_one_wall(self):
        body = self.tc80x40()
        first = self.guided_cutout(body, self.face_towards(body, UP), radius=5.0)
        # Its center is over the older hole: the bottom wall is the first material under it.
        second = self.guided_cutout(first, self.face_towards(first, UP), radius=RADIUS)
        removed = math.pi * RADIUS**2 * TC_THICKNESS
        self.assertAlmostEqual(second.Shape.Volume, body.Shape.Volume - removed, places=3)

    def test_a_region_off_the_profile_cuts_nothing(self):
        body = self.tc80x40()
        top = self.face_towards(body, UP)
        cutout = self.guided_cutout(body, top, radius=5.0)
        center = body.Shape.getElement(top).CenterOfMass
        # Beside the tube, across its axis: nothing under them.
        self.add_circle(cutout, center + SIDE * 200, 5.0)
        self.add_circle(cutout, center - SIDE * 200, 5.0)
        self.assertEqual(cutout.getStatusString(), "Valid")
        removed = math.pi * 5.0**2 * TC_THICKNESS
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)


class TestCutTypes(OneWallFixture):
    def test_one_wall_is_the_third_cut_type_and_the_guided_default(self):
        self.assertEqual(create_extruded_cutout_tool.GUIDED_CUT_TYPE, "One wall")
        body = self.tube()
        top = self.face_towards(body, UP)
        cutout = self.guided_cutout(body, top, radius=HOLE_RADIUS)
        self.assertEqual(cutout.getEnumerationsOfProperty("CutType"), ["Through All", "Distance", "One wall"])
        self.assertEqual(cutout.CutType, "One wall")

    def test_the_extrusion_length_shows_for_distance_only(self):
        body = self.tube()
        cutout = self.guided_cutout(body, self.face_towards(body, UP), radius=HOLE_RADIUS)
        for cut_type, mode in (("Distance", []), ("One wall", ["Hidden"]), ("Through All", ["Hidden"])):
            with self.subTest(cut_type=cut_type):
                cutout.CutType = cut_type
                self.assertEqual(cutout.getEditorMode("ExtrusionLength"), mode)

    def test_through_all_and_distance_keep_their_depth(self):
        body = self.tube()
        cutout = self.guided_cutout(body, self.face_towards(body, UP), radius=HOLE_RADIUS)
        area = math.pi * HOLE_RADIUS**2
        cutout.CutType = "Through All"
        self.doc.recompute()
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - 2 * area * WALL, places=3)
        cutout.CutType = "Distance"
        cutout.ExtrusionLength = 1.0
        self.doc.recompute()
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - area * 1.0, places=3)

    def test_the_cut_type_panel_offers_one_wall_and_hides_the_length(self):
        body = self.tube()
        cutout = self.guided_cutout(body, self.face_towards(body, UP), radius=HOLE_RADIUS)
        panel = CreateExtrudedCutoutTaskPanel(cutout)
        combo = panel.comboCutType
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["Through All", "Distance", "One wall"])
        self.assertEqual(combo.currentText(), "One wall")
        self.assertTrue(panel.spinA.isHidden())
        combo.setCurrentIndex(1)
        self.assertEqual(cutout.CutType, "Distance")
        self.assertFalse(panel.spinA.isHidden())
        combo.setCurrentIndex(2)
        self.assertEqual(cutout.CutType, "One wall")
        self.assertTrue(panel.spinA.isHidden())

    def test_a_cutout_saved_before_one_wall_gains_it_on_restore(self):
        body = self.tube()
        sketch = self.doc.addObject("Sketcher::SketchObject", "Hole")
        cutout = make_extruded_cutout(sketch, (body, [self.face_towards(body, UP)]))
        # The enumeration of a document saved by MaxProFrame 1.0.
        cutout.CutType = ["Through All", "Distance"]
        cutout.CutType = "Distance"
        cutout.Proxy.onDocumentRestored(cutout)
        self.assertEqual(cutout.getEnumerationsOfProperty("CutType"), ["Through All", "Distance", "One wall"])
        self.assertEqual(cutout.CutType, "Distance")


if __name__ == "__main__":
    unittest.main()

"""Drill Hole reference: the hole stays where it was placed when the vertex it was placed from changes."""

import unittest

import FreeCAD as App
from test_drill_hole_geometry import ONE_HOLE, UP, DrillHoleFixture

CORNER = (-50, -25, 25)
WARNING = "The reference vertex changed: check the hole."


class TestDrillHoleReference(DrillHoleFixture):
    def corner_hole(self, body, along, across=25.0):
        return self.hole(body, self.face_towards(body, UP), self.vertex_at(body, CORNER), along, across)

    def assert_hole_at(self, obj, volume, *center):
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, volume, places=3)
        self.assertTrue(self.empty(obj.Shape, *center), center)

    def test_the_hole_stays_when_the_named_vertex_is_still_in_place(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        body.OffsetA = 0.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, -20, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_stays_when_the_reference_vertex_is_renumbered(self):
        body = self.tube()
        first = self.corner_hole(body, 130.0)
        obj = self.corner_hole(first, 230.0)
        # Through All drills the bottom wall too: the corner is still there, under another name.
        first.CutType = "Through All"
        self.doc.recompute()
        self.assertNotEqual(self.vertex_at(first, CORNER), obj.ReferenceVertex)
        self.assert_hole_at(obj, first.Shape.Volume - ONE_HOLE, 180, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_stays_with_a_warning_when_the_corner_is_gone(self):
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # The start end moves from x = -50 to x = 100: the corner is gone, the hole at x = 180 is still on the tube.
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 24)
        # Not moved to the offsets from the new start corner.
        self.assertFalse(self.empty(obj.Shape, 330, 0, 24))
        self.assertEqual(obj.ReferenceWarning, WARNING)

        # Back to the 50 mm extension of the fixture: the corner is there again.
        body.OffsetB = 50.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_picking_another_vertex_places_the_hole_from_it(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        obj.ReferenceVertex = self.vertex_at(body, (350, 25, 25))
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 320, 0, 24)
        self.assertFalse(self.empty(obj.Shape, -20, 0, 24))
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_moves_with_its_profile(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        # The path turns a quarter about Z and moves: (x, y, z) goes to (10 - y, 100 + x, z).
        body.AttachmentSupport[0][0].Placement = App.Placement(App.Vector(10, 100, 0), App.Rotation(UP, 90))
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 10, 80, 24)
        self.assertFalse(self.empty(obj.Shape, 10, 80, -24))
        self.assertEqual(obj.ReferenceWarning, "")


if __name__ == "__main__":
    unittest.main()

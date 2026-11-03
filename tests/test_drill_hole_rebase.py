"""Drill Hole moved to another base: the base it leaves is shown again unless something still builds on it."""

import unittest

from test_drill_hole_geometry import UP, DrillHoleFixture
from test_end_miter_geometry import CENTER

# A second tube, parallel to the first one, 200 mm away.
OTHER_PATH = ((0, 200, 0), (300, 200, 0))


class TestDrillHoleRebase(DrillHoleFixture):
    def other_tube(self):
        return self.make_profile(self.make_sketch(OTHER_PATH), "Edge1", **CENTER)

    def move(self, obj, body):
        obj.baseObject = (body, (self.face_towards(body, UP),))
        obj.ReferenceVertex = self.vertex_at(body, (-50, 175, 25))
        self.doc.recompute()

    def test_the_base_a_hole_leaves_is_shown_again_and_the_new_one_hidden(self):
        first, second = self.tube(), self.other_tube()
        obj = self.hole(first, self.face_towards(first, UP), self.vertex_at(first, (-50, -25, 25)), 30.0, 25.0)
        self.assertFalse(first.ViewObject.Visibility)
        self.move(obj, second)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(first.ViewObject.Visibility)
        self.assertFalse(second.ViewObject.Visibility)
        self.assertTrue(self.empty(obj.Shape, -20, 200, 24))

    def test_the_base_a_hole_leaves_stays_hidden_while_another_hole_is_built_on_it(self):
        first, second = self.tube(), self.other_tube()
        top, corner = self.face_towards(first, UP), self.vertex_at(first, (-50, -25, 25))
        obj = self.hole(first, top, corner, 30.0, 25.0)
        self.hole(first, top, corner, 90.0, 25.0)
        self.move(obj, second)
        self.assertFalse(first.ViewObject.Visibility)

    def test_a_hole_labelled_after_the_base_it_leaves_is_labelled_after_its_new_base(self):
        first, second = self.tube(), self.other_tube()
        obj = self.hole(first, self.face_towards(first, UP), self.vertex_at(first, (-50, -25, 25)), 30.0, 25.0)
        self.assertEqual(obj.Label, f"{first.Label}_Dh")
        self.move(obj, second)
        self.assertEqual(obj.Label, f"{second.Label}_Dh")

    def test_a_hole_the_user_labelled_keeps_its_label_on_another_base(self):
        first, second = self.tube(), self.other_tube()
        obj = self.hole(first, self.face_towards(first, UP), self.vertex_at(first, (-50, -25, 25)), 30.0, 25.0)
        obj.Label = "Bolt holes"
        self.move(obj, second)
        self.assertEqual(obj.Label, "Bolt holes")


if __name__ == "__main__":
    unittest.main()

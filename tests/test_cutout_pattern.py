"""Cutout pattern: the sketch repeated in one row along the profile, a count and a pitch on each side of it."""

import math
import unittest

import FreeCAD as App
from test_cutout_flow import UP, WALL
from test_cutout_one_wall import RADIUS, OneWallFixture

# The pattern properties of a cutout: a count and a pitch on each side of the sketch, along the profile.
PATTERN_PROPERTIES = ("AlongBackwardCount", "AlongBackwardPitch", "AlongForwardCount", "AlongForwardPitch")
# The tube's path runs from x = 0 to x = 300: forward is +X.
FORWARD = App.Vector(1, 0, 0)


class PatternFixture(OneWallFixture):
    def top_cutout(self):
        """(body, cutout, sketch center): a cutout of a circle of RADIUS at the middle of the tube's top face."""
        body = self.tube()
        top = self.face_towards(body, UP)
        cutout = self.guided_cutout(body, top)
        return body, cutout, body.Shape.getElement(top).CenterOfMass

    def set_pattern(self, cutout, backward=(0, 50.0), forward=(0, 50.0)):
        (cutout.AlongBackwardCount, cutout.AlongBackwardPitch) = backward
        (cutout.AlongForwardCount, cutout.AlongForwardPitch) = forward
        self.doc.recompute()

    def hole(self):
        return math.pi * RADIUS**2 * WALL

    def cut_at(self, cutout, center, offset):
        """Whether the top wall of ``cutout`` is cut at ``offset`` mm forward of ``center``."""
        return not self.inside(cutout.Shape, center + FORWARD * offset - UP * (WALL / 2))


class TestCutoutPattern(PatternFixture):
    def test_a_new_cutout_has_an_empty_pattern_and_cuts_the_sketch_alone(self):
        body, cutout, center = self.top_cutout()
        self.assertEqual([cutout.getGroupOfProperty(name) for name in PATTERN_PROPERTIES], ["ExtrudedCutout"] * 4)
        self.assertEqual((cutout.AlongBackwardCount, cutout.AlongForwardCount), (0, 0))
        self.assertEqual((cutout.AlongBackwardPitch.Value, cutout.AlongForwardPitch.Value), (50.0, 50.0))
        self.assertAlmostEqual(body.Shape.Volume - cutout.Shape.Volume, self.hole(), places=3)

    def test_one_backward_every_50_and_two_forward_every_30_make_four_cutouts(self):
        """S1: "<- 1@50mm (croquis) 2@30mm": at -50, the sketch, +30 and +60 mm toward the end of the path."""
        body, cutout, center = self.top_cutout()
        self.set_pattern(cutout, backward=(1, 50.0), forward=(2, 30.0))
        self.assertEqual(cutout.getStatusString(), "Valid")
        self.assertAlmostEqual(body.Shape.Volume - cutout.Shape.Volume, 4 * self.hole(), places=3)
        for offset in (-50.0, 0.0, 30.0, 60.0):
            with self.subTest(offset=offset):
                self.assertTrue(self.cut_at(cutout, center, offset))
        for offset in (-30.0, -80.0, 90.0):
            with self.subTest(uncut=offset):
                self.assertFalse(self.cut_at(cutout, center, offset))

    def test_every_copy_goes_through_the_wall_under_it(self):
        body, cutout, center = self.top_cutout()
        self.set_pattern(cutout, forward=(3, 40.0))
        # One wall: the bottom wall stays whole under every copy.
        for offset in (0.0, 40.0, 80.0, 120.0):
            with self.subTest(offset=offset):
                bottom = center + FORWARD * offset - UP * (50.0 - WALL / 2)
                self.assertTrue(self.inside(cutout.Shape, bottom))
        self.assertAlmostEqual(body.Shape.Volume - cutout.Shape.Volume, 4 * self.hole(), places=3)

    def test_more_than_1000_cutouts_fail_with_a_message(self):
        body, cutout, center = self.top_cutout()
        self.set_pattern(cutout, backward=(600, 0.1), forward=(500, 0.1))
        self.assertNotEqual(cutout.getStatusString(), "Valid")
        self.assertIn("Cutout / Hole: the pattern makes 1101 cutouts, at most 1000.", cutout.getStatusString())

    def test_a_cutout_saved_without_a_pattern_opens_with_an_empty_one_and_the_same_cut(self):
        """S3: the properties are added on restore, counts 0."""
        body, cutout, center = self.top_cutout()
        volume = cutout.Shape.Volume
        for name in PATTERN_PROPERTIES:
            cutout.removeProperty(name)
        cutout.Proxy.onDocumentRestored(cutout)
        self.assertEqual((cutout.AlongBackwardCount, cutout.AlongForwardCount), (0, 0))
        cutout.touch()
        self.doc.recompute()
        self.assertAlmostEqual(cutout.Shape.Volume, volume, places=3)

    def test_a_drill_hole_keeps_its_own_pattern_properties(self):
        """S3: the cutout's hook adds nothing to a drill hole, whose pattern stays in its DrillHole group."""
        from freecad.maxproframe.drill_hole import make_drill_hole

        body = self.tube()
        top = self.face_towards(body, UP)
        corner = body.Shape.getElement(top).Vertexes[0].Point
        vertex = next(
            f"Vertex{index}" for index, v in enumerate(body.Shape.Vertexes, start=1) if v.Point.isEqual(corner, 1e-6)
        )
        hole = make_drill_hole((body, (top,)), vertex)
        self.doc.recompute()
        self.assertEqual([hole.getGroupOfProperty(name) for name in PATTERN_PROPERTIES], ["DrillHole"] * 4)


if __name__ == "__main__":
    unittest.main()

"""Extend / Cut against a profile whose face names FreeCAD keeps (no miter on the target).

Offsets, anchors and Links behave as before the lost-face fix; a section turned half way keeps the trim on the
same side of the path (the inner face), as it does for mitered targets (L16).
"""

import unittest

import FreeCAD as App
from test_extend_cut_lost_face import HALF, WIDTH, LostFaceFixture


class BareTargets(LostFaceFixture):
    def cut_targets(self, left, right):
        return left.TrimmedBody, right.TrimmedBody

    def slat_min_x(self):
        return self.trims[0].Shape.BoundBox.XMin  # in the Part

    def inner_x(self):
        """Where the inner face of the left side is: the side's highest x, in the Part."""
        return self.left.Shape.BoundBox.XMax


class TestBareTargetMatchesMain(BareTargets):
    def test_offsets_follow_the_named_face(self):
        for prop, value in (("OffsetX", 10.0), ("OffsetY", 10.0)):
            with self.subTest(prop=prop):
                setattr(self.left, prop, value)
                self.resize(self.doc, 1000.0, 2100.0)
                self.assert_all_valid(self.doc)
                self.assertEqual(self.trims[0].TrimmingBoundary[0][1], ("Face1",))
                self.assertAlmostEqual(self.slat_min_x(), self.inner_x(), places=4)
                setattr(self.left, prop, 0.0)
                self.resize(self.doc, WIDTH, 2200.0)

    def test_link_with_its_source_placement_follows(self):
        link = self.doc.addObject("App::Link", "L")
        link.LinkedObject, link.LinkTransform = self.right, False
        self.part.addObject(link)
        link.Placement = self.right.Placement.multiply(App.Placement(App.Vector(-100, 0, 0), App.Rotation()))
        self.doc.recompute()
        self.trim.TrimmingBoundary = [(link, (self.inner_face(self.right, -1),))]
        self.doc.recompute()
        x = self.trim.Shape.BoundBox.XMax
        self.resize(self.doc, 1000.0, 2100.0)
        self.assert_all_valid(self.doc)
        self.assertAlmostEqual(self.trim.Shape.BoundBox.XMax, x, places=4)


class TestBareTargetTurned(BareTargets):
    def test_turned_half_way_keeps_the_inner_face(self):
        # The picked face moves to the outside; the trim stays on the inner face, on the same side of the path.
        self.left.RotationAngle = 180.0
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assertAlmostEqual(self.slat_min_x(), self.inner_x(), places=4)
        self.assertAlmostEqual(self.slat_min_x(), -WIDTH / 2.0 + HALF, places=4)
        self.resize(self.doc, 1000.0, 2100.0)
        self.assert_all_valid(self.doc)
        self.assertAlmostEqual(self.slat_min_x(), self.inner_x(), places=4)


if __name__ == "__main__":
    unittest.main()

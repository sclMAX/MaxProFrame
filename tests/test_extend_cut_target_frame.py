"""Extend / Cut keeps its face when the target is a Link or its section turns, and when its link is set again."""

import unittest

import FreeCAD as App
from test_extend_cut_lost_face import WIDTH, LostFaceFixture


class TestTargetFrame(LostFaceFixture):
    def link_to_the_right_side(self):
        """The slat cut against a Link to the right side, on the face it was cut against."""
        link = self.doc.addObject("App::Link", "RightLink")
        link.LinkedObject = self.right
        self.part.addObject(link)
        self.trim.TrimmingBoundary = [(link, (self.inner_face(self.right, -1),))]
        self.doc.recompute()
        return link

    def test_a_link_target_recomputes_and_follows(self):
        self.link_to_the_right_side()
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, WIDTH)
        for width, length in ((1000.0, 2100.0), (1200.0, 2300.0), (900.0, 1900.0), (WIDTH, 2200.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)

    def test_a_workbench_link_target_recomputes_and_follows(self):
        # The Link command adds an attachment, off, to its links.
        link = self.link_to_the_right_side()
        link.addExtension("Part::AttachExtensionPython")
        link.MapMode = "Deactivated"
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        for width, length in ((1000.0, 2100.0), (1200.0, 2300.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)

    def check_turn(self, angle):
        self.left.TrimmedBody.RotationAngle = angle
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, WIDTH)
        for width, length in ((1000.0, 2100.0), (1200.0, 2300.0)):
            with self.subTest(angle=angle, width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)

    def test_a_square_side_turned_half_way_keeps_the_inner_face(self):
        self.check_turn(180.0)

    def test_a_square_side_turned_a_quarter_keeps_the_inner_face(self):
        self.check_turn(90.0)

    def test_a_link_set_again_then_shrunk_keeps_the_inner_face(self):
        self.trim.TrimmingBoundary = list(self.trim.TrimmingBoundary)
        self.resize(self.doc, 1000.0, 2100.0)
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, 1000.0)


if __name__ == "__main__":
    unittest.main()

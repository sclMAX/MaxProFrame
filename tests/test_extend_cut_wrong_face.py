"""Extend / Cut keeps the face it was placed on when FreeCAD gives its name to another face of the target.

Shrinking the frame of LostFaceFixture makes FreeCAD resolve the name of the inner face of a side to its outer
face: the slat still ends on the inner face.
"""

import unittest

from test_extend_cut_lost_face import LostFaceFixture


class TestExtendCutKeepsTheInnerFace(LostFaceFixture):
    def test_shrinking_both_sizes_keeps_the_inner_face(self):
        for width, length in ((1000.0, 2100.0), (1200.0, 2300.0), (900.0, 1900.0), (1100.0, 2200.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)


if __name__ == "__main__":
    unittest.main()

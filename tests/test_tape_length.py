"""Tape length: a piece is as long as its longest side along its axis, as a workshop tapes it to cut it.

The longest straight edge of the finished piece parallel to its axis, not the tip-to-tip extent; a round
section has no such edge and keeps the tip-to-tip extent.
"""

import math
import unittest

from test_cut_ends import ALONG_X, SLANTED_TARGET
from test_cut_list import KERF, CutListFixture, cell
from test_end_miter_geometry import CENTER
from test_piece_table import PieceTableFixture

# Every fixture path runs 300 mm along X; the bevels tilt the ends about the height axis.
PATH = 300.0
SIDE = 40.0


def slant(angle, width=SIDE):
    """How much further one side of a ``width`` wide tube reaches than the other at an end cut ``angle`` off square."""
    return width * math.tan(math.radians(angle))


class TapeLengthFixture(CutListFixture):
    def square_tube(self, **bevels):
        """A 40x40 tube along X with sharp corners, beveled."""
        return self.tube(self.make_sketch(ALONG_X), width=SIDE, height=SIDE, **bevels)

    def parallelogram(self, **props):
        """A 40x40 tube cut 12/12 with both ends tilted the same way: both sides are 300 long."""
        return self.square_tube(BevelACutY=12.0, BevelBCutY=-12.0, **props)

    def tip_to_tip(self, obj):
        return obj.Shape.BoundBox.XLength


class TestTapeLength(TapeLengthFixture):
    def test_a_square_cut_piece_keeps_its_length(self):
        self.assertAlmostEqual(self.square_tube().Length.Value, PATH, places=6)

    def test_a_trapezoid_is_as_long_as_its_long_side_tip_to_tip(self):
        # Cuts converging: the long side runs tip to tip, half the 80 width past each end of the path.
        obj = self.tube_along_x(BevelACutY=45.0, BevelBCutY=45.0)
        self.assertAlmostEqual(obj.Length.Value, PATH + slant(45.0, 80.0), places=6)
        self.assertAlmostEqual(obj.Length.Value, self.tip_to_tip(obj), places=6)

    def test_a_parallelogram_is_as_long_as_its_sides_not_tip_to_tip(self):
        # Both sides are 300 long; tip to tip is one 40 * tan 12 = 8.5 slant longer.
        obj = self.parallelogram()
        self.assertAlmostEqual(obj.Length.Value, PATH, places=6)
        self.assertAlmostEqual(self.tip_to_tip(obj) - obj.Length.Value, slant(12.0), places=6)

    def test_a_45_end_and_a_12_end_tilted_apart_give_the_longer_side(self):
        # The 45 end lengthens one side by 20, the 12 end shortens that same side by 20 * tan 12.
        obj = self.square_tube(BevelACutY=45.0, BevelBCutY=-12.0)
        self.assertAlmostEqual(obj.Length.Value, PATH + slant(45.0, 20.0) - slant(12.0, 20.0), places=6)
        self.assertAlmostEqual(self.tip_to_tip(obj) - obj.Length.Value, slant(12.0), places=6)

    def test_a_tube_with_rounded_corners_is_as_long_as_its_flat_sides(self):
        obj = self.parallelogram(MakeFillet=True, RadiusLarge=4.0, RadiusSmall=2.0)
        self.assertGreater(len(obj.Shape.Faces), 10)
        self.assertAlmostEqual(obj.Length.Value, PATH, places=6)

    def test_a_round_tube_keeps_its_tip_to_tip_length(self):
        # No straight edge runs along a round tube: nothing to tape but tip to tip.
        pipe = self.tube(self.make_sketch(ALONG_X), family="Pipe", width=SIDE, height=SIDE, BevelBCutY=30.0)
        self.assertAlmostEqual(pipe.Length.Value, PATH + slant(30.0, 20.0), places=6)
        self.assertAlmostEqual(pipe.Length.Value, self.tip_to_tip(pipe), places=6)

    def test_a_trimmed_piece_is_as_long_as_its_longest_side(self):
        # The Extend Cut end, 30 off square, tilts the same way as the 30 bevel of the other end.
        body = self.square_tube(BevelBCutY=30.0)
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        obj = self.valid_extend_cut(body, target)
        self.assertAlmostEqual(self.tip_to_tip(obj) - obj.Length.Value, slant(30.0), places=6)

    def test_a_trimmed_piece_measures_a_side_split_by_the_trim_whole(self):
        # Extending a beveled end leaves the long side in two edges on one line: the side is still tip to tip.
        body = self.square_tube(BevelACutY=30.0)
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        obj = self.valid_extend_cut(body, target)
        self.assertAlmostEqual(obj.Length.Value, self.tip_to_tip(obj), places=6)

    def test_a_cutout_is_as_long_as_the_piece_it_cuts(self):
        cutout = self.hole_in_the_middle(self.parallelogram())
        self.assertAlmostEqual(cutout.Length.Value, PATH, places=6)


class TestTapeLengthInTheLists(TapeLengthFixture):
    def test_the_bom_shows_the_longest_side(self):
        sheet = self.bom(self.pieces(self.parallelogram()))
        self.assertEqual(cell(sheet, "E2"), "Length")
        self.assertAlmostEqual(float(cell(sheet, "E3")), PATH)

    def test_the_cut_list_and_its_stock_bars_use_the_longest_side(self):
        pieces = [self.parallelogram() for _ in range(2)]
        for obj in pieces:
            obj.PID = "3"
        sheet = self.cut_list(self.pieces(*pieces))
        self.assertAlmostEqual(float(cell(sheet, "D2")), PATH)
        self.assertEqual(cell(sheet, "H2"), "2")
        used, stock, count = self.statistics(sheet)
        self.assertAlmostEqual(float(used), 2 * (PATH + KERF))
        self.assertEqual([stock, count], ["6000", "1"])


class TestTapeLengthInThePieceTable(PieceTableFixture, TapeLengthFixture):
    def test_the_piece_table_shows_the_longest_side(self):
        obj = self.parallelogram()
        obj.PID = "3"
        self.run_command(self.add_view("View", obj))
        self.assertEqual(self.rows(self.table().Source)[1], ["3", "40x40x2", "1", "300.0", "12.0 <40", "12.0 <40"])


if __name__ == "__main__":
    unittest.main()

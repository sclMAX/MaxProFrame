"""Fingers at an End Miter corner on a Folded Bar (odd/tasks/miter-fingers.md, T3: S1, S5; D1, D5).

The user's case: a free end of a Folded Bar, cut by an End Miter against a straight tube, interlocks with it in Fingers
at the inner vertex of their corner; so do the free ends of two bars. A face clicked on the bar stands for the face of
the tube under the clicked point (``folded_bar.segment_at``), as for the other tools on a bar. The finger piece goes on
top of the bar's end tube; the bar folds it (its shape has the fingers and the cuts of the other tube's fingers), the
Unfolded Bar carries them, and the bar is as long as its finger tips (S5). The straight tube takes its piece as between
two straight tubes (T2). A tube of a bar whose end at the corner is a folded corner, or the open corner of a closed
bar (D5), is refused saying so. Deleting the Interlock gives the bar its End Miter back; undo brings the fingers back;
a saved bar opens with them.
"""

import math
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from test_end_miter_geometry import polar
from test_folded_bar_tools import BEND_MESSAGE, face_at
from test_tab_interlock_folded_bar import TabsOnBarFixture, face_towards
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe._utils import piece_stack
from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.extruded_cutout import along_extent
from freecad.maxproframe.folded_bar import make_folded_bar, make_unfolded_bar
from freecad.maxproframe.interlock import is_miter_interlock
from freecad.maxproframe.interlock_geometry import InterlockError
from freecad.maxproframe.miter_finger_interlock import MiterFace, make_miter_fingers, miter_order, miter_pieces
from freecad.maxproframe.profile_pattern import newest_piece

X, Y = App.Vector(1, 0, 0), App.Vector(0, 1, 0)
VOLUME_TOLERANCE = 1e-2
LENGTH_TOLERANCE = 1e-4
GAP = 0.5
# The user's layout (make_legs): on the bar, the inner wall of the right tube (normal -X); the inner wall of the bottom
# tube is its top face (normal +Y).
RIGHT_INNER = App.Vector(275, 100, 0)
# The second bar of two: up at x = 600, then back along y = 0 to the free end of the first bar at (300, 0).
OTHER_BAR = (((600, -200, 0), (600, 0, 0)), ((600, 0, 0), (300, 0, 0)))
FOLDED = (
    "The End Miter corner between {} and {} is at a folded corner of {}: the fingers go on a free end of a Folded Bar."
)
OPEN = (
    "The End Miter corner between {} and {} is at the open corner of {}: the fingers go on a free end of a Folded Bar."
)


def leaving(angle):
    """The axis of the bar's end tube from the corner at the origin, at the inner ``angle`` (degrees) from the axis of
    the loose tube, which arrives along +X."""
    return App.Vector(*polar(1.0, 180.0 - angle))


def turned(vector):
    """``vector`` turned 90 degrees counterclockwise about Z."""
    return App.Vector(-vector.y, vector.x, 0)


class MiterFingersOnBarFixture(TabsOnBarFixture):
    def mitered(self, body, others, gap=0.0):
        return make_end_miter_profile(body, others, True, gap)

    def recomputed(self, *objects):
        self.doc.recompute()
        for obj in objects:
            self.assertEqual("Valid", obj.getStatusString(), obj.Label)

    def user_corner(self, gap=0.0):
        """The user's layout with both free ends of the bar mitered against the loose bottom tube (as the End Miter
        panel makes them): ((bottom, right, top, left), bar, (bottom miter, right miter, left miter))."""
        (bottom, right, top, left), bar = self.make_legs()
        miters = (
            self.mitered(bottom, [right, left], gap),
            self.mitered(right, [bottom], gap),
            self.mitered(left, [bottom], gap),
        )
        self.recomputed(*miters)
        self.assertEqual([miters[1], top, miters[2]], list(bar.Segments))
        self.assertOneSolid(bar)
        # The bar reaches the outside of the bottom tube, half the gap (across the 45 degree miter plane) short of it.
        self.assertAlmostEqual(-25.0 + gap / 2 * math.sqrt(2.0), bar.Shape.BoundBox.YMin, delta=LENGTH_TOLERANCE)
        return (bottom, right, top, left), bar, miters

    def oblique_corner(self, angle):
        """A loose tube along +X up to the origin and a bar of two tubes whose first one leaves the origin at the inner
        ``angle``, both mitered against each other: (loose, (end tube, other tube), bar, (loose miter, end miter))."""
        direction = leaving(angle)
        end = direction * 300.0
        far = end + turned(direction) * 200.0
        tubes = self.frame(edges=(((0, 0, 0), tuple(end)), (tuple(end), tuple(far))))
        bar = make_folded_bar(tubes, bend(**PLAIN))
        self.assertOneSolid(bar)
        loose = self.loose(((-300, 0, 0), (0, 0, 0)), "Loose")
        miters = (self.mitered(loose, [tubes[0]]), self.mitered(tubes[0], [loose]))
        self.recomputed(*miters)
        self.assertEqual([miters[1], tubes[1]], list(bar.Segments))
        return loose, tubes, bar, miters

    def on_the_bar(self, bar, point):
        return MiterFace(bar, face_at(bar, point), point)

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def assertRefused(self, message, first, second):
        """Neither ``miter_order`` nor ``make_miter_fingers`` accepts the faces; nothing is made."""
        names = self.names()
        order = miter_order(first, second)
        self.assertIsNone(order.first)
        self.assertEqual(message, str(order.error))
        with self.assertRaises(InterlockError) as raised:
            make_miter_fingers(first, second)
        self.assertEqual(message, str(raised.exception))
        self.assertEqual(names, self.names())

    def assertFoldsTheFingers(self, bar, index, piece, under, other, before):
        """The bar folds ``piece`` (the fingers of its tube ``index`` on ``under``) as one solid with the fingers and
        the cuts of the other tube's fingers, the Unfolded Bar carries both, and the bar is as long as the finger tips
        (S5). ``other``: the finger piece of the other tube; ``before``: (bar volume, unfolded volume, developed
        length) before the fingers."""
        volume, unfolded_volume, length = before
        unfolded = self.unfolded_of(bar)
        for obj in (piece, bar, unfolded):
            self.assertOneSolid(obj)
        self.assertEqual(piece, bar.Segments[index])
        self.assertFalse(piece.Visibility)
        self.assertFalse(under.Visibility)
        added, removed = piece.Shape.cut(under.Shape), under.Shape.cut(piece.Shape)
        self.assertGreater(added.Volume, VOLUME_TOLERANCE)
        self.assertGreater(removed.Volume, VOLUME_TOLERANCE)
        self.assertFilled(added.Volume, bar.Shape, added)
        self.assertFilled(0.0, bar.Shape, removed)
        self.assertFilled(added.Volume, unfolded.Shape, self.on_bar(bar, index, added))
        self.assertFilled(0.0, unfolded.Shape, self.on_bar(bar, index, removed))
        change = added.Volume - removed.Volume
        self.assertAlmostEqual(volume + change, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(unfolded_volume + change, unfolded.Shape.Volume, delta=VOLUME_TOLERANCE)
        # The fingers of both tubes interlock: the bar does not overlap the other tube.
        self.assertLess(bar.Shape.common(other.Shape).Volume, VOLUME_TOLERANCE)
        # S5: the bar is as long as the tips of its fingers reach past its End Miter.
        reach = piece.Length.Value - under.Length.Value
        self.assertGreaterEqual(reach, 0.0)
        self.assertAlmostEqual(length + reach, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        box = unfolded.Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(bar.DevelopedLength.Value, box.XLength, delta=LENGTH_TOLERANCE)
        rows, links = [], []
        traverse_assembly(rows, links, bar)
        self.assertEqual(f"{bar.DevelopedLength.Value:.1f}", rows[0]["length"])
        return reach

    def assertStraightSide(self, piece, under, tube, axis):
        """The loose tube's piece is as between two straight tubes (T2): on its newest piece, one solid, as long as it
        reaches along its ``axis``."""
        self.assertOneSolid(piece)
        self.assertEqual([piece, under, tube], list(piece_stack(piece)))
        self.assertEqual(piece, newest_piece(tube))
        low, high = along_extent(piece.Shape, axis)
        self.assertAlmostEqual(high - low, piece.Length.Value, places=6)


class FreeEndAndStraightTubeTest(MiterFingersOnBarFixture):
    """The user's case: the free end of the bar (the right tube) and the loose bottom tube at 90 degrees."""

    def fingers(self, gap=0.0, **settings):
        tubes, bar, miters = self.user_corner(gap)
        bottom, right = tubes[:2]
        before = (bar.Shape.Volume, *self.straight(bar))
        interlock = make_miter_fingers(
            self.on_the_bar(bar, RIGHT_INNER), MiterFace(miters[0], face_towards(miters[0], Y), None), **settings
        )
        self.doc.recompute()
        return tubes, bar, miters, interlock, before

    def assertFingersOnTheFreeEnd(self, gap):
        (bottom, right, top, left), bar, miters, interlock, before = self.fingers(gap)
        bottom_miter, right_miter, left_miter = miters

        self.assertTrue(is_miter_interlock(interlock))
        self.assertEqual((right, bottom), (interlock.PieceA, interlock.PieceB))
        self.assertEqual((right_miter, bottom_miter), (interlock.FaceA[0], interlock.FaceB[0]))
        piece_a, piece_b = miter_pieces(interlock)
        self.assertEqual([piece_a, right_miter, right], list(piece_stack(piece_a)))
        self.assertEqual([piece_a, top, left_miter], list(bar.Segments))
        self.assertFoldsTheFingers(bar, 0, piece_a, right_miter, piece_b, before)
        self.assertStraightSide(piece_b, bottom_miter, bottom, X)
        self.assertNotIn(interlock, bar.Interlocks)

    def test_the_free_end_of_the_bar_and_the_straight_tube_get_fingers_and_the_bar_folds_them(self):
        self.assertFingersOnTheFreeEnd(0.0)

    def test_the_fingers_cross_the_miter_gap_on_the_bar_too(self):
        self.assertFingersOnTheFreeEnd(GAP)

    def test_the_straight_tube_clicked_first_owns_the_first_finger_and_the_bar_still_folds(self):
        tubes, bar, miters = self.user_corner()
        bottom, right = tubes[:2]
        before = (bar.Shape.Volume, *self.straight(bar))

        interlock = make_miter_fingers(
            MiterFace(miters[0], face_towards(miters[0], Y), None), self.on_the_bar(bar, RIGHT_INNER), Flip=True
        )
        self.doc.recompute()

        self.assertEqual((bottom, right), (interlock.PieceA, interlock.PieceB))
        piece_a, piece_b = miter_pieces(interlock)
        self.assertFoldsTheFingers(bar, 0, piece_b, miters[1], piece_a, before)
        self.assertStraightSide(piece_a, miters[0], bottom, X)

    def test_deleting_the_interlock_gives_the_bar_its_miter_back_and_undo_brings_the_fingers_back(self):
        self.doc.UndoMode = 1
        (bottom, right, top, left), bar, miters, interlock, before = self.fingers()
        bottom_miter, right_miter, left_miter = miters
        piece_a, piece_b = miter_pieces(interlock)
        names = (interlock.Name, piece_a.Name, piece_b.Name)
        fingered = (bar.Shape.Volume, self.unfolded_of(bar).Shape.Volume, bar.DevelopedLength.Value)

        self.doc.openTransaction("Delete")
        self.doc.removeObject(interlock.Name)
        self.doc.commitTransaction()
        self.doc.recompute()

        def gone():
            self.assertEqual([None] * 3, [self.doc.getObject(name) for name in names])
            self.assertEqual([right_miter, top, left_miter], list(bar.Segments))
            for obj in (bar, self.unfolded_of(bar)):
                self.assertOneSolid(obj)
            self.assertAlmostEqual(before[0], bar.Shape.Volume, delta=VOLUME_TOLERANCE)
            self.assertAlmostEqual(before[1], self.unfolded_of(bar).Shape.Volume, delta=VOLUME_TOLERANCE)
            self.assertAlmostEqual(before[2], bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
            self.assertFalse(right_miter.Visibility)
            self.assertEqual(bottom_miter, newest_piece(bottom))
            self.assertTrue(bottom_miter.Visibility)

        gone()
        self.doc.undo()
        self.doc.recompute()
        interlock, piece_a, piece_b = (self.doc.getObject(name) for name in names)
        self.assertEqual([piece_a, piece_b], miter_pieces(interlock))
        self.assertEqual([piece_a, top, left_miter], list(bar.Segments))
        for obj in (piece_a, piece_b, bar, self.unfolded_of(bar)):
            self.assertOneSolid(obj)
        self.assertAlmostEqual(fingered[0], bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(fingered[1], self.unfolded_of(bar).Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(fingered[2], bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        self.doc.redo()
        self.doc.recompute()
        gone()

    def test_a_saved_bar_with_fingers_opens_with_them(self):
        _, bar, _, interlock, _ = self.fingers(Count=4)
        piece_a, piece_b = miter_pieces(interlock)
        names = [segment.Name for segment in bar.Segments]
        bar_name, piece_names = bar.Name, (piece_a.Name, piece_b.Name)
        volumes = (bar.Shape.Volume, piece_b.Shape.Volume)
        length = bar.DevelopedLength.Value
        folder = tempfile.mkdtemp(prefix="mpf_miter_finger_interlock_folded_bar_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)

        # The cleanup of the fixture closes the document by this same name.
        self.doc = App.openDocument(path)
        bar = self.doc.getObject(bar_name)
        self.assertEqual(names, [segment.Name for segment in bar.Segments])
        for name in piece_names:
            self.doc.getObject(name).touch()
        self.doc.recompute()

        piece_a, piece_b = (self.doc.getObject(name) for name in piece_names)
        self.assertEqual(names, [segment.Name for segment in bar.Segments])
        for obj in (piece_a, piece_b, bar):
            self.assertOneSolid(obj)
        self.assertAlmostEqual(volumes[0], bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(volumes[1], piece_b.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)

    def test_a_click_on_a_bend_of_the_bar_is_refused(self):
        _, bar, miters = self.user_corner()
        point = self.bend_point(bar, 45.0)

        self.assertRefused(
            BEND_MESSAGE, self.on_the_bar(bar, point), MiterFace(miters[0], face_towards(miters[0], Y), None)
        )


class ObliqueFreeEndTest(MiterFingersOnBarFixture):
    """The free end of a bar and a straight tube at an oblique corner, the bar's end tube clicked first."""

    def assertFingersAt(self, angle, **settings):
        loose, tubes, bar, miters = self.oblique_corner(angle)
        before = (bar.Shape.Volume, *self.straight(bar))
        direction = leaving(angle)
        # Halfway along the inner wall of the end tube (25 from its axis, toward the inside of the corner).
        point = direction * 150.0 + turned(direction) * 25.0

        interlock = make_miter_fingers(
            self.on_the_bar(bar, point), MiterFace(miters[0], face_towards(miters[0], Y), None), **settings
        )
        self.doc.recompute()

        piece_a, piece_b = miter_pieces(interlock)
        self.assertEqual((tubes[0], loose), (interlock.PieceA, interlock.PieceB))
        self.assertEqual([piece_a, tubes[1]], list(bar.Segments))
        reach = self.assertFoldsTheFingers(bar, 0, piece_a, miters[1], piece_b, before)
        self.assertStraightSide(piece_b, miters[0], loose, X)
        return reach

    def test_a_sharp_corner_gets_fingers_and_the_bar_folds_them(self):
        self.assertFingersAt(60.0, Clearance=0.2)

    def test_an_obtuse_corner_gets_fingers_and_the_bar_folds_them(self):
        self.assertFingersAt(120.0, Count=2, Clearance=0.2)

    def test_a_wide_corner_with_deep_fingers_makes_the_bar_as_long_as_its_finger_tips(self):
        # At 150 degrees the miter point of a tube 50 deep is 50 tan(15) = 13.4 past the inner vertex; fingers 10 deep
        # end 2 s = 20 past it: the bar is longer to cut than with its End Miter alone (S5).
        reach = self.assertFingersAt(150.0, Depth=10.0)
        self.assertGreater(reach, 1.0)


class TwoBarsTest(MiterFingersOnBarFixture):
    """The free ends of two different bars, each mitered against the other's end tube."""

    def test_the_free_ends_of_two_bars_interlock_and_both_bars_fold_their_fingers(self):
        (right, top, left), bar = self.legs()
        back, end = self.frame(edges=OTHER_BAR)
        other_bar = make_folded_bar([back, end], bend(**PLAIN))
        self.assertOneSolid(other_bar)
        miters = (self.mitered(right, [end]), self.mitered(end, [right]))
        self.recomputed(*miters)
        self.assertEqual([miters[0], top, left], list(bar.Segments))
        self.assertEqual([back, miters[1]], list(other_bar.Segments))
        before = [(obj.Shape.Volume, *self.straight(obj)) for obj in (bar, other_bar)]
        # The inside of the corner is toward +X +Y: the outer wall of the first bar's right tube, the top of the
        # other bar's end tube.
        first, second = App.Vector(325, 100, 0), App.Vector(450, 25, 0)

        interlock = make_miter_fingers(self.on_the_bar(bar, first), self.on_the_bar(other_bar, second))
        self.doc.recompute()

        piece_a, piece_b = miter_pieces(interlock)
        self.assertEqual((right, end), (interlock.PieceA, interlock.PieceB))
        self.assertEqual([piece_a, top, left], list(bar.Segments))
        self.assertEqual([back, piece_b], list(other_bar.Segments))
        self.assertFoldsTheFingers(bar, 0, piece_a, miters[0], piece_b, before[0])
        self.assertFoldsTheFingers(other_bar, 1, piece_b, miters[1], piece_a, before[1])
        self.assertLess(bar.Shape.common(other_bar.Shape).Volume, VOLUME_TOLERANCE)
        for obj in (bar, other_bar):
            self.assertNotIn(interlock, obj.Interlocks)


class NotAFreeEndTest(MiterFingersOnBarFixture):
    """A tube of a bar whose end at the corner is not a free end of the bar is refused, naming the bar."""

    def test_a_folded_corner_of_the_bar_is_refused(self):
        (_, right, top, _), bar = self.make_legs()

        self.assertRefused(
            FOLDED.format(right.Label, top.Label, bar.Label),
            self.on_the_bar(bar, RIGHT_INNER),
            self.on_the_bar(bar, App.Vector(150, 175, 0)),
        )

    def test_the_open_corner_of_a_closed_bar_is_refused(self):
        (bottom, _, _, left), bar = self.make_bar(**PLAIN)

        self.assertRefused(
            OPEN.format(bottom.Label, left.Label, bar.Label),
            self.on_the_bar(bar, App.Vector(150, 25, 0)),
            self.on_the_bar(bar, App.Vector(25, 100, 0)),
        )

    def test_a_tube_of_the_bar_given_itself_is_refused_too(self):
        # A face of the tube the bar folds, not of the bar: the same refusal.
        (_, right, top, _), bar = self.make_legs()

        self.assertRefused(
            FOLDED.format(right.Label, top.Label, bar.Label),
            MiterFace(right, face_towards(right, -X), None),
            MiterFace(top, face_towards(top, -Y), None),
        )


if __name__ == "__main__":
    unittest.main()

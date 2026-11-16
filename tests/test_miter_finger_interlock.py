"""Fingers Interlock at an End Miter corner between two straight tubes (odd/tasks/miter-fingers.md, T2: S1 S5 S6, D1
D2; S2-S4 through the geometry of T1).

Two straight tubes A and B, each cut by its own End Miter against the other, get Fingers at the inner vertex of their
corner when the two faces given are their inner walls (S1): an Interlock of Kind Fingers marked as being at an End
Miter corner (D2), and one piece on top of each tube's newest piece that fuses its own fingers and cuts the other's
(D1). Both read the pieces under the finger pieces, so neither depends on the other. Without both End Miters against
each other the Interlock is refused saying what is missing (S6). Each tube is as long as the tips of its fingers (S5)
in the Cut List, the Piece Table and the BOM, and keeps the cut angles of its End Miter. Deleting the Interlock gives
the pieces under back; undo brings everything back. A Folded Bar never takes this Interlock: its folded-corner Fingers
work as before.
"""

import math
import os
import unittest
from unittest import mock

import FreeCAD as App
from miter_helpers import use_language
from test_end_miter_geometry import polar
from test_interlock import G, InterlockObjectFixture
from test_notch_geometry import TrimFixture
from test_tab_interlock import RADIUS, T, TabInterlockFixture

from freecad.maxproframe import miter_finger_interlock
from freecad.maxproframe._utils import piece_stack
from freecad.maxproframe.best_fit import CutPart, best_fit_decreasing
from freecad.maxproframe.create_bom import decimal_text, make_cut_list, traverse_assembly
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.cut_ends import cut_ends
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.extruded_cutout import along_extent
from freecad.maxproframe.folded_bar import bar_chain, corner_interlocks
from freecad.maxproframe.folded_chain import base_profile
from freecad.maxproframe.interlock import interlock_settings, is_interlock, is_miter_interlock, make_interlock
from freecad.maxproframe.interlock_geometry import FINGERS, FingerSettings, InterlockError
from freecad.maxproframe.miter_finger_interlock import (
    MiterFace,
    make_miter_fingers,
    miter_order,
    miter_pieces,
)
from freecad.maxproframe.piece_table import piece_texts
from freecad.maxproframe.profile_pattern import newest_piece

X, Y, Z = App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)
LENGTH = 300.0
VOLUME_TOLERANCE = 1e-3
NAMES = ("TubeA", "TubeB")
# The refusals name the tubes by their labels: {a} the first one, {b} the second one.
NOT_INNER = "The faces of {a} and {b} are not the inner walls of an End Miter corner between them."
MISSING_ONE = (
    "The fingers of the corner between {a} and {b} need an End Miter of {0} against {1}: make it with Miter Ends."
)
MISSING_BOTH = (
    "The fingers of the corner between {a} and {b} need an End Miter of each tube against the other: make them "
    "with Miter Ends."
)
SAME_TUBE = "Both faces are on {a}: click the inner wall of each tube of the End Miter corner."
TWICE = "The corner between {a} and {b} already has fingers: {0}."
NO_FINGER = "The interlock of the corner between {a} and {b} needs at least 2 fingers."
GAPS = "The End Miters of {a} and {b} have different gaps: give them the same Gap."
# angle (inner, degrees), End Miter Gap, outer corner radius of the tubes, settings
CASES = (
    (90.0, 0.0, RADIUS, {}),
    (90.0, 0.5, 0.0, dict(Clearance=0.2)),
    (60.0, 0.0, 0.0, dict(Count=2, Tip="Chamfer", TipSize=1.0, Clearance=0.2)),
    (120.0, 1.0, RADIUS, dict(Flip=True, Clearance=0.2)),
)


def leaving(angle):
    """The axis of B from the corner, at the inner ``angle`` (degrees) from A's axis away from the corner (-X)."""
    return App.Vector(*polar(1.0, 180.0 - angle))


def inner_normal_b(angle):
    """The outward normal of B's inner wall, toward the inside of the corner."""
    e = leaving(angle)
    return App.Vector(-e.y, e.x, 0)


class MiterCorner:
    """What a mitered corner is made of: profiles, End Miters and the inner wall normals of both tubes."""

    def __init__(self, a, b, miter_a, miter_b, angle):
        self.a, self.b, self.miter_a, self.miter_b, self.angle = a, b, miter_a, miter_b, angle
        self.normal_a, self.normal_b, self.axis_b = Y, inner_normal_b(angle), leaving(angle)

    def text(self, message, *values):
        """``message`` naming the tubes of this corner."""
        return message.format(*values, a=self.a.Label, b=self.b.Label)


class MiterCornerMixin:
    """Two straight TC80x40x1.5-like tubes meeting at a corner: A along +X up to ``origin``, B leaving it at the inner
    ``angle``; 80 across the corner plane, 40 along the corner axis (Z)."""

    def tubes(self, angle=90.0, radius=RADIUS, origin=(0.0, 0.0)):
        x, y = origin
        end = App.Vector(*polar(LENGTH, 180.0 - angle))
        a = TabInterlockFixture.tube(self, ((x - LENGTH, y, 0), (x, y, 0)), NAMES[0], radius)
        b = TabInterlockFixture.tube(self, ((x, y, 0), (x + end.x, y + end.y, 0)), NAMES[1], radius)
        return a, b

    def mitered(self, angle=90.0, gap=0.0, radius=RADIUS, origin=(0.0, 0.0), only=None):
        """The ``MiterCorner`` of both tubes, each cut by an End Miter against the other with ``gap``; ``only`` 0 or 1:
        only that tube is mitered (the other one keeps its profile)."""
        a, b = self.tubes(angle, radius, origin)
        miters = [a, b]
        for index, (body, other) in enumerate(((a, b), (b, a))):
            if only is None or only == index:
                miters[index] = make_end_miter_profile(body, [other], True, gap)
        self.doc.recompute()
        for obj in miters:
            self.assertEqual("Valid", obj.getStatusString())
        return MiterCorner(a, b, *miters, angle)

    def face(self, obj, normal):
        return TrimFixture.face_towards(self, obj, normal)

    def inner_faces(self, corner, a=None, b=None):
        """(MiterFace of A's inner wall, of B's inner wall) on ``a`` and ``b`` (default: the End Miters)."""
        a = corner.miter_a if a is None else a
        b = corner.miter_b if b is None else b
        return MiterFace(a, self.face(a, corner.normal_a), None), MiterFace(b, self.face(b, corner.normal_b), None)

    def fingers(self, angle=90.0, gap=0.0, radius=RADIUS, origin=(0.0, 0.0), **settings):
        """(corner, interlock, piece A, piece B) of a mitered corner with Fingers."""
        corner = self.mitered(angle, gap, radius, origin)
        interlock = make_miter_fingers(*self.inner_faces(corner), **settings)
        self.doc.recompute()
        return (corner, interlock, *miter_pieces(interlock))


class MiterFingersFixture(MiterCornerMixin, TabInterlockFixture):
    def assertInterlocked(self, corner, piece_a, piece_b):
        """Both pieces valid, one solid each, not overlapping; each one took some of the other's End Miter."""
        for obj in (piece_a, piece_b):
            self.assertOneSolid(obj)
        self.assertLess(piece_a.Shape.common(piece_b.Shape).Volume, VOLUME_TOLERANCE)
        for mine, theirs, plain in (
            (piece_a, corner.miter_b, corner.miter_a),
            (piece_b, corner.miter_a, corner.miter_b),
        ):
            # S4: the fingers cross the miter (and its gap) into where the other tube was.
            self.assertGreater(mine.Shape.common(theirs.Shape).Volume, 1.0)
            # The other tube's fingers took some of it.
            self.assertGreater(plain.Shape.cut(mine.Shape).Volume, 1.0)

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def assertRefused(self, message, first, second, **settings):
        """Neither ``miter_order`` nor ``make_miter_fingers`` accepts the faces; nothing is made."""
        names = self.names()
        order = miter_order(first, second, **settings)
        self.assertIsNone(order.first)
        self.assertEqual(message, str(order.error))
        with self.assertRaises(InterlockError) as raised:
            make_miter_fingers(first, second, **settings)
        self.assertEqual(message, str(raised.exception))
        self.assertEqual(names, self.names())
        return order

    @staticmethod
    def extent(obj, axis):
        low, high = along_extent(obj.Shape, axis)
        return high - low

    @staticmethod
    def level_point(s, z, deep):
        """A point of the overlap of both bands ``s`` deep at height ``z`` (90 degrees, corner at the origin): ``deep``
        past A's miter or before it."""
        vertex = App.Vector(-40.0, 40.0, z)
        return vertex + (App.Vector(0.75 * s, -0.25 * s, 0) if deep else App.Vector(0.25 * s, -0.75 * s, 0))


class MiterFingersTest(MiterFingersFixture):
    def test_a_miter_corner_gets_fingers_on_both_tubes(self):
        for index, (angle, gap, radius, settings) in enumerate(CASES):
            with self.subTest(angle=angle, gap=gap, radius=radius, settings=settings):
                corner, interlock, piece_a, piece_b = self.fingers(
                    angle, gap, radius, origin=(1000.0 * index, 0.0), **settings
                )

                self.assertTrue(is_interlock(interlock))
                self.assertTrue(is_miter_interlock(interlock))
                self.assertEqual(FINGERS, interlock.Kind)
                self.assertEqual((corner.a, corner.b), (interlock.PieceA, interlock.PieceB))
                expected = FingerSettings(
                    **{
                        field: settings[name]
                        for name, field in (
                            ("Count", "count"),
                            ("Tip", "tip"),
                            ("TipSize", "tip_size"),
                            ("Clearance", "clearance"),
                            ("Flip", "flip"),
                        )
                        if name in settings
                    }
                )
                self.assertEqual(expected, interlock_settings(interlock))
                self.assertEqual(
                    (f"{corner.miter_a.Label}_Fg", f"{corner.miter_b.Label}_Fg"), (piece_a.Label, piece_b.Label)
                )
                self.assertInterlocked(corner, piece_a, piece_b)
                # D1: on top of each tube's newest piece; no cycle between them.
                self.assertEqual([piece_a, corner.miter_a, corner.a], list(piece_stack(piece_a)))
                self.assertEqual([piece_b, corner.miter_b, corner.b], list(piece_stack(piece_b)))
                self.assertEqual((corner.a, corner.b), (base_profile(piece_a), base_profile(piece_b)))
                self.assertEqual((piece_a, piece_b), (newest_piece(corner.a), newest_piece(corner.b)))
                self.assertNotIn(piece_b, piece_a.OutListRecursive)
                self.assertNotIn(piece_a, piece_b.OutListRecursive)
                self.assertNotIn(interlock, piece_a.InListRecursive)
                # The tree: the Interlock under the first tube's piece; only the newest pieces show.
                self.assertEqual([corner.miter_a, interlock], piece_a.ViewObject.Proxy.claimChildren())
                self.assertEqual([corner.miter_b], piece_b.ViewObject.Proxy.claimChildren())
                self.assertFalse(corner.miter_a.ViewObject.Visibility)
                self.assertFalse(corner.miter_b.ViewObject.Visibility)
                for obj in (piece_a, piece_b):
                    self.assertEqual("interlock-fingers.svg", os.path.basename(obj.ViewObject.Proxy.getIcon()))
                    self.assertTrue(os.path.isfile(obj.ViewObject.Proxy.getIcon()))
                # No Folded Bar lists it.
                self.assertFalse(any(interlock in getattr(obj, "Interlocks", ()) for obj in self.doc.Objects))

    def test_the_first_face_owns_the_first_finger_and_flip_swaps(self):
        # 90 degrees, R = 3: the levels of Count 3 along Z (40 high, centered); probed where both walls overlap.
        corner, interlock, piece_a, piece_b = self.fingers()
        bounds = FingerSettings().bounds(40.0)
        middle = [(low + high) / 2 for low, high in zip(bounds, bounds[1:])]

        def owners():
            found = []
            for z in middle:
                inside = [
                    all(obj.Shape.isInside(self.level_point(T, z, deep), 1e-7, False) for deep in (0, 1))
                    for obj in (piece_a, piece_b)
                ]
                self.assertEqual(1, inside.count(True), (z, inside))
                found.append(inside.index(True))
            return found

        self.assertEqual([0, 1, 0], owners())
        interlock.Flip = True
        self.doc.recompute()
        self.assertEqual([1, 0, 1], owners())

    def test_both_end_miters_are_required(self):
        # S6: only A is mitered against B.
        corner = self.mitered(only=0)
        first, second = self.inner_faces(corner)
        order = self.assertRefused(corner.text(MISSING_ONE, corner.b.Label, corner.a.Label), first, second)
        self.assertTrue(order.found)
        # Only B is mitered against A.
        corner = self.mitered(origin=(1000.0, 0.0), only=1)
        order = self.assertRefused(corner.text(MISSING_ONE, corner.a.Label, corner.b.Label), *self.inner_faces(corner))
        self.assertTrue(order.found)
        # Neither: two plain tubes.
        a, b = self.tubes(origin=(2000.0, 0.0))
        order = self.assertRefused(
            MISSING_BOTH.format(a=a.Label, b=b.Label),
            MiterFace(a, self.face(a, Y), None),
            MiterFace(b, self.face(b, -X), None),
        )
        self.assertFalse(order.found)

    def test_faces_that_are_not_the_inner_walls_are_refused(self):
        corner = self.mitered()
        a, b = corner.miter_a, corner.miter_b
        for first, second in (
            (self.face(a, -Y), self.face(b, X)),
            (self.face(a, Z), self.face(b, Z)),
            (self.face(a, Y), self.face(b, Z)),
            (self.face(a, -X), self.face(b, X)),
        ):
            with self.subTest(first=first, second=second):
                self.assertRefused(corner.text(NOT_INNER), MiterFace(a, first, None), MiterFace(b, second, None))
        self.assertRefused(
            corner.text(SAME_TUBE), MiterFace(a, self.face(a, Y), None), MiterFace(a, self.face(a, Z), None)
        )
        self.assertRefused(corner.text(NO_FINGER), *self.inner_faces(corner), Count=1)
        with self.assertRaises(ValueError):
            make_miter_fingers(*self.inner_faces(corner), Length=3.0)

    def test_one_interlock_per_corner(self):
        corner, interlock, piece_a, piece_b = self.fingers()
        twice = corner.text(TWICE, interlock.Label)
        self.assertRefused(twice, *self.inner_faces(corner, piece_a, piece_b))
        self.assertRefused(twice, *self.inner_faces(corner))

    def test_one_interlock_per_corner_whatever_the_click_order(self):
        # S2: the second tube's wall clicked first names the corner the other way round; it has fingers all the same.
        corner, interlock, piece_a, piece_b = self.fingers()
        twice = TWICE.format(interlock.Label, a=corner.b.Label, b=corner.a.Label)
        for first, second in (self.inner_faces(corner, piece_a, piece_b), self.inner_faces(corner)):
            with self.subTest(first=first.piece.Label):
                self.assertRefused(twice, second, first)

    def test_an_extend_cut_or_an_end_miter_against_a_third_tube_is_no_end_miter_of_the_corner(self):
        # S6: B is cut, but not by an End Miter against A.
        corner = self.mitered(only=0)
        cut = make_extend_cut_profile(corner.b, (corner.a, (self.face(corner.a, Y),)))
        self.doc.recompute()
        self.assertEqual("Valid", cut.getStatusString())
        order = self.assertRefused(
            corner.text(MISSING_ONE, corner.b.Label, corner.a.Label),
            MiterFace(corner.miter_a, self.face(corner.miter_a, Y), None),
            MiterFace(cut, self.face(cut, -X), None),
        )
        self.assertTrue(order.found)

        # B mitered against a third tube C, leaving the corner along +X.
        a, b = self.tubes(origin=(1000.0, 0.0))
        c = self.tube(((1000.0, 0, 0), (1000.0 + LENGTH, 0, 0)), "TubeC", RADIUS)
        miter_a = make_end_miter_profile(a, [b], True, 0.0)
        miter_b = make_end_miter_profile(b, [c], True, 0.0)
        self.doc.recompute()
        for obj in (miter_a, miter_b):
            self.assertEqual("Valid", obj.getStatusString())
        order = self.assertRefused(
            MISSING_ONE.format(b.Label, a.Label, a=a.Label, b=b.Label),
            MiterFace(miter_a, self.face(miter_a, Y), None),
            MiterFace(miter_b, self.face(miter_b, -X), None),
        )
        self.assertTrue(order.found)

    def test_end_miters_with_different_gaps_are_refused(self):
        corner = self.mitered(gap=0.5)
        corner.miter_b.MiterGap = 0.0
        self.doc.recompute()
        self.assertRefused(corner.text(GAPS), *self.inner_faces(corner))

        # One Gap changed after the fingers are made: both pieces say so, with the shapes under them.
        corner, _, piece_a, piece_b = self.fingers(gap=0.5, origin=(1000.0, 0.0))
        corner.miter_a.MiterGap = 1.0
        self.doc.recompute()
        for obj, base in ((piece_a, corner.miter_a), (piece_b, corner.miter_b)):
            self.assertIn("Invalid", obj.State)
            self.assertEqual(corner.text(GAPS), obj.getStatusString())
            self.assertAlmostEqual(base.Shape.Volume, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
        corner.miter_b.MiterGap = 1.0
        self.doc.recompute()
        self.assertInterlocked(corner, piece_a, piece_b)

    def test_the_faces_clicked_on_older_pieces_go_on_the_newest_ones(self):
        corner = self.mitered()
        interlock = make_miter_fingers(
            MiterFace(corner.a, self.face(corner.a, Y), None), MiterFace(corner.b, self.face(corner.b, -X), None)
        )
        self.doc.recompute()
        piece_a, piece_b = miter_pieces(interlock)
        self.assertEqual((corner.miter_a, corner.miter_b), (piece_a.baseObject[0], piece_b.baseObject[0]))
        self.assertEqual((corner.miter_a, corner.miter_b), (interlock.FaceA[0], interlock.FaceB[0]))
        self.assertInterlocked(corner, piece_a, piece_b)
        order = miter_order(*self.inner_faces(self.mitered(origin=(1000.0, 0.0))))
        self.assertIsNone(order.error)
        self.assertTrue(order.found)


class MiterFingersLengthTest(MiterFingersFixture):
    """S5: each tube is as long as it reaches along its axis, finger tips included; its cut angles are its End
    Miter's."""

    def assertLengthToTheTips(self, corner, piece_a, piece_b):
        for piece, miter, axis in ((piece_a, corner.miter_a, X), (piece_b, corner.miter_b, corner.axis_b)):
            self.assertAlmostEqual(self.extent(piece, axis), piece.Length.Value, places=6)
            rows, links = [], []
            traverse_assembly(rows, links, piece)
            traverse_assembly(rows, links, miter)
            row, miter_row = rows
            self.assertEqual(f"{piece.Length.Value:.1f}", row["length"])
            self.assertEqual(decimal_text(piece.Length.Value), piece_texts(piece)[1])
            # The fingers are cut with the miter end: the piece keeps the angles of its End Miter.
            self.assertEqual(cut_ends(miter), cut_ends(piece))
            self.assertEqual(
                (miter_row["cut_angle_1"], miter_row["cut_angle_2"], miter_row["ends"]),
                (row["cut_angle_1"], row["cut_angle_2"], row["ends"]),
            )
            self.assertEqual((miter.CuttingAngleA, miter.CuttingAngleB), (piece.CuttingAngleA, piece.CuttingAngleB))
            self.assertEqual(miter.Cutout, piece.Cutout)

    def test_at_usual_angles_the_miter_point_is_farther_than_the_finger_tips(self):
        for index, (angle, gap, radius, settings) in enumerate(CASES):
            with self.subTest(angle=angle, gap=gap, radius=radius):
                corner, _, piece_a, piece_b = self.fingers(angle, gap, radius, (1000.0 * index, 0.0), **settings)
                self.assertLengthToTheTips(corner, piece_a, piece_b)
                self.assertAlmostEqual(corner.miter_a.Length.Value, piece_a.Length.Value, places=6)

    def test_a_wide_corner_with_deep_fingers_is_as_long_as_its_finger_tips(self):
        # At 150 degrees the miter point of a tube 80 deep is 80 tan(15) = 21.4 past the inner vertex; fingers 15 deep
        # end 2 s = 30 past it: the tube is longer to cut than its End Miter.
        corner, interlock, piece_a, piece_b = self.fingers(150.0, Depth=15.0)
        self.assertInterlocked(corner, piece_a, piece_b)
        self.assertLengthToTheTips(corner, piece_a, piece_b)
        for piece, miter in ((piece_a, corner.miter_a), (piece_b, corner.miter_b)):
            self.assertAlmostEqual(
                miter.Length.Value + 30.0 - 80.0 * math.tan(math.radians(15.0)), piece.Length.Value, 6
            )
        # The Cut List cuts it that long.
        rows, links = [], []
        traverse_assembly(rows, links, piece_a)
        parts = [CutPart(row["label"], float(row["length"]), 1.0, row) for row in rows]
        sheet = self.doc.addObject("Spreadsheet::Sheet", "CutList")
        make_cut_list({"Steel": best_fit_decreasing(6000.0, parts)}, spreadsheet=sheet)
        self.doc.recompute()
        self.assertAlmostEqual(piece_a.Length.Value, float(sheet.getContents("D2").removeprefix("'")), places=1)
        # A hole drilled on the piece with fingers keeps its length to the tips.
        bottom = self.face(piece_a, -Z)
        hole = make_drill_hole((piece_a, (bottom,)), self.vertex_of(piece_a, bottom))
        hole.OffsetAlong, hole.OffsetAcross = 20.0, 20.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())
        self.assertAlmostEqual(piece_a.Length.Value, hole.Length.Value, places=6)


class MiterFingersLifeTest(MiterFingersFixture):
    def test_changing_a_setting_recomputes_both_pieces(self):
        corner, interlock, piece_a, piece_b = self.fingers()
        volumes = (piece_a.Shape.Volume, piece_b.Shape.Volume)

        interlock.Count, interlock.Clearance = 2, G
        self.doc.recompute()

        self.assertInterlocked(corner, piece_a, piece_b)
        self.assertNotAlmostEqual(volumes[0], piece_a.Shape.Volume, places=3)
        self.assertNotAlmostEqual(volumes[1], piece_b.Shape.Volume, places=3)

    def test_touching_a_tube_or_an_end_miter_recomputes_both_pieces_the_same(self):
        # D1: each piece reads the pieces under the other one, through the Interlock: neither depends on the other.
        corner, interlock, piece_a, piece_b = self.fingers()
        self.assertNotIn(piece_b, piece_a.OutListRecursive)
        self.assertNotIn(piece_a, piece_b.OutListRecursive)
        shapes = [obj.Shape.copy() for obj in (piece_a, piece_b)]
        lengths = [obj.Length.Value for obj in (piece_a, piece_b)]

        for touched in (corner.a, corner.b, corner.miter_a, corner.miter_b):
            with self.subTest(touched=touched.Label):
                # Each piece moves its fingers onto the piece under it once it has made them.
                with mock.patch.object(
                    miter_finger_interlock, "_in_frame", side_effect=miter_finger_interlock._in_frame
                ) as moved:
                    touched.touch()
                    self.doc.recompute()

                self.assertEqual(
                    sorted((corner.miter_a.Name, corner.miter_b.Name)),
                    sorted(call.args[0].Name for call in moved.call_args_list),
                )
                for obj, shape, length in zip((piece_a, piece_b), shapes, lengths):
                    self.assertOneSolid(obj)
                    self.assertLess(obj.Shape.cut(shape).Volume, VOLUME_TOLERANCE)
                    self.assertLess(shape.cut(obj.Shape).Volume, VOLUME_TOLERANCE)
                    self.assertAlmostEqual(length, obj.Length.Value, places=6)
                self.assertInterlocked(corner, piece_a, piece_b)

    def test_a_refused_setting_leaves_both_pieces_in_error_with_their_base_shapes(self):
        corner, interlock, piece_a, piece_b = self.fingers()

        interlock.Count = 1
        self.doc.recompute()

        for obj, base in ((piece_a, corner.miter_a), (piece_b, corner.miter_b)):
            self.assertIn("Invalid", obj.State)
            self.assertEqual(corner.text(NO_FINGER), obj.getStatusString())
            self.assertAlmostEqual(base.Shape.Volume, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
        interlock.Count = 3
        self.doc.recompute()
        self.assertInterlocked(corner, piece_a, piece_b)

    def test_editing_the_miter_gap_recomputes_the_fingers_across_it(self):
        corner, _, piece_a, piece_b = self.fingers()
        for gap in (0.5, 1.0, 0.0):
            with self.subTest(gap=gap):
                for miter in (corner.miter_a, corner.miter_b):
                    miter.MiterGap = gap
                self.doc.recompute()
                self.assertInterlocked(corner, piece_a, piece_b)
                self.assertLess(
                    piece_a.Shape.common(corner.miter_b.Shape).Volume
                    + piece_b.Shape.common(corner.miter_a.Shape).Volume,
                    2 * 40.0 * 3.0 * 6.0,
                )

    def test_deleting_the_interlock_gives_the_pieces_under_back_and_undo_brings_them_back(self):
        self.doc.UndoMode = 1
        corner, interlock, piece_a, piece_b = self.fingers()
        bottom = self.face(piece_b, -Z)
        hole = make_drill_hole((piece_b, (bottom,)), self.vertex_of(piece_b, bottom))
        hole.OffsetAlong, hole.OffsetAcross = 20.0, 20.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())
        names = (interlock.Name, piece_a.Name, piece_b.Name)
        volumes = (piece_a.Shape.Volume, piece_b.Shape.Volume)

        self.doc.openTransaction("Delete")
        self.doc.removeObject(interlock.Name)
        self.doc.commitTransaction()
        self.doc.recompute()

        def gone():
            self.assertEqual([None] * 3, [self.doc.getObject(name) for name in names])
            self.assertEqual(corner.miter_a, newest_piece(corner.a))
            self.assertTrue(corner.miter_a.ViewObject.Visibility)
            # The hole drilled on B's fingers now drills B's End Miter.
            self.assertEqual(corner.miter_b, hole.baseObject[0])
            self.assertEqual("Valid", hole.getStatusString())

        gone()
        self.doc.undo()
        self.doc.recompute()
        interlock, piece_a, piece_b = (self.doc.getObject(name) for name in names)
        self.assertEqual([piece_a, piece_b], miter_pieces(interlock))
        self.assertEqual(piece_b, hole.baseObject[0])
        self.assertEqual(piece_a, newest_piece(corner.a))
        for expected, obj in zip(volumes, (piece_a, piece_b)):
            self.assertOneSolid(obj)
            self.assertAlmostEqual(expected, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.doc.redo()
        self.doc.recompute()
        gone()

    def test_a_saved_interlock_opens_and_finds_its_faces_again(self):
        _, interlock, piece_a, piece_b = self.fingers(120.0, 0.5, Count=4, Clearance=0.2)
        names = (interlock.Name, piece_a.Name, piece_b.Name)
        volumes = (piece_a.Shape.Volume, piece_b.Shape.Volume)
        lengths = (piece_a.Length.Value, piece_b.Length.Value)

        self.reopen()

        interlock, piece_a, piece_b = (self.doc.getObject(name) for name in names)
        self.assertTrue(is_miter_interlock(interlock))
        self.assertEqual(FingerSettings(count=4, clearance=0.2), interlock_settings(interlock))
        self.assertEqual([piece_a, piece_b], miter_pieces(interlock))
        # A face name that no longer names the face picked: the face on its plane is found again.
        first, _ = interlock.FaceA
        second, _ = interlock.FaceB
        interlock.FaceA = (first, ("Face1",))
        interlock.FaceB = (second, ("?Face2",))
        for obj in (piece_a, piece_b):
            obj.touch()
        self.doc.recompute()
        for expected, length, obj in zip(volumes, lengths, (piece_a, piece_b)):
            self.assertOneSolid(obj)
            self.assertAlmostEqual(expected, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
            self.assertAlmostEqual(length, obj.Length.Value, places=6)

    def test_a_reopened_wide_corner_keeps_its_length_to_the_finger_tips_before_any_recompute(self):
        # S5: the Length saved is the one to the tips, not the End Miter's, until the next recompute too.
        corner, _, piece_a, piece_b = self.fingers(150.0, Depth=15.0)
        names = (piece_a.Name, piece_b.Name)
        lengths = (piece_a.Length.Value, piece_b.Length.Value)
        for length, miter in zip(lengths, (corner.miter_a, corner.miter_b)):
            self.assertGreater(length, miter.Length.Value + 1.0)

        self.reopen()

        for name, length in zip(names, lengths):
            self.assertAlmostEqual(length, self.doc.getObject(name).Length.Value, places=6)


class FoldedBarBesideMiterFingersTest(MiterCornerMixin, InterlockObjectFixture):
    """A folded-corner Fingers Interlock works as before; a Folded Bar never takes a miter-corner Interlock."""

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")

    def test_a_bar_folds_its_fingers_and_leaves_a_miter_interlock_out(self):
        profiles, bar = self.make_bar(container=None)
        bottom, right, _, _ = profiles
        folded = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()
        self.assertFalse(is_miter_interlock(folded))
        expected = self.assertFolds(bar, profiles, FingerSettings(clearance=G))

        corner = self.mitered(origin=(5000.0, 5000.0))
        interlock = make_miter_fingers(*self.inner_faces(corner), Clearance=G)
        self.doc.recompute()
        self.assertTrue(is_miter_interlock(interlock))
        piece_a, piece_b = miter_pieces(interlock)
        for obj in (piece_a, piece_b):
            self.assertOneSolid(obj)
        self.assertFolds(bar, profiles, FingerSettings(clearance=G))

        # Even listed by the bar, it is on none of its folded corners: the bar leaves it out.
        bar.Interlocks = [*bar.Interlocks, interlock]
        self.doc.recompute()
        self.assertEqual([folded, None, None], corner_interlocks(bar, bar_chain(bar)))
        self.assertFolds(bar, profiles, FingerSettings(clearance=G))
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)


if __name__ == "__main__":
    unittest.main()

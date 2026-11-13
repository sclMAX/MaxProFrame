"""Shared ground of the click-to-add tools on a Folded Bar (odd/tasks/folded-bar-tools.md, T1: S4 S5).

The layout is the user's (L1): a Folded Bar of three tubes (right, top, left) with the bottom tube loose. A click on
the bar names the tube under the clicked point and that tube's own face (``folded_bar.segment_at``): the side walls
of the bar span several tubes, so the point picks the tube, not the face name. A point on a bend zone is on no single
straight tube face: the tools that need a face or a point refuse it with "Click a straight part of the folded bar.",
the whole-profile ones take the nearest tube. A piece made later on a tube of the bar is folded into it at the next
recompute of the document, without touching the bar, and the tube stays hidden (S4). A piece released from the bar
(``folded_bar.release_piece``) before it is removed leaves the bar folding the piece under it, as before.
"""

import math
import unittest

import FreeCAD as App
import Part
from test_folded_bar import FoldedBarFixture
from test_unfolded_geometry import PLAIN, STEEL, bend

from freecad.maxproframe import folded_bar
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.folded_geometry import fold
from freecad.maxproframe.profile_pattern import container_placement, placed

BEND_MESSAGE = "Click a straight part of the folded bar."
ON_FACE = 1e-6
PARALLEL = 1e-9


def global_shape(obj):
    return placed(obj.Shape, container_placement(obj))


def face_at(obj, point):
    """Name of the face of ``obj`` the global ``point`` lies on (the first one), or None."""
    vertex = Part.Vertex(point)
    for index, face in enumerate(global_shape(obj).Faces, 1):
        if face.distToShape(vertex)[0] <= ON_FACE:
            return f"Face{index}"
    return None


def normal_of(obj, sub):
    face = global_shape(obj).getElement(sub)
    return face.Surface.Axis


class FoldedBarToolsFixture(FoldedBarFixture):
    def make_legs(self):
        """The user's layout: the right, top and left tubes folded into one bar, the bottom one loose."""
        bottom, right, top, left = self.frame()
        bar = folded_bar.make_folded_bar([right, top, left], bend(**PLAIN))
        self.assertOneSolid(bar)
        return (bottom, right, top, left), bar

    def bend_point(self, bar, degrees):
        """Point on the outer face of the bend of the corner between the right and top tubes, ``degrees`` from +X."""
        radius = STEEL.outer_radius
        center = App.Vector(325 - radius, 225 - radius, 0)
        point = center + App.Vector(math.cos(math.radians(degrees)), math.sin(math.radians(degrees)), 0) * radius
        self.assertIsNotNone(face_at(bar, point), "the point is not on the bar")
        return point

    def pick(self, bar, point, nearest=False):
        sub = face_at(bar, point)
        self.assertIsNotNone(sub, f"{point} is not on the bar")
        return folded_bar.segment_at(bar, sub, point, nearest=nearest)

    def assertPicked(self, tube, normal, pick, point):
        self.assertIsNone(pick.reason)
        self.assertEqual(tube, pick.tip)
        self.assertIsNotNone(pick.face)
        face = global_shape(tube).getElement(pick.face)
        self.assertLessEqual(face.distToShape(Part.Vertex(point))[0], ON_FACE)
        self.assertLess(face.Surface.Axis.cross(App.Vector(*normal)).Length, PARALLEL)
        self.assertLess((pick.point - point).Length, ON_FACE)


class SegmentAtTest(FoldedBarToolsFixture):
    def test_a_point_on_a_side_wall_spanning_the_tubes_picks_the_tube_under_it_and_its_face(self):
        (_, right, top, left), bar = self.make_legs()
        points = {right: App.Vector(300, 100, 25), top: App.Vector(150, 200, 25), left: App.Vector(0, 100, 25)}

        # One face of the bar is the top wall of the three tubes.
        self.assertEqual(1, len({face_at(bar, point) for point in points.values()}))
        for tube, point in points.items():
            with self.subTest(tube=tube.Label):
                self.assertPicked(tube, (0, 0, 1), self.pick(bar, point), point)

    def test_a_point_on_an_outer_wall_picks_the_tube_under_it_and_its_face(self):
        (_, right, top, left), bar = self.make_legs()

        for tube, point, normal in (
            (right, App.Vector(325, 100, 0), (1, 0, 0)),
            (top, App.Vector(150, 225, 0), (0, 1, 0)),
            (left, App.Vector(-25, 100, 0), (1, 0, 0)),
        ):
            with self.subTest(tube=tube.Label):
                self.assertPicked(tube, normal, self.pick(bar, point), point)

    def test_a_point_on_a_bend_zone_is_refused_with_the_message(self):
        _, bar = self.make_legs()

        # The round outer wall of the bend, and the side wall where the two tubes meet at the corner.
        for point in (self.bend_point(bar, 45.0), App.Vector(285, 195, 25)):
            with self.subTest(point=point):
                pick = self.pick(bar, point)
                self.assertEqual(BEND_MESSAGE, pick.reason)
                self.assertIsNone(pick.tip)
                self.assertIsNone(pick.face)

    def test_nearest_mode_takes_the_nearest_tube_on_a_bend_and_the_face_on_a_straight_part(self):
        (_, right, top, _), bar = self.make_legs()

        for degrees, tube in ((20.0, right), (70.0, top)):
            with self.subTest(degrees=degrees):
                pick = self.pick(bar, self.bend_point(bar, degrees), nearest=True)
                self.assertIsNone(pick.reason)
                self.assertEqual(tube, pick.tip)
                self.assertIsNone(pick.face)
        point = App.Vector(150, 200, 25)
        self.assertPicked(top, (0, 0, 1), self.pick(bar, point, nearest=True), point)

    def test_without_a_point_the_center_of_the_clicked_face_picks(self):
        (_, right, _, _), bar = self.make_legs()
        point = App.Vector(325, 100, 0)

        pick = folded_bar.segment_at(bar, face_at(bar, point), None)

        self.assertIsNone(pick.reason)
        self.assertEqual(right, pick.tip)
        self.assertIsNotNone(pick.face)


class BarFollowsTest(FoldedBarToolsFixture):
    def miter_right(self, bottom, right):
        """An End Miter of the right tube against the loose bottom one: the free end of the bar."""
        return make_end_miter_profile(right, [bottom])

    def test_a_piece_made_on_a_tube_is_folded_in_at_the_next_recompute_and_stays_hidden(self):
        (bottom, right, top, left), bar = self.make_legs()
        self.assertAlmostEqual(0.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)

        miter = self.miter_right(bottom, right)
        self.doc.recompute()

        self.assertEqual("Valid", miter.getStatusString())
        self.assertEqual([miter, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertNotIn("Touched", bar.State)
        self.assertFalse(miter.Visibility)
        self.assertFalse(right.Visibility)
        expected = fold(build_chain([miter, top, left]), bend(**PLAIN))
        self.assertSameVolume(expected, bar.Shape)
        # The miter reaches the outside of the bottom tube.
        self.assertAlmostEqual(-25.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)

    def test_a_released_piece_removed_leaves_the_bar_as_before(self):
        (bottom, right, top, left), bar = self.make_legs()
        volume = bar.Shape.Volume
        miter = self.miter_right(bottom, right)
        self.doc.recompute()
        self.assertEqual([miter, top, left], list(bar.Segments))

        folded_bar.release_piece(miter)
        self.assertEqual([right, top, left], list(bar.Segments))
        if getattr(miter, "ViewObject", None) is not None:
            # As a delete in the tree would: the trimmed tube shows again.
            miter.ViewObject.Proxy.onDelete(miter.ViewObject, [])
        self.doc.removeObject(miter.Name)
        self.doc.recompute()

        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=1e-3)
        # Without the miter: the bar ends at the path again.
        self.assertAlmostEqual(0.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)
        self.assertFalse(right.Visibility)

    def test_a_removed_segment_does_not_break_the_recompute_of_the_others(self):
        (bottom, right, top, left), bar = self.make_legs()
        miter = self.miter_right(bottom, right)
        self.doc.recompute()

        # Removed without release: the bar loses the entry; the follow before the recompute skips it.
        self.doc.removeObject(miter.Name)
        self.doc.recompute()

        self.assertEqual("Valid", right.getStatusString())
        self.assertNotIn(None, list(bar.Segments))


if __name__ == "__main__":
    unittest.main()

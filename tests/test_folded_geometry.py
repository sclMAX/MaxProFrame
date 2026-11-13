"""Folded bar of a chain (odd/tasks/folded-miter.md, T4: S7 S14 S16, with S1 S8 S20 as they show folded).

The folded bar is rebuilt from the unfolded bar: each segment goes back where its profile was drawn and the outer
wall of each bend zone is revolved around its bend center, so the outside of the frame keeps its size and the outer
corners are round with the real radius; the notch flanks meet, the key tab fills its socket and the cuts made on the
segments stay where they were drawn.
"""

import math
import unittest
from types import SimpleNamespace

import FreeCAD as App
import Part
from test_end_miter_geometry import polar
from test_unfolded_geometry import DEPTH, PLAIN, STEEL, K, R, T, UnfoldFixture, bend, key_centers

from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.folded_geometry import fold, fold_bar
from freecad.maxproframe.unfolded_geometry import unfold

E = DEPTH / 2
# w of the middle of a side wall (the walls across the bend axis).
SIDE_WALL = DEPTH / 2 - T / 2
TOLERANCE = 1e-6
LENGTH_TOLERANCE = 1e-4
VOLUME_TOLERANCE = 1e-3
# The rectangle unfolded and folded with the default settings, shared by the tests that only read it (FoldFixture).
DEFAULT = {}


def box(center, size, rotation=None):
    """A box of ``size`` centered on ``center``, turned by ``rotation`` around its center."""
    shape = Part.makeBox(*size)
    shape.translate(App.Vector(*size) * -0.5)
    if rotation is not None:
        shape.Placement = App.Placement(App.Vector(), rotation).multiply(shape.Placement)
    shape.translate(App.Vector(*center))
    return shape


def forget_default(name):
    DEFAULT.clear()
    App.closeDocument(name)


class FoldFixture(UnfoldFixture):
    # Whether the tests of the class read ``self.default``: the rectangle with the default settings as (chain, unfolded,
    # folded), built once per test module in a document of its own that closes when the module ends.
    reads_default = False

    def setUp(self):
        if self.reads_default:
            # Built before the test's own document, which stays the active one.
            self.default = self.default_rectangle()
        super().setUp()

    def default_rectangle(self):
        if not DEFAULT:
            self.doc = App.newDocument("DefaultRectangle")
            unittest.addModuleCleanup(forget_default, self.doc.Name)
            chain = self.rectangle()
            unfolded = unfold(chain, STEEL)
            # What fold(chain, STEEL) computes.
            DEFAULT.update(chain=chain, unfolded=unfolded, folded=fold_bar(chain, unfolded))
        return SimpleNamespace(**DEFAULT)

    def solid(self, shape):
        self.assertIsInstance(shape, Part.Solid)
        self.assertTrue(shape.isValid())
        return shape

    def inside(self, shape, point):
        return shape.isInside(App.Vector(point), TOLERANCE, True)

    def common(self, shape, region):
        return shape.common(region).Volume

    @staticmethod
    def bisector(corner):
        """Outward unit vector on the bisector of ``corner``, across the bend axis."""
        n_after = App.Rotation(corner.axis, corner.bend_angle).multVec(corner.outer_normal)
        return (corner.outer_normal + n_after).normalize()

    def sharp(self, corner):
        """The virtual sharp outside corner of the frame (center anchored tube: the outer faces are E from the path)."""
        h = math.radians(corner.bend_angle) / 2
        return corner.point + self.bisector(corner) * (E / math.cos(h))

    def center(self, corner, r=R):
        """The bend center: r + t inside both outer faces."""
        h = math.radians(corner.bend_angle) / 2
        return corner.point + self.bisector(corner) * ((E - r - T) / math.cos(h))

    def mid_arc(self, corner, r=R):
        """Middle of the bent wall: on the bisector, r + t / 2 from the bend center."""
        return self.center(corner, r) + self.bisector(corner) * (r + T / 2)

    def assertRoundCorner(self, shape, corner, r=R, walls=(0.0, SIDE_WALL, -SIDE_WALL)):
        self.assertFalse(self.inside(shape, self.sharp(corner)))
        for w in walls:
            self.assertTrue(self.inside(shape, self.mid_arc(corner, r) + corner.axis * w), w)
            # Past the outside of the arc (r + t from its center) there is nothing.
            self.assertFalse(self.inside(shape, self.mid_arc(corner, r) + self.bisector(corner) * T + corner.axis * w))


class RectangleFoldTest(FoldFixture):
    reads_default = True

    def test_rectangle_folds_into_one_solid_with_the_outside_of_the_frame(self):
        chain = self.default.chain

        for options in (PLAIN, {}):
            with self.subTest(options=options):
                shape = self.solid(fold(chain, bend(**options)) if options else self.default.folded)
                box_ = shape.BoundBox
                for value, expected in (
                    (box_.XMin, -E),
                    (box_.XMax, 300 + E),
                    (box_.YMin, -E),
                    (box_.YMax, 200 + E),
                    (box_.ZMin, -E),
                    (box_.ZMax, E),
                ):
                    self.assertAlmostEqual(expected, value, delta=LENGTH_TOLERANCE)

    def test_folded_corners_are_round_with_the_real_radius(self):
        chain = self.default.chain
        shape = self.solid(self.default.folded)

        for corner in chain.corners:
            self.assertRoundCorner(shape, corner)

    def test_open_corner_keeps_the_tips(self):
        chain = self.default.chain
        shape = self.solid(self.default.folded)

        region = box((0, 0, 0), (80, 80, 60))
        tips = chain.segments[0].tip.Shape.fuse(chain.segments[-1].tip.Shape)
        self.assertGreater(self.common(tips, region), 0)
        self.assertAlmostEqual(self.common(tips, region), self.common(shape, region), delta=VOLUME_TOLERANCE)
        # The outer corner of the box at the open corner stays empty: neither tip reaches it.
        self.assertFalse(self.inside(shape, (-E / 2, -E / 2, 0)))

    def test_volume_adds_the_revolved_outer_wall_by_pappus(self):
        chain = self.default.chain
        # The relief takes the side walls out of the bend zone, so the folded pieces do not overlap the bent wall.
        options = dict(key=False)
        unfolded = unfold(chain, bend(**options))

        # What fold(chain, bend(**options)) computes.
        shape = self.solid(fold_bar(chain, unfolded))

        # The outer wall section (50 x 2) revolves with its centroid at r + t/2 from the axis instead of BA long flat.
        area = DEPTH * T
        added = sum(math.radians(c.bend_angle) * (T / 2 - K * T) * area for c in unfolded.corners)
        # The plain tips cross at the open corner: the folded solid holds what both share once.
        shared = self.common(chain.segments[0].tip.Shape, chain.segments[-1].tip.Shape)
        self.assertGreater(shared, 0)
        self.assertAlmostEqual(unfolded.shape.Volume + added - shared, shape.Volume, delta=VOLUME_TOLERANCE)

    def test_segments_far_from_the_corners_match_their_tips(self):
        chain = self.default.chain
        shape = self.solid(self.default.folded)

        for segment in chain.segments:
            middle = (segment.start + segment.end) * 0.5
            region = box(middle, (40, 40, 60))
            self.assertAlmostEqual(
                self.common(segment.tip.Shape, region), self.common(shape, region), delta=VOLUME_TOLERANCE
            )


class KeyFoldTest(FoldFixture):
    reads_default = True

    def test_tab_of_each_segment_fills_the_socket_of_the_next(self):
        unfolded = self.default.unfolded
        shape = self.solid(self.default.folded)

        for index, corner in enumerate(unfolded.corners):
            tab, socket = key_centers(corner)
            for w in (SIDE_WALL, -SIDE_WALL):
                straight_tab = corner.frame.multVec(App.Vector(*tab, w))
                straight_socket = corner.frame.multVec(App.Vector(*socket, w))
                folded_tab = unfolded.placements[index].inverse().multVec(straight_tab)
                folded_socket = unfolded.placements[index + 1].inverse().multVec(straight_socket)
                self.assertLess((folded_tab - folded_socket).Length, TOLERANCE, (index, w))
                self.assertTrue(self.inside(shape, folded_tab), (index, w))

    def test_clearance_leaves_a_gap_between_the_flanks(self):
        chain = self.default.chain
        tight = self.solid(self.default.folded)
        loose = self.solid(fold(chain, bend(clearance=1.0)))

        v = 12.0
        h = math.radians(45)
        for corner in chain.corners:
            # On the bisector, where both flanks meet, below the key and above the relief.
            point = self.center(corner) - self.bisector(corner) * ((v - R - T) / math.cos(h))
            for w in (SIDE_WALL, -SIDE_WALL):
                self.assertTrue(self.inside(tight, point + corner.axis * w))
                self.assertFalse(self.inside(loose, point + corner.axis * w))
            self.assertRoundCorner(loose, corner)

    def test_clearance_leaves_a_gap_along_the_relief_arcs(self):
        # S8 (L26): folded, the side walls of both segments stop the whole clearance short of the bent wall along
        # their relief arcs (the relief radius is the inside radius: the arcs are centered on the bend axis).
        chain = self.default.chain
        tight = self.solid(self.default.folded)
        loose = self.solid(fold(chain, bend(clearance=1.0, key=False)))

        for corner in chain.corners:
            center = self.center(corner)
            turn = corner.bend_angle / 8
            # Toward the bent wall, between it and the flank of the segment before and of the segment after.
            for angle in (turn, corner.bend_angle - turn):
                outward = App.Rotation(corner.axis, angle).multVec(corner.outer_normal)
                for distance, kept in ((R - 1.5, True), (R - 0.5, False), (R - 0.1, False), (R + T / 2, True)):
                    for w in (SIDE_WALL, -SIDE_WALL):
                        point = center + outward * distance + corner.axis * w
                        self.assertTrue(self.inside(tight, point), (angle, distance, w))
                        self.assertEqual(kept, self.inside(loose, point), (angle, distance, w))


class CornerRadiusFoldTest(FoldFixture):
    reads_default = True

    def test_one_corner_radius_changes_only_its_arc(self):
        chain = self.default.chain
        plain = self.solid(self.default.folded)

        shape = self.solid(fold(chain, [STEEL, bend(radius=6.0), STEEL]))

        corners = chain.corners
        self.assertRoundCorner(shape, corners[1], 6.0)
        self.assertTrue(self.inside(plain, self.mid_arc(corners[1])))
        self.assertFalse(self.inside(shape, self.mid_arc(corners[1])))
        for index, corner in enumerate(corners):
            region = box(self.sharp(corner), (100, 100, 60))
            if index == 1:
                self.assertGreater(abs(self.common(shape, region) - self.common(plain, region)), 1)
            else:
                self.assertRoundCorner(shape, corner)
                self.assertAlmostEqual(self.common(plain, region), self.common(shape, region), delta=VOLUME_TOLERANCE)


class ArbitraryAnglesFoldTest(FoldFixture):
    def chain(self):
        a = (0, 0, 0)
        b = (200, 0, 0)
        c = tuple(p + q for p, q in zip(b, polar(150, 60)))
        d = tuple(p + q for p, q in zip(c, polar(120, 195)))
        return build_chain(self.frame(edges=((a, b), (b, c), (c, d))))

    def test_any_angle_folds_into_one_solid_matching_the_tips(self):
        chain = self.chain()
        for options in (dict(key=False), {}):
            with self.subTest(options=options):
                shape = self.solid(fold(chain, bend(**options)))

                for index, segment in enumerate(chain.segments):
                    # Clear of the corners: a folded corner reaches e tan(theta / 2) along each segment (inner wall).
                    reaches = [
                        (
                            E * math.tan(math.radians(chain.corners[found].bend_angle) / 2)
                            if 0 <= found < len(chain.corners)
                            else 0.0
                        )
                        for found in (index - 1, index)
                    ]
                    along = (reaches[0] + segment.length - reaches[1]) / 2
                    turn = App.Rotation(App.Vector(1, 0, 0), segment.direction)
                    region = box(segment.start + segment.direction * along, (20, 56, 60), turn)
                    self.assertAlmostEqual(
                        self.common(segment.tip.Shape, region), self.common(shape, region), delta=VOLUME_TOLERANCE
                    )
                for corner in chain.corners:
                    self.assertRoundCorner(shape, corner, walls=(0.0, SIDE_WALL, -SIDE_WALL))


class FeatureFoldTest(FoldFixture):
    reads_default = True

    def test_hole_drilled_in_a_segment_stays_where_it_was_drawn(self):
        bottom, right, top, left = self.frame()
        faces = [
            (index, face)
            for index, face in enumerate(right.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).z > 1 - 1e-9
        ]
        top_face, _ = max(faces, key=lambda item: item[1].CenterOfMass.z)
        vertex = next(
            f"Vertex{index}"
            for index, found in enumerate(right.Shape.Vertexes, 1)
            if found.Point.isEqual(App.Vector(275, 0, 25), 1e-6)
        )
        # The same rectangle before the hole.
        plain = self.default.folded
        hole = make_drill_hole((right, (f"Face{top_face}",)), vertex)
        hole.OffsetAlong = 100.0
        hole.OffsetAcross = 25.0
        hole.Diameter = 10.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())

        shape = self.solid(fold(build_chain([bottom, right, top, left]), STEEL))

        self.assertAlmostEqual(plain.Volume - math.pi * 5**2 * T, shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertTrue(self.inside(plain, (300, 100, 24)))
        self.assertFalse(self.inside(shape, (300, 100, 24)))
        self.assertTrue(self.inside(shape, (300, 110, 24)))


if __name__ == "__main__":
    unittest.main()

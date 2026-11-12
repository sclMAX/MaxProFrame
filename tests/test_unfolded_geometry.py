"""Unfolded bar of a folded chain (odd/tasks/folded-miter.md, T3: S1 S3 S5 S6 S8 S9 S14 S15 S16 S17 S20).

The chain unbends into one straight solid along X: each folded corner keeps its outer wall whole through the bend
zone and gets a V notch (with its key and relief) in the other walls; the developed length follows the bend
configuration; the cuts made on the segments (miters, holes) move with them.
"""

import math
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import polar
from test_folded_chain import ChainFixture

from freecad.maxproframe.bend_config import BendConfiguration
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.trimmed_profile import TrimmedProfile
from freecad.maxproframe.unfolded_geometry import UnfoldError, unfold

# 50 x 50 x 2 square tube, centered on its path; the configuration bends its 2 mm walls with r = 3, K = 0.4.
STEEL = BendConfiguration("Steel 50x50x2", "Steel", 2.0, 3.0, 0.4)
R, T, K = 3.0, 2.0, 0.4
DEPTH = 50.0
# w of the middle of a side wall: the walls across the bend axis.
SIDE_WALL = DEPTH / 2 - T / 2
PLAIN = dict(key=False, relief=False)
TOLERANCE = 1e-6
LENGTH_TOLERANCE = 1e-4


def allowance(angle, r=R, k=K):
    return math.radians(angle) * (r + k * T)


def developed(lengths, angles, radii=None, k=K):
    """Developed length by the formula: outside mold line kept, each corner adds its bend allowance."""
    total = sum(lengths)
    for angle, r in zip(angles, radii or [R] * len(angles)):
        tangent = math.tan(math.radians(angle) / 2)
        total += 2 * (DEPTH / 2) * tangent - 2 * (r + T) * tangent + allowance(angle, r, k)
    return total


def key_centers(corner, r=R, rho=R, diameter=DEPTH / 4):
    """(u, v) of the bulb center of the tab (segment before) and of the socket (segment after), by the design."""
    h = math.radians(corner.bend_angle) / 2
    v_k = (T + rho + DEPTH - T) / 2
    s = (v_k - r - T) / math.cos(h)
    tab = (-s * math.sin(h) + diameter * math.cos(h), r + T + s * math.cos(h) + diameter * math.sin(h))
    socket = (
        corner.bend_allowance + s * math.sin(h) + diameter * math.cos(h),
        r + T + s * math.cos(h) - diameter * math.sin(h),
    )
    return tab, socket


class UnfoldFixture(ChainFixture):
    def rectangle(self):
        bottom, right, top, left = self.frame()
        return build_chain([bottom, right, top, left])

    def solid(self, bar):
        self.assertEqual(1, len(bar.shape.Solids))
        self.assertTrue(bar.shape.isValid())
        return bar.shape

    def assertLength(self, expected, bar):
        self.assertAlmostEqual(expected, bar.length, places=6)
        box = bar.shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(expected, box.XLength, delta=LENGTH_TOLERANCE)

    def filled(self, bar, corner, u, v, w):
        """Whether the bar has material at (u, v, w) of the frame of ``corner``."""
        return bar.shape.isInside(corner.frame.multVec(App.Vector(u, v, w)), TOLERANCE, True)

    def assertRefused(self, message, chain, configuration=STEEL, **kwargs):
        with self.assertRaises(UnfoldError) as raised:
            unfold(chain, configuration, **kwargs)
        self.assertIsInstance(raised.exception, ValueError)
        self.assertEqual(message, str(raised.exception))


class RectangleUnfoldTest(UnfoldFixture):
    def test_rectangle_unfolds_into_one_straight_solid_of_the_developed_length(self):
        bar = unfold(self.rectangle(), STEEL, **PLAIN)

        shape = self.solid(bar)
        ba = allowance(90)
        self.assertLength(1000 + 3 * (50 - 2 * 5 + (math.pi / 2) * (3 + 0.4 * 2)), bar)
        self.assertAlmostEqual(50.0, shape.BoundBox.YLength, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(50.0, shape.BoundBox.ZLength, delta=LENGTH_TOLERANCE)
        # Bend zone starts: X_i + L_i + e tan h - OSSB, with X_{i+1} = X_i + L_i + 2 e tan h - 2 OSSB + BA.
        starts = [320.0, 560.0 + ba, 900.0 + 2 * ba]
        self.assertEqual(3, len(bar.corners))
        for corner, start in zip(bar.corners, starts):
            self.assertAlmostEqual(90.0, corner.bend_angle, places=6)
            self.assertAlmostEqual(R, corner.inside_radius, places=9)
            self.assertAlmostEqual(ba, corner.bend_allowance, places=9)
            self.assertAlmostEqual(start, corner.start, places=6)
            self.assertAlmostEqual(start, corner.frame.Base.x, places=6)
            self.assertVector((1, 0, 0), corner.frame.Rotation.multVec(App.Vector(1, 0, 0)))
            # The origin is on the outside face of the bent wall at the section center: away from the notch (it
            # reaches u = -44 on the inner wall) the tube lies in 0 <= v <= depth, its side walls at w = +-24.
            for v, w, kept in (
                (T / 2, 0, True),
                (-T / 2, 0, False),
                (DEPTH - T / 2, 0, True),
                (DEPTH + T / 2, 0, False),
                (DEPTH / 2, SIDE_WALL, True),
                (DEPTH / 2, -SIDE_WALL, True),
                (DEPTH / 2, 0, False),
            ):
                self.assertEqual(kept, self.filled(bar, corner, -60, v, w), (v, w))

    def test_bar_starts_at_the_open_corner_end_of_the_first_segment(self):
        bottom, right, top, left = self.frame()
        chain = build_chain([bottom, right, top, left], open_corner=(bottom, right))

        bar = unfold(chain, STEEL, **PLAIN)

        self.solid(bar)
        self.assertLength(developed([300, 200, 300, 200], [90] * 3), bar)
        # The first segment runs from (300, 0) back to (0, 0): its first bend starts 300 + 25 - 5 from X = 0.
        self.assertAlmostEqual(320.0, bar.corners[0].start, places=6)
        for corner in bar.corners:
            self.assertTrue(self.filled(bar, corner, corner.bend_allowance / 2, T / 2, 0))
            self.assertFalse(self.filled(bar, corner, corner.bend_allowance / 2, DEPTH - T / 2, 0))

    def test_bent_wall_stays_whole_through_each_bend_and_the_other_walls_open(self):
        chain = self.rectangle()
        for options in (PLAIN, {}):
            with self.subTest(options=options):
                bar = unfold(chain, STEEL, **options)
                self.solid(bar)
                for corner in bar.corners:
                    ba = corner.bend_allowance
                    for u in (0.0, ba / 4, ba / 2, 3 * ba / 4, ba):
                        for w in (0.0, SIDE_WALL, -SIDE_WALL):
                            self.assertTrue(self.filled(bar, corner, u, T / 2, w), (u, w))
                    self.assertFalse(self.filled(bar, corner, ba / 2, DEPTH - T / 2, 0))
                    self.assertFalse(self.filled(bar, corner, ba / 2, DEPTH / 2, SIDE_WALL))
                    self.assertFalse(self.filled(bar, corner, ba / 2, DEPTH / 2, -SIDE_WALL))

    def test_relief_removes_the_side_walls_next_to_the_bent_wall(self):
        chain = self.rectangle()
        relieved = unfold(chain, STEEL, key=False)
        plain = unfold(chain, STEEL, **PLAIN)

        self.solid(relieved)
        self.assertAlmostEqual(plain.length, relieved.length, places=9)
        self.assertLess(relieved.shape.Volume, plain.shape.Volume)
        for corner, plain_corner in zip(relieved.corners, plain.corners):
            ba = corner.bend_allowance
            # Outside the V (its flanks are at u = 2.7 and 3.27 at v = 2.3) and between the relief discs.
            for u in (2.0, ba - 2.0):
                for w in (SIDE_WALL, -SIDE_WALL):
                    self.assertFalse(self.filled(relieved, corner, u, 2.3, w), (u, w))
                    self.assertTrue(self.filled(plain, plain_corner, u, 2.3, w), (u, w))
                    self.assertTrue(self.filled(relieved, corner, u, T / 2, w), (u, w))

    def test_clearance_moves_each_flank_back_half_of_it(self):
        chain = self.rectangle()
        tight = unfold(chain, STEEL, **PLAIN)
        loose = unfold(chain, STEEL, clearance=1.0, **PLAIN)

        self.solid(loose)
        self.assertAlmostEqual(tight.length, loose.length, places=9)
        v = DEPTH / 2
        for tight_corner, loose_corner in zip(tight.corners, loose.corners):
            ba = tight_corner.bend_allowance
            h = math.radians(45)
            # Flanks without clearance at height v, and the way back into the material of each segment.
            flanks = (
                ((-(v - R - T) * math.tan(h), v), (-math.cos(h), -math.sin(h))),
                ((ba + (v - R - T) * math.tan(h), v), (math.cos(h), -math.sin(h))),
            )
            for (u0, v0), (du, dv) in flanks:
                for back, kept in ((0.25, False), (0.75, True)):
                    u, w_v = u0 + back * du, v0 + back * dv
                    self.assertTrue(self.filled(tight, tight_corner, u, w_v, SIDE_WALL), (u, w_v))
                    self.assertEqual(kept, self.filled(loose, loose_corner, u, w_v, SIDE_WALL), (u, w_v, back))

    def test_key_keeps_a_tab_on_one_flank_and_cuts_its_socket_in_the_other(self):
        chain = self.rectangle()
        keyed = unfold(chain, STEEL)
        unkeyed = unfold(chain, STEEL, key=False)

        self.solid(keyed)
        self.solid(unkeyed)
        for keyed_corner, unkeyed_corner in zip(keyed.corners, unkeyed.corners):
            tab, socket = key_centers(keyed_corner)
            for w in (SIDE_WALL, -SIDE_WALL):
                self.assertTrue(self.filled(keyed, keyed_corner, *tab, w))
                self.assertFalse(self.filled(keyed, keyed_corner, *socket, w))
                self.assertFalse(self.filled(unkeyed, unkeyed_corner, *tab, w))
                self.assertTrue(self.filled(unkeyed, unkeyed_corner, *socket, w))

    def test_radius_outside_its_limits_is_refused(self):
        chain = self.rectangle()
        # min = t; max = depth - 2t - key diameter (depth / 4) with the key, depth - 2t without it.
        self.assertRefused("The inside bend radius must be between 2 and 33.5 mm.", chain, radius=1.9)
        self.assertRefused("The inside bend radius must be between 2 and 33.5 mm.", chain, radius=33.6)
        self.assertRefused("The inside bend radius must be between 2 and 46 mm.", chain, radius=46.1, key=False)
        self.assertRefused("The inside bend radius must be between 2 and 33.5 mm.", chain, corner_radii={1: 33.6})
        refused = BendConfiguration("Steel big radius", "Steel", 2.0, 40.0, 0.4)
        self.assertRefused("The inside bend radius must be between 2 and 33.5 mm.", chain, configuration=refused)

    def test_radius_at_its_limits_is_accepted(self):
        chain = self.rectangle()
        for radius, options in ((2.0, {}), (33.5, {}), (46.0, dict(key=False))):
            with self.subTest(radius=radius, options=options):
                bar = unfold(chain, STEEL, radius=radius, **options)
                self.solid(bar)
                self.assertLength(developed([300, 200, 300, 200], [90] * 3, [radius] * 3), bar)
                self.assertEqual([radius] * 3, [corner.inside_radius for corner in bar.corners])

    def test_one_corner_can_override_the_bar_radius(self):
        bar = unfold(self.rectangle(), STEEL, corner_radii={1: 6.0})

        self.solid(bar)
        self.assertEqual([R, 6.0, R], [corner.inside_radius for corner in bar.corners])
        self.assertAlmostEqual(allowance(90, 6.0), bar.corners[1].bend_allowance, places=9)
        self.assertLength(developed([300, 200, 300, 200], [90] * 3, [R, 6.0, R]), bar)

    def test_length_follows_the_bend_configuration(self):
        chain = self.rectangle()
        softer = BendConfiguration("Steel K 0.3", "Steel", 2.0, 3.0, 0.3)
        wider = BendConfiguration("Steel r 4", "Steel", 2.0, 4.0, 0.4)

        first = unfold(chain, STEEL, **PLAIN)
        second = unfold(chain, softer, **PLAIN)
        third = unfold(chain, wider, **PLAIN)

        self.assertAlmostEqual(3 * (math.pi / 2) * (0.4 - 0.3) * 2, first.length - second.length, places=6)
        self.assertLength(developed([300, 200, 300, 200], [90] * 3, k=0.3), second)
        self.assertEqual([4.0] * 3, [corner.inside_radius for corner in third.corners])
        self.assertLength(developed([300, 200, 300, 200], [90] * 3, [4.0] * 3), third)

    def test_configuration_for_other_walls_is_refused(self):
        thicker = BendConfiguration("Steel 2.5", "Steel", 2.5, 3.0, 0.4)

        self.assertRefused("Steel 2.5 is for 2.5 mm walls; Profile has 2 mm walls.", self.rectangle(), thicker)


class ArbitraryAnglesUnfoldTest(UnfoldFixture):
    def chain(self):
        a = (0, 0, 0)
        b = (200, 0, 0)
        c = tuple(p + q for p, q in zip(b, polar(150, 60)))
        d = tuple(p + q for p, q in zip(c, polar(120, 195)))
        return build_chain(self.frame(edges=((a, b), (b, c), (c, d))))

    def test_any_angle_unfolds_by_the_formula(self):
        bar = unfold(self.chain(), STEEL)

        self.solid(bar)
        self.assertLength(developed([200, 150, 120], [60, 135]), bar)
        self.assertEqual([60.0, 135.0], [round(corner.bend_angle, 6) for corner in bar.corners])
        for corner in bar.corners:
            ba = corner.bend_allowance
            self.assertAlmostEqual(allowance(corner.bend_angle), ba, places=9)
            for u in (0.0, ba / 2, ba):
                self.assertTrue(self.filled(bar, corner, u, T / 2, 0))
            self.assertFalse(self.filled(bar, corner, ba / 2, DEPTH - T / 2, 0))
            tab, socket = key_centers(corner)
            self.assertTrue(self.filled(bar, corner, *tab, SIDE_WALL))
            self.assertFalse(self.filled(bar, corner, *socket, SIDE_WALL))
        tangent = math.tan(math.radians(30))
        self.assertAlmostEqual(200 + 25 * tangent - 5 * tangent, bar.corners[0].start, places=6)

    def test_key_that_does_not_fit_in_the_notch_is_refused(self):
        # At 60 degrees a 36 mm bulb reaches past the other flank of the V.
        self.assertRefused(
            "The key does not fit in the notch between Profile and Profile001: make it smaller.",
            self.chain(),
            key_diameter=36.0,
        )


class FeatureTransferTest(UnfoldFixture):
    def mitered_rectangle(self):
        """Rectangle whose bottom and left profiles are End Mitered at the open corner (0, 0)."""
        bottom, right, top, left = self.frame()
        miters = []
        for body, boundary in ((bottom, left), (left, bottom)):
            miter = self.doc.addObject("Part::FeaturePython", "Miter")
            TrimmedProfile(miter)
            miter.TrimmedBody = body
            miter.TrimmingBoundary = [(boundary, ("Edge1",))]
            miter.TrimmedProfileType = "End Miter"
            miters.append(miter)
        self.doc.recompute()
        for miter in miters:
            self.assertEqual("Valid", miter.getStatusString())
        return build_chain([bottom, right, top, left]), miters

    @staticmethod
    def ends_normal_to_x(shape):
        return [
            face
            for face in shape.Faces
            if isinstance(face.Surface, Part.Plane) and abs(face.normalAt(0, 0).x) > 1 - 1e-9
        ]

    def test_end_miter_at_the_open_corner_slants_the_bar_ends(self):
        plain = unfold(self.rectangle(), STEEL, **PLAIN)
        chain, miters = self.mitered_rectangle()

        bar = unfold(chain, STEEL, **PLAIN)

        shape = self.solid(bar)
        self.assertEqual(2, len(self.ends_normal_to_x(plain.shape)))
        self.assertEqual([], self.ends_normal_to_x(shape))
        # Each miter reaches the outer corner of the frame: 25 mm past the path end on the outer wall.
        self.assertLength(plain.length + 2 * 25, bar)
        changed = sum(miter.Shape.Volume - miter.TrimmedBody.Shape.Volume for miter in miters)
        self.assertAlmostEqual(plain.shape.Volume + changed, shape.Volume, delta=1e-3)
        first, last = bar.corners[0], bar.corners[-1]
        # The 45 degree miter: the outer wall reaches the bar ends, the inner wall stops one depth (50 mm) earlier.
        for corner, end, inward in ((first, 0.0, 1), (last, bar.length, -1)):
            self.assertTrue(self.filled(bar, corner, end + inward * 2 - corner.start, T / 2, 0))
            self.assertFalse(self.filled(bar, corner, end + inward * 2 - corner.start, DEPTH - T / 2, 0))
            self.assertTrue(self.filled(bar, corner, end + inward * 51 - corner.start, DEPTH - T / 2, 0))
        for plain_corner, corner in zip(plain.corners, bar.corners):
            self.assertAlmostEqual(plain_corner.start + 25, corner.start, places=6)

    def test_hole_drilled_in_a_segment_moves_with_it(self):
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
        plain = unfold(build_chain([bottom, right, top, left]), STEEL, **PLAIN)
        hole = make_drill_hole((right, (f"Face{top_face}",)), vertex)
        hole.OffsetAlong = 100.0
        hole.OffsetAcross = 25.0
        hole.Diameter = 10.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())
        self.assertFalse(hole.Shape.isInside(App.Vector(300, 100, 24), TOLERANCE, True))

        bar = unfold(build_chain([bottom, right, top, left]), STEEL, **PLAIN)

        self.solid(bar)
        self.assertAlmostEqual(plain.length, bar.length, places=9)
        self.assertAlmostEqual(plain.shape.Volume - math.pi * 5**2 * T, bar.shape.Volume, delta=1e-3)
        corner = bar.corners[0]
        # The path of the right profile starts at u = BA + e tan h - OSSB in the frame of the first corner,
        # its outer wall is the bent wall and the top of the frame (global +Z) is the bend axis side w > 0.
        along = corner.bend_allowance + 20 + 100
        self.assertFalse(self.filled(bar, corner, along, DEPTH / 2, SIDE_WALL))
        self.assertTrue(self.filled(bar, corner, along + 10, DEPTH / 2, SIDE_WALL))
        self.assertTrue(self.filled(plain, plain.corners[0], along, DEPTH / 2, SIDE_WALL))


if __name__ == "__main__":
    unittest.main()

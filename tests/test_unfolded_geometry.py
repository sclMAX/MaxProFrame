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
# A simple bar: no key (the relief is always on, S8 L36).
PLAIN = dict(key=False)
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


def miter_line(corner, r=R, g=0.0, depth=DEPTH, t=T):
    """(start, end) of the miter line seen on the side wall of the folded bar, along the flank from the bend axis
    point (0, r + t) inward (S20, L33).

    The edge of the flank of the segment before, moved back g/2: from where it leaves the disc the relief keeps
    (radius r - g around the bend axis point) to the inner corner (v = depth).
    """
    h = math.radians(corner.bend_angle) / 2
    return -math.sqrt((r - g) ** 2 - (g / 2) ** 2), (depth - r - t + (g / 2) * math.sin(h)) / math.cos(h)


def key_along(corner, r=R, along=None, g=0.0, depth=DEPTH, t=T):
    """Where the key center sits on the miter line, from the bend axis point (0, r + t) inward: ``along`` when given
    (the key slid to where it fits, L32), else the middle of ``miter_line``."""
    if along is not None:
        return along
    return sum(miter_line(corner, r, g, depth, t)) / 2


def key_point(corner, x, y, after=False, r=R, along=None, g=0.0, depth=DEPTH, t=T):
    """(u, v) of the point (x, y) of the key frame of the segment before (or ``after``) of ``corner``.

    The key frame has its origin at the key center (``key_along``), on the miter line (the flank without clearance);
    x goes across the flank into the V for the segment before and into the material for the segment after; y goes
    along the flank.
    """
    h = math.radians(corner.bend_angle) / 2
    s = key_along(corner, r, along, g, depth, t) + y
    if after:
        return (
            corner.bend_allowance + s * math.sin(h) + x * math.cos(h),
            r + t + s * math.cos(h) - x * math.sin(h),
        )
    return (-s * math.sin(h) + x * math.cos(h), r + t + s * math.cos(h) + x * math.sin(h))


def key_centers(corner, r=R, diameter=DEPTH / 4):
    """(u, v) of a point in the middle of the tab (segment before) and of the socket (segment after).

    Both are a quarter of the diameter off the miter line, so they meet when the corner folds.
    """
    return key_point(corner, diameter / 4, 0.0, r=r), key_point(corner, diameter / 4, 0.0, after=True, r=r)


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

    def test_placements_move_each_segment_path_onto_the_bar(self):
        chain = self.rectangle()

        bar = unfold(chain, STEEL, **PLAIN)

        ba = allowance(90)
        starts = [0.0, 340.0 + ba, 580.0 + 2 * ba, 920.0 + 3 * ba]
        self.assertEqual(4, len(bar.placements))
        for segment, placement, start in zip(chain.segments, bar.placements, starts):
            self.assertVector((start, 0, 0), placement.multVec(segment.start))
            self.assertVector((start + segment.length, 0, 0), placement.multVec(segment.end))
        for index, (corner, unfolded) in enumerate(zip(chain.corners, bar.corners)):
            # The outer wall of the corner faces -v in its frame on the segments before and after the bend.
            outward = unfolded.frame.Rotation.multVec(App.Vector(0, -1, 0))
            self.assertVector(outward, bar.placements[index].Rotation.multVec(corner.outer_normal))
            after = App.Rotation(corner.axis, corner.bend_angle).multVec(corner.outer_normal)
            self.assertVector(outward, bar.placements[index + 1].Rotation.multVec(after))

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
        relieved = unfold(self.rectangle(), STEEL, key=False)

        self.solid(relieved)
        for corner in relieved.corners:
            ba = corner.bend_allowance
            for w in (SIDE_WALL, -SIDE_WALL):
                # Outside the V (its flanks are at u = 2.7 and 3.27 at v = 2.3) and between the relief discs.
                for u in (2.0, ba - 2.0):
                    self.assertFalse(self.filled(relieved, corner, u, 2.3, w), (u, w))
                    self.assertTrue(self.filled(relieved, corner, u, T / 2, w), (u, w))
                # Before and after the bend zone the side walls stay.
                for u in (-2.0, ba + 2.0):
                    self.assertTrue(self.filled(relieved, corner, u, 2.3, w), (u, w))

    def test_relief_follows_the_inside_radius_of_each_corner(self):
        # S8, S20 (L36): the relief radius is the inside radius of each corner, the one given to a single corner
        # included, so the disc it keeps is concentric with the bend axis: it keeps the side walls up to r from the
        # bend axis point of each segment and removes them from there to the bent wall.
        bar = unfold(self.rectangle(), STEEL, corner_radii={1: 6.0})

        self.solid(bar)
        a = math.radians(30)
        for corner, r in zip(bar.corners, (R, 6.0, R)):
            self.assertAlmostEqual(r, corner.inside_radius, places=9)
            # From the bend axis point of each segment toward the bent wall, 30 degrees off it, clear of the V.
            sides = (
                ((0.0, r + T), (math.sin(a), -math.cos(a))),
                ((corner.bend_allowance, r + T), (-math.sin(a), -math.cos(a))),
            )
            for (u0, v0), (du, dv) in sides:
                # r + 0.2 still stays above the bent wall (v > t): r / cos(30 degrees) reaches it.
                for distance, kept in ((r - 0.5, True), (r - 0.1, True), (r + 0.2, False)):
                    u, v = u0 + du * distance, v0 + dv * distance
                    for w in (SIDE_WALL, -SIDE_WALL):
                        self.assertEqual(kept, self.filled(bar, corner, u, v, w), (r, u, v, w, distance))

    def test_relief_has_no_setting(self):
        # S8 (L36): the relief is always on and its radius is the inside radius of each corner.
        chain = self.rectangle()
        for options in (dict(relief=False), dict(relief=True), dict(relief_radius=2.0)):
            with self.subTest(options=options):
                with self.assertRaises(TypeError):
                    unfold(chain, STEEL, **options)

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

    def test_clearance_moves_the_relief_arcs_back_by_all_of_it(self):
        # S8 (L26): the arcs of the relief (centered on the bend axis points with the default radius) move back the
        # whole clearance: folded, they face the bent wall, whose face does not move.
        chain = self.rectangle()
        tight = unfold(chain, STEEL, key=False)
        loose = unfold(chain, STEEL, clearance=1.0, key=False)

        self.solid(loose)
        a = math.radians(45) / 4
        for tight_corner, loose_corner in zip(tight.corners, loose.corners):
            # From the bend axis point of each segment, between the bent wall and its flank.
            sides = (
                ((0.0, R + T), (math.sin(a), -math.cos(a))),
                ((loose_corner.bend_allowance, R + T), (-math.sin(a), -math.cos(a))),
            )
            for (u0, v0), (du, dv) in sides:
                for distance, kept in ((R - 1.5, True), (R - 0.5, False), (R - 0.1, False)):
                    u, v = u0 + du * distance, v0 + dv * distance
                    for w in (SIDE_WALL, -SIDE_WALL):
                        self.assertTrue(self.filled(tight, tight_corner, u, v, w), (u, v, w))
                        self.assertEqual(kept, self.filled(loose, loose_corner, u, v, w), (u, v, w, distance))

    def test_key_is_a_half_circle_centered_on_the_miter_line(self):
        # S20 (L26): the tab (radius d/2 - g/2) stands out of the flank of the segment before, on the flank moved back
        # half the clearance; the socket (radius d/2 + g/2) is cut into the flank of the segment after; both centered
        # on the miter line at its middle (from the relief arc gap to the inner corner, L33), without a neck.
        g, d = 1.0, DEPTH / 4
        bar = unfold(self.rectangle(), STEEL, clearance=g)

        self.solid(bar)
        tab, socket = d / 2 - g / 2, d / 2 + g / 2
        for corner in bar.corners:
            for w in (SIDE_WALL, -SIDE_WALL):

                def filled(x, y, after=False):
                    return self.filled(bar, corner, *key_point(corner, x, y, after, g=g), w)

                for angle in (0, 45, 80, -45, -80):
                    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                    for radius, kept in ((tab - 0.2, True), (tab + 0.2, False)):
                        self.assertEqual(kept, filled(radius * cos, radius * sin), (angle, radius, w))
                    for radius, kept in ((socket - 0.2, False), (socket + 0.2, True)):
                        self.assertEqual(kept, filled(radius * cos, radius * sin, after=True), (angle, radius, w))
                # The tab sits on its flank, moved back half the clearance, with no gap in between.
                self.assertTrue(filled(-g / 4, 0))
                # Past the key, along the flanks, the clearance stays open.
                for y in (tab + 0.5, -(tab + 0.5)):
                    self.assertFalse(filled(-g / 4, y), y)
                    self.assertTrue(filled(-3 * g / 4, y), y)
                for y in (socket + 0.5, -(socket + 0.5)):
                    self.assertFalse(filled(g / 4, y, after=True), y)
                    self.assertTrue(filled(3 * g / 4, y, after=True), y)
                # No neck: nothing stands out a diameter past the flank, and the socket is not cut that deep.
                self.assertFalse(filled(d, 0))
                self.assertTrue(filled(d, 0, after=True))

    def test_radius_outside_its_limits_is_refused(self):
        chain = self.rectangle()
        # S15 (L40): min = t; max = (depth - t) / (1 - cos(theta / 2)) - 2t, the largest radius whose inside of the bend
        # still passes outside the inner corner, less two walls; 48 / 0.29289 - 4 = 159.88 at 90 degrees, rounded
        # down to 0.1 mm. With or without the key: the key takes no room from the radius.
        message = "The inside bend radius must be between 2 and 159.8 mm."
        self.assertRefused(message, chain, radius=1.9)
        self.assertRefused(message, chain, radius=159.9)
        self.assertRefused(message, chain, radius=159.9, key=False)
        self.assertRefused(message, chain, corner_radii={1: 159.9})
        refused = BendConfiguration("Steel big radius", "Steel", 2.0, 160.0, 0.4)
        self.assertRefused(message, chain, configuration=refused)

    def test_radius_at_its_limits_is_accepted(self):
        # Legs long enough for the outer arc of the largest radius (r + t = 161.8 mm from both outer walls).
        chain = build_chain(self.frame(edges=(((0, 0, 0), (600, 0, 0)), ((600, 0, 0), (600, 600, 0)))))
        for radius, options in ((2.0, {}), (159.8, dict(key=False))):
            with self.subTest(radius=radius, options=options):
                bar = unfold(chain, STEEL, radius=radius, **options)
                self.solid(bar)
                self.assertLength(developed([600, 600], [90], [radius]), bar)
                self.assertEqual([radius], [corner.inside_radius for corner in bar.corners])
        # With the key at that radius the miter line is 1.7 mm long, below the inner wall: no key fits on it.
        self.assertRefused(
            "The key does not fit in the notch between Profile and Profile001 with this inside radius: make the "
            "radius smaller or turn the key off.",
            chain,
            radius=159.8,
        )

    def test_largest_radius_follows_the_angle_of_each_corner(self):
        # S15 (L40): 48 / (1 - cos 30) - 4 = 354.28 at 60 degrees, 48 / (1 - cos 67.5) - 4 = 73.76 at 135 degrees; each
        # corner is checked with its own angle and radius, and the message gives its own range.
        a, b = (0, 0, 0), (200, 0, 0)
        c = tuple(p + q for p, q in zip(b, polar(150, 60)))
        d = tuple(p + q for p, q in zip(c, polar(120, 195)))
        chain = build_chain(self.frame(edges=((a, b), (b, c), (c, d))))
        self.assertEqual([60.0, 135.0], [round(corner.bend_angle, 6) for corner in chain.corners])

        self.assertRefused("The inside bend radius must be between 2 and 73.7 mm.", chain, radius=73.8, key=False)
        self.assertRefused(
            "The inside bend radius must be between 2 and 354.2 mm.", chain, corner_radii={0: 354.3}, key=False
        )

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


class KeyRoomUnfoldTest(UnfoldFixture):
    def narrow_chain(self):
        """Two tubes with a 30 degree corner: a narrow V."""
        bend = tuple(p + q for p, q in zip((200, 0, 0), polar(150, 30)))
        return build_chain(self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), bend))))

    def assertKeyAt(self, bar, d=DEPTH / 4, g=0.0, r=R, along=None, depth=DEPTH, t=T, side_wall=SIDE_WALL):
        """The tab (radius d/2 - g/2) and the socket (radius d/2 + g/2) of every corner are half circles centered on
        the miter line at ``along`` (its middle when None, ``key_along``)."""
        tab, socket = d / 2 - g / 2, d / 2 + g / 2
        for corner in bar.corners:
            for w in (side_wall, -side_wall):

                def filled(x, y, after=False):
                    point = key_point(corner, x, y, after, r, along, g, depth, t)
                    return self.filled(bar, corner, *point, w)

                for angle in (0, 45, 80, -45, -80):
                    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                    for radius, kept in ((tab - 0.05, True), (tab + 0.05, False)):
                        self.assertEqual(kept, filled(radius * cos, radius * sin), (angle, radius, w))
                    for radius, kept in ((socket - 0.05, False), (socket + 0.05, True)):
                        self.assertEqual(kept, filled(radius * cos, radius * sin, after=True), (angle, radius, w))

    def test_key_sits_at_the_middle_of_the_miter_line_below_the_bend_axis(self):
        # L32, L33: an 80x40x1.5 tube bent across its 40 mm side with r = 25. The miter line seen on the folded bar runs
        # from the gap around the disc the relief keeps (radius 25 - 0.5 around the bend axis) to the inner corner:
        # 43.84 mm, as measured on the folded bar; its middle falls 2.6 mm below the bend axis point, in that disc,
        # where the 8 mm key fits.
        tubes = self.frame(family="Rectangular Hollow", width=40.0, height=80.0, thickness=1.5)
        chain = build_chain(tubes)
        self.assertEqual([40.0] * 3, [round(corner.depth, 6) for corner in chain.corners])
        configuration = BendConfiguration("Steel 80x40x1.5", "Steel", 1.5, 25.0, 0.4)
        line = dict(r=25.0, g=0.5, depth=40.0, t=1.5)

        bar = unfold(chain, configuration, clearance=0.5, key_diameter=8.0)

        self.solid(bar)
        start, end = miter_line(bar.corners[0], **line)
        self.assertAlmostEqual(43.84, end - start, places=2)
        self.assertAlmostEqual(-2.58, (start + end) / 2, places=2)
        self.assertKeyAt(bar, d=8.0, side_wall=40.0 - 1.5 / 2, **line)

    def test_radius_above_the_old_key_room_unfolds_with_the_key(self):
        # S15 (L39, L40): the key no longer takes its diameter from the largest radius (was depth - 2t - d = 33.5 mm).
        chain = self.rectangle()
        bar = unfold(chain, STEEL, radius=40.0)

        self.solid(bar)
        self.assertLength(developed([300, 200, 300, 200], [90] * 3, [40.0] * 3), bar)
        self.assertKeyAt(bar, r=40.0)

    def test_users_radius_30_on_the_80x40_tube_unfolds_with_the_key(self):
        # L39: an 80x40x1.5 tube bent across its 40 mm side with r = 30, the default key (10 mm) and 1 mm of clearance
        # was refused with "between 1.5 and 27 mm"; at 90 degrees the largest radius is now
        # 38.5 / (1 - cos 45) - 3 = 128.45 mm (L40), rounded down to 0.1 mm.
        tubes = self.frame(family="Rectangular Hollow", width=40.0, height=80.0, thickness=1.5)
        chain = build_chain(tubes)
        configuration = BendConfiguration("Steel 80x40x1.5", "Steel", 1.5, 30.0, 0.4)

        bar = unfold(chain, configuration, clearance=1.0)

        self.solid(bar)
        self.assertEqual([30.0] * 3, [corner.inside_radius for corner in bar.corners])
        self.assertKeyAt(bar, d=10.0, g=1.0, r=30.0, depth=40.0, t=1.5, side_wall=40.0 - 1.5 / 2)
        self.assertRefused(
            "The inside bend radius must be between 1.5 and 128.4 mm.", chain, configuration=configuration, radius=128.5
        )

    def test_users_40x40_tube_folds_with_an_outer_radius_of_130(self):
        # L40: two 40x40x1.5 tubes at 90 degrees bent with an outer radius of about 130 mm (r = 128.4, the largest):
        # the bend axis is past the inner wall, the inside of the bend passes 1.3 mm outside the inner corner. The
        # bar unfolds into one solid of the developed length; with the key on, the miter line (1.3 mm) has no room.
        r, t, depth = 128.4, 1.5, 40.0
        tubes = self.frame(
            edges=(((0, 0, 0), (600, 0, 0)), ((600, 0, 0), (600, 600, 0))), width=depth, height=depth, thickness=t
        )
        chain = build_chain(tubes)
        configuration = BendConfiguration("Steel 40x40x1.5", "Steel", t, r, 0.4)

        bar = unfold(chain, configuration, key=False)

        self.solid(bar)
        h = math.radians(45)
        self.assertLength(1200 + 2 * (depth / 2 - r - t) * math.tan(h) + math.radians(90) * (r + 0.4 * t), bar)
        self.assertRefused(
            "The key does not fit in the notch between Profile and Profile001 with this inside radius: make the "
            "radius smaller or turn the key off.",
            chain,
            configuration=configuration,
        )

    def test_key_slides_inward_out_of_a_narrow_v(self):
        # At 30 degrees the V is narrow near the bent wall: centered at the middle of the miter line (21.8 mm in), a
        # 30 mm tab would cross the other flank. It slides inward until it touches it: (d/2) / sin(theta) mm from where
        # the flanks meet, BA / (2 sin(theta / 2)) mm outward from the bend axis point.
        chain = self.narrow_chain()
        bar = unfold(chain, STEEL, key_diameter=30.0)

        self.solid(bar)
        corner = bar.corners[0]
        h = math.radians(corner.bend_angle) / 2
        self.assertAlmostEqual(21.8, key_along(corner), places=1)
        self.assertKeyAt(bar, d=30.0, along=15.0 / math.sin(2 * h) - corner.bend_allowance / (2 * math.sin(h)))

    def test_key_slides_outward_off_the_inner_wall(self):
        # With r = 2, centered at the middle of the miter line (v = 26.3), the tab of a 44 mm key would reach into
        # the inner wall (v = 48): it slides outward until its tab touches it, at v = 48 - 22.
        bar = unfold(self.rectangle(), STEEL, radius=2.0, key_diameter=44.0)

        self.solid(bar)
        corner = bar.corners[0]
        self.assertAlmostEqual(26.3, 2.0 + T + key_along(corner, r=2.0) * math.cos(math.radians(45)), places=1)
        self.assertKeyAt(bar, d=44.0, r=2.0, along=(26.0 - 2.0 - T) / math.cos(math.radians(45)))

    def test_key_that_fits_nowhere_on_the_miter_line_is_refused(self):
        # At 30 degrees a 43 mm key is too wide for the V wherever its tab stays below the inner wall; a smaller one
        # fits.
        self.assertRefused(
            "The key does not fit in the notch between Profile and Profile001: make it smaller.",
            self.narrow_chain(),
            key_diameter=43.0,
        )

    def test_key_the_clearance_leaves_no_room_for_is_refused(self):
        # With 18 mm of clearance even the smallest key (37 mm across, its tab just past its flank) has a 27.5 mm
        # socket: taller than the side wall between the bent wall and the inner wall wherever it sits on the miter line.
        message = (
            "The key does not fit in the notch between Profile and Profile001 with this inside radius: make the "
            "radius smaller or turn the key off."
        )
        self.assertRefused(message, self.rectangle(), clearance=18.0, key_diameter=37.0)


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

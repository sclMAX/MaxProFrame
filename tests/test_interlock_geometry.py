"""Interlocks: fingers at the inner vertex of a folded corner (odd/tasks/joint-tabs.md, T1: S2 S3 S4 S5 S6).

The inner wall band of a folded corner is split along the bend axis (w) into fingers that alternate which segment owns
the overlap of both inner walls: each finger level is the stepped band of odd/tasks/stepped-corners.md (S2, S3) with
the segment before (A) or the one after (B) covering it. The clearance opens every mating face pair by all of it, the
finger sides included; the finger tips can be chamfered or rounded in the inner wall plane; every cut through the inner
wall stays laser-cuttable; the bar folds back into one solid without overlap and keeps its developed length.
"""

import math
from dataclasses import replace

import test_folded_geometry as folded_tests
import test_unfolded_geometry as unfolded_tests
from test_end_miter_geometry import polar
from test_folded_geometry import VOLUME_TOLERANCE, FoldFixture
from test_unfolded_geometry import DEPTH, STEEL, STEPPED, K, R, S, T, bend, step_ends

from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.folded_geometry import fold_bar
from freecad.maxproframe.interlock_geometry import CHAMFER, ROUND, SQUARE, FingerSettings
from freecad.maxproframe.unfolded_geometry import check_settings, unfold

# The 50 x 50 tube of the fixtures is 50 mm along the bend axis.
SPAN = 50.0
# Three fingers in a 4 mm band (as the stepped tests' step), no clearance, square tips.
FINGERS = FingerSettings(depth=S)
# v of the middle of the inner wall, and of its visible face from the bend axis point (y = v - (r + t)).
INNER_WALL = DEPTH - T / 2
TOP = DEPTH - R - T
TOLERANCE = 1e-6


def boundaries(count=3, span=SPAN):
    """The w where the fingers of ``count`` even fingers meet, both ends of the band included."""
    return [-span / 2 + span * index / count for index in range(count + 1)]


class InterlockFixture(FoldFixture):
    def chain_at(self, angle):
        """Two 200 mm tubes meeting at a corner of ``angle`` (the bend angle)."""
        corner = tuple(p + q for p, q in zip((200, 0, 0), polar(200, angle)))
        return build_chain(self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), corner))))

    @staticmethod
    def fingered(corner_clearance=0.0, **changes):
        """``STEEL`` with ``FINGERS`` changed by ``changes`` at its corner."""
        return bend(clearance=corner_clearance, interlock=replace(FINGERS, **changes))

    def unfolded_solid(self, bar):
        return unfolded_tests.UnfoldFixture.solid(self, bar)


class FingerUnfoldTest(InterlockFixture):
    """S3, S4, S6: the fingers on the unfolded bar."""

    def test_levels_alternate_which_segment_owns_the_band(self):
        # S3: A owns the first finger (its band reaches its tip x_A - g/2), B the second (the mirror about the middle of
        # the bend zone), A the third; Flip gives the first one to B.
        g = 0.4
        chain = self.chain_at(90)
        tip = step_ends(90)[0] - g / 2
        found = boundaries()
        middles = [(low + high) / 2 for low, high in zip(found, found[1:])]
        for flip in (False, True):
            bar = unfold(chain, self.fingered(g, clearance=g, flip=flip))
            self.unfolded_solid(bar)
            corner = bar.corners[0]
            ba = corner.bend_allowance
            for index, w in enumerate(middles):
                b_owns = (index % 2 == 1) != flip
                with self.subTest(flip=flip, level=index):
                    if b_owns:
                        probes = ((ba - tip + 0.1, True), (ba - tip - 0.1, False), (tip - 0.1, False))
                    else:
                        probes = ((tip - 0.1, True), (tip + 0.1, False), (ba - tip + 0.1, False))
                    for u, kept in probes:
                        self.assertEqual(kept, self.filled(bar, corner, u, INNER_WALL, w), (u, w))

    def test_clearance_opens_the_finger_sides_by_all_of_it(self):
        # S4: the finger side faces get g/2 each: the finger of one segment ends g/2 before the boundary of its level,
        # the next one's starts g/2 past it. The clearance of the fingers, not the corner's, opens them.
        g = 1.0
        bar = unfold(self.chain_at(90), self.fingered(clearance=g))
        self.unfolded_solid(bar)
        corner = bar.corners[0]
        ba = corner.bend_allowance
        tip = step_ends(90)[0] - g / 2
        # Inside A's finger and inside B's, along u.
        on_a, on_b = tip - 1.0, ba - tip + 1.0
        found = boundaries()
        for index, w_b in enumerate(found[1:-1], 1):
            # Below the boundary A owns the level when it is the first or the third one.
            below, above = (on_a, on_b) if index % 2 == 1 else (on_b, on_a)
            with self.subTest(boundary=w_b):
                for u, w, kept in (
                    (below, w_b - g / 2 - 0.05, True),
                    (below, w_b - g / 2 + 0.05, False),
                    (above, w_b + g / 2 - 0.05, False),
                    (above, w_b + g / 2 + 0.05, True),
                ):
                    self.assertEqual(kept, self.filled(bar, corner, u, INNER_WALL, w), (u, w))

    def test_chamfered_and_round_tips_lead_the_fingers_in(self):
        # S4: Chamfer cuts the triangle of legs TipSize off each tip corner of a finger in the inner wall plane, Round
        # keeps the quarter disc of radius TipSize there; Square keeps the corner.
        k = 2.0
        chain = self.chain_at(90)
        x_a = step_ends(90)[0]
        w_b = boundaries()[1]
        # (a, b) from the tip corner into the finger, (shape, kept) for each tip.
        probes = (
            ((0.3, 0.3), {SQUARE: True, CHAMFER: False, ROUND: False}),
            ((0.8, 0.8), {SQUARE: True, CHAMFER: False, ROUND: True}),
            ((1.5, 1.5), {SQUARE: True, CHAMFER: True, ROUND: True}),
        )
        for tip in (SQUARE, CHAMFER, ROUND):
            bar = unfold(chain, self.fingered(tip=tip, tip_size=k))
            self.unfolded_solid(bar)
            corner = bar.corners[0]
            ba = corner.bend_allowance
            for (a, b), kept in probes:
                with self.subTest(tip=tip, probe=(a, b)):
                    # The top corner of A's first finger, and the bottom corner of B's second one.
                    self.assertEqual(kept[tip], self.filled(bar, corner, x_a - a, INNER_WALL, w_b - b))
                    self.assertEqual(kept[tip], self.filled(bar, corner, ba - x_a + a, INNER_WALL, w_b + b))

    def test_every_cut_through_the_inner_wall_is_laser_cuttable(self):
        # S3: every face the fingers leave in the inner wall is a plane of the wall (normal along v) or swept along v
        # (finger ends, finger sides, chamfers, round tips): a laser without a bevel head cuts it.
        half = SPAN / 2 - T - 0.1
        cases = [(angle, dict(tip=CHAMFER, tip_size=2.0, clearance=0.5)) for angle in (60, 90, 120)]
        cases.append((90, dict(tip=ROUND, tip_size=2.0)))
        for angle, changes in cases:
            with self.subTest(angle=angle, tip=changes["tip"]):
                bar = unfold(self.chain_at(angle), self.fingered(**changes))
                self.unfolded_solid(bar)
                corner = bar.corners[0]
                ba = corner.bend_allowance
                x_a, x_b = step_ends(angle)
                tangent = math.tan(math.radians(angle) / 2)
                reach = (min(x_a, -x_b, -DEPTH * tangent) - 10, ba + max(x_b, -x_a, DEPTH * tangent) + 10)
                faces = unfolded_tests.SteppedCornerUnfoldTest.local_faces(self, bar, corner, reach)
                sides = tips = 0
                for normal, box in faces:
                    if box.YMin < DEPTH - T - TOLERANCE or box.ZMin < -half or box.ZMax > half:
                        continue
                    across = abs(normal.y)
                    self.assertTrue(across < TOLERANCE or across > 1 - TOLERANCE, (normal, box))
                    if abs(normal.z) > 1 - TOLERANCE:
                        sides += 1
                    elif across < TOLERANCE and abs(normal.x) < 1 - TOLERANCE:
                        tips += 1
                self.assertGreaterEqual(sides, 2)
                self.assertGreaterEqual(tips, 1)

    def test_fingers_keep_the_developed_length(self):
        # S5: the fingers only cut the inner wall band: the bar keeps its length; no interlock is the default.
        self.assertIsNone(STEEL.interlock)
        chain = self.chain_at(90)
        plain = unfold(chain, STEEL)
        fingered = unfold(chain, self.fingered(tip=ROUND, tip_size=1.0, clearance=0.5))
        self.unfolded_solid(fingered)
        self.assertAlmostEqual(plain.length, fingered.length, places=9)

    def test_fingers_that_do_not_fit_are_refused(self):
        # S6: fewer than 2 fingers, fingers not wider than the clearance (or inner ones too wide for the band), a tip
        # larger than half the narrowest finger less the clearance, a band depth the stepped joint refuses.
        chain = self.chain_at(90)
        corner = "the corner between Profile and Profile001"
        cases = (
            (f"The interlock of {corner} needs at least 2 fingers.", dict(count=1)),
            (f"The fingers of {corner} do not fit: make them fewer or narrower.", dict(finger_width=SPAN)),
            (f"The fingers of {corner} do not fit: make them fewer or narrower.", dict(count=5, clearance=10.0)),
            (f"The finger tips of {corner} must be between 0 and 8.3 mm.", dict(tip=CHAMFER, tip_size=8.4)),
            (
                f"The finger tips of {corner} must be between 0 and 4.5 mm.",
                dict(finger_width=10.0, clearance=1.0, tip=ROUND, tip_size=4.6),
            ),
            (f"The step depth of {corner} must be between 2 and 24.9 mm.", dict(depth=1.9)),
        )
        for message, changes in cases:
            with self.subTest(changes=changes):
                self.assertRefused(message, chain, self.fingered(**changes))
        for changes in (dict(count=2), dict(tip=CHAMFER, tip_size=8.3), dict(finger_width=10.0, tip_size=4.5)):
            with self.subTest(accepted=changes):
                check_settings(chain, self.fingered(**changes))


class FingerFoldTest(InterlockFixture):
    """S5: the fingered corner folds back."""

    def test_fingers_fold_into_one_solid_without_overlap(self):
        # The folded volume is the unfolded one plus what the outer wall gains revolved (Pappus): no finger of A
        # overlaps one of B (a fuse would lose it); each finger closes by the bend like the stepped joint it is, with
        # the segment that owns it: the tip of each finger is where its segment goes.
        found = boundaries()
        middles = [(low + high) / 2 for low, high in zip(found, found[1:])]
        for angle in (60, 90, 120):
            for changes in ({}, dict(clearance=1.0, flip=True, tip=CHAMFER, tip_size=2.0)):
                with self.subTest(angle=angle, changes=changes):
                    chain = self.chain_at(angle)
                    g = changes.get("clearance", 0.0)
                    unfolded = unfold(chain, self.fingered(g, **changes))

                    shape = self.solid(fold_bar(chain, unfolded))

                    added = math.radians(unfolded.corners[0].bend_angle) * (T / 2 - K * T) * DEPTH * T
                    self.assertAlmostEqual(unfolded.shape.Volume + added, shape.Volume, delta=VOLUME_TOLERANCE)
                    self.assertRoundCorner(shape, chain.corners[0])
                    tip = step_ends(angle)[0] - g / 2
                    for index, w in enumerate(middles):
                        b_owns = (index % 2 == 1) != changes.get("flip", False)
                        x = -tip + 0.3 if b_owns else tip - 0.3
                        point = folded_tests.SteppedFoldTest.folded_point(unfolded, x, TOP - T / 2, w, b_owns)
                        self.assertTrue(self.inside(shape, point), (index, b_owns))

    def test_fingers_fit_a_bend_wider_than_the_tube(self):
        # A 45 degree bend of outer radius 80 on the 50 mm tube (PruebaLaserCut.FCStd): the bend axis lies past the
        # inner wall, but the relief its kept discs leave is low, far below the band; automatic depth, 0.5 clearance.
        chain = self.chain_at(45)
        corners = replace(self.fingered(0.5, clearance=0.5, depth=0.0), outer_radius=80.0)
        unfolded = unfold(chain, corners)
        self.unfolded_solid(unfolded)

        shape = self.solid(fold_bar(chain, unfolded))

        added = math.radians(unfolded.corners[0].bend_angle) * (T / 2 - K * T) * DEPTH * T
        self.assertAlmostEqual(unfolded.shape.Volume + added, shape.Volume, delta=VOLUME_TOLERANCE)


class NoInterlockTest(InterlockFixture):
    """S1: without an interlock a Miter or Stepped corner unfolds and folds as before (the shared band code)."""

    # (angle, settings) -> (unfolded volume, folded volume), measured before the interlocks existed.
    PINNED = {
        (90, "miter"): (153389.176938, 153420.592865),
        (90, "stepped"): (153573.176938, 153604.592865),
        (60, "stepped flipped"): (153206.885235, 153227.829186),
    }

    def test_corners_without_interlock_unfold_and_fold_as_before(self):
        settings = {
            "miter": STEEL,
            "stepped": bend(**STEPPED),
            "stepped flipped": bend(clearance=1.0, step_flip=True, **STEPPED),
        }
        for (angle, name), (unfolded_volume, folded_volume) in self.PINNED.items():
            with self.subTest(angle=angle, settings=name):
                chain = self.chain_at(angle)
                unfolded = unfold(chain, settings[name])
                self.unfolded_solid(unfolded)
                folded = self.solid(fold_bar(chain, unfolded))
                self.assertAlmostEqual(unfolded_volume, unfolded.shape.Volume, delta=VOLUME_TOLERANCE)
                self.assertAlmostEqual(folded_volume, folded.Volume, delta=VOLUME_TOLERANCE)

"""Tabs: the tabs of a T joint Interlock and the slots they pass through (odd/tasks/t-joint-tabs.md, T1: S3 S4 S5).

A crossbar (the arriving tube, trimmed against a face of the rail) ends in tabs on the flat part of one of its walls:
the wall prolonged along the crossbar axis through the rail wall, flush with its inside face by default (D3) or as
long as asked. The rail gets one slot per tab: the footprint of the tab inside the rail wall, seen along the rail face
normal and grown by the clearance; at an oblique joint the slot is longer (S5). Every cut is square to the wall it goes
through (D2); tabs and slots must lie on the flat parts of both walls (D4), otherwise the Interlock is refused naming
the two tubes.
"""

import math
import unittest
from dataclasses import replace

import FreeCAD as App
import Part
from miter_helpers import use_language

from freecad.maxproframe.interlock_geometry import (
    CHAMFER,
    FINGERS,
    KINDS,
    ROUND,
    SQUARE,
    TABS,
    FingerSettings,
    InterlockError,
    TabSettings,
)
from freecad.maxproframe.tab_geometry import TJoint, check, make_tabs

# TC80x40x1.5-like tubes: 80 wide, 40 high, 1.5 thick, outer corner radius 3.
WIDE, HIGH, T, RADIUS = 80.0, 40.0, 1.5, 3.0
# The flat part of the 40 mm wall, between its corner radii.
FLAT = HIGH - 2 * RADIUS
# The rail runs along Y; the face the crossbar butts against is the plane x = RAIL_X.
RAIL_X = 100.0
NAMES = ("Crossbar", "Rail")
TOLERANCE = 1e-6
VOLUME_TOLERANCE = 1e-4
X, Y, Z = App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)


def tube(start, end, wide=WIDE, high=HIGH):
    """A rectangular tube along X from ``start`` to ``end``: ``wide`` along Y, ``high`` along Z, centered on the
    X axis, walls T thick with outer corners of RADIUS."""

    def rounded(length, width, height, radius, x):
        box = Part.makeBox(length, width, height, App.Vector(x, -width / 2, -height / 2))
        along = [edge for edge in box.Edges if abs(edge.Vertexes[0].Point.x - edge.Vertexes[1].Point.x) > TOLERANCE]
        return box.makeFillet(radius, along)

    outer = rounded(end - start, wide, high, RADIUS, start)
    inner = rounded(end - start + 2, wide - 2 * T, high - 2 * T, RADIUS - T, start - 1)
    return outer.cut(inner)


def even(count, span=FLAT):
    """The (low, high) of each of ``count`` even tabs: 2 * count + 1 equal parts, tabs centered."""
    part = span / (2 * count + 1)
    return [(-span / 2 + (2 * index + 1) * part, -span / 2 + (2 * index + 2) * part) for index in range(count)]


def planar_face(shape, normal, farthest=True):
    """The planar face of ``shape`` whose outward normal is ``normal``, farthest along it (or nearest)."""
    found = [
        face
        for face in shape.Faces
        if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(normal) < 1e-6
    ]
    pick = max if farthest else min
    return pick(found, key=lambda face: face.CenterOfMass.dot(normal))


class TabFixture(unittest.TestCase):
    def setUp(self):
        # Refusals are checked in English: an earlier test may leave FreeCAD in another language.
        use_language(self, "English", "en_US")

    @staticmethod
    def rail():
        """The rail along Y, 80 along X from RAIL_X, 40 along Z."""
        shape = tube(-300, 300)
        shape.rotate(App.Vector(), Z, 90)
        shape.translate(App.Vector(RAIL_X + WIDE / 2, 0, 0))
        return shape

    @staticmethod
    def direction(angle):
        """The crossbar axis toward the rail, at ``angle`` degrees to the rail axis (Y), in the XY plane."""
        return App.Vector(math.sin(math.radians(angle)), math.cos(math.radians(angle)), 0)

    def crossbar(self, angle=90, gap=0.0, lift=0.0):
        """(crossbar, its 40 mm wall carrying the tabs): its axis at ``angle`` to the rail's, through
        (RAIL_X, 0, ``lift``), trimmed on the plane ``gap`` before the rail face."""
        shape = tube(-400, 400)
        shape.rotate(App.Vector(), Z, 90 - angle)
        shape.translate(App.Vector(RAIL_X, 0, lift))
        kept = Part.makeBox(1000, 2000, 1000, App.Vector(RAIL_X - gap - 1000, -1000, -500))
        shape = shape.common(kept)
        # The wall on +Y of the tube before turning it: 40 high, its normal in the XY plane.
        normal = App.Vector(-math.sin(math.radians(90 - angle)), math.cos(math.radians(90 - angle)), 0)
        return shape, planar_face(shape, normal)

    def joint(self, angle=90, gap=0.0, lift=0.0, rail=None, rail_face=None, end=None):
        """(TJoint, crossbar, rail) of the crossbar at ``angle`` against the rail face x = RAIL_X."""
        rail = self.rail() if rail is None else rail
        crossbar, wall = self.crossbar(angle, gap, lift)
        rail_face = planar_face(rail, -X, farthest=True) if rail_face is None else rail_face
        if end is None and gap:
            end = (App.Vector(RAIL_X - gap, 0, 0), X)
        joint = TJoint(NAMES, wall, T, self.direction(angle), rail_face, T, end)
        return joint, crossbar, rail

    def assertBox(self, shape, x=None, y=None, z=None, places=6):
        box = shape.BoundBox
        for expected, found in ((x, (box.XMin, box.XMax)), (y, (box.YMin, box.YMax)), (z, (box.ZMin, box.ZMax))):
            if expected is not None:
                self.assertAlmostEqual(expected[0], found[0], places=places)
                self.assertAlmostEqual(expected[1], found[1], places=places)

    def assertRefused(self, message, settings, joint):
        for call in (check, make_tabs):
            with self.subTest(call=call.__name__):
                with self.assertRaises(InterlockError) as raised:
                    call(settings, joint)
                self.assertEqual(message, str(raised.exception))


class TabSettingsTest(unittest.TestCase):
    """S3, S4: the Tabs settings reuse the Fingers fields and add the length."""

    def test_tabs_are_a_kind_next_to_fingers(self):
        self.assertEqual({FINGERS: FingerSettings, TABS: TabSettings}, KINDS)
        self.assertEqual("Tabs", TabSettings.kind)
        self.assertEqual("Fingers", FingerSettings.kind)
        settings = TabSettings()
        fields = ("count", "tab_width", "tip", "tip_size", "length", "clearance")
        self.assertEqual((2, 0.0, SQUARE, 0.0, 0.0, 0.0), tuple(getattr(settings, name) for name in fields))

    def test_even_tabs_and_tabs_of_a_given_width_are_centered(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                found = TabSettings(count=count).bounds(FLAT)
                for (low, high), (found_low, found_high) in zip(even(count), found, strict=True):
                    self.assertAlmostEqual(low, found_low, places=9)
                    self.assertAlmostEqual(high, found_high, places=9)
        # Tabs of a width, the gaps between them and at both ends equal.
        self.assertEqual([(-5.0, 5.0)], TabSettings(count=1, tab_width=10.0).bounds(FLAT))
        found = TabSettings(count=3, tab_width=8.0).bounds(FLAT)
        for (low, high), (found_low, found_high) in zip(((-14.5, -6.5), (-4, 4), (6.5, 14.5)), found, strict=True):
            self.assertAlmostEqual(low, found_low, places=9)
            self.assertAlmostEqual(high, found_high, places=9)

    def test_length_zero_is_the_rail_wall_thickness(self):
        self.assertEqual(T, TabSettings().tab_length(T))
        self.assertEqual(4.5, TabSettings(length=4.5).tab_length(T))

    def test_an_unknown_tip_is_a_programming_error(self):
        with self.assertRaises(ValueError) as raised:
            TabSettings(tip="Pointed").check(NAMES, FLAT)
        self.assertNotIsInstance(raised.exception, InterlockError)


class SquareTabTest(TabFixture):
    """S3, S4: a square T joint, tabs on the 40 mm wall of the crossbar."""

    def tab_and_slot_boxes(self, settings, bounds, depth=T):
        joint, _, rail = self.joint()
        shapes = make_tabs(settings, joint)
        g = settings.clearance
        self.assertEqual(len(bounds), len(shapes.tabs))
        self.assertEqual(len(bounds), len(shapes.slots))
        tabs = sorted(shapes.tabs, key=lambda shape: shape.BoundBox.ZMin)
        slots = sorted(shapes.slots, key=lambda shape: shape.BoundBox.ZMin)
        for (low, high), tab, slot in zip(bounds, tabs, slots, strict=True):
            with self.subTest(tab=(low, high)):
                self.assertTrue(tab.isValid())
                # The wall prolonged from the crossbar end (the rail face) to ``depth`` across the rail wall.
                self.assertBox(tab, x=(RAIL_X, RAIL_X + depth), y=(WIDE / 2 - T, WIDE / 2), z=(low, high))
                self.assertAlmostEqual((high - low) * T * depth, tab.Volume, delta=VOLUME_TOLERANCE)
                # The slot is the tab grown by the clearance, through the whole rail wall.
                removed = slot.common(rail)
                self.assertBox(removed, x=(RAIL_X, RAIL_X + T), y=(WIDE / 2 - T - g / 2, WIDE / 2 + g / 2))
                self.assertBox(removed, z=(low - g / 2, high + g / 2))
                self.assertAlmostEqual((high - low + g) * (T + g) * T, removed.Volume, delta=VOLUME_TOLERANCE)
        return shapes, rail

    def test_even_tabs_go_through_the_rail_wall_flush_with_its_inside_face(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                self.tab_and_slot_boxes(TabSettings(count=count), even(count))

    def test_tabs_of_a_given_width_are_evenly_spaced(self):
        self.tab_and_slot_boxes(TabSettings(count=3, tab_width=8.0), [(-14.5, -6.5), (-4, 4), (6.5, 14.5)])
        self.tab_and_slot_boxes(TabSettings(count=1, tab_width=10.0), [(-5.0, 5.0)])

    def test_the_clearance_grows_each_slot_by_all_of_it_half_on_each_side(self):
        g = 0.4
        shapes, rail = self.tab_and_slot_boxes(TabSettings(count=2, clearance=g), even(2))
        slotted = rail.cut(shapes.slots)
        for tab in shapes.tabs:
            self.assertAlmostEqual(0.0, tab.common(slotted).Volume, delta=VOLUME_TOLERANCE)
            self.assertAlmostEqual(g / 2, tab.distToShape(slotted)[0], places=6)

    def test_a_longer_tab_protrudes_past_the_inside_face_by_the_difference(self):
        # S4: 0 is Automatic (the rail wall thickness); a length is measured across the rail wall (D3). The slot only
        # depends on the tab inside the rail wall.
        self.tab_and_slot_boxes(TabSettings(count=2, length=T + 3.0), even(2), depth=T + 3.0)
        self.tab_and_slot_boxes(TabSettings(count=2, length=1.0), even(2), depth=1.0)

    def test_the_tabs_start_on_the_crossbar_end_with_a_trim_gap(self):
        gap = 1.0
        joint, crossbar, _ = self.joint(gap=gap)
        tabs = make_tabs(TabSettings(count=2), joint).tabs
        for tab in tabs:
            self.assertBox(tab, x=(RAIL_X - gap, RAIL_X + T))
        fused = crossbar.fuse(tabs).removeSplitter()
        self.assertEqual(1, len(fused.Solids))

    def test_chamfered_and_round_tips_in_the_crossbar_wall_plane(self):
        # S3: Chamfer cuts the triangle of legs TipSize off both tip corners, Round leaves a quarter disc of that
        # radius; both swept through the crossbar wall.
        k = 1.0
        (low, high), *_ = even(2)
        cut = {SQUARE: 0.0, CHAMFER: k * k / 2, ROUND: k * k * (1 - math.pi / 4)}
        joint, _, _ = self.joint()
        for tip, corner in cut.items():
            with self.subTest(tip=tip):
                tab = min(make_tabs(TabSettings(tip=tip, tip_size=k), joint).tabs, key=lambda s: s.BoundBox.ZMin)
                self.assertTrue(tab.isValid())
                self.assertAlmostEqual((high - low) * T * T - 2 * corner * T, tab.Volume, delta=VOLUME_TOLERANCE)
                # (along x from the tip, along z from the side) into the tab, kept or not.
                for (a, b), kept in (((0.2, 0.2), tip == SQUARE), ((0.4, 0.4), tip != CHAMFER), ((0.9, 0.9), True)):
                    for z in (low + b, high - b):
                        point = App.Vector(RAIL_X + T - a, WIDE / 2 - T / 2, z)
                        self.assertEqual(kept, tab.isInside(point, TOLERANCE, True), (tip, a, b, z))


class ObliqueTabTest(TabFixture):
    """S5: an oblique T joint (the crossbar at 60 degrees to the rail): the slots are longer."""

    ANGLE = 60.0

    def test_the_slots_are_the_footprint_of_the_tabs_inside_the_rail_wall(self):
        theta = math.radians(self.ANGLE)
        # Along the rail: the wall T thick crossing the face at 60 degrees, and its shift across the rail wall.
        footprint = T / math.sin(theta) + T / math.tan(theta)
        self.assertGreater(footprint, T)
        for g in (0.0, 0.4):
            with self.subTest(clearance=g):
                joint, _, rail = self.joint(self.ANGLE)
                shapes = make_tabs(TabSettings(count=2, clearance=g), joint)
                slotted = rail.cut(shapes.slots)
                for (low, high), tab, slot in zip(
                    even(2),
                    sorted(shapes.tabs, key=lambda s: s.BoundBox.ZMin),
                    sorted(shapes.slots, key=lambda s: s.BoundBox.ZMin),
                    strict=True,
                ):
                    w = high - low
                    removed = slot.common(rail)
                    self.assertAlmostEqual(footprint + g, removed.BoundBox.YLength, places=6)
                    self.assertBox(removed, x=(RAIL_X, RAIL_X + T), z=(low - g / 2, high + g / 2))
                    self.assertAlmostEqual((footprint + g) * (w + g) * T, removed.Volume, delta=VOLUME_TOLERANCE)
                    # The tab goes through the whole rail wall, its tip square to the crossbar wall: its corner on the
                    # shallower face ends flush with the inside face, the other one passes it.
                    self.assertAlmostEqual(w * T * T / math.sin(theta), tab.common(rail).Volume, delta=VOLUME_TOLERANCE)
                    self.assertAlmostEqual(RAIL_X + T + T * math.cos(theta), tab.BoundBox.XMax, places=6)
                    self.assertBox(tab, z=(low, high))
                    self.assertAlmostEqual(0.0, tab.common(slotted).Volume, delta=VOLUME_TOLERANCE)

    def test_every_cut_is_square_to_the_wall_it_goes_through(self):
        # D2: the tab faces are the crossbar wall faces or swept along its normal (sides, tip, chamfers, rounds); the
        # slot faces are the rail wall planes or swept along its normal.
        joint, _, _ = self.joint(self.ANGLE)
        wall = joint.crossbar_face.normalAt(0, 0)
        for tip in (CHAMFER, ROUND):
            with self.subTest(tip=tip):
                shapes = make_tabs(TabSettings(count=3, tip=tip, tip_size=1.0, clearance=0.3), joint)
                for shapes_of, normal in ((shapes.tabs, wall), (shapes.slots, -X)):
                    for shape in shapes_of:
                        for face in shape.Faces:
                            surface = face.Surface
                            if isinstance(surface, Part.Plane):
                                along = abs(face.normalAt(0, 0).dot(normal))
                                self.assertTrue(along < TOLERANCE or along > 1 - TOLERANCE, (tip, along))
                            else:
                                self.assertIsInstance(surface, Part.Cylinder)
                                self.assertAlmostEqual(1.0, abs(surface.Axis.dot(normal)), places=6)

    def test_the_tip_size_range_follows_the_oblique_tab(self):
        # The tab passes its crossbar end by T / sin(60) = 1.73 mm along the axis: the tip corners fit 1.7 mm.
        joint, _, _ = self.joint(self.ANGLE)
        for tip in (CHAMFER, ROUND):
            with self.subTest(tip=tip):
                check(TabSettings(tip=tip, tip_size=1.7), joint)
                self.assertRefused(
                    "The tab tips of the T joint between Crossbar and Rail must be between 0 and 1.7 mm.",
                    TabSettings(tip=tip, tip_size=1.8),
                    joint,
                )


class TabSolidsTest(TabFixture):
    """The tabs fuse with the crossbar end into one solid; the slots cut the rail into one solid."""

    def test_tabs_fuse_with_the_crossbar_and_slots_keep_the_rail_whole(self):
        for angle in (90, 60, 120):
            for tip in (SQUARE, CHAMFER, ROUND):
                with self.subTest(angle=angle, tip=tip):
                    joint, crossbar, rail = self.joint(angle)
                    settings = TabSettings(count=3, tip=tip, tip_size=0.8, clearance=0.3)
                    shapes = make_tabs(settings, joint)
                    fused = crossbar.fuse(shapes.tabs).removeSplitter()
                    self.assertEqual(1, len(fused.Solids))
                    self.assertTrue(fused.isValid())
                    self.assertGreater(fused.Volume, crossbar.Volume + VOLUME_TOLERANCE)
                    slotted = rail.cut(shapes.slots)
                    self.assertEqual(1, len(slotted.Solids))
                    self.assertTrue(slotted.isValid())
                    self.assertLess(slotted.Volume, rail.Volume - VOLUME_TOLERANCE)
                    self.assertAlmostEqual(0.0, fused.common(slotted).Volume, delta=VOLUME_TOLERANCE)
                    if angle == 90:
                        tabs = sum(tab.Volume for tab in shapes.tabs)
                        self.assertAlmostEqual(crossbar.Volume + tabs, fused.Volume, delta=VOLUME_TOLERANCE)


class TabRefusalTest(TabFixture):
    """D4 and the checks: an Interlock that does not fit is refused, naming both tubes."""

    def test_settings_that_do_not_fit_are_refused(self):
        joint, _, _ = self.joint()
        between = "the T joint between Crossbar and Rail"
        cases = (
            (f"The interlock of {between} needs at least 1 tab.", dict(count=0)),
            (f"The tabs of {between} do not fit: make them fewer or narrower.", dict(count=2, tab_width=17.0)),
            # Gaps of 1 mm between 10 mm tabs: a 1 mm clearance joins the slots.
            (f"The tabs of {between} do not fit: make them fewer or narrower.", dict(tab_width=10.0, clearance=1.0)),
            (f"The tab tips of {between} must be between 0 and 1.5 mm.", dict(tip=CHAMFER, tip_size=1.6)),
            (f"The tab tips of {between} must be between 0 and 1.5 mm.", dict(tip=ROUND, tip_size=1.6)),
            (f"The tab tips of {between} must be between 0 and 1 mm.", dict(tab_width=2.0, tip=ROUND, tip_size=1.1)),
            (f"The tab tips of {between} must be between 0 and 1.5 mm.", dict(tip=CHAMFER, tip_size=-0.1)),
            (f"The tab length of {between} must be 0 (automatic) or more.", dict(length=-1.0)),
        )
        base = TabSettings(count=3)
        for message, changes in cases:
            with self.subTest(changes=changes):
                self.assertRefused(message, replace(base, **changes), joint)
        for changes in (
            dict(count=1),
            dict(count=2, tab_width=16.9),
            dict(tab_width=10.0, clearance=0.9),
            dict(tip=CHAMFER, tip_size=1.5),
            dict(tip=ROUND, tip_size=1.5),
            dict(tab_width=2.0, tip=ROUND, tip_size=1.0),
            dict(tip=SQUARE, tip_size=5.0),
            dict(length=10.0),
        ):
            with self.subTest(accepted=changes):
                settings = replace(base, **changes)
                check(settings, joint)
                self.assertEqual(settings.count, len(make_tabs(settings, joint).tabs))

    def test_slots_off_the_flat_part_of_the_rail_face_are_refused(self):
        # D4: the crossbar 10 mm higher: its top tab falls on the corner radius of the rail face.
        message = "The slots of the T joint between Crossbar and Rail do not fall on the flat part of the face of Rail."
        joint, _, _ = self.joint(lift=10.0)
        self.assertRefused(message, TabSettings(count=2), joint)
        # Near the end of the rail.
        short = tube(-300, 39)
        short.rotate(App.Vector(), Z, 90)
        short.translate(App.Vector(RAIL_X + WIDE / 2, 0, 0))
        joint, _, _ = self.joint(rail=short)
        self.assertRefused(message, TabSettings(count=2), joint)
        # The clearance alone takes the slots off the flat part.
        joint, _, _ = self.joint()
        self.assertRefused(message, TabSettings(count=1, tab_width=FLAT - 0.2, clearance=0.4), joint)
        check(TabSettings(count=1, tab_width=FLAT - 0.4, clearance=0.4), joint)
        check(TabSettings(count=2), self.joint(lift=3.0)[0])

    def test_faces_that_are_no_t_joint_are_refused(self):
        rail = self.rail()
        along = "There is no T joint between Crossbar and Rail: Crossbar runs along the face of Rail."
        no_end = "There is no T joint between Crossbar and Rail: Crossbar does not end on the face of Rail."
        settings = TabSettings(count=2)
        # The top face of the rail: the crossbar axis runs along it.
        joint, _, _ = self.joint(rail=rail, rail_face=planar_face(rail, Z))
        self.assertRefused(along, settings, joint)
        # The far face of the rail, facing away from the crossbar.
        joint, _, _ = self.joint(rail=rail, rail_face=planar_face(rail, X))
        self.assertRefused(no_end, settings, joint)
        # A crossbar ending farther from the face than the rail wall is thick, or inside the rail wall.
        self.assertRefused(no_end, settings, self.joint(gap=T + 0.1)[0])
        self.assertRefused(no_end, settings, self.joint(end=(App.Vector(RAIL_X + 1.0, 0, 0), X))[0])
        check(settings, self.joint(gap=T)[0])
        check(settings, self.joint(120)[0])


if __name__ == "__main__":
    unittest.main()

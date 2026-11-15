"""Tabs Interlock on a Folded Bar: the crossbar, the rail or both are tubes of a bar (odd/tasks/t-joint-tabs.md, T3:
S7).

A face clicked on the bar stands for the face of the tube under the clicked point (``folded_bar.segment_at``), as for
the other tools on a bar; a click on a bend is refused with "Click a straight part of the folded bar.". The slots go
through a straight part of a tube of the bar; the tabs go past a free end of a bar (the start of its first tube or the
end of its last one, on an open bar), never at a folded corner nor at the open corner of a closed frame. The bar folds
the new _Tb and _Sl pieces: its shape shows the tabs and the slots, the Unfolded Bar carries them at their places, and
a bar with tabs is as long as its tab tips (S6). Deleting the Interlock gives the bar the pieces under back; undo
brings them back; a saved bar opens with them.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from miter_helpers import use_language
from test_folded_bar_tools import BEND_MESSAGE, FoldedBarToolsFixture, face_at
from test_unfolded_geometry import PLAIN, T, bend

from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.folded_bar import make_folded_bar, make_unfolded_bar
from freecad.maxproframe.interlock_geometry import InterlockError
from freecad.maxproframe.profile_pattern import placed
from freecad.maxproframe.tab_interlock import make_tab_interlock, tab_pieces

X, Y = App.Vector(1, 0, 0), App.Vector(0, 1, 0)
# The bar: the right, top and left tubes of the 50 x 50 x 2 rectangle of the fixtures, open at the bottom.
LEGS = (
    ((300, 0, 0), (300, 200, 0)),
    ((300, 200, 0), (0, 200, 0)),
    ((0, 200, 0), (0, 0, 0)),
)
# A loose rail under the bar: its top face (y = 0) is where both free ends of the bar end.
RAIL_BELOW = ((-100, -25, 0), (400, -25, 0))
# A loose crossbar from below, ending 5 mm short of the bottom face of the top tube (y = 175).
CROSSBAR_UP = ((150, -100, 0), (150, 170, 0))
# On the bar: the outer wall of the right tube (normal +X), the bottom face of the top tube (normal -Y).
RIGHT_OUTER = App.Vector(325, 100, 0)
TOP_UNDER = App.Vector(100, 175, 0)
VOLUME_TOLERANCE = 1e-2
LENGTH_TOLERANCE = 1e-4
# The Gap of an Extend / Cut the crossbar ends on (S8): the 0.5 mm of the manual test (L12), and one wider than the
# tube wall (T) is thick.
GAP, WIDE_GAP = 0.5, 2.5
CORNER = "The T joint between {} and {} is at a folded corner of {}: the tabs go on a free end of a Folded Bar."
OPEN = "The T joint between {} and {} is at the open corner of {}: the tabs go on a free end of a Folded Bar."


def face_towards(obj, direction):
    """Name of the planar face of ``obj`` whose outward normal points along ``direction``, farthest out."""
    candidates = [
        (face.CenterOfMass.dot(direction), f"Face{index}")
        for index, face in enumerate(obj.Shape.Faces, start=1)
        if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(direction) < 1e-6
    ]
    return max(candidates)[1]


class TabsOnBarFixture(FoldedBarToolsFixture):
    def setUp(self):
        super().setUp()
        # Refusals are checked in English: an earlier test may leave FreeCAD in another language.
        use_language(self, "English", "en_US")

    def legs(self):
        """(right, top, left), the open bar folding them: its free ends at (300, 0) and (0, 0)."""
        tubes = self.frame(edges=LEGS)
        bar = make_folded_bar(tubes, bend(**PLAIN))
        self.assertOneSolid(bar)
        return tubes, bar

    def loose(self, edge, label):
        tube = self.frame(edges=(edge,))[0]
        tube.Label = label
        return tube

    def trimmed(self, piece, target, direction):
        """An Extend / Cut of ``piece`` against the face of ``target`` looking along ``direction``."""
        trim = make_extend_cut_profile(piece, (target, (face_towards(target, direction),)))
        self.doc.recompute()
        self.assertEqual("Valid", trim.getStatusString())
        return trim

    def straight(self, bar):
        """(unfolded volume, developed length) of ``bar`` as it is."""
        unfolded = make_unfolded_bar(bar)
        self.assertOneSolid(unfolded)
        return unfolded.Shape.Volume, bar.DevelopedLength.Value

    def unfolded_of(self, bar):
        return next(obj for obj in bar.InList if getattr(obj, "FoldedBar", None) == bar)

    def on_bar(self, bar, index, shape):
        """``shape`` (global, of the tube ``index`` of ``bar``) moved where the Unfolded Bar carries it."""
        return placed(shape, bar.Proxy.unfolded_bar(bar).placements[index])

    def assertFilled(self, expected, shape, region):
        self.assertAlmostEqual(expected, shape.common(region).Volume, delta=VOLUME_TOLERANCE)

    def assertSlotsIn(self, bar, index, slots, rail, tabs):
        """The slots ``slots`` cut in ``rail`` (tube ``index`` of ``bar``) show in the bar and its Unfolded Bar."""
        removed = rail.Shape.cut(slots.Shape)
        self.assertGreater(removed.Volume, VOLUME_TOLERANCE)
        # The tabs fill the slots: where the rail was.
        self.assertAlmostEqual(removed.Volume, tabs.Shape.common(rail.Shape).Volume, delta=VOLUME_TOLERANCE)
        self.assertFilled(0.0, bar.Shape, removed)
        self.assertFilled(0.0, self.unfolded_of(bar).Shape, self.on_bar(bar, index, removed))
        return removed.Volume

    def assertTabsOn(self, bar, index, tabs, under):
        """The tabs of ``tabs`` (on ``under``, tube ``index`` of ``bar``) show in the bar and its Unfolded Bar."""
        added = tabs.Shape.cut(under.Shape)
        self.assertGreater(added.Volume, VOLUME_TOLERANCE)
        self.assertFilled(added.Volume, bar.Shape, added)
        self.assertFilled(added.Volume, self.unfolded_of(bar).Shape, self.on_bar(bar, index, added))
        return added.Volume


class RailOnBarTest(TabsOnBarFixture):
    """(a) The rail is the top tube of the bar: the slots go through its bottom face, clicked on the bar."""

    def test_the_slots_go_through_the_tube_under_the_click_and_the_bar_folds_them(self):
        (right, top, left), bar = self.legs()
        crossbar = self.loose(CROSSBAR_UP, "Crossbar")
        trim = self.trimmed(crossbar, top, -Y)
        volume, (unfolded_volume, length) = bar.Shape.Volume, self.straight(bar)

        interlock = make_tab_interlock(trim, face_towards(trim, X), bar, face_at(bar, TOP_UNDER), rail_point=TOP_UNDER)
        self.doc.recompute()

        tabs, slots = tab_pieces(interlock)
        self.assertEqual((top, top), (slots.baseObject[0], interlock.RailFace[0]))
        self.assertEqual((crossbar, top), (interlock.PieceA, interlock.PieceB))
        self.assertEqual([right, slots, left], list(bar.Segments))
        for obj in (tabs, slots, bar):
            self.assertOneSolid(obj)
        self.assertOneSolid(self.unfolded_of(bar))
        removed = self.assertSlotsIn(bar, 1, slots, top, tabs)
        self.assertAlmostEqual(volume - removed, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(unfolded_volume - removed, self.unfolded_of(bar).Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        self.assertFalse(slots.Visibility)
        self.assertNotIn(interlock, bar.Interlocks)
        # The BOM: the bar is one piece with cutouts, the slotted tube is the bar.
        rows, links = [], []
        traverse_assembly(rows, links, bar)
        traverse_assembly(rows, links, slots)
        (row,) = rows
        self.assertEqual("Yes", row["cutout"])

    def test_a_click_on_a_bend_of_the_rail_bar_is_refused(self):
        _, bar = self.legs()
        crossbar = self.loose(CROSSBAR_UP, "Crossbar")
        names = sorted(obj.Name for obj in self.doc.Objects)
        point = self.bend_point(bar, 45.0)

        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(crossbar, face_towards(crossbar, X), bar, face_at(bar, point), rail_point=point)

        self.assertEqual(BEND_MESSAGE, str(raised.exception))
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))


class CrossbarOnBarTest(TabsOnBarFixture):
    """(b) The crossbar is the first tube of the bar: its free end, cut against a loose rail, ends in tabs."""

    def tabs_at_the_start(self):
        (right, top, left), bar = self.legs()
        rail = self.loose(RAIL_BELOW, "Rail")
        trim = self.trimmed(right, rail, Y)
        self.assertEqual([trim, top, left], list(bar.Segments))
        before = (bar.Shape.Volume, *self.straight(bar))
        interlock = make_tab_interlock(
            bar, face_at(bar, RIGHT_OUTER), rail, face_towards(rail, Y), crossbar_point=RIGHT_OUTER
        )
        self.doc.recompute()
        return (right, top, left), bar, rail, trim, interlock, before

    def test_the_tabs_go_past_the_free_end_and_the_bar_is_as_long_as_their_tips(self):
        (right, top, left), bar, rail, trim, interlock, before = self.tabs_at_the_start()
        volume, unfolded_volume, length = before

        tabs, slots = tab_pieces(interlock)
        self.assertEqual((trim, trim), (tabs.baseObject[0], interlock.CrossbarFace[0]))
        self.assertEqual((right, rail), (interlock.PieceA, interlock.PieceB))
        self.assertEqual([tabs, top, left], list(bar.Segments))
        for obj in (tabs, slots, bar):
            self.assertOneSolid(obj)
        self.assertOneSolid(self.unfolded_of(bar))
        added = self.assertTabsOn(bar, 0, tabs, trim)
        self.assertAlmostEqual(volume + added, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(unfolded_volume + added, self.unfolded_of(bar).Shape.Volume, delta=VOLUME_TOLERANCE)
        # The tabs go through the rail wall: the bar reaches T past its end, and is T longer to cut (S6).
        self.assertAlmostEqual(-T, bar.Shape.BoundBox.YMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + T, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        box = self.unfolded_of(bar).Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + T, box.XLength, delta=LENGTH_TOLERANCE)
        rows, links = [], []
        traverse_assembly(rows, links, bar)
        self.assertEqual(f"{length + T:.1f}", rows[0]["length"])
        # The loose rail gets the slots.
        self.assertTrue(slots.Cutout)
        self.assertAlmostEqual(
            rail.Shape.Volume - slots.Shape.Volume, tabs.Shape.common(rail.Shape).Volume, delta=VOLUME_TOLERANCE
        )
        self.assertFalse(tabs.Visibility)
        self.assertNotIn(interlock, bar.Interlocks)

    def test_the_last_tube_takes_tabs_at_its_free_end_too(self):
        (right, top, left), bar, rail, _, first, before = self.tabs_at_the_start()
        start_tabs, start_slots = tab_pieces(first)
        length = before[2]
        trim = self.trimmed(left, start_slots, Y)
        point = App.Vector(-25, 100, 0)

        interlock = make_tab_interlock(
            bar, face_at(bar, point), start_slots, face_towards(start_slots, Y), crossbar_point=point
        )
        self.doc.recompute()

        tabs, slots = tab_pieces(interlock)
        self.assertEqual((left, rail), (interlock.PieceA, interlock.PieceB))
        self.assertEqual([start_tabs, top, tabs], list(bar.Segments))
        for obj in (tabs, slots, bar):
            self.assertOneSolid(obj)
        self.assertTabsOn(bar, 2, tabs, trim)
        self.assertTabsOn(bar, 0, start_tabs, start_tabs.baseObject[0])
        self.assertAlmostEqual(length + 2 * T, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + 2 * T, self.unfolded_of(bar).Shape.BoundBox.XLength, delta=LENGTH_TOLERANCE)

    def test_deleting_the_interlock_gives_the_bar_its_trim_back_and_undo_brings_the_tabs_back(self):
        self.doc.UndoMode = 1
        (right, top, left), bar, rail, trim, interlock, before = self.tabs_at_the_start()
        volume, _, length = before
        tabs, slots = tab_pieces(interlock)
        names = (interlock.Name, tabs.Name, slots.Name)
        tabbed = (bar.Shape.Volume, bar.DevelopedLength.Value)

        self.doc.openTransaction("Delete")
        self.doc.removeObject(interlock.Name)
        self.doc.commitTransaction()
        self.doc.recompute()

        def gone():
            self.assertEqual([None] * 3, [self.doc.getObject(name) for name in names])
            self.assertEqual([trim, top, left], list(bar.Segments))
            self.assertOneSolid(bar)
            self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
            self.assertAlmostEqual(length, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
            self.assertFalse(trim.Visibility)
            self.assertTrue(rail.Visibility)

        gone()
        self.doc.undo()
        self.doc.recompute()
        interlock, tabs, slots = (self.doc.getObject(name) for name in names)
        self.assertEqual((tabs, slots), tab_pieces(interlock))
        self.assertEqual([tabs, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(tabbed[0], bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(tabbed[1], bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        self.doc.redo()
        self.doc.recompute()
        gone()

    def test_a_saved_bar_with_tabs_opens_with_them(self):
        _, bar, _, _, interlock, _ = self.tabs_at_the_start()
        tabs, _ = tab_pieces(interlock)
        names = [segment.Name for segment in bar.Segments]
        bar_name, tabs_name = bar.Name, tabs.Name
        volume, length = bar.Shape.Volume, bar.DevelopedLength.Value
        folder = tempfile.mkdtemp(prefix="mpf_tab_interlock_folded_bar_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)

        # The cleanup of the fixture closes the document by this same name.
        self.doc = App.openDocument(path)
        bar = self.doc.getObject(bar_name)
        self.assertEqual(names, [segment.Name for segment in bar.Segments])
        self.doc.getObject(tabs_name).touch()
        self.doc.recompute()

        self.assertEqual(names, [segment.Name for segment in bar.Segments])
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)

    def test_a_click_on_a_bend_of_the_crossbar_bar_is_refused(self):
        _, bar = self.legs()
        rail = self.loose(RAIL_BELOW, "Rail")
        names = sorted(obj.Name for obj in self.doc.Objects)
        point = self.bend_point(bar, 45.0)

        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(bar, face_at(bar, point), rail, face_towards(rail, Y), crossbar_point=point)

        self.assertEqual(BEND_MESSAGE, str(raised.exception))
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))

    def test_tabs_at_a_folded_corner_of_the_bar_are_refused(self):
        (right, _, _), bar = self.legs()
        # Its bottom face (y = 225) against the end of the right tube at its corner with the top one.
        rail = self.loose(((-100, 250, 0), (400, 250, 0)), "Rail")
        names = sorted(obj.Name for obj in self.doc.Objects)

        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(bar, face_at(bar, RIGHT_OUTER), rail, face_towards(rail, -Y), crossbar_point=RIGHT_OUTER)

        self.assertEqual(CORNER.format(right.Label, "Rail", bar.Label), str(raised.exception))
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))

    def test_tabs_at_the_open_corner_of_a_closed_bar_are_refused(self):
        (bottom, _, _, _), bar = self.make_bar(**PLAIN)
        # Its +X face (x = -25) against the start of the bottom tube, where the frame opens.
        rail = self.loose(((-50, -100, 0), (-50, 300, 0)), "Rail")
        names = sorted(obj.Name for obj in self.doc.Objects)
        point = App.Vector(150, -25, 0)

        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(bar, face_at(bar, point), rail, face_towards(rail, X), crossbar_point=point)

        self.assertEqual(OPEN.format(bottom.Label, "Rail", bar.Label), str(raised.exception))
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))


class CrossbarOnBarGapTest(TabsOnBarFixture):
    """S8 (T6): the free end of the bar is trimmed with a Gap: its tabs cross it and the bar folds them."""

    def assertAcrossTheGap(self, gap):
        (right, top, left), bar = self.legs()
        rail = self.loose(RAIL_BELOW, "Rail")
        trim = self.trimmed(right, rail, Y)
        trim.TrimGap = gap
        self.doc.recompute()
        self.assertEqual("Valid", trim.getStatusString())
        self.assertAlmostEqual(gap, trim.Shape.BoundBox.YMin, delta=LENGTH_TOLERANCE)
        volume, unfolded_volume, length = bar.Shape.Volume, *self.straight(bar)

        interlock = make_tab_interlock(
            bar, face_at(bar, RIGHT_OUTER), rail, face_towards(rail, Y), crossbar_point=RIGHT_OUTER
        )
        self.doc.recompute()

        tabs, slots = tab_pieces(interlock)
        self.assertEqual([tabs, top, left], list(bar.Segments))
        for obj in (tabs, slots, bar, self.unfolded_of(bar)):
            self.assertOneSolid(obj)
        added = self.assertTabsOn(bar, 0, tabs, trim)
        self.assertAlmostEqual(volume + added, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(unfolded_volume + added, self.unfolded_of(bar).Shape.Volume, delta=VOLUME_TOLERANCE)
        # The tabs cross the gap and the rail wall: T past the rail face, T + gap past the end of the bar (S6).
        self.assertAlmostEqual(-T, bar.Shape.BoundBox.YMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(gap, tabs.Shape.cut(trim.Shape).BoundBox.YMax, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + T + gap, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        box = self.unfolded_of(bar).Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + T + gap, box.XLength, delta=LENGTH_TOLERANCE)
        removed = rail.Shape.Volume - slots.Shape.Volume
        self.assertGreater(removed, VOLUME_TOLERANCE)
        self.assertAlmostEqual(removed, tabs.Shape.common(rail.Shape).Volume, delta=VOLUME_TOLERANCE)

        # The Gap edited afterwards: the tabs follow, the slots stay.
        trim.TrimGap = 0.0
        self.doc.recompute()
        for obj in (tabs, slots, bar):
            self.assertOneSolid(obj)
        self.assertAlmostEqual(-T, bar.Shape.BoundBox.YMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + T + gap, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(removed, rail.Shape.Volume - slots.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_the_tabs_cross_the_gap_of_the_free_end_and_the_bar_is_as_long_as_their_tips(self):
        self.assertAcrossTheGap(GAP)

    def test_the_tabs_cross_a_gap_wider_than_the_tube_wall(self):
        self.assertAcrossTheGap(WIDE_GAP)


class UnfoldedBarStartTest(TabsOnBarFixture):
    def test_the_unfolded_bar_of_a_bar_reaching_past_its_path_starts_at_x_0(self):
        # The free end of the right tube extended 10 mm past its path: the unfold starts there, not at the path.
        (right, _, _), bar = self.legs()
        length = bar.DevelopedLength.Value
        rail = self.loose(((-100, -35, 0), (400, -35, 0)), "Rail")
        self.trimmed(right, rail, Y)
        unfolded = make_unfolded_bar(bar)

        self.assertOneSolid(unfolded)
        self.assertAlmostEqual(length + 10.0, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        box = unfolded.Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(length + 10.0, box.XLength, delta=LENGTH_TOLERANCE)


class BothOnBarsTest(TabsOnBarFixture):
    """(c) The crossbar is the first tube of one bar, the rail the first tube of another one."""

    def test_the_tabs_of_one_bar_go_through_the_slots_of_the_other(self):
        (right, top, left), bar = self.legs()
        rail_tubes = self.frame(edges=(RAIL_BELOW, ((400, -25, 0), (400, 300, 0))))
        rail_bar = make_folded_bar(rail_tubes, bend(**PLAIN))
        self.assertOneSolid(rail_bar)
        rail, up = rail_tubes
        trim = self.trimmed(right, rail, Y)
        length = bar.DevelopedLength.Value
        rail_volume = rail_bar.Shape.Volume
        for obj in (bar, rail_bar):
            make_unfolded_bar(obj)
        point = App.Vector(200, 0, 0)

        interlock = make_tab_interlock(
            bar,
            face_at(bar, RIGHT_OUTER),
            rail_bar,
            face_at(rail_bar, point),
            crossbar_point=RIGHT_OUTER,
            rail_point=point,
        )
        self.doc.recompute()

        tabs, slots = tab_pieces(interlock)
        self.assertEqual((trim, rail), (tabs.baseObject[0], slots.baseObject[0]))
        self.assertEqual([tabs, top, left], list(bar.Segments))
        self.assertEqual([slots, up], list(rail_bar.Segments))
        for obj in (tabs, slots, bar, rail_bar, self.unfolded_of(bar), self.unfolded_of(rail_bar)):
            self.assertOneSolid(obj)
        self.assertTabsOn(bar, 0, tabs, trim)
        removed = self.assertSlotsIn(rail_bar, 0, slots, rail, tabs)
        self.assertAlmostEqual(rail_volume - removed, rail_bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length + T, bar.DevelopedLength.Value, delta=LENGTH_TOLERANCE)
        # The tabs of the bar fill the slots of the other bar.
        self.assertLess(bar.Shape.common(rail_bar.Shape).Volume, VOLUME_TOLERANCE)
        for obj in (bar, rail_bar):
            self.assertNotIn(interlock, obj.Interlocks)


if __name__ == "__main__":
    unittest.main()

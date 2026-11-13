"""Drill Hole on a Folded Bar (odd/tasks/folded-bar-tools.md, T3: S2, S4, S5).

The layout is the user's (L1): the right, top and left tubes folded into one bar, the bottom tube loose. A click on a
straight wall of the bar in the Drill Hole panel drills the tube under the clicked point, on that tube's own face; the
bar folds the hole at once (preview and after OK) and the tube and the hole stay hidden. Cancel, or a preview dropped
for another face, leaves the bar as before and linking no removed object. A click on a bend adds nothing and the panel
says "Click a straight part of the folded bar."

A pattern across the wall (T9, L14) leaves the bar a sound solid with every hole, also where a hole is tangent to
the edge of the wall or to the next hole.
"""

import math
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_drill_hole_panel import AUTO_PREVIEW_PARAM, keep_remembered_diameter
from test_extend_cut_preview import keep_auto_preview, wait
from test_folded_bar_tools import BEND_MESSAGE, FoldedBarToolsFixture, face_at, global_shape
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe import create_drill_hole_tool, folded_bar
from freecad.maxproframe.create_drill_hole_tool import DrillHoleCommand, DrillHoleTaskPanel

# A point on the outer wall of the right tube of the bar (+X), one on its top wall (+Z), and one on the outer wall of
# the loose bottom tube (-Y).
RIGHT_WALL = App.Vector(325, 100, 0)
RIGHT_WALL_LOW = App.Vector(325, 40, 0)
TOP_WALL = App.Vector(150, 225, 0)
BOTTOM_WALL = App.Vector(150, -25, 0)
# The corner of the right tube at the free end of the bar, on its outer wall.
FREE_END_CORNER = App.Vector(325, 0, 25)
VOLUME_TOLERANCE = 1e-3
# L14: the user's TC80x40x1.5 tubes, 40 across the frame and 80 high, and the center of the side wall (+Z, 40 wide)
# of the top tube and of the loose bottom tube.
TC_TUBE = dict(family="Rectangular Hollow", width=40.0, height=80.0, thickness=1.5)
TC_TOP_SIDE = App.Vector(150, 200, 40)
TC_BOTTOM_SIDE = App.Vector(150, 0, 40)
HOLE_DIAMETER = 10.0
# A hole through the 1.5 mm wall.
HOLE_VOLUME = math.pi * (HOLE_DIAMETER / 2) ** 2 * TC_TUBE["thickness"]


class DrillHoleFoldedBarFixture(FoldedBarToolsFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self, DrillHoleTaskPanel)
        keep_remembered_diameter(self)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        recorded = self.recorded
        base = create_drill_hole_tool.DrillHoleTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_drill_hole_tool, "DrillHoleTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        self.events()
        for panel in self.recorded:
            panel.clean()
        self.events()

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def legs(self):
        """(bottom, right, top, left), bar, the bar's volume, the names of the objects: the user's layout."""
        tubes, bar = self.make_legs()
        self.doc.recompute()
        self.doc.clearUndos()
        return tubes, bar, bar.Shape.Volume, self.names()

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def new_objects(self, before):
        return [obj for obj in self.doc.Objects if obj.Name not in before]

    def run_command(self):
        count = len(self.recorded)
        DrillHoleCommand().Activated()
        self.assertEqual(count + 1, len(self.recorded))
        self.assertTrue(Gui.Control.activeDialog())
        return self.recorded[-1]

    def click_at(self, obj, point, sub=None):
        """A click on ``obj`` at the global ``point``, as the 3D view reports it (on the face under it)."""
        sub = sub or face_at(obj, point)
        self.assertIsNotNone(sub, f"{point} is not on {obj.Label}")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, point.x, point.y, point.z)
        self.events()
        wait()

    def vertex_at(self, obj, point):
        for index, vertex in enumerate(global_shape(obj).Vertexes, start=1):
            if (vertex.Point - point).Length < 1e-6:
                return f"Vertex{index}"
        self.fail(f"no vertex of {obj.Label} at {point}")

    def preview(self, before):
        """The one drill hole the panel added to a document that held ``before``."""
        new = self.new_objects(before)
        self.assertEqual(1, len(new), [obj.Name for obj in new])
        self.assertTrue(hasattr(new[0], "ReferenceVertex"))
        return new[0]

    def assertDrilled(self, panel, hole, tube, point):
        """``hole`` drills ``tube`` on its own face under ``point``; the panel names that face."""
        face = face_at(tube, point)
        self.assertEqual((tube, face), panel.face)
        self.assertEqual(f"{tube.Label} ({tube.Name}) {face}", panel.form.face_label.text())
        self.assertEqual(tube, hole.baseObject[0])
        self.assertEqual((face,), tuple(hole.baseObject[1]))
        self.assertEqual("", panel.form.message_label.text())
        self.assertEqual("Valid", hole.getStatusString())

    def assertFolds(self, bar, segments, volume):
        """``bar`` folds ``segments``, hides them, and has less than ``volume``: the hole shows in it."""
        self.assertEqual(segments, list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertNotIn("Touched", bar.State)
        self.assertLess(bar.Shape.Volume, volume - VOLUME_TOLERANCE)
        self.assertTrue(bar.Visibility)
        for segment in segments:
            self.assertFalse(segment.Visibility, segment.Label)

    def assertAsBefore(self, tubes, bar, volume, before):
        _, right, top, left = tubes
        self.assertEqual(before, self.names())
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        for tube in (right, top, left):
            self.assertFalse(tube.Visibility, tube.Label)


class DrillHoleClickOnBarTest(DrillHoleFoldedBarFixture):
    def test_a_click_on_a_straight_wall_drills_the_tube_under_it_and_the_bar_folds_the_preview(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()

        self.click_at(bar, RIGHT_WALL)

        hole = self.preview(before)
        self.assertDrilled(panel, hole, right, RIGHT_WALL)
        # The panel's own recompute folded the hole into the bar: no manual recompute.
        self.assertFolds(bar, [hole, top, left], volume)
        self.assertFalse(right.Visibility)
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def test_ok_keeps_the_hole_folded_into_the_bar(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)

        self.assertTrue(panel.accept())
        self.doc.recompute()

        hole = self.preview(before)
        self.assertEqual(right, hole.baseObject[0])
        self.assertFolds(bar, [hole, top, left], volume)
        self.assertFalse(right.Visibility)

    def test_cancel_leaves_the_bar_as_before(self):
        tubes, bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)
        self.preview(before)

        self.assertTrue(panel.reject())

        self.assertAsBefore(tubes, bar, volume, before)
        self.doc.recompute()
        self.assertAsBefore(tubes, bar, volume, before)

    def test_cancel_without_undo_leaves_the_bar_as_before(self):
        tubes, bar, volume, before = self.legs()
        self.doc.UndoMode = 0
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)
        self.preview(before)

        self.assertTrue(panel.reject())

        self.assertAsBefore(tubes, bar, volume, before)
        self.doc.recompute()
        self.assertAsBefore(tubes, bar, volume, before)

    def test_another_tube_of_the_bar_drops_the_preview_and_the_bar_folds_the_new_one(self):
        (_, right, top, left), bar, volume, before = self.legs()
        self.doc.UndoMode = 0
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)

        self.click_at(bar, TOP_WALL)

        hole = self.preview(before)
        self.assertDrilled(panel, hole, top, TOP_WALL)
        self.assertFolds(bar, [right, hole, left], volume)

    def test_a_click_on_the_bar_where_it_folds_the_preview_stays_on_the_tube(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)

        self.click_at(bar, RIGHT_WALL_LOW)

        hole = self.preview(before)
        self.assertDrilled(panel, hole, right, RIGHT_WALL_LOW)
        self.assertFolds(bar, [hole, top, left], volume)

    def test_a_vertex_of_the_bar_is_the_vertex_of_the_tube_under_it(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)

        self.click_at(bar, FREE_END_CORNER, sub=self.vertex_at(bar, FREE_END_CORNER))

        self.assertEqual(self.vertex_at(right, FREE_END_CORNER), panel.vertex)
        hole = self.preview(before)
        self.assertDrilled(panel, hole, right, RIGHT_WALL)
        self.assertEqual(self.vertex_at(right, FREE_END_CORNER), hole.ReferenceVertex)
        self.assertFolds(bar, [hole, top, left], volume)

    def test_a_preselected_wall_of_the_bar_is_the_face_of_the_tube_under_it(self):
        (_, right, top, left), bar, volume, before = self.legs()
        Gui.Selection.addSelection(
            self.doc.Name, bar.Name, face_at(bar, RIGHT_WALL), RIGHT_WALL.x, RIGHT_WALL.y, RIGHT_WALL.z
        )

        panel = self.run_command()

        self.assertEqual((right, face_at(right, RIGHT_WALL)), panel.face)
        self.assertEqual("", panel.form.message_label.text())

    def test_apply_and_continue_then_a_click_on_the_bar_builds_on_the_hole_made(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)
        first = self.preview(before)
        self.assertTrue(panel.apply_and_continue())
        one_hole = bar.Shape.Volume

        self.click_at(bar, RIGHT_WALL_LOW)

        second = self.preview(before + [first.Name])
        self.assertDrilled(panel, second, first, RIGHT_WALL_LOW)
        # Both holes show in the bar.
        self.assertFolds(bar, [second, top, left], one_hole)


class DrillHoleBendTest(DrillHoleFoldedBarFixture):
    def test_a_click_on_a_bend_adds_nothing_and_says_why(self):
        tubes, bar, volume, before = self.legs()
        panel = self.run_command()

        # The round outer wall of the bend, and the side wall where two tubes meet at the corner.
        for point in (self.bend_point(bar, 45.0), App.Vector(285, 195, 25)):
            with self.subTest(point=point):
                self.click_at(bar, point)

                self.assertEqual(BEND_MESSAGE, panel.form.message_label.text())
                self.assertIsNone(panel.face)
                self.assertEqual("No preview", panel.form.status_label.text())
                self.assertAsBefore(tubes, bar, volume, before)

    def test_a_click_on_a_bend_keeps_the_face_picked_before(self):
        (_, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)

        self.click_at(bar, self.bend_point(bar, 45.0))

        self.assertEqual(BEND_MESSAGE, panel.form.message_label.text())
        self.assertEqual((right, face_at(right, RIGHT_WALL)), panel.face)
        hole = self.preview(before)
        self.assertFolds(bar, [hole, top, left], volume)


class DrillHoleLooseTubeTest(DrillHoleFoldedBarFixture):
    def test_a_click_on_the_loose_tube_drills_it_and_leaves_the_bar_alone(self):
        (bottom, right, top, left), bar, volume, before = self.legs()
        panel = self.run_command()

        self.click_at(bottom, BOTTOM_WALL)

        hole = self.preview(before)
        self.assertDrilled(panel, hole, bottom, BOTTOM_WALL)
        self.assertFalse(bottom.Visibility)
        self.assertTrue(panel.accept())
        self.doc.recompute()
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)


class DrillHoleTransversalPatternTest(DrillHoleFoldedBarFixture):
    """L14: 10 mm holes at the center of the side wall of the top tube, One wall, 1 back and 1 forward along at 50 mm,
    then 1 across backward: 15 mm puts that row tangent to the edge of the 40 mm wall (15 + 5 = 20), 10 mm puts it
    tangent to the holes at the point (pitch = diameter), 12 mm is clear of both."""

    def tc_legs(self):
        """(bottom, right, top, left), bar, the bar's volume: the user's layout with TC80x40x1.5 tubes."""
        tubes = self.frame(**TC_TUBE)
        bar = folded_bar.make_folded_bar(tubes[1:], bend(**PLAIN))
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertSound(bar.Shape)
        return tubes, bar, bar.Shape.Volume

    def drill_pattern(self, obj, point, across_pitch):
        """The Drill Hole panel on ``obj`` clicked at ``point`` (the center of the face) with the user's pattern."""
        panel = self.run_command()
        self.click_at(obj, point)
        form = panel.form
        form.spin_diameter.setValue(HOLE_DIAMETER)
        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("One wall"))
        form.groupBox_pattern.setChecked(True)
        for side, count, pitch in (
            ("along_backward", 1, 50.0),
            ("along_forward", 1, 50.0),
            ("across_backward", 1, across_pitch),
        ):
            getattr(form, f"spin_{side}_count").setValue(count)
            getattr(form, f"spin_{side}_pitch").setValue(pitch)
        self.events()
        wait()
        return panel

    def assertSound(self, shape):
        """One valid solid FreeCAD can draw: the geometry check finds nothing and every edge has its curve."""
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(1, len(shape.Solids))
        try:
            shape.check(True)
        except Exception as error:
            self.fail(f"the geometry check fails: {error}")
        for index, edge in enumerate(shape.Edges, 1):
            try:
                edge.Curve
            except Exception as error:
                self.fail(f"Edge{index} has no curve: {error}")

    def assertBarHasTheHoles(self, bar, tube, hole, volume):
        """``bar`` folds ``hole`` into a sound solid, less what the holes take from ``tube``."""
        self.assertEqual("Valid", hole.getStatusString())
        self.assertSound(hole.Shape)
        self.assertEqual("Valid", bar.getStatusString())
        self.assertIn(hole, bar.Segments)
        self.assertSound(bar.Shape)
        drilled = tube.Shape.Volume - hole.Shape.Volume
        self.assertGreaterEqual(drilled, 6 * HOLE_VOLUME - VOLUME_TOLERANCE)
        self.assertAlmostEqual(volume - drilled, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def check_bar_pattern(self, pitch):
        (_, right, top, left), bar, volume = self.tc_legs()
        before = self.names()
        panel = self.drill_pattern(bar, TC_TOP_SIDE, pitch)

        hole = self.preview(before)
        self.assertEqual((top, face_at(top, TC_TOP_SIDE)), panel.face)
        # The preview shows in the bar, and so does the hole after OK.
        self.assertBarHasTheHoles(bar, top, hole, volume)
        self.assertTrue(panel.accept())
        self.doc.recompute()
        self.assertEqual([right, hole, left], list(bar.Segments))
        self.assertBarHasTheHoles(bar, top, hole, volume)
        return bar, volume

    def test_a_row_across_tangent_to_the_edge_of_the_wall_keeps_the_bar_sound_with_every_hole(self):
        self.check_bar_pattern(15.0)

    def test_a_row_across_tangent_to_the_holes_at_the_point_keeps_the_bar_sound_with_every_hole(self):
        self.check_bar_pattern(10.0)

    def test_a_row_across_clear_of_the_edge_keeps_the_bar_sound_with_every_hole(self):
        bar, volume = self.check_bar_pattern(12.0)

        # Clear of the edge and of each other: six whole holes through the wall.
        self.assertAlmostEqual(volume - 6 * HOLE_VOLUME, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def check_loose_pattern(self, pitch):
        (bottom, *_), bar, volume = self.tc_legs()
        before = self.names()

        self.drill_pattern(bottom, TC_BOTTOM_SIDE, pitch)

        hole = self.preview(before)
        self.assertEqual("Valid", hole.getStatusString())
        self.assertSound(hole.Shape)
        self.assertGreaterEqual(bottom.Shape.Volume - hole.Shape.Volume, 6 * HOLE_VOLUME - VOLUME_TOLERANCE)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_the_pattern_tangent_to_the_edge_on_the_loose_tube_leaves_it_sound(self):
        self.check_loose_pattern(15.0)

    def test_the_pattern_tangent_to_the_holes_on_the_loose_tube_leaves_it_sound(self):
        self.check_loose_pattern(10.0)


class DrillHoleDeleteTest(DrillHoleFoldedBarFixture):
    def test_deleting_a_hole_folded_into_the_bar_leaves_the_tube_hidden_and_the_bar_as_before(self):
        tubes, bar, volume, before = self.legs()
        right = tubes[1]
        panel = self.run_command()
        self.click_at(bar, RIGHT_WALL)
        self.assertTrue(panel.accept())
        hole = self.preview(before)

        # As a delete in the tree does.
        self.assertTrue(hole.ViewObject.Proxy.onDelete(hole.ViewObject, []))
        self.assertFalse(right.Visibility)
        self.doc.removeObject(hole.Name)
        self.doc.recompute()

        self.assertAsBefore(tubes, bar, volume, before)

    def test_deleting_a_hole_on_the_loose_tube_shows_the_tube(self):
        (bottom, *_), bar, volume, before = self.legs()
        panel = self.run_command()
        self.click_at(bottom, BOTTOM_WALL)
        self.assertTrue(panel.accept())
        hole = self.preview(before)
        self.assertFalse(bottom.Visibility)

        self.assertTrue(hole.ViewObject.Proxy.onDelete(hole.ViewObject, []))

        self.assertTrue(bottom.Visibility)


if __name__ == "__main__":
    unittest.main()

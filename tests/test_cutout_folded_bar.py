"""Cutout on a Folded Bar (odd/tasks/folded-bar-tools.md, T4: S3 S4 S5).

The layout is the user's (L1): the right, top and left tubes folded into one bar, the bottom tube loose. A click on
the bar in the Cutout panel takes the face of the tube under the clicked point (``folded_bar.segment_at``): the sketch
and the cutout are made on that tube face, never on the bar. The bar folds the new cutout at the next recompute of
the document, without a manual recompute, and the tube and the cutout stay hidden (S4). A click on a bend adds
nothing and says "Click a straight part of the folded bar." (S5). One face and one sketch preselected cut the tube
under the face of the bar directly, or are refused on a bend.
"""

import math
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtWidgets
from test_folded_bar_tools import BEND_MESSAGE, FoldedBarToolsFixture, face_at
from test_unfolded_geometry import T

from freecad.maxproframe import create_extruded_cutout_tool
from freecad.maxproframe.create_extruded_cutout_tool import AddExtrudedCutoutCommandClass
from freecad.maxproframe.frameforge_exceptions import FrameForgeException

HOLE_RADIUS = 5.0
NO_FACE = "Click a planar face of a profile, a trimmed profile, a cutout or a folded bar."
# The outer wall of the right tube, and the top wall (+Z) of the right tube (a bar face spanning the three tubes).
RIGHT_OUTER = App.Vector(325, 100, 0)
RIGHT_TOP = App.Vector(300, 100, 25)
VOLUME_TOLERANCE = 1e-2


def face_towards(obj, point, direction):
    """Name of the planar face of ``obj`` through ``point`` whose outward normal points along ``direction``."""
    vertex = Part.Vertex(point)
    for index, face in enumerate(obj.Shape.Faces, start=1):
        if (
            isinstance(face.Surface, Part.Plane)
            and face.normalAt(0, 0).getAngle(direction) < 1e-6
            and face.distToShape(vertex)[0] < 1e-6
        ):
            return f"Face{index}"
    raise AssertionError(f"no face of {obj.Label} through {point} towards {direction}")


def hole(walls):
    return math.pi * HOLE_RADIUS**2 * T * walls


class CutoutFoldedBarFixture(FoldedBarToolsFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        # The face panel opens the new sketch once closed: the tests draw in it without the Sketcher. The patch
        # outlives close_dialog, where that deferred opening runs (FixtureIsolationTest).
        opener = patch.object(create_extruded_cutout_tool, "_edit_sketch")
        self.edit_sketch = opener.start()
        self.addCleanup(opener.stop)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        QtWidgets.QApplication.processEvents()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def legs(self):
        (bottom, right, top, left), bar = self.make_legs()
        self.doc.recompute()
        return (bottom, right, top, left), bar

    def select(self, obj, sub="", point=None):
        if point is None:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        else:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, point.x, point.y, point.z)

    def click(self, obj, point):
        """A click in the 3D view on ``obj`` at the global ``point``: it replaces the selection."""
        Gui.Selection.clearSelection()
        self.select(obj, face_at(obj, point), point)
        QtWidgets.QApplication.processEvents()

    def run_command(self):
        """Run the command on the current selection and return the face panel it opens."""
        created = []
        base = create_extruded_cutout_tool.CutoutTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_extruded_cutout_tool, "CutoutTaskPanel", Recording):
            AddExtrudedCutoutCommandClass().Activated()
        self.panels.extend(created)
        self.assertEqual(1, len(created))
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def run_direct(self):
        """Run the command on a face and a sketch selected; return the depth panels it opened."""
        created = []
        base = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_extruded_cutout_tool, "CreateExtrudedCutoutTaskPanel", Recording):
            AddExtrudedCutoutCommandClass().Activated()
        return created

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def created(self, before):
        """(sketch, cutout) the command added to a document that held ``before``."""
        new = [obj for obj in self.doc.Objects if obj.Name not in before]
        sketches = [obj for obj in new if obj.isDerivedFrom("Sketcher::SketchObject")]
        cutouts = [obj for obj in new if hasattr(obj, "baseObject")]
        self.assertEqual((1, 1, 2), (len(sketches), len(cutouts), len(new)))
        return sketches[0], cutouts[0]

    def face_label(self, panel):
        return panel.form.face_label.text()

    def message(self, panel):
        return panel.form.message_label.text()

    def add_hole(self, sketch, center):
        """A circle on ``sketch`` centered on the global ``center``."""
        local = sketch.Placement.inverse().multVec(center)
        sketch.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), App.Vector(0, 0, 1), HOLE_RADIUS))

    def assertOnTube(self, tube, face, sketch, cutout, bar):
        """The sketch and the cutout link the tube face, never the bar."""
        self.assertEqual((tube, [face]), cutout.baseObject)
        self.assertNotIn(bar, cutout.OutList)
        self.assertNotIn(bar, sketch.OutList)

    def new_cutout(self, tube_point):
        """Click the bar at ``tube_point`` in the face panel and press OK: (panel, sketch, cutout)."""
        before = self.names()
        panel = self.run_command()
        self.click(self.bar, tube_point)
        self.assertEqual("", self.message(panel))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        return panel, sketch, cutout


class CutoutPanelOnFoldedBarTest(CutoutFoldedBarFixture):
    def test_a_click_on_the_outer_wall_of_a_leg_cuts_the_face_of_its_tube_and_the_bar_follows(self):
        (_, right, top, left), bar = self.legs()
        self.bar = bar
        volume = bar.Shape.Volume
        face = face_towards(right, RIGHT_OUTER, App.Vector(1, 0, 0))

        panel, sketch, cutout = self.new_cutout(RIGHT_OUTER)

        self.assertOnTube(right, face, sketch, cutout, bar)
        self.assertEqual([(right, (face,))], sketch.AttachmentSupport)
        self.assertEqual("FlatFace", sketch.MapMode)
        self.assertEqual({right}, {obj for obj, _ in sketch.ExternalGeometry})
        self.assertEqual("One wall", cutout.CutType)
        # OK recomputed the document: the bar folds the cutout at once, the tube and the cutout stay hidden.
        self.assertEqual([cutout, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertFalse(right.Visibility)
        self.assertFalse(cutout.Visibility)
        self.edit_sketch.assert_not_called()

        # The hole drawn in the sketch shows in the bar after a plain recompute.
        self.add_hole(sketch, RIGHT_OUTER)
        self.doc.recompute()

        self.assertEqual("Valid", cutout.getStatusString())
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume - hole(1), bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertFalse(right.Visibility)
        self.assertFalse(cutout.Visibility)

    def test_the_face_label_names_the_tube_face_under_the_click(self):
        (_, right, _, _), bar = self.legs()
        panel = self.run_command()
        face = face_towards(right, RIGHT_TOP, App.Vector(0, 0, 1))

        self.click(bar, RIGHT_TOP)

        self.assertEqual(f"{right.Label} ({right.Name}) {face}", self.face_label(panel))
        self.assertEqual("", self.message(panel))

    def test_a_click_on_a_bend_adds_nothing_and_says_to_click_a_straight_part(self):
        (_, right, top, left), bar = self.legs()
        volume = bar.Shape.Volume
        before = self.names()
        panel = self.run_command()

        for point in (self.bend_point(bar, 45.0), App.Vector(285, 195, 25)):
            with self.subTest(point=point):
                self.click(bar, point)
                self.assertEqual(BEND_MESSAGE, self.message(panel))
                self.assertEqual(NO_FACE, self.face_label(panel))

        self.assertFalse(panel.accept())
        self.assertEqual(before, self.names())
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_a_bend_click_after_a_face_keeps_the_face(self):
        (_, right, _, _), bar = self.legs()
        panel = self.run_command()
        face = face_towards(right, RIGHT_OUTER, App.Vector(1, 0, 0))
        self.click(bar, RIGHT_OUTER)

        self.click(bar, self.bend_point(bar, 45.0))

        self.assertEqual(BEND_MESSAGE, self.message(panel))
        self.assertEqual(f"{right.Label} ({right.Name}) {face}", self.face_label(panel))

    def test_a_preselected_face_of_the_bar_takes_the_tube_face_under_the_point(self):
        (_, right, top, left), bar = self.legs()
        self.select(bar, face_at(bar, RIGHT_TOP), RIGHT_TOP)
        face = face_towards(right, RIGHT_TOP, App.Vector(0, 0, 1))
        before = self.names()

        panel = self.run_command()

        self.assertEqual(f"{right.Label} ({right.Name}) {face}", self.face_label(panel))
        self.assertEqual("", self.message(panel))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        self.assertOnTube(right, face, sketch, cutout, bar)
        self.assertEqual([cutout, top, left], list(bar.Segments))

    def test_a_preselected_bend_is_refused_with_the_message(self):
        _, bar = self.legs()
        point = self.bend_point(bar, 45.0)
        self.select(bar, face_at(bar, point), point)

        panel = self.run_command()

        self.assertEqual(NO_FACE, self.face_label(panel))
        self.assertEqual(BEND_MESSAGE, self.message(panel))

    def test_cancel_of_the_face_panel_leaves_the_bar_as_before(self):
        (_, right, top, left), bar = self.legs()
        volume = bar.Shape.Volume
        before = self.names()
        panel = self.run_command()
        self.click(bar, RIGHT_OUTER)

        self.assertTrue(panel.reject())
        self.doc.recompute()

        self.assertEqual(before, self.names())
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_a_loose_tube_still_takes_its_own_face(self):
        (bottom, right, top, left), bar = self.legs()
        point = App.Vector(150, -25, 0)
        face = face_towards(bottom, point, App.Vector(0, -1, 0))
        before = self.names()
        panel = self.run_command()

        self.click(bottom, point)

        self.assertEqual(f"{bottom.Label} ({bottom.Name}) {face}", self.face_label(panel), self.message(panel))
        self.assertTrue(panel.accept(), self.message(panel))
        sketch, cutout = self.created(before)
        self.assertEqual((bottom, [face]), cutout.baseObject)
        self.assertEqual([(bottom, (face,))], sketch.AttachmentSupport)
        self.assertEqual([right, top, left], list(bar.Segments))


class DepthPanelOnFoldedBarTest(CutoutFoldedBarFixture):
    def drawn_cutout(self):
        (_, right, top, left), bar = self.legs()
        self.bar = bar
        volume = bar.Shape.Volume
        _, sketch, cutout = self.new_cutout(RIGHT_TOP)
        self.add_hole(sketch, RIGHT_TOP)
        self.doc.recompute()
        self.assertAlmostEqual(volume - hole(1), bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        return (right, top, left), bar, sketch, cutout, volume

    def test_the_depth_preview_shows_in_the_bar(self):
        _, bar, _, cutout, volume = self.drawn_cutout()
        panel = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel(cutout, created=True)
        form = panel.form

        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("Through All"))

        # Through All cuts the top and the bottom wall of the tube.
        self.assertAlmostEqual(volume - hole(2), bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertTrue(panel.accept())
        self.assertAlmostEqual(volume - hole(2), bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertFalse(cutout.Visibility)

    def test_cancel_of_a_new_cutout_gives_the_tube_back_to_the_bar(self):
        (right, top, left), bar, sketch, cutout, volume = self.drawn_cutout()
        names = (cutout.Name, sketch.Name)
        panel = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel(cutout, created=True)

        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
            self.assertTrue(panel.reject())

        self.assertIsNone(self.doc.getObject(names[0]))
        self.assertIsNone(self.doc.getObject(names[1]))
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertFalse(right.Visibility)


class FixtureIsolationTest(unittest.TestCase):
    """A test of this module leaves nothing behind for the next one (weekly CI #148, S4).

    OK in the face panel opens the new sketch once the panel is closed (``_edit_sketch`` on a 0 ms timer). The
    fixture closes the panel in its cleanup: the timer then fires and must still find the patched opener. The real
    one opened the Sketcher on the document being closed, whose closing then left the depth panel of that cutout
    on a timer for the next test (``_DepthAfterSketch``).
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_the_sketch_made_by_ok_is_not_opened_once_the_test_has_ended(self):
        result = unittest.TestResult()
        with patch.object(create_extruded_cutout_tool, "_edit_sketch") as after_the_test:
            # Through a suite, as the runner does: the class fixtures of the nested test run too.
            unittest.TestSuite([CutoutPanelOnFoldedBarTest("test_a_loose_tube_still_takes_its_own_face")]).run(result)
            QtWidgets.QApplication.processEvents()

        self.assertEqual([], [text for _, text in result.failures + result.errors])
        after_the_test.assert_not_called()
        self.assertEqual(set(), create_extruded_cutout_tool._DepthAfterSketch._listening)
        self.assertFalse(Gui.Control.activeDialog())


class DirectCutoutOnFoldedBarTest(CutoutFoldedBarFixture):
    def hole_sketch(self, center):
        """A free sketch holding a hole centered on the global ``center``, in the plane z = ``center.z``."""
        sketch = self.doc.addObject("Sketcher::SketchObject", "HoleSketch")
        sketch.Placement.Base = App.Vector(0, 0, center.z)
        self.add_hole(sketch, center)
        self.doc.recompute()
        return sketch

    def test_a_bar_face_and_a_sketch_cut_the_tube_under_the_face_and_the_bar_follows(self):
        (_, right, top, left), bar = self.legs()
        volume = bar.Shape.Volume
        sketch = self.hole_sketch(RIGHT_TOP)
        face = face_towards(right, RIGHT_TOP, App.Vector(0, 0, 1))
        self.select(bar, face_at(bar, RIGHT_TOP), RIGHT_TOP)
        self.select(sketch)
        before = self.names()

        panels = self.run_direct()

        cutout = self.doc.getObject(f"{right.Name}_Ex")
        self.assertIsNotNone(cutout)
        self.assertEqual([cutout.Name], [name for name in self.names() if name not in before])
        self.assertEqual([cutout], [panel.obj for panel in panels])
        self.assertEqual((right, [face]), cutout.baseObject)
        self.assertEqual(sketch, cutout.Sketch)
        self.assertNotIn(bar, cutout.OutList)
        # The bar folds the cutout at once: Through All cuts the top and the bottom wall of the tube.
        self.assertEqual([cutout, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume - hole(2), bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertFalse(right.Visibility)
        self.assertFalse(cutout.Visibility)

    def test_a_bend_of_the_bar_and_a_sketch_are_refused_with_the_message(self):
        (_, right, top, left), bar = self.legs()
        sketch = self.hole_sketch(RIGHT_TOP)
        point = App.Vector(285, 195, 25)
        self.select(bar, face_at(bar, point), point)
        self.select(sketch)
        before = self.names()

        with self.assertRaises(FrameForgeException) as raised:
            self.run_direct()

        self.assertEqual(BEND_MESSAGE, str(raised.exception))
        self.assertEqual(before, self.names())
        self.assertEqual([right, top, left], list(bar.Segments))
        self.assertFalse(Gui.Control.activeDialog())


if __name__ == "__main__":
    unittest.main()

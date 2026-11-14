"""Extend / Cut and Notch on a Folded Bar (odd/tasks/folded-bar-tools.md, T5: S3 S4 S5).

The layout is the user's (L1): a Folded Bar of three tubes (right, top, left) with the bottom tube loose. A click on
the bar in the panel stands for the tube under the clicked point: a target face is that tube's own face (a click on
a bend says "Click a straight part of the folded bar."), a profile to cut is the tube under the point or the nearest
one. A trim of a tube of the bar shows folded into the bar at once (preview and OK), Cancel leaves the bar as before.
A cut that would make the bar depend on itself, or cut a tube at its folded corner, is refused.
"""

import time
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtCore, QtWidgets
from test_folded_bar_tools import BEND_MESSAGE, ON_FACE, FoldedBarToolsFixture, face_at

from freecad.maxproframe import create_extend_cut_tool, create_notch_tool, folded_bar
from freecad.maxproframe.create_extend_cut_tool import ExtendCutCommand
from freecad.maxproframe.create_notch_tool import NotchCommand
from freecad.maxproframe.ff_tools import get_param_group

FOLD_MESSAGE = "{} cannot be cut at its folded corner with {}."
SELF_MESSAGE = "{} cannot trim itself"
FACE_MESSAGE = "Click a face of the folded bar."
NO_TARGET = "Click a face, or select a profile in the tree."
# Points on the bar: the outer wall of the right leg (normal +X), the outer wall of the top leg (normal +Y).
RIGHT_OUTER = App.Vector(325, 100, 0)
TOP_OUTER = App.Vector(150, 225, 0)
# The outer wall of the loose bottom tube (normal -Y).
BOTTOM_OUTER = App.Vector(150, -25, 0)
VOLUME_TOLERANCE = 1e-3


def wait(seconds=0.6):
    # Lets the preview timer fire: processEvents alone does not wait for it.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


class ExtendCutBarFixture(FoldedBarToolsFixture):
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
        self.addCleanup(self.close_panels)
        for panel_class in (create_extend_cut_tool.ExtendCutTaskPanel, create_notch_tool.NotchTaskPanel):
            self.keep_auto_preview(panel_class)

    def keep_auto_preview(self, panel_class):
        """Start from the default Update automatically of ``panel_class``; restore what was stored after the test."""
        name = panel_class.auto_preview_param
        param = get_param_group(writable=True)
        stored = name in param.GetBools()
        previous = param.GetBool(name, True)

        def restore():
            if stored:
                param.SetBool(name, previous)
            else:
                param.RemBool(name)

        self.addCleanup(restore)
        param.RemBool(name)

    def close_panels(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def run_command(self, module, panel_name, command):
        created = []
        base = getattr(module, panel_name)

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(module, panel_name, Recording):
            command.Activated()
        self.panels.extend(created)
        self.assertEqual(1, len(created))
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def extend_cut_panel(self):
        return self.run_command(create_extend_cut_tool, "ExtendCutTaskPanel", ExtendCutCommand())

    def notch_panel(self):
        return self.run_command(create_notch_tool, "NotchTaskPanel", NotchCommand())

    def click(self, obj, point):
        """A click in the 3D view on ``obj`` at the global ``point``: it replaces the selection."""
        sub = face_at(obj, point)
        self.assertIsNotNone(sub, f"{point} is not on {obj.Label}")
        Gui.Selection.clearSelection()
        with patch.object(
            QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.KeyboardModifier.NoModifier
        ):
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, point.x, point.y, point.z)
            QtWidgets.QApplication.processEvents()

    def select_whole(self, obj):
        """``obj`` selected as a whole in the tree: it replaces the selection."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name)
        QtWidgets.QApplication.processEvents()

    def target_bottom(self):
        """An Extend Cut panel with the outer wall of the loose bottom tube as target, and the bar."""
        (bottom, right, top, left), bar = self.make_legs()
        panel = self.extend_cut_panel()
        self.click(bottom, BOTTOM_OUTER)
        self.assertEqual(bottom, panel.target[0])
        return panel, (bottom, right, top, left), bar

    def trims(self, joint="Extend Cut"):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == joint]

    def message(self, panel):
        return panel.form.message_label.text()

    def assertFaceAt(self, obj, face, point):
        """``face`` is the face of ``obj`` (a tube, never the bar) under the global ``point``."""
        self.assertIsNotNone(face)
        self.assertEqual(face_at(obj, point), face)

    def assertBarAsBefore(self, bar, segments, volume):
        self.doc.recompute()
        self.assertEqual(segments, list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        # The right leg ends at the path again.
        self.assertAlmostEqual(0.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)
        for segment in segments:
            self.assertFalse(segment.Visibility, segment.Label)


class ExtendCutTargetOnBarTest(ExtendCutBarFixture):
    def test_a_target_face_clicked_on_the_bar_is_the_face_of_the_tube_under_the_point(self):
        (bottom, right, _, _), bar = self.make_legs()
        panel = self.extend_cut_panel()

        self.click(bar, RIGHT_OUTER)

        obj, faces = panel.target
        self.assertEqual(right, obj)
        self.assertEqual(1, len(faces))
        self.assertFaceAt(right, faces[0], RIGHT_OUTER)
        self.assertEqual(" ".join([f"{right.Label} ({right.Name})", faces[0]]), panel.form.target_label.text())
        self.assertEqual("", self.message(panel))

        self.click(bottom, BOTTOM_OUTER)
        self.assertEqual([bottom], panel.profiles)
        self.assertTrue(panel.accept())

        (trim,) = self.trims()
        self.assertEqual("Valid", trim.getStatusString())
        self.assertEqual(bottom, trim.TrimmedBody)
        self.assertEqual([(right, (faces[0],))], trim.TrimmingBoundary)
        # The loose tube now reaches the outer wall of the right leg.
        self.assertAlmostEqual(325.0, trim.Shape.BoundBox.XMax, delta=ON_FACE)

    def test_a_target_click_on_a_bend_is_refused_with_the_message(self):
        _, bar = self.make_legs()
        panel = self.extend_cut_panel()

        self.click(bar, self.bend_point(bar, 45.0))

        self.assertIsNone(panel.target)
        self.assertEqual(BEND_MESSAGE, self.message(panel))


class ExtendCutProfilesOnBarTest(ExtendCutBarFixture):
    def test_the_free_end_leg_clicked_on_the_bar_is_cut_and_the_bar_follows_the_preview(self):
        panel, (bottom, right, top, left), bar = self.target_bottom()
        volume = bar.Shape.Volume

        self.click(bar, RIGHT_OUTER)
        wait()

        self.assertEqual([right], panel.profiles)
        self.assertEqual("", self.message(panel))
        (preview,) = self.trims()
        self.assertEqual("Valid", preview.getStatusString())
        self.assertEqual(right, preview.TrimmedBody)
        self.assertEqual([preview, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        # The right leg reaches the outer wall of the bottom tube.
        self.assertAlmostEqual(-25.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)
        self.assertFalse(right.Visibility)
        self.assertFalse(preview.Visibility)

        self.assertTrue(panel.reject())

        self.assertEqual([], self.trims())
        self.assertBarAsBefore(bar, [right, top, left], volume)

    def test_ok_keeps_the_cut_folded_into_the_bar(self):
        panel, (bottom, right, top, left), bar = self.target_bottom()

        self.click(bar, RIGHT_OUTER)
        self.assertTrue(panel.accept())
        self.doc.recompute()

        (trim,) = self.trims()
        self.assertEqual([trim, top, left], list(bar.Segments))
        self.assertEqual([(bottom, (face_at(bottom, BOTTOM_OUTER),))], trim.TrimmingBoundary)
        self.assertOneSolid(bar)
        self.assertAlmostEqual(-25.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)
        self.assertFalse(right.Visibility)
        self.assertFalse(trim.Visibility)

    def test_cancel_with_undo_off_leaves_the_bar_as_before(self):
        self.doc.UndoMode = 0
        panel, (bottom, right, top, left), bar = self.target_bottom()
        volume = bar.Shape.Volume

        self.click(bar, RIGHT_OUTER)
        wait()
        self.assertEqual(1, len(self.trims()))
        self.assertTrue(panel.reject())

        self.assertEqual([], self.trims())
        self.assertBarAsBefore(bar, [right, top, left], volume)

    def test_a_profile_click_on_a_bend_takes_the_nearest_tube(self):
        panel, (bottom, right, _, _), bar = self.target_bottom()

        self.click(bar, self.bend_point(bar, 20.0))

        self.assertEqual([right], panel.profiles)
        self.assertEqual("", self.message(panel))


class ExtendCutBarRefusalsTest(ExtendCutBarFixture):
    def test_a_tube_cannot_be_cut_at_its_folded_corner(self):
        (_, right, top, _), bar = self.make_legs()
        panel = self.extend_cut_panel()
        self.click(bar, TOP_OUTER)
        self.assertEqual(top, panel.target[0])

        self.click(bar, RIGHT_OUTER)

        self.assertEqual([], panel.profiles)
        self.assertEqual(FOLD_MESSAGE.format(right.Label, top.Label), self.message(panel))
        wait()
        self.assertEqual([], self.trims())

    def test_a_target_built_on_the_bar_cannot_cut_one_of_its_tubes(self):
        # The Unfolded Bar is made from the bar: a trim of a tube against it would make the bar depend on itself.
        (_, right, _, _), bar = self.make_legs()
        unfolded = folded_bar.make_unfolded_bar(bar)
        # The middle of its side wall farthest along +Y.
        side = max(unfolded.Shape.Faces, key=lambda face: face.CenterOfMass.y).CenterOfMass
        panel = self.extend_cut_panel()
        self.click(unfolded, side)
        self.assertEqual(unfolded, panel.target[0])

        self.click(bar, RIGHT_OUTER)

        self.assertEqual([], panel.profiles)
        self.assertEqual(SELF_MESSAGE.format(right.Label), self.message(panel))

    def test_a_target_on_the_tube_being_cut_is_refused(self):
        panel, (_, right, _, _), bar = self.target_bottom()
        self.click(bar, RIGHT_OUTER)
        wait()
        panel.form.change_target_button.setChecked(True)

        self.click(bar, App.Vector(325, 150, 0))

        self.assertEqual(SELF_MESSAGE.format(right.Label), self.message(panel))
        self.assertNotEqual(right, panel.target[0])

    def test_the_whole_bar_selected_in_the_tree_is_not_a_target(self):
        # odd/tasks/pending-followups.md, S4d: it asks for a face, not for a straight part.
        _, bar = self.make_legs()
        Gui.Selection.addSelection(self.doc.Name, bar.Name, "")

        panel = self.extend_cut_panel()

        self.assertIsNone(panel.target)
        self.assertEqual([], panel.profiles)
        self.assertEqual(FACE_MESSAGE, self.message(panel))
        self.assertEqual(NO_TARGET, panel.form.target_label.text())

    def test_the_whole_bar_selected_in_the_tree_while_the_panel_is_open_is_not_a_target(self):
        _, bar = self.make_legs()
        panel = self.extend_cut_panel()

        self.select_whole(bar)

        self.assertIsNone(panel.target)
        self.assertEqual([], panel.profiles)
        self.assertEqual(FACE_MESSAGE, self.message(panel))
        self.assertEqual(NO_TARGET, panel.form.target_label.text())


class ExtendCutWholeBarTest(ExtendCutBarFixture):
    """odd/tasks/pending-followups.md, S4d: a whole bar selected in the tree adds the tubes at its free ends."""

    def assertProfiles(self, profiles, panel):
        self.assertEqual(profiles, panel.profiles)
        rows = [panel.form.profiles_list.item(row).text() for row in range(panel.form.profiles_list.count())]
        self.assertEqual([f"{obj.Label} ({obj.Name})" for obj in profiles], rows)

    def test_a_whole_bar_selected_while_the_panel_is_open_adds_the_tubes_at_its_free_ends(self):
        panel, (bottom, right, _, left), bar = self.target_bottom()

        self.select_whole(bar)

        self.assertEqual(bottom, panel.target[0])
        self.assertProfiles([right, left], panel)
        self.assertEqual("", self.message(panel))
        self.assertTrue(panel.accept())
        self.assertEqual({right, left}, {trim.TrimmedBody for trim in self.trims()})
        for trim in self.trims():
            self.assertEqual("Valid", trim.getStatusString())

    def test_a_whole_bar_preselected_after_the_target_adds_the_tubes_at_its_free_ends(self):
        (bottom, right, _, left), bar = self.make_legs()
        Gui.Selection.addSelection(
            self.doc.Name, bottom.Name, face_at(bottom, BOTTOM_OUTER), BOTTOM_OUTER.x, BOTTOM_OUTER.y, BOTTOM_OUTER.z
        )
        Gui.Selection.addSelection(self.doc.Name, bar.Name, "")

        panel = self.extend_cut_panel()

        obj, faces = panel.target
        self.assertEqual(bottom, obj)
        self.assertFaceAt(bottom, faces[0], BOTTOM_OUTER)
        self.assertProfiles([right, left], panel)
        self.assertEqual("", self.message(panel))

    def test_a_whole_closed_bar_adds_nothing_and_says_to_click_its_tubes(self):
        panel, (bottom, _, _, _), _ = self.target_bottom()
        _, closed = self.make_bar()

        self.select_whole(closed)

        self.assertEqual(bottom, panel.target[0])
        self.assertProfiles([], panel)
        self.assertEqual(f"{closed.Label} is closed: click its tubes to add them.", self.message(panel))


class ExtendCutBarPreselectionTest(ExtendCutBarFixture):
    def test_a_preselected_bar_face_and_tube_open_the_panel_on_the_tubes(self):
        (bottom, right, _, _), bar = self.make_legs()
        for obj, point in ((bar, RIGHT_OUTER), (bottom, BOTTOM_OUTER)):
            Gui.Selection.addSelection(self.doc.Name, obj.Name, face_at(obj, point), point.x, point.y, point.z)

        panel = self.extend_cut_panel()

        obj, faces = panel.target
        self.assertEqual(right, obj)
        self.assertFaceAt(right, faces[0], RIGHT_OUTER)
        self.assertEqual([bottom], panel.profiles)


class NotchOnBarTest(ExtendCutBarFixture):
    def test_a_notch_target_clicked_on_the_bar_is_the_tube_under_the_point(self):
        (bottom, right, _, _), bar = self.make_legs()
        panel = self.notch_panel()

        self.click(bar, RIGHT_OUTER)
        self.assertEqual((right, ()), panel.target)
        self.click(bottom, BOTTOM_OUTER)
        self.assertEqual([bottom], panel.profiles)
        self.assertTrue(panel.accept())

        (notch,) = self.trims("Notch")
        self.assertEqual("Valid", notch.getStatusString())
        self.assertEqual(bottom, notch.TrimmedBody)
        self.assertEqual([(right, ("",))], notch.TrimmingBoundary)


if __name__ == "__main__":
    unittest.main()

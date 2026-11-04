"""Drill Hole command and panel: pick a face and a vertex, live preview, one Undo step, edit by double-click."""

import math
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtWidgets
from test_cutout_flow import END, SIDE, UP, CutoutFixture
from test_drill_hole_geometry import DIAMETER, ONE_HOLE, WALL, DrillHoleFixture
from test_end_miter_geometry import CENTER
from test_extend_cut_preview import keep_auto_preview, wait

from freecad.maxproframe import create_drill_hole_tool, drill_hole
from freecad.maxproframe.create_drill_hole_tool import DrillHoleCommand
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.create_extend_cut_tool import ExtendCutTaskPanel, make_extend_cut_profile
from freecad.maxproframe.create_notch_tool import make_notch_profile
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.ff_tools import get_param_group

# Two preview delays and a recompute in between, with room for a loaded machine.
SETTLE = 2.0

CORNER = (-50, -25, 25)
FAR_CORNER = (350, 25, 25)
BOTTOM_CORNER = (-50, -25, -25)
WARNING = "The reference vertex changed: check the hole."
NO_FACE = "Click a planar face of a profile, a trimmed profile or a cutout."
NO_VERTEX = "Click a vertex of the face."
# Remembered state of the Update automatically check box of the Drill Hole panel.
AUTO_PREVIEW_PARAM = "Drill Hole Auto Preview"


def hole_volume(diameter, depth):
    return math.pi * (diameter / 2) ** 2 * depth


class RecomputeCounter:
    """Stands for a document: counts its recomputes and those started while another one runs."""

    def __init__(self, doc):
        self.doc = doc
        self.calls = 0
        self.nested = 0
        self._running = 0

    def __getattr__(self, name):
        return getattr(self.doc, name)

    def recompute(self, *args):
        self.calls += 1
        if self._running:
            self.nested += 1
        self._running += 1
        try:
            return self.doc.recompute(*args)
        finally:
            self._running -= 1


class DrillHolePanelFixture(CutoutFixture, DrillHoleFixture):
    def setUp(self):
        super().setUp()
        keep_auto_preview(self, SimpleNamespace(auto_preview_param=AUTO_PREVIEW_PARAM))
        self.recorded = []
        base = create_drill_hole_tool.DrillHoleTaskPanel
        recorded = self.recorded

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_drill_hole_tool, "DrillHoleTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)

    def close_dialog(self):
        super().close_dialog()
        for panel in self.recorded:
            panel.clean()

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def run_command(self, *items):
        """Run the command on a selection and return the panel it opens."""
        self.select(*items)
        count = len(self.recorded)
        DrillHoleCommand().Activated()
        self.assertEqual(len(self.recorded), count + 1)
        self.assertTrue(Gui.Control.activeDialog())
        return self.recorded[-1]

    def click(self, obj, sub):
        super().click(obj, sub)
        self.events()

    def new_objects(self, before):
        return [obj for obj in self.doc.Objects if obj.Name not in before]

    def preview(self, before):
        """The one drill hole the panel added to a document that held ``before``."""
        new = self.new_objects(before)
        self.assertEqual(len(new), 1, [obj.Name for obj in new])
        self.assertTrue(hasattr(new[0], "ReferenceVertex"))
        return new[0]

    def vertex_of(self, obj, face):
        """Name of the first vertex of ``obj`` on its face ``face``."""
        return self.vertex_at(obj, obj.Shape.getElement(face).Vertexes[0].Point)

    def set_values(self, panel, along=30.0, across=25.0, **values):
        form = panel.form
        form.spin_offset_along.setValue(along)
        form.spin_offset_across.setValue(across)
        for name, value in values.items():
            getattr(form, f"spin_{name}").setValue(value)

    def set_cut_type(self, panel, cut_type):
        combo = panel.form.combo_cut_type
        combo.setCurrentIndex(combo.findData(cut_type))

    def values(self, obj):
        return (
            obj.ReferenceVertex,
            round(obj.OffsetAlong.Value, 6),
            round(obj.OffsetAcross.Value, 6),
            round(obj.Diameter.Value, 6),
            obj.Count,
            round(obj.Pitch.Value, 6),
            obj.CutType,
            round(obj.ExtrusionLength.Value, 6),
        )

    def existing(self, **values):
        """A drill hole on the top face of a tube, from CORNER, with no Undo step: (body, hole)."""
        body = self.tube()
        obj = make_drill_hole((body, (self.face_towards(body, UP),)), self.vertex_at(body, CORNER))
        obj.OffsetAlong = 30.0
        obj.OffsetAcross = 25.0
        for name, value in values.items():
            setattr(obj, name, value)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.doc.clearUndos()
        return body, obj

    def edit(self, obj):
        """Double-click ``obj``: the panel it opens."""
        count = len(self.recorded)
        Gui.getDocument(self.doc.Name).setEdit(obj, 0)
        self.events()
        self.assertEqual(len(self.recorded), count + 1)
        self.assertTrue(Gui.Control.activeDialog())
        return self.recorded[-1]

    def status(self, panel):
        return panel.form.status_label.text()

    def count_recomputes(self, panel):
        """Count the recomputes the panel starts from now on."""
        counter = RecomputeCounter(panel.doc)
        panel.doc = counter
        return counter

    def hook_execute(self):
        """Hooks run once each, in order, after the next drill hole recomputes.

        Call it before the panel makes a drill hole: FreeCAD keeps the execute it finds on a new object.
        """
        execute = drill_hole.DrillHole.execute
        hooks = []

        def execute_and_hook(proxy, fp):
            result = execute(proxy, fp)
            if hooks:
                hooks.pop(0)(fp)
            return result

        patcher = patch.object(drill_hole.DrillHole, "execute", execute_and_hook)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hooks

    def type_during_next_recompute(self, hooks, panel, value, pump):
        """The next drill hole recompute gets ``value`` typed in the Diameter, then calls ``pump``.

        A recompute pumps Qt events: a keystroke typed meanwhile reaches the panel during the recompute.
        Returns the Diameter that recompute drilled, once it ran.
        """
        typed = []

        def type_value(fp):
            typed.append(round(fp.Diameter.Value, 6))
            panel.form.spin_diameter.setValue(value)
            pump()

        hooks.append(type_value)
        return typed

    def previewed_panel(self, **values):
        """A creation panel on the top face of a tube from CORNER, previewed with ``values``: (body, panel, hole, before)."""
        body = self.tube()
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, **values)
        wait()
        return body, panel, self.preview(before), before


class TestDrillHoleCommand(DrillHolePanelFixture):
    def test_the_command_is_drill_hole_next_to_cutout_hole_and_active_with_a_document(self):
        # S7: named Drill Hole, next to Cutout / Hole, which keeps its name.
        from freecad.maxproframe.InitGui import MaxProFrame

        tools = MaxProFrame.toolbox_maxproframe
        self.assertEqual(tools.index("MaxProFrame_DrillHole"), tools.index("MaxProFrame_AddExtrudeCutout") + 1)
        self.assertIn("MaxProFrame_DrillHole", Gui.listCommands())
        resources = DrillHoleCommand().GetResources()
        self.assertEqual(resources["MenuText"], "Drill Hole")
        self.assertTrue(resources["ToolTip"].startswith("<b>Drill Hole</b>"))
        self.assertEqual(os.path.basename(resources["Pixmap"]), "drill-hole.svg")
        self.assertTrue(os.path.isfile(resources["Pixmap"]))
        body = self.tube()
        path = body.AttachmentSupport[0][0]
        top = self.face_towards(body, UP)
        for selection in ([], [(body, "")], [(path, "")], [(body, "Edge1")], [(body, top)]):
            with self.subTest(selection=[(obj.Name, sub) for obj, sub in selection]):
                self.select(*selection)
                self.assertTrue(DrillHoleCommand().IsActive())


class TestDrillHolePicks(DrillHolePanelFixture):
    def test_a_preselected_face_and_vertex_are_the_reference_and_extra_items_are_explained(self):
        # S1, S2: a planar face of a profile and any vertex of it.
        body = self.tube()
        top, side = self.face_towards(body, UP), self.face_towards(body, SIDE)
        corner = self.vertex_at(body, CORNER)
        far = self.vertex_at(body, FAR_CORNER)
        panel = self.run_command((body, top), (body, corner), (body, side), (body, far))
        form = panel.form
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(panel.vertex, corner)
        self.assertEqual(form.windowTitle(), "Drill Hole")
        self.assertEqual(form.face_label.text(), f"{body.Label} ({body.Name}) {top}")
        self.assertEqual(form.vertex_label.text(), corner)
        self.assertEqual(
            self.message(panel).split("\n"),
            [
                f"{body.Label}: {side} is not used, a drill hole takes one face",
                f"{body.Label}: {far} is not used, a drill hole takes one vertex",
            ],
        )

    def test_clicks_pick_the_face_then_its_vertex_and_explain_refused_picks_without_changing_the_document(self):
        # S2, S8: a face first, then a vertex of it; anything else is explained in the panel.
        body = self.tube()
        pipe = self.tube()
        pipe.Family = "Pipe"
        self.doc.recompute()
        curved = next(
            f"Face{index}"
            for index, face in enumerate(pipe.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        path = body.AttachmentSupport[0][0]
        top, end = self.face_towards(body, UP), self.face_towards(body, END)
        corner, bottom = self.vertex_at(body, CORNER), self.vertex_at(body, BOTTOM_CORNER)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.face_label.text(), NO_FACE)
        self.assertEqual(form.vertex_label.text(), NO_VERTEX)
        refused = (
            ((body, corner), "Click a face first, then one of its vertices."),
            ((body, end), f"{body.Label}: {end} is an end face (wall thickness)"),
            ((pipe, curved), f"{pipe.Label}: {curved} is not planar"),
            ((path, "Edge1"), f"{path.Label} is not a profile"),
            ((body, "Edge1"), f"{body.Label}: Edge1 is not a face"),
        )
        for (obj, sub), message in refused:
            with self.subTest(pick=(obj.Name, sub)):
                self.click(obj, sub)
                self.assertIsNone(panel.face)
                self.assertEqual(self.message(panel), message)
        self.click(body, top)
        self.assertEqual(panel.face, (body, top))
        self.assertIsNone(panel.vertex)
        self.assertEqual(self.message(panel), "")
        self.click(body, bottom)
        self.assertIsNone(panel.vertex)
        self.assertEqual(self.message(panel), f"{body.Label}: {bottom} is not a vertex of {top}")
        self.assertEqual(form.vertex_label.text(), NO_VERTEX)
        # Nothing is created until a face and a vertex are picked.
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.click(body, corner)
        self.assertEqual(panel.vertex, corner)
        self.assertEqual(form.vertex_label.text(), corner)
        self.assertEqual(self.message(panel), "")

    def test_a_new_face_keeps_the_vertex_only_when_the_vertex_is_on_it(self):
        body = self.tube()
        top, side = self.face_towards(body, UP), self.face_towards(body, SIDE)
        bottom = self.face_towards(body, App.Vector(0, 0, -1))
        corner = self.vertex_at(body, CORNER)
        before = self.names()
        panel = self.run_command((body, top), (body, corner))
        self.preview(before)
        self.click(body, side)
        self.assertEqual((panel.face, panel.vertex), ((body, side), corner))
        self.preview(before)
        self.click(body, bottom)
        self.assertEqual((panel.face, panel.vertex), ((body, bottom), None))
        self.assertEqual(panel.form.vertex_label.text(), NO_VERTEX)
        # Without a vertex there is nothing to preview.
        self.assertEqual(self.names(), before)

    def test_clicks_on_the_preview_pick_the_face_and_vertex_of_its_base(self):
        # S2: any vertex of the face, also clicked on the preview that hides the profile.
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel)
        obj = self.preview(before)
        self.click(obj, self.face_towards(obj, UP))
        self.assertEqual(panel.face, (body, top))
        self.click(obj, self.vertex_at(obj, FAR_CORNER))
        self.assertEqual(panel.vertex, self.vertex_at(body, FAR_CORNER))
        self.assertEqual(self.message(panel), "")
        self.assertIs(self.preview(before), obj)
        self.assertEqual(obj.ReferenceVertex, self.vertex_at(body, FAR_CORNER))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 320, 0, 24))
        self.assertFalse(self.empty(obj.Shape, -20, 0, 24))


class TestDrillHolePreview(DrillHolePanelFixture):
    def test_the_holes_are_previewed_live_while_the_values_change(self):
        # S3, S6: offsets, diameter, linear pattern and the three depths, previewed as they change.
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top), (body, self.vertex_at(body, CORNER)))
        form = panel.form
        obj = self.preview(before)
        self.assertEqual(obj.Label, f"{body.Label}_Dh")
        self.assertEqual(form.combo_cut_type.currentData(), "One wall")
        self.assertEqual(
            [form.combo_cut_type.itemText(i) for i in range(form.combo_cut_type.count())],
            ["Through All", "Distance", "One wall"],
        )
        self.assertAlmostEqual(form.spin_diameter.value(), DIAMETER, places=6)
        self.assertEqual(form.spin_count.value(), 1)
        self.assertFalse(form.spin_pitch.isEnabled())
        self.assertFalse(form.spin_depth.isEnabled())
        # The depth starts at the wall under the face.
        self.assertAlmostEqual(form.spin_depth.value(), WALL, places=6)
        # Value changes are previewed once typing pauses (S9).
        self.set_values(panel)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        form.spin_count.setValue(3)
        self.assertTrue(form.spin_pitch.isEnabled())
        form.spin_pitch.setValue(40.0)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 60, 0, 24))
        form.spin_diameter.setValue(6.0)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * hole_volume(6.0, WALL), places=3)
        self.set_cut_type(panel, "Through All")
        self.assertFalse(form.spin_depth.isEnabled())
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 6 * hole_volume(6.0, WALL), places=3)
        self.set_cut_type(panel, "Distance")
        self.assertTrue(form.spin_depth.isEnabled())
        form.spin_depth.setValue(1.0)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * hole_volume(6.0, 1.0), places=3)
        form.spin_count.setValue(1)
        self.assertFalse(form.spin_pitch.isEnabled())
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(6.0, 1.0), places=3)
        self.assertEqual(self.preview(before), obj)

    def test_a_diameter_typed_during_a_recompute_is_previewed_in_the_end(self):
        # S9, L12: typing "12" over "10" goes through 1; the "2" arrives while the 1 mm preview recomputes.
        hooks = self.hook_execute()
        body, panel, obj, before = self.previewed_panel()
        typed = self.type_during_next_recompute(hooks, panel, 12.0, self.events)
        panel.form.spin_diameter.setValue(1.0)
        # The value typed during the recompute restarts the preview delay: wait for both previews.
        wait(SETTLE)
        self.assertEqual(typed, [1.0])
        self.assertAlmostEqual(obj.Diameter.Value, 12.0, places=6)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(12.0, WALL), places=3)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(self.status(panel), "Preview updated")

    def test_no_recompute_starts_while_one_runs_and_one_more_follows_it(self):
        # S9: a change, and the preview timer, arriving during a recompute wait for it to end.
        hooks = self.hook_execute()
        body, panel, obj, before = self.previewed_panel()
        counter = self.count_recomputes(panel)
        typed = self.type_during_next_recompute(hooks, panel, 12.0, wait)
        panel.form.spin_diameter.setValue(1.0)
        # The value typed during the recompute restarts the preview delay: wait for both previews.
        wait(SETTLE)
        self.assertEqual(typed, [1.0])
        self.assertEqual(counter.nested, 0)
        self.assertEqual(counter.calls, 2)
        self.assertAlmostEqual(obj.Diameter.Value, 12.0, places=6)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(12.0, WALL), places=3)

    def press_during_next_recompute(self, hooks, panel, button, value=None):
        """The next drill hole recompute gets ``value`` typed in the Diameter, then OK or Cancel pressed.

        Returns what the button returned, once that recompute ran.
        """
        returned = []

        def press(fp):
            if value is not None:
                panel.form.spin_diameter.setValue(value)
            returned.append(getattr(panel, button)())

        hooks.append(press)
        return returned

    def test_ok_pressed_during_a_recompute_creates_the_hole_with_the_last_values_once_it_ends(self):
        hooks = self.hook_execute()
        body, panel, obj, before = self.previewed_panel()
        counter = self.count_recomputes(panel)
        returned = self.press_during_next_recompute(hooks, panel, "accept", 14.0)
        panel.form.spin_diameter.setValue(12.0)
        wait(SETTLE)
        # The dialog stays open until the recompute ends, then OK runs and closes it.
        self.assertEqual(returned, [False])
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(counter.nested, 0)
        self.assertEqual(self.new_objects(before), [obj])
        self.assertAlmostEqual(obj.Diameter.Value, 14.0, places=6)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(14.0, WALL), places=3)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])

    def test_cancel_pressed_during_a_recompute_leaves_the_document_unchanged_once_it_ends(self):
        hooks = self.hook_execute()
        body, panel, obj, before = self.previewed_panel()
        counter = self.count_recomputes(panel)
        returned = self.press_during_next_recompute(hooks, panel, "reject")
        panel.form.spin_diameter.setValue(12.0)
        wait(SETTLE)
        self.assertEqual(returned, [False])
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(counter.nested, 0)
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(body.ViewObject.Visibility)

    def test_quick_changes_are_previewed_once_after_the_delay_and_cancel_stops_a_pending_one(self):
        # S9: debounced.
        body, panel, obj, before = self.previewed_panel()
        self.assertEqual(self.status(panel), "Preview updated")
        counter = self.count_recomputes(panel)
        for value in (1.0, 12.0, 8.0):
            panel.form.spin_diameter.setValue(value)
            self.events()
        self.assertEqual(counter.calls, 0)
        self.assertEqual(self.status(panel), "Pending changes")
        wait()
        self.assertEqual(counter.calls, 1)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(8.0, WALL), places=3)
        self.assertEqual(self.status(panel), "Preview updated")
        panel.form.spin_diameter.setValue(6.0)
        self.assertTrue(panel.reject())
        wait()
        self.assertEqual(counter.calls, 1)
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_update_automatically_is_checked_by_default_and_remembered_on_its_own(self):
        # S9: the Extend / Cut check box, remembered under its own name.
        keep_auto_preview(self, ExtendCutTaskPanel)
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.assertTrue(form.cb_auto_update.isChecked())
        self.assertEqual(form.cb_auto_update.text(), "Update automatically")
        self.assertEqual(form.groupBox_preview.title(), "Preview")
        form.cb_auto_update.setChecked(False)
        counter = self.count_recomputes(panel)
        form.spin_diameter.setValue(6.0)
        wait()
        self.assertEqual(counter.calls, 0)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertFalse(get_param_group().GetBool(AUTO_PREVIEW_PARAM, True))
        self.assertNotIn(ExtendCutTaskPanel.auto_preview_param, get_param_group(writable=True).GetBools())
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.assertEqual(self.names(), before)
        # Checking it again previews at once.
        panel.form.cb_auto_update.setChecked(True)
        self.assertAlmostEqual(self.preview(before).Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertEqual(self.status(panel), "Preview updated")
        self.assertTrue(get_param_group().GetBool(AUTO_PREVIEW_PARAM, False))

    def test_with_update_automatically_unchecked_ok_creates_the_hole_with_the_panel_values_in_one_undo_step(self):
        # S9: nothing is recomputed until OK, which keeps the current values.
        keep_auto_preview(self, SimpleNamespace(auto_preview_param=AUTO_PREVIEW_PARAM), False)
        body = self.tube()
        top, corner = self.face_towards(body, UP), self.vertex_at(body, CORNER)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, top), (body, corner))
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.status(panel), "Pending changes")
        counter = self.count_recomputes(panel)
        self.set_values(panel, diameter=12.0, count=2, pitch=40.0)
        wait()
        self.assertEqual(counter.calls, 0)
        self.assertEqual(self.names(), before)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual(self.values(obj)[:7], (corner, 30.0, 25.0, 12.0, 2, 40.0, "One wall"))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * hole_volume(12.0, WALL), places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)


class TestDrillHoleCreation(DrillHolePanelFixture):
    def test_ok_creates_the_drill_hole_in_the_container_of_its_base_in_one_undo_step(self):
        # S1, S3, S6: one object, in the profile's container, with the panel values, one Undo step.
        body = self.tube()
        body.Label = "Profile_TC50x50x2_000"
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        part.Placement.Base = App.Vector(0, 500, 0)
        self.doc.recompute()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, CORNER)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, top), (body, corner))
        self.set_values(panel, count=2, pitch=40.0, diameter=8.0)
        self.set_cut_type(panel, "Through All")
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual(obj.Name, f"{body.Name}_Dh")
        self.assertEqual(obj.Label, "Profile_TC50x50x2_000_Dh")
        self.assertEqual(obj.getParentGeoFeatureGroup(), part)
        self.assertEqual(obj.baseObject, (body, [top]))
        self.assertEqual(self.values(obj)[:7], (corner, 30.0, 25.0, 8.0, 2, 40.0, "Through All"))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 4 * hole_volume(8.0, WALL), places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)

    def test_a_distance_depth_is_kept_as_the_extrusion_length(self):
        body = self.tube()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel)
        self.set_cut_type(panel, "Distance")
        panel.form.spin_depth.setValue(1.5)
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual(obj.CutType, "Distance")
        self.assertAlmostEqual(obj.ExtrusionLength.Value, 1.5, places=6)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(DIAMETER, 1.5), places=3)

    def test_ok_without_a_face_or_a_vertex_keeps_the_panel_open_and_creates_nothing(self):
        body = self.tube()
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command()
        self.assertFalse(panel.accept())
        self.assertEqual(self.message(panel), "Select a planar face of a profile, a trimmed profile or a cutout.")
        self.click(body, self.face_towards(body, UP))
        self.assertFalse(panel.accept())
        self.assertEqual(self.message(panel), "Select a vertex of the face.")
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_leaves_the_document_unchanged_and_stops_listening(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, top), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, diameter=6.0)
        self.preview(before)
        self.assertFalse(body.ViewObject.Visibility)
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(body.ViewObject.Visibility)
        self.click(body, self.face_towards(body, SIDE))
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(self.names(), before)

    def test_a_hole_on_an_extend_cut_trim_a_notch_or_an_end_miter_is_created_and_valid(self):
        # L10 follow-up: the base can be a trim of the profile.
        for joint in ("Extend / Cut", "Notch", "End Miter"):
            with self.subTest(joint=joint):
                self.close_dialog()
                body = self.tube()
                if joint == "End Miter":
                    # A corner at the end of the tube, at x = 300.
                    target = self.make_profile(self.make_sketch(((300, 0, 0), (300, 200, 0))), "Edge1", **CENTER)
                else:
                    target = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
                if joint == "Notch":
                    trim = make_notch_profile(body, target)
                elif joint == "End Miter":
                    trim = make_end_miter_profile(body, [target])
                else:
                    trim = make_extend_cut_profile(body, (target, (self.face_towards(target, -END),)))
                self.doc.recompute()
                self.assertEqual(trim.getStatusString(), "Valid")
                top = self.face_towards(trim, UP)
                vertex = self.vertex_of(trim, top)
                self.doc.clearUndos()
                before = self.names()
                panel = self.run_command((trim, top), (trim, vertex))
                self.assertEqual(self.message(panel), "")
                self.set_values(panel)
                self.assertTrue(panel.accept())
                obj = self.preview(before)
                self.assertEqual(obj.Label, f"{trim.Label}_Dh")
                self.assertEqual(obj.baseObject, (trim, [top]))
                self.assertEqual(obj.ReferenceVertex, vertex)
                self.assertEqual(obj.getStatusString(), "Valid")
                self.assertEqual(obj.ReferenceWarning, "")
                self.assertAlmostEqual(obj.Shape.Volume, trim.Shape.Volume - ONE_HOLE, places=3)
                self.assertEqual(self.doc.UndoCount, 1)


class TestDrillHoleEdit(DrillHolePanelFixture):
    def test_double_click_shows_the_stored_values_and_ok_keeps_the_changes_in_one_undo_step(self):
        # S6: edit by double-click.
        body, obj = self.existing(Diameter=8.0, Count=2, Pitch=60.0)
        top = self.face_towards(body, UP)
        stored = self.values(obj)
        panel = self.edit(obj)
        form = panel.form
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(panel.vertex, self.vertex_at(body, CORNER))
        self.assertEqual(form.face_label.text(), f"{body.Label} ({body.Name}) {top}")
        self.assertAlmostEqual(form.spin_offset_along.value(), 30.0, places=6)
        self.assertAlmostEqual(form.spin_offset_across.value(), 25.0, places=6)
        self.assertAlmostEqual(form.spin_diameter.value(), 8.0, places=6)
        self.assertEqual(form.spin_count.value(), 2)
        self.assertTrue(form.spin_pitch.isEnabled())
        self.assertAlmostEqual(form.spin_pitch.value(), 60.0, places=6)
        self.assertEqual(form.combo_cut_type.currentData(), "One wall")
        self.assertEqual(form.warning_label.text(), "")
        self.assertTrue(form.warning_label.isHidden())
        before = self.names()
        # A click on the edited hole picks the vertex of its base.
        self.click(obj, self.vertex_at(obj, FAR_CORNER))
        form.spin_diameter.setValue(DIAMETER)
        form.spin_count.setValue(1)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(panel.accept())
        self.assertEqual(self.names(), before)
        self.assertEqual(obj.ReferenceVertex, self.vertex_at(body, FAR_CORNER))
        self.assertEqual((obj.Diameter.Value, obj.Count), (DIAMETER, 1))
        self.assertTrue(self.empty(obj.Shape, 320, 0, 24))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.values(obj), stored)

    def test_stored_lengths_finer_than_the_fields_are_kept_unless_that_field_is_changed(self):
        # R3-001: the fields show two decimals; OK must not write their rounded values back.
        fine = dict(OffsetAlong=30.125, OffsetAcross=24.875, Diameter=4.7625, Pitch=50.0625)
        body, obj = self.existing(Count=2, CutType="Distance", ExtrusionLength=1.0625, **fine)
        stored = self.values(obj)
        panel = self.edit(obj)
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.values(obj), stored)
        self.assertEqual(self.doc.UndoCount, 0)
        panel = self.edit(obj)
        panel.form.spin_count.setValue(3)
        wait()
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(obj.Count, 3)
        self.assertEqual(self.values(obj)[1:4] + self.values(obj)[5:], stored[1:4] + stored[5:])
        self.assertEqual(self.doc.UndoCount, 1)

    def test_ok_without_changes_leaves_no_undo_step(self):
        body, obj = self.existing()
        stored = self.values(obj)
        for change_back in (False, True):
            with self.subTest(change_back=change_back):
                panel = self.edit(obj)
                if change_back:
                    # Previewed, then set back: nothing changed in the end.
                    panel.form.spin_diameter.setValue(6.0)
                    wait()
                    self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(6.0, WALL), places=3)
                    panel.form.spin_diameter.setValue(DIAMETER)
                self.assertTrue(panel.accept())
                self.events()
                self.assertEqual(self.values(obj), stored)
                self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
                self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_restores_the_stored_values_without_an_undo_step(self):
        body, obj = self.existing(CutType="Distance", ExtrusionLength=1.5)
        stored = self.values(obj)
        panel = self.edit(obj)
        form = panel.form
        self.assertEqual(form.combo_cut_type.currentData(), "Distance")
        self.assertAlmostEqual(form.spin_depth.value(), 1.5, places=6)
        form.spin_count.setValue(3)
        self.set_cut_type(panel, "Through All")
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 6 * ONE_HOLE, places=3)
        self.assertTrue(panel.reject())
        self.assertEqual(self.values(obj), stored)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(DIAMETER, 1.5), places=3)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_the_panel_shows_the_reference_warning(self):
        # S4 surfaced in the panel: the corner is gone, the hole kept its place.
        body, obj = self.existing(OffsetAlong=230.0)
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assertEqual(obj.ReferenceWarning, WARNING)
        panel = self.edit(obj)
        self.assertEqual(panel.form.warning_label.text(), WARNING)
        self.assertFalse(panel.form.warning_label.isHidden())
        self.assertTrue(panel.reject())


class TestDrillHoleSpanish(DrillHolePanelFixture):
    def test_the_command_the_panel_and_its_messages_are_spanish(self):
        # S7: Drill Hole is Agujero in Spanish; the panel, its messages and the warning follow.
        body = self.tube()
        top = self.face_towards(body, UP)
        corner, bottom = self.vertex_at(body, CORNER), self.vertex_at(body, BOTTOM_CORNER)
        use_language(self, "Spanish", "es_ES")
        resources = DrillHoleCommand().GetResources()
        self.assertEqual(App.Qt.translate("MaxProFrame_DrillHole", resources["MenuText"]), "Agujero")
        self.assertTrue(
            App.Qt.translate("MaxProFrame_DrillHole", resources["ToolTip"]).startswith(
                "<b>Agujero</b><br><br>Hacé clic en una cara plana de un perfil, un perfil recortado o un calado"
            )
        )
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.windowTitle(), "Agujero")
        self.assertEqual(
            [box.title() for box in (form.groupBox_reference, form.groupBox_holes, form.groupBox_preview)],
            ["Referencia", "Agujeros", "Previsualización"],
        )
        self.assertEqual(
            [
                getattr(form, f"label_{name}").text()
                for name in ("offset_along", "offset_across", "diameter", "count", "pitch", "cut_type", "depth")
            ],
            [
                "Desplazamiento longitudinal",
                "Desplazamiento transversal",
                "Diámetro",
                "Cantidad",
                "Paso",
                "Tipo de corte",
                "Profundidad",
            ],
        )
        self.assertEqual(form.combo_cut_type.currentText(), "Una pared")
        self.assertEqual(form.cb_auto_update.text(), "Actualizar automáticamente")
        self.assertEqual(
            form.hint_label.text(),
            "Hacé clic en una cara y luego en uno de sus vértices: los agujeros se ubican a partir de ese vértice. "
            "Hacé clic de nuevo para cambiarlos.",
        )
        self.assertEqual(
            form.face_label.text(), "Hacé clic en una cara plana de un perfil, un perfil recortado o un calado."
        )
        self.assertEqual(form.vertex_label.text(), "Hacé clic en un vértice de la cara.")
        self.assertEqual(self.status(panel), "Sin previsualización")
        self.click(body, corner)
        self.assertEqual(self.message(panel), "Hacé clic primero en una cara y luego en uno de sus vértices.")
        self.click(body, top)
        self.assertFalse(panel.accept())
        self.assertEqual(self.message(panel), "Seleccioná un vértice de la cara.")
        self.click(body, bottom)
        self.assertEqual(self.message(panel), f"{body.Label}: {bottom} no es un vértice de {top}")
        before = self.names()
        self.click(body, corner)
        wait()
        obj = self.preview(before)
        self.assertEqual(self.status(panel), "Previsualización actualizada")
        self.assertEqual(obj.getDocumentationOfProperty("Count"), "Cantidad de agujeros")
        self.assertTrue(panel.accept())
        # S4: the warning of a hole whose corner is gone.
        obj.OffsetAlong = 230.0
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assertEqual(obj.ReferenceWarning, "La referencia cambió, revisá el agujero.")


if __name__ == "__main__":
    unittest.main()

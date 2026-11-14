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
from PySide import QtCore, QtGui, QtWidgets
from test_cutout_flow import END, SIDE, UP, CutoutFixture
from test_drill_hole_geometry import DIAMETER, ONE_HOLE, WALL, DrillHoleFixture
from test_end_miter_geometry import CENTER
from test_extend_cut_preview import keep_auto_preview, wait

from freecad.maxproframe import create_drill_hole_tool, drill_hole
from freecad.maxproframe.create_drill_hole_tool import PATTERN_ROWS, DrillHoleCommand
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
NO_FACE = "Click a planar face of a profile, a trimmed profile, a cutout or a folded bar."
NO_VERTEX = "Click a vertex of the face."
# Remembered state of the Update automatically check box of the Drill Hole panel.
AUTO_PREVIEW_PARAM = "Drill Hole Auto Preview"
# Diameter of the last drill hole confirmed by OK or Apply and continue, for the next new one (S1).
DIAMETER_PARAM = "Drill Hole Diameter"


def keep_remembered_diameter(test):
    """Start ``test`` with no remembered diameter and put back the stored one after it."""
    param = get_param_group(writable=True)
    stored = DIAMETER_PARAM in param.GetFloats()
    previous = param.GetFloat(DIAMETER_PARAM, 0.0)

    def restore():
        if stored:
            param.SetFloat(DIAMETER_PARAM, previous)
        else:
            param.RemFloat(DIAMETER_PARAM)

    test.addCleanup(restore)
    param.RemFloat(DIAMETER_PARAM)


def remembered_diameter():
    """The remembered diameter of a new drill hole, or None when there is none."""
    param = get_param_group()
    return param.GetFloat(DIAMETER_PARAM, 0.0) if DIAMETER_PARAM in param.GetFloats() else None


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
        keep_remembered_diameter(self)
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

    def click_at(self, obj, sub, point):
        """A click on ``sub`` of ``obj`` at the global ``point``, as the 3D view reports it."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, *point)
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

    def set_pattern(self, panel, hole_at_point=True, **sides):
        """Check the Pattern group and set ``sides`` (along_forward=(count, pitch), ...) and Hole at the point."""
        form = panel.form
        form.groupBox_pattern.setChecked(True)
        form.cb_hole_at_point.setChecked(hole_at_point)
        for side, (count, pitch) in sides.items():
            getattr(form, f"spin_{side}_count").setValue(count)
            getattr(form, f"spin_{side}_pitch").setValue(pitch)

    def set_cut_type(self, panel, cut_type):
        combo = panel.form.combo_cut_type
        combo.setCurrentIndex(combo.findData(cut_type))

    def values(self, obj):
        return (
            obj.ReferenceVertex,
            round(obj.OffsetAlong.Value, 6),
            round(obj.OffsetAcross.Value, 6),
            round(obj.Diameter.Value, 6),
            obj.AlongForwardCount,
            round(obj.AlongForwardPitch.Value, 6),
            obj.CutType,
            round(obj.ExtrusionLength.Value, 6),
            obj.HoleAtPoint,
            obj.AlongBackwardCount,
            round(obj.AlongBackwardPitch.Value, 6),
            obj.AcrossBackwardCount,
            round(obj.AcrossBackwardPitch.Value, 6),
            obj.AcrossForwardCount,
            round(obj.AcrossForwardPitch.Value, 6),
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
        self.assertEqual(
            resources["ToolTip"],
            "<b>Drill Hole</b><br><br>Click a planar face of a profile, a trimmed profile, a cutout or a folded bar, "
            "then one of its nine circles to measure from: a corner, the middle of an edge or the center. Round holes "
            "are drilled at the offsets from that point: one, or a pattern on both sides of it along and across the "
            "profile, with a diameter and a depth.",
        )
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


class TestDrillHoleCornerPicks(DrillHolePanelFixture):
    """A click on a face near a corner takes that corner: the vertex itself need not be hit."""

    def test_a_click_on_a_face_takes_the_face_and_its_corner_nearest_to_the_click(self):
        body = self.tube()
        top, side = self.face_towards(body, UP), self.face_towards(body, SIDE)
        corner, far = self.vertex_at(body, CORNER), self.vertex_at(body, FAR_CORNER)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command()
        self.assertEqual(
            panel.form.hint_label.text(),
            "Click a circle on the face to place the holes from it: a corner, the middle of an edge or the center. "
            "A click on the face takes the nearest circle.",
        )
        self.click_at(body, top, (-40, -18, 25))
        self.assertEqual((panel.face, panel.vertex), ((body, top), corner))
        self.assertEqual(panel.form.vertex_label.text(), corner)
        self.assertEqual(self.message(panel), "")
        wait()
        obj = self.preview(before)
        self.assertEqual(obj.ReferenceVertex, corner)
        # Another click on the same face moves the corner.
        self.click_at(body, top, (330, 15, 25))
        self.assertEqual((panel.face, panel.vertex), ((body, top), far))
        wait()
        self.assertEqual(obj.ReferenceVertex, far)
        # A click on another face takes its own nearest corner.
        side_face = body.Shape.getElement(side)
        nearest = min(side_face.Vertexes, key=lambda v: v.Point.distanceToPoint(App.Vector(-49, -25, -24)))
        self.click_at(body, side, (-49, -25, -24))
        self.assertEqual((panel.face, panel.vertex), ((body, side), self.vertex_at(body, nearest.Point)))
        self.assertEqual(self.message(panel), "")
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_a_click_on_a_vertex_and_a_click_without_a_point_keep_their_meaning(self):
        # A click on the vertex itself still takes it; a selection without a point (tree, script) only takes the face.
        body = self.tube()
        top = self.face_towards(body, UP)
        corner, far = self.vertex_at(body, CORNER), self.vertex_at(body, FAR_CORNER)
        panel = self.run_command()
        self.click(body, top)
        self.assertEqual((panel.face, panel.vertex), ((body, top), None))
        self.click_at(body, far, FAR_CORNER)
        self.assertEqual(panel.vertex, far)
        self.click(body, top)
        self.assertEqual((panel.face, panel.vertex), ((body, top), far))
        self.click_at(body, corner, CORNER)
        self.assertEqual(panel.vertex, corner)

    def test_the_click_point_is_global_for_a_profile_in_a_moved_container(self):
        body = self.tube()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        part.Placement.Base = App.Vector(0, 500, 0)
        self.doc.recompute()
        top = self.face_towards(body, UP)
        panel = self.run_command()
        # Near FAR_CORNER once the container moves it 500 mm along y; near CORNER in the profile's own coordinates.
        self.click_at(body, top, (330, 515, 25))
        self.assertEqual((panel.face, panel.vertex), ((body, top), self.vertex_at(body, FAR_CORNER)))
        marker = panel.corner_marker()
        self.assertTrue(marker.isEqual(App.Vector(350, 525, 25), 1e-6), marker)

    def test_a_marker_shows_the_corner_until_the_panel_closes(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        bottom = self.face_towards(body, App.Vector(0, 0, -1))
        panel = self.run_command()
        self.assertIsNone(panel.corner_marker())
        self.click(body, top)
        self.assertIsNone(panel.corner_marker())
        self.click_at(body, top, (-40, -18, 25))
        self.assertTrue(panel.corner_marker().isEqual(App.Vector(*CORNER), 1e-6))
        self.click_at(body, top, (330, 15, 25))
        self.assertTrue(panel.corner_marker().isEqual(App.Vector(*FAR_CORNER), 1e-6))
        # A face the corner is not on drops the corner and its marker.
        self.click(body, bottom)
        self.assertIsNone(panel.vertex)
        self.assertIsNone(panel.corner_marker())
        self.click_at(body, bottom, (-40, -18, -25))
        self.assertTrue(panel.corner_marker().isEqual(App.Vector(*BOTTOM_CORNER), 1e-6))
        self.assertTrue(panel.reject())
        self.assertIsNone(panel.corner_marker())

    def test_the_corners_of_the_picked_face_are_clickable_markers(self):
        body = self.tube()
        top, side = self.face_towards(body, UP), self.face_towards(body, SIDE)
        top_face = body.Shape.getElement(top)
        corners = [self.vertex_at(body, v.Point) for v in top_face.Vertexes]
        far = self.vertex_at(body, FAR_CORNER)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command()
        self.assertEqual(panel.reference_markers(), [])
        self.click(body, top)
        # The corners come first; the edge middles (TestDrillHoleMidpoints) follow them.
        markers = [(name, point) for name, point in panel.reference_markers() if name.startswith("Vertex")]
        self.assertEqual([name for name, _ in markers], corners)
        for (name, point), vertex in zip(markers, top_face.Vertexes):
            self.assertTrue(point.isEqual(vertex.Point, 1e-6), (name, point))
        # A marker picks its corner, as a click on the vertex does.
        self.assertTrue(panel.pick_marker(far))
        self.assertEqual((panel.face, panel.vertex), ((body, top), far))
        self.assertEqual(panel.form.vertex_label.text(), far)
        self.assertTrue(panel.corner_marker().isEqual(App.Vector(*FAR_CORNER), 1e-6))
        wait()
        obj = self.preview(before)
        self.assertEqual(obj.ReferenceVertex, far)
        # A vertex off the face is no marker: nothing changes.
        off_face = next(self.vertex_at(body, v.Point) for v in body.Shape.getElement(side).Vertexes if v.Point.z < 0)
        self.assertFalse(panel.pick_marker(off_face))
        self.assertEqual(panel.vertex, far)
        self.assertTrue(panel.reject())
        self.assertEqual(panel.reference_markers(), [])
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_markers_follow_a_profile_in_a_moved_container(self):
        body = self.tube()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        part.Placement.Base = App.Vector(0, 500, 0)
        self.doc.recompute()
        top = self.face_towards(body, UP)
        panel = self.run_command()
        self.click(body, top)
        points = dict(panel.reference_markers())
        self.assertTrue(points[self.vertex_at(body, FAR_CORNER)].isEqual(App.Vector(350, 525, 25), 1e-6))
        self.assertTrue(panel.reject())

    def test_a_left_click_on_a_marker_picks_it_and_the_view_does_not_select_under_it(self):
        from pivy import coin

        body = self.tube()
        top = self.face_towards(body, UP)
        corner, far = self.vertex_at(body, CORNER), self.vertex_at(body, FAR_CORNER)
        panel = self.run_command()
        self.click_at(body, top, (-40, -18, 25))
        self.assertEqual(panel.vertex, corner)
        # The screen is the xy plane of the model, in pixels.
        panel._viewport_point = lambda point: (point.x, point.y)

        def press(x, y, state=coin.SoMouseButtonEvent.DOWN, button=coin.SoMouseButtonEvent.BUTTON1):
            event = coin.SoMouseButtonEvent()
            event.setButton(button)
            event.setState(state)
            event.setPosition(coin.SbVec2s(x, y))
            handled = []
            panel._on_mouse_button(SimpleNamespace(getEvent=lambda: event, setHandled=lambda: handled.append(1)))
            self.events()
            return bool(handled)

        # Off every marker: the view goes on as usual.
        self.assertFalse(press(50, 10))
        self.assertFalse(press(50, 10, coin.SoMouseButtonEvent.UP))
        self.assertEqual(panel.vertex, corner)
        # Another button near a marker: ignored.
        self.assertFalse(press(345, 21, button=coin.SoMouseButtonEvent.BUTTON3))
        self.assertEqual(panel.vertex, corner)
        # Within the hit radius of the far corner: it is picked, press and release are kept from the view.
        self.assertTrue(press(345, 21))
        self.assertEqual(panel.vertex, far)
        self.assertTrue(press(345, 21, coin.SoMouseButtonEvent.UP))
        self.assertFalse(press(345, 21, coin.SoMouseButtonEvent.UP))
        # The nearest marker wins.
        self.assertTrue(press(-48, -24))
        self.assertEqual(panel.vertex, corner)
        self.assertTrue(panel.reject())
        # Closed: clicks go to the view.
        self.assertFalse(press(345, 21))
        self.assertEqual(panel.vertex, corner)

    def test_marker_at_takes_the_nearest_marker_within_the_radius(self):
        markers = [("Vertex1", App.Vector(0, 0, 0)), ("Vertex2", App.Vector(30, 0, 0))]
        project = lambda point: (point.x, point.y)  # noqa: E731
        self.assertEqual(create_drill_hole_tool.marker_at(markers, (4, 3), project), markers[0])
        self.assertEqual(create_drill_hole_tool.marker_at(markers, (22, 0), project), markers[1])
        self.assertEqual(create_drill_hole_tool.marker_at(markers, (10, 0), project), markers[0])
        self.assertIsNone(create_drill_hole_tool.marker_at(markers, (15, 0), project))
        self.assertIsNone(create_drill_hole_tool.marker_at([], (0, 0), project))

    def test_there_is_no_next_corner_button(self):
        # S6: the circles replace Next corner.
        body = self.tube()
        panel = self.run_command()
        self.click(body, self.face_towards(body, UP))
        self.assertFalse(hasattr(panel.form, "button_next_corner"))
        self.assertFalse(hasattr(panel, "_next_corner"))
        buttons = [button.text() for button in panel.form.findChildren(QtWidgets.QPushButton)]
        self.assertNotIn("Next corner", buttons)
        self.assertTrue(panel.reject())


# Ends of the edges of the top face of the tube, and the middle of each one with its kind.
LONG_NEAR = ((-50, -25, 25), (350, -25, 25))
LONG_FAR = ((-50, 25, 25), (350, 25, 25))
SHORT_START = ((-50, -25, 25), (-50, 25, 25))
SHORT_END = ((350, -25, 25), (350, 25, 25))
TOP_MIDDLES = {
    LONG_NEAR: ((150, -25, 25), "along"),
    LONG_FAR: ((150, 25, 25), "along"),
    SHORT_START: ((-50, 0, 25), "across"),
    SHORT_END: ((350, 0, 25), "across"),
}


class MidpointFixture(DrillHolePanelFixture):
    def edge_at(self, obj, ends):
        """Name of the edge of ``obj`` between the two points ``ends``."""
        wanted = [App.Vector(*point) for point in ends]
        for index, edge in enumerate(obj.Shape.Edges, start=1):
            points = [vertex.Point for vertex in edge.Vertexes]
            if len(points) == 2 and all(any(p.isEqual(w, 1e-6) for p in points) for w in wanted):
                return f"Edge{index}"
        self.fail(f"no edge between {ends}")

    def centers(self, panel):
        return (panel.center_along, panel.center_across)

    def marker_at_point(self, panel, point):
        """Name of the one marker of ``panel`` at the global ``point``."""
        names = [name for name, at in panel.reference_markers() if at.isEqual(App.Vector(*point), 1e-6)]
        self.assertEqual(len(names), 1, (point, panel.reference_markers()))
        return names[0]

    def ends(self, obj, ends):
        """Names of the vertices of ``obj`` at the two points ``ends``."""
        return {self.vertex_at(obj, point) for point in ends}

    def vertex_point(self, obj, name):
        point = obj.Shape.getElement(name).Point
        return (point.x, point.y, point.z)

    def assert_points(self, points, expected):
        self.assertEqual(len(points), len(expected), points)
        for point in expected:
            self.assertTrue(any(p.isEqual(App.Vector(*point), 1e-6) for p in points), (point, points))


class TestDrillHoleMidpoints(MidpointFixture):
    """S3: the middles of the edges of the picked face are markers that center the holes along or across."""

    def test_the_middles_of_the_edges_of_the_picked_face_are_markers_with_their_kind(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        top_face = body.Shape.getElement(top)
        corners = [self.vertex_at(body, v.Point) for v in top_face.Vertexes]
        panel = self.run_command()
        self.click(body, top)
        markers = panel.reference_markers()
        self.assertEqual([name for name, _ in markers if name.startswith("Vertex")], corners)
        middles = dict((name, point) for name, point in markers if name.startswith("Edge"))
        self.assertEqual(len(middles), 4, list(middles))
        for ends, (middle, kind) in TOP_MIDDLES.items():
            name = self.edge_at(body, ends)
            with self.subTest(edge=name, kind=kind):
                self.assertTrue(middles[name].isEqual(App.Vector(*middle), 1e-6), middles[name])
                self.assertEqual(panel.marker_kind(name), kind)
        self.assertEqual(panel.marker_kind(corners[0]), "corner")
        self.assertIsNone(panel.marker_kind("Edge999"))
        self.assertTrue(panel.reject())
        self.assertEqual(panel.reference_markers(), [])

    def test_a_long_edge_middle_centers_along_and_measures_across_from_that_edge(self):
        body = self.tube()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.assertEqual(self.centers(panel), (False, False))
        self.set_values(panel, along=0.0, across=10.0)
        edge = self.edge_at(body, LONG_FAR)
        self.assertTrue(panel.pick_marker(edge))
        # L15: the reference corner is an end of the clicked edge.
        self.assertIn(panel.vertex, self.ends(body, LONG_FAR))
        self.assertEqual(self.centers(panel), (True, False))
        self.assertEqual(panel.form.vertex_label.text(), f"Middle of {edge}")
        self.assert_points([panel.corner_marker()], [self.vertex_point(body, panel.vertex)])
        # L11: only the point the offsets are measured from is filled.
        self.assert_points(panel.highlighted_markers(), [TOP_MIDDLES[LONG_FAR][0]])
        wait()
        obj = self.preview(before)
        self.assertEqual((obj.ReferenceVertex, obj.CenterAlong, obj.CenterAcross), (panel.vertex, True, False))
        # Across from the far long edge, 10 mm into the face; along from the middle.
        self.assertTrue(self.empty(obj.Shape, 150, 15, 24))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)

    def test_a_short_edge_middle_centers_across_and_another_point_replaces_it(self):
        body = self.tube()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, along=0.0, across=0.0)
        short = self.edge_at(body, SHORT_END)
        self.assertTrue(panel.pick_marker(short))
        self.assertIn(panel.vertex, self.ends(body, SHORT_END))
        self.assertEqual(self.centers(panel), (False, True))
        self.assertEqual(panel.form.vertex_label.text(), f"Middle of {short}")
        # S6: another middle is a reference of its own, nothing is combined.
        long = self.edge_at(body, LONG_FAR)
        self.assertTrue(panel.pick_marker(long))
        self.assertIn(panel.vertex, self.ends(body, LONG_FAR))
        self.assertEqual(self.centers(panel), (True, False))
        self.assertEqual(panel.form.vertex_label.text(), f"Middle of {long}")
        # The face center centers the hole on the face.
        self.assertTrue(panel.pick_marker(self.marker_at_point(panel, (150, 0, 25))))
        self.assertEqual(self.centers(panel), (True, True))
        self.assertEqual(panel.form.vertex_label.text(), "Center of the face")
        self.assert_points(panel.highlighted_markers(), [(150, 0, 25)])
        wait()
        obj = self.preview(before)
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (True, True))
        self.assertTrue(self.empty(obj.Shape, 150, 0, 24))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(panel.reject())

    def test_a_middle_picked_without_a_corner_takes_the_first_end_of_its_edge(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        panel = self.run_command()
        self.click(body, top)
        self.assertIsNone(panel.vertex)
        name = self.edge_at(body, SHORT_START)
        self.assertTrue(panel.pick_marker(name))
        first = body.Shape.getElement(name).Vertexes[0].Point
        self.assertEqual((panel.vertex, self.centers(panel)), (self.vertex_at(body, first), (False, True)))
        self.assertTrue(panel.reject())

    def test_a_left_click_on_a_middle_picks_it(self):
        from pivy import coin

        body = self.tube()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        panel._viewport_point = lambda point: (point.x, point.y)
        event = coin.SoMouseButtonEvent()
        event.setButton(coin.SoMouseButtonEvent.BUTTON1)
        event.setState(coin.SoMouseButtonEvent.DOWN)
        event.setPosition(coin.SbVec2s(152, -22))
        handled = []
        panel._on_mouse_button(SimpleNamespace(getEvent=lambda: event, setHandled=lambda: handled.append(1)))
        self.events()
        self.assertEqual(handled, [1])
        self.assertEqual((panel.vertex, self.centers(panel)), (self.vertex_at(body, CORNER), (True, False)))
        self.assertTrue(panel.reject())

    def test_a_corner_marker_a_face_click_or_a_vertex_click_measure_from_the_corner(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner, far = self.vertex_at(body, CORNER), self.vertex_at(body, FAR_CORNER)
        before = self.names()
        panel = self.run_command((body, top), (body, corner))

        def center_both():
            panel.pick_marker(self.marker_at_point(panel, TOP_CENTER))
            self.assertEqual(self.centers(panel), (True, True))

        for name, action, vertex in (
            ("corner marker", lambda: panel.pick_marker(far), far),
            ("corner marker on the reference", lambda: panel.pick_marker(corner), corner),
            ("face click near a corner", lambda: self.click_at(body, top, (-40, -18, 25)), corner),
            ("vertex click", lambda: self.click(body, corner), corner),
        ):
            with self.subTest(name):
                center_both()
                action()
                self.assertEqual(self.centers(panel), (False, False))
                self.assertEqual(panel.vertex, vertex)
                self.assertEqual(panel.form.vertex_label.text(), panel.vertex)
                self.assert_points(panel.highlighted_markers(), [panel.corner_marker()])
                wait()
                obj = self.preview(before)
                self.assertEqual((obj.ReferenceVertex, obj.CenterAlong, obj.CenterAcross), (panel.vertex, False, False))
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)

    def test_ok_creates_a_centered_hole_in_one_undo_step(self):
        body = self.tube()
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, along=0.0, across=0.0)
        panel.pick_marker(self.marker_at_point(panel, TOP_CENTER))
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (True, True))
        self.assertTrue(self.empty(obj.Shape, 150, 0, 24))
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)


class TestDrillHoleMidpointEdit(MidpointFixture):
    """S3 when editing: the centers are part of the edit, like the other values."""

    def test_double_click_shows_the_centers_and_ok_keeps_them_in_one_undo_step(self):
        body, obj = self.existing(OffsetAcross=10.0)
        self.assertTrue(self.empty(obj.Shape, -20, -15, 24))
        panel = self.edit(obj)
        self.assertEqual(self.centers(panel), (False, False))
        panel.pick_marker(self.marker_at_point(panel, TOP_CENTER))
        wait()
        self.assertTrue(self.empty(obj.Shape, 180, 10, 24))
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (True, True))
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, False))
        self.assertTrue(self.empty(obj.Shape, -20, -15, 24))
        panel = self.edit(obj)
        self.assertEqual(self.centers(panel), (False, False))
        self.assertTrue(panel.reject())

    def test_a_centered_hole_shows_its_centers_and_cancel_restores_them(self):
        for undo_mode in (1, 0):
            with self.subTest(undo_mode=undo_mode):
                body, obj = self.existing(OffsetAlong=10.0, OffsetAcross=10.0, CenterAlong=True, CenterAcross=True)
                corner = self.vertex_at(body, CORNER)
                panel = self.edit(obj)
                self.assertEqual(self.centers(panel), (True, True))
                self.assertEqual(panel.form.vertex_label.text(), "Center of the face")
                self.assert_points(panel.highlighted_markers(), [(150, 0, 25)])
                self.doc.UndoMode = undo_mode
                self.addCleanup(setattr, self.doc, "UndoMode", 1)
                panel.pick_marker(corner)
                wait()
                self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, False))
                self.assertTrue(self.empty(obj.Shape, -40, -15, 24))
                self.assertTrue(panel.reject())
                self.assertEqual((obj.CenterAlong, obj.CenterAcross), (True, True))
                self.assertTrue(self.empty(obj.Shape, 160, 10, 24))
                self.assertEqual(self.doc.UndoCount, 0)
                self.doc.UndoMode = 1

    def test_ok_without_changes_to_the_centers_leaves_no_undo_step(self):
        body, obj = self.existing(CenterAlong=True)
        corner = self.vertex_at(body, CORNER)
        for change_back in (False, True):
            with self.subTest(change_back=change_back):
                panel = self.edit(obj)
                self.assertEqual(self.centers(panel), (True, False))
                if change_back:
                    # Off, previewed, then on again from the same corner: nothing changed in the end.
                    panel.pick_marker(corner)
                    wait()
                    self.assertFalse(obj.CenterAlong)
                    panel.pick_marker(self.edge_at(body, LONG_NEAR))
                self.assertTrue(panel.accept())
                self.events()
                self.assertEqual((obj.ReferenceVertex, obj.CenterAlong, obj.CenterAcross), (corner, True, False))
                self.assertTrue(self.empty(obj.Shape, 180, 0, 24))
                self.assertEqual(self.doc.UndoCount, 0)


# Middle of the top face of the tube.
TOP_CENTER = (150, 0, 25)


class TestDrillHoleOriginMarker(MidpointFixture):
    """L11: the one filled orange marker is the point the offsets are measured from."""

    def drawn(self, panel):
        """(filled orange points, white points) of the markers drawn over the 3D view."""
        self.assertIsNotNone(panel._corner_node)
        node = panel._corner_node[1]
        filled, white = [], []
        for index in range(node.getNumChildren()):
            group = node.getChild(index)
            color = tuple(round(c, 6) for c in group.getChild(0).rgb[0].getValue())
            points = [App.Vector(*point.getValue()) for point in group.getChild(1).point.getValues()]
            if color == tuple(round(c, 6) for c in create_drill_hole_tool.CORNER_MARKER_COLOR):
                filled += points
            else:
                self.assertEqual(color, tuple(round(c, 6) for c in create_drill_hole_tool.PICK_MARKER_COLOR))
                white += points
        return filled, white

    def test_the_origin_marker_is_the_corner_the_middle_along_across_or_the_face_center(self):
        body = self.tube()
        corner = self.vertex_at(body, CORNER)
        panel = self.run_command((body, self.face_towards(body, UP)), (body, corner))
        all_markers = [point for _, point in panel.reference_markers()]
        self.assertEqual(len(all_markers), 9)
        states = (
            ("no center", corner, CORNER),
            ("along", self.edge_at(body, LONG_NEAR), TOP_MIDDLES[LONG_NEAR][0]),
            ("along, other long edge", self.edge_at(body, LONG_FAR), TOP_MIDDLES[LONG_FAR][0]),
            ("across", self.edge_at(body, SHORT_START), TOP_MIDDLES[SHORT_START][0]),
            ("both", self.marker_at_point(panel, TOP_CENTER), TOP_CENTER),
        )
        for name, pick, origin in states:
            with self.subTest(name):
                self.assertTrue(panel.pick_marker(pick))
                self.assertTrue(panel.origin_marker().isEqual(App.Vector(*origin), 1e-6), panel.origin_marker())
                self.assert_points(panel.highlighted_markers(), [origin])
                filled, white = self.drawn(panel)
                self.assert_points(filled, [origin])
                # Every other marker, the reference corner too when a center is on, is white; none twice.
                others = [p for p in all_markers if not p.isEqual(App.Vector(*origin), 1e-6)]
                self.assert_points(white, [(p.x, p.y, p.z) for p in others])
                if name != "no center":
                    self.assertTrue(any(p.isEqual(panel.corner_marker(), 1e-6) for p in white))
        self.assertTrue(panel.reject())
        self.assertIsNone(panel.origin_marker())
        self.assertEqual(panel.highlighted_markers(), [])

    def test_the_origin_marker_is_where_holes_with_offsets_zero_are_drilled(self):
        body = self.tube()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, FAR_CORNER)))
        self.set_values(panel, along=0.0, across=0.0)
        panel.pick_marker(self.marker_at_point(panel, TOP_CENTER))
        wait()
        origin = panel.origin_marker()
        self.assertTrue(origin.isEqual(App.Vector(*TOP_CENTER), 1e-6), origin)
        self.assertTrue(self.empty(panel.obj.Shape, origin.x, origin.y, origin.z - 1))
        self.assertTrue(panel.reject())

    def test_no_origin_marker_without_a_vertex(self):
        body = self.tube()
        panel = self.run_command()
        self.click(body, self.face_towards(body, UP))
        self.assertIsNone(panel.vertex)
        self.assertIsNone(panel.origin_marker())
        self.assertEqual(panel.highlighted_markers(), [])
        filled, white = self.drawn(panel)
        self.assertEqual((len(filled), len(white)), (0, 9))
        self.assertTrue(panel.reject())


class TestDrillHoleMarkerClick(MidpointFixture):
    """L10: FreeCAD still selects what lies under a clicked marker; the panel ignores and clears it."""

    def press(self, panel, x, y, state):
        """A left mouse button event at the screen (x, y), without pumping events: whether it was handled."""
        from pivy import coin

        event = coin.SoMouseButtonEvent()
        event.setButton(coin.SoMouseButtonEvent.BUTTON1)
        event.setState(state)
        event.setPosition(coin.SbVec2s(x, y))
        handled = []
        panel._on_mouse_button(SimpleNamespace(getEvent=lambda: event, setHandled=lambda: handled.append(1)))
        return bool(handled)

    def select_at(self, obj, sub, point):
        """What FreeCAD selects under the click, as the 3D view reports it."""
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, *point)

    def state(self, panel):
        return (panel.face, panel.vertex, self.centers(panel), self.message(panel), panel.form.vertex_label.text())

    def test_what_freecad_selects_under_a_clicked_marker_changes_nothing_and_is_cleared(self):
        from pivy import coin

        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, CORNER)
        panel = self.run_command((body, top), (body, corner))
        panel._viewport_point = lambda point: (point.x, point.y)
        Gui.Selection.clearSelection()
        obj = panel.obj
        self.assertIsNotNone(obj)
        edge = self.edge_at(obj, SHORT_END)
        # The middle of the short far edge: centered across from the far end.
        self.assertTrue(self.press(panel, 349, 1, coin.SoMouseButtonEvent.DOWN))
        self.events()
        state = self.state(panel)
        self.assertEqual(state[2], (False, True))
        under = (
            ("edge of the preview", obj, edge, (350, 0, 25)),
            ("face", body, top, (-40, -18, 25)),
            ("vertex", body, corner, CORNER),
        )
        for name, target, sub, point in under:
            with self.subTest(name, during="press"):
                self.select_at(target, sub, point)
                self.assertEqual(self.state(panel), state)
                self.events()
                self.assertEqual(self.state(panel), state)
                self.assertEqual(Gui.Selection.getSelectionEx(), [])
        # The release still belongs to the click: what is selected while it is processed is ignored too.
        self.assertTrue(self.press(panel, 349, 1, coin.SoMouseButtonEvent.UP))
        for name, target, sub, point in under:
            with self.subTest(name, during="release"):
                self.select_at(target, sub, point)
                self.assertEqual(self.state(panel), state)
        self.events()
        self.assertEqual(self.state(panel), state)
        self.assertEqual(Gui.Selection.getSelectionEx(), [])
        # Once the click ended, a selection is a pick again.
        self.click_at(obj, edge, (350, 0, 25))
        self.assertEqual(self.message(panel), f"{obj.Label}: {edge} is not a face")
        self.click_at(body, top, (-40, -18, 25))
        self.assertEqual((panel.vertex, self.centers(panel)), (corner, (False, False)))
        self.assertTrue(panel.reject())

    def test_a_click_off_the_markers_selects_as_before(self):
        from pivy import coin

        body = self.tube()
        top = self.face_towards(body, UP)
        panel = self.run_command((body, top), (body, self.vertex_at(body, CORNER)))
        panel._viewport_point = lambda point: (point.x, point.y)
        obj = panel.obj
        edge = self.edge_at(obj, SHORT_END)
        self.assertFalse(self.press(panel, 200, 10, coin.SoMouseButtonEvent.DOWN))
        Gui.Selection.clearSelection()
        self.select_at(obj, edge, (350, 0, 25))
        self.events()
        self.assertEqual(self.message(panel), f"{obj.Label}: {edge} is not a face")
        self.assertFalse(self.press(panel, 200, 10, coin.SoMouseButtonEvent.UP))
        self.click_at(body, top, (330, 15, 25))
        self.assertEqual(panel.vertex, self.vertex_at(body, FAR_CORNER))
        self.assertTrue(panel.reject())


# The nine points of the top face of the tube: (point, kind, (CenterAlong, CenterAcross)).
TOP_POINTS = (
    (CORNER, "corner", (False, False)),
    ((350, -25, 25), "corner", (False, False)),
    ((-50, 25, 25), "corner", (False, False)),
    (FAR_CORNER, "corner", (False, False)),
    (TOP_MIDDLES[LONG_NEAR][0], "along", (True, False)),
    (TOP_MIDDLES[LONG_FAR][0], "along", (True, False)),
    (TOP_MIDDLES[SHORT_START][0], "across", (False, True)),
    (TOP_MIDDLES[SHORT_END][0], "across", (False, True)),
    (TOP_CENTER, "center", (True, True)),
)


class TestDrillHoleNinePoints(MidpointFixture):
    """S6: one click on any of the nine points of the face sets the whole reference."""

    def label(self, body, point, kind):
        if kind == "corner":
            return self.vertex_at(body, point)
        if kind == "center":
            return "Center of the face"
        ends = next(ends for ends, (middle, _) in TOP_MIDDLES.items() if middle == point)
        return f"Middle of {self.edge_at(body, ends)}"

    def assert_reference(self, panel, body, point, kind, centers):
        self.assertEqual(self.centers(panel), centers)
        self.assertEqual(panel.form.vertex_label.text(), self.label(body, point, kind))
        origin = panel.origin_marker()
        self.assertTrue(origin is not None and origin.isEqual(App.Vector(*point), 1e-6), origin)
        self.assert_points(panel.highlighted_markers(), [point])
        top = body.Shape.getElement(self.face_towards(body, UP))
        if kind == "corner":
            self.assertEqual(panel.vertex, self.vertex_at(body, point))
        elif kind == "center":
            self.assertIn(panel.vertex, {self.vertex_at(body, vertex.Point) for vertex in top.Vertexes})
        else:
            ends = next(ends for ends, (middle, _) in TOP_MIDDLES.items() if middle == point)
            self.assertIn(panel.vertex, self.ends(body, ends))

    def test_each_of_the_nine_points_sets_the_whole_reference_from_any_previous_one(self):
        body = self.tube()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.assertEqual(len(panel.reference_markers()), 9)
        self.assertEqual(panel.marker_kind(self.marker_at_point(panel, TOP_CENTER)), "center")
        previous = (FAR_CORNER, TOP_CENTER, TOP_MIDDLES[LONG_NEAR][0], TOP_MIDDLES[SHORT_END][0])
        for point, kind, centers in TOP_POINTS:
            for start in previous:
                with self.subTest(point=point, after=start):
                    self.assertTrue(panel.pick_marker(self.marker_at_point(panel, start)))
                    self.assertTrue(panel.pick_marker(self.marker_at_point(panel, point)))
                    self.assert_reference(panel, body, point, kind, centers)
        wait()
        obj = self.preview(before)
        self.assertEqual((obj.ReferenceVertex, obj.CenterAlong, obj.CenterAcross), (panel.vertex, True, True))
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)

    def test_a_click_on_the_face_takes_the_nearest_of_the_nine_points(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, along=0.0, across=0.0)
        for click, point, kind, centers in (
            ((140, 17, 25), TOP_MIDDLES[LONG_FAR][0], "along", (True, False)),
            ((-44, -4, 25), TOP_MIDDLES[SHORT_START][0], "across", (False, True)),
            ((158, -6, 25), TOP_CENTER, "center", (True, True)),
            ((338, -19, 25), (350, -25, 25), "corner", (False, False)),
            ((345, 3, 25), TOP_MIDDLES[SHORT_END][0], "across", (False, True)),
            ((146, 4, 25), TOP_CENTER, "center", (True, True)),
        ):
            with self.subTest(click=click):
                self.click_at(body, top, click)
                self.assertEqual(panel.face, (body, top))
                self.assert_reference(panel, body, point, kind, centers)
                self.assertEqual(self.message(panel), "")
        wait()
        obj = self.preview(before)
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (True, True))
        self.assertTrue(self.empty(obj.Shape, *TOP_CENTER[:2], 24))
        # Another face: the nearest of its own points.
        bottom = self.face_towards(body, App.Vector(0, 0, -1))
        self.click_at(body, bottom, (152, 3, -25))
        self.assertEqual((panel.face, self.centers(panel)), ((body, bottom), (True, True)))
        self.assertTrue(panel.origin_marker().isEqual(App.Vector(150, 0, -25), 1e-6), panel.origin_marker())
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)


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
        self.assertEqual(form.spin_along_forward_count.value(), 0)
        self.assertFalse(form.spin_along_forward_pitch.isEnabled())
        self.assertFalse(form.spin_depth.isEnabled())
        # The depth starts at the wall under the face.
        self.assertAlmostEqual(form.spin_depth.value(), WALL, places=6)
        # Value changes are previewed once typing pauses (S9).
        self.set_values(panel)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        form.groupBox_pattern.setChecked(True)
        form.spin_along_forward_count.setValue(2)
        self.assertTrue(form.spin_along_forward_pitch.isEnabled())
        form.spin_along_forward_pitch.setValue(40.0)
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
        form.spin_along_forward_count.setValue(0)
        self.assertFalse(form.spin_along_forward_pitch.isEnabled())
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
        # Checking it again previews at once (a whole hole: off the corner, where new holes start).
        self.set_values(panel)
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
        self.set_values(panel, diameter=12.0)
        self.set_pattern(panel, along_forward=(1, 40.0))
        wait()
        self.assertEqual(counter.calls, 0)
        self.assertEqual(self.names(), before)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual(self.values(obj)[:7], (corner, 30.0, 25.0, 12.0, 1, 40.0, "One wall"))
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
        self.set_values(panel, diameter=8.0)
        self.set_pattern(panel, along_forward=(1, 40.0))
        self.set_cut_type(panel, "Through All")
        self.assertTrue(panel.accept())
        obj = self.preview(before)
        self.assertEqual(obj.Name, f"{body.Name}_Dh")
        self.assertEqual(obj.Label, "Profile_TC50x50x2_000_Dh")
        self.assertEqual(obj.getParentGeoFeatureGroup(), part)
        self.assertEqual(obj.baseObject, (body, [top]))
        self.assertEqual(self.values(obj)[:7], (corner, 30.0, 25.0, 8.0, 1, 40.0, "Through All"))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 4 * hole_volume(8.0, WALL), places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)

    def test_the_offsets_are_documented_from_the_picked_point_to_the_pattern_origin(self):
        body, obj = self.existing()
        self.assertEqual(
            obj.getDocumentationOfProperty("OffsetAlong"),
            "Distance from the picked point to the pattern origin (the hole at the point), along the profile",
        )
        self.assertEqual(
            obj.getDocumentationOfProperty("OffsetAcross"),
            "Distance from the picked point to the pattern origin (the hole at the point), across the profile",
        )

    def test_a_new_hole_starts_with_both_offsets_at_zero(self):
        # The hole starts on the picked point: a corner, the middle of an edge or the face center.
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command()
        self.assertEqual(panel.form.spin_offset_along.value(), 0.0)
        self.assertEqual(panel.form.spin_offset_across.value(), 0.0)
        self.click_at(body, top, (150, 0, 25))
        wait()
        obj = self.preview(before)
        self.assertEqual((obj.OffsetAlong.Value, obj.OffsetAcross.Value), (0.0, 0.0))
        normal, centers = obj.Proxy.centers(obj)
        self.assertTrue(centers[0].isEqual(App.Vector(150, 0, 25), 1e-6), centers[0])
        self.assertTrue(panel.accept())
        self.assertEqual(obj.getStatusString(), "Valid")

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
        self.assertEqual(
            self.message(panel), "Select a planar face of a profile, a trimmed profile, a cutout or a folded bar."
        )
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


class TestDrillHoleRememberedDiameter(DrillHolePanelFixture):
    """S1: the diameter of the last confirmed drill hole, kept in FreeCAD preferences, opens the next new one."""

    def test_the_first_new_hole_opens_with_the_default_diameter(self):
        # S1: first use, nothing remembered yet.
        self.tube()
        panel = self.run_command()
        self.assertEqual(panel.form.spin_diameter.value(), drill_hole.DEFAULT_DIAMETER)
        self.assertIsNone(remembered_diameter())

    def test_ok_remembers_the_diameter_and_the_next_new_hole_opens_and_is_drilled_with_it(self):
        # S1: stored in the preferences on OK; a new drill hole opens with it.
        other = self.tube()
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.assertIsNone(remembered_diameter())
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(remembered_diameter(), 8.0)
        before = self.names()
        panel = self.run_command((other, self.face_towards(other, UP)), (other, self.vertex_at(other, CORNER)))
        self.assertEqual(panel.form.spin_diameter.value(), 8.0)
        # Off the corner, for a whole hole; the diameter is left as the panel opened.
        self.set_values(panel)
        wait()
        obj = self.preview(before)
        self.assertAlmostEqual(obj.Diameter.Value, 8.0, places=6)
        self.assertAlmostEqual(obj.Shape.Volume, other.Shape.Volume - hole_volume(8.0, WALL), places=3)

    def test_cancel_does_not_remember_the_diameter(self):
        # S1: never on Cancel; the next new hole opens with the last confirmed one.
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.assertTrue(panel.accept())
        self.close_dialog()
        panel = self.run_command()
        panel.form.spin_diameter.setValue(6.0)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertEqual(remembered_diameter(), 8.0)
        self.assertEqual(self.run_command().form.spin_diameter.value(), 8.0)

    def test_editing_shows_the_holes_own_diameter_and_ok_remembers_it(self):
        # S1: an existing hole shows its own diameter; OK confirms it, Cancel does not.
        get_param_group(writable=True).SetFloat(DIAMETER_PARAM, 8.0)
        body, obj = self.existing(Diameter=12.0)
        panel = self.edit(obj)
        self.assertEqual(panel.form.spin_diameter.value(), 12.0)
        panel.form.spin_diameter.setValue(14.0)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertEqual(remembered_diameter(), 8.0)
        panel = self.edit(obj)
        self.assertEqual(panel.form.spin_diameter.value(), 12.0)
        panel.form.spin_diameter.setValue(14.0)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(remembered_diameter(), 14.0)


class TestDrillHoleApplyAndContinue(DrillHolePanelFixture):
    """S2-S5: Apply and continue creates the hole in its own Undo step and keeps the panel open for the next face."""

    def other_profile(self):
        """A second profile, across the tube at x = 250: (profile, its top face, a vertex of that face)."""
        other = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        top = self.face_towards(other, UP)
        return other, top, self.vertex_of(other, top)

    def dialog_box(self):
        """The button row of the task dialog: the one button box holding its OK and Cancel."""
        boxes = [
            box
            for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
            if box.button(QtWidgets.QDialogButtonBox.Ok) is not None
            and box.button(QtWidgets.QDialogButtonBox.Cancel) is not None
        ]
        self.assertEqual(len(boxes), 1)
        return boxes[0]

    def apply_button(self):
        """Apply and continue in the task dialog's button row, or None."""
        return self.dialog_box().button(QtWidgets.QDialogButtonBox.Apply)

    def apply(self, panel):
        """Click Apply and continue, as the user does."""
        button = self.apply_button()
        self.assertTrue(button.isEnabled())
        button.click()
        self.events()

    def form_values(self, panel):
        """Every value of the panel fields: offsets, diameter, pattern, cut type and depth."""
        form = panel.form
        spins = [form.spin_offset_along, form.spin_offset_across, form.spin_diameter]
        spins += [getattr(form, f"spin_{row}_{kind}") for row, _ in PATTERN_ROWS for kind in ("count", "pitch")]
        return (
            [round(spin.value(), 6) for spin in spins + [form.spin_depth]],
            form.groupBox_pattern.isChecked(),
            form.cb_hole_at_point.isChecked(),
            form.combo_cut_type.currentData(),
        )

    def test_the_button_shows_only_while_creating_and_is_enabled_once_a_face_and_a_point_are_picked(self):
        # S2: only while creating a drill hole, not while editing one.
        body = self.tube()
        panel = self.run_command()
        button = self.apply_button()
        self.assertEqual(button.text(), "Apply and continue")
        self.assertFalse(button.isHidden())
        self.assertFalse(button.isEnabled())
        self.click(body, self.face_towards(body, UP))
        self.assertFalse(button.isEnabled())
        self.click(body, self.vertex_at(body, CORNER))
        self.assertTrue(button.isEnabled())
        self.assertTrue(panel.reject())
        self.close_dialog()
        body, obj = self.existing()
        self.edit(obj)
        self.assertIsNone(self.apply_button())

    def test_the_button_sits_next_to_ok_and_cancel_not_in_the_form(self):
        # S2 (L4): in the task dialog's own button row, not at the bottom of the form.
        body = self.tube()
        panel = self.run_command()
        box = self.dialog_box()
        button = box.button(QtWidgets.QDialogButtonBox.Apply)
        self.assertIsNotNone(button)
        self.assertEqual(button.text(), "Apply and continue")
        self.assertIs(button.parentWidget(), box.button(QtWidgets.QDialogButtonBox.Ok).parentWidget())
        self.assertIs(button.parentWidget(), box.button(QtWidgets.QDialogButtonBox.Cancel).parentWidget())
        self.assertFalse(hasattr(panel.form, "button_apply_continue"))
        self.assertEqual(
            [b.text() for b in panel.form.findChildren(QtWidgets.QPushButton) if b.text() == "Apply and continue"],
            [],
        )
        self.assertTrue(panel.reject())
        self.close_dialog()
        body, obj = self.existing()
        self.edit(obj)
        box = self.dialog_box()
        self.assertIsNone(box.button(QtWidgets.QDialogButtonBox.Apply))
        self.assertEqual(
            [b.text() for b in box.buttons() if b.text() == "Apply and continue"],
            [],
        )

    def test_the_button_does_not_run_ok(self):
        # S2: the standard Apply button only applies and continues; the dialog stays open, OK never runs.
        body, panel, first, before = self.previewed_panel()
        with patch.object(panel, "accept", wraps=panel.accept) as accept:
            self.apply(panel)
        accept.assert_not_called()
        self.assertTrue(Gui.Control.activeDialog())
        self.assertFalse(panel._closed)
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        self.assertIsNotNone(self.apply_button())
        self.assertFalse(self.apply_button().isEnabled())

    def test_apply_creates_the_hole_in_its_own_undo_step_and_the_next_one_on_another_profile_keeps_every_value(self):
        # S2, S3, S1: one Undo step per hole; the panel waits for a face with every value kept.
        other, top, vertex = self.other_profile()
        body, panel, first, before = self.previewed_panel(diameter=8.0)
        self.set_pattern(panel, along_forward=(2, 40.0))
        self.set_cut_type(panel, "Distance")
        panel.form.spin_depth.setValue(1.5)
        wait()
        kept = self.form_values(panel)
        self.apply(panel)
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual(first.getStatusString(), "Valid")
        self.assertEqual(first.baseObject, (body, [self.face_towards(body, UP)]))
        self.assertEqual(self.values(first)[1:8], (30.0, 25.0, 8.0, 2, 40.0, "Distance", 1.5))
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        self.assertEqual(remembered_diameter(), 8.0)
        # Waiting for a face: no reference, no markers, no preview, every value kept.
        self.assertEqual((panel.face, panel.vertex), (None, None))
        self.assertEqual(panel.form.face_label.text(), NO_FACE)
        self.assertEqual(panel.form.vertex_label.text(), NO_VERTEX)
        self.assertEqual(panel.reference_markers(), [])
        self.assertEqual(self.status(panel), "No preview")
        self.assertEqual(self.message(panel), "")
        self.assertFalse(self.apply_button().isEnabled())
        self.assertEqual(self.form_values(panel), kept)
        # Only the face and the point change with the next clicks.
        self.click(other, top)
        self.click(other, vertex)
        wait()
        second = self.preview(before + [first.Name])
        self.assertEqual(second.baseObject, (other, [top]))
        self.assertEqual(self.values(second), (vertex, *self.values(first)[1:]))
        self.assertTrue(panel.accept())
        self.assertEqual(second.getStatusString(), "Valid")
        self.assertAlmostEqual(second.Shape.Volume, other.Shape.Volume - 3 * hole_volume(8.0, 1.5), places=3)
        self.assertAlmostEqual(first.Shape.Volume, body.Shape.Volume - 3 * hole_volume(8.0, 1.5), places=3)
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole", "Create Drill Hole"])
        self.doc.undo()
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual(first.getStatusString(), "Valid")

    def fields(self, panel):
        """Every field of the panel that takes an expression."""
        return [spin for _, spin in panel._fields()]

    def shown_fx_icons(self, panel):
        """How many fields show their Fx icon: FreeCAD's icon is a label inside the field's line edit."""
        return sum(
            any(not label.isHidden() for label in spin.lineEdit().findChildren(QtWidgets.QLabel))
            for spin in self.fields(panel)
        )

    def press_equal(self, spin):
        """Type = in ``spin``, as the user does to open the expression editor; the editors it opened, closed.

        FreeCAD shows the editor (DlgExpressionInput) as a window that is not modal.
        """
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Equal, QtCore.Qt.NoModifier, "=")
        QtWidgets.QApplication.sendEvent(spin, event)
        self.events()
        editors = [
            widget
            for widget in QtWidgets.QApplication.topLevelWidgets()
            if widget.objectName() == "DlgExpressionInput" and widget.isVisible()
        ]
        opened = [editor.objectName() for editor in editors]
        for editor in editors:
            editor.reject()
        self.events()
        return opened

    def test_after_apply_the_fields_offer_no_expression_editor_until_the_next_hole_exists(self):
        # The applied hole is done: no Fx icon and no editor on =, so no expression lands on it.
        other, top, vertex = self.other_profile()
        body, panel, first, before = self.previewed_panel()
        self.assertEqual(self.shown_fx_icons(panel), len(self.fields(panel)))
        self.assertEqual(self.press_equal(panel.form.spin_diameter), ["DlgExpressionInput"])
        enabled = [spin.isEnabled() for spin in self.fields(panel)]
        self.apply(panel)
        self.assertEqual(self.shown_fx_icons(panel), 0)
        self.assertEqual(self.press_equal(panel.form.spin_diameter), [])
        self.assertEqual(list(first.ExpressionEngine), [])
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        # The values stay editable for the next hole: the closed Pattern group and the depth of a
        # Through all cut stay disabled as before.
        self.assertEqual([spin.isEnabled() for spin in self.fields(panel)], enabled)
        self.assertTrue(all(enabled[:3]))
        # The next hole's preview binds the fields to it again.
        self.click(other, top)
        self.click(other, vertex)
        wait()
        second = self.preview(before + [first.Name])
        self.assertEqual(self.shown_fx_icons(panel), len(self.fields(panel)))
        self.assertTrue(all(Gui.ExpressionBinding(spin).isBound() for spin in self.fields(panel)))
        self.assertEqual(self.press_equal(panel.form.spin_diameter), ["DlgExpressionInput"])
        self.assertEqual(list(second.ExpressionEngine), [])
        self.assertTrue(panel.reject())
        self.assertEqual(self.new_objects(before), [first])

    def test_after_apply_an_expression_stays_on_the_applied_hole_and_goes_to_the_next_one(self):
        # A field driven by an expression: the applied hole keeps it, the field offers no editor on that hole,
        # and the next hole gets the same expression with the other values.
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "Diameter")
        varset.Diameter = 6.0
        self.doc.recompute()
        other, top, vertex = self.other_profile()
        body, panel, first, before = self.previewed_panel()
        first.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        self.apply(panel)
        self.assertEqual(dict(first.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(self.shown_fx_icons(panel), 0)
        self.assertEqual(self.press_equal(panel.form.spin_diameter), [])
        self.assertEqual(dict(first.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        self.click(other, top)
        self.click(other, vertex)
        wait()
        second = self.preview(before + [first.Name])
        self.assertEqual(dict(second.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(second.Diameter.Value, 6.0)
        self.assertTrue(panel.accept())
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole", "Create Drill Hole"])

    def test_a_click_on_the_applied_hole_chains_the_next_hole_on_it_at_the_other_end_of_the_profile(self):
        # S4: the drilled profile shows the applied hole: it is the base of the next one, both stay cut.
        body, panel, first, before = self.previewed_panel()
        self.apply(panel)
        self.assertTrue(first.ViewObject.Visibility)
        top = self.face_towards(first, UP)
        self.click_at(first, top, (340, 20, 25))
        self.assertEqual(self.message(panel), "")
        self.assertEqual(panel.face, (first, top))
        self.assertEqual(panel.vertex, self.vertex_at(first, FAR_CORNER))
        wait()
        second = self.preview(before + [first.Name])
        self.assertEqual(second.baseObject, (first, [top]))
        self.assertTrue(panel.accept())
        for obj in (first, second):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertEqual(obj.ReferenceWarning, "")
        self.assertAlmostEqual(second.Shape.Volume, body.Shape.Volume - 2 * ONE_HOLE, places=3)
        self.assertTrue(self.empty(second.Shape, -20, 0, 24))
        self.assertTrue(self.empty(second.Shape, 320, 0, 24))
        self.assertEqual(
            [obj.ViewObject.Visibility for obj in (body, first, second)],
            [False, False, True],
        )
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole", "Create Drill Hole"])

    def test_cancel_after_apply_keeps_the_applied_hole_and_drops_the_one_in_progress(self):
        # S5: on another profile, and chained on the applied hole.
        other, top, vertex = self.other_profile()
        body, panel, first, before = self.previewed_panel()
        self.apply(panel)
        self.click(other, top)
        self.click(other, vertex)
        wait()
        self.preview(before + [first.Name])
        self.assertFalse(other.ViewObject.Visibility)
        self.assertTrue(panel.reject())
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual(first.getStatusString(), "Valid")
        self.assertAlmostEqual(first.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertEqual(
            [obj.ViewObject.Visibility for obj in (body, first, other)],
            [False, True, True],
        )
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        self.close_dialog()
        body, panel, first, before = self.previewed_panel()
        self.apply(panel)
        self.click_at(first, self.face_towards(first, UP), (340, 20, 25))
        wait()
        self.preview(before + [first.Name])
        self.assertFalse(first.ViewObject.Visibility)
        self.assertTrue(panel.reject())
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual([obj.ViewObject.Visibility for obj in (body, first)], [False, True])
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])

    def test_ok_with_no_face_after_apply_closes_the_panel_and_keeps_the_applied_hole(self):
        # S5: nothing is in progress, OK just closes.
        body, panel, first, before = self.previewed_panel()
        self.apply(panel)
        self.assertTrue(panel.accept())
        self.assertEqual(self.message(panel), "")
        self.assertEqual(self.new_objects(before), [first])
        self.assertEqual(first.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        # Closed: a click picks nothing.
        self.click(first, self.face_towards(first, UP))
        self.assertIsNone(panel.face)

    def test_apply_with_a_failing_hole_keeps_it_in_progress_without_an_undo_step(self):
        # S2: like OK, the panel keeps the hole and shows why.
        body, panel, obj, before = self.previewed_panel()
        self.set_pattern(panel, False)
        wait()
        self.apply(panel)
        self.assertIn("Drill Hole: no hole to drill.", self.message(panel))
        self.assertEqual(panel.face, (body, self.face_towards(body, UP)))
        self.assertEqual(self.new_objects(before), [obj])
        self.assertIsNone(remembered_diameter())
        # Nothing was committed: Cancel leaves the document unchanged.
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_apply_pressed_during_a_recompute_applies_the_last_values_once_it_ends(self):
        # S2: a recompute pumps Qt events; the button waits for it, and the panel stays open.
        hooks = self.hook_execute()
        body, panel, first, before = self.previewed_panel()

        def press(fp):
            panel.form.spin_diameter.setValue(14.0)
            self.apply_button().click()

        hooks.append(press)
        panel.form.spin_diameter.setValue(12.0)
        wait(SETTLE)
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.new_objects(before), [first])
        self.assertAlmostEqual(first.Diameter.Value, 14.0, places=6)
        self.assertEqual(first.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoNames, ["Create Drill Hole"])
        self.assertEqual((panel.face, panel.vertex), (None, None))

    def test_the_button_and_its_tooltip_are_spanish(self):
        # S2: Aplicar y seguir.
        use_language(self, "Spanish", "es_ES")
        self.run_command()
        button = self.apply_button()
        self.assertEqual(button.text(), "Aplicar y seguir")
        self.assertEqual(
            button.toolTip(),
            "Crea este agujero, que se deshace por separado, y deja el panel abierto: hacé clic en una cara para el "
            "próximo agujero, en otro perfil o en este, con los mismos valores.",
        )


class TestDrillHoleEdit(DrillHolePanelFixture):
    def test_double_click_shows_the_stored_values_and_ok_keeps_the_changes_in_one_undo_step(self):
        # S6: edit by double-click.
        body, obj = self.existing(Diameter=8.0, AlongForwardCount=1, AlongForwardPitch=60.0)
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
        self.assertTrue(form.groupBox_pattern.isChecked())
        self.assertEqual(form.spin_along_forward_count.value(), 1)
        self.assertTrue(form.spin_along_forward_pitch.isEnabled())
        self.assertAlmostEqual(form.spin_along_forward_pitch.value(), 60.0, places=6)
        self.assertEqual(form.combo_cut_type.currentData(), "One wall")
        self.assertEqual(form.warning_label.text(), "")
        self.assertTrue(form.warning_label.isHidden())
        before = self.names()
        # A click on the edited hole picks the vertex of its base.
        self.click(obj, self.vertex_at(obj, FAR_CORNER))
        form.spin_diameter.setValue(DIAMETER)
        form.spin_along_forward_count.setValue(0)
        wait()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(panel.accept())
        self.assertEqual(self.names(), before)
        self.assertEqual(obj.ReferenceVertex, self.vertex_at(body, FAR_CORNER))
        self.assertEqual((obj.Diameter.Value, obj.AlongForwardCount), (DIAMETER, 0))
        self.assertTrue(self.empty(obj.Shape, 320, 0, 24))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.values(obj), stored)

    def test_stored_lengths_finer_than_the_fields_are_kept_unless_that_field_is_changed(self):
        # R3-001: the fields show two decimals; OK must not write their rounded values back.
        fine = dict(OffsetAlong=30.125, OffsetAcross=24.875, Diameter=4.7625, AlongForwardPitch=50.0625)
        body, obj = self.existing(AlongForwardCount=1, CutType="Distance", ExtrusionLength=1.0625, **fine)
        stored = self.values(obj)
        panel = self.edit(obj)
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.values(obj), stored)
        self.assertEqual(self.doc.UndoCount, 0)
        panel = self.edit(obj)
        panel.form.spin_along_forward_count.setValue(2)
        wait()
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(obj.AlongForwardCount, 2)
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
        self.set_pattern(panel, along_forward=(2, 50.0))
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
        self.assertEqual(
            App.Qt.translate("MaxProFrame_DrillHole", resources["ToolTip"]),
            (
                "<b>Agujero</b><br><br>Hacé clic en una cara plana de un perfil, un perfil recortado, un calado o una "
                "barra plegada y luego en uno de sus nueve círculos para medir desde ahí: una esquina, el medio de un "
                "borde o el centro. Se perforan agujeros redondos a las distancias indicadas desde ese punto: uno solo, "
                "o un patrón a ambos lados, a lo largo y a lo ancho del perfil, con un diámetro y una profundidad."
            ),
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
                for name in ("offset_along", "offset_across", "diameter", "cut_type", "depth")
            ],
            [
                "Desplazamiento longitudinal",
                "Desplazamiento transversal",
                "Diámetro",
                "Tipo de corte",
                "Profundidad",
            ],
        )
        self.assertEqual(form.combo_cut_type.currentText(), "Una pared")
        self.assertEqual(form.cb_auto_update.text(), "Actualizar automáticamente")
        self.assertEqual(
            form.hint_label.text(),
            "Hacé clic en un círculo de la cara para ubicar los agujeros desde ahí: una esquina, el medio de un borde o "
            "el centro. Un clic en la cara toma el círculo más cercano.",
        )
        self.assertEqual(
            form.face_label.text(),
            "Hacé clic en una cara plana de un perfil, un perfil recortado, un calado o una barra plegada.",
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
        self.assertEqual(
            obj.getDocumentationOfProperty("AlongForwardCount"),
            "Cantidad de agujeros hacia adelante del punto, a lo largo del perfil",
        )
        self.assertTrue(panel.accept())
        # S4: the warning of a hole whose corner is gone.
        obj.OffsetAlong = 230.0
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assertEqual(obj.ReferenceWarning, "La referencia cambió, revisá el agujero.")


class TestDrillHoleMidpointsSpanish(MidpointFixture):
    def test_the_centering_of_the_reference_is_spanish(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, CORNER)
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((body, top), (body, corner))
        long, short = self.edge_at(body, LONG_NEAR), self.edge_at(body, SHORT_START)
        panel.pick_marker(long)
        self.assertEqual(panel.form.vertex_label.text(), f"Medio de {long}")
        panel.pick_marker(self.marker_at_point(panel, TOP_CENTER))
        self.assertEqual(panel.form.vertex_label.text(), "Centro de la cara")
        panel.pick_marker(corner)
        self.assertEqual(panel.form.vertex_label.text(), corner)
        panel.pick_marker(short)
        self.assertEqual(panel.form.vertex_label.text(), f"Medio de {short}")
        wait()
        obj = panel.obj
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, True))
        self.assertEqual(
            obj.getDocumentationOfProperty("CenterAlong"),
            "Medir el desplazamiento longitudinal desde el medio del largo de la cara",
        )
        self.assertEqual(
            obj.getDocumentationOfProperty("CenterAcross"),
            "Medir el desplazamiento transversal desde el medio del ancho de la cara",
        )
        self.assertTrue(panel.reject())


class TestDrillHoleExpressions(DrillHolePanelFixture):
    """Every field takes a FreeCAD expression (Fx), bound to the property of the drill hole shown."""

    FIELDS = (
        ("spin_offset_along", "OffsetAlong"),
        ("spin_offset_across", "OffsetAcross"),
        ("spin_diameter", "Diameter"),
        ("spin_along_backward_count", "AlongBackwardCount"),
        ("spin_along_backward_pitch", "AlongBackwardPitch"),
        ("spin_along_forward_count", "AlongForwardCount"),
        ("spin_along_forward_pitch", "AlongForwardPitch"),
        ("spin_across_backward_count", "AcrossBackwardCount"),
        ("spin_across_backward_pitch", "AcrossBackwardPitch"),
        ("spin_across_forward_count", "AcrossForwardCount"),
        ("spin_across_forward_pitch", "AcrossForwardPitch"),
        ("spin_depth", "ExtrusionLength"),
    )

    def varset(self, diameter):
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "Diameter")
        varset.Diameter = diameter
        self.doc.recompute()
        return varset

    def bindings(self, panel):
        return {prop: Gui.ExpressionBinding(getattr(panel.form, field)).isBound() for field, prop in self.FIELDS}

    def test_the_fields_are_bound_once_the_preview_exists(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top))
        # Without a vertex there is no drill hole yet: plain fields.
        self.assertEqual(set(self.bindings(panel).values()), {False})
        self.click(body, self.vertex_at(body, CORNER))
        wait()
        hole = self.preview(before)
        self.assertEqual(set(self.bindings(panel).values()), {True})
        # What the Fx editor does: the expression goes on the bound property and the field shows its value.
        varset = self.varset(6.0)
        hole.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        self.assertTrue(Gui.ExpressionBinding(panel.form.spin_diameter).hasExpression())
        self.assertAlmostEqual(panel.form.spin_diameter.value(), 6.0, places=6)
        self.assertTrue(panel.reject())

    def test_ok_keeps_an_expression_set_in_the_panel_in_one_undo_step(self):
        varset = self.varset(6.0)
        body, panel, hole, before = self.previewed_panel()
        hole.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.set_pattern(panel, along_forward=(1, 50.0))
        wait()
        self.assertTrue(panel.accept())
        self.assertEqual(dict(hole.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual((hole.Diameter.Value, hole.AlongForwardCount), (6.0, 1))
        self.assertAlmostEqual(hole.Shape.Volume, body.Shape.Volume - 2 * hole_volume(6.0, WALL), places=3)
        varset.Diameter = 4.0
        self.doc.recompute()
        self.assertAlmostEqual(hole.Shape.Volume, body.Shape.Volume - 2 * hole_volume(4.0, WALL), places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)

    def test_an_expression_is_kept_when_the_preview_is_made_again(self):
        varset = self.varset(6.0)
        body, panel, hole, before = self.previewed_panel()
        hole.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        # Another face without the vertex drops the preview; its vertex makes a new one.
        bottom = self.face_towards(body, App.Vector(0, 0, -1))
        self.click(body, bottom)
        wait()
        self.assertEqual(self.names(), before)
        self.click(body, self.vertex_at(body, BOTTOM_CORNER))
        wait()
        again = self.preview(before)
        self.assertEqual(dict(again.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(set(self.bindings(panel).values()), {True})
        self.assertTrue(Gui.ExpressionBinding(panel.form.spin_diameter).hasExpression())
        self.assertTrue(panel.accept())
        self.assertEqual(again.getStatusString(), "Valid")
        self.assertAlmostEqual(again.Diameter.Value, 6.0, places=6)

    def test_cancel_of_a_new_hole_with_an_expression_leaves_the_document_unchanged(self):
        varset = self.varset(6.0)
        body, panel, hole, before = self.previewed_panel()
        hole.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), before)
        self.assertTrue(body.ViewObject.Visibility)

    def test_an_existing_expression_is_shown_and_kept_while_other_fields_change(self):
        body, obj = self.existing()
        varset = self.varset(8.0)
        obj.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.edit(obj)
        form = panel.form
        self.assertEqual(set(self.bindings(panel).values()), {True})
        self.assertTrue(Gui.ExpressionBinding(form.spin_diameter).hasExpression())
        self.assertAlmostEqual(form.spin_diameter.value(), 8.0, places=6)
        self.set_pattern(panel, along_forward=(1, 50.0))
        wait()
        self.assertTrue(panel.accept())
        self.assertEqual(dict(obj.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(obj.AlongForwardCount, 1)
        varset.Diameter = 6.0
        self.doc.recompute()
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * hole_volume(6.0, WALL), places=3)

    def test_ok_with_only_an_expression_set_keeps_it_in_one_undo_step(self):
        _, obj = self.existing()
        varset = self.varset(6.0)
        self.doc.clearUndos()
        panel = self.edit(obj)
        obj.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        wait()
        self.assertTrue(panel.accept())
        self.assertEqual(dict(obj.ExpressionEngine), {"Diameter": f"{varset.Name}.Diameter"})
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_with_undo_off_removes_an_expression_set_in_the_panel(self):
        body, obj = self.existing()
        varset = self.varset(6.0)
        stored = self.values(obj)
        panel = self.edit(obj)
        self.doc.UndoMode = 0
        self.addCleanup(setattr, self.doc, "UndoMode", 1)
        obj.setExpression("Diameter", f"{varset.Name}.Diameter")
        self.doc.recompute()
        wait()
        self.assertTrue(panel.reject())
        self.assertEqual(dict(obj.ExpressionEngine), {})
        self.assertEqual(self.values(obj), stored)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)


# The pattern rows of the panel, in order, and the drill hole properties they set.
PATTERN_ROWS = (
    ("along_backward", "AlongBackward"),
    ("along_forward", "AlongForward"),
    ("across_backward", "AcrossBackward"),
    ("across_forward", "AcrossForward"),
)
USER_EXAMPLE = dict(along_backward=(3, 20.0), along_forward=(5, 30.0))


class PatternPanelFixture(DrillHolePanelFixture):
    def pattern_of(self, obj):
        """(HoleAtPoint, then count and pitch of each row) of the drill hole ``obj``."""
        values = [obj.HoleAtPoint]
        for _, prop in PATTERN_ROWS:
            values += [getattr(obj, f"{prop}Count"), round(getattr(obj, f"{prop}Pitch").Value, 6)]
        return tuple(values)

    def fields_of(self, panel):
        """(Hole at the point, then count and pitch of each row) shown by the panel."""
        form = panel.form
        values = [form.cb_hole_at_point.isChecked()]
        for row, _ in PATTERN_ROWS:
            values += [getattr(form, f"spin_{row}_count").value(), round(getattr(form, f"spin_{row}_pitch").value(), 6)]
        return tuple(values)

    def pattern_existing(self, **values):
        """A drill hole from CORNER, offsets 100 and 25: the point at (50, 0), with the pattern ``values``."""
        return self.existing(**{"OffsetAlong": 100.0, **values})


class TestDrillHolePatternPanel(PatternPanelFixture):
    """S1, S3, S5: the checkable Pattern group, its title, its fields and the hole at the point (L6)."""

    def test_a_new_hole_has_the_pattern_unchecked_with_its_fields_hidden_and_drills_one_hole(self):
        body = self.tube()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        form = panel.form
        box = form.groupBox_pattern
        self.assertTrue(box.isCheckable())
        self.assertFalse(box.isChecked())
        self.assertEqual(box.title(), "Pattern")
        self.assertTrue(form.pattern_fields.isHidden())
        self.assertTrue(form.cb_hole_at_point.isChecked())
        self.assertEqual(form.cb_hole_at_point.text(), "Hole at the point")
        self.assertEqual(
            [getattr(form, f"label_{row}").text() for row, _ in PATTERN_ROWS],
            ["Along ← backward", "Along → forward", "Across ← backward", "Across → forward"],
        )
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Holes per side", "Pitch")
        )
        self.assertEqual(self.fields_of(panel), (True, 0, 50.0, 0, 50.0, 0, 50.0, 0, 50.0))
        self.set_values(panel)
        wait()
        obj = self.preview(before)
        self.assertEqual(self.pattern_of(obj), (True, 0, 50.0, 0, 50.0, 0, 50.0, 0, 50.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        box.setChecked(True)
        self.assertFalse(form.pattern_fields.isHidden())
        box.setChecked(False)
        self.assertTrue(form.pattern_fields.isHidden())
        self.assertTrue(panel.reject())

    def test_the_title_sums_up_the_pattern(self):
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.set_pattern(panel, along_backward=(3, 20.0))
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 4 holes")
        self.set_pattern(panel, **USER_EXAMPLE)
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 9 holes")
        self.set_pattern(panel, along_backward=(0, 20.0), along_forward=(5, 12.5))
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 6 holes")
        self.set_pattern(panel, **USER_EXAMPLE, across_forward=(2, 25.0))
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 27 holes")
        self.set_pattern(panel, False, **USER_EXAMPLE, across_backward=(1, 10.0))
        self.assertEqual(
            form.groupBox_pattern.title(),
            "Pattern: 24 holes",
        )
        # Every count back to 0: one hole at the point, or none.
        self.set_pattern(panel, **{row: (0, 50.0) for row, _ in PATTERN_ROWS})
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 1 hole")
        form.cb_hole_at_point.setChecked(False)
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 0 holes")
        self.set_pattern(panel, **USER_EXAMPLE)
        form.groupBox_pattern.setChecked(False)
        self.assertEqual(form.groupBox_pattern.title(), "Pattern")
        self.assertTrue(panel.reject())

    def test_each_pitch_is_enabled_only_while_its_count_is_above_zero(self):
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        form.groupBox_pattern.setChecked(True)
        for row, _ in PATTERN_ROWS:
            with self.subTest(row=row):
                count, pitch = getattr(form, f"spin_{row}_count"), getattr(form, f"spin_{row}_pitch")
                self.assertFalse(pitch.isEnabled())
                count.setValue(1)
                self.assertTrue(pitch.isEnabled())
                others = [getattr(form, f"spin_{other}_pitch").isEnabled() for other, _ in PATTERN_ROWS if other != row]
                self.assertEqual(others, [False, False, False])
                count.setValue(0)
                self.assertFalse(pitch.isEnabled())
        self.assertTrue(panel.reject())

    def test_the_users_example_is_previewed_and_ok_creates_it_in_one_undo_step(self):
        # S2 through the panel: 9 holes, the point 100 mm into the face from the corner.
        body = self.tube()
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, self.face_towards(body, UP)), (body, self.vertex_at(body, CORNER)))
        self.set_values(panel, along=100.0)
        self.set_pattern(panel, **USER_EXAMPLE)
        wait()
        obj = self.preview(before)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 9 * ONE_HOLE, places=3)
        self.assertTrue(panel.accept())
        self.assertEqual(self.pattern_of(obj), (True, 3, 20.0, 5, 30.0, 0, 50.0, 0, 50.0))
        self.assertEqual(obj.getStatusString(), "Valid")
        for x in (-10, 10, 30, 50, 80, 110, 140, 170, 200):
            self.assertTrue(self.empty(obj.Shape, x, 0, 24), x)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)

    def test_without_the_hole_at_the_point_or_any_count_the_panel_shows_the_error(self):
        body, panel, obj, before = self.previewed_panel()
        self.set_pattern(panel, False)
        wait()
        self.assertIn(
            "Drill Hole: no hole to drill. Check Hole at the point or set a count in the pattern.", self.message(panel)
        )
        self.assertFalse(panel.accept())
        self.assertTrue(Gui.Control.activeDialog())
        self.set_pattern(panel, False, across_forward=(1, 15.0))
        wait()
        self.assertEqual(self.message(panel), "")
        self.assertTrue(panel.accept())
        self.assertEqual(self.pattern_of(obj), (False, 0, 50.0, 0, 50.0, 0, 50.0, 1, 15.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 15, 24))


class TestDrillHolePatternFieldWidth(PatternPanelFixture):
    """The count and pitch fields of the Pattern group: as wide as their values, never squeezed or stretched."""

    def pattern_spins(self, panel):
        form = panel.form
        return [getattr(form, f"spin_{row}_{kind}") for row, _ in PATTERN_ROWS for kind in ("count", "pitch")]

    def set_width(self, panel, width):
        """Show the panel ``width`` wide, in its Tasks dock floated: FreeCAD places the Fx icons of shown fields only."""
        dock = panel.form.parentWidget()
        while not isinstance(dock, QtWidgets.QDockWidget):
            dock = dock.parentWidget()
        if not dock.isFloating():
            dock.setFloating(True)
            self.addCleanup(dock.setFloating, False)
        dock.show()
        panel.form.setFixedWidth(width)
        self.events()
        self.assertTrue(panel.form.isVisible())

    def test_the_pattern_fields_keep_their_width_when_the_panel_widens(self):
        body, panel, obj, before = self.previewed_panel()
        self.set_pattern(panel, along_backward=(1, 50.0))
        narrowest = panel.form.minimumSizeHint().width()
        self.set_width(panel, narrowest)
        widths = [spin.width() for spin in self.pattern_spins(panel)]
        self.set_width(panel, narrowest + 300)
        self.assertEqual([spin.width() for spin in self.pattern_spins(panel)], widths)
        self.assertTrue(panel.reject())

    def test_each_pattern_field_shows_its_whole_value_left_of_the_fx_icon_in_the_narrowest_panel(self):
        body, panel, obj, before = self.previewed_panel()
        self.set_pattern(
            panel,
            along_backward=(999, 9999.99),
            **{row: (0, 9999.99) for row, _ in PATTERN_ROWS if row != "along_backward"},
        )
        self.set_width(panel, panel.form.minimumSizeHint().width())
        for spin in self.pattern_spins(panel):
            line = spin.lineEdit()
            icons = [label for label in line.findChildren(QtWidgets.QLabel) if label.isVisible()]
            self.assertEqual(len(icons), 1, icons)
            text_end = line.textMargins().left() + line.fontMetrics().horizontalAdvance(line.text())
            self.assertLessEqual(text_end, icons[0].geometry().left(), (spin.objectName(), line.text(), spin.width()))
        self.assertTrue(panel.reject())


class TestDrillHolePatternEdit(PatternPanelFixture):
    def test_the_group_opens_checked_for_a_hole_with_a_count_or_without_the_hole_at_the_point(self):
        for values, checked in (
            ({}, False),
            ({"AlongForwardCount": 2, "AlongForwardPitch": 40.0}, True),
            ({"AcrossBackwardCount": 1, "AcrossBackwardPitch": 15.0}, True),
            ({"HoleAtPoint": False, "AlongBackwardCount": 1}, True),
        ):
            with self.subTest(values=values):
                self.close_dialog()
                _, obj = self.pattern_existing(**values)
                panel = self.edit(obj)
                form = panel.form
                self.assertEqual(form.groupBox_pattern.isChecked(), checked)
                self.assertEqual(form.pattern_fields.isHidden(), not checked)
                self.assertEqual(self.fields_of(panel), self.pattern_of(obj))
                self.assertTrue(panel.reject())

    def test_unchecking_the_group_previews_one_hole_keeps_the_fields_and_ok_keeps_it_in_one_undo_step(self):
        body, obj = self.pattern_existing(HoleAtPoint=False, AlongForwardCount=2, AlongForwardPitch=40.0)
        stored = self.values(obj)
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * ONE_HOLE, places=3)
        panel = self.edit(obj)
        form = panel.form
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 2 holes")
        form.groupBox_pattern.setChecked(False)
        wait()
        self.assertEqual(form.groupBox_pattern.title(), "Pattern")
        self.assertEqual(self.pattern_of(obj), (True, 0, 50.0, 0, 40.0, 0, 50.0, 0, 50.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 50, 0, 24))
        # The fields keep their values for when the group is checked again.
        self.assertEqual(self.fields_of(panel), (False, 0, 50.0, 2, 40.0, 0, 50.0, 0, 50.0))
        form.groupBox_pattern.setChecked(True)
        wait()
        self.assertEqual(self.pattern_of(obj), (False, 0, 50.0, 2, 40.0, 0, 50.0, 0, 50.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * ONE_HOLE, places=3)
        form.groupBox_pattern.setChecked(False)
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.pattern_of(obj), (True, 0, 50.0, 0, 40.0, 0, 50.0, 0, 50.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.values(obj), stored)

    def test_ok_keeps_a_changed_pattern_in_one_undo_step(self):
        body, obj = self.pattern_existing(AlongForwardCount=1, AlongForwardPitch=40.0)
        stored = self.values(obj)
        panel = self.edit(obj)
        self.set_pattern(panel, **USER_EXAMPLE, across_forward=(1, 15.0))
        wait()
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.pattern_of(obj), (True, 3, 20.0, 5, 30.0, 0, 50.0, 1, 15.0))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 18 * ONE_HOLE, places=3)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.values(obj), stored)

    def test_cancel_restores_the_pattern_also_with_undo_off(self):
        for undo in (1, 0):
            with self.subTest(undo=undo):
                self.close_dialog()
                body, obj = self.pattern_existing(HoleAtPoint=False, AlongBackwardCount=1, AlongBackwardPitch=30.0)
                stored = self.values(obj)
                panel = self.edit(obj)
                self.doc.UndoMode = undo
                self.addCleanup(setattr, self.doc, "UndoMode", 1)
                self.set_pattern(panel, **USER_EXAMPLE, across_backward=(1, 12.0), across_forward=(1, 12.0))
                wait()
                self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 27 * ONE_HOLE, places=3)
                self.assertTrue(panel.reject())
                self.assertEqual(self.values(obj), stored)
                self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
                self.assertTrue(self.empty(obj.Shape, 20, 0, 24))
                self.assertEqual(self.doc.UndoCount, 0)

    def test_ok_without_a_change_to_the_pattern_leaves_no_undo_step(self):
        body, obj = self.pattern_existing(
            AlongForwardCount=2, AlongForwardPitch=40.0, AcrossForwardCount=1, AcrossForwardPitch=15.0
        )
        stored = self.values(obj)
        for toggle in (False, True):
            with self.subTest(toggle=toggle):
                panel = self.edit(obj)
                if toggle:
                    # Unchecked and previewed, then checked again: nothing changed in the end.
                    panel.form.groupBox_pattern.setChecked(False)
                    wait()
                    self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
                    panel.form.groupBox_pattern.setChecked(True)
                self.assertTrue(panel.accept())
                self.events()
                self.assertEqual(self.values(obj), stored)
                self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 6 * ONE_HOLE, places=3)
                self.assertEqual(self.doc.UndoCount, 0)

    def test_an_expression_on_a_pattern_field_is_shown_and_kept(self):
        # S5: the pattern fields take Fx like the others.
        body, obj = self.pattern_existing(AlongForwardCount=1)
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyInteger", "Holes")
        varset.Holes = 2
        varset.addProperty("App::PropertyLength", "Spacing")
        varset.Spacing = 30.0
        obj.setExpression("AlongForwardCount", f"{varset.Name}.Holes")
        obj.setExpression("AcrossForwardPitch", f"{varset.Name}.Spacing / 2")
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.edit(obj)
        form = panel.form
        for spin in (form.spin_along_forward_count, form.spin_across_forward_pitch):
            self.assertTrue(Gui.ExpressionBinding(spin).hasExpression())
        self.assertEqual(form.spin_along_forward_count.value(), 2)
        self.assertAlmostEqual(form.spin_across_forward_pitch.value(), 15.0, places=6)
        form.spin_across_forward_count.setValue(1)
        wait()
        self.assertTrue(panel.accept())
        self.assertEqual(
            dict(obj.ExpressionEngine),
            {"AlongForwardCount": f"{varset.Name}.Holes", "AcrossForwardPitch": f"{varset.Name}.Spacing / 2"},
        )
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 6 * ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 100, 15, 24))
        self.assertEqual(self.doc.UndoCount, 1)


# Image#7 (L8): across 2 every 5 mm on both sides, 8 mm holes; along 3 every 30 mm backward, 4 every 20 mm forward.
IMAGE_7 = dict(along_backward=(3, 30.0), along_forward=(4, 20.0), across_backward=(2, 5.0), across_forward=(2, 5.0))


def sides_of(rows):
    """The ``sides`` of drill_hole.pattern_positions for the panel rows ``rows`` (along_forward=(count, pitch), ...)."""
    sides = {prop: (0, 50.0) for _, prop in PATTERN_ROWS}
    sides.update({prop: rows[row] for row, prop in PATTERN_ROWS if row in rows})
    return sides


def overlap(axis, pitch, diameter):
    return f"The holes overlap: the pitch {axis} ({pitch}) is smaller than the diameter ({diameter})."


def pair_overlap(axis, apart, diameter):
    return (
        f"The holes overlap: with no hole at the point, the holes {axis} on each side of the point are {apart} apart, "
        f"less than the diameter ({diameter})."
    )


class TestDrillHolePatternFeedback(PatternPanelFixture):
    """S6 (L10): the overlap warning, the total in the title and the per-side count column."""

    def warning(self, panel):
        """Text of the warning area, and whether it shows."""
        label = panel.form.warning_label
        return label.text(), not label.isHidden()

    def test_the_warning_names_each_axis_whose_pitch_is_smaller_than_the_diameter_and_clears_when_fixed(self):
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.assertEqual(self.warning(panel), ("", False))
        self.set_pattern(panel, along_forward=(2, 5.0))
        self.assertEqual(self.warning(panel), (overlap("along", "5 mm", "8 mm"), True))
        self.set_pattern(panel, along_forward=(0, 5.0), across_backward=(2, 5.5))
        self.assertEqual(self.warning(panel), (overlap("across", "5.5 mm", "8 mm"), True))
        # Both axes: one line each, along first; the smallest pitch of an axis is named.
        self.set_pattern(panel, along_backward=(1, 6.0), along_forward=(3, 4.0))
        self.assertEqual(
            self.warning(panel),
            (f"{overlap('along', '4 mm', '8 mm')}\n{overlap('across', '5.5 mm', '8 mm')}", True),
        )
        # Live with the diameter too.
        panel.form.spin_diameter.setValue(5.0)
        self.assertEqual(self.warning(panel), (overlap("along", "4 mm", "5 mm"), True))
        # A pitch equal to the diameter does not overlap.
        self.set_pattern(panel, along_forward=(3, 5.0), across_backward=(2, 5.0))
        self.assertEqual(self.warning(panel), ("", False))
        self.assertTrue(panel.reject())

    def test_a_pair_without_the_hole_at_the_point_closer_than_the_diameter_is_warned(self):
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.set_pattern(panel, False, along_backward=(1, 3.0), along_forward=(1, 3.0))
        self.assertEqual(self.warning(panel), (pair_overlap("along", "6 mm", "8 mm"), True))
        self.set_pattern(panel, False, along_backward=(0, 3.0), along_forward=(0, 3.0))
        self.set_pattern(panel, False, across_backward=(1, 2.5), across_forward=(1, 3.0))
        self.assertEqual(self.warning(panel), (pair_overlap("across", "5.5 mm", "8 mm"), True))
        # 2 x 5 mm apart: the pair does not overlap, and a lone first hole meets no hole at the point.
        self.set_pattern(panel, False, across_backward=(1, 5.0), across_forward=(1, 5.0))
        self.assertEqual(self.warning(panel), ("", False))
        # With the hole at the point the same pitch overlaps it.
        panel.form.cb_hole_at_point.setChecked(True)
        self.assertEqual(self.warning(panel), (overlap("across", "5 mm", "8 mm"), True))
        self.assertTrue(panel.reject())

    def test_the_warning_shows_only_while_the_pattern_group_is_checked(self):
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.set_pattern(panel, across_forward=(2, 5.0))
        self.assertEqual(self.warning(panel), (overlap("across", "5 mm", "8 mm"), True))
        panel.form.groupBox_pattern.setChecked(False)
        self.assertEqual(self.warning(panel), ("", False))
        panel.form.groupBox_pattern.setChecked(True)
        self.assertEqual(self.warning(panel), (overlap("across", "5 mm", "8 mm"), True))
        self.assertTrue(panel.reject())

    def test_ok_creates_overlapping_holes_in_one_undo_step(self):
        # Overlapping can be on purpose: a warning, not an error.
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.set_pattern(panel, across_backward=(2, 5.0), across_forward=(2, 5.0))
        wait()
        self.assertEqual(self.warning(panel), (overlap("across", "5 mm", "8 mm"), True))
        self.assertEqual(self.message(panel), "")
        self.assertTrue(panel.accept())
        self.assertEqual(self.preview(before), obj)
        self.assertEqual(self.pattern_of(obj), (True, 0, 50.0, 0, 50.0, 2, 5.0, 2, 5.0))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_the_title_starts_with_the_total_of_holes_drilled(self):
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.set_pattern(panel, False, **IMAGE_7)
        total = len(drill_hole.pattern_positions(False, sides_of(IMAGE_7)))
        self.assertEqual(total, 28)
        self.assertEqual(
            form.groupBox_pattern.title(),
            f"Pattern: {total} holes",
        )
        form.cb_hole_at_point.setChecked(True)
        self.assertEqual(len(drill_hole.pattern_positions(True, sides_of(IMAGE_7))), 40)
        self.assertEqual(
            form.groupBox_pattern.title(),
            "Pattern: 40 holes",
        )
        self.assertTrue(panel.reject())

    def test_one_hole_is_singular_in_the_title(self):
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.set_pattern(panel)
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 1 hole")
        self.set_pattern(panel, False, across_forward=(1, 15.0))
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 1 hole")
        self.assertTrue(panel.reject())

    def test_the_count_column_is_holes_per_side(self):
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Holes per side", "Pitch")
        )
        self.assertTrue(panel.reject())


class TestDrillHolePatternFeedbackSpanish(PatternPanelFixture):
    def test_the_total_the_count_column_and_the_overlap_warning_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        form = panel.form
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Agujeros por lado", "Paso")
        )
        self.set_pattern(panel, False, **IMAGE_7)
        self.assertEqual(
            form.groupBox_pattern.title(),
            "Patrón: 28 agujeros",
        )
        self.assertEqual(
            form.warning_label.text(),
            "Los agujeros se superponen: el paso transversal (5 mm) es menor que el diámetro (8 mm).",
        )
        self.set_pattern(panel, False, along_backward=(1, 3.0), along_forward=(1, 3.0))
        self.set_pattern(panel, False, across_backward=(0, 5.0), across_forward=(0, 5.0))
        self.assertEqual(form.groupBox_pattern.title(), "Patrón: 2 agujeros")
        self.assertEqual(
            form.warning_label.text(),
            "Los agujeros se superponen: sin agujero en el punto, los agujeros longitudinales a cada lado del punto "
            "quedan a 6 mm entre sí, menos que el diámetro (8 mm).",
        )
        self.set_pattern(panel, True, along_backward=(0, 3.0), along_forward=(0, 3.0))
        self.assertEqual(form.groupBox_pattern.title(), "Patrón: 1 agujero")
        self.assertTrue(panel.reject())

    def test_both_overlap_lines_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        body, panel, obj, before = self.previewed_panel(diameter=8.0)
        self.set_pattern(panel, False, across_backward=(1, 2.0), across_forward=(1, 3.0), along_forward=(2, 6.0))
        self.assertEqual(
            panel.form.warning_label.text(),
            "Los agujeros se superponen: el paso longitudinal (6 mm) es menor que el diámetro (8 mm).\n"
            "Los agujeros se superponen: sin agujero en el punto, los agujeros transversales a cada lado del punto "
            "quedan a 5 mm entre sí, menos que el diámetro (8 mm).",
        )
        self.assertTrue(panel.reject())


class TestDrillHolePatternSpanish(PatternPanelFixture):
    def test_the_pattern_group_its_title_the_properties_and_the_errors_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        body, panel, obj, before = self.previewed_panel()
        form = panel.form
        self.assertEqual(form.groupBox_pattern.title(), "Patrón")
        self.assertEqual(form.cb_hole_at_point.text(), "Agujero en el punto")
        self.assertEqual(
            [getattr(form, f"label_{row}").text() for row, _ in PATTERN_ROWS],
            ["Longitudinal ← atrás", "Longitudinal → adelante", "Transversal ← atrás", "Transversal → adelante"],
        )
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Agujeros por lado", "Paso")
        )
        self.set_pattern(panel, False, **USER_EXAMPLE, across_forward=(2, 25.0))
        self.assertEqual(
            form.groupBox_pattern.title(),
            "Patrón: 16 agujeros",
        )
        self.assertEqual(
            [obj.getDocumentationOfProperty(name) for name in drill_hole_properties()],
            [
                "Cantidad de agujeros hacia atrás del punto, a lo largo del perfil",
                "Distancia entre los agujeros hacia atrás del punto, a lo largo del perfil",
                "Cantidad de agujeros hacia adelante del punto, a lo largo del perfil",
                "Distancia entre los agujeros hacia adelante del punto, a lo largo del perfil",
                "Cantidad de agujeros hacia atrás del punto, transversal al perfil",
                "Distancia entre los agujeros hacia atrás del punto, transversal al perfil",
                "Cantidad de agujeros hacia adelante del punto, transversal al perfil",
                "Distancia entre los agujeros hacia adelante del punto, transversal al perfil",
                "Perforar un agujero en el punto que dan los desplazamientos",
            ],
        )
        self.set_pattern(panel, False, **{row: (0, 50.0) for row, _ in PATTERN_ROWS})
        self.assertEqual(form.groupBox_pattern.title(), "Patrón: 0 agujeros")
        # Pending events can hold the preview timer past the default wait here: give it room.
        wait(SETTLE)
        self.assertIn(
            "Agujero: no hay ningún agujero para perforar. Marcá Agujero en el punto o poné una cantidad en el patrón.",
            self.message(panel),
        )
        self.set_pattern(panel, True, along_forward=(1000, 1.0))
        wait(SETTLE)
        self.assertIn("Agujero: el patrón da 1001 agujeros, como máximo 1000.", self.message(panel))
        self.assertTrue(panel.reject())


def drill_hole_properties():
    """The pattern properties of a drill hole, in the order of the panel rows, then HoleAtPoint."""
    return [f"{prop}{kind}" for _, prop in PATTERN_ROWS for kind in ("Count", "Pitch")] + ["HoleAtPoint"]


if __name__ == "__main__":
    unittest.main()

"""Drill Hole panel: no geometry while its own recompute runs (odd/tasks/panel-recompute-deadlock.md, S2, S3, S4).

FreeCAD's progress bar pumps Qt events inside a recompute (L2): the hooks below click a vertex, a face of the preview
and a marker there. None of it may run geometry then (the face of the preview is matched to its base with an OCC
boolean); it waits for the recompute to end, and the preview ends matching the last values. Values typed and OK or
Cancel pressed during a recompute are covered by test_drill_hole_panel.TestDrillHolePreview.
"""

import unittest

from test_cutout_flow import UP
from test_drill_hole_geometry import WALL
from test_drill_hole_panel import CORNER, FAR_CORNER, SETTLE, MidpointFixture, hole_volume
from test_extend_cut_preview import wait
from test_recompute_gate import during, hook_execute, watch

from freecad.maxproframe import create_drill_hole_tool, drill_hole
from freecad.maxproframe.create_drill_hole_tool import DrillHoleTaskPanel


class DrillHoleRecomputeGateTest(MidpointFixture):
    def setUp(self):
        super().setUp()
        self.hooks, state = hook_execute(self, drill_hole.DrillHole)
        self.geometry = watch(
            self,
            create_drill_hole_tool,
            ("_base_element", "_on_face", "wall_thickness", "_face_middles", "_face_center", "face_problem"),
            state,
        )
        self.panel_calls = watch(self, DrillHoleTaskPanel, ("_preview", "_markers"), state)

    def ran_during(self):
        return during(self.geometry) + during(self.panel_calls)

    def test_a_vertex_clicked_while_the_preview_recomputes_is_taken_once_it_ends(self):
        body, panel, obj, before = self.previewed_panel()
        far = self.vertex_at(body, FAR_CORNER)

        def click_and_type(fp):
            self.click(body, far)
            panel.form.spin_diameter.setValue(8.0)

        self.hooks.append(click_and_type)

        panel.form.spin_diameter.setValue(6.0)
        wait(SETTLE)

        self.assertEqual([], self.hooks)
        self.assertEqual([], self.ran_during())
        self.assertIn(("_on_face", False), self.geometry)
        self.assertEqual(far, panel.vertex)
        self.assertEqual(far, obj.ReferenceVertex)
        self.assertAlmostEqual(obj.Diameter.Value, 8.0, places=6)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual("Preview updated", self.status(panel))

    def test_a_face_of_the_preview_clicked_while_it_recomputes_is_matched_to_its_base_once_it_ends(self):
        # The face clicked on the preview is the face of its base it overlaps most: an OCC boolean.
        body, panel, obj, before = self.previewed_panel()
        top = self.face_towards(obj, UP)
        self.hooks.append(lambda fp: self.click_at(obj, top, (FAR_CORNER[0] - 1, FAR_CORNER[1] - 1, FAR_CORNER[2])))

        panel.form.spin_diameter.setValue(6.0)
        wait(SETTLE)

        self.assertEqual([], self.ran_during())
        self.assertIn(("_base_element", False), self.geometry)
        self.assertEqual((body, self.face_towards(body, UP)), panel.face)
        self.assertEqual(self.vertex_at(body, FAR_CORNER), obj.ReferenceVertex)
        self.assertAlmostEqual(obj.Diameter.Value, 6.0, places=6)
        self.assertEqual("Preview updated", self.status(panel))

    def test_a_marker_picked_while_the_preview_recomputes_is_taken_once_it_ends(self):
        body, panel, obj, before = self.previewed_panel(along=0.0, across=0.0)
        top = self.face_towards(body, UP)
        picked = []
        self.hooks.append(lambda fp: picked.append(panel.pick_marker(top)))

        panel.form.spin_diameter.setValue(6.0)
        wait(SETTLE)

        self.assertEqual([True], picked)
        self.assertEqual([], self.ran_during())
        self.assertEqual((True, True), self.centers(panel))
        self.assertEqual((True, True), (obj.CenterAlong, obj.CenterAcross))
        # The hole at the center of the top face, 6 mm across.
        self.assertTrue(self.empty(obj.Shape, 150, 0, 24))
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - hole_volume(6.0, WALL), places=3)
        self.assertEqual("Preview updated", self.status(panel))

    def test_a_pick_and_a_preview_without_a_recompute_in_between_are_unchanged(self):
        # S4: a click on a vertex of the face picks it; the preview follows.
        body, panel, obj, before = self.previewed_panel()
        self.assertEqual(self.vertex_at(body, CORNER), obj.ReferenceVertex)
        far = self.vertex_at(body, FAR_CORNER)
        self.click(body, far)
        wait()
        self.assertEqual(far, obj.ReferenceVertex)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual("Preview updated", self.status(panel))
        self.assertTrue(panel.accept())
        self.assertEqual(self.new_objects(before), [obj])
        self.assertEqual(self.doc.UndoCount, 1)


if __name__ == "__main__":
    unittest.main()

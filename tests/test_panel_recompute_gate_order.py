"""Extend / Cut and Drill Hole panels: what is done during their recompute runs in the order it was done once the
recompute ends (odd/tasks/panel-recompute-deadlock.md, S1-S4). A value typed, a click and then OK, Apply or Cancel
pressed inside it: the click is taken before the button runs, as without a recompute."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from test_drill_hole_panel import FAR_CORNER, MidpointFixture
from test_extend_cut_geometry import NEAR
from test_extend_cut_preview import wait
from test_keep_end_panel import KeepEndFixture
from test_recompute_gate import hook_execute

from freecad.maxproframe import drill_hole
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# Long enough for the preview timer to fire inside the recompute.
INSIDE = 3 * GAP_DELAY_MS / 1000
# The preview delay, the recompute and the ones that follow it, with room for a loaded machine.
SETTLE = 2.5


class ExtendCutOrderTest(KeepEndFixture):
    def setUp(self):
        super().setUp()
        self.hooks, _ = hook_execute(self, TrimmedProfile)

    def existing(self, gap=0.0):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)), gap)
        self.doc.recompute()
        self.doc.clearUndos()
        return target, face, body, obj

    def test_a_gap_typed_a_target_clicked_and_ok_during_the_edit_recompute_keep_the_click(self):
        target, face, body, obj = self.existing(gap=1.0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        far = self.face_towards(target, App.Vector(1, 0, 0))
        returned = []

        def type_click_ok(fp):
            panel.form.sb_gap.setValue(2.0)
            wait(INSIDE)
            self.click(target, far)
            returned.append(panel.accept())

        self.hooks.append(type_click_ok)
        panel.form.sb_gap.setValue(3.0)
        wait(SETTLE)

        self.assertEqual([], self.hooks)
        self.assertEqual([False], returned)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertEqual(obj.TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.doc.UndoCount, 1)

    def test_several_gaps_typed_during_the_edit_recompute_end_at_the_last(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)

        def type_several(fp):
            for gap in (2.0, 5.0, 4.0):
                panel.form.sb_gap.setValue(gap)
                wait(INSIDE)

        self.hooks.append(type_several)
        panel.form.sb_gap.setValue(1.0)
        wait(SETTLE)

        self.assertEqual([], self.hooks)
        self.assertAlmostEqual(obj.TrimGap.Value, 4.0)
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR - 4.0))
        self.assertEqual("Preview updated", self.status(panel))

    def test_apply_pressed_during_the_preview_recompute_creates_the_trim_and_keeps_the_panel_open(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        returned = []

        def type_and_apply(fp):
            panel.form.sb_gap.setValue(2.0)
            wait(INSIDE)
            returned.append(panel.apply_and_continue())

        self.hooks.append(type_and_apply)
        panel.form.sb_gap.setValue(1.0)
        wait(SETTLE)

        self.assertEqual([False], returned)
        self.assertTrue(Gui.Control.activeDialog())
        self.assertAlmostEqual(self.trim_of(body).TrimGap.Value, 2.0)
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertIsNone(panel.target)


class DrillHoleOrderTest(MidpointFixture):
    def setUp(self):
        super().setUp()
        self.hooks, _ = hook_execute(self, drill_hole.DrillHole)

    def test_a_diameter_typed_a_vertex_clicked_and_ok_during_the_recompute_keep_the_click(self):
        body, panel, obj, before = self.previewed_panel()
        far = self.vertex_at(body, FAR_CORNER)
        returned = []

        def type_click_ok(fp):
            panel.form.spin_diameter.setValue(8.0)
            wait(INSIDE)
            self.click(body, far)
            returned.append(panel.accept())

        self.hooks.append(type_click_ok)
        panel.form.spin_diameter.setValue(6.0)
        wait(SETTLE)

        self.assertEqual([False], returned)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(far, obj.ReferenceVertex)
        self.assertAlmostEqual(obj.Diameter.Value, 8.0, places=6)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_pressed_during_the_recompute_drops_the_preview(self):
        body, panel, obj, before = self.previewed_panel()
        returned = []

        def type_and_cancel(fp):
            panel.form.spin_diameter.setValue(8.0)
            wait(INSIDE)
            returned.append(panel.reject())

        self.hooks.append(type_and_cancel)
        panel.form.spin_diameter.setValue(6.0)
        wait(SETTLE)

        self.assertEqual([False], returned)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(self.new_objects(before), [])
        self.assertEqual(self.doc.UndoCount, 0)


if __name__ == "__main__":
    unittest.main()

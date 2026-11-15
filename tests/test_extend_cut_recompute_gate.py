"""Extend / Cut panel: no geometry while its own recompute runs (odd/tasks/panel-recompute-deadlock.md, S1, S3, S4).

FreeCAD's progress bar pumps Qt events inside a recompute (L2): the hooks below type in the Gap, let the preview
timer fire, click and press OK or Cancel there. None of it may run geometry then; it waits for the recompute to end,
and the preview ends matching the last values.
"""

import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from test_extend_cut_geometry import FAR, NEAR
from test_extend_cut_preview import wait
from test_keep_end_panel import KeepEndFixture
from test_recompute_gate import during, hook_execute, watch

from freecad.maxproframe import create_extend_cut_tool
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS
from freecad.maxproframe.create_extend_cut_tool import ExtendCutTaskPanel, make_extend_cut_profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# Long enough for the preview timer to fire inside the recompute.
INSIDE = 3 * GAP_DELAY_MS / 1000
# The preview delay, the recompute and the one that follows it, with room for a loaded machine.
SETTLE = 2.0
# The longest wait for the hooked recompute to start (a first test in a cold FreeCAD may be slow).
START = 10.0


class ExtendCutRecomputeGateTest(KeepEndFixture):
    def setUp(self):
        super().setUp()
        self.hooks, state = hook_execute(self, TrimmedProfile)
        geometry = watch(
            self, create_extend_cut_tool, ("_cut_off_piece", "_edge_lines", "parallel_problem", "fold_problem"), state
        )
        recomputes = watch(self, ExtendCutTaskPanel, ("_retarget", "_rebuild_preview", "_preview_edit"), state)
        self.calls = (geometry, recomputes)

    def settle(self):
        """Let the hooked recompute start, then the preview delay and the recomputes after it pass."""
        deadline = time.monotonic() + START
        while self.hooks and time.monotonic() < deadline:
            wait(0.1)
        wait(SETTLE)

    def ran_during(self):
        return during(self.calls[0]) + during(self.calls[1])

    def existing(self, gap=0.0):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)), gap)
        self.doc.recompute()
        self.doc.clearUndos()
        return target, face, body, obj

    def type_inside(self, panel, gap):
        """A hook: ``gap`` typed in the Gap, and the preview timer due, inside the recompute."""

        def type_gap(fp):
            panel.form.sb_gap.setValue(gap)
            wait(INSIDE)

        return type_gap

    def test_a_gap_typed_while_the_edit_recomputes_waits_for_it_and_is_previewed_then(self):
        # S1, L1: editing a trim, the Gap typed while its preview recomputes.
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.hooks.append(self.type_inside(panel, 2.0))

        panel.form.sb_gap.setValue(1.0)
        self.settle()

        self.assertEqual([], self.hooks)
        self.assertEqual([], self.ran_during())
        self.assertIn(("_cut_off_piece", False), self.calls[0])
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR - 2.0))
        self.assertEqual("Preview updated", self.status(panel))
        self.assertEqual("", self.message(panel))
        self.assertTrue(panel.accept())
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_the_preview_timer_due_while_a_flip_recomputes_runs_once_it_ends(self):
        # L2: a button recomputes the edited trim; the Gap typed meanwhile and its preview timer fire inside.
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.hooks.append(self.type_inside(panel, 2.0))

        self.flip_rows(panel, 0)
        self.settle()

        self.assertEqual([], self.hooks)
        self.assertEqual([], self.ran_during())
        self.assertEqual(obj.KeepEnd, "End")
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertEqual(self.box(obj.Shape), (NEAR + 2.0, 500.0))
        [(trim, piece)] = panel.discarded()
        self.assertEqual(self.box(piece), (0.0, NEAR + 2.0))
        self.assertEqual("Preview updated", self.status(panel))
        self.assertEqual("", self.message(panel))

    def test_a_target_clicked_while_the_edit_recomputes_is_taken_once_it_ends(self):
        target, face, body, obj = self.existing(gap=1.0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        far = self.face_towards(target, App.Vector(1, 0, 0))
        self.hooks.append(lambda fp: self.click(target, far))

        panel.form.sb_gap.setValue(3.0)
        self.settle()

        self.assertEqual([], self.ran_during())
        self.assertEqual(panel.target, (target, (far,)))
        self.assertEqual(obj.TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.box(obj.Shape), (0.0, FAR - 3.0))
        self.assertEqual("Preview updated", self.status(panel))

    def test_cancel_pressed_while_the_edit_recomputes_puts_the_trim_back_once_it_ends(self):
        target, face, body, obj = self.existing(gap=1.0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        returned = []

        def type_and_cancel(fp):
            self.type_inside(panel, 2.0)(fp)
            returned.append(panel.reject())

        self.hooks.append(type_and_cancel)

        panel.form.sb_gap.setValue(4.0)
        self.settle()

        self.assertEqual([False], returned)
        self.assertEqual([], self.ran_during())
        self.assertFalse(Gui.Control.activeDialog())
        self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR - 1.0))
        self.assertEqual(self.doc.UndoCount, 0)

    def test_ok_pressed_while_the_preview_recomputes_creates_the_trim_with_the_last_gap_once_it_ends(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        returned = []

        def type_and_ok(fp):
            self.type_inside(panel, 2.0)(fp)
            returned.append(panel.accept())

        self.hooks.append(type_and_ok)

        panel.form.sb_gap.setValue(1.0)
        self.settle()

        self.assertEqual([False], returned)
        self.assertEqual([], self.ran_during())
        self.assertFalse(Gui.Control.activeDialog())
        trim = self.trim_of(body)
        self.assertAlmostEqual(trim.TrimGap.Value, 2.0)
        self.assertEqual(self.box(trim.Shape), (0.0, NEAR - 2.0))
        self.assertEqual(trim.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoCount, 1)

    def test_preview_and_ok_without_a_recompute_in_between_are_unchanged(self):
        # S4: the Gap previewed after the delay, OK keeping it in one Undo step.
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        panel.form.sb_gap.setValue(2.0)
        self.assertEqual("Pending changes", self.status(panel))
        wait()
        self.assertEqual("Preview updated", self.status(panel))
        self.assertEqual(self.box(self.trim_of(body).Shape), (0.0, NEAR - 2.0))
        self.assertTrue(panel.accept())
        self.assertEqual(self.box(self.trim_of(body).Shape), (0.0, NEAR - 2.0))
        self.assertEqual(self.doc.UndoCount, 1)


if __name__ == "__main__":
    unittest.main()

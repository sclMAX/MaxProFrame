"""The order in which the recompute gate runs what waited (odd/tasks/panel-recompute-deadlock.md, S3, S4): a button
pressed during a recompute runs after every work queued before it, also the work queued while a queued work holds
the gate again; an error keeps neither the rest of the queue nor the button from running."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from freecad.maxproframe import recompute_gate
from freecad.maxproframe.recompute_gate import RecomputeGate


class RecomputeGateOrderTest(unittest.TestCase):
    def setUp(self):
        self.ran = []
        self.active = True
        self.gate = RecomputeGate(lambda: self.active)
        control = SimpleNamespace(activeDialog=lambda: True, closeDialog=lambda: self.ran.append("closed"))
        patcher = patch.object(recompute_gate.Gui, "Control", control)
        patcher.start()
        self.addCleanup(patcher.stop)

    def work(self, name):
        return lambda: self.ran.append(name)

    def ok(self):
        """OK: it runs and closes the panel."""
        self.ran.append("ok")
        self.active = False
        return True

    def preview_again(self):
        """A queued preview: it recomputes, holding the gate again; a click arrives meanwhile."""
        self.ran.append("preview")
        with self.gate.hold():
            self.gate.wait(self.work("click during the preview"))

    def test_a_button_runs_after_the_whole_queue_when_a_queued_work_holds_the_gate_again(self):
        with self.gate.hold():
            self.gate.wait(self.preview_again)
            self.gate.wait(self.work("click"))
            self.gate.defer(self.ok)
        self.assertEqual(["preview", "click", "click during the preview", "ok", "closed"], self.ran)
        self.assertFalse(self.gate.held)

    def test_a_button_pressed_while_a_queued_work_holds_the_gate_again_runs_after_the_queue(self):
        def preview_and_ok():
            self.ran.append("preview")
            with self.gate.hold():
                self.assertTrue(self.gate.defer(self.ok))

        with self.gate.hold():
            self.gate.wait(preview_and_ok)
            self.gate.wait(self.work("click"))
        self.assertEqual(["preview", "click", "ok", "closed"], self.ran)

    def test_an_error_in_a_queued_work_keeps_neither_the_rest_nor_the_button_from_running(self):
        def fail():
            self.ran.append("fail")
            raise ValueError("queued work failed")

        with self.assertRaisesRegex(ValueError, "queued work failed"):
            with self.gate.hold():
                self.gate.wait(fail)
                self.gate.wait(self.work("click"))
                self.gate.defer(self.ok)
        self.assertEqual(["fail", "click", "ok", "closed"], self.ran)
        self.assertFalse(self.gate.held)
        # Nothing is left to run at the next release.
        self.active = True
        self.ran = []
        with self.gate.hold():
            pass
        self.assertEqual([], self.ran)

    def test_an_error_inside_the_hold_leaves_the_queue_for_the_next_release(self):
        with self.assertRaises(ValueError):
            with self.gate.hold():
                self.gate.wait(self.work("a"))
                raise ValueError
        self.assertEqual([], self.ran)
        with self.gate.hold():
            pass
        self.assertEqual(["a"], self.ran)


if __name__ == "__main__":
    unittest.main()

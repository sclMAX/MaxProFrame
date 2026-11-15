"""The recompute gate of the task panels (odd/tasks/panel-recompute-deadlock.md, S3), and the test hooks that run
keys, timers and clicks inside a recompute, as FreeCAD's progress bar does when it pumps Qt events."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from freecad.maxproframe import recompute_gate
from freecad.maxproframe.recompute_gate import RecomputeGate


def hook_execute(test, proxy_class):
    """(hooks, state): each hook runs once, in order, inside the next recompute of an object of ``proxy_class``,
    right after its execute, while ``state.during`` is True.

    Call it before the objects are made: FreeCAD keeps the execute it finds on a new object.
    """
    execute = proxy_class.execute
    hooks = []
    state = SimpleNamespace(during=False)

    def execute_and_hook(proxy, fp):
        result = execute(proxy, fp)
        if hooks and not state.during:
            hook = hooks.pop(0)
            state.during = True
            try:
                hook(fp)
            finally:
                state.during = False
        return result

    patcher = patch.object(proxy_class, "execute", execute_and_hook)
    patcher.start()
    test.addCleanup(patcher.stop)
    return hooks, state


def watch(test, owner, names, state):
    """[(name, whether it ran during the hooked recompute)] of every call to the attributes ``names`` of ``owner``:
    geometry run there waits forever for the threads of the recompute's own boolean (L2)."""
    calls = []
    for name in names:
        real = getattr(owner, name)

        def watched(*args, real=real, name=name, **kwargs):
            calls.append((name, state.during))
            return real(*args, **kwargs)

        patcher = patch.object(owner, name, watched)
        patcher.start()
        test.addCleanup(patcher.stop)
    return calls


def during(calls):
    """The names of ``calls`` that ran during the hooked recompute."""
    return [name for name, inside in calls if inside]


class RecomputeGateTest(unittest.TestCase):
    def setUp(self):
        self.active = True
        self.gate = RecomputeGate(lambda: self.active)
        self.ran = []

    def work(self, name):
        def run():
            self.ran.append(name)

        return run

    def test_work_runs_at_once_while_the_gate_is_free(self):
        self.assertFalse(self.gate.held)
        self.assertFalse(self.gate.wait(self.work("a")))
        self.assertFalse(self.gate.defer(self.work("ok")))
        self.assertEqual([], self.ran)

    def test_work_asked_for_while_held_runs_in_order_once_the_outermost_hold_ends(self):
        first, second = self.work("first"), self.work("second")
        with self.gate.hold():
            self.assertTrue(self.gate.held)
            self.assertTrue(self.gate.wait(first))
            with self.gate.hold():
                self.assertTrue(self.gate.wait(second))
                # The same work asked for again runs once.
                self.assertTrue(self.gate.wait(first))
            self.assertEqual([], self.ran)
        self.assertFalse(self.gate.held)
        self.assertEqual(["first", "second"], self.ran)

    def test_work_that_holds_the_gate_again_runs_what_it_queued_once_it_ends(self):
        def recompute_again():
            self.ran.append("again")
            with self.gate.hold():
                self.gate.wait(self.work("after again"))

        with self.gate.hold():
            self.gate.wait(recompute_again)
        self.assertEqual(["again", "after again"], self.ran)

    def test_a_button_pressed_while_held_runs_after_the_queued_work_and_closes_the_dialog_when_it_accepts(self):
        control = SimpleNamespace(activeDialog=lambda: True, closeDialog=lambda: self.ran.append("closed"))
        with patch.object(recompute_gate.Gui, "Control", control):
            for returned, expected in ((True, ["work", "button", "closed"]), (False, ["work", "button"])):
                with self.subTest(returned=returned):
                    self.ran = []

                    def button(returned=returned):
                        self.ran.append("button")
                        return returned

                    with self.gate.hold():
                        self.assertTrue(self.gate.defer(button))
                        self.gate.wait(self.work("work"))
                    self.assertEqual(expected, self.ran)

    def test_nothing_waiting_runs_once_the_panel_closed_or_cleared(self):
        with self.gate.hold():
            self.gate.wait(self.work("closed"))
            self.gate.defer(self.work("button"))
            self.active = False
        self.active = True
        with self.gate.hold():
            self.gate.wait(self.work("cleared"))
            self.gate.defer(self.work("button"))
            self.gate.clear()
        self.assertEqual([], self.ran)

    def test_an_error_inside_the_hold_frees_the_gate(self):
        with self.assertRaises(ValueError):
            with self.gate.hold():
                self.gate.wait(self.work("a"))
                raise ValueError
        self.assertFalse(self.gate.held)


if __name__ == "__main__":
    unittest.main()

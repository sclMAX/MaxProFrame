"""Keep a task panel from running geometry while its own recompute runs (odd/tasks/panel-recompute-deadlock.md, S3).

FreeCAD's progress bar pumps Qt events inside a recompute: a timer of the panel, a key typed or a click then runs
inside it. An OCC boolean run there (a cut, a nested recompute) waits forever for the threads the paused boolean of
the recompute holds, and FreeCAD freezes. While the gate is held, the panel queues that work instead of running it:
the values typed still reach the panel, and the queued work runs, in order, once the outermost hold ends, so the
panel ends matching its last values. A dialog button (OK, Cancel, Apply) pressed meanwhile runs after all of it,
also after the work queued while a queued work recomputes again.
"""

import contextlib
from functools import partial

import FreeCADGui as Gui


class RecomputeGate:
    """Held while a panel recomputes; what the panel is asked to do meanwhile waits for the hold to end.

    ``active`` tells whether the panel still runs: queued work is dropped once it closed.
    """

    def __init__(self, active):
        self._active = active
        self._depth = 0
        self._waiting = []
        self._button = None
        # Whether the queue is being run: a hold ending meanwhile leaves what it queued to that run.
        self._releasing = False

    @property
    def held(self):
        """Whether a recompute of the panel runs."""
        return self._depth > 0

    @contextlib.contextmanager
    def hold(self):
        """Hold the gate for the block (a recompute of the panel and its follow-up); then run what waited."""
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
        if not self._depth:
            self._release()

    def wait(self, work):
        """Whether ``work`` waits for the recompute to end, to run once then: an equal work queued already runs once."""
        if not self.held:
            return False
        if work not in self._waiting:
            self._waiting.append(work)
        return True

    def defer(self, button):
        """Whether a dialog button waits for the recompute to end; ``button`` then runs after the queued work, the
        last one pressed, and closes the dialog when it returns True (FreeCAD took False for it meanwhile)."""
        if not self.held:
            return False
        self._button = button
        return True

    def clear(self):
        """Drop what waits: the panel closed."""
        self._waiting = []
        self._button = None

    def _release(self):
        """Run what waited, in order, then the button: only from the outermost release, so a queued work that holds
        the gate again neither runs the button before the rest of the queue nor the rest before what it queued.

        A work that raises does not stop the others nor the button: the first error is raised once they ran.
        """
        if self._releasing:
            return
        self._releasing = True
        error = None
        try:
            while self._waiting or self._button is not None:
                if self._waiting:
                    work = self._waiting.pop(0)
                else:
                    work, self._button = partial(self._press, self._button), None
                if not self._active():
                    continue
                try:
                    work()
                except Exception as exception:
                    error = error or exception
        finally:
            self._releasing = False
        if error is not None:
            raise error

    @staticmethod
    def _press(button):
        """Run the deferred ``button``; close the dialog when it accepts (FreeCAD took False for it meanwhile)."""
        if button() and Gui.Control.activeDialog():
            Gui.Control.closeDialog()

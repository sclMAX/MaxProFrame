"""Bounded, read-only native CI evidence. Never pump events or answer dialogs."""

import faulthandler
import json
import pathlib
import sys
import time
from collections import deque


def modal_snapshot(app):
    """Only structural state; deliberately exclude titles, text and object names."""
    try:
        active = app.activeModalWidget()
        windows = []
        for widget in app.topLevelWidgets()[:32]:
            windows.append(
                {
                    "class": str(widget.metaObject().className())[:80],
                    "visible": bool(widget.isVisible()),
                    "modal": bool(widget.isModal()),
                }
            )
        return {
            "active_modal": str(active.metaObject().className())[:80] if active else None,
            "windows": windows,
        }
    except Exception:
        return {"unavailable": True}


class Session:
    def __init__(self, directory, qt, widgets):
        self.stack_file = open(pathlib.Path(directory) / "python-stacks.log", "wb")
        self.timer = None
        self.count = 0
        self.started = time.monotonic()
        self.path = pathlib.Path(directory) / "modal-state.jsonl"
        # One dump, not periodic: CPython bounds dumps to 100 threads, 100
        # frames/thread and 500 characters/string. No locals or source lines.
        try:
            faulthandler.dump_traceback_later(120, repeat=False, file=self.stack_file)
        except Exception:
            self.stack_file.close()
            raise
        if qt is not None and widgets is not None:
            self.attach_qt(qt, widgets)

    def attach_qt(self, qt, widgets):
        self.timer = qt.QTimer()
        self.timer.timeout.connect(lambda: self.snapshot(widgets.QApplication.instance()))
        self.timer.start(30000)

    def snapshot(self, app):
        if self.count >= 12:
            return
        self.count += 1
        try:
            state = modal_snapshot(app)
            state["elapsed_seconds"] = round(time.monotonic() - self.started, 1)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(state, ensure_ascii=True) + "\n")
        except Exception:
            pass
        if self.count == 12 and self.timer is not None:
            self.timer.stop()

    def stop(self):
        if self.timer is not None:
            self.timer.stop()
        faulthandler.cancel_dump_traceback_later()
        self.stack_file.close()


def event_number(value):
    """PySide6 enums expose .value; PySide2 also accepts integer conversion."""
    return int(getattr(value, "value", value))


class StructuralObserver:
    def __init__(self, directory):
        self.path = pathlib.Path(directory) / "qt-events.jsonl"
        self.count = 0
        self.errors = set()
        self.ordinary = []
        self.modal = deque(maxlen=64)
        self.failures = []
        self.started = time.monotonic()

    def record(self, widget, kind):
        try:
            state = {
                "event": event_number(kind),
                "class": str(widget.metaObject().className())[:80],
                "visible": bool(widget.isVisible()),
                "modal": bool(widget.isModal()),
            }
        except Exception as exc:
            self.failure("event", exc)
            return
        self.write(state)

    def failure(self, phase, exc):
        key = (phase, type(exc).__name__[:80])
        if key not in self.errors and len(self.errors) < 16:
            self.errors.add(key)
            self.write({"phase": phase, "error": key[1]})

    def write(self, state):
        if "error" in state:
            if len(self.failures) >= 16:
                return
            self.failures.append(state)
        elif state.get("modal"):
            self.modal.append(state)
        else:
            if len(self.ordinary) >= 192:
                return
            self.ordinary.append(state)
        self.count = len(self.ordinary) + len(self.modal) + len(self.failures)
        state["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        # Reserve modal tail and error capacity: startup widgets cannot consume it.
        rows = sorted([*self.ordinary, *self.modal, *self.failures], key=lambda row: row["elapsed_seconds"])
        try:
            with self.path.open("w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
        except OSError as exc:
            key = ("write", type(exc).__name__[:80])
            if key not in self.errors:
                self.errors.add(key)
                sys.stderr.write(json.dumps({"phase": key[0], "error": key[1]}) + "\n")


def attach_structural(session, qt, widgets, directory):
    """Install a passive, retained application event filter in manual mode only."""
    observer = StructuralObserver(directory)
    kinds = {
        event_number(getattr(qt.QEvent, name))
        for name in ("Show", "Hide", "Close", "WindowBlocked", "WindowUnblocked")
    }

    class Filter(qt.QObject):
        def eventFilter(self, watched, event):
            try:
                kind = event_number(event.type())
                if kind in kinds and isinstance(watched, widgets.QWidget):
                    observer.record(watched, kind)
            except Exception as exc:
                observer.failure("callback", exc)
            return False

    session.event_filter = Filter()
    session.observer = observer
    app = widgets.QApplication.instance()
    app.installEventFilter(session.event_filter)
    session.snapshot(app)


def start(directory, qt=None, widgets=None):
    return Session(directory, qt, widgets)

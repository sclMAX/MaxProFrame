"""Bounded, read-only native CI evidence. Never pump events or answer dialogs."""

import faulthandler
import json
import pathlib
import time


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


def start(directory, qt=None, widgets=None):
    return Session(directory, qt, widgets)

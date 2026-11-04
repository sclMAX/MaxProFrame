"""Deterministic diagnostics tests; no native Qt dependency."""

import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci import diagnostics


class TestDiagnostics(unittest.TestCase):
    def test_snapshot_is_read_only_bounded_and_excludes_widget_text(self):
        widget = mock.Mock()
        widget.metaObject.return_value.className.return_value = "QMessageBox"
        widget.isVisible.return_value = True
        widget.isModal.return_value = True
        app = mock.Mock()
        app.activeModalWidget.return_value = widget
        app.topLevelWidgets.return_value = [widget] * 100
        snapshot = diagnostics.modal_snapshot(app)
        self.assertEqual(snapshot["active_modal"], "QMessageBox")
        self.assertEqual(len(snapshot["windows"]), 32)
        self.assertEqual(snapshot["windows"][0], {"class": "QMessageBox", "visible": True, "modal": True})
        for forbidden in ("accept", "reject", "close", "done", "text", "windowTitle", "objectName"):
            getattr(widget, forbidden).assert_not_called()
        app.processEvents.assert_not_called()

    def test_one_shot_stack_dump_and_bounded_timer_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            timer = mock.Mock()
            qt = mock.Mock()
            qt.QTimer.return_value = timer
            widgets = mock.Mock()
            widgets.QApplication.instance.return_value = mock.Mock()
            with (
                mock.patch.object(diagnostics.faulthandler, "dump_traceback_later") as arm,
                mock.patch.object(diagnostics.faulthandler, "enable") as enable,
            ):
                session = diagnostics.start(directory, qt, widgets)
                arm.assert_called_once_with(120, repeat=False, file=session.stack_file)
                enable.assert_called_once_with(file=session.stack_file, all_threads=True)
            callback = timer.timeout.connect.call_args.args[0]
            for _ in range(20):
                callback()
            lines = (pathlib.Path(directory) / "modal-state.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 12)
            timer.stop.assert_called()
            with (
                mock.patch.object(diagnostics.faulthandler, "cancel_dump_traceback_later") as cancel,
                mock.patch.object(diagnostics.faulthandler, "disable") as disable,
            ):
                session.stop()
                cancel.assert_called_once_with()
                disable.assert_called_once_with()
            self.assertTrue(session.stack_file.closed)

    def test_a_native_crash_writes_the_python_stack_of_every_thread(self):
        # A SIGSEGV in a native test leaves no other trace of the Python code that ran into it (#69).
        root = pathlib.Path(__file__).resolve().parents[2]
        script = (
            "import faulthandler, sys\n"
            "from ci import diagnostics\n"
            "diagnostics.start(sys.argv[1])\n"
            "def crashing_test():\n"
            "    faulthandler._sigsegv()\n"
            "crashing_test()\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.run(
                [sys.executable, "-c", script, directory], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertNotEqual(proc.returncode, 0)
            stacks = (pathlib.Path(directory) / "python-stacks.log").read_text(encoding="utf-8", errors="replace")
        self.assertIn("Fatal Python error: Segmentation fault", stacks)
        self.assertIn("line 5 in crashing_test", stacks)
        self.assertIn("(most recent call first)", stacks)

    def test_qt_snapshot_failure_is_nonfatal_and_does_not_record_exception_text(self):
        app = mock.Mock()
        app.activeModalWidget.side_effect = RuntimeError("private text")
        self.assertEqual(diagnostics.modal_snapshot(app), {"unavailable": True})

"""Deterministic diagnostics tests; no native Qt dependency."""

import pathlib
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
            with mock.patch.object(diagnostics.faulthandler, "dump_traceback_later") as arm:
                session = diagnostics.start(directory, qt, widgets)
                arm.assert_called_once_with(120, repeat=False, file=session.stack_file)
            callback = timer.timeout.connect.call_args.args[0]
            for _ in range(20):
                callback()
            lines = (pathlib.Path(directory) / "modal-state.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 12)
            timer.stop.assert_called()
            with mock.patch.object(diagnostics.faulthandler, "cancel_dump_traceback_later") as cancel:
                session.stop()
                cancel.assert_called_once_with()
            self.assertTrue(session.stack_file.closed)

    def test_qt_snapshot_failure_is_nonfatal_and_does_not_record_exception_text(self):
        app = mock.Mock()
        app.activeModalWidget.side_effect = RuntimeError("private text")
        self.assertEqual(diagnostics.modal_snapshot(app), {"unavailable": True})

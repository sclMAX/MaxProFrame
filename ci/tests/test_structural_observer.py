"""Deterministic structural Qt observer boundaries without native Qt."""

import enum
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from ci import diagnostics


class TestStructuralObserver(unittest.TestCase):
    def test_filter_enum_callback_is_passive_and_error_is_observable(self):
        class Event(enum.Enum):
            Show = 17
            Hide = 18
            Close = 19
            WindowBlocked = 20
            WindowUnblocked = 21

        class Widget:
            def metaObject(self):
                return types.SimpleNamespace(className=lambda: "QDialog")

            def isVisible(self):
                return True

            def isModal(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            app = mock.Mock()
            session = mock.Mock()
            qt = types.SimpleNamespace(QObject=object, QEvent=Event)
            widgets = types.SimpleNamespace(QWidget=Widget, QApplication=mock.Mock(instance=lambda: app))
            diagnostics.attach_structural(session, qt, widgets, directory)
            app.installEventFilter.assert_called_once_with(session.event_filter)
            session.snapshot.assert_called_once_with(app)
            event = types.SimpleNamespace(type=lambda: Event.Show)
            self.assertFalse(session.event_filter.eventFilter(Widget(), event))
            event = mock.Mock()
            event.type.side_effect = TypeError("private dialog body")
            for _ in range(100):
                self.assertFalse(session.event_filter.eventFilter(Widget(), event))
            rows = [json.loads(line) for line in session.observer.path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["event"], 17)
            self.assertEqual(rows[1]["phase"], "callback")
            self.assertEqual(rows[1]["error"], "TypeError")
            self.assertNotIn("private", session.observer.path.read_text())
            app.processEvents.assert_not_called()

    def test_write_failure_reports_only_structural_metadata_once(self):
        observer = diagnostics.StructuralObserver("/unused")
        with mock.patch.object(pathlib.Path, "open", side_effect=OSError("private")), mock.patch(
            "sys.stderr.write"
        ) as stderr:
            for _ in range(1000):
                observer.write({"event": 17})
        stderr.assert_called_once_with('{"phase": "write", "error": "OSError"}\n')
        self.assertEqual(observer.count, 192)

    def test_enum_boundary_and_bounded_errors(self):
        class Event(enum.Enum):
            Show = 17

        self.assertEqual(diagnostics.event_number(Event.Show), 17)
        self.assertEqual(diagnostics.event_number(17), 17)
        with tempfile.TemporaryDirectory() as directory:
            observer = diagnostics.StructuralObserver(directory)
            widget = mock.Mock()
            widget.metaObject.side_effect = TypeError("private body")
            for _ in range(1000):
                observer.record(widget, Event.Show)
            rows = [json.loads(line) for line in observer.path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["error"], "TypeError")
            self.assertEqual(rows[0]["phase"], "event")
            self.assertNotIn("private", observer.path.read_text())

    def test_startup_saturation_preserves_later_modal_tail_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            observer = diagnostics.StructuralObserver(directory)
            ordinary = {"event": 17, "class": "QWidget", "modal": False}
            for _ in range(1000):
                observer.write(dict(ordinary))
            observer.failure("event", TypeError("private"))
            for number in range(1000):
                observer.write({"event": 17, "class": "QDialog", "modal": True, "sequence": number})
            observer.write({"event": 17, "class": "QMessageBox", "modal": True})
            rows = [json.loads(line) for line in observer.path.read_text().splitlines()]
            self.assertTrue(any(row.get("class") == "QMessageBox" for row in rows))
            self.assertTrue(any(row.get("error") == "TypeError" for row in rows))
            self.assertLessEqual(len(rows), 272)
            self.assertEqual(sum(row.get("modal") is True for row in rows), 64)
            self.assertEqual(sum(row.get("modal") is False for row in rows), 192)

    def test_success_is_structural_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            observer = diagnostics.StructuralObserver(directory)
            widget = mock.Mock()
            widget.metaObject.return_value.className.return_value = "QDialog"
            widget.isVisible.return_value = True
            widget.isModal.return_value = True
            for _ in range(1000):
                observer.record(widget, 17)
            rows = observer.path.read_text().splitlines()
            self.assertEqual(len(rows), 64)
            self.assertEqual(json.loads(rows[0])["class"], "QDialog")
            widget.text.assert_not_called()
            widget.windowTitle.assert_not_called()
            widget.close.assert_not_called()

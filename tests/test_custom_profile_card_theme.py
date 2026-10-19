"""Native Qt checks for palette-aware custom profile cards."""

import os
import unittest
from types import SimpleNamespace

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.custom_profile_cards import CustomProfileCard


def _log_checkpoint(marker: str) -> None:
    reports_dir = os.environ.get("FF_REPORTS")
    if not reports_dir:
        return
    try:
        os.makedirs(reports_dir, exist_ok=True)
        log_path = os.path.join(reports_dir, "theme-fixture.log")
        with open(log_path, "a", encoding="ascii") as f:
            f.write(f"{marker}\n")
            f.flush()
    except Exception:
        pass


class TestCustomProfileCardTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.original_palette = QtGui.QPalette(self.app.palette())
        self.parent = QtWidgets.QWidget()
        self.parent.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        self.selected = []
        self.card = CustomProfileCard(
            2,
            "CP2",
            "10.31",
            {},
            SimpleNamespace(current_lib_meta={"is_user": True}),
            SimpleNamespace(select_card=self.selected.append),
            self.parent,
        )
        QtWidgets.QVBoxLayout(self.parent).addWidget(self.card)

    def tearDown(self):
        try:
            if hasattr(self, "original_palette") and self.original_palette is not None:
                _log_checkpoint("before: app.setPalette restore")
                self.app.setPalette(self.original_palette)
                _log_checkpoint("after: app.setPalette restore")
        finally:
            try:
                if hasattr(self, "card") and self.card is not None:
                    try:
                        self.app.paletteChanged.disconnect(self.card._on_palette_changed)
                    except Exception:
                        pass
            finally:
                if hasattr(self, "parent") and self.parent is not None:
                    _log_checkpoint("before: delete cleanup")
                    self.parent.close()
                    self.parent.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(self.parent, QtCore.QEvent.DeferredDelete)
                    _log_checkpoint("after: delete cleanup")

    def _polish_and_layout(self):
        _log_checkpoint("before: local polish/layout")
        self.parent.ensurePolished()
        self.card.ensurePolished()
        for child in self.card.findChildren(QtWidgets.QWidget):
            child.ensurePolished()
        parent_layout = self.parent.layout()
        if parent_layout is not None:
            parent_layout.activate()
        card_layout = self.card.layout()
        if card_layout is not None:
            card_layout.activate()
        self.parent.adjustSize()
        _log_checkpoint("after: local polish/layout")

    def apply_theme(self, dark):
        palette = QtGui.QPalette(self.app.palette())
        colors = {
            QtGui.QPalette.Window: "#303030" if dark else "#eeeeee",
            QtGui.QPalette.WindowText: "#eeeeee" if dark else "#202020",
            QtGui.QPalette.Base: "#202020" if dark else "#ffffff",
            QtGui.QPalette.Text: "#ffffff" if dark else "#101010",
            QtGui.QPalette.AlternateBase: "#404040" if dark else "#dddddd",
            QtGui.QPalette.Mid: "#808080",
            QtGui.QPalette.Highlight: "#225588",
            QtGui.QPalette.HighlightedText: "#ffffff",
        }
        for role, color in colors.items():
            palette.setColor(role, QtGui.QColor(color))
        _log_checkpoint(f"before: app.setPalette dark={dark}")
        self.app.setPalette(palette)
        _log_checkpoint(f"after: app.setPalette dark={dark}")
        self._polish_and_layout()
        return palette

    def assert_theme(self, palette, selected):
        self._polish_and_layout()
        background = QtGui.QPalette.Highlight if selected else QtGui.QPalette.Window
        foreground = QtGui.QPalette.HighlightedText if selected else QtGui.QPalette.WindowText
        _log_checkpoint("before: card.grab")
        image = self.card.grab().toImage()
        _log_checkpoint("after: card.grab")
        self.assertEqual(image.pixelColor(5, 5).name(), palette.color(background).name())
        labels = [label for label in self.card.findChildren(QtWidgets.QLabel) if label is not self.card.thumbnail_label]
        self.assertEqual(len(labels), 3)
        for label in labels:
            self.assertEqual(label.palette().color(QtGui.QPalette.WindowText).name(), palette.color(foreground).name())
        for editor in (self.card.code_edit, self.card.weight_edit):
            self.assertEqual(
                editor.palette().color(QtGui.QPalette.Text).name(), palette.color(QtGui.QPalette.Text).name()
            )
            role = QtGui.QPalette.AlternateBase if editor.isReadOnly() else QtGui.QPalette.Base
            self.assertEqual(editor.palette().color(QtGui.QPalette.Base).name(), palette.color(role).name())
        self.assertEqual(
            self.card.thumbnail_label.palette().color(QtGui.QPalette.Window).name(),
            palette.color(QtGui.QPalette.Base).name(),
        )

    def test_light_and_dark_selected_editable_and_readonly(self):
        _log_checkpoint("test-entry: test_light_and_dark_selected_editable_and_readonly")
        for dark in (False, True):
            for editable in (True, False):
                for selected in (False, True):
                    with self.subTest(dark=dark, editable=editable, selected=selected):
                        _log_checkpoint(f"subtest: dark={dark} editable={editable} selected={selected}")
                        palette = self.apply_theme(dark)
                        self.card.set_editable(editable)
                        self.card.setSelected(selected)
                        self.assert_theme(palette, selected)
                        self.assertEqual(self.card.code_edit.isReadOnly(), not editable)
                        self.assertEqual(self.card.weight_edit.isReadOnly(), not editable)
                        self.assertEqual(self.card.code_edit.text(), "CP2")
                        self.assertEqual(self.card.weight_edit.text(), "10.31")
        self.selected.clear()
        self.card.click()
        self.assertEqual(self.selected, [2])
        _log_checkpoint("test-complete: test_light_and_dark_selected_editable_and_readonly")

    def test_live_theme_change_preserves_selection_and_readonly(self):
        _log_checkpoint("test-entry: test_live_theme_change_preserves_selection_and_readonly")
        self.card.set_editable(False)
        self.card.setSelected(True)
        for dark in (True, False, True):
            with self.subTest(dark=dark):
                _log_checkpoint(f"subtest: dark={dark}")
                self.assert_theme(self.apply_theme(dark), True)
                self.assertTrue(self.card.code_edit.isReadOnly())
                self.assertTrue(self.card.weight_edit.isReadOnly())
        _log_checkpoint("test-complete: test_live_theme_change_preserves_selection_and_readonly")

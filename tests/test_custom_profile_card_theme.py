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
        self.assertEqual(len(labels), 0)
        for label in labels:
            self.assertEqual(label.palette().color(QtGui.QPalette.WindowText).name(), palette.color(foreground).name())
        for editor in (self.card.code_edit, self.card.weight_edit):
            self.assertEqual(
                editor.palette().color(QtGui.QPalette.Text).name(),
                palette.color(QtGui.QPalette.Text if editor is self.card.weight_edit else foreground).name()
            )
            self.assertTrue(editor.isReadOnly())
            self.assertFalse(editor.hasFrame())
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
                        self.assertEqual(self.card.btn_edit_properties.isEnabled(), editable)
                        self.assertTrue(self.card.code_edit.isReadOnly())
                        self.assertTrue(self.card.weight_edit.isReadOnly())
                        self.assertEqual(self.card.code_edit.text(), "CP2")
                        self.assertEqual(self.card.weight_edit.text(), "10.31")
        self.selected.clear()
        self.card.click()
        self.assertEqual(self.selected, [2])
        _log_checkpoint("test-complete: test_light_and_dark_selected_editable_and_readonly")

    def test_badge_and_edit_icon_have_subtle_palette_borders(self):
        for dark in (False, True):
            palette = self.apply_theme(dark)
            # A non-blue accent proves the controls follow the theme, not a fixed color.
            palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#a050c0"))
            self.app.setPalette(palette)
            for editable in (False, True):
                self.card.set_editable(editable)
                for selected in (False, True):
                    self.card.setSelected(selected)
                    self._polish_and_layout()
                    for widget, background, foreground in (
                        (self.card.weight_edit, QtGui.QPalette.AlternateBase, QtGui.QPalette.Text),
                        (self.card.btn_edit_properties, QtGui.QPalette.Button, QtGui.QPalette.ButtonText),
                    ):
                        with self.subTest(dark=dark, editable=editable, selected=selected,
                                          widget=widget.objectName()):
                            surface = palette.color(background)
                            ink = palette.color(QtGui.QPalette.Highlight if editable else foreground)
                            strength = 0.55 if editable else 0.3
                            expected = QtGui.QColor(*(
                                round(a * strength + b * (1 - strength))
                                for a, b in zip(ink.getRgb()[:3], surface.getRgb()[:3])
                            ))
                            self.assertIn(f"border: 1px solid {expected.name()};", widget.styleSheet())
                            rendered = widget.grab().toImage()
                            self.assertEqual(rendered.pixelColor(rendered.width() // 2, 0).name(), expected.name())
                    self.assertEqual(self.card.weight_edit._display_lines(), ["10.31 kg/m"])
                    self.assertEqual(self.card.btn_edit_properties.size(), QtCore.QSize(28, 28))

    def test_edit_icon_accent_highlight_requires_enabled_hover_or_focus(self):
        for dark in (False, True):
            palette = self.apply_theme(dark)
            button = self.card.btn_edit_properties
            self.card.set_editable(True)
            accent = palette.color(QtGui.QPalette.Highlight).name()
            for state in ("hover", "focus"):
                self.assertIn(f"QToolButton:enabled:{state}", button.styleSheet())
            self.assertIn(f"border: 1px solid {accent};", button.styleSheet())
            self.card.set_editable(False)
            self.assertFalse(button.isEnabled())
            self.assertNotIn(":hover", button.styleSheet())
            self.assertNotIn(":focus", button.styleSheet())

    def test_thumbnail_badge_and_icon_replace_footer_without_covering_profile(self):
        self._polish_and_layout()
        preview = self.card.thumbnail_label
        button = self.card.btn_edit_properties
        badge = self.card.weight_edit
        self.assertIsInstance(button, QtWidgets.QToolButton)
        self.assertEqual(button.text(), "")
        self.assertFalse(button.icon().isNull())
        self.assertTrue(button.toolTip())
        self.assertEqual(button.accessibleName(), button.toolTip())
        self.assertGreaterEqual(button.width(), 28)
        self.assertGreaterEqual(button.height(), 28)
        self.assertIs(button.parentWidget(), preview)
        self.assertIs(badge.parentWidget(), preview)
        self.assertEqual(self.card.findChildren(QtWidgets.QPushButton), [])
        self.assertLess(button.geometry().center().x(), preview.width() // 2)
        self.assertLess(button.geometry().center().y(), preview.height() // 2)
        self.assertGreater(badge.geometry().center().x(), preview.width() // 2)
        self.assertGreater(badge.geometry().center().y(), preview.height() // 2)
        safe = preview.contentsRect()
        self.assertFalse(safe.intersects(button.geometry()))
        self.assertFalse(safe.intersects(badge.geometry()))
        self.assertGreaterEqual(safe.height(), 60)
        self.assertEqual(self.card.layout().indexOf(button), -1)
        self.assertEqual(self.card.layout().indexOf(badge), -1)
        self.assertEqual(badge._display_lines(), ["10.31 kg/m"])
        self.selected.clear()
        QtWidgets.QApplication.sendEvent(
            badge, QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(3, 3),
                                   QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        )
        self.assertEqual(self.selected, [2])
        for dark in (False, True):
            self.apply_theme(dark)
            self.card.setSelected(dark)
            reports = os.environ.get("FF_REPORTS")
            if reports:
                self.card.grab().save(os.path.join(reports, "card-badge-dark.png" if dark else "card-badge-light.png"))

    def test_data_hierarchy_elision_units_and_uniform_height(self):
        from unittest.mock import patch

        self._polish_and_layout()
        self.assertEqual(self.card.findChildren(QtWidgets.QLabel), [self.card.thumbnail_label])
        self.assertTrue(self.card.code_edit.font().bold())
        self.assertGreater(self.card.code_edit.fontMetrics().height(),
                           self.card.description_edit.fontMetrics().height())
        self.assertGreater(self.card.description_edit.fontMetrics().height(),
                           self.card.weight_edit.fontMetrics().height())
        self.assertTrue(self.card.description_edit.isHidden())
        height = self.card.sizeHint().height()
        self.card.description_edit.setText("A description long enough to wrap over two lines " * 6)
        self._polish_and_layout()
        self.assertFalse(self.card.description_edit.isHidden())
        self.assertEqual(self.card.sizeHint().height(), height)
        lines = self.card.description_edit._display_lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"), lines)
        self.assertGreaterEqual(self.card.description_edit.contentsRect().height(),
                                self.card.description_edit.fontMetrics().height() * 2)
        self.assertEqual(self.card.description_edit.toolTip(), self.card.description_edit.text())
        title = "A very long profile code " * 8
        self.card.code_edit.setText(title)
        self.assertEqual(self.card.code_edit.toolTip(), title)
        self.assertTrue(self.card.code_edit._display_lines()[0].endswith("…"))
        with patch.object(QtWidgets, "QStylePainter") as painter:
            self.card.weight_edit.grab()
        self.assertEqual(painter.return_value.drawText.call_args.args[-1], "10.31 kg/m")
        self.assertEqual(self.card.weight_edit.text(), "10.31")
        reports = os.environ.get("FF_REPORTS")
        if reports:
            self.card.grab().save(os.path.join(reports, "card-hierarchy.png"))
        self.card.description_edit.clear()
        self._polish_and_layout()
        self.assertTrue(self.card.description_edit.isHidden())
        self.assertEqual(self.card.sizeHint().height(), height)

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

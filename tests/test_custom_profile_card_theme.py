"""Native card behavior and layout; mixed-palette pixels live in test_native_card_theme."""

import unittest
from types import SimpleNamespace

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from elision_helpers import font_ellipsis

from freecad.maxproframe.custom_profile_cards import CustomProfileCard


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
        self.app.paletteChanged.disconnect(self.card._on_palette_changed)
        self.parent.close()
        self.parent.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(self.parent, QtCore.QEvent.DeferredDelete)
        self.app.setPalette(self.original_palette)

    def _polish_and_layout(self):
        self.parent.ensurePolished()
        for child in self.parent.findChildren(QtWidgets.QWidget):
            child.ensurePolished()
            if child.layout():
                child.layout().activate()
        self.parent.layout().activate()
        self.parent.adjustSize()
        # Exercise shown-widget palette propagation, as in the native QSS
        # fixture; WA_DontShowOnScreen keeps that lifecycle off screen.
        self.parent.show()
        self.parent.layout().activate()

    def apply_theme(self, dark):
        palette = QtGui.QPalette(self.original_palette)
        for role in (QtGui.QPalette.Window, QtGui.QPalette.Base, QtGui.QPalette.Button):
            palette.setColor(role, QtGui.QColor("#303030" if dark else "#eeeeee"))
        for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
            palette.setColor(role, QtGui.QColor("#eeeeee" if dark else "#202020"))
        self.app.setPalette(palette)
        self._polish_and_layout()
        return palette

    def test_unselected_outline_uses_live_theme_and_selection_stays_stronger(self):
        for dark in (False, True, False):
            self.apply_theme(dark)
            self.parent.setStyleSheet(
                "QFrame#custom_card { background-color: %s; color: %s; border: none; }"
                % (("#303030", "#eeeeee") if dark else ("#eeeeee", "#202020"))
            )
            self._polish_and_layout()
            for editable in (False, True):
                self.card.set_editable(editable)
                self.card.setSelected(False)
                image = self.card.grab().toImage()
                ratio = image.devicePixelRatio()
                x = round(self.card.width() / 2 * ratio)
                background = image.pixelColor(x, round(6 * ratio))
                border = image.pixelColor(x, round(2 * ratio))
                self.assertNotEqual(border, background, "Unselected card needs a visible outline")
                ink = self.card.palette().color(self.card.foregroundRole())
                self.card.setSelected(True)
                selected = self.card.grab().toImage().pixelColor(x, round(2 * ratio))
                self.assertEqual(selected, ink)
                self.assertNotEqual(border, selected, "Selection must remain more prominent")

    def test_light_and_dark_selected_editable_and_readonly(self):
        for dark in (False, True):
            self.apply_theme(dark)
            for editable in (True, False):
                for selected in (False, True):
                    with self.subTest(dark=dark, editable=editable, selected=selected):
                        self.card.set_editable(editable)
                        self.card.setSelected(selected)
                        self.assertEqual(self.card.btn_edit_properties.isEnabled(), editable)
                        for field in (self.card.code_edit, self.card.weight_edit, self.card.description_edit):
                            self.assertTrue(field.isReadOnly())
                            self.assertFalse(field.hasFrame())
                            self.assertEqual(field.focusPolicy(), QtCore.Qt.NoFocus)
                            self.assertEqual(field.styleSheet(), "")
                        self.assertEqual(self.card.code_edit.text(), "CP2")
                        self.assertEqual(self.card.weight_edit.text(), "10.31")
        self.selected.clear()
        self.card.click()
        self.assertEqual(self.selected, [2])

    def test_card_inherits_actual_parent_palette_not_dialog_snapshot(self):
        # Both receivers exist before the first polish/theme change. QSS owns
        # effective palettes, so a requested parent color is not the oracle.
        reference = QtWidgets.QFrame(self.parent)
        reference.setObjectName(self.card.objectName())
        reference.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.parent.layout().addWidget(reference)
        title = QtWidgets.QLabel("CP2", self.card.code_edit.parentWidget())
        title.setObjectName(self.card.code_edit.objectName())
        title.setFont(self.card.code_edit.font())
        title.setTextFormat(QtCore.Qt.PlainText)
        title.setAlignment(self.card.code_edit.alignment())
        title.move(-1000, -1000)
        surfaces = []
        try:
            self._polish_and_layout()
            reference.resize(self.card.size())

            def surface(image):
                ratio = image.devicePixelRatio()
                return image.pixelColor(round(6 * ratio), round(6 * ratio))

            self.assertEqual(surface(self.card.grab().toImage()), surface(reference.grab().toImage()))
            for dark in (False, True, False):
                # Local ancestor QSS exercises real style replacement without
                # changing the application's stylesheet or forcing palettes.
                background, ink = ("#303030", "#eeeeee") if dark else ("#eeeeee", "#202020")
                for phase in ("parent", "qss"):
                    if phase == "parent":
                        inherited = QtGui.QPalette(self.parent.palette())
                        inherited.setColor(QtGui.QPalette.Window, QtGui.QColor(background))
                        inherited.setColor(QtGui.QPalette.WindowText, QtGui.QColor(ink))
                        self.parent.setPalette(inherited)
                    else:
                        self.parent.setStyleSheet(
                            "QFrame#custom_card { background-color: %s; color: %s; }"
                            "QLabel#card_code { color: %s; }" % (background, ink, ink)
                        )
                    for editable in (True, False):
                        for selected in (False, True):
                            with self.subTest(dark=dark, phase=phase, editable=editable, selected=selected):
                                self.card.set_editable(editable)
                                self.card.setSelected(selected)
                                self._polish_and_layout()
                                reference.resize(self.card.size())
                                title.resize(self.card.code_edit.size())
                                actual = self.card.grab().toImage()
                                native = reference.grab().toImage()
                                self.assertEqual(surface(actual), surface(native))
                                actual_text = self.card.code_edit.grab().toImage()
                                native_text = title.grab().toImage()
                                self.assertEqual(actual_text, native_text)
                                self.assertGreater(
                                    len(
                                        {
                                            native_text.pixel(x, y)
                                            for y in range(native_text.height())
                                            for x in range(native_text.width())
                                        }
                                    ),
                                    1,
                                )
                                self.assertEqual(self.card.styleSheet(), "")
                                self.assertEqual(self.card.code_edit.styleSheet(), "")
                                self.assertEqual(self.card.code_edit.text(), "CP2")
                                self.assertEqual(self.card.weight_edit.text(), "10.31")
                                self.assertTrue(self.card.code_edit.isReadOnly())
                                self.assertEqual(self.card.btn_edit_properties.isEnabled(), editable)
                    if phase == "qss":
                        surfaces.append(surface(actual))
            self.assertNotEqual(surfaces[0], surfaces[1])
            self.assertEqual(surfaces[0], surfaces[2])
            self.assertEqual(self.selected, [])
        finally:
            for receiver in (title, reference):
                receiver.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(receiver, QtCore.QEvent.DeferredDelete)

    def test_preview_surface_is_native_across_selection_and_readonly(self):
        mask = QtGui.QPixmap(160, 64)
        mask.fill(QtCore.Qt.transparent)
        self.card.update_thumbnail(mask)
        # Native and custom QLabel share the actual ancestor and polish cohort.
        reference = QtWidgets.QLabel(self.card.thumbnail_label.parentWidget())
        reference.setObjectName(self.card.thumbnail_label.objectName())
        reference.setAlignment(self.card.thumbnail_label.alignment())
        reference.move(-1000, -1000)
        surfaces = []
        try:
            self._polish_and_layout()
            reference.resize(self.card.thumbnail_label.size())

            def surface(image):
                ratio = image.devicePixelRatio()
                return image.pixelColor(round(5 * ratio), round(64 * ratio))

            self.assertEqual(surface(self.card.thumbnail_label.grab().toImage()), surface(reference.grab().toImage()))
            for dark in (False, True, False):
                background = "#303030" if dark else "#eeeeee"
                self.parent.setStyleSheet("QLabel#card_thumbnail { background-color: %s; }" % background)
                for editable in (True, False):
                    for selected in (True, False):
                        with self.subTest(dark=dark, editable=editable, selected=selected):
                            self.card.set_editable(editable)
                            self.card.setSelected(selected)
                            self._polish_and_layout()
                            reference.resize(self.card.thumbnail_label.size())
                            preview = self.card.thumbnail_label.grab().toImage()
                            native = reference.grab().toImage()
                            # Below the overlays and inside the selection border.
                            ratio = preview.devicePixelRatio()
                            actual = preview.pixelColor(round(5 * ratio), round(64 * ratio))
                            expected = native.pixelColor(
                                round(5 * native.devicePixelRatio()), round(64 * native.devicePixelRatio())
                            )
                            self.assertEqual(actual, expected)
                            self.assertEqual(self.card.thumbnail_label.styleSheet(), "")
                            self.assertEqual(self.card.code_edit.text(), "CP2")
                            self.assertEqual(self.card.weight_edit.text(), "10.31")
                            self.assertTrue(self.card.weight_edit.isReadOnly())
                            self.assertEqual(self.card.btn_edit_properties.isEnabled(), editable)
                surfaces.append(actual)
            self.assertNotEqual(surfaces[0], surfaces[1])
            self.assertEqual(surfaces[0], surfaces[2])
            self.assertEqual(self.selected, [])
        finally:
            reference.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(reference, QtCore.QEvent.DeferredDelete)

    def test_description_background_matches_card_in_light_and_dark_and_selected(self):
        for dark in (False, True):
            self.apply_theme(dark)
            for selected in (False, True):
                for text in ("", "Sample description"):
                    self.card.setSelected(selected)
                    self.card.description_edit.setText(text)
                    self._polish_and_layout()
                    image = self.card.grab().toImage()
                    ratio = image.devicePixelRatio()
                    slot = self.card.description_slot
                    point = slot.mapTo(self.card, QtCore.QPoint(slot.width() - 10, 4))
                    self.assertEqual(
                        image.pixelColor(round(point.x() * ratio), round(point.y() * ratio)),
                        image.pixelColor(round(6 * ratio), round(6 * ratio)),
                    )

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
            badge,
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonPress,
                QtCore.QPointF(3, 3),
                QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
            ),
        )
        self.assertEqual(self.selected, [2])

    def test_public_mouse_dispatch_selects_once_and_preserves_focus_selection(self):
        self.card.description_edit.setText("Description")
        self._polish_and_layout()
        for widget in (
            self.card,
            self.card.thumbnail_label,
            self.card.code_edit,
            self.card.weight_edit,
            self.card.description_edit,
            self.card.description_slot,
        ):
            for button in (QtCore.Qt.LeftButton, QtCore.Qt.RightButton):
                with self.subTest(widget=widget.objectName(), button=button):
                    self.selected.clear()
                    for kind, buttons in (
                        (QtCore.QEvent.MouseButtonPress, button),
                        (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
                    ):
                        QtWidgets.QApplication.sendEvent(
                            widget, QtGui.QMouseEvent(kind, QtCore.QPointF(3, 3), button, buttons, QtCore.Qt.NoModifier)
                        )
                    self.assertEqual(self.selected, [2] if button == QtCore.Qt.LeftButton else [])
        self.selected.clear()
        QtWidgets.QApplication.sendEvent(self.card.code_edit, QtGui.QFocusEvent(QtCore.QEvent.FocusIn))
        self.assertEqual(self.selected, [2])

    def test_data_hierarchy_elision_units_and_uniform_height(self):
        self._polish_and_layout()
        for field in (self.card.code_edit, self.card.description_edit, self.card.weight_edit):
            self.assertIsInstance(field, QtWidgets.QLabel)
        self.assertTrue(self.card.code_edit.font().bold())
        self.assertGreater(
            self.card.code_edit.fontMetrics().height(), self.card.description_edit.fontMetrics().height()
        )
        self.assertGreater(
            self.card.description_edit.fontMetrics().height(), self.card.weight_edit.fontMetrics().height()
        )
        self.assertTrue(self.card.description_edit.isHidden())
        height = self.card.sizeHint().height()
        self.card.description_edit.setText("A description long enough to wrap over two lines " * 6)
        self._polish_and_layout()
        self.assertFalse(self.card.description_edit.isHidden())
        self.assertEqual(self.card.sizeHint().height(), height)
        lines = self.card.description_edit._display_lines()
        self.assertEqual(len(lines), 2)
        self.assertLess(len(" ".join(lines)), len(self.card.description_edit.text()))
        self.assertTrue(lines[-1].endswith(font_ellipsis(self.card.description_edit.fontMetrics())), lines)
        self.assertGreaterEqual(
            self.card.description_edit.contentsRect().height(), self.card.description_edit.fontMetrics().height() * 2
        )
        self.assertEqual(self.card.description_edit.toolTip(), self.card.description_edit.text())
        title = "A very long profile code " * 8
        self.card.code_edit.setText(title)
        self.assertEqual(self.card.code_edit.toolTip(), title)
        code_line = self.card.code_edit._display_lines()[0]
        self.assertLess(len(code_line), len(title))
        self.assertTrue(code_line.endswith(font_ellipsis(self.card.code_edit.fontMetrics())), code_line)
        self.assertEqual(self.card.weight_edit._display_lines(), ["10.31 kg/m"])
        self.assertEqual(self.card.weight_edit.text(), "10.31")
        self.card.description_edit.clear()
        self._polish_and_layout()
        self.assertTrue(self.card.description_edit.isHidden())
        self.assertEqual(self.card.sizeHint().height(), height)

    def test_live_theme_change_preserves_selection_and_readonly(self):
        self.card.set_editable(False)
        self.card.setSelected(True)
        for dark in (True, False, True):
            self.apply_theme(dark)
            self.assertTrue(self.card._selected)
            self.assertFalse(self.card.btn_edit_properties.isEnabled())
            self.assertTrue(self.card.code_edit.isReadOnly())
            self.assertTrue(self.card.weight_edit.isReadOnly())
            self.assertEqual(self.card.code_edit.text(), "CP2")
            self.assertEqual(self.card.weight_edit.text(), "10.31")

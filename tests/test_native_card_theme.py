"""Native rendered regressions for S1–S3 (run inside FreeCAD's Qt process).

The application palette deliberately disagrees with local, standard-selector QSS.
All image comparisons use logical coordinates and color/ink bounds, not an exact
reference bitmap, so font rasterization and display scale may differ.
"""

import os
import unittest
from types import SimpleNamespace

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import Part

from freecad.maxproframe.custom_profile_cards import (
    CustomProfileCard,
    create_placeholder_pixmap,
    render_face_silhouette,
)


class TestNativeCardTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.original_palette = QtGui.QPalette(self.app.palette())
        self.host = QtWidgets.QWidget()
        self.host.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        self.layout = QtWidgets.QVBoxLayout(self.host)
        self.table = QtWidgets.QTableWidget(1, 8, self.host)
        self.table.setItem(0, 0, QtWidgets.QTableWidgetItem("CP2"))
        self.table.item(0, 0).setData(QtCore.Qt.UserRole, {"Description": "Native description"})
        self.table.setItem(0, 7, QtWidgets.QTableWidgetItem("10.31"))
        self.table.hide()
        self.dirty = []
        self.selected = []
        dialog = SimpleNamespace(
            current_lib_meta={"is_user": True}, table_sizes=self.table,
            palette=self.host.palette, _mark_dirty=lambda: self.dirty.append(True),
        )

        def select(row):
            self.selected.append(row)
            self.card.setSelected(True)

        self.card = CustomProfileCard(
            0, "CP2", "10.31", {"Description": "Native description"}, dialog,
            SimpleNamespace(select_card=select), self.host,
        )
        self.layout.addWidget(self.card)
        self.reference = QtWidgets.QLabel("CP2", self.host)
        self.reference.setFont(self.card.code_edit.font())
        self.reference.setFixedSize(220, self.card.code_edit.height())
        self.layout.addWidget(self.reference)
        self.preview_reference = QtWidgets.QLabel("No Preview", self.host)
        self.preview_reference.setFixedSize(160, 100)
        self.preview_reference.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.preview_reference)

    def tearDown(self):
        # Disconnect before restoring the global palette: no callback into teardown.
        try:
            self.app.paletteChanged.disconnect(self.card._on_palette_changed)
        except (RuntimeError, TypeError, AttributeError):
            pass
        self.host.close()
        self.host.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(self.host, QtCore.QEvent.DeferredDelete)
        self.app.setPalette(self.original_palette)

    def polish(self):
        self.host.ensurePolished()
        for child in self.host.findChildren(QtWidgets.QWidget):
            child.ensurePolished()
            if child.layout() is not None:
                child.layout().activate()
        self.layout.activate()
        self.host.adjustSize()
        self.host.show()
        self.layout.activate()

    def theme(self, dark):
        # Opposite application palette reproduces the RC mixed-palette failure.
        palette = QtGui.QPalette(self.original_palette)
        app_surface, app_ink = ("#fafafa", "#161616") if dark else ("#242424", "#eeeeee")
        for role in (QtGui.QPalette.Window, QtGui.QPalette.Base, QtGui.QPalette.Button):
            palette.setColor(role, QtGui.QColor(app_surface))
        for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
            palette.setColor(role, QtGui.QColor(app_ink))
        self.app.setPalette(palette)
        self.surface = QtGui.QColor("#292c31" if dark else "#f3eee4")
        self.ink = QtGui.QColor("#e9e3cf" if dark else "#253147")
        self.host.setStyleSheet(
            "QWidget { background-color: %s; color: %s; } "
            "QLabel { background-color: %s; color: %s; } "
            "QLineEdit { background-color: %s; color: %s; selection-background-color: #9362bd; } "
            "QToolButton { background-color: %s; color: %s; }"
            % ((self.surface.name(), self.ink.name()) * 4)
        )
        self.polish()

    @staticmethod
    def distance(a, b):
        return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue()))

    def image(self, widget):
        return widget.grab().toImage()

    def sample(self, image, x, y):
        ratio = image.devicePixelRatio()
        return image.pixelColor(round(x * ratio), round(y * ratio))

    def ink_bounds(self, image, ink=None):
        ink = ink or self.ink
        points = []
        # Scan physical pixels; normalize bounds to logical pixels afterwards.
        for y in range(image.height()):
            for x in range(image.width()):
                if self.distance(image.pixelColor(x, y), ink) < 55:
                    points.append((x, y))
        self.assertTrue(points, "No visible theme-colored text/glyph ink")
        ratio = image.devicePixelRatio()
        return ((max(x for x, _ in points) - min(x for x, _ in points) + 1) / ratio,
                (max(y for _, y in points) - min(y for _, y in points) + 1) / ratio)

    def assert_title_ink(self):
        actual = self.ink_bounds(self.image(self.card.code_edit))
        native = self.ink_bounds(self.image(self.reference))
        for measured, expected in zip(actual, native):
            self.assertAlmostEqual(measured, expected, delta=3,
                                   msg="Visible title ink must match locally styled native label")

    def capture(self, name):
        reports = os.environ.get("FF_REPORTS")
        if reports:
            self.assertTrue(self.card.grab().save(os.path.join(reports, name + ".png")))

    def assert_native_field_ink(self, field):
        # Grab first: this delivers any pending resize and refreshes the adapter's
        # displayed lines. The raw text() deliberately is not QLabel's painted text.
        actual_image = self.image(field)
        displayed = QtWidgets.QLabel.text(field)
        self.assertEqual(displayed, "\n".join(field._display_lines()))
        reference = QtWidgets.QLabel(field.parentWidget())
        # Match the receiving style context, including transparent ancestors.
        # Polish BEFORE copying font/geometry. A newly-created hidden QLabel has
        # not yet resolved inherited QSS; polishing afterwards can replace its font.
        reference.ensurePolished()
        reference.setTextFormat(QtCore.Qt.PlainText)
        reference.setFont(field.font())
        reference.setAlignment(field.alignment())
        reference.setContentsMargins(field.contentsMargins())
        reference.setMargin(field.margin())
        reference.setIndent(field.indent())
        reference.setFixedSize(field.size())
        reference.setText(displayed)
        expected_image = self.image(reference)
        self.assertEqual(reference.font(), field.font(), "Native oracle font differs after polish")
        self.assertEqual(reference.contentsRect(), field.contentsRect(), "Native oracle content geometry differs")
        self.assertEqual(QtWidgets.QLabel.text(reference), displayed)
        actual = self.ink_bounds(actual_image)
        expected = self.ink_bounds(expected_image)
        try:
            for dimension, measured, native in zip(("width", "height"), actual, expected):
                self.assertAlmostEqual(measured, native, delta=3,
                                       msg="%s %s; display=%r; font=%s; actual/native state=%r/%r" % (
                                           field.objectName(), dimension, displayed, field.font().toString(),
                                           self.label_state(field), self.label_state(reference)))
        except AssertionError:
            reports = os.environ.get("FF_REPORTS")
            if reports:
                # Preserve both complete images, including surfaces and any frame,
                # so a false ink mask can be distinguished from different glyphs.
                state = "%s-%s-%s" % (field.objectName(), self.surface.name()[1:],
                                         "multiline" if "\n" in displayed else "single")
                self.assertTrue(actual_image.save(os.path.join(reports, state + "-actual.png")))
                self.assertTrue(expected_image.save(os.path.join(reports, state + "-native.png")))
            raise
        finally:
            reference.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(reference, QtCore.QEvent.DeferredDelete)

    @staticmethod
    def label_state(label):
        resolved = QtGui.QFontInfo(label.font())
        return {
            "textFormat": str(label.textFormat()), "wordWrap": label.wordWrap(),
            "alignment": str(label.alignment()), "indent": label.indent(),
            "margin": label.margin(), "frameWidth": label.frameWidth(),
            "fontHeight": label.fontMetrics().height(),
            "resolvedFont": (resolved.family(), resolved.pixelSize(), resolved.weight()),
            "foreground": label.palette().color(label.foregroundRole()).name(),
        }

    def click_preview(self):
        widget = self.card.thumbnail_label
        point = QtCore.QPointF(6, widget.height() / 2)
        previous = list(self.selected)
        for kind, buttons in ((QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
                              (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
            QtWidgets.QApplication.sendEvent(widget, QtGui.QMouseEvent(
                kind, point, QtCore.Qt.LeftButton, buttons, QtCore.Qt.NoModifier))
        self.polish()
        self.assertEqual(self.selected, previous + [0])

    def test_initial_mouse_selection_and_live_qss_keep_native_ink(self):
        for dark in (False, True, False):
            with self.subTest(dark=dark):
                self.card.setSelected(False)
                self.theme(dark)
                self.assert_title_ink()
                before = self.image(self.card)
                self.capture("native-card-%s-initial" % ("dark" if dark else "light"))
                for field in (self.card.description_edit, self.card.weight_edit):
                    self.assert_native_field_ink(field)
                self.assertLess(self.distance(self.sample(before, 6, 6), self.surface), 3)
                self.click_preview()
                self.assert_title_ink()
                after = self.image(self.card)
                self.capture("native-card-%s-selected" % ("dark" if dark else "light"))
                # Selection must be visible, but not recolor unrelated title ink.
                changed = sum(
                    self.distance(self.sample(before, x, y), self.sample(after, x, y)) > 20
                    for y in range(2, self.card.height() - 2)
                    for x in (2, 3, self.card.width() - 3, self.card.width() - 4)
                )
                self.assertGreater(changed, 8, "Mouse selection needs a visible card indicator")
                self.assertEqual(self.card.code_edit.text(), "CP2")
                self.assertEqual(self.card.weight_edit.text(), "10.31")
                self.assertEqual(self.dirty, [])

    def test_preview_surface_and_glyph_follow_live_native_style(self):
        for dark in (False, True):
            with self.subTest(dark=dark):
                self.theme(dark)
                preview = self.card.thumbnail_label
                reference = self.image(self.preview_reference)
                self.ink_bounds(reference)  # Prove this theme's native label is readable.
                for pixmap in (create_placeholder_pixmap(text="No Preview"),
                               render_face_silhouette(Part.makePlane(20, 12))):
                    self.card.update_thumbnail(pixmap)
                    rendered = self.image(preview)
                    self.assertLess(self.distance(
                        self.sample(rendered, 5, preview.height() // 2),
                        self.sample(reference, 5, 50)), 3,
                        "Preview must use the effective native surface, not fixed gray")
                    # Inspect the unobstructed preview strip, excluding overlay ink.
                    ratio = rendered.devicePixelRatio()
                    safe = preview.contentsRect()
                    glyph = rendered.copy(round(safe.x() * ratio), round(safe.y() * ratio),
                                          round(safe.width() * ratio), round(safe.height() * ratio))
                    glyph.setDevicePixelRatio(ratio)
                    self.ink_bounds(glyph)
                self.assert_native_field_ink(self.card.weight_edit)
                # Same receiving preview must recolor already cached geometry on QSS replacement.
                self.host.setStyleSheet(self.host.styleSheet().replace(self.ink.name(), "#b65b92"))
                self.ink = QtGui.QColor("#b65b92")
                self.polish()
                rendered = self.image(preview)
                self.ink_bounds(rendered.copy(round(safe.x() * ratio), round(safe.y() * ratio),
                                              round(safe.width() * ratio), round(safe.height() * ratio)))
                self.capture("native-card-custom-%s" % ("dark" if dark else "light"))

    def test_pencil_uses_effective_toolbutton_ink_after_qss_replacement(self):
        for dark in (False, True):
            self.theme(dark)
            button = self.card.btn_edit_properties
            for editable in (True, False):
                self.card.set_editable(editable)
                self.polish()
                image = self.image(button)
                ratio = image.devicePixelRatio()
                center = button.rect().center()
                pencil = image.copy(round((center.x() - 8) * ratio),
                                    round((center.y() - 8) * ratio),
                                    round(16 * ratio), round(16 * ratio))
                self.ink_bounds(pencil)
                self.assertEqual(button.isEnabled(), editable)

    def test_raw_adapter_contract_readonly_elision_and_table_updates(self):
        self.theme(False)
        self.assertIs(self.card.le_code, self.card.code_edit)
        self.assertIs(self.card.le_weight, self.card.weight_edit)
        for editable in (True, False):
            self.card.set_editable(editable)
            self.assertEqual(self.card.btn_edit_properties.isEnabled(), editable)
            for field in (self.card.code_edit, self.card.description_edit, self.card.weight_edit):
                self.assertTrue(field.isReadOnly())
        seen = []
        self.card.weight_edit.textChanged.connect(seen.append)
        self.card.weight_edit.setText("3.25")
        self.assertEqual(seen, ["3.25"])
        self.assertEqual(self.table.item(0, 7).text(), "3.25")
        self.assertEqual(self.card.weight_edit.text(), "3.25")
        self.assertEqual(self.card.weight_edit._display_lines(), ["3.25 kg/m"])
        self.assertEqual(self.card.weight_edit.toolTip(), "3.25 kg/m")
        title = "Long native profile code " * 12
        self.card.code_edit.setText(title)
        self.assertEqual(self.table.item(0, 0).text(), title)
        self.assertEqual(self.card.code_edit.text(), title)
        self.assertEqual(self.card.code_edit.toolTip(), title)
        self.assertTrue(self.card.code_edit._display_lines()[0].endswith("…"))
        height = self.card.sizeHint().height()
        description = "A description with multiple words to wrap and elide " * 12
        self.card.description_edit.setText(description)
        self.polish()
        lines = self.card.description_edit._display_lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))
        self.assertEqual(self.card.description_edit.text(), description)
        self.assert_native_field_ink(self.card.description_edit)
        self.assertEqual(self.table.item(0, 0).data(QtCore.Qt.UserRole)["Description"], description)
        self.assertEqual(self.card.sizeHint().height(), height)
        self.card.description_edit.clear()
        self.assertTrue(self.card.description_edit.isHidden())
        self.assertEqual(self.card.sizeHint().height(), height)

"""Initial-display header badge geometry and rendered text regressions."""

import json
import os
from pathlib import Path
import tempfile
import unittest

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog


class TestHeaderBadgeGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="frameforge-header-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        stock = root / "stock"
        stock.mkdir()
        data = {
            "_metadata": {"name": "Stock", "material": "Steel", "density": 7.85},
            "Square": {"sizes": {"10": {"Height": "10", "Width": "10", "Weight": "0.785"}}},
        }
        (stock / "stock.json").write_text(json.dumps(data), encoding="utf-8")
        self.manager = LibraryManager(user_dir=str(root / "user"), stock_dir=str(stock))

    def make_dialog(self, dark):
        # Theme is local to the dialog: never change global Qt or user preferences.
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self.dispose_dialog, dialog)
        dialog.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        palette = QtGui.QPalette(dialog.palette())
        for role, color in (
            (QtGui.QPalette.Window, "#303030" if dark else "#eeeeee"),
            (QtGui.QPalette.WindowText, "#eeeeee" if dark else "#202020"),
            (QtGui.QPalette.AlternateBase, "#404040" if dark else "#dddddd"),
        ):
            palette.setColor(role, QtGui.QColor(color))
        dialog.setPalette(palette)
        dialog.show()
        self.polish_and_layout(dialog)
        return dialog

    def polish_and_layout(self, dialog):
        # Settle only this dialog's widgets/layouts, not unrelated queued callbacks.
        dialog.ensurePolished()
        for child in dialog.findChildren(QtWidgets.QWidget):
            child.ensurePolished()
        dialog.layout().activate()
        for layout in dialog.findChildren(QtWidgets.QLayout):
            layout.activate()

    def dispose_dialog(self, dialog):
        dialog.close()
        dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(dialog, QtCore.QEvent.DeferredDelete)

    def assert_visible_ink(self, badge):
        image = badge.grab().toImage()
        rect = badge.rect().adjusted(9, 6, -9, -6)
        ratio = image.devicePixelRatio()
        text_rect = QtCore.QRectF(rect)
        rows = [
            y
            for y in range(image.height())
            if rect.top() <= (y + 0.5) / ratio < rect.y() + rect.height()
        ]
        # Sample the blank left padding, away from both the rounded border and
        # text. Verify its uniformity instead of assuming a palette/QSS color.
        blank = {
            image.pixelColor(x, y).rgba()
            for y in rows
            for x in range(image.width())
            if 4 <= (x + 0.5) / ratio < 7
        }
        self.assertEqual(len(blank), 1, "Blank badge interior must have a uniform background")
        background = next(iter(blank))
        actual = {
            (x, y)
            for y in rows
            for x in range(image.width())
            if text_rect.contains(QtCore.QPointF((x + 0.5) / ratio, (y + 0.5) / ratio))
            and image.pixelColor(x, y).rgba() != background
        }
        self.assertTrue(actual, "Rendered header must contain visible elided text")
        metrics = badge.fontMetrics()
        text = metrics.elidedText(badge.text(), QtCore.Qt.ElideRight, max(0, rect.width()))
        glyphs = metrics.tightBoundingRect(text)
        baseline = rect.y() + (rect.height() - metrics.height()) / 2 + metrics.ascent()
        # Only demand empty edge rows when measured glyph bounds leave room
        # for them, including one logical pixel of rasterization/rounding slack.
        if baseline + glyphs.top() > rect.top() + 1:
            self.assertGreater(
                min(y for _, y in actual), min(rows), "Text touches the top clipping edge"
            )
        if baseline + glyphs.y() + glyphs.height() < rect.y() + rect.height() - 1:
            self.assertLess(
                max(y for _, y in actual), max(rows), "Text touches the bottom clipping edge"
            )
        # This is a functional clipping check, not proof of every interior
        # stroke. Saved widget captures support the separate visual review.

    def save_captures(self, dialog, case):
        reports = os.environ.get("FF_REPORTS")
        if not reports:
            return
        root = Path(reports)
        root.mkdir(parents=True, exist_ok=True)
        for name, widget in (
            ("dialog", dialog),
            ("library", dialog.lbl_lib_banner),
            ("family", dialog.lbl_family_name),
        ):
            path = root / f"header-badge-{case}-{name}.png"
            self.assertTrue(widget.grab().save(str(path), "PNG"), f"Could not save {path}")

    def test_initial_library_and_family_text_fits_in_light_and_dark(self):
        for dark in (False, True):
            dialog = self.make_dialog(dark)
            self.save_captures(dialog, "initial-dark" if dark else "initial-light")
            for badge in (dialog.lbl_lib_banner, dialog.lbl_family_name):
                with self.subTest(dark=dark, badge=badge.text()):
                    self.assertTrue(badge.text())
                    self.assertTrue(badge.isVisible())
                    drawn = badge.rect().adjusted(9, 6, -9, -6)
                    self.assertGreaterEqual(
                        drawn.height(),
                        badge.fontMetrics().height(),
                        "Paint padding must leave one complete font-height row",
                    )
                    self.assert_visible_ink(badge)

    def test_library_material_and_family_share_one_row(self):
        for dark in (False, True):
            dialog = self.make_dialog(dark)
            library = dialog.lbl_lib_banner
            family = dialog.lbl_family_name
            library_rect = QtCore.QRect(library.mapTo(dialog, QtCore.QPoint()), library.size())
            family_rect = QtCore.QRect(family.mapTo(dialog, QtCore.QPoint()), family.size())
            self.assertEqual(library_rect.center().y(), family_rect.center().y())
            self.assertLess(library_rect.right(), family_rect.left())
            self.assertIn("Stock | " + translate("frameforge", "Steel"), library.text())
            separators = [label for label in dialog.findChildren(QtWidgets.QLabel)
                          if label.text() == "-"]
            self.assertEqual(len(separators), 1)
            separator = separators[0]
            position = separator.mapTo(dialog, QtCore.QPoint())
            self.assertGreater(position.x(), library_rect.right())
            self.assertLess(position.x() + separator.width(), family_rect.left())

    def test_header_stays_grouped_when_dialog_grows(self):
        for dark in (False, True):
            dialog = self.make_dialog(dark)
            for width in (1000, 1600):
                dialog.resize(width, dialog.height())
                self.polish_and_layout(dialog)
                library = dialog.lbl_lib_banner
                family = dialog.lbl_family_name
                gap = family.x() - (library.x() + library.width())
                separator = next(label for label in dialog.findChildren(QtWidgets.QLabel)
                                 if label.text() == "-")
                self.assertLessEqual(gap, separator.sizeHint().width() + 8,
                                     "Extra width must follow the family, not separate the badges")
                self.assertEqual(library.geometry().center().y(), family.geometry().center().y())

    def test_narrow_badges_elide_without_losing_full_public_text(self):
        dialog = self.make_dialog(False)
        for name, badge in (
            ("library", dialog.lbl_lib_banner),
            ("family", dialog.lbl_family_name),
        ):
            with self.subTest(badge=badge.text()):
                full_text = badge.text()
                tooltip = badge.toolTip()
                self.assertTrue(full_text)
                self.assertIn(full_text, tooltip)
                badge.setFixedWidth(45)
                self.polish_and_layout(dialog)
                self.save_captures(dialog, f"narrow-light-{name}")
                self.assertEqual(badge.width(), 45)
                self.assertEqual(badge.minimumSizeHint().width(), 0)
                drawn = badge.rect().adjusted(9, 6, -9, -6)
                elided = badge.fontMetrics().elidedText(full_text, QtCore.Qt.ElideRight, drawn.width())
                self.assertNotEqual(elided, full_text)
                self.assertEqual(badge.text(), full_text)
                self.assertEqual(badge.toolTip(), tooltip)
                self.assert_visible_ink(badge)

"""Manager controls must use effective local QSS, not application-palette guesses.

Run inside FreeCAD; no application settings or global event queue are changed.
The two literal fixtures stand for already-resolved FreeCAD theme tokens.
"""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    AddFamilyDialog,
    NewLibraryDialog,
    ProfileLibraryManagerDialog,
)

THEMES = (
    {"surface": "#24374b", "ink": "#f3dfac", "button": "#40566d", "disabled": "#8394a5"},
    {"surface": "#e9dfca", "ink": "#283c59", "button": "#c9d9e5", "disabled": "#68777e"},
)


def stylesheet(theme):
    return (
        """
        QDialog { background-color: %(surface)s; color: %(ink)s; }
        QLabel {
            background-color: %(surface)s; color: %(ink)s;
            border: 1px solid %(ink)s; font-size: 15px;
        }
        QPushButton {
            background-color: %(button)s; color: %(ink)s;
            border: 1px solid %(ink)s; padding: 6px 16px;
        }
        QPushButton:disabled { background-color: %(surface)s; color: %(disabled)s; }
    """
        % theme
    )


class TestNativeManagerTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="frameforge-native-manager-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        stock = root / "stock"
        stock.mkdir()
        self.data = {
            "_metadata": {"name": "Stock", "material": "Steel", "density": 7.85},
            "Pipe": {"norm": "P", "sizes": {"10": {"Height": "10", "Thickness": "1"}}},
            "Square": {"norm": "S", "sizes": {"20": {"Height": "20", "Width": "20"}}},
        }
        (stock / "stock.json").write_text(json.dumps(self.data), encoding="utf-8")
        self.manager = LibraryManager(user_dir=str(root / "user"), stock_dir=str(stock))
        self.manager.save_user_library("Editable", copy.deepcopy(self.data))
        self.manager.create_folder_library(str(root / "folder"), "Folder", data=copy.deepcopy(self.data))
        # Geometry persistence is unrelated to rendering and must not touch real settings.
        for method in ("_restore_window_geometry", "_save_window_geometry"):
            patcher = patch.object(ProfileLibraryManagerDialog, method)
            patcher.start()
            self.addCleanup(patcher.stop)

    def own(self, dialog):
        self.addCleanup(self.dispose, dialog)
        dialog.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        return dialog

    def dispose(self, dialog):
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
            dialog.close()
        dialog.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(dialog, QtCore.QEvent.DeferredDelete)

    def settle(self, dialog):
        dialog.ensurePolished()
        for child in dialog.findChildren(QtWidgets.QWidget):
            child.ensurePolished()
        for layout in dialog.findChildren(QtWidgets.QLayout):
            layout.activate()
        dialog.layout().activate()

    def apply_theme(self, dialog, theme):
        dialog.setStyleSheet(stylesheet(theme))
        dialog.show()
        self.settle(dialog)

    def make_manager(self):
        dialog = self.own(ProfileLibraryManagerDialog(library_manager=self.manager))
        # A local palette deliberately conflicts with QSS. Never mutate app.palette().
        palette = QtGui.QPalette(self.app.palette())
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#fafafa"))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#ad187c"))
        dialog.setPalette(palette)
        return dialog

    def capture(self, widget, name):
        reports = os.environ.get("FF_REPORTS")
        if reports:
            root = Path(reports)
            root.mkdir(parents=True, exist_ok=True)
            self.assertTrue(widget.grab().save(str(root / ("native-manager-" + name + ".png")), "PNG"))

    def assert_surface(self, widget, color):
        image = widget.grab().toImage()
        ratio = image.devicePixelRatio()
        # Left interior is outside preview pixmaps and text, away from rounded corners.
        actual = image.pixelColor(int(2 * ratio), int(widget.height() * ratio / 2))
        self.assertEqual(actual.name(), color, "Local QSS must own the rendered surface")

    def assert_ink(self, widget, color):
        widget.ensurePolished()
        expected = QtGui.QColor(color)
        self.assertEqual(widget.palette().color(widget.foregroundRole()).name(), color)
        image = widget.grab().toImage()
        ratio = image.devicePixelRatio()
        # Ignore borders: demand actual text-colored ink inside the content area.
        found = any(
            max(
                abs(actual.red() - expected.red()),
                abs(actual.green() - expected.green()),
                abs(actual.blue() - expected.blue()),
            )
            <= 25
            for y in range(int(7 * ratio), int(image.height() - 7 * ratio))
            for x in range(int(10 * ratio), int(image.width() - 10 * ratio))
            for actual in (image.pixelColor(x, y),)
        )
        self.assertTrue(found, "The native foreground must be painted, not merely stored in a palette")

    def test_badges_initial_switch_and_live_qss_keep_native_ink_and_geometry(self):
        dialog = self.make_manager()
        for theme in THEMES:
            self.apply_theme(dialog, theme)
            for library in ("Stock", "Editable", "Folder"):
                dialog.refresh_libraries(select_name=library)
                for row in range(dialog.list_families.count()):
                    dialog.list_families.setCurrentRow(row)
                    self.settle(dialog)
                    self.capture(dialog, f"{theme['surface'][1:]}-{library}-family-{row}")
                    with self.subTest(theme=theme, library=library, family=dialog.current_family):
                        self.assertEqual(dialog.current_lib_meta["name"], library)
                        self.assertEqual(dialog.lbl_family_name.text(), dialog.list_families.currentItem().text())
                        self.assertIn(library, dialog.lbl_lib_banner.text())
                        for badge in (dialog.lbl_lib_banner, dialog.lbl_family_name):
                            full_text, tooltip = badge.text(), badge.toolTip()
                            self.assertIn(full_text, tooltip)
                            self.assert_surface(badge, theme["surface"])
                            self.assert_ink(badge, theme["ink"])
                            self.assertGreaterEqual(badge.height() - 12, badge.fontMetrics().height())
                            # At most 27 px of text room, and always less than the text needs in this font.
                            room = min(27, badge.fontMetrics().horizontalAdvance(full_text) - 1)
                            badge.setFixedWidth(room + 2 * badge._TEXT_INSET_X)
                            self.settle(dialog)
                            self.assertEqual(badge.minimumSizeHint().width(), 0)
                            elided = badge.fontMetrics().elidedText(full_text, QtCore.Qt.ElideRight, room)
                            self.assertNotEqual(elided, full_text)
                            self.assertEqual((badge.text(), badge.toolTip()), (full_text, tooltip))
                            self.assert_ink(badge, theme["ink"])
                            badge.setMinimumWidth(0)
                            badge.setMaximumWidth(16777215)

    def test_badge_font_change_reflows_height_and_retains_elision_contract(self):
        dialog = self.make_manager()
        for size in (15, 23, 12):
            dialog.setStyleSheet(stylesheet(THEMES[0]).replace("font-size: 15px", f"font-size: {size}px"))
            dialog.show()
            self.settle(dialog)
            for badge in (dialog.lbl_lib_banner, dialog.lbl_family_name):
                full_text, tooltip = badge.text(), badge.toolTip()
                self.assertGreaterEqual(badge.height() - 12, badge.fontMetrics().height())
                badge.setFixedWidth(65)
                self.settle(dialog)
                self.assert_ink(badge, THEMES[0]["ink"])
                badge.setMinimumWidth(0)
                badge.setMaximumWidth(16777215)
                self.assertEqual((badge.text(), badge.toolTip()), (full_text, tooltip))
                badge.setMinimumWidth(0)
                badge.setMaximumWidth(16777215)
            self.capture(dialog, f"font-{size}")

    def test_save_states_follow_qss_without_changing_dirty_or_permissions(self):
        dialog = self.make_manager()
        for theme in THEMES:
            self.apply_theme(dialog, theme)
            for library in ("Editable", "Folder", "Stock"):
                dialog.refresh_libraries(select_name=library)
                before = copy.deepcopy(dialog.current_lib_data)
                self.assertFalse(dialog.is_dirty)
                self.assertFalse(dialog.btn_save.isEnabled())
                self.assert_surface(dialog.btn_save, theme["surface"])
                self.assert_ink(dialog.btn_save, theme["disabled"])
                self.capture(dialog.btn_save, f"{theme['surface'][1:]}-{library}-save-disabled")
                # Actual editor input drives dirty state, not a rendering-only flag.
                if library != "Stock":
                    dialog.le_norm.setText(dialog.le_norm.text() + " changed")
                else:
                    self.assertFalse(dialog.le_norm.isEnabled())
                    dialog.is_dirty = True
                self.assertTrue(dialog.is_dirty)
                self.assertEqual(dialog.btn_save.isEnabled(), library != "Stock")
                other = THEMES[1] if theme is THEMES[0] else THEMES[0]
                self.apply_theme(dialog, other)
                self.assertTrue(dialog.is_dirty)
                self.assertEqual(dialog.btn_save.isEnabled(), library != "Stock")
                self.assert_surface(dialog.btn_save, other["button"] if library != "Stock" else other["surface"])
                self.assert_ink(dialog.btn_save, other["ink"] if library != "Stock" else other["disabled"])
                self.capture(dialog, f"{other['surface'][1:]}-{library}-save-dirty-replacement")
                self.apply_theme(dialog, theme)
                self.assert_surface(dialog.btn_save, theme["button"] if library != "Stock" else theme["surface"])
                self.assert_ink(dialog.btn_save, theme["ink"] if library != "Stock" else theme["disabled"])
                # No click/save was requested; theme transitions cannot write a catalog.
                self.assertEqual(self.manager.get_library(library), before)
                dialog.is_dirty = False
                self.assertFalse(dialog.btn_save.isEnabled())

    def test_status_and_auxiliary_previews_inherit_local_theme_on_replacement(self):
        dialog = self.make_manager()
        family_dialog = self.own(AddFamilyDialog())
        folder_dialog = self.own(NewLibraryDialog(is_folder=True, user_dir=str(Path(self.temp.name) / "new")))
        info_labels = [label for label in folder_dialog.findChildren(QtWidgets.QLabel) if label.wordWrap()]
        self.assertEqual(len(info_labels), 1)
        for theme in THEMES:
            for window in (dialog, family_dialog, folder_dialog):
                self.apply_theme(window, theme)
            for row in (0, 1):
                dialog.list_families.setCurrentRow(row)
                family_dialog.list_families.setCurrentRow(row)
                self.settle(dialog)
                self.settle(family_dialog)
                for preview in (dialog.lbl_family_icon, family_dialog.lbl_preview):
                    self.assert_surface(preview, theme["surface"])
            self.assert_surface(info_labels[0], theme["surface"])
            self.assert_ink(info_labels[0], theme["ink"])
            # Reuse existing display text: no new severity wording is prescribed.
            message = dialog.lbl_lib_banner.text()
            for flags in ({}, {"is_warning": True}, {"is_error": True}):
                dialog._set_status(message, **flags)
                self.settle(dialog)
                self.assertEqual(dialog.lbl_status.text(), message)
                self.assertEqual(dialog.lbl_status.property("is_error"), flags.get("is_error", False))
                self.assertEqual(dialog.lbl_status.property("is_warning"), flags.get("is_warning", False))
                self.assert_surface(dialog.lbl_status, theme["surface"])
                self.assert_ink(dialog.lbl_status, theme["ink"])
            self.capture(dialog, f"{theme['surface'][1:]}-status-error")
            self.capture(family_dialog, f"{theme['surface'][1:]}-add-family")
            self.capture(folder_dialog, f"{theme['surface'][1:]}-folder-info")

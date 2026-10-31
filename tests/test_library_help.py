"""Native checks for the bundled library manager guide and its contextual help."""

import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from miter_helpers import use_language
from PySide import QtCore, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest

from freecad.maxproframe import help_viewer
from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate
from freecad.maxproframe.help_viewer import HELP_PATH, HelpDialog, guide_path, show_help, topic_headings
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    AddFamilyDialog,
    NewLibraryDialog,
    ProfileLibraryManagerDialog,
)

ENGLISH_HEADINGS = {
    "overview": "Profile Library Manager",
    "libraries": "Libraries",
    "new-library": "Create a library",
    "duplicate": "Duplicate a system library",
    "share": "Share a library",
    "families": "Families",
    "sizes": "Profiles and sizes",
    "custom-profiles": "Custom profiles",
    "saving": "Save your changes",
    "use": "Use your profiles in a model",
}


def guide_headings(path):
    with open(path, encoding="utf-8") as guide:
        return [match.group(1) for match in re.finditer(r"^#{1,2} (.+?)\s*$", guide.read(), re.MULTILINE)]


def spanish_catalog():
    root = ET.parse(os.path.join(TRANSLATIONSPATH, "maxproframe_es.ts")).getroot()
    return {
        message.findtext("source"): message.findtext("translation")
        for context in root.findall("context")
        if context.findtext("name") == "frameforge"
        for message in context.findall("message")
    }


def help_windows(parent):
    return parent.findChildren(HelpDialog, options=QtCore.Qt.FindDirectChildrenOnly)


def reset_help(parent):
    """Hide the parent's help window at the top of the guide, so only a new request can show a topic."""
    for window in help_windows(parent):
        window.close()
        window.findChild(QtWidgets.QTextBrowser).verticalScrollBar().setValue(0)


def first_visible_text(help_dialog):
    browser = help_dialog.findChild(QtWidgets.QTextBrowser)
    return browser.cursorForPosition(QtCore.QPoint(0, 0)).block().text()


class TestHelpGuide(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        use_language(self, "English", "en_US")
        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 300)
        self.addCleanup(self.parent.deleteLater)
        self.addCleanup(lambda: [window.close() for window in help_windows(self.parent)])

    def test_every_topic_heading_is_a_heading_in_both_guides(self):
        self.assertEqual(topic_headings(), ENGLISH_HEADINGS)
        english = guide_headings(os.path.join(HELP_PATH, "library-manager.md"))
        spanish = guide_headings(os.path.join(HELP_PATH, "library-manager.es.md"))
        catalog = spanish_catalog()
        self.assertEqual(catalog.get("library-manager.md"), "library-manager.es.md")
        for topic, heading in ENGLISH_HEADINGS.items():
            with self.subTest(topic=topic):
                self.assertIn(heading, english)
                self.assertIn(catalog.get(heading), spanish)

    def test_guide_path_follows_language_and_falls_back_to_english(self):
        english = os.path.join(HELP_PATH, "library-manager.md")
        self.assertEqual(guide_path(), english)
        for translated in ("library-manager.fr.md", "../../library-manager.es.md.missing"):
            with self.subTest(translated=translated):
                with patch.object(help_viewer, "translate", return_value=translated):
                    self.assertEqual(guide_path(), english)
        use_language(self, "Spanish", "es_ES")
        self.assertEqual(guide_path(), os.path.join(HELP_PATH, "library-manager.es.md"))
        window = show_help(self.parent, "families")
        self.app.processEvents()
        self.assertEqual(first_visible_text(window), "Familias")

    def test_show_help_reuses_one_window_per_parent_and_scrolls_topic_to_top(self):
        window = show_help(self.parent, "sizes")
        self.app.processEvents()
        self.assertIsInstance(window, HelpDialog)
        self.assertTrue(window.isVisible())
        self.assertFalse(window.isModal())
        self.assertTrue(window.windowFlags() & QtCore.Qt.Window)
        self.assertEqual(window.windowTitle(), translate("frameforge", "MaxProFrame Help"))
        browser = window.findChild(QtWidgets.QTextBrowser)
        self.assertTrue(browser.isReadOnly())
        self.assertTrue(browser.openExternalLinks())
        self.assertEqual(first_visible_text(window), "Profiles and sizes")
        for topic, heading in ENGLISH_HEADINGS.items():
            with self.subTest(topic=topic):
                self.assertIs(show_help(self.parent, topic), window)
                self.app.processEvents()
                self.assertEqual(first_visible_text(window), heading)
        window.close()
        self.assertIs(show_help(self.parent, "unknown-topic"), window)
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertEqual(browser.verticalScrollBar().value(), 0)
        self.assertEqual(first_visible_text(window), "Profile Library Manager")
        self.assertEqual(help_windows(self.parent), [window])
        other = QtWidgets.QWidget()
        self.addCleanup(other.deleteLater)
        second = show_help(other, "families")
        self.addCleanup(second.close)
        self.assertIsNot(second, window)


class TestLibraryManagerHelp(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        use_language(self, "English", "en_US")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = LibraryManager(
            user_dir=os.path.join(self.temp.name, "user"),
            stock_dir=os.path.join(self.temp.name, "stock"),
            registry_path=os.path.join(self.temp.name, "registry.json"),
        )
        self.manager.create_folder_library(
            os.path.join(self.temp.name, "catalog"),
            "Catalog",
            data={
                "Square Hollow": {
                    "norm": "Standard",
                    "sizes": {"SH40": {"Height": "40", "Width": "40", "Thickness": "2", "Weight": "2.4"}},
                },
                "Custom Profile": {
                    "canonical_family": "Custom Profile",
                    "fillet": False,
                    "sizes": {"PGC100": {"Weight": "2.3", "Description": "Correa"}},
                },
                "Pipe": {"fillet": False, "sizes": {}},
                "C": {"canonical_family": "Custom Profile", "fillet": False, "sizes": {}},
            },
        )
        self.manager.create_folder_library(os.path.join(self.temp.name, "empty"), "Empty", data={})
        # Seed bundled catalogs through the existing writer, then discover them read-only.
        stock_writer = LibraryManager(
            user_dir=self.manager.stock_dir, stock_dir=os.path.join(self.temp.name, "empty-stock")
        )
        stock_writer.save_user_library("Stock", {"Pipe": {"fillet": False, "sizes": {}}})
        stock_writer.save_user_library("Bare", {"_metadata": {"name": "Bare"}})
        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)

        def discard_on_cleanup():
            for window in help_windows(self.dialog):
                window.close()
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
                self.dialog.close()

        self.addCleanup(discard_on_cleanup)
        self.dialog.show()
        self.app.processEvents()

    def library(self, name):
        self.dialog.refresh_libraries(select_name=name)
        self.assertEqual(self.dialog.current_lib_meta["name"], name)

    def family(self, key):
        for row in range(self.dialog.list_families.count()):
            if self.dialog.list_families.item(row).data(QtCore.Qt.UserRole) == key:
                self.dialog.list_families.setCurrentRow(row)
                return
        self.fail(key)

    def open_help(self, focus=None, key=False):
        reset_help(self.dialog)
        if focus is not None:
            focus.setFocus()
        self.app.processEvents()
        if key:
            self.dialog.activateWindow()
            self.app.processEvents()
            QtTest.QTest.keyClick(focus or self.dialog, QtCore.Qt.Key_F1)
        else:
            QtTest.QTest.mouseClick(self.dialog.btn_help, QtCore.Qt.LeftButton)
        self.app.processEvents()
        windows = help_windows(self.dialog)
        self.assertEqual(len(windows), 1)
        self.assertTrue(windows[0].isVisible())
        return first_visible_text(windows[0])

    def test_help_button_sits_in_the_header(self):
        button = self.dialog.btn_help
        self.assertEqual(button.text(), "?")
        self.assertEqual(button.toolTip(), translate("frameforge", "Help (F1)"))
        self.assertTrue(button.isVisible())

    def test_help_button_and_f1_open_the_focused_area_topic(self):
        self.library("Catalog")
        self.family("Square Hollow")
        cases = [
            (self.dialog.list_libraries, "Libraries"),
            (self.dialog.btn_dup_lib, "Libraries"),
            (self.dialog.list_families, "Families"),
            (self.dialog.le_norm, "Families"),
            (self.dialog.btn_add_family, "Families"),
            (self.dialog.table_sizes, "Profiles and sizes"),
            (self.dialog.le_search, "Profiles and sizes"),
            (self.dialog.btn_add_size, "Profiles and sizes"),
        ]
        for widget, heading in cases:
            for key in (False, True):
                with self.subTest(widget=widget.metaObject().className(), heading=heading, key=key):
                    self.assertEqual(self.open_help(widget, key=key), heading)
        self.family("Custom Profile")
        card = self.dialog.cards_view.card_by_code("PGC100")
        for widget in (card.description_edit, self.dialog.btn_capture_section, self.dialog.btn_import_dxf):
            for key in (False, True):
                with self.subTest(widget=widget.metaObject().className(), key=key):
                    self.assertEqual(self.open_help(widget, key=key), "Custom profiles")
        self.dialog.le_norm.setText("Edited")
        for key in (False, True):
            with self.subTest(widget="save", key=key):
                self.assertEqual(self.open_help(self.dialog.btn_save, key=key), "Save your changes")

    def test_help_without_a_focused_area_follows_the_state(self):
        self.dialog.btn_help.setFocus()
        cases = [
            ("Catalog", "Custom Profile", "Custom profiles"),
            ("Catalog", "Square Hollow", "Profiles and sizes"),
            ("Stock", "Pipe", "Profiles and sizes"),
            ("Bare", None, "Duplicate a system library"),
            ("Empty", None, "Libraries"),
        ]
        for library, family, heading in cases:
            for key in (False, True):
                with self.subTest(library=library, family=family, key=key):
                    self.library(library)
                    if family:
                        self.family(family)
                    self.dialog.btn_help.setFocus()
                    self.assertEqual(self.open_help(self.dialog.btn_help, key=key), heading)

    def test_sub_dialog_help_opens_their_topic(self):
        cases = [
            (lambda: NewLibraryDialog(self.dialog, user_dir=self.manager.user_dir), "Create a library"),
            (
                lambda: NewLibraryDialog(
                    self.dialog, title="Duplicate Library", is_duplicate=True, user_dir=self.manager.user_dir
                ),
                "Duplicate a system library",
            ),
            (lambda: AddFamilyDialog(self.dialog), "Families"),
        ]
        for factory, heading in cases:
            sub = factory()
            self.addCleanup(sub.deleteLater)
            self.addCleanup(lambda sub=sub: [window.close() for window in help_windows(sub)])
            sub.show()
            focusable = [
                widget for widget in sub.findChildren(QtWidgets.QWidget) if widget.focusPolicy() & QtCore.Qt.TabFocus
            ]
            self.assertTrue(focusable)
            button = sub.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Help)
            self.assertIsNotNone(button)
            for focus in [None] + focusable:
                for key in (False, True):
                    with self.subTest(heading=heading, focus=focus and focus.metaObject().className(), key=key):
                        reset_help(sub)
                        sub.activateWindow()
                        QtTest.QTest.qWaitForWindowActive(sub)
                        if focus is not None:
                            focus.setFocus()
                        self.app.processEvents()
                        if key:
                            QtTest.QTest.keyClick(sub.focusWidget() or sub, QtCore.Qt.Key_F1)
                        else:
                            QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
                        self.app.processEvents()
                        windows = help_windows(sub)
                        self.assertEqual(len(windows), 1)
                        self.assertTrue(windows[0].isVisible())
                        self.assertEqual(first_visible_text(windows[0]), heading)
                        self.assertTrue(sub.isVisible())
                        self.assertEqual(help_windows(self.dialog), [])
            sub.reject()
            self.app.processEvents()
            self.assertFalse(help_windows(sub)[0].isVisible())

    def test_every_control_has_a_translated_tooltip(self):
        expected = {
            self.dialog.list_libraries: "Select a library to see its families. [System] libraries are read-only.",
            self.dialog.list_families: "Select a family to see its profiles.",
            self.dialog.le_norm: "Standard or catalog reference of this family, for example EN 10219.",
            self.dialog.le_search: "Filter the profiles of this family by code or description.",
            self.dialog.table_sizes: "Profiles of this family: one row per size, dimensions in mm and weight in kg/m.",
            self.dialog.btn_save: "Save the pending changes of this library.",
            self.dialog.btn_close: "Close the library manager.",
            self.dialog.btn_help: "Help (F1)",
        }
        for widget, text in expected.items():
            with self.subTest(text=text):
                self.assertEqual(widget.toolTip(), translate("frameforge", text))
        controls = (QtWidgets.QAbstractButton, QtWidgets.QLineEdit, QtWidgets.QAbstractItemView)
        missing = [
            widget.metaObject().className() + ":" + getattr(widget, "text", lambda: "")()
            for kind in controls
            for widget in self.dialog.findChildren(kind)
            # Qt-internal sub-buttons and the cards (owned by their own module) are out of scope.
            if widget.isVisibleTo(self.dialog)
            and not widget.toolTip()
            and not isinstance(widget.parentWidget(), (QtWidgets.QLineEdit, QtWidgets.QAbstractScrollArea))
            and not self.dialog.cards_view.isAncestorOf(widget)
            and widget.window() is self.dialog
        ]
        self.assertEqual(missing, [])

    def test_empty_states_explain_the_next_step(self):
        self.library("Empty")
        self.assertTrue(self.dialog.lbl_families_empty.isVisible())
        self.assertEqual(
            self.dialog.lbl_families_empty.text(),
            translate("frameforge", "This library has no families yet. Add one with +."),
        )
        self.library("Bare")
        self.assertTrue(self.dialog.lbl_families_empty.isVisible())
        self.assertEqual(
            self.dialog.lbl_families_empty.text(),
            translate("frameforge", "This system library is read-only. Duplicate it to create your own families."),
        )
        self.library("Catalog")
        self.assertFalse(self.dialog.lbl_families_empty.isVisible())
        no_profiles = translate("frameforge", "This family has no profiles.")
        for library, family, hint in (
            ("Catalog", "Pipe", "Add a size with +."),
            ("Catalog", "C", "Capture a section or import a DXF to add one."),
            ("Stock", "Pipe", "Duplicate the library to edit it."),
        ):
            with self.subTest(library=library, family=family):
                self.library(library)
                self.family(family)
                self.assertTrue(self.dialog.lbl_profiles_empty.isVisible())
                self.assertEqual(self.dialog.lbl_profiles_empty.text(), no_profiles)
                self.assertTrue(self.dialog.lbl_profiles_hint.isVisible())
                self.assertEqual(self.dialog.lbl_profiles_hint.text(), translate("frameforge", hint))
        self.library("Catalog")
        self.family("Square Hollow")
        self.assertFalse(self.dialog.lbl_profiles_empty.isVisible())
        self.assertFalse(self.dialog.lbl_profiles_hint.isVisible())
        self.dialog.le_search.setText("missing")
        self.assertEqual(self.dialog.lbl_profiles_empty.text(), translate("frameforge", "No matching profiles."))
        self.assertFalse(self.dialog.lbl_profiles_hint.isVisible())
        self.assertFalse(self.dialog.is_dirty)


if __name__ == "__main__":
    unittest.main()

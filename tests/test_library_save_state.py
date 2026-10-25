"""Save is actionable only for editable libraries with accepted pending changes."""

import copy
import os
import unittest
from unittest.mock import patch

import test_library_usability as fixtures
from PySide import QtWidgets

from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog


class TestLibrarySaveState(unittest.TestCase):
    def setUp(self):
        fixtures.TestLibraryUsability.setUp(self)

    def properties(self, action):
        from PySide import QtCore

        self.dialog.combo_family.setCurrentText("Custom Profile")
        self.error = None

        def interact():
            modal = self.app.activeModalWidget()
            try:
                action(modal)
            except BaseException as error:
                self.error = error
                modal.reject()

        QtCore.QTimer.singleShot(0, interact)
        self.dialog.cards_view.card_by_code("PGC100").btn_edit_properties.click()
        if self.error:
            raise self.error

    def test_pristine_library_and_passive_navigation_cannot_save(self):
        before = copy.deepcopy(self.manager.get_library("Catalog"))
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog.btn_save.isEnabled())
        if os.environ.get("FF_REPORTS"):
            self.assertTrue(self.dialog.grab().save(os.path.join(os.environ["FF_REPORTS"], "save-disabled.png")))
        for family in ("Custom Profile", "Square Hollow", "Pipe"):
            self.dialog.combo_family.setCurrentText(family)
            self.dialog.le_search.setText("anything")
            self.dialog.le_search.clear()
            self.assertFalse(self.dialog.is_dirty)
            self.assertFalse(self.dialog.btn_save.isEnabled())
        with patch.object(self.manager, "save_folder_library") as write:
            self.dialog.btn_save.click()
        write.assert_not_called()
        self.assertEqual(self.manager.get_library("Catalog"), before)

    def test_properties_accept_cancel_and_noop_keep_correct_save_state(self):
        self.assertFalse(self.dialog.btn_save.isEnabled())
        self.properties(lambda modal: modal.accept())
        self.assertFalse(self.dialog.btn_save.isEnabled())
        self.properties(lambda modal: (modal.code.setText("Canceled name"), modal.reject()))
        self.assertFalse(self.dialog.btn_save.isEnabled())
        self.properties(lambda modal: (modal.description.setText("Accepted description"), modal.accept()))
        self.assertTrue(self.dialog.is_dirty)
        self.assertTrue(self.dialog.btn_save.isEnabled())
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog.btn_save.isEnabled())
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]["PGC100"]
        self.assertEqual(saved["Description"], "Accepted description")
        self.properties(lambda modal: modal.reject())
        self.assertFalse(self.dialog.btn_save.isEnabled())

    def test_standard_edits_failed_save_and_successful_retry(self):
        self.dialog.combo_family.setCurrentText("Square Hollow")
        before = copy.deepcopy(self.manager.get_library("Catalog"))
        self.dialog.table_sizes.item(0, 1).setText("42")
        self.assertTrue(self.dialog.is_dirty)
        self.assertTrue(self.dialog.btn_save.isEnabled())
        with patch.object(self.manager, "save_folder_library", side_effect=OSError("write failed")):
            with patch.object(QtWidgets.QMessageBox, "warning") as warning:
                self.dialog.btn_save.click()
                warning.assert_called_once()
        self.assertTrue(self.dialog.is_dirty)
        self.assertTrue(self.dialog.btn_save.isEnabled())
        self.assertEqual(self.manager.get_library("Catalog"), before)
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog.btn_save.isEnabled())
        self.assertEqual(self.manager.get_library("Catalog")["Square Hollow"]["sizes"]["SH40"]["Height"], "42")

    def test_readonly_library_never_enables_save(self):
        data = copy.deepcopy(self.dialog.current_lib_data)
        stock = LibraryManager(user_dir=self.manager.stock_dir, stock_dir=self.temp.name + "/empty-stock")
        stock.save_user_library("Stock", data)
        self.dialog.refresh_libraries(select_name="Stock")
        self.assertFalse(self.dialog.btn_save.isEnabled())
        # Even a programmatic dirty notification cannot bypass library permissions.
        self.dialog._mark_dirty()
        self.assertFalse(self.dialog.btn_save.isEnabled())
        before = copy.deepcopy(self.manager.get_library("Stock"))
        self.dialog.btn_save.click()
        self.assertEqual(self.manager.get_library("Stock"), before)
        self.dialog.is_dirty = False

    def test_reload_resets_save_after_discarding_pending_edits(self):
        self.dialog.combo_family.setCurrentText("Square Hollow")
        before = copy.deepcopy(self.manager.get_library("Catalog"))
        self.dialog.table_sizes.item(0, 1).setText("45")
        self.assertTrue(self.dialog.btn_save.isEnabled())
        self.dialog.refresh_libraries(select_name="Catalog")
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog.btn_save.isEnabled())
        self.assertEqual(self.manager.get_library("Catalog"), before)

    def test_empty_manager_starts_with_save_disabled(self):
        manager = LibraryManager(
            user_dir=self.temp.name + "/empty-user",
            stock_dir=self.temp.name + "/empty-system",
            registry_path=self.temp.name + "/empty-registry.json",
        )
        dialog = ProfileLibraryManagerDialog(library_manager=manager)
        self.addCleanup(dialog.close)
        self.assertIsNone(dialog.current_lib_meta)
        self.assertFalse(dialog.btn_save.isEnabled())

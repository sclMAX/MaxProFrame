"""Native GUI checks for compact headers, selection safety, and stored fillet."""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide import QtCore, QtWidgets

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import AddFamilyDialog, ProfileLibraryManagerDialog

class TestLibraryUsability(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = LibraryManager(user_dir=os.path.join(self.temp.name, "user"),
                                      stock_dir=os.path.join(self.temp.name, "stock"),
                                      registry_path=os.path.join(self.temp.name, "registry.json"))
        self.folder = os.path.join(self.temp.name, "catalog")
        self.manager.create_folder_library(self.folder, "Catalog", data={
            "Square Hollow": {"fillet": True, "norm": "Standard", "sizes": {
                "SH40": {"Height": "40", "Width": "40", "Thickness": "2", "Radius1": "4", "Radius2": "2", "Weight": "2.4"}}},
            "Custom Profile": {"canonical_family": "Custom Profile", "fillet": False, "sizes": {
                "PGC100": {"Weight": "2.3", "vendor": "keep"},
                "AL200": {"Weight": "1.2"}}},
            "Pipe": {"fillet": False, "sizes": {}}})
        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self.dialog.close)
        self.dialog.refresh_libraries(select_name="Catalog")

    def family(self, name):
        self.dialog.combo_family.setCurrentText(name)

    def test_compact_banner_and_stored_fillet(self):
        self.family("Square Hollow")
        banner = self.dialog.lbl_lib_banner
        self.assertNotIn(self.folder, banner.text())
        self.assertIn("Catalog", banner.text())
        self.assertIn(self.folder, banner.toolTip())
        self.assertIn(self.dialog._get_family_display_name("Square Hollow", self.dialog.current_lib_data["Square Hollow"]),
                      self.dialog.lbl_family_name.text())
        self.assertFalse(hasattr(self.dialog, "cb_fillet"))
        self.assertFalse(self.dialog.table_sizes.isColumnHidden(5))
        self.dialog.table_sizes.item(0, 1).setText("42")
        self.dialog._commit_current_family_edits()
        self.assertTrue(self.dialog.current_lib_data["Square Hollow"]["fillet"])
        picker = AddFamilyDialog(self.dialog)
        self.addCleanup(picker.close)
        self.assertIsInstance(picker.cb_fillet, QtWidgets.QCheckBox)

    def test_delete_requires_real_selection(self):
        self.family("Square Hollow")
        table = self.dialog.table_sizes
        table.setCurrentCell(0, 0)
        table.selectRow(0)
        self.assertTrue(self.dialog.btn_del_size.isEnabled())
        table.clearSelection()
        self.assertFalse(self.dialog.btn_del_size.isEnabled())
        self.dialog._on_delete_size()
        self.assertEqual(table.rowCount(), 1)
        self.family("Pipe")
        self.assertFalse(self.dialog.btn_del_size.isEnabled())

    def test_clear_selection_disables_library_and_family_removal(self):
        self.family("Square Hollow")
        self.dialog.list_families.clearSelection()
        self.dialog.list_libraries.clearSelection()
        self.assertFalse(self.dialog.btn_del_family.isEnabled())
        self.assertFalse(self.dialog.btn_del_lib.isEnabled())
        before = copy.deepcopy(self.dialog.current_lib_data)
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.dialog._on_delete_family()
            self.dialog._on_delete_library()
        question.assert_not_called()
        self.assertEqual(self.dialog.current_lib_data, before)

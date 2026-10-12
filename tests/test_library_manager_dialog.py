import os
import shutil
import tempfile
import unittest

from freecad.frameforge.library_manager import LibraryManager


class TestLibraryManagerDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set offscreen platform for headless Qt execution
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_dialog_user_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)

    def tearDown(self):
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def test_dialog_lifecycle_and_crud(self):
        try:
            from PySide import QtWidgets
        except ImportError:
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)

        # 1. Verify libraries populated in list
        self.assertGreater(dialog.list_libraries.count(), 0)

        # 2. Check stock library selection (read-only mode)
        dialog.list_libraries.setCurrentRow(0)
        self.assertFalse(dialog.btn_del_lib.isEnabled())

        # 3. Create a user library directly via manager and refresh dialog
        test_data = {
            "_metadata": {"name": "Indumatics Test"},
            "Square Hollow": {
                "norm": "Indumatics",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "40x40x2": {
                        "Height": "40",
                        "Width": "40",
                        "Thickness": "2",
                        "Flange Thickness": "0",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": "0.82",
                    }
                },
            },
        }
        self.manager.save_user_library("Indumatics Test", test_data)
        dialog.refresh_libraries(select_name="Indumatics Test")

        # Verify selected user library is editable
        self.assertTrue(dialog.btn_del_lib.isEnabled())
        self.assertTrue(dialog.btn_save.isEnabled())

        # Verify family and sizes loaded
        self.assertEqual(dialog.combo_family.currentText(), "Square Hollow")
        self.assertEqual(dialog.table_sizes.rowCount(), 1)
        self.assertEqual(dialog.table_sizes.item(0, 0).text(), "40x40x2")

        # 4. Add a size row
        dialog._on_add_size()
        self.assertEqual(dialog.table_sizes.rowCount(), 2)

        # Modify new row values
        dialog.table_sizes.item(1, 0).setText("60x60x3")
        dialog.table_sizes.item(1, 1).setText("60")
        dialog.table_sizes.item(1, 2).setText("60")
        dialog.table_sizes.item(1, 3).setText("3")

        # 5. Save changes
        dialog._on_save_library()

        # Verify disk persistence
        reloaded = self.manager.get_library("Indumatics Test")
        self.assertIn("60x60x3", reloaded["Square Hollow"]["sizes"])
        self.assertEqual(reloaded["Square Hollow"]["sizes"]["60x60x3"]["Height"], "60")

    def test_family_switch_preserves_edits(self):
        try:
            from PySide import QtWidgets
        except ImportError:
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog

        test_data = {
            "_metadata": {"name": "MultiFamily"},
            "FamilyA": {
                "norm": "NormA",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {"A1": {"Height": "10", "Width": "10", "Thickness": "1"}},
            },
            "FamilyB": {
                "norm": "NormB",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {"B1": {"Height": "20", "Width": "20", "Thickness": "2"}},
            },
        }
        self.manager.save_user_library("MultiFamily", test_data)
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        dialog.refresh_libraries(select_name="MultiFamily")

        # Select FamilyA and edit table
        dialog.combo_family.setCurrentText("FamilyA")
        dialog.table_sizes.item(0, 1).setText("99")  # Change Height of A1 to 99
        dialog.le_norm.setText("NormA_Modified")

        # Switch to FamilyB
        dialog.combo_family.setCurrentText("FamilyB")
        self.assertEqual(dialog.combo_family.currentText(), "FamilyB")

        # Save library
        dialog._on_save_library()

        # Reload from disk and verify FamilyA edits were committed and persisted
        saved = self.manager.get_library("MultiFamily")
        self.assertEqual(saved["FamilyA"]["sizes"]["A1"]["Height"], "99")
        self.assertEqual(saved["FamilyA"]["norm"], "NormA_Modified")


if __name__ == "__main__":
    unittest.main()

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

    def test_dialog_wood_density_calculation(self):
        try:
            from PySide import QtWidgets
        except ImportError:
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        from freecad.frameforge.library_manager import STANDARD_DENSITIES, calculate_linear_weight
        from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog

        test_data = {
            "_metadata": {"name": "WoodTest"},
            "Square": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {"100x100": {"Height": "100", "Width": "100", "Thickness": "0"}},
            },
        }
        self.manager.save_user_library("WoodTest", test_data)
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        dialog.refresh_libraries(select_name="WoodTest")

        # Simulate the item text from QInputDialog for Wood (Soft) and Wood (Hard)
        for wood_label, expected_key in [
            ("Wood (Soft) (0.55 g/cm³)", "Wood (Soft)"),
            ("Wood (Hard) (0.75 g/cm³)", "Wood (Hard)"),
        ]:
            parsed_key = wood_label.rsplit(" (", 1)[0]
            self.assertEqual(parsed_key, expected_key)
            self.assertIn(parsed_key, STANDARD_DENSITIES)
            density = STANDARD_DENSITIES[parsed_key]
            weight = calculate_linear_weight("Square", 100.0, 100.0, 0, density)
            self.assertAlmostEqual(weight, 5.5 if "Soft" in wood_label else 7.5, places=2)

    def test_add_multiple_sizes_generates_unique_codes_and_persists(self):
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
            "_metadata": {"name": "UniqueSizesLib"},
            "Square": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {},
            },
        }
        self.manager.save_user_library("UniqueSizesLib", test_data)
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        dialog.refresh_libraries(select_name="UniqueSizesLib")

        # Add two sizes
        dialog._on_add_size()
        dialog._on_add_size()

        self.assertEqual(dialog.table_sizes.rowCount(), 2)
        code1 = dialog.table_sizes.item(0, 0).text()
        code2 = dialog.table_sizes.item(1, 0).text()

        # Codes must be distinct
        self.assertNotEqual(code1, code2)
        self.assertEqual(code1, "Nuevo_50x50x2")
        self.assertEqual(code2, "Nuevo_50x50x2_1")

        # Edit dimensions on both
        dialog.table_sizes.item(0, 1).setText("50")
        dialog.table_sizes.item(1, 1).setText("70")

        # Save and reload
        dialog._on_save_library()
        reloaded = self.manager.get_library("UniqueSizesLib")
        self.assertIn(code1, reloaded["Square"]["sizes"])
        self.assertIn(code2, reloaded["Square"]["sizes"])
        self.assertEqual(reloaded["Square"]["sizes"][code1]["Height"], "50")
        self.assertEqual(reloaded["Square"]["sizes"][code2]["Height"], "70")


if __name__ == "__main__":
    unittest.main()

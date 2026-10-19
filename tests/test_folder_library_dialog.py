import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import STANDARD_DENSITIES, LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    NewLibraryDialog,
    ProfileLibraryManagerDialog,
)


class TestFolderLibraryDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix="ff_test_folder_dialog_")
        self.user_dir = os.path.join(self.test_root, "user")
        self.stock_dir = os.path.join(self.test_root, "stock")
        self.reg_dir = os.path.join(self.test_root, "registry")
        self.reg_path = os.path.join(self.reg_dir, "folders.json")
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.stock_dir, exist_ok=True)
        os.makedirs(self.reg_dir, exist_ok=True)

        # Create a stock library for testing read-only invariants
        stock_data = {
            "_metadata": {"name": "StockSteel", "material": "Steel", "density": 7.85},
            "Square Hollow": {
                "norm": "EN 10219",
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
                        "Weight": "2.4",
                    }
                },
            },
        }
        with open(os.path.join(self.stock_dir, "stock_steel.json"), "w", encoding="utf-8") as f:
            json.dump(stock_data, f)

        self.manager = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def tearDown(self):
        if os.path.exists(self.test_root):
            shutil.rmtree(self.test_root)

    def test_r1_header_compact_actions_and_tooltips_present(self):
        """R1: Dialog provides New Folder Library and Register Folder Library buttons."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)

        self.assertTrue(hasattr(dialog, "btn_new_folder_lib"))
        self.assertTrue(hasattr(dialog, "btn_register_folder_lib"))
        self.assertEqual(dialog.btn_new_folder_lib.size(), QtCore.QSize(26, 26))
        self.assertEqual(dialog.btn_register_folder_lib.size(), QtCore.QSize(26, 26))
        self.assertFalse(dialog.btn_new_folder_lib.icon().isNull())
        self.assertFalse(dialog.btn_register_folder_lib.icon().isNull())
        self.assertEqual(dialog.btn_new_folder_lib.toolTip(), translate("frameforge", "New Folder Library"))
        self.assertEqual(
            dialog.btn_register_folder_lib.toolTip(),
            translate("frameforge", "Register Folder Library"),
        )
        self.assertEqual(dialog.btn_new_folder_lib.parentWidget(), dialog.list_libraries.parentWidget())
        self.assertEqual(dialog.btn_register_folder_lib.parentWidget(), dialog.list_libraries.parentWidget())

    def test_r2_new_folder_library_create_flow_and_persistence(self):
        """R2: New folder library creation initializes manifest and selects library."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)

        new_dir = os.path.join(self.test_root, "my_new_folder_lib")
        os.makedirs(new_dir, exist_ok=True)

        with (
            patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=new_dir),
            patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(NewLibraryDialog, "get_values", return_value=("Alu Folder", "Aluminium", 2.7, False)),
        ):
            dialog.btn_new_folder_lib.click()

        manifest_path = os.path.join(new_dir, "library.json")
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["_metadata"]["name"], "Alu Folder")
        self.assertEqual(manifest["_metadata"]["material"], "Aluminium")
        self.assertEqual(manifest["_metadata"]["density"], 2.7)
        self.assertTrue(manifest["_metadata"]["is_folder"])

        current_item = dialog.list_libraries.currentItem()
        self.assertIsNotNone(current_item)
        self.assertTrue(current_item.text().startswith(translate("frameforge", "[Folder] ")))
        self.assertIn("Alu Folder", current_item.text())
        self.assertEqual(current_item.data(QtCore.Qt.UserRole)["name"], "Alu Folder")
        self.assertEqual(current_item.toolTip(), new_dir)
        self.assertIn("Alu Folder", dialog.lbl_status.text())

    def test_r3_register_existing_folder_library_in_place(self):
        """R3: Register existing folder library discovers catalog without modifying files."""
        existing_dir = os.path.join(self.test_root, "existing_workshop")
        self.manager.create_folder_library(
            folder_path=existing_dir,
            name="Workshop Existing",
            material="Wood",
            density=0.7,
        )
        manifest_path = os.path.join(existing_dir, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            initial_content = f.read()

        # Unregister from manager so we can register it through UI
        self.manager.unregister_folder_library("Workshop Existing")

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        names = [
            dialog.list_libraries.item(i).data(QtCore.Qt.UserRole)["name"] for i in range(dialog.list_libraries.count())
        ]
        self.assertNotIn("Workshop Existing", names)

        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=existing_dir):
            dialog.btn_register_folder_lib.click()

        current_item = dialog.list_libraries.currentItem()
        self.assertEqual(current_item.data(QtCore.Qt.UserRole)["name"], "Workshop Existing")
        self.assertTrue(current_item.text().startswith(translate("frameforge", "[Folder] ")))

        with open(manifest_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), initial_content)

    def test_r4_selected_folder_tag_banner_tooltip_and_duplicate_guard(self):
        """R4: Folder selection updates banner with path, configures delete/duplicate buttons."""
        folder_dir = os.path.join(self.test_root, "timber_profiles")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Timber Lib",
            material="Wood",
            density=0.7,
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="Timber Lib")

        self.assertEqual(
            dialog.lbl_lib_banner.text(),
            translate("frameforge", "Folder Library: %s%s | Material: %s (Editable)")
            % ("Timber Lib", f" | {folder_dir}", f"{translate('frameforge', 'Wood')} (0.7 g/cm³)"),
        )
        self.assertIn(translate("frameforge", "Wood"), dialog.lbl_lib_banner.text())
        self.assertIn(folder_dir, dialog.lbl_lib_banner.text())
        self.assertEqual(dialog.lbl_lib_banner.toolTip(), folder_dir)

        # Contextual Unregister tooltip on delete button
        self.assertTrue(dialog.btn_del_lib.isEnabled())
        self.assertEqual(
            dialog.btn_del_lib.toolTip(),
            translate("frameforge", "Unregister Folder Library"),
        )

        # T6 duplicate button enabled for folder libraries
        self.assertTrue(dialog.btn_dup_lib.isEnabled())
        self.assertEqual(dialog.btn_dup_lib.toolTip(), translate("frameforge", "Duplicate Library"))

        # When clicked with directory picker canceled, retains current library without throwing
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
            dialog.btn_dup_lib.click()
            # If clicked with canceled picker, it must retain current selection without throwing
            names = [
                dialog.list_libraries.item(i).data(QtCore.Qt.UserRole)["name"]
                for i in range(dialog.list_libraries.count())
            ]
            self.assertEqual(names.count("Timber Lib"), 1)

    def test_r5_save_folder_library_manifest(self):
        """R5: Saving modifications updates folder library.json without mutating user_dir."""
        folder_dir = os.path.join(self.test_root, "saveable_folder")
        initial_data = {
            "Square Hollow": {
                "norm": "Original Norm",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Flange Thickness": "0",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": "1.0",
                    }
                },
            }
        }
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Saveable Lib",
            material="Steel",
            density=7.85,
            data=initial_data,
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="Saveable Lib")

        dialog.le_norm.setText("ISO 10799-Folder")
        self.assertTrue(dialog.is_dirty)

        dialog.btn_save.click()
        self.assertFalse(dialog.is_dirty)

        manifest_path = os.path.join(folder_dir, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["Square Hollow"]["norm"], "ISO 10799-Folder")
        self.assertEqual(manifest["_metadata"]["name"], "Saveable Lib")
        self.assertTrue(manifest["_metadata"]["is_folder"])

        # Ensure no stray JSON was written to user_dir
        self.assertEqual(os.listdir(self.user_dir), [])

    def test_r6_safe_unregister_keeps_files_and_never_calls_delete_user_library(self):
        """R6: Unregistering folder library removes local registry entry and keeps all disk files."""
        folder_dir = os.path.join(self.test_root, "unregister_target")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Unregister Me",
            material="Steel",
            density=7.85,
        )
        # Put an extra file in folder to verify retention
        canary_file = os.path.join(folder_dir, "canary.txt")
        with open(canary_file, "w") as f:
            f.write("CANARY")

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="Unregister Me")

        with (
            patch.object(self.manager, "delete_user_library") as mock_delete,
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes),
        ):
            dialog.btn_del_lib.click()
            mock_delete.assert_not_called()

        # Files on disk must remain completely intact
        self.assertTrue(os.path.isfile(os.path.join(folder_dir, "library.json")))
        self.assertTrue(os.path.isfile(canary_file))
        self.assertEqual(open(canary_file).read(), "CANARY")

        # But library should be unregistered from manager and UI
        names = [
            dialog.list_libraries.item(i).data(QtCore.Qt.UserRole)["name"] for i in range(dialog.list_libraries.count())
        ]
        self.assertNotIn("Unregister Me", names)

    def test_r7_cancel_create_register_unregister_leaves_filesystem_and_state_unchanged(self):
        """R7: User cancelling folder dialogs leaves files and selection intact."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)

        initial_count = dialog.list_libraries.count()

        # 1. Cancel New Folder Directory Picker
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
            dialog.btn_new_folder_lib.click()
        self.assertEqual(dialog.list_libraries.count(), initial_count)

        # 2. Cancel New Folder Name Dialog
        target_dir = os.path.join(self.test_root, "unused_dir")
        os.makedirs(target_dir, exist_ok=True)
        with (
            patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=target_dir),
            patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Rejected),
        ):
            dialog.btn_new_folder_lib.click()
        self.assertEqual(dialog.list_libraries.count(), initial_count)
        self.assertFalse(os.path.exists(os.path.join(target_dir, "library.json")))

        # 3. Cancel Register Directory Picker
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
            dialog.btn_register_folder_lib.click()
        self.assertEqual(dialog.list_libraries.count(), initial_count)

    def test_r8_invalid_folder_or_collision_error_preserves_selection_and_dirty_edits(self):
        """R8: Creation or registration error shows warning and retains dirty edits."""
        # Create a user library and mark it dirty
        self.manager.save_user_library(
            "UserLib",
            {
                "_metadata": {"name": "UserLib"},
                "Square Hollow": {"norm": "Original", "fillet": False, "sizes": {"50x50x2": {"Height": "50"}}},
            },
        )
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="UserLib")

        dialog.le_norm.setText("UnsavedNormEdit")
        self.assertTrue(dialog.is_dirty)

        # Attempt to register non-existent folder
        with (
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Cancel),
            patch.object(
                QtWidgets.QFileDialog, "getExistingDirectory", return_value=os.path.join(self.test_root, "nonexistent")
            ),
            patch.object(QtWidgets.QMessageBox, "warning") as mock_warn,
        ):
            dialog.btn_register_folder_lib.click()

        self.assertEqual(dialog.current_lib_meta["name"], "UserLib")
        self.assertEqual(dialog.le_norm.text(), "UnsavedNormEdit")
        self.assertTrue(dialog.is_dirty)

    def test_r9_corrupt_registry_refresh_retains_selection_and_data(self):
        """R9: Damaged registry on refresh shows error without clearing list or losing current edits."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)

        initial_count = dialog.list_libraries.count()
        self.assertGreater(initial_count, 0)

        # Corrupt the registry file on disk
        with open(self.reg_path, "w") as f:
            f.write("{ invalid json corrupted ")

        with (
            patch.object(QtWidgets.QMessageBox, "critical") as mock_crit,
            patch.object(QtWidgets.QMessageBox, "warning") as mock_warn,
        ):
            success = dialog.refresh_libraries()
            self.assertFalse(success)

        # List must not have been wiped out
        self.assertEqual(dialog.list_libraries.count(), initial_count)

    def test_r10_legacy_controls_and_compatibility(self):
        """R10: Legacy NewLibraryDialog 4-tuple and stock library read-only controls preserved."""
        dlg = NewLibraryDialog(None, title="New Library", default_material="Steel")
        name, mat, dens, recalc = dlg.get_values()
        self.assertEqual(name, "")
        self.assertEqual(mat, "Steel")
        self.assertEqual(dens, 7.85)
        self.assertFalse(recalc)
        dlg.close()

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="StockSteel")

        # Stock library invariant: cannot delete or unregister, cannot save
        self.assertFalse(dialog.btn_del_lib.isEnabled())
        self.assertFalse(dialog.btn_save.isEnabled())
        self.assertTrue(dialog.btn_dup_lib.isEnabled())
        self.assertEqual(dialog.btn_dup_lib.toolTip(), translate("frameforge", "Duplicate Library"))
        self.assertEqual(dialog.btn_del_lib.toolTip(), translate("frameforge", "Delete Library"))

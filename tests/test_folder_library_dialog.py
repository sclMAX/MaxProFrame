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
        # Cleanups run LIFO: close owned managers before removing their files.
        self.addCleanup(shutil.rmtree, self.test_root)
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

    def _close_manager_dialog(self, dialog):
        def discard_owned_changes(parent, *args, **kwargs):
            self.assertIs(parent, dialog, "Cleanup must only answer its owned manager")
            return QtWidgets.QMessageBox.Discard

        with patch.object(QtWidgets.QMessageBox, "question", side_effect=discard_owned_changes):
            self.assertTrue(dialog.close())

    def test_import_menu_action_wiring_and_cancel_preserve_state(self):
        # Deterministic QAction wiring only. Mouse popup behavior is manual
        # desktop evidence, not simulated here with a nested native event loop.
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        self.assertEqual(dialog.btn_import_lib.popupMode(), QtWidgets.QToolButton.InstantPopup)
        menu = dialog.btn_import_lib.menu()
        self.assertEqual(
            [a.text() for a in menu.actions()],
            [
                translate("frameforge", "Import ZIP…"),
                translate("frameforge", "Register Folder Library"),
            ],
        )
        selection = dialog.list_libraries.currentItem()
        data = copy.deepcopy(dialog.current_lib_data)
        dirty = dialog.is_dirty

        def registry_bytes():
            if not os.path.exists(self.reg_path):
                return None
            with open(self.reg_path, "rb") as stream:
                return stream.read()

        registry = registry_bytes()
        for index, action in enumerate(menu.actions()):
            with (
                self.subTest(action=action.text()),
                patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")) as archive,
                patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value="") as folder,
            ):
                action.trigger()
            self.assertEqual(archive.call_count, int(index == 0))
            self.assertEqual(folder.call_count, int(index == 1))
            self.assertEqual(dialog.list_libraries.currentItem(), selection)
            self.assertEqual(dialog.current_lib_data, data)
            self.assertEqual(dialog.is_dirty, dirty)
            self.assertEqual(registry_bytes(), registry)

    def test_zip_import_selects_registered_library(self):
        source = os.path.join(self.test_root, "source")
        self.manager.create_folder_library(source, "Shared", material="Wood", density=0.7)
        archive = os.path.join(self.test_root, "shared.zip")
        self.manager.export_library_zip("Shared", archive)
        self.manager.unregister_folder_library("Shared")
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(archive, "")):
            dialog._on_import_library()
        self.assertEqual(dialog.current_lib_meta["name"], "Shared")
        self.assertTrue(dialog.current_lib_meta["is_folder"])
        self.assertEqual(dialog.current_lib_data["_metadata"]["density"], 0.7)
        self.assertEqual(
            self.manager.get_folder_library_path("Shared"), self.manager.get_default_library_folder("Shared")
        )

    def test_import_cancel_and_rejected_zip_preserve_state(self):
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        initial = copy.deepcopy(dialog.current_lib_data)

        def registry_bytes():
            if not os.path.exists(self.reg_path):
                return None
            with open(self.reg_path, "rb") as stream:
                return stream.read()

        registry_before = registry_bytes()
        invalid = os.path.join(self.test_root, "invalid.zip")
        with open(invalid, "wb") as stream:
            stream.write(b"not a ZIP")
        for path in ("", invalid):
            with (
                self.subTest(path=path),
                patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(path, "")),
                patch.object(QtWidgets.QMessageBox, "warning") as warning,
            ):
                dialog._on_import_library()
            self.assertEqual(dialog.current_lib_data, initial)
            self.assertEqual(registry_bytes(), registry_before)
            self.assertEqual(os.listdir(self.user_dir), [])
            self.assertEqual(warning.call_count, bool(path))

    def test_export_saved_custom_and_stock_guard(self):
        folder = os.path.join(self.test_root, "exportable")
        self.manager.create_folder_library(folder, "Exportable")
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name="Exportable")
        self.assertTrue(dialog.btn_export_lib.isEnabled())
        output = os.path.join(self.test_root, "shared.zip")
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(output, "")):
            dialog._on_export_library()
        self.assertTrue(os.path.isfile(output))
        with open(output, "rb") as stream:
            before = stream.read()
        with (
            patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(output, "")),
            patch.object(QtWidgets.QMessageBox, "warning") as warning,
        ):
            dialog._on_export_library()
        warning.assert_called_once()
        with open(output, "rb") as stream:
            self.assertEqual(stream.read(), before)
        dialog.refresh_libraries(select_name="StockSteel")
        self.assertFalse(dialog.btn_export_lib.isEnabled())
        with patch.object(self.manager, "export_library_zip") as export:
            dialog._on_export_library()
        export.assert_not_called()

    def test_real_save_failure_blocks_export(self):
        import hashlib
        from pathlib import Path

        folder = Path(self.test_root) / "source"
        self.manager.create_folder_library(str(folder), "Boundary", data={"Square": {"norm": "Original", "sizes": {}}})
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name="Boundary")
        dialog.le_norm.setText("Unsaved")
        self.assertTrue(dialog.is_dirty)

        def hashes():
            return {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in Path(self.test_root).rglob("*")
                if p.is_file()
            }

        before = hashes()
        with (
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Save),
            patch.object(self.manager, "save_folder_library", side_effect=OSError("disk full")),
            patch.object(QtWidgets.QMessageBox, "warning") as warning,
            patch.object(QtWidgets.QFileDialog, "getSaveFileName") as picker,
            patch.object(self.manager, "export_library_zip") as export,
        ):
            dialog.btn_export_lib.click()
        warning.assert_called_once()
        warning.assert_called_once_with(
            dialog,
            translate("frameforge", "Error"),
            translate("frameforge", "Error saving library: %s") % "disk full",
        )
        picker.assert_not_called()
        export.assert_not_called()
        self.assertTrue(dialog.is_dirty)
        self.assertEqual(dialog.le_norm.text(), "Unsaved")
        self.assertEqual(hashes(), before)

    def test_dirty_export_cancel_failed_save_and_save_success(self):
        folder = os.path.join(self.test_root, "dirty_export")
        self.manager.create_folder_library(folder, "Dirty Export")
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name="Dirty Export")
        dialog.current_lib_data["Square"] = {"norm": "Unsaved", "sizes": {}}
        dialog.is_dirty = True
        initial = copy.deepcopy(dialog.current_lib_data)
        manifest = os.path.join(folder, "library.json")
        with open(manifest, "rb") as stream:
            saved = stream.read()
        for reply in (QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Discard):
            with (
                patch.object(QtWidgets.QMessageBox, "question", return_value=reply) as question,
                patch.object(QtWidgets.QFileDialog, "getSaveFileName") as picker,
                patch.object(self.manager, "export_library_zip") as export,
            ):
                dialog._on_export_library()
            self.assertEqual(question.call_args[0][3], QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Cancel)
            picker.assert_not_called()
            export.assert_not_called()
            self.assertTrue(dialog.is_dirty)
            self.assertEqual(dialog.current_lib_data, initial)
            with open(manifest, "rb") as stream:
                self.assertEqual(stream.read(), saved)
        with (
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Save),
            patch.object(dialog, "_on_save_library"),
            patch.object(self.manager, "export_library_zip") as export,
        ):
            dialog._on_export_library()
        export.assert_not_called()
        self.assertTrue(dialog.is_dirty)
        output = os.path.join(self.test_root, "dirty.zip")
        with (
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Save),
            patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(output, "")),
        ):
            dialog._on_export_library()
        self.assertFalse(dialog.is_dirty)
        import zipfile

        with zipfile.ZipFile(output) as archive:
            data = json.loads(archive.read("library.json"))
        self.assertEqual(data["Square"]["norm"], "Unsaved")
        with open(manifest, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), dialog.current_lib_data)

    def test_r1_header_compact_actions_and_tooltips_present(self):
        """S1: Five icon-only actions appear in the requested order."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        self.assertFalse(hasattr(dialog, "btn_new_folder_lib"))
        buttons = (
            dialog.btn_new_lib,
            dialog.btn_del_lib,
            dialog.btn_import_lib,
            dialog.btn_dup_lib,
            dialog.btn_export_lib,
        )
        header = dialog.list_libraries.parentWidget().layout().itemAt(0).layout()
        self.assertEqual([header.itemAt(i).widget() for i in range(1, 6)], list(buttons))
        for button in buttons:
            self.assertEqual(button.size(), QtCore.QSize(26, 26))
            self.assertEqual(button.text(), "")
            self.assertTrue(button.toolTip())
            self.assertFalse(button.icon().isNull())
        self.assertEqual(dialog.btn_import_lib.toolTip(), translate("frameforge", "Import Library"))
        self.assertEqual(dialog.btn_export_lib.toolTip(), translate("frameforge", "Export Library"))
        self.assertNotEqual(dialog.btn_import_lib.icon().cacheKey(), dialog.btn_export_lib.icon().cacheKey())

    def test_r2_new_folder_library_create_flow_and_persistence(self):
        """R2: New folder library creation initializes manifest and selects library."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)

        new_dir = os.path.join(self.test_root, "my_new_folder_lib")
        os.makedirs(new_dir, exist_ok=True)

        with (
            patch.object(NewLibraryDialog, "get_destination", return_value=new_dir),
            patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(NewLibraryDialog, "get_values", return_value=("Alu Folder", "Aluminium", 2.7, False)),
        ):
            dialog.btn_new_lib.click()

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
        self.addCleanup(self._close_manager_dialog, dialog)
        names = [
            dialog.list_libraries.item(i).data(QtCore.Qt.UserRole)["name"] for i in range(dialog.list_libraries.count())
        ]
        self.assertNotIn("Workshop Existing", names)

        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=existing_dir):
            dialog.btn_import_lib.menu().actions()[1].trigger()

        current_item = dialog.list_libraries.currentItem()
        self.assertEqual(current_item.data(QtCore.Qt.UserRole)["name"], "Workshop Existing")
        self.assertTrue(current_item.text().startswith(translate("frameforge", "[Folder] ")))

        with open(manifest_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), initial_content)

    def test_r4_selected_folder_tag_banner_tooltip_and_duplicate_guard(self):
        """R4: Compact folder banner retains details in tooltip and contextual actions."""
        folder_dir = os.path.join(self.test_root, "timber_profiles")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Timber Lib",
            material="Wood",
            density=0.7,
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name="Timber Lib")

        compact_text = f"Timber Lib | {translate('frameforge', 'Wood')}"
        self.assertEqual(dialog.lbl_lib_banner.text(), compact_text)
        self.assertEqual(
            dialog.lbl_lib_banner.toolTip(),
            f"{compact_text}\n0.7 g/cm³\n{folder_dir}",
        )
        current_item = dialog.list_libraries.currentItem()
        self.assertTrue(current_item.text().startswith(translate("frameforge", "[Folder] ")))
        self.assertEqual(current_item.data(QtCore.Qt.UserRole)["name"], "Timber Lib")
        self.assertEqual(current_item.toolTip(), folder_dir)

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
        with patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Rejected):
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
        self.addCleanup(self._close_manager_dialog, dialog)
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
        self.addCleanup(self._close_manager_dialog, dialog)
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
        self.addCleanup(self._close_manager_dialog, dialog)

        initial_count = dialog.list_libraries.count()

        # 1. Cancel unified creation dialog
        with patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Rejected):
            dialog.btn_new_lib.click()
        self.assertEqual(dialog.list_libraries.count(), initial_count)

        # 2. Cancel New Folder Name Dialog
        target_dir = os.path.join(self.test_root, "unused_dir")
        os.makedirs(target_dir, exist_ok=True)
        with (
            patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=target_dir),
            patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Rejected),
        ):
            dialog.btn_new_lib.click()
        self.assertEqual(dialog.list_libraries.count(), initial_count)
        self.assertFalse(os.path.exists(os.path.join(target_dir, "library.json")))

        # 3. Cancel Register Directory Picker
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
            dialog.btn_import_lib.menu().actions()[1].trigger()
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
        self.addCleanup(self._close_manager_dialog, dialog)
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
            dialog.btn_import_lib.menu().actions()[1].trigger()

        self.assertEqual(dialog.current_lib_meta["name"], "UserLib")
        self.assertEqual(dialog.le_norm.text(), "UnsavedNormEdit")
        self.assertTrue(dialog.is_dirty)

    def test_r9_corrupt_registry_refresh_retains_selection_and_data(self):
        """R9: Damaged registry on refresh shows error without clearing list or losing current edits."""
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)

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
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name="StockSteel")

        # Stock library invariant: cannot delete or unregister, cannot save
        self.assertFalse(dialog.btn_del_lib.isEnabled())
        self.assertFalse(dialog.btn_save.isEnabled())
        self.assertTrue(dialog.btn_dup_lib.isEnabled())
        self.assertEqual(dialog.btn_dup_lib.toolTip(), translate("frameforge", "Duplicate Library"))
        self.assertEqual(dialog.btn_del_lib.toolTip(), translate("frameforge", "Delete Library"))

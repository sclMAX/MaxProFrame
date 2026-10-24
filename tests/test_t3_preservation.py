"""Regression coverage for folder UI unsaved-data preservation (D1-D4)."""

import hashlib
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    NewLibraryDialog,
    ProfileLibraryManagerDialog,
    QtCore,
    QtWidgets,
)


class TestT3Preservation(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_t3_preservation_")
        self.addCleanup(self.workspace.cleanup)
        self.root = self.workspace.name
        self.manager = LibraryManager(
            user_dir=os.path.join(self.root, "user"),
            stock_dir=os.path.join(self.root, "stock"),
            registry_path=os.path.join(self.root, "registry", "folders.json"),
        )
        self.paths = {}
        for name in ("A", "B"):
            self.paths[name] = os.path.join(self.root, name)
            self.manager.create_folder_library(
                self.paths[name],
                name,
                data={
                    "Square Hollow": {
                        "norm": name + " original",
                        "fillet": False,
                        "sizes": {"S": {"Height": "20", "Width": "20", "Thickness": "2"}},
                    },
                },
            )
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.dialog.refresh_libraries(select_name="A")
        self.messages = ExitStack()
        self.addCleanup(self.messages.close)
        for method in ("warning", "critical", "information"):
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method))
        # LIFO: close the owned manager before message patches and files retire.
        self.addCleanup(self._close_manager_dialog, self.dialog)

    def _close_manager_dialog(self, dialog):
        def discard_owned_changes(parent, *args, **kwargs):
            self.assertIs(parent, dialog)
            return QtWidgets.QMessageBox.Discard

        with patch.object(QtWidgets.QMessageBox, "question", side_effect=discard_owned_changes):
            self.assertTrue(dialog.close())

    def snapshot(self):
        return {
            os.path.relpath(os.path.join(root, file), self.root): open(os.path.join(root, file), "rb").read()
            for root, _, files in os.walk(self.root)
            for file in files
        }

    def dirty(self):
        self.dialog.le_norm.setText("KEEP UNSAVED")
        self.assertTrue(self.dialog.is_dirty)

    def select_b(self):
        for index in range(self.dialog.list_libraries.count()):
            item = self.dialog.list_libraries.item(index)
            if item.data(QtCore.Qt.UserRole)["name"] == "B":
                self.dialog.list_libraries.setCurrentItem(item)
                return
        self.fail("B missing")

    def assert_preserved(self, disk):
        self.assertEqual(self.dialog.current_lib_meta["name"], "A")
        self.assertEqual(self.dialog.list_libraries.currentItem().data(QtCore.Qt.UserRole)["name"], "A")
        self.assertEqual(self.dialog.le_norm.text(), "KEEP UNSAVED")
        self.assertEqual(self.dialog.current_family, "Square Hollow")
        self.assertTrue(self.dialog.is_dirty)
        self.assertEqual(self.snapshot(), disk)

    def test_d1_unregister_dirty_guard_and_cancel(self):
        self.dirty()
        disk = self.snapshot()
        titles = []

        def cancel(parent, title, *args):
            titles.append(title)
            return QtWidgets.QMessageBox.Cancel

        with patch.object(QtWidgets.QMessageBox, "question", side_effect=cancel):
            self.dialog.btn_del_lib.click()
        self.assertEqual(titles, [translate("frameforge", "Unsaved Changes")])
        self.assert_preserved(disk)

    def test_d1_discard_then_unregister_failure_or_no_keeps_dirty(self):
        for response in (QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes):
            with self.subTest(response=response):
                self.dirty()
                disk = self.snapshot()
                with (
                    patch.object(
                        QtWidgets.QMessageBox, "question", side_effect=[QtWidgets.QMessageBox.Discard, response]
                    ),
                    patch.object(self.manager, "unregister_folder_library", side_effect=OSError("unregister failed")),
                ):
                    self.dialog.btn_del_lib.click()
                self.assert_preserved(disk)

    def test_d1_discard_then_unregister_success_clears_dirty_and_unregisters(self):
        self.dirty()
        with patch.object(
            QtWidgets.QMessageBox, "question", side_effect=[QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Yes]
        ):
            self.dialog.btn_del_lib.click()
        self.assertFalse(self.dialog.is_dirty)
        self.assertEqual(self.dialog.current_lib_meta["name"], "B")
        self.assertEqual(self.manager.list_libraries()[0]["name"], "B")

    def test_d2_discard_then_canceled_or_failed_action_retains_guard(self):
        cases = (
            "new-picker-cancel",
            "register-picker-cancel",
            "new-name-reject",
            "register-missing",
            "new-collision",
            "new-write-error",
        )
        for case in cases:
            with self.subTest(case=case), ExitStack() as stack:
                self.dirty()
                disk = self.snapshot()
                stack.enter_context(
                    patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard)
                )
                stack.enter_context(
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getExistingDirectory",
                        return_value="" if "picker-cancel" in case else os.path.join(self.root, "new"),
                    )
                )
                stack.enter_context(
                    patch.object(
                        NewLibraryDialog,
                        "exec_",
                        return_value=(
                            QtWidgets.QDialog.Rejected
                            if case in ("new-name-reject", "new-picker-cancel")
                            else QtWidgets.QDialog.Accepted
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(NewLibraryDialog, "get_values", return_value=("Created", "Steel", 7.85, False))
                )
                stack.enter_context(
                    patch.object(NewLibraryDialog, "get_destination", return_value=os.path.join(self.root, "new"))
                )
                if case == "new-collision":
                    stack.enter_context(
                        patch.object(self.manager, "create_folder_library", side_effect=FileExistsError("collision"))
                    )
                if case == "new-write-error":
                    stack.enter_context(
                        patch.object(self.manager, "create_folder_library", side_effect=OSError("write failed"))
                    )
                if case.startswith("register"):
                    self.dialog.btn_import_lib.menu().actions()[1].trigger()
                else:
                    self.dialog.btn_new_lib.click()
                self.assert_preserved(disk)
                with patch.object(
                    QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Cancel
                ) as prompt:
                    self.select_b()
                    prompt.assert_called_once()
                self.assert_preserved(disk)

    def test_d3_failed_selection_keeps_metadata_family_and_edits(self):
        self.dirty()
        disk = self.snapshot()
        original = self.manager.get_library

        def fail_b(name):
            if name == "B":
                raise OSError("load B failed")
            return original(name)

        with (
            patch.object(self.manager, "get_library", side_effect=fail_b),
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard),
        ):
            self.select_b()
        self.assert_preserved(disk)
        self.dialog.btn_save.click()
        self.assertEqual(self.manager.get_library("A")["Square Hollow"]["norm"], "KEEP UNSAVED")
        self.assertEqual(self.manager.get_library("B")["Square Hollow"]["norm"], "B original")

    def test_d3_refresh_get_library_failure_preserves_state(self):
        self.dirty()
        disk = self.snapshot()
        original = self.manager.get_library

        def fail_created(name):
            if name == "Created":
                raise OSError("load Created failed")
            return original(name)

        with (
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard),
            patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=os.path.join(self.root, "new")),
            patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(NewLibraryDialog, "get_values", return_value=("Created", "Steel", 7.85, False)),
            patch.object(self.manager, "create_folder_library"),
            patch.object(
                self.manager,
                "list_libraries",
                return_value=[
                    {"name": "A", "is_folder": True, "is_user": True},
                    {"name": "B", "is_folder": True, "is_user": True},
                    {"name": "Created", "is_folder": True, "is_user": True},
                ],
            ),
            patch.object(self.manager, "get_library", side_effect=fail_created),
        ):
            self.dialog.btn_new_lib.click()

        self.assert_preserved(disk)
        self.assertEqual(
            self.dialog.lbl_status.text(),
            translate("frameforge", "Error loading library '%s': %s") % ("Created", "load Created failed"),
        )

    def test_d4_refresh_error_not_overwritten_by_success(self):
        for action in ("create", "register"):
            with self.subTest(action=action), ExitStack() as stack:
                self.dirty()
                stack.enter_context(
                    patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard)
                )
                stack.enter_context(
                    patch.object(
                        QtWidgets.QFileDialog, "getExistingDirectory", return_value=os.path.join(self.root, "new")
                    )
                )
                stack.enter_context(patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Accepted))
                stack.enter_context(
                    patch.object(NewLibraryDialog, "get_values", return_value=("Created", "Steel", 7.85, False))
                )
                stack.enter_context(patch.object(self.manager, "create_folder_library"))
                stack.enter_context(
                    patch.object(self.manager, "register_folder_library", return_value={"name": "Created"})
                )
                stack.enter_context(patch.object(self.manager, "list_libraries", side_effect=OSError("refresh failed")))
                if action == "register":
                    self.dialog.btn_import_lib.menu().actions()[1].trigger()
                else:
                    self.dialog.btn_new_lib.click()
                self.assertEqual(
                    self.dialog.lbl_status.text(),
                    translate("frameforge", "Error loading libraries: %s") % "refresh failed",
                )
                self.assertTrue(self.dialog.is_dirty)
                self.assertEqual(self.dialog.le_norm.text(), "KEEP UNSAVED")
                self.assertEqual(self.dialog.current_lib_meta["name"], "A")

    def test_d4_create_and_register_success_switches_library_and_clears_dirty(self):
        for action in ("create", "register"):
            with self.subTest(action=action), ExitStack() as stack:
                self.dirty()
                target_path = os.path.join(self.root, f"new_{action}")
                stack.enter_context(
                    patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard)
                )
                stack.enter_context(
                    patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=target_path)
                )
                stack.enter_context(patch.object(NewLibraryDialog, "exec_", return_value=QtWidgets.QDialog.Accepted))
                stack.enter_context(
                    patch.object(NewLibraryDialog, "get_values", return_value=(f"Lib_{action}", "Steel", 7.85, False))
                )
                if action == "register":
                    self.manager.create_folder_library(target_path, f"Lib_{action}")
                    self.manager.unregister_folder_library(f"Lib_{action}")
                    self.dialog.refresh_libraries(select_name="A")
                    self.dirty()
                if action == "register":
                    self.dialog.btn_import_lib.menu().actions()[1].trigger()
                else:
                    self.dialog.btn_new_lib.click()
                self.assertEqual(self.dialog.current_lib_meta["name"], f"Lib_{action}")
                self.assertFalse(self.dialog.is_dirty)
                message = (
                    "Library '%s' created successfully."
                    if action == "create"
                    else "Folder library '%s' registered successfully."
                )
                self.assertEqual(self.dialog.lbl_status.text(), translate("frameforge", message) % f"Lib_{action}")

    def test_unregister_keeps_nested_assets_byte_identical(self):
        from pathlib import Path

        root = Path(self.paths["A"])
        (root / "sections").mkdir()
        (root / "sections" / "keep.FCStd").write_bytes(b"user owned sketch sentinel\x00")

        def hashes():
            return {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*")
                if p.is_file()
            }

        before = hashes()
        self.dirty()
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            side_effect=[
                QtWidgets.QMessageBox.Discard,
                QtWidgets.QMessageBox.Yes,
            ],
        ):
            self.dialog.btn_del_lib.click()
        self.assertEqual(hashes(), before)
        self.assertEqual(self.dialog.current_lib_meta["name"], "B")
        self.assertFalse(self.dialog.is_dirty)
        self.assertNotIn("A", [x["name"] for x in self.manager.list_libraries()])

    def test_failed_save_preserves_bytes_and_cancels_picker(self):
        self.dirty()
        before = self.snapshot()
        hashes = lambda data: {k: hashlib.sha256(v).hexdigest() for k, v in data.items()}
        with (
            patch.object(
                QtWidgets.QMessageBox,
                "question",
                return_value=QtWidgets.QMessageBox.Save,
            ),
            patch.object(
                self.manager,
                "save_folder_library",
                side_effect=OSError("disk full"),
            ),
            patch.object(QtWidgets.QFileDialog, "getExistingDirectory") as picker,
        ):
            self.dialog.btn_new_lib.click()
        picker.assert_not_called()
        self.assert_preserved(before)
        self.assertEqual(hashes(self.snapshot()), hashes(before))
        self.assertEqual(
            self.dialog.lbl_status.text(),
            translate("frameforge", "Error saving library: %s") % "disk full",
        )

    def test_existing_selection_save_discard_and_cancel(self):
        self.dirty()
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Save):
            self.select_b()
        self.assertEqual(self.dialog.current_lib_meta["name"], "B")
        self.assertFalse(self.dialog.is_dirty)
        self.assertEqual(self.manager.get_library("A")["Square Hollow"]["norm"], "KEEP UNSAVED")
        self.dialog.le_norm.setText("discard B")
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
            self.dialog.list_libraries.setCurrentRow(0)
        self.assertEqual(self.dialog.current_lib_meta["name"], "A")
        self.assertFalse(self.dialog.is_dirty)
        self.assertEqual(self.manager.get_library("B")["Square Hollow"]["norm"], "B original")

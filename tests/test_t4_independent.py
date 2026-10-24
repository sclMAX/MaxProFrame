"""Independent T4 invariant probes (E1-E4).

Original fixture SHA256: 9deb56a431eb71cebfbcadbd902f1ea117c92c30beb61a350d12b842e8a872c7.
Derived from the original probes, with owned-dialog Discard made explicit.
Discovery uses load_tests to run only the 4 independent cases.
"""
import copy
import hashlib
import os
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part

try:
    from test_folder_section_management import TestFolderSectionManagement as _Fixture
except ImportError:
    from tests.test_folder_section_management import TestFolderSectionManagement as _Fixture


class IndependentT4(_Fixture):
    def snapshot(self):
        return {os.path.relpath(os.path.join(root, name), self.folder_lib_path):
                hashlib.sha256(open(os.path.join(root, name), "rb").read()).hexdigest()
                for root, dirs, names in os.walk(self.folder_lib_path) for name in names}

    def install(self, rows):
        self.dialog.current_lib_data["Custom Profile"]["sizes"] = copy.deepcopy(rows)
        self._select_family("Custom Profile")
        self.dialog.btn_save.click()

    def props(self, path):
        return {"Height": "40", "Width": "80", "Weight": "25.12",
                "asset_path": path, "object_name": "Section", "asset_id": "original"}

    def test_s9_capture_discard_restores_files(self):
        before = self.snapshot()
        doc = self._new_doc("Source")
        sketch = self._create_rect_sketch(doc)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)
        self.dialog.btn_capture_section.click()
        self.dialog._dxf_review.btn_add.click()
        # The generic question mock is not an intentional Discard response.
        self._close_manager_dialog(self.dialog)
        self.assertTrue(self.dialog._is_closed)
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(before, self.snapshot())

    def test_s2_s8_removed_edit_target_cannot_replace_sibling(self):
        a = self._create_published_asset("a", 80, 40)
        b = self._create_published_asset("b", 30, 20)
        self.install({"A": self.props(a), "B": self.props(b)})
        self.dialog.table_sizes.selectRow(0)
        self.dialog.btn_edit_section.click()
        self._confirm_delete_size()
        self.dialog.table_sizes.selectRow(0)
        self.dialog._commit_current_family_edits()
        before = copy.deepcopy(self.dialog.current_lib_data)
        self.dialog.btn_apply_edit.click()
        self.dialog._commit_current_family_edits()
        self.assertEqual(before, self.dialog.current_lib_data)

    def test_s9_canonical_shared_reference_survives(self):
        path = self._create_published_asset("shared")
        full = os.path.join(self.folder_lib_path, path)
        os.symlink("shared.FCStd", os.path.join(self.folder_lib_path, "sections", "alias.FCStd"))
        self.install({"A": self.props(path), "B": self.props("sections/alias.FCStd")})
        before = open(full, "rb").read()
        self.dialog.table_sizes.selectRow(0)
        self._confirm_delete_size()
        self.dialog.btn_save.click()
        self.assertTrue(os.path.isfile(full))
        self.assertEqual(before, open(full, "rb").read())

    def test_s9_failed_delete_save_preserves_manifest(self):
        self.install({"Bad": self.props("../outside.FCStd")})
        before = self.snapshot()
        self.dialog.table_sizes.selectRow(0)
        self._confirm_delete_size()
        self.dialog.btn_save.click()
        self.assertEqual(before, self.snapshot())


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for method_name in [
        "test_s9_capture_discard_restores_files",
        "test_s2_s8_removed_edit_target_cannot_replace_sibling",
        "test_s9_canonical_shared_reference_survives",
        "test_s9_failed_delete_save_preserves_manifest",
    ]:
        suite.addTest(IndependentT4(method_name))
    return suite

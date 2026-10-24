import ast
import gc
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from freecad.maxproframe.library_manager import LibraryManager


class TestLibraryManagerDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set offscreen platform for headless Qt execution
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide import QtCore

        cls._orig_default_locale = QtCore.QLocale()

    @classmethod
    def tearDownClass(cls):
        from PySide import QtCore, QtWidgets

        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance()
        tr = getattr(ProfileLibraryManagerDialog, "_translator", None)
        if tr is not None and app is not None:
            app.removeTranslator(tr)
        ProfileLibraryManagerDialog._translator = None
        ProfileLibraryManagerDialog._translator_installed = False
        if hasattr(cls, "_orig_default_locale"):
            QtCore.QLocale.setDefault(cls._orig_default_locale)

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_dialog_user_")
        self.addCleanup(shutil.rmtree, self.test_user_dir)
        self.manager = LibraryManager(user_dir=self.test_user_dir)
        self.addCleanup(self._reset_translations)
        self.owned_dialogs = []
        self.addCleanup(self._close_owned_managers)

    def _own_manager(self, dialog):
        self.owned_dialogs.append(dialog)
        return dialog

    def _close_owned_managers(self):
        from freecad.maxproframe.library_manager_dialog import QtWidgets

        for dialog in reversed(self.owned_dialogs):

            def discard_owned_changes(parent, *args, **kwargs):
                self.assertIs(parent, dialog)
                return QtWidgets.QMessageBox.Discard

            with patch.object(QtWidgets.QMessageBox, "question", side_effect=discard_owned_changes):
                self.assertTrue(dialog.close())

    def _reset_translations(self):
        from PySide import QtWidgets

        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance()
        tr = getattr(ProfileLibraryManagerDialog, "_translator", None)
        if tr is not None and app is not None:
            app.removeTranslator(tr)
        ProfileLibraryManagerDialog._translator = None
        ProfileLibraryManagerDialog._translator_installed = False

    def test_dynamic_family_columns_and_hidden_value_preservation(self):
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog, QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        families = {
            "Round Bar": {0, 1, 7},
            "Pipe": {0, 1, 3, 7},
            "Flat Sections": {0, 1, 2, 7},
            "Square": {0, 1, 2, 7},
            "Square Hollow": {0, 1, 2, 3, 5, 6, 7},
            "Rectangular Hollow": {0, 1, 2, 3, 5, 6, 7},
            "Equal Leg Angles": {0, 1, 2, 3, 5, 6, 7},
            "Unequal Leg Angles": {0, 1, 2, 3, 5, 6, 7},
            "IPE": {0, 1, 2, 3, 4, 5, 7},
            "UPE": set(range(8)),
            "T-Slot": {0, 1, 2, 7},
            "Unknown": set(range(8)),
        }
        self.manager.save_user_library(
            "Dynamic",
            {
                "_metadata": {"name": "Dynamic"},
                **{
                    name: {
                        "norm": "Test",
                        "fillet": True,
                        "sizes": {
                            "S1": {"Height": "20", "Width": "20", "Thickness": "2", "Radius1": "4", "Radius2": "2"}
                        },
                    }
                    for name in families
                },
            },
        )
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="Dynamic")
        for name, expected in families.items():
            with self.subTest(family=name):
                dialog.combo_family.setCurrentText(name)
                visible = {i for i in range(8) if not dialog.table_sizes.isColumnHidden(i)}
                self.assertEqual(visible, expected)
        dialog.combo_family.setCurrentText("Square Hollow")
        self.assertFalse(hasattr(dialog, "cb_fillet"))
        self.assertFalse(dialog.table_sizes.isColumnHidden(5))
        self.assertFalse(dialog.table_sizes.isColumnHidden(6))
        dialog.table_sizes.item(0, 0).setText("Renamed")
        dialog.table_sizes.item(0, 1).setText("30")
        dialog.btn_save.click()
        saved = self.manager.get_library("Dynamic")["Square Hollow"]["sizes"]["Renamed"]
        self.assertEqual(saved["Radius1"], "4")
        self.assertEqual(saved["Radius2"], "2")
        self.assertEqual(saved["Height"], "30")
        self.assertTrue(self.manager.get_library("Dynamic")["Square Hollow"]["fillet"])
        self.assertFalse(dialog.table_sizes.isColumnHidden(5))
        self.assertEqual(dialog.table_sizes.item(0, 5).text(), "4")
        dialog.combo_family.setCurrentText("Pipe")
        from freecad.maxproframe.ff_tools import translate

        self.assertEqual(dialog.table_sizes.horizontalHeaderItem(1).text(), translate("frameforge", "Diameter [mm]"))
        dialog.combo_family.setCurrentText("Square")
        self.assertEqual(dialog.table_sizes.horizontalHeaderItem(1).text(), translate("frameforge", "Height [mm]"))

    def test_master_detail_families_list_and_icons(self):
        from freecad.maxproframe.ff_tools import PROFILEIMAGES_PATH, translate
        from freecad.maxproframe.library_manager_dialog import (
            ProfileLibraryManagerDialog,
            QtCore,
            QtGui,
            QtWidgets,
        )

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        data = {"_metadata": {"name": "MasterDetail"}}
        for key, code, fillet in [("Square Hollow", "S1", True), ("Pipe", "P1", False), ("Custom Family", "C1", False)]:
            data[key] = {
                "norm": key + " standard",
                "fillet": fillet,
                "sizes": {code: {"Height": "20", "Width": "20", "Thickness": "2"}},
            }
        self.manager.save_user_library("MasterDetail", data)
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="MasterDetail")
        families = dialog.list_families
        self.assertEqual(families.count(), 3)
        self.assertGreaterEqual(families.iconSize().width(), 50)
        self.assertEqual(families.iconSize(), QtCore.QSize(60, 30))
        self.assertEqual(dialog.left_splitter.orientation(), QtCore.Qt.Vertical)
        self.assertEqual(dialog.left_splitter.handleWidth(), 6)
        self.assertEqual(dialog.left_splitter.count(), 2)
        self.assertEqual(dialog.left_splitter.widget(0), dialog.list_libraries.parentWidget())
        self.assertEqual(dialog.left_splitter.widget(1), families.parentWidget())
        self.assertTrue(dialog.combo_family.isHidden())
        for row in range(families.count()):
            item = families.item(row)
            key = item.data(QtCore.Qt.UserRole)
            self.assertEqual(item.text(), translate("frameforge", key))
            self.assertFalse(item.icon().isNull())
            image = os.path.join(PROFILEIMAGES_PATH, "Metal", key.replace(" ", "_") + ".png")
            if not os.path.isfile(image):
                image = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            self.assertEqual(item.icon().pixmap(60, 30).toImage(), QtGui.QIcon(image).pixmap(60, 30).toImage())
            families.setCurrentItem(item)
            self.assertEqual(dialog.combo_family.currentText(), key)
            self.assertEqual(dialog.table_sizes.rowCount(), 1)
            self.assertEqual(dialog.table_sizes.item(0, 0).text(), next(iter(data[key]["sizes"])))
            self.assertEqual(dialog.le_norm.text(), data[key]["norm"])
            dialog._commit_current_family_edits()
            self.assertEqual(dialog.current_lib_data[key]["fillet"], data[key]["fillet"])
            self.assertIsNotNone(dialog.lbl_family_icon.pixmap())
            self.assertFalse(dialog.lbl_family_icon.pixmap().isNull())
        self.assertEqual(dialog.lbl_family_icon.size(), QtCore.QSize(120, 60))
        for button, tooltip in [
            (dialog.btn_new_lib, "New Library"),
            (dialog.btn_dup_lib, "Duplicate Library"),
            (dialog.btn_del_lib, "Delete Library"),
            (dialog.btn_add_family, "Add Family"),
            (dialog.btn_del_family, "Delete Family"),
            (dialog.btn_add_size, "Add Size"),
            (dialog.btn_del_size, "Remove Size"),
        ]:
            self.assertEqual(button.size(), QtCore.QSize(26, 26))
            self.assertEqual(button.minimumSize(), button.maximumSize())
            self.assertEqual(button.text(), "")
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.toolTip(), translate("frameforge", tooltip))
            expected_parent = (
                dialog.list_libraries.parentWidget()
                if button in (dialog.btn_new_lib, dialog.btn_dup_lib, dialog.btn_del_lib)
                else (
                    families.parentWidget()
                    if button in (dialog.btn_add_family, dialog.btn_del_family)
                    else dialog.table_sizes.parentWidget()
                )
            )
            self.assertEqual(button.parentWidget(), expected_parent)
        dialog.combo_family.setCurrentText("Pipe")
        self.assertEqual(families.currentItem().data(QtCore.Qt.UserRole), "Pipe")
        self.assertFalse(dialog.lbl_family_icon.pixmap().isNull())

    def test_family_toolbar_crud_and_edit_preservation(self):
        from unittest.mock import patch

        from freecad.maxproframe.library_manager_dialog import (
            ProfileLibraryManagerDialog,
            QtCore,
            QtWidgets,
        )

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        self.manager.save_user_library(
            "FamilyToolbar",
            {
                "_metadata": {"name": "FamilyToolbar"},
                "Square Hollow": {"norm": "Original", "fillet": False, "sizes": {"S1": {"Height": "20"}}},
            },
        )
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="FamilyToolbar")
        dialog.le_norm.setText("Edited")
        dialog.table_sizes.item(0, 1).setText("99")
        with patch("freecad.maxproframe.library_manager_dialog.AddFamilyDialog") as mock_dlg_cls:
            mock_dlg = mock_dlg_cls.return_value
            mock_dlg.exec_.return_value = QtWidgets.QDialog.Accepted
            mock_dlg.get_values.return_value = ("Pipe", False)
            dialog.btn_add_family.click()
        self.assertEqual(dialog.list_families.count(), 2)
        self.assertEqual(dialog.list_families.currentItem().data(QtCore.Qt.UserRole), "Pipe")
        self.assertEqual(dialog.table_sizes.rowCount(), 0)
        dialog.btn_save.click()
        saved = self.manager.get_library("FamilyToolbar")
        self.assertEqual(saved["Square Hollow"]["norm"], "Edited")
        self.assertEqual(saved["Square Hollow"]["sizes"]["S1"]["Height"], "99")
        self.assertIn("Pipe", saved)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No):
            dialog.btn_del_family.click()
        self.assertEqual(dialog.list_families.count(), 2)
        self.assertFalse(dialog.is_dirty)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
            dialog.btn_del_family.click()
            self.assertEqual(dialog.list_families.count(), 1)
            self.assertEqual(dialog.combo_family.currentText(), "Square Hollow")
            dialog.btn_del_family.click()
        self.assertEqual(dialog.list_families.count(), 0)
        self.assertEqual(dialog.combo_family.currentText(), "")
        self.assertEqual(dialog.table_sizes.rowCount(), 0)
        self.assertFalse(dialog.btn_del_family.isEnabled())
        self.assertFalse(dialog.btn_add_size.isEnabled())
        self.assertFalse(dialog.btn_del_size.isEnabled())
        self.assertTrue(dialog.lbl_family_icon.pixmap().isNull() if dialog.lbl_family_icon.pixmap() else True)
        dialog.btn_save.click()
        self.assertEqual(set(self.manager.get_library("FamilyToolbar")), {"_metadata"})

    def test_dialog_lifecycle_and_crud(self):
        try:
            from PySide import QtWidgets
        except ImportError:
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))

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
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

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
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
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

    def test_family_switch_with_duplicate_code_validation_failure_preserves_edits(self):
        from unittest.mock import patch

        from PySide import QtCore, QtWidgets

        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        self.manager.save_user_library(
            "DupCheckLib",
            {
                "_metadata": {"name": "DupCheckLib"},
                "FamilyA": {
                    "norm": "NormA",
                    "fillet": False,
                    "sizes": {"A1": {"Height": "50"}, "A2": {"Height": "60"}},
                },
                "FamilyB": {"norm": "NormB", "fillet": False, "sizes": {"B1": {"Height": "70"}}},
            },
        )

        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="DupCheckLib")

        # Select FamilyA and edit size A2 to be A1 (duplicate code!) and modify height
        dialog.combo_family.setCurrentText("FamilyA")
        dialog.table_sizes.item(1, 0).setText("A1")
        dialog.table_sizes.item(0, 1).setText("999")

        # Attempt to switch to FamilyB: should fail validation and abort switch
        with patch.object(QtWidgets.QMessageBox, "warning") as mock_warn:
            item_b = [
                dialog.list_families.item(i)
                for i in range(dialog.list_families.count())
                if dialog.list_families.item(i).data(QtCore.Qt.UserRole) == "FamilyB"
            ][0]
            dialog.list_families.setCurrentItem(item_b)
            mock_warn.assert_called_once()

        # Selection must still be FamilyA and edits must remain in table
        self.assertEqual(dialog.combo_family.currentText(), "FamilyA")
        self.assertEqual(dialog.table_sizes.item(0, 1).text(), "999")
        self.assertEqual(dialog.table_sizes.item(1, 0).text(), "A1")

    def test_library_switch_dirty_guard_save_and_cancel(self):
        from unittest.mock import patch

        from PySide import QtCore, QtWidgets

        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        self.manager.save_user_library(
            "LibOne",
            {
                "_metadata": {"name": "LibOne"},
                "FamOne": {"norm": "Original", "fillet": False, "sizes": {"S1": {"Height": "10"}}},
            },
        )
        self.manager.save_user_library(
            "LibTwo",
            {
                "_metadata": {"name": "LibTwo"},
                "FamTwo": {"norm": "Original", "fillet": False, "sizes": {"S2": {"Height": "20"}}},
            },
        )

        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="LibOne")

        # Edit LibOne
        dialog.le_norm.setText("ChangedNorm")
        dialog.table_sizes.item(0, 1).setText("88")
        self.assertTrue(dialog.is_dirty)

        # 1. Test Cancel: should abort switch and keep LibOne selected and dirty
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Cancel):
            item_two = [
                dialog.list_libraries.item(i)
                for i in range(dialog.list_libraries.count())
                if dialog.list_libraries.item(i).data(QtCore.Qt.UserRole)["name"] == "LibTwo"
            ][0]
            dialog.list_libraries.setCurrentItem(item_two)

        self.assertEqual(dialog.current_lib_meta["name"], "LibOne")
        self.assertEqual(dialog.le_norm.text(), "ChangedNorm")
        self.assertTrue(dialog.is_dirty)

        # 2. Test Save: should save LibOne then switch to LibTwo
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Save):
            dialog.list_libraries.setCurrentItem(item_two)

        self.assertEqual(dialog.current_lib_meta["name"], "LibTwo")
        # Verify LibOne changes were persisted
        saved_one = self.manager.get_library("LibOne")
        self.assertEqual(saved_one["FamOne"]["norm"], "ChangedNorm")
        self.assertEqual(saved_one["FamOne"]["sizes"]["S1"]["Height"], "88")

    def test_auto_calculate_linear_weight_on_dimension_edits_and_manual_override(self):
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog, QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        alu_data = {
            "_metadata": {"name": "AutoAlu", "material": "Aluminium", "density": 2.70},
            "Square Hollow": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Weight": "1.037",
                    }
                },
            },
        }
        self.manager.save_user_library("AutoAlu", alu_data)
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="AutoAlu")

        # Verify banner displays material and density
        from freecad.maxproframe.ff_tools import translate

        self.assertIn(translate("frameforge", "Aluminium"), dialog.lbl_lib_banner.text())
        self.assertIn("2.7", dialog.lbl_lib_banner.toolTip())

        # Change Height (col 1) from 50 to 100
        dialog.table_sizes.item(0, 1).setText("100")
        new_w = float(dialog.table_sizes.item(0, 7).text())
        self.assertAlmostEqual(new_w, 1.577, places=2)

        # Test manual override: user explicitly types a custom weight
        dialog.table_sizes.item(0, 7).setText("1.999")
        self.assertEqual(dialog.table_sizes.item(0, 7).text(), "1.999")

        # Test adding a size automatically computes initial weight with library density
        initial_count = dialog.table_sizes.rowCount()
        dialog._on_add_size()
        self.assertEqual(dialog.table_sizes.rowCount(), initial_count + 1)
        added_w = float(dialog.table_sizes.item(initial_count, 7).text())
        self.assertAlmostEqual(added_w, 1.037, places=2)

    def test_dialog_wood_density_calculation(self):
        try:
            from PySide import QtWidgets
        except ImportError:
            try:
                from PySide6 import QtWidgets
            except ImportError:
                from PySide2 import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        from freecad.maxproframe.library_manager import STANDARD_DENSITIES, calculate_linear_weight
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

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
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
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
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

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
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="UniqueSizesLib")

        # Add two sizes
        dialog._on_add_size()
        dialog._on_add_size()

        self.assertEqual(dialog.table_sizes.rowCount(), 2)
        code1 = dialog.table_sizes.item(0, 0).text()
        code2 = dialog.table_sizes.item(1, 0).text()

        # Codes must be distinct
        self.assertNotEqual(code1, code2)
        self.assertEqual(code1, "New_50x50x2")
        self.assertEqual(code2, "New_50x50x2_1")

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

    def test_delete_only_family_disables_size_actions_and_guards_orphan_sizes(self):
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog, QtWidgets

        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        test_data = {
            "_metadata": {"name": "OrphanGuardLib"},
            "SoloFamily": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {"Size_1": {"Height": "50", "Width": "50", "Thickness": "2"}},
            },
        }
        self.manager.save_user_library("OrphanGuardLib", test_data)
        dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
        dialog.refresh_libraries(select_name="OrphanGuardLib")

        self.assertTrue(dialog.btn_add_size.isEnabled())
        del dialog.current_lib_data["SoloFamily"]
        dialog._populate_families()

        self.assertFalse(dialog.btn_del_family.isEnabled())
        self.assertFalse(dialog.btn_add_size.isEnabled())
        self.assertFalse(dialog.btn_del_size.isEnabled())
        self.assertTrue(dialog.lbl_family_icon.pixmap().isNull() if dialog.lbl_family_icon.pixmap() else True)
        self.assertEqual(dialog.table_sizes.rowCount(), 0)

        dialog._on_add_size()
        self.assertEqual(dialog.table_sizes.rowCount(), 0)

        dialog._on_save_library()
        reloaded = self.manager.get_library("OrphanGuardLib")
        self.assertNotIn("SoloFamily", reloaded)

    def test_warning_uses_english_source(self):
        from freecad.maxproframe import library_manager_dialog

        with open(library_manager_dialog.__file__, encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read())
        strings = [
            node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        self.assertNotIn("Aviso", strings)
        self.assertIn("Warning", strings)

    def test_spanish_locale_translation_survives(self):
        from freecad.maxproframe.library_manager_dialog import (
            ProfileLibraryManagerDialog,
            QtCore,
            QtWidgets,
        )

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        cls = ProfileLibraryManagerDialog
        original_locale = QtCore.QLocale()
        import FreeCAD as App
        import FreeCADGui as Gui

        prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        original_language = prefs.GetString("Language", "")
        original_gui_locale = Gui.getLocale()
        dialog = None
        fresh_dialog = None
        english_dialog = None
        try:
            # FreeCAD selection wins even when the system/default locale differs.
            QtCore.QLocale.setDefault(QtCore.QLocale("en_US"))
            prefs.SetString("Language", "Spanish")
            Gui.setLocale("Spanish")
            Gui.updateLocale()
            dialog = self._own_manager(cls(library_manager=self.manager))
            gc.collect()
            self.assertEqual(dialog.btn_new_lib.toolTip(), "Nueva Biblioteca")
            self.assertEqual(dialog.windowTitle(), "MaxProFrame")
            # A second dialog proves translation still works after the loader returns
            # and garbage collection, rather than merely retaining existing labels.
            fresh_dialog = self._own_manager(cls(library_manager=self.manager))
            self.assertEqual(fresh_dialog.btn_new_lib.toolTip(), "Nueva Biblioteca")
            self.assertEqual(fresh_dialog.windowTitle(), "MaxProFrame")

            # Legacy cleanup must not uninstall FreeCAD's shared translator.
            cls.uninstall_translations()
            dialog.close()
            fresh_dialog.close()
            fresh_dialog = self._own_manager(cls(library_manager=self.manager))
            gc.collect()
            self.assertEqual(fresh_dialog.btn_new_lib.toolTip(), "Nueva Biblioteca")
            self.assertEqual(fresh_dialog.windowTitle(), "MaxProFrame")

            # English selection wins even on a Spanish system/default locale.
            QtCore.QLocale.setDefault(QtCore.QLocale("es_ES"))
            prefs.SetString("Language", "English")
            Gui.setLocale("English")
            Gui.updateLocale()
            english_dialog = self._own_manager(cls(library_manager=self.manager))
            self.assertEqual(english_dialog.btn_new_lib.toolTip(), "New Library")
            self.assertEqual(english_dialog.windowTitle(), "MaxProFrame")
        finally:
            if english_dialog is not None:
                english_dialog.close()
            if fresh_dialog is not None:
                fresh_dialog.close()
            if dialog is not None:
                dialog.close()
            QtCore.QLocale.setDefault(original_locale)
            Gui.setLocale(original_gui_locale)
            prefs.SetString("Language", original_language)
            Gui.updateLocale()

    def test_translations_and_indumatics_removal(self):
        from PySide import QtCore, QtWidgets

        from freecad.maxproframe.ff_tools import TRANSLATIONSPATH
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # 1. Verify Spanish translation loads and translates core UI elements
        translator = QtCore.QTranslator()
        qm_path = os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")
        self.assertTrue(os.path.isfile(qm_path), f"QM file not found at {qm_path}")
        loaded = translator.load(qm_path)
        self.assertTrue(loaded, "Failed to load frameforge_es.qm")

        app.installTranslator(translator)
        try:
            dialog = self._own_manager(ProfileLibraryManagerDialog(library_manager=self.manager))
            # Under Spanish translator:
            self.assertEqual(dialog.windowTitle(), "MaxProFrame")
            self.assertEqual(dialog.btn_new_lib.toolTip(), "Nueva Biblioteca")
            self.assertEqual(dialog.btn_dup_lib.toolTip(), "Duplicar Biblioteca")
            self.assertEqual(dialog.btn_del_lib.toolTip(), "Eliminar Biblioteca")
            self.assertEqual(dialog.btn_save.text(), "Guardar Cambios")
            expected_families = {
                "Square Hollow": "Tubo Cuadrado Hueco",
                "Rectangular Hollow": "Tubo Rectangular Hueco",
                "Pipe": "Tubo Redondo (Caño)",
                "Equal Leg Angles": "Ángulo de Alas Iguales",
                "Unequal Leg Angles": "Ángulo de Alas Desiguales",
                "Flat Sections": "Planchuelas / Pletinas",
                "Round Bar": "Barra Redonda Maciza",
                "Square": "Barra Cuadrada Maciza",
                "Channels": "Canales",
                "T-Slot": "Perfil con ranura en T",
                "T-Slot 3-Slots": "Perfil con ranura en T de 3 ranuras",
                "T-Slot 2-Slots": "Perfil con ranura en T de 2 ranuras",
                "T-Slot 2-Slots Opp": "Perfil con ranura en T de 2 ranuras opuestas",
                "T-Slot 1-Slot": "Perfil con ranura en T de 1 ranura",
                "V-Slot": "Perfil con ranura en V",
                "Custom Profile": "Perfil personalizado",
                **{key: key for key in ("HEA", "HEB", "HEM", "IPE", "IPN", "UPE", "UPN")},
            }
            for source, expected in expected_families.items():
                self.assertEqual(translator.translate("frameforge", source), expected)
            self.assertEqual(translator.translate("frameforge", "Library Families"), "Familias en la biblioteca")
            self.assertIn(
                "<b>Familias en la biblioteca:</b>", [label.text() for label in dialog.findChildren(QtWidgets.QLabel)]
            )
            self.assertEqual(dialog.btn_add_family.toolTip(), "Agregar Familia")
            self.assertEqual(dialog.btn_del_family.toolTip(), "Eliminar Familia")
            for row in range(dialog.list_families.count()):
                item = dialog.list_families.item(row)
                key = item.data(QtCore.Qt.UserRole)
                self.assertEqual(item.text(), expected_families.get(key, key))

            # Verify 'Indumatics' is nowhere in the dialog texts
            # and replaced with 'Tubos Aluminio'
            self.assertNotIn("Indumatics", dialog.findChildren(QtWidgets.QLabel)[0].text())
            self.assertIn("Tubos Aluminio", dialog.findChildren(QtWidgets.QLabel)[0].text())
        finally:
            app.removeTranslator(translator)


if __name__ == "__main__":
    unittest.main()

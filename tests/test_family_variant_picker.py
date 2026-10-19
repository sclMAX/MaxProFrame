import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.ff_tools import PROFILEIMAGES_PATH, TRANSLATIONSPATH, translate
from freecad.maxproframe.library_manager import KNOWN_FAMILIES, LibraryManager

try:
    from freecad.maxproframe.library_manager import FILLET_FAMILIES, get_canonical_family
except ImportError:
    FILLET_FAMILIES = frozenset(
        [
            "Square Hollow",
            "Rectangular Hollow",
            "Equal Leg Angles",
            "Unequal Leg Angles",
            "HEA",
            "HEB",
            "HEM",
            "IPE",
            "IPN",
            "UPE",
            "UPN",
        ]
    )

    def get_canonical_family(family_key, family_data=None):
        if family_data and isinstance(family_data, dict) and "canonical_family" in family_data:
            return family_data["canonical_family"]
        return family_key


class TestFamilyVariantPicker(unittest.TestCase):
    """
    Focused unit tests for T2 (S1, S2, S3, S4):
    AddFamilyDialog, variant naming and persistence, canonical resolution,
    informational checkbox, and duplicate prevention.
    """

    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_picker_user_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)

    def tearDown(self):
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def test_add_family_offers_all_stock_metal_families(self):
        """Every stock Metal family is selectable, without losing existing choices."""
        from freecad.maxproframe.library_manager_dialog import AddFamilyDialog

        dialog = AddFamilyDialog()
        self.addCleanup(dialog.close)
        stock_families = {key for key in self.manager.get_library("Metal") if not key.startswith("_")}
        previous_choices = {
            "Square Hollow",
            "Rectangular Hollow",
            "Pipe",
            "Equal Leg Angles",
            "Unequal Leg Angles",
            "Channels",
            "Square",
            "Round Bar",
            "Flat Sections",
            "T-Slot",
            "V-Slot",
            "Custom Profile",
        }
        offered = [
            dialog.list_families.item(row).data(QtCore.Qt.UserRole) for row in range(dialog.list_families.count())
        ]
        self.assertEqual(len(offered), len(set(offered)))
        self.assertTrue(previous_choices.issubset(offered))
        self.assertTrue(
            stock_families.issubset(offered), f"Missing Metal families: {sorted(stock_families - set(offered))}"
        )
        for family in sorted(stock_families):
            with self.subTest(family=family):
                dialog.select_family(family)
                self.assertEqual(dialog.get_values(), (family, False))
                item = dialog.list_families.currentItem()
                self.assertEqual(item.text(), translate("frameforge", family))
                self.assertFalse(item.icon().isNull())
                self.assertFalse(dialog.lbl_preview.pixmap().isNull())
                self.assertEqual(dialog.cb_fillet.isEnabled(), family in FILLET_FAMILIES)
                if family in FILLET_FAMILIES:
                    dialog.cb_fillet.setChecked(True)
                    self.assertEqual(dialog.get_values(), (family, True))
                    dialog.cb_fillet.setChecked(False)

    def test_s3_add_family_dialog_translated_names_and_icons(self):
        """S3: AddFamilyDialog displays translated family names and valid icons for all known families."""
        from freecad.maxproframe.library_manager_dialog import AddFamilyDialog

        dialog = AddFamilyDialog()
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.windowTitle(), translate("frameforge", "Add Family"))
        self.assertEqual(dialog.list_families.count(), len(KNOWN_FAMILIES))

        for row in range(dialog.list_families.count()):
            item = dialog.list_families.item(row)
            fam_key = item.data(QtCore.Qt.UserRole)
            self.assertIn(fam_key, KNOWN_FAMILIES)
            self.assertEqual(item.text(), translate("frameforge", fam_key))
            self.assertFalse(item.icon().isNull(), f"Icon missing for {fam_key}")

        # Verify Spanish translations in dialog
        translator = QtCore.QTranslator()
        qm_path = os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")
        if os.path.isfile(qm_path) and translator.load(qm_path):
            self.app.installTranslator(translator)
            try:
                es_dialog = AddFamilyDialog()
                self.addCleanup(es_dialog.close)
                found_spanish = False
                for r in range(es_dialog.list_families.count()):
                    it = es_dialog.list_families.item(r)
                    if it.data(QtCore.Qt.UserRole) == "Square Hollow":
                        self.assertEqual(it.text(), "Tubo Cuadrado Hueco")
                        found_spanish = True
                self.assertTrue(found_spanish)
            finally:
                self.app.removeTranslator(translator)

    def test_s3_add_family_dialog_toggle_enabled_only_for_fillet_families(self):
        """S3: With Fillet choice is enabled only for families in FILLET_FAMILIES."""
        from freecad.maxproframe.library_manager_dialog import AddFamilyDialog

        dialog = AddFamilyDialog()
        self.addCleanup(dialog.close)

        for fam in ("Square Hollow", "Rectangular Hollow", "Equal Leg Angles", "HEA", "IPE"):
            dialog.select_family(fam)
            self.assertTrue(
                dialog.cb_fillet.isEnabled(),
                f"cb_fillet should be enabled for {fam}",
            )

        for fam in ("Round Bar", "Pipe", "Flat Sections", "Square", "Channels"):
            dialog.select_family(fam)
            self.assertFalse(
                dialog.cb_fillet.isEnabled(),
                f"cb_fillet should be disabled for {fam}",
            )
            self.assertFalse(dialog.cb_fillet.isChecked())

    def test_s3_add_family_dialog_preview_follows_toggle(self):
        """S3: Family preview image follows the fillet toggle."""
        from freecad.maxproframe.library_manager_dialog import AddFamilyDialog

        dialog = AddFamilyDialog()
        self.addCleanup(dialog.close)

        dialog.select_family("Square Hollow")
        dialog.cb_fillet.setChecked(False)
        self.assertFalse(dialog.lbl_preview.pixmap().isNull())
        plain_img = dialog.lbl_preview.pixmap().toImage()

        dialog.cb_fillet.setChecked(True)
        self.assertFalse(dialog.lbl_preview.pixmap().isNull())
        fillet_img = dialog.lbl_preview.pixmap().toImage()

        # Filleted image pixmap differs from plain image pixmap
        self.assertNotEqual(plain_img, fillet_img)

        # Unchecking returns to plain image
        dialog.cb_fillet.setChecked(False)
        self.assertEqual(dialog.lbl_preview.pixmap().toImage(), plain_img)

    def test_s3_add_family_dialog_cancel_no_changes(self):
        """S3: Canceling AddFamilyDialog leaves library data and dirty state unchanged."""
        from freecad.maxproframe.library_manager_dialog import (
            AddFamilyDialog,
            ProfileLibraryManagerDialog,
        )

        self.manager.save_user_library(
            "CancelLib",
            {
                "_metadata": {"name": "CancelLib"},
                "Pipe": {"norm": "Standard", "fillet": False, "sizes": {}},
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="CancelLib")

        with patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Rejected):
            dialog.btn_add_family.click()

        self.assertEqual(dialog.list_families.count(), 1)
        self.assertNotIn("Square Hollow", dialog.current_lib_data)
        self.assertFalse(dialog.is_dirty)

    def test_s3_add_family_duplicate_rejection_with_warning(self):
        """S3: Reject duplicate canonical+fillet with explicit warning and no dirty/data changes."""
        from freecad.maxproframe.library_manager_dialog import (
            AddFamilyDialog,
            ProfileLibraryManagerDialog,
        )

        # Prepopulate with a plain variant and a legacy filleted entry
        self.manager.save_user_library(
            "DupLib",
            {
                "_metadata": {"name": "DupLib"},
                "Square Hollow": {
                    "canonical_family": "Square Hollow",
                    "norm": "Custom",
                    "fillet": False,
                    "sizes": {},
                },
                "Equal Leg Angles": {
                    "norm": "Legacy Angles",
                    "fillet": True,
                    "sizes": {},
                },
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="DupLib")
        initial_keys = set(dialog.current_lib_data.keys())

        # Attempt 1: Duplicate of plain Square Hollow
        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Square Hollow", False)),
            patch.object(QtWidgets.QMessageBox, "warning") as mock_warn,
        ):
            dialog.btn_add_family.click()
            mock_warn.assert_called_once()

        self.assertEqual(set(dialog.current_lib_data.keys()), initial_keys)
        self.assertFalse(dialog.is_dirty)

        # Attempt 2: Duplicate of legacy filleted Equal Leg Angles
        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Equal Leg Angles", True)),
            patch.object(QtWidgets.QMessageBox, "warning") as mock_warn,
        ):
            dialog.btn_add_family.click()
            mock_warn.assert_called_once()

        self.assertEqual(set(dialog.current_lib_data.keys()), initial_keys)
        self.assertFalse(dialog.is_dirty)

    def test_s1_both_variants_coexist_with_same_size_code(self):
        """S1: Plain and filleted variants coexist in the same library with independent size tables."""
        from freecad.maxproframe.library_manager_dialog import (
            AddFamilyDialog,
            ProfileLibraryManagerDialog,
        )

        self.manager.save_user_library(
            "CoexistLib",
            {
                "_metadata": {"name": "CoexistLib"},
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="CoexistLib")

        # Add plain Square Hollow
        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Square Hollow", False)),
        ):
            dialog.btn_add_family.click()

        self.assertIn("Square Hollow", dialog.current_lib_data)
        # Add a size to plain variant
        dialog._on_add_size()
        dialog.table_sizes.item(0, 0).setText("50x50x2")
        dialog.table_sizes.item(0, 1).setText("50")
        dialog.table_sizes.item(0, 2).setText("50")
        dialog.table_sizes.item(0, 3).setText("2")

        # Add filleted Square Hollow
        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Square Hollow", True)),
        ):
            dialog.btn_add_family.click()

        self.assertIn("Square Hollow (Fillet)", dialog.current_lib_data)
        # Add the same size code to filleted variant with different corner radii
        dialog._on_add_size()
        dialog.table_sizes.item(0, 0).setText("50x50x2")
        dialog.table_sizes.item(0, 1).setText("50")
        dialog.table_sizes.item(0, 2).setText("50")
        dialog.table_sizes.item(0, 3).setText("2")
        dialog.table_sizes.item(0, 5).setText("4")  # Radius1
        dialog.table_sizes.item(0, 6).setText("2")  # Radius2

        # Save library
        dialog._on_save_library()

        # Reload from disk and verify independent persistence
        saved = self.manager.get_library("CoexistLib")
        self.assertIn("Square Hollow", saved)
        self.assertIn("Square Hollow (Fillet)", saved)

        plain_entry = saved["Square Hollow"]
        fillet_entry = saved["Square Hollow (Fillet)"]

        self.assertFalse(plain_entry["fillet"])
        self.assertTrue(fillet_entry["fillet"])
        self.assertEqual(plain_entry.get("canonical_family"), "Square Hollow")
        self.assertEqual(fillet_entry.get("canonical_family"), "Square Hollow")

        self.assertIn("50x50x2", plain_entry["sizes"])
        self.assertIn("50x50x2", fillet_entry["sizes"])
        self.assertEqual(fillet_entry["sizes"]["50x50x2"]["Radius1"], "4")
        self.assertEqual(fillet_entry["sizes"]["50x50x2"]["Radius2"], "2")

    def test_s2_occupied_legacy_base_key_assigns_no_fillet_suffix(self):
        """S2: For occupied legacy base key holding filleted variant, use ' (No Fillet)' for new plain entry."""
        from freecad.maxproframe.library_manager_dialog import (
            AddFamilyDialog,
            ProfileLibraryManagerDialog,
        )

        # Legacy catalog where base key "Square Hollow" holds filleted variant
        self.manager.save_user_library(
            "LegacyOccupiedLib",
            {
                "_metadata": {"name": "LegacyOccupiedLib"},
                "Square Hollow": {
                    "norm": "DIN 59410",
                    "fillet": True,
                    "sizes": {"60x60x3": {"Height": "60", "Width": "60", "Thickness": "3"}},
                },
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="LegacyOccupiedLib")

        # Add plain variant for Square Hollow
        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Square Hollow", False)),
        ):
            dialog.btn_add_family.click()

        # Base key must remain unchanged for legacy entry
        self.assertIn("Square Hollow", dialog.current_lib_data)
        self.assertTrue(dialog.current_lib_data["Square Hollow"]["fillet"])

        # New plain entry gets " (No Fillet)" key and canonical_family metadata
        self.assertIn("Square Hollow (No Fillet)", dialog.current_lib_data)
        new_entry = dialog.current_lib_data["Square Hollow (No Fillet)"]
        self.assertFalse(new_entry["fillet"])
        self.assertEqual(new_entry["canonical_family"], "Square Hollow")

    def test_s2_visible_variant_names_and_raw_dictionary_keys(self):
        """S2: Visible variant names derived from canonical type+boolean; raw keys kept in UserRole/combo."""
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        self.manager.save_user_library(
            "DisplayNamesLib",
            {
                "_metadata": {"name": "DisplayNamesLib"},
                "Square Hollow (Fillet)": {
                    "canonical_family": "Square Hollow",
                    "fillet": True,
                    "norm": "Custom",
                    "sizes": {},
                },
                "Square Hollow (No Fillet)": {
                    "canonical_family": "Square Hollow",
                    "fillet": False,
                    "norm": "Custom",
                    "sizes": {},
                },
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="DisplayNamesLib")

        # English check
        raw_keys = [dialog.list_families.item(i).data(QtCore.Qt.UserRole) for i in range(dialog.list_families.count())]
        self.assertIn("Square Hollow (Fillet)", raw_keys)
        self.assertIn("Square Hollow (No Fillet)", raw_keys)

        # Display texts derived from canonical type + boolean
        expected_fillet = f"{translate('frameforge', 'Square Hollow')} ({translate('frameforge', 'Fillet')})"
        expected_no_fillet = f"{translate('frameforge', 'Square Hollow')} ({translate('frameforge', 'No Fillet')})"
        display_texts = [dialog.list_families.item(i).text() for i in range(dialog.list_families.count())]
        self.assertIn(expected_fillet, display_texts)
        self.assertIn(expected_no_fillet, display_texts)

        # Hidden combo retains raw keys
        combo_keys = [dialog.combo_family.itemText(i) for i in range(dialog.combo_family.count())]
        self.assertIn("Square Hollow (Fillet)", combo_keys)
        self.assertIn("Square Hollow (No Fillet)", combo_keys)

        # Explicit Spanish translation check
        translator = QtCore.QTranslator()
        qm_path = os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")
        if os.path.isfile(qm_path) and translator.load(qm_path):
            self.app.installTranslator(translator)
            try:
                es_dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
                self.addCleanup(es_dialog.close)
                es_dialog.refresh_libraries(select_name="DisplayNamesLib")
                es_texts = [es_dialog.list_families.item(i).text() for i in range(es_dialog.list_families.count())]
                self.assertIn("Tubo Cuadrado Hueco (Con redondeos)", es_texts)
                self.assertIn("Tubo Cuadrado Hueco (Sin redondeos)", es_texts)
            finally:
                self.app.removeTranslator(translator)

    def test_s4_variant_dynamic_columns_and_canonical_weight_calculation(self):
        """S4: Dynamic columns and auto-weight calculations resolve canonical type from metadata."""
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        self.manager.save_user_library(
            "VariantCalcLib",
            {
                "_metadata": {"name": "VariantCalcLib", "material": "Steel", "density": 7.85},
                "Square Hollow (Fillet)": {
                    "canonical_family": "Square Hollow",
                    "fillet": True,
                    "norm": "Custom",
                    "sizes": {
                        "50x50x2": {
                            "Height": "50",
                            "Width": "50",
                            "Thickness": "2",
                            "Flange Thickness": "0",
                            "Radius1": "4",
                            "Radius2": "2",
                            "Weight": "0",
                        }
                    },
                },
                "Square Hollow (No Fillet)": {
                    "canonical_family": "Square Hollow",
                    "fillet": False,
                    "norm": "Custom",
                    "sizes": {
                        "50x50x2": {
                            "Height": "50",
                            "Width": "50",
                            "Thickness": "2",
                            "Flange Thickness": "0",
                            "Radius1": "0",
                            "Radius2": "0",
                            "Weight": "0",
                        }
                    },
                },
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="VariantCalcLib")

        # 1. Filleted variant has Radius1 and Radius2 visible
        dialog.combo_family.setCurrentText("Square Hollow (Fillet)")
        self.assertFalse(dialog.table_sizes.isColumnHidden(5))  # Radius1
        self.assertFalse(dialog.table_sizes.isColumnHidden(6))  # Radius2

        # Editing dimensions recalculates weight using canonical type "Square Hollow"
        dialog.table_sizes.item(0, 1).setText("100")
        weight_val = float(dialog.table_sizes.item(0, 7).text())
        # Theoretical weight of 100x50x2 steel hollow = ~4.48 kg/m
        self.assertGreater(weight_val, 4.0)
        self.assertLess(weight_val, 5.0)

        # 2. Plain variant has Radius1 and Radius2 hidden
        dialog.combo_family.setCurrentText("Square Hollow (No Fillet)")
        self.assertTrue(dialog.table_sizes.isColumnHidden(5))
        self.assertTrue(dialog.table_sizes.isColumnHidden(6))

        # Adding size computes weight using canonical type
        dialog._on_add_size()
        new_row = dialog.table_sizes.rowCount() - 1
        new_w = float(dialog.table_sizes.item(new_row, 7).text())
        self.assertAlmostEqual(new_w, 3.014, places=2)

    def test_s4_explicit_variant_checkbox_informational_disabled(self):
        """S4: Family-level checkbox is disabled (informational) for explicit variants, editable for legacy."""
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        self.manager.save_user_library(
            "InfoCheckboxLib",
            {
                "_metadata": {"name": "InfoCheckboxLib"},
                "Square Hollow (Fillet)": {
                    "canonical_family": "Square Hollow",
                    "fillet": True,
                    "norm": "Custom",
                    "sizes": {},
                },
                "Legacy Family": {
                    "norm": "Custom",
                    "fillet": False,
                    "sizes": {},
                },
            },
        )

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="InfoCheckboxLib")

        # Explicit variant: checkbox is disabled and checked
        dialog.combo_family.setCurrentText("Square Hollow (Fillet)")
        self.assertFalse(dialog.cb_fillet.isEnabled())
        self.assertTrue(dialog.cb_fillet.isChecked())

        # Legacy entry: checkbox is enabled and editable
        dialog.combo_family.setCurrentText("Legacy Family")
        self.assertTrue(dialog.cb_fillet.isEnabled())
        self.assertFalse(dialog.cb_fillet.isChecked())

    def test_b1_occupied_legacy_destination_key_collision_rejected_without_overwriting(self):
        """B1: Destination-key collision with legacy entry lacking canonical_family rejects with warning without overwriting sizes."""
        import copy
        import hashlib

        from freecad.maxproframe.library_manager_dialog import (
            AddFamilyDialog,
            ProfileLibraryManagerDialog,
        )

        lib_name = "LegacyCollisionLib"
        initial_data = {
            "_metadata": {"name": lib_name},
            "Square Hollow (Fillet)": {
                "norm": "DIN 59410",
                "fillet": True,
                "sizes": {
                    "70x70x3": {
                        "Height": "70",
                        "Width": "70",
                        "Thickness": "3",
                    }
                },
            },
            "Pipe": {
                "norm": "Standard",
                "fillet": False,
                "sizes": {},
            },
        }
        self.manager.save_user_library(lib_name, initial_data)
        file_path = os.path.join(self.test_user_dir, f"{lib_name.lower()}.json")
        with open(file_path, "rb") as f:
            file_hash_before = hashlib.sha256(f.read()).hexdigest()

        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name=lib_name)

        # Select Pipe
        dialog.combo_family.setCurrentText("Pipe")
        self.assertEqual(dialog.combo_family.currentText(), "Pipe")

        snapshot_data = copy.deepcopy(dialog.current_lib_data)
        snapshot_dirty = dialog.is_dirty
        snapshot_selected = dialog.combo_family.currentText()

        with (
            patch.object(AddFamilyDialog, "exec_", return_value=QtWidgets.QDialog.Accepted),
            patch.object(AddFamilyDialog, "get_values", return_value=("Square Hollow", True)),
            patch.object(QtWidgets.QMessageBox, "warning") as mock_warn,
        ):
            dialog.btn_add_family.click()

            mock_warn.assert_called_once()

        # State, memory, dirty flag, file hash, and selection must remain unchanged
        self.assertEqual(dialog.current_lib_data, snapshot_data)
        self.assertIn("70x70x3", dialog.current_lib_data["Square Hollow (Fillet)"]["sizes"])
        self.assertEqual(
            dialog.current_lib_data["Square Hollow (Fillet)"]["sizes"]["70x70x3"]["Height"],
            "70",
        )
        self.assertEqual(dialog.is_dirty, snapshot_dirty)
        self.assertFalse(dialog.is_dirty)
        self.assertEqual(dialog.combo_family.currentText(), snapshot_selected)

        with open(file_path, "rb") as f:
            file_hash_after = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(file_hash_before, file_hash_after)


if __name__ == "__main__":
    unittest.main()

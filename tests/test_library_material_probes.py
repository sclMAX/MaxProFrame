import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from freecad.maxproframe.library_manager import LibraryManager, STANDARD_DENSITIES


class MaterialProbes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        from freecad.maxproframe.library_manager_dialog import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["probes"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = LibraryManager(user_dir=self.tmp.name)

    def create(self, name="Source", family="Square Hollow"):
        return self.manager.save_user_library(name, {
            "_metadata": {"name": name, "material": "Aluminium", "density": 2.7},
            family: {"sizes": {"A": {
                "Height": "50", "Width": "50", "Thickness": "2",
                "Flange Thickness": "0", "Weight": "9.123",
            }}},
        })

    def digest(self, path):
        with open(path, "rb") as stream:
            return hashlib.sha256(stream.read()).hexdigest()

    def dialog(self, name="Source"):
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self._close_manager_dialog, dialog)
        dialog.refresh_libraries(select_name=name)
        return dialog

    def _close_manager_dialog(self, dialog):
        from freecad.maxproframe.library_manager_dialog import QtWidgets

        def discard_owned_changes(parent, *args, **kwargs):
            self.assertIs(parent, dialog)
            return QtWidgets.QMessageBox.Discard

        with patch.object(QtWidgets.QMessageBox, "question", side_effect=discard_owned_changes):
            self.assertTrue(dialog.close())

    def test_s1_s2_s3_s5_ui_and_persistence(self):
        from freecad.maxproframe.library_manager_dialog import (
            NewLibraryDialog, QtCore, QtWidgets,
        )
        from freecad.maxproframe.ff_tools import translate
        self.create()
        dialog = self.dialog()
        self.assertIn(translate("frameforge", "Aluminium"), dialog.lbl_lib_banner.text())
        self.assertIn("2.7 g/cm³", dialog.lbl_lib_banner.toolTip())
        self.assertFalse(hasattr(dialog, "btn_calc_weight"))
        self.assertFalse(any(
            button.text() == translate("frameforge", "Calculate Theoretical Weight")
            for button in dialog.findChildren(QtWidgets.QPushButton)
        ))
        # Independently derived rectangular-annulus weights.
        for column, text, expected in [
            (1, "100", "1.577"), (2, "60", "1.685"),
            (3, "3", "2.495"), (4, "4", "2.495"),
        ]:
            dialog.table_sizes.item(0, column).setText(text)
            self.assertEqual(dialog.table_sizes.item(0, 7).text(), expected)
        dialog.table_sizes.item(0, 7).setText("6.789")
        dialog.table_sizes.item(0, 0).setText("Renamed")
        dialog._on_save_library()
        saved = self.manager.get_library("Source")
        self.assertEqual(saved["Square Hollow"]["sizes"]["Renamed"]["Weight"], "6.789")
        dialog.refresh_libraries(select_name="Source")
        self.assertEqual(dialog.table_sizes.item(0, 7).text(), "6.789")
        self.assertTrue(dialog.table_sizes.item(0, 7).flags() & QtCore.Qt.ItemIsEditable)
        picker = NewLibraryDialog(is_duplicate=True)
        self.addCleanup(picker.close)
        self.assertEqual(dict(
            picker.combo_material.itemData(i)
            for i in range(picker.combo_material.count())
        ), STANDARD_DENSITIES)
        self.assertTrue(picker.get_values()[3])
        self.create("Channel", "Channels")
        channel = self.dialog("Channel")
        channel.table_sizes.item(0, 4).setText("4")
        self.assertEqual(channel.table_sizes.item(0, 7).text(), "1.307")

    def test_s4_duplicate_and_collision_invariants(self):
        source = self.create()
        before = self.digest(source)
        self.manager.duplicate_library(
            "Source", "Clone", target_material="Steel", recalculate_weights=True,
        )
        clone = self.manager.get_library("Clone")
        self.assertEqual(clone["_metadata"]["density"], 7.85)
        self.assertEqual(clone["Square Hollow"]["sizes"]["A"]["Weight"], "3.014")
        self.assertEqual(self.digest(source), before)
        target = os.path.join(self.tmp.name, "clone", "library.json")
        target_before = self.digest(target)
        with self.assertRaises(FileExistsError) as error:
            self.manager.duplicate_library(
                "Source", "Clone", target_material="Copper", recalculate_weights=True,
            )
        self.assertEqual(str(error.exception), f"Target directory '{os.path.dirname(target)}' is not empty.")
        self.assertEqual(self.digest(target), target_before)
        self.assertEqual(self.digest(source), before)
        self.assertIn("Clone", self.manager.get_all_profiles())

    def test_s1_partial_legacy_metadata_consistency(self):
        with open(os.path.join(self.tmp.name, "legacy.json"), "w") as stream:
            json.dump({
                "_metadata": {"name": "Legacy", "material": "Aluminium"},
                "Square": {"sizes": {}},
            }, stream)
        listed = next(
            item for item in self.manager.list_libraries() if item["name"] == "Legacy"
        )
        self.assertEqual(
            (listed["material"], listed["density"]),
            self.manager.get_library_material_info("Legacy"),
        )

    def test_s4_material_is_immutable(self):
        path = self.create()
        before = self.digest(path)
        data = self.manager.get_library("Source")
        try:
            self.manager.save_user_library("Source", data, material="Copper", density=8.96)
        except ValueError:
            pass
        self.assertEqual(self.digest(path), before)

    def test_s1_malformed_density_does_not_block_discovery(self):
        self.create()
        with open(os.path.join(self.tmp.name, "bad.json"), "w") as stream:
            json.dump({
                "_metadata": {"name": "Bad", "material": "Steel", "density": "oops"},
            }, stream)
        self.assertIn("Square Hollow", self.manager.get_library("Metal"))
        self.manager.list_libraries()

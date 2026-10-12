import ast
import gc
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
        from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog, QtWidgets

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
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        dialog.refresh_libraries(select_name="OrphanGuardLib")

        self.assertTrue(dialog.btn_add_size.isEnabled())
        del dialog.current_lib_data["SoloFamily"]
        dialog._populate_families()

        self.assertFalse(dialog.btn_del_family.isEnabled())
        self.assertFalse(dialog.btn_add_size.isEnabled())
        self.assertFalse(dialog.btn_del_size.isEnabled())
        self.assertEqual(dialog.table_sizes.rowCount(), 0)

        dialog._on_add_size()
        self.assertEqual(dialog.table_sizes.rowCount(), 0)

        dialog._on_save_library()
        reloaded = self.manager.get_library("OrphanGuardLib")
        self.assertNotIn("SoloFamily", reloaded)

    def test_warning_uses_english_source(self):
        from freecad.frameforge import library_manager_dialog

        with open(library_manager_dialog.__file__, encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read())
        strings = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        self.assertNotIn("Aviso", strings)
        self.assertIn("Warning", strings)

    def test_spanish_locale_translation_survives(self):
        from freecad.frameforge.library_manager_dialog import (
            ProfileLibraryManagerDialog, QtCore, QtWidgets,
        )

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        cls = ProfileLibraryManagerDialog
        original_locale = QtCore.QLocale()
        original_installed = getattr(cls, "_translator_installed", False)
        original_translator = getattr(cls, "_translator", None)
        if original_translator is not None:
            app.removeTranslator(original_translator)
        dialog = None
        fresh_dialog = None
        english_dialog = None
        try:
            cls._translator_installed = False
            cls._translator = None
            QtCore.QLocale.setDefault(QtCore.QLocale("es_ES"))
            dialog = cls(library_manager=self.manager)
            gc.collect()
            self.assertEqual(dialog.btn_new_lib.text(), "+ Nueva")
            self.assertEqual(dialog.windowTitle(), "FrameForge - Gestor de Bibliotecas de Perfiles")
            # A second dialog proves translation still works after the loader returns
            # and garbage collection, rather than merely retaining existing labels.
            fresh_dialog = cls(library_manager=self.manager)
            self.assertEqual(fresh_dialog.btn_new_lib.text(), "+ Nueva")
            self.assertEqual(fresh_dialog.windowTitle(), "FrameForge - Gestor de Bibliotecas de Perfiles")

            # Preserve untranslated English UI when no matching catalog is loaded.
            app.removeTranslator(cls._translator)
            cls._translator_installed = False
            QtCore.QLocale.setDefault(QtCore.QLocale("en_US"))
            english_dialog = cls(library_manager=self.manager)
            self.assertEqual(english_dialog.btn_new_lib.text(), "+ New")
            self.assertEqual(english_dialog.windowTitle(), "FrameForge - Profile Library Manager")
        finally:
            if english_dialog is not None:
                english_dialog.close()
            if fresh_dialog is not None:
                fresh_dialog.close()
            if dialog is not None:
                dialog.close()
            translator = getattr(cls, "_translator", None)
            if translator is not None:
                app.removeTranslator(translator)
            cls._translator = original_translator
            cls._translator_installed = original_installed
            QtCore.QLocale.setDefault(original_locale)
            if original_translator is not None:
                app.installTranslator(original_translator)

    def test_translations_and_indumatics_removal(self):
        from PySide import QtCore, QtWidgets
        from freecad.frameforge.ff_tools import TRANSLATIONSPATH
        from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # 1. Verify Spanish translation loads and translates core UI elements
        translator = QtCore.QTranslator()
        qm_path = os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")
        self.assertTrue(os.path.isfile(qm_path), f"QM file not found at {qm_path}")
        loaded = translator.load(qm_path)
        self.assertTrue(loaded, "Failed to load frameforge_es.qm")

        app.installTranslator(translator)
        try:
            dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
            # Under Spanish translator:
            self.assertEqual(dialog.windowTitle(), "FrameForge - Gestor de Bibliotecas de Perfiles")
            self.assertEqual(dialog.btn_new_lib.text(), "+ Nueva")
            self.assertEqual(dialog.btn_dup_lib.text(), "Duplicar")
            self.assertEqual(dialog.btn_del_lib.text(), "Eliminar")
            self.assertEqual(dialog.btn_save.text(), "Guardar Cambios")

            # Verify 'Indumatics' is nowhere in the dialog texts
            # and replaced with 'Tubos Aluminio'
            self.assertNotIn("Indumatics", dialog.findChildren(QtWidgets.QLabel)[0].text())
            self.assertIn("Tubos Aluminio", dialog.findChildren(QtWidgets.QLabel)[0].text())
        finally:
            app.removeTranslator(translator)



if __name__ == "__main__":
    unittest.main()

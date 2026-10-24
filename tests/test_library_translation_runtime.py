"""Native translation ownership regressions; no translation-function substitutes."""
import os
import tempfile
import unittest
from unittest.mock import patch

try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from freecad.maxproframe.ff_tools import translate, TRANSLATIONSPATH
    from freecad.maxproframe.library_manager import LibraryManager
    from freecad.maxproframe.library_manager_dialog import (
        ProfileLibraryManagerDialog, AddFamilyDialog, NewLibraryDialog,
        ManageProfileLibrariesCommand,
    )
    NATIVE = True
except ImportError:
    NATIVE = False


@unittest.skipUnless(NATIVE, "Native FreeCAD GUI required")
class TestLibraryTranslationRuntime(unittest.TestCase):
    def setUp(self):
        self.prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        language = self.prefs.GetString("Language", "")
        locale = Gui.getLocale()
        default = QtCore.QLocale()
        def restore():
            QtCore.QLocale.setDefault(default)
            Gui.setLocale(locale)
            self.prefs.SetString("Language", language)
            Gui.updateLocale()
        self.addCleanup(restore)
        self.temp = tempfile.TemporaryDirectory(prefix="library-language-")
        self.addCleanup(self.temp.cleanup)
        # Registered before dialogs: LIFO keeps Discard active during close.
        discard = patch.object(QtWidgets.QMessageBox, "question",
                               return_value=QtWidgets.QMessageBox.Discard)
        discard.start()
        self.addCleanup(discard.stop)
        self.manager = LibraryManager(user_dir=self.temp.name)
        self.name = "Mi catálogo English"
        self.data = {"_metadata": {"name": self.name}, "Square Hollow": {
            "norm": "English norma á", "sizes": {"Code English ñ": {
                "Height": "50", "Width": "50", "Thickness": "2",
                "Weight": "1", "Description": "English descripción"}}},
            "Pipe": {"norm": "Pipe standard", "sizes": {}},
            "C": {"norm": "C standard", "fillet": True, "sizes": {}}}
        self.manager.save_user_library(self.name, self.data)
        self.baseline = self.manager.get_library(self.name)

    def language(self, selected, system):
        QtCore.QLocale.setDefault(QtCore.QLocale(system))
        self.prefs.SetString("Language", selected)
        Gui.setLocale(selected)
        Gui.updateLocale()

    def dialog(self):
        dlg = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dlg.close)
        for row in range(dlg.list_libraries.count()):
            if dlg.list_libraries.item(row).data(QtCore.Qt.UserRole)["name"] == self.name:
                dlg.list_libraries.setCurrentRow(row)
                break
        self.family(dlg, "Square Hollow")
        return dlg

    def family(self, dlg, key):
        for row in range(dlg.list_families.count()):
            if dlg.list_families.item(row).data(QtCore.Qt.UserRole) == key:
                dlg.list_families.setCurrentRow(row)
                return
        self.fail(key)

    def assert_spanish(self, dlg):
        self.assertEqual(dlg.list_families.currentItem().text(), "Tubo Cuadrado Hueco")
        self.assertEqual(dlg.lbl_family_name.text(), dlg.list_families.currentItem().text())
        self.assertEqual([dlg.table_sizes.horizontalHeaderItem(i).text() for i in range(9)],
                         ["Código", "Alto [mm]", "Ancho [mm]", "Espesor [mm]",
                          "Espesor Ala [mm]", "Radio 1 [mm]", "Radio 2 [mm]",
                          "Peso [kg/m]", "Labio [mm]"])
        self.assertEqual(dlg.lbl_profile_count.text(), "1 de 1 perfiles")
        self.assertEqual(dlg.table_sizes.item(0, 0).text(), "Code English ñ")
        self.assertEqual(dlg.le_norm.text(), "English norma á")
        dlg.le_search.setText("unmatched")
        self.assertEqual(dlg.lbl_profile_count.text(), "0 de 1 perfiles")
        self.assertEqual(dlg.lbl_profiles_empty.text(), "No hay perfiles que coincidan")
        dlg.le_search.clear()
        dlg.le_norm.setText("Editada")
        self.assertEqual(dlg.lbl_status.text(), "Cambios sin guardar.")
        dlg.close()
        self.assertEqual(self.manager.get_library(self.name), self.baseline)

    def test_a_second_close_preserves_static_and_dynamic_language(self):
        self.language("Spanish", "es_ES")
        first = self.dialog()
        second = self.dialog()
        second.close()
        # Same helper, but the list was built before the second dialog closed.
        self.family(first, "Pipe")
        self.family(first, "Square Hollow")
        self.assert_spanish(first)
        self.assert_spanish(self.dialog())
        self.assertEqual(translate("frameforge", "Create Profile"), "Crear perfil")

    def test_b_selected_spanish_wins_over_english_system(self):
        self.language("Spanish", "en_US")
        self.assert_spanish(self.dialog())

    def test_c_selected_english_wins_over_spanish_system(self):
        self.language("English", "es_ES")
        dlg = self.dialog()
        self.assertEqual(dlg.lbl_family_name.text(), "Square Hollow")
        self.assertEqual(dlg.table_sizes.horizontalHeaderItem(0).text(), "Code")
        self.assertEqual(dlg.lbl_profile_count.text(), "1 of 1 profiles")
        dlg.le_search.setText("unmatched")
        self.assertEqual(dlg.lbl_profiles_empty.text(), "No matching profiles.")
        dlg.le_norm.setText("Changed")
        self.assertEqual(dlg.lbl_status.text(), "Unsaved changes.")
        dlg.close()
        self.assertEqual(translate("frameforge", "Create Profile"), "Create Profile")
        self.assertEqual(self.manager.get_library(self.name), self.baseline)

    def test_d_failed_discovery_can_retry(self):
        self.language("Spanish", "en_US")
        with patch("freecad.maxproframe.library_manager_dialog.TRANSLATIONSPATH", self.temp.name):
            ProfileLibraryManagerDialog.ensure_translations_loaded()
        ProfileLibraryManagerDialog.ensure_translations_loaded()
        self.assert_spanish(self.dialog())

    def test_e_owned_dialogs_alternate_headers_and_shared_consumers(self):
        Gui.addLanguagePath(TRANSLATIONSPATH)
        for selected, system, title in (("Spanish", "en_US", "Crear perfil"),
                                        ("English", "es_ES", "Create Profile")):
            with self.subTest(language=selected):
                self.language(selected, system)
                dlg = self.dialog()
                child = AddFamilyDialog(dlg)
                self.addCleanup(child.close)
                nested = NewLibraryDialog(child, user_dir=self.temp.name)
                self.addCleanup(nested.close)
                self.assertEqual(child.windowTitle(), translate("frameforge", "Add Family"))
                nested.close()
                child.close()
                self.family(dlg, "Pipe")
                self.assertEqual(dlg.table_sizes.horizontalHeaderItem(1).text(),
                                 "Diámetro [mm]" if selected == "Spanish" else "Diameter [mm]")
                self.assertEqual(dlg.lbl_profiles_empty.text(),
                                 "Esta familia no tiene perfiles." if selected == "Spanish"
                                 else "This family has no profiles.")
                self.family(dlg, "C")
                self.assertEqual(dlg.table_sizes.horizontalHeaderItem(5).text(),
                                 "Radio exterior [mm]" if selected == "Spanish" else "Exterior Radius [mm]")
                dlg.close()
                self.assertEqual(translate("frameforge", "Create Profile"), title)

    def test_f_command_reuses_then_reopens_manager(self):
        self.language("Spanish", "en_US")
        command = ManageProfileLibrariesCommand()
        main = Gui.getMainWindow()
        command.Activated()
        first = main._frameforge_library_manager
        self.addCleanup(first.close)
        command.Activated()
        self.assertIs(main._frameforge_library_manager, first)
        first.close()
        command.Activated()
        second = main._frameforge_library_manager
        self.addCleanup(second.close)
        self.assertIsNot(first, second)
        self.assertEqual(second.btn_save.text(), "Guardar Cambios")

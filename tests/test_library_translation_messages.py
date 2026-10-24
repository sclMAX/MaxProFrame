"""Native library presentation tests; translation calls are never mocked."""
import copy
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

VARIANTS = {
    "T-Slot": "Perfil con ranura en T",
    "T-Slot 3-Slots": "Perfil con ranura en T de 3 ranuras",
    "T-Slot 2-Slots": "Perfil con ranura en T de 2 ranuras",
    "T-Slot 2-Slots Opp": "Perfil con ranura en T de 2 ranuras opuestas",
    "T-Slot 1-Slot": "Perfil con ranura en T de 1 ranura",
}


class TestLibraryTranslationMessages(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="library-messages-"))
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        old_language, old_locale = prefs.GetString("Language", ""), Gui.getLocale()
        def restore():
            Gui.setLocale(old_locale)
            prefs.SetString("Language", old_language)
            Gui.updateLocale()
        self.stack.callback(restore)
        self.language("Spanish")
        # Enter before dialog callbacks: LIFO keeps Discard available throughout cleanup.
        self.stack.enter_context(patch.object(QtWidgets.QMessageBox, "question",
                                             return_value=QtWidgets.QMessageBox.Discard))
        self.manager = LibraryManager(user_dir=self.temp)
        self.data = {"_metadata": {"name": "English catálogo"},
                     **{key: {"norm": "English norma", "sizes": {}} for key in VARIANTS},
                     "My T-Slot special": {"norm": "Custom", "sizes": {}},
                     "Square Hollow (Fillet)": {"canonical_family": "Square Hollow",
                                                "fillet": True, "norm": "Raw", "sizes": {}}}
        self.manager.save_user_library("English catálogo", self.data)
        self.before = self.manager.get_library("English catálogo")
        self.dlg = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.stack.callback(self.dlg.close)
        self.dlg.refresh_libraries(select_name="English catálogo")

    def language(self, name):
        App.ParamGet("User parameter:BaseApp/Preferences/General").SetString("Language", name)
        Gui.setLocale(name)
        Gui.updateLocale()

    def family(self, key):
        for row in range(self.dlg.list_families.count()):
            item = self.dlg.list_families.item(row)
            if item.data(QtCore.Qt.UserRole) == key:
                self.dlg.list_families.setCurrentItem(item)
                return item
        self.fail(key)

    def test_delete_prompt_uses_display_but_deletes_only_key(self):
        key = "Square Hollow (Fillet)"
        self.family(key)
        for reply in (QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes):
            with patch.object(QtWidgets.QMessageBox, "question", return_value=reply) as question:
                self.dlg.btn_del_family.click()
            self.assertEqual(question.call_args.args[1:3],
                             ("Eliminar Familia", "¿Eliminar la familia 'Tubo Cuadrado Hueco (Con redondeos)' y todas sus medidas?"))
            expected = copy.deepcopy(self.before)
            if reply == QtWidgets.QMessageBox.Yes:
                del expected[key]
            self.assertEqual(self.dlg.current_lib_data, expected)
            self.assertEqual(self.manager.get_library("English catálogo"), self.before)
        self.dlg.btn_save.click()
        self.assertEqual(self.manager.get_library("English catálogo"), expected)

    def test_standard_variants_and_custom_name_preserve_storage(self):
        for key, display in VARIANTS.items():
            item = self.family(key)
            self.assertEqual(item.text(), display)
            self.assertEqual(self.dlg.lbl_family_name.text(), display)
            self.assertEqual(item.data(QtCore.Qt.UserRole), key)
        self.assertEqual(self.family("My T-Slot special").text(), "My T-Slot special")
        self.assertEqual(self.manager.get_library("English catálogo"), self.before)

    def test_backend_detail_has_translated_action_context(self):
        with patch.object(self.manager, "delete_user_library", side_effect=OSError("kernel diagnostic")), \
             patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes), \
             patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.dlg.btn_del_lib.click()
        self.assertEqual(warning.call_args.args[1:3],
                         ("Error", "No se pudo eliminar la biblioteca 'English catálogo': kernel diagnostic"))
        self.assertEqual(self.manager.get_library("English catálogo"), self.before)
        self.assertEqual(self.dlg.current_lib_data, self.before)

    def test_gui_edit_failures_are_translated_and_reject_without_changes(self):
        # Native visible action, with only the external edit-session/GUI boundary substituted.
        data = {"_metadata": {"name": "Sections"}, "Custom Profile": {
            "norm": "English norm", "sizes": {"English code": {
                "asset_path": "assets/example.FCStd", "Weight": "1",
                "Description": "English description"}}}}
        self.manager.create_folder_library(self.temp + "/sections", "Sections", data=data)
        self.dlg.refresh_libraries(select_name="Sections")
        self.family("Custom Profile")
        self.dlg.table_sizes.selectRow(0)
        self.dlg.show()
        before = self.manager.get_library("Sections")
        cases = ((None, "El documento GUI activo de FreeCAD no está disponible para editar."),
                 (SimpleNamespace(setEdit=lambda _: False), "No se pudo entrar en el modo de edición del croquis."),
                 (SimpleNamespace(setEdit=lambda _: True, getInEdit=lambda: None),
                  "No se pudo verificar el modo de edición del croquis."))
        for gui_doc, message in cases:
            with self.subTest(message=message), ExitStack() as stack:
                session = Mock(working_doc_name="Missing", working_sketch_name="Sketch")
                stack.enter_context(patch("freecad.maxproframe.section_library.resolve_and_validate_asset_path"))
                stack.enter_context(patch("freecad.maxproframe.section_library.SectionEditSession", return_value=session))
                stack.enter_context(patch.object(App, "setActiveDocument"))
                stack.enter_context(patch.object(Gui, "setActiveDocument"))
                stack.enter_context(patch.object(Gui, "activateWorkbench"))
                stack.enter_context(patch.object(Gui, "getDocument", return_value=gui_doc))
                warning = stack.enter_context(patch.object(QtWidgets.QMessageBox, "warning"))
                self.dlg.btn_edit_section.click()
                self.assertEqual(warning.call_args.args[1:3],
                                 ("Error", "No se pudo abrir la sección para editar: " + message))
                session.close.assert_called_once_with(discard_uncommitted=True)
                self.assertEqual(self.manager.get_library("Sections"), before)
                self.assertEqual(self.dlg.current_lib_data, before)
                self.assertFalse(self.dlg.is_dirty)

    def test_english_delete_prompt_and_variant_behavior_preserved(self):
        self.dlg.close()
        self.language("English")
        self.dlg = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.stack.callback(self.dlg.close)
        self.dlg.refresh_libraries(select_name="English catálogo")
        self.family("T-Slot 2-Slots Opp")
        self.assertEqual(self.dlg.lbl_family_name.text(), "T-Slot 2-Slots Opp")
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No) as question:
            self.dlg.btn_del_family.click()
        self.assertEqual(question.call_args.args[1:3],
                         ("Delete Family", "Delete family 'T-Slot 2-Slots Opp' and all its dimensions?"))
        self.assertEqual(self.dlg.current_lib_data, self.before)
        self.assertEqual(self.manager.get_library("English catálogo"), self.before)

"""Native GUI checks for compact metadata and non-destructive family search."""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide import QtCore, QtWidgets

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import AddFamilyDialog, ProfileLibraryManagerDialog


class TestLibraryUsability(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = LibraryManager(user_dir=os.path.join(self.temp.name, "user"),
                                      stock_dir=os.path.join(self.temp.name, "stock"),
                                      registry_path=os.path.join(self.temp.name, "registry.json"))
        self.folder = os.path.join(self.temp.name, "catalog")
        self.manager.create_folder_library(self.folder, "Catalog", data={
            "Square Hollow": {"fillet": True, "norm": "Standard", "sizes": {
                "SH40": {"Height": "40", "Width": "40", "Thickness": "2", "Radius1": "4", "Radius2": "2", "Weight": "2.4", "Description": "Tubo estructural"}}},
            "Custom Profile": {"canonical_family": "Custom Profile", "fillet": False, "sizes": {
                "PGC100": {"Weight": "2.3", "Description": "Correa galvanizada", "vendor": "keep"},
                "AL200": {"Weight": "1.2", "Description": "Ángulo de aluminio"}}},
            "Pipe": {"fillet": False, "sizes": {}}})
        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        def discard_on_cleanup():
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
                self.dialog.close()
        self.addCleanup(discard_on_cleanup)
        self.dialog.refresh_libraries(select_name="Catalog")

    def family(self, name):
        self.dialog.combo_family.setCurrentText(name)

    def test_compact_banner_and_stored_fillet(self):
        self.family("Square Hollow")
        banner = self.dialog.lbl_lib_banner
        self.assertNotIn(self.folder, banner.text())
        self.assertIn("Catalog", banner.text())
        self.assertIn(self.folder, banner.toolTip())
        self.assertIn(self.dialog._get_family_display_name("Square Hollow", self.dialog.current_lib_data["Square Hollow"]),
                      self.dialog.lbl_family_name.text())
        self.assertFalse(hasattr(self.dialog, "cb_fillet"))
        self.assertFalse(self.dialog.table_sizes.isColumnHidden(5))
        self.dialog.table_sizes.item(0, 1).setText("42")
        self.dialog._commit_current_family_edits()
        self.assertTrue(self.dialog.current_lib_data["Square Hollow"]["fillet"])
        picker = AddFamilyDialog(self.dialog)
        self.addCleanup(picker.close)
        self.assertIsInstance(picker.cb_fillet, QtWidgets.QCheckBox)

    def test_header_badges_are_compact_and_inline(self):
        self.family("Pipe")
        self.dialog.show()
        self.app.processEvents()
        library, family = self.dialog.lbl_lib_banner, self.dialog.lbl_family_name
        self.assertLess(library.width(), library.parentWidget().width() - library.x())
        self.assertGreater(family.x(), library.geometry().right())
        self.assertEqual(family.geometry().center().y(), library.geometry().center().y())
        self.assertEqual(family.height(), library.height())
        for badge in (library, family):
            self.assertIsInstance(badge, QtWidgets.QLabel)
            self.assertEqual(badge.textFormat(), QtCore.Qt.PlainText)
            margins = badge.contentsMargins()
            self.assertGreaterEqual(
                badge.height(), badge.fontMetrics().height() + margins.top() + margins.bottom())
            self.assertLessEqual(badge.width(), badge.sizeHint().width())
            self.assertFalse(badge.grab().isNull())
        self.assertTrue(library.text().startswith("Catalog | "))
        self.assertIn(library.text(), library.toolTip())
        self.assertIn(self.folder, library.toolTip())
        self.assertIn("g/cm³", library.toolTip())
        self.assertEqual(family.text(), self.dialog._get_family_display_name("Pipe"))
        self.assertEqual(family.toolTip(), family.text())
        self.family("Square Hollow")
        self.assertEqual(family.text(), self.dialog._get_family_display_name("Square Hollow"))
        self.assertEqual(family.toolTip(), family.text())
        self.dialog.combo_family.setCurrentIndex(-1)
        self.assertTrue(family.isHidden())
        self.assertEqual(family.text(), "")
        self.assertEqual(family.toolTip(), "")

    def test_long_badges_fit_without_changing_data(self):
        self.family("Pipe")
        self.dialog.resize(920, 580)
        self.dialog.show()
        self.app.processEvents()
        width = self.dialog.width()
        before = copy.deepcopy(self.dialog.current_lib_data)
        name = "<b>Long library & material</b> " * 30
        self.dialog._update_banner(True, name, is_folder=True, folder_path=self.folder)
        family = self.dialog.lbl_family_name
        family.setText(name)
        family.setToolTip(name)
        self.app.sendEvent(self.dialog, QtCore.QEvent(QtCore.QEvent.PaletteChange))
        self.app.processEvents()
        self.assertIn(name, self.dialog.lbl_lib_banner.text())
        self.assertEqual(family.text(), name)
        self.assertEqual(self.dialog.width(), width)
        for badge in (self.dialog.lbl_lib_banner, family):
            self.assertEqual(badge.textFormat(), QtCore.Qt.PlainText)
            self.assertLessEqual(badge.x() + badge.width(), badge.parentWidget().width())
            self.assertLess(
                badge.width(), badge.sizeHint().width(),
                f"badge_text={badge.text()!r}; tooltip={badge.toolTip()!r}; expected_length={len(name)}",
            )
            self.assertIn(name, badge.toolTip())
        self.assertIn(self.folder, self.dialog.lbl_lib_banner.toolTip())
        self.assertIn("g/cm³", self.dialog.lbl_lib_banner.toolTip())
        self.assertEqual(self.dialog.current_lib_data, before)
        self.assertFalse(self.dialog.is_dirty)

    def test_delete_requires_real_selection(self):
        self.family("Square Hollow")
        table = self.dialog.table_sizes
        table.setCurrentCell(0, 0)
        table.selectRow(0)
        self.assertTrue(self.dialog.btn_del_size.isEnabled())
        table.clearSelection()
        self.assertFalse(self.dialog.btn_del_size.isEnabled())
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.dialog.btn_del_size.click()
            self.dialog._on_delete_size()
        question.assert_not_called()
        self.assertEqual(table.rowCount(), 1)
        self.family("Pipe")
        self.assertFalse(self.dialog.btn_del_size.isEnabled())

    def test_delete_confirmation_no_preserves_selection_and_storage(self):
        import html
        for family, code in (("Square Hollow", "SH40"), ("Custom Profile", "PGC100")):
            for response in (QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.NoButton, QtWidgets.QMessageBox.Ok):
                with self.subTest(family=family, response=response):
                    self.family(family)
                    table = self.dialog.table_sizes
                    if family == "Custom Profile":
                        self.dialog.cards_view.card_by_code(code).click()
                    else:
                        table.selectRow(0)
                    before = copy.deepcopy(self.dialog.current_lib_data)
                    stored = copy.deepcopy(self.manager.get_library("Catalog"))
                    with open(os.path.join(self.folder, "library.json"), "rb") as stream:
                        manifest = stream.read()
                    rows = [[table.item(r, c).text() if table.item(r, c) else None
                             for c in range(table.columnCount())] for r in range(table.rowCount())]
                    assets = set(self.dialog._staged_deleted_assets)
                    new_assets = set(self.dialog._staged_new_assets)
                    dirty = self.dialog.is_dirty
                    card = self.dialog.cards_view.card_by_code(code) if family == "Custom Profile" else None
                    with patch.object(QtWidgets.QMessageBox, "question", return_value=response) as question:
                        self.dialog.btn_del_size.click()
                    question.assert_called_once_with(
                        self.dialog, translate("frameforge", "Remove Size"),
                        "<p>" + html.escape(translate("frameforge", "Remove size '%s'?") % code) + "</p>",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.No)
                    self.assertEqual(self.dialog.current_lib_data, before)
                    self.assertEqual(self.manager.get_library("Catalog"), stored)
                    with open(os.path.join(self.folder, "library.json"), "rb") as stream:
                        self.assertEqual(stream.read(), manifest)
                    self.assertEqual([[table.item(r, c).text() if table.item(r, c) else None
                                       for c in range(table.columnCount())] for r in range(table.rowCount())], rows)
                    self.assertEqual(self.dialog._staged_deleted_assets, assets)
                    self.assertEqual(self.dialog._staged_new_assets, new_assets)
                    self.assertEqual(self.dialog.is_dirty, dirty)
                    if card:
                        self.assertIs(self.dialog.cards_view.card_by_code(code), card)

    def test_delete_confirmation_yes_and_markup_code(self):
        import html
        self.family("Square Hollow")
        code = "<b>SH40 & special</b>"
        self.dialog.table_sizes.item(0, 0).setText(code)
        self.dialog.table_sizes.selectRow(0)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes) as question:
            self.dialog.btn_del_size.click()
        self.assertEqual(question.call_args[0][2], "<p>" + html.escape(
            translate("frameforge", "Remove size '%s'?") % code) + "</p>")
        self.assertEqual(self.dialog.table_sizes.rowCount(), 0)
        self.assertTrue(self.dialog.is_dirty)
        self.dialog.btn_save.click()
        self.assertEqual(self.manager.get_library("Catalog")["Square Hollow"]["sizes"], {})

    def test_custom_description_persists_with_metadata_and_weight(self):
        self.family("Custom Profile")
        card = self.dialog.cards_view.card_by_code("PGC100")
        card.description_edit.setText("Descripción nueva")
        card.code_edit.setText("PGC101")
        card.weight_edit.setText("3.25")
        self.assertEqual(card.weight_edit._display_lines(), ["3.25 kg/m"])
        self.assertNotIn(translate("frameforge", "Weight (kg/m):"),
                         [label.text() for label in card.findChildren(QtWidgets.QLabel)])
        self.dialog._on_save_library()
        self.dialog.refresh_libraries(select_name="Catalog")
        self.family("Custom Profile")
        card = self.dialog.cards_view.card_by_code("PGC101")
        self.assertEqual(card.description_edit.text(), "Descripción nueva")
        self.assertEqual(card.weight_edit.text(), "3.25")
        props = self.dialog.table_sizes.item(card.row, 0).data(QtCore.Qt.UserRole)
        self.assertEqual(props["vendor"], "keep")
        self.assertEqual(props["Description"], "Descripción nueva")

    def test_search_cards_preserves_hidden_edits_and_selection_safety(self):
        self.family("Custom Profile")
        card = self.dialog.cards_view.card_by_code("PGC100")
        card.description_edit.setText("Correa editada")
        card.click()
        self.dialog.le_search.setText("ANGULO")
        self.assertTrue(card.isHidden())
        self.assertFalse(self.dialog.cards_view.card_by_code("AL200").isHidden())
        self.assertFalse(self.dialog.btn_del_size.isEnabled())
        before = self.dialog.table_sizes.rowCount()
        data_before = copy.deepcopy(self.dialog.current_lib_data)
        dirty_before = self.dialog.is_dirty
        assets_before = set(self.dialog._staged_deleted_assets)
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.dialog.btn_del_size.click()
            self.dialog._on_delete_size()
        question.assert_not_called()
        self.assertEqual(self.dialog.table_sizes.rowCount(), before)
        self.assertEqual(self.dialog.current_lib_data, data_before)
        self.assertEqual(self.dialog.is_dirty, dirty_before)
        self.assertEqual(self.dialog._staged_deleted_assets, assets_before)
        other = self.dialog.cards_view.card_by_code("AL200")
        position = self.dialog.cards_view.grid_layout.getItemPosition(
            self.dialog.cards_view.grid_layout.indexOf(other))
        self.assertEqual(position[:2], (0, 0))
        self.assertEqual(other.row, 1)
        self.assertEqual(self.dialog.lbl_profile_count.text(), translate("frameforge", "%s of %s profiles") % (1, 2))
        self.dialog._on_save_library()
        self.dialog.le_search.clear()
        self.assertFalse(card.isHidden())
        self.assertIs(self.dialog.cards_view.card_by_code("PGC100"), card)
        self.assertEqual(self.dialog.lbl_profile_count.text(), translate("frameforge", "%s of %s profiles") % (2, 2))
        self.dialog.refresh_libraries(select_name="Catalog")
        self.family("Custom Profile")
        self.assertEqual(self.dialog.cards_view.card_by_code("PGC100").description_edit.text(), "Correa editada")
        self.dialog.le_search.setText("pgc")
        self.assertFalse(self.dialog.cards_view.card_by_code("PGC100").isHidden())
        self.assertTrue(self.dialog.cards_view.card_by_code("AL200").isHidden())

    def test_search_table_and_distinct_empty_states(self):
        self.family("Square Hollow")
        self.assertTrue(self.dialog.le_search.isClearButtonEnabled())
        self.dialog.le_search.setText("sh40")
        self.assertFalse(self.dialog.table_sizes.isRowHidden(0))
        self.dialog.le_search.setText("ESTRUCTURAL")
        self.assertFalse(self.dialog.table_sizes.isRowHidden(0))
        self.dialog.le_search.setText("missing")
        self.assertTrue(self.dialog.table_sizes.isRowHidden(0))
        self.assertEqual(self.dialog.lbl_profiles_empty.text(), translate("frameforge", "No matching profiles."))
        self.assertEqual(self.dialog.lbl_profile_count.text(), translate("frameforge", "%s of %s profiles") % (0, 1))
        self.family("Pipe")
        self.assertEqual(self.dialog.lbl_profiles_empty.text(), translate("frameforge", "This family has no profiles."))
        self.assertFalse(self.dialog.is_dirty)

    def test_readonly_fields_search_and_all_remove_buttons(self):
        self.family("Custom Profile")
        data = copy.deepcopy(self.dialog.current_lib_data)
        # Seed via the existing writer, then discover it as a bundled catalog.
        stock_writer = LibraryManager(user_dir=self.manager.stock_dir,
                                      stock_dir=os.path.join(self.temp.name, "empty-stock"))
        stock_writer.save_user_library("Stock", data)
        self.dialog.refresh_libraries(select_name="Stock")
        self.family("Custom Profile")
        self.assertIn(translate("frameforge", "Read-only"), self.dialog.lbl_lib_banner.text())
        card = self.dialog.cards_view.card_by_code("PGC100")
        for field in (card.code_edit, card.weight_edit, card.description_edit):
            self.assertTrue(field.isReadOnly())
        card.click()
        for button in (self.dialog.btn_del_size, self.dialog.btn_del_family, self.dialog.btn_del_lib):
            self.assertFalse(button.isEnabled())
        before = copy.deepcopy(self.manager.get_library("Stock"))
        self.dialog.le_search.setText("galvanizada")
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.dialog.btn_del_size.click()
            self.dialog._on_delete_size()
        question.assert_not_called()
        self.assertEqual(self.manager.get_library("Stock"), before)
        self.assertFalse(self.dialog.is_dirty)

    def test_metadata_merge_table_authority_and_clearing_description(self):
        self.family("Custom Profile")
        card = self.dialog.cards_view.card_by_code("PGC100")
        item = self.dialog.table_sizes.item(card.row, 0)
        props = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        props["new_metadata"] = {"nested": [1, 2]}
        props["Description"] = "Desde la tabla"
        item.setData(QtCore.Qt.UserRole, props)
        self.assertEqual(card.description_edit.text(), "Desde la tabla")
        card.description_edit.clear()
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]["PGC100"]
        self.assertEqual(saved["new_metadata"], {"nested": [1, 2]})
        self.assertEqual(saved["vendor"], "keep")
        self.assertEqual(saved["Description"], "")

    def test_spanish_usability_translations_in_all_runtime_aliases(self):
        from freecad.maxproframe.ff_tools import TRANSLATIONSPATH
        messages = {
            "Remove size '%s'?": "¿Quitar la medida '%s'?",
            "Description:": "Descripción:",
            "Weight (kg/m):": "Peso (kg/m):",
            "Read-only": "Solo lectura",
            "Search this family…": "Buscar en esta familia…",
            "%s of %s profiles": "%s de %s perfiles",
            "No matching profiles.": "No hay perfiles que coincidan",
            "This family has no profiles.": "Esta familia no tiene perfiles.",
        }
        for prefix in ("frameforge", "FrameForge", "maxproframe", "MaxProFrame"):
            for locale in ("es", "es-ES", "es-CO", "es-AR"):
                translator = QtCore.QTranslator()
                self.assertTrue(translator.load(os.path.join(TRANSLATIONSPATH, f"{prefix}_{locale}.qm")))
                for source, expected in messages.items():
                    self.assertEqual(translator.translate("frameforge", source), expected)

    def test_clear_selection_disables_library_and_family_removal(self):
        self.family("Square Hollow")
        self.dialog.list_families.clearSelection()
        self.dialog.list_libraries.clearSelection()
        self.assertFalse(self.dialog.btn_del_family.isEnabled())
        self.assertFalse(self.dialog.btn_del_lib.isEnabled())
        before = copy.deepcopy(self.dialog.current_lib_data)
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.dialog._on_delete_family()
            self.dialog._on_delete_library()
        question.assert_not_called()
        self.assertEqual(self.dialog.current_lib_data, before)

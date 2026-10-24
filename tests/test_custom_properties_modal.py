"""Native GUI coverage for staged custom-profile property edits."""
import copy
import unittest
from unittest.mock import patch

from PySide import QtCore, QtGui, QtWidgets
import test_library_usability as fixtures


class TestCustomPropertiesModal(unittest.TestCase):
    def setUp(self):
        fixtures.TestLibraryUsability.setUp(self)
        self.dialog.combo_family.setCurrentText("Custom Profile")
        self.card = self.dialog.cards_view.card_by_code("PGC100")

    def open_modal(self, action):
        def interact():
            modal = self.app.activeModalWidget()
            try:
                self.assertIsNotNone(modal)
                self.assertEqual(modal.objectName(), "custom_properties_dialog")
                action(modal)
            except BaseException as exc:
                self.error = exc
                modal.reject()
        self.error = None
        QtCore.QTimer.singleShot(0, interact)
        self.card.btn_edit_properties.click()
        if self.error:
            raise self.error

    def fields(self, modal):
        return tuple(modal.findChild(QtWidgets.QLineEdit, name) for name in
                     ("property_code", "property_description", "property_weight"))

    def save(self, modal):
        modal.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Save).click()

    def test_card_is_display_only_and_modal_cancel_preserves_all_data(self):
        before = copy.deepcopy(self.dialog.current_lib_data)
        for field in (self.card.code_edit, self.card.description_edit, self.card.weight_edit):
            self.assertTrue(field.isReadOnly())
            self.assertFalse(field.hasFrame())
        def cancel(modal):
            code, description, weight = self.fields(modal)
            self.assertEqual([f.text() for f in (code, description, weight)],
                             ["PGC100", "Correa galvanizada", "2.3"])
            for field in (code, description, weight):
                self.assertFalse(field.isReadOnly())
                field.setText("changed")
            modal.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Cancel).click()
        self.open_modal(cancel)
        self.assertEqual(self.dialog.current_lib_data, before)
        self.assertFalse(self.dialog.is_dirty)
        self.assertEqual(self.card.code_edit.text(), "PGC100")
        self.assertEqual(self.card.description_edit.text(), "Correa galvanizada")
        self.assertEqual(self.card.weight_edit.text(), "2.3")
        self.assertEqual(self.manager.get_library("Catalog"), before)

    def test_save_updates_card_and_persists_metadata_without_geometry_edit(self):
        def edit(modal):
            for field, value in zip(self.fields(modal), ("PGC101", "Updated description", "3.25")):
                field.setText(value)
            self.save(modal)
        with patch.object(self.dialog, "_on_edit_section") as geometry:
            self.open_modal(edit)
        geometry.assert_not_called()
        self.assertEqual(self.dialog.cards_view.selected_index(), self.card.row)
        self.assertEqual(self.card.code_edit.text(), "PGC101")
        self.assertEqual(self.card.description_edit.text(), "Updated description")
        self.assertEqual(self.card.weight_edit.text(), "3.25")
        self.assertTrue(self.dialog.is_dirty)
        self.assertIn("PGC100", self.manager.get_library("Catalog")["Custom Profile"]["sizes"])
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]
        self.assertNotIn("PGC100", saved)
        self.assertEqual(saved["PGC101"]["vendor"], "keep")
        self.assertEqual(saved["PGC101"]["Description"], "Updated description")
        self.assertEqual(saved["PGC101"]["Weight"], "3.25")
        self.assertEqual(saved["AL200"]["Weight"], "1.2")
        self.dialog.refresh_libraries(select_name="Catalog")
        self.dialog.combo_family.setCurrentText("Custom Profile")
        self.assertEqual(self.dialog.cards_view.card_by_code("PGC101").weight_edit.text(), "3.25")

    def test_invalid_properties_never_partially_apply(self):
        before = copy.deepcopy(self.manager.get_library("Catalog"))
        item = self.dialog.table_sizes.item(self.card.row, 0)
        metadata = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        def invalid(modal):
            code, description, weight = self.fields(modal)
            with patch.object(QtWidgets.QMessageBox, "warning") as warning:
                for bad_code, bad_weight in (("", "2"), (" AL200 ", "2"),
                                              ("NEW", "0"), ("NEW", "-1"),
                                              ("NEW", "nan"), ("NEW", "inf"),
                                              ("NEW", "bad")):
                    code.setText(bad_code)
                    description.setText("must not leak")
                    weight.setText(bad_weight)
                    self.save(modal)
                    self.assertTrue(modal.isVisible())
                    self.assertEqual(item.text(), "PGC100")
                    self.assertEqual(item.data(QtCore.Qt.UserRole), metadata)
                    self.assertEqual(self.card.weight_edit.text(), "2.3")
                    self.assertFalse(self.dialog.is_dirty)
                self.assertEqual(warning.call_count, 7)
            modal.reject()
        self.open_modal(invalid)
        self.assertEqual(self.manager.get_library("Catalog"), before)

    def test_readonly_disables_modal_even_after_palette_change(self):
        self.card.set_editable(False)
        self.app.setPalette(QtGui.QPalette(self.app.palette()))
        self.assertFalse(self.card.btn_edit_properties.isEnabled())
        with patch.object(QtWidgets.QDialog, "exec_") as execute:
            self.card.btn_edit_properties.click()
            self.card._edit_properties()
        execute.assert_not_called()
        self.assertFalse(self.dialog.is_dirty)

    def test_standard_family_remains_editable_table(self):
        self.dialog.combo_family.setCurrentText("Square Hollow")
        self.dialog.table_sizes.item(0, 1).setText("42")
        self.dialog.btn_save.click()
        self.assertEqual(self.manager.get_library("Catalog")["Square Hollow"]["sizes"]["SH40"]["Height"], "42")

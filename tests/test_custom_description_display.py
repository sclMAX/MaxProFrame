"""Native read-only descriptions must never truncate the stored catalog value."""
import copy
import unittest

from PySide import QtCore, QtWidgets

import test_library_usability as fixtures


class TestCustomDescriptionDisplay(unittest.TestCase):
    def setUp(self):
        fixtures.TestLibraryUsability.setUp(self)
        self.dialog.combo_family.setCurrentText("Custom Profile")
        self.card = self.dialog.cards_view.card_by_code("PGC100")

    def test_unfocused_description_shows_prefix_and_preserves_saved_text(self):
        text = "Perfil C 100mm x 40mm con una descripción larga " * 3
        field = self.card.description_edit
        field.setText(text)
        field.setFixedWidth(120)
        field.clearFocus()
        self.assertFalse(field.hasFocus())
        self.assertFalse(field.grab().isNull())
        self.assertEqual(field.textFormat(), QtCore.Qt.PlainText)
        # Read QLabel's actual display string, separately from the raw adapter.
        lines = QtWidgets.QLabel.text(field).splitlines()
        displayed = " ".join(lines)
        self.assertTrue(lines[0].startswith("Perfil C"), displayed)
        self.assertTrue(lines[-1].endswith("…"), displayed)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertLessEqual(field.fontMetrics().horizontalAdvance(line), field.contentsRect().width())
        self.assertNotEqual(displayed, text)
        self.assertEqual(field.text(), text)
        self.assertEqual(field.toolTip(), text)
        item = self.dialog.table_sizes.item(self.card.row, 0)
        expected = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        self.assertEqual(expected["Description"], text)
        self.assertEqual(expected["vendor"], "keep")
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]["PGC100"]
        for key, value in expected.items():
            self.assertEqual(saved[key], value)
        self.dialog.refresh_libraries(select_name="Catalog")
        self.dialog.combo_family.setCurrentText("Custom Profile")
        restored = self.dialog.cards_view.card_by_code("PGC100").description_edit
        self.assertEqual(restored.text(), text)
        self.assertEqual(restored.toolTip(), text)

    def test_readonly_description_preserves_raw_signals_table_and_saved_value(self):
        field = self.card.description_edit
        self.assertIsInstance(field, QtWidgets.QLabel)
        self.assertTrue(field.isReadOnly())
        self.assertEqual(field.focusPolicy(), QtCore.Qt.NoFocus)
        changes = []
        field.textChanged.connect(changes.append)
        self.addCleanup(lambda: field.textChanged.disconnect(changes.append))
        text = "Perfilnuevo  C 100mm x 40mm"
        field.setText(text)
        field.setText(text)
        self.assertEqual(changes, [text])
        self.assertEqual(field.text(), text)
        self.assertEqual(field.toolTip(), text)
        item = self.dialog.table_sizes.item(self.card.row, 0)
        props = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        self.assertEqual(props["Description"], text)
        self.assertEqual(props["vendor"], "keep")

        # Table-originated updates remain authoritative, without signal feedback.
        table_text = "Perfil C 100mm x 40mm\nDescripción completa desde tabla"
        props["Description"] = table_text
        item.setData(QtCore.Qt.UserRole, props)
        self.assertEqual(changes, [text, table_text])
        self.assertEqual(field.text(), table_text)
        self.assertEqual(field.toolTip(), table_text)
        self.assertEqual(item.data(QtCore.Qt.UserRole), props)
        self.assertTrue(self.dialog.is_dirty)
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]["PGC100"]
        for key, value in props.items():
            self.assertEqual(saved[key], value)
        self.assertEqual(saved["Weight"], "2.3")

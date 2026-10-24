"""Description elision must never truncate the editable catalog value."""
import unittest
from unittest.mock import patch

from PySide import QtCore, QtGui, QtWidgets

import test_library_usability as fixtures


class TestCustomDescriptionDisplay(unittest.TestCase):
    def setUp(self):
        fixtures.TestLibraryUsability.setUp(self)
        self.dialog.combo_family.setCurrentText("Custom Profile")
        self.card = self.dialog.cards_view.card_by_code("PGC100")

    def test_unfocused_description_shows_prefix_and_preserves_saved_text(self):
        text = "Perfil C 100mm x 40mm con una descripción larga"
        field = self.card.description_edit
        field.setText(text)
        field.resize(120, 28)
        field.clearFocus()
        self.assertFalse(field.hasFocus())
        with patch.object(QtWidgets, "QStylePainter") as painter:
            field.grab()
        painter.return_value.drawText.assert_called()
        displayed = painter.return_value.drawText.call_args.args[-1]
        self.assertTrue(displayed.startswith("Perfil C"), displayed)
        self.assertTrue(displayed.endswith("…"), displayed)
        self.assertNotEqual(displayed, text)
        self.assertEqual(field.text(), text)
        self.assertEqual(field.toolTip(), text)
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Catalog")["Custom Profile"]["sizes"]["PGC100"]
        self.assertEqual(saved["Description"], text)

    def test_editing_keeps_full_value_and_caret_position(self):
        field = self.card.description_edit
        field.setText("Perfil C 100mm x 40mm")
        field.setCursorPosition(6)
        field.insert("nuevo ")
        self.assertEqual(field.text(), "Perfilnuevo  C 100mm x 40mm")
        self.assertEqual(field.cursorPosition(), 12)
        self.assertEqual(field.toolTip(), field.text())
        item = self.dialog.table_sizes.item(self.card.row, 0)
        self.assertEqual(item.data(QtCore.Qt.UserRole)["Description"], field.text())

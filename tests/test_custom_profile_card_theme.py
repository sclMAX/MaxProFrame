"""Native Qt checks for palette-aware custom profile cards."""
import unittest
from types import SimpleNamespace

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from freecad.maxproframe.custom_profile_cards import CustomProfileCard


class TestCustomProfileCardTheme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.original_palette = QtGui.QPalette(self.app.palette())
        self.parent = QtWidgets.QWidget()
        self.selected = []
        self.card = CustomProfileCard(
            2, "CP2", "10.31", {},
            SimpleNamespace(current_lib_meta={"is_user": True}),
            SimpleNamespace(select_card=self.selected.append), self.parent,
        )
        QtWidgets.QVBoxLayout(self.parent).addWidget(self.card)

    def tearDown(self):
        self.parent.close()
        self.parent.deleteLater()
        self.app.setPalette(self.original_palette)
        self.app.processEvents()

    def apply_theme(self, dark):
        palette = QtGui.QPalette(self.app.palette())
        colors = {
            QtGui.QPalette.Window: "#303030" if dark else "#eeeeee",
            QtGui.QPalette.WindowText: "#eeeeee" if dark else "#202020",
            QtGui.QPalette.Base: "#202020" if dark else "#ffffff",
            QtGui.QPalette.Text: "#ffffff" if dark else "#101010",
            QtGui.QPalette.AlternateBase: "#404040" if dark else "#dddddd",
            QtGui.QPalette.Mid: "#808080",
            QtGui.QPalette.Highlight: "#225588",
            QtGui.QPalette.HighlightedText: "#ffffff",
        }
        for role, color in colors.items():
            palette.setColor(role, QtGui.QColor(color))
        self.app.setPalette(palette)
        self.parent.show()
        self.app.processEvents()
        return palette

    def assert_theme(self, palette, selected):
        self.app.processEvents()
        background = QtGui.QPalette.Highlight if selected else QtGui.QPalette.Window
        foreground = QtGui.QPalette.HighlightedText if selected else QtGui.QPalette.WindowText
        image = self.card.grab().toImage()
        self.assertEqual(image.pixelColor(5, 5).name(), palette.color(background).name())
        labels = [label for label in self.card.findChildren(QtWidgets.QLabel)
                  if label is not self.card.thumbnail_label]
        self.assertEqual(len(labels), 3)
        for label in labels:
            self.assertEqual(label.palette().color(QtGui.QPalette.WindowText).name(),
                             palette.color(foreground).name())
        for editor in (self.card.code_edit, self.card.weight_edit):
            self.assertEqual(editor.palette().color(QtGui.QPalette.Text).name(),
                             palette.color(QtGui.QPalette.Text).name())
            role = QtGui.QPalette.AlternateBase if editor.isReadOnly() else QtGui.QPalette.Base
            self.assertEqual(editor.palette().color(QtGui.QPalette.Base).name(), palette.color(role).name())
        self.assertEqual(self.card.thumbnail_label.palette().color(QtGui.QPalette.Window).name(),
                         palette.color(QtGui.QPalette.Base).name())

    def test_light_and_dark_selected_editable_and_readonly(self):
        for dark in (False, True):
            for editable in (True, False):
                for selected in (False, True):
                    with self.subTest(dark=dark, editable=editable, selected=selected):
                        palette = self.apply_theme(dark)
                        self.card.set_editable(editable)
                        self.card.setSelected(selected)
                        self.assert_theme(palette, selected)
                        self.assertEqual(self.card.code_edit.isReadOnly(), not editable)
                        self.assertEqual(self.card.weight_edit.isReadOnly(), not editable)
                        self.assertEqual(self.card.code_edit.text(), "CP2")
                        self.assertEqual(self.card.weight_edit.text(), "10.31")
        self.selected.clear()
        self.card.click()
        self.assertEqual(self.selected, [2])

    def test_live_theme_change_preserves_selection_and_readonly(self):
        self.card.set_editable(False)
        self.card.setSelected(True)
        for dark in (True, False, True):
            with self.subTest(dark=dark):
                self.assert_theme(self.apply_theme(dark), True)
                self.assertTrue(self.card.code_edit.isReadOnly())
                self.assertTrue(self.card.weight_edit.isReadOnly())

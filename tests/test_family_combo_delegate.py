"""Native regression tests for the translated Family combo of Create Profiles.

The popup delegate must never treat the combo box itself as an open item
editor: focus changes and Tab/Enter/Escape on the combo used to make Qt print
"QAbstractItemView::commitData/closeEditor called with an editor that does not
belong to this view" and swallowed Tab and Escape.
"""

import unittest
from unittest.mock import patch

# Imported as a module so unittest does not collect its test case here again.
import test_task_panel_preview as preview
from PySide import QtCore, QtGui, QtWidgets


class TestFamilyComboDelegate(unittest.TestCase):
    setUpClass = classmethod(preview.TestTaskPanelPreview.setUpClass.__func__)
    setUp = preview.TestTaskPanelPreview.setUp
    _language = preview.TestTaskPanelPreview._language
    _close_panels = preview.TestTaskPanelPreview._close_panels
    _panel = preview.TestTaskPanelPreview._panel

    def _combo(self):
        panel = self._panel()
        combo = panel.form_proxy.combo_family
        delegate = combo.itemDelegate()
        signals = []
        delegate.commitData.connect(lambda editor: signals.append(("commitData", editor)))
        delegate.closeEditor.connect(lambda editor, hint=None: signals.append(("closeEditor", editor)))
        return panel, combo, signals

    def _key(self, combo, key):
        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            event = QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier)
            self.app.sendEvent(combo, event)
        self.app.processEvents()

    def test_focus_out_does_not_close_the_combo_as_an_item_editor(self):
        _panel, combo, signals = self._combo()
        self.app.sendEvent(combo, QtGui.QFocusEvent(QtCore.QEvent.FocusOut, QtCore.Qt.TabFocusReason))
        self.app.processEvents()
        self.assertEqual(signals, [])

    def test_editing_keys_do_not_commit_or_close_the_combo(self):
        _panel, combo, signals = self._combo()
        for key in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            with self.subTest(key=key):
                self._key(combo, key)
                self.assertEqual(signals, [])
        self._key(combo, QtCore.Qt.Key_Escape)
        self.assertEqual(signals, [])

    def test_family_names_are_still_translated_in_popup_and_combo(self):
        panel, combo, _signals = self._combo()
        seen = []

        def fake_translate(context, text, *args):
            seen.append((context, text))
            return "T:" + text

        with patch("freecad.maxproframe.create_profiles_tool.translate", side_effect=fake_translate):
            option = QtWidgets.QStyleOptionViewItem()
            combo.itemDelegate().initStyleOption(option, combo.model().index(combo.currentIndex(), 0))
            self.assertEqual(option.text, "T:Custom Profile")
            seen.clear()
            combo.grab()
            self.assertIn(("frameforge", "Custom Profile"), seen)
        self.assertEqual(combo.currentText(), "Custom Profile")
        self.assertEqual(panel.form_proxy.combo_family.currentText(), "Custom Profile")


if __name__ == "__main__":
    unittest.main()

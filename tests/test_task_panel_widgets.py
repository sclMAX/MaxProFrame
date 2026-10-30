import os
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.task_panel_widgets import (
    EdgeListWidget,
    ModeSwitchWidget,
    SectionHeaderButton,
    create_advanced_icon,
    create_mirror_h_icon,
    create_mirror_v_icon,
    create_placement_icon,
    create_pre_extend_icon,
    create_profile_section_icon,
)


class TestTaskPanelWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        # Earlier suites may leave a non-English locale installed; these assertions expect English text.
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        language, locale, default = prefs.GetString("Language", ""), Gui.getLocale(), QtCore.QLocale()

        def restore_language():
            prefs.SetString("Language", language)
            Gui.setLocale(locale)
            Gui.updateLocale()
            QtCore.QLocale.setDefault(default)

        self.addCleanup(restore_language)
        prefs.SetString("Language", "English")
        Gui.setLocale("English")
        Gui.updateLocale()
        QtCore.QLocale.setDefault(QtCore.QLocale("en_US"))

    def test_icons_creation(self):
        icon_mh = create_mirror_h_icon()
        self.assertFalse(icon_mh.isNull())
        pix_off = icon_mh.pixmap(16, 16, QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.assertFalse(pix_off.isNull())
        pix_on = icon_mh.pixmap(16, 16, QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.assertFalse(pix_on.isNull())

        icon_mv = create_mirror_v_icon()
        self.assertFalse(icon_mv.isNull())

        icon_pe = create_pre_extend_icon()
        self.assertFalse(icon_pe.isNull())

        icon_ps = create_profile_section_icon()
        self.assertFalse(icon_ps.isNull())

        icon_pl = create_placement_icon()
        self.assertFalse(icon_pl.isNull())

        icon_adv = create_advanced_icon()
        self.assertFalse(icon_adv.isNull())

    def test_section_header_button(self):
        target = QtWidgets.QWidget()
        target.show()
        btn = SectionHeaderButton("Profile", create_profile_section_icon(), target, expanded=True)
        self.assertTrue(btn.isChecked())
        self.assertTrue(target.isVisible())
        self.assertEqual(btn.arrowType(), QtCore.Qt.DownArrow)

        # Toggle to collapse
        btn.setChecked(False)
        self.assertFalse(target.isVisible())
        self.assertEqual(btn.arrowType(), QtCore.Qt.RightArrow)

        # Toggle to expand
        btn.setChecked(True)
        self.assertTrue(target.isVisible())
        self.assertEqual(btn.arrowType(), QtCore.Qt.DownArrow)

    def test_mode_switch_widget(self):
        switch = ModeSwitchWidget()
        self.assertFalse(switch.is_per_edge())

        received = []
        switch.modeChanged.connect(received.append)

        switch.set_per_edge(True)
        self.assertTrue(switch.is_per_edge())
        self.assertEqual(received, [True])

        switch.set_per_edge(False)
        self.assertFalse(switch.is_per_edge())
        self.assertEqual(received, [True, False])

    def test_edge_list_widget(self):
        edge_list = EdgeListWidget()
        edges = [("e1", "Arista 1 (Edge1)"), ("e2", "Arista 2 (Edge2)")]
        edge_list.set_edges(edges)
        # Key events only reach the list while its own window is active, not one left active by another suite.
        edge_list.show()
        edge_list.activateWindow()
        edge_list.list_widget.setFocus()
        self.addCleanup(edge_list.close)
        self.app.processEvents()

        self.assertEqual(edge_list.get_selected_edge(), "e1")
        self.assertEqual(edge_list.list_widget.selectionMode(), QtWidgets.QAbstractItemView.ExtendedSelection)
        # Qt records the modifiers of a delivered key press as the application state; clear it afterwards or
        # later tests that read QApplication.keyboardModifiers() see a Ctrl that nobody is holding.
        self.addCleanup(lambda: self.assertEqual(QtWidgets.QApplication.keyboardModifiers(), QtCore.Qt.NoModifier))
        self.addCleanup(
            QtWidgets.QApplication.sendEvent,
            edge_list.list_widget,
            QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.NoModifier),
        )
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        QtWidgets.QApplication.sendEvent(edge_list.list_widget, event)
        self.assertEqual(edge_list.get_selected_edges(), ["e1", "e2"])

        selected = []
        edge_list.edgeSelected.connect(selected.append)

        edge_list.select_edge("e2")
        self.assertEqual(edge_list.get_selected_edge(), "e2")
        self.assertIn("e2", selected)

        # Update badge
        edge_list.update_edge_badge("e2", rotation="90", mirror_h=True, mirror_v=False)
        _, item_widget = edge_list._items["e2"]
        self.assertEqual(item_widget.lbl_badge.text(), "90° · Mirror H")

        # Remove edge
        removed = []
        edge_list.edgeRemoved.connect(removed.append)
        item_widget.btn_remove.click()
        self.assertEqual(removed, ["e2"])


if __name__ == "__main__":
    unittest.main()

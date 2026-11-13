"""Expression fields (Fx): the icon sits at the right end of the field, vertically centered, and a bound field
keeps its text readable in FreeCAD's dark theme (odd/tasks/folded-corners.md, T7: S14)."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.expression_fields import bind, count_field, length_field, unbind

# Pixels the icon may sit off its place (FreeCAD's margin and rounding).
SLACK = 6
MAIN_WINDOW_PARAMS = "User parameter:BaseApp/Preferences/MainWindow"
# What the FreeCAD Dark preference pack sets (PreferencePacks/FreeCAD Dark/FreeCAD Dark.cfg).
DARK_THEME = (("StyleSheet", "FreeCAD.qss"), ("Theme", "FreeCAD Dark"), ("QtStyle", "FreeCAD"))
# Least lightness difference (0-255) between a text and its background for the text to be read.
READABLE = 100


def use_dark_theme(test):
    """Style FreeCAD with its FreeCAD Dark theme for ``test``, as the preference pack does; the theme before after."""
    param = App.ParamGet(MAIN_WINDOW_PARAMS)
    stored = param.GetStrings()
    saved = [(name, name in stored, param.GetString(name)) for name, _ in DARK_THEME]

    def restore():
        for name, was_stored, value in saved:
            if was_stored:
                param.SetString(name, value)
            else:
                param.RemString(name)
        Gui.runCommand("Std_ReloadStyleSheet")

    test.addCleanup(restore)
    for name, value in DARK_THEME:
        param.SetString(name, value)
    # FreeCAD restyles on its Reload stylesheet command, not when the parameters change; it fills the @ colors.
    Gui.runCommand("Std_ReloadStyleSheet")


def assert_readable(test, spin):
    """The text of ``spin`` reads on its background whether its window is active or not."""
    palette = spin.lineEdit().palette()
    text = palette.color(QtGui.QPalette.Active, QtGui.QPalette.Text)
    base = palette.color(QtGui.QPalette.Active, QtGui.QPalette.Base)
    inactive = palette.color(QtGui.QPalette.Inactive, QtGui.QPalette.Text)
    test.assertGreaterEqual(abs(text.lightness() - base.lightness()), READABLE, (text.name(), base.name()))
    test.assertEqual(inactive.name(), text.name())


class ExpressionFieldFixture(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.doc = App.newDocument("ExpressionIconTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        if Gui.activeDocument() is None:
            self.skipTest("Real GUI document required for the expression binding")
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.addProperty("App::PropertyLength", "Length")
        self.varset.addProperty("App::PropertyInteger", "Number")
        self.window = QtWidgets.QWidget()
        self.addCleanup(self.window.deleteLater)
        self.layout = QtWidgets.QFormLayout(self.window)

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()


class TestExpressionIconPlace(ExpressionFieldFixture):
    def icon(self, spin):
        labels = [label for label in spin.lineEdit().findChildren(QtWidgets.QLabel) if label.isVisible()]
        self.assertEqual(len(labels), 1, labels)
        return labels[0]

    def assert_in_place(self, spin):
        line = spin.lineEdit()
        icon = self.icon(spin).geometry()
        self.assertGreater(icon.width(), 0)
        self.assertLess(icon.width(), line.height())
        # At the right end of the text field, left of the spin arrows.
        self.assertGreaterEqual(icon.left(), 0)
        self.assertLessEqual(line.width() - 1 - icon.right(), SLACK, (line.geometry(), icon))
        self.assertGreaterEqual(line.width() - 1 - icon.right(), 0, (line.geometry(), icon))
        # Vertically centered.
        self.assertLessEqual(abs((icon.top() + icon.bottom()) - (line.height() - 1)), 2, (line.geometry(), icon))

    def test_a_field_bound_once_shown_places_its_icon_at_the_right_vertically_centered(self):
        # The Drill Hole panel binds its fields to the preview once there is one: the panel is shown by then.
        length = length_field(0.0, 1000.0, 10.0)
        count = count_field(1, 100, 1)
        self.layout.addRow("Length", length)
        self.layout.addRow("Count", count)
        self.window.resize(320, 120)
        self.window.show()
        self.events()
        self.assertTrue(bind(length, self.varset, "Length"))
        self.assertTrue(bind(count, self.varset, "Number"))
        self.events()
        self.assert_in_place(length)
        self.assert_in_place(count)

    def test_a_field_bound_before_shown_places_its_icon_at_the_right_vertically_centered(self):
        length = length_field(0.0, 1000.0, 10.0)
        self.layout.addRow("Length", length)
        self.assertTrue(bind(length, self.varset, "Length"))
        self.window.resize(320, 120)
        self.window.show()
        self.events()
        self.assert_in_place(length)

    def test_the_icon_follows_the_field_when_it_is_resized(self):
        length = length_field(0.0, 1000.0, 10.0)
        self.layout.addRow("Length", length)
        self.window.resize(320, 120)
        self.window.show()
        self.events()
        self.assertTrue(bind(length, self.varset, "Length"))
        self.window.resize(480, 120)
        self.events()
        self.assert_in_place(length)


class TestExpressionFieldColors(ExpressionFieldFixture):
    """A bound field keeps the text colors of the theme, and FreeCAD's own colors for an expression."""

    def show_bound(self):
        spin = length_field(0.0, 1000.0, 10.0)
        self.layout.addRow("Length", spin)
        self.window.resize(320, 120)
        self.window.show()
        self.events()
        self.assertTrue(bind(spin, self.varset, "Length"))
        self.events()
        return spin

    def test_a_bound_field_reads_in_the_dark_theme(self):
        use_dark_theme(self)
        spin = self.show_bound()
        assert_readable(self, spin)
        # Unbound again it still reads.
        unbind(spin)
        self.events()
        assert_readable(self, spin)

    def test_a_field_driven_by_an_expression_keeps_freecads_expression_color(self):
        use_dark_theme(self)
        spin = self.show_bound()
        self.varset.setExpression("Length", "2 * 6 mm")
        self.doc.recompute()
        self.events()
        self.assertTrue(Gui.ExpressionBinding(spin).hasExpression())
        palette = spin.lineEdit().palette()
        driven = palette.color(QtGui.QPalette.Active, QtGui.QPalette.Text)
        self.assertEqual(QtGui.QColor(QtCore.Qt.lightGray).name(), driven.name())
        self.assertEqual(driven.name(), palette.color(QtGui.QPalette.Inactive, QtGui.QPalette.Text).name())
        # An expression that cannot be evaluated: FreeCAD's red.
        self.varset.setExpression("Length", "2 * 6 mm * Nowhere")
        self.doc.recompute()
        self.events()
        invalid = spin.lineEdit().palette().color(QtGui.QPalette.Active, QtGui.QPalette.Text)
        self.assertEqual(QtGui.QColor(QtCore.Qt.red).name(), invalid.name())
        # The expression taken away: the theme's text again.
        self.varset.setExpression("Length", None)
        self.doc.recompute()
        self.events()
        assert_readable(self, spin)


class TestExpressionUnbind(ExpressionFieldFixture):
    """unbind takes the expression editor away from a field until it is bound again."""

    def editors_opened_by_equal(self, spin):
        """Type = in ``spin``; the expression editors it opened, closed (FreeCAD's editor is not modal)."""
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Equal, QtCore.Qt.NoModifier, "=")
        QtWidgets.QApplication.sendEvent(spin, event)
        self.events()
        opened = [
            widget
            for widget in QtWidgets.QApplication.topLevelWidgets()
            if widget.isVisible() and widget.objectName() == "DlgExpressionInput"
        ]
        names = [widget.objectName() for widget in opened]
        for widget in opened:
            widget.close()
        self.events()
        return names

    def test_a_failed_bind_keeps_the_field_unbound(self):
        # The field stays bound to the old object when binding fails: = must still open no editor on it.
        spin = length_field(0.0, 1000.0, 10.0)
        self.layout.addRow("Length", spin)
        self.window.show()
        self.events()
        self.assertTrue(bind(spin, self.varset, "Length"))
        self.assertEqual(self.editors_opened_by_equal(spin), ["DlgExpressionInput"])
        unbind(spin)
        self.assertEqual(self.editors_opened_by_equal(spin), [])
        with patch.object(Gui, "ExpressionBinding", side_effect=RuntimeError("cannot bind")):
            self.assertFalse(bind(spin, self.varset, "Length"))
        self.assertEqual(self.editors_opened_by_equal(spin), [])
        self.assertEqual(list(self.varset.ExpressionEngine), [])
        # A bind that works gives the editor back.
        self.assertTrue(bind(spin, self.varset, "Length"))
        self.assertEqual(self.editors_opened_by_equal(spin), ["DlgExpressionInput"])


if __name__ == "__main__":
    unittest.main()

"""Task panel number fields that take FreeCAD expressions (the Fx button), bound to a document object property.

The fields are FreeCAD's ``Gui::DoubleSpinBox`` and ``Gui::IntSpinBox``: a ``QDoubleSpinBox`` and a
``QSpinBox`` with the expression editor once bound. The Fx editor sets the expression on the bound
property at once, inside the transaction the panel holds open; OK keeps it, Cancel takes it back.
"""

import FreeCADGui as Gui
from PySide import QtCore, QtGui


def _widget(class_name, fallback):
    widget = Gui.UiLoader().createWidget(class_name)
    widget = widget if widget is not None else fallback()
    _keep_theme_text(widget)
    return widget


# Object name of the event filter that keeps the text of a field in the colors of the theme.
_THEME_TEXT = "maxproframe_theme_text"


class _ThemeText(QtCore.QObject):
    """Gives the text of an editable field the colors of the theme back when FreeCAD resets them.

    FreeCAD's spin box keeps the palette its field had before the stylesheet styled it and, whenever the field
    is resized or bound with no expression, sets the text of the active window to that palette's: black on the
    dark field of FreeCAD Dark. A field driven by an expression is read-only: its gray (or red, when invalid)
    text is FreeCAD's and stays.
    """

    def __init__(self, spin):
        super().__init__(spin)
        self.setObjectName(_THEME_TEXT)
        self.spin = spin
        self.syncing = False

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.PaletteChange and not self.syncing:
            self.sync()
        return False

    def sync(self):
        line = self.spin.lineEdit()
        if line is None or self.spin.isReadOnly():
            return
        theme = self.spin.palette()
        palette = line.palette()
        text = QtGui.QPalette.Text
        groups = (QtGui.QPalette.Active, QtGui.QPalette.Inactive)
        if all(palette.color(group, text) == theme.color(group, text) for group in groups):
            return
        for group in groups:
            palette.setColor(group, text, theme.color(group, text))
        self.syncing = True
        try:
            line.setPalette(palette)
        finally:
            self.syncing = False


def _keep_theme_text(spin):
    """Keep the text of ``spin`` in the colors of the theme (see _ThemeText); once per field."""
    line = spin.lineEdit()
    if line is None or spin.findChildren(QtCore.QObject, _THEME_TEXT):
        return
    keeper = _ThemeText(spin)
    # The field's own palette changes when the theme does; its line edit's when FreeCAD sets its colors.
    spin.installEventFilter(keeper)
    line.installEventFilter(keeper)
    keeper.sync()


def length_field(minimum, maximum, value, decimals=2):
    """A length field in mm, from ``minimum`` to ``maximum``, showing ``value``."""
    spin = _widget("Gui::DoubleSpinBox", QtGui.QDoubleSpinBox)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSuffix(" mm")
    spin.setValue(value)
    return spin


def angle_field(minimum, maximum, value, decimals=2):
    """An angle field in degrees, from ``minimum`` to ``maximum``, showing ``value``."""
    spin = _widget("Gui::DoubleSpinBox", QtGui.QDoubleSpinBox)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSuffix(" °")
    spin.setValue(value)
    return spin


def count_field(minimum, maximum, value):
    """A whole number field from ``minimum`` to ``maximum``, showing ``value``."""
    spin = _widget("Gui::IntSpinBox", QtGui.QSpinBox)
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    return spin


# Object name of the event filter unbind installs on a field.
_NO_EDITOR = "maxproframe_no_expression_editor"


class _NoEditor(QtCore.QObject):
    """Swallows the = that opens the expression editor of a field: the object it was bound to is done."""

    def eventFilter(self, watched, event):
        return event.type() == QtCore.QEvent.KeyPress and event.text() == "="


def bind(widget, obj, prop):
    """Bind ``widget`` to ``obj.prop`` so it offers the expression editor; False when it cannot.

    A field unbound before gets its editor back only once bound: a failed bind leaves it bound to the old
    object, whose editor stays taken away.
    """
    _keep_theme_text(widget)
    try:
        Gui.ExpressionBinding(widget).bind(obj, prop)
    except Exception:
        return False
    for blocker in widget.findChildren(QtCore.QObject, _NO_EDITOR):
        widget.removeEventFilter(blocker)
        # deleteLater deletes it on the next event loop: unnamed, unbind no longer takes it for the one in place.
        blocker.setObjectName("")
        blocker.deleteLater()
    _place_icon(widget)
    return True


def unbind(widget):
    """Take the expression editor away from ``widget`` until it is bound again; FreeCAD has no unbind.

    The field stays bound to the object it showed: its Fx icon is hidden and its = swallowed, so the editor
    cannot set an expression on that object. Binding the field again shows the icon.
    """
    _keep_theme_text(widget)
    for label in widget.lineEdit().findChildren(QtGui.QLabel):
        label.hide()
    if not widget.findChildren(QtCore.QObject, _NO_EDITOR):
        blocker = _NoEditor(widget)
        blocker.setObjectName(_NO_EDITOR)
        widget.installEventFilter(blocker)


def _place_icon(widget):
    """Put the Fx icon of ``widget`` at the right end of the field, vertically centered.

    FreeCAD places the icon only when the field is resized, and the icon is sized when the field is
    bound: a field bound once shown (the Drill Hole panel binds to its first preview) keeps the icon
    where its unbound size put it, short of the right end and above the middle.
    """
    size = widget.size()
    QtCore.QCoreApplication.sendEvent(widget, QtGui.QResizeEvent(size, size))


def expression_of(obj, prop):
    """The expression driving ``obj.prop``, or None."""
    for path, expression in getattr(obj, "ExpressionEngine", ()):
        if path.lstrip(".") == prop:
            return expression
    return None


def expressions_of(obj, props):
    """{prop: expression or None} for each of ``props`` of ``obj``."""
    return {prop: expression_of(obj, prop) for prop in props}


def restore_expressions(obj, expressions):
    """Give ``obj`` back the ``expressions`` taken by expressions_of; whether one changed."""
    changed = False
    for prop, expression in expressions.items():
        if expression_of(obj, prop) != expression:
            obj.setExpression(prop, expression)
            changed = True
    return changed


def fit_width(spin, longest):
    """Fix the width of ``spin`` to show the text of ``longest`` beside its Fx icon.

    FreeCAD draws the icon over the end of the text and no layout keeps the field wide enough for both:
    a Pattern field would be squeezed under its value in a narrow panel and stretched in a wide one.
    """
    spin.ensurePolished()
    metrics = spin.fontMetrics()
    hint = spin.sizeHint()
    # The size hint fits the text of the maximum; the rest is the frame, the margins and the arrows.
    frame = hint.width() - metrics.horizontalAdvance(spin.textFromValue(spin.maximum()) + spin.suffix())
    # The icon is a square as high as the field.
    spin.setFixedWidth(frame + metrics.horizontalAdvance(spin.textFromValue(longest) + spin.suffix()) + hint.height())


def length_text(value):
    """``value`` in mm as a pattern shows it: up to two decimals, no trailing zeros (12.5 mm)."""
    return f"{value:.2f}".rstrip("0").rstrip(".") + " mm"

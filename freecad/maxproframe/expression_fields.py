"""Task panel number fields that take FreeCAD expressions (the Fx button), bound to a document object property.

The fields are FreeCAD's ``Gui::DoubleSpinBox`` and ``Gui::IntSpinBox``: a ``QDoubleSpinBox`` and a
``QSpinBox`` with the expression editor once bound. The Fx editor sets the expression on the bound
property at once, inside the transaction the panel holds open; OK keeps it, Cancel takes it back.
"""

import FreeCADGui as Gui
from PySide import QtCore, QtGui


def _widget(class_name, fallback):
    widget = Gui.UiLoader().createWidget(class_name)
    return widget if widget is not None else fallback()


def length_field(minimum, maximum, value, decimals=2):
    """A length field in mm, from ``minimum`` to ``maximum``, showing ``value``."""
    spin = _widget("Gui::DoubleSpinBox", QtGui.QDoubleSpinBox)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSuffix(" mm")
    spin.setValue(value)
    return spin


def count_field(minimum, maximum, value):
    """A whole number field from ``minimum`` to ``maximum``, showing ``value``."""
    spin = _widget("Gui::IntSpinBox", QtGui.QSpinBox)
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    return spin


def bind(widget, obj, prop):
    """Bind ``widget`` to ``obj.prop`` so it offers the expression editor; False when it cannot."""
    try:
        Gui.ExpressionBinding(widget).bind(obj, prop)
    except Exception:
        return False
    _place_icon(widget)
    return True


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

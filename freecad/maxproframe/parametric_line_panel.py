"""Task panel of parametric lines drawn from vertices along a global axis or a custom vector.

Creating, the panel previews one line per selected vertex and OK keeps them in one Undo step. Editing (a
double-click on such a line), it changes that line. The Length field takes expressions (the Fx button): bound
to the first line, its expression is given to every line of the panel.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui

from freecad.maxproframe import expression_fields
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.parametric_line import AXES, DEFAULT_LENGTH, make_line_from_vertex
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Direction of new lines: legs hang down from a frame.
DEFAULT_DIRECTION = "-Z"
# Properties of a line the panel sets, restored when an edit is cancelled.
EDITED_PROPERTIES = ("Direction", "CustomDirection", "Length")
VECTOR_LIMIT = 1e6


class ParametricLineTaskPanel:
    """Direction, custom vector and length of lines from ``vertices`` ((object, "VertexN")), or of ``edited``."""

    def __init__(self, vertices=(), edited=None):
        self.edited = edited
        self.doc = edited.Document if edited is not None else App.ActiveDocument
        self._closed = False
        if edited is not None:
            self.lines = [edited]
            self._saved = {prop: getattr(edited, prop) for prop in EDITED_PROPERTIES}
            self._saved_expression = expression_fields.expression_of(edited, "Length")
            direction, custom, length = edited.Direction, App.Vector(edited.CustomDirection), edited.Length.Value
            self.doc.openTransaction("Edit Parametric Line")
        else:
            direction, custom, length = DEFAULT_DIRECTION, App.Vector(0, 0, -1), DEFAULT_LENGTH
            self.doc.openTransaction("Create Parametric Line")
            self.lines = [
                make_line_from_vertex(vertex, direction, length, custom, recompute=False) for vertex in vertices
            ]
        self.form = keep_alive_until_destroyed(self._build_form(direction, custom, length))
        self._connect()
        if self.lines:
            expression_fields.bind(self.form.spin_length, self.lines[0], "Length")
        self._update()

    # Form.

    def _build_form(self, direction, custom, length):
        form = QtGui.QWidget()
        form.setWindowTitle(translate("frameforge", "Parametric Line"))
        layout = QtGui.QVBoxLayout(form)
        group = QtGui.QGroupBox(translate("frameforge", "From the vertex"))
        rows = QtGui.QFormLayout(group)
        form.combo_direction = QtGui.QComboBox()
        for axis in AXES:
            form.combo_direction.addItem(axis, axis)
        form.combo_direction.addItem(translate("frameforge", "Custom vector"), "Custom")
        form.combo_direction.setCurrentIndex(max(0, form.combo_direction.findData(direction)))
        form.combo_direction.setToolTip(
            translate("frameforge", "Global axis the lines run along, or Custom vector to give X, Y and Z.")
        )
        rows.addRow(QtGui.QLabel(translate("frameforge", "Direction")), form.combo_direction)
        for axis in ("x", "y", "z"):
            spin = QtGui.QDoubleSpinBox()
            spin.setRange(-VECTOR_LIMIT, VECTOR_LIMIT)
            spin.setDecimals(3)
            spin.setValue(getattr(custom, axis))
            setattr(form, f"spin_{axis}", spin)
            rows.addRow(QtGui.QLabel(f"{axis.upper()}"), spin)
        form.spin_length = expression_fields.length_field(0.01, 1e7, length)
        form.spin_length.setToolTip(translate("frameforge", "Length of each line. Fx takes an expression."))
        rows.addRow(QtGui.QLabel(translate("frameforge", "Length")), form.spin_length)
        layout.addWidget(group)
        form.status_label = QtGui.QLabel()
        form.status_label.setWordWrap(True)
        layout.addWidget(form.status_label)
        return form

    def _connect(self):
        form = self.form
        form.combo_direction.currentIndexChanged.connect(self._update)
        for spin in (form.spin_x, form.spin_y, form.spin_z, form.spin_length):
            spin.valueChanged.connect(self._update)

    def direction(self):
        return self.form.combo_direction.currentData()

    def custom_vector(self):
        form = self.form
        return App.Vector(form.spin_x.value(), form.spin_y.value(), form.spin_z.value())

    # Preview.

    def _update(self, *args):
        """Give every line the values of the fields and recompute them."""
        if self._closed:
            return
        form = self.form
        custom = self.direction() == "Custom"
        for spin in (form.spin_x, form.spin_y, form.spin_z):
            spin.setEnabled(custom)
        zero = custom and self.custom_vector().Length < 1e-9
        form.status_label.setText(translate("frameforge", "The custom vector is zero: give X, Y or Z.") if zero else "")
        if not self.lines:
            return
        expression = expression_fields.expression_of(self.lines[0], "Length")
        for line in self.lines:
            line.Direction = self.direction()
            line.CustomDirection = self.custom_vector()
            if line is not self.lines[0]:
                if expression_fields.expression_of(line, "Length") != expression:
                    line.setExpression("Length", expression)
            if expression is None:
                line.Length = form.spin_length.value()
        self.doc.recompute()

    # Dialog.

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def accept(self):
        self._update()
        self._closed = True
        self.doc.commitTransaction()
        self._close()
        return True

    def reject(self):
        self._closed = True
        self.doc.abortTransaction()
        # With Undo off the transaction keeps nothing: take the changes back by hand.
        if self.edited is not None:
            if _alive(self.edited):
                for prop, value in self._saved.items():
                    setattr(self.edited, prop, value)
                self.edited.setExpression("Length", self._saved_expression)
        else:
            for line in self.lines:
                if _alive(line):
                    self.doc.removeObject(line.Name)
        self.doc.recompute()
        self._close()
        return True

    def _close(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()


def _alive(obj):
    try:
        return obj.Document is not None and obj.Name in [o.Name for o in obj.Document.Objects]
    except Exception:
        return False


def show_panel(panel):
    Gui.Control.showDialog(panel)

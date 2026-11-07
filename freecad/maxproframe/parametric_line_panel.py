"""Task panel of parametric lines drawn from vertices along a global axis, a custom vector or an angle in a plane.

Creating, the panel previews one line per selected vertex; a click on a vertex adds a line from it, a click
on a vertex with a line removes that line, and OK keeps them in one Undo step. It starts with the direction,
custom vector, plane, angle and length of the last OK. Editing (a double-click on such a line), it changes that
line. The Length and Angle fields take expressions (the Fx button): bound to the first line, their expressions
are given to every line of the panel.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.maxproframe import expression_fields
from freecad.maxproframe.ff_tools import get_param_group, translate
from freecad.maxproframe.parametric_line import AXES, DEFAULT_LENGTH, PLANES, _global_vertex, make_line_from_vertex
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Direction of new lines until an OK remembers one: legs hang down from a frame.
DEFAULT_DIRECTION = "-Z"
DEFAULT_CUSTOM = App.Vector(0, 0, -1)
DEFAULT_PLANE = "XY"
# Values of the last OK on a new-line panel, the ones the next one starts with.
DIRECTION_PARAM = "Parametric Line Direction"
LENGTH_PARAM = "Parametric Line Length"
PLANE_PARAM = "Parametric Line Plane"
ANGLE_PARAM = "Parametric Line Angle"
CUSTOM_PARAMS = {axis: f"Parametric Line Custom {axis.upper()}" for axis in ("x", "y", "z")}
# Properties of a line the panel sets, restored when an edit is cancelled.
EDITED_PROPERTIES = ("Direction", "CustomDirection", "Plane", "Angle", "Length")
# Properties whose expression, set with Fx on the first line, every line of the panel gets.
EXPRESSION_PROPERTIES = ("Length", "Angle")
VECTOR_LIMIT = 1e6


def remembered_values():
    """Values a new-line panel starts with: direction, custom vector, length, plane and angle."""
    param = get_param_group()
    direction = param.GetString(DIRECTION_PARAM, DEFAULT_DIRECTION)
    if direction not in (*AXES, "Custom", "Angle"):
        direction = DEFAULT_DIRECTION
    custom = App.Vector(*(param.GetFloat(CUSTOM_PARAMS[axis], getattr(DEFAULT_CUSTOM, axis)) for axis in "xyz"))
    length = param.GetFloat(LENGTH_PARAM, DEFAULT_LENGTH)
    plane = param.GetString(PLANE_PARAM, DEFAULT_PLANE)
    if plane not in PLANES:
        plane = DEFAULT_PLANE
    return {
        "direction": direction,
        "custom": custom,
        "length": length if length > 0 else DEFAULT_LENGTH,
        "plane": plane,
        "angle": _angle_in_range(param.GetFloat(ANGLE_PARAM, 0.0)),
    }


def _angle_in_range(angle):
    """``angle`` in degrees brought into -180..180."""
    return (angle + 180.0) % 360.0 - 180.0 if not -180.0 <= angle <= 180.0 else angle


def _angle_hint(plane):
    """Which way the angle runs in ``plane``: "0° = +X, 90° = +Y"."""
    first, second = plane
    return f"0° = +{first}, 90° = +{second}"


def _clicked_vertex(doc, obj, sub):
    """(object, "VertexN") of a click on ``sub`` of the object named ``obj``, or None when it is no vertex."""
    document = App.getDocument(doc) if doc in App.listDocuments() else None
    top = document.getObject(getattr(obj, "Name", obj)) if document is not None else None
    if top is None or not sub:
        return None
    try:
        # A click inside a Part names the path to the object holding the vertex.
        source = top.getSubObjectList(sub)[-1]
    except Exception:
        return None
    element = sub.rsplit(".", 1)[-1]
    if not element.startswith("Vertex") or _global_vertex((source, [element])) is None:
        return None
    return source, element


class ParametricLineTaskPanel:
    """Direction, custom vector and length of lines from ``vertices`` ((object, "VertexN")), or of ``edited``."""

    def __init__(self, vertices=(), edited=None):
        self.edited = edited
        self.doc = edited.Document if edited is not None else App.ActiveDocument
        self._closed = False
        # Expression of the Length of the last line removed, given to the next line added.
        self._expressions = {}
        self._message = ""
        if edited is not None:
            self.lines = [edited]
            self._saved = {prop: getattr(edited, prop) for prop in EDITED_PROPERTIES}
            self._saved_expressions = expression_fields.expressions_of(edited, EXPRESSION_PROPERTIES)
            values = {
                "direction": edited.Direction,
                "custom": App.Vector(edited.CustomDirection),
                "length": edited.Length.Value,
                "plane": edited.Plane,
                "angle": edited.Angle.Value,
            }
            self.doc.openTransaction("Edit Parametric Line")
        else:
            values = remembered_values()
            self.doc.openTransaction("Create Parametric Line")
            self.lines = [
                make_line_from_vertex(
                    vertex,
                    values["direction"],
                    values["length"],
                    values["custom"],
                    recompute=False,
                    plane=values["plane"],
                    angle=values["angle"],
                )
                for vertex in vertices
            ]
        self.form = keep_alive_until_destroyed(self._build_form(values))
        # FreeCAD may close the dialog without OK or Cancel: clicks then stop adding lines.
        self.form.destroyed.connect(self._stop_picking)
        self._connect()
        # The line the Length field is bound to, for its Fx editor.
        self._bound = None
        self._bind_length()
        self._update()

    # Form.

    def _build_form(self, values):
        form = QtGui.QWidget()
        form.setWindowTitle(translate("frameforge", "Parametric Line"))
        layout = QtGui.QVBoxLayout(form)
        group = QtGui.QGroupBox(translate("frameforge", "From the vertex"))
        rows = QtGui.QFormLayout(group)
        form.combo_direction = QtGui.QComboBox()
        for axis in AXES:
            form.combo_direction.addItem(axis, axis)
        form.combo_direction.addItem(translate("frameforge", "Angle in a plane"), "Angle")
        form.combo_direction.addItem(translate("frameforge", "Custom vector"), "Custom")
        form.combo_direction.setCurrentIndex(max(0, form.combo_direction.findData(values["direction"])))
        form.combo_direction.setToolTip(
            translate(
                "frameforge",
                "Global axis the lines run along, Angle in a plane to give a global plane and an angle, or Custom "
                "vector to give X, Y and Z.",
            )
        )
        rows.addRow(QtGui.QLabel(translate("frameforge", "Direction")), form.combo_direction)
        for axis in ("x", "y", "z"):
            spin = QtGui.QDoubleSpinBox()
            spin.setRange(-VECTOR_LIMIT, VECTOR_LIMIT)
            spin.setDecimals(3)
            spin.setValue(getattr(values["custom"], axis))
            setattr(form, f"spin_{axis}", spin)
            rows.addRow(QtGui.QLabel(f"{axis.upper()}"), spin)
        form.combo_plane = QtGui.QComboBox()
        for plane in PLANES:
            form.combo_plane.addItem(plane, plane)
        form.combo_plane.setCurrentIndex(max(0, form.combo_plane.findData(values["plane"])))
        form.combo_plane.setToolTip(translate("frameforge", "Global plane the angle is measured in."))
        rows.addRow(QtGui.QLabel(translate("frameforge", "Plane")), form.combo_plane)
        form.spin_angle = expression_fields.angle_field(-180, 180, values["angle"])
        form.spin_angle.setToolTip(
            translate("frameforge", "Angle in the plane, counterclockwise from its first axis. Fx takes an expression.")
        )
        rows.addRow(QtGui.QLabel(translate("frameforge", "Angle")), form.spin_angle)
        form.angle_hint = QtGui.QLabel()
        rows.addRow(QtGui.QLabel(), form.angle_hint)
        form.spin_length = expression_fields.length_field(0.01, 1e7, values["length"])
        form.spin_length.setToolTip(translate("frameforge", "Length of each line. Fx takes an expression."))
        rows.addRow(QtGui.QLabel(translate("frameforge", "Length")), form.spin_length)
        layout.addWidget(group)
        if self.edited is None:
            form.hint_label = QtGui.QLabel(
                translate("frameforge", "Click a vertex to add a line from it. Click it again to remove its line.")
            )
            form.hint_label.setWordWrap(True)
            layout.addWidget(form.hint_label)
        form.status_label = QtGui.QLabel()
        form.status_label.setWordWrap(True)
        layout.addWidget(form.status_label)
        return form

    def _connect(self):
        form = self.form
        form.combo_direction.currentIndexChanged.connect(self._update)
        form.combo_plane.currentIndexChanged.connect(self._update)
        for spin in (form.spin_x, form.spin_y, form.spin_z, form.spin_angle, form.spin_length):
            spin.valueChanged.connect(self._update)

    def direction(self):
        return self.form.combo_direction.currentData()

    def custom_vector(self):
        form = self.form
        return App.Vector(form.spin_x.value(), form.spin_y.value(), form.spin_z.value())

    def plane(self):
        return self.form.combo_plane.currentData()

    # Preview.

    def _update(self, *args):
        """Give every line the values of the fields and recompute them."""
        if self._closed:
            return
        form = self.form
        custom = self.direction() == "Custom"
        for spin in (form.spin_x, form.spin_y, form.spin_z):
            spin.setEnabled(custom)
        angle = self.direction() == "Angle"
        form.combo_plane.setEnabled(angle)
        form.spin_angle.setEnabled(angle)
        form.angle_hint.setText(_angle_hint(self.plane()) if angle else "")
        zero = custom and self.custom_vector().Length < 1e-9
        messages = [translate("frameforge", "The custom vector is zero: give X, Y or Z.")] if zero else []
        form.status_label.setText("\n".join(messages + ([self._message] if self._message else [])))
        if not self.lines:
            return
        expressions = expression_fields.expressions_of(self.lines[0], EXPRESSION_PROPERTIES)
        fields = {"Length": form.spin_length, "Angle": form.spin_angle}
        for line in self.lines:
            line.Direction = self.direction()
            line.CustomDirection = self.custom_vector()
            line.Plane = self.plane()
            for prop, expression in expressions.items():
                if line is not self.lines[0] and expression_fields.expression_of(line, prop) != expression:
                    line.setExpression(prop, expression)
                if expression is None:
                    setattr(line, prop, fields[prop].value())
        self.doc.recompute()

    def _bind_length(self):
        """Bind the Length and Angle fields to the first line, or take their Fx editors away when there is no line."""
        first = self.lines[0] if self.lines else None
        if first is self._bound:
            return
        for field, prop in ((self.form.spin_length, "Length"), (self.form.spin_angle, "Angle")):
            if first is None:
                expression_fields.unbind(field)
            else:
                expression_fields.bind(field, first, prop)
        self._bound = first

    # Picking vertices.

    def addSelection(self, doc, obj, sub, other):
        # Never change the document or the selection during FreeCAD's selection observer dispatch.
        if not self._closed:
            QtCore.QTimer.singleShot(0, lambda: self._pick(doc, obj, sub))

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, doc):
        pass

    def _pick(self, doc, obj, sub):
        """A click on a vertex adds a line from it, or removes the line it has; any other click says so."""
        if self._closed:
            return
        vertex = _clicked_vertex(doc, obj, sub) if doc == self.doc.Name else None
        line = self._line_of(vertex)
        if line is not None:
            self._remove(line)
            self._message = ""
        elif vertex is not None and vertex[0] not in self.lines:
            self._add(vertex)
            self._message = ""
        else:
            self._message = translate("frameforge", "Click a vertex: only a vertex starts a line.")
        Gui.Selection.clearSelection()
        self._bind_length()
        self._update()

    def _line_of(self, vertex):
        """The line of the panel starting at ``vertex``, or None; the start of a line stands for its vertex."""
        if vertex is None:
            return None
        source, element = vertex
        for line in self.lines:
            if (source == line and element == "Vertex1") or (
                line.Vertex1 and line.Vertex1[0] == source and list(line.Vertex1[1]) == [element]
            ):
                return line
        return None

    def _add(self, vertex):
        line = make_line_from_vertex(
            vertex,
            self.direction(),
            self.form.spin_length.value(),
            self.custom_vector(),
            recompute=False,
            plane=self.plane(),
            angle=self.form.spin_angle.value(),
        )
        if not self.lines:
            for prop, expression in self._expressions.items():
                if expression is not None:
                    line.setExpression(prop, expression)
        self.lines.append(line)

    def _remove(self, line):
        if len(self.lines) == 1:
            self._expressions = expression_fields.expressions_of(line, EXPRESSION_PROPERTIES)
        self.lines.remove(line)
        if line is self._bound:
            # Their Fx editors must not reach a removed line, even before the fields are bound again.
            expression_fields.unbind(self.form.spin_length)
            expression_fields.unbind(self.form.spin_angle)
            self._bound = None
        self.doc.removeObject(line.Name)

    def _stop_picking(self, *args):
        self._closed = True
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    # Dialog.

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def accept(self):
        self._update()
        self._stop_picking()
        if self.edited is None:
            self._remember()
        if self.edited is None and not self.lines:
            # Nothing was created: no Undo step.
            self.doc.abortTransaction()
        else:
            self.doc.commitTransaction()
        self._close()
        return True

    def _remember(self):
        param = get_param_group(writable=True)
        param.SetString(DIRECTION_PARAM, self.direction())
        custom = self.custom_vector()
        for axis, name in CUSTOM_PARAMS.items():
            param.SetFloat(name, getattr(custom, axis))
        param.SetFloat(LENGTH_PARAM, self.form.spin_length.value())
        param.SetString(PLANE_PARAM, self.plane())
        param.SetFloat(ANGLE_PARAM, self.form.spin_angle.value())

    def reject(self):
        self._stop_picking()
        self.doc.abortTransaction()
        # With Undo off the transaction keeps nothing: take the changes back by hand.
        if self.edited is not None:
            if _alive(self.edited):
                for prop, value in self._saved.items():
                    setattr(self.edited, prop, value)
                expression_fields.restore_expressions(self.edited, self._saved_expressions)
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
    if panel.edited is None:
        # Clicks start from an empty selection: a click on a selected vertex is then a click too.
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(panel)

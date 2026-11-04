import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe.create_end_miter_tool import (
    GAP_DELAY_MS,
    _alive_document,
    _failures,
    remove_overlay,
    scene_graph,
)
from freecad.maxproframe.create_extend_cut_tool import (
    _in_document,
    _selected_items,
    _trim_chain,
    show_panel,
    trimmed_body_problem,
)
from freecad.maxproframe.create_extruded_cutout_tool import CUT_TYPE_LABELS, MAX_DEPTH, MIN_DEPTH, face_problem
from freecad.maxproframe.create_profiles_tool import place_in_container_of
from freecad.maxproframe.drill_hole import (
    DEFAULT_CUT_TYPE,
    DEFAULT_DIAMETER,
    DEFAULT_PITCH,
    REFERENCE_TOLERANCE,
    make_drill_hole,
)
from freecad.maxproframe.expression_fields import (
    bind,
    count_field,
    expression_of,
    expressions_of,
    length_field,
    restore_expressions,
)
from freecad.maxproframe.extruded_cutout import CUT_TYPES, wall_thickness
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Offsets of a new drill hole from its vertex, in mm.
DEFAULT_OFFSET = 10.0
# Ranges of the panel fields: offsets and pitch in mm, diameter in mm, count as the Count property allows.
MAX_OFFSET = 1e6
MIN_DIAMETER = 0.01
MAX_COUNT = 1000
# Two values closer than this are the same.
TOLERANCE = 1e-9
# Color of the marker on the reference corner.
CORNER_MARKER_COLOR = (1.0, 0.6, 0.0)


def _click_point(other):
    """The global point of a 3D view click from the selection observer, or None.

    A selection made without a point (the tree, a script) reports the origin: it stands for no point.
    """
    try:
        point = App.Vector(*other[:3])
    except Exception:
        return None
    return None if point.Length == 0 else point


def _container_placement(obj):
    """Placement from the coordinates of the shape of ``obj`` to global coordinates."""
    try:
        return obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    except Exception:
        return App.Placement()


def _nearest_corner(obj, face, point):
    """Name of the vertex of the face ``face`` of ``obj`` nearest to the global ``point``, or None."""
    face_shape = _element(obj, face)
    if not isinstance(face_shape, Part.Face) or not face_shape.Vertexes:
        return None
    local = _container_placement(obj).inverse().multVec(point)
    nearest = min(face_shape.Vertexes, key=lambda vertex: vertex.Point.distanceToPoint(local))
    return _base_element(obj, nearest)


def _face_corners(obj, face):
    """Names of the vertices of the face ``face`` of ``obj``, in the order of the face."""
    face_shape = _element(obj, face)
    if not isinstance(face_shape, Part.Face):
        return []
    return [name for name in (_base_element(obj, vertex) for vertex in face_shape.Vertexes) if name]


def _spin_changed(spin, stored):
    """Whether ``spin`` shows another value than ``stored``, as far as its decimals tell.

    A stored length finer than the field (4.7625 shown as 4.76) is kept until the field is changed.
    """
    # Rounded the way the field rounds it: Python's round(30.125, 2) is 30.12, the field shows 30.13.
    shown = spin.valueFromText(spin.textFromValue(stored))
    return abs(shown - spin.value()) > TOLERANCE


def _element(obj, sub):
    """The element ``sub`` of the shape of ``obj``, or None when it has none by that name."""
    try:
        return obj.Shape.getElement(sub) if sub else None
    except Exception:
        return None


def _on_face(obj, face, vertex):
    """Whether the vertex ``vertex`` of ``obj`` is a vertex of its face ``face``."""
    face_shape, vertex_shape = _element(obj, face), _element(obj, vertex)
    if not isinstance(face_shape, Part.Face) or not isinstance(vertex_shape, Part.Vertex):
        return False
    return any(point.Point.isEqual(vertex_shape.Point, REFERENCE_TOLERANCE) for point in face_shape.Vertexes)


def _base_element(base, element):
    """Name of the element of ``base`` that ``element`` (of a drill hole on ``base``) lies on, or None.

    A vertex is the vertex of ``base`` at its place; a planar face is the face of ``base`` in its plane
    that overlaps it most.
    """
    if isinstance(element, Part.Vertex):
        for index, vertex in enumerate(base.Shape.Vertexes, start=1):
            if vertex.Point.isEqual(element.Point, REFERENCE_TOLERANCE):
                return f"Vertex{index}"
        return None
    if not isinstance(element, Part.Face) or not isinstance(element.Surface, Part.Plane):
        return None
    normal = element.normalAt(0, 0)
    overlaps = []
    for index, face in enumerate(base.Shape.Faces, start=1):
        if not isinstance(face.Surface, Part.Plane) or face.normalAt(0, 0).getAngle(normal) > TOLERANCE**0.5:
            continue
        if abs((face.CenterOfMass - element.CenterOfMass).dot(normal)) > REFERENCE_TOLERANCE:
            continue
        overlaps.append((face.common(element).Area, f"Face{index}"))
    area, name = max(overlaps, default=(0.0, None))
    return name if area > TOLERANCE else None


# Properties of a drill hole its panel fields bind to, for expressions.
EXPRESSION_PROPERTIES = ("OffsetAlong", "OffsetAcross", "Diameter", "Count", "Pitch", "ExtrusionLength")


class DrillHoleTaskPanel:
    """Face, vertex, offsets, diameter, linear pattern and depth of a drill hole, previewed live.

    A click on a planar face of a profile, a trimmed profile or a cutout picks the face and its corner
    nearest to the click, the vertex the holes are placed from; a click on one of its vertices, or Next
    corner, picks that vertex. Every other pick is explained. The picked corner is marked in the 3D view.
    A click on the drill hole being previewed or edited (it hides its base) stands for the face or
    vertex of its base under the click.

    Without ``edited`` the preview is the drill hole OK keeps, made once a face and a vertex are
    picked, inside one transaction that Cancel aborts. With ``edited`` (an existing drill hole) the
    edited hole itself is the preview, inside the edit transaction: OK keeps the changes in one Undo
    step, or none when nothing changed; Cancel puts the stored values back.

    The preview follows the panel under the Update automatically check box, like Extend / Cut does:
    value changes once typing pauses, picks at once. OK applies the panel values in any case.
    """

    # Remembered state of the "Update automatically" check box, and its value until first changed.
    auto_preview_param = "Drill Hole Auto Preview"
    auto_preview_default = True

    def __init__(self, selection=(), edited=None):
        self.edited = edited
        # The drill hole showing the panel: the edited one, or the preview once there is one.
        self.obj = edited
        self.doc = edited.Document if edited is not None else App.ActiveDocument
        self.face = None
        self.vertex = None
        self._closed = False
        self._transaction_open = False
        # (scene, node) of the marker on the reference corner, and its global point.
        self._corner_node = None
        self._corner_point = None
        # (body, visibility) of the bodies the preview hides, as they were before.
        self._visibility = []
        # Message area: what the last pick explained, then the last preview or OK failure.
        self._messages = []
        self._error = ""
        # What the shown drill hole was last recomputed for (see _wanted).
        self._previewed = ()
        # A recompute pumps Qt events: an update asked for meanwhile runs once it ends.
        self._recomputing = False
        self._pending = False
        # OK or Cancel pressed during a recompute: it runs once the recompute ends.
        self._deferred = None
        # Expressions of the dropped preview, given to the next one.
        self._expressions = {}
        # Value changes fire one by one while typing: the preview waits this long for the next one.
        self._preview_timer = QtCore.QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(GAP_DELAY_MS)
        self._preview_timer.timeout.connect(self._update_preview)
        if edited is not None:
            base, (face, *_) = edited.baseObject
            self.face = (base, face)
            self.vertex = edited.ReferenceVertex
            # The values Cancel puts back, also when undo is disabled.
            self._edit_before = self._values(edited)
            self._edit_expressions = expressions_of(edited, EXPRESSION_PROPERTIES)
        self.form = keep_alive_until_destroyed(self._build_form())
        # FreeCAD may close the dialog without OK or Cancel: the form is then deleted.
        self.form.destroyed.connect(self._form_gone)
        if edited is not None:
            self._previewed = self._wanted()
            # The expression editor (Fx) changes the edited hole at once: inside the edit transaction.
            self._open_transaction()
        messages = []
        if edited is None:
            messages = self._add_items(selection)
        self._show(messages)
        self._show_warning()
        if edited is None:
            self._update_preview()

    def _build_form(self):
        form = QtGui.QWidget()
        form.setWindowTitle(translate("frameforge", "Drill Hole"))
        layout = QtGui.QVBoxLayout(form)

        form.groupBox_reference = QtGui.QGroupBox(translate("frameforge", "Reference"))
        reference = QtGui.QVBoxLayout(form.groupBox_reference)
        form.face_label = QtGui.QLabel()
        form.vertex_label = QtGui.QLabel()
        form.hint_label = QtGui.QLabel(
            translate(
                "frameforge",
                "Click a face near the corner the holes are placed from, or the vertex itself. Click again to change it.",
            )
        )
        for label in (form.face_label, form.vertex_label, form.hint_label):
            label.setWordWrap(True)
            reference.addWidget(label)
        form.button_next_corner = QtGui.QPushButton(translate("frameforge", "Next corner"))
        form.button_next_corner.clicked.connect(self._next_corner)
        reference.addWidget(form.button_next_corner)
        layout.addWidget(form.groupBox_reference)

        form.groupBox_holes = QtGui.QGroupBox(translate("frameforge", "Holes"))
        fields = QtGui.QFormLayout(form.groupBox_holes)
        obj = self.edited
        form.spin_offset_along = self._length_spin(
            -MAX_OFFSET, MAX_OFFSET, obj.OffsetAlong.Value if obj else DEFAULT_OFFSET
        )
        form.spin_offset_across = self._length_spin(
            -MAX_OFFSET, MAX_OFFSET, obj.OffsetAcross.Value if obj else DEFAULT_OFFSET
        )
        form.spin_diameter = self._length_spin(
            MIN_DIAMETER, MAX_OFFSET, obj.Diameter.Value if obj else DEFAULT_DIAMETER
        )
        form.spin_count = count_field(1, MAX_COUNT, obj.Count if obj else 1)
        form.spin_pitch = self._length_spin(MIN_DEPTH, MAX_OFFSET, obj.Pitch.Value if obj else DEFAULT_PITCH)
        form.combo_cut_type = QtGui.QComboBox()
        for cut_type in CUT_TYPES:
            form.combo_cut_type.addItem(translate("frameforge", CUT_TYPE_LABELS[cut_type]), cut_type)
        form.combo_cut_type.setCurrentIndex(
            max(form.combo_cut_type.findData(obj.CutType if obj else DEFAULT_CUT_TYPE), 0)
        )
        form.spin_depth = self._length_spin(MIN_DEPTH, MAX_DEPTH, obj.ExtrusionLength.Value if obj else MIN_DEPTH)
        for name, label, widget in (
            ("offset_along", translate("frameforge", "Offset along"), form.spin_offset_along),
            ("offset_across", translate("frameforge", "Offset across"), form.spin_offset_across),
            ("diameter", translate("frameforge", "Diameter"), form.spin_diameter),
            ("count", translate("frameforge", "Count"), form.spin_count),
            ("pitch", translate("frameforge", "Pitch"), form.spin_pitch),
            ("cut_type", translate("frameforge", "Cut type"), form.combo_cut_type),
            ("depth", translate("frameforge", "Depth"), form.spin_depth),
        ):
            setattr(form, f"label_{name}", QtGui.QLabel(label))
            fields.addRow(getattr(form, f"label_{name}"), widget)
        layout.addWidget(form.groupBox_holes)

        form.groupBox_preview = QtGui.QGroupBox(translate("frameforge", "Preview"))
        preview = QtGui.QVBoxLayout(form.groupBox_preview)
        form.cb_auto_update = QtGui.QCheckBox(translate("frameforge", "Update automatically"))
        form.cb_auto_update.setChecked(get_param_group().GetBool(self.auto_preview_param, self.auto_preview_default))
        form.status_label = QtGui.QLabel()
        preview.addWidget(form.cb_auto_update)
        preview.addWidget(form.status_label)
        layout.addWidget(form.groupBox_preview)

        form.warning_label = QtGui.QLabel()
        form.message_label = QtGui.QLabel()
        for label in (form.warning_label, form.message_label):
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()

        self.form = form
        if obj is not None:
            self._bind_fields()
        self._set_depth()
        self._enable_fields()
        for spin in (
            form.spin_offset_along,
            form.spin_offset_across,
            form.spin_diameter,
            form.spin_count,
            form.spin_pitch,
            form.spin_depth,
        ):
            spin.valueChanged.connect(self._changed)
        form.combo_cut_type.currentIndexChanged.connect(self._changed)
        form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)
        return form

    @staticmethod
    def _length_spin(minimum, maximum, value):
        return length_field(minimum, maximum, value)

    def _fields(self):
        """(property, field) of every field that takes an expression."""
        form = self.form
        return (
            ("OffsetAlong", form.spin_offset_along),
            ("OffsetAcross", form.spin_offset_across),
            ("Diameter", form.spin_diameter),
            ("Count", form.spin_count),
            ("Pitch", form.spin_pitch),
            ("ExtrusionLength", form.spin_depth),
        )

    def _bind_fields(self):
        """Bind the fields to the drill hole shown, for the expression editor (Fx)."""
        for prop, spin in self._fields():
            bind(spin, self.obj, prop)

    def _set_depth(self):
        """Keep the depth of a Distance cut, else show the thickness of the wall under the face."""
        if self.form.combo_cut_type.currentData() == "Distance" or self.face is None:
            return
        base, face = self.face
        try:
            depth = wall_thickness(base.Shape, base.Shape.getElement(face))
        except Exception:
            depth = None
        if depth:
            spin = self.form.spin_depth
            blocked = spin.blockSignals(True)
            try:
                spin.setValue(depth)
            finally:
                spin.blockSignals(blocked)

    def _enable_fields(self):
        self.form.spin_pitch.setEnabled(self.form.spin_count.value() > 1)
        self.form.spin_depth.setEnabled(self.form.combo_cut_type.currentData() == "Distance")

    @staticmethod
    def _values(obj):
        """(base, face, vertex, offsets, diameter, count, pitch, cut type, depth) of the drill hole ``obj``."""
        base, (face, *_) = obj.baseObject
        return (
            base,
            face,
            obj.ReferenceVertex,
            round(obj.OffsetAlong.Value, 9),
            round(obj.OffsetAcross.Value, 9),
            round(obj.Diameter.Value, 9),
            obj.Count,
            round(obj.Pitch.Value, 9),
            obj.CutType,
            round(obj.ExtrusionLength.Value, 9),
        )

    def _wanted(self):
        """What the shown drill hole must be recomputed for to match the panel; () without a face and a vertex."""
        if self.face is None or self.vertex is None:
            return ()
        form = self.form
        cut_type = form.combo_cut_type.currentData()
        return (
            *self.face,
            self.vertex,
            round(form.spin_offset_along.value(), 9),
            round(form.spin_offset_across.value(), 9),
            round(form.spin_diameter.value(), 9),
            form.spin_count.value(),
            round(form.spin_pitch.value(), 9),
            cut_type,
            round(form.spin_depth.value(), 9) if cut_type == "Distance" else None,
        )

    def _apply_to(self, obj):
        """Set the panel values on ``obj``; unchanged values are left alone, so not recomputed."""
        form = self.form
        base, face = self.face
        if obj.baseObject[0] != base or tuple(obj.baseObject[1]) != (face,):
            obj.baseObject = (base, [face])
        if obj.ReferenceVertex != self.vertex:
            obj.ReferenceVertex = self.vertex
        # An expression drives its property on its own: the field only shows its value.
        for prop, spin in (
            ("OffsetAlong", form.spin_offset_along),
            ("OffsetAcross", form.spin_offset_across),
            ("Diameter", form.spin_diameter),
            ("Pitch", form.spin_pitch),
        ):
            if expression_of(obj, prop) is None and _spin_changed(spin, getattr(obj, prop).Value):
                setattr(obj, prop, spin.value())
        if expression_of(obj, "Count") is None and obj.Count != form.spin_count.value():
            obj.Count = form.spin_count.value()
        cut_type = form.combo_cut_type.currentData()
        if obj.CutType != cut_type:
            obj.CutType = cut_type
        if (
            cut_type == "Distance"
            and expression_of(obj, "ExtrusionLength") is None
            and _spin_changed(form.spin_depth, obj.ExtrusionLength.Value)
        ):
            obj.ExtrusionLength = form.spin_depth.value()

    def _restore(self, obj, values):
        base, face, vertex, along, across, diameter, count, pitch, cut_type, depth = values
        if obj.baseObject[0] != base or tuple(obj.baseObject[1]) != (face,):
            obj.baseObject = (base, [face])
        if obj.ReferenceVertex != vertex:
            obj.ReferenceVertex = vertex
        for prop, value in (
            ("OffsetAlong", along),
            ("OffsetAcross", across),
            ("Diameter", diameter),
            ("Pitch", pitch),
            ("ExtrusionLength", depth),
        ):
            if abs(getattr(obj, prop).Value - value) > TOLERANCE:
                setattr(obj, prop, value)
        if obj.Count != count:
            obj.Count = count
        if obj.CutType != cut_type:
            obj.CutType = cut_type

    # Picks.

    def _add_items(self, selection):
        """Take the first usable face, then the first of its vertices, of the preselection; return the problems."""
        messages = []
        vertices = []
        for obj, subs in selection:
            problem = trimmed_body_problem(None, obj)
            if problem is not None:
                messages.append(problem)
                continue
            for sub in subs:
                if isinstance(_element(obj, sub), Part.Vertex):
                    vertices.append((obj, sub))
                    continue
                problem = face_problem(obj, sub)
                if problem is not None:
                    messages.append(problem)
                elif self.face is None:
                    self.face = (obj, sub)
                else:
                    messages.append(
                        translate("frameforge", "{}: {} is not used, a drill hole takes one face").format(
                            obj.Label, sub
                        )
                    )
        for obj, sub in vertices:
            problem = self._vertex_problem(obj, sub)
            if problem is not None:
                messages.append(problem)
            elif self.vertex is None:
                self.vertex = sub
            else:
                messages.append(
                    translate("frameforge", "{}: {} is not used, a drill hole takes one vertex").format(obj.Label, sub)
                )
        self._set_depth()
        return messages

    def _vertex_problem(self, obj, sub):
        """Why the vertex ``sub`` of ``obj`` cannot be the vertex of the face, or None when it can."""
        if self.face is None:
            return translate("frameforge", "Click a face first, then one of its vertices.")
        base, face = self.face
        if obj != base or not _on_face(base, face, sub):
            return translate("frameforge", "{}: {} is not a vertex of {}").format(obj.Label, sub, face)
        return None

    def _pick(self, obj, sub, point=None):
        """Take the face or vertex ``sub`` of ``obj``: (whether the reference changed, problems).

        A face clicked at the global ``point`` also takes its corner nearest to the click.
        """
        problem = trimmed_body_problem(None, obj)
        if problem is not None:
            return False, [problem]
        if isinstance(_element(obj, sub), Part.Vertex):
            problem = self._vertex_problem(obj, sub)
            if problem is not None:
                return False, [problem]
            changed = self.vertex != sub
            self.vertex = sub
            return changed, []
        # The shown drill hole, or one built on it, cannot be its own base.
        problem = face_problem(obj, sub) or trimmed_body_problem(self.obj, obj)
        if problem is not None:
            return False, [problem]
        corner = _nearest_corner(obj, sub, point) if point is not None else None
        if self.face == (obj, sub):
            changed = corner is not None and corner != self.vertex
            if changed:
                self.vertex = corner
            return changed, []
        if corner is not None:
            self.vertex = corner
        elif self.vertex is not None and not (self.face[0] == obj and _on_face(obj, sub, self.vertex)):
            self.vertex = None
        self.face = (obj, sub)
        self._set_depth()
        return True, []

    def _next_corner(self):
        """Take the corner of the face after the current one, the first one without a current one."""
        if self.face is None or not _in_document(self.face[0]):
            return
        corners = _face_corners(*self.face)
        if not corners:
            return
        index = corners.index(self.vertex) + 1 if self.vertex in corners else 0
        self.vertex = corners[index % len(corners)]
        self._show([])
        self._update_preview()

    def _on_base(self, obj, sub):
        """(object, element) a click on ``sub`` of ``obj`` stands for: the base of the shown drill hole, else itself."""
        if self.obj is None or obj != self.obj or not _in_document(obj) or not obj.baseObject:
            return obj, sub
        base = obj.baseObject[0]
        name = _base_element(base, _element(obj, sub))
        return (base, name) if name is not None else (obj, sub)

    # Display.

    def _show(self, messages):
        """Show the face, the vertex and ``messages``."""
        if self.face is not None and not _in_document(self.face[0]):
            self.face, self.vertex = None, None
        if self.face is None:
            text = translate("frameforge", "Click a planar face of a profile, a trimmed profile or a cutout.")
        else:
            obj, face = self.face
            text = f"{obj.Label} ({obj.Name}) {face}"
        self.form.face_label.setText(text)
        self.form.vertex_label.setText(self.vertex or translate("frameforge", "Click a vertex of the face."))
        self.form.button_next_corner.setEnabled(self.face is not None)
        self._draw_corner_marker()
        self._messages = list(messages)
        self._error = ""
        self._show_messages()
        self._show_status()

    def corner_marker(self):
        """Global point of the marker on the reference corner, or None when none is shown."""
        return self._corner_point

    def _draw_corner_marker(self):
        """Mark the reference corner over the 3D view in place of the previous mark."""
        self._remove_corner_marker()
        if self._closed or self.face is None or self.vertex is None:
            return
        vertex = _element(self.face[0], self.vertex)
        if not isinstance(vertex, Part.Vertex):
            return
        self._corner_point = _container_placement(self.face[0]).multVec(vertex.Point)
        scene = scene_graph(self.doc)
        if scene is None:
            return  # No 3D view (offscreen or another view type): the point is still kept.
        from pivy import coin

        try:
            index = Gui.getMarkerIndex("CIRCLE_FILLED", 9)
        except Exception:
            index = coin.SoMarkerSet.CIRCLE_FILLED_9_9
        # An annotation is drawn over the shapes, so the corner stays visible behind the preview.
        node = coin.SoAnnotation()
        color = coin.SoBaseColor()
        color.rgb.setValue(*CORNER_MARKER_COLOR)
        coordinates = coin.SoCoordinate3()
        point = self._corner_point
        coordinates.point.setValues(0, 1, [(point.x, point.y, point.z)])
        marker = coin.SoMarkerSet()
        marker.markerIndex.setValue(index)
        for child in (color, coordinates, marker):
            node.addChild(child)
        scene.addChild(node)
        self._corner_node = (scene, node)

    def _remove_corner_marker(self):
        remove_overlay(self._corner_node)
        self._corner_node = None
        self._corner_point = None

    def _show_messages(self):
        self.form.message_label.setText("\n".join(self._messages + ([self._error] if self._error else [])))

    def _show_status(self):
        if self._previewed != self._wanted():
            text = translate("frameforge", "Pending changes")
        elif self.obj is not None and _in_document(self.obj):
            text = translate("frameforge", "Preview updated")
        else:
            text = translate("frameforge", "No preview")
        self.form.status_label.setText(text)

    def _show_warning(self):
        """Show the ReferenceWarning of the shown drill hole, hidden when it is empty."""
        warning = self.obj.ReferenceWarning if self.obj is not None and _in_document(self.obj) else ""
        self.form.warning_label.setText(warning)
        self.form.warning_label.setVisible(bool(warning))

    # Preview.

    def _changed(self, *args):
        """A value changed: preview once changes pause."""
        if not self._active():
            return
        self._enable_fields()
        self._show_status()
        self._preview_timer.start()

    def _on_auto_update_toggled(self, checked):
        get_param_group(writable=True).SetBool(self.auto_preview_param, checked)
        self._update_preview()

    def _open_transaction(self):
        if not self._transaction_open:
            self.doc.openTransaction("Edit Drill Hole" if self.edited is not None else "Create Drill Hole")
            self._transaction_open = True

    def _update_preview(self, *args, force=False):
        """Make the shown drill hole match the panel when Update automatically is checked (or ``force``).

        Never recomputes while a recompute of the panel runs: an update asked for meanwhile follows it,
        so the preview ends at the last values.
        """
        if not self._active():
            return
        if self._recomputing:
            self._pending = True
            return
        self._recomputing = True
        try:
            while True:
                self._pending = False
                if force or self.form.cb_auto_update.isChecked():
                    self._preview(force)
                # OK pressed meanwhile previews the last values itself, Cancel drops them.
                if not (self._pending and self._active()) or self._deferred is not None:
                    break
        finally:
            self._recomputing = False
        if self._active():
            self._show_status()
        deferred, self._deferred = self._deferred, None
        if deferred is not None and self._active() and deferred():
            self._close_dialog()

    def _preview(self, force):
        """Recompute the shown drill hole for the panel values; without a face and a vertex the preview goes."""
        # Taken before the recompute: a value typed during it is not previewed yet.
        wanted = self._wanted()
        if not force and wanted == self._previewed and (not wanted or _in_document(self.obj)):
            return
        self._error = ""
        if not wanted:
            if self.edited is None:
                self._drop_preview()
            self._previewed = ()
            self._show_messages()
            self._show_warning()
            return
        self._open_transaction()
        try:
            if self.edited is None and (
                self.obj is None or not _in_document(self.obj) or self.obj.baseObject[0] != self.face[0]
            ):
                # A drill hole is named after its base: another base makes another preview.
                self._drop_preview()
                self._make_preview()
            self._apply_to(self.obj)
            self.doc.recompute()
            self._error = _failures([self.obj])
        except Exception as error:
            self._error = str(error)
        self._previewed = wanted
        self._show_messages()
        self._show_warning()

    def _make_preview(self):
        base, face = self.face
        self._visibility = [
            (body, body.ViewObject.Visibility)
            for body in _trim_chain(base)
            if getattr(body, "ViewObject", None) is not None
        ]
        self.obj = make_drill_hole((base, (face,)), self.vertex)
        place_in_container_of(self.obj, base)
        restore_expressions(self.obj, self._expressions)
        self._bind_fields()

    def _drop_preview(self):
        """Remove the preview and show the bodies it hid as they were before."""
        if self.edited is not None:
            return
        if self.obj is not None and _in_document(self.obj):
            self._expressions = expressions_of(self.obj, EXPRESSION_PROPERTIES)
            self.doc.removeObject(self.obj.Name)
        self.obj = None
        for body, visible in self._visibility:
            if _in_document(body):
                body.ViewObject.Visibility = visible
        self._visibility = []

    def _discard_preview(self):
        """Abort the preview transaction; a leftover preview (undo disabled) is removed by hand."""
        if self._transaction_open and _alive_document(self.doc):
            try:
                self.doc.abortTransaction()
            except Exception:
                pass
        self._transaction_open = False
        self._drop_preview()

    def _restore_edit(self):
        """Put the edited drill hole back as it was when the panel opened, even with undo disabled."""
        if self._transaction_open and _alive_document(self.doc):
            try:
                self.doc.abortTransaction()
            except Exception:
                pass
        self._transaction_open = False
        if not _in_document(self.edited):
            return
        restore_expressions(self.edited, self._edit_expressions)
        if self._values(self.edited) != self._edit_before:
            self._restore(self.edited, self._edit_before)
        self.doc.recompute()

    # Selection observer.

    def addSelection(self, doc, obj, sub, other):
        if not self._active():
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source is None:
            return
        changed, messages = self._pick(*self._on_base(source, sub), _click_point(other))
        self._show(messages)
        if changed:
            # Never recompute during FreeCAD's selection observer dispatch.
            QtCore.QTimer.singleShot(0, self._update_preview)

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, other):
        pass

    # Dialog.

    def _active(self):
        return not self._closed

    def _form_gone(self, *args):
        if not self._closed:
            self.closed()

    def closed(self):
        # FreeCAD can close the dialog without OK or Cancel (document closed, another dialog shown).
        if self._closed:
            return
        self.clean()
        if self.edited is None:
            self._discard_preview()
        else:
            self._restore_edit()

    def clean(self):
        self._closed = True
        self._preview_timer.stop()
        self._remove_corner_marker()
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _close_edit(self):
        if not _alive_document(self.doc):
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def _close_dialog(self):
        """Close the dialog after OK or Cancel ran on their own (pressed during a recompute)."""
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def _defer(self, button):
        """A recompute pumps Qt events: OK or Cancel pressed during it waits for it to end."""
        if not self._recomputing:
            return False
        self._deferred = button
        return True

    def reject(self):
        if self._defer(self.reject):
            return False
        self.clean()
        if self.edited is None:
            self._discard_preview()
        else:
            self._restore_edit()
            self._close_edit()
        return True

    def _missing(self):
        if self.face is None:
            return translate("frameforge", "Select a planar face of a profile, a trimmed profile or a cutout.")
        if self.vertex is None:
            return translate("frameforge", "Select a vertex of the face.")
        return ""

    def accept(self):
        if self._defer(self.accept):
            return False
        problem = self._missing()
        if problem:
            self._show([problem])
            return False
        # OK keeps the current values even when the preview is out of date or a change is pending.
        self._preview_timer.stop()
        self._update_preview(force=True)
        if self._error:
            # The panel stays open with the error, to change the values.
            return False
        if (
            self.edited is not None
            and self._values(self.edited) == self._edit_before
            and expressions_of(self.edited, EXPRESSION_PROPERTIES) == self._edit_expressions
        ):
            # Nothing changed in the end: no Undo step.
            self._restore_edit()
        else:
            self.doc.commitTransaction()
        self._transaction_open = False
        self.clean()
        if self.edited is not None:
            self._close_edit()
        return True


class DrillHoleCommand:
    """Drill Hole command: round holes on a planar face, placed from a vertex of that face."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "drill-hole.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_DrillHole", "Drill Hole"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_DrillHole",
                "<b>Drill Hole</b><br><br>Click a planar face of a profile, a trimmed profile or a cutout near the corner to measure from: round holes are drilled at the offsets from that corner, one or a row of them, with a diameter and a depth.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        show_panel(DrillHoleTaskPanel(_selected_items()))


add_command("MaxProFrame_DrillHole", DrillHoleCommand())

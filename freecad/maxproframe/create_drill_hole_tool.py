import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import get_profile_from_trimmedbody
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
    face_axes,
    make_drill_hole,
    offset_origin,
    pattern_count,
)
from freecad.maxproframe.expression_fields import (
    bind,
    count_field,
    expression_of,
    expressions_of,
    fit_width,
    length_field,
    length_text,
    restore_expressions,
)
from freecad.maxproframe.extruded_cutout import CUT_TYPES, wall_thickness
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Offsets of a new drill hole from its reference point, in mm: the hole starts on the picked point.
DEFAULT_OFFSET = 0.0
# Ranges of the panel fields: offsets and pitches in mm, diameter in mm, counts as the count properties allow.
MAX_OFFSET = 1e6
MIN_DIAMETER = 0.01
MAX_COUNT = 1000
# Longest pitch the Pattern fields are sized for, in mm: a longer one still fits, scrolled in its field.
LONGEST_PITCH = 9999.99
# Two values closer than this are the same.
TOLERANCE = 1e-9
# Color of the one filled marker: the point the offsets are measured from.
CORNER_MARKER_COLOR = (1.0, 0.6, 0.0)
# Color of the clickable markers on the corners, the edge middles and the center of the face.
PICK_MARKER_COLOR = (1.0, 1.0, 1.0)
# Size (pixels) of the corner markers and of the smaller edge middle and center markers.
CORNER_MARKER_SIZE = 11
MIDDLE_MARKER_SIZE = 9
# A click this close (screen pixels) to a marker picks it.
MARKER_HIT_RADIUS = 10.0


def marker_at(markers, position, project, radius=MARKER_HIT_RADIUS):
    """The marker of ``markers`` (name, global point) nearest to the screen ``position``, or None.

    ``project`` maps a global point to screen coordinates; a marker farther than ``radius`` is not hit.
    """
    best, best_distance = None, radius
    for marker in markers:
        try:
            x, y = project(marker[1])[:2]
        except Exception:
            continue
        distance = ((x - position[0]) ** 2 + (y - position[1]) ** 2) ** 0.5
        if distance <= best_distance:
            best, best_distance = marker, distance
    return best


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


def _face_corners(obj, face):
    """Names of the vertices of the face ``face`` of ``obj``, in the order of the face."""
    face_shape = _element(obj, face)
    if not isinstance(face_shape, Part.Face):
        return []
    return [name for name in (_base_element(obj, vertex) for vertex in face_shape.Vertexes) if name]


def _profile_axis(obj):
    """Direction of the profile ``obj`` is made from, in the coordinates of the shape of ``obj``, or None."""
    try:
        # Profiles are extruded along their local Z.
        return get_profile_from_trimmedbody(obj).Placement.Rotation.multVec(App.Vector(0, 0, 1))
    except Exception:
        return None


def _edge_name(obj, edge):
    """Name of the edge of ``obj`` that ``edge`` (an edge of one of its faces) is, or None."""
    for index, candidate in enumerate(obj.Shape.Edges, start=1):
        if candidate.isSame(edge):
            return f"Edge{index}"
    return None


def _face_middles(obj, face):
    """(edge name, middle, kind, names of its two ends) of every straight edge of the face ``face`` of ``obj``.

    The middle is in the coordinates of the shape. The kind is "along" for an edge parallel to the
    profile axis, else "across".
    """
    face_shape = _element(obj, face)
    if not isinstance(face_shape, Part.Face):
        return []
    axis = _profile_axis(obj)
    middles = []
    for edge in face_shape.Edges:
        if not isinstance(edge.Curve, (Part.Line, Part.LineSegment)) or len(edge.Vertexes) != 2:
            continue
        name = _edge_name(obj, edge)
        ends = tuple(_base_element(obj, vertex) for vertex in edge.Vertexes)
        if name is None or None in ends:
            continue
        start, end = (vertex.Point for vertex in edge.Vertexes)
        direction = end - start
        parallel = (
            axis is not None
            and direction.Length > TOLERANCE
            and direction.cross(axis).Length <= TOLERANCE**0.5 * direction.Length * axis.Length
        )
        middles.append((name, (start + end) * 0.5, "along" if parallel else "across", ends))
    return middles


def _face_center(obj, face):
    """Middle of the face ``face`` of ``obj`` along and across the profile, in the coordinates of the shape.

    The point a drill hole centered both ways measures from, whatever corner it keeps; the center of mass
    when the face has no direction along the profile. None when ``face`` is no face with vertices.
    """
    face_shape = _element(obj, face)
    if not isinstance(face_shape, Part.Face) or not face_shape.Vertexes:
        return None
    vertex = face_shape.Vertexes[0].Point
    try:
        along, across = face_axes(face_shape, _profile_axis(obj), vertex, True, True)
    except Exception:
        return face_shape.CenterOfMass
    return offset_origin(face_shape, vertex, along, across, True, True)


def _spin_changed(spin, stored):
    """Whether ``spin`` shows another value than ``stored``, as far as its decimals tell.

    A stored length finer than the field (4.7625 shown as 4.76) is kept until the field is changed.
    """
    # Rounded the way the field rounds it: Python's round(30.125, 2) is 30.12, the field shows 30.13.
    # Not through the field's textFromValue: FreeCAD's expression field gives every decimal there.
    shown = float(QtCore.QLocale.c().toString(stored, "f", spin.decimals()))
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


# Rows of the Pattern group: (field name, prefix of the count and pitch properties of the drill hole).
PATTERN_ROWS = (
    ("along_backward", "AlongBackward"),
    ("along_forward", "AlongForward"),
    ("across_backward", "AcrossBackward"),
    ("across_forward", "AcrossForward"),
)
PATTERN_PROPERTIES = tuple(f"{prop}{kind}" for _, prop in PATTERN_ROWS for kind in ("Count", "Pitch"))
# Properties of a drill hole its panel fields bind to, for expressions.
EXPRESSION_PROPERTIES = ("OffsetAlong", "OffsetAcross", "Diameter", *PATTERN_PROPERTIES, "ExtrusionLength")


class DrillHoleTaskPanel:
    """Face, vertex, offsets, diameter, pattern and depth of a drill hole, previewed live.

    The face shows nine clickable markers: its corners, the middles of its straight edges and its center.
    One click on a marker is the whole reference (L15): a corner measures the offsets from it; the middle
    of an edge along the profile measures the offset along from the middle of the face length, of an edge
    across the offset across from the middle of the face width; the center measures both from the middle
    of the face. A click on a planar face of a profile, a trimmed profile or a cutout picks the face and
    its marker nearest to the click; a click on one of its vertices picks that corner. Every other pick
    is explained. The point the offsets are measured from is the one filled marker. What FreeCAD selects
    under a clicked marker is no pick.
    A click on the drill hole being previewed or edited (it hides its base) stands for the face or
    vertex of its base under the click.

    Without ``edited`` the preview is the drill hole OK keeps, made once a face and a vertex are
    picked, inside one transaction that Cancel aborts. With ``edited`` (an existing drill hole) the
    edited hole itself is the preview, inside the edit transaction: OK keeps the changes in one Undo
    step, or none when nothing changed; Cancel puts the stored values back.

    The checkable Pattern group adds holes on each side of the point, along and across, and can leave
    out the hole at the point. Unchecked, the drill hole is one hole at the point: no count on any side
    and the hole at the point, while the fields keep their values for when it is checked again. It
    opens checked for a drill hole with a count or without the hole at the point.

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
        # Whether the offsets are measured from the middle of the face along and across the profile.
        self.center_along = False
        self.center_across = False
        self._closed = False
        self._transaction_open = False
        # (scene, node) of the markers on the face, and the global points of the reference corner and of
        # the point the offsets are measured from.
        self._corner_node = None
        self._corner_point = None
        self._origin_point = None
        # (view, callback) listening to mouse clicks on the markers, and whether a press hit one.
        self._mouse_callback = None
        self._marker_pressed = False
        # From a press on a marker until its release is processed: FreeCAD's selection is no pick then.
        self._marker_click = False
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
            self.center_along = bool(getattr(edited, "CenterAlong", False))
            self.center_across = bool(getattr(edited, "CenterAcross", False))
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
                "Click a circle on the face to place the holes from it: a corner, the middle of an edge or the center. "
                "A click on the face takes the nearest circle.",
            )
        )
        for label in (form.face_label, form.vertex_label, form.hint_label):
            label.setWordWrap(True)
            reference.addWidget(label)
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
        self._build_pattern(form, obj)
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
            ("pattern", None, form.groupBox_pattern),
            ("cut_type", translate("frameforge", "Cut type"), form.combo_cut_type),
            ("depth", translate("frameforge", "Depth"), form.spin_depth),
        ):
            if label is None:
                fields.addRow(widget)
                continue
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
        self._show_pattern_title()
        for spin in (
            form.spin_offset_along,
            form.spin_offset_across,
            form.spin_diameter,
            *self._pattern_spins(),
            form.spin_depth,
        ):
            spin.valueChanged.connect(self._changed)
        form.combo_cut_type.currentIndexChanged.connect(self._changed)
        form.cb_hole_at_point.toggled.connect(self._changed)
        form.groupBox_pattern.toggled.connect(self._on_pattern_toggled)
        form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)
        return form

    def _build_pattern(self, form, obj):
        """The checkable Pattern group: Hole at the point, then a count and a pitch for each side of each axis.

        The fields sit in ``form.pattern_fields``, hidden while the group is unchecked.
        """
        form.groupBox_pattern = QtGui.QGroupBox(translate("frameforge", "Pattern"))
        form.groupBox_pattern.setCheckable(True)
        form.pattern_fields = QtGui.QWidget()
        QtGui.QVBoxLayout(form.groupBox_pattern).addWidget(form.pattern_fields)
        grid = QtGui.QGridLayout(form.pattern_fields)
        grid.setContentsMargins(0, 0, 0, 0)
        # The fields keep their width: the labels take the room left.
        grid.setColumnStretch(0, 1)
        form.cb_hole_at_point = QtGui.QCheckBox(translate("frameforge", "Hole at the point"))
        form.cb_hole_at_point.setChecked(bool(obj.HoleAtPoint) if obj else True)
        grid.addWidget(form.cb_hole_at_point, 0, 0, 1, 3)
        form.label_pattern_count = QtGui.QLabel(translate("frameforge", "Holes per side"))
        form.label_pattern_pitch = QtGui.QLabel(translate("frameforge", "Pitch"))
        grid.addWidget(form.label_pattern_count, 1, 1)
        grid.addWidget(form.label_pattern_pitch, 1, 2)
        labels = (
            translate("frameforge", "Along ← backward"),
            translate("frameforge", "Along → forward"),
            translate("frameforge", "Across ← backward"),
            translate("frameforge", "Across → forward"),
        )
        for line, ((row, prop), label) in enumerate(zip(PATTERN_ROWS, labels), start=2):
            count = count_field(0, MAX_COUNT, getattr(obj, f"{prop}Count") if obj else 0)
            pitch = self._length_spin(
                MIN_DEPTH, MAX_OFFSET, getattr(obj, f"{prop}Pitch").Value if obj else DEFAULT_PITCH
            )
            fit_width(count, MAX_COUNT)
            fit_width(pitch, LONGEST_PITCH)
            setattr(form, f"label_{row}", QtGui.QLabel(label))
            setattr(form, f"spin_{row}_count", count)
            setattr(form, f"spin_{row}_pitch", pitch)
            for column, widget in enumerate((getattr(form, f"label_{row}"), count, pitch)):
                grid.addWidget(widget, line, column)
        checked = obj is not None and (
            not obj.HoleAtPoint or any(getattr(obj, f"{prop}Count") > 0 for _, prop in PATTERN_ROWS)
        )
        form.groupBox_pattern.setChecked(checked)
        form.pattern_fields.setHidden(not checked)

    def _pattern_spins(self):
        """The count and pitch fields of the Pattern group, row by row."""
        form = self.form
        return [getattr(form, f"spin_{row}_{kind}") for row, _ in PATTERN_ROWS for kind in ("count", "pitch")]

    def _pattern_sides(self):
        """(hole at the point, {side: (count, pitch)}) the fields of the Pattern group show, as drill_hole takes them."""
        form = self.form
        return form.cb_hole_at_point.isChecked(), {
            prop: (getattr(form, f"spin_{row}_count").value(), getattr(form, f"spin_{row}_pitch").value())
            for row, prop in PATTERN_ROWS
        }

    def _pattern_title(self):
        """Title of the Pattern group: "Pattern", followed by the total and the holes each side adds when checked.

        For example "Pattern: 9 holes, ← 3 × 20 mm | 5 × 30 mm →", the holes across after "across", and "no
        hole at the point" when that is unchecked. The total is the number of holes drilled ("1 hole").
        """
        form = self.form
        title = translate("frameforge", "Pattern")
        if not form.groupBox_pattern.isChecked():
            return title
        total = pattern_count(*self._pattern_sides())
        parts = [
            (translate("frameforge", "{} hole") if total == 1 else translate("frameforge", "{} holes")).format(total)
        ]
        for axis in ("along", "across"):
            sides = []
            for side, text in (
                ("backward", translate("frameforge", "← {} × {}")),
                ("forward", translate("frameforge", "{} × {} →")),
            ):
                count = getattr(form, f"spin_{axis}_{side}_count").value()
                if count > 0:
                    sides.append(text.format(count, length_text(getattr(form, f"spin_{axis}_{side}_pitch").value())))
            if sides:
                sides = " | ".join(sides)
                parts.append(sides if axis == "along" else translate("frameforge", "across {}").format(sides))
        if not form.cb_hole_at_point.isChecked():
            parts.append(translate("frameforge", "no hole at the point"))
        return translate("frameforge", "Pattern: {}").format(", ".join(parts))

    def _show_pattern_title(self):
        self.form.groupBox_pattern.setTitle(self._pattern_title())

    def _overlap_warnings(self):
        """One line for each axis whose holes overlap, while the Pattern group is checked.

        Two holes of a side overlap when its pitch is smaller than the diameter, and so do its first hole
        and the hole at the point. Without the hole at the point, the nearest holes on each side of the
        point overlap each other when closer than the diameter: the sum of the two pitches.
        """
        form = self.form
        if not form.groupBox_pattern.isChecked():
            return []
        diameter = form.spin_diameter.value()
        at_point, sides = self._pattern_sides()
        lines = []
        for prefix, pitch_text, pair_text in (
            (
                "Along",
                translate("frameforge", "The holes overlap: the pitch along ({}) is smaller than the diameter ({})."),
                translate(
                    "frameforge",
                    "The holes overlap: with no hole at the point, the holes along on each side of the point are {} "
                    "apart, less than the diameter ({}).",
                ),
            ),
            (
                "Across",
                translate("frameforge", "The holes overlap: the pitch across ({}) is smaller than the diameter ({})."),
                translate(
                    "frameforge",
                    "The holes overlap: with no hole at the point, the holes across on each side of the point are {} "
                    "apart, less than the diameter ({}).",
                ),
            ),
        ):
            backward, forward = sides[f"{prefix}Backward"], sides[f"{prefix}Forward"]
            pitches = [
                pitch
                for count, pitch in (backward, forward)
                if pitch < diameter - TOLERANCE and (count > 1 or (count == 1 and at_point))
            ]
            apart = backward[1] + forward[1]
            if pitches:
                lines.append(pitch_text.format(length_text(min(pitches)), length_text(diameter)))
            elif not at_point and backward[0] > 0 and forward[0] > 0 and apart < diameter - TOLERANCE:
                lines.append(pair_text.format(length_text(apart), length_text(diameter)))
        return lines

    def _on_pattern_toggled(self, checked):
        self.form.pattern_fields.setHidden(not checked)
        self._changed()

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
            *zip(PATTERN_PROPERTIES, self._pattern_spins()),
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
        form = self.form
        for row, _ in PATTERN_ROWS:
            getattr(form, f"spin_{row}_pitch").setEnabled(getattr(form, f"spin_{row}_count").value() > 0)
        self.form.spin_depth.setEnabled(self.form.combo_cut_type.currentData() == "Distance")

    @staticmethod
    def _values(obj):
        """(base, face, vertex, centers, offsets, diameter, cut type, depth, hole at the point, pattern) of ``obj``.

        The pattern is the (count, pitch) of each row of the Pattern group.
        """
        base, (face, *_) = obj.baseObject
        return (
            base,
            face,
            obj.ReferenceVertex,
            bool(getattr(obj, "CenterAlong", False)),
            bool(getattr(obj, "CenterAcross", False)),
            round(obj.OffsetAlong.Value, 9),
            round(obj.OffsetAcross.Value, 9),
            round(obj.Diameter.Value, 9),
            obj.CutType,
            round(obj.ExtrusionLength.Value, 9),
            bool(obj.HoleAtPoint),
            tuple(
                (getattr(obj, f"{prop}Count"), round(getattr(obj, f"{prop}Pitch").Value, 9)) for _, prop in PATTERN_ROWS
            ),
        )

    def _pattern_wanted(self):
        """(hole at the point, (count, pitch) of each row) the drill hole gets: one hole while unchecked."""
        form = self.form
        checked = form.groupBox_pattern.isChecked()
        return (
            form.cb_hole_at_point.isChecked() or not checked,
            tuple(
                (
                    getattr(form, f"spin_{row}_count").value() if checked else 0,
                    round(getattr(form, f"spin_{row}_pitch").value(), 9),
                )
                for row, _ in PATTERN_ROWS
            ),
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
            self.center_along,
            self.center_across,
            round(form.spin_offset_along.value(), 9),
            round(form.spin_offset_across.value(), 9),
            round(form.spin_diameter.value(), 9),
            cut_type,
            round(form.spin_depth.value(), 9) if cut_type == "Distance" else None,
            *self._pattern_wanted(),
        )

    def _apply_to(self, obj):
        """Set the panel values on ``obj``; unchanged values are left alone, so not recomputed."""
        form = self.form
        base, face = self.face
        if obj.baseObject[0] != base or tuple(obj.baseObject[1]) != (face,):
            obj.baseObject = (base, [face])
        if obj.ReferenceVertex != self.vertex:
            obj.ReferenceVertex = self.vertex
        for prop, value in (("CenterAlong", self.center_along), ("CenterAcross", self.center_across)):
            if getattr(obj, prop) != value:
                setattr(obj, prop, value)
        # An expression drives its property on its own: the field only shows its value.
        for prop, spin in (
            ("OffsetAlong", form.spin_offset_along),
            ("OffsetAcross", form.spin_offset_across),
            ("Diameter", form.spin_diameter),
            *((f"{prop}Pitch", getattr(form, f"spin_{row}_pitch")) for row, prop in PATTERN_ROWS),
        ):
            if expression_of(obj, prop) is None and _spin_changed(spin, getattr(obj, prop).Value):
                setattr(obj, prop, spin.value())
        hole_at_point, pattern = self._pattern_wanted()
        if obj.HoleAtPoint != hole_at_point:
            obj.HoleAtPoint = hole_at_point
        for (_, prop), (count, _) in zip(PATTERN_ROWS, pattern):
            if expression_of(obj, f"{prop}Count") is None and getattr(obj, f"{prop}Count") != count:
                setattr(obj, f"{prop}Count", count)
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
        base, face, vertex, center_along, center_across, along, across, diameter, cut_type, depth, at_point, pattern = (
            values
        )
        if obj.baseObject[0] != base or tuple(obj.baseObject[1]) != (face,):
            obj.baseObject = (base, [face])
        if obj.ReferenceVertex != vertex:
            obj.ReferenceVertex = vertex
        for prop, value in (("CenterAlong", center_along), ("CenterAcross", center_across)):
            if hasattr(obj, prop) and getattr(obj, prop) != value:
                setattr(obj, prop, value)
        for prop, value in (
            ("OffsetAlong", along),
            ("OffsetAcross", across),
            ("Diameter", diameter),
            *((f"{prop}Pitch", pitch) for (_, prop), (_, pitch) in zip(PATTERN_ROWS, pattern)),
            ("ExtrusionLength", depth),
        ):
            if abs(getattr(obj, prop).Value - value) > TOLERANCE:
                setattr(obj, prop, value)
        for (_, prop), (count, _) in zip(PATTERN_ROWS, pattern):
            if getattr(obj, f"{prop}Count") != count:
                setattr(obj, f"{prop}Count", count)
        if obj.HoleAtPoint != at_point:
            obj.HoleAtPoint = at_point
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

        A face clicked at the global ``point`` also takes its marker nearest to the click: a corner, the
        middle of an edge or the center. A face taken without a point keeps the vertex when it is on it.
        """
        problem = trimmed_body_problem(None, obj)
        if problem is not None:
            return False, [problem]
        if isinstance(_element(obj, sub), Part.Vertex):
            problem = self._vertex_problem(obj, sub)
            if problem is not None:
                return False, [problem]
            changed = self.vertex != sub or self._centered()
            self.vertex = sub
            self._measure_from_corner()
            return changed, []
        # The shown drill hole, or one built on it, cannot be its own base.
        problem = face_problem(obj, sub) or trimmed_body_problem(self.obj, obj)
        if problem is not None:
            return False, [problem]
        before = self._reference()
        if self.face != (obj, sub):
            if self.vertex is not None and not (self.face[0] == obj and _on_face(obj, sub, self.vertex)):
                self.vertex = None
            # The middles and the center belong to the face they were picked on.
            self._measure_from_corner()
            self.face = (obj, sub)
            self._set_depth()
        if point is not None:
            marker = min(self._markers(), key=lambda marker: marker[1].distanceToPoint(point), default=None)
            if marker is not None:
                self._take(marker)
        return self._reference() != before, []

    def _reference(self):
        return (self.face, self.vertex, self.center_along, self.center_across)

    def _centered(self):
        return self.center_along or self.center_across

    def _measure_from_corner(self):
        self.center_along = False
        self.center_across = False

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
            self._measure_from_corner()
        if self.face is None:
            text = translate("frameforge", "Click a planar face of a profile, a trimmed profile or a cutout.")
        else:
            obj, face = self.face
            text = f"{obj.Label} ({obj.Name}) {face}"
        self.form.face_label.setText(text)
        self.form.vertex_label.setText(self._vertex_text())
        self._draw_corner_marker()
        self._messages = list(messages)
        self._error = ""
        self._show_messages()
        self._show_status()

    def _vertex_text(self):
        """The point the offsets are measured from: the reference vertex, the middle of an edge or the face center."""
        if self.vertex is None:
            return translate("frameforge", "Click a vertex of the face.")
        if self.center_along and self.center_across:
            return translate("frameforge", "Center of the face")
        if self._centered():
            # The middle of the edge of that kind the reference corner is an end of.
            kind = "along" if self.center_along else "across"
            edge = next(
                (name for name, _, other, ends in _face_middles(*self.face) if other == kind and self.vertex in ends),
                None,
            )
            if edge is not None:
                return translate("frameforge", "Middle of {}").format(edge)
        return self.vertex

    def corner_marker(self):
        """Global point of the reference corner, or None when there is none on the face."""
        return self._corner_point

    def origin_marker(self):
        """Global point of the filled marker, the point the offsets are measured from, or None when none is shown.

        The reference corner; with a center on, the middle of the face along, across or both from it.
        """
        return self._origin_point

    def _markers(self):
        """(name, global point, kind, ends) of the markers of the picked face.

        The corners (kind "corner", no ends) come first, then the middles of the straight edges (kind
        "along" or "across", the names of the two ends of the edge), then the center of the face (named
        after the face, kind "center", the names of its corners).
        """
        if self._closed or self.face is None or not _in_document(self.face[0]):
            return []
        obj = self.face[0]
        placement = _container_placement(obj)
        markers = []
        for name in _face_corners(*self.face):
            vertex = _element(obj, name)
            if isinstance(vertex, Part.Vertex):
                markers.append((name, placement.multVec(vertex.Point), "corner", ()))
        for name, middle, kind, ends in _face_middles(*self.face):
            markers.append((name, placement.multVec(middle), kind, ends))
        corners = tuple(name for name, _, kind, _ in markers if kind == "corner")
        center = _face_center(*self.face)
        if corners and center is not None:
            markers.append((self.face[1], placement.multVec(center), "center", corners))
        return markers

    def reference_markers(self):
        """(name, global point) of the clickable markers: corners (VertexN), edge middles (EdgeN), center (FaceN)."""
        return [(name, point) for name, point, *_ in self._markers()]

    def marker_kind(self, name):
        """Kind of the marker ``name`` of the picked face (corner, along, across or center), None when it is none."""
        return next((kind for marker, _, kind, _ in self._markers() if marker == name), None)

    def highlighted_markers(self):
        """Global points of the filled markers: only the point the offsets are measured from, when shown."""
        return [self._origin_point] if self._origin_point is not None else []

    def _offset_origin(self):
        """Point the offsets are measured from, in the coordinates of the shape, as the drill hole places it.

        None without a reference corner on the face.
        """
        obj, face = self.face
        face_shape = _element(obj, face)
        vertex = _element(obj, self.vertex) if self.vertex is not None else None
        if not isinstance(face_shape, Part.Face) or not isinstance(vertex, Part.Vertex):
            return None
        axis = _profile_axis(obj)
        if not self._centered() or axis is None:
            return vertex.Point
        try:
            along, across = face_axes(face_shape, axis, vertex.Point, self.center_along, self.center_across)
        except Exception:
            return vertex.Point
        return offset_origin(face_shape, vertex.Point, along, across, self.center_along, self.center_across)

    def _take(self, marker):
        """Make ``marker`` (name, global point, kind, ends) the whole reference, whatever it was before.

        A corner measures the offsets from it. The middle of an edge along the profile centers them along,
        of any other straight edge across, the face center both ways. The reference corner is then the
        current one when it is an end of that edge (a corner of the face), else the first one: a centered
        direction does not depend on it, the other one goes into the face from that edge.
        """
        name, _, kind, ends = marker
        if kind == "corner":
            self.vertex = name
        elif self.vertex not in ends:
            self.vertex = ends[0]
        self.center_along = kind in ("along", "center")
        self.center_across = kind in ("across", "center")

    def pick_marker(self, name):
        """Take the marker ``name`` as the whole reference, as a click on it does (see _take)."""
        if not self._active():
            return False
        marker = next((marker for marker in self._markers() if marker[0] == name), None)
        if marker is None:
            return False
        before = self._reference()
        self._take(marker)
        changed = self._reference() != before
        self._show([])
        if changed:
            # Never recompute during the 3D view's event dispatch.
            QtCore.QTimer.singleShot(0, self._update_preview)
        return True

    def _draw_corner_marker(self):
        """Mark the corners and edge middles of the face over the 3D view, in place of the previous marks.

        The point the offsets are measured from is filled: the reference corner, an edge middle or the face
        center. The other markers, the reference corner too when a center is on, are open.
        """
        self._remove_corner_marker()
        if self._closed or self.face is None:
            return
        markers = self._markers()
        placement = _container_placement(self.face[0])
        vertex = _element(self.face[0], self.vertex) if self.vertex is not None else None
        if isinstance(vertex, Part.Vertex):
            self._corner_point = placement.multVec(vertex.Point)
        origin = self._offset_origin()
        if origin is not None:
            self._origin_point = placement.multVec(origin)
        scene = scene_graph(self.doc)
        if scene is None:
            return  # No 3D view (offscreen or another view type): the points are still kept.
        from pivy import coin

        # An annotation is drawn over the shapes, so the corners stay visible behind the preview.
        node = coin.SoAnnotation()
        # The marker at the origin is drawn once, filled.
        others = [
            (point, kind)
            for _, point, kind, _ in markers
            if self._origin_point is None or not point.isEqual(self._origin_point, REFERENCE_TOLERANCE)
        ]
        for points, rgb, style, size in (
            (
                [point for point, kind in others if kind == "corner"],
                PICK_MARKER_COLOR,
                "CIRCLE_LINE",
                CORNER_MARKER_SIZE,
            ),
            (
                [point for point, kind in others if kind != "corner"],
                PICK_MARKER_COLOR,
                "CIRCLE_LINE",
                MIDDLE_MARKER_SIZE,
            ),
            (
                self.highlighted_markers(),
                CORNER_MARKER_COLOR,
                "CIRCLE_FILLED",
                MIDDLE_MARKER_SIZE if self._centered() else CORNER_MARKER_SIZE,
            ),
        ):
            if points:
                self._add_markers(coin, node, points, rgb, style, size)
        scene.addChild(node)
        self._corner_node = (scene, node)
        self._listen_to_mouse()

    @staticmethod
    def _add_markers(coin, node, points, rgb, style, size):
        try:
            index = Gui.getMarkerIndex(style, size)
        except Exception:
            index = getattr(coin.SoMarkerSet, f"{style}_{size}_{size}")
        group = coin.SoSeparator()
        color = coin.SoBaseColor()
        color.rgb.setValue(*rgb)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(0, len(points), [(point.x, point.y, point.z) for point in points])
        marker = coin.SoMarkerSet()
        marker.markerIndex.setValue(index)
        for child in (color, coordinates, marker):
            group.addChild(child)
        node.addChild(group)

    def _remove_corner_marker(self):
        remove_overlay(self._corner_node)
        self._corner_node = None
        self._corner_point = None
        self._origin_point = None

    # Clicks on the markers.

    def _view(self):
        try:
            return Gui.getDocument(self.doc.Name).ActiveView
        except Exception:
            return None

    def _listen_to_mouse(self):
        """Listen to the mouse buttons of the 3D view, once, while the panel is open."""
        if self._mouse_callback is not None or self._closed:
            return
        view = self._view()
        if view is None or not hasattr(view, "addEventCallbackPivy"):
            return
        from pivy import coin

        try:
            callback = view.addEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), self._on_mouse_button)
        except Exception:
            return
        self._mouse_callback = (view, callback)

    def _stop_listening_to_mouse(self):
        if self._mouse_callback is None:
            return
        view, callback = self._mouse_callback
        self._mouse_callback = None
        try:
            from pivy import coin

            view.removeEventCallbackPivy(coin.SoMouseButtonEvent.getClassTypeId(), callback)
        except Exception:
            pass

    def _viewport_point(self, point):
        """Screen coordinates (pixels from the bottom left, as Coin events give them) of the global ``point``."""
        view = self._mouse_callback[0] if self._mouse_callback is not None else self._view()
        return view.getPointOnViewport(point)

    def _on_mouse_button(self, event_callback):
        """A left click on a marker picks it; what the 3D view selects under it meanwhile is no pick (addSelection)."""
        from pivy import coin

        event = event_callback.getEvent()
        if event.getButton() != coin.SoMouseButtonEvent.BUTTON1:
            return
        if event.getState() == coin.SoMouseButtonEvent.DOWN:
            marker = None
            if self._active():
                marker = marker_at(self.reference_markers(), event.getPosition().getValue(), self._viewport_point)
            self._marker_pressed = marker is not None
            self._marker_click = marker is not None
            if marker is not None:
                event_callback.setHandled()
                self.pick_marker(marker[0])
        elif self._marker_pressed:
            # The release of a click on a marker is not a click on the face under it.
            self._marker_pressed = False
            event_callback.setHandled()
            # setHandled does not keep FreeCAD from selecting under the marker: the click lasts until
            # the release is processed.
            QtCore.QTimer.singleShot(0, self._end_marker_click)

    def _end_marker_click(self):
        self._marker_click = False

    def _clear_selection(self):
        if self._active():
            Gui.Selection.clearSelection()

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
        """Show the ReferenceWarning of the shown drill hole, then the overlapping holes; hidden when empty."""
        reference = self.obj.ReferenceWarning if self.obj is not None and _in_document(self.obj) else ""
        warning = "\n".join(([reference] if reference else []) + self._overlap_warnings())
        self.form.warning_label.setText(warning)
        self.form.warning_label.setVisible(bool(warning))

    # Preview.

    def _changed(self, *args):
        """A value changed: preview once changes pause."""
        if not self._active():
            return
        self._enable_fields()
        self._show_pattern_title()
        self._show_warning()
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
        if self._marker_click:
            # FreeCAD selects what lies under a clicked marker: not a pick, and not left selected.
            # Never change the selection during FreeCAD's selection observer dispatch.
            QtCore.QTimer.singleShot(0, self._clear_selection)
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
        self._marker_pressed = self._marker_click = False
        self._remove_corner_marker()
        self._stop_listening_to_mouse()
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
                "<b>Drill Hole</b><br><br>Click a planar face of a profile, a trimmed profile or a cutout, then one of its nine circles to measure from: a corner, the middle of an edge or the center. Round holes are drilled at the offsets from that point: one, or a pattern on both sides of it along and across the profile, with a diameter and a depth.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        show_panel(DrillHoleTaskPanel(_selected_items()))


add_command("MaxProFrame_DrillHole", DrillHoleCommand())

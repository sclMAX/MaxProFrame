"""Folded miter commands: Folded Bar (create and edit, previewed live) and Unfold Bar.

See odd/tasks/folded-miter.md, T6, and odd/tasks/folded-corners.md, T4. The panel lists the corners of the bar in
chain order, corner 1 at its start and the open corner of a closed frame last (S1). The selected corners show in the
3D view and fill the Corner fields with their outer radius, clearance, key, key diameter, K-factor and joint (Miter or
Stepped, with the step depth and flip of a Stepped one; odd/tasks/stepped-corners.md, S6): a field whose value differs
between them shows it is mixed, and a value typed goes to every selected corner (S2, S3). The open corner of a closed
frame has its own joint, step and clearance, the ones of the bar's ends there; its other fields are the first
corner's, disabled while it is selected. With one corner selected, once its Folded Corner object exists, the number
fields take expressions bound to it (S9). Remove
takes off the end tube of the first or last corner of an open bar, or opens a closed frame at the selected corner
(S4). A new corner starts with the values last set in the panel, remembered in the MaxProFrame parameters on OK (S5).
The selected corners of the preview are drawn over the 3D view, each as the part of the bar around its vertex, in the
selection color (S13).
A value typed in a corner field applies once the field is done (Enter, Tab or leaving it); the arrows and the wheel at
once. While the preview recomputes, FreeCAD's progress bar runs the keys and clicks of the panel: they wait for the
recompute to end, as OCC booleans run inside its own would wait forever for its threads (S15).
The wall thickness and the material are the profile's, shown read-only (S7). Whatever keeps the chain from folding is
shown and keeps OK disabled: the chain messages, an own miter at a folded corner (S12) and the unfold messages of the
corners (S9, S15).

Like Create Miter Ends (S22, T9), the command opens the panel at once, with the selected pieces if any, and the panel
takes the pieces clicked while it is open: a click adds one at the end of the bar, Ctrl+click or deselecting drops it.
"""

import math
import os
from collections import namedtuple
from dataclasses import replace

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe._utils import is_foldedbar
from freecad.maxproframe.create_end_miter_tool import (
    GAP_DELAY_MS,
    _alive,
    _alive_document,
    _built_on,
    _ctrl_held,
    _failures,
    remove_overlay,
    scene_graph,
)
from freecad.maxproframe.create_profiles_tool import _MixedPresentation
from freecad.maxproframe.expression_fields import (
    bind,
    expression_of,
    expressions_of,
    length_field,
    length_text,
    restore_expressions,
    unbind,
)
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.folded_bar import (
    bar_tips,
    make_folded_bar,
    make_unfolded_bar,
    nearest_piece,
    open_corner,
    pick_point,
    set_segments,
    update_corners,
)
from freecad.maxproframe.folded_chain import (
    ChainError,
    base_profile,
    build_chain,
    cut_at_fold_message,
    cuts_at_folds,
    section_offset,
)
from freecad.maxproframe.folded_corner import SETTINGS_PROPERTIES, corner_key, corner_settings, make_folded_corner
from freecad.maxproframe.profile_pattern import container_placement, newest_piece, placed
from freecad.maxproframe.qt_lifetime import invalidate_wrapper_on_destroy, is_alive, keep_alive_until_destroyed
from freecad.maxproframe.unfolded_geometry import JOINTS, MITER, STEPPED, CornerSettings, UnfoldError, check_settings

# Remembered state of the panel's "Update automatically" check box.
AUTO_PREVIEW_PARAM = "Folded Bar Auto Preview"
# Largest radius, clearance or key size the fields take (mm).
MAX_SIZE = 1000.0
# Corner object properties the panel sets; of the bar it sets Segments and Corners.
PROPERTIES = (
    "PieceA",
    "PieceB",
    "OuterRadius",
    "Clearance",
    "Key",
    "KeyDiameter",
    "KFactor",
    "Joint",
    "StepDepth",
    "StepFlip",
    "Open",
)
# Corner object properties the number fields bind to, for the expression editor (S9).
EXPRESSION_PROPERTIES = ("OuterRadius", "Clearance", "KeyDiameter", "KFactor", "StepDepth")
# The number fields of the Corner group: (field, CornerSettings field, corner object property).
NUMBER_FIELDS = (
    ("spin_outer_radius", "outer_radius", "OuterRadius"),
    ("spin_clearance", "clearance", "Clearance"),
    ("spin_key_diameter", "key_diameter", "KeyDiameter"),
    ("spin_k_factor", "k_factor", "KFactor"),
    ("spin_step_depth", "step_depth", "StepDepth"),
)
# The CornerSettings fields the open corner of a closed frame has of its own, the ones of the bar's ends there
# (stepped-corners S4, S6); its other fields are the first corner's.
OPEN_FIELDS = ("clearance", "joint", "step_depth", "step_flip")
# CornerSettings field -> corner object property.
PROPERTY_OF = {field: prop for prop, field in SETTINGS_PROPERTIES.items()}
# The values last set in the panel, given to the next corner (S5): (parameter, kind, CornerSettings field).
LAST_VALUE_PARAMS = (
    ("Folded Corner Outer Radius", "Float", "outer_radius"),
    ("Folded Corner Clearance", "Float", "clearance"),
    ("Folded Corner Key", "Bool", "key"),
    ("Folded Corner Key Diameter", "Float", "key_diameter"),
    ("Folded Corner K-Factor", "Float", "k_factor"),
    ("Folded Corner Joint", "String", "joint"),
    ("Folded Corner Step Depth", "Float", "step_depth"),
    ("Folded Corner Step Flip", "Bool", "step_flip"),
)
# A corner before any value was ever set: outer radius 10 mm, clearance 0.5 mm, the key of default size, automatic K,
# a Miter joint (with an automatic step, not flipped, once Stepped).
FIRST_VALUES = CornerSettings(
    outer_radius=10.0,
    clearance=0.5,
    key=True,
    key_diameter=0.0,
    k_factor=0.0,
    joint=MITER,
    step_depth=0.0,
    step_flip=False,
)
# The selected corners drawn over the 3D view (S13): room added around a corner (mm), transparency of the faces, width
# of the edges and tolerance of the drawn faces and edges (mm).
OVERLAY_MARGIN = 0.5
OVERLAY_TRANSPARENCY = 0.5
OVERLAY_LINE_WIDTH = 2.0
OVERLAY_TOLERANCE = 0.1
# FreeCAD's selection color: its preference, else its default (packed RGBA).
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
DEFAULT_SELECTION_COLOR = 0x1CAD1C00
VALUE_TOLERANCE = 1e-9

# A row of the corner list: the corner by the names of its two profiles, the indexes of the chain segments meeting
# there (in chain order) and whether it is the open corner of a closed frame.
Row = namedtuple("Row", "key before after open")


def last_values():
    """The values a new corner starts with: the ones last set, else ``FIRST_VALUES``."""
    param = get_param_group()
    values = {}
    for name, kind, field in LAST_VALUE_PARAMS:
        values[field] = getattr(param, f"Get{kind}")(name, getattr(FIRST_VALUES, field))
    if values["joint"] not in JOINTS:
        values["joint"] = FIRST_VALUES.joint
    return CornerSettings(**values)


def remember_values(settings):
    """Keep ``settings`` as the values the next corner starts with, between sessions."""
    param = get_param_group(writable=True)
    for name, kind, field in LAST_VALUE_PARAMS:
        getattr(param, f"Set{kind}")(name, _setting(field, getattr(settings, field)))


def _setting(field, value):
    """``value`` (a property value or a plain one) as the ``CornerSettings`` ``field`` takes it."""
    value = value.Value if hasattr(value, "Value") else value
    if field in ("key", "step_flip"):
        return bool(value)
    if field == "joint":
        return str(value)
    return float(value)


def _plain(value):
    """A property value as the panel compares it."""
    if hasattr(value, "Name") and hasattr(value, "Document"):
        return value.Name
    if hasattr(value, "Value"):
        return round(value.Value, 9)
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, (list, tuple)):
        return tuple(item.Name if hasattr(item, "Name") else _plain(item) for item in value)
    return value


def _corner_key(chain, corner):
    """A corner by the two profiles meeting there, whatever the order of the chain."""
    return frozenset(chain.segments[index].profile.Name for index in (corner.before, corner.after))


def _profile_name(obj):
    """Name of the profile ``obj`` is made from, or None."""
    profile = base_profile(obj) if obj is not None and _alive(obj) else None
    return profile.Name if profile is not None else None


def _snapshot(bar):
    """What the panel may change on ``bar``: its Segments, BaseTubes and Corners, and the PROPERTIES and the
    expressions of each corner object; ``Tips``, the pieces it folds (``bar_tips``), is not compared."""
    corners = [obj for obj in bar.Corners if obj is not None]
    return {
        "Segments": list(bar.Segments),
        "BaseTubes": list(getattr(bar, "BaseTubes", [])),
        "Tips": bar_tips(bar),
        "Corners": [obj.Name for obj in corners],
        "values": {obj.Name: {prop: getattr(obj, prop) for prop in PROPERTIES} for obj in corners},
        "expressions": {obj.Name: expressions_of(obj, EXPRESSION_PROPERTIES) for obj in corners},
    }


def _plain_snapshot(snapshot):
    return (
        _plain(snapshot["Segments"]),
        _plain(snapshot["BaseTubes"]),
        tuple(snapshot["Corners"]),
        tuple(
            (name, tuple((prop, _plain(value)) for prop, value in values.items()))
            for name, values in sorted(snapshot["values"].items())
        ),
        tuple((name, tuple(sorted(found.items()))) for name, found in sorted(snapshot["expressions"].items())),
    )


def selection_color():
    """FreeCAD's selection color, (red, green, blue) from 0 to 1."""
    packed = App.ParamGet(VIEW_PARAMS).GetUnsigned("SelectionColor", DEFAULT_SELECTION_COLOR)
    return tuple(((packed >> shift) & 0xFF) / 255.0 for shift in (24, 16, 8))


def _axes_meet(first, second):
    """Where the axes of the tubes of the segments ``first`` and ``second`` meet, midway between them when skew."""
    p1, d1 = first.start + section_offset(first), first.direction
    p2, d2 = second.start + section_offset(second), second.direction
    w = p1 - p2
    b, d, e = d1.dot(d2), d1.dot(w), d2.dot(w)
    denominator = 1.0 - b * b
    if denominator < 1e-12:
        # In line: the end of the first one.
        return first.end + section_offset(first)
    t = (b * e - d) / denominator
    s = (e - b * d) / denominator
    return (p1 + d1 * t + p2 + d2 * s) * 0.5


def corner_box(chain, row, radius):
    """The box around the corner ``row`` of ``chain`` folded with the outer ``radius`` (0 for the open corner): the
    whole bend, and past it a stretch of each tube as long as the tube is deep (S13). Global coordinates."""
    first, second = chain.segments[row.before], chain.segments[row.after]
    size = max(first.width, first.height)
    turn = min(math.degrees(first.direction.getAngle(second.direction)), 170.0)
    half = (radius + size / 2) * math.tan(math.radians(turn) / 2) + size + OVERLAY_MARGIN
    # Square to the tube before the corner: square to both at a right angle.
    x = App.Vector(first.direction).normalize()
    z = x.cross(second.direction)
    if z.Length < 1e-9:
        z = x.cross(App.Vector(0, 0, 1)) if abs(x.z) < 0.9 else x.cross(App.Vector(1, 0, 0))
    z.normalize()
    y = z.cross(x)
    c = _axes_meet(first, second)
    matrix = App.Matrix(x.x, y.x, z.x, c.x, x.y, y.y, z.y, c.y, x.z, y.z, z.z, c.z, 0, 0, 0, 1)
    box = Part.makeBox(2 * half, 2 * half, 2 * half, App.Vector(-half, -half, -half))
    box.Placement = App.Placement(matrix)
    return box


def _overlay_group(shape, color):
    """A Coin group drawing ``shape``: its faces in ``color``, semitransparent, and its edges."""
    from pivy import coin

    group = coin.SoSeparator()
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*color)
    material.emissiveColor.setValue(*(value * 0.5 for value in color))
    material.transparency.setValue(OVERLAY_TRANSPARENCY)
    points, triangles = shape.tessellate(OVERLAY_TOLERANCE)
    coordinates = coin.SoCoordinate3()
    coordinates.point.setValues(0, len(points), [(point.x, point.y, point.z) for point in points])
    faces = coin.SoIndexedFaceSet()
    indexes = [index for triangle in triangles for index in (*triangle, -1)]
    faces.coordIndex.setValues(0, len(indexes), indexes)
    for child in (material, coordinates, faces):
        group.addChild(child)
    lines = []
    for edge in shape.Edges:
        try:
            line = edge.discretize(Deflection=OVERLAY_TOLERANCE)
        except Exception:
            continue
        if len(line) > 1:
            lines.append(line)
    if lines:
        edges = coin.SoSeparator()
        base_color = coin.SoBaseColor()
        base_color.rgb.setValue(*color)
        style = coin.SoDrawStyle()
        style.lineWidth.setValue(OVERLAY_LINE_WIDTH)
        edge_points = coin.SoCoordinate3()
        flat = [(point.x, point.y, point.z) for line in lines for point in line]
        edge_points.point.setValues(0, len(flat), flat)
        line_set = coin.SoLineSet()
        line_set.numVertices.setValues(0, len(lines), [len(line) for line in lines])
        for child in (base_color, style, edge_points, line_set):
            edges.addChild(child)
        group.addChild(edges)
    return group


def show_panel(panel):
    Gui.Control.showDialog(panel)


class _RecomputeEnd:
    """Document observer: once a document ends a recompute, ``callback`` runs from the event loop, outside FreeCAD's
    observer dispatch. Any document: a recompute of another open one pumps Qt events all the same."""

    def __init__(self, callback):
        self.callback = callback

    def slotRecomputedDocument(self, doc):
        QtCore.QTimer.singleShot(0, self.callback)


class _FinishOnEnter(QtCore.QObject):
    """Enter in a corner field finishes the field and nothing else (S15).

    The spin box applies the value and leaves the key unhandled; FreeCAD's task view, an ancestor of the form, would
    then take it as OK and close the panel. The form stops the key on its way up.
    """

    KEYS = (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)

    def __init__(self, form, fields):
        super().__init__(form)
        self.fields = fields
        form.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.KeyPress and event.key() in self.KEYS:
            focused = QtWidgets.QApplication.focusWidget()
            for field in self.fields:
                if is_alive(field) and focused in (field, field.lineEdit()):
                    event.accept()
                    return True
        return False


class FoldedBarTaskPanel:
    """The corners of a Folded Bar, each with its outer radius, clearance, key, K-factor and joint, previewed.

    Without ``edited`` the preview is the Folded Bar OK keeps, made from the pieces ``selection`` (the first one
    starts the bar) inside one transaction that Cancel aborts. With ``edited`` the bar itself is the preview: OK keeps
    the changes in one Undo step, or none when nothing changed; Cancel puts it back.

    As a selection observer (added by the command, as End Miter's) the new bar takes the pieces clicked while the
    panel is open; an edited bar keeps its pieces, as an edited End Miter does, though Remove may take off an end
    tube or open a closed frame at another corner.
    """

    auto_preview_param = AUTO_PREVIEW_PARAM
    auto_preview_default = True

    def __init__(self, selection=(), edited=None):
        self.edited = edited
        self.obj = edited
        # (piece, Visibility) of what the preview hides: Cancel shows it again, undo or not.
        self._visibility = []
        # The pieces the bar folds: a tube it falls back to too (a piece removed, not yet recomputed).
        self.selection = bar_tips(edited) if edited is not None else []
        if edited is None:
            for obj in selection:
                self.add_member(obj)
        self.doc = edited.Document if edited is not None else (
            self.selection[0].Document if self.selection else App.ActiveDocument
        )  # fmt: skip
        self._closed = False
        # Selection changes the panel makes itself are not the user's clicks.
        self._syncing = False
        self._transaction_open = False
        self._recomputing = False
        # A recompute the panel did not start runs: the observer told when it ends, and whether a look is due at it
        # in a moment anyway, to run what waits for it.
        self._recompute_end = None
        self._resuming = False
        # What the panel was asked to do while the preview recomputed, run once it returns (S15).
        self._waiting = []
        self._deferred = None
        self._previewed = None
        self._problems = []
        self._error = ""
        self._chain = None
        # The pair of pieces build_chain opened the chain at, None where it chose the corner itself.
        self._chain_pair = None
        self._ok_button = None
        # The pair of pieces where a closed frame stays open (S4), one of them the first piece; None: by default.
        self._open_pair = None
        # The values of each corner, by the names of its two profiles: a corner met first gets the values last set.
        self._values = {}
        # The values of the open corner, by its key, once it has its own (loaded with the bar or set in the panel):
        # until then it takes the first corner's (stepped-corners S6).
        self._open_values = {}
        self._last = self._loaded = last_values()
        self._rows = []
        # The expressions of the corners of a dropped preview, by corner: the next preview takes them back.
        self._kept_expressions = {}
        # The fields are being filled by the panel, not typed.
        self._filling = False
        self._mixed_edits = set()
        # (Name, ID) of the corner object the fields are bound to; "" before any binding.
        self._bound = ""
        self._highlighted = False
        # (scene, node) of the selected corners drawn over the 3D view (S13), and the shapes drawn, by what they are.
        self._overlay = None
        self._corner_shapes = {}
        if edited is not None:
            self._before = _snapshot(edited)
            opened = open_corner(edited)
            if opened is not None:
                self._open_pair = [opened.PieceA, opened.PieceB]
            for obj in edited.Corners:
                key = corner_key(obj) if obj is not None else None
                if key is not None:
                    (self._open_values if obj.Open else self._values).setdefault(key, corner_settings(obj))
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(GAP_DELAY_MS)
        self._timer.timeout.connect(self.update_preview)
        self.form = keep_alive_until_destroyed(self._build_form())
        self.form.destroyed.connect(self._form_gone)
        self._connect()
        self._refresh()
        if edited is not None:
            self._previewed = self._wanted()
            # The expression editor (Fx) changes the corner objects at once: inside the edit transaction.
            self._open_transaction()
        self.update_preview()

    # Form.

    def _build_form(self):
        form = QtWidgets.QWidget()
        form.setWindowTitle(translate("MaxProFrame", "Folded Bar"))
        layout = QtWidgets.QVBoxLayout(form)

        form.groupBox_corners = QtWidgets.QGroupBox(translate("MaxProFrame", "Corners"))
        corners = QtWidgets.QFormLayout(form.groupBox_corners)
        form.label_tube = QtWidgets.QLabel()
        form.label_tube.setToolTip(
            translate("MaxProFrame", "Material and wall thickness of the tubes, from their profile")
        )
        corners.addRow(translate("MaxProFrame", "Tube"), form.label_tube)
        form.corner_list = QtWidgets.QListWidget()
        form.corner_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        form.corner_list.setMaximumHeight(120)
        form.corner_list.setToolTip(
            translate(
                "MaxProFrame",
                "Corners from the start of the bar: click, Ctrl+click or Shift+click to select the ones to edit",
            )
        )
        corners.addRow(form.corner_list)
        form.button_remove = QtWidgets.QPushButton(translate("MaxProFrame", "Remove"))
        form.button_remove.setToolTip(
            translate(
                "MaxProFrame",
                "Open bar: take off the end tube of the first or last corner selected. Closed frame: open the frame "
                "at the selected corner.",
            )
        )
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(form.button_remove)
        corners.addRow(buttons)
        layout.addWidget(form.groupBox_corners)

        form.groupBox_corner = QtWidgets.QGroupBox(translate("MaxProFrame", "Corner"))
        corner = QtWidgets.QFormLayout(form.groupBox_corner)
        form.spin_outer_radius = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_outer_radius.setToolTip(
            translate("MaxProFrame", "Radius seen outside the bend: the inside radius is it less the wall thickness")
        )
        corner.addRow(translate("MaxProFrame", "Outer radius"), form.spin_outer_radius)
        form.spin_clearance = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_clearance.setToolTip(
            translate("MaxProFrame", "Gap between the notch flanks and around the key, half on each side")
        )
        corner.addRow(translate("MaxProFrame", "Clearance"), form.spin_clearance)
        form.cb_key = QtWidgets.QCheckBox(translate("MaxProFrame", "Interlocking key"))
        corner.addRow(form.cb_key)
        form.spin_key_diameter = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_key_diameter.setSpecialValueText(translate("MaxProFrame", "Default"))
        form.spin_key_diameter.setToolTip(
            translate(
                "MaxProFrame",
                "Diameter of the key, a half circle on the miter line; Default: a quarter of the tube depth across "
                "the bent wall",
            )
        )
        corner.addRow(translate("MaxProFrame", "Key diameter"), form.spin_key_diameter)
        form.spin_k_factor = length_field(0.0, 1.0, 0.0, decimals=3)
        form.spin_k_factor.setSuffix("")
        form.spin_k_factor.setSingleStep(0.01)
        form.spin_k_factor.setSpecialValueText(translate("MaxProFrame", "Automatic"))
        form.spin_k_factor.setToolTip(
            translate(
                "MaxProFrame",
                "Where the neutral axis sits in the wall, 0 < K <= 1; Automatic: from DIN 6935, by the inside radius "
                "and the wall thickness",
            )
        )
        corner.addRow(translate("MaxProFrame", "K-factor"), form.spin_k_factor)
        # The joint (stepped-corners S1, S5, S6): the stored values stay Miter and Stepped, whatever the language.
        form.combo_joint = QtWidgets.QComboBox()
        form.combo_joint.addItem(translate("MaxProFrame", "Miter"), MITER)
        form.combo_joint.addItem(translate("MaxProFrame", "Stepped"), STEPPED)
        form.combo_joint.setToolTip(
            translate(
                "MaxProFrame",
                "How the inner wall is cut: Miter, at half the bend angle (a bevel cut); Stepped, an interlock of "
                "straight cuts only, for any tube laser",
            )
        )
        corner.addRow(translate("MaxProFrame", "Joint"), form.combo_joint)
        form.spin_step_depth = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_step_depth.setSpecialValueText(translate("MaxProFrame", "Automatic"))
        form.spin_step_depth.setToolTip(
            translate(
                "MaxProFrame",
                "Depth of the step of a Stepped joint across the bent wall; Automatic: the larger of the wall "
                "thickness and the outer corner radius of the tube",
            )
        )
        corner.addRow(translate("MaxProFrame", "Step depth"), form.spin_step_depth)
        form.cb_step_flip = QtWidgets.QCheckBox(translate("MaxProFrame", "Flip step"))
        form.cb_step_flip.setToolTip(
            translate("MaxProFrame", "Swap the tubes of a Stepped joint: the other one covers the step")
        )
        corner.addRow(form.cb_step_flip)
        layout.addWidget(form.groupBox_corner)
        # A field whose value differs between the selected corners says so, as in Create Profile.
        self._mixed = {name: _MixedPresentation(getattr(form, name)) for name, _, _ in NUMBER_FIELDS}
        self._mixed["combo_joint"] = _MixedPresentation(form.combo_joint, combo=True)
        for name, _, _ in NUMBER_FIELDS:
            # A value typed applies once the field is done, not at every key (S15).
            getattr(form, name).setKeyboardTracking(False)
        form.finish_on_enter = _FinishOnEnter(form, [getattr(form, name) for name, _, _ in NUMBER_FIELDS])

        form.groupBox_preview = QtWidgets.QGroupBox(translate("MaxProFrame", "Preview"))
        preview = QtWidgets.QVBoxLayout(form.groupBox_preview)
        form.cb_auto_update = QtWidgets.QCheckBox(translate("MaxProFrame", "Update automatically"))
        form.cb_auto_update.setChecked(get_param_group().GetBool(self.auto_preview_param, self.auto_preview_default))
        form.status_label = QtWidgets.QLabel()
        preview.addWidget(form.cb_auto_update)
        preview.addWidget(form.status_label)
        layout.addWidget(form.groupBox_preview)

        form.message_label = QtWidgets.QLabel()
        form.message_label.setWordWrap(True)
        layout.addWidget(form.message_label)
        return form

    def _connect(self):
        form = self.form
        form.corner_list.itemSelectionChanged.connect(self._corner_selection_changed)
        form.button_remove.clicked.connect(self.remove_corners)
        for name, field, _ in NUMBER_FIELDS:
            spin = getattr(form, name)
            spin.valueChanged.connect(lambda value, field=field: self._field_changed(field, value))
            # A value typed in a mixed field goes to every corner, even the value it hides.
            spin.lineEdit().textEdited.connect(lambda _text, name=name: self._mixed_edits.add(name))
            spin.editingFinished.connect(lambda name=name, field=field: self._finish_mixed(name, field))
        form.cb_key.toggled.connect(lambda checked: self._field_changed("key", bool(checked)))
        form.combo_joint.currentIndexChanged.connect(self._joint_changed)
        # The joint shown under Mixed values chosen again: no index change, it goes to every corner all the same.
        form.combo_joint.activated.connect(self._joint_activated)
        form.cb_step_flip.toggled.connect(lambda checked: self._field_changed("step_flip", bool(checked)))
        form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)

    # Corner list.

    def _rows_of(self, chain):
        rows = [Row(_corner_key(chain, corner), corner.before, corner.after, False) for corner in chain.corners]
        if chain.closed:
            rows.append(Row(self._open_key(chain), len(chain.segments) - 1, 0, True))
        return rows

    @staticmethod
    def _open_key(chain):
        """The key of the open corner of the closed ``chain``: its last segment meets its first one there."""
        return frozenset((chain.segments[-1].profile.Name, chain.segments[0].profile.Name))

    def _row_text(self, number, row):
        segments = self._chain.segments
        before, after = segments[row.before].profile.Label, segments[row.after].profile.Label
        values = self._row_values(row)
        if row.open:
            text = translate("MaxProFrame", "Open · {} → {}").format(before, after)
        else:
            key = translate("MaxProFrame", "key") if values.key else translate("MaxProFrame", "no key")
            text = translate("MaxProFrame", "{} · {} → {} · R {} · {} · clearance {}").format(
                number, before, after, length_text(values.outer_radius), key, length_text(values.clearance)
            )
        if values.joint == STEPPED:
            text = translate("MaxProFrame", "{} · stepped").format(text)
        return text

    def _hint(self):
        """What the list says while the listed pieces fold no corner."""
        if not self.selection:
            return translate("MaxProFrame", "Click the tube where the bar starts.")
        if len(self.selection) == 1:
            return translate("MaxProFrame", "Click the next tube, after {}.").format(self.selection[0].Label)
        return translate("MaxProFrame", "Tubes picked: {}").format(", ".join(obj.Label for obj in self.selection))

    def _show_rows(self):
        """One row per corner of the chain, the selected ones kept; else the hint."""
        widget = self.form.corner_list
        rows = self._rows_of(self._chain) if self._chain is not None else []
        texts = [self._row_text(number, row) for number, row in enumerate(rows, 1)]
        chosen = {row.key for row in self._selected()}
        widget.blockSignals(True)
        try:
            if rows and [row.key for row in rows] == [row.key for row in self._rows] and widget.count() == len(rows):
                for index, text in enumerate(texts):
                    if widget.item(index).text() != text:
                        widget.item(index).setText(text)
            else:
                widget.clear()
                if not rows:
                    item = QtWidgets.QListWidgetItem(self._hint())
                    item.setFlags(QtCore.Qt.NoItemFlags)
                    widget.addItem(item)
                for row, text in zip(rows, texts):
                    item = QtWidgets.QListWidgetItem(text)
                    widget.addItem(item)
                    item.setSelected(row.key in chosen)
        finally:
            widget.blockSignals(False)
        self._rows = rows

    def _selected(self):
        """The rows selected in the list, in their order."""
        widget = self.form.corner_list
        indexes = sorted(widget.row(item) for item in widget.selectedItems())
        return [self._rows[index] for index in indexes if index < len(self._rows)]

    def _field_rows(self):
        """The corners the fields edit: the selected ones, the open one too (its OPEN_FIELDS only)."""
        return self._selected()

    def _show_tube(self):
        """The material and the wall thickness of the tubes, read from their profile (S7)."""
        profile = None
        if self._chain is not None:
            profile = self._chain.segments[0].profile
        elif self.selection and _alive(self.selection[0]):
            profile = base_profile(self.selection[0])
        text = ""
        if profile is not None:
            thickness = getattr(profile, "Thickness", None)
            parts = (getattr(profile, "Material", "") or "", length_text(float(thickness)) if thickness else "")
            text = " · ".join(part for part in parts if part)
        self.form.label_tube.setText(text)

    def _corner_selection_changed(self):
        if not self._active() or self._wait(self._corner_selection_changed):
            return
        self._mixed_edits.clear()
        self._present_fields()
        self._enable_remove()
        self._highlight()

    # Corner values.

    def _corner_object(self, key):
        """The corner object of the bar shown for the corner ``key``, or None."""
        bar = self.obj
        if bar is None or not _alive(bar):
            return None
        for obj in bar.Corners:
            if obj is not None and _alive(obj) and corner_key(obj) == key:
                return obj
        return None

    def _driven(self, key, fields):
        """{CornerSettings field: value} of ``fields`` an expression drives on the object of the corner ``key``."""
        obj = self._corner_object(key)
        if obj is None:
            return {}
        return {
            field: _setting(field, getattr(obj, prop))
            for prop, field in SETTINGS_PROPERTIES.items()
            if field in fields and expression_of(obj, prop) is not None
        }

    def _corner_values(self, key):
        """The ``CornerSettings`` of the folded corner ``key``: the panel's, but where an expression drives its
        object."""
        values = self._values.get(key, self._last)
        driven = self._driven(key, SETTINGS_PROPERTIES.values())
        if driven:
            values = replace(values, **driven)
            self._values[key] = values
        return values

    def _open_values_of(self, chain, key):
        """The ``CornerSettings`` of the open corner ``key`` of ``chain``: the first corner's, with the OPEN_FIELDS of
        its own once it has them, and where an expression drives its object (stepped-corners S6)."""
        values = self._corner_values(_corner_key(chain, chain.corners[0])) if chain.corners else self._last
        own = self._open_values.get(key)
        if own is not None:
            values = replace(values, **{field: getattr(own, field) for field in OPEN_FIELDS})
        driven = self._driven(key, OPEN_FIELDS)
        if driven:
            values = replace(values, **driven)
            self._open_values[key] = values
        return values

    def _row_values(self, row):
        """The ``CornerSettings`` of the corner of ``row``."""
        if row.open:
            return self._open_values_of(self._chain, row.key)
        return self._corner_values(row.key)

    def _settings(self, chain):
        """The ``CornerSettings`` of each folded corner of ``chain``."""
        return [self._corner_values(_corner_key(chain, corner)) for corner in chain.corners]

    def _open_settings(self, chain):
        """The ``CornerSettings`` of the open corner of ``chain`` when it is closed, else None."""
        return self._open_values_of(chain, self._open_key(chain)) if chain.closed else None

    def _present_check(self, box, text, column):
        """Show ``column`` (the values of the selected corners) in the check ``box`` labelled ``text``: unchecked and
        Mixed values when they differ. (checked, mixed)."""
        mixed = len({bool(value) for value in column}) > 1
        checked = not mixed and bool(column[0])
        if box.isChecked() != checked:
            box.setChecked(checked)
        box.setProperty("mixedValues", mixed)
        box.setText(f"{text} — {translate('frameforge', 'Mixed values')}" if mixed else text)
        return checked, mixed

    def _present_fields(self):
        """The fields show the values of the selected corners, mixed where they differ; disabled with none. With the
        open corner selected only its OPEN_FIELDS are enabled; the step only for a Stepped joint (or mixed)."""
        form = self.form
        rows = self._field_rows()
        values = [self._row_values(row) for row in rows] or [self._last]
        enabled = bool(rows)
        folded_only = not any(row.open for row in rows)
        joints = {value.joint for value in values}
        stepped = STEPPED in joints
        previous, self._filling = self._filling, True
        try:
            for name, field, _ in NUMBER_FIELDS:
                spin = getattr(form, name)
                column = [float(getattr(value, field)) for value in values]
                if abs(spin.value() - column[0]) > VALUE_TOLERANCE:
                    spin.setValue(column[0])
                self._mixed[name].set_mixed(max(column) - min(column) > VALUE_TOLERANCE)
                spin.setEnabled(enabled and (folded_only or field in OPEN_FIELDS))
            checked, mixed = self._present_check(
                form.cb_key, translate("MaxProFrame", "Interlocking key"), [value.key for value in values]
            )
            form.cb_key.setEnabled(enabled and folded_only)
            form.spin_key_diameter.setEnabled(enabled and folded_only and (checked or mixed))
            index = form.combo_joint.findData(values[0].joint)
            if form.combo_joint.currentIndex() != index:
                form.combo_joint.setCurrentIndex(index)
            self._mixed["combo_joint"].set_mixed(len(joints) > 1)
            form.combo_joint.setEnabled(enabled)
            self._present_check(
                form.cb_step_flip, translate("MaxProFrame", "Flip step"), [value.step_flip for value in values]
            )
            form.spin_step_depth.setEnabled(enabled and stepped)
            form.cb_step_flip.setEnabled(enabled and stepped)
        finally:
            self._filling = previous
        self._bind_fields(rows)

    def _bind_fields(self, rows):
        """Bind the number fields to the one corner selected, once its object exists; else no expression editor. The
        open corner binds its OPEN_FIELDS only."""
        row = rows[0] if len(rows) == 1 else None
        obj = self._corner_object(row.key) if row is not None else None
        bound = (obj.Name, obj.ID, row.open) if obj is not None else None
        if bound == self._bound:
            return
        self._bound = bound
        for name, field, prop in NUMBER_FIELDS:
            spin = getattr(self.form, name)
            if obj is None or (row.open and field not in OPEN_FIELDS) or not bind(spin, obj, prop):
                unbind(spin)

    def _field_changed(self, field, value):
        """A value typed or chosen: it goes to every selected corner and to the next new one."""
        if self._filling or not self._active():
            return
        rows = self._field_rows()
        if not rows or (field not in OPEN_FIELDS and any(row.open for row in rows)):
            return
        prop = PROPERTY_OF[field]
        driven = 0
        for row in rows:
            obj = self._corner_object(row.key)
            if obj is not None and expression_of(obj, prop) is not None:
                # The expression drives it: the field only shows its value.
                driven += 1
                continue
            if row.open:
                self._open_values[row.key] = replace(self._row_values(row), **{field: value})
            else:
                self._values[row.key] = replace(self._corner_values(row.key), **{field: value})
        if driven < len(rows):
            self._last = replace(self._last, **{field: value})
        self._changed()

    def _joint_changed(self, index):
        joint = self.form.combo_joint.itemData(index)
        if joint in JOINTS:
            self._field_changed("joint", joint)

    def _joint_activated(self, index):
        if self.form.combo_joint.property("mixedValues"):
            self._joint_changed(index)

    def _finish_mixed(self, name, field):
        edited = name in self._mixed_edits
        self._mixed_edits.discard(name)
        spin = getattr(self.form, name)
        if edited and spin.property("mixedValues"):
            self._field_changed(field, spin.value())

    # Remove (S4).

    def _removal(self):
        """What Remove does with the selected corners: ("tubes", segment indexes), ("open", row) or None."""
        chain, rows = self._chain, self._selected()
        if chain is None or not rows:
            return None
        if chain.closed:
            if len(rows) == 1 and not rows[0].open:
                return ("open", rows[0])
            return None
        last = len(chain.corners) - 1
        indexes = set()
        for row in rows:
            # The corner index is the index of the segment before it.
            if row.before == last:
                indexes.add(len(chain.segments) - 1)
            elif row.before == 0:
                indexes.add(0)
            else:
                return None
        if self.edited is not None and len(chain.segments) - len(indexes) < 2:
            # An edited bar keeps two tubes at least: no piece can be picked to replace them.
            return None
        return ("tubes", sorted(indexes))

    def _enable_remove(self):
        self.form.button_remove.setEnabled(self._active() and self._removal() is not None)

    def remove_corners(self, *args):
        """Remove the selected corners: the end tube of the first or last corner of an open bar, or open a closed
        frame at the selected corner, the bar then starting there. Whether anything changed (not yet while the
        preview recomputes: it waits)."""
        if not self._active() or self._wait(self.remove_corners):
            return False
        action = self._removal()
        if action is None:
            return False
        kind, what = action
        chain = self._chain
        by_profile = {_profile_name(obj): obj for obj in self.selection}
        order = [by_profile[segment.profile.Name] for segment in chain.segments]
        if kind == "tubes":
            self.selection = [obj for index, obj in enumerate(order) if index not in what]
        else:
            before, after = order[what.before], order[what.after]
            first = _profile_name(self.selection[0])
            if first == _profile_name(before):
                self._open_pair = [before, after]
            elif first == _profile_name(after):
                self._open_pair = [after, before]
            else:
                # The bar starts at the open corner: the tube after it comes first, the one before it last.
                split = what.after
                self.selection = order[split:] + order[:split]
                self._open_pair = [after, before]
        widget = self.form.corner_list
        widget.blockSignals(True)
        widget.clearSelection()
        widget.blockSignals(False)
        self._timer.stop()
        self._refresh()
        self.update_preview()
        self._highlight()
        return True

    # Checks.

    def _build_chain(self):
        """(chain of the listed pieces, open pair used): open at the chosen corner while it is one of the first
        piece, else where build_chain opens it."""
        pair = self._open_pair
        if pair is not None and self.selection:
            names = [_profile_name(obj) for obj in pair]
            listed = {_profile_name(obj) for obj in self.selection}
            if None not in names and set(names) <= listed and _profile_name(self.selection[0]) in names:
                try:
                    return build_chain(self.selection, open_corner=pair), pair
                except ChainError:
                    pass
        return build_chain(self.selection), None

    def _check(self):
        """(messages of what keeps the bar from folding, chain or None)."""
        try:
            chain, self._chain_pair = self._build_chain()
        except ChainError as error:
            self._chain_pair = None
            return [str(error)], None
        for corner in chain.corners:
            # A corner met for the first time starts with the values last set (S5).
            self._values.setdefault(_corner_key(chain, corner), self._last)
        problems = [cut_at_fold_message(chain, cut) for cut in cuts_at_folds(chain)]
        try:
            check_settings(chain, self._settings(chain), open_corner=self._open_settings(chain))
        except UnfoldError as error:
            problems.append(str(error))
        return problems, chain

    def problems(self):
        """What keeps OK disabled now."""
        return list(self._problems) + ([self._error] if self._error and not self._pending() else [])

    def _refresh(self):
        """Check the panel values; show the corners, the tube, the fields, the messages, the status and OK."""
        if self._wait(self._refresh):
            return
        self._problems, self._chain = self._check()
        self._show_rows()
        self._show_tube()
        self._present_fields()
        self._enable_remove()
        self._show_messages()

    def _show_messages(self):
        error = [self._error] if self._error and not self._pending() else []
        self.form.message_label.setText("\n".join(self._problems + error))
        if self._pending():
            status = translate("MaxProFrame", "Pending changes")
        elif self.obj is not None and _alive(self.obj):
            status = translate("MaxProFrame", "Preview updated")
        else:
            status = translate("MaxProFrame", "No preview")
        self.form.status_label.setText(status)
        self._enable_ok()

    def _pending(self):
        return self._previewed != self._wanted()

    def can_accept(self):
        return not self._closed and not self.problems()

    def ok_button_enabled(self):
        """Whether OK can be pressed: the dialog's button when it is shown."""
        if self._ok_button is not None:
            return self._ok_button.isEnabled()
        return self.can_accept()

    def _enable_ok(self):
        if self._ok_button is not None:
            self._ok_button.setEnabled(self.can_accept())

    # Changes.

    def _changed(self, *args):
        if not self._active() or self._wait(self._changed):
            return
        self._refresh()
        self._timer.start()

    def _on_auto_update_toggled(self, checked):
        get_param_group(writable=True).SetBool(self.auto_preview_param, checked)
        self.update_preview()

    # Preview.

    def _wanted(self):
        """What the bar must be: None while something keeps it from folding."""
        if self._problems or self._chain is None:
            return None
        chain = self._chain
        tips = tuple(segment.tip.Name for segment in chain.segments)
        corners = tuple(
            (tuple(sorted(_corner_key(chain, corner))), tuple(_plain(value) for value in vars(settings).values()))
            for corner, settings in zip(chain.corners, self._settings(chain))
        )
        opened = None
        if chain.closed:
            settings = self._open_settings(chain)
            opened = (
                chain.segments[0].profile.Name,
                chain.segments[-1].profile.Name,
                tuple(_plain(value) for value in vars(settings).values()),
            )
        return (("Segments", tips), ("Corners", corners), ("Open", opened))

    def update_preview(self, *args, force=False):
        """Make the bar match the panel when Update automatically is checked (or ``force``)."""
        if not self._active():
            return
        if self._wait(self._forced_preview if force else self.update_preview):
            # Asked for (the preview delay over) while the preview recomputes: right after it, not dropped.
            return
        self._recomputing = True
        try:
            if force or self.form.cb_auto_update.isChecked():
                self._preview(force)
        finally:
            self._recomputing = False
        if self._active():
            # The corner objects made or recomputed: the values their expressions give, the fields bound to them.
            self._show_rows()
            self._present_fields()
            self._show_messages()
            if self._selected() or self._overlay is not None:
                self._highlight()
        self._run_waiting()

    def _run_waiting(self):
        """Run what waited for the recompute, then OK or Cancel pressed meanwhile."""
        waiting, self._waiting = self._waiting, []
        for work in waiting:
            if self._active():
                work()
        deferred, self._deferred = self._deferred, None
        if deferred is not None and self._active() and deferred():
            self._close_dialog()

    def _forced_preview(self):
        self.update_preview(force=True)

    def _busy(self):
        """Whether a document recomputes: the panel's preview, or a recompute the panel did not start (the user's, the
        expression editor's, one of another open document), which pumps Qt events all the same (issue #148)."""
        if self._recomputing:
            return True
        for doc in App.listDocuments().values():
            try:
                if doc.Recomputing:
                    return True
            except Exception:
                continue
        return False

    def _wait(self, work):
        """Whether ``work`` waits for the recompute to end, to run once then (S15).

        A recompute pumps Qt events (FreeCAD's progress bar; newer FreeCAD inside its booleans too): a key typed, the
        preview delay over, a click on the list or a button runs inside it. An OCC boolean run there (the checks of
        the corners, the overlay) waits forever for the threads the paused boolean of the recompute holds, and
        FreeCAD freezes (L23). Values typed still reach the panel, but nothing geometric runs until the recompute
        returns.
        """
        if not self._busy():
            return False
        if work not in self._waiting:
            self._waiting.append(work)
        self._resume_later()
        return True

    def _resume_later(self):
        """What waits for a recompute the panel did not start runs once the document says it ended, or at the latest
        a moment later. The panel's own preview runs it as it returns."""
        if self._recomputing:
            return
        if self._recompute_end is None:
            self._recompute_end = _RecomputeEnd(self._resume)
            App.addDocumentObserver(self._recompute_end)
        if not self._resuming:
            self._resuming = True
            QtCore.QTimer.singleShot(GAP_DELAY_MS, self._look_again)

    def _look_again(self):
        self._resuming = False
        self._resume()

    def _resume(self):
        if not self._active():
            return
        if self._busy():
            self._resume_later()
            return
        self._stop_watching()
        self._run_waiting()

    def _stop_watching(self):
        """No longer told when the document ends a recompute."""
        observer, self._recompute_end = self._recompute_end, None
        if observer is not None:
            try:
                App.removeDocumentObserver(observer)
            except Exception:
                pass

    def _preview(self, force):
        wanted = self._wanted()
        if wanted is None:
            if self.edited is None and self._preview_of_other_pieces():
                self._drop_preview()
            return
        if not force and wanted == self._previewed and _alive(self.obj):
            return
        self._error = ""
        self._open_transaction()
        # A selected preview changed or remade is no click of the user.
        self._syncing = True
        try:
            settings = self._settings(self._chain)
            opened = self._open_settings(self._chain)
            if self.obj is None or not _alive(self.obj):
                self.obj = make_folded_bar(self.selection, settings, open_corner=self._chain_pair, open_settings=opened)
                self._restore_kept_expressions()
            else:
                # The bar follows the chain of the list: the pieces clicked or removed since, its start; its base
                # tubes with them.
                set_segments(self.obj, [segment.tip for segment in self._chain.segments])
                # The corner objects follow the chain and the fields; the open one is where the chain opens, with
                # its own joint, step and clearance.
                update_corners(self.obj, self._chain, settings, open_settings=opened)
                self.doc.recompute()
            self._error = _failures([self.obj])
        except Exception as error:
            self._error = str(error)
        finally:
            self._syncing = False
        self._previewed = wanted
        if self.edited is None:
            self._show_unlisted()
        else:
            self._show_removed()

    def _restore_kept_expressions(self):
        """The new preview takes the expressions of the corners of the one dropped before."""
        restored = False
        for obj in self.obj.Corners:
            expressions = self._kept_expressions.get(corner_key(obj)) if obj is not None else None
            if expressions and restore_expressions(obj, expressions):
                restored = True
        self._kept_expressions = {}
        if restored:
            self.doc.recompute()

    def _preview_bar(self):
        """The previewed new bar, or None (none yet, or editing)."""
        if self.edited is None and self.obj is not None and _alive(self.obj):
            return self.obj
        return None

    @staticmethod
    def _profiles_of(bar):
        """Names of the profiles ``bar`` folds."""
        if bar is None or not _alive(bar):
            return set()
        profiles = (base_profile(segment) for segment in bar_tips(bar))
        return {profile.Name for profile in profiles if profile is not None}

    def _profiles_in_bar(self):
        """Names of the profiles the preview folds now."""
        return self._profiles_of(self._preview_bar())

    def _preview_of_other_pieces(self):
        """Whether a preview shows pieces other than the listed ones."""
        if self._preview_bar() is None:
            return False
        return self._profiles_in_bar() != {base_profile(obj).Name for obj in self.selection}

    def _drop_preview(self):
        """Remove the preview of pieces that no longer fold: the pieces show again."""
        self._kept_expressions = {
            corner_key(obj): expressions_of(obj, EXPRESSION_PROPERTIES)
            for obj in self.obj.Corners
            if obj is not None and _alive(obj) and corner_key(obj) is not None
        }
        self._syncing = True
        try:
            self.doc.removeObject(self.obj.Name)
        finally:
            self._syncing = False
        self.obj = None
        self._error = ""
        self._previewed = None
        self._show_unlisted()

    def _show_unlisted(self):
        """Show the pieces the preview hid as they were, but the ones it still folds."""
        folded = self._profiles_in_bar()
        for piece, visible in self._visibility:
            if not _alive(piece) or piece.Visibility == visible:
                continue
            profile = base_profile(piece)
            if profile is None or profile.Name not in folded:
                piece.Visibility = visible

    def _show_removed(self):
        """Show the pieces Remove took off the edited bar: it no longer hides them."""
        folded = self._profiles_of(self.obj)
        for piece in self._before["Tips"]:
            if _alive(piece) and not piece.Visibility and _profile_name(piece) not in folded:
                piece.Visibility = True

    # Pieces clicked while the panel is open (S22), as in End Miter.

    def add_member(self, obj):
        """List ``obj`` at the end; one entry per profile: a piece made from a listed one takes its place."""
        if obj is None or not _alive(obj) or base_profile(obj) is None or obj in self.selection:
            return False
        if any(obj in _built_on(member) for member in self.selection):
            return False
        replaced = [index for index, member in enumerate(self.selection) if member in _built_on(obj)]
        if replaced:
            # The start of the bar stays where it was.
            self.selection[replaced[0]] = obj
            self.selection = [member for index, member in enumerate(self.selection) if index not in replaced[1:]]
        else:
            self.selection.append(obj)
        profile = base_profile(obj)
        for piece in (obj, newest_piece(profile)):
            if all(piece.Name != seen.Name for seen, _ in self._visibility):
                self._visibility.append((piece, piece.Visibility))
        return True

    def _members_changed(self):
        """Show the new list: its chain, corners and messages; the preview follows later."""
        self._refresh()

    def _clicked(self, doc, obj, sub, point):
        """The piece a selection change stands for: a click on the preview stands for the piece under it."""
        document = App.getDocument(doc) if doc in App.listDocuments() else None
        if document is None or self.doc is None or document.Name != self.doc.Name:
            return None
        source = document.getObject(getattr(obj, "Name", obj))
        bar = self._preview_bar()
        if source is not None and bar is not None and source.Name == bar.Name:
            return self._member_at(bar, sub, point)
        return source

    def _member_at(self, bar, sub, point):
        """The listed piece nearest to the clicked point of the preview (else to the clicked sub-element).

        As ``folded_bar.segment_at`` in its nearest mode, among the listed pieces: the preview may still fold others.
        """
        return nearest_piece(self.selection, pick_point(bar, sub, point))

    def _still_selected(self, member):
        """Whether ``member`` keeps an entry in the selection."""
        return any(selection.Object == member for selection in Gui.Selection.getSelectionEx("*"))

    def addSelection(self, doc, obj, sub, point=None):
        # The preview syncs while it recomputes: a selection change then is no click to take (S15).
        if self._syncing or not self._active() or self.edited is not None:
            return
        source = self._clicked(doc, obj, sub, point)
        if source is None or base_profile(source) is None:
            return
        if _ctrl_held() and source in self.selection:
            # Ctrl+click toggles: a listed piece leaves the list.
            self.selection.remove(source)
            self._members_changed()
        elif self.add_member(source):
            self._members_changed()
        # Never change the selection, the document or the 3D view during FreeCAD's observer dispatch.
        QtCore.QTimer.singleShot(0, self._after_selection)

    def removeSelection(self, doc, obj, sub):
        # A piece leaves the list once it has nothing selected; a face of the preview stands for the piece under it.
        if self._syncing or not self._active() or self.edited is not None:
            return
        bar = self._preview_bar()
        on_preview = bar is not None and getattr(obj, "Name", obj) == bar.Name
        source = self._clicked(doc, obj, sub, None)
        if source in self.selection and (on_preview or not self._still_selected(source)):
            self.selection.remove(source)
            self._members_changed()
            QtCore.QTimer.singleShot(0, self._after_selection)

    def clearSelection(self, other):
        pass

    def _after_selection(self):
        if not self._active() or self._wait(self._after_selection):
            return
        self.update_preview()
        self._highlight()

    # 3D view.

    def _select(self, targets):
        """Select ``targets`` ((object, sub-element names)) in the 3D view: no click of the user."""
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            for obj, subs in targets:
                parents = obj.Parents
                for sub in subs:
                    if parents:
                        top, path = parents[0]
                        Gui.Selection.addSelection(obj.Document.Name, top.Name, path + sub)
                    else:
                        Gui.Selection.addSelection(obj.Document.Name, obj.Name, sub)
        finally:
            self._syncing = False
        self._highlighted = bool(targets)

    def _highlight(self):
        """Show the selected corners in the 3D view (S2, S3, S13): the ones the preview folds drawn over it, the bar
        around each vertex, with nothing selected in FreeCAD; the tubes of the others selected while the preview does
        not fold them. With no corner selected, the listed pieces (new bar)."""
        if not self._active() or self._wait(self._highlight):
            return
        rows = self._selected()
        if not rows or self._chain is None:
            self._draw_corners(None, [])
            if self.edited is None:
                self._highlight_members()
            elif self._highlighted:
                self._select([])
            return
        bar = self.obj if self.obj is not None and _alive(self.obj) else None
        folded = self._profiles_of(bar)
        drawn = [row for row in rows if {self._profile_at(row.before), self._profile_at(row.after)} <= folded]
        self._draw_corners(bar, drawn)
        indexes = sorted({index for row in rows if row not in drawn for index in (row.before, row.after)})
        by_profile = {_profile_name(obj): obj for obj in self.selection}
        targets = []
        for index in indexes:
            member = by_profile.get(self._profile_at(index))
            if self._profile_at(index) not in folded and member is not None and _alive(member):
                targets.append((member, [""]))
        self._select(targets)

    def _profile_at(self, index):
        """Name of the profile of the chain segment ``index``."""
        return self._chain.segments[index].profile.Name

    def _draw_corners(self, bar, rows):
        """Draw the corners ``rows`` of the folded ``bar`` over the 3D view (S13), in the selection color: the overlay
        drawn before goes. An annotation is drawn over the shapes, so the corners stay visible."""
        remove_overlay(self._overlay)
        self._overlay = None
        scene = scene_graph(self.doc) if rows else None
        if scene is None:
            return  # Nothing to draw, or no 3D view (another view type).
        from pivy import coin

        color = selection_color()
        node = coin.SoAnnotation()
        for row in rows:
            shape = self._corner_shape(bar, row)
            if shape is not None:
                node.addChild(_overlay_group(shape, color))
        if node.getNumChildren():
            scene.addChild(node)
            self._overlay = (scene, node)

    def _corner_shape(self, bar, row):
        """The part of the folded ``bar`` around the corner ``row``, in global coordinates, or None."""
        radius = 0.0
        if not row.open:
            radius = self._corner_values(row.key).outer_radius
            obj = self._corner_object(row.key)
            if obj is not None:
                # The bar may still show the radius it was folded with.
                radius = max(radius, float(obj.OuterRadius.Value))
        try:
            box = corner_box(self._chain, row, radius)
            placement = container_placement(bar)
            shape = bar.Shape
            key = (
                bar.Name,
                shape.hashCode(),
                tuple(round(value, 9) for value in placement.toMatrix().A),
                tuple(round(value, 9) for value in box.Placement.toMatrix().A),
                round(box.BoundBox.DiagonalLength, 9),
            )
            if key not in self._corner_shapes:
                if len(self._corner_shapes) > 64:
                    self._corner_shapes.clear()
                common = placed(shape, placement).common(box)
                self._corner_shapes[key] = None if common.isNull() or not common.Faces else common
            return self._corner_shapes[key]
        except Exception:
            return None

    def _highlight_members(self):
        """Show every listed piece selected as a whole object; the ones the preview folds as the preview."""
        if not self._active() or self.edited is not None:
            return
        bar = self._preview_bar()
        folded = self._profiles_in_bar()
        shown = []
        for member in self.selection:
            obj = bar if base_profile(member).Name in folded else member
            if obj is not None and _alive(obj) and all(obj.Name != seen.Name for seen in shown):
                shown.append(obj)
        self._select([(obj, [""]) for obj in shown])

    def _open_transaction(self):
        if not self._transaction_open:
            self.doc.openTransaction("Edit Folded Bar" if self.edited is not None else "Create Folded Bar")
            self._transaction_open = True

    # Dialog.

    def _active(self):
        return not self._closed

    def _form_gone(self, *args):
        if not self._closed:
            self.closed()

    def closed(self):
        """FreeCAD closed the dialog without OK or Cancel (document closed, another dialog shown)."""
        if not self._closed:
            self.clean()
            self._discard()

    def clean(self):
        self._closed = True
        self._timer.stop()
        self._stop_watching()
        self._waiting = []
        self._leave_fields()
        # The corners drawn over the 3D view go with the panel (S13).
        remove_overlay(self._overlay)
        self._overlay = None
        self._corner_shapes = {}
        # OK, Cancel or any other close: the panel stops taking the clicks (added by the command only).
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _leave_fields(self):
        """No field of the panel keeps the focus while the dialog closes: a field that loses the focus as it is
        deleted runs its focus handlers on a deleted widget."""
        try:
            focused = QtWidgets.QApplication.focusWidget()
            if focused is not None and self.form is not None and self.form.isAncestorOf(focused):
                focused.clearFocus()
        except RuntimeError:
            pass  # The form is gone already.

    def _discard(self):
        """Abort the transaction; with undo disabled, remove the new bar or put the edited one back by hand."""
        if not _alive_document(self.doc):
            return
        if self._transaction_open:
            try:
                self.doc.abortTransaction()
            except Exception:
                pass
        self._transaction_open = False
        changed = False
        if self.edited is None:
            if self.obj is not None and _alive(self.obj):
                self.doc.removeObject(self.obj.Name)
                changed = True
            for piece, visible in self._visibility:
                if _alive(piece) and piece.Visibility != visible:
                    piece.Visibility = visible
        elif _alive(self.edited):
            changed = self._restore_edited()
        if changed:
            self.doc.recompute()

    def _restore_edited(self):
        """Put the edited bar and its corner objects back as they were, expressions too: the ones removed are made
        again, the ones made since removed."""
        bar, before = self.edited, self._before
        changed = False
        made = [obj for obj in bar.Corners if obj is not None and _alive(obj) and obj.Name not in before["values"]]
        corners = []
        for name in before["Corners"]:
            obj = self.doc.getObject(name)
            if obj is None:
                # Removed with its corner: made again, with its values below.
                values = before["values"][name]
                obj = make_folded_corner(
                    bar, values["PieceA"], values["PieceB"], FIRST_VALUES, open_corner=values["Open"]
                )
                changed = True
            corners.append(obj)
        # The links as they were, not set_segments: a bar waiting to fall back to a tube keeps it in BaseTubes.
        for prop in ("BaseTubes", "Segments"):
            links = [obj for obj in before[prop] if _alive(obj)]
            if prop in bar.PropertiesList and _plain(list(getattr(bar, prop))) != _plain(links):
                setattr(bar, prop, links)
                changed = True
        if [obj.Name for obj in bar.Corners if obj is not None] != [obj.Name for obj in corners]:
            bar.Corners = corners
            changed = True
        for obj in made:
            if _alive(obj) and obj.Name not in before["Corners"]:
                self.doc.removeObject(obj.Name)
                changed = True
        for obj, name in zip(corners, before["Corners"]):
            if restore_expressions(obj, before["expressions"][name]):
                changed = True
            for prop, value in before["values"][name].items():
                if _plain(getattr(obj, prop)) != _plain(value):
                    setattr(obj, prop, value)
                    changed = True
        return changed

    def _unchanged(self):
        return _plain_snapshot(_snapshot(self.edited)) == _plain_snapshot(self._before)

    def _close_edit(self):
        if self.edited is None or not _alive_document(self.doc):
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def _close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def _defer(self, button):
        """A recompute pumps Qt events: OK or Cancel pressed during it waits for it to end."""
        if not self._busy():
            return False
        self._deferred = button
        self._resume_later()
        return True

    def open(self):
        self._highlight()

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def modifyStandardButtons(self, box):
        """Keep the OK button: it is disabled while something keeps the bar from folding."""
        # The task view deletes the row when the dialog closes: no wrapper may outlive it.
        invalidate_wrapper_on_destroy(box)
        button = box.button(QtGui.QDialogButtonBox.Ok)
        if button is None:
            return
        invalidate_wrapper_on_destroy(button)
        button.destroyed.connect(self._ok_button_gone)
        self._ok_button = button
        self._enable_ok()

    def _ok_button_gone(self, *args):
        self._ok_button = None

    def reject(self):
        if self._defer(self.reject):
            return False
        self.clean()
        self._discard()
        self._close_edit()
        if self.edited is None:
            # The pieces were selected to show the panel's list: closed, nothing stays selected.
            Gui.Selection.clearSelection()
        return True

    def accept(self):
        if self._defer(self.accept):
            return False
        if self._closed:
            return False
        # OK keeps the current values even when the preview is out of date.
        self._timer.stop()
        self._refresh()
        if self._problems:
            return False
        self.update_preview(force=True)
        if self._error:
            # The panel stays open with the error, to change the values.
            return False
        if self._last != self._loaded:
            # The next corner, in this session or the next, starts with the values last set (S5).
            remember_values(self._last)
        if self.edited is not None and self._unchanged():
            # Nothing changed in the end: no Undo step.
            self._discard()
        else:
            self.doc.commitTransaction()
        self._transaction_open = False
        self.clean()
        self._close_edit()
        Gui.Selection.clearSelection()
        return True


class FoldedBarCommand:
    """Folded Bar: fold the selected tube pieces into one bar with folded corners."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "FoldedBar.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_FoldedBar", "Folded Bar"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_FoldedBar",
                "<b>Folded Bar</b><br><br>Click two or more tube profiles (or pieces made from them) that meet end to "
                "end, the first one where the bar starts: their corners fold, with a V notch, a key and a relief cut "
                "by the laser and the outer wall bent. A closed frame stays open at one corner. Double-click the bar "
                "to edit it.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        panel = FoldedBarTaskPanel([item.Object for item in Gui.Selection.getSelectionEx()])
        show_panel(panel)
        Gui.Selection.addObserver(panel)


class UnfoldBarCommand:
    """Unfold Bar: the straight bar of the selected Folded Bar, to export for a tube laser."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "UnfoldedBar.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_UnfoldBar", "Unfold Bar"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_UnfoldBar",
                "<b>Unfold Bar</b><br><br>Select a Folded Bar: its straight bar with every cut is made from X = 0 "
                "along X, to export with File > Export (STEP, IGES, BREP) for a tube laser.",
            ),
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        selection = Gui.Selection.getSelection()
        return len(selection) == 1 and is_foldedbar(selection[0])

    def Activated(self):
        bar = Gui.Selection.getSelection()[0]
        doc = bar.Document
        doc.openTransaction("Unfold Bar")
        make_unfolded_bar(bar)
        doc.commitTransaction()


add_command("MaxProFrame_FoldedBar", FoldedBarCommand())
add_command("MaxProFrame_UnfoldBar", UnfoldBarCommand())

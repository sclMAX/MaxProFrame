"""Interlock command: locating fingers at a folded corner of a Folded Bar (odd/tasks/joint-tabs.md, T3: S1, S6, S7),
fingers at an End Miter corner between two tubes (odd/tasks/miter-fingers.md, T4: S1, S2, S6, S7) or tabs at a T joint
(odd/tasks/t-joint-tabs.md, T4: S1-S4), picked by two faces.

The panel takes two faces, preselected when the command starts or clicked while it is open (as Drill Hole takes them),
and deduces the kind of Interlock from them (``InterlockTaskPanel._deduce``):

- Fingers: the inner walls of the two tubes meeting at one folded corner of a Folded Bar, each one read at its picked
  point as a face of the tube under it (``folded_bar.segment_at``): the planar faces on the inside of that corner (S3).
  Those make one Interlock on the corner (``interlock.make_interlock``), previewed on the bar.
- Fingers at an End Miter corner: else, the inner walls of two tubes, each cut by its own End Miter against the other
  (straight tubes, or the free end of a Folded Bar), in the order clicked: the first one owns the first finger
  (``miter_finger_interlock.miter_order``, ``make_miter_fingers``: an Interlock of Kind Fingers with a finger piece on
  each tube). Tried before Tabs: two faces of tubes where either one has an End Miter against the other are a miter
  corner, never a T joint (S7); what it refuses there (a missing End Miter, End Miters with different gaps, a corner
  with fingers already) is what the panel says (S6).
- Tabs: otherwise, a wall of a crossbar and the face of the rail it butts against, clicked in either order
  (``tab_interlock.tab_order``: the order clicked, else the other way round), on straight profiles, trims, cutouts or
  Folded Bars; ``tab_interlock.make_tab_interlock`` adds the tabs and slots pieces.

A pair that makes neither creates nothing and the panel says why, OK disabled: the refusal of the Tabs order that
found a T joint (its crossbar ends on the rail face); else the Fingers refusal when both faces are on one Folded Bar, or
one is on a Folded Bar and the other on no tube; else, for the inner walls of two tubes without End Miters whose ends
meet at a corner, that they need an End Miter of each tube against the other (S6,
``miter_finger_interlock.unmitered_corner``, odd/tasks/miter-fingers.md T5); else the refusal of the Tabs order
clicked. A click on no face or on a
bend of a bar is refused at once. The settings of the kind (Fingers: Count, FingerWidth, Tip, TipSize for a Chamfer or
Round tip only, Depth, Clearance, Flip; Tabs: the same without Depth and Flip, with the tab Length) update the
Interlock as they change and recompute the document; whatever its bar or its pieces refuse shows in the panel and keeps
OK disabled. OK keeps the Interlock, Cancel leaves the document as it was; Apply and continue keeps it in its own Undo
step and waits for the next two faces. A double click on an Interlock (or on the tabs or slots piece of a Tabs one, or
on a finger piece of a miter corner) opens the same panel on it, without picking (``interlock.EDIT_PANEL``); OK keeps
the changes in one Undo step, Cancel puts its values back. A new Interlock starts with the settings last kept with OK or Apply and continue for its kind
(Fingers at a folded corner and at a miter corner share theirs). While the panel's own recompute runs, the faces
clicked and the fields changed wait for it to end (odd/tasks/panel-recompute-deadlock.md, S3). The Interlock made or
edited is drawn over the 3D view, its two faces and its corner, following Flip (``interlock_highlight``,
odd/tasks/interlock-highlight.md S2).
"""

import os
from collections import namedtuple

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe import interlock, interlock_highlight
from freecad.maxproframe._utils import is_foldedbar
from freecad.maxproframe.create_drill_hole_tool import _button_id, _click_point
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, _alive, _alive_document
from freecad.maxproframe.create_folded_bar_tool import _FinishOnEnter
from freecad.maxproframe.expression_fields import count_field, length_field
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.folded_bar import PICK_TOLERANCE, bar_chain, folding_bar, segment_at
from freecad.maxproframe.folded_chain import ChainError, base_profile, section_offset
from freecad.maxproframe.interlock import interlock_key, is_miter_interlock, make_interlock
from freecad.maxproframe.interlock_geometry import (
    CHAMFER,
    FINGERS,
    KINDS,
    ROUND,
    SQUARE,
    TABS,
    TIPS,
    InterlockError,
    TabSettings,
)
from freecad.maxproframe.miter_finger_interlock import (
    MiterFace,
    MiterOrder,
    end_mitered,
    make_miter_fingers,
    miter_order,
    miter_pieces,
    unmitered_corner,
)
from freecad.maxproframe.profile_pattern import global_shape
from freecad.maxproframe.qt_lifetime import invalidate_wrapper_on_destroy, keep_alive_until_destroyed
from freecad.maxproframe.tab_interlock import TabFace, make_tab_interlock, tab_order, tab_pieces
from freecad.maxproframe.trimmed_profile import face_normal

# Largest length and count the fields take (mm, fingers).
MAX_SIZE = 1000.0
MAX_COUNT = 99
# Cosine above which a face normal is the inner wall normal.
NORMAL_TOLERANCE = 1e-6
# The kind of the Interlock last kept: the panel shows its settings until two faces make one.
KIND_PARAM = "Interlock Kind"
# The settings last kept, given to the next Interlock of each kind: (parameter, kind, Interlock property).
LAST_VALUE_PARAMS = {
    FINGERS: (
        ("Interlock Count", "Int", "Count"),
        ("Interlock Finger Width", "Float", "FingerWidth"),
        ("Interlock Tip", "String", "Tip"),
        ("Interlock Tip Size", "Float", "TipSize"),
        ("Interlock Depth", "Float", "Depth"),
        ("Interlock Clearance", "Float", "Clearance"),
        ("Interlock Flip", "Bool", "Flip"),
    ),
    TABS: (
        ("Interlock Tabs Count", "Int", "Count"),
        ("Interlock Tabs Width", "Float", "FingerWidth"),
        ("Interlock Tabs Tip", "String", "Tip"),
        ("Interlock Tabs Tip Size", "Float", "TipSize"),
        ("Interlock Tabs Length", "Float", "Length"),
        ("Interlock Tabs Clearance", "Float", "Clearance"),
    ),
}
# The first Interlock ever of each kind. Fingers: three even square fingers, the automatic depth and the clearance of a
# first Folded Corner. Tabs: the ``TabSettings`` defaults, two even square tabs through the rail wall.
FIRST_VALUES = {
    FINGERS: {
        "Kind": FINGERS,
        "Count": 3,
        "FingerWidth": 0.0,
        "Tip": SQUARE,
        "TipSize": 0.0,
        "Depth": 0.0,
        "Clearance": 0.5,
        "Flip": False,
    },
    TABS: {
        "Kind": TABS,
        "Count": TabSettings().count,
        "FingerWidth": TabSettings().tab_width,
        "Tip": TabSettings().tip,
        "TipSize": TabSettings().tip_size,
        "Length": TabSettings().length,
        "Clearance": TabSettings().clearance,
    },
}

PickedFace = namedtuple("PickedFace", "bar profile normal point")
PickedFace.__doc__ = """A face picked on the Folded Bar ``bar``: the tube ``profile`` under it, the outward ``normal``
of its face and the picked ``point``, global."""


def last_kind():
    """The kind of the Interlock last kept, else Fingers."""
    kind = get_param_group().GetString(KIND_PARAM, FINGERS)
    return kind if kind in KINDS else FINGERS


def last_values(kind=None):
    """The settings a new Interlock of ``kind`` (default: ``last_kind``) starts with: the ones last kept for it, else
    ``FIRST_VALUES``."""
    kind = last_kind() if kind is None else kind
    param, first = get_param_group(), FIRST_VALUES[kind]
    values = {"Kind": kind}
    for name, type_, prop in LAST_VALUE_PARAMS[kind]:
        values[prop] = getattr(param, f"Get{type_}")(name, first[prop])
    if values["Tip"] not in TIPS:
        values["Tip"] = first["Tip"]
    return values


def remember_values(values):
    """Keep ``values`` (by Interlock property, with its Kind) for the next Interlock of that kind, between sessions."""
    param = get_param_group(writable=True)
    param.SetString(KIND_PARAM, values["Kind"])
    for name, type_, prop in LAST_VALUE_PARAMS[values["Kind"]]:
        getattr(param, f"Set{type_}")(name, values[prop])


def _plain(value):
    """A property or field value as the panel compares and stores it."""
    value = value.Value if hasattr(value, "Value") else value
    return round(value, 9) if isinstance(value, float) else value


def values_of(obj):
    """The settings of the Interlock ``obj``, by property: its Kind and those of its kind."""
    kind = str(obj.Kind)
    return {"Kind": kind, **{prop: _plain(getattr(obj, prop)) for _, _, prop in LAST_VALUE_PARAMS[kind]}}


def interlock_bar(obj):
    """The Folded Bar listing the Interlock ``obj``, or None."""
    for parent in obj.InList:
        if is_foldedbar(parent) and obj in parent.Interlocks:
            return parent
    return None


# What the panel says (S6).


def pick_hint():
    return translate(
        "MaxProFrame",
        "Click the inner walls of the two tubes at a folded corner of a Folded Bar or at an End Miter corner for "
        "fingers, or a wall of a crossbar and the face of the rail it butts against for tabs.",
    )


def other_face_hint(first=None):
    """What to click after the face ``first`` (a ``Click``): the other inner wall after an inner wall at a folded
    corner; after a face of a tube cut by an End Miter, the other inner wall of its miter corner or the other face of a
    T joint; else the other face of a T joint."""
    if first is None or first.fingers is not None:
        return translate("MaxProFrame", "Click the inner wall of the other tube at that corner.")
    if first.mitered:
        return translate(
            "MaxProFrame",
            "Click the inner wall of the other tube at the End Miter corner for fingers, or the other face of the T "
            "joint for tabs.",
        )
    return translate(
        "MaxProFrame",
        "Click the other face of the T joint: the face of the rail the crossbar butts against, or the wall of the "
        "crossbar that carries the tabs.",
    )


def _segment_index(chain, profile):
    for index, segment in enumerate(chain.segments):
        if segment.profile.Name == profile.Name:
            return index
    return None


def _inner_normal(chain, corner, index):
    """Outward normal of the inner wall of the segment ``index`` at ``corner``: towards the inside of the corner."""
    d1, d2 = chain.segments[corner.before].direction, chain.segments[corner.after].direction
    if index == corner.before:
        normal = d2 - d1 * d1.dot(d2)
    else:
        normal = (d1 - d2 * d2.dot(d1)) * -1
    return normal.normalize()


def _on_inner_wall(chain, corner, index, face):
    """Whether ``face`` is the inner wall of the segment ``index`` at ``corner``: facing the inside of the corner, on
    the outside of the tube (not the inside of its outer wall)."""
    normal = _inner_normal(chain, corner, index)
    if face.normal.dot(normal) < 1 - NORMAL_TOLERANCE:
        return False
    segment = chain.segments[index]
    center = segment.start + section_offset(segment)
    return abs((face.point - center).dot(normal) - corner.depth / 2) <= PICK_TOLERANCE


def corner_faces(obj):
    """((PieceA, faces), (PieceB, faces)) of the Fingers Interlock ``obj`` at a folded corner: the planar faces of its
    bar, global, on the inner wall of each of its two tubes at that corner (``_on_inner_wall``, as a click is read);
    None when no bar lists it or its bar has no such corner (odd/tasks/interlock-highlight.md, S4)."""
    bar = interlock_bar(obj)
    if bar is None or obj.PieceA is None or obj.PieceB is None:
        return None
    try:
        chain = bar_chain(bar)
    except ChainError:
        return None
    pieces = (obj.PieceA, obj.PieceB)
    indexes = [_segment_index(chain, piece) for piece in pieces]
    corner = next((c for c in chain.corners if [c.before, c.after] in (indexes, indexes[::-1])), None)
    if corner is None:
        return None
    planar = [face for face in global_shape(bar).Faces if isinstance(face.Surface, Part.Plane)]
    found = []
    for piece, index in zip(pieces, indexes):
        segment = chain.segments[index]
        walls = []
        for face in planar:
            center = face.CenterOfMass
            # Within its tube: a coplanar face of another tube is not its wall.
            along = (center - segment.start).dot(segment.direction)
            if not -PICK_TOLERANCE <= along <= segment.length + PICK_TOLERANCE:
                continue
            if _on_inner_wall(chain, corner, index, PickedFace(bar, piece, face_normal(face), center)):
                walls.append(face)
        found.append((piece, walls))
    return tuple(found)


def _inner_wall_message(profile):
    return translate("MaxProFrame", "Click the inner wall of {}: its face on the inside of the folded corner.").format(
        profile.Label
    )


def picked_face(obj, sub, point=None):
    """(PickedFace, None) for a face ``sub`` of the Folded Bar ``obj`` clicked at ``point`` that is the inner wall of
    its tube at one of its folded corners; else (None, what to pick)."""
    if obj is None:
        return None, pick_hint()
    if not is_foldedbar(obj):
        return None, translate(
            "MaxProFrame", "{} is not a Folded Bar: click the inner walls of two tubes of a Folded Bar."
        ).format(obj.Label)
    if not sub:
        return None, pick_hint()
    pick = segment_at(obj, sub, point)
    if pick.reason:
        return None, pick.reason
    profile = base_profile(pick.tip)
    try:
        chain = bar_chain(obj)
        element = global_shape(pick.tip).getElement(pick.face)
        normal = element.normalAt(*element.Surface.parameter(pick.point))
    except ChainError as error:
        return None, str(error)
    except Exception:
        return None, _inner_wall_message(profile)
    face = PickedFace(obj, profile, normal, pick.point)
    index = _segment_index(chain, profile)
    corners = [corner for corner in chain.corners if index in (corner.before, corner.after)]
    if not any(_on_inner_wall(chain, corner, index, face) for corner in corners):
        return None, _inner_wall_message(profile)
    return face, None


def picked_corner(first, second):
    """(chain, corner, None) for the folded corner whose inner walls are the faces ``first`` and ``second``; else
    (None, None, what to pick)."""
    bar = first.bar
    if bar.Name != second.bar.Name:
        return None, None, translate("MaxProFrame", "Click both faces on the same Folded Bar.")
    try:
        chain = bar_chain(bar)
    except ChainError as error:
        return None, None, str(error)
    indexes = [_segment_index(chain, face.profile) for face in (first, second)]
    corner = next((c for c in chain.corners if {c.before, c.after} == set(indexes)), None)
    labels = (first.profile.Label, second.profile.Label, bar.Label)
    if corner is None:
        if chain.closed and set(indexes) == {0, len(chain.segments) - 1}:
            text = translate(
                "MaxProFrame",
                "{} and {} meet at the open corner of {}, which does not fold: click the inner walls at a folded "
                "corner.",
            )
        else:
            text = translate(
                "MaxProFrame",
                "{} and {} do not meet at a folded corner of {}: click the inner walls of two tubes that do.",
            )
        return None, None, text.format(*labels)
    for face, index in zip((first, second), indexes):
        if not _on_inner_wall(chain, corner, index, face):
            return None, None, _inner_wall_message(face.profile)
    return chain, corner, None


Click = namedtuple("Click", "obj sub point fingers refusal mitered", defaults=(False,))
Click.__doc__ = """A face clicked for an Interlock: ``sub`` of ``obj`` at the global ``point`` (or None); ``fingers``
the PickedFace when it is an inner wall at a folded corner of a Folded Bar, else None and ``refusal`` says why;
``mitered`` whether its tube is cut by an End Miter (it may be an inner wall of a miter corner)."""


def clicked_face(obj, sub, point=None):
    """(Click, None) for the face ``sub`` of ``obj`` clicked at ``point`` when it may be one of the two faces of an
    Interlock, Fingers or Tabs; (None, what to click) for no face or a bend of a Folded Bar."""
    if obj is None or not sub:
        return None, pick_hint()
    if is_foldedbar(obj):
        pick = segment_at(obj, sub, point)
        if pick.reason:
            return None, pick.reason
    fingers, refusal = picked_face(obj, sub, point)
    mitered = fingers is None and end_mitered(MiterFace(obj, sub, point))
    return Click(obj, sub, point, fingers, refusal, mitered), None


def _same_corner_tube(first, second):
    """Whether the clicks ``first`` and ``second`` are inner walls of the same tube of one Folded Bar."""
    return (
        first.fingers is not None
        and second.fingers is not None
        and first.fingers.bar.Name == second.fingers.bar.Name
        and first.fingers.profile.Name == second.fingers.profile.Name
    )


def _fingers_meant(first, second):
    """Whether the clicks ``first`` and ``second`` that make no Interlock and no T joint ask for Fingers: both on one
    Folded Bar, or one on a Folded Bar and the other on no tube."""
    bars = [click.obj.Name for click in (first, second) if is_foldedbar(click.obj)]
    if len(bars) == 2:
        return bars[0] == bars[1]
    return len(bars) == 1 and any(not is_foldedbar(c.obj) and base_profile(c.obj) is None for c in (first, second))


def _without_kind(values):
    return {prop: value for prop, value in values.items() if prop != "Kind"}


def show_panel(panel, picking=False):
    Gui.Control.showDialog(panel)
    if picking:
        Gui.Selection.addObserver(panel)


def edit_interlock(obj):
    """Double click on the Interlock ``obj``: its panel (``interlock.EDIT_PANEL``)."""
    show_panel(InterlockTaskPanel(edited=obj))


class InterlockTaskPanel:
    """Two faces, the kind of Interlock they make (the module docstring says how) and its settings.

    ``picks`` are the faces preselected, (object, sub-element, picked point or None); as a selection observer (added by
    the command) the panel takes the faces clicked while it is open, until the Interlock is made. Apply and continue
    keeps it in its own Undo step and waits for the faces of the next one, with the same settings. With ``edited`` the
    panel changes that Interlock, without picking. ``kind`` is the kind the fields show: that of the Interlock made or
    edited; before, that of the Interlock last kept.
    """

    def __init__(self, picks=(), edited=None):
        self.edited = edited
        self.obj = edited
        self.kind = str(edited.Kind) if edited is not None else last_kind()
        # Whether the Fingers shown are at an End Miter corner: the tool tips say so.
        self.miter = edited is not None and is_miter_interlock(edited)
        self.bar = interlock_bar(edited) if edited is not None else None
        self.doc = edited.Document if edited is not None else App.ActiveDocument
        # The faces picked so far, at most one until they make the Interlock.
        self.faces = []
        # Why the last face clicked was refused (S6).
        self._refusal = ""
        self._closed = False
        self._transaction_open = False
        self._recomputing = False
        self._retrying = False
        self._filling = False
        self._clicks = []
        self._ok_button = None
        # Apply and continue in the dialog's button row, next to OK and Cancel: only while creating.
        self._apply_button = None
        # Whether Apply and continue kept an Interlock: OK with none made since then just closes.
        self._applied = False
        # Its faces and its corner over the 3D view (odd/tasks/interlock-highlight.md, S2), and whether drawing it
        # waits for a recompute.
        self._overlay = interlock_highlight.InterlockOverlay()
        self._overlay_waiting = False
        self._before = values_of(edited) if edited is not None else None
        # The settings of each kind for its next Interlock: those last kept, as the fields change them.
        self._values = {kind: last_values(kind) for kind in KINDS}
        if edited is not None:
            self._values[self.kind] = dict(self._before)
        self.form = keep_alive_until_destroyed(self._build_form())
        self.form.destroyed.connect(self._form_gone)
        self._fill(self._values[self.kind])
        self._connect()
        if edited is not None:
            self._open_transaction("Edit Interlock")
        # The tree selection draws no overlay while the panel is open.
        interlock_highlight.panel_opened(self)
        for obj, sub, point in picks:
            self._pick(obj, sub, point)
        self._show()

    # Form.

    def _build_form(self):
        form = QtWidgets.QWidget()
        form.setWindowTitle(translate("MaxProFrame", "Interlock"))
        layout = QtWidgets.QVBoxLayout(form)

        form.groupBox_corner = QtWidgets.QGroupBox(translate("MaxProFrame", "Corner"))
        corner = QtWidgets.QVBoxLayout(form.groupBox_corner)
        form.label_corner = QtWidgets.QLabel()
        corner.addWidget(form.label_corner)
        form.message_label = QtWidgets.QLabel()
        form.message_label.setWordWrap(True)
        corner.addWidget(form.message_label)
        layout.addWidget(form.groupBox_corner)

        form.groupBox_settings = QtWidgets.QGroupBox(translate("MaxProFrame", "Fingers"))
        settings = QtWidgets.QFormLayout(form.groupBox_settings)
        form.combo_kind = QtWidgets.QComboBox()
        form.combo_kind.addItem(translate("MaxProFrame", "Fingers"), FINGERS)
        form.combo_kind.addItem(translate("MaxProFrame", "Tabs"), TABS)
        # The two faces make the kind: it shows, it is no choice.
        form.combo_kind.setEnabled(False)
        form.combo_kind.setToolTip(
            translate(
                "MaxProFrame",
                "Shape of the interlock: Fingers, at the inner vertex of a folded corner or of an End Miter corner; "
                "Tabs, on the end of a crossbar through slots in the rail at a T joint",
            )
        )
        settings.addRow(translate("MaxProFrame", "Kind"), form.combo_kind)
        form.spin_count = count_field(1, MAX_COUNT, FIRST_VALUES[FINGERS]["Count"])
        settings.addRow(translate("MaxProFrame", "Count"), form.spin_count)
        form.spin_finger_width = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_finger_width.setSpecialValueText(translate("MaxProFrame", "Even"))
        form.label_finger_width = QtWidgets.QLabel()
        settings.addRow(form.label_finger_width, form.spin_finger_width)
        form.combo_tip = QtWidgets.QComboBox()
        for tip, text in (
            (SQUARE, translate("MaxProFrame", "Square")),
            (CHAMFER, translate("MaxProFrame", "Chamfer")),
            (ROUND, translate("MaxProFrame", "Round")),
        ):
            form.combo_tip.addItem(text, tip)
        settings.addRow(translate("MaxProFrame", "Tip"), form.combo_tip)
        form.spin_tip_size = length_field(0.0, MAX_SIZE, 0.0)
        settings.addRow(translate("MaxProFrame", "Tip size"), form.spin_tip_size)
        form.spin_depth = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_depth.setSpecialValueText(translate("MaxProFrame", "Automatic"))
        form.spin_depth.setToolTip(
            translate(
                "MaxProFrame",
                "Depth of the finger band across the bent wall; Automatic: the step depth of a Stepped joint",
            )
        )
        form.label_depth = QtWidgets.QLabel(translate("MaxProFrame", "Depth"))
        settings.addRow(form.label_depth, form.spin_depth)
        form.spin_length = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_length.setSpecialValueText(translate("MaxProFrame", "Automatic"))
        form.spin_length.setToolTip(
            translate(
                "MaxProFrame",
                "How far the tabs go across the rail wall, along its normal; Automatic: the rail wall thickness, "
                "flush with its inside face",
            )
        )
        form.label_length = QtWidgets.QLabel(translate("MaxProFrame", "Length"))
        settings.addRow(form.label_length, form.spin_length)
        form.spin_clearance = length_field(0.0, MAX_SIZE, 0.0)
        settings.addRow(translate("MaxProFrame", "Clearance"), form.spin_clearance)
        form.cb_flip = QtWidgets.QCheckBox(translate("MaxProFrame", "Flip"))
        form.cb_flip.setToolTip(
            translate("MaxProFrame", "Swap the tubes: the tube after the corner owns the first finger")
        )
        settings.addRow(form.cb_flip)
        layout.addWidget(form.groupBox_settings)
        spins = self._spins(form)
        for spin in spins:
            # A value typed applies once the field is done; Enter does not close the panel.
            spin.setKeyboardTracking(False)
        form.finish_on_enter = _FinishOnEnter(form, spins)
        return form

    @staticmethod
    def _spins(form):
        return [
            form.spin_count,
            form.spin_finger_width,
            form.spin_tip_size,
            form.spin_depth,
            form.spin_length,
            form.spin_clearance,
        ]

    def _connect(self):
        form = self.form
        for spin in self._spins(form):
            spin.valueChanged.connect(self._changed)
        form.combo_tip.currentIndexChanged.connect(self._changed)
        form.cb_flip.toggled.connect(self._changed)

    def _fill(self, values):
        """Show ``values`` (by Interlock property, with their Kind) in the fields, and the fields of that kind."""
        form = self.form
        self._filling = True
        try:
            self.kind = values["Kind"]
            form.combo_kind.setCurrentIndex(max(0, form.combo_kind.findData(self.kind)))
            form.spin_count.setValue(int(values["Count"]))
            form.spin_finger_width.setValue(float(values["FingerWidth"]))
            form.combo_tip.setCurrentIndex(max(0, form.combo_tip.findData(values["Tip"])))
            form.spin_tip_size.setValue(float(values["TipSize"]))
            form.spin_clearance.setValue(float(values["Clearance"]))
            if self.kind == TABS:
                form.spin_length.setValue(float(values["Length"]))
            else:
                form.spin_depth.setValue(float(values["Depth"]))
                form.cb_flip.setChecked(bool(values["Flip"]))
        finally:
            self._filling = False
        self._show_kind()
        self._enable_tip_size()

    def _show_kind(self):
        """The fields, labels and tool tips of the kind shown: Tabs have a Length, no Depth nor Flip."""
        form = self.form
        tabs = self.kind == TABS
        for widget in (form.label_depth, form.spin_depth, form.cb_flip):
            widget.setVisible(not tabs)
        for widget in (form.label_length, form.spin_length):
            widget.setVisible(tabs)
        if tabs:
            form.groupBox_corner.setTitle(translate("MaxProFrame", "T joint"))
            form.groupBox_settings.setTitle(translate("MaxProFrame", "Tabs"))
            form.label_finger_width.setText(translate("MaxProFrame", "Tab width"))
            form.spin_count.setToolTip(
                translate("MaxProFrame", "Number of tabs, at least 1, across the flat part of the crossbar wall")
            )
            form.spin_finger_width.setToolTip(
                translate(
                    "MaxProFrame",
                    "Width of every tab, with equal gaps between them and at both ends; Even: the tabs and the gaps "
                    "split the flat part of the wall evenly",
                )
            )
            form.combo_tip.setToolTip(
                translate("MaxProFrame", "Corners of each tab tip: Square, Chamfer or Round, to lead it into its slot")
            )
            form.spin_tip_size.setToolTip(
                translate("MaxProFrame", "Chamfer leg or radius of the tab tip corners, in the crossbar wall plane")
            )
            form.spin_clearance.setToolTip(
                translate("MaxProFrame", "Gap around each tab in its slot, half on each side")
            )
            return
        form.groupBox_corner.setTitle(translate("MaxProFrame", "Corner"))
        form.groupBox_settings.setTitle(translate("MaxProFrame", "Fingers"))
        form.label_finger_width.setText(translate("MaxProFrame", "Finger width"))
        if self.miter:
            form.spin_count.setToolTip(
                translate(
                    "MaxProFrame",
                    "Number of fingers, at least 2; the tube of the first face clicked owns the first one",
                )
            )
            form.spin_depth.setToolTip(
                translate(
                    "MaxProFrame",
                    "Depth of the finger band across the inner walls; Automatic: the step depth of a Stepped joint",
                )
            )
            form.cb_flip.setToolTip(
                translate("MaxProFrame", "Swap the tubes: the tube of the second face clicked owns the first finger")
            )
        else:
            form.spin_count.setToolTip(
                translate("MaxProFrame", "Number of fingers, at least 2; the tube before the corner owns the first one")
            )
            form.spin_depth.setToolTip(
                translate(
                    "MaxProFrame",
                    "Depth of the finger band across the bent wall; Automatic: the step depth of a Stepped joint",
                )
            )
            form.cb_flip.setToolTip(
                translate("MaxProFrame", "Swap the tubes: the tube after the corner owns the first finger")
            )
        form.spin_finger_width.setToolTip(
            translate(
                "MaxProFrame",
                "Width of every finger but the two outermost, centered; Even: the fingers split the tube evenly",
            )
        )
        form.combo_tip.setToolTip(
            translate("MaxProFrame", "Corners of each finger tip: Square, Chamfer or Round, to lead it in")
        )
        form.spin_tip_size.setToolTip(
            translate("MaxProFrame", "Chamfer leg or radius of the finger tip corners, in the inner wall plane")
        )
        form.spin_clearance.setToolTip(
            translate("MaxProFrame", "Gap between every pair of mating finger faces, half on each side")
        )

    def field_values(self):
        """The settings in the fields, by Interlock property: the Kind shown and those of that kind."""
        form = self.form
        values = {
            "Kind": self.kind,
            "Count": int(form.spin_count.value()),
            "FingerWidth": _plain(float(form.spin_finger_width.value())),
            "Tip": form.combo_tip.currentData(),
            "TipSize": _plain(float(form.spin_tip_size.value())),
            "Clearance": _plain(float(form.spin_clearance.value())),
        }
        if self.kind == TABS:
            values["Length"] = _plain(float(form.spin_length.value()))
        else:
            values["Depth"] = _plain(float(form.spin_depth.value()))
            values["Flip"] = bool(form.cb_flip.isChecked())
        return values

    def _enable_tip_size(self):
        self.form.spin_tip_size.setEnabled(self.form.combo_tip.currentData() in (CHAMFER, ROUND))

    # Picking.

    def _pick(self, obj, sub, point):
        """Take the face ``sub`` of ``obj`` clicked at ``point``: the second one of a pair that makes an Interlock
        makes it; a refused face or pair is not taken and says why."""
        if self.obj is not None:
            return
        click, refusal = clicked_face(obj, sub, point)
        if click is None:
            self._refusal = refusal
            return
        self._refusal = ""
        first = self.faces[0] if self.faces else None
        if first is None or _same_corner_tube(first, click):
            # An inner wall of the same tube again takes the place of the first one.
            self.faces = [click]
            return
        kind, made, refusal = self._deduce(first, click)
        if refusal is not None:
            # The newest face starts the next pair, unless only the first one is an inner wall at a folded corner.
            self.faces = [first] if first.fingers is not None and click.fingers is None else [click]
            self._refusal = refusal
            return
        self.faces = [first, click]
        self._make(kind, made)

    def _deduce(self, first, second):
        """(kind, what makes it, None) for the clicks ``first`` and ``second``: Fingers at a folded corner, else
        Fingers at an End Miter corner (a ``MiterOrder``), else Tabs at a T joint; (None, None, why) when they make
        neither (the module docstring says which refusal shows)."""
        if first.fingers is not None and second.fingers is not None:
            corner, fingers_refusal = self._fingers_corner(first.fingers, second.fingers)
            if fingers_refusal is None:
                return FINGERS, corner, None
        else:
            fingers_refusal = first.refusal if first.fingers is None else second.refusal
        # S7: a miter corner, made or refused, never goes on to a T joint.
        miter = miter_order(
            *(MiterFace(click.obj, click.sub, click.point) for click in (first, second)),
            **_without_kind(self._values[FINGERS]),
        )
        if miter.error is None:
            return FINGERS, miter, None
        if miter.found:
            return None, None, str(miter.error)
        faces = [TabFace(click.obj, click.sub, click.point) for click in (first, second)]
        order = tab_order(*faces, **_without_kind(self._values[TABS]))
        if order.error is None:
            return TABS, order, None
        if not order.found:
            if _fingers_meant(first, second):
                return None, None, fingers_refusal
            # S6: the inner walls at a corner of two tubes without End Miters, no T joint.
            unmitered = unmitered_corner(*(MiterFace(click.obj, click.sub, click.point) for click in (first, second)))
            if unmitered is not None:
                return None, None, str(unmitered)
        return None, None, str(order.error)

    @staticmethod
    def _fingers_corner(first, second):
        """((bar, piece_a, piece_b), None) for the folded corner whose inner walls are the PickedFaces ``first`` and
        ``second`` (pieces in chain order) when it has no interlock yet; else (None, why)."""
        chain, corner, refusal = picked_corner(first, second)
        if refusal is not None:
            return None, refusal
        piece_a, piece_b = (chain.segments[index].profile for index in (corner.before, corner.after))
        key = frozenset((piece_a.Name, piece_b.Name))
        taken = [obj for obj in second.bar.Interlocks if _alive(obj) and interlock_key(obj) == key]
        if taken:
            return None, translate(
                "MaxProFrame", "The corner between {} and {} has an interlock already: double-click {} to edit it."
            ).format(piece_a.Label, piece_b.Label, taken[0].Label)
        return (second.bar, piece_a, piece_b), None

    def _make(self, kind, made):
        """The Interlock of ``kind`` that ``made`` stands for (Fingers: (bar, piece_a, piece_b) in chain order, or the
        ``MiterOrder`` of a miter corner; Tabs: the ``TabOrder``), with the settings of that kind, shown in the
        fields."""
        miter = isinstance(made, MiterOrder)
        if kind != self.kind:
            self._fill(self._values[kind])
        if miter != self.miter:
            self.miter = miter
            self._show_kind()
        values = self.field_values()
        self._open_transaction("Create Interlock")
        if kind == FINGERS and not miter:
            bar, piece_a, piece_b = made
            self.bar = bar
            self.obj = make_interlock(bar, piece_a, piece_b, **values)
        else:
            try:
                if miter:
                    self.obj = make_miter_fingers(made.first, made.second, **_without_kind(values))
                else:
                    self.obj = make_tab_interlock(
                        made.crossbar.piece,
                        made.crossbar.sub,
                        made.rail.piece,
                        made.rail.sub,
                        crossbar_point=made.crossbar.point,
                        rail_point=made.rail.point,
                        **_without_kind(values),
                    )
            except InterlockError as error:
                self.doc.abortTransaction()
                self._transaction_open = False
                self.faces = self.faces[-1:]
                self._refusal = str(error)
                return
            self.bar = None
        self._recompute()

    def addSelection(self, doc, obj, sub, point=None):
        if not self._active() or self.edited is not None or self.obj is not None:
            return
        self._clicks.append((doc, obj, sub, point))
        # Never recompute during FreeCAD's selection observer dispatch.
        QtCore.QTimer.singleShot(0, self._take_clicks)

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, other):
        pass

    def _take_clicks(self):
        if self._active() and self._busy():
            # odd/tasks/panel-recompute-deadlock.md S3: no geometry while a recompute runs; the clicks wait for it.
            QtCore.QTimer.singleShot(GAP_DELAY_MS, self._take_clicks)
            return
        clicks, self._clicks = self._clicks, []
        for doc, obj, sub, point in clicks:
            if not self._active():
                return
            document = App.getDocument(doc) if doc in App.listDocuments() else None
            source = document.getObject(getattr(obj, "Name", obj)) if document is not None else None
            if source is not None:
                self._pick(source, sub, _click_point(point) if point is not None else None)
        if self._active():
            self._show()

    # Settings.

    def _changed(self, *args):
        if self._filling or not self._active():
            return
        self._values[self.kind] = self.field_values()
        self._enable_tip_size()
        self._apply()

    def _apply(self):
        """Give the Interlock the settings of the fields and recompute its bar; later while a recompute runs (a
        recompute pumps Qt events: a field changed meanwhile waits for it)."""
        if not self._active():
            return
        if self.obj is not None and _alive(self.obj):
            if self._busy():
                if not self._retrying:
                    self._retrying = True
                    QtCore.QTimer.singleShot(GAP_DELAY_MS, self._retry)
                return
            changed = False
            for prop, value in _without_kind(self.field_values()).items():
                if _plain(getattr(self.obj, prop)) != value:
                    setattr(self.obj, prop, value)
                    changed = True
            if changed:
                self._recompute()
        self._show()

    def _retry(self):
        self._retrying = False
        self._apply()

    def _busy(self):
        if self._recomputing:
            return True
        return any(getattr(doc, "Recomputing", False) for doc in App.listDocuments().values())

    def _invalid(self):
        """What the bar of a Fingers Interlock at a folded corner, or the pieces of a Tabs one or of one at a miter
        corner and the bars folding them, refuse."""
        if str(self.obj.Kind) == TABS or is_miter_interlock(self.obj):
            found = tab_pieces(self.obj) if str(self.obj.Kind) == TABS else miter_pieces(self.obj)
            pieces = [piece for piece in found if piece is not None]
            objects = pieces + [folding_bar(piece) for piece in pieces]
        else:
            objects = [self.bar]
        for obj in objects:
            if obj is not None and _alive(obj) and "Invalid" in obj.State:
                return [obj.getStatusString()]
        return []

    def _recompute(self):
        self._recomputing = True
        try:
            self.doc.recompute()
        finally:
            self._recomputing = False

    # Messages and OK.

    def problems(self):
        """What keeps OK disabled: the faces still to pick, or the refusal of the bar or the pieces."""
        if self.obj is None or not _alive(self.obj):
            if self._refusal:
                return [self._refusal]
            return [other_face_hint(self.faces[0]) if self.faces else pick_hint()]
        return self._invalid()

    def _show(self):
        if not self._active():
            return
        text = ""
        obj = self.obj
        if obj is not None and _alive(obj) and obj.PieceA is not None and obj.PieceB is not None:
            if str(obj.Kind) == TABS:
                text = translate("MaxProFrame", "T joint: {} → {}")
            else:
                text = translate("MaxProFrame", "Corner: {} → {}")
            text = text.format(obj.PieceA.Label, obj.PieceB.Label)
        self.form.label_corner.setText(text)
        self.form.message_label.setText("\n".join(self.problems()))
        self._enable_ok()
        self._draw_overlay()

    def _draw_overlay(self):
        """Draw the faces and the corner of the Interlock made or edited over the 3D view, as its settings and Flip
        are now; none before it is made. While a recompute runs it waits for it to end: the faces come from it
        (odd/tasks/panel-recompute-deadlock.md, S3)."""
        if not self._active():
            return
        if self._busy():
            if not self._overlay_waiting:
                self._overlay_waiting = True
                QtCore.QTimer.singleShot(GAP_DELAY_MS, self._overlay_later)
            return
        self._overlay.show(self.obj if self.obj is not None and _alive(self.obj) else None)

    def _overlay_later(self):
        self._overlay_waiting = False
        self._draw_overlay()

    def can_accept(self):
        """OK: the Interlock made and its bar valid, or nothing made since Apply and continue (OK just closes)."""
        if not self._active():
            return False
        return (self.edited is None and self._nothing_since_applied()) or not self.problems()

    def can_apply(self):
        """Apply and continue: an Interlock made since the last one kept, its bar valid."""
        return self._active() and self.edited is None and not self.problems()

    def ok_button_enabled(self):
        """Whether OK can be pressed: the dialog's button when it is shown."""
        if self._ok_button is not None:
            return self._ok_button.isEnabled()
        return self.can_accept()

    def _enable_ok(self):
        """OK and Apply and continue enabled as ``can_accept`` and ``can_apply`` say."""
        for button, enabled in ((self._ok_button, self.can_accept), (self._apply_button, self.can_apply)):
            if button is not None:
                button.setEnabled(enabled())

    # Dialog.

    def _active(self):
        return not self._closed

    def _open_transaction(self, name):
        if not self._transaction_open:
            self.doc.openTransaction(name)
            self._transaction_open = True

    def getStandardButtons(self):
        """OK and Cancel, and Apply (shown as Apply and continue) while creating."""
        buttons = QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
        if self.edited is None:
            buttons |= QtGui.QDialogButtonBox.Apply
        return buttons

    def modifyStandardButtons(self, box):
        """Keep the OK button and turn Apply into Apply and continue: both are disabled until the Interlock is made
        and while its bar is in error."""
        # The task view deletes the row when the dialog closes: no wrapper may outlive it.
        invalidate_wrapper_on_destroy(box)
        button = box.button(QtGui.QDialogButtonBox.Ok)
        if button is not None:
            invalidate_wrapper_on_destroy(button)
            button.destroyed.connect(self._ok_button_gone)
            self._ok_button = button
        button = box.button(QtGui.QDialogButtonBox.Apply)
        if button is not None:
            invalidate_wrapper_on_destroy(button)
            button.setText(translate("frameforge", "Apply and continue"))
            button.setToolTip(
                translate(
                    "MaxProFrame",
                    "Create this interlock in its own Undo step and keep the panel open: click the two faces of the "
                    "next one, with the same settings.",
                )
            )
            button.destroyed.connect(self._apply_button_gone)
            self._apply_button = button
        self._enable_ok()

    def clicked(self, button):
        """A button of the dialog's row: Apply creates the Interlock and continues, OK and Cancel run on their own."""
        if _button_id(button) == _button_id(QtGui.QDialogButtonBox.Apply):
            self.apply_and_continue()

    def _ok_button_gone(self, *args):
        self._ok_button = None

    def _apply_button_gone(self, *args):
        self._apply_button = None

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
        self._clicks = []
        self._overlay.remove()
        interlock_highlight.panel_closed(self)
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _discard(self):
        """Abort the transaction; with undo disabled, remove the new Interlock or put the edited one back by hand."""
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
        elif _alive(self.edited) and values_of(self.edited) != self._before:
            for prop, value in _without_kind(self._before).items():
                setattr(self.edited, prop, value)
            changed = True
        if changed:
            self.doc.recompute()

    def _close_edit(self):
        if self.edited is None or not _alive_document(self.doc):
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def reject(self):
        if self._recomputing:
            return False
        self.clean()
        self._discard()
        self._close_edit()
        Gui.Selection.clearSelection()
        return True

    def _nothing_since_applied(self):
        """Whether Apply and continue kept an Interlock and no other one is made since."""
        return self._applied and (self.obj is None or not _alive(self.obj))

    def apply_and_continue(self, *args):
        """Keep the Interlock as OK does, in its own Undo step, then wait for the faces of the next one.

        The settings stay for the next Interlock: only the corner changes with the next clicks. Only while creating.
        Returns whether the Interlock was kept.
        """
        if self.edited is not None or self._closed or self._recomputing:
            return False
        # A value still waiting for a recompute applies now.
        self._apply()
        if self.problems():
            return False
        # The next Interlock, in this session or the next, starts with these settings.
        remember_values(self.field_values())
        self.doc.commitTransaction()
        self._transaction_open = False
        self._applied = True
        # The next Interlock's transaction opens when its second face is clicked.
        self.obj = None
        self.bar = None
        self.faces = []
        self._refusal = ""
        Gui.Selection.clearSelection()
        self._show()
        return True

    def accept(self):
        if self._closed or self._recomputing:
            return False
        if self.edited is None and self._nothing_since_applied():
            # Nothing made since Apply and continue: OK just closes the panel.
            self.clean()
            Gui.Selection.clearSelection()
            return True
        # A value still waiting for a recompute applies now.
        self._apply()
        if self.problems():
            return False
        values = self.field_values()
        unchanged = self.edited is not None and values_of(self.edited) == self._before
        if not unchanged:
            # The next Interlock, in this session or the next, starts with these settings.
            remember_values(values)
        if unchanged:
            # Nothing changed in the end: no Undo step.
            self._discard()
        else:
            self.doc.commitTransaction()
        self._transaction_open = False
        self.clean()
        self._close_edit()
        Gui.Selection.clearSelection()
        return True


class InterlockCommand:
    """Interlock: fingers that locate the two tubes of a folded corner of a Folded Bar or of an End Miter corner,
    picked by their inner walls, or tabs on a crossbar end through slots in the rail at a T joint, picked by a crossbar
    wall and the rail face."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "Interlock.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_Interlock", "Interlock"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_Interlock",
                "<b>Interlock</b><br><br>Click two faces. The inner wall faces of the two tubes at a folded corner of "
                "a Folded Bar, or at an End Miter corner of two tubes cut against each other with Miter Ends: "
                "fingers cut by the laser at the inner vertex of the corner locate one tube on the other. A wall of a "
                "crossbar and the face of the rail it butts against (a T joint): tabs on the "
                "crossbar end go through slots cut in the rail. Set their count, width, tip and clearance in the "
                "panel. Double-click the Interlock to edit it.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        picks = []
        for selection in Gui.Selection.getSelectionEx():
            subs = selection.SubElementNames or ("",)
            points = list(selection.PickedPoints) + [None] * len(subs)
            for sub, point in zip(subs, points):
                picks.append((selection.Object, sub, _click_point(point) if point is not None else None))
        show_panel(InterlockTaskPanel(picks), picking=True)


interlock.EDIT_PANEL = edit_interlock

add_command("MaxProFrame_Interlock", InterlockCommand())

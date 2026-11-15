"""Interlock command: locating fingers at a folded corner of a Folded Bar, picked by two faces (odd/tasks/joint-tabs.md,
T3: S1, S6, S7).

The panel takes two faces of one Folded Bar, preselected when the command starts or clicked while it is open (as
Drill Hole takes them): each one is read at its picked point as a face of the tube under it (``folded_bar.segment_at``).
They must be the inner walls of the two tubes meeting at one folded corner of the bar: the planar faces on the inside
of that corner (S3). Those make one Interlock on the corner (``interlock.make_interlock``, in one transaction),
previewed on the bar; anything else creates nothing and the panel says what to pick (S6): a face of something that is
not a Folded Bar, a bend, an outer or a side wall, two tubes that do not meet at a folded corner, the open corner of a
closed frame, a corner that has an interlock. The settings (Kind, Count, FingerWidth, Tip, TipSize for a Chamfer or
Round tip only, Depth, Clearance, Flip) update the Interlock as they change and recompute the bar; whatever the bar
refuses (too few fingers, a tip too large, a band that does not fit) shows in the panel and keeps OK disabled. OK keeps
the Interlock, Cancel leaves the document as it was. A double click on an Interlock opens the same panel on it, without
picking (``interlock.EDIT_PANEL``); OK keeps the changes in one Undo step, Cancel puts its values back. A new
Interlock starts with the settings last kept with OK.
"""

import os
from collections import namedtuple

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe import interlock
from freecad.maxproframe._utils import is_foldedbar
from freecad.maxproframe.create_drill_hole_tool import _button_id, _click_point
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, _alive, _alive_document
from freecad.maxproframe.create_folded_bar_tool import _FinishOnEnter
from freecad.maxproframe.expression_fields import count_field, length_field
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.folded_bar import PICK_TOLERANCE, bar_chain, segment_at
from freecad.maxproframe.folded_chain import ChainError, base_profile, section_offset
from freecad.maxproframe.interlock import interlock_key, make_interlock
from freecad.maxproframe.interlock_geometry import CHAMFER, FINGERS, KINDS, ROUND, SQUARE, TIPS
from freecad.maxproframe.profile_pattern import global_shape
from freecad.maxproframe.qt_lifetime import invalidate_wrapper_on_destroy, keep_alive_until_destroyed

# Largest length and count the fields take (mm, fingers).
MAX_SIZE = 1000.0
MAX_COUNT = 99
# Cosine above which a face normal is the inner wall normal.
NORMAL_TOLERANCE = 1e-6
# The settings last kept, given to the next Interlock: (parameter, kind, Interlock property).
LAST_VALUE_PARAMS = (
    ("Interlock Kind", "String", "Kind"),
    ("Interlock Count", "Int", "Count"),
    ("Interlock Finger Width", "Float", "FingerWidth"),
    ("Interlock Tip", "String", "Tip"),
    ("Interlock Tip Size", "Float", "TipSize"),
    ("Interlock Depth", "Float", "Depth"),
    ("Interlock Clearance", "Float", "Clearance"),
    ("Interlock Flip", "Bool", "Flip"),
)
# The first Interlock ever: three even square fingers, the automatic depth and the clearance of a first Folded Corner.
FIRST_VALUES = {
    "Kind": FINGERS,
    "Count": 3,
    "FingerWidth": 0.0,
    "Tip": SQUARE,
    "TipSize": 0.0,
    "Depth": 0.0,
    "Clearance": 0.5,
    "Flip": False,
}

PickedFace = namedtuple("PickedFace", "bar profile normal point")
PickedFace.__doc__ = """A face picked on the Folded Bar ``bar``: the tube ``profile`` under it, the outward ``normal``
of its face and the picked ``point``, global."""


def last_values():
    """The settings a new Interlock starts with: the ones last kept, else ``FIRST_VALUES``."""
    param = get_param_group()
    values = {prop: getattr(param, f"Get{kind}")(name, FIRST_VALUES[prop]) for name, kind, prop in LAST_VALUE_PARAMS}
    if values["Kind"] not in KINDS:
        values["Kind"] = FIRST_VALUES["Kind"]
    if values["Tip"] not in TIPS:
        values["Tip"] = FIRST_VALUES["Tip"]
    return values


def remember_values(values):
    """Keep ``values`` (by Interlock property) for the next Interlock, between sessions."""
    param = get_param_group(writable=True)
    for name, kind, prop in LAST_VALUE_PARAMS:
        getattr(param, f"Set{kind}")(name, values[prop])


def _plain(value):
    """A property or field value as the panel compares and stores it."""
    value = value.Value if hasattr(value, "Value") else value
    return round(value, 9) if isinstance(value, float) else value


def values_of(obj):
    """The settings of the Interlock ``obj``, by property."""
    return {prop: _plain(getattr(obj, prop)) for _, _, prop in LAST_VALUE_PARAMS}


def interlock_bar(obj):
    """The Folded Bar listing the Interlock ``obj``, or None."""
    for parent in obj.InList:
        if is_foldedbar(parent) and obj in parent.Interlocks:
            return parent
    return None


# What the panel says (S6).


def pick_hint():
    return translate("MaxProFrame", "Click the inner walls of the two tubes at a folded corner of a Folded Bar.")


def other_face_hint():
    return translate("MaxProFrame", "Click the inner wall of the other tube at that corner.")


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


def show_panel(panel, picking=False):
    Gui.Control.showDialog(panel)
    if picking:
        Gui.Selection.addObserver(panel)


def edit_interlock(obj):
    """Double click on the Interlock ``obj``: its panel (``interlock.EDIT_PANEL``)."""
    show_panel(InterlockTaskPanel(edited=obj))


class InterlockTaskPanel:
    """Two inner wall faces of a folded corner of a Folded Bar, and the settings of the Interlock made there.

    ``picks`` are the faces preselected, (object, sub-element, picked point or None); as a selection observer (added by
    the command) the panel takes the faces clicked while it is open, until the Interlock is made. Apply and continue
    keeps it in its own Undo step and waits for the faces of the next one, with the same settings. With ``edited`` the
    panel changes that Interlock, without picking.
    """

    def __init__(self, picks=(), edited=None):
        self.edited = edited
        self.obj = edited
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
        self._loaded = last_values()
        self._before = values_of(edited) if edited is not None else None
        self.form = keep_alive_until_destroyed(self._build_form())
        self.form.destroyed.connect(self._form_gone)
        self._fill(self._before if edited is not None else self._loaded)
        self._connect()
        if edited is not None:
            self._open_transaction("Edit Interlock")
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
        form.combo_kind.setToolTip(
            translate("MaxProFrame", "Shape of the interlock: Fingers, at the inner vertex of a folded corner")
        )
        settings.addRow(translate("MaxProFrame", "Kind"), form.combo_kind)
        form.spin_count = count_field(1, MAX_COUNT, FIRST_VALUES["Count"])
        form.spin_count.setToolTip(
            translate("MaxProFrame", "Number of fingers, at least 2; the tube before the corner owns the first one")
        )
        settings.addRow(translate("MaxProFrame", "Count"), form.spin_count)
        form.spin_finger_width = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_finger_width.setSpecialValueText(translate("MaxProFrame", "Even"))
        form.spin_finger_width.setToolTip(
            translate(
                "MaxProFrame",
                "Width of every finger but the two outermost, centered; Even: the fingers split the tube evenly",
            )
        )
        settings.addRow(translate("MaxProFrame", "Finger width"), form.spin_finger_width)
        form.combo_tip = QtWidgets.QComboBox()
        for tip, text in (
            (SQUARE, translate("MaxProFrame", "Square")),
            (CHAMFER, translate("MaxProFrame", "Chamfer")),
            (ROUND, translate("MaxProFrame", "Round")),
        ):
            form.combo_tip.addItem(text, tip)
        form.combo_tip.setToolTip(
            translate("MaxProFrame", "Corners of each finger tip: Square, Chamfer or Round, to lead it in")
        )
        settings.addRow(translate("MaxProFrame", "Tip"), form.combo_tip)
        form.spin_tip_size = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_tip_size.setToolTip(
            translate("MaxProFrame", "Chamfer leg or radius of the finger tip corners, in the inner wall plane")
        )
        settings.addRow(translate("MaxProFrame", "Tip size"), form.spin_tip_size)
        form.spin_depth = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_depth.setSpecialValueText(translate("MaxProFrame", "Automatic"))
        form.spin_depth.setToolTip(
            translate(
                "MaxProFrame",
                "Depth of the finger band across the bent wall; Automatic: the step depth of a Stepped joint",
            )
        )
        settings.addRow(translate("MaxProFrame", "Depth"), form.spin_depth)
        form.spin_clearance = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_clearance.setToolTip(
            translate("MaxProFrame", "Gap between every pair of mating finger faces, half on each side")
        )
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
        return [form.spin_count, form.spin_finger_width, form.spin_tip_size, form.spin_depth, form.spin_clearance]

    def _connect(self):
        form = self.form
        for spin in self._spins(form):
            spin.valueChanged.connect(self._changed)
        form.combo_kind.currentIndexChanged.connect(self._changed)
        form.combo_tip.currentIndexChanged.connect(self._changed)
        form.cb_flip.toggled.connect(self._changed)

    def _fill(self, values):
        """Show ``values`` (by Interlock property) in the fields."""
        form = self.form
        self._filling = True
        try:
            form.combo_kind.setCurrentIndex(max(0, form.combo_kind.findData(values["Kind"])))
            form.spin_count.setValue(int(values["Count"]))
            form.spin_finger_width.setValue(float(values["FingerWidth"]))
            form.combo_tip.setCurrentIndex(max(0, form.combo_tip.findData(values["Tip"])))
            form.spin_tip_size.setValue(float(values["TipSize"]))
            form.spin_depth.setValue(float(values["Depth"]))
            form.spin_clearance.setValue(float(values["Clearance"]))
            form.cb_flip.setChecked(bool(values["Flip"]))
        finally:
            self._filling = False
        self._enable_tip_size()

    def field_values(self):
        """The settings in the fields, by Interlock property."""
        form = self.form
        return {
            "Kind": form.combo_kind.currentData(),
            "Count": int(form.spin_count.value()),
            "FingerWidth": _plain(float(form.spin_finger_width.value())),
            "Tip": form.combo_tip.currentData(),
            "TipSize": _plain(float(form.spin_tip_size.value())),
            "Depth": _plain(float(form.spin_depth.value())),
            "Clearance": _plain(float(form.spin_clearance.value())),
            "Flip": bool(form.cb_flip.isChecked()),
        }

    def _enable_tip_size(self):
        self.form.spin_tip_size.setEnabled(self.form.combo_tip.currentData() in (CHAMFER, ROUND))

    # Picking.

    def _pick(self, obj, sub, point):
        """Take the face ``sub`` of ``obj`` clicked at ``point``: the second one of a folded corner makes the
        Interlock; a refused one is not taken and says why."""
        if self.obj is not None:
            return
        face, refusal = picked_face(obj, sub, point)
        if face is None:
            self._refusal = refusal
            return
        self._refusal = ""
        first = self.faces[0] if self.faces else None
        if first is None or (first.bar.Name == face.bar.Name and first.profile.Name == face.profile.Name):
            # A face of the same tube again takes the place of the first one.
            self.faces = [face]
            return
        chain, corner, refusal = picked_corner(first, face)
        if refusal is None:
            piece_a, piece_b = (chain.segments[index].profile for index in (corner.before, corner.after))
            key = frozenset((piece_a.Name, piece_b.Name))
            taken = [obj for obj in face.bar.Interlocks if _alive(obj) and interlock_key(obj) == key]
            if taken:
                refusal = translate(
                    "MaxProFrame", "The corner between {} and {} has an interlock already: double-click {} to edit it."
                ).format(piece_a.Label, piece_b.Label, taken[0].Label)
        if refusal is not None:
            # The newest face starts the next pair.
            self.faces = [face]
            self._refusal = refusal
            return
        self.faces = [first, face]
        self._make(face.bar, piece_a, piece_b)

    def _make(self, bar, piece_a, piece_b):
        """The Interlock between ``piece_a`` and ``piece_b`` (chain order) with the settings of the fields."""
        self._open_transaction("Create Interlock")
        self.bar = bar
        self.obj = make_interlock(bar, piece_a, piece_b, **self.field_values())
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
            for prop, value in self.field_values().items():
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

    def _recompute(self):
        self._recomputing = True
        try:
            self.doc.recompute()
        finally:
            self._recomputing = False

    # Messages and OK.

    def problems(self):
        """What keeps OK disabled: the faces still to pick, or the refusal of the bar."""
        if self.obj is None or not _alive(self.obj):
            if self._refusal:
                return [self._refusal]
            return [other_face_hint() if self.faces else pick_hint()]
        if self.bar is not None and _alive(self.bar) and "Invalid" in self.bar.State:
            return [self.bar.getStatusString()]
        return []

    def _show(self):
        if not self._active():
            return
        text = ""
        if self.obj is not None and _alive(self.obj) and self.obj.PieceA is not None and self.obj.PieceB is not None:
            text = translate("MaxProFrame", "Corner: {} → {}").format(self.obj.PieceA.Label, self.obj.PieceB.Label)
        self.form.label_corner.setText(text)
        self.form.message_label.setText("\n".join(self.problems()))
        self._enable_ok()

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
                    "Create this interlock in its own Undo step and keep the panel open: click the inner walls at "
                    "the next folded corner, with the same settings.",
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
            for prop, value in self._before.items():
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
    """Interlock: fingers that locate the two tubes of a folded corner of a Folded Bar, picked by their inner walls."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "Interlock.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_Interlock", "Interlock"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_Interlock",
                "<b>Interlock</b><br><br>Click the inner wall faces of the two tubes at a folded corner of a Folded "
                "Bar: fingers cut by the laser at the inner vertex of the corner locate one tube on the other. Set "
                "their count, width, tip and clearance in the panel. Double-click the Interlock to edit it.",
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

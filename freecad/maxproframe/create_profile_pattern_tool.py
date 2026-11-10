import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import (
    get_profile_from_trimmedbody,
    is_extrudedcutout,
    is_group,
    is_part,
    is_pattern_link,
    is_profile,
    is_trimmedbody,
)
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, _alive_document, _failures
from freecad.maxproframe.create_extend_cut_tool import _in_document, _selected_items, _trim_chain
from freecad.maxproframe.expression_fields import count_field, length_field, length_text
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, translate
from freecad.maxproframe.profile_pattern import (
    BETWEEN_FACES,
    COUNT_AND_PITCH,
    DEFAULT_PITCH,
    MAX_COUNT,
    MODE_LABELS,
    MODES,
    SENSE_LABELS,
    SENSES,
    between_faces_problem,
    edge_direction,
    global_element,
    link_sub,
    make_profile_pattern,
)
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Longest pitch the field is sized for, in mm.
MAX_PITCH = 1e6
# Properties the panel sets, in the order it sets them.
VALUES = ("Mode", "Count", "Pitch", "Sense", "Edge", "Faces")


def is_piece(obj):
    """A piece a pattern repeats: a profile, a trimmed profile, a cutout or a drill hole."""
    return is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj)


def picked(obj, sub):
    """(object, sub-element) a click on ``sub`` of ``obj`` stands for: the first object of the path that is no Part
    or folder, with the rest of the path.

    A link to a Part holding the pattern would make it depend on itself; a Link of the path keeps its placement.
    """
    names = (sub or "").split(".")
    while len(names) > 1 and (is_part(obj) or is_group(obj)):
        child = obj.Document.getObject(names[0])
        if child is None:
            break
        obj, names = child, names[1:]
    return obj, ".".join(names)


def element_kind(obj, sub):
    """ "edge" for a straight edge, "face" for a planar face, else None."""
    element = global_element(obj, sub) if sub else None
    if isinstance(element, Part.Edge) and isinstance(element.Curve, Part.Line):
        return "edge"
    if isinstance(element, Part.Face) and isinstance(element.Surface, Part.Plane):
        return "face"
    return None


def show_panel(panel):
    Gui.Control.showDialog(panel)
    # Unresolved picks: a Link on the path keeps its placement (see picked).
    Gui.Selection.addObserver(panel, 0)


class ProfilePatternTaskPanel:
    """The piece, the direction edge, the mode, the count, the pitch or the faces of a Profile Pattern, previewed.

    The piece is the one selected (or the first one clicked); then a click on a straight edge sets the direction,
    and clicks on planar faces set the two faces of Between faces: a third face starts the pair again.

    Without ``edited`` the preview is the pattern OK keeps, made once a piece and an edge are picked, inside one
    transaction that Cancel aborts. With ``edited`` the edited pattern itself is the preview, inside the edit
    transaction: OK keeps the changes in one Undo step, or none when nothing changed; Cancel puts it back.
    Value changes are previewed once typing pauses, picks at once.
    """

    def __init__(self, selection=(), edited=None):
        self.edited = edited
        self.obj = edited
        self.doc = edited.Document if edited is not None else App.ActiveDocument
        self.piece = edited.Piece if edited is not None else None
        self.edge = link_sub(edited.Edge) if edited is not None else None
        self.faces = [(obj, sub) for obj, subs in edited.Faces for sub in subs] if edited is not None else []
        self._closed = False
        self._transaction_open = False
        self._messages = []
        self._error = ""
        self._previewed = None
        self._recomputing = False
        self._pending = False
        self._deferred = None
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(GAP_DELAY_MS)
        self._timer.timeout.connect(self._update_preview)
        # (profile, OffsetX, OffsetY) of the profile Between faces moves, as they were before the first preview:
        # Cancel puts them back, undo or not.
        self._offsets = None
        if edited is not None:
            self._before = self._values(edited)
            self._open_transaction()
        self.form = keep_alive_until_destroyed(self._build_form())
        self.form.destroyed.connect(self._form_gone)
        messages = self._add_items(selection) if edited is None else []
        if edited is not None:
            self._previewed = self._wanted()
        self._show(messages)
        if self._active():
            Gui.Selection.clearSelection()
        self._update_preview()

    # Form.

    def _build_form(self):
        obj = self.edited
        form = QtGui.QWidget()
        form.setWindowTitle(translate("frameforge", "Profile Pattern"))
        layout = QtGui.QVBoxLayout(form)

        form.groupBox_picks = QtGui.QGroupBox(translate("frameforge", "Piece and direction"))
        picks = QtGui.QVBoxLayout(form.groupBox_picks)
        form.piece_label = QtGui.QLabel()
        form.edge_label = QtGui.QLabel()
        form.faces_label = QtGui.QLabel()
        form.hint_label = QtGui.QLabel(
            translate(
                "frameforge",
                "Click a straight edge, of the frame for instance, for the direction. For Between faces, click the "
                "two planar faces the pieces go between.",
            )
        )
        for label in (form.piece_label, form.edge_label, form.faces_label, form.hint_label):
            label.setWordWrap(True)
            picks.addWidget(label)
        layout.addWidget(form.groupBox_picks)

        form.groupBox_pattern = QtGui.QGroupBox(translate("frameforge", "Pattern"))
        fields = QtGui.QFormLayout(form.groupBox_pattern)
        form.combo_mode = QtGui.QComboBox()
        for mode in MODES:
            form.combo_mode.addItem(translate("frameforge", MODE_LABELS[mode]), mode)
        form.combo_mode.setCurrentIndex(MODES.index(obj.Mode) if obj is not None else 0)
        fields.addRow(translate("frameforge", "Mode"), form.combo_mode)
        form.mode_label = QtGui.QLabel()
        form.mode_label.setWordWrap(True)
        form.mode_label.setStyleSheet("color: #c06000;")
        fields.addRow(form.mode_label)
        form.label_count = QtGui.QLabel()
        form.spin_count = count_field(1, MAX_COUNT, obj.Count if obj is not None else 1)
        fields.addRow(form.label_count, form.spin_count)
        form.label_pitch = QtGui.QLabel(translate("frameforge", "Pitch (center to center)"))
        form.spin_pitch = length_field(0.0, MAX_PITCH, obj.Pitch.Value if obj is not None else DEFAULT_PITCH)
        fields.addRow(form.label_pitch, form.spin_pitch)
        form.label_sense = QtGui.QLabel(translate("frameforge", "Sense"))
        form.combo_sense = QtGui.QComboBox()
        for sense in SENSES:
            form.combo_sense.addItem(translate("frameforge", SENSE_LABELS[sense]), sense)
        form.combo_sense.setCurrentIndex(SENSES.index(obj.Sense) if obj is not None else 0)
        fields.addRow(form.label_sense, form.combo_sense)
        form.result_label = QtGui.QLabel()
        fields.addRow(form.result_label)
        layout.addWidget(form.groupBox_pattern)

        form.message_label = QtGui.QLabel()
        form.message_label.setWordWrap(True)
        layout.addWidget(form.message_label)
        form.status_label = QtGui.QLabel()
        layout.addWidget(form.status_label)

        form.combo_mode.currentIndexChanged.connect(self._mode_changed)
        form.combo_sense.currentIndexChanged.connect(self._changed)
        form.spin_count.valueChanged.connect(self._changed)
        form.spin_pitch.valueChanged.connect(self._changed)
        return form

    def _mode(self):
        return self.form.combo_mode.currentData()

    def _show_fields(self):
        """Show the fields of the mode, and why Between faces cannot be used when it cannot."""
        form = self.form
        count_and_pitch = self._mode() == COUNT_AND_PITCH
        for widget in (form.label_pitch, form.spin_pitch, form.label_sense, form.combo_sense):
            widget.setVisible(count_and_pitch)
        form.faces_label.setVisible(not count_and_pitch)
        form.label_count.setText(
            translate("frameforge", "Copies")
            if count_and_pitch
            else translate("frameforge", "Pieces (the original included)")
        )
        problem = self._between_faces_problem()
        form.mode_label.setText(problem or "")
        form.mode_label.setVisible(bool(problem))
        item = form.combo_mode.model().item(MODES.index(BETWEEN_FACES))
        if item is not None:
            item.setEnabled(not problem or not count_and_pitch)
        text = ""
        if not count_and_pitch and self.obj is not None and _in_document(self.obj) and not self._error:
            text = translate("frameforge", "Gap: {}. Pitch: {}.").format(
                length_text(self.obj.Gap.Value), length_text(self.obj.Spacing.Value)
            )
        form.result_label.setText(text)
        form.result_label.setVisible(bool(text))

    def _between_faces_problem(self):
        if self.piece is None or self.edge is None:
            return None
        try:
            return between_faces_problem(self.piece, edge_direction(*self.edge))
        except Exception as error:
            return str(error)

    def _show(self, messages):
        self._messages = list(messages)
        form = self.form
        form.piece_label.setText(
            translate("frameforge", "Piece: {}").format(self.piece.Label)
            if self.piece is not None
            else translate("frameforge", "Piece: none")
        )
        form.edge_label.setText(
            translate("frameforge", "Direction: {}").format(self._name(self.edge))
            if self.edge is not None
            else translate("frameforge", "Direction: none")
        )
        form.faces_label.setText(
            translate("frameforge", "Faces: {}").format(", ".join(self._name(face) for face in self.faces) or "-")
        )
        self._show_fields()
        self._show_messages()

    @staticmethod
    def _name(item):
        obj, sub = item
        return f"{obj.Label} {sub}"

    def _show_messages(self):
        self.form.message_label.setText("\n".join(self._messages + ([self._error] if self._error else [])))
        if self._previewed != self._wanted():
            status = translate("frameforge", "Pending changes")
        elif self.obj is not None and _in_document(self.obj):
            status = translate("frameforge", "Preview updated")
        else:
            status = translate("frameforge", "No preview")
        self.form.status_label.setText(status)

    # Picks.

    def _add_items(self, selection):
        messages = []
        for obj, subs in selection:
            if self.piece is None and is_piece(obj):
                self.piece = obj
                continue
            for sub in subs:
                messages = self._pick(obj, sub)[1]
        if self.piece is None:
            messages = [self._piece_hint()]
        elif self.edge is None:
            messages = messages or [self._edge_hint()]
        return messages

    @staticmethod
    def _piece_hint():
        return translate(
            "frameforge", "Select the piece to repeat: click a profile, a trimmed profile, a cutout or a drill hole."
        )

    @staticmethod
    def _edge_hint():
        return translate("frameforge", "Click a straight edge for the direction of the copies.")

    def _pick(self, obj, sub):
        """Take a click on ``sub`` of ``obj``: (whether a pick changed, messages)."""
        obj, sub = picked(obj, sub)
        if self.piece is None:
            if self.edited is None and is_piece(obj):
                self.piece = obj
                return True, [] if self.edge is not None else [self._edge_hint()]
            return False, [self._piece_hint()]
        if is_pattern_link(obj):
            return False, [translate("frameforge", "Click the frame, not a copy of the pattern.")]
        kind = element_kind(obj, sub)
        if kind == "edge":
            self.edge = (obj, sub)
            return True, []
        if kind == "face":
            if obj in list(_trim_chain(self.piece)):
                return False, [translate("frameforge", "The faces must not be on the piece: it moves between them.")]
            self.faces = [(obj, sub)] if len(self.faces) >= 2 else self.faces + [(obj, sub)]
            return True, []
        return False, [
            translate("frameforge", "Click a straight edge for the direction, or a planar face for Between faces.")
        ]

    def addSelection(self, doc, obj, sub, other):
        if not self._active():
            return
        document = App.getDocument(doc) if doc in App.listDocuments() else None
        source = document.getObject(obj) if document is not None else None
        if source is None:
            return
        changed, messages = self._pick(source, sub)
        self._show(messages)
        if changed:
            # Never recompute during FreeCAD's selection observer dispatch.
            QtCore.QTimer.singleShot(0, self._update_preview)

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, other):
        pass

    # Preview.

    def _wanted(self):
        """What the preview must show: the picks and the values, or None when they make no pattern yet."""
        if self.piece is None or self.edge is None:
            return None
        form = self.form
        faces = tuple((obj.Name, sub) for obj, sub in self.faces)
        edge = (self.edge[0].Name, self.edge[1])
        return (
            self._mode(),
            form.spin_count.value(),
            form.spin_pitch.value(),
            form.combo_sense.currentData(),
            edge,
            faces,
        )

    def _problem(self):
        """What is missing for OK, or ""."""
        if self.piece is None:
            return self._piece_hint()
        if self.edge is None:
            return self._edge_hint()
        if self._mode() == BETWEEN_FACES:
            problem = self._between_faces_problem()
            if problem:
                return problem
            if len(self.faces) != 2:
                return translate("frameforge", "Click the two planar faces the pieces go between.")
        return ""

    def _changed(self, *args):
        if not self._active():
            return
        self._show_messages()
        self._timer.start()

    def _mode_changed(self, *args):
        if not self._active():
            return
        self._show_fields()
        self._timer.stop()
        QtCore.QTimer.singleShot(0, self._update_preview)

    def _open_transaction(self):
        if self._offsets is None:
            self._offsets = self._profile_offsets()
        if not self._transaction_open:
            self.doc.openTransaction("Edit Profile Pattern" if self.edited is not None else "Create Profile Pattern")
            self._transaction_open = True

    def _update_preview(self, *args, force=False):
        """Make the pattern shown match the panel; never during a recompute of the panel: it follows it."""
        if not self._active():
            return
        if self._recomputing:
            self._pending = True
            return
        self._recomputing = True
        try:
            while True:
                self._pending = False
                self._preview(force)
                if not (self._pending and self._active()) or self._deferred is not None:
                    break
        finally:
            self._recomputing = False
        if self._active():
            self._show_fields()
            self._show_messages()
        deferred, self._deferred = self._deferred, None
        if deferred is not None and self._active() and deferred():
            self._close_dialog()

    def _preview(self, force):
        wanted = self._wanted()
        if not force and wanted == self._previewed and (wanted is None or _in_document(self.obj)):
            return
        self._error = ""
        problem = self._problem()
        if wanted is None or (problem and self._mode() == BETWEEN_FACES):
            # Nothing to show yet, or Between faces still waits for its faces: the preview stays as it was.
            self._error = problem if wanted is not None else ""
            self._previewed = wanted
            return
        self._open_transaction()
        try:
            if self.obj is None or not _in_document(self.obj):
                self.obj = make_profile_pattern(self.piece, self.edge)
            self._apply_to(self.obj)
            self.doc.recompute()
            self._error = _failures([self.obj])
        except Exception as error:
            self._error = str(error)
        self._previewed = wanted

    def _apply_to(self, obj):
        mode, count, pitch, sense, _, _ = self._wanted()
        values = {
            "Mode": mode,
            "Count": count,
            "Pitch": pitch,
            "Sense": sense,
            "Edge": (self.edge[0], (self.edge[1],)),
            "Faces": [(face, (sub,)) for face, sub in self.faces],
        }
        for prop in VALUES:
            if self._values(obj)[VALUES.index(prop)] != self._value(values[prop], prop):
                setattr(obj, prop, values[prop])

    @staticmethod
    def _value(value, prop):
        """``value`` of ``prop`` as _values reads it."""
        if prop == "Pitch":
            return round(float(value), 6)
        if prop == "Edge":
            return (value[0].Name, tuple(value[1]))
        if prop == "Faces":
            return tuple((obj.Name, tuple(subs)) for obj, subs in value)
        return value

    @staticmethod
    def _values(obj):
        edge = link_sub(obj.Edge)
        return (
            obj.Mode,
            obj.Count,
            round(obj.Pitch.Value, 6),
            obj.Sense,
            (edge[0].Name, (edge[1],)) if edge else None,
            tuple((face.Name, tuple(subs)) for face, subs in obj.Faces),
        )

    def _profile_offsets(self):
        profile = get_profile_from_trimmedbody(self.piece) if self.piece is not None else None
        if profile is None or not hasattr(profile, "OffsetX"):
            return None
        return profile, profile.OffsetX.Value, profile.OffsetY.Value

    def _put_offsets_back(self):
        """Give the profile Between faces moved its offsets back, as Cancel does with undo disabled."""
        if self._offsets is None or not _in_document(self._offsets[0]):
            return False
        profile, offset_x, offset_y = self._offsets
        changed = False
        for prop, value in (("OffsetX", offset_x), ("OffsetY", offset_y)):
            if getattr(profile, prop).Value != value:
                setattr(profile, prop, value)
                changed = True
        return changed

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
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _discard(self):
        """Abort the transaction; with undo disabled, remove the new pattern or put the edited one back by hand."""
        if not _alive_document(self.doc):
            return
        if self._transaction_open:
            try:
                self.doc.abortTransaction()
            except Exception:
                pass
        self._transaction_open = False
        changed = False
        if self.edited is None and self.obj is not None and _in_document(self.obj):
            self.doc.removeObject(self.obj.Name)
            changed = True
        elif self.edited is not None and _in_document(self.edited) and self._values(self.edited) != self._before:
            for prop, value in zip(VALUES, self._before):
                if prop == "Edge":
                    value = (self.doc.getObject(value[0]), value[1]) if value else None
                elif prop == "Faces":
                    value = [(self.doc.getObject(name), subs) for name, subs in value]
                setattr(self.edited, prop, value)
            changed = True
        changed = self._put_offsets_back() or changed
        if changed:
            self.doc.recompute()

    def _close_edit(self):
        if not _alive_document(self.doc):
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def _close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def _defer(self, button):
        """A recompute pumps Qt events: OK or Cancel pressed during it waits for it to end."""
        if not self._recomputing:
            return False
        self._deferred = button
        return True

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def reject(self):
        if self._defer(self.reject):
            return False
        self.clean()
        self._discard()
        if self.edited is not None:
            self._close_edit()
        return True

    def accept(self):
        if self._defer(self.accept):
            return False
        problem = self._problem()
        if problem:
            self._show([problem])
            return False
        # OK keeps the current values even when a change is still pending.
        self._timer.stop()
        self._update_preview(force=True)
        if self._error:
            # The panel stays open with the error, to change the values.
            return False
        if self.edited is not None and self._values(self.edited) == self._before:
            # Nothing changed in the end: no Undo step.
            self._discard()
        else:
            self.doc.commitTransaction()
        self._transaction_open = False
        self.clean()
        if self.edited is not None:
            self._close_edit()
        return True


class ProfilePatternCommand:
    """Profile Pattern command: repeat a piece as Links along a straight edge."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "profile-pattern.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ProfilePattern", "Profile Pattern"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ProfilePattern",
                "<b>Profile Pattern</b><br><br>Select a profile, a trimmed profile, a cutout or a drill hole and "
                "click a straight edge for the direction: the copies are Links placed by count and pitch (in the "
                "edge's sense, inverted or symmetric) or between two faces with equal gaps. A change to the piece "
                "shows on every copy; the BOM counts them with its ID. Double-click the pattern to edit it.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        show_panel(ProfilePatternTaskPanel(_selected_items()))


add_command("MaxProFrame_ProfilePattern", ProfilePatternCommand())

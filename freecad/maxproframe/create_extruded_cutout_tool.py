import glob
import json
import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe.create_end_miter_tool import _alive, _base_profile, _failures
from freecad.maxproframe.create_extend_cut_tool import _selected_items, show_panel, trimmed_body_problem
from freecad.maxproframe.create_profiles_tool import place_in_container_of
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
from freecad.maxproframe.extruded_cutout import (
    CUT_TYPES,
    MAX_COUNT,
    ExtrudedCutout,
    ViewProviderExtrudedCutout,
    axis_positions,
    pattern_extents,
    wall_thickness,
)
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    PROFILESPATH,
    QT_TRANSLATE_NOOP,
    UIPATH,
    FormProxy,
    add_command,
    translate,
)
from freecad.maxproframe.frameforge_exceptions import FrameForgeException
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

# Cut type of the cutouts made from the face panel: the wall under the face only.
GUIDED_CUT_TYPE = "One wall"
# A face whose normal leans this much (cosine) along the profile axis is an end face, not a wall.
END_FACE_TOLERANCE = 1e-6
# Shown names of the cut types, in CUT_TYPES order.
CUT_TYPE_LABELS = {
    "Through All": QT_TRANSLATE_NOOP("frameforge", "Through All"),
    "Distance": QT_TRANSLATE_NOOP("frameforge", "Distance"),
    "One wall": QT_TRANSLATE_NOOP("frameforge", "One wall"),
}
# Depth range of a Distance cut, in mm.
MIN_DEPTH = 0.01
MAX_DEPTH = 1e6
# Rows of the Pattern group: (field name, prefix of the count and pitch properties of the cutout).
PATTERN_ROWS = (("backward", "AlongBackward"), ("forward", "AlongForward"))
PATTERN_PROPERTIES = tuple(f"{prop}{kind}" for _, prop in PATTERN_ROWS for kind in ("Count", "Pitch"))
# Longest pitch a Pattern field is as wide as.
LONGEST_PITCH = 9999.99
# Below this two lengths (mm) are the same.
LENGTH_TOLERANCE = 1e-6


def make_extruded_cutout(sketch, selected_face):
    """A cutout of the face ``selected_face`` (object, face name) by ``sketch``; the caller places it."""
    selected_object = selected_face[0]
    obj = selected_object.Document.addObject("Part::FeaturePython", f"{selected_object.Name}_Ex")
    # Named after the object, labelled after its label, as trims are (_Tr, _Mt).
    obj.Label = f"{selected_object.Label}_Ex"
    obj.addExtension("Part::AttachExtensionPython")
    ExtrudedCutout(obj, sketch, selected_face)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderExtrudedCutout(obj.ViewObject)
    return obj


def face_outline(obj, face):
    """Names of the edges of ``obj`` that bound its face ``face``."""
    edges = obj.Shape.getElement(face).Edges
    return [
        f"Edge{index}"
        for index, edge in enumerate(obj.Shape.Edges, start=1)
        if any(edge.isSame(face_edge) for face_edge in edges)
    ]


def make_cutout_sketch(obj, face):
    """A sketch on the face ``face`` of ``obj``, in its container, holding the face outline.

    The outline is external geometry, so construction: it builds no wire of the cut.
    """
    sketch = obj.Document.addObject("Sketcher::SketchObject", f"{obj.Name}_Sketch")
    sketch.Label = f"{obj.Label}_Sketch"
    # Sketcher rejects external geometry from outside the sketch's own container.
    place_in_container_of(sketch, obj)
    sketch.AttachmentSupport = [(obj, face)]
    sketch.MapMode = "FlatFace"
    for edge in face_outline(obj, face):
        sketch.addExternal(obj.Name, edge)
    return sketch


def face_problem(obj, sub):
    """Why the element ``sub`` of ``obj`` cannot be the face to cut, or None when it can."""
    problem = trimmed_body_problem(None, obj)
    if problem is not None:
        return problem
    if not sub:
        return translate("frameforge", "{}: pick one of its faces").format(obj.Label)
    face = obj.getSubObject(sub)
    if not isinstance(face, Part.Face):
        return translate("frameforge", "{}: {} is not a face").format(obj.Label, sub)
    if not isinstance(face.Surface, Part.Plane):
        return translate("frameforge", "{}: {} is not planar").format(obj.Label, sub)
    profile = _base_profile(obj)
    if profile is not None:
        # Profiles are extruded along their local Z: a wall face lies along it.
        axis = profile.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        if abs(face.normalAt(0, 0).dot(axis)) > END_FACE_TOLERANCE:
            return translate("frameforge", "{}: {} is an end face (wall thickness)").format(obj.Label, sub)
    return None


def _edit_sketch(doc_name, name, cutout_name=None, created=True):
    """Open the sketch ``name`` in the Sketcher, unless it is gone (undone, document closed).

    FreeCAD shows one task dialog at a time: another one open leaves the sketch closed.
    With ``cutout_name``, closing the sketch opens the depth panel of that cutout, a new one
    when ``created``.
    """
    doc = App.listDocuments().get(doc_name)
    sketch = doc.getObject(name) if doc is not None else None
    if sketch is not None and not Gui.Control.activeDialog():
        if cutout_name is not None:
            _DepthAfterSketch(doc_name, name, cutout_name, created)
        Gui.getDocument(doc_name).setEdit(sketch)


def _show_depth_panel(doc_name, cutout_name, created=True):
    """Open the depth panel of the cutout ``cutout_name``, unless it is gone or a dialog is open."""
    doc = App.listDocuments().get(doc_name)
    cutout = doc.getObject(cutout_name) if doc is not None else None
    if cutout is not None and not Gui.Control.activeDialog():
        Gui.Control.showDialog(CreateExtrudedCutoutTaskPanel(cutout, created=created))


class _DepthAfterSketch:
    """Opens the depth panel of a cutout once its sketch leaves the Sketcher, then stops listening."""

    # FreeCAD holds observers weakly enough to drop them: keep them alive while they listen.
    _listening = set()

    def __init__(self, doc_name, sketch_name, cutout_name, created=True):
        self.doc_name, self.sketch_name, self.cutout_name = doc_name, sketch_name, cutout_name
        self.created = created
        self._listening.add(self)
        Gui.addDocumentObserver(self)

    def slotResetEdit(self, vobj):
        obj = getattr(vobj, "Object", None)
        if obj is None or obj.Document.Name != self.doc_name or obj.Name != self.sketch_name:
            return
        self.stop()
        # The Sketcher closes its own task dialog after this signal.
        QtCore.QTimer.singleShot(0, lambda: _show_depth_panel(self.doc_name, self.cutout_name, self.created))

    def slotDeletedDocument(self, gui_doc):
        if gui_doc.Document.Name == self.doc_name:
            self.stop()

    def stop(self):
        self._listening.discard(self)
        try:
            Gui.removeDocumentObserver(self)
        except Exception:
            pass


class CutoutTaskPanel:
    """One planar face of a profile, trimmed profile or cutout; OK draws a cut on it.

    ``selection`` items are (object, sub-element names): the first usable face is the face to
    cut, every other item is explained. A click picks another face. OK creates, in one Undo
    step, a sketch on the face (see make_cutout_sketch) and the cutout made with it, then opens
    the sketch once the panel is closed. Nothing changes the document before OK.
    """

    def __init__(self, selection=()):
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(os.path.join(UIPATH, "create_cutout.ui")))
        # FreeCAD may close the dialog without OK or Cancel: the form is then deleted.
        self.form.destroyed.connect(self._form_gone)
        self._translate_form()
        self.face = None
        self._closed = False
        messages = []
        for obj, subs in selection:
            messages += self._add_item(obj, subs)
        self._show(messages)

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, translate("frameforge", "Cutout / Hole")),
            (form.groupBox_face.setTitle, translate("frameforge", "Face")),
            (
                form.hint_label.setText,
                translate(
                    "frameforge",
                    "Click another face to change it. OK creates a sketch on the face and opens it to draw the cutout.",
                ),
            ),
        ):
            setter(text)

    def _add_item(self, obj, subs):
        """Take the first usable face of ``obj`` among ``subs`` unless one is taken; return the problems."""
        problem = trimmed_body_problem(None, obj)
        if problem is not None:
            return [problem]
        messages = []
        for sub in subs:
            problem = face_problem(obj, sub)
            if problem is not None:
                messages.append(problem)
            elif self.face is None:
                self.face = (obj, sub)
            else:
                messages.append(
                    translate("frameforge", "{}: {} is not used, a cutout takes one face").format(obj.Label, sub)
                )
        return messages

    def _show(self, messages):
        if self.face is not None and not _alive(self.face[0]):
            self.face = None
        if self.face is None:
            text = translate("frameforge", "Click a planar face of a profile, a trimmed profile or a cutout.")
        else:
            obj, sub = self.face
            text = f"{obj.Label} ({obj.Name}) {sub}"
        self.form.face_label.setText(text)
        self.form.message_label.setText("\n".join(messages))

    def addSelection(self, doc, obj, sub, other):
        if self._closed:
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source is None:
            return
        problem = face_problem(source, sub)
        if problem is not None:
            self._show([problem])
            return
        self.face = (source, sub)
        # Ctrl+Click keeps the faces clicked before selected: only this last one is used.
        faces = sum(
            isinstance(element, Part.Face)
            for item in Gui.Selection.getSelectionEx("", 0)
            for element in item.SubObjects
        )
        self._show(
            [translate("frameforge", "Only the last face clicked is used: a cutout takes one face.")]
            if faces > 1
            else []
        )

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, other):
        pass

    def _form_gone(self, *args):
        self.clean()

    def closed(self):
        self.clean()

    def clean(self):
        self._closed = True
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def reject(self):
        # Nothing was created before OK.
        self.clean()
        return True

    def accept(self):
        if self.face is None or not _alive(self.face[0]):
            self.face = None
            self._show([translate("frameforge", "Select a planar face of a profile, a trimmed profile or a cutout.")])
            return False
        obj, sub = self.face
        doc = obj.Document
        doc.openTransaction("Create Cutout")
        try:
            sketch = make_cutout_sketch(obj, sub)
            cutout = make_extruded_cutout(sketch, (obj, [sub]))
            place_in_container_of(cutout, obj)
            cutout.CutType = GUIDED_CUT_TYPE
            doc.recompute()
            error = _failures([sketch, cutout])
        except Exception as exception:
            error = str(exception)
        if error:
            # Nothing is kept: the panel stays open with the error.
            doc.abortTransaction()
            doc.recompute()
            self._show([error])
            return False
        doc.commitTransaction()
        self.clean()
        # The sketch editor opens its own task dialog, once this one is closed; closing it opens the depth panel.
        doc_name, name, cutout_name = doc.Name, sketch.Name, cutout.Name
        QtCore.QTimer.singleShot(0, lambda: _edit_sketch(doc_name, name, cutout_name))
        return True


class CreateExtrudedCutoutTaskPanel:
    """Cut type and depth of a cutout, previewed live; OK keeps them in one Undo step.

    ``created``: the cutout was just made by the face panel and its sketch closed; Cancel then asks
    to delete the cutout with its sketch. Otherwise Cancel restores the values the panel opened with.
    Edit sketch keeps the values like OK, opens the sketch and opens this panel again once the
    sketch is closed, still ``created`` for a new cutout.
    """

    def __init__(self, obj, created=False):
        self.obj = obj
        self.created = created
        self.doc = obj.Document
        self._initial = (obj.CutType, obj.ExtrusionLength.Value)
        self._initial_pattern = self._pattern_of(obj)
        self._initial_expressions = expressions_of(obj, ("ExtrusionLength", *PATTERN_PROPERTIES))
        self.form = self._build_form()
        self.doc.openTransaction("Edit Cutout")

    def _build_form(self):
        form = QtGui.QWidget()
        form.setWindowTitle(translate("frameforge", "Cutout / Hole"))
        layout = QtGui.QFormLayout(form)
        form.label_cut_type = QtGui.QLabel(translate("frameforge", "Cut type"))
        form.combo_cut_type = QtGui.QComboBox()
        for cut_type in CUT_TYPES:
            form.combo_cut_type.addItem(translate("frameforge", CUT_TYPE_LABELS[cut_type]), cut_type)
        form.combo_cut_type.setCurrentIndex(max(form.combo_cut_type.findData(self.obj.CutType), 0))
        form.label_depth = QtGui.QLabel(translate("frameforge", "Depth"))
        form.spin_depth = length_field(MIN_DEPTH, MAX_DEPTH, self._initial_depth())
        bind(form.spin_depth, self.obj, "ExtrusionLength")
        form.button_edit_sketch = QtGui.QPushButton(translate("frameforge", "Edit sketch"))
        form.button_edit_sketch.setEnabled(self.obj.Sketch is not None)
        if self.obj.Sketch is not None and getattr(self.obj.Sketch, "ViewObject", None) is not None:
            form.button_edit_sketch.setIcon(self.obj.Sketch.ViewObject.Icon)
        layout.addRow(form.label_cut_type, form.combo_cut_type)
        layout.addRow(form.label_depth, form.spin_depth)
        self._build_pattern(form)
        layout.addRow(form.groupBox_pattern)
        form.warning_label = QtGui.QLabel()
        form.warning_label.setWordWrap(True)
        form.warning_label.setHidden(True)
        layout.addRow(form.warning_label)
        layout.addRow(form.button_edit_sketch)
        form.button_edit_sketch.clicked.connect(self._edit_sketch)
        form.combo_cut_type.currentIndexChanged.connect(self._apply)
        form.spin_depth.valueChanged.connect(self._apply)
        form.groupBox_pattern.toggled.connect(self._on_pattern_toggled)
        for spin in self._pattern_spins(form):
            spin.valueChanged.connect(self._apply)
        form.spin_depth.setEnabled(self.obj.CutType == "Distance")
        self._show_pattern(form)
        return form

    @staticmethod
    def _pattern_of(obj):
        """(count, pitch) of each row of ``obj``'s pattern."""
        return tuple((getattr(obj, f"{prop}Count"), getattr(obj, f"{prop}Pitch").Value) for _, prop in PATTERN_ROWS)

    def _build_pattern(self, form):
        """The checkable Pattern group: a count and a pitch on each side of the sketch, along the profile.

        The fields sit in ``form.pattern_fields``, hidden while the group is unchecked; it opens checked when
        the cutout has a cutout on either side.
        """
        form.groupBox_pattern = QtGui.QGroupBox(translate("frameforge", "Pattern"))
        form.groupBox_pattern.setCheckable(True)
        form.pattern_fields = QtGui.QWidget()
        QtGui.QVBoxLayout(form.groupBox_pattern).addWidget(form.pattern_fields)
        grid = QtGui.QGridLayout(form.pattern_fields)
        grid.setContentsMargins(0, 0, 0, 0)
        # The fields keep their width: the labels take the room left.
        grid.setColumnStretch(0, 1)
        form.label_pattern_count = QtGui.QLabel(translate("frameforge", "Cutouts per side"))
        form.label_pattern_pitch = QtGui.QLabel(translate("frameforge", "Pitch"))
        grid.addWidget(form.label_pattern_count, 0, 1)
        grid.addWidget(form.label_pattern_pitch, 0, 2)
        labels = (translate("frameforge", "← Backward"), translate("frameforge", "Forward →"))
        for line, ((row, prop), label) in enumerate(zip(PATTERN_ROWS, labels), start=1):
            count = count_field(0, MAX_COUNT, getattr(self.obj, f"{prop}Count"))
            pitch = length_field(MIN_DEPTH, MAX_DEPTH, getattr(self.obj, f"{prop}Pitch").Value)
            fit_width(count, MAX_COUNT)
            fit_width(pitch, LONGEST_PITCH)
            bind(count, self.obj, f"{prop}Count")
            bind(pitch, self.obj, f"{prop}Pitch")
            setattr(form, f"label_{row}", QtGui.QLabel(label))
            setattr(form, f"spin_{row}_count", count)
            setattr(form, f"spin_{row}_pitch", pitch)
            for column, widget in enumerate((getattr(form, f"label_{row}"), count, pitch)):
                grid.addWidget(widget, line, column)
        checked = any(count > 0 for count, _ in self._pattern_of(self.obj))
        form.groupBox_pattern.setChecked(checked)
        form.pattern_fields.setHidden(not checked)

    @staticmethod
    def _pattern_spins(form):
        """The count and pitch fields of the Pattern group, in PATTERN_PROPERTIES order."""
        return [getattr(form, f"spin_{row}_{kind}") for row, _ in PATTERN_ROWS for kind in ("count", "pitch")]

    def _pattern_wanted(self, form):
        """(count, pitch) of each row the cutout gets: none on either side while the group is unchecked."""
        checked = form.groupBox_pattern.isChecked()
        return tuple(
            (getattr(form, f"spin_{row}_count").value() if checked else 0, getattr(form, f"spin_{row}_pitch").value())
            for row, _ in PATTERN_ROWS
        )

    def _on_pattern_toggled(self, checked):
        self.form.pattern_fields.setHidden(not checked)
        self._apply()

    def _pattern_title(self, form):
        """ "Pattern", followed by the number of cutouts, the sketch included, when checked: "Pattern: 4 cutouts"."""
        if not form.groupBox_pattern.isChecked():
            return translate("frameforge", "Pattern")
        total = 1 + sum(count for count, _ in self._pattern_wanted(form))
        text = translate("frameforge", "{} cutout") if total == 1 else translate("frameforge", "{} cutouts")
        return translate("frameforge", "Pattern: {}").format(text.format(total))

    def _pattern_warnings(self, form):
        """Lines on the pattern while checked: cutouts that overlap, cutouts past the end of the face.

        Two cutouts of a side overlap when its pitch is smaller than the sketch along the profile, and so do
        its first cutout and the sketch.
        """
        if not form.groupBox_pattern.isChecked():
            return []
        extents = pattern_extents(self.obj)
        if extents is None:
            return []
        (sketch_min, sketch_max), (face_min, face_max) = extents
        length = sketch_max - sketch_min
        backward, forward = self._pattern_wanted(form)
        lines = []
        pitches = [pitch for count, pitch in (backward, forward) if count > 0 and pitch < length - LENGTH_TOLERANCE]
        if pitches:
            lines.append(
                translate(
                    "frameforge",
                    "The cutouts overlap: the pitch ({}) is smaller than the sketch along the profile ({}).",
                ).format(length_text(min(pitches)), length_text(length))
            )
        offsets = axis_positions(backward, forward, True)
        if (
            sketch_min + offsets[0] < face_min - LENGTH_TOLERANCE
            or sketch_max + offsets[-1] > face_max + LENGTH_TOLERANCE
        ):
            lines.append(translate("frameforge", "A cutout reaches past the end of the face."))
        return lines

    def _show_pattern(self, form):
        form.groupBox_pattern.setTitle(self._pattern_title(form))
        warnings = self._pattern_warnings(form)
        form.warning_label.setText("\n".join(warnings))
        form.warning_label.setHidden(not warnings)

    def _initial_depth(self):
        """The stored depth of a Distance cut, else the thickness of the wall under the face."""
        if self.obj.CutType == "Distance":
            return self.obj.ExtrusionLength.Value
        try:
            base, (face_name, *_) = self.obj.baseObject
            thickness = wall_thickness(base.Shape, base.Shape.getElement(face_name))
        except Exception:
            thickness = None
        return thickness if thickness else self.obj.ExtrusionLength.Value

    def _apply(self, *args):
        cut_type = self.form.combo_cut_type.currentData()
        self.form.spin_depth.setEnabled(cut_type == "Distance")
        self.obj.CutType = cut_type
        # An expression drives the depth on its own: the field only shows its value.
        if cut_type == "Distance" and expression_of(self.obj, "ExtrusionLength") is None:
            self.obj.ExtrusionLength = self.form.spin_depth.value()
        self._set_pattern(self._pattern_wanted(self.form))
        self.doc.recompute()
        self._show_pattern(self.form)

    def _set_pattern(self, pattern):
        """Give the cutout ``pattern`` ((count, pitch) per row); an expression drives its property on its own."""
        for (_, prop), (count, pitch) in zip(PATTERN_ROWS, pattern):
            for name, value in ((f"{prop}Count", count), (f"{prop}Pitch", pitch)):
                current = getattr(self.obj, name)
                current = current.Value if hasattr(current, "Value") else current
                if expression_of(self.obj, name) is None and abs(current - value) > LENGTH_TOLERANCE:
                    setattr(self.obj, name, value)

    def _edit_sketch(self, *args):
        """Keep the values in one Undo step, close the panel and open the sketch; closing it comes back here."""
        if self.obj.Sketch is None:
            return
        self.doc.commitTransaction()
        doc_name, sketch_name, cutout_name, created = self.doc.Name, self.obj.Sketch.Name, self.obj.Name, self.created
        # The button belongs to the dialog being closed: close it once its click is handled.
        QtCore.QTimer.singleShot(0, lambda: self._close_for_sketch(doc_name, sketch_name, cutout_name, created))

    def _close_for_sketch(self, doc_name, sketch_name, cutout_name, created):
        self._leave_edit()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        QtCore.QTimer.singleShot(0, lambda: _edit_sketch(doc_name, sketch_name, cutout_name, created))

    def _leave_edit(self):
        gui_doc = Gui.getDocument(self.doc.Name)
        in_edit = gui_doc.getInEdit() if gui_doc is not None else None
        if in_edit is not None and in_edit.Object == self.obj:
            gui_doc.resetEdit()

    def accept(self):
        self.doc.commitTransaction()
        self.doc.recompute()
        if self.obj.Sketch is not None and getattr(self.obj.Sketch, "ViewObject", None) is not None:
            self.obj.Sketch.ViewObject.hide()
        self._leave_edit()
        return True

    def reject(self):
        if self.created:
            answer = QtGui.QMessageBox.question(
                Gui.getMainWindow(),
                translate("frameforge", "Cutout / Hole"),
                translate("frameforge", "Delete the cutout and its sketch?"),
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                QtGui.QMessageBox.No,
            )
            if answer != QtGui.QMessageBox.Yes:
                return False
        self.doc.abortTransaction()
        if self.created:
            self._delete_cutout()
        else:
            # Abort undoes the preview; set the values again in case the transaction held nothing.
            restore_expressions(self.obj, self._initial_expressions)
            cut_type, depth = self._initial
            if self.obj.CutType != cut_type:
                self.obj.CutType = cut_type
            if abs(self.obj.ExtrusionLength.Value - depth) > 1e-9:
                self.obj.ExtrusionLength = depth
            self._set_pattern(self._initial_pattern)
            self._leave_edit()
        self.doc.recompute()
        return True

    def _delete_cutout(self):
        """Remove the new cutout and its sketch in one Undo step, showing the face's object again."""
        base = self.obj.baseObject[0] if self.obj.baseObject else None
        sketch = self.obj.Sketch
        self.doc.openTransaction("Delete Cutout")
        self.doc.removeObject(self.obj.Name)
        if sketch is not None:
            self.doc.removeObject(sketch.Name)
        self.doc.commitTransaction()
        if base is not None and getattr(base, "ViewObject", None) is not None:
            base.ViewObject.Visibility = True


def _is_face_and_sketch(selection):
    """Whether ``selection`` (getSelectionEx) is one face of an object and one sketch, in any order."""
    if len(selection) != 2:
        return False
    sketches = [sel for sel in selection if sel.Object.isDerivedFrom("Sketcher::SketchObject")]
    if len(sketches) != 1:
        return False
    (other,) = [sel for sel in selection if sel is not sketches[0]]
    return len(other.SubObjects) == 1 and isinstance(other.SubObjects[0], Part.Face)


class AddExtrudedCutoutCommandClass:
    """Cutout / Hole command: a cut from a sketch on a face."""

    def GetResources(self):
        return {
            # The name of a svg file available in the resources.
            "Pixmap": os.path.join(ICONPATH, "cutout-hole.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_AddExtrudeCutout", "Cutout / Hole"),
            "Accel": "E, C",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_AddExtrudeCutout",
                "<b>Cutout / Hole</b><br><br>Click a planar face of a profile, a trimmed profile or a cutout, then OK: a sketch holding the face outline is created on the face and opened. Draw the hole and close the sketch to cut it.<br><br>Or preselect one face and one sketch to cut with that sketch directly.",
            ),
        }

    def Activated(self):
        """Cut directly with one preselected face and sketch, else open the face panel."""
        if _is_face_and_sketch(Gui.Selection.getSelectionEx()):
            self._create_from_selection()
        else:
            show_panel(CutoutTaskPanel(_selected_items()))

    def _create_from_selection(self):
        """Create an Extruded Cutout object from the selected face and sketch."""
        # Get the selected object and face.
        selection = Gui.Selection.getSelectionEx()[0]
        # When user select first the sketch
        if selection.Object.isDerivedFrom("Sketcher::SketchObject"):
            # Get selected sketch
            cutSketch = selection.Object
            # Check if we have any sub-objects (faces) selected.
            selection = Gui.Selection.getSelectionEx()[1]
            if len(selection.SubObjects) == 0:
                raise FrameForgeException("No face selected. Please select a face.")
            # Get selected object.
            selected_object = selection.Object
            # Get the selected face.
            selected_face = [selected_object, selection.SubElementNames[0]]
        # When user select first the object face.
        else:
            # Check if we have any sub-objects (faces) selected.
            if len(selection.SubObjects) == 0:
                raise FrameForgeException("No face selected. Please select a face.")
            # Get selected object.
            selected_object = selection.Object
            # Get the selected face.
            selected_face = [selected_object, selection.SubElementNames[0]]
            # Get selected sketch.
            selection = Gui.Selection.getSelectionEx()[1]
            cutSketch = selection.Object

        if cutSketch is None or not selected_object.Shape:
            raise FrameForgeException("Both a valid sketch and an object with a shape must be selected.")

        App.ActiveDocument.openTransaction("Create Cutout")

        obj = make_extruded_cutout(cutSketch, selected_face)

        if len(selected_object.Parents) > 0:
            part = selected_object.Parents[-1][0]
            part.addObject(obj)

            part.addObject(cutSketch)

        App.ActiveDocument.commitTransaction()

        obj.recompute()

        panel = CreateExtrudedCutoutTaskPanel(obj)
        Gui.Control.showDialog(panel)

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None


add_command("MaxProFrame_AddExtrudeCutout", AddExtrudedCutoutCommandClass())

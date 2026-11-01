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
from freecad.maxproframe.extruded_cutout import ExtrudedCutout, ViewProviderExtrudedCutout
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

# Cut type of the cutouts made from the face panel.
GUIDED_CUT_TYPE = "Through All"
# A face whose normal leans this much (cosine) along the profile axis is an end face, not a wall.
END_FACE_TOLERANCE = 1e-6


def make_extruded_cutout(sketch, selected_face):
    """A cutout of the face ``selected_face`` (object, face name) by ``sketch``; the caller places it."""
    selected_object = selected_face[0]
    obj = selected_object.Document.addObject("Part::FeaturePython", f"{selected_object.Name}_Ex")
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


def _edit_sketch(doc_name, name):
    """Open the sketch ``name`` in the Sketcher, unless it is gone (undone, document closed).

    FreeCAD shows one task dialog at a time: another one open leaves the sketch closed.
    """
    doc = App.listDocuments().get(doc_name)
    sketch = doc.getObject(name) if doc is not None else None
    if sketch is not None and not Gui.Control.activeDialog():
        Gui.getDocument(doc_name).setEdit(sketch)


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
                translate("frameforge", "OK creates a sketch on the face and opens it to draw the cutout."),
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
        if problem is None:
            self.face = (source, sub)
        self._show([] if problem is None else [problem])

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
        # The sketch editor opens its own task dialog, once this one is closed.
        doc_name, name = doc.Name, sketch.Name
        QtCore.QTimer.singleShot(0, lambda: _edit_sketch(doc_name, name))
        return True


class CreateExtrudedCutoutTaskPanel:
    """TaskPanel pour FrameForge ExtrudedCutout (corrigé pour CutType)."""

    def __init__(self, obj):
        self.obj = obj

        self.cut_types = [
            "Through All",
            "Distance",
        ]

        self.form = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(self.form)

        layout.addWidget(QtGui.QLabel("Cut type"))
        self.comboCutType = QtGui.QComboBox()
        self.comboCutType.addItems(self.cut_types)
        try:
            current = str(self.obj.CutType)
            idx = self.cut_types.index(current)
        except Exception:
            idx = 0
        self.comboCutType.setCurrentIndex(idx)
        layout.addWidget(self.comboCutType)

        self.spinA = QtGui.QDoubleSpinBox()
        self.spinA.setRange(-1e6, 1e6)
        self.spinA.setDecimals(4)
        try:
            self.spinA.setValue(float(self.obj.ExtrusionLength1.Value))
        except Exception:
            try:
                self.spinA.setValue(float(self.obj.ExtrusionLength1))
            except Exception:
                self.spinA.setValue(500.0)

        layout.addWidget(QtGui.QLabel("Extrusion Length"))
        layout.addWidget(self.spinA)

        self.comboCutType.currentIndexChanged.connect(self.onCutTypeChanged)
        self.spinA.valueChanged.connect(self.onLengthAChanged)

        self.updateWidgetsVisibility()

    def onCutTypeChanged(self, idx):
        if 0 <= idx < len(self.cut_types):
            self.obj.CutType = self.cut_types[idx]
        else:
            self.obj.CutType = self.cut_types[0]
        self.updateWidgetsVisibility()

        self.obj.recompute()

    def onLengthAChanged(self, val):
        self.obj.ExtrusionLength = val
        self.obj.recompute()

    def updateWidgetsVisibility(self):
        """Afficher/masquer les widgets de longueur selon CutType selectionné."""
        ct = getattr(self.obj, "CutType", self.cut_types[0])
        self.spinA.setVisible(ct in ["Distance"])

    def open(self):
        App.Console.PrintMessage(translate("frameforge", "Opening Create Extrude Cutout\n"))

        App.ActiveDocument.openTransaction("Create Cutout")

    def accept(self):
        App.Console.PrintMessage(translate("frameforge", "Accepting Create Extrude Cutout\n"))
        try:
            if hasattr(self.obj, "Sketch") and self.obj.Sketch:
                try:
                    self.obj.Sketch.ViewObject.hide()
                except Exception:
                    pass
        except Exception:
            pass

        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()

        return True

    def reject(self):
        App.Console.PrintMessage(translate("frameforge", "Rejecting Create Extrude Cutout\n"))
        App.ActiveDocument.abortTransaction()

        return True


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
    """Add Extruded Cutout command."""

    def GetResources(self):
        return {
            # The name of a svg file available in the resources.
            "Pixmap": os.path.join(ICONPATH, "extruded-cutout.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_AddExtrudeCutout", "Extruded Cutout"),
            "Accel": "E, C",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_AddExtrudeCutout",
                "<b>Extruded cutout from a sketch extrusion</b><br><br>1. Select a face of the part (not a thickness face).<br>2. Select a closed sketch for the extruded cut.<br>3. Use the Property editor to adjust the other parameters.",
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

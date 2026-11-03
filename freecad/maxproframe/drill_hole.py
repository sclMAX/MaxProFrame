"""Drill Hole: round holes on a planar face of a profile, placed from a vertex of that face.

A drill hole is a cutout without a sketch: it keeps ``baseObject`` and the profile data of a cutout,
so the cut list, the IDs and the trims treat it as one.
"""

import os

import FreeCAD as App
import Part

from freecad.maxproframe._utils import get_childrens_from_extrudedcutout, get_profile_from_extrudedcutout
from freecad.maxproframe.extruded_cutout import (
    ExtrudedCutout,
    ViewProviderExtrudedCutout,
    _uncut_shape,
    cut_tools,
)
from freecad.maxproframe.ff_tools import ICONPATH, translate
from freecad.maxproframe.frameforge_exceptions import FrameForgeException

# Depth of a new drill hole: the wall under the face.
DEFAULT_CUT_TYPE = "One wall"
DEFAULT_DIAMETER = 10.0
DEFAULT_PITCH = 50.0
# Below this a component of a direction is zero.
TOLERANCE = 1e-9


def make_drill_hole(selected_face, vertex):
    """A drill hole on the face ``selected_face`` (object, (face name,)) placed from ``vertex``; the caller places it."""
    selected_object = selected_face[0]
    obj = selected_object.Document.addObject("Part::FeaturePython", f"{selected_object.Name}_Dh")
    # Named after the object, labelled after its label, as cutouts are (_Ex).
    obj.Label = f"{selected_object.Label}_Dh"
    obj.addExtension("Part::AttachExtensionPython")
    DrillHole(obj, selected_face, vertex)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderDrillHole(obj.ViewObject)
    return obj


def _inward(direction, vertex, center):
    """``direction``, or its opposite, so that it points from ``vertex`` into the face at ``center``."""
    return -direction if (center - vertex).dot(direction) < -TOLERANCE else direction


def face_axes(face, axis, vertex):
    """(along, across) unit directions on ``face`` from ``vertex``, both pointing into the face.

    ``along`` follows the profile ``axis``; ``across`` is square to it on the face.
    """
    normal = face.normalAt(0, 0)
    along = axis - normal * axis.dot(normal)
    if along.Length < TOLERANCE:
        raise FrameForgeException(translate("frameforge", "Drill Hole: the face is square to the profile axis."))
    along.normalize()
    across = normal.cross(along)
    center = face.CenterOfMass
    return _inward(along, vertex, center), _inward(across, vertex, center)


class DrillHole(ExtrudedCutout):
    def __init__(self, obj, selected_face, vertex):
        super().__init__(obj, None, selected_face)
        obj.setEditorMode("Sketch", 2)
        obj.CutType = DEFAULT_CUT_TYPE
        obj.addProperty(
            "App::PropertyString",
            "ReferenceVertex",
            "DrillHole",
            translate("frameforge", "Vertex of the face the hole is placed from"),
        ).ReferenceVertex = vertex
        obj.addProperty(
            "App::PropertyDistance",
            "OffsetAlong",
            "DrillHole",
            translate("frameforge", "Distance from the vertex to the first hole, along the profile"),
        )
        obj.addProperty(
            "App::PropertyDistance",
            "OffsetAcross",
            "DrillHole",
            translate("frameforge", "Distance from the vertex to the holes, across the profile"),
        )
        obj.addProperty(
            "App::PropertyLength", "Diameter", "DrillHole", translate("frameforge", "Hole diameter")
        ).Diameter = DEFAULT_DIAMETER
        obj.addProperty(
            "App::PropertyIntegerConstraint", "Count", "DrillHole", translate("frameforge", "Number of holes")
        ).Count = (1, 1, 1000, 1)
        obj.addProperty(
            "App::PropertyLength",
            "Pitch",
            "DrillHole",
            translate("frameforge", "Distance between two holes, along the profile"),
        ).Pitch = DEFAULT_PITCH

    def onDocumentRestored(self, obj):
        """Nothing to migrate yet: drill holes were created with every property."""

    def centers(self, fp):
        """Centers of the holes, on the face plane."""
        selected_object, (face_name, *_) = fp.baseObject
        face = selected_object.Shape.getElement(face_name)
        if not isinstance(face.Surface, Part.Plane):
            raise FrameForgeException(
                translate("frameforge", "Drill Hole: {} of {} is not planar.").format(face_name, selected_object.Label)
            )
        vertex = selected_object.Shape.getElement(fp.ReferenceVertex).Point
        profile = get_profile_from_extrudedcutout(fp)
        # Profiles are extruded along their local Z.
        axis = profile.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        along, across = face_axes(face, axis, vertex)
        first = vertex + along * fp.OffsetAlong.Value + across * fp.OffsetAcross.Value
        return face, [first + along * (fp.Pitch.Value * index) for index in range(fp.Count)]

    def execute(self, fp):
        """Drill the holes when the object is recomputed."""
        if fp.baseObject is None:
            raise FrameForgeException(translate("frameforge", "Drill Hole: no face to drill."))
        for child in get_childrens_from_extrudedcutout(fp.baseObject[0]):
            if getattr(child, "ViewObject", None) is not None:
                child.ViewObject.Visibility = False
        face, centers = self.centers(fp)
        normal = face.normalAt(0, 0)
        radius = fp.Diameter.Value / 2
        disks = [Part.Face(Part.Wire(Part.makeCircle(radius, center, normal))) for center in centers]
        shape = fp.baseObject[0].Shape
        middle = sum(centers, App.Vector()) * (1.0 / len(centers))
        tools = cut_tools(shape, disks, -normal, fp.CutType, fp.ExtrusionLength.Value, middle)
        # Cut the way a cutout is, so both sit where their base is.
        fp.Shape = shape.cut(tools) if tools is not None else _uncut_shape(shape)
        self._update_structure_data(fp)


class ViewProviderDrillHole(ViewProviderExtrudedCutout):
    def claimChildren(self):
        base = self.Object.baseObject[0] if self.Object.baseObject else None
        if base is None:
            return []
        if getattr(base, "ViewObject", None) is not None:
            base.ViewObject.Visibility = False
        return [base]

    def onDelete(self, fp, sub):
        if self.Object.baseObject:
            self.Object.baseObject[0].ViewObject.Visibility = True
        return True

    def setEdit(self, vobj, mode):
        return None

    def setupContextMenu(self, vobj, menu):
        """No sketch to edit."""

    def getIcon(self):
        return os.path.join(ICONPATH, "cutout-hole.svg")

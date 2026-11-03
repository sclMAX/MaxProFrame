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
# Distance (mm) within which a vertex or a face plane is where the reference snapshot was taken.
REFERENCE_TOLERANCE = 0.001


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
    return _plane_axes(face.normalAt(0, 0), axis, vertex, face.CenterOfMass)


def _plane_axes(normal, axis, vertex, center):
    """(along, across) unit directions on the plane of ``normal`` from ``vertex``, both pointing to ``center``."""
    along = axis - normal * axis.dot(normal)
    if along.Length < TOLERANCE:
        raise FrameForgeException(translate("frameforge", "Drill Hole: the face is square to the profile axis."))
    along.normalize()
    across = normal.cross(along)
    return _inward(along, vertex, center), _inward(across, vertex, center)


def _element(elements, name, prefix):
    """The element ``name`` (``prefix`` and a number from 1) of ``elements``, or None when there is none."""
    number = name[len(prefix) :]
    if name.startswith(prefix) and number.isdigit() and 1 <= int(number) <= len(elements):
        return elements[int(number) - 1]
    return None


def _resolve_vertex(shape, name, point):
    """The point of vertex ``name`` of ``shape`` when it is at ``point``, else of the nearest vertex at ``point``.

    None when no vertex of ``shape`` is at ``point`` any more.
    """
    named = _element(shape.Vertexes, name, "Vertex")
    if named is not None and named.Point.distanceToPoint(point) <= REFERENCE_TOLERANCE:
        return named.Point
    nearest = min(shape.Vertexes, key=lambda vertex: vertex.Point.distanceToPoint(point), default=None)
    if nearest is not None and nearest.Point.distanceToPoint(point) <= REFERENCE_TOLERANCE:
        return nearest.Point
    return None


def _on_plane(face, normal, point):
    """Whether ``face`` is planar, faces along ``normal`` and its plane holds ``point``."""
    return (
        isinstance(face.Surface, Part.Plane)
        and face.normalAt(0, 0).getAngle(normal) < TOLERANCE**0.5
        and abs((point - face.CenterOfMass).dot(normal)) <= REFERENCE_TOLERANCE
    )


def _resolve_face(shape, name, normal, point):
    """Face ``name`` of ``shape`` when it is on the reference plane, else the nearest face on it, else None."""
    named = _element(shape.Faces, name, "Face")
    if named is not None and _on_plane(named, normal, point):
        return named
    faces = [face for face in shape.Faces if _on_plane(face, normal, point)]
    return min(faces, key=lambda face: face.distToShape(Part.Vertex(point))[0], default=None)


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
        # Snapshot of the reference, local to the profile, taken from the face and vertex named ReferenceName.
        for name, kind, tip in (
            (
                "ReferencePoint",
                "App::PropertyVector",
                translate("frameforge", "Reference vertex position, local to the profile"),
            ),
            (
                "ReferenceNormal",
                "App::PropertyVector",
                translate("frameforge", "Reference face normal, local to the profile"),
            ),
            (
                "ReferenceName",
                "App::PropertyString",
                translate("frameforge", "Face and vertex the reference was taken from"),
            ),
        ):
            obj.addProperty(kind, name, "DrillHole", tip)
            obj.setEditorMode(name, ["ReadOnly", "Hidden"])
        obj.addProperty(
            "App::PropertyString",
            "ReferenceWarning",
            "DrillHole",
            translate("frameforge", "Set when the reference vertex is gone and the hole kept its place"),
        )
        obj.setEditorMode("ReferenceWarning", 1)

    def onDocumentRestored(self, obj):
        """Nothing to migrate yet: drill holes were created with every property."""

    def reference(self, fp):
        """(vertex point, face normal, face center) the holes are placed from.

        A face or vertex other than the snapshot's (a new hole, or picked by the user) takes a new
        snapshot. Otherwise the snapshot is found again on the base shape: the named vertex, else
        the vertex now at its place; when none is, the hole keeps the snapshot and warns.
        """
        selected_object, (face_name, *_) = fp.baseObject
        shape = selected_object.Shape
        placement = get_profile_from_extrudedcutout(fp).Placement
        name = f"{face_name}/{fp.ReferenceVertex}"
        if fp.ReferenceName != name:
            face = shape.getElement(face_name)
            if not isinstance(face.Surface, Part.Plane):
                raise FrameForgeException(
                    translate("frameforge", "Drill Hole: {} of {} is not planar.").format(
                        face_name, selected_object.Label
                    )
                )
            vertex = shape.getElement(fp.ReferenceVertex).Point
            normal = face.normalAt(0, 0)
            fp.ReferencePoint = placement.inverse().multVec(vertex)
            fp.ReferenceNormal = placement.Rotation.inverted().multVec(normal)
            fp.ReferenceName = name
            self._warn(fp, "")
            return vertex, normal, face.CenterOfMass
        point = placement.multVec(fp.ReferencePoint)
        normal = placement.Rotation.multVec(fp.ReferenceNormal)
        vertex = _resolve_vertex(shape, fp.ReferenceVertex, point)
        face = _resolve_face(shape, face_name, normal, point)
        if vertex is None or face is None:
            self._warn(fp, translate("frameforge", "The reference vertex changed: check the hole."))
        else:
            self._warn(fp, "")
        center = face.CenterOfMass if face is not None else shape.BoundBox.Center
        return (vertex if vertex is not None else point), normal, center

    def _warn(self, fp, warning):
        if warning:
            App.Console.PrintWarning(f"{fp.Label}: {warning}\n")
        if fp.ReferenceWarning != warning:
            fp.ReferenceWarning = warning

    def centers(self, fp):
        """(face normal, centers of the holes on the face plane)."""
        vertex, normal, center = self.reference(fp)
        profile = get_profile_from_extrudedcutout(fp)
        # Profiles are extruded along their local Z.
        axis = profile.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        along, across = _plane_axes(normal, axis, vertex, center)
        first = vertex + along * fp.OffsetAlong.Value + across * fp.OffsetAcross.Value
        return normal, [first + along * (fp.Pitch.Value * index) for index in range(fp.Count)]

    def execute(self, fp):
        """Drill the holes when the object is recomputed."""
        if fp.baseObject is None:
            raise FrameForgeException(translate("frameforge", "Drill Hole: no face to drill."))
        for child in get_childrens_from_extrudedcutout(fp.baseObject[0]):
            if getattr(child, "ViewObject", None) is not None:
                child.ViewObject.Visibility = False
        normal, centers = self.centers(fp)
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

"""Drill Hole: round holes on a planar face of a profile, placed from a vertex of that face.

A drill hole is a cutout without a sketch: it keeps ``baseObject`` and the profile data of a cutout,
so the cut list, the IDs and the trims treat it as one.
"""

import os
import re

import FreeCAD as App
import Part

from freecad.maxproframe._utils import (
    get_childrens_from_extrudedcutout,
    get_profile_from_extrudedcutout,
    is_extrudedcutout,
    is_foldedbar,
    is_trimmedbody,
    restore_length,
)
from freecad.maxproframe.extruded_cutout import (
    ExtrudedCutout,
    ViewProviderExtrudedCutout,
    _uncut_shape,
    axis_positions,
    cut_tools,
    measured_piece,
)
from freecad.maxproframe.ff_tools import ICONPATH, place_in_container_of, translate
from freecad.maxproframe.frameforge_exceptions import FrameForgeException
from freecad.maxproframe.profile import section_shift

# Depth of a new drill hole: the wall under the face.
DEFAULT_CUT_TYPE = "One wall"
DEFAULT_DIAMETER = 10.0
DEFAULT_PITCH = 50.0
# Holes a pattern side adds, and holes a drill hole makes at most.
MAX_COUNT = 1000
MAX_HOLES = 1000
# Prefixes of the pattern properties: a count and a pitch on each side of the point, along and across.
PATTERN_SIDES = ("AlongBackward", "AlongForward", "AcrossBackward", "AcrossForward")
# Below this a component of a direction is zero.
TOLERANCE = 1e-9
# Distance (mm) within which a vertex or a face plane is where the reference snapshot was taken.
REFERENCE_TOLERANCE = 0.001
# Prefix FreeCAD gives a linked element it cannot find any more after the linked shape changed.
MISSING_ELEMENT_PREFIX = "?"


def make_drill_hole(selected_face, vertex):
    """A drill hole on the face ``selected_face`` (object, (face name,)) placed from ``vertex``.

    It is in the folder or Part/Body holding the object of the face.
    """
    selected_object = selected_face[0]
    obj = selected_object.Document.addObject("Part::FeaturePython", f"{selected_object.Name}_Dh")
    # Named after the object, labelled after its label, as cutouts are (_Ex).
    obj.Label = f"{selected_object.Label}_Dh"
    obj.addExtension("Part::AttachExtensionPython")
    # Placed before it links to its base, so the Part does not drag in what the base links to.
    place_in_container_of(obj, selected_object)
    DrillHole(obj, selected_face, vertex)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderDrillHole(obj.ViewObject)
    return obj


def _inward(direction, vertex, center):
    """``direction``, or its opposite, so that it points from ``vertex`` into the face at ``center``."""
    return -direction if (center - vertex).dot(direction) < -TOLERANCE else direction


def face_axes(face, axis, vertex, center_along=False, center_across=False):
    """(along, across) unit directions the offsets go in on ``face`` (see _plane_axes).

    ``along`` follows the profile ``axis``; ``across`` is square to it on the face.
    """
    return _plane_axes(face.normalAt(0, 0), axis, vertex, face.CenterOfMass, center_along, center_across)


def _plane_axes(normal, axis, vertex, center, center_along=False, center_across=False):
    """(along, across) unit directions the offsets go in on the plane of ``normal``.

    A direction measured from ``vertex`` points from it to ``center``, into the face. A centered one
    (``center_along``, ``center_across``) is fixed whatever the vertex: along toward the end of the
    path of the profile, across ``normal`` x that along.
    """
    along = axis - normal * axis.dot(normal)
    if along.Length < TOLERANCE:
        raise FrameForgeException(translate("frameforge", "Drill Hole: the face is square to the profile axis."))
    along.normalize()
    across = normal.cross(along)
    # A profile is attached at the end of its path and extruded back to its start: its path runs against
    # its ``axis``.
    path = -along
    return (
        path if center_along else _inward(along, vertex, center),
        normal.cross(path) if center_across else _inward(across, vertex, center),
    )


def _middle_shift(face, vertex, direction):
    """Distance along ``direction`` from ``vertex`` to the middle of the extent of ``face``; 0 without a face."""
    if face is None or not face.Vertexes:
        return 0.0
    distances = [(point.Point - vertex).dot(direction) for point in face.Vertexes]
    return (min(distances) + max(distances)) / 2


def offset_origin(face, vertex, along, across, center_along, center_across):
    """Point the offsets are measured from: ``vertex``, moved to the middle of ``face`` along and/or across."""
    origin = vertex
    if center_along:
        origin = origin + along * _middle_shift(face, vertex, along)
    if center_across:
        origin = origin + across * _middle_shift(face, vertex, across)
    return origin


def _add_reference_anchor(obj, shift=None):
    """Give ``obj`` the anchor shift of its section when the reference was taken, unless it has it."""
    if hasattr(obj, "ReferenceAnchor"):
        return
    obj.addProperty(
        "App::PropertyVector",
        "ReferenceAnchor",
        "DrillHole",
        translate("frameforge", "Where the anchor put the section when the reference was taken, local to the profile"),
    )
    obj.setEditorMode("ReferenceAnchor", ["ReadOnly", "Hidden"])
    if shift is not None:
        obj.ReferenceAnchor = shift


def _add_center_properties(obj):
    """Add CenterAlong and CenterAcross, off, when ``obj`` has not got them."""
    for name, tip in (
        ("CenterAlong", translate("frameforge", "Measure the offset along from the middle of the face length")),
        ("CenterAcross", translate("frameforge", "Measure the offset across from the middle of the face width")),
    ):
        if not hasattr(obj, name):
            obj.addProperty("App::PropertyBool", name, "DrillHole", tip)
            setattr(obj, name, False)


def _pattern_tips():
    """{property: tooltip} of the pattern properties, in the order they are added."""
    return {
        "AlongBackwardCount": translate("frameforge", "Number of holes backward of the point, along the profile"),
        "AlongBackwardPitch": translate(
            "frameforge", "Distance between the holes backward of the point, along the profile"
        ),
        "AlongForwardCount": translate("frameforge", "Number of holes forward of the point, along the profile"),
        "AlongForwardPitch": translate(
            "frameforge", "Distance between the holes forward of the point, along the profile"
        ),
        "AcrossBackwardCount": translate("frameforge", "Number of holes backward of the point, across the profile"),
        "AcrossBackwardPitch": translate(
            "frameforge", "Distance between the holes backward of the point, across the profile"
        ),
        "AcrossForwardCount": translate("frameforge", "Number of holes forward of the point, across the profile"),
        "AcrossForwardPitch": translate(
            "frameforge", "Distance between the holes forward of the point, across the profile"
        ),
        "HoleAtPoint": translate("frameforge", "Drill a hole at the point the offsets give"),
    }


def _add_pattern_properties(obj):
    """Add the pattern properties ``obj`` has not got: no count on any side, a hole at the point."""
    for name, tip in _pattern_tips().items():
        if hasattr(obj, name):
            continue
        if name.endswith("Count"):
            obj.addProperty("App::PropertyIntegerConstraint", name, "DrillHole", tip)
            setattr(obj, name, (0, 0, MAX_COUNT, 1))
        elif name.endswith("Pitch"):
            obj.addProperty("App::PropertyLength", name, "DrillHole", tip)
            setattr(obj, name, DEFAULT_PITCH)
        else:
            obj.addProperty("App::PropertyBool", name, "DrillHole", tip)
            setattr(obj, name, True)


def _migrate_count_pitch(obj):
    """Turn the Count and Pitch of a drill hole saved by 1.5.0 into holes forward along (S4).

    Count holes from the point, Pitch apart, are the hole at the point and Count - 1 forward. An
    expression on Pitch moves to AlongForwardPitch, one on Count becomes ``(expression) - 1`` on
    AlongForwardCount. Count and Pitch are then removed.
    """
    if not (hasattr(obj, "Count") and hasattr(obj, "Pitch")) or hasattr(obj, "AlongForwardCount"):
        return
    count, pitch = obj.Count, obj.Pitch.Value
    expressions = {path.lstrip("."): expression for path, expression in obj.ExpressionEngine}
    _add_pattern_properties(obj)
    obj.AlongForwardCount = max(count - 1, 0)
    obj.AlongForwardPitch = pitch
    for old, new, expression in (
        ("Pitch", "AlongForwardPitch", expressions.get("Pitch")),
        ("Count", "AlongForwardCount", f"({expressions['Count']}) - 1" if expressions.get("Count") else None),
    ):
        if expressions.get(old):
            obj.setExpression(old, None)
        if expression:
            obj.setExpression(new, expression)
        obj.removeProperty(old)


def _pattern(fp):
    """(hole at the point, {side: (count, pitch)}) of the drill hole ``fp``.

    A drill hole saved with Count and Pitch has not got the pattern until it is restored: the same holes.
    """
    if not hasattr(fp, "AlongForwardCount") and hasattr(fp, "Count"):
        sides = {side: (0, 0.0) for side in PATTERN_SIDES}
        sides["AlongForward"] = (max(fp.Count - 1, 0), fp.Pitch.Value)
        return True, sides
    return fp.HoleAtPoint, {
        side: (getattr(fp, f"{side}Count"), getattr(fp, f"{side}Pitch").Value) for side in PATTERN_SIDES
    }


def _pattern_axes(at_point, sides):
    """(along, across) positions of the pattern ``sides``, ([], []) when it has no hole at all.

    An axis without holes still holds the point's line (position 0) for the holes of the other axis.
    """
    along = axis_positions(sides["AlongBackward"], sides["AlongForward"], at_point)
    across = axis_positions(sides["AcrossBackward"], sides["AcrossForward"], at_point)
    if not along and not across:
        return [], []
    return along or [0.0], across or [0.0]


def pattern_count(at_point, sides):
    """Number of holes of the pattern, as pattern_positions makes them: 0 when it has none.

    Not limited to MAX_HOLES, which pattern_positions refuses.
    """
    along, across = _pattern_axes(at_point, sides)
    return len(along) * len(across)


def pattern_positions(at_point, sides):
    """(along, across) positions of the holes from the point: every combination of one along and one across.

    An axis without holes still holds the point's line (position 0) for the holes of the other axis.
    Raise when there is no hole at all or more than MAX_HOLES.
    """
    along, across = _pattern_axes(at_point, sides)
    if not along:
        raise FrameForgeException(
            translate(
                "frameforge", "Drill Hole: no hole to drill. Check Hole at the point or set a count in the pattern."
            )
        )
    total = len(along) * len(across)
    if total > MAX_HOLES:
        raise FrameForgeException(
            translate("frameforge", "Drill Hole: the pattern makes {} holes, at most {}.").format(total, MAX_HOLES)
        )
    return [(a, b) for b in across for a in along]


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


def _builds_on(obj, base):
    """Whether ``obj`` is a cutout or a trim made from ``base``."""
    if is_extrudedcutout(obj):
        return bool(obj.baseObject) and obj.baseObject[0] == base
    return is_trimmedbody(obj) and obj.TrimmedBody == base


def _show_unless_built_on(base, left_by):
    """Show ``base`` again once ``left_by`` no longer cuts it, unless another cutout or trim builds on it."""
    if getattr(base, "ViewObject", None) is None or base.Document is None:
        return
    if any(_builds_on(obj, base) for obj in base.InList if obj != left_by):
        return
    base.ViewObject.Visibility = True


def _relabel(fp, left, base):
    """Label ``fp`` after ``base`` when it still has the label it got from ``left``; a user label stays."""
    # FreeCAD may number a duplicate label: Profile_Dh001.
    if re.fullmatch(re.escape(f"{left.Label}_Dh") + r"\d*", fp.Label):
        fp.Label = f"{base.Label}_Dh"


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
            translate(
                "frameforge",
                "Distance from the picked point to the pattern origin (the hole at the point), along the profile",
            ),
        )
        obj.addProperty(
            "App::PropertyDistance",
            "OffsetAcross",
            "DrillHole",
            translate(
                "frameforge",
                "Distance from the picked point to the pattern origin (the hole at the point), across the profile",
            ),
        )
        obj.addProperty(
            "App::PropertyLength", "Diameter", "DrillHole", translate("frameforge", "Hole diameter")
        ).Diameter = DEFAULT_DIAMETER
        _add_pattern_properties(obj)
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
        _add_reference_anchor(obj)
        obj.addProperty(
            "App::PropertyString",
            "ReferenceWarning",
            "DrillHole",
            translate("frameforge", "Set when the reference vertex is gone and the hole kept its place"),
        )
        obj.setEditorMode("ReferenceWarning", 1)
        _add_center_properties(obj)

    def add_pattern_properties(self, obj):
        """None of a cutout's: a drill hole has its own pattern, in its DrillHole group (_add_pattern_properties)."""

    def onDocumentRestored(self, obj):
        """Drill holes saved before CenterAlong and CenterAcross gain them off: measured from their vertex.

        Drill holes saved with Count and Pitch (1.5.0) get the same holes as a pattern; any other one
        gains the pattern properties it lacks: one hole at the point.
        """
        _add_center_properties(obj)
        _migrate_count_pitch(obj)
        _add_pattern_properties(obj)
        # Saved before ReferenceAnchor: the snapshot was taken with the anchor the profile is saved with. Read
        # it now, before an edit of the anchor recomputes the hole.
        profile = get_profile_from_extrudedcutout(obj) if obj.baseObject else None
        if profile is not None:
            _add_reference_anchor(obj, section_shift(profile))
        # Saved before the tape length: the length of the piece it cuts, as a cutout gets it.
        restore_length(obj, measured_piece)

    def onBeforeChange(self, fp, prop):
        if prop == "baseObject" and fp.baseObject:
            # A name, not the object: the proxy is saved with the document.
            self._left_base = fp.baseObject[0].Name

    def onChanged(self, fp, prop):
        super().onChanged(fp, prop)
        if prop == "baseObject":
            name = getattr(self, "_left_base", None)
            self._left_base = None
            left = fp.Document.getObject(name) if name else None
            if left is not None and (not fp.baseObject or fp.baseObject[0] != left):
                _show_unless_built_on(left, fp)
                if fp.baseObject:
                    _relabel(fp, left, fp.baseObject[0])

    def reference(self, fp):
        """(vertex point, face normal, face center, face or None) the holes are placed from.

        A face or vertex other than the snapshot's (a new hole, or picked by the user) takes a new
        snapshot. Otherwise the snapshot is found again on the base shape: the named vertex, else
        the vertex now at its place; when none is, the hole keeps the snapshot and warns.
        """
        profile = get_profile_from_extrudedcutout(fp)
        # A new drill hole, or one whose profile could not be read on opening: the anchor it has now.
        _add_reference_anchor(fp, section_shift(profile))
        selected_object, (face_name, *_) = fp.baseObject
        # A face FreeCAD lost track of after an edit of the base is named "?Face3": it is still the
        # face of the snapshot, found again below from its plane.
        face_name = face_name.removeprefix(MISSING_ELEMENT_PREFIX)
        shape = selected_object.Shape
        placement = profile.Placement
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
            fp.ReferenceAnchor = section_shift(profile)
            self._warn(fp, "")
            return vertex, normal, face.CenterOfMass, face
        # The anchor moves the section, not the profile: the snapshot moves with the section.
        point = placement.multVec(fp.ReferencePoint + section_shift(profile) - fp.ReferenceAnchor)
        normal = placement.Rotation.multVec(fp.ReferenceNormal)
        vertex = _resolve_vertex(shape, fp.ReferenceVertex, point)
        face = _resolve_face(shape, face_name, normal, point)
        if vertex is None or face is None:
            self._warn(fp, translate("frameforge", "The reference vertex changed: check the hole."))
        else:
            self._warn(fp, "")
        center = face.CenterOfMass if face is not None else shape.BoundBox.Center
        return (vertex if vertex is not None else point), normal, center, face

    def _warn(self, fp, warning):
        if warning:
            App.Console.PrintWarning(f"{fp.Label}: {warning}\n")
        if fp.ReferenceWarning != warning:
            fp.ReferenceWarning = warning

    def centers(self, fp):
        """(face normal, centers of the holes on the face plane).

        The offsets are measured from the vertex, positive into the face, or from the middle of the face
        along (CenterAlong) or across (CenterAcross) the profile, positive toward the end of the path of
        the profile along and to a fixed side across. They give the point; the pattern adds holes on each
        side of it, forward in the positive direction of each offset (see pattern_positions).
        """
        vertex, normal, center, face = self.reference(fp)
        profile = get_profile_from_extrudedcutout(fp)
        # Profiles are extruded along their local Z.
        axis = profile.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        # A drill hole saved before the centers has not got them until it is restored.
        center_along, center_across = getattr(fp, "CenterAlong", False), getattr(fp, "CenterAcross", False)
        along, across = _plane_axes(normal, axis, vertex, center, center_along, center_across)
        origin = offset_origin(face, vertex, along, across, center_along, center_across)
        point = origin + along * fp.OffsetAlong.Value + across * fp.OffsetAcross.Value
        positions = pattern_positions(*_pattern(fp))
        return normal, [point + along * a + across * b for a, b in positions]

    def execute(self, fp):
        """Drill the holes when the object is recomputed."""
        if fp.baseObject is None or not fp.baseObject[1]:
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
        """Show the base again; in a Folded Bar the bar folds the base again instead and keeps it hidden."""
        from freecad.maxproframe.folded_bar import release_piece

        obj = self.Object
        folded = any(is_foldedbar(parent) and obj in parent.Segments for parent in obj.InList)
        release_piece(obj)
        if obj.baseObject and not folded:
            obj.baseObject[0].ViewObject.Visibility = True
        return True

    def setEdit(self, vobj, mode):
        """Double-click: the Drill Hole panel on this hole."""
        if mode != 0:
            return None
        from freecad.maxproframe import create_drill_hole_tool

        # The panel listens to clicks: they change the face and the vertex.
        create_drill_hole_tool.show_panel(create_drill_hole_tool.DrillHoleTaskPanel(edited=self.Object))
        return True

    def setupContextMenu(self, vobj, menu):
        """No sketch to edit."""

    def getIcon(self):
        return os.path.join(ICONPATH, "drill-hole.svg")

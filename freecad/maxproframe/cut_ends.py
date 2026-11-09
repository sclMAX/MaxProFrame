"""Cut angle of each end of a piece and how both ends sit, read on its finished solid.

The solid is brought into the frame of its profile: X across the width W, Y across the height H, Z along the
axis. End 1 is the start (Z min, CuttingAngleA), end 2 the end (Z max, CuttingAngleB). The normal of the flat
cut at an end, projected on X and Y, gives the angle seen on the faces of size W and on those of size H.
"""

import math

import FreeCAD as App
import Part

from freecad.maxproframe._utils import is_profile
from freecad.maxproframe.populate_ids import profile_source
from freecad.maxproframe.trimmed_profile import face_normal, in_frame_of

ROUND_FAMILIES = ("Round Bar", "Pipe")
# Degrees under which an angle counts as square.
ZERO_ANGLE = 0.05
# Share of the section area the projected end faces may miss and still be the whole section.
AREA_TOLERANCE = 1e-4
# Smallest |nz| of a face crossing the axis: below it the face runs along the profile.
AXIS_TOLERANCE = 1e-6
# Largest angle, in radians, between the normals of end faces that lie on one plane.
PLANE_TOLERANCE = 1e-6
# Ends column: tilted apart on one face, tilted the same way on one face, one end square.
TRAPEZOID, PARALLELOGRAM, ONE_SQUARE = "\\_/", "/_/", "|_/"


def _in_profile_frame(source, obj, shape):
    """``shape`` of ``obj`` in the local frame of its profile ``source``."""
    shape = in_frame_of(source, obj, shape).copy()
    shape.transformShape(source.Placement.inverse().toMatrix())
    return shape


def _size(value):
    """A face size as printed: 80.0 -> "80", 1.5 -> "1.5"."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _section(source):
    """(W, H, area) of the section of the profile ``source``, sliced halfway along its axis, or None."""
    shape = _in_profile_frame(source, source, source.Shape)
    if not shape.Solids:
        return None
    box = shape.BoundBox
    wires = shape.slice(App.Vector(0, 0, 1), (box.ZMin + box.ZMax) / 2)
    if not wires:
        return None
    try:
        face = Part.makeFace(wires, "Part::FaceMakerBullseye")
    except Part.OCCError:
        return None
    return face.BoundBox.XLength, face.BoundBox.YLength, face.Area


def _end_normal(shape, end, area):
    """Outward normal of the one flat cut at ``end`` (-1 start, 1 end) of ``shape``, or None for any other end."""
    box = shape.BoundBox
    tolerance = max(1e-6 * box.ZLength, 1e-6)
    extreme = box.ZMin if end < 0 else box.ZMax
    faces = []
    for face in shape.Faces:
        if not isinstance(face.Surface, Part.Plane):
            continue
        normal = face_normal(face)
        reach = face.BoundBox.ZMin if end < 0 else face.BoundBox.ZMax
        if abs(normal.z) <= AXIS_TOLERANCE or abs(reach - extreme) > tolerance:
            continue
        faces.append((face, normal if normal.z * end > 0 else -normal))
    if not faces:
        return None
    first, normal = faces[0]
    # Several faces are fine when they lie on one plane.
    for face, other in faces[1:]:
        offset = abs(normal.dot(face.CenterOfMass - first.CenterOfMass))
        if other.getAngle(normal) > PLANE_TOLERANCE or offset > tolerance:
            return None
    projected = sum(face.Area for face, _ in faces) * abs(normal.z)
    if abs(projected - area) > AREA_TOLERANCE * area:
        return None
    return normal


def _tilts(normal):
    """Angles, in degrees, of the cut seen on the faces of size W and on those of size H."""
    tilts = (math.atan2(abs(normal.x), abs(normal.z)), math.atan2(abs(normal.y), abs(normal.z)))
    return tuple(angle if angle >= ZERO_ANGLE else 0.0 for angle in map(math.degrees, tilts))


def _angle_text(normal, width, height, round_section):
    """``45.0 <80``, ``45.0 <80 + 10.0 <40`` or ``0.0``; a single angle without face on a round section."""
    if round_section:
        angle = math.degrees(math.acos(min(1.0, abs(normal.z))))
        return f"{angle:.1f}" if angle >= ZERO_ANGLE else "0.0"
    parts = [f"{angle:.1f} <{_size(size)}" for angle, size in zip(_tilts(normal), (width, height)) if angle]
    return " + ".join(parts) or "0.0"


def _ends(start, end):
    """The Ends symbol of the outward normals of both ends, empty unless both lie on one face or one is square."""
    tilted = [[axis for axis, angle in enumerate(_tilts(normal)) if angle] for normal in (start, end)]
    if len(tilted[0]) == len(tilted[1]) == 1 and tilted[0] == tilted[1]:
        axis = tilted[0][0]
        return TRAPEZOID if start[axis] * end[axis] > 0 else PARALLELOGRAM
    if sorted(map(len, tilted)) == [0, 1]:
        return ONE_SQUARE
    return ""


def cut_ends(obj):
    """(cut angle 1, cut angle 2, ends) of the piece ``obj``: a profile, a trim of it or a cutout.

    A piece whose ends are not each one flat cut (a notch, a cutout eating an end), or that cannot be read on its
    profile (not made from a profile, no solid, no section), keeps its CuttingAngleA/B and gets no Ends symbol.
    """
    fallback = (obj.CuttingAngleA, obj.CuttingAngleB, "")
    source = profile_source(obj)
    if source is None or not is_profile(source) or obj.Shape.isNull() or not obj.Shape.Solids:
        return fallback
    section = _section(source)
    if section is None:
        return fallback
    width, height, area = section
    shape = _in_profile_frame(source, obj, obj.Shape)
    normals = [_end_normal(shape, end, area) for end in (-1, 1)]
    if None in normals:
        return fallback
    round_section = getattr(source, "Family", None) in ROUND_FAMILIES
    angles = [_angle_text(normal, width, height, round_section) for normal in normals]
    return angles[0], angles[1], _ends(*normals)

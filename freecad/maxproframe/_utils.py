# -*- coding: utf-8 -*-

__title__ = "Curves workbench utilities"
__author__ = "Christophe Grellier (Chris_G)"
__license__ = "LGPL 2.1"
__doc__ = "Curves workbench utilities common to all tools."

import math
from numbers import Number

import FreeCAD
import Part

from freecad.maxproframe.ff_tools import translate


def getRootObject(obj):
    if obj.isDerivedFrom("PartDesign::Feature"):
        body = obj.getParentGeoFeatureGroup()
        if body:
            return body

    return obj


def getSubShape(shape, shape_type, n):
    if shape_type == "Vertex" and len(shape.Vertexes) >= n:
        return shape.Vertexes[n - 1]
    elif shape_type == "Edge" and len(shape.Edges) >= n:
        return shape.Edges[n - 1]
    elif shape_type == "Face" and len(shape.Faces) >= n:
        return shape.Faces[n - 1]
    else:
        return None


def getShape(obj, prop, shape_type):
    if hasattr(obj, prop) and obj.getPropertyByName(prop):
        prop_link = obj.getPropertyByName(prop)
        if obj.getTypeIdOfProperty(prop) == "App::PropertyLinkSub":
            if shape_type in prop_link[1][0]:
                # try:  # FC 0.19+
                # return prop_link[0].getSubObject(prop_link[1][0])
                # except AttributeError:  # FC 0.18 (stable)
                n = eval(obj.getPropertyByName(prop)[1][0].lstrip(shape_type))
                osh = obj.getPropertyByName(prop)[0].Shape
                sh = osh.copy()
                if (
                    sh
                    and (not shape_type == "Vertex")
                    and hasattr(obj.getPropertyByName(prop)[0], "getGlobalPlacement")
                ):
                    pl = obj.getPropertyByName(prop)[0].getGlobalPlacement()
                    sh.Placement = pl
                return getSubShape(sh, shape_type, n)

        elif obj.getTypeIdOfProperty(prop) == "App::PropertyLinkSubList":
            res = []
            for tup in prop_link:
                for ss in tup[1]:
                    if shape_type in ss:
                        # try:  # FC 0.19+
                        # res.append(tup[0].getSubObject(ss))
                        # except AttributeError:  # FC 0.18 (stable)
                        n = eval(ss.lstrip(shape_type))
                        sh = tup[0].Shape.copy()
                        if sh and (not shape_type == "Vertex") and hasattr(tup[0], "getGlobalPlacement"):
                            pl = tup[0].getGlobalPlacement()
                            sh.Placement = pl
                        res.append(getSubShape(sh, shape_type, n))
            return res
        else:
            FreeCAD.Console.PrintError("CurvesWB._utils.getShape: wrong property type.\n")
            return None
    else:
        # FreeCAD.Console.PrintError("CurvesWB._utils.getShape: %r has no property %r\n"%(obj, prop))
        return None


def is_fusion(obj):
    if obj.TypeId == "Part::MultiFuse":
        shape = obj.Shape
        if shape is not None and (shape.ShapeType == "Compound" or shape.isValid() and len(shape.Faces) > 0):
            return True
    return False


def is_part(obj):
    return obj.TypeId == "App::Part"


def is_group(obj):
    return obj.TypeId == "App::DocumentObjectGroup"


def is_profile(obj):
    if obj.TypeId == "Part::FeaturePython":
        if hasattr(obj, "ProfileWidth") and hasattr(obj, "ProfileHeight") and hasattr(obj, "ProfileLength"):
            return True
    return False


def is_trimmedbody(obj):
    if obj.TypeId == "Part::FeaturePython":
        if hasattr(obj, "TrimmedBody"):
            return True
    return False


def is_extrudedcutout(obj):
    if obj.TypeId == "Part::FeaturePython":
        if hasattr(obj, "baseObject"):
            return True
    return False


def is_link(obj):
    return obj.TypeId == "App::Link" and hasattr(obj, "AttachmentOffset")


def is_part_or_part_design(obj):
    return obj.TypeId.startswith(("Part::", "PartDesign::"))


def is_profile_pattern(obj):
    """A Profile Pattern: the object repeating a piece as Links."""
    return obj.TypeId == "App::FeaturePython" and "Piece" in obj.PropertiesList and "Copies" in obj.PropertiesList


def is_pattern_link(obj):
    """A copy a Profile Pattern made of its piece: a Link it keeps in its Copies, counted as that piece."""
    return obj.TypeId == "App::Link" and any(
        is_profile_pattern(parent) and obj.Name in (copy.Name for copy in parent.Copies) for parent in obj.InList
    )


def get_profiles_and_links_from_object(profiles, links, obj):
    if is_fusion(obj):
        for child in obj.Shapes:
            get_profiles_and_links_from_object(profiles, links, child)

    elif is_group(obj):
        for child in obj.Group:
            get_profiles_and_links_from_object(profiles, links, child)

    elif is_part(obj):
        for child in obj.Group:
            # TODO: Fix this ugly way to find children
            # I didn't find another way when into a Part
            # It makes it mandatory to have visible object when generating BOM
            if child.getParentGroup() in (obj, None) and child.Visibility:
                get_profiles_and_links_from_object(profiles, links, child)

    elif is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj) or is_pattern_link(obj):
        # A Profile Pattern copy is one more piece of what it copies, not a link of its own.
        profiles.append(obj)

    elif is_link(obj):
        links.append(obj)


def get_profiles_and_links_from_document():
    """(profiles and Profile Pattern copies, other links) of the active document."""
    doc = FreeCAD.ActiveDocument
    copies = [o for o in doc.Objects if is_pattern_link(o)]
    names = {o.Name for o in copies}
    return (
        [o for o in doc.Objects if is_profile(o)] + copies,
        [o for o in doc.Objects if is_link(o) and o.Name not in names],
    )


# TODO move this code into TrimmedProfile ?
def get_profile_from_trimmedbody(obj):
    if is_trimmedbody(obj):
        return get_profile_from_trimmedbody(obj.TrimmedBody)
    elif is_extrudedcutout(obj):
        return get_profile_from_extrudedcutout(obj)
    else:
        return obj


# TODO move this code into TrimmedProfile ?
def get_childrens_from_trimmedbody(obj):
    yield obj
    if is_trimmedbody(obj):
        yield from get_childrens_from_trimmedbody(obj.TrimmedBody)


# TODO move this code into ExtrudedCutOut ?
def get_profile_from_extrudedcutout(obj):
    if is_extrudedcutout(obj):
        bo = obj.baseObject[0]
        if is_profile(bo):
            return bo
        elif is_trimmedbody(bo):
            return get_profile_from_trimmedbody(bo)
        elif is_extrudedcutout(bo):
            return get_profile_from_extrudedcutout(bo)
        else:
            return None

    else:
        raise Exception("Not an extruded cutout")


# TODO move this code into ExtrudedCutOut ?
def get_childrens_from_extrudedcutout(obj):
    yield obj
    if is_trimmedbody(obj):
        yield from get_childrens_from_trimmedbody(obj.TrimmedBody)
    elif is_extrudedcutout(obj):
        yield from get_childrens_from_extrudedcutout(obj.baseObject[0])


# TODO move this code into ExtrudedCutOut ?
def get_trimmedprofile_from_extrudedcutout(obj):
    if is_extrudedcutout(obj):
        bo = obj.baseObject[0]
        if is_trimmedbody(bo):
            return bo
        elif is_extrudedcutout(bo):
            return get_trimmedprofile_from_extrudedcutout(bo)
        else:
            return None
    else:
        raise Exception("Not an extruded cutout")


# TODO move this code into TrimmedProfile ?
def get_trimmed_profile_all_cutting_angles(trimmed_profile):
    """Retourne récursivement la liste des angles de coupe (en degrés)
    d'un TrimmedProfile, y compris ceux de ses parents/enfants imbriqués."""
    angles = []

    if trimmed_profile.TrimmedProfileType == "Notch":
        # A notch copies the target shape: no single cutting angle, "P" marks it in the BOM.
        angles.append("P")

    elif trimmed_profile.TrimmedProfileType == "End Miter":
        # Geometry keeps the raw angle; the readable angles show one decimal.
        angles.extend(round(plane.cut_angle(), 1) for plane in trimmed_profile.Proxy.miter_planes(trimmed_profile))

    elif trimmed_profile.TrimmedProfileType == "Extend Cut":
        # The angle between the profile axis and the target plane normal; one decimal as End Miter.
        angles.append(round(trimmed_profile.Proxy.extend_cut_plane(trimmed_profile).cut_angle(), 1))

    else:
        raise ValueError("Unknown TrimmedProfileType")

    if hasattr(trimmed_profile.TrimmedBody, "TrimmedProfileType"):
        parent_profile = trimmed_profile.TrimmedBody
        angles.extend(get_trimmed_profile_all_cutting_angles(parent_profile))

    return sorted(angles, key=lambda x: (x is not None, "" if isinstance(x, Number) else type(x).__name__, x))


def normalize_anchor(val):
    """Normalize anchor to int 0–2. Accepts bool (legacy: True→1, False→0) or int; e.g. from custom macros."""
    if isinstance(val, bool):
        return 1 if val else 0
    return max(0, min(2, int(val)))


# A straight edge whose direction is this far (sine of the angle) from the axis still runs along it.
PARALLEL_TOLERANCE = 1e-6
# Straight edges whose lines are this close lie on one side of the piece.
COLLINEAR_TOLERANCE = 1e-6


def longest_side(shape, axis):
    """Length of the longest side of ``shape`` along the unit vector ``axis``, as a tape measures it.

    A side is a line of straight edges parallel to ``axis``; a side left in several edges on one line
    (split by a trim) is measured from its first to its last end. None when no straight edge runs along ``axis``.
    """
    sides = []  # [point of the line off the axis, lowest projection, highest projection]
    for edge in shape.Edges:
        if not isinstance(edge.Curve, Part.Line) or edge.Curve.Direction.cross(axis).Length > PARALLEL_TOLERANCE:
            continue
        start, end = (vertex.Point.dot(axis) for vertex in (edge.Vertexes[0], edge.Vertexes[-1]))
        offset = edge.Vertexes[0].Point - axis * start
        for side in sides:
            if (side[0] - offset).Length <= COLLINEAR_TOLERANCE:
                side[1], side[2] = min(side[1], start, end), max(side[2], start, end)
                break
        else:
            sides.append([offset, min(start, end), max(start, end)])
    return max((high - low for _, low, high in sides), default=None)


def length_along_normal(obj):
    """Length of a piece along its axis, the direction of its path edge: its longest side, as taped to cut it.

    A section without a straight edge along the axis (round tube or bar) keeps its tip-to-tip extent.
    """
    # The document of the piece, not the active one: a document being opened is not always active.
    doc = obj.Document

    if is_profile(obj):
        if hasattr(obj, "Target"):
            target = obj.Target
            edge = doc.getObject(target[0].Name).getSubObject(target[1][0])
        else:
            return obj.ProfileLength

    elif is_trimmedbody(obj):

        def resolve_edge(link):
            target = obj.Proxy.getTarget(link)
            return doc.getObject(target[0].Name).getSubObject(target[1][0])

        edge = resolve_edge(obj.TrimmedBody)

    else:
        return 0.0

    dir_vec = (edge.Vertexes[-1].Point.sub(edge.Vertexes[0].Point)).normalize()
    n = dir_vec.normalize()

    side = longest_side(obj.Shape, n)
    if side is not None:
        return side

    vertices = obj.Shape.Vertexes

    projections = [v.Point.dot(n) for v in vertices]

    length = max(projections) - min(projections)
    return length


def restore_length(obj, measured=lambda obj: obj):
    """Set the Length of ``obj`` to the tape length of ``measured(obj)`` as its shape is, without recomputing it.

    For a document being opened: a piece saved before the tape length gets it at once. Every shape is read from
    the file before any object is told the document is restored, whatever the order of the objects. A path or
    shape that gives no length (missing, empty) keeps the saved Length. ``obj`` stays as touched as it was: the
    shape is unchanged, so a Length set here asks for no recompute.
    """
    try:
        length = length_along_normal(measured(obj))
        saved = obj.Length.Value
    except Exception:
        return
    if not isinstance(length, Number) or not math.isfinite(length) or length == saved:
        return
    touched = "Touched" in obj.State
    obj.Length = length
    if not touched:
        obj.purgeTouched()


def add_custom_profile_link(obj, read_only=True):
    """Give ``obj`` its CustomProfile: a global link, as library sections live outside its Part.

    A profile keeps it editable (``read_only=False``); the pieces made from it only show it.
    """
    obj.addProperty("App::PropertyLinkGlobal", "CustomProfile", "Profile", "Target profile")
    if read_only:
        obj.setEditorMode("CustomProfile", 1)


def restore_custom_profile_link(obj, read_only=True):
    """Turn the local CustomProfile link of ``obj``, as saved before it was global, into a global one.

    For a document being opened: the link keeps its section (or none), ``obj`` saved without it gains an
    empty one, and ``obj`` stays as touched as it was. Opening never fails on it: a link that cannot be
    turned is reported on the console.
    """
    try:
        section = None
        if "CustomProfile" in obj.PropertiesList:
            if obj.getTypeIdOfProperty("CustomProfile") == "App::PropertyLinkGlobal":
                return
            section = obj.CustomProfile
        touched = "Touched" in obj.State
        if "CustomProfile" in obj.PropertiesList:
            obj.removeProperty("CustomProfile")
        add_custom_profile_link(obj, read_only)
        obj.CustomProfile = section
        if not touched:
            obj.purgeTouched()
    except Exception:
        FreeCAD.Console.PrintWarning(
            translate("frameforge", "{}: its CustomProfile link could not be turned into a global one.\n").format(
                getattr(obj, "Label", "")
            )
        )


def get_readable_cutting_angles(ba_y, ba_x, bb_y, bb_x, *trim_cuts):
    all_bevels = [ba_y, ba_x, bb_y, bb_x]
    start_bevels = [ba_y, ba_x]
    end_bevels = [bb_y, bb_x]

    if len(trim_cuts) == 0:
        if all(b == "N/A" for b in all_bevels):
            return ("N/A", "N/A")

        # a real profile
        if all([b == 0 for b in all_bevels]):
            return ("0.0", "0.0")

        elif ba_y == bb_y == 0.0:
            angles = (ba_x, bb_x)
            angles = angles if (angles[0] * angles[1] < 0) else (abs(angles[0]), abs(angles[1]))
            return (f"{angles[0]:.1f}", f"{angles[1]:.1f}")

        elif ba_x == bb_x == 0.0:
            angles = (ba_y, bb_y)
            angles = angles if (angles[0] * angles[1] < 0) else (abs(angles[0]), abs(angles[1]))
            return (f"{angles[0]:.1f}", f"{angles[1]:.1f}")

        elif (ba_y == 0.0 and bb_x == 0.0) ^ (ba_x == 0.0 and bb_y == 0.0):
            return (f"{(ba_y + ba_x):.1f}", f"* {(bb_y+bb_x):.1f}")

        else:
            return (f"{ba_y:.1f} / {ba_x:.1f}", f"{bb_y:.1f} / {bb_x:.1f}")

    elif len(trim_cuts) == 2:
        trim_cuts = [f"{tc:.1f}" if isinstance(tc, float) else tc for tc in trim_cuts]
        return (f"@ {trim_cuts[0]}", f"@ {trim_cuts[1]}")

    elif len(trim_cuts) == 1:
        bevels_not_zero = [b for b in all_bevels if b != 0]
        if len(bevels_not_zero) == 0:
            return ("0.0", f"@ {trim_cuts[0]}")

        elif len(bevels_not_zero) == 1:
            return (f"{abs(bevels_not_zero[0])}", f"@ {trim_cuts[0]}")

    return ("?", "?")

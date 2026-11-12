"""Chain of tube profiles joined by folded corners: the skeleton a folded bar is built from.

The selected profiles (or any trim, cutout or drill hole made from them) are ordered end to end from the first
selected one. A closed frame opens at one corner: the one given, else where the first and the last selected profiles
meet, else the start of the first selected one's path. Every other corner folds: its bend angle is how far the path
turns, its axis is normal to both paths, and its outer wall (the one that stays whole and bends) faces away from the
turn. The chain is refused, saying why, when its profiles are not one straight tube that folds into one bar.
"""

import math
from dataclasses import dataclass

import FreeCAD as App
import Part

from freecad.maxproframe._utils import is_extrudedcutout, is_profile, is_trimmedbody
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.profile import section_shift
from freecad.maxproframe.profile_pattern import container_placement, newest_piece

FOLDABLE_FAMILIES = ("Square Hollow", "Rectangular Hollow")
# Path ends closer than this meet (mm).
MEET_TOLERANCE = 1e-4
# Squared sine below which two directions are parallel.
PARALLEL_TOLERANCE = 1e-10
# A section moved less than this across a fold continues the previous one (mm).
CONTINUITY_TOLERANCE = 1e-4
SIZE_TOLERANCE = 1e-6


class ChainError(ValueError):
    """The selection cannot fold into one bar; the message says why."""


@dataclass
class Segment:
    profile: object
    tip: object
    start: App.Vector
    end: App.Vector
    direction: App.Vector
    length: float
    x_axis: App.Vector
    y_axis: App.Vector
    width: float
    height: float
    thickness: float


@dataclass
class Corner:
    before: int
    after: int
    point: App.Vector
    bend_angle: float
    axis: App.Vector
    outer_normal: App.Vector
    depth: float


@dataclass
class Chain:
    segments: list
    corners: list
    closed: bool
    open_point: App.Vector = None


def _label(obj):
    return obj.Label


def base_profile(obj):
    """The profile ``obj`` is made from, through its trims, cutouts and drill holes; None when there is none."""
    seen = set()
    while obj is not None and obj.Name not in seen:
        seen.add(obj.Name)
        if is_profile(obj):
            return obj
        if is_trimmedbody(obj):
            obj = obj.TrimmedBody
        elif is_extrudedcutout(obj) and obj.baseObject:
            obj = obj.baseObject[0]
        else:
            return None
    return None


def _path_edge(profile):
    target = getattr(profile, "Target", None)
    if not target or not target[1]:
        raise ChainError(translate("MaxProFrame", "{} has no path to fold.").format(_label(profile)))
    sketch, subs = target
    edge = Part.getShape(sketch, subs[0], needSubElement=True).copy()
    edge.Placement = container_placement(sketch).multiply(edge.Placement)
    if not isinstance(edge.Curve, Part.Line):
        raise ChainError(
            translate("MaxProFrame", "{} follows a curved path: only straight profiles can be folded.").format(
                _label(profile)
            )
        )
    return edge


def _size(profile):
    return float(profile.ProfileWidth), float(profile.ProfileHeight), float(profile.Thickness)


def _size_text(size):
    return " x ".join(f"{value:g}" for value in size)


def _check_tubes(profiles):
    for profile in profiles:
        if profile.Family not in FOLDABLE_FAMILIES:
            raise ChainError(
                translate(
                    "MaxProFrame",
                    "{} is a {} profile: only Square Hollow and Rectangular Hollow tubes can be folded.",
                ).format(_label(profile), profile.Family)
            )
    first = profiles[0]
    for profile in profiles[1:]:
        if any(abs(a - b) > SIZE_TOLERANCE for a, b in zip(_size(profile), _size(first))):
            difference = (_size_text(_size(profile)), _size_text(_size(first)))
        elif profile.Material != first.Material:
            difference = (profile.Material, first.Material)
        else:
            continue
        raise ChainError(
            translate("MaxProFrame", "{} is not the same tube as {}: {} instead of {}.").format(
                _label(profile), _label(first), *difference
            )
        )


def _meeting_points(edges, labels):
    """Points where path ends meet, each with the (segment, end) pairs there; raises on three at one point."""
    points = []
    for index, edge in enumerate(edges):
        for end, vertex in enumerate((edge.Vertexes[0].Point, edge.Vertexes[-1].Point)):
            for point in points:
                if (point[0] - vertex).Length <= MEET_TOLERANCE:
                    point[1].append((index, end))
                    break
            else:
                points.append((vertex, [(index, end)]))
    meetings = [point for point in points if len(point[1]) > 1]
    if any(len(ends) > 2 for _, ends in meetings):
        raise ChainError(translate("MaxProFrame", "More than two of the selected profiles meet at one point."))
    partner = {}
    for point, (first, second) in meetings:
        partner[first] = (second, point)
        partner[second] = (first, point)
    for index, label in enumerate(labels):
        if (index, 0) not in partner and (index, 1) not in partner:
            raise ChainError(
                translate(
                    "MaxProFrame", "The selected profiles do not form one chain: {} meets none of the others."
                ).format(label)
            )
    return partner


def _corner_between(partner, first, second):
    for end in (0, 1):
        found = partner.get((first, end))
        if found and found[0][0] == second:
            return end, found[1]
    return None


def _walk(partner, start, end, count):
    """Segments in order as (index, entry end), from ``start`` entered at ``end``."""
    order = [(start, end)]
    while True:
        index, entry = order[-1]
        found = partner.get((index, 1 - entry))
        if found is None or found[0][0] == start:
            break
        order.append(found[0])
        if len(order) > count:
            break
    return order


def _segment(profile, edge, entry):
    points = (edge.Vertexes[0].Point, edge.Vertexes[-1].Point)
    start, end = points[entry], points[1 - entry]
    rotation = container_placement(profile).multiply(profile.Placement).Rotation
    width, height, thickness = _size(profile)
    return Segment(
        profile=profile,
        tip=newest_piece(profile),
        start=start,
        end=end,
        direction=(end - start).normalize(),
        length=(end - start).Length,
        x_axis=rotation.multVec(App.Vector(1, 0, 0)),
        y_axis=rotation.multVec(App.Vector(0, 1, 0)),
        width=width,
        height=height,
        thickness=thickness,
    )


def _parallel(a, b):
    return a.cross(b).Length ** 2 < PARALLEL_TOLERANCE


def section_offset(segment):
    """Center of the section of ``segment`` seen from its path: the anchor, offsets and rotation together."""
    profile = segment.profile
    local = section_shift(profile) + App.Vector(segment.width / 2, segment.height / 2, 0)
    center = container_placement(profile).multiply(profile.Placement).multVec(local) - segment.start
    return center - segment.direction * center.dot(segment.direction)


def _corner(index, first, second):
    labels = (_label(first.profile), _label(second.profile))
    d1, d2 = first.direction, second.direction
    if _parallel(d1, d2):
        if d1.dot(d2) > 0:
            message = translate("MaxProFrame", "{} and {} are in line: there is nothing to fold.").format(*labels)
        else:
            message = translate(
                "MaxProFrame", "{1} turns back on {0}: a corner can fold less than 180 degrees."
            ).format(*labels)
        raise ChainError(message)
    axis = d1.cross(d2).normalize()
    if not (_parallel(axis, first.x_axis) or _parallel(axis, first.y_axis)):
        raise ChainError(
            translate(
                "MaxProFrame",
                "The corner between {} and {} bends across a corner of the tube: "
                "its walls must be parallel to the bend.",
            ).format(*labels)
        )
    fold = App.Rotation(d1, d2)
    turned_x = fold.multVec(first.x_axis)
    same_axes = _parallel(turned_x, second.x_axis) or (
        abs(first.width - first.height) <= SIZE_TOLERANCE and _parallel(turned_x, second.y_axis)
    )
    moved = (fold.multVec(section_offset(first)) - section_offset(second)).Length
    if not same_axes or moved > CONTINUITY_TOLERANCE:
        raise ChainError(
            translate(
                "MaxProFrame",
                "{1} does not continue {0} across the fold: give both the same anchor, offsets and rotation.",
            ).format(*labels)
        )
    inward = d2 - d1 * d2.dot(d1)
    outer = inward.normalize() * -1
    depth = first.width if _parallel(outer, first.x_axis) else first.height
    bend_angle = math.degrees(math.acos(max(-1.0, min(1.0, d1.dot(d2)))))
    return Corner(index, index + 1, App.Vector(first.end), bend_angle, axis, outer, depth)


def build_chain(selection, open_corner=None):
    """The chain of the profiles in ``selection``, from the first selected one.

    ``open_corner`` is an optional pair of objects of ``selection`` (or made from its profiles) whose profiles meet at
    the corner a closed frame opens at; the first selected profile must be one of them.
    """
    profiles = []
    for obj in selection:
        profile = base_profile(obj)
        if profile is None:
            raise ChainError(translate("MaxProFrame", "{} is not a profile.").format(_label(obj)))
        if profile in profiles:
            raise ChainError(translate("MaxProFrame", "{} is selected more than once.").format(_label(profile)))
        profiles.append(profile)
    if len(profiles) < 2:
        raise ChainError(translate("MaxProFrame", "Select at least two profiles that meet end to end."))
    _check_tubes(profiles)
    edges = [_path_edge(profile) for profile in profiles]
    labels = [_label(profile) for profile in profiles]
    partner = _meeting_points(edges, labels)
    free_ends = [(index, end) for index in range(len(profiles)) for end in (0, 1) if (index, end) not in partner]
    closed = not free_ends

    if not closed:
        if open_corner is not None:
            raise ChainError(
                translate(
                    "MaxProFrame", "Only a closed frame has an open corner: these profiles already have two free ends."
                )
            )
        start_end = next((end for index, end in free_ends if index == 0), None)
        if start_end is None:
            raise ChainError(
                translate("MaxProFrame", "Select first a profile at one end of the chain: {} is in its middle.").format(
                    labels[0]
                )
            )
        open_point = None
    elif open_corner is not None:
        pair = [base_profile(obj) for obj in open_corner]
        indexes = [profiles.index(profile) if profile in profiles else None for profile in pair]
        found = None if None in indexes else _corner_between(partner, *indexes)
        if found is None:
            raise ChainError(
                translate("MaxProFrame", "{} and {} do not meet at a corner.").format(*(_label(p) for p in pair))
            )
        if 0 not in indexes:
            raise ChainError(
                translate(
                    "MaxProFrame", "The open corner must be at one end of the first selected profile ({})."
                ).format(labels[0])
            )
        other = indexes[1] if indexes[0] == 0 else indexes[0]
        start_end, open_point = _corner_between(partner, 0, other)
    else:
        found = _corner_between(partner, 0, len(profiles) - 1)
        start_end, open_point = found if found else (0, partner[(0, 0)][1])

    order = _walk(partner, 0, start_end, len(profiles))
    if len(order) != len(profiles):
        raise ChainError(translate("MaxProFrame", "The selected profiles do not form one chain."))
    segments = [_segment(profiles[index], edges[index], entry) for index, entry in order]
    corners = [_corner(index, segments[index], segments[index + 1]) for index in range(len(segments) - 1)]
    return Chain(segments, corners, closed, App.Vector(open_point) if open_point is not None else None)

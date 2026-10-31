"""Miter joints found among selected members from their path ends.

Two members form a joint when the closest pair of their path ends meet: those ends lie
within the sum of both section diagonals of each other, the crossing of both end axes
reaches each end as a corner, and the members are not parallel in the same direction.
A member end claimed by two or more joints is a point where three or more members
meet; those joints are skipped and the point is reported.
"""

import itertools

from freecad.maxproframe.miter_geometry import EXTENSION_LIMIT, axes_crossing, meeting_ends, parallel, path_end

# Deepest crossing inside a member, in section diagonals, that still counts as a corner.
CORNER_DEPTH = 1.0
# Distance, in mm, below which two parallel axes count as collinear.
COLLINEAR_TOLERANCE = 1e-6


class Joint:
    """Two members meeting at ``point``; ``ends`` holds (member index, at start) for both."""

    def __init__(self, first, first_at_start, second, second_at_start, point):
        self.first = first
        self.second = second
        self.ends = ((first, first_at_start), (second, second_at_start))
        self.point = point


class SkippedPoint:
    """A point where three or more members meet; ``members`` are sorted member indices."""

    def __init__(self, point, members):
        self.point = point
        self.members = members


def find_joints(members):
    """Joints and skipped points for ``members``, a sequence of (path edge, section diagonal).

    Returns ``(joints, skipped)`` where joints reference members by index.
    """
    candidates = []
    for first, second in itertools.combinations(range(len(members)), 2):
        joint = _joint(first, members[first], second, members[second])
        if joint is not None:
            candidates.append(joint)

    claims = {}
    for joint in candidates:
        for end in joint.ends:
            claims.setdefault(end, []).append(joint)
    crowded = {end for end, claimed in claims.items() if len(claimed) > 1}

    joints = [joint for joint in candidates if not crowded.intersection(joint.ends)]
    skipped = _skipped_points([joint for joint in candidates if crowded.intersection(joint.ends)], members)
    return joints, skipped


def _joint(first, first_member, second, second_member):
    edge, diagonal = first_member
    other_edge, other_diagonal = second_member
    at_start, other_at_start = meeting_ends(edge, other_edge)
    point, inward = path_end(edge, at_start)
    other_point, other_inward = path_end(other_edge, other_at_start)

    # Closest ends farther apart than both sections belong to opposite members of a frame.
    if (other_point - point).Length > diagonal + other_diagonal:
        return None
    if parallel(inward, other_inward):
        if inward.dot(other_inward) > 0:
            return None
        # Opposite directions only meet end to end on a common line.
        if (other_point - point).cross(inward).Length > COLLINEAR_TOLERANCE:
            return None

    crossing = axes_crossing(point, inward, other_point, other_inward)
    if not _reaches_corner(point, inward, diagonal, crossing):
        return None
    if not _reaches_corner(other_point, other_inward, other_diagonal, crossing):
        return None
    return Joint(first, at_start, second, other_at_start, crossing)


def _reaches_corner(end, inward, diagonal, crossing):
    """Whether ``crossing`` is a corner for the member end: within reach and not deep inside it."""
    if (crossing - end).Length > EXTENSION_LIMIT * diagonal:
        return False
    # A crossing deep inside a member is a T or a cross, not a corner.
    return (crossing - end).dot(inward) <= CORNER_DEPTH * diagonal


def _skipped_points(joints, members):
    """Group skipped joints that share member ends into one reported point each."""
    owner = {}

    def root(end):
        while owner.setdefault(end, end) != end:
            end = owner[end]
        return end

    for joint in joints:
        first, second = (root(end) for end in joint.ends)
        owner[first] = second

    groups = {}
    for end in owner:
        groups.setdefault(root(end), []).append(end)

    skipped = []
    for ends in groups.values():
        points = [path_end(members[index][0], at_start)[0] for index, at_start in ends]
        center = sum(points[1:], points[0]) * (1.0 / len(points))
        skipped.append(SkippedPoint(center, sorted({index for index, _ in ends})))
    return skipped

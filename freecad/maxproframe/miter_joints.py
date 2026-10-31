"""Miter joints found among selected members from their path ends.

Two members form a joint when the closest pair of their path ends meet: the crossing
of both end axes lies within the extension limit of each end, and the members are not
parallel in the same direction. A member end claimed by two or more joints is a point
where three or more members meet; those joints are skipped and the point is reported.
"""

import itertools

from freecad.maxproframe.miter_geometry import EXTENSION_LIMIT, _axes_crossing, _meeting_ends

# Unit-vector cross product below which two axes count as parallel.
PARALLEL_TOLERANCE = 1e-7
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


def end_frame(edge, at_start):
    """Path end point and the unit direction from it into the member."""
    param = edge.FirstParameter if at_start else edge.LastParameter
    tangent = edge.tangentAt(param).normalize()
    return edge.valueAt(param), tangent if at_start else -tangent


def _joint(first, first_member, second, second_member):
    edge, diagonal = first_member
    other_edge, other_diagonal = second_member
    at_start, other_at_start = _meeting_ends(edge, other_edge)
    point, inward = end_frame(edge, at_start)
    other_point, other_inward = end_frame(other_edge, other_at_start)

    if inward.cross(other_inward).Length < PARALLEL_TOLERANCE:
        if inward.dot(other_inward) > 0:
            return None
        # Opposite directions only meet end to end on a common line.
        if (other_point - point).cross(inward).Length > COLLINEAR_TOLERANCE:
            return None

    crossing = _axes_crossing(point, inward, other_point, other_inward)
    for end, direction, size in ((point, inward, diagonal), (other_point, other_inward, other_diagonal)):
        if (crossing - end).Length > EXTENSION_LIMIT * size:
            return None
        # A crossing deep inside a member is a T or a cross, not a corner.
        if (crossing - end).dot(direction) > size:
            return None
    return Joint(first, at_start, second, other_at_start, crossing)


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
        points = [end_frame(members[index][0], at_start)[0] for index, at_start in ends]
        center = sum(points[1:], points[0]) * (1.0 / len(points))
        skipped.append(SkippedPoint(center, sorted({index for index, _ in ends})))
    return skipped

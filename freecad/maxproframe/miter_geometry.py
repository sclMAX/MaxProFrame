"""Miter planes derived from the real position of attached profiles.

Each member contributes its path edge and the centroid of its placed cross-section.
The miter plane reflects one member axis onto the other: it passes through the
crossing of both axes and its normal is ``u1 - u2``, where ``u1`` and ``u2`` point
from the joint into each member.
"""

import math

import FreeCAD as App
import Part

TOLERANCE = 1e-7
# Squared sine of the angle below which two unit axes count as parallel.
PARALLEL_TOLERANCE = 1e-7
# Longest extension, in section diagonals, before a joint is refused as too far.
EXTENSION_LIMIT = 10.0
# How far, in mm, the points measuring how far a body reaches may stray from its curved edges.
REACH_DEFLECTION = 0.01
# How far, in mm, a body end must be from the profile end to count as moved by a trim.
MOVED_TOLERANCE = 1e-3


class MiterError(RuntimeError):
    pass


class Member:
    """A profile path edge and the axis of its placed section."""

    def __init__(self, edge, profile_shape):
        self.edge = edge
        # The section is taken at a path point the profile body covers, then moved from there to each end.
        self.param = _section_parameter(edge, profile_shape)
        self.section = _section(edge, profile_shape, self.param)

    def end(self, at_start):
        """Point, inward direction (into the member) and section centroid at one end."""
        point, inward, _ = self._end_frame(at_start)
        section = self.section_at(at_start)
        centroid = section.CenterOfMass if section.Faces else section.BoundBox.Center
        return point, inward, centroid

    def section_at(self, at_start):
        """The section moved to one end of the path."""
        _, _, placement = self._end_frame(at_start)
        return self.section.transformed(placement.toMatrix())

    def _end_frame(self, at_start):
        point, inward = path_end(self.edge, at_start)
        tangent = inward if at_start else -inward
        section_point = self.edge.valueAt(self.param)
        section_tangent = self.edge.tangentAt(self.param).normalize()
        # A planar sweep keeps the section offset in the edge frame: turn it with the tangent.
        rotation = App.Rotation(section_tangent, tangent)
        placement = App.Placement(point - rotation.multVec(section_point), rotation)
        return point, inward, placement


class MiterPlane:
    """Plane at ``origin`` with unit ``normal`` pointing into the kept member."""

    def __init__(self, origin, normal, inward, section):
        self.origin = origin
        self.normal = normal
        self.inward = inward
        self.section = section

    def cut_angle(self):
        """Angle between the cut and a square cut, in degrees."""
        cosine = min(1.0, abs(self.normal.dot(self.inward)))
        return math.degrees(math.acos(cosine))

    def shifted(self, distance):
        return MiterPlane(self.origin + self.normal * distance, self.normal, self.inward, self.section)

    def extension(self, tool="End Miter"):
        """Prism that prolongs the member end past the plane, or None when the end already passes it.

        ``tool`` names the command in the error messages.
        """
        if not self.section.Faces:
            raise MiterError(f"{tool}: the profile section is not a closed face and cannot be extended.")
        along = self.normal.dot(self.inward)
        diagonal = self.section.BoundBox.DiagonalLength
        needed = (self.section.CenterOfMass - self.origin).dot(self.normal) / along
        # The farthest section point lies at most one diagonal away from the axis; a sharp
        # angle (small ``along``) stretches that margin, so the limit bounds the whole prism.
        length = needed + diagonal / along
        if length > EXTENSION_LIMIT * diagonal:
            raise MiterError(
                f"{tool}: the joint is too far to extend the profile ({length:.1f} mm, "
                f"limit {EXTENSION_LIMIT * diagonal:.1f} mm)."
            )
        if length <= TOLERANCE:
            return None
        return self.section.extrude(-self.inward * length)

    def removal_volume(self, shape):
        """Half-space beyond the plane, large enough to cover ``shape``."""
        box = shape.BoundBox
        size = 2.0 * (box.DiagonalLength + (box.Center - self.origin).Length) + 10.0
        x_dir = _perpendicular(self.normal)
        y_dir = self.normal.cross(x_dir)
        corner = self.origin - x_dir * (size / 2.0) - y_dir * (size / 2.0)
        face = Part.makePlane(size, size, corner, self.normal, x_dir)
        return face.extrude(-self.normal * size)


def miter_plane(member, other):
    """Plane that cuts ``member`` where it meets ``other``."""
    at_start, other_at_start = meeting_ends(member.edge, other.edge)
    _, inward, centroid = member.end(at_start)
    _, other_inward, other_centroid = other.end(other_at_start)

    normal = inward - other_inward
    if normal.Length < TOLERANCE:
        raise MiterError("End Miter: profiles overlap in the same direction.")
    normal.normalize()
    origin = axes_crossing(centroid, inward, other_centroid, other_inward)
    return MiterPlane(origin, normal, inward, member.section_at(at_start))


def real_stretch(edge, shape, base_shape):
    """The straight path ``edge`` with each end moved to where ``shape`` really ends, when a trim moved it.

    A trim or cutout (``shape``) may end its profile (``base_shape``) away from the path ends; End Miter meets
    members where their bodies end. An end ``shape`` reaches as far as the profile keeps the path end, so a
    profile without trims keeps its path. A curved path, or a shape with nothing along it, keeps ``edge``.
    """
    if not isinstance(edge.Curve, Part.Line):
        return edge
    start = edge.valueAt(edge.FirstParameter)
    direction = edge.valueAt(edge.LastParameter) - start
    length = direction.Length
    reach, base_reach = _reach(shape, start, direction), _reach(base_shape, start, direction)
    if length < TOLERANCE or reach is None or base_reach is None:
        return edge
    low, high = (
        moved if abs(moved - kept) > MOVED_TOLERANCE else path
        for moved, kept, path in zip(reach, base_reach, (0.0, length))
    )
    if high - low < TOLERANCE:
        return edge
    direction.normalize()
    return Part.LineSegment(start + direction * low, start + direction * high).toShape()


def _reach(shape, start, direction):
    """(lowest, highest) distance ``shape`` reaches along ``direction`` from ``start``, or None for no shape."""
    if shape is None or shape.isNull() or not shape.Edges:
        return None
    unit = App.Vector(direction).normalize()
    # Points along every edge: a curved edge (an oblique cut of a round tube) reaches past its vertices.
    points = [point for edge in shape.Edges for point in edge.discretize(Deflection=REACH_DEFLECTION)]
    distances = [(point - start).dot(unit) for point in points]
    return min(distances), max(distances)


def path_end(edge, at_start):
    """Path end point and the unit direction from it into the member."""
    param = edge.FirstParameter if at_start else edge.LastParameter
    tangent = edge.tangentAt(param).normalize()
    return edge.valueAt(param), (tangent if at_start else -tangent)


def meeting_ends(edge, other):
    """(member at start, other at start) for the closest pair of path ends."""
    pairs = []
    for at_start in (True, False):
        for other_at_start in (True, False):
            a = edge.valueAt(edge.FirstParameter if at_start else edge.LastParameter)
            b = other.valueAt(other.FirstParameter if other_at_start else other.LastParameter)
            pairs.append(((a - b).Length, at_start, other_at_start))
    _, at_start, other_at_start = min(pairs, key=lambda pair: pair[0])
    return at_start, other_at_start


def parallel(d1, d2):
    """Whether two unit directions are parallel, in the same or the opposite sense."""
    b = d1.dot(d2)
    return 1.0 - b * b < PARALLEL_TOLERANCE


def axes_crossing(p1, d1, p2, d2):
    """Midpoint of the closest points of two lines; the midpoint of p1 and p2 when parallel."""
    if parallel(d1, d2):
        return (p1 + p2) * 0.5
    w0 = p1 - p2
    b = d1.dot(d2)
    denominator = 1.0 - b * b
    d = d1.dot(w0)
    e = d2.dot(w0)
    s = (b * e - d) / denominator
    t = (e - b * d) / denominator
    return (p1 + d1 * s + p2 + d2 * t) * 0.5


def _mid_parameter(edge):
    return (edge.FirstParameter + edge.LastParameter) / 2.0


def _slice(edge, profile_shape, param):
    """Wires of the profile cut by the plane normal to the path at ``param``."""
    point = edge.valueAt(param)
    tangent = edge.tangentAt(param).normalize()
    return profile_shape.slice(tangent, tangent.dot(point))


def _section_parameter(edge, profile_shape):
    """Path parameter where the profile body is cut: mid-edge, or the path point nearest the body bounding box centre.

    End offsets can shorten the body past the path midpoint, which then lies outside the body.
    """
    param = _mid_parameter(edge)
    if _slice(edge, profile_shape, param) or profile_shape.isNull():
        return param
    _, points, _ = edge.distToShape(Part.Vertex(profile_shape.BoundBox.Center))
    nearest = edge.Curve.parameter(points[0][0])
    return min(max(nearest, edge.FirstParameter), edge.LastParameter)


def _section(edge, profile_shape, param=None):
    """Profile section at ``param`` (mid-edge by default): a face, or its wires when they do not bound one."""
    param = _mid_parameter(edge) if param is None else param
    point = edge.valueAt(param)
    wires = _slice(edge, profile_shape, param)
    if not wires:
        raise MiterError("End Miter: the profile does not cross its own path.")
    reach = profile_shape.BoundBox.DiagonalLength
    nearest = min((w.BoundBox.Center - point).Length for w in wires)
    wires = [w for w in wires if (w.BoundBox.Center - point).Length <= nearest + reach / 2.0]
    try:
        return Part.makeFace(wires, "Part::FaceMakerBullseye")
    except Part.OCCError:
        return Part.Compound(wires)


def _perpendicular(vector):
    helper = App.Vector(1, 0, 0) if abs(vector.x) < 0.9 else App.Vector(0, 1, 0)
    result = vector.cross(helper)
    result.normalize()
    return result

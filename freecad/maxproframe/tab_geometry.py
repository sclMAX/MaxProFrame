"""Tabs of a T joint Interlock: the crossbar wall ends in tabs through slots cut in the rail wall, at any angle
(odd/tasks/t-joint-tabs.md, S3, S4, S5).

A T joint is a crossbar (the arriving tube, trimmed against a face of the other one) butting against the rail (the
receiving tube). ``TJoint`` gives what the geometry needs, in one coordinate system (global, or the container of both
tubes), all known to a TrimmedProfile Extend / Cut and its target:

- ``crossbar_face``: the planar outer face of the crossbar wall that carries the tabs, oriented outward (a face of the
  crossbar solid); its extent across the crossbar axis is the flat part of the wall, outside its corner radii (D4).
- ``crossbar_thickness`` (t_c), and ``direction`` (d): the crossbar axis, toward the rail.
- ``rail_face``: the planar outer face of the rail wall the crossbar butts against (plane P), oriented outward, toward
  the crossbar; it is the flat part of that wall (D4). ``rail_thickness`` (t_r).
- ``end``: (point, normal) of the plane the trimmed crossbar ends on (the Extend / Cut plane, its gap included); None
  stands for P itself.
- ``gap``: how far ``end`` stops before the plane the crossbar was trimmed to, the Gap of its Extend / Cut (S8): the
  joint is checked on the end moved back toward the rail by it, the tabs cross it.

In the crossbar wall plane, with a across the axis and s along d, each tab lies on the flat part of the wall where
``TabSettings.bounds`` puts it and runs along d from the crossbar end to the plane ``TabSettings.tab_length`` across
the rail wall, measured along the normal of P (D3), across the trim gap too when the crossbar ends before P (S8).
Every tab face is a face of the wall or swept along its normal, the tip corners chamfered or rounded in the wall plane
(D2): where the crossbar meets P obliquely across its wall thickness, the tip ends at that depth on the shallower face
of the wall (so the tab goes all the way through) and the root starts at the crossbar end on the face that ends
farther back (so the tab fuses with the crossbar end). Each slot is the projection along the normal of P of the square
tab (its tip corners left square) inside the rail wall, grown by the clearance (half on each side, its corners kept
sharp) and cut square through the rail wall (D2): at an oblique joint it is longer than the tab is thick (S5).
"""

import math
from dataclasses import dataclass
from typing import NamedTuple

import FreeCAD as App
import Part

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.interlock_geometry import (
    CHAMFER,
    SIZE_TOLERANCE,
    SQUARE,
    TIP_STEP,
    InterlockError,
    tabs_misfit,
)

# |cos| between the crossbar axis and a plane normal below which the axis runs along the plane.
PARALLEL_TOLERANCE = 1e-6
# How far the slot tools reach past both faces of the rail wall, so they cut it through (mm).
SLOT_MARGIN = 1.0
# Slot area allowed off the rail face, for rounding (mm²).
AREA_TOLERANCE = 1e-6
# Points of a footprint closer than this, or this close to the line of their neighbours, are dropped (mm).
POINT_TOLERANCE = 1e-7
# Shortest edge kept in a tab outline (mm).
EDGE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class TJoint:
    """A T joint between a crossbar and the rail it butts against (the module docstring says each field).

    ``names`` are the labels of the (crossbar, rail) tubes, for the refusals.
    """

    names: tuple
    crossbar_face: object
    crossbar_thickness: float
    direction: object
    rail_face: object
    rail_thickness: float
    end: tuple = None
    gap: float = 0.0


class TabShapes(NamedTuple):
    """The ``tabs`` to fuse with the crossbar end and the ``slots`` to cut from the rail, one solid per tab, in the
    coordinates of the ``TJoint``; listed in the order of the tabs across the crossbar wall."""

    tabs: list
    slots: list


def check(settings, joint):
    """Raise InterlockError when the tabs ``settings`` (``TabSettings``) do not fit ``joint`` (``TJoint``)."""
    _Layout(settings, joint).check()


def make_tabs(settings, joint):
    """The ``TabShapes`` of the tabs ``settings`` at ``joint``; raises InterlockError as ``check`` does."""
    layout = _Layout(settings, joint)
    footprints = layout.check()
    return TabShapes([layout.tab(*bounds) for bounds in layout.bounds], [layout.slot(face) for face in footprints])


def _unit(vector):
    found = App.Vector(vector)
    if found.Length < SIZE_TOLERANCE:
        raise ValueError("A direction of the T joint is a null vector.")
    return found.normalize()


def _perpendicular(vector):
    helper = App.Vector(1, 0, 0) if abs(vector.x) < 0.9 else App.Vector(0, 1, 0)
    return vector.cross(helper).normalize()


class _Layout:
    """The tabs of ``settings`` at ``joint`` in the crossbar wall frame: O on the outer face, in the middle of its
    flat part; A across the axis, D along it toward the rail, N the outward wall normal (z = 0 on the outer face,
    -t_c on the inner one)."""

    def __init__(self, settings, joint):
        self.settings, self.names = settings, tuple(joint.names)
        face = joint.crossbar_face
        self.N = _unit(face.normalAt(0, 0))
        d = _unit(joint.direction)
        if abs(d.dot(self.N)) > PARALLEL_TOLERANCE:
            raise ValueError("The crossbar face of a T joint must be a wall along the crossbar axis.")
        self.D = _unit(d - self.N * d.dot(self.N))
        self.A = self.N.cross(self.D)
        origin = face.CenterOfMass
        points = [point for edge in face.OuterWire.Edges for point in edge.discretize(Deflection=0.01)]
        across = [(point - origin).dot(self.A) for point in points]
        self.span = max(across) - min(across)
        self.O = origin + self.A * ((max(across) + min(across)) / 2)
        self.t_c, self.t_r = float(joint.crossbar_thickness), float(joint.rail_thickness)
        self.rail_face = joint.rail_face
        self.n_r = _unit(joint.rail_face.normalAt(0, 0))
        self.Q = joint.rail_face.CenterOfMass
        end_point, end_normal = (self.Q, self.n_r) if joint.end is None else joint.end
        self.E, self.m = App.Vector(end_point), _unit(end_normal)
        # The end normal looks back, away from the rail: the end moved by -gap along it is where the trim was.
        if self.m.dot(self.D) > 0:
            self.m = -self.m
        self.gap = float(joint.gap)
        self.L = settings.tab_length(self.t_r)
        self.bounds = settings.bounds(self.span) if int(settings.count) >= 1 else []

    # Refusals.

    def _no_end(self):
        return InterlockError(
            translate(
                "MaxProFrame", "There is no T joint between {} and {}: {crossbar} does not end on the face of {rail}."
            ).format(*self.names, crossbar=self.names[0], rail=self.names[1])
        )

    def _off_rail(self):
        return InterlockError(
            translate(
                "MaxProFrame",
                "The slots of the T joint between {} and {} do not fall on the flat part of the face of {rail}.",
            ).format(*self.names, rail=self.names[1])
        )

    def check(self):
        """Raise InterlockError when the tabs do not fit; else the footprint faces of the slots, on P."""
        self.settings.check(self.names, self.span)
        self._check_joint()
        self._check_tips()
        return self._check_slots()

    def _check_joint(self):
        """The crossbar axis crosses P toward the rail and the crossbar ends on P: not inside the rail wall, nor
        farther before it than the rail wall is thick; with a trim gap, its end moved back toward the rail by the gap
        does (S8)."""
        along = self.D.dot(self.n_r)
        if abs(along) < PARALLEL_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame", "There is no T joint between {} and {}: {crossbar} runs along the face of {rail}."
                ).format(*self.names, crossbar=self.names[0], rail=self.names[1])
            )
        if along > 0 or abs(self.D.dot(self.m)) < PARALLEL_TOLERANCE:
            raise self._no_end()
        for a in (-self.span / 2, self.span / 2):
            for z in (0.0, -self.t_c):
                trimmed = self._s_on(self.E, self.m, -self.gap, a, z)
                depth = (self.Q - self._point(a, trimmed, z)).dot(self.n_r)
                if depth > SIZE_TOLERANCE or depth < -self.t_r - SIZE_TOLERANCE:
                    raise self._no_end()
            if self._s_tip(a) - self._s_far(a) <= SIZE_TOLERANCE:
                raise self._no_end()

    def _check_tips(self):
        """The tip size is at most what lets both tip corners of every tab fit on its tip edge and on the part of its
        sides past the crossbar end, rounded down to 0.1 mm."""
        settings = self.settings
        if settings.tip == SQUARE:
            return
        limit = min(self._tip_limit(*bounds) for bounds in self.bounds)
        maximum = round(math.floor(limit / TIP_STEP + SIZE_TOLERANCE) * TIP_STEP, 6)
        if settings.tip_size < -SIZE_TOLERANCE or settings.tip_size > maximum + SIZE_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame", "The tab tips of the T joint between {} and {} must be between 0 and {max:g} mm."
                ).format(*self.names, max=maximum)
            )

    def _tip_limit(self, a0, a1):
        root0, tip0, tip1, root1 = self._corners(a0, a1)
        edge = (tip1 - tip0).Length
        free = (self._s_tip(a0) - self._s_far(a0), self._s_tip(a1) - self._s_far(a1))
        if self.settings.tip == CHAMFER:
            return min(edge / 2, *free)
        halves = ((root0 - tip0).getAngle(tip1 - tip0) / 2, (tip0 - tip1).getAngle(root1 - tip1) / 2)
        return min(edge / sum(1 / math.tan(half) for half in halves), *(f * math.tan(h) for f, h in zip(free, halves)))

    def _check_slots(self):
        """The footprint faces of the slots: apart from each other (else the slots join and the tabs do not fit), and
        the tab footprints they grow on the rail face (S9: the clearance may run past its edge)."""
        footprints = [self._footprint(*bounds) for bounds in self.bounds]
        faces = [grown for _, grown in footprints]
        for index, face in enumerate(faces[:-1]):
            for other in faces[index + 1 :]:
                if face.distToShape(other)[0] <= SIZE_TOLERANCE:
                    raise tabs_misfit(self.names)
        for tab, _ in footprints:
            if tab.Area - tab.common(self.rail_face).Area > AREA_TOLERANCE:
                raise self._off_rail()
        return faces

    # The crossbar wall frame.

    def _point(self, a, s, z=0.0):
        return self.O + self.A * a + self.D * s + self.N * z

    def _s_on(self, point, normal, offset, a, z):
        """s where the line of (a, z) along D meets the plane through ``point`` of unit ``normal`` moved by
        ``offset`` along it."""
        return (offset - (self.O - point).dot(normal) - a * self.A.dot(normal) - z * self.N.dot(normal)) / self.D.dot(
            normal
        )

    def _s_end(self, a, z):
        return self._s_on(self.E, self.m, 0.0, a, z)

    def _s_root(self, a):
        """Where the tab starts: the crossbar end on the face of its wall that ends farther back."""
        return min(self._s_end(a, z) for z in (0.0, -self.t_c))

    def _s_far(self, a):
        """Where the crossbar end is on the face of its wall that ends farther on."""
        return max(self._s_end(a, z) for z in (0.0, -self.t_c))

    def _s_tip(self, a):
        """Where the tab ends: ``L`` across the rail wall on the face of the crossbar wall that gets there last."""
        return max(self._s_on(self.Q, self.n_r, -self.L, a, z) for z in (0.0, -self.t_c))

    def _corners(self, a0, a1):
        """(root at a0, tip at a0, tip at a1, root at a1) of the tab from a0 to a1, as (a, s, 0) vectors."""
        return (
            App.Vector(a0, self._s_root(a0), 0),
            App.Vector(a0, self._s_tip(a0), 0),
            App.Vector(a1, self._s_tip(a1), 0),
            App.Vector(a1, self._s_root(a1), 0),
        )

    # Shapes.

    def tab(self, a0, a1, tips=True):
        """The solid of the tab from a0 to a1 across the wall: its outline in the outer face plane swept through
        the wall; the tip corners chamfered or rounded when ``tips``."""
        root0, tip0, tip1, root1 = self._corners(a0, a1)
        k = float(self.settings.tip_size)
        shape = self.settings.tip if tips and k > SIZE_TOLERANCE else SQUARE
        first = _corner(tip0, root0, tip1, shape, k)
        second = _corner(tip1, tip0, root1, shape, k)
        edges = []

        def place(at):
            return self._point(at.x, at.y)

        def line(start, end):
            if (end - start).Length > EDGE_TOLERANCE:
                edges.append(Part.LineSegment(place(start), place(end)).toShape())

        def turn(corner):
            start, middle, end = corner
            if shape == CHAMFER:
                line(start, end)
            elif middle is not None:
                edges.append(Part.Arc(place(start), place(middle), place(end)).toShape())

        line(root0, first[0])
        turn(first)
        line(first[2], second[0])
        turn(second)
        line(second[2], root1)
        line(root1, root0)
        return Part.Face(Part.Wire(edges)).extrude(self.N * -self.t_c)

    def _rail_axes(self):
        e1 = _perpendicular(self.n_r)
        return e1, self.n_r.cross(e1)

    def _footprint(self, a0, a1):
        """(tab, slot): the faces, on P, of the tab from a0 to a1 (the square tab inside the rail wall seen along the
        normal of P) and of its slot (that face grown by the clearance)."""
        square = self.tab(a0, a1, tips=False)
        e1, e2 = self._rail_axes()
        box = square.BoundBox
        center = box.Center - self.n_r * (box.Center - self.Q).dot(self.n_r)
        size = 2 * (box.DiagonalLength + (center - self.Q).Length) + 10
        plane = Part.makePlane(size, size, center - e1 * (size / 2) - e2 * (size / 2), self.n_r, e1)
        inside = square.common(plane.extrude(self.n_r * -self.t_r))
        if not inside.Vertexes:
            raise self._no_end()
        hull = _hull([((v.Point - self.Q).dot(e1), (v.Point - self.Q).dot(e2)) for v in inside.Vertexes])
        if len(hull) < 3:
            raise self._no_end()
        grown = _grow(hull, float(self.settings.clearance) / 2)
        return tuple(self._face_on_p(polygon, e1, e2) for polygon in (hull, grown))

    def _face_on_p(self, polygon, e1, e2):
        """The face on P of the 2D ``polygon`` in its (e1, e2) axes from Q."""
        points = [self.Q + e1 * x + e2 * y for x, y in polygon]
        return Part.Face(Part.makePolygon(points + points[:1]))

    def slot(self, footprint):
        """The slot tool of ``footprint``: swept along the normal of P through the rail wall, past both its faces."""
        tool = footprint.translated(self.n_r * SLOT_MARGIN)
        return tool.extrude(self.n_r * -(self.t_r + 2 * SLOT_MARGIN))


def _corner(corner, previous, following, shape, k):
    """(start, middle, end) of the tip ``corner`` of a tab outline between the edges from ``previous`` and to
    ``following``: the chamfer of legs ``k`` (middle None), the arc of radius ``k`` tangent to both edges, or the
    corner itself for Square."""
    if shape == SQUARE:
        return corner, None, corner
    back, on = (previous - corner).normalize(), (following - corner).normalize()
    if shape == CHAMFER:
        return corner + back * k, None, corner + on * k
    half = back.getAngle(on) / 2
    tangent = k / math.tan(half)
    bisector = (back + on).normalize()
    center = corner + bisector * (k / math.sin(half))
    return corner + back * tangent, center - bisector * k, corner + on * tangent


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull(points):
    """The convex hull of 2D ``points``, counterclockwise, without repeated or collinear points."""
    found = []
    for point in sorted(points):
        if not found or math.dist(found[-1], point) > POINT_TOLERANCE:
            found.append(point)
    if len(found) < 3:
        return found

    def half(ordered):
        chain = []
        for point in ordered:
            while len(chain) >= 2 and _cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain[:-1]

    hull = half(found) + half(found[::-1])
    kept = []
    for index, point in enumerate(hull):
        before, after = hull[index - 1], hull[(index + 1) % len(hull)]
        length = math.dist(before, after)
        if length > POINT_TOLERANCE and abs(_cross(before, point, after)) / length > POINT_TOLERANCE:
            kept.append(point)
    return kept


def _grow(polygon, offset):
    """The convex counterclockwise ``polygon`` with every edge moved out by ``offset``, its corners kept sharp."""
    if offset <= SIZE_TOLERANCE:
        return polygon
    lines = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        lines.append(((start[0] + dy / length * offset, start[1] - dx / length * offset), (dx, dy)))
    grown = []
    for index, ((x2, y2), (dx2, dy2)) in enumerate(lines):
        (x1, y1), (dx1, dy1) = lines[index - 1]
        t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / (dx1 * dy2 - dy1 * dx2)
        grown.append((x1 + dx1 * t, y1 + dy1 * t))
    return grown

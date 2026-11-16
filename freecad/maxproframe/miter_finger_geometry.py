"""Fingers at the inner vertex of an End Miter corner between two separate tubes (odd/tasks/miter-fingers.md, T1: S2,
S3, S4, D3, D4).

Two straight tubes A and B meet at a corner, each cut by its own End Miter against the other. ``MiterCorner`` gives
what the geometry needs, in one coordinate system (global, or the container of both tubes), per tube (``MiterTube``):

- ``face``: the planar outer face of its inner wall (the wall on the inside of the corner), oriented outward, toward
  the inside of the corner; ``thickness`` (t): its wall thickness.
- ``direction``: its axis, toward the corner.
- ``section``: its cross-section face (the profile section), anywhere along its axis: the fingers are the tube
  prolonged past its miter (corner radii and side walls included), so they keep its section.
- ``miter``: (point, normal) of the plane its End Miter really cuts it on, the gap included (the miter plane shifted
  by half the End Miter Gap into the tube, as ``TrimmedProfile._end_miter`` does with ``miter_planes``); either sense
  of the normal.

The corner axis W runs along both inner wall faces (n_A x n_B); V, the inner vertex, is where both face planes meet,
at the middle of the tubes along W. In the corner plane each tube has its frame: x along its axis toward the corner
from V, y into the tube from its inner wall face. The band of a tube is y in [0, s], s the finger depth (0: the larger
of the wall thicknesses and corner radii, ``unfolded_geometry.automatic_step_depth``). Both bands overlap in a
parallelogram at V (odd/tasks/stepped-corners.md L8, ``unfolded_geometry._OpenStep``): along W the tubes are split
into the levels of ``FingerSettings.bounds``; in each level one tube, the owner (A in the first one, alternating; B
first with ``flip``, D3), covers the whole overlap: its finger is its tube prolonged past its own miter plane (across
the gap, S4), within its band, up to its cross-section through the farthest vertex of the overlap less half the
clearance g. The other tube loses its band from its own cross-section g past the overlap on toward the corner, and
whatever the finger takes from it below its band, grown by g (g/2 past the finger tip, g past its other faces); next
levels overlap by g along W, so the finger sides open by g, g/2 each. Below the band the corner stays the plain miter
(S3). Chamfered or round tips are cut from the finger tip corners next to another finger, in the plane of the inner
wall, swept through the band.

Every cut is square to the wall it goes through (D4): tube cross-sections, planes parallel to the inner walls, planes
across W and the tips swept along the inner wall normal. So at an oblique corner the cross-section cut of the tube
that does not own a level leaves a notch at the inner vertex: a triangle of legs s and s |cot(angle)| (0 at 90
degrees), as the fingers of a folded corner do.
"""

import math
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple

import FreeCAD as App
import Part

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.interlock_geometry import CHAMFER, SIZE_TOLERANCE, SQUARE, InterlockError
from freecad.maxproframe.unfolded_geometry import automatic_step_depth

# |cos| between directions that must be square to each other, below which they count as such.
PARALLEL_TOLERANCE = 1e-6
# How far the inner walls may end off their miter planes, and how much the tubes may differ along the corner (mm).
MEET_TOLERANCE = 1e-3
# How far the cut tools reach past the faces they need, so no cut face lies on a face of the tube (mm).
MARGIN = 1.0
# The largest depth is rounded down to it, so the range in the message is accepted whole (mm).
DEPTH_STEP = 0.1
AREA_TOLERANCE = 1e-9
# How far, in mm, the points measuring a section may stray from its curved edges.
DEFLECTION = 0.01


@dataclass(frozen=True)
class MiterTube:
    """One tube of an End Miter corner (the module docstring says each field); ``name`` labels it in the refusals."""

    name: str
    face: object
    thickness: float
    direction: object
    section: object
    miter: tuple


@dataclass(frozen=True)
class MiterCorner:
    """The End Miter corner between tube ``a`` (the first face given: it owns the first finger, D3) and tube ``b``."""

    a: MiterTube
    b: MiterTube

    @property
    def names(self):
        return (self.a.name, self.b.name)


class TubeFingers(NamedTuple):
    """What one tube of the corner gets: the ``fingers`` to fuse with it (solids past its miter plane), the ``cuts``
    to remove from it (where the other tube's fingers go, with the clearance) and ``tip``: (point, unit direction of
    its axis toward the corner) of the cross-section its fingers end on."""

    fingers: list
    cuts: list
    tip: tuple


class MiterFingerShapes(NamedTuple):
    """``a`` and ``b``: the ``TubeFingers`` of both tubes; ``owners``: per finger level along W, 0 when A covers it,
    1 when B does; ``depth``: the finger depth s used."""

    a: TubeFingers
    b: TubeFingers
    owners: list
    depth: float


def check(settings, corner):
    """Raise InterlockError when the fingers ``settings`` (``FingerSettings``) do not fit ``corner`` (``MiterCorner``)."""
    _Layout(settings, corner).check()


def make_fingers(settings, corner):
    """The ``MiterFingerShapes`` of the fingers ``settings`` at ``corner``; raises InterlockError as ``check`` does."""
    layout = _Layout(settings, corner)
    layout.check()
    return layout.shapes()


def joined(shape, tube):
    """``shape`` of one tube of the corner with its ``TubeFingers`` ``tube``: its fingers fused, the cuts removed."""
    if tube.fingers:
        shape = shape.fuse(tube.fingers)
    if tube.cuts:
        shape = shape.cut(tube.cuts)
    return shape.removeSplitter()


def _unit(vector):
    found = App.Vector(vector)
    if found.Length < SIZE_TOLERANCE:
        raise ValueError("A direction of the miter corner is a null vector.")
    return found.normalize()


def _points(shape):
    return [point for edge in shape.Edges for point in edge.discretize(Deflection=DEFLECTION)]


def _clip(polygon, normal, limit):
    """The convex ``polygon`` [(x, y)] cut to the points q with ``normal`` . q <= ``limit``."""
    kept = []
    for index, point in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        here = normal[0] * point[0] + normal[1] * point[1] - limit
        there = normal[0] * following[0] + normal[1] * following[1] - limit
        if here <= 0:
            kept.append(point)
        if (here < 0 < there) or (there < 0 < here):
            ratio = here / (here - there)
            kept.append((point[0] + ratio * (following[0] - point[0]), point[1] + ratio * (following[1] - point[1])))
    return kept


def _area(polygon):
    pairs = zip(polygon, polygon[1:] + polygon[:1])
    return abs(sum(x * ny - nx * y for (x, y), (nx, ny) in pairs)) / 2


def _dot(first, second):
    return first[0] * second[0] + first[1] * second[1]


@dataclass
class _Side:
    """One tube in the corner frame: 3D unit ``n`` (its inner wall face normal), ``d`` (its axis toward the corner),
    ``m`` (its miter plane normal, into the tube) and ``plane`` (a point of that plane); their 2D forms and the plane
    offset ``c`` once the frame is known."""

    tube: MiterTube
    n: object
    d: object
    m: object
    plane: object
    n2: tuple = None
    d2: tuple = None
    m2: tuple = None
    c: float = 0.0
    depth: float = 0.0
    radius: float = 0.0

    @property
    def t(self):
        return float(self.tube.thickness)


class _Layout:
    """The fingers ``settings`` at ``corner`` in its frame (the module docstring): V the inner vertex, W the corner
    axis, (U1, U2) the corner plane, U1 along A's axis; 2D points are (x, y) of that plane from V."""

    def __init__(self, settings, corner):
        self.settings, self.names = settings, tuple(corner.names)
        self.sides = [self._side(tube) for tube in (corner.a, corner.b)]

    # Refusals.

    def _not_a_corner(self):
        return InterlockError(
            translate(
                "MaxProFrame", "The faces of {} and {} are not the inner walls of an End Miter corner between them."
            ).format(*self.names)
        )

    def _misfit(self):
        return InterlockError(
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} do not fit at this angle: make the depth smaller.",
            ).format(*self.names)
        )

    def _across_the_gap(self):
        return InterlockError(
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} do not reach across the miter gap: make the gap smaller "
                "or the depth larger.",
            ).format(*self.names)
        )

    # The corner frame.

    def _side(self, tube):
        face = tube.face
        if not isinstance(face.Surface, Part.Plane):
            raise self._not_a_corner()
        n, d = _unit(face.normalAt(0, 0)), _unit(tube.direction)
        # A face across the axis (an end, the miter face) is no wall of the tube.
        if abs(d.dot(n)) > PARALLEL_TOLERANCE:
            raise self._not_a_corner()
        point, normal = tube.miter
        m = _unit(normal)
        if m.dot(d) > 0:
            m = -m
        return _Side(tube, n, d, m, App.Vector(point))

    def check(self):
        """Raise InterlockError when the faces are no End Miter corner or the fingers do not fit it."""
        self._frame()
        self.settings.check(self.names, self.span)
        self._check_depth()
        self._check_fit()

    def _frame(self):
        """V, W, U1, U2, the span along W and each side's 2D forms; refuses faces that are not the inner walls of two
        tubes meeting at their End Miters (planar corner, inner walls facing each other, parallel miter planes with the
        inner vertex half way between them, each inner wall ending on its own) or tubes of another size along W."""
        a, b = self.sides
        w = a.n.cross(b.n)
        if w.Length < PARALLEL_TOLERANCE:
            raise self._not_a_corner()
        self.W = w.normalize()
        square = (side.d.dot(self.W) for side in self.sides)
        if any(abs(value) > PARALLEL_TOLERANCE for value in square) or abs(a.m.dot(self.W)) > PARALLEL_TOLERANCE:
            raise self._not_a_corner()
        # Each inner wall faces the other tube coming: its normal points against the other axis.
        if a.n.dot(b.d) > -PARALLEL_TOLERANCE or b.n.dot(a.d) > -PARALLEL_TOLERANCE:
            raise self._not_a_corner()
        if a.m.dot(b.m) > -1 + PARALLEL_TOLERANCE:
            raise self._not_a_corner()
        self.gap = (a.plane - b.plane).dot(a.m)
        if self.gap < -MEET_TOLERANCE:
            raise self._not_a_corner()
        low, high = self._extent(a.tube.section)
        if any(
            abs(found - wanted) > MEET_TOLERANCE for found, wanted in zip(self._extent(b.tube.section), (low, high))
        ):
            raise InterlockError(
                translate(
                    "MaxProFrame", "{} and {} are not the same size along their corner: their fingers cannot match."
                ).format(*self.names)
            )
        self.span = high - low
        # V: on both face planes, half way along W.
        q_a, q_b = a.tube.face.CenterOfMass, b.tube.face.CenterOfMass
        cos = a.n.dot(b.n)
        along_b = b.n.dot(q_b - q_a) / (1 - cos * cos)
        base = q_a + a.n * (-cos * along_b) + b.n * along_b
        self.V = base + self.W * ((low + high) / 2 - self.W.dot(base))
        if abs((self.V - b.plane).dot(a.m) - self.gap / 2) > MEET_TOLERANCE:
            raise self._not_a_corner()
        self.U1 = _unit(a.d - self.W * a.d.dot(self.W))
        self.U2 = self.W.cross(self.U1)
        for side in self.sides:
            # Its inner wall ends on its own miter plane, at the inner vertex moved back by half the gap.
            ends = max((vertex.Point - self.V).dot(side.d) for vertex in side.tube.face.Vertexes)
            if abs(ends - (self.gap / 2) / side.d.dot(side.m)) > MEET_TOLERANCE:
                raise self._not_a_corner()
            side.n2, side.d2, side.m2 = (self._flat(vector) for vector in (side.n, side.d, side.m))
            side.c = (side.plane - self.V).dot(side.m)
            section = _points(side.tube.section)
            side.depth = max((self.V - point).dot(side.n) for point in section)
            across = [vertex.Point.dot(self.W) for vertex in side.tube.face.Vertexes]
            side.radius = max(0.0, (self.span - (max(across) - min(across))) / 2)

    def _extent(self, section):
        if not section.Faces:
            raise ValueError("The section of a tube of a miter corner must be a face.")
        along = [point.dot(self.W) for point in _points(section)]
        return min(along), max(along)

    def _flat(self, vector):
        return (vector.dot(self.U1), vector.dot(self.U2))

    @cached_property
    def depth(self):
        """The finger depth s: the setting, or the larger wall thickness or corner radius of both tubes."""
        if self.settings.depth > SIZE_TOLERANCE:
            return float(self.settings.depth)
        return automatic_step_depth(max(s.t for s in self.sides), max(s.radius for s in self.sides))

    @property
    def g(self):
        return float(self.settings.clearance)

    def _check_depth(self):
        """At least the thicker wall, under half the shallower tube, rounded down to 0.1 mm."""
        thickest = max(side.t for side in self.sides)
        largest = min(side.depth for side in self.sides) / 2 - SIZE_TOLERANCE
        maximum = round(math.floor(largest / DEPTH_STEP + SIZE_TOLERANCE) * DEPTH_STEP, 6)
        if self.depth < thickest - SIZE_TOLERANCE or self.depth > maximum + SIZE_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame",
                    "The finger depth of the corner between {} and {} must be between {min:g} and {max:g} mm.",
                ).format(*self.names, min=thickest, max=maximum)
            )

    def _check_fit(self):
        """Each tube's fingers reach past the other one's miter plane (across the gap, S4) and, with the clearance
        below them, stay clear of the other tube's outer wall (the far wall across its depth)."""
        for owner, other in ((0, 1), (1, 0)):
            mine, theirs = self.sides[owner], self.sides[other]
            finger = self._finger_polygon(owner, 0.0)
            if len(finger) < 3 or _area(finger) <= AREA_TOLERANCE:
                raise self._across_the_gap() if self.gap > SIZE_TOLERANCE else self._misfit()
            if max(_dot(theirs.m2, point) - theirs.c for point in finger) <= SIZE_TOLERANCE:
                raise self._across_the_gap()
            deepest = max(-_dot(theirs.n2, point) for point in finger) + self.g
            if deepest > theirs.depth - theirs.t + SIZE_TOLERANCE:
                raise self._misfit()

    # The overlap of both bands.

    @cached_property
    def _overlap(self):
        """The 4 vertices of the overlap of both bands: n_A . q and n_B . q each 0 or -s."""
        a, b = self.sides
        cos, s = _dot(a.n2, b.n2), self.depth
        found = []
        for on_a in (0.0, -s):
            for on_b in (0.0, -s):
                k_a, k_b = (on_a - cos * on_b) / (1 - cos * cos), (on_b - cos * on_a) / (1 - cos * cos)
                found.append((k_a * a.n2[0] + k_b * b.n2[0], k_a * a.n2[1] + k_b * b.n2[1]))
        return found

    def _end(self, index):
        """Where the band of tube ``index`` ends when it covers the overlap: x of its farthest vertex."""
        return max(_dot(self.sides[index].d2, point) for point in self._overlap)

    def _start(self, index):
        """Where the band of tube ``index`` starts when the other covers the overlap: g past its farthest vertex,
        along the tube away from the corner."""
        return max(-_dot(self.sides[index].d2, point) for point in self._overlap) + self.g

    @cached_property
    def _far(self):
        sizes = [side.depth for side in self.sides] + [self.span, self.depth, self.gap, self.g]
        return 10 * (sum(sizes) + MARGIN)

    def _square(self):
        far = self._far
        return [(-far, -far), (far, -far), (far, far), (-far, far)]

    def _finger_polygon(self, owner, low=-MARGIN):
        """The finger of tube ``owner`` in the corner plane: its band (from ``low`` on y) past its miter plane up to
        half the clearance before its end."""
        side, polygon = self.sides[owner], self._square()
        polygon = _clip(polygon, side.n2, -low)
        polygon = _clip(polygon, (-side.n2[0], -side.n2[1]), self.depth)
        polygon = _clip(polygon, side.d2, self._end(owner) - self.g / 2)
        return _clip(polygon, side.m2, side.c)

    def _band_polygon(self, other):
        """What tube ``other`` loses where the other tube covers the overlap: its band from its start on toward the
        corner, up to a margin past its miter plane."""
        side, polygon = self.sides[other], self._square()
        polygon = _clip(polygon, side.n2, MARGIN)
        polygon = _clip(polygon, (-side.n2[0], -side.n2[1]), self.depth)
        polygon = _clip(polygon, (-side.d2[0], -side.d2[1]), self._start(other))
        return _clip(polygon, (-side.m2[0], -side.m2[1]), MARGIN - side.c)

    def _trim_polygon(self, owner):
        """What the other tube loses below its band where the finger of tube ``owner`` goes: the finger grown by the
        clearance (g past its faces, g/2 past its tip), up to the other tube's start and a margin back past the owner's
        miter plane (the other tube has nothing there)."""
        side, other = self.sides[owner], 1 - owner
        theirs, polygon = self.sides[other], self._square()
        polygon = _clip(polygon, side.n2, self.g)
        polygon = _clip(polygon, (-side.n2[0], -side.n2[1]), self.depth + self.g)
        polygon = _clip(polygon, side.d2, self._end(owner) + self.g / 2)
        polygon = _clip(polygon, (-theirs.d2[0], -theirs.d2[1]), self._start(other))
        return _clip(polygon, side.m2, side.c + MARGIN)

    # Shapes.

    def _prism(self, polygon, low, high):
        """The 2D ``polygon`` of the corner plane swept along W from ``low`` to ``high``."""
        points = [self.V + self.U1 * x + self.U2 * y + self.W * low for x, y in polygon]
        return Part.Face(Part.makePolygon(points + points[:1])).extrude(self.W * (high - low))

    def _tube(self, side):
        """The tube of ``side`` prolonged both ways along its axis: its section swept far past the corner."""
        section = side.tube.section.copy()
        at = (section.CenterOfMass - self.V).dot(side.d)
        section.translate(side.d * (-self._far - at))
        return section.extrude(side.d * (2 * self._far))

    def levels(self):
        """[(w0, w1, owner)] of every finger level along W from V (``FingerSettings.bounds``), owner 0 for A."""
        bounds = self.settings.bounds(self.span)
        flip = bool(self.settings.flip)
        return [(low, high, int((index % 2 == 1) != flip)) for index, (low, high) in enumerate(zip(bounds, bounds[1:]))]

    def _tips(self, owner, index, levels):
        """The solids that lead the fingers of tube ``owner`` in, at level ``index`` (joint-tabs.md S4): at each tip
        corner next to another finger, the chamfer triangle of legs ``tip_size`` or the square less its quarter disc,
        in the (x, W) plane of the owner, swept along its inner wall normal through the band; they reach past the tip,
        never along W into the next level."""
        settings, k = self.settings, float(self.settings.tip_size)
        if settings.tip == SQUARE or k <= SIZE_TOLERANCE:
            return []
        side, g = self.sides[owner], self.g
        w0, w1, _ = levels[index]
        corners = [(w0 + g / 2, -1)] if index > 0 else []
        if index < len(levels) - 1:
            corners.append((w1 - g / 2, 1))
        along = _unit(side.d - self.W * side.d.dot(self.W))
        inward, m, round_side = -side.n, MARGIN, (1 - math.sqrt(0.5)) * k
        tip = self._end(owner) - g / 2
        solids = []
        for corner_w, across in corners:
            origin = self.V + along * tip + self.W * corner_w - inward * MARGIN
            y_axis = self.W * across
            at = [origin + along * x + y_axis * y for x, y in ((-k, 0), (m, 0), (m, -k), (0, -k), (-round_side,) * 2)]
            if settings.tip == CHAMFER:
                edges = Part.makePolygon(at[:4] + at[:1]).Edges
            else:
                edges = Part.makePolygon(at[3:0:-1] + at[:1]).Edges + [Part.Arc(at[0], at[4], at[3]).toShape()]
            solids.append(Part.Face(Part.Wire(edges)).extrude(inward * (self.depth + 2 * MARGIN)))
        return solids

    def shapes(self):
        """The ``MiterFingerShapes``: per level, the owner's finger (its prolonged tube in the finger prism, less the
        tips) and the other tube's cuts (its band and the finger's trim), next levels overlapping by g along W."""
        levels, g, reach = self.levels(), self.g, self._far
        fingers, cuts = ([], []), ([], [])
        polygons = [self._finger_polygon(owner) for owner in (0, 1)]
        bands = [self._band_polygon(other) for other in (0, 1)]
        trims = [self._trim_polygon(owner) for owner in (0, 1)]
        tubes = [self._tube(side) for side in self.sides]
        for index, (low, high, owner) in enumerate(levels):
            other = 1 - owner
            first, last = index == 0, index == len(levels) - 1
            finger_low, finger_high = -reach if first else low + g / 2, reach if last else high - g / 2
            cut_low, cut_high = -reach if first else low - g / 2, reach if last else high + g / 2
            finger = self._prism(polygons[owner], finger_low, finger_high).common(tubes[owner])
            tips = self._tips(owner, index, levels)
            if tips:
                finger = finger.cut(tips)
            fingers[owner].extend(finger.Solids)
            cuts[other].append(self._prism(bands[other], cut_low, cut_high))
            trim = trims[owner]
            if len(trim) >= 3 and _area(trim) > AREA_TOLERANCE:
                cuts[other].append(self._prism(trim, cut_low, cut_high))
        tips = []
        for index, side in enumerate(self.sides):
            along = _unit(side.d - self.W * side.d.dot(self.W))
            tips.append((self.V + along * (self._end(index) - g / 2), along))
        found = [TubeFingers(fingers[index], cuts[index], tips[index]) for index in (0, 1)]
        return MiterFingerShapes(found[0], found[1], [owner for _, _, owner in levels], self.depth)

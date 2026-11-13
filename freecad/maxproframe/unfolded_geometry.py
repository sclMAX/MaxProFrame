"""Unfolded bar of a folded chain: the chain unbent into one straight solid along X, with every cut.

Every segment of the chain (``folded_chain.build_chain``) is moved rigidly onto the X axis, one after the other,
so that the outside of the frame keeps its size (outside mold line): between two segments the outer wall of the bend
(the one that stays whole) develops its bend allowance theta * (r + K t), with r the inside radius of the corner (its
outer radius less the wall thickness of the tube) and K its K-factor, by default the one of DIN 6935
(``automatic_k_factor``). At each folded corner the other walls get
a V notch whose flanks meet when the corner folds, with an interlocking key (a half circle centered on the miter line,
at its middle or slid along it to the nearest place where it fits, standing out of one flank as the tab, its socket cut
into the other) and a curved relief next to the bent wall, always cut, whose radius is the inside radius of the corner
(so the disc it keeps is concentric with the bend axis); the clearance moves the flanks, the key and the relief arcs
apart. Each corner has its own settings (``CornerSettings``).
With the ``Stepped`` joint the V stops at the inner wall band (v from d - s to d, s the step depth): there the segment
before (A, the segment after with ``step_flip``) keeps its band up to one cross-section, so it covers the whole overlap
of both bands when folded, and the other segment (B) keeps its band from one cross-section past that overlap; B's side
walls give way where A's band folds onto them. Every cut through the inner wall is then a tube cross-section, so any
tube laser cuts it.
The cuts made on each segment (its trims, cutouts and drill holes) move with it. The bar starts at X = 0 at the
open-corner end of the first segment. A closed frame whose open corner is ``Stepped`` gets that joint at both ends of
the bar instead of the ends' own cuts there: around the virtual sharp of the outer faces the last segment covers the
overlap of the inner wall bands and the first one the overlap of the outer wall bands (v from 0 to s) as far as
nothing passes the other tube's outer face (a notch is left at the outer edge away from 90 degrees), the side walls
between keep the miter. See odd/tasks/folded-miter.md, section "T3 design", odd/tasks/folded-corners.md (S6 outer
radius, S7 thickness from the profile, S8 automatic K-factor) and odd/tasks/stepped-corners.md (S2-S5, L8, L11, L13).
"""

import math
from dataclasses import dataclass, field, fields
from functools import cached_property

import FreeCAD as App
import Part

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.folded_chain import ChainError, _corner, section_offset
from freecad.maxproframe.profile_pattern import container_placement, placed

# Default key: its diameter as a part of the depth across the bent wall (S20).
KEY_DIAMETER_RATIO = 0.25
SIZE_TOLERANCE = 1e-6
AREA_TOLERANCE = 1e-6
VOLUME_TOLERANCE = 1e-6
# How far the pieces cut at the ends of the bar reach past them, so no cut face lies on an end face (mm).
END_MARGIN = 1.0
# How close the key slides to whatever keeps it from the middle of the miter line (mm).
KEY_STEP = 1e-3
# The largest tolerance the fix of a broken bar may give its edges and faces (mm).
FIX_TOLERANCE = 1e-3
# The largest outer radius is rounded down to it, so the range in the message is accepted whole (mm).
RADIUS_STEP = 0.1
X_AXIS = App.Vector(1, 0, 0)
# DIN 6935: from this r / t on the neutral axis is at the middle of the wall (K = 0.5).
DIN_6935_RATIO = 5.0
# The joints of a folded corner: the inner wall cut at theta / 2 (a bevel), or stepped with tube cross-sections.
MITER, STEPPED = JOINTS = ("Miter", "Stepped")
# The largest step depth is rounded down to it, so the range in the message is accepted whole (mm).
STEP_DEPTH_STEP = 0.1


class UnfoldError(ValueError):
    """The chain cannot unfold with these settings; the message says why."""


@dataclass(frozen=True)
class CornerSettings:
    """How one folded corner bends.

    ``outer_radius``: the radius seen outside the bend (mm); the inside radius is it less the wall thickness of the
    tube. ``clearance`` goes half on each side of the notch flanks and of the key, and all of it on the relief arcs.
    ``key``: the interlocking key in the notch, of ``key_diameter`` (0: a quarter of the depth across the bent wall).
    ``k_factor``: where the neutral axis sits in the wall, 0 < K <= 1 (0: automatic, ``automatic_k_factor``).
    ``joint``: ``Miter`` (the inner wall cut at theta / 2) or ``Stepped`` (the inner wall band, ``step_depth`` deep,
    cut with tube cross-sections; 0: automatic, ``automatic_step_depth``); ``step_flip`` gives the band that covers
    the overlap to the segment after instead of the one before. The clearance also opens the step faces, half on
    each side. A Miter corner ignores the step settings.
    """

    outer_radius: float
    clearance: float = 0.0
    key: bool = True
    key_diameter: float = 0.0
    k_factor: float = 0.0
    joint: str = MITER
    step_depth: float = 0.0
    step_flip: bool = False


def automatic_k_factor(inside_radius, thickness):
    """The K-factor of DIN 6935 for a bend of ``inside_radius`` in a wall of ``thickness``.

    DIN 6935 gives the correction factor k = 0.65 + 0.5 log10(r / t) up to r / t = 5 and 1 from there on; the K-factor
    is half of it: K = 0.325 + 0.25 log10(r / t), 0.5 from r / t = 5 on (0.325 at r = t, 0.40 at r = 2t).
    """
    ratio = float(inside_radius) / float(thickness)
    if ratio >= DIN_6935_RATIO - SIZE_TOLERANCE:
        return 0.5
    return 0.325 + 0.25 * math.log10(ratio)


def automatic_step_depth(thickness, corner_radius):
    """The step depth of a stepped corner when none is given: the larger of the wall ``thickness`` and the outer
    ``corner_radius`` of the tube section, so the tilted flank below the band never crosses the rounded edge of the
    stepped wall."""
    return max(float(thickness), float(corner_radius))


def _corner_radius(profile):
    """The outer corner radius of the tube section of ``profile`` (its ``RadiusLarge``; 0 without one)."""
    return float(getattr(profile, "RadiusLarge", 0.0) or 0.0)


def _clip_right(points, limit):
    """The polygon ``points`` (u, v) cut to u <= ``limit``."""
    clipped = []
    for index, (u, v) in enumerate(points):
        nu, nv = points[(index + 1) % len(points)]
        if u <= limit:
            clipped.append((u, v))
        if (u < limit) != (nu < limit) and u != nu:
            ratio = (limit - u) / (nu - u)
            if 0 < ratio < 1:
                clipped.append((limit, v + ratio * (nv - v)))
    return clipped


def _area(points):
    return abs(sum(u * nv - nu * v for (u, v), (nu, nv) in zip(points, points[1:] + points[:1]))) / 2


def _mirrored(points):
    """The polygon ``points`` (u, v) mirrored about u = 0."""
    return [(-u, v) for u, v in reversed(points)]


def _overlap(angle, low, high):
    """(x, x') of the vertices of the overlap of two bands y in [``low``, ``high``] when the frame (x', y') is the frame
    (x, y) turned by ``angle`` about its origin (L8): with a, b in {low, high}, x = (cos a - b) / sin and
    x' = (a - cos b) / sin."""
    theta = math.radians(angle)
    sin, cos = math.sin(theta), math.cos(theta)
    bands = [(a, b) for a in (low, high) for b in (low, high)]
    return [(cos * a - b) / sin for a, b in bands], [(a - cos * b) / sin for a, b in bands]


def _past_miter(low, high, end, tangent):
    """The band y in [``low``, ``high``] past the miter line x = -y ``tangent`` up to x = ``end``, as (x, y) points
    (empty when the band ends before the miter line)."""
    if -low * tangent < end:
        return [(-low * tangent, low), (end, low), (end, high), (-high * tangent, high)]
    if -high * tangent < end:
        return [(end, -end / tangent), (end, high), (-high * tangent, high)]
    return []


def _check_step_depth(names, thickness, step_depth, largest):
    """The step depth of a stepped corner between ``names`` (S5): at least the wall thickness, at most ``largest``
    rounded down to 0.1 mm."""
    maximum = round(math.floor(largest / STEP_DEPTH_STEP + SIZE_TOLERANCE) * STEP_DEPTH_STEP, 6)
    if step_depth < thickness - SIZE_TOLERANCE or step_depth > maximum + SIZE_TOLERANCE:
        raise UnfoldError(
            translate(
                "MaxProFrame",
                "The step depth of the corner between {} and {} must be between {min:g} and {max:g} mm.",
            ).format(*names, min=thickness, max=maximum)
        )


def _step_misfit(names):
    """The refusal of a step that does not fit at the angle of the corner between ``names``."""
    return UnfoldError(
        translate(
            "MaxProFrame",
            "The step of the corner between {} and {} does not fit at this angle: make the step depth smaller.",
        ).format(*names)
    )


@dataclass
class UnfoldedCorner:
    """A folded corner on the unfolded bar.

    ``start`` is the X where its bend zone starts on the outer wall (the zone is ``bend_allowance`` long).
    ``frame`` places the corner coordinates (u, v, w) in the bar: origin at X = ``start`` on the outside face of the
    bent wall, at the section center across it; u along +X, v inward (across the bent wall), w along the bend axis.
    ``step_split`` is None at a Miter corner; at a Stepped one it is (v, u): from v on (the stepped band) the segment
    after owns the bar from u on, inside the gap the band leaves between both segments (below, its nominal flank
    splits them).
    """

    bend_angle: float
    inside_radius: float
    bend_allowance: float
    start: float
    frame: App.Placement
    step_split: tuple = None


@dataclass
class UnfoldedBar:
    """The straight bar; ``placements`` move each segment of the chain from where it was drawn onto the bar."""

    shape: Part.Shape
    length: float
    corners: list
    placements: list = field(default_factory=list)


def _label(obj):
    return obj.Label


def _global_shape(obj):
    return placed(obj.Shape, container_placement(obj))


def _box(shape):
    try:
        return shape.optimalBoundingBox()
    except Exception:
        return shape.BoundBox


def refine(shape):
    """``shape`` with the faces lying on one surface merged (the seams the booleans leave); its edges stay as they are.

    ``removeSplitter`` also merges the edges: where a cut touches an edge of a wall or another cut (a hole tangent to
    the edge of its wall or to the next hole) it joins edges across that point into a face that crosses itself, and on
    OCC 8 its merged edges leave the faces they bound (odd/tasks/folded-bar-tools.md, T9).
    """
    unify = Part.ShapeUpgrade.UnifySameDomain(shape, False, True, False)
    unify.build()
    return unify.shape()


def _sound(shape):
    """Whether ``shape`` is one valid closed solid with volume whose edges all have their curve: one FreeCAD draws."""
    try:
        if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
            return False
        if not all(shell.isClosed() for shell in shape.Shells) or shape.Volume <= VOLUME_TOLERANCE:
            return False
        for edge in shape.Edges:
            if not edge.Degenerated:
                edge.Curve
    except Exception:
        return False
    return True


def sound_solid(shape):
    """``shape`` when it is a sound solid (``_sound``), else a fixed copy of it when the fix makes it one and keeps its
    volume, else None: the caller says the shape is broken instead of drawing it (S4 of folded-bar-tools)."""
    if _sound(shape):
        return shape
    try:
        volume = shape.Volume
        fixed = shape.copy()
        fixed.fix(SIZE_TOLERANCE, SIZE_TOLERANCE, FIX_TOLERANCE)
    except Exception:
        return None
    if not _sound(fixed) or abs(fixed.Volume - volume) > VOLUME_TOLERANCE * max(1.0, abs(volume)):
        return None
    return fixed.Solids[0] if fixed.ShapeType != "Solid" else fixed


def _polygon(points):
    points = [App.Vector(u, v, 0) for u, v in points]
    return Part.Face(Part.makePolygon(points + points[:1]))


def _disc(center, radius):
    return Part.Face(Part.Wire(Part.makeCircle(radius, App.Vector(center[0], center[1], 0))))


def _cut_disc(center, radius, x_min):
    """The part of the disc at ``center`` with x >= ``x_min`` (the chord at ``x_min`` crosses the disc)."""
    reach = math.degrees(math.acos((x_min - center[0]) / radius))
    point = App.Vector(center[0], center[1], 0)
    arc = Part.makeCircle(radius, point, App.Vector(0, 0, 1), -reach, reach)
    ends = arc.Vertexes
    chord = Part.makeLine(ends[-1].Point, ends[0].Point)
    return Part.Face(Part.Wire([arc, chord]))


def _prism(face, reach):
    """``face`` of the (u, v) plane extruded through ``reach`` on both sides along w."""
    face = face.copy()
    face.translate(App.Vector(0, 0, -reach))
    return face.extrude(App.Vector(0, 0, 2 * reach))


@dataclass
class _Bend:
    """The sizes of one folded corner, in its (u, v) plane."""

    names: tuple
    angle: float
    radius: float
    thickness: float
    k_factor: float
    depth: float
    clearance: float
    key: bool
    diameter: float
    joint: str = MITER
    step_depth: float = 0.0
    step_flip: bool = False

    @property
    def half(self):
        return math.radians(self.angle) / 2

    @property
    def stepped(self):
        return self.joint == STEPPED

    @property
    def _flank_top(self):
        """Where the flanks of the V end inward: the inner corner (v = depth), or the bottom of the stepped band."""
        return self.depth - self.step_depth if self.stepped else self.depth

    @property
    def _key_top(self):
        """How high the key may reach: the inside of the inner wall, or the bottom of the stepped band."""
        return self.depth - self.step_depth if self.stepped else self.depth - self.thickness

    def sizes(self):
        """Everything but the names: two corners of the same sizes remove the same solid."""
        return tuple(getattr(self, item.name) for item in fields(self) if item.name != "names")

    @property
    def allowance(self):
        return math.radians(self.angle) * (self.radius + self.k_factor * self.thickness)

    @property
    def setback(self):
        """Outside setback: from the virtual sharp to where the bend starts on the outer wall."""
        return (self.radius + self.thickness) * math.tan(self.half)

    def check_radius(self):
        """The outer radius (r + t), checked as such (S6): at least twice the wall thickness (the inside radius at
        least the wall thickness); at most the largest inside radius whose inside of the bend (radius r around the
        bend axis) still passes outside the inner corner, less two wall thicknesses (S15, L40), plus the wall. The
        inner corner is on the flank at v = depth, (r + t - depth) / cos(theta / 2) from the bend axis point: that
        equals r at (depth - t) / (1 - cos(theta / 2)). It depends on the angle of the corner; the key takes no room
        from it (whether the key fits on the miter line is ``check_key``'s job)."""
        t = self.thickness
        outer = self.radius + t
        minimum = 2 * t
        # The largest inside radius ((depth - t) / (1 - cos(theta / 2)) - 2t) plus the wall.
        largest = (self.depth - t) / (1 - math.cos(self.half)) - t
        maximum = round(math.floor(largest / RADIUS_STEP + SIZE_TOLERANCE) * RADIUS_STEP, 6)
        if outer < minimum - SIZE_TOLERANCE or outer > maximum + SIZE_TOLERANCE:
            raise UnfoldError(
                translate(
                    "MaxProFrame",
                    "The outer radius of the corner between {} and {} must be between {min:g} and {max:g} mm.",
                ).format(*self.names, min=minimum, max=maximum)
            )

    def check_k_factor(self):
        """Where the neutral axis sits in the wall: above 0 (its inside face) up to 1 (its outside face)."""
        if not 0 < self.k_factor <= 1:
            raise UnfoldError(
                translate(
                    "MaxProFrame", "The K-factor of the corner between {} and {} must be between 0 and 1."
                ).format(*self.names)
            )

    def _flank_heights(self, v):
        """u of the flank of the segment before and of the one after at height ``v`` (clearance included)."""
        h, t, r, g = self.half, self.thickness, self.radius, self.clearance
        back = (g / 2) / math.cos(h)
        rise = (v - r - t) * math.tan(h)
        return -rise - back, self.allowance + rise + back

    def _apex(self):
        """Height v where both flanks (moved back half the clearance each) meet: the bottom of the V when above t."""
        h, t, r, g = self.half, self.thickness, self.radius, self.clearance
        return r + t - (self.allowance + g / math.cos(h)) / (2 * math.tan(h))

    def notch(self, top):
        """The V between both flanks, from the inside of the bent wall (v = t) up to ``top``."""
        t = self.thickness
        apex = self._apex()
        top_before, top_after = self._flank_heights(top)
        if apex > t:
            u_apex = self._flank_heights(apex)[0]
            return _polygon([(u_apex, apex), (top_after, top), (top_before, top)])
        bottom_before, bottom_after = self._flank_heights(t)
        return _polygon([(bottom_before, t), (bottom_after, t), (top_after, top), (top_before, top)])

    def relief_region(self):
        """The rectangle next to the bent wall, as high as the inside radius, and the discs it keeps, each one
        centered on the bend axis point of its segment: folded, the disc kept is concentric with the bend axis. The
        clearance moves their arcs back by all of it: folded, they face the bent wall, which has no cut face there."""
        t, ba, r = self.thickness, self.allowance, self.radius
        rectangle = _polygon([(0, t), (ba, t), (ba, t + r), (0, t + r)])
        kept = r - self.clearance
        if kept <= SIZE_TOLERANCE:
            return (rectangle,)
        return rectangle, _disc((0, t + r), kept), _disc((ba, t + r), kept)

    @cached_property
    def _relief_cut(self):
        """The face the relief removes from the side walls: its rectangle minus the discs it keeps."""
        rectangle, *discs = self.relief_region()
        return rectangle.cut(discs) if discs else rectangle

    def _flank_point(self, along):
        """(u, v) of the flank of the segment before, moved back half the clearance, ``along`` it from its bend axis
        point (0, r + t) inward (outward when negative)."""
        h, g = self.half, self.clearance
        return (
            -(g / 2) * math.cos(h) - along * math.sin(h),
            self.radius + self.thickness - (g / 2) * math.sin(h) + along * math.cos(h),
        )

    @cached_property
    def miter_line(self):
        """(start, end) of the miter line seen on the side wall of the folded bar, as distances along the flanks from
        their bend axis points inward: the edge of the flank of the segment before (moved back half the clearance),
        from where it leaves the relief (the gap around the disc the relief keeps) to the inner corner of the bar
        (v = depth)."""
        h, t = self.half, self.thickness
        base = self._flank_point(0.0)[1]
        start = (max(self._apex(), t) - base) / math.cos(h)
        end = (self._flank_top - base) / math.cos(h)
        if end > start:
            origin = App.Vector(*self._flank_point(0.0), 0)
            line = Part.makeLine(*(App.Vector(*self._flank_point(along), 0) for along in (start, end)))
            direction = App.Vector(-math.sin(h), math.cos(h), 0)
            for edge in line.common(self._relief_cut).Edges:
                start = max([start] + [(vertex.Point - origin).dot(direction) for vertex in edge.Vertexes])
        return start, end

    def _key_shape(self, after, radius, x_min, along):
        """The key on the flank of the segment before (tab) or after (socket): the disc of ``radius`` centered on
        the miter line ``along`` it from the bend axis point inward, kept where x >= ``x_min``; x goes across the
        flank, into the V for the segment before and into the material for the segment after."""
        h, t, r = self.half, self.thickness, self.radius
        shape = _cut_disc((0.0, along), radius, x_min)
        origin = App.Vector(self.allowance if after else 0.0, r + t, 0)
        turn = -math.degrees(h) if after else math.degrees(h)
        shape.Placement = App.Placement(origin, App.Rotation(App.Vector(0, 0, 1), turn))
        return shape

    def tab(self, along=None, diameter=None):
        """Half circle standing out of the flank of the segment before, on that flank moved back half the clearance."""
        g = self.clearance
        d = self.diameter if diameter is None else diameter
        return self._key_shape(False, d / 2 - g / 2, -g / 2, self.key_along if along is None else along)

    def socket(self, along=None, diameter=None):
        """Half circle cut into the flank of the segment after, only into that segment."""
        d = self.diameter if diameter is None else diameter
        return self._key_shape(True, d / 2 + self.clearance / 2, 0.0, self.key_along if along is None else along)

    @cached_property
    def _behind_flank(self):
        """The V up past the inner wall, and the half plane behind the flank of the segment before (moved back half
        the clearance): a tab must stay in the first one or on its flank."""
        reach = 10 * (2 * self.depth + self.allowance)
        h, g = self.half, self.clearance
        normal = App.Vector(math.cos(h), math.sin(h), 0)
        along = App.Vector(-math.sin(h), math.cos(h), 0)
        flank = App.Vector(0, self.radius + self.thickness, 0) - normal * (g / 2)
        corners = (
            flank - along * reach,
            flank + along * reach,
            flank + along * reach - normal * reach,
            flank - along * reach - normal * reach,
        )
        return self.notch(self.depth + reach), _polygon([(p.x, p.y) for p in corners])

    def _key_fits(self, along, diameter):
        """(below, above) for the key of ``diameter`` centered ``along`` the miter line: whether it clears what lies
        below it (the bottom and the other flank of the V, the relief, the bent wall) and above it (the inner wall).
        The tab stays in the V and the socket in the material of its segment."""
        tab, socket = self.tab(along, diameter), self.socket(along, diameter)
        boxes = [_box(tab), _box(socket)]
        above = all(box.YMax <= self._key_top + SIZE_TOLERANCE for box in boxes)
        if above and self.stepped:
            # The tab must not reach where the stepped band of the other segment folds (flipped step).
            above = all(tab.common(face).Area <= AREA_TOLERANCE for face in self._step_regions()[1:])
        below = all(box.YMin >= self.thickness - SIZE_TOLERANCE for box in boxes)
        if below:
            notch, behind = self._behind_flank
            below = tab.cut(notch).cut(behind).Area <= AREA_TOLERANCE
        if below:
            below = all(shape.common(self._relief_cut).Area <= AREA_TOLERANCE for shape in (tab, socket))
        return below, above

    def _fitting_along(self, diameter):
        """Where the key of ``diameter`` is centered on the miter line, from the bend axis point inward: at the middle
        of the miter line (``miter_line``), or, when it does not fit there, slid along it to the nearest place where
        it fits (L32). None when it fits nowhere on it."""
        start, end = self.miter_line
        if end - start <= SIZE_TOLERANCE:
            return None
        middle = (start + end) / 2
        below, above = self._key_fits(middle, diameter)
        if below and above:
            return middle
        if below == above:
            return None
        # Inward when something below is in the way, outward when the inner wall is.
        side, target = (0, end) if not below else (1, start)
        if not self._key_fits(target, diameter)[side]:
            return None
        blocked, clear = middle, target
        while abs(clear - blocked) > KEY_STEP:
            probe = (blocked + clear) / 2
            if self._key_fits(probe, diameter)[side]:
                clear = probe
            else:
                blocked = probe
        return clear if all(self._key_fits(clear, diameter)) else None

    @cached_property
    def key_along(self):
        """Where the key is centered on the miter line (``_fitting_along``); None when it fits nowhere."""
        return self._fitting_along(self.diameter)

    def _room_for_a_key(self):
        """Whether the smallest key (three times the clearance across, or a point without clearance) fits somewhere
        on the miter line."""
        g = self.clearance
        if g > SIZE_TOLERANCE:
            return self._fitting_along(min(self.diameter, 3 * g)) is not None
        start, end = self.miter_line
        lowest = self._flank_point(start)[1]
        return end - start > SIZE_TOLERANCE and lowest < self._key_top - SIZE_TOLERANCE

    def check_key(self):
        g, d = self.clearance, self.diameter
        refused = UnfoldError(
            translate("MaxProFrame", "The key does not fit in the notch between {} and {}: make it smaller.").format(
                *self.names
            )
        )
        # The tab must reach out of its flank, moved back half the clearance.
        if d / 2 - g / 2 <= g / 2 + SIZE_TOLERANCE:
            raise refused
        if self.key_along is not None:
            return
        # Not even the smallest key fits anywhere on the miter line: the radius leaves no room.
        if not self._room_for_a_key():
            raise UnfoldError(
                translate(
                    "MaxProFrame",
                    "The key does not fit in the notch between {} and {} with this radius: make the radius smaller or "
                    "turn the key off.",
                ).format(*self.names)
            )
        raise refused

    @cached_property
    def _step_ends(self):
        """(x_A, x'_B): where A's band ends along A and B's band along B, from their bend axis points, without
        clearance (L8). With y = v - (r + t), folded, B's (x', y') is A's (x, y) turned by theta about the bend axis;
        the bands y in [D - s, D] and y' in [D - s, D] (D = depth - r - t) overlap in a parallelogram whose vertices
        are at x = (cos a - b) / sin and x' = (a - cos b) / sin (a, b in {D - s, D}, ``_overlap``): A ends at its
        farthest x (it covers the whole overlap), B at its farthest x' (past it)."""
        top = self.depth - self.radius - self.thickness
        ends, ends_after = _overlap(self.angle, top - self.step_depth, top)
        return max(ends), max(ends_after)

    def _step_points(self):
        """(band, trim) of the stepped joint as (u, v) points, A being the segment before: the band is the rectangle
        the inner wall band loses between A's end and B's end, each moved back half the clearance; the trim (T') is A's
        band past the miter line, grown half the clearance, where it folds into B, in B's coordinates and up to B's
        end (empty when it does not reach B)."""
        h, g, t, s = self.half, self.clearance, self.thickness, self.step_depth
        ba, depth, c = self.allowance, self.depth, self.radius + self.thickness
        x_a, x_b = self._step_ends
        band = [(x_a - g / 2, depth - s), (ba + x_b + g / 2, depth - s), (ba + x_b + g / 2, depth + t)]
        band.append((x_a - g / 2, depth + t))
        # A's band past the miter line (x >= -y tan(theta / 2)), in A's (x, y).
        tab = _past_miter(depth - c - s - g / 2, depth - c + t, x_a + g / 2, math.tan(h))
        theta = math.radians(self.angle)
        sin, cos = math.sin(theta), math.cos(theta)
        trim = [(ba + x * cos + y * sin, c - x * sin + y * cos) for x, y in tab]
        trim = _clip_right(trim, ba + x_b + g / 2) if trim else []
        if len(trim) < 3 or _area(trim) <= AREA_TOLERANCE:
            trim = []
        return band, trim

    def _step_regions(self):
        """The faces the stepped band removes: the band rectangle and, when there is one, the trim of B's side walls;
        mirrored about the middle of the bend zone with ``step_flip``."""
        ba = self.allowance
        regions = [points for points in self._step_points() if points]
        if self.step_flip:
            regions = [[(ba - u, v) for u, v in reversed(points)] for points in regions]
        return [_polygon(points) for points in regions]

    def step_split(self):
        """(v, u) of ``UnfoldedCorner.step_split``: the bottom of the band and the middle of the gap the band leaves
        between the segments (mirrored with ``step_flip``); None at a Miter corner."""
        if not self.stepped:
            return None
        band = self._step_points()[0]
        middle = (band[0][0] + band[1][0]) / 2
        return self.depth - self.step_depth, self.allowance - middle if self.step_flip else middle

    def check_step(self):
        """The step depth of a stepped corner (S5): at least the wall thickness; at most where the band (from
        v = depth - s) still clears the relief (v = t + r), and under half the depth, rounded down to 0.1 mm."""
        if not self.stepped:
            return
        t = self.thickness
        largest = min(self.depth - t - self.radius, self.depth / 2 - SIZE_TOLERANCE)
        _check_step_depth(self.names, t, self.step_depth, largest)

    def check_step_fit(self):
        """Whether the stepped band fits at the angle of the corner (L8): A's band stays on its side of B's flank on
        the unfolded bar (the folded bar splits the segments there), and the trim of B's side walls stays above the
        bent wall and the bottom of the V."""
        if not self.stepped:
            return
        g, h, c = self.clearance, self.half, self.radius + self.thickness
        x_a = self._step_ends[0]
        b_flank = self.allowance + (self.depth - self.step_depth - c) * math.tan(h)
        trim = self._step_points()[1]
        lowest = min((v for _, v in trim), default=math.inf)
        if x_a - g / 2 > b_flank + SIZE_TOLERANCE or lowest < max(self.thickness, self._apex()) - SIZE_TOLERANCE:
            raise _step_misfit(self.names)

    def removed(self, reach):
        """What the corner removes, as a solid of the corner coordinates (u, v, w)."""
        cuts = [self.notch(self._flank_top if self.stepped else self.depth + self.thickness)]
        if self.key:
            cuts[0] = cuts[0].cut(self.tab())
            cuts.append(self.socket())
        if self.stepped:
            cuts.extend(self._step_regions())
        solids = [_prism(face, reach) for face in cuts]
        rectangle, *discs = self.relief_region()
        relief = _prism(rectangle, reach)
        if discs:
            relief = relief.cut([_prism(disc, reach) for disc in discs])
        solids.append(relief)
        removed = solids[0]
        for solid in solids[1:]:
            removed = removed.fuse(solid)
        return removed


@dataclass
class _OpenEnd:
    """One end of the bar at a stepped open corner: ``frame`` places the (u, v, w) of that end on the bar (origin at
    the virtual sharp, u along +X, v inward from the outer face, w along the corner axis), ``cuts`` are the (u, v)
    polygons it loses, ``kept`` is the X its material reaches, ``zone`` the box from where the joint starts to the
    end: what the tip changes there is dropped."""

    frame: App.Placement
    cuts: list
    kept: float
    zone: Part.Shape


@dataclass
class _OpenStep:
    """The stepped joint of the open corner of a closed chain, where the last segment (A) meets the first one (B)
    (S4, L11).

    It is computed folded, around the virtual sharp of the outer faces: each end has its frame (x, y), x along its tube
    (toward the corner on A, away from it on B) from the sharp, y inward from its outer face; B's frame is A's turned
    by the corner's angle about the sharp. The inner band (y from d - s to d) is the one of a folded corner (L8, A
    covers the overlap, B ends past it, B gives way where A's band past the miter line folds onto it); the outer band
    (y from 0 to s) the same with the roles swapped (B covers it, as far as nothing of it passes A's outer face plane:
    away from 90 degrees a notch is left at the outer edge, L13); the side walls between keep the miter plane
    through the sharp, each moved back half the clearance. ``step_flip`` swaps A and B: mirrored about the miter line.
    """

    names: tuple
    corner: object
    thickness: float
    clearance: float
    step_depth: float
    step_flip: bool

    @property
    def half(self):
        return math.radians(self.corner.bend_angle) / 2

    def _turned(self, points):
        """``points`` (x, y) of A's frame in B's frame; mirrored about the miter line, B's in A's."""
        theta = math.radians(self.corner.bend_angle)
        sin, cos = math.sin(theta), math.cos(theta)
        return [(x * cos + y * sin, -x * sin + y * cos) for x, y in points]

    @cached_property
    def _ends(self):
        """(A's inner end, B's inner start, A's outer end, B's outer start) along their tubes, from the sharp, each
        moved back half the clearance; the overlap (``_overlap``) of the inner bands; and B's outer start without
        clearance.

        B's outer band covers the overlap of the outer bands only as far as its cross-section stays inside A's outer
        face plane (L13): A's y = x' sin + y' cos must not be negative for y' in [0, s], so B starts at the sharp
        (x' = 0) up to 90 degrees and at -s cot(theta) past it above; at 90 degrees that covers the whole overlap,
        else a notch is left at the outer edge (a weld groove). Nothing of A past the miter line reaches past B's
        outer face plane."""
        g, s, d = self.clearance, self.step_depth, self.corner.depth
        theta = math.radians(self.corner.bend_angle)
        inner = _overlap(self.corner.bend_angle, d - s, d)
        outer = _overlap(self.corner.bend_angle, 0.0, s)
        b_start = max(0.0, -s * math.cos(theta) / math.sin(theta))
        return (
            (max(inner[0]) - g / 2, max(inner[1]) + g / 2, min(outer[0]) - g / 2, b_start + g / 2),
            inner,
            b_start,
        )

    @cached_property
    def _trims(self):
        """(trim of A, trim of B) as (x, y) points of their frames: B's outer band past the miter line, grown half the
        clearance, where it folds into A, from A's outer end on; A's inner band past the miter line, grown half the
        clearance, where it folds into B, up to B's inner start (as at a folded corner, L8)."""
        g, t, s, d = self.clearance, self.thickness, self.step_depth, self.corner.depth
        tangent = math.tan(self.half)
        (_, b_inner, a_outer, _), inner, b_start = self._ends
        a_tab = _past_miter(d - s - g / 2, d + t, max(inner[0]) + g / 2, tangent)
        b_trim = _clip_right(self._turned(a_tab), b_inner)
        # Mirrored about the miter line, B's outer band is the covering one and A's frame B's.
        b_tab = _past_miter(-t, s + g / 2, -b_start + g / 2, tangent)
        a_trim = _mirrored(_clip_right(self._turned(b_tab), -a_outer))
        return tuple(
            points if len(points) >= 3 and _area(points) > AREA_TOLERANCE else [] for points in (a_trim, b_trim)
        )

    def _cuts(self, far):
        """(cuts of the last segment, cuts of the first one): the (u, v) polygons each end loses, ``far`` being past
        everything; with ``step_flip`` each end loses the mirror of what the other one loses unflipped."""
        g, s, d = self.clearance, self.step_depth, self.corner.depth
        a_inner, b_inner, a_outer, b_outer = self._ends[0]
        tangent, back = math.tan(self.half), (g / 2) / math.cos(self.half)
        low, high = s * tangent + back, (d - s) * tangent + back
        a_cut = [(a_outer, -far), (far, -far), (far, far), (a_inner, far), (a_inner, d - s), (-high, d - s)]
        a_cut.extend([(-low, s), (a_outer, s)])
        b_cut = [(b_outer, -far), (b_outer, s), (low, s), (high, d - s), (b_inner, d - s), (b_inner, far)]
        b_cut.extend([(-far, far), (-far, -far)])
        a_cuts, b_cuts = ([cut] + ([trim] if trim else []) for cut, trim in zip((a_cut, b_cut), self._trims))
        if self.step_flip:
            return [_mirrored(points) for points in b_cuts], [_mirrored(points) for points in a_cuts]
        return a_cuts, b_cuts

    def check(self):
        """The step depth (S5): at least the wall thickness and under half the depth; the trims stay between the bands
        (A's inner band must not fold into B's outer band, nor B's outer band into A's inner one)."""
        t, s, d = self.thickness, self.step_depth, self.corner.depth
        _check_step_depth(self.names, t, s, d / 2 - SIZE_TOLERANCE)
        a_trim, b_trim = self._trims
        if min((v for _, v in b_trim), default=math.inf) < s - SIZE_TOLERANCE:
            raise _step_misfit(self.names)
        if max((v for _, v in a_trim), default=-math.inf) > d - s + SIZE_TOLERANCE:
            raise _step_misfit(self.names)

    def ends(self, chain, placements):
        """(last, first): the ``_OpenEnd`` of the last segment and of the first one on the bar placed by ``placements``
        (``_straight_placements``). Each end zone reaches back to the miter plane at the inner face (moved back half
        the clearance), so the End Miter of that end is dropped whole."""
        corner, d = self.corner, self.corner.depth
        tangent, back = math.tan(self.half), (self.clearance / 2) / math.cos(self.half)
        far = 10 * (d + max(abs(value) for value in self._ends[0]) + d * tangent)
        cuts = self._cuts(far)
        turned = App.Rotation(corner.axis, corner.bend_angle).multVec(corner.outer_normal)
        found = []
        for side, index, point, normal in ((1, -1, "end", corner.outer_normal), (-1, 0, "start", turned)):
            segment, placement = chain.segments[index], placements[index]
            offset = section_offset(segment)
            # The sharp, where the outer faces meet, is (offset . normal + d / 2) tan(theta / 2) past the path end of
            # the last segment, and as far before the path start of the first one.
            x = placement.multVec(getattr(segment, point)).x + side * (offset.dot(normal) + d / 2) * tangent
            rotation = placement.Rotation
            origin = App.Vector(x, 0, 0) + rotation.multVec(offset + normal * (d / 2))
            axes = (X_AXIS, rotation.multVec(normal * -1), rotation.multVec(corner.axis))
            polygons = cuts[0 if side > 0 else 1]
            near = [u for points in polygons for u, _ in points if abs(u) < far / 2]
            if side > 0:
                zone = min(near + [-(d * tangent + back)])
                section = _polygon([(zone - 1, 0), (far / 2, 0), (far / 2, d), (zone - 1, d)])
                kept = x + _box(section.cut([_polygon(points) for points in polygons])).XMax
                box = Part.makeBox(2 * far, 2 * far, 2 * far, App.Vector(x + zone, -far, -far))
            else:
                zone = max(near + [d * tangent + back])
                section = _polygon([(-far / 2, 0), (zone + 1, 0), (zone + 1, d), (-far / 2, d)])
                kept = x + _box(section.cut([_polygon(points) for points in polygons])).XMin
                box = Part.makeBox(2 * far, 2 * far, 2 * far, App.Vector(x + zone - 2 * far, -far, -far))
            found.append(_OpenEnd(App.Placement(origin, App.Rotation(*axes, "XYZ")), polygons, kept, box))
        return found


def _per_corner(chain, corners):
    """One CornerSettings per corner of ``chain``: ``corners`` is one for all of them or one per corner."""
    if isinstance(corners, CornerSettings):
        return [corners] * len(chain.corners)
    corners = list(corners)
    if len(corners) != len(chain.corners):
        raise ValueError(
            f"Give one CornerSettings per corner of the chain: it has {len(chain.corners)} corners, "
            f"{len(corners)} given."
        )
    return corners


def _bends(chain, corners):
    """The bends of ``chain`` with the settings ``corners`` (``unfold``), checked as ``unfold`` checks them."""
    bends = []
    for corner, chosen in zip(chain.corners, _per_corner(chain, corners)):
        # The wall thickness is the profile's (S7): the inside radius follows from the outer one (S6).
        thickness = chain.segments[corner.before].thickness
        joint = str(chosen.joint)
        if joint not in JOINTS:
            raise ValueError(f"Unknown joint {joint!r}: give Miter or Stepped.")
        stepped = joint == STEPPED
        step_depth = 0.0
        if stepped:
            # S5: 0 is automatic, from the tube of the segment before (all the tubes of a chain are alike).
            corner_radius = _corner_radius(chain.segments[corner.before].profile)
            step_depth = float(chosen.step_depth) or automatic_step_depth(thickness, corner_radius)
        bend = _Bend(
            names=(_label(chain.segments[corner.before].profile), _label(chain.segments[corner.after].profile)),
            angle=corner.bend_angle,
            radius=float(chosen.outer_radius) - thickness,
            thickness=thickness,
            k_factor=float(chosen.k_factor),
            depth=corner.depth,
            clearance=float(chosen.clearance),
            key=bool(chosen.key),
            diameter=float(chosen.key_diameter) or corner.depth * KEY_DIAMETER_RATIO,
            joint=joint,
            step_depth=step_depth,
            step_flip=stepped and bool(chosen.step_flip),
        )
        bend.check_radius()
        if bend.k_factor == 0:
            # S8: automatic, once the inside radius is known to be at least the wall thickness.
            bend.k_factor = automatic_k_factor(bend.radius, thickness)
        bend.check_k_factor()
        bend.check_step()
        bend.check_step_fit()
        bends.append(bend)
    # A tube too short for its bends makes no key fit either: say so first.
    _check_lengths(chain, bends)
    for bend in bends:
        if bend.key:
            bend.check_key()
    return bends


def _open_step(chain, open_corner):
    """The stepped joint of the open corner of ``chain`` with the settings ``open_corner`` (``unfold``), checked; None
    when the chain is open, or ``open_corner`` is None or a Miter."""
    if open_corner is None or not chain.closed:
        return None
    joint = str(open_corner.joint)
    if joint not in JOINTS:
        raise ValueError(f"Unknown joint {joint!r}: give Miter or Stepped.")
    if joint != STEPPED:
        return None
    first, last = chain.segments[0], chain.segments[-1]
    try:
        # The last segment meets the first one as at a folded corner (its angle, axis, outer wall and depth).
        corner = _corner(len(chain.segments) - 1, last, first)
    except ChainError as error:
        raise UnfoldError(str(error)) from error
    thickness = last.thickness
    step = _OpenStep(
        # Named as the open corner object names it: the first piece, then the last one.
        names=(_label(first.profile), _label(last.profile)),
        corner=corner,
        thickness=thickness,
        clearance=float(open_corner.clearance),
        step_depth=float(open_corner.step_depth) or automatic_step_depth(thickness, _corner_radius(last.profile)),
        step_flip=bool(open_corner.step_flip),
    )
    step.check()
    return step


def check_settings(chain, corners, open_corner=None):
    """Raise what ``unfold`` would raise for ``corners`` and ``open_corner`` (as ``unfold`` takes them), without
    building any shape."""
    _bends(chain, corners)
    _open_step(chain, open_corner)


def _check_lengths(chain, bends):
    """Each tube holds the bends at its ends (S23): on the outer wall of the unbent bar, the bend zone of the corner
    before it ends no later than that of the corner after it starts; an open end is the end of its path. That is, the
    setbacks of its folded corners ((r + t) tan(theta / 2) each) are at most its length from one virtual sharp (or
    open end) to the other, with some straight wall left: with none, the side walls rest on the outer wall only at a
    point and the tube comes apart."""
    placements, corners = _straight_placements(chain, bends)
    for index, (segment, placement) in enumerate(zip(chain.segments, placements)):
        path_start = placement.multVec(segment.start).x
        start = corners[index - 1][0] + bends[index - 1].allowance if index else path_start
        end = corners[index][0] if index < len(corners) else path_start + segment.length
        if end <= start + SIZE_TOLERANCE:
            raise UnfoldError(
                translate("MaxProFrame", "{} is too short for the radius of its corners.").format(
                    _label(segment.profile)
                )
            )


def _straight_placements(chain, bends):
    """Placement of each segment on the X axis, and (start X, frame) of each corner, before the bar is moved to 0."""
    first = chain.segments[0]
    rotation = App.Rotation(first.direction, first.x_axis, first.y_axis, "XYZ").inverted()
    position = 0.0
    placements, corners = [], []
    for index, segment in enumerate(chain.segments):
        placements.append(App.Placement(App.Vector(position, 0, 0) - rotation.multVec(segment.start), rotation))
        if index == len(chain.corners):
            break
        corner, bend = chain.corners[index], bends[index]
        offset = section_offset(segment)
        reach = offset.dot(corner.outer_normal) + corner.depth / 2
        tangent = math.tan(bend.half)
        start = position + segment.length + reach * tangent - bend.setback
        origin = App.Vector(start, 0, 0) + rotation.multVec(offset + corner.outer_normal * (corner.depth / 2))
        axes = (X_AXIS, rotation.multVec(corner.outer_normal * -1), rotation.multVec(corner.axis))
        corners.append((start, App.Placement(origin, App.Rotation(*axes, "XYZ"))))
        position += segment.length + 2 * reach * tangent - 2 * bend.setback + bend.allowance
        following = chain.segments[index + 1]
        rotation = rotation.multiply(App.Rotation(segment.direction, following.direction).inverted())
    return placements, corners


def _section(chain, placement):
    """Section of the first segment's base profile, normal to the path at its middle, on the X axis."""
    segment = chain.segments[0]
    base = placed(_global_shape(segment.profile), placement)
    middle = placement.Base.x + placement.Rotation.multVec(segment.start).x + segment.length / 2
    wires = base.slice(X_AXIS, middle)
    face = Part.makeFace(wires, "Part::FaceMakerBullseye")
    face.translate(App.Vector(-middle, 0, 0))
    return face


def _slab(section, start, end):
    face = section.copy()
    face.translate(App.Vector(start, 0, 0))
    return face.extrude(App.Vector(end - start, 0, 0))


def _segment_changes(chain, placements, section, x_min, x_max, zones=()):
    """(removed, added) solids of the cuts made on the segments, on the bar.

    Each segment's tip is compared with its base profile; at the ends of the bar the base profile is taken as
    reaching the bar ends, so whatever of the bar the tip does not fill there is removed too. Nothing is changed
    inside ``zones`` (solids): the ends a stepped open corner rebuilds.
    """
    removed, added = [], []
    last = len(chain.segments) - 1
    for index, (segment, placement) in enumerate(zip(chain.segments, placements)):
        base = placed(_global_shape(segment.profile), placement)
        reference = base
        box = _box(base)
        if index == 0 and x_min < box.XMin - SIZE_TOLERANCE:
            reference = reference.fuse(_slab(section, x_min - END_MARGIN, box.XMin))
        if index == last and x_max > box.XMax + SIZE_TOLERANCE:
            reference = reference.fuse(_slab(section, box.XMax, x_max + END_MARGIN))
        if segment.tip is segment.profile and reference is base:
            continue
        tip = placed(_global_shape(segment.tip), placement)
        for found, into in ((reference.cut(tip), removed), (tip.cut(reference), added)):
            if zones and found.Solids:
                found = found.cut(list(zones))
            if found.Solids and found.Volume > VOLUME_TOLERANCE:
                into.append(found)
    return removed, added


def unfold(chain, corners, open_corner=None):
    """The unfolded bar of ``chain`` (``folded_chain.build_chain``) bent with ``corners``.

    ``corners`` is one ``CornerSettings`` for every corner, or a sequence of one per corner of the chain in chain
    order (ValueError otherwise). The wall thickness is the one of the tubes. At each corner the clearance goes half on
    each side of the notch flanks and of the key, and all of it on the relief arcs (they face the bent wall). The key
    (a half circle centered on the miter line, at its middle or where it fits nearest to it, a quarter of the depth
    across the bent wall by default) can be turned off. The relief is always cut, its radius the inside radius of
    each corner: the disc it keeps is then concentric with the bend axis (any other radius leaves a void or a
    collision at the folded corner). The K-factor is the one of DIN 6935 unless given (``automatic_k_factor``).
    A ``Stepped`` corner stops the V at its inner wall band and cuts the band with tube cross-sections (L8): the
    segment before (the one after with ``step_flip``) keeps its band over the whole overlap of both bands folded, the
    other one keeps its band from past that overlap and loses its side walls where the first band folds onto them;
    the key stays below the band. The step depth is the larger of the wall thickness and the outer corner radius of
    the tube unless given (``automatic_step_depth``).
    ``open_corner`` is the ``CornerSettings`` of the open corner of a closed chain (ignored on an open one): with None
    or ``Miter`` the ends of the bar are the segments' own tips there (their End Miter, if any); with ``Stepped``
    both ends get the stepped joint (S4, L11) and lose whatever their tips change from where it starts on (the End
    Miter): the last segment covers the overlap of the inner bands and the first one the overlap of the outer bands
    as far as nothing passes the last one's outer face, leaving a notch at the outer edge away from 90 degrees (L13)
    (swapped with ``step_flip``), the side walls between keep the miter through the virtual sharp of the outer faces,
    the clearance moves each end back half of it; only its joint, clearance and step settings are read.
    Raises UnfoldError when the radius, the K-factor, the step or the key of a corner do not suit the tube, or when a
    tube is too short for the bends at its ends.
    """
    bends = _bends(chain, corners)
    step = _open_step(chain, open_corner)
    placements, corners = _straight_placements(chain, bends)
    section = _section(chain, placements[0])
    if step is None:
        x_min = _box(placed(_global_shape(chain.segments[0].tip), placements[0])).XMin
        x_max = _box(placed(_global_shape(chain.segments[-1].tip), placements[-1])).XMax

        bar = _slab(section, x_min, x_max)
        removed, added = _segment_changes(chain, placements, section, x_min, x_max)
    else:
        ends = step.ends(chain, placements)
        x_min, x_max = ends[1].kept, ends[0].kept
        start, end = x_min - END_MARGIN, x_max + END_MARGIN
        bar = _slab(section, start, end)
        removed, added = _segment_changes(chain, placements, section, start, end, [found.zone for found in ends])
    for solid in removed:
        bar = bar.cut(solid)
    for solid in added:
        bar = bar.fuse(solid)
    reach = chain.segments[0].width + chain.segments[0].height
    # The solid a corner removes is built once for all the corners of the same sizes.
    removed_by_sizes = {}
    for bend, (_, frame) in zip(bends, corners):
        sizes = bend.sizes()
        if sizes not in removed_by_sizes:
            removed_by_sizes[sizes] = bend.removed(reach)
        bar = bar.cut(placed(removed_by_sizes[sizes], frame))
    if step is not None:
        bar = bar.cut([placed(_prism(_polygon(points), reach), found.frame) for found in ends for points in found.cuts])
    bar = refine(bar)
    if len(bar.Solids) == 1:
        bar = bar.Solids[0]
    shift = App.Vector(-x_min, 0, 0)
    bar.translate(shift)

    unfolded = [
        UnfoldedCorner(
            bend_angle=bend.angle,
            inside_radius=bend.radius,
            bend_allowance=bend.allowance,
            start=start - x_min,
            frame=App.Placement(frame.Base + shift, frame.Rotation),
            step_split=bend.step_split(),
        )
        for bend, (start, frame) in zip(bends, corners)
    ]
    moved = [App.Placement(placement.Base + shift, placement.Rotation) for placement in placements]
    return UnfoldedBar(bar, x_max - x_min, unfolded, moved)

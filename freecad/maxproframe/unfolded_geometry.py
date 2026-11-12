"""Unfolded bar of a folded chain: the chain unbent into one straight solid along X, with every cut.

Every segment of the chain (``folded_chain.build_chain``) is moved rigidly onto the X axis, one after the other,
so that the outside of the frame keeps its size (outside mold line): between two segments the outer wall of the bend
(the one that stays whole) develops its bend allowance theta * (r + K t). At each folded corner the other walls get
a V notch whose flanks meet when the corner folds, with an interlocking key (a half circle centered on the miter line,
at its middle or slid along it to the nearest place where it fits, standing out of one flank as the tab, its socket cut
into the other) and a curved relief next to the bent wall, always cut, whose radius is the inside radius of the corner
(so the disc it keeps is concentric with the bend axis); the clearance moves the flanks, the key and the relief arcs
apart.
The cuts made on each segment (its trims, cutouts and drill holes) move with it. The bar starts at X = 0 at the
open-corner end of the first segment. See odd/tasks/folded-miter.md, section "T3 design".
"""

import math
from dataclasses import dataclass, field, fields
from functools import cached_property

import FreeCAD as App
import Part

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.folded_chain import section_offset
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
# The largest inside radius is rounded down to it, so the range in the message is accepted whole (mm).
RADIUS_STEP = 0.1
X_AXIS = App.Vector(1, 0, 0)


class UnfoldError(ValueError):
    """The chain cannot unfold with these settings; the message says why."""


@dataclass
class UnfoldedCorner:
    """A folded corner on the unfolded bar.

    ``start`` is the X where its bend zone starts on the outer wall (the zone is ``bend_allowance`` long).
    ``frame`` places the corner coordinates (u, v, w) in the bar: origin at X = ``start`` on the outside face of the
    bent wall, at the section center across it; u along +X, v inward (across the bent wall), w along the bend axis.
    """

    bend_angle: float
    inside_radius: float
    bend_allowance: float
    start: float
    frame: App.Placement


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


def _check_thickness(chain, configuration):
    tube = chain.segments[0]
    if abs(float(configuration.thickness) - tube.thickness) > SIZE_TOLERANCE:
        raise UnfoldError(
            translate("MaxProFrame", "{config} is for {a:g} mm walls; {tube} has {b:g} mm walls.").format(
                config=configuration.name, a=float(configuration.thickness), tube=_label(tube.profile), b=tube.thickness
            )
        )


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

    @property
    def half(self):
        return math.radians(self.angle) / 2

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
        """At least the wall thickness; at most the largest radius whose inside of the bend (radius r around the bend
        axis) still passes outside the inner corner, less two wall thicknesses (S15, L40). The inner corner is on the
        flank at v = depth, (r + t - depth) / cos(theta / 2) from the bend axis point: that equals r at
        (depth - t) / (1 - cos(theta / 2)). It depends on the angle of the corner; the key takes no room from it
        (whether the key fits on the miter line is ``check_key``'s job)."""
        t = self.thickness
        minimum = t
        largest = (self.depth - t) / (1 - math.cos(self.half)) - 2 * t
        maximum = round(math.floor(largest / RADIUS_STEP + SIZE_TOLERANCE) * RADIUS_STEP, 6)
        if self.radius < minimum - SIZE_TOLERANCE or self.radius > maximum + SIZE_TOLERANCE:
            raise UnfoldError(
                translate("MaxProFrame", "The inside bend radius must be between {min:g} and {max:g} mm.").format(
                    min=minimum, max=maximum
                )
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
        end = (self.depth - base) / math.cos(h)
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
        above = all(box.YMax <= self.depth - self.thickness + SIZE_TOLERANCE for box in boxes)
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
        return end - start > SIZE_TOLERANCE and lowest < self.depth - self.thickness - SIZE_TOLERANCE

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
                    "The key does not fit in the notch between {} and {} with this inside radius: make the radius "
                    "smaller or turn the key off.",
                ).format(*self.names)
            )
        raise refused

    def removed(self, reach):
        """What the corner removes, as a solid of the corner coordinates (u, v, w)."""
        cuts = [self.notch(self.depth + self.thickness)]
        if self.key:
            cuts[0] = cuts[0].cut(self.tab())
            cuts.append(self.socket())
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


def _bends(chain, configuration, radius, corner_radii, clearance, key, key_diameter):
    radius = float(configuration.inside_radius) if radius is None else float(radius)
    corner_radii = corner_radii or {}
    bends = []
    for index, corner in enumerate(chain.corners):
        r = float(corner_radii.get(index, radius))
        diameter = corner.depth * KEY_DIAMETER_RATIO if key_diameter is None else float(key_diameter)
        bend = _Bend(
            names=(_label(chain.segments[corner.before].profile), _label(chain.segments[corner.after].profile)),
            angle=corner.bend_angle,
            radius=r,
            thickness=chain.segments[corner.before].thickness,
            k_factor=float(configuration.k_factor),
            depth=corner.depth,
            clearance=float(clearance),
            key=key,
            diameter=diameter,
        )
        bend.check_radius()
        bends.append(bend)
    # A tube too short for its bends makes no key fit either: say so first.
    _check_lengths(chain, bends)
    if key:
        for bend in bends:
            bend.check_key()
    return bends


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


def _segment_changes(chain, placements, section, x_min, x_max):
    """(removed, added) solids of the cuts made on the segments, on the bar.

    Each segment's tip is compared with its base profile; at the ends of the bar the base profile is taken as
    reaching the bar ends, so whatever of the bar the tip does not fill there is removed too.
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
            if found.Solids and found.Volume > VOLUME_TOLERANCE:
                into.append(found)
    return removed, added


def unfold(chain, configuration, radius=None, corner_radii=None, clearance=0.0, key=True, key_diameter=None):
    """The unfolded bar of ``chain`` (``folded_chain.build_chain``) bent with ``configuration``.

    ``radius`` is the inside bend radius of the bar (the configuration's when None); ``corner_radii`` maps a corner
    index to its own radius. ``clearance`` goes half on each side of the notch flanks and of the key, and all of it on
    the relief arcs (they face the bent wall). The key (a half circle of ``key_diameter`` centered on the miter line,
    at its middle or where it fits nearest to it, a quarter of the depth across the bent wall by default) can be
    turned off. The relief is always cut, its radius the inside radius of each corner: the disc it keeps is then
    concentric with the bend axis (any other radius leaves a void or a collision at the folded corner).
    Raises UnfoldError when the configuration, the radius or the key do not suit the tube, or when a tube is too short
    for the bends at its ends.
    """
    _check_thickness(chain, configuration)
    bends = _bends(chain, configuration, radius, corner_radii, clearance, key, key_diameter)
    placements, corners = _straight_placements(chain, bends)
    section = _section(chain, placements[0])
    x_min = _box(placed(_global_shape(chain.segments[0].tip), placements[0])).XMin
    x_max = _box(placed(_global_shape(chain.segments[-1].tip), placements[-1])).XMax

    bar = _slab(section, x_min, x_max)
    removed, added = _segment_changes(chain, placements, section, x_min, x_max)
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
    bar = bar.removeSplitter()
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
        )
        for bend, (start, frame) in zip(bends, corners)
    ]
    moved = [App.Placement(placement.Base + shift, placement.Rotation) for placement in placements]
    return UnfoldedBar(bar, x_max - x_min, unfolded, moved)

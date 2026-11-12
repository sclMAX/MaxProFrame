"""Unfolded bar of a folded chain: the chain unbent into one straight solid along X, with every cut.

Every segment of the chain (``folded_chain.build_chain``) is moved rigidly onto the X axis, one after the other,
so that the outside of the frame keeps its size (outside mold line): between two segments the outer wall of the bend
(the one that stays whole) develops its bend allowance theta * (r + K t). At each folded corner the other walls get
a V notch whose flanks meet when the corner folds, with an interlocking key (a round bulb tab on one flank, its
socket on the other) and a curved relief next to the bent wall; the clearance moves the flanks and the key apart.
The cuts made on each segment (its trims, cutouts and drill holes) move with it. The bar starts at X = 0 at the
open-corner end of the first segment. See odd/tasks/folded-miter.md, section "T3 design".
"""

import math
from dataclasses import dataclass, field

import FreeCAD as App
import Part

from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.folded_chain import section_offset
from freecad.maxproframe.profile_pattern import container_placement, placed

# Default key: bulb diameter as a part of the depth across the bent wall, neck width as a part of the bulb (S20).
KEY_DIAMETER_RATIO = 0.25
NECK_RATIO = 0.6
SIZE_TOLERANCE = 1e-6
AREA_TOLERANCE = 1e-6
VOLUME_TOLERANCE = 1e-6
# How far the pieces cut at the ends of the bar reach past them, so no cut face lies on an end face (mm).
END_MARGIN = 1.0
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
    relief: bool
    diameter: float
    neck: float
    relief_radius: float

    @property
    def half(self):
        return math.radians(self.angle) / 2

    @property
    def allowance(self):
        return math.radians(self.angle) * (self.radius + self.k_factor * self.thickness)

    @property
    def setback(self):
        """Outside setback: from the virtual sharp to where the bend starts on the outer wall."""
        return (self.radius + self.thickness) * math.tan(self.half)

    def check_radius(self):
        minimum = self.thickness
        maximum = self.depth - 2 * self.thickness - (self.diameter if self.key else 0.0)
        if self.radius < minimum - SIZE_TOLERANCE or self.radius > maximum + SIZE_TOLERANCE:
            raise UnfoldError(
                translate("MaxProFrame", "The inside bend radius must be between {min:g} and {max:g} mm.").format(
                    min=minimum, max=maximum
                )
            )

    def check_relief(self):
        """Without the relief the side walls by the bent wall stay flat: past this angle they stick out of the corner."""
        widest = math.degrees(2 * math.acos(self.radius / (self.radius + self.thickness)))
        if not self.relief and self.angle > widest + 1e-9:
            raise UnfoldError(
                translate(
                    "MaxProFrame",
                    "The corner between {} and {} bends {:g} degrees: without the relief it bends up to {:g} degrees. "
                    "Turn the relief on.",
                ).format(*self.names, round(self.angle, 1), round(widest, 1))
            )

    def _flank_heights(self, v):
        """u of the flank of the segment before and of the one after at height ``v`` (clearance included)."""
        h, t, r, g = self.half, self.thickness, self.radius, self.clearance
        back = (g / 2) / math.cos(h)
        rise = (v - r - t) * math.tan(h)
        return -rise - back, self.allowance + rise + back

    def notch(self, top):
        """The V between both flanks, from the inside of the bent wall (v = t) up to ``top``."""
        h, t, r, g = self.half, self.thickness, self.radius, self.clearance
        apex = r + t - (self.allowance + g / math.cos(h)) / (2 * math.tan(h))
        top_before, top_after = self._flank_heights(top)
        if apex > t:
            u_apex = self._flank_heights(apex)[0]
            return _polygon([(u_apex, apex), (top_after, top), (top_before, top)])
        bottom_before, bottom_after = self._flank_heights(t)
        return _polygon([(bottom_before, t), (bottom_after, t), (top_after, top), (top_before, top)])

    def relief_region(self):
        t, ba, rho = self.thickness, self.allowance, self.relief_radius
        rectangle = _polygon([(0, t), (ba, t), (ba, t + rho), (0, t + rho)])
        return rectangle, _disc((0, t + rho), rho), _disc((ba, t + rho), rho)

    def _key_height(self):
        low = self.thickness + (self.relief_radius if self.relief else 0.0)
        return low, self.depth - self.thickness

    def _key_shape(self, after, grow):
        """Bulb and neck on the flank of the segment before (tab) or after (socket), grown by ``grow`` each side."""
        h, t, r, g, d = self.half, self.thickness, self.radius, self.clearance, self.diameter
        low, high = self._key_height()
        along = ((low + high) / 2 - r - t) / math.cos(h)
        neck = self.neck / 2 + grow
        bulb = _disc((d, along), d / 2 + grow)
        stem = _polygon([(-g, along - neck), (d, along - neck), (d, along + neck), (-g, along + neck)])
        shape = bulb.fuse(stem).removeSplitter()
        origin = App.Vector(self.allowance if after else 0.0, r + t, 0)
        turn = -math.degrees(h) if after else math.degrees(h)
        shape.Placement = App.Placement(origin, App.Rotation(App.Vector(0, 0, 1), turn))
        return shape

    def tab(self):
        return self._key_shape(False, -self.clearance / 2)

    def socket(self):
        return self._key_shape(True, self.clearance / 2)

    def check_key(self):
        refused = UnfoldError(
            translate("MaxProFrame", "The key does not fit in the notch between {} and {}: make it smaller.").format(
                *self.names
            )
        )
        g, d = self.clearance, self.diameter
        if d - g <= SIZE_TOLERANCE or self.neck - g <= SIZE_TOLERANCE:
            raise refused
        low, high = self._key_height()
        middle = (low + high) / 2
        if middle - d / 2 < low - SIZE_TOLERANCE or middle + d / 2 > high + SIZE_TOLERANCE:
            raise refused
        tab = self.tab()
        reach = 10 * (self.depth + d + self.allowance + tab.BoundBox.DiagonalLength)
        h = self.half
        normal = App.Vector(math.cos(h), math.sin(h), 0)
        along = App.Vector(-math.sin(h), math.cos(h), 0)
        flank = App.Vector(0, self.radius + self.thickness, 0) - normal * (g / 2)
        behind = _polygon(
            [
                (p.x, p.y)
                for p in (
                    flank - along * reach,
                    flank + along * reach,
                    flank + along * reach - normal * reach,
                    flank - along * reach - normal * reach,
                )
            ]
        )
        outside = tab.cut(self.notch(self.depth + reach)).cut(behind)
        if outside.Area > AREA_TOLERANCE:
            raise refused

    def removed(self, reach):
        """What the corner removes, as a solid of the corner coordinates (u, v, w)."""
        cuts = [self.notch(self.depth + self.thickness)]
        if self.key:
            cuts[0] = cuts[0].cut(self.tab())
            cuts.append(self.socket())
        solids = [_prism(face, reach) for face in cuts]
        if self.relief:
            rectangle, *discs = self.relief_region()
            solids.append(_prism(rectangle, reach).cut([_prism(disc, reach) for disc in discs]))
        removed = solids[0]
        for solid in solids[1:]:
            removed = removed.fuse(solid)
        return removed


def _bends(chain, configuration, radius, corner_radii, clearance, key, relief, key_diameter, neck_width, relief_radius):
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
            relief=relief,
            diameter=diameter,
            neck=diameter * NECK_RATIO if neck_width is None else float(neck_width),
            relief_radius=r if relief_radius is None else float(relief_radius),
        )
        bend.check_radius()
        bend.check_relief()
        if key:
            bend.check_key()
        bends.append(bend)
    return bends


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


def unfold(
    chain,
    configuration,
    radius=None,
    corner_radii=None,
    clearance=0.0,
    key=True,
    relief=True,
    key_diameter=None,
    neck_width=None,
    relief_radius=None,
):
    """The unfolded bar of ``chain`` (``folded_chain.build_chain``) bent with ``configuration``.

    ``radius`` is the inside bend radius of the bar (the configuration's when None); ``corner_radii`` maps a corner
    index to its own radius. ``clearance`` goes half on each side of the notch flanks and of the key. The key (bulb
    ``key_diameter`` with a ``neck_width`` neck; a quarter of the depth across the bent wall and 60 % of it by
    default) and the relief (``relief_radius``, the inside radius by default) can be turned off.
    Raises UnfoldError when the configuration, the radius or the key do not suit the tube.
    """
    _check_thickness(chain, configuration)
    bends = _bends(
        chain, configuration, radius, corner_radii, clearance, key, relief, key_diameter, neck_width, relief_radius
    )
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
    for bend, (_, frame) in zip(bends, corners):
        bar = bar.cut(placed(bend.removed(reach), frame))
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

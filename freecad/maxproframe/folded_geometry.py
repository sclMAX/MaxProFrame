"""Folded bar of a chain: the unfolded bar bent back into the frame, with the real bend radius.

The folded bar is rebuilt from the unfolded bar (``unfolded_geometry.unfold``), so both always hold the same cuts.
At each folded corner the bend strip (the outer wall in the bend zone) is replaced by its section at the start of the
bend revolved by the bend angle around the bend center, r + t inside the outer face: the outer corners are round and
the outside of the frame keeps its size. The rest of the bar is split at the notch flanks into its segments, and each
one goes back where its profile was drawn, so its cuts (miters, cutouts, holes) stay there and the key tab of a
segment fills the socket of the next one. See odd/tasks/folded-miter.md, section "T4 design".
"""

import math

import FreeCAD as App
import Part

from freecad.maxproframe.profile_pattern import placed
from freecad.maxproframe.unfolded_geometry import _polygon, _prism, refine, unfold

X_AXIS = App.Vector(1, 0, 0)
Z_AXIS = App.Vector(0, 0, 1)
# How far the section of a strip is taken on each side of the start of its bend before slicing it (mm).
SECTION_MARGIN = 1.0


def _in_frame(corner, face, reach):
    """``face`` of the (u, v) plane of ``corner``, extruded through ``reach`` along w, on the bar."""
    return placed(_prism(face, reach), corner.frame)


def _strip(corner, thickness, reach):
    """The bend strip of ``corner``: u in [0, BA] up to the inside of the bent wall (v <= t)."""
    ba = corner.bend_allowance
    return _in_frame(corner, _polygon([(0, -reach), (ba, -reach), (ba, thickness), (0, thickness)]), reach)


def _strip_section(bar, corner, thickness, reach):
    """Section of the bar at the start of the bend of ``corner`` (u = 0), through its strip (v <= t), on the bar."""
    m = SECTION_MARGIN
    near = bar.common(_in_frame(corner, _polygon([(-m, -reach), (m, -reach), (m, thickness), (-m, thickness)]), reach))
    return Part.makeFace(near.slice(X_AXIS, corner.start), "Part::FaceMakerBullseye")


def _after(corner, thickness, far, reach):
    """What the segment after ``corner`` owns of the bar near it: behind its nominal flank, from the bend start on.

    The flank half plane alone would reach back past the start of the bend (u < 0) when the bend allowance is shorter
    than the outside setback (wide angles), taking the outer wall of the segment before; u >= 0 keeps it there.
    """
    h = math.radians(corner.bend_angle) / 2
    ba, r, t = corner.bend_allowance, corner.inside_radius, thickness

    def flank(v):
        return ba + (v - r - t) * math.tan(h)

    low, high = -reach, reach
    far = max(far, flank(high)) + reach
    behind = _polygon([(flank(low), low), (far, low), (far, high), (flank(high), high)])
    started = _polygon([(0, low), (far, low), (far, high), (0, high)])
    return _in_frame(corner, behind.common(started), reach)


def fold_bar(chain, unfolded):
    """The folded solid of ``chain`` from its unfolded bar ``unfolded``, in global coordinates (where it was drawn).

    Returns one solid; a boolean that yields more than one gives the shape as it is.
    """
    first = chain.segments[0]
    thickness = first.thickness
    reach = first.width + first.height
    bar = unfolded.shape
    back = [placement.inverse() for placement in unfolded.placements]

    strips, revolved = [], []
    for index, corner in enumerate(unfolded.corners):
        strips.append(_strip(corner, thickness, reach))
        section = placed(_strip_section(bar, corner, thickness, reach), back[index])
        center = back[index].multVec(corner.frame.multVec(App.Vector(0, corner.inside_radius + thickness, 0)))
        axis = back[index].Rotation.multVec(corner.frame.Rotation.multVec(Z_AXIS))
        revolved.append(section.revolve(center, axis, corner.bend_angle))

    rest = bar.cut(strips) if strips else bar
    far = unfolded.length + reach
    owned = [_after(corner, thickness, far, reach) for corner in unfolded.corners]
    pieces = []
    for index, placement in enumerate(back):
        piece = rest
        if index > 0:
            piece = piece.common(owned[index - 1])
        if index < len(owned):
            piece = piece.cut(owned[index])
        pieces.append(placed(piece, placement))

    folded = pieces[0].fuse(pieces[1:] + revolved) if len(pieces) + len(revolved) > 1 else pieces[0]
    folded = refine(folded)
    if len(folded.Solids) == 1:
        return folded.Solids[0]
    return folded


def fold(chain, corners):
    """The folded solid of ``chain`` bent with ``corners``: one ``CornerSettings`` or one per corner (``unfold``).

    Raises UnfoldError when the chain cannot unfold with these settings.
    """
    return fold_bar(chain, unfold(chain, corners))

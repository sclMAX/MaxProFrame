"""Interlocks: locating shapes added between the two faces of a joint, one geometry class per kind.

An interlock is chosen by its ``Kind``; each kind is one frozen settings class registered in ``KINDS``, which knows its
own settings, sizes and checks, and is read by the bar code that cuts it (odd/tasks/joint-tabs.md, S2). This module
ships the kind ``Fingers`` (S3, S4): at the inner vertex of a folded corner the inner wall band is split along the
bend axis (w) into fingers that alternate which segment owns the overlap of both inner walls, each finger level being
the stepped band of odd/tasks/stepped-corners.md (S2, S3); ``unfolded_geometry`` cuts them and ``folded_geometry``
splits the segments along them. Hooks, clips, the through tab and slot of a T joint and the in-plane key of a miter
join later as new entries of ``KINDS``, without changing the object's links, the two-face picking or the bar
integration.

This module imports nothing of ``unfolded_geometry``, which imports it.
"""

import math
from dataclasses import dataclass

from freecad.maxproframe.ff_tools import translate

FINGERS = "Fingers"
# The tip of a finger, in the inner wall plane: as cut, chamfered or rounded to lead it in (S4).
SQUARE, CHAMFER, ROUND = TIPS = ("Square", "Chamfer", "Round")
SIZE_TOLERANCE = 1e-6
# The largest tip size is rounded down to it, so the range in the message is accepted whole (mm).
TIP_STEP = 0.1


class InterlockError(ValueError):
    """The interlock does not fit its joint; the message says why."""


@dataclass(frozen=True)
class FingerSettings:
    """The fingers at the inner vertex of a folded corner (odd/tasks/joint-tabs.md, S3, S4).

    ``count`` fingers (at least 2; the segment before owns the first one, the segment after with ``flip``) split the
    tube along the bend axis: ``finger_width`` 0 splits it evenly, otherwise every finger but the two outermost is
    that wide, centered, and the outermost ones share the rest. ``tip`` is ``Square``, ``Chamfer`` or ``Round``,
    ``tip_size`` the chamfer leg or the radius at the tip corners of each finger, in the inner wall plane. ``depth`` is
    the band depth s (0: the automatic step depth of a stepped corner). ``clearance`` opens every mating face pair by
    all of it, g/2 per piece, the finger sides included (stepped-corners.md T6).
    """

    count: int = 3
    finger_width: float = 0.0
    tip: str = SQUARE
    tip_size: float = 0.0
    depth: float = 0.0
    clearance: float = 0.0
    flip: bool = False

    kind = FINGERS

    def widths(self, span):
        """The width of each finger along w in a tube ``span`` wide there."""
        count = int(self.count)
        if self.finger_width <= 0 or count == 2:
            return [span / count] * count
        outer = (span - (count - 2) * self.finger_width) / 2
        return [outer] + [float(self.finger_width)] * (count - 2) + [outer]

    def bounds(self, span):
        """The ``count`` + 1 boundaries of the fingers along w, from -``span`` / 2 to ``span`` / 2."""
        found = [-span / 2]
        for width in self.widths(span)[:-1]:
            found.append(found[-1] + width)
        return found + [span / 2]

    def check(self, names, span):
        """Raise InterlockError when the fingers do not fit a tube ``span`` wide along w at the corner between
        ``names`` (S6): fewer than 2, a finger not wider than the clearance (the inner ones too wide for the span), a
        tip larger than half the narrowest finger less the clearance (rounded down to 0.1 mm)."""
        if self.tip not in TIPS:
            raise ValueError(f"Unknown tip {self.tip!r}: give Square, Chamfer or Round.")
        if int(self.count) < 2:
            raise InterlockError(
                translate(
                    "MaxProFrame", "The interlock of the corner between {} and {} needs at least 2 fingers."
                ).format(*names)
            )
        g = float(self.clearance)
        narrowest = min(self.widths(span))
        if narrowest <= g + SIZE_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame",
                    "The fingers of the corner between {} and {} do not fit: make them fewer or narrower.",
                ).format(*names)
            )
        if self.tip == SQUARE:
            return
        maximum = round(math.floor((narrowest - g) / 2 / TIP_STEP + SIZE_TOLERANCE) * TIP_STEP, 6)
        if self.tip_size < -SIZE_TOLERANCE or self.tip_size > maximum + SIZE_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame",
                    "The finger tips of the corner between {} and {} must be between 0 and {max:g} mm.",
                ).format(*names, max=maximum)
            )


# Every kind of interlock by its name: its settings class (S2).
KINDS = {FINGERS: FingerSettings}

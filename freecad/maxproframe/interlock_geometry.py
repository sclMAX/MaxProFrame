"""Interlocks: locating shapes added between the two faces of a joint, one geometry class per kind.

An interlock is chosen by its ``Kind``; each kind is one frozen settings class registered in ``KINDS``, which knows its
own settings, sizes and checks, and is read by the bar code that cuts it (odd/tasks/joint-tabs.md, S2). This module
ships the kind ``Fingers`` (S3, S4): at the inner vertex of a folded corner the inner wall band is split along the
bend axis (w) into fingers that alternate which segment owns the overlap of both inner walls, each finger level being
the stepped band of odd/tasks/stepped-corners.md (S2, S3); ``unfolded_geometry`` cuts them and ``folded_geometry``
splits the segments along them. It ships the kind ``Tabs`` too (odd/tasks/t-joint-tabs.md, S3, S4): at a T joint the
crossbar wall ends in tabs through slots in the rail wall, built by ``tab_geometry``. Hooks, clips and the in-plane key
of a miter join later as new entries of ``KINDS``, without changing the object's links, the two-face picking or the bar
integration.

This module imports nothing of ``unfolded_geometry``, which imports it.
"""

import math
from dataclasses import dataclass

from freecad.maxproframe.ff_tools import translate

FINGERS = "Fingers"
TABS = "Tabs"
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


@dataclass(frozen=True)
class TabSettings:
    """The tabs of a T joint (odd/tasks/t-joint-tabs.md, S3, S4): the crossbar wall ends in tabs through slots in the
    rail wall; ``tab_geometry`` builds them.

    The Fingers fields again (S3): ``count`` tabs (at least 1) on the flat part of the crossbar wall, across its axis;
    ``tab_width`` 0 splits that part evenly into 2 * ``count`` + 1 parts, tabs and gaps alike (Even), otherwise the
    tabs are that wide with equal gaps between them and at both ends. ``tip`` is ``Square``, ``Chamfer`` or ``Round``,
    ``tip_size`` the chamfer leg or the radius at both tip corners of each tab, in the crossbar wall plane.
    ``clearance`` grows each slot by all of it, half on each side of the tab. ``length`` is how far the tab goes
    across the rail wall, measured along the rail face normal from its outer face (D3); 0 is Automatic, the rail wall
    thickness: the tab ends flush with the inside face (S4).
    """

    count: int = 2
    tab_width: float = 0.0
    tip: str = SQUARE
    tip_size: float = 0.0
    length: float = 0.0
    clearance: float = 0.0

    kind = TABS

    def bounds(self, span):
        """[(low, high)]: where each tab lies across the crossbar wall, in a flat part ``span`` wide centered on 0."""
        count = int(self.count)
        width = float(self.tab_width) if self.tab_width > 0 else span / (2 * count + 1)
        gap = (span - count * width) / (count + 1)
        lows = [-span / 2 + gap + index * (width + gap) for index in range(count)]
        return [(low, low + width) for low in lows]

    def tab_length(self, rail_thickness):
        """How far the tabs go across the rail wall: ``length``, or the rail wall thickness when it is 0."""
        return float(self.length) if self.length > SIZE_TOLERANCE else float(rail_thickness)

    def check(self, names, span):
        """Raise InterlockError when the tabs do not suit a crossbar wall whose flat part is ``span`` wide, at the T
        joint between ``names`` (crossbar, rail): fewer than 1, a negative length, no gap left between them. The
        checks that need the joint (the tip size, the slots on the rail face) are ``tab_geometry.check``'s."""
        if self.tip not in TIPS:
            raise ValueError(f"Unknown tip {self.tip!r}: give Square, Chamfer or Round.")
        if int(self.count) < 1:
            raise InterlockError(
                translate("MaxProFrame", "The interlock of the T joint between {} and {} needs at least 1 tab.").format(
                    *names
                )
            )
        if self.length < -SIZE_TOLERANCE:
            raise InterlockError(
                translate(
                    "MaxProFrame", "The tab length of the T joint between {} and {} must be 0 (automatic) or more."
                ).format(*names)
            )
        if self.tab_width > 0 and span - int(self.count) * float(self.tab_width) <= SIZE_TOLERANCE:
            raise tabs_misfit(names)


def tabs_misfit(names):
    """The InterlockError of tabs that do not fit at the T joint between ``names``."""
    return InterlockError(
        translate(
            "MaxProFrame", "The tabs of the T joint between {} and {} do not fit: make them fewer or narrower."
        ).format(*names)
    )


# Every kind of interlock by its name: its settings class (S2).
KINDS = {FINGERS: FingerSettings, TABS: TabSettings}

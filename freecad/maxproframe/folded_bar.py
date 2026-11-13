"""Folded Bar and Unfolded Bar: the document objects of folded miters.

A Folded Bar joins a chain of tube profiles (``folded_chain.build_chain``) by folded corners: its shape is the
folded solid with the real bend radius (``folded_geometry.fold_bar``), where the frame was drawn. It keeps a copy of
its bend configuration, so the document opens the same on a computer without that configuration, and every size of
its corners (radius per bar and per corner, clearance, key; the relief follows the radius). It hides the segment
tips and is one piece for the BOM, the cut list and the IDs, as long as its developed length. The Unfolded Bar is its
straight solid from X = 0 along +X, the one exported (STEP, IGES, BREP) for a tube laser. See
odd/tasks/folded-miter.md, "T5 design".
"""

import os

import FreeCAD as App
import Part

from freecad.maxproframe import unfolded_geometry
from freecad.maxproframe.bend_config import BendConfiguration
from freecad.maxproframe.ff_tools import ICONPATH, get_param_group, place_in_container_of, translate
from freecad.maxproframe.folded_chain import ChainError, base_profile, build_chain
from freecad.maxproframe.folded_geometry import fold_bar
from freecad.maxproframe.profile_pattern import container_placement
from freecad.maxproframe.unfolded_geometry import CornerSettings, UnfoldError, unfold
from freecad.maxproframe.version import __version__ as ff_version

# Where the Create BOM panel keeps the stock length of the cut list, and its default (mm).
STOCK_LENGTH_PARAM = "Stock Length"
DEFAULT_STOCK_LENGTH = 6000.0
# make_folded_bar options -> property; the unfold argument of the same name.
OPTION_PROPERTIES = {
    "radius": "InsideRadius",
    "corner_radii": "CornerRadii",
    "clearance": "Clearance",
    "key": "Key",
    "key_diameter": "KeyDiameter",
}


def _add(obj, kind, name, group, tooltip, value=None, read_only=False):
    """Add the property ``name`` to ``obj`` with ``value`` unless it has it: a bar saved before keeps its values."""
    if name in obj.PropertiesList:
        return
    obj.addProperty(kind, name, group, tooltip)
    if value is not None:
        setattr(obj, name, value)
    if read_only:
        obj.setEditorMode(name, 1)


def bend_configuration(obj):
    """The bend configuration a Folded Bar keeps a copy of."""
    return BendConfiguration(
        obj.BendConfiguration, obj.BendMaterial, obj.WallThickness.Value, obj.InsideRadius.Value, obj.KFactor
    )


def unfold_options(obj):
    """The ``unfold`` arguments of the sizes a Folded Bar keeps; 0 is the default size of each."""

    def size(value):
        return value.Value or None

    return dict(
        radius=obj.InsideRadius.Value,
        corner_radii={index: radius for index, radius in enumerate(obj.CornerRadii) if radius > 0},
        clearance=obj.Clearance.Value,
        key=obj.Key,
        key_diameter=size(obj.KeyDiameter),
    )


def corner_settings(chain, configuration, radius=None, corner_radii=None, clearance=0.0, key=True, key_diameter=None):
    """The ``CornerSettings`` of each corner of ``chain`` from the bar-wide sizes a Folded Bar keeps today.

    The outer radius of a corner is its inside radius (its own in ``corner_radii``, else ``radius``, else the
    configuration's) plus the wall thickness of its tube; the K-factor is the configuration's. ``key_diameter`` None
    or 0 is the default key. Until the corners are objects of their own (odd/tasks/folded-corners.md, T3).
    """
    radius = float(configuration.inside_radius) if radius is None else float(radius)
    corner_radii = corner_radii or {}
    return [
        CornerSettings(
            outer_radius=float(corner_radii.get(index, radius)) + chain.segments[corner.before].thickness,
            clearance=float(clearance),
            key=bool(key),
            key_diameter=float(key_diameter or 0.0),
            k_factor=float(configuration.k_factor),
        )
        for index, corner in enumerate(chain.corners)
    ]


def check_settings(chain, configuration, radius=None, corner_radii=None, clearance=0.0, key=True, key_diameter=None):
    """Raise the UnfoldError ``unfold`` would raise for these settings, without building any shape."""
    unfolded_geometry.check_settings(
        chain,
        corner_settings(
            chain,
            configuration,
            radius=radius,
            corner_radii=corner_radii,
            clearance=clearance,
            key=key,
            key_diameter=key_diameter,
        ),
    )


def stock_length():
    """The stock length the cut list fits pieces in (mm)."""
    return get_param_group().GetFloat(STOCK_LENGTH_PARAM, DEFAULT_STOCK_LENGTH)


def warn_if_longer_than_stock(obj):
    """Warn on the console when the Folded Bar ``obj`` is longer than the stock of the cut list (S19)."""
    stock = stock_length()
    length = obj.DevelopedLength.Value
    if length > stock:
        App.Console.PrintWarning(
            translate(
                "MaxProFrame",
                "{}: its developed length ({:.1f} mm) is longer than the stock length of the cut list ({:.1f} mm).\n",
            ).format(obj.Label, length, stock)
        )


def _one_solid(shape):
    return shape is not None and not shape.isNull() and len(shape.Solids) == 1


class FoldedBar:
    def __init__(self, obj):
        self.add_properties(obj)
        obj.Proxy = self

    @staticmethod
    def add_properties(obj):
        _add(
            obj, "App::PropertyString", "MaxProFrameVersion", "Profile",
            "MaxProFrame version used to create the object", ff_version,
        )  # fmt: skip
        _add(obj, "App::PropertyString", "PID", "Profile", "Profile ID", "", read_only=True)
        _add(
            obj, "App::PropertyLinkList", "Segments", "FoldedBar",
            translate("App::Property", "Tube pieces folded into the bar, in chain order from its start"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLinkList", "OpenCorner", "FoldedBar",
            translate("App::Property", "The two pieces meeting at the open corner of a closed frame; none: default"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyString", "BendConfiguration", "Bend",
            translate("App::Property", "Name of the bend configuration copied into the bar"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyString", "BendMaterial", "Bend",
            translate("App::Property", "Material of the bend configuration"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "WallThickness", "Bend",
            translate("App::Property", "Wall thickness the bend configuration is for"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "InsideRadius", "Bend",
            translate("App::Property", "Inside bend radius of every folded corner"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyFloat", "KFactor", "Bend",
            translate("App::Property", "Where the neutral axis sits in the wall: 0 inside face, 1 outside face"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyFloatList", "CornerRadii", "Bend",
            translate("App::Property", "Inside bend radius of each folded corner in chain order; 0: InsideRadius"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "Clearance", "Notch",
            translate("App::Property", "Gap between the notch flanks and around the key, half on each side"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyBool", "Key", "Notch", translate("App::Property", "Interlocking key in each notch"), True
        )
        _add(
            obj, "App::PropertyLength", "KeyDiameter", "Notch",
            translate(
                "App::Property",
                "Diameter of the key, a half circle on the miter line; 0: a quarter of the tube depth across the "
                "bent wall",
            ),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "DevelopedLength", "Structure",
            translate("App::Property", "Length of the unfolded bar: the length to cut"), read_only=True,
        )  # fmt: skip
        for name in ("Family", "CatalogFamily", "SizeName", "Material"):
            _add(obj, "App::PropertyString", name, "Profile", "", read_only=True)
        _add(obj, "App::PropertyFloat", "ApproxWeight", "Base", "Approximate weight in Kilogram", read_only=True)
        _add(obj, "App::PropertyFloat", "Price", "Base", "Profile Price", read_only=True)

    def onDocumentRestored(self, obj):
        """A bar saved by an older MaxProFrame gets the properties it lacks, with their defaults."""
        self.add_properties(obj)

    def execute(self, obj):
        self.unfolded = None
        chain = build_chain(list(obj.Segments), open_corner=list(obj.OpenCorner) or None)
        self._follow_tips(obj, chain)
        unfolded = unfold(chain, corner_settings(chain, bend_configuration(obj), **unfold_options(obj)))
        folded = fold_bar(chain, unfolded) if _one_solid(unfolded.shape) else None
        if not _one_solid(folded):
            raise UnfoldError(
                translate("MaxProFrame", "{} does not fold into one solid: change its bend settings.").format(obj.Label)
            )
        # The recompute puts the shape at the bar's Placement: its geometry is moved into the bar's own frame.
        local = folded.copy()
        local.transformShape(container_placement(obj).multiply(obj.Placement).inverse().toMatrix(), True)
        obj.Shape = local
        obj.DevelopedLength = unfolded.length
        self._copy_profile(obj, chain.segments[0].profile, unfolded.length)
        for segment in chain.segments:
            # The bar replaces its pieces in the 3D view and in the BOM.
            if segment.tip.Visibility:
                segment.tip.Visibility = False
        self.unfolded = unfolded
        warn_if_longer_than_stock(obj)

    @staticmethod
    def _follow_tips(obj, chain):
        """Link the current tips of the segments: a trim, cutout or drill hole made on one after the bar.

        From then on the bar recomputes after it; this time a tip the recompute has not reached yet is computed
        first, so the bar folds its cut.
        """
        tips = [segment.tip for segment in chain.segments]
        if [tip.Name for tip in tips] == [segment.Name for segment in obj.Segments if segment is not None]:
            return
        obj.Segments = tips
        for tip in tips:
            if "Touched" in tip.State or tip.Shape.isNull():
                tip.recompute()

    @staticmethod
    def _copy_profile(obj, profile, length):
        """What the BOM and the cut list read on a profile, for one piece of ``length``."""
        obj.Family = profile.Family
        obj.CatalogFamily = getattr(profile, "CatalogFamily", "") or profile.Family
        obj.SizeName = profile.SizeName
        obj.Material = profile.Material
        obj.ApproxWeight = getattr(profile, "LinearWeight", 0.0) * length / 1000
        obj.Price = getattr(profile, "UnitPrice", 0.0) * length / 1000

    def unfolded_bar(self, obj):
        """The ``unfold`` result of the bar ``obj``: the one of its last recompute, else computed now."""
        unfolded = getattr(self, "unfolded", None)
        if unfolded is None or "Touched" in obj.State:
            chain = build_chain(list(obj.Segments), open_corner=list(obj.OpenCorner) or None)
            unfolded = unfold(chain, corner_settings(chain, bend_configuration(obj), **unfold_options(obj)))
        return unfolded

    def dumps(self):
        return None

    def loads(self, state):
        return None


class UnfoldedBar:
    def __init__(self, obj):
        self.add_properties(obj)
        obj.Proxy = self

    @staticmethod
    def add_properties(obj):
        _add(
            obj, "App::PropertyString", "MaxProFrameVersion", "Profile",
            "MaxProFrame version used to create the object", ff_version,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLink", "FoldedBar", "UnfoldedBar",
            translate("App::Property", "The folded bar this is the straight bar of"),
        )  # fmt: skip

    def onDocumentRestored(self, obj):
        self.add_properties(obj)

    def execute(self, obj):
        bar = obj.FoldedBar
        if bar is None:
            return
        unfolded = bar.Proxy.unfolded_bar(bar)
        if not _one_solid(unfolded.shape):
            raise UnfoldError(
                translate("MaxProFrame", "{} does not unfold into one solid: change its bend settings.").format(
                    bar.Label
                )
            )
        obj.Shape = unfolded.shape.Solids[0].copy()

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderFoldedBar:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(ICONPATH, "FoldedBar.svg")

    def claimChildren(self):
        return list(self.Object.Segments)

    def doubleClicked(self, vobj):
        """Edit the bar: unhandled, the tree starts renaming it instead."""
        import FreeCADGui as Gui

        Gui.getDocument(vobj.Object.Document.Name).setEdit(vobj.Object.Name, 0)
        return True

    def setEdit(self, vobj, mode):
        """Double-click or Edit: the Folded Bar panel on this bar."""
        if mode != 0:
            return None
        import FreeCADGui as Gui

        if Gui.Control.activeDialog():
            App.Console.PrintMessage("MaxProFrame: close the active task dialog before editing a folded bar.\n")
            return False
        from freecad.maxproframe import create_folded_bar_tool

        create_folded_bar_tool.show_panel(create_folded_bar_tool.FoldedBarTaskPanel(edited=vobj.Object))
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def onDelete(self, vobj, sub):
        """The pieces of a deleted bar show again."""
        for tip in self.Object.Segments:
            if tip is not None:
                tip.Visibility = True
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderUnfoldedBar:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(ICONPATH, "UnfoldedBar.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def make_folded_bar(selection, configuration, open_corner=None, **options):
    """A Folded Bar of the tube pieces ``selection`` (first = start of the bar) bent with ``configuration``.

    ``open_corner``: the pair of pieces meeting where a closed frame opens (``build_chain``). ``options`` are the
    sizes of ``unfold`` (radius, corner_radii as {corner index: radius}, clearance, key, key_diameter). The bar joins
    the folder or Part holding the first piece and is recomputed: a selection that does not fold leaves it in error
    with the reason.
    """
    unknown = set(options) - set(OPTION_PROPERTIES)
    if unknown:
        raise TypeError(f"Unknown folded bar options: {', '.join(sorted(unknown))}")
    selection = list(selection)
    try:
        chain = build_chain(selection, open_corner=open_corner)
        segments = [segment.tip for segment in chain.segments]
        corners = len(chain.corners)
    except ChainError:
        # Kept as selected: the recompute reports why it does not fold.
        segments, corners = selection, max(len(selection) - 1, 0)

    doc = selection[0].Document
    obj = doc.addObject("Part::FeaturePython", "FoldedBar")
    place_in_container_of(obj, selection[0])
    FoldedBar(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderFoldedBar(obj.ViewObject)
    obj.BendConfiguration = configuration.name
    obj.BendMaterial = configuration.material
    obj.WallThickness = float(configuration.thickness)
    obj.InsideRadius = float(configuration.inside_radius)
    obj.KFactor = float(configuration.k_factor)
    radii = [0.0] * corners
    for index, radius in dict(options.pop("corner_radii", None) or {}).items():
        radii[index] = float(radius)
    obj.CornerRadii = radii
    for option, value in options.items():
        if value is not None:
            setattr(obj, OPTION_PROPERTIES[option], value)
    obj.Segments = segments
    obj.OpenCorner = list(open_corner or ())
    doc.recompute()
    return obj


def make_unfolded_bar(folded_bar):
    """The Unfolded Bar of ``folded_bar``: its straight solid from X = 0 along +X, at the document origin."""
    doc = folded_bar.Document
    obj = doc.addObject("Part::FeaturePython", "UnfoldedBar")
    UnfoldedBar(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderUnfoldedBar(obj.ViewObject)
    obj.FoldedBar = folded_bar
    doc.recompute()
    return obj

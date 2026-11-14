"""Folded Bar and Unfolded Bar: the document objects of folded miters.

A Folded Bar joins a chain of tube profiles (``folded_chain.build_chain``) by folded corners: its shape is the
folded solid with the real bend radius (``folded_geometry.fold_bar``), where the frame was drawn. Each corner is a
Folded Corner object it links in ``Corners`` (``folded_corner``, odd/tasks/folded-corners.md S10): its outer radius,
clearance, key and K-factor, and the open corner of a closed frame; the bar keeps no bend setting of its own (S7), the
wall thickness is the one of its tubes. It hides the segment tips and is one piece for the BOM, the cut list and the
IDs, as long as its developed length. The Unfolded Bar is its straight solid from X = 0 along +X, the one exported
(STEP, IGES, BREP) for a tube laser. See odd/tasks/folded-miter.md, "T5 design".

The click-to-add tools work on a bar through its tubes (odd/tasks/folded-bar-tools.md, T1): ``segment_at`` names the
tube under a click on the bar and that tube's own face, a piece made later on a tube is folded into the bar before
every recompute of its document (``follow_new_pieces``), and ``release_piece`` gives a piece back to the piece under
it before a tool removes it.

The bar keeps the tube each segment is made from (``BaseTubes``, odd/tasks/pending-followups.md S4c): a segment whose
piece is removed without release (undone after a recompute outside its transaction, deleted from a script) falls back
to its tube, or to the piece left on it, instead of leaving the bar (``bar_tubes``).
"""

import os
from collections import namedtuple

import FreeCAD as App
import Part

from freecad.maxproframe._utils import is_foldedbar, piece_stack
from freecad.maxproframe.ff_tools import ICONPATH, get_param_group, place_in_container_of, translate
from freecad.maxproframe.folded_chain import ChainError, build_chain
from freecad.maxproframe.folded_corner import corner_key, corner_settings, make_folded_corner, set_corner_settings
from freecad.maxproframe.folded_geometry import fold_bar
from freecad.maxproframe.profile_pattern import (
    container_placement,
    global_element,
    global_shape,
    is_planar_face,
    newest_piece,
    placed,
)
from freecad.maxproframe.unfolded_geometry import CornerSettings, UnfoldError, sound_solid, unfold
from freecad.maxproframe.version import __version__ as ff_version

# Where the Create BOM panel keeps the stock length of the cut list, and its default (mm).
STOCK_LENGTH_PARAM = "Stock Length"
DEFAULT_STOCK_LENGTH = 6000.0
# A clicked point this close to a face of a tube lies on it (mm): the 3D view picks in single precision.
PICK_TOLERANCE = 1e-2
# Squared sine below which two face normals are parallel.
NORMAL_TOLERANCE = 1e-10


BarPick = namedtuple("BarPick", ("tip", "face", "point", "reason"))
BarPick.__doc__ = """What a click on a Folded Bar stands for (``segment_at``).

``tip``: the current tip of the tube (its newest piece, the one the bar folds), None when refused. ``face``: the name
of the face of ``tip`` under the point ("Face3"), None when there is no single one. ``point``: the clicked point in
global coordinates, None when there is none. ``reason``: None, or the translated message to show when refused.
"""


def straight_part_message():
    """What a tool needing a face or a point says about a click on a bend of a Folded Bar (S5)."""
    return translate("MaxProFrame", "Click a straight part of the folded bar.")


def pick_point(obj, sub, point=None):
    """The global point a click on ``obj`` stands for, or None.

    ``point`` is the clicked point the 3D view gives (global; the origin means none); without it, the center of the
    sub-element ``sub`` of ``obj`` (its point for a vertex).
    """
    try:
        if point is not None and App.Vector(*point).Length > 0:
            return App.Vector(*point)
        if sub:
            element = obj.Shape.getElement(sub)
            center = element.Point if hasattr(element, "Point") else element.CenterOfMass
            return container_placement(obj).multVec(center)
    except Exception:
        pass
    return None


def nearest_piece(pieces, point):
    """The piece of ``pieces`` whose shape (where it is) is nearest to the global ``point``; None without either."""
    pieces = list(pieces)
    if point is None or not pieces:
        return None
    vertex = Part.Vertex(point)

    def distance(piece):
        try:
            return vertex.distToShape(placed(piece.Shape, container_placement(piece)))[0]
        except Exception:
            return float("inf")

    return min(pieces, key=distance)


def base_tube(piece):
    """The tube ``piece`` is made from: the bottom of its trims and cutouts (``piece_stack``), ``piece`` for a tube."""
    return list(piece_stack(piece))[-1]


def _in_order(names, within):
    """Whether the names ``names`` are some of ``within``, in its order."""
    rest = iter(within)
    return all(name in rest for name in names)


def bar_tubes(bar):
    """The tubes ``bar`` folds, in its order: the base tube of each segment.

    A removed piece leaves ``Segments`` (FreeCAD drops the link) but its tube stays in ``BaseTubes``: while the tubes
    of the segments left are some of ``BaseTubes`` in its order, ``BaseTubes`` holds (S4c), so that segment folds its
    tube again. A removed tube leaves both, its segment drops out. ``Segments`` set to other tubes (another order, a
    tube not in ``BaseTubes``, a bar saved before ``BaseTubes``) gives the tubes.
    """
    current = [base_tube(segment) for segment in bar.Segments if _alive(segment)]
    stored = [tube for tube in getattr(bar, "BaseTubes", ()) if _alive(tube)]
    if _in_order([tube.Name for tube in current], [tube.Name for tube in stored]):
        return stored
    return current


def bar_tips(bar):
    """The current tip of each tube of ``bar``, in its order: the newest piece of each tube it folds (``bar_tubes``).

    As ``build_chain`` takes them.
    """
    return [newest_piece(tube) for tube in bar_tubes(bar)]


def _names(objects):
    return [obj.Name for obj in objects if obj is not None]


def set_segments(bar, pieces):
    """Have ``bar`` fold ``pieces`` (its ``Segments``) and keep the tube of each (its ``BaseTubes``).

    The way to give a bar other pieces or other tubes: ``Segments`` alone set to some of its tubes would get the
    others back (``bar_tubes``). Returns whether anything changed.
    """
    pieces = [piece for piece in pieces if _alive(piece)]
    tubes = [base_tube(piece) for piece in pieces]
    changed = False
    if "BaseTubes" in bar.PropertiesList and _names(bar.BaseTubes) != _names(tubes):
        bar.BaseTubes = tubes
        changed = True
    if _names(bar.Segments) != _names(pieces):
        bar.Segments = pieces
        changed = True
    return changed


def _clicked_normal(bar, sub):
    """(is a face, normal): the normal of the clicked face of ``bar`` when it is planar, else None."""
    element = global_element(bar, sub) if sub else None
    if not isinstance(element, Part.Face):
        return False, None
    return True, (element.Surface.Axis if is_planar_face(element) else None)


def _faces_under(tip, point, normal):
    """Names of the planar faces of ``tip`` (where it is) ``point`` lies on, parallel to ``normal`` when given."""
    try:
        shape = global_shape(tip)
    except Exception:
        return []
    vertex = Part.Vertex(point)
    if shape.isNull() or shape.distToShape(vertex)[0] > PICK_TOLERANCE:
        return []
    names = []
    for index, face in enumerate(shape.Faces, 1):
        if not is_planar_face(face):
            continue
        axis = face.Surface.Axis
        if normal is not None and axis.cross(normal).Length ** 2 > NORMAL_TOLERANCE:
            continue
        if abs((point - face.Surface.Position).dot(axis)) > PICK_TOLERANCE:
            continue
        if face.distToShape(vertex)[0] <= PICK_TOLERANCE:
            names.append(f"Face{index}")
    return names


def segment_at(bar, sub, point=None, nearest=False):
    """The tube of the Folded Bar ``bar`` a click on it stands for, as a ``BarPick``.

    ``sub`` is the clicked sub-element of the bar ("Face12"), ``point`` the clicked point (global, as the 3D view and
    ``Gui.Selection`` give it); without a point the center of ``sub`` is taken. The side walls of a bar span several
    tubes, so the point, not the face name, picks the tube.

    Default (tools that need a face or a point: Drill Hole, Cutout, an Extend Cut target): the point must lie on
    exactly one planar face of one tube tip, parallel to the clicked face of the bar; the result names that tip and
    its face. Anywhere else (a bend, where two tubes meet at a corner, a round wall) it is refused: ``tip`` and
    ``face`` are None and ``reason`` is "Click a straight part of the folded bar." (``straight_part_message``).

    ``nearest=True`` (whole-profile tools: End Miter, the profiles of an Extend Cut): never refused for a bend; the
    tip is the one under the point, else the nearest one, and ``face`` its face under the point or None.

    Typical use::

        pick = segment_at(bar, sub, point)
        if pick.reason:
            show(pick.reason)
        else:
            use(pick.tip, pick.face)
    """
    target = pick_point(bar, sub, point)
    tips = bar_tips(bar)
    on_face, normal = _clicked_normal(bar, sub)
    found = []
    if target is not None and (normal is not None or not on_face):
        found = [(tip, name) for tip in tips for name in _faces_under(tip, target, normal)]
    if len(found) == 1:
        return BarPick(found[0][0], found[0][1], target, None)
    if nearest:
        tip = nearest_piece(tips, target)
        if tip is not None:
            return BarPick(tip, None, target, None)
    return BarPick(None, None, target, straight_part_message())


def follow_new_pieces(doc):
    """Have every Folded Bar of ``doc`` fold the newest piece of each of its tubes; relinked bars recompute next.

    A trim, cutout or drill hole made on a tube of a bar later links the tube, not the bar: run before every
    recompute of the document (``NewPieceObserver``), the bar then recomputes after the new piece in that same
    recompute, folds it and hides it. A segment whose piece was removed folds its tube again, or the piece left on it
    (``bar_tubes``); one whose tube was removed is dropped.
    """
    for obj in list(doc.Objects):
        try:
            if not is_foldedbar(obj):
                continue
            set_segments(obj, bar_tips(obj))
        except Exception as error:
            App.Console.PrintWarning(f"MaxProFrame: {getattr(obj, 'Label', obj)} does not follow its pieces: {error}\n")


def release_piece(piece):
    """Give ``piece`` back to the piece under it in every Folded Bar folding it: call it before removing ``piece``.

    A tool that removes a preview piece outside an aborted transaction calls it first, so no bar links a removed
    object (removing a linked object would shrink ``Segments``): the bar folds the piece ``piece`` was made from again.
    Recompute the document after the removal: the bar then folds that piece again and hides it, also when the
    removed piece's ViewProvider ``onDelete`` (or the tool) showed it. Nothing changes for a piece no bar folds or a
    piece made from nothing.
    """
    if not _alive(piece):
        return
    stack = list(piece_stack(piece))
    if len(stack) < 2:
        return
    base = stack[1]
    for bar in list(piece.InList):
        if is_foldedbar(bar) and piece in bar.Segments:
            bar.Segments = [base if segment == piece else segment for segment in bar.Segments]


def _add(obj, kind, name, group, tooltip, value=None, read_only=False, hidden=False):
    """Add the property ``name`` to ``obj`` with ``value`` unless it has it: a bar saved before keeps its values.

    Returns whether it was added.
    """
    if name in obj.PropertiesList:
        return False
    obj.addProperty(kind, name, group, tooltip)
    if value is not None:
        setattr(obj, name, value)
    if read_only:
        obj.setEditorMode(name, 1)
    if hidden:
        obj.setEditorMode(name, 2)
    return True


def _alive(obj):
    try:
        return obj is not None and obj.Document is not None
    except Exception:
        return False


def open_corner(bar):
    """The corner object of ``bar`` marked ``Open`` (the first one), or None."""
    for obj in bar.Corners:
        if obj is not None and obj.Open and corner_key(obj) is not None:
            return obj
    return None


def bar_chain(bar):
    """The chain of ``bar``: its segments, open where its open corner object says (else where ``build_chain`` does)."""
    opened = open_corner(bar)
    return build_chain(bar_tips(bar), open_corner=[opened.PieceA, opened.PieceB] if opened else None)


def _pair(chain, corner):
    return chain.segments[corner.before].profile, chain.segments[corner.after].profile


def folded_corners(bar, chain):
    """The corner object of ``bar`` of each folded corner of ``chain``, in chain order; None where it has none.

    A corner is matched by its two profiles, in either order; the open corner object is not one of them.
    """
    opened = open_corner(bar)
    by_pair = {}
    for obj in bar.Corners:
        key = corner_key(obj)
        if key is not None and obj is not opened:
            by_pair.setdefault(key, obj)
    return [by_pair.get(frozenset(profile.Name for profile in _pair(chain, corner))) for corner in chain.corners]


def bar_settings(bar, chain):
    """The ``CornerSettings`` of each folded corner of ``chain`` from the corner objects of ``bar``.

    Raises UnfoldError naming the two pieces of a corner that has no corner object.
    """
    settings = []
    for corner, obj in zip(chain.corners, folded_corners(bar, chain)):
        if obj is None:
            raise UnfoldError(
                translate("MaxProFrame", "The corner between {} and {} has no Folded Corner object.").format(
                    *(profile.Label for profile in _pair(chain, corner))
                )
            )
        settings.append(corner_settings(obj))
    return settings


def open_settings(bar, chain):
    """The ``CornerSettings`` of the open corner object of ``bar`` when ``chain`` is closed, else None.

    ``unfold`` takes them as its ``open_corner``: with ``Stepped`` both ends of the bar get the stepped joint
    (odd/tasks/stepped-corners.md, S4); without an open corner object, or with ``Miter``, the ends are the tubes' own.
    """
    opened = open_corner(bar) if chain.closed else None
    return corner_settings(opened) if opened is not None else None


def unfold_bar(bar, chain):
    """``unfold`` of ``chain`` with the settings of the corner objects of ``bar``, its open corner's too."""
    return unfold(chain, bar_settings(bar, chain), open_corner=open_settings(bar, chain))


def _per_corner(chain, corners):
    """``corners`` as one ``CornerSettings`` per folded corner of ``chain``; ValueError for a wrong count."""
    if isinstance(corners, CornerSettings):
        return [corners] * len(chain.corners)
    corners = list(corners)
    if len(corners) != len(chain.corners):
        raise ValueError(f"{len(chain.corners)} corner settings expected, {len(corners)} given")
    return corners


def update_corners(bar, chain, corners, open_settings=None):
    """Make the corner objects of ``bar`` the corners of ``chain``, bent with ``corners``, and link them in order.

    ``corners`` is one ``CornerSettings`` for every folded corner or one per folded corner in chain order. A closed
    frame also gets its open corner (``Open``, last in ``Corners``) with ``open_settings``, by default the settings of
    the first corner (odd/tasks/stepped-corners.md, S6: the panel gives the open corner its own joint, step and
    clearance). The corner objects of ``bar`` are kept by their two profiles (they keep their names, so the
    expressions on them); missing ones are made, the ones of corners no longer in the chain are removed.
    """
    settings = _per_corner(chain, corners)
    wanted = [(_pair(chain, corner), chosen, False) for corner, chosen in zip(chain.corners, settings)]
    if chain.closed and settings:
        # The bar starts at its first segment, at the open corner: the last segment meets it there.
        opened = settings[0] if open_settings is None else open_settings
        wanted.append(((chain.segments[0].profile, chain.segments[-1].profile), opened, True))
    existing = {}
    for obj in bar.Corners:
        key = corner_key(obj)
        if key is not None:
            existing.setdefault(key, obj)
    objects = []
    for (piece_a, piece_b), chosen, is_open in wanted:
        obj = existing.pop(frozenset((piece_a.Name, piece_b.Name)), None)
        if obj is None:
            obj = make_folded_corner(bar, piece_a, piece_b, chosen, open_corner=is_open)
        else:
            set_corner_settings(obj, chosen)
            if bool(obj.Open) != is_open:
                obj.Open = is_open
        objects.append(obj)
    if [obj.Name for obj in bar.Corners if obj is not None] != [obj.Name for obj in objects]:
        bar.Corners = objects
    for obj in existing.values():
        if _alive(obj):
            bar.Document.removeObject(obj.Name)


def remove_corners(bar):
    """Remove the corner objects of ``bar`` that no other bar links."""
    doc = bar.Document
    for obj in list(bar.Corners):
        if not _alive(obj):
            continue
        others = [parent for parent in obj.InList if parent is not bar and "Corners" in parent.PropertiesList]
        if not others:
            doc.removeObject(obj.Name)


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


def _sound(bar, shape):
    """``shape`` of the Folded Bar ``bar``, fixed when it needs it (``sound_solid``); UnfoldError when it stays broken.

    A broken solid (not valid, an edge without its curve) is never drawn: the bar is in error, saying why
    (odd/tasks/folded-bar-tools.md, T9, S4).
    """
    sound = sound_solid(shape)
    if sound is None:
        raise UnfoldError(
            translate(
                "MaxProFrame",
                "{} does not fold into a valid solid: check the cuts on its tubes (a hole or cutout touching an edge "
                "or another cut).",
            ).format(bar.Label)
        )
    return sound


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
            read_only=True,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLinkList", "BaseTubes", "FoldedBar",
            translate("App::Property", "Tube each segment of the bar is made from, in its order"), hidden=True,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLinkList", "Corners", "FoldedBar",
            translate(
                "App::Property",
                "Folded Corner objects of the bar in chain order from its start, then the open corner of a closed "
                "frame",
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
        """A bar saved by an older MaxProFrame gets the properties it lacks, with their defaults.

        One saved before ``BaseTubes`` gets the tube of each of its segments (S4c): it folds the same, untouched. Its
        ``Segments`` become read-only, as a new bar's: tubes are added and removed in the Folded Bar panel.
        """
        self.add_properties(obj)
        if "ReadOnly" not in obj.getEditorMode("Segments"):
            obj.setEditorMode("Segments", 1)
        if not obj.BaseTubes:
            tubes = [base_tube(segment) for segment in obj.Segments if _alive(segment)]
            if tubes:
                touched = "Touched" in obj.State
                obj.BaseTubes = tubes
                if not touched:
                    obj.purgeTouched()

    def onBeforeChange(self, obj, prop):
        if prop == "Label":
            self._label_before = obj.Label

    def onChanged(self, obj, prop):
        """A renamed bar renames each Unfolded Bar still labelled ``<old label>_Unfolded``; others keep theirs."""
        if prop != "Label":
            return
        before = getattr(self, "_label_before", None)
        self._label_before = None
        if not before or before == obj.Label or _restoring(obj):
            return
        for user in obj.InList:
            if isinstance(getattr(user, "Proxy", None), UnfoldedBar) and user.Label == unfolded_label(before):
                user.Label = unfolded_label(obj.Label)

    def unsetupObject(self, obj):
        """The bar leaves the document (not by undo): its corner objects go with it."""
        remove_corners(obj)

    def execute(self, obj):
        self.unfolded = None
        chain = bar_chain(obj)
        self._follow_tips(obj, chain)
        unfolded = unfold_bar(obj, chain)
        folded = fold_bar(chain, unfolded) if _one_solid(unfolded.shape) else None
        if not _one_solid(folded):
            raise UnfoldError(
                translate("MaxProFrame", "{} does not fold into one solid: change its bend settings.").format(obj.Label)
            )
        folded = _sound(obj, folded)
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
        if not set_segments(obj, tips):
            return
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
            unfolded = unfold_bar(obj, bar_chain(obj))
        return unfolded

    def dumps(self):
        return None

    def loads(self, state):
        return None


class NewPieceObserver:
    """Has every Folded Bar fold the newest piece of each of its tubes at each recompute of a document (S4)."""

    def slotBeforeRecomputeDocument(self, doc):
        follow_new_pieces(doc)


if "_NEW_PIECE_OBSERVER" not in globals():
    _NEW_PIECE_OBSERVER = NewPieceObserver()
    App.addDocumentObserver(_NEW_PIECE_OBSERVER)


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
        obj.Shape = _sound(bar, unfolded.shape.Solids[0]).copy()

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
        """Under the bar in the tree: its segments, then its corners."""
        return [obj for obj in (*self.Object.Segments, *self.Object.Corners) if obj is not None]

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
        """The pieces of a deleted bar show again; its corners are removed with it (``FoldedBar.unsetupObject``)."""
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


def make_folded_bar(selection, corners, open_corner=None, open_settings=None):
    """A Folded Bar of the tube pieces ``selection`` (first = start of the bar), its corners bent with ``corners``.

    ``corners`` is one ``CornerSettings`` for every folded corner or a sequence of one per folded corner in chain
    order (ValueError otherwise, before anything is made). ``open_corner``: the pair of pieces meeting where a closed
    frame opens (``build_chain``). A Folded Corner object is made for each folded corner, and for the open corner of a
    closed frame (``Open``, with ``open_settings``, by default the settings of the first corner). The bar joins the
    folder or Part holding the first piece and is recomputed: a selection that does not fold leaves it in error with
    the reason, and without corners.
    """
    selection = list(selection)
    try:
        chain = build_chain(selection, open_corner=open_corner)
    except ChainError:
        # Kept as selected: the recompute reports why it does not fold.
        chain = None
    if chain is not None:
        corners = _per_corner(chain, corners)
        segments = [segment.tip for segment in chain.segments]
    else:
        segments = selection

    doc = selection[0].Document
    obj = doc.addObject("Part::FeaturePython", "FoldedBar")
    place_in_container_of(obj, selection[0])
    FoldedBar(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderFoldedBar(obj.ViewObject)
    set_segments(obj, segments)
    if chain is not None:
        update_corners(obj, chain, corners, open_settings=open_settings)
    doc.recompute()
    return obj


def unfolded_label(bar_label):
    """The label MaxProFrame gives the Unfolded Bar of a folded bar labelled ``bar_label``."""
    return "{}_Unfolded".format(bar_label)


def _restoring(obj):
    doc = getattr(obj, "Document", None)
    return "Restore" in getattr(obj, "State", []) or bool(getattr(doc, "Restoring", False))


def make_unfolded_bar(folded_bar):
    """The Unfolded Bar of ``folded_bar``: its straight solid from X = 0 along +X, at the document origin.

    Its label is the folded bar's label followed by ``_Unfolded`` (see ``FoldedBar.onChanged`` for renames).
    """
    doc = folded_bar.Document
    obj = doc.addObject("Part::FeaturePython", "UnfoldedBar")
    obj.Label = unfolded_label(folded_bar.Label)
    UnfoldedBar(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderUnfoldedBar(obj.ViewObject)
    obj.FoldedBar = folded_bar
    doc.recompute()
    return obj

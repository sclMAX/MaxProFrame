"""Profile Pattern: Links to a piece repeated along a straight edge, by count and pitch or between two faces.

The copies are App::Link objects to the piece: a change to it shows on every copy, and the BOM, the Cut
List and the Piece Table count each copy as one more piece with its ID. A trim, cutout or drill hole made
from the piece later shows on every copy too: they link the newest piece of its chain.
"""

import os

import FreeCAD as App
import Part

from freecad.maxproframe._utils import get_profile_from_trimmedbody, is_profile, is_profile_pattern
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, place_in_container_of, translate
from freecad.maxproframe.version import __version__ as ff_version

# Mode: copies at a pitch from the piece, or every piece, the piece too, between two faces with equal gaps.
COUNT_AND_PITCH = "Count and pitch"
BETWEEN_FACES = "Between faces"
MODES = (COUNT_AND_PITCH, BETWEEN_FACES)
# Sense of the copies of Count and pitch along the edge: its own, the opposite, or both (Count on each side).
EDGE_SENSE = "Edge sense"
INVERTED = "Inverted"
SYMMETRIC = "Symmetric"
SENSES = (EDGE_SENSE, INVERTED, SYMMETRIC)
# Labels of the modes and senses, translated where they are shown.
MODE_LABELS = {
    COUNT_AND_PITCH: QT_TRANSLATE_NOOP("frameforge", "Count and pitch"),
    BETWEEN_FACES: QT_TRANSLATE_NOOP("frameforge", "Between faces"),
}
SENSE_LABELS = {
    EDGE_SENSE: QT_TRANSLATE_NOOP("frameforge", "Edge sense"),
    INVERTED: QT_TRANSLATE_NOOP("frameforge", "Inverted"),
    SYMMETRIC: QT_TRANSLATE_NOOP("frameforge", "Symmetric (count on each side)"),
}
DEFAULT_PITCH = 100.0
MAX_COUNT = 10000
# A direction this far (cosine) from square to the piece is still across it.
ACROSS_TOLERANCE = 1e-6
# Moves and gaps (mm) smaller than this are none: what is already in place is not changed.
MOVE_TOLERANCE = 1e-7

X = App.Vector(1, 0, 0)
Y = App.Vector(0, 1, 0)
Z = App.Vector(0, 0, 1)


def container_placement(obj):
    """Placement from the coordinates of ``obj`` (its shape, its sub-elements) to global ones: its Parts'."""
    try:
        return obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    except Exception:
        return App.Placement()


def placed(shape, placement):
    """A copy of ``shape`` moved by ``placement``."""
    shape = shape.copy()
    shape.Placement = placement.multiply(shape.Placement)
    return shape


def global_element(obj, sub):
    """The sub-element ``sub`` of ``obj`` (a path through Links too) in global coordinates, or None."""
    try:
        element = obj.getSubObject(sub)
    except Exception:
        return None
    if not isinstance(element, Part.Shape) or element.isNull():
        return None
    return placed(element, container_placement(obj))


def global_shape(obj):
    """The shape of ``obj`` in global coordinates."""
    return placed(obj.Shape, container_placement(obj))


def link_sub(link):
    """(object, sub-element) of a PropertyLinkSub value, or None."""
    if not link or link[0] is None or not link[1]:
        return None
    return link[0], link[1][0]


def edge_direction(obj, sub):
    """Global unit vector of the straight edge ``sub`` of ``obj``, from its first vertex to its last."""
    edge = global_element(obj, sub)
    if not isinstance(edge, Part.Edge) or not isinstance(edge.Curve, Part.Line) or len(edge.Vertexes) != 2:
        raise ValueError(translate("frameforge", "Profile Pattern: the direction must be a straight edge."))
    return (edge.Vertexes[-1].Point - edge.Vertexes[0].Point).normalize()


def extent_along(shape, direction):
    """(lowest, highest) projections of ``shape`` on the unit vector ``direction``."""
    turned = placed(shape, App.Placement(App.Vector(), App.Rotation(direction, X)))
    box = turned.optimalBoundingBox()
    return box.XMin, box.XMax


def face_position(obj, sub, direction):
    """Where the planar face ``sub`` of ``obj`` is along ``direction``: the projection of its center."""
    face = global_element(obj, sub)
    if not isinstance(face, Part.Face) or not isinstance(face.Surface, Part.Plane):
        raise ValueError(translate("frameforge", "Profile Pattern: the limits must be planar faces."))
    return face.CenterOfMass.dot(direction)


def offset_axes(profile):
    """(axis, x, y): global unit vectors of the path of ``profile`` and of what its OffsetX and OffsetY move it along.

    The offsets drive its AttachmentOffset, applied in the frame of the path edge.
    """
    frame = container_placement(profile).multiply(profile.Placement.multiply(profile.AttachmentOffset.inverse()))
    return tuple(frame.Rotation.multVec(axis) for axis in (Z, X, Y))


def _has_expression(obj, prop):
    return any(path.lstrip(".") == prop for path, _ in getattr(obj, "ExpressionEngine", ()))


def between_faces_problem(piece, direction):
    """Why Between faces cannot move ``piece`` along ``direction``, or None when it can.

    It moves the piece by the offsets of its profile (OffsetX, OffsetY): across the profile, not along it.
    """
    profile = get_profile_from_trimmedbody(piece)
    if (
        profile is None
        or not is_profile(profile)
        or not hasattr(profile, "OffsetX")
        or getattr(profile, "MapMode", "Deactivated") == "Deactivated"
    ):
        return translate(
            "frameforge",
            "Between faces moves the piece by the offsets of its profile, and {} has no path edge to offset from. "
            "Use Count and pitch.",
        ).format(piece.Label)
    axis, along_x, along_y = offset_axes(profile)
    if abs(axis.dot(direction)) > ACROSS_TOLERANCE:
        return translate(
            "frameforge",
            "Between faces moves the piece by the offsets of its profile, across the piece: click an edge across "
            "it, not along it, or use Count and pitch.",
        )
    for prop, axis in (("OffsetX", along_x), ("OffsetY", along_y)):
        if abs(axis.dot(direction)) > ACROSS_TOLERANCE and _has_expression(profile, prop):
            return translate(
                "frameforge",
                "Between faces moves the piece by the offsets of its profile, and an expression sets {} of {}.",
            ).format(prop, profile.Label)
    return None


def count_and_pitch_steps(count, sense):
    """How many pitches from the piece each copy is, in the sense of the edge (negative: against it)."""
    forward = list(range(1, count + 1))
    if sense == INVERTED:
        return [-step for step in forward]
    if sense == SYMMETRIC:
        return forward + [-step for step in forward]
    return forward


def between_faces_moves(low, high, first, second, count):
    """(moves, gap) of ``count`` pieces, the piece first, between two faces with equal free gaps.

    ``low`` and ``high`` bound the piece along the direction, ``first`` and ``second`` are the faces there.
    The piece takes the slot next to the first face, the others follow toward the second. The moves are
    along the direction, from where the piece is; the gap is the free room between neighbors and to the faces.
    """
    sense = 1.0 if second >= first else -1.0
    width = high - low
    gap = (abs(second - first) - count * width) / (count + 1)
    if gap < -MOVE_TOLERANCE:
        raise ValueError(
            translate("frameforge", "Profile Pattern: {} pieces of {} mm do not fit between the faces ({} mm).").format(
                count, round(width, 2), round(abs(second - first), 2)
            )
        )
    # Where the side of the piece that faces the first face goes, slot by slot.
    near = low if sense > 0 else high
    return [first + sense * (gap + index * (width + gap)) - near for index in range(count)], gap


def move_piece(piece, move):
    """Move ``piece`` by the global vector ``move`` across its profile, through the offsets of that profile."""
    profile = get_profile_from_trimmedbody(piece)
    _, along_x, along_y = offset_axes(profile)
    for prop, axis in (("OffsetX", along_x), ("OffsetY", along_y)):
        step = move.dot(axis)
        if abs(step) > MOVE_TOLERANCE:
            setattr(profile, prop, getattr(profile, prop).Value + step)


def newest_piece(piece):
    """The piece built on ``piece`` last: the end of the trims, cutouts and drill holes made from it, one on another.

    Where two are made from one piece, the chain goes on through the one whose end is shown (a trim or a cutout
    hides what it is made from); ``piece`` itself when none is made from it, or when that tells none apart.
    """
    from freecad.maxproframe.drill_hole import _builds_on

    def ends(obj, seen):
        later = [child for child in obj.InList if child.Name not in seen and _builds_on(child, obj)]
        if not later:
            return [obj]
        seen = seen | {child.Name for child in later}
        return [end for child in later for end in ends(child, seen)]

    found = ends(piece, {piece.Name})
    if len(found) > 1:
        found = [end for end in found if end.Visibility]
    return found[0] if len(found) == 1 else piece


def make_profile_pattern(piece, edge, mode=COUNT_AND_PITCH, count=1, pitch=DEFAULT_PITCH, sense=EDGE_SENSE, faces=()):
    """A Profile Pattern of ``piece`` along the straight edge ``edge`` (object, sub-element).

    It joins the folder or Part/Body holding the piece before it links to anything, as its copies do.
    ``faces`` are the two (object, face) limits of Between faces.
    """
    doc = piece.Document
    obj = doc.addObject("App::FeaturePython", f"{piece.Name}_Pattern")
    obj.Label = f"{piece.Label}_Pattern"
    place_in_container_of(obj, piece)
    ProfilePattern(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderProfilePattern(obj.ViewObject)
    obj.Piece = piece
    obj.Edge = (edge[0], (edge[1],))
    obj.Mode = mode
    obj.Count = count
    obj.Pitch = pitch
    obj.Sense = sense
    obj.Faces = [(face_obj, (face,)) for face_obj, face in faces]
    return obj


class ProfilePattern:
    """Keeps one App::Link per copy of the piece, placed by the mode, and their ID the piece's."""

    def __init__(self, obj):
        obj.addProperty("App::PropertyLink", "Piece", "Pattern", "The piece the copies repeat")
        obj.addProperty(
            "App::PropertyLinkSubGlobal", "Edge", "Pattern", "Straight edge the copies follow (its sense, Inverted)"
        )
        obj.addProperty("App::PropertyEnumeration", "Mode", "Pattern", "Count and pitch, or Between faces").Mode = list(
            MODES
        )
        obj.addProperty(
            "App::PropertyIntegerConstraint",
            "Count",
            "Pattern",
            "Count and pitch: copies (on each side when Symmetric). Between faces: pieces, the original included",
        ).Count = (1, 1, MAX_COUNT, 1)
        obj.addProperty("App::PropertyLength", "Pitch", "Pattern", "Count and pitch: center to center").Pitch = (
            DEFAULT_PITCH
        )
        obj.addProperty(
            "App::PropertyEnumeration", "Sense", "Pattern", "Count and pitch: along the edge, against it, or both"
        ).Sense = list(SENSES)
        obj.addProperty(
            "App::PropertyLinkSubListGlobal", "Faces", "Pattern", "Between faces: the two planar faces, first first"
        )
        obj.addProperty("App::PropertyLength", "Gap", "Pattern", "Between faces: free room between the pieces")
        obj.addProperty("App::PropertyLength", "Spacing", "Pattern", "Between faces: center to center")
        obj.addProperty("App::PropertyLinkList", "Copies", "Pattern", "The Links the pattern keeps")
        obj.addProperty(
            "App::PropertyString",
            "MaxProFrameVersion",
            "MaxProFrame",
            "MaxProFrame version used to create the object",
        ).MaxProFrameVersion = ff_version
        for prop in ("Gap", "Spacing", "Copies", "MaxProFrameVersion"):
            obj.setEditorMode(prop, 1)
        obj.Proxy = self

    def execute(self, obj):
        piece = obj.Piece
        edge = link_sub(obj.Edge)
        if piece is None or edge is None:
            raise ValueError(translate("frameforge", "Profile Pattern: a piece and a direction edge are needed."))
        direction = edge_direction(*edge)
        # The copies show the newest piece: Between faces measures it, and moves it by the offsets of its profile.
        piece = newest_piece(piece)
        if obj.Mode == BETWEEN_FACES:
            moves = self._between_faces(obj, piece, direction)
        else:
            moves = [direction * (step * obj.Pitch.Value) for step in count_and_pitch_steps(obj.Count, obj.Sense)]
        self._place_copies(obj, piece, moves)

    def _between_faces(self, obj, piece, direction):
        """Moves of the copies from the piece; the piece itself goes to its slot."""
        problem = between_faces_problem(piece, direction)
        if problem:
            raise ValueError(problem)
        faces = [(face_obj, sub) for face_obj, subs in obj.Faces for sub in subs]
        if len(faces) != 2:
            raise ValueError(translate("frameforge", "Profile Pattern: Between faces needs two planar faces."))
        low, high = extent_along(global_shape(piece), direction)
        first, second = (face_position(face_obj, sub, direction) for face_obj, sub in faces)
        moves, gap = between_faces_moves(low, high, first, second, obj.Count)
        obj.Gap = max(gap, 0.0)
        obj.Spacing = max(gap, 0.0) + high - low
        if abs(moves[0]) > MOVE_TOLERANCE:
            # The piece moves later in this recompute: the copies are placed from where it is now.
            move_piece(piece, direction * moves[0])
        return [direction * move for move in moves[1:]]

    def _place_copies(self, obj, piece, moves):
        """One Link per move to ``piece``, moved that far (global) from it, with the ID of its profile.

        The ID of the profile: a trim or cutout made during this recompute gets it from there later in it.
        """
        doc = obj.Document
        copies = [link for link in obj.Copies if doc.getObject(link.Name) is not None]
        while len(copies) < len(moves):
            copies.append(self._new_copy(obj, piece))
        for extra in copies[len(moves) :]:
            # FreeCAD deletes it once the recompute is over: out of its Part or folder now, while the recompute
            # still reaches them, or they would be left to recompute. Through Group: removeObject would take what
            # it links out of a Part too.
            parent = extra.getParentGroup() or extra.getParentGeoFeatureGroup()
            if parent is not None:
                parent.Group = [child for child in parent.Group if child != extra]
            doc.removeObject(extra.Name)
        copies = copies[: len(moves)]
        if [link.Name for link in obj.Copies] != [link.Name for link in copies]:
            obj.Copies = copies
        # The copies share the Part of the piece: their placements are in its coordinates.
        to_local = container_placement(piece).Rotation.inverted()
        pid = getattr(get_profile_from_trimmedbody(piece) or piece, "PID", "")
        for link, move in zip(copies, moves):
            if link.LinkedObject != piece:
                link.LinkedObject = piece
            placement = App.Placement(to_local.multVec(move), App.Rotation()).multiply(piece.Placement)
            if not link.Placement.isSame(placement, MOVE_TOLERANCE):
                link.Placement = placement
            if getattr(link, "PID", pid) != pid:
                link.PID = pid
        for link in copies:
            # A copy has nothing to compute itself; one made or moved during this recompute is not reached by it,
            # nor by the pass that follows when the piece moved, and would stay marked to recompute.
            link.purgeTouched()

    @staticmethod
    def _new_copy(obj, piece):
        from freecad.maxproframe.create_link import add_link

        link = add_link(obj.Document, f"{piece.Label}_Link")
        # In the Part of the piece before it links to it: the Part would drag in what the piece links to.
        place_in_container_of(link, piece)
        link.LinkedObject = piece
        return link

    def unsetupObject(self, obj):
        """Deleting the pattern deletes its copies; the piece stays."""
        doc = obj.Document
        for link in list(obj.Copies):
            if doc.getObject(link.Name) is not None:
                doc.removeObject(link.Name)

    def dumps(self):
        return None

    def loads(self, state):
        return None


def follow_newest_pieces(doc):
    """Link the copies of every pattern of ``doc`` to the newest piece of its chain; touch the patterns relinked.

    A trim, cutout or drill hole made from the piece later links the piece, not the pattern, and one removed leaves
    the copies linking nothing: before the recompute, so it computes them before the patterns that place them.
    """
    for obj in doc.Objects:
        if not is_profile_pattern(obj) or obj.Piece is None:
            continue
        newest = newest_piece(obj.Piece)
        stale = [link for link in obj.Copies if link.LinkedObject != newest]
        for link in stale:
            link.LinkedObject = newest
        if stale:
            obj.touch()


class NewestPieceObserver:
    """Has every pattern follow the newest piece of its chain at each recompute of a document."""

    def slotBeforeRecomputeDocument(self, doc):
        follow_newest_pieces(doc)


if "_NEWEST_PIECE_OBSERVER" not in globals():
    _NEWEST_PIECE_OBSERVER = NewestPieceObserver()
    App.addDocumentObserver(_NEWEST_PIECE_OBSERVER)


class ViewProviderProfilePattern:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(ICONPATH, "profile-pattern.svg")

    def claimChildren(self):
        return list(self.Object.Copies)

    def setEdit(self, vobj, mode):
        """Double-click: the Profile Pattern panel on this pattern."""
        if mode != 0:
            return None
        import FreeCADGui as Gui

        if Gui.Control.activeDialog():
            App.Console.PrintMessage("MaxProFrame: close the active task dialog before editing a pattern.\n")
            return False
        from freecad.maxproframe import create_profile_pattern_tool

        create_profile_pattern_tool.show_panel(create_profile_pattern_tool.ProfilePatternTaskPanel(edited=self.Object))
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

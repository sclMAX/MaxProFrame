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
# A piece FreeCAD keeps hidden after an Undo is shown again every SHOW_RETRY_MS, SHOW_TRIES times at most.
SHOW_RETRY_MS = 50
SHOW_TRIES = 60
# Distance (mm) and angle (radians) within which an element lies where the element a link named was, as Extend Cut.
ELEMENT_TOLERANCE = 1e-3
ELEMENT_ANGLE_TOLERANCE = 1e-5
# Kinds of the elements a pattern links: its direction edge, its two faces.
EDGE, FACE = "Edge", "Face"
# (document name, pattern name) -> {"Edge": kept, "Faces": [kept, ...]}: where the edge and the faces its links
# name are, each kept as (object name, point, vector) in the frame of the path of the profile its object is built
# on: a point of the line of the edge and its direction, the center of the face and its normal. Taken from the
# elements the links name when they are set, on opening and after an Undo or Redo, and from every element found
# there again: a new size of the frame makes FreeCAD lose their names ("?Edge1") or give them to other elements.
# Kept out of the proxy, which is saved with the document.
_KEPT_ELEMENTS = {}

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


def is_straight_edge(element):
    return isinstance(element, Part.Edge) and isinstance(element.Curve, Part.Line) and len(element.Vertexes) == 2


def is_planar_face(element):
    return isinstance(element, Part.Face) and isinstance(element.Surface, Part.Plane)


def edge_direction(obj, sub):
    """Global unit vector of the straight edge ``sub`` of ``obj``, from its first vertex to its last."""
    edge = global_element(obj, sub)
    if not is_straight_edge(edge):
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
    if not is_planar_face(face):
        raise ValueError(translate("frameforge", "Profile Pattern: the limits must be planar faces."))
    return face.CenterOfMass.dot(direction)


def _holder(obj, sub):
    """(object whose shape has the element ``sub`` of ``obj`` names, path to it, element name, whether lost).

    The holder is ``obj`` itself, or the object at the end of the path through Links and Parts; its element names
    are the ones the link uses. Lost: FreeCAD marked the name as found no more ("?Face2"). None for no holder.
    """
    from freecad.maxproframe.trimmed_profile import MISSING_ELEMENT_PREFIX

    path, _, name = sub.rpartition(".")
    lost = sub.startswith(MISSING_ELEMENT_PREFIX) or name.startswith(MISSING_ELEMENT_PREFIX)
    path, name = path.removeprefix(MISSING_ELEMENT_PREFIX), name.removeprefix(MISSING_ELEMENT_PREFIX)
    try:
        holder = obj.getSubObject(path + ".", 1) if path else obj
    except Exception:
        holder = None
    return (holder, path, name, lost) if holder is not None else None


def _holder_frame(holder):
    """Placement, in the coordinates of the shape of ``holder``, of the path of the profile it is built on.

    As Extend Cut finds its target face again: an element of a piece keeps its place in this frame wherever a new
    size of the sketch takes the path. An object built on no profile: its own placement.
    """
    from freecad.maxproframe.trimmed_profile import _target_frame

    try:
        return _target_frame(holder)
    except Exception:
        return App.Placement(holder.getLinkedObject(True, App.Matrix())[1])


def _point_and_vector(element, kind):
    """An edge: its first vertex and its direction. A face: its center and its normal."""
    from freecad.maxproframe.trimmed_profile import face_normal

    if kind == EDGE:
        return element.Vertexes[0].Point, (element.Vertexes[-1].Point - element.Vertexes[0].Point).normalize()
    return element.CenterOfMass, face_normal(element)


def _is_kind(element, kind):
    return is_straight_edge(element) if kind == EDGE else is_planar_face(element)


def _named_element(shape, name, kind):
    """The element ``name`` of ``shape`` when it is of ``kind`` (straight edge, planar face), else None."""
    try:
        element = shape.getElement(name)
    except Exception:
        return None
    return element if _is_kind(element, kind) else None


def element_snapshot(obj, sub, kind):
    """(object name, point, vector) of the element ``sub`` of ``obj`` in the frame of its holder, or None."""
    found = _holder(obj, sub)
    if found is None or found[3]:
        return None
    holder, _, name, _ = found
    element = _named_element(Part.getShape(holder), name, kind)
    if element is None:
        return None
    frame = _holder_frame(holder).inverse()
    point, vector = _point_and_vector(element, kind)
    return obj.Name, frame.multVec(point), frame.Rotation.multVec(vector)


def _faces_of(obj):
    """The two (object, face) limits of the pattern ``obj``, in order."""
    return [(face_obj, sub) for face_obj, subs in getattr(obj, "Faces", ()) for sub in subs]


def remember_elements(obj):
    """Remember where the edge and the faces the links of the pattern ``obj`` name are, for a new size to find them.

    For links set, opened or put back by Undo / Redo: the shapes are the ones they were picked on. A name lost
    keeps what was remembered for that link, when it is on the same object.
    """
    if obj.Document is None or not {"Edge", "Faces"} <= set(obj.PropertiesList):
        return
    key = (obj.Document.Name, obj.Name)
    before = _KEPT_ELEMENTS.get(key, {})

    def kept(link_obj, sub, kind, old):
        try:
            new = element_snapshot(link_obj, sub, kind)
        except Exception:
            # The next recompute reports what is wrong with the element.
            new = None
        return new if new is not None or old is None or old[0] != link_obj.Name else old

    edge = link_sub(obj.Edge)
    old_faces = before.get("Faces", [])
    _KEPT_ELEMENTS[key] = {
        "Edge": kept(*edge, EDGE, before.get("Edge")) if edge else None,
        "Faces": [
            kept(face_obj, sub, FACE, old_faces[index] if index < len(old_faces) else None)
            for index, (face_obj, sub) in enumerate(_faces_of(obj))
        ],
    }


def remember_all_elements(doc):
    """After an Undo or Redo, every pattern of ``doc`` remembers the elements its links name in the state back."""
    for obj in doc.Objects:
        if is_profile_pattern(obj) and isinstance(getattr(obj, "Proxy", None), ProfilePattern):
            remember_elements(obj)


def _lies_on(element, point, vector, kind):
    """An edge: on the line through ``point`` along ``vector``, either sense. A face: on the plane through ``point``
    with the normal ``vector``."""
    if kind == EDGE:
        start, direction = _point_and_vector(element, EDGE)
        if direction.cross(vector).Length > ELEMENT_ANGLE_TOLERANCE:
            return False
        offset = point - start
        return (offset - direction * offset.dot(direction)).Length <= ELEMENT_TOLERANCE
    from freecad.maxproframe.trimmed_profile import _on_plane

    return _on_plane(element, point, vector)


def _parallel(element, vector):
    return element.Curve.Direction.cross(vector).Length <= ELEMENT_ANGLE_TOLERANCE


def _lost_error(holder, name, kind):
    if kind == EDGE:
        message = translate("frameforge", "Profile Pattern: {} has no straight edge where its edge {} was.")
    else:
        message = translate("frameforge", "Profile Pattern: {} has no planar face where its face {} was.")
    return ValueError(message.format(holder.Label, name))


def find_element(obj, sub, kept, kind):
    """(sub-element, sure) the link (``obj``, ``sub``) of a pattern stands for now.

    ``kept`` is what the pattern remembers of it (``remember_elements``). The element named when it lies where
    the remembered one was (an edge on its line, a face on its plane); else the element of that kind there: the one
    named so, else the one nearest the remembered point. Nothing there any more: an edge takes the straight edge
    named, else the nearest one, along the remembered direction (only the direction counts); a face takes the face
    named, as the link says. ``sure`` is False then: what is remembered stays. Nothing found fails naming the object.
    Nothing remembered: the link as it is, sure.
    """
    found = _holder(obj, sub)
    if found is None:
        return sub, False
    holder, path, name, lost = found
    shape = Part.getShape(holder)
    named = None if lost else _named_element(shape, name, kind)
    if kept is None or kept[0] != obj.Name:
        if lost:
            raise _lost_error(holder, name, kind)
        # Nothing remembered: the link as it is, with the errors of a wrong element.
        return sub, True
    frame = _holder_frame(holder)
    point, vector = frame.multVec(kept[1]), frame.Rotation.multVec(kept[2])
    full = lambda element_name: f"{path}.{element_name}" if path else element_name  # noqa: E731
    if named is not None and _lies_on(named, point, vector, kind):
        return sub, True
    elements = shape.Edges if kind == EDGE else shape.Faces
    elements = [(f"{kind}{index}", element) for index, element in enumerate(elements, 1) if _is_kind(element, kind)]

    def nearest(candidates):
        exact = [element_name for element_name, _ in candidates if element_name == name]
        if exact:
            return exact[0]
        return min(candidates, key=lambda item: item[1].distToShape(Part.Vertex(point))[0])[0]

    there = [(element_name, element) for element_name, element in elements if _lies_on(element, point, vector, kind)]
    if there:
        return full(nearest(there)), True
    if kind == EDGE:
        along = [(element_name, element) for element_name, element in elements if _parallel(element, vector)]
        if along:
            chosen = nearest(along)
            App.Console.PrintLog(
                f"Profile Pattern: no edge of {holder.Label} on the line of {name}; {chosen} along it is used.\n"
            )
            return full(chosen), False
    elif named is not None:
        App.Console.PrintLog(f"Profile Pattern: no face of {holder.Label} on the plane of {name}; it is used.\n")
        return sub, False
    raise _lost_error(holder, name, kind)


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


def copies_needed(obj):
    """How many copies the values of the pattern ``obj`` ask for."""
    if obj.Mode == BETWEEN_FACES:
        return max(obj.Count - 1, 0)
    return len(count_and_pitch_steps(obj.Count, obj.Sense))


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

    def onChanged(self, obj, prop):
        if prop in ("Count", "Mode", "Sense"):
            self._drop_extra_copies(obj)
        elif prop in ("Edge", "Faces"):
            doc = obj.Document
            # Set by hand, by the panel or by Undo (read again once every shape is back). The pattern linking an
            # element found again happens while recomputing and keeps what is remembered.
            if doc is not None and not doc.Recomputing and not doc.Restoring:
                remember_elements(obj)

    def onDocumentRestored(self, obj):
        """Remember the elements the links name as saved: a new size that makes FreeCAD lose them finds them again."""
        remember_elements(obj)

    @staticmethod
    def _drop_extra_copies(obj):
        """Delete the copies the new values leave over now, in the Undo step that changes them.

        Deleted by the recompute, they would get a Delete step of their own, and its Undo would bring them back
        without the pattern or the Part keeping them. Not while the document is opened, undone or recomputed.
        """
        doc = obj.Document
        if doc is None or "Copies" not in obj.PropertiesList:
            return
        if any(getattr(doc, state, False) for state in ("Restoring", "Transacting", "Recomputing")):
            return
        copies = [link for link in obj.Copies if doc.getObject(link.Name) is not None]
        needed = copies_needed(obj)
        if len(copies) <= needed:
            return
        obj.Copies = copies[:needed]
        for extra in copies[needed:]:
            doc.removeObject(extra.Name)

    def execute(self, obj):
        piece = obj.Piece
        edge = link_sub(obj.Edge)
        if piece is None or edge is None:
            raise ValueError(translate("frameforge", "Profile Pattern: a piece and a direction edge are needed."))
        direction = self._direction(obj, edge)
        # The copies show the newest piece: Between faces measures it, and moves it by the offsets of its profile.
        piece = newest_piece(piece)
        if obj.Mode == BETWEEN_FACES:
            moves = self._between_faces(obj, piece, direction)
        else:
            moves = [direction * (step * obj.Pitch.Value) for step in count_and_pitch_steps(obj.Count, obj.Sense)]
        self._place_copies(obj, piece, moves)

    @staticmethod
    def _kept_elements(obj):
        return _KEPT_ELEMENTS.setdefault((obj.Document.Name, obj.Name), {"Edge": None, "Faces": []})

    def _direction(self, obj, edge):
        """Global direction of the edge of ``obj``, found again where it was; the link follows it, in its sense."""
        edge_obj, sub = edge
        kept = self._kept_elements(obj)
        before = kept["Edge"]
        found, sure = find_element(edge_obj, sub, before, EDGE)
        if found != sub:
            obj.Edge = (edge_obj, (found,))
        direction = edge_direction(edge_obj, found)
        now = element_snapshot(edge_obj, found, EDGE)
        if now is not None and before is not None and before[0] == now[0] and now[2].dot(before[2]) < 0:
            # The edge found runs the other way: the copies keep the sense of the edge picked.
            direction = -direction
            now = (now[0], now[1], -now[2])
        if sure and now is not None:
            kept["Edge"] = now
        return direction

    def _faces(self, obj):
        """The two (object, face) limits of ``obj``, found again where they were; the links follow them."""
        faces = _faces_of(obj)
        kept = self._kept_elements(obj)
        remembered = list(kept["Faces"]) + [None] * (len(faces) - len(kept["Faces"]))
        found = []
        for index, (face_obj, sub) in enumerate(faces):
            name, sure = find_element(face_obj, sub, remembered[index], FACE)
            found.append((face_obj, name))
            if sure:
                remembered[index] = element_snapshot(face_obj, name, FACE) or remembered[index]
        kept["Faces"] = remembered[: len(faces)]
        if found != faces:
            obj.Faces = [(face_obj, (name,)) for face_obj, name in found]
        return found

    def _between_faces(self, obj, piece, direction):
        """Moves of the copies from the piece; the piece itself goes to its slot."""
        problem = between_faces_problem(piece, direction)
        if problem:
            raise ValueError(problem)
        faces = self._faces(obj)
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


def show_newest_pieces(doc, relinked):
    """Show the newest piece of every pattern of ``doc`` whose copies an Undo or Redo relinked (``relinked``: names).

    Undoing a hole, cutout or trim made on the piece after the pattern relinks the copies back to the piece. Until
    the tree view catches up, the piece is still listed only under a copy, as a child of the hole that copy showed:
    FreeCAD then refuses to show it, and the Undo leaves it hidden. Shown again once the tree lets it.
    """
    pieces = []
    for obj in doc.Objects:
        if is_profile_pattern(obj) and obj.Piece is not None and any(link.Name in relinked for link in obj.Copies):
            pieces.append(newest_piece(obj.Piece))
    show_when_showable(pieces)


def show_when_showable(pieces, tries=SHOW_TRIES):
    """Show ``pieces``; those FreeCAD keeps hidden yet are tried again later, ``tries`` times in all."""
    hidden = []
    for piece in pieces:
        try:
            if piece.Document.getObject(piece.Name) is not piece or piece.Visibility:
                continue
        except Exception:
            continue  # deleted meanwhile
        piece.Visibility = True
        if not piece.Visibility:
            hidden.append(piece)
    if hidden and tries > 1 and App.GuiUp:
        from PySide import QtCore

        QtCore.QTimer.singleShot(SHOW_RETRY_MS, lambda: show_when_showable(hidden, tries - 1))


class NewestPieceObserver:
    """Has every pattern follow the newest piece of its chain at each recompute of a document, and show it after an
    Undo or Redo that relinked its copies."""

    def __init__(self):
        self._relinked = {}

    def slotBeforeRecomputeDocument(self, doc):
        follow_newest_pieces(doc)

    def slotChangedObject(self, obj, prop):
        if prop == "LinkedObject" and getattr(obj.Document, "Transacting", False):
            self._relinked.setdefault(obj.Document.Name, set()).add(obj.Name)

    def slotUndoDocument(self, doc):
        remember_all_elements(doc)
        show_newest_pieces(doc, self._relinked.pop(doc.Name, set()))

    def slotRedoDocument(self, doc):
        remember_all_elements(doc)
        show_newest_pieces(doc, self._relinked.pop(doc.Name, set()))

    def slotDeletedObject(self, obj):
        doc = getattr(obj, "Document", None)
        if doc is not None:
            _KEPT_ELEMENTS.pop((doc.Name, obj.Name), None)

    def slotDeletedDocument(self, doc):
        self._relinked.pop(doc.Name, None)
        for key in [key for key in _KEPT_ELEMENTS if key[0] == doc.Name]:
            del _KEPT_ELEMENTS[key]


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

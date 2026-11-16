"""Fingers Interlock at an End Miter corner between two straight tubes (odd/tasks/miter-fingers.md, T2: S1, S5, S6; D1,
D2).

Two separate tubes A and B, each cut by its own End Miter against the other, interlock with Fingers at the inner vertex
of their corner (``miter_finger_geometry``). The Interlock (``interlock.Interlock``) is of Kind Fingers, with the same
settings as at a folded corner, marked ``AtEndMiter`` (``interlock.is_miter_interlock``, D2): no Folded Bar takes it
(``interlock.on_folded_corner``). It links the two tube profiles (``PieceA`` the first face given, which owns the first
finger, ``PieceB``) and remembers the two inner walls given: ``FaceA`` and ``FaceB`` (the piece under each tube's
fingers and its inner wall face), each one's plane local to the profile of its tube (``tab_interlock.face_snapshot``),
so a face FreeCAD renames or loses after an upstream edit is found again on that plane (``tab_interlock.found_face``).

Two pieces make it real, one on top of the stack of each tube, a cutout-like piece (``FingerPiece``, label suffix
_Fg) as the pieces of a Tabs Interlock are (D1): the piece under it with its own fingers fused and the other tube's
fingers cut out of it (``miter_finger_geometry.joined``). Both read the Interlock, which links the pieces under them:
neither depends on the other. They build the ``MiterCorner`` from the two faces and from the End Miter of each tube
against the other, found in its stack (S6): its real cut plane, the gap included (``TrimmedProfile.miter_planes``
shifted by half its ``MiterGap``) and its section. A refusal leaves a piece with the shape under it, in error with the
InterlockError message. Each piece is as long as it reaches along its axis, its finger tips included (S5), and keeps
the cut angles of its End Miter (``cut_ends``): the BOM, the Cut List and the Piece Table read them.

Deleting the Interlock removes both pieces (``Interlock.unsetupObject``) and gives back the pieces under them
(``tab_interlock.give_back``); undo brings everything back. ``make_miter_fingers`` makes it; ``miter_order`` tells,
making nothing, whether two faces clicked make one and what is refused (for the Interlock panel).

Either tube, or both, can be the end tube of a Folded Bar (T3: the user's case). A face clicked on the bar stands for
the face of the tube under the clicked point (``folded_bar.segment_at``, as for Tabs); a click on a bend is refused.
The finger piece is the newest piece of its tube: the bar folds it at the next recompute of the document
(``folded_bar.follow_new_pieces``), its shape shows the fingers and the cuts, its unfold carries them and its developed
length runs to the finger tips (S5). The fingers go only on a free end of a bar (the start of its first tube or the
end of its last one, on an open bar): a corner at a folded corner of the bar or at the open corner of a closed bar
(D5) is refused naming the tubes and the bar (``_check_bar_ends``), at creation and at every recompute.
"""

from collections import namedtuple

import Part

from freecad.maxproframe._utils import is_trimmedbody, piece_stack
from freecad.maxproframe.extruded_cutout import along_extent
from freecad.maxproframe.ff_tools import place_in_container_of, translate
from freecad.maxproframe.folded_bar import bar_chain, folding_bar
from freecad.maxproframe.folded_chain import FOLDABLE_FAMILIES, ChainError, base_profile
from freecad.maxproframe.interlock import (
    FINGER_PROPERTIES,
    FINGER_ROLES,
    FINGERS_A_ROLE,
    MITER_SIDES,
    Interlock,
    ViewProviderInterlock,
    add_miter_properties,
    interlock_pieces,
    interlock_settings,
    is_miter_interlock,
)
from freecad.maxproframe.interlock_geometry import FINGERS, FingerSettings, InterlockError
from freecad.maxproframe.miter_finger_geometry import MiterCorner, MiterTube, TubeFingers, check, joined, make_fingers
from freecad.maxproframe.profile_pattern import container_placement, newest_piece, placed
from freecad.maxproframe.tab_interlock import (
    ViewProviderInterlockPiece,
    _alive,
    _flat_face,
    _InterlockPiece,
    _make_piece,
    _on_bar,
    face_snapshot,
    found_face,
)
from freecad.maxproframe.trimmed_profile import _container_placement, in_frame_of

END_MITER = "End Miter"
# The Interlock a miter corner starts with: the FingerSettings defaults.
DEFAULT_COUNT = FingerSettings().count

MiterFace = namedtuple("MiterFace", "piece sub point")
MiterFace.__doc__ = """A face clicked for Fingers at an End Miter corner: the face ``sub`` of ``piece`` (a piece of a
tube or a Folded Bar), clicked at the global ``point`` (None: the center of the face). On a bar the point picks the
tube (``folded_bar.segment_at``)."""

MiterOrder = namedtuple("MiterOrder", "first second error found")
MiterOrder.__doc__ = """Whether two faces clicked make Fingers at an End Miter corner (``miter_order``): the
``MiterFace`` of the ``first`` tube (it owns the first finger) and of the ``second`` one, in the order clicked, when
they do (``error`` None); else ``error``, the InterlockError to show, and ``found``, whether either tube has an End
Miter against the other (a miter corner, refused for another reason: S6, S7)."""


def _names(first, second):
    """The labels of the tubes of ``first`` and ``second`` (their profiles), as the refusals name them."""
    return tuple((base_profile(piece) or piece).Label for piece in (first, second))


def _not_a_corner(names):
    # The text of miter_finger_geometry's refusal: one message for faces that are no inner walls of a miter corner.
    return InterlockError(
        translate(
            "MaxProFrame", "The faces of {} and {} are not the inner walls of an End Miter corner between them."
        ).format(*names)
    )


def _same_tube(label):
    return InterlockError(
        translate(
            "MaxProFrame", "Both faces are on {}: click the inner wall of each tube of the End Miter corner."
        ).format(label)
    )


def _thickness(profile, names):
    family = getattr(profile, "Family", "")
    if family not in FOLDABLE_FAMILIES:
        raise InterlockError(
            translate(
                "MaxProFrame", "The fingers of the corner between {} and {} need two tubes: {} is a {} profile."
            ).format(*names, profile.Label, family)
        )
    return float(profile.Thickness)


# The free ends of a Folded Bar.


def _bar_end(piece, profile, other):
    """(bar, whether the end of the tube ``profile`` (of ``piece``) nearest the piece ``other`` is an end of that bar,
    whether the bar is closed) for a tube a Folded Bar folds, else None. A bar that does not fold says why itself: None
    too."""
    bar = folding_bar(piece)
    if bar is None:
        return None
    try:
        chain = bar_chain(bar)
    except ChainError:
        return None
    index = next((i for i, segment in enumerate(chain.segments) if segment.profile.Name == profile.Name), None)
    if index is None:
        return None
    segment = chain.segments[index]
    near = placed(other.Shape, container_placement(other))
    at_start = near.distToShape(Part.Vertex(segment.start))[0] <= near.distToShape(Part.Vertex(segment.end))[0]
    # The start of the first tube or the end of the last one: an end of the bar, else a folded corner.
    bar_end = index == 0 if at_start else index == len(chain.segments) - 1
    return bar, bar_end, chain.closed


def _check_bar_ends(names, pieces, profiles):
    """Raise InterlockError when a Folded Bar folds the tube of either of ``pieces`` and the end of that tube at the
    corner (its end nearest the other piece) is no free end of the bar: a folded corner, or the open corner of a
    closed bar (D5)."""
    for index in (0, 1):
        found = _bar_end(pieces[index], profiles[index], pieces[1 - index])
        if found is None:
            continue
        bar, bar_end, closed = found
        if bar_end and not closed:
            continue
        if bar_end:
            text = translate(
                "MaxProFrame",
                "The End Miter corner between {} and {} is at the open corner of {}: the fingers go on a free end of a "
                "Folded Bar.",
            )
        else:
            text = translate(
                "MaxProFrame",
                "The End Miter corner between {} and {} is at a folded corner of {}: the fingers go on a free end of a "
                "Folded Bar.",
            )
        raise InterlockError(text.format(*names, bar.Label))


# The End Miters.


def _end_miter(piece, other):
    """(End Miter, index of its TrimmingBoundary item) of the newest End Miter in the stack of ``piece`` against the
    tube ``other`` (a profile), or None."""
    for obj in piece_stack(piece):
        if not is_trimmedbody(obj) or obj.TrimmedProfileType != END_MITER:
            continue
        for index, boundary in enumerate(obj.TrimmingBoundary or ()):
            target = boundary[0]
            tube = base_profile(target) if target is not None else None
            if tube is not None and tube.Name == other.Name:
                return obj, index
    return None


def _miters(names, pieces, profiles):
    """The End Miter of each of ``pieces`` against the other tube (``_end_miter``); raises InterlockError saying which
    is missing and what makes it (S6)."""
    found = [_end_miter(pieces[0], profiles[1]), _end_miter(pieces[1], profiles[0])]
    if found == [None, None]:
        raise InterlockError(
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} need an End Miter of each tube against the other: make "
                "them with Miter Ends.",
            ).format(*names)
        )
    for index in (0, 1):
        if found[index] is None:
            raise InterlockError(
                translate(
                    "MaxProFrame",
                    "The fingers of the corner between {} and {} need an End Miter of {} against {}: make it with "
                    "Miter Ends.",
                ).format(*names, names[index], names[1 - index])
            )
    return found


def _tube(name, frame, piece, face, thickness, miter):
    """The ``MiterTube`` of ``face`` (of ``piece``, cut by ``miter``: (End Miter, boundary index)) in the coordinates
    of the container of ``frame``."""
    trim, index = miter
    plane = trim.Proxy.miter_planes(trim)[index].shifted(trim.MiterGap.Value / 2.0)
    move = _container_placement(frame).inverse().multiply(_container_placement(trim))
    return MiterTube(
        name,
        in_frame_of(frame, piece, face),
        thickness,
        move.Rotation.multVec(-plane.inward),
        in_frame_of(frame, trim, plane.section),
        (move.multVec(plane.origin), move.Rotation.multVec(plane.normal)),
    )


def _corner(names, first, first_face, second, second_face):
    """The ``MiterCorner`` of the face ``first_face`` of the piece ``first`` (tube A) and ``second_face`` of ``second``
    (tube B), in the coordinates of the container of ``first``; raises InterlockError for a profile that is no tube, a
    tube of a Folded Bar not at a free end of it (``_check_bar_ends``) or a missing End Miter."""
    profiles = base_profile(first), base_profile(second)
    if None in profiles:
        raise _not_a_corner(names)
    thickness = [_thickness(profile, names) for profile in profiles]
    _check_bar_ends(names, (first, second), profiles)
    miters = _miters(names, (first, second), profiles)
    return MiterCorner(
        *(
            _tube(name, first, piece, face, wall, miter)
            for name, piece, face, wall, miter in zip(
                names, (first, second), (first_face, second_face), thickness, miters
            )
        )
    )


# The Interlock.


def interlock_faces(obj):
    """((piece, face) of tube A, (piece, face) of tube B) of the miter-corner Interlock ``obj``: each face found on its
    piece on the plane it remembers. Raises InterlockError when one is gone."""
    faces = []
    for side in MITER_SIDES:
        link = getattr(obj, f"Face{side}")
        piece, subs = link if link else (None, ())
        sub = subs[0] if subs else ""
        snapshot = tuple(getattr(obj, f"{name}{side}") for name in ("Point", "Normal", "Anchor"))
        found = found_face(piece, sub, *snapshot) if _alive(piece) else None
        if found is None:
            raise InterlockError(
                translate("MaxProFrame", "The interlock {} lost the face of {} it was made on.").format(
                    obj.Label, getattr(piece, "Label", side)
                )
            )
        faces.append((piece, found[1]))
    return tuple(faces)


def interlock_fingers(obj):
    """(piece of tube A, ``MiterFingerShapes``) of the miter-corner Interlock ``obj``, the shapes in the coordinates of
    the container of that piece. Raises InterlockError as ``interlock_faces`` and ``miter_finger_geometry`` do."""
    (first, first_face), (second, second_face) = interlock_faces(obj)
    corner = _corner(_names(first, second), first, first_face, second, second_face)
    return first, make_fingers(interlock_settings(obj), corner)


def miter_pieces(obj):
    """[finger piece of tube A, of tube B] of the miter-corner Interlock ``obj``; None for one it has not got."""
    pieces = {piece.InterlockRole: piece for piece in interlock_pieces(obj)}
    return [pieces.get(role) for role in FINGER_ROLES]


def _in_frame(piece, first, tube):
    """The ``TubeFingers`` ``tube``, in the coordinates of the container of ``first``, in those of ``piece``."""
    move = _container_placement(piece).inverse().multiply(_container_placement(first))
    if move.isIdentity():
        return tube
    matrix = move.toMatrix()

    def moved(shape):
        shape = shape.copy()
        shape.transformShape(matrix)
        return shape

    point, direction = tube.tip
    return TubeFingers(
        [moved(shape) for shape in tube.fingers],
        [moved(shape) for shape in tube.cuts],
        (move.multVec(point), move.Rotation.multVec(direction)),
    )


class FingerPiece(_InterlockPiece):
    """A tube of an End Miter corner with its fingers fused and the other tube's cut out (_Fg); ``InterlockRole``
    FingersA for tube A, FingersB for tube B."""

    def __init__(self, obj, interlock, base, role):
        self.role = role
        super().__init__(obj, interlock, base)
        del self.role

    @staticmethod
    def interlock_tooltip():
        return translate("App::Property", "The Interlock of the End Miter corner this piece adds its fingers for")

    def made(self, fp):
        """(``TubeFingers`` of its tube, in its coordinates,)."""
        first, shapes = interlock_fingers(fp.Interlock)
        tube = shapes.a if fp.InterlockRole == FINGERS_A_ROLE else shapes.b
        return (_in_frame(fp.baseObject[0], first, tube),)

    def shaped(self, fp, under, tube):
        return joined(under.Shape, tube)

    def _update_structure_data(self, fp, under=None, made=None):
        """S5: as long as the piece under it, plus how far its finger tips reach past it along its axis."""
        super()._update_structure_data(fp, under, made)
        under = fp.baseObject[0] if under is None else under
        fp.Cutout = bool(under.Cutout)
        if made is None:
            return
        point, direction = made[0].tip
        reach = point.dot(direction) - along_extent(under.Shape, direction)[1]
        fp.Length = under.Length.Value + max(reach, 0.0)


class ViewProviderFingerPiece(ViewProviderInterlockPiece):
    icon = "interlock-fingers.svg"

    def claimChildren(self):
        """The piece under it, hidden; the piece of tube A shows the Interlock too."""
        children = super().claimChildren()
        obj = self.Object
        if obj.InterlockRole == FINGERS_A_ROLE and obj.Interlock is not None:
            children.append(obj.Interlock)
        return children


# Creation.

_Located = namedtuple("_Located", "names profiles pieces subs faces snapshots")


def _located(first, second):
    """The two faces ``first`` and ``second`` (``MiterFace``), found on the newest piece of each tube; a face clicked
    on a Folded Bar stands for the face of the tube under its point (``tab_interlock._on_bar``).

    Raises InterlockError for a click on a bend of a bar, a face that is no flat face of a tube, both faces on one
    tube.
    """
    clicked = [_on_bar(face.piece, face.sub, face.point) for face in (first, second)]
    names = _names(clicked[0][0], clicked[1][0])
    profiles = base_profile(clicked[0][0]), base_profile(clicked[1][0])
    if None in profiles:
        raise _not_a_corner(names)
    if profiles[0].Name == profiles[1].Name:
        raise _same_tube(profiles[0].Label)
    pieces, subs, faces, snapshots = [], [], [], []
    for piece, sub in clicked:
        newest = newest_piece(piece)
        picked = _flat_face(piece, sub)
        if picked is None:
            raise _not_a_corner(names)
        found = found_face(newest, sub if newest == piece else "", *face_snapshot(piece, picked))
        if found is None:
            raise _not_a_corner(names)
        pieces.append(newest)
        subs.append(found[0])
        faces.append(found[1])
        snapshots.append(face_snapshot(newest, found[1]))
    return _Located(names, profiles, pieces, subs, faces, snapshots)


def _twin(profiles):
    """The miter-corner Interlock already between the two tubes ``profiles``, or None: one per corner (S2)."""
    key = {profile.Name for profile in profiles}
    for obj in profiles[0].InList:
        if is_miter_interlock(obj) and obj.PieceA is not None and obj.PieceB is not None:
            if {obj.PieceA.Name, obj.PieceB.Name} == key:
                return obj
    return None


def _check(located, settings):
    """Raise InterlockError when the corner of ``located`` already has fingers, has not got both End Miters, or the
    fingers of ``settings`` (by property name) do not fit it."""
    names = located.names
    twin = _twin(located.profiles)
    if twin is not None:
        raise InterlockError(
            translate("MaxProFrame", "The corner between {} and {} already has fingers: {}.").format(*names, twin.Label)
        )
    values = {FINGER_PROPERTIES[name]: value for name, value in settings.items()}
    first, second = located.pieces
    check(FingerSettings(**values), _corner(names, first, located.faces[0], second, located.faces[1]))


def _unknown_settings(settings):
    unknown = sorted(set(settings) - set(FINGER_PROPERTIES))
    if unknown:
        raise ValueError(f"Unknown finger settings: {', '.join(unknown)}; give {', '.join(FINGER_PROPERTIES)}.")


def miter_order(first, second, **settings):
    """Whether the faces ``first`` and ``second`` (``MiterFace``, in the order clicked: the first one owns the first
    finger, D3) make Fingers at an End Miter corner with ``settings`` (by property name, as for
    ``make_miter_fingers``), as a ``MiterOrder``. Makes nothing."""
    _unknown_settings(settings)
    try:
        located = _located(first, second)
    except InterlockError as error:
        return MiterOrder(None, None, error, False)
    found = any(
        _end_miter(piece, other) is not None for piece, other in zip(located.pieces, reversed(located.profiles))
    )
    try:
        _check(located, settings)
    except InterlockError as error:
        return MiterOrder(None, None, error, found)
    return MiterOrder(first, second, None, True)


def _piece_maker(role):
    def make(obj, interlock, base):
        return FingerPiece(obj, interlock, base, role)

    return make


def make_miter_fingers(first, second, **settings):
    """A Fingers Interlock at the End Miter corner between the tubes of the faces ``first`` and ``second``
    (``MiterFace``: the inner wall of each tube; the first one owns the first finger, D3), with a finger piece (_Fg) on
    each tube.

    The faces are found on the newest piece of each tube, which the new pieces go on. ``settings`` are by property
    name (``Count=3``, ``Clearance=0.2``: ``interlock.FINGER_PROPERTIES``); another name raises ValueError. Raises
    InterlockError, before anything is made, for a click on a bend of a Folded Bar, two faces of one tube, a tube of a
    bar not at a free end of it, a corner that already has fingers, a tube without its End Miter against the other
    (S6), faces that are not the inner walls of the corner or fingers that do not fit it
    (``miter_finger_geometry.check``). Run it in the caller's transaction and recompute the document afterwards: a bar
    folds the new pieces then.
    """
    _unknown_settings(settings)
    located = _located(first, second)
    _check(located, settings)

    first_piece = located.pieces[0]
    doc = first_piece.Document
    obj = doc.addObject("App::FeaturePython", "Interlock")
    # Before it links anything: a Part receiving it would pull in what it links.
    place_in_container_of(obj, first_piece)
    Interlock(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderInterlock(obj.ViewObject)
    obj.Label = "Interlock_{}_{}".format(*(profile.Label for profile in located.profiles))
    obj.Kind = FINGERS
    obj.Count = DEFAULT_COUNT
    add_miter_properties(obj)
    obj.PieceA, obj.PieceB = located.profiles
    for side, piece, name, snapshot in zip(MITER_SIDES, located.pieces, located.subs, located.snapshots):
        setattr(obj, f"Face{side}", (piece, (name,)))
        for prop, value in zip(("Point", "Normal", "Anchor"), snapshot):
            setattr(obj, f"{prop}{side}", value)
    for name, value in settings.items():
        setattr(obj, name, value)
    for role, piece, name in zip(FINGER_ROLES, located.pieces, located.subs):
        _make_piece(_piece_maker(role), ViewProviderFingerPiece, piece, name, obj, "_Fg")
    return obj

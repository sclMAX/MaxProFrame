"""Tabs Interlock on straight pieces: the crossbar ends in tabs through slots cut in the rail (odd/tasks/t-joint-tabs.md,
T2: S1, S6; D1).

A Tabs Interlock (``interlock.Interlock`` with ``Kind`` Tabs) holds the settings and links the two tube profiles
(``PieceA`` the crossbar, ``PieceB`` the rail) and the two faces picked: ``CrossbarFace`` (the piece under the tabs and
the crossbar wall that carries them) and ``RailFace`` (the piece under the slots and the rail face they go through).
Each face is remembered as its plane, local to the profile of its tube, with the anchor shift of the section, as a
Drill Hole remembers its reference: a face FreeCAD renames or loses after a cut or a move of its piece is found again
on that plane (``found_face``).

Two pieces make it real, each one on top of the stack of its tube, a cutout-like piece (``baseObject``, the profile
data, ``Cutout``) so the stacks (``piece_stack``, ``base_profile``, ``newest_piece``), the BOM, the Cut List, the Piece
Table and the IDs treat it as one:

- ``TabPiece`` (label suffix _Tb): the piece under it fused with the tabs. Its ``Length`` runs to the tab tips (S6);
  its cut angles are those of the piece under it (``cut_ends``): the tabs are cut with its end.
- ``SlotPiece`` (label suffix _Sl): the piece under it cut by the slots, ``Cutout`` True.

Both build the same ``tab_geometry.TJoint`` from the Interlock (``interlock_joint``): the crossbar wall, its axis
toward the rail, the end plane (the Extend / Cut against the rail in the crossbar's stack, else its end face nearest
the rail face), the rail face and both wall thicknesses. A refusal leaves the piece with the shape under it and in error
with the InterlockError message. Neither depends on the other: the tabs read the rail piece under the slots and the
slots the crossbar piece under the tabs, and the crossbar trim keeps targeting the rail piece it was made against.

Deleting the Interlock removes both pieces (``Interlock.unsetupObject``); a piece removed gives back the piece under
it: whatever was built on it, or linked it, links the piece under it instead (``give_back``). Undo brings everything
back. ``make_tab_interlock`` is what the Interlock panel calls.

The crossbar, the rail or both can be tubes of a Folded Bar (T3: S7). A face clicked on the bar stands for the face of
the tube under the clicked point (``folded_bar.segment_at``, as for a Drill Hole or a Cutout on a bar); a click on a
bend is refused. The new piece is the newest piece of its tube: the bar folds it at the next recompute of the
document (``folded_bar.follow_new_pieces``) and its unfold carries what the piece changes on its tube, the slots cut
and the tabs added past the end of the tube (the bar is then as long as the tab tips). The tabs go only on a free end
of a bar (the start of its first tube or the end of its last one, on an open bar): at a folded corner or at the open
corner of a closed frame the joint is refused naming the tubes and the bar (``_check_bar_end``).
"""

import os

import FreeCAD as App
import Part

from freecad.maxproframe._utils import (
    get_childrens_from_extrudedcutout,
    is_foldedbar,
    is_tab_piece,
    is_trimmedbody,
    piece_stack,
    restore_custom_profile_link,
)
from freecad.maxproframe.drill_hole import MISSING_ELEMENT_PREFIX, _element, _on_plane, _show_unless_built_on
from freecad.maxproframe.extruded_cutout import ExtrudedCutout, ViewProviderExtrudedCutout, _uncut_shape, along_extent
from freecad.maxproframe.ff_tools import ICONPATH, place_in_container_of, translate
from freecad.maxproframe.folded_bar import bar_chain, folding_bar, segment_at
from freecad.maxproframe.folded_chain import FOLDABLE_FAMILIES, ChainError, base_profile
from freecad.maxproframe.interlock import (
    SLOTS_ROLE,
    TAB_PROPERTIES,
    TAB_SIDES,
    TABS_ROLE,
    Interlock,
    ViewProviderInterlock,
    interlock_pieces,
    interlock_settings,
    is_interlock,
)
from freecad.maxproframe.interlock_geometry import TABS, InterlockError, TabSettings
from freecad.maxproframe.profile import section_shift
from freecad.maxproframe.profile_pattern import container_placement, newest_piece
from freecad.maxproframe.tab_geometry import TJoint, check, make_tabs
from freecad.maxproframe.trimmed_profile import face_normal, in_frame_of

# |cos| between a face normal and the crossbar axis above which the face is no wall along the crossbar.
WALL_TOLERANCE = 1e-6
# Distance (mm) and angle (radians) within which two remembered faces lie on one plane.
PLANE_TOLERANCE = 1e-3
ANGLE_TOLERANCE = 1e-5
# Distance (mm) within which an element of the piece under is where the element of a removed piece was.
ELEMENT_TOLERANCE = 1e-3
# The Interlock a Tabs Interlock starts with: the TabSettings defaults.
DEFAULT_COUNT = TabSettings().count


def _names(crossbar, rail):
    """The labels of the tubes of ``crossbar`` and ``rail`` (their profiles), as the refusals name them."""
    return tuple((base_profile(piece) or piece).Label for piece in (crossbar, rail))


def _no_faces(names):
    return InterlockError(
        translate("MaxProFrame", "There is no T joint between {} and {}: pick a flat face of each tube.").format(*names)
    )


def _alive(obj):
    try:
        return obj is not None and obj.Document is not None and obj.Document.getObject(obj.Name) is obj
    except Exception:
        return False


# The faces: picked, remembered local to the profile, found again.


def _flat_face(piece, sub):
    """The planar face ``sub`` of ``piece``, or None."""
    name = (sub or "").removeprefix(MISSING_ELEMENT_PREFIX)
    face = _element(piece.Shape.Faces, name, "Face") if name else None
    return face if face is not None and isinstance(face.Surface, Part.Plane) else None


def face_snapshot(piece, face):
    """(point, normal, anchor shift) of the planar ``face`` of ``piece``, local to the profile of its tube."""
    profile = base_profile(piece)
    inverse = profile.Placement.inverse()
    return inverse.multVec(face.CenterOfMass), inverse.Rotation.multVec(face_normal(face)), section_shift(profile)


def found_face(piece, sub, point, normal, anchor):
    """(face name, face) of ``piece`` on the plane remembered by ``face_snapshot``, or None.

    The face ``sub`` when it is on that plane ("?Face3", a face FreeCAD lost track of, is read as Face3), else the
    face on it nearest the point remembered. The anchor moves the section, not the profile: the plane moves with it.
    """
    profile = base_profile(piece)
    placement = profile.Placement
    at = placement.multVec(point + section_shift(profile) - anchor)
    normal = placement.Rotation.multVec(normal)
    faces = piece.Shape.Faces
    name = (sub or "").removeprefix(MISSING_ELEMENT_PREFIX)
    named = _element(faces, name, "Face") if name else None
    if named is not None and _on_plane(named, normal, at):
        return name, named
    on_plane = [(f"Face{index}", face) for index, face in enumerate(faces, 1) if _on_plane(face, normal, at)]
    return min(on_plane, key=lambda item: item[1].distToShape(Part.Vertex(at))[0], default=None)


def _same_plane(first, second):
    """Whether two remembered (point, normal) lie on one plane."""
    (point, normal), (other_point, other_normal) = first, second
    return normal.getAngle(other_normal) < ANGLE_TOLERANCE and abs((other_point - point).dot(normal)) < PLANE_TOLERANCE


# The joint.


def _untabbed(piece):
    """The first piece of the stack of ``piece`` without tabs: its end faces are the crossbar's own."""
    return next((obj for obj in piece_stack(piece) if not is_tab_piece(obj)), piece)


def _end_plane(crossbar, rail_profile, rail_face, direction):
    """(point, normal) of the plane the crossbar ends on near ``rail_face``, or None for the plane of that face.

    The Extend / Cut against the rail in the stack of ``crossbar`` (the one nearest the rail face), its gap included;
    else the planar end face of the crossbar nearest the rail face.
    """
    center, normal = rail_face.CenterOfMass, face_normal(rail_face)
    planes = []
    for piece in piece_stack(crossbar):
        if not is_trimmedbody(piece) or piece.TrimmedProfileType != "Extend Cut" or not piece.TrimmingBoundary:
            continue
        target = piece.TrimmingBoundary[0][0]
        tube = base_profile(target) if target is not None else None
        if tube is not None and tube.Name == rail_profile.Name:
            plane = piece.Proxy.extend_cut_plane(piece)
            planes.append((plane.origin, plane.normal))
    if not planes:
        planes = [
            (face.CenterOfMass, face_normal(face))
            for face in _untabbed(crossbar).Shape.Faces
            if isinstance(face.Surface, Part.Plane) and abs(face_normal(face).dot(direction)) > WALL_TOLERANCE
        ]
    return min(planes, key=lambda plane: abs((plane[0] - center).dot(normal)), default=None)


def _thickness(profile, names):
    family = getattr(profile, "Family", "")
    if family not in FOLDABLE_FAMILIES:
        raise InterlockError(
            translate("MaxProFrame", "The tabs of the T joint between {} and {} need two tubes: {} is a {} profile.")
            .format(*names, profile.Label, family)
        )  # fmt: skip
    return float(profile.Thickness)


def _joint(names, crossbar, crossbar_face, rail, rail_face):
    """The ``TJoint`` of ``crossbar_face`` of the piece ``crossbar`` against ``rail_face`` of the piece ``rail``, in
    the coordinates of the container of ``crossbar``."""
    crossbar_profile, rail_profile = base_profile(crossbar), base_profile(rail)
    if crossbar_profile is None or rail_profile is None:
        raise _no_faces(names)
    t_c, t_r = _thickness(crossbar_profile, names), _thickness(rail_profile, names)
    rail_face = in_frame_of(crossbar, rail, rail_face)
    rail_normal = face_normal(rail_face)
    # A profile is its section swept along the Z axis of its placement.
    axis = crossbar_profile.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    if abs(face_normal(crossbar_face).dot(axis)) > WALL_TOLERANCE:
        raise InterlockError(
            translate(
                "MaxProFrame", "There is no T joint between {} and {}: the face of {crossbar} is not a wall along it."
            ).format(*names, crossbar=names[0])
        )
    direction = -axis if axis.dot(rail_normal) > 0 else axis
    _check_bar_end(names, crossbar, crossbar_profile, direction)
    end = _end_plane(crossbar, rail_profile, rail_face, direction)
    return TJoint(names, crossbar_face, t_c, direction, rail_face, t_r, end)


def _check_bar_end(names, crossbar, profile, direction):
    """Raise InterlockError when a Folded Bar folds the tube ``profile`` of ``crossbar`` and its end toward the rail
    (along ``direction``, in the coordinates of the container of ``profile``) is no free end of the bar: a folded
    corner, or the open corner of a closed frame. A bar that does not fold says why itself."""
    bar = folding_bar(crossbar)
    if bar is None:
        return
    try:
        chain = bar_chain(bar)
    except ChainError:
        return
    index = next((i for i, segment in enumerate(chain.segments) if segment.profile.Name == profile.Name), None)
    if index is None:
        return
    toward = container_placement(profile).Rotation.multVec(direction)
    # The tabs at the end of the segment or at its start: an end of the bar, or a folded corner.
    bar_end = index == len(chain.segments) - 1 if toward.dot(chain.segments[index].direction) > 0 else index == 0
    if bar_end and not chain.closed:
        return
    if bar_end:
        text = translate(
            "MaxProFrame",
            "The T joint between {} and {} is at the open corner of {}: the tabs go on a free end of a Folded Bar.",
        )
    else:
        text = translate(
            "MaxProFrame",
            "The T joint between {} and {} is at a folded corner of {}: the tabs go on a free end of a Folded Bar.",
        )
    raise InterlockError(text.format(*names, bar.Label))


def _side(obj, side):
    """(piece, face name, (point, normal, anchor)) of the ``side`` (Crossbar or Rail) of the Tabs Interlock ``obj``."""
    link = getattr(obj, f"{side}Face")
    piece, subs = link if link else (None, ())
    sub = subs[0] if subs else ""
    return piece, sub, tuple(getattr(obj, f"{side}{name}") for name in ("Point", "Normal", "Anchor"))


def interlock_joint(obj):
    """The ``TJoint`` of the Tabs Interlock ``obj``, in the coordinates of the container of its crossbar piece.

    Raises InterlockError when a face it was made on is gone, and as ``_joint``.
    """
    faces = []
    for side in TAB_SIDES:
        piece, sub, snapshot = _side(obj, side)
        found = found_face(piece, sub, *snapshot) if _alive(piece) else None
        if found is None:
            raise InterlockError(
                translate("MaxProFrame", "The interlock {} lost the face of {} it was made on.").format(
                    obj.Label, getattr(piece, "Label", side)
                )
            )
        faces.append((piece, found[1]))
    (crossbar, crossbar_face), (rail, rail_face) = faces
    return _joint(_names(crossbar, rail), crossbar, crossbar_face, rail, rail_face)


def interlock_shapes(obj):
    """(``TJoint``, ``TabShapes``) of the Tabs Interlock ``obj``, in the coordinates of its crossbar piece."""
    joint = interlock_joint(obj)
    return joint, make_tabs(interlock_settings(obj), joint)


def tab_pieces(obj):
    """(tabs piece, slots piece) of the Tabs Interlock ``obj``; None for one it has not got."""
    pieces = {piece.InterlockRole: piece for piece in interlock_pieces(obj)}
    return pieces.get(TABS_ROLE), pieces.get(SLOTS_ROLE)


# The pieces.


class _InterlockPiece(ExtrudedCutout):
    """A piece of a Tabs Interlock on top of ``baseObject``: a cutout without sketch nor pattern."""

    role = None

    def __init__(self, obj, interlock, base):
        super().__init__(obj, None, base)
        for name in ("Sketch", "ExtrusionLength", "CutType"):
            obj.setEditorMode(name, 2)
        obj.addProperty(
            "App::PropertyLinkGlobal",
            "Interlock",
            "Interlock",
            translate("App::Property", "The Tabs Interlock this piece adds its tabs or slots for"),
        )
        obj.setEditorMode("Interlock", 1)
        obj.addProperty("App::PropertyString", "InterlockRole", "Interlock", "Tabs or Slots")
        obj.InterlockRole = self.role
        obj.setEditorMode("InterlockRole", ["ReadOnly", "Hidden"])
        obj.Interlock = interlock

    def add_pattern_properties(self, obj):
        """None: the Interlock gives what the piece adds."""

    def onDocumentRestored(self, obj):
        restore_custom_profile_link(obj)

    def onChanged(self, fp, prop):
        """No cut type to show."""

    def execute(self, fp):
        """The piece under it with the tabs or the slots of its Interlock; with its shape when they are refused."""
        under = fp.baseObject[0] if fp.baseObject else None
        if under is None:
            return
        for child in get_childrens_from_extrudedcutout(under):
            if getattr(child, "ViewObject", None) is not None:
                child.ViewObject.Visibility = False
        made = None
        try:
            if fp.Interlock is not None:
                made = interlock_shapes(fp.Interlock)
        finally:
            fp.Shape = _uncut_shape(under.Shape) if made is None else self.shaped(fp, under, *made)
            self._update_structure_data(fp, under, made)

    def shaped(self, fp, under, joint, shapes):
        raise NotImplementedError

    def _update_structure_data(self, fp, under=None, made=None):
        """The profile data of a cutout; the length and cut angles of the piece under it."""
        super()._update_structure_data(fp)
        under = fp.baseObject[0] if under is None else under
        fp.Length = under.Length.Value
        fp.CuttingAngleA, fp.CuttingAngleB = under.CuttingAngleA, under.CuttingAngleB

    def unsetupObject(self, fp):
        """The piece leaves the document (not by undo): the piece under it is given back."""
        give_back(fp)


class TabPiece(_InterlockPiece):
    """The crossbar piece with the tabs of its Interlock (_Tb)."""

    role = TABS_ROLE

    def shaped(self, fp, under, joint, shapes):
        return under.Shape.fuse(shapes.tabs).removeSplitter()

    def _update_structure_data(self, fp, under=None, made=None):
        """S6: as long as the piece under it, plus how far the tab tips reach past its end along the crossbar axis."""
        super()._update_structure_data(fp, under, made)
        under = fp.baseObject[0] if under is None else under
        fp.Cutout = bool(under.Cutout)
        if made is None:
            return
        joint, shapes = made
        reach = along_extent(Part.Compound(shapes.tabs), joint.direction)[1]
        reach -= along_extent(under.Shape, joint.direction)[1]
        fp.Length = under.Length.Value + max(reach, 0.0)


class SlotPiece(_InterlockPiece):
    """The rail piece with the slots of its Interlock (_Sl): a piece with a cutout."""

    role = SLOTS_ROLE

    def shaped(self, fp, under, joint, shapes):
        crossbar = fp.Interlock.CrossbarFace[0]
        return under.Shape.cut(in_frame_of(under, crossbar, Part.Compound(shapes.slots)))

    def _update_structure_data(self, fp, under=None, made=None):
        super()._update_structure_data(fp, under, made)
        fp.Cutout = True


class ViewProviderInterlockPiece(ViewProviderExtrudedCutout):
    icon = "Interlock.svg"

    def claimChildren(self):
        """The piece under it, hidden; the tabs piece shows its Interlock too."""
        obj = self.Object
        base = obj.baseObject[0] if obj.baseObject else None
        if base is not None and getattr(base, "ViewObject", None) is not None:
            base.ViewObject.Visibility = False
        children = [base] if base is not None else []
        if obj.InterlockRole == TABS_ROLE and obj.Interlock is not None:
            children.append(obj.Interlock)
        return children

    def onDelete(self, vobj, sub):
        """The piece under it is given back as it leaves the document (``give_back``)."""
        return True

    def doubleClicked(self, vobj):
        """Edit the Interlock of the piece."""
        interlock = vobj.Object.Interlock
        if interlock is None or getattr(interlock, "ViewObject", None) is None:
            return False
        return interlock.ViewObject.Proxy.doubleClicked(interlock.ViewObject)

    def setEdit(self, vobj, mode):
        """Nothing of its own to edit: its Interlock holds the settings."""
        return None if mode != 0 else False

    def setupContextMenu(self, vobj, menu):
        """No sketch to edit."""

    def getIcon(self):
        return os.path.join(ICONPATH, self.icon)


class ViewProviderTabPiece(ViewProviderInterlockPiece):
    icon = "interlock-tabs.svg"


class ViewProviderSlotPiece(ViewProviderInterlockPiece):
    icon = "interlock-slots.svg"


# Giving the piece under back.


def _matching(old, sub, new):
    """The name of the element of ``new`` where the element ``sub`` of ``old`` is; ``sub`` when there is none."""
    name = (sub or "").removeprefix(MISSING_ELEMENT_PREFIX)
    for prefix, elements in (("Face", "Faces"), ("Edge", "Edges"), ("Vertex", "Vertexes")):
        if name.startswith(prefix):
            break
    else:
        return sub
    element = _element(getattr(old.Shape, elements), name, prefix)
    if element is None:
        return sub
    at = element.Point if prefix == "Vertex" else element.CenterOfMass
    candidates = list(enumerate(getattr(new.Shape, elements), 1))
    if prefix == "Face" and isinstance(element.Surface, Part.Plane):
        normal = face_normal(element)
        candidates = [(index, face) for index, face in candidates if _on_plane(face, normal, at)]
    found = [(item.distToShape(Part.Vertex(at))[0], index) for index, item in candidates]
    found = [(distance, index) for distance, index in found if distance <= ELEMENT_TOLERANCE or prefix == "Face"]
    return f"{prefix}{min(found)[1]}" if found else sub


def _relinked(value, kind, old, new):
    """The value ``value`` of a link property of type ``kind`` with ``new`` where it links ``old``; None if it does not."""
    if value is None:
        return None
    if "LinkSubList" in kind:
        if not any(item[0] == old for item in value):
            return None
        return [
            (new, tuple(_matching(old, sub, new) for sub in subs)) if target == old else (target, subs)
            for target, subs in (
                (item[0], (item[1],) if isinstance(item[1], str) else tuple(item[1])) for item in value
            )
        ]
    if "LinkSub" in kind:
        target, subs = value
        if target != old:
            return None
        return (new, tuple(_matching(old, sub, new) for sub in ((subs,) if isinstance(subs, str) else subs)))
    if "LinkList" in kind:
        return [new if item == old else item for item in value] if old in value else None
    return new if value == old else None


def give_back(piece):
    """Before ``piece`` leaves the document: whatever links it (a cutout, drill hole or trim built on it, a target, a
    Folded Bar, another Tabs Interlock) links the piece under it instead, on the same faces, edges and vertices; the
    piece under it shows again unless something is built on it. Containers keep their own membership."""
    stack = list(piece_stack(piece))
    if len(stack) < 2 or not _alive(stack[1]):
        return
    under = stack[1]
    from freecad.maxproframe.folded_bar import release_piece

    release_piece(piece)
    for user in list(piece.InList):
        if user == piece or not _alive(user) or user.hasExtension("App::GroupExtension"):
            continue
        vertex = getattr(user, "ReferenceVertex", None) if "ReferenceVertex" in user.PropertiesList else None
        for prop in user.PropertiesList:
            kind = user.getTypeIdOfProperty(prop)
            if not kind.startswith("App::PropertyLink") or prop == "ExpressionEngine":
                continue
            value = _relinked(getattr(user, prop), kind, piece, under)
            if value is None:
                continue
            if prop == "baseObject" and vertex:
                # A Drill Hole keeps its reference vertex where it is.
                user.ReferenceVertex = _matching(piece, vertex, under)
            setattr(user, prop, value)
    _show_unless_built_on(under, piece)


# Creation.


def _pick(clicked, sub, newest, names):
    """(face name on ``newest``, face, snapshot) of the face ``sub`` of the piece ``clicked``, found on its newest
    piece ``newest``."""
    face = _flat_face(clicked, sub)
    if face is None:
        raise _no_faces(names)
    snapshot = face_snapshot(clicked, face)
    found = found_face(newest, sub if newest == clicked else "", *snapshot)
    if found is None:
        raise _no_faces(names)
    return found[0], found[1], face_snapshot(newest, found[1])


def _twin(crossbar_profile, rail_profile, crossbar_snapshot, rail_snapshot):
    """The Tabs Interlock already on the same two faces of the same two tubes, or None."""
    for obj in crossbar_profile.InList:
        if not is_interlock(obj) or str(obj.Kind) != TABS or obj.PieceA != crossbar_profile:
            continue
        if obj.PieceB != rail_profile:
            continue
        same = all(
            _same_plane(snapshot[:2], (getattr(obj, f"{side}Point"), getattr(obj, f"{side}Normal")))
            for side, snapshot in zip(TAB_SIDES, (crossbar_snapshot, rail_snapshot))
        )
        if same:
            return obj
    return None


def _make_piece(cls, view_provider, base, face, interlock, suffix):
    doc = base.Document
    obj = doc.addObject("Part::FeaturePython", f"{base.Name}{suffix}")
    obj.Label = f"{base.Label}{suffix}"
    # Before it links anything: a Part receiving it would pull in what it links.
    place_in_container_of(obj, base)
    cls(obj, interlock, (base, (face,)))
    if getattr(obj, "ViewObject", None) is not None:
        view_provider(obj.ViewObject)
    return obj


def _on_bar(piece, sub, point):
    """(piece, face name) a click on the face ``sub`` of ``piece`` at the global ``point`` stands for: on a Folded Bar,
    the tube under the point and its face (``folded_bar.segment_at``), else ``piece`` and ``sub``.

    Raises InterlockError with the reason of a click on a bend.
    """
    if piece is None or not is_foldedbar(piece):
        return piece, sub
    pick = segment_at(piece, sub, point)
    if pick.reason:
        raise InterlockError(pick.reason)
    return pick.tip, pick.face


def make_tab_interlock(
    crossbar_piece, crossbar_sub, rail_piece, rail_sub, crossbar_point=None, rail_point=None, **settings
):
    """A Tabs Interlock between the face ``crossbar_sub`` of ``crossbar_piece`` (the wall that carries the tabs) and
    the face ``rail_sub`` of ``rail_piece`` (the rail face the slots go through), with its _Tb and _Sl pieces.

    The faces are found on the newest piece of each tube, which the new pieces go on. A piece may be a Folded Bar: the
    face clicked on it, at the clicked global point ``crossbar_point`` or ``rail_point`` (the 3D view gives it; without
    it the center of the face), stands for the face of the tube of the bar under that point (``folded_bar.segment_at``).
    ``settings`` are by property name (``Count=3``, ``Length=3.0``: ``interlock.TAB_PROPERTIES``). Raises
    InterlockError, before anything is made, for a click on a bend of a bar, when the faces make no T joint the tabs
    fit (``tab_geometry.check``), when the crossbar is a tube of a Folded Bar and the joint is not at a free end of the
    bar, or when the two faces already have tabs. Run it in the caller's transaction and recompute the document
    afterwards: a bar folds the new pieces then.
    """
    unknown = sorted(set(settings) - set(TAB_PROPERTIES))
    if unknown:
        raise ValueError(f"Unknown tab settings: {', '.join(unknown)}; give {', '.join(TAB_PROPERTIES)}.")
    crossbar_piece, crossbar_sub = _on_bar(crossbar_piece, crossbar_sub, crossbar_point)
    rail_piece, rail_sub = _on_bar(rail_piece, rail_sub, rail_point)
    names = _names(crossbar_piece, rail_piece)
    crossbar_profile, rail_profile = base_profile(crossbar_piece), base_profile(rail_piece)
    if crossbar_profile is None or rail_profile is None or crossbar_profile.Name == rail_profile.Name:
        raise _no_faces(names)
    crossbar, rail = newest_piece(crossbar_piece), newest_piece(rail_piece)
    crossbar_name, crossbar_face, crossbar_snapshot = _pick(crossbar_piece, crossbar_sub, crossbar, names)
    rail_name, rail_face, rail_snapshot = _pick(rail_piece, rail_sub, rail, names)
    # Before the joint: the slots already there keep the same tabs off the rail face.
    twin = _twin(crossbar_profile, rail_profile, crossbar_snapshot, rail_snapshot)
    if twin is not None:
        raise InterlockError(
            translate("MaxProFrame", "The T joint between {} and {} already has tabs on that face: {}.").format(
                *names, twin.Label
            )
        )
    values = {TAB_PROPERTIES[name]: value for name, value in settings.items()}
    check(TabSettings(**values), _joint(names, crossbar, crossbar_face, rail, rail_face))

    doc = crossbar.Document
    obj = doc.addObject("App::FeaturePython", "Interlock")
    # Before it links anything: a Part receiving it would pull in what it links.
    place_in_container_of(obj, crossbar)
    Interlock(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderInterlock(obj.ViewObject)
    obj.Label = f"Interlock_{crossbar_profile.Label}_{rail_profile.Label}"
    obj.Kind = TABS
    obj.Count = DEFAULT_COUNT
    obj.PieceA, obj.PieceB = crossbar_profile, rail_profile
    for side, piece, name, snapshot in (
        ("Crossbar", crossbar, crossbar_name, crossbar_snapshot),
        ("Rail", rail, rail_name, rail_snapshot),
    ):
        setattr(obj, f"{side}Face", (piece, (name,)))
        for prop, value in zip(("Point", "Normal", "Anchor"), snapshot):
            setattr(obj, f"{side}{prop}", value)
    for name, value in settings.items():
        setattr(obj, name, value)
    _make_piece(TabPiece, ViewProviderTabPiece, crossbar, crossbar_name, obj, "_Tb")
    _make_piece(SlotPiece, ViewProviderSlotPiece, rail, rail_name, obj, "_Sl")
    return obj

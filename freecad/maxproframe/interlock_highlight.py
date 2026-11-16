"""Where an Interlock is: its two faces and its corner drawn over the 3D view (odd/tasks/interlock-highlight.md, T1:
S1-S5; D1, D2).

An Interlock has no shape of its own. ``InterlockOverlay`` draws, over the 3D view of its document, the face of its
first tube in orange and the face of the second in blue (the colors of Extend / Cut), and a mark in FreeCAD's
selection color at the inner vertex of the corner or where the crossbar wall meets the rail face (``drawing``). The
first tube is the one that owns the first finger, Flip included, or the crossbar that carries the tabs. Every kind:
Fingers at a folded corner (the inner walls on the bar, ``create_interlock_tool.corner_faces``), Fingers at an End
Miter corner (``miter_finger_interlock.interlock_faces``) and Tabs at a T joint (``tab_interlock.tab_faces``).

The overlay is a Coin annotation added to the scene graph, as the Extend / Cut and Folded Bar panels draw theirs
(``create_end_miter_tool.remove_overlay``): no document object, nothing saved, nothing for TechDraw, the selection
and the view objects untouched (S3, S5).

The Interlock panel draws it for the Interlock it makes or edits (S2). ``TreeSelection``, one selection observer added
once, draws it while exactly one Interlock is selected and no Interlock panel is open, and removes it as soon as that
is no longer so (S3). It draws from the event loop, never inside FreeCAD's selection observer dispatch, and waits while
a document recomputes (odd/tasks/panel-recompute-deadlock.md, S3).
"""

from collections import namedtuple

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, marker_group, remove_overlay, scene_graph
from freecad.maxproframe.create_extend_cut_tool import HIGHLIGHT_COLORS, PROFILE, TARGET
from freecad.maxproframe.create_folded_bar_tool import _overlay_group, selection_color
from freecad.maxproframe.interlock import is_interlock, is_miter_interlock, on_folded_corner
from freecad.maxproframe.interlock_geometry import FINGERS, TABS
from freecad.maxproframe.profile_pattern import container_placement, placed
from freecad.maxproframe.trimmed_profile import face_normal

# The face of the first tube and of the second: the target and the profile of Extend / Cut.
FIRST_COLOR = HIGHLIGHT_COLORS[TARGET]
SECOND_COLOR = HIGHLIGHT_COLORS[PROFILE]
# Pixels across the mark of the corner or the T joint.
MARK_SIZE = 11
# Below this length of the cross product of their normals two faces are parallel: no line where they meet.
PARALLEL = 1e-9

Drawing = namedtuple("Drawing", "first second mark")
Drawing.__doc__ = """What the overlay of an Interlock shows, global: the faces of the ``first`` tube (it owns the first
finger, or carries the tabs) and of the ``second`` one, each a list of faces, and the ``mark`` point of the corner or
the T joint (None when a face is lost)."""


def _alive(obj):
    try:
        return obj is not None and obj.Document is not None and obj.Document.getObject(obj.Name) is obj
    except Exception:
        return False


def _sides(obj):
    """((piece, [global faces]) of tube A, of tube B) of the Interlock ``obj``, or None."""
    if is_miter_interlock(obj) or str(obj.Kind) == TABS:
        if is_miter_interlock(obj):
            from freecad.maxproframe.miter_finger_interlock import interlock_faces as found
        else:
            from freecad.maxproframe.tab_interlock import tab_faces as found
        return tuple((piece, [placed(face, container_placement(piece))]) for piece, face in found(obj))
    if on_folded_corner(obj):
        from freecad.maxproframe.create_interlock_tool import corner_faces

        return corner_faces(obj)
    return None


def _center(faces):
    return sum((face.CenterOfMass for face in faces), App.Vector()) * (1.0 / len(faces))


def _plane(faces):
    """(point, normal) of the largest of ``faces``."""
    face = max(faces, key=lambda item: item.Area)
    return face.CenterOfMass, face_normal(face)


def meeting_point(first, second, near):
    """The point of the line where the planes ``first`` and ``second`` ((point, normal)) meet that is nearest to
    ``near``; ``near`` for parallel planes."""
    (p1, n1), (p2, n2) = first, second
    line = n1.cross(n2)
    square = line.dot(line)
    if square < PARALLEL:
        return App.Vector(near)
    # The point of both planes nearest the origin plus the line through it.
    on_line = (n2.cross(line) * n1.dot(p1) + line.cross(n1) * n2.dot(p2)) * (1.0 / square)
    return on_line + line * ((near - on_line).dot(line) / square)


def drawing(obj):
    """The ``Drawing`` of the Interlock ``obj``, or None when it has no face to show.

    The first tube is tube A (``PieceA``: before the folded corner, the first face clicked at an End Miter corner, the
    crossbar of Tabs), swapped by Flip for Fingers. The mark is at the inner vertex of the corner, midway across the
    two inner walls, or where the crossbar wall meets the rail face, at the middle of that wall.
    """
    if not _alive(obj) or not is_interlock(obj):
        return None
    try:
        sides = _sides(obj)
    except Exception:
        # A face lost or a bar in error: the overlay never breaks the panel nor the selection.
        return None
    if sides is None:
        return None
    (_, faces_a), (_, faces_b) = sides
    mark = None
    if faces_a and faces_b:
        if str(obj.Kind) == TABS:
            near = _center(faces_a)
        else:
            near = (_center(faces_a) + _center(faces_b)) * 0.5
        mark = meeting_point(_plane(faces_a), _plane(faces_b), near)
    if str(obj.Kind) == FINGERS and bool(getattr(obj, "Flip", False)):
        faces_a, faces_b = faces_b, faces_a
    if not faces_a and not faces_b:
        return None
    return Drawing(faces_a, faces_b, mark)


class InterlockOverlay:
    """The overlay of one Interlock over the 3D view of its document: ``show`` draws it in place of the one drawn
    before, ``remove`` takes it away."""

    def __init__(self):
        self._overlay = None
        self.obj = None

    @property
    def node(self):
        """The Coin node drawn, or None."""
        return None if self._overlay is None else self._overlay[1]

    def remove(self):
        remove_overlay(self._overlay)
        self._overlay = None
        self.obj = None

    def show(self, obj):
        """Draw the Interlock ``obj`` (None: nothing); no 3D view (another view type) draws nothing."""
        self.remove()
        drawn = drawing(obj) if obj is not None else None
        scene = scene_graph(obj.Document) if drawn is not None else None
        if scene is None:
            return
        import Part
        from pivy import coin

        # An annotation is drawn over the shapes: the faces stay visible inside the tubes.
        node = coin.SoAnnotation()
        for faces, color in ((drawn.first, FIRST_COLOR), (drawn.second, SECOND_COLOR)):
            if faces:
                node.addChild(_overlay_group(Part.Compound(faces), color))
        if drawn.mark is not None:
            node.addChild(marker_group([drawn.mark], selection_color(), MARK_SIZE))
        scene.addChild(node)
        self._overlay = (scene, node)
        self.obj = obj


# The Interlock panels open: while one is, the tree selection draws nothing (the panel draws its own).
_PANELS = []


def panel_opened(panel):
    if panel not in _PANELS:
        _PANELS.append(panel)
    TREE_SELECTION.later()


def panel_closed(panel):
    if panel in _PANELS:
        _PANELS.remove(panel)
    TREE_SELECTION.later()


def _panel_open():
    """Whether an Interlock panel is shown: one opened and not closed, while FreeCAD shows a task dialog."""
    _PANELS[:] = [panel for panel in _PANELS if not getattr(panel, "_closed", False)]
    return bool(_PANELS) and bool(Gui.Control.activeDialog())


def _recomputing():
    return any(getattr(doc, "Recomputing", False) for doc in App.listDocuments().values())


def selected_interlock():
    """The Interlock selected when it is the only object selected, in any document; else None."""
    try:
        selection = Gui.Selection.getSelection("*")
    except Exception:
        return None
    if len(selection) != 1 or not is_interlock(selection[0]):
        return None
    return selection[0]


class TreeSelection:
    """Selection observer: the overlay of the Interlock selected alone, by the tree or a click, while no Interlock
    panel is open (S3); gone once it is deselected, the selection cleared, it is deleted or its document closes.

    It only reads the selection; the overlay is drawn later, from the event loop (never during FreeCAD's selection
    observer dispatch), and waits while a document recomputes."""

    def __init__(self):
        self.overlay = InterlockOverlay()
        self._scheduled = False

    def addSelection(self, doc, obj, sub, point=None):
        self.later()

    def removeSelection(self, doc, obj, sub):
        self.later()

    def setSelection(self, doc):
        self.later()

    def clearSelection(self, doc):
        self.later()

    def later(self, delay=0):
        if not self._scheduled:
            self._scheduled = True
            QtCore.QTimer.singleShot(delay, self.refresh)

    def refresh(self):
        self._scheduled = False
        if _recomputing():
            self.later(GAP_DELAY_MS)
            return
        obj = selected_interlock()
        if obj is None or _panel_open():
            self.overlay.remove()
            return
        self.overlay.show(obj)


if "TREE_SELECTION" not in globals():
    TREE_SELECTION = TreeSelection()
    Gui.Selection.addObserver(TREE_SELECTION)

"""Where an Interlock is, drawn over the 3D view (odd/tasks/interlock-highlight.md, T1: S1-S5; D1, D2).

An Interlock has no shape: selecting it alone in the tree draws its two faces over the 3D view, the first tube's in
orange and the second's in blue (the colors of Extend / Cut; for Tabs the rail face orange, as the target of Extend /
Cut, and the crossbar wall blue: L5), and a mark in the selection color at the inner vertex of its corner or where the
crossbar wall meets the rail face; for every kind: Fingers at a folded corner, Fingers at an
End Miter corner, Tabs at a T joint (S1, S3, S4). Deselecting it, clearing the selection, deleting it or closing its
document takes the drawing away; a recompute draws it again, so a property changed in the property editor shows (L5).
Each test starts and ends with no task dialog, no selection, no refresh waiting and no overlay (L4). The selection and the visibility of every object stay as they are, and nothing goes
into the document (S3, S5). The Interlock panel draws the same while it makes or edits one, Flip swapping the colors;
OK, Cancel and Apply and continue take it away (S2). No geometry while a recompute runs (D2).
"""

from unittest.mock import call, patch

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin
from PySide import QtCore, QtWidgets
from test_extend_cut_preview import scene_graph
from test_folded_bar_tools import face_at
from test_interlock_panel import BOTTOM_INNER, RIGHT_INNER
from test_miter_finger_panel import A_INNER, B_INNER, MiterPanelFixture
from test_recompute_gate import during, hook_execute, watch
from test_tab_interlock_panel import CROSS_EAST, RAIL_TOP
from test_unfolded_geometry import PLAIN

from freecad.maxproframe import create_interlock_tool, interlock_highlight
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS
from freecad.maxproframe.create_folded_bar_tool import selection_color
from freecad.maxproframe.interlock import make_interlock
from freecad.maxproframe.miter_finger_interlock import MiterFace, make_miter_fingers, miter_pieces
from freecad.maxproframe.profile_pattern import newest_piece
from freecad.maxproframe.tab_interlock import TabPiece, make_tab_interlock, tab_pieces

ORANGE = (1.0, 0.5, 0.0)
BLUE = (0.0, 0.4, 1.0)
TOLERANCE = 1e-3
# The inner vertex of the folded corner between the bottom and the right tube of the rectangle (inner walls y = 25 and
# x = 275), midway across the 50 mm tubes.
FOLDED_VERTEX = App.Vector(275, 25, 0)
# The inner vertex of the straight End Miter corner (A's inner wall y = -575, B's x = -25).
MITER_VERTEX = App.Vector(-25, -575, 0)
# Where the east wall of the crossbar (x = 175) meets the top face of the rail (y = -500).
T_JOINT = App.Vector(175, -500, 0)


def _children(node, kind):
    return [node.getChild(index) for index in range(node.getNumChildren()) if node.getChild(index).isOfType(kind)]


def _points(group):
    (coordinates,) = _children(group, coin.SoCoordinate3.getClassTypeId())
    return [App.Vector(*coordinates.point[i].getValue()) for i in range(coordinates.point.getNum())]


def _rounded(color):
    return tuple(round(value, 3) for value in color)


def drawn_faces(node):
    """[(color, points)] of the faces the overlay ``node`` draws, in order."""
    found = []
    for group in _children(node, coin.SoSeparator.getClassTypeId()):
        materials = _children(group, coin.SoMaterial.getClassTypeId())
        if materials:
            found.append((_rounded(materials[0].diffuseColor[0].getValue()), _points(group)))
    return found


def drawn_marks(node):
    """[(color, points)] of the marks the overlay ``node`` draws."""
    found = []
    for group in _children(node, coin.SoSeparator.getClassTypeId()):
        if _children(group, coin.SoMarkerSet.getClassTypeId()):
            (color,) = _children(group, coin.SoBaseColor.getClassTypeId())
            found.append((_rounded(color.rgb[0].getValue()), _points(group)))
    return found


class HighlightFixture(MiterPanelFixture):
    def setUp(self):
        super().setUp()
        # Self-contained (L4): no task dialog nor selection an earlier test left, no tree refresh waiting.
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        self.settle()
        self.addCleanup(self.assertNothingLeft)

    def settle(self):
        """Process events until no tree refresh waits."""
        self.events()
        self.assertTrue(self.wait_for(lambda: not interlock_highlight.TREE_SELECTION.pending()))

    def assertNothingLeft(self):
        """At the end of a test: with nothing selected and no panel, no overlay is drawn (S5)."""
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        self.settle()
        self.assertIsNone(interlock_highlight.TREE_SELECTION.overlay.node)

    # The three kinds.

    def folded(self, **values):
        """(bottom, right, bar, Interlock at their folded corner)."""
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        made = make_interlock(bar, bottom, right, **values)
        self.doc.recompute()
        self.assertEqual("Valid", bar.getStatusString())
        return bottom, right, bar, made

    def miter(self):
        """(miter of A, miter of B, Interlock at their End Miter corner)."""
        _, _, miter_a, miter_b = self.straight_corner()
        made = make_miter_fingers(
            MiterFace(miter_a, face_at(miter_a, A_INNER), None), MiterFace(miter_b, face_at(miter_b, B_INNER), None)
        )
        self.doc.recompute()
        return miter_a, miter_b, made

    def tabs(self):
        """(rail, crossbar profile, its trim, Tabs Interlock on the crossbar's east wall against the rail top)."""
        rail, crossbar, trim = self.straight_t()
        made = make_tab_interlock(trim, face_at(trim, CROSS_EAST), rail, face_at(rail, RAIL_TOP))
        self.doc.recompute()
        return rail, crossbar, trim, made

    # The 3D view, the selection and the document.

    def scene(self):
        """(scene graph of the 3D view, its number of children now): an overlay added later is the next child."""
        scene = scene_graph(self, self.doc)
        return scene, scene.getNumChildren()

    def overlay(self, scene, children):
        """The overlay drawn over the 3D view since ``children`` were counted, or None: one at most."""
        self.assertIn(scene.getNumChildren(), (children, children + 1))
        if scene.getNumChildren() == children:
            return None
        node = scene.getChild(children)
        # An annotation is drawn over the shapes: always visible.
        self.assertEqual("Annotation", node.getTypeId().getName())
        return node

    def state(self):
        """What the overlay must not change: the selection, every visibility, the objects and the Undo steps."""
        return (
            [(item.ObjectName, tuple(item.SubElementNames)) for item in Gui.Selection.getSelectionEx(self.doc.Name)],
            {obj.Name: obj.ViewObject.Visibility for obj in self.doc.Objects},
            sorted(obj.Name for obj in self.doc.Objects),
            list(self.doc.UndoNames),
        )

    def tree_select(self, obj):
        """Select ``obj`` alone, as a click on it in the tree does."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name)
        self.events()

    def assertOnPlane(self, points, axis, value):
        """Every point of ``points`` has the coordinate ``axis`` (x, y or z) at ``value``."""
        self.assertTrue(points)
        self.assertTrue(all(abs(getattr(point, axis) - value) < TOLERANCE for point in points), (axis, value))

    def assertDrawn(self, node, first, second, mark):
        """``node`` draws the face of the first tube in orange on the plane ``first`` ((axis, value)), the second's in
        blue on ``second`` and one mark at ``mark`` in the selection color."""
        self.assertIsNotNone(node)
        (orange, orange_points), (blue, blue_points) = drawn_faces(node)
        self.assertEqual((ORANGE, BLUE), (orange, blue))
        self.assertOnPlane(orange_points, *first)
        self.assertOnPlane(blue_points, *second)
        ((color, (point,)),) = drawn_marks(node)
        self.assertEqual(_rounded(selection_color()), color)
        self.assertLess(point.distanceToPoint(mark), TOLERANCE)

    def delete_selected(self):
        """Std_Delete, as the Delete key runs it, answering Yes to FreeCAD's question about dependent objects."""

        def answer():
            box = QtWidgets.QApplication.activeModalWidget()
            if isinstance(box, QtWidgets.QMessageBox):
                button = box.button(QtWidgets.QMessageBox.Yes)
                (button or box.defaultButton()).click()

        timer = QtCore.QTimer()
        timer.timeout.connect(answer)
        timer.start(50)
        try:
            Gui.runCommand("Std_Delete")
            self.events()
        finally:
            timer.stop()


class TreeSelectionTest(HighlightFixture):
    def test_a_folded_corner_interlock_selected_in_the_tree_shows_its_faces_and_corner(self):
        bottom, right, bar, made = self.folded()
        scene, children = self.scene()

        self.tree_select(made)
        before = self.state()
        self.events()

        # S1, S4: bottom (before the corner) owns the first finger: its inner wall in orange, the right one's in blue.
        self.assertDrawn(self.overlay(scene, children), ("y", 25.0), ("x", 275.0), FOLDED_VERTEX)
        # S3, S5: the selection, the visibilities and the document as they were.
        self.assertEqual(before, self.state())
        self.assertEqual([(made.Name, ())], before[0])

        Gui.Selection.clearSelection()
        self.events()
        self.assertIsNone(self.overlay(scene, children))
        self.assertEqual(before[1:], self.state()[1:])

    def test_flip_swaps_the_colors_of_the_tree_overlay(self):
        _, _, _, made = self.folded(Flip=True)
        scene, children = self.scene()

        self.tree_select(made)

        self.assertDrawn(self.overlay(scene, children), ("x", 275.0), ("y", 25.0), FOLDED_VERTEX)

    def test_a_miter_corner_interlock_deselected_takes_its_overlay_away(self):
        _, _, made = self.miter()
        scene, children = self.scene()

        self.tree_select(made)
        before = self.state()

        self.assertDrawn(self.overlay(scene, children), ("y", -575.0), ("x", -25.0), MITER_VERTEX)
        self.assertEqual(before, self.state())

        Gui.Selection.removeSelection(self.doc.Name, made.Name)
        self.events()
        self.assertIsNone(self.overlay(scene, children))

    def test_a_tabs_interlock_shows_its_t_joint_and_delete_still_deletes_only_it(self):
        rail, crossbar, trim, made = self.tabs()
        tabs, slots = tab_pieces(made)
        scene, children = self.scene()

        self.tree_select(made)
        before = self.state()

        # The rail face in orange, as the target of Extend / Cut; the crossbar wall that carries the tabs in blue.
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)
        self.assertEqual(before, self.state())

        gone = {made.Name, tabs.Name, slots.Name}
        self.delete_selected()
        self.doc.recompute()
        self.events()

        # Only the Interlock and its pieces left; the pieces under them given back.
        self.assertEqual(sorted(set(before[2]) - gone), sorted(obj.Name for obj in self.doc.Objects))
        self.assertEqual(trim, newest_piece(crossbar))
        self.assertEqual(rail, newest_piece(rail))
        self.assertTrue(trim.ViewObject.Visibility)
        self.assertIsNone(self.overlay(scene, children))

    def test_only_an_interlock_selected_alone_shows(self):
        _, _, made = self.miter()
        piece_a, _ = miter_pieces(made)
        scene, children = self.scene()

        for selected in ((piece_a,), (made, piece_a)):
            with self.subTest(selected=[obj.Label for obj in selected]):
                Gui.Selection.clearSelection()
                for obj in selected:
                    Gui.Selection.addSelection(self.doc.Name, obj.Name)
                self.events()
                self.assertIsNone(self.overlay(scene, children))

    def test_closing_the_document_takes_the_overlay_away(self):
        _, _, made = self.miter()
        scene, children = self.scene()
        self.tree_select(made)
        self.assertIsNotNone(self.overlay(scene, children))
        tree = interlock_highlight.TREE_SELECTION.overlay
        self.assertIsNotNone(tree.node)

        name = self.doc.Name
        try:
            App.closeDocument(name)
            self.events()
            # The view goes with its scene; the overlay keeps nothing of it.
            self.assertIsNone(tree.node)
            self.assertIsNone(tree.obj)
        finally:
            # The fixture closes its document again at the end.
            self.doc = App.newDocument(name)
        self.assertEqual(name, self.doc.Name)

    def test_the_tree_overlay_waits_for_a_recompute_to_end(self):
        hooks, state = hook_execute(self, TabPiece)
        _, _, trim, made = self.tabs()
        scene, children = self.scene()
        calls = watch(self, interlock_highlight, ("drawing",), state)
        seen = {}

        def inside(fp):
            self.tree_select(made)
            self.wait_for(lambda: False, seconds=0.5)
            seen["children"] = scene.getNumChildren()

        hooks.append(inside)
        trim.touch()
        self.doc.recompute()

        self.assertEqual({"children": children}, seen)
        self.assertEqual([], during(calls))
        self.assertTrue(self.wait_for(lambda: scene.getNumChildren() == children + 1))
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)

    def test_flip_changed_while_selected_updates_the_tree_overlay(self):
        _, _, _, made = self.folded()
        scene, children = self.scene()
        self.tree_select(made)
        self.assertDrawn(self.overlay(scene, children), ("y", 25.0), ("x", 275.0), FOLDED_VERTEX)
        before = self.state()

        # L5: as the property editor does, then its recompute.
        made.Flip = True
        self.doc.recompute()
        self.events()

        self.assertDrawn(self.overlay(scene, children), ("x", 275.0), ("y", 25.0), FOLDED_VERTEX)
        self.assertEqual(before[:3], self.state()[:3])

    def test_a_tabs_setting_changed_while_selected_redraws_without_a_recompute_of_its_own(self):
        _, _, _, made = self.tabs()
        scene, children = self.scene()
        self.tree_select(made)
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)

        class Recomputes:
            count = 0

            def slotRecomputedDocument(self, doc):
                Recomputes.count += 1

        counter = Recomputes()
        App.addDocumentObserver(counter)
        self.addCleanup(App.removeDocumentObserver, counter)
        with patch.object(interlock_highlight, "drawing", wraps=interlock_highlight.drawing) as drawn:
            made.Count = 3
            self.doc.recompute()
            self.settle()

        # Drawn again once the recompute ended, one overlay, and the redraw recomputed nothing.
        self.assertEqual([call(made)], drawn.call_args_list)
        self.assertEqual(1, Recomputes.count)
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)

    def test_non_interlock_selections_draw_nothing(self):
        rail, crossbar, trim, made = self.tabs()
        tabs, _ = tab_pieces(made)
        sketch = rail.AttachmentSupport[0][0]
        scene, children = self.scene()

        for selected in (
            ((rail, ""),),
            ((trim, ""),),
            ((sketch, ""),),
            ((made, ""), (rail, "")),
            ((tabs, "Face1"),),
            ((tabs, "Edge1"),),
            ((tabs, "Vertex1"),),
        ):
            with self.subTest(selected=[(obj.Label, sub) for obj, sub in selected]):
                Gui.Selection.clearSelection()
                for obj, sub in selected:
                    Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
                self.events()
                self.assertIsNone(self.overlay(scene, children))

    def test_delete_then_undo_then_select_again(self):
        _, crossbar, trim, made = self.tabs()
        names = sorted(obj.Name for obj in self.doc.Objects)
        name = made.Name
        scene, children = self.scene()
        self.tree_select(made)
        self.assertIsNotNone(self.overlay(scene, children))

        self.delete_selected()
        self.doc.recompute()
        self.events()
        self.assertIsNone(self.doc.getObject(name))
        self.assertIsNone(self.overlay(scene, children))

        self.doc.undo()
        self.doc.recompute()
        self.events()
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))
        self.assertIsNone(self.overlay(scene, children))
        self.tree_select(self.doc.getObject(name))

        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)

    def test_a_selection_is_not_left_waiting_behind_a_refresh_for_a_recompute(self):
        # L4, the cause of the CI failures: a refresh run inside a recompute (FreeCAD pumps events there) waits for it
        # to end; a selection made meanwhile must not wait behind it.
        _, _, made = self.miter()
        scene, children = self.scene()
        interlock_highlight.TREE_SELECTION.later(GAP_DELAY_MS * 20)

        self.tree_select(made)

        self.assertDrawn(self.overlay(scene, children), ("y", -575.0), ("x", -25.0), MITER_VERTEX)

    def test_a_panel_never_shown_does_not_hide_the_tree_overlay(self):
        # L4: only an Interlock panel shown in the task view keeps the tree from drawing, not one built and dropped
        # while another task dialog is open.
        _, _, made = self.miter()
        scene, children = self.scene()
        dropped = create_interlock_tool.InterlockTaskPanel()
        self.addCleanup(dropped.clean)

        class Other:
            def __init__(self):
                self.form = QtWidgets.QWidget()

            def getStandardButtons(self):
                return QtWidgets.QDialogButtonBox.Close

        Gui.Control.showDialog(Other())
        self.events()
        self.assertTrue(Gui.Control.activeDialog())

        self.tree_select(made)

        self.assertDrawn(self.overlay(scene, children), ("y", -575.0), ("x", -25.0), MITER_VERTEX)
        Gui.Control.closeDialog()
        self.events()


class PanelOverlayTest(HighlightFixture):
    def test_editing_shows_the_overlay_flip_swaps_its_colors_and_ok_takes_it_away(self):
        _, _, _, made = self.folded()
        scene, children = self.scene()
        self.tree_select(made)
        self.assertIsNotNone(self.overlay(scene, children))

        panel = self.edit(made)
        self.events()

        # One overlay: the panel's (the tree draws none while an Interlock panel is open).
        node = self.overlay(scene, children)
        self.assertIsNotNone(panel._overlay.node)
        self.assertIsNone(interlock_highlight.TREE_SELECTION.overlay.node)
        self.assertDrawn(node, ("y", 25.0), ("x", 275.0), FOLDED_VERTEX)

        panel.form.cb_flip.setChecked(True)
        self.events()
        self.assertDrawn(self.overlay(scene, children), ("x", 275.0), ("y", 25.0), FOLDED_VERTEX)
        panel.form.spin_count.setValue(4)
        self.events()
        self.assertDrawn(self.overlay(scene, children), ("x", 275.0), ("y", 25.0), FOLDED_VERTEX)

        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertIsNone(self.overlay(scene, children))
        self.assertTrue(made.Flip)

    def test_editing_and_cancel_takes_the_overlay_away(self):
        _, _, made = self.miter()
        scene, children = self.scene()
        panel = self.edit(made)

        self.assertDrawn(self.overlay(scene, children), ("y", -575.0), ("x", -25.0), MITER_VERTEX)
        panel.form.cb_flip.setChecked(True)
        self.events()
        self.assertDrawn(self.overlay(scene, children), ("x", -25.0), ("y", -575.0), MITER_VERTEX)

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertIsNone(self.overlay(scene, children))
        self.assertFalse(made.Flip)

    def test_creating_shows_the_overlay_once_made_until_apply_and_continue_or_cancel(self):
        rail, _, trim = self.straight_t()
        scene, children = self.scene()

        panel = self.run_command((trim, CROSS_EAST))
        self.assertIsNone(self.overlay(scene, children))
        self.click(rail, RAIL_TOP)
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)

        self.apply()
        self.assertIsNone(self.overlay(scene, children))

        _, bar = self.make_bar(**PLAIN)
        names = sorted(obj.Name for obj in self.doc.Objects)
        self.click(bar, BOTTOM_INNER)
        self.click(bar, RIGHT_INNER)
        self.assertDrawn(self.overlay(scene, children), ("y", 25.0), ("x", 275.0), FOLDED_VERTEX)

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertIsNone(self.overlay(scene, children))
        # The first one kept by Apply and continue, nothing else left (S5).
        self.assertEqual(1, len(self.interlocks()))
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))

    def test_ok_after_creating_takes_the_overlay_away(self):
        _, _, miter_a, miter_b = self.straight_corner()
        scene, children = self.scene()

        panel = self.run_command((miter_a, A_INNER), (miter_b, B_INNER))
        self.assertDrawn(self.overlay(scene, children), ("y", -575.0), ("x", -25.0), MITER_VERTEX)

        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertIsNone(self.overlay(scene, children))

    def test_the_panel_overlay_waits_for_a_recompute_to_end(self):
        hooks, state = hook_execute(self, TabPiece)
        _, _, trim, made = self.tabs()
        scene, children = self.scene()
        panel = self.edit(made)
        self.assertIsNotNone(self.overlay(scene, children))
        calls = watch(self, interlock_highlight, ("drawing",), state)

        def inside(fp):
            panel._draw_overlay()
            self.wait_for(lambda: False, seconds=0.5)

        hooks.append(inside)
        trim.touch()
        self.doc.recompute()

        self.assertEqual([], during(calls))
        self.assertTrue(self.wait_for(lambda: bool(calls)))
        self.assertDrawn(self.overlay(scene, children), ("y", -500.0), ("x", 175.0), T_JOINT)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertIsNone(self.overlay(scene, children))

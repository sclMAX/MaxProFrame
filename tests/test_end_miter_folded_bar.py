"""End Miter on a Folded Bar (odd/tasks/folded-bar-tools.md, T2: S1, S4).

The layout is the user's (L1): a Folded Bar of three tubes (right, top, left) with the bottom tube loose. A click on
the bar in the End Miter panel lists the tube under the clicked point (its current piece, as a click on that tube
would), also when the bar is preselected before the command; the partners of a miter are tubes, never the bar. The
miters at the free ends of the bar show folded into the bar in the preview and stay after OK; a preview dropped while
the panel is open or a Cancel leaves the bar as before, never linking a removed object.
"""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import keep_auto_preview, use_language
from PySide import QtCore, QtWidgets
from test_folded_bar_tools import FoldedBarToolsFixture, face_at
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe import create_end_miter_tool
from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.folded_geometry import fold

LENGTH = 1e-6
# Near the bottom of the right and left legs, on the top wall: one face of the bar spans the three tubes there.
RIGHT_LEG = App.Vector(300, 20, 25)
LEFT_LEG = App.Vector(0, 20, 25)
# On the outer walls of the legs: a face of the bar on that tube only.
RIGHT_OUTER_WALL = App.Vector(325, 20, 0)
LEFT_OUTER_WALL = App.Vector(-25, 20, 0)


class EndMiterFoldedBarTest(FoldedBarToolsFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self.close_panels)
        (self.bottom, self.right, self.top, self.left), self.bar = self.make_legs()
        self.volume = self.bar.Shape.Volume

    def close_panels(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def events(self):
        QtWidgets.QApplication.processEvents()

    def open_panel(self, members=()):
        panel = create_end_miter_tool.EndMiterTaskPanel(members)
        self.panels.append(panel)
        Gui.Selection.addObserver(panel)
        return panel

    def run_command(self):
        created = []
        base = create_end_miter_tool.EndMiterTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_end_miter_tool, "EndMiterTaskPanel", Recording):
            create_end_miter_tool.CreateEndMiterCommand().Activated()
        self.panels.extend(created)
        self.assertEqual(1, len(created))
        return created[0]

    def select(self, obj, point=None):
        """Select ``obj`` as a click at the global ``point`` on it would (the whole object without a point)."""
        if point is None:
            Gui.Selection.addSelection(self.doc.Name, obj.Name)
        else:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, face_at(obj, point), point.x, point.y, point.z)

    def click(self, obj, point=None, ctrl=False):
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            self.select(obj, point)
            self.events()

    def trims(self):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "End Miter"]

    def trim_of(self, body):
        found = [obj for obj in self.trims() if obj.TrimmedBody == body]
        self.assertEqual(1, len(found), body.Label)
        return found[0]

    @staticmethod
    def boundaries(trim):
        return {link[0] for link in trim.TrimmingBoundary}

    def listed(self, panel):
        return [panel.form.members_list.item(row).text() for row in range(panel.form.members_list.count())]

    def assertListed(self, members, panel):
        self.assertEqual(members, panel.members)
        self.assertEqual([f"{obj.Label} ({obj.Name})" for obj in members], self.listed(panel))

    def assertBarFolds(self, segments):
        """The bar folds ``segments`` now, as one valid solid, without a manual recompute, and hides them."""
        bar = self.bar
        self.assertEqual(segments, list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertNotIn("Touched", bar.State)
        self.assertSameVolume(fold(build_chain(segments), bend(**PLAIN)), bar.Shape)
        for piece in segments + [self.right, self.left]:
            self.assertFalse(piece.Visibility, piece.Label)

    def assertBothEndsMitered(self):
        """Both free ends of the bar are mitered against the bottom tube: the bar reaches its outside."""
        right_miter, left_miter = self.trim_of(self.right), self.trim_of(self.left)
        for miter in (right_miter, left_miter):
            self.assertEqual("Valid", miter.getStatusString())
            # The partner is the loose tube, never the bar.
            self.assertEqual({self.bottom}, self.boundaries(miter))
        self.assertEqual({self.right, self.left}, self.boundaries(self.trim_of(self.bottom)))
        self.assertBarFolds([right_miter, self.top, left_miter])
        self.assertAlmostEqual(-25.0, self.bar.Shape.BoundBox.YMin, delta=LENGTH)
        return right_miter, left_miter

    def assertBarAsBefore(self):
        self.assertEqual([], self.trims())
        self.assertBarFolds([self.right, self.top, self.left])
        self.assertAlmostEqual(self.volume, self.bar.Shape.Volume, delta=1e-3)
        self.assertAlmostEqual(0.0, self.bar.Shape.BoundBox.YMin, delta=LENGTH)

    def test_clicks_on_both_legs_of_the_bar_list_their_tubes_and_the_preview_miters_both_free_ends(self):
        panel = self.open_panel([self.bottom])

        self.click(self.bar, RIGHT_LEG)
        self.click(self.bar, LEFT_LEG)

        self.assertListed([self.bottom, self.right, self.left], panel)
        self.assertEqual("2 joints will be created.", panel.form.message_label.text())
        self.assertEqual("Preview updated", panel.form.status_label.text())
        self.assertBothEndsMitered()

    def test_a_click_on_a_bend_of_the_bar_lists_the_nearest_tube(self):
        panel = self.open_panel([self.bottom])

        self.click(self.bar, self.bend_point(self.bar, 20.0))

        self.assertListed([self.bottom, self.right], panel)

    def test_ok_keeps_the_miters_folded_into_the_bar(self):
        panel = self.open_panel([self.bottom])
        self.click(self.bar, RIGHT_LEG)
        self.click(self.bar, LEFT_LEG)

        self.assertTrue(panel.accept())
        self.doc.recompute()

        self.assertBothEndsMitered()

    def test_ok_without_a_preview_folds_the_miters_into_the_bar(self):
        panel = self.open_panel([self.bottom])
        panel.form.cb_auto_update.setChecked(False)
        self.click(self.bar, RIGHT_LEG)
        self.click(self.bar, LEFT_LEG)
        self.assertEqual([], self.trims())

        self.assertTrue(panel.accept())

        self.assertBothEndsMitered()

    def test_undo_after_ok_gives_the_bar_its_tubes_back_and_redo_the_miters(self):
        for auto in (True, False):
            with self.subTest(auto_preview=auto):
                self.assertBarAsBefore()
                panel = self.open_panel([self.bottom])
                panel.form.cb_auto_update.setChecked(auto)
                self.click(self.bar, RIGHT_LEG)
                self.click(self.bar, LEFT_LEG)
                self.assertTrue(panel.accept())
                self.assertBothEndsMitered()

                self.doc.undo()
                self.doc.recompute()
                self.assertBarAsBefore()

                self.doc.redo()
                self.doc.recompute()
                self.assertBothEndsMitered()

                # The next round starts from the bar as before.
                self.doc.undo()
                self.doc.recompute()

    def test_a_click_on_a_mitered_end_of_the_bar_stands_for_its_tube(self):
        panel = self.open_panel([self.bottom])
        self.click(self.bar, RIGHT_LEG)
        self.click(self.bar, LEFT_LEG)
        miters = self.assertBothEndsMitered()

        # The bar now folds the preview miter there: clicking it again adds nothing new.
        self.click(self.bar, RIGHT_LEG)

        self.assertListed([self.bottom, self.right, self.left], panel)
        self.assertEqual(list(miters), [self.trim_of(self.right), self.trim_of(self.left)])

    def test_removing_one_leg_while_the_panel_is_open_leaves_the_bar_folding_its_tube(self):
        panel = self.open_panel([self.bottom])
        self.click(self.bar, RIGHT_LEG)
        self.click(self.bar, LEFT_LEG)
        _, left_miter = self.assertBothEndsMitered()

        self.click(self.bar, RIGHT_LEG, ctrl=True)

        self.assertListed([self.bottom, self.left], panel)
        self.assertEqual({self.bottom, self.left}, {miter.TrimmedBody for miter in self.trims()})
        self.assertEqual({self.left}, self.boundaries(self.trim_of(self.bottom)))
        # The bar folds the right tube again (its end at the path), the left miter still.
        self.assertBarFolds([self.right, self.top, left_miter])
        self.assertAlmostEqual(-25.0, self.bar.Shape.BoundBox.YMin, delta=LENGTH)

    def test_deselecting_a_clicked_face_of_the_bar_drops_its_tube(self):
        panel = self.open_panel([self.bottom])
        panel.form.cb_auto_update.setChecked(False)

        self.select(self.bar, RIGHT_OUTER_WALL)
        self.assertListed([self.bottom, self.right], panel)
        Gui.Selection.removeSelection(self.doc.Name, self.bar.Name, face_at(self.bar, RIGHT_OUTER_WALL))
        self.events()

        self.assertListed([self.bottom], panel)

    def test_cancel_leaves_the_bar_as_before(self):
        for undo in (1, 0):
            with self.subTest(undo=undo):
                self.doc.UndoMode = undo
                panel = self.open_panel([self.bottom])
                self.click(self.bar, RIGHT_LEG)
                self.click(self.bar, LEFT_LEG)
                self.assertBothEndsMitered()

                self.assertTrue(panel.reject())
                self.events()

                self.assertBarAsBefore()
                self.doc.recompute()
                self.assertBarAsBefore()

    def test_a_bar_preselected_before_the_command_lists_the_tubes_under_its_points(self):
        self.select(self.bottom)
        # Two faces of the bar: a face is selected once, at one point.
        self.select(self.bar, RIGHT_OUTER_WALL)
        self.select(self.bar, LEFT_OUTER_WALL)
        (selected_bar,) = [selection for selection in Gui.Selection.getSelectionEx() if selection.Object == self.bar]
        self.assertEqual(2, len(selected_bar.SubElementNames))

        panel = self.run_command()
        self.events()

        self.assertListed([self.bottom, self.right, self.left], panel)
        self.assertBothEndsMitered()

    # odd/tasks/pending-followups.md, S4d: the whole bar, selected in the tree, stands for the tubes at its free ends.

    def test_a_whole_bar_preselected_before_the_command_lists_the_tubes_at_its_free_ends(self):
        self.select(self.bottom)
        self.select(self.bar)

        panel = self.run_command()
        self.events()

        self.assertListed([self.bottom, self.right, self.left], panel)
        self.assertEqual("2 joints will be created.", panel.form.message_label.text())
        self.assertBothEndsMitered()

    def test_a_whole_bar_selected_while_the_panel_is_open_lists_the_tubes_at_its_free_ends(self):
        panel = self.open_panel([self.bottom])

        self.click(self.bar)

        self.assertListed([self.bottom, self.right, self.left], panel)
        self.assertEqual("2 joints will be created.", panel.form.message_label.text())
        self.assertBothEndsMitered()

    def test_a_whole_closed_bar_lists_nothing_and_says_to_click_its_tubes(self):
        _, closed = self.make_bar()
        closed_message = f"{closed.Label} is closed: click its tubes to add them."
        self.select(self.bottom)
        self.select(closed)

        panel = self.run_command()
        self.events()

        self.assertListed([self.bottom], panel)
        self.assertEqual(
            "\n".join(["Select two or more profiles to miter.", closed_message]), panel.form.message_label.text()
        )
        self.close_panels()

        panel = self.open_panel([self.bottom])
        self.click(closed)

        self.assertListed([self.bottom], panel)
        self.assertEqual(
            "\n".join(["Select two or more profiles to miter.", closed_message]), panel.form.message_label.text()
        )
        # The next click explains itself: the note goes.
        self.click(self.bar, RIGHT_LEG)
        self.assertListed([self.bottom, self.right], panel)
        self.assertEqual("1 joint will be created.", panel.form.message_label.text())


if __name__ == "__main__":
    unittest.main()

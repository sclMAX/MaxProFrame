"""Create and Refresh Balloons: which view they act on, what they place, and what they report."""

import glob
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_edit_balloons_tool import (
    CreateBalloonsCommand,
    RefreshBalloonsCommand,
    cancel_view_pick,
)
from freecad.maxproframe.profile import Profile


def page_template():
    """A template shipped with FreeCAD: a page refuses views without one."""
    pattern = os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Templates", "**", "A4_Landscape*.svg")
    return sorted(glob.glob(pattern, recursive=True))[0]


def value(quantity):
    return getattr(quantity, "Value", quantity)


def make_profile(doc, name, x):
    """A 50 x 50 tube, 250 long, along Z through (x, 0)."""
    axis = doc.addObject("Part::Feature", f"{name}Axis")
    axis.Shape = Part.makeLine(App.Vector(x, 0, 0), App.Vector(x, 0, 250))
    obj = doc.addObject("Part::FeaturePython", name)
    obj.addExtension("Part::AttachExtensionPython")
    Profile(
        obj,
        init_w=50.0,
        init_h=50.0,
        init_mt=2.0,
        init_ft=0.0,
        init_r1=0.0,
        init_r2=0.0,
        init_len=250.0,
        init_wg=8.0,
        init_unit_price=3.0,
        init_mf=False,
        init_anchor_x=1,
        init_anchor_y=1,
        material="Metal",
        fam="Square Hollow",
        size_name="Probe",
        bevels_combined=False,
        catalog_family="Square Hollow (No Fillet)",
        link_sub=(axis, ("Edge1",)),
    )
    obj.MapMode = "NormalToEdge"
    obj.AttachmentSupport = (axis, "Edge1")
    return obj


class TestBalloons(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BalloonsTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1
        self.left = make_profile(self.doc, "Left", 0)
        self.right = make_profile(self.doc, "Right", 200)
        self.left.PID = "1"
        self.right.PID = "2"
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = page_template()
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.left, self.right]
        self.view.Direction = App.Vector(0, -1, 0)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.doc.recompute()
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        # Runs before the document closes: a pick left waiting must not outlive the test.
        self.addCleanup(self.settle)
        self.addCleanup(cancel_view_pick)

    def settle(self):
        """Run the work a pick defers out of the selection callback."""
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def select(self, *objs):
        Gui.Selection.clearSelection()
        for obj in objs:
            Gui.Selection.addSelection(obj)
        self.settle()

    def create(self, *objs):
        self.select(*objs)
        CreateBalloonsCommand().Activated()
        self.settle()
        return self.balloons()

    def refresh(self, *objs):
        self.select(*objs)
        RefreshBalloonsCommand().Activated()
        self.settle()

    def press_escape(self):
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(Gui.getMainWindow(), event)
        self.settle()

    def balloons(self):
        return {b.TargetName: b for b in self.doc.Objects if b.TypeId == "TechDraw::DrawViewBalloon"}

    def targets(self):
        """The piece of every balloon, repeated if a piece has two."""
        return sorted(b.TargetName for b in self.doc.Objects if b.TypeId == "TechDraw::DrawViewBalloon")

    def status_message(self):
        return Gui.getMainWindow().statusBar().currentMessage()

    def add_view(self, name, *sources):
        view = self.doc.addObject("TechDraw::DrawViewPart", name)
        self.page.addView(view)
        view.Source = list(sources)
        self.doc.recompute()
        return view

    def test_both_commands_are_enabled_with_just_a_document(self):
        for selection in ((), (self.left,), (self.view,)):
            self.select(*selection)
            self.assertTrue(CreateBalloonsCommand().IsActive())
            self.assertTrue(RefreshBalloonsCommand().IsActive())

    def test_a_view_alone_gets_one_balloon_per_piece_with_its_id(self):
        balloons = self.create(self.view)
        self.assertEqual(sorted(balloons), ["Left", "Right"])
        self.assertEqual(balloons["Left"].Text, "1")
        self.assertEqual(balloons["Right"].Text, "2")
        self.assertIn(balloons["Left"], self.page.Views)
        self.assertEqual(balloons["Left"].SourceView.Name, self.view.Name)
        # The arrows point at each piece: 200 mm apart along the view X, same height.
        self.assertAlmostEqual(value(balloons["Right"].OriginX) - value(balloons["Left"].OriginX), 200, places=6)
        self.assertAlmostEqual(value(balloons["Right"].OriginY), value(balloons["Left"].OriginY), places=6)
        self.assertEqual(self.status_message(), "Balloons created: 2.")

    def test_a_piece_of_another_document_gets_no_balloon(self):
        # A balloon keeps only the Name of its piece: it could not find one in another document again.
        other = App.newDocument("BalloonsOther")
        self.addCleanup(App.closeDocument, other.Name)
        external = make_profile(other, "Left", 400)
        external.PID = "9"
        other.recompute()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        # FreeCAD links another document only once both are saved.
        other.saveAs(os.path.join(folder, "Other.FCStd"))
        self.doc.saveAs(os.path.join(folder, "Drawing.FCStd"))
        self.view.XSource = [external]
        self.doc.recompute()
        balloons = self.create(self.view)
        self.assertEqual(sorted(balloons), ["Left", "Right"])
        self.assertEqual(balloons["Left"].Text, "1")
        self.assertEqual(self.status_message(), "Balloons created: 2.")

    def test_running_it_again_only_marks_the_pieces_without_a_balloon(self):
        self.create(self.view)
        undo_count = self.doc.UndoCount
        self.create(self.view)
        self.assertEqual(self.targets(), ["Left", "Right"])
        self.assertEqual(self.status_message(), "Balloons created: 0. Already had a balloon: 2.")
        self.assertEqual(self.doc.UndoCount, undo_count)
        added = make_profile(self.doc, "Added", 400)
        added.PID = "3"
        self.view.Source = [self.left, self.right, added]
        self.doc.recompute()
        self.create(self.view)
        self.assertEqual(self.targets(), ["Added", "Left", "Right"])
        self.assertEqual(self.status_message(), "Balloons created: 1. Already had a balloon: 2.")

    def test_a_balloon_in_another_view_does_not_count(self):
        other = self.add_view("OtherView", self.left)
        self.create(other)
        self.create(self.view)
        self.assertEqual(self.targets(), ["Left", "Left", "Right"])
        self.assertEqual(self.status_message(), "Balloons created: 2.")

    def test_pieces_selected_with_the_view_are_the_only_ones_marked(self):
        self.assertEqual(sorted(self.create(self.view, self.left)), ["Left"])
        self.assertEqual(self.status_message(), "Balloons created: 1.")

    def test_two_views_say_select_one_and_change_nothing(self):
        other = self.add_view("OtherView", self.left)
        undo_count = self.doc.UndoCount
        self.assertEqual(self.create(self.view, other, self.left), {})
        self.assertEqual(self.status_message(), "More than one TechDraw view is selected: select one.")
        self.assertEqual(self.doc.UndoCount, undo_count)
        # Nothing waits for a click either.
        self.select(self.view)
        self.assertEqual(self.balloons(), {})

    def test_without_a_view_it_waits_for_a_click_on_one(self):
        self.assertEqual(self.create(), {})
        self.assertEqual(self.status_message(), "Create Balloons: Click a TechDraw view (Esc to cancel).")
        self.select(self.view)
        self.assertEqual(self.targets(), ["Left", "Right"])
        self.assertEqual(self.status_message(), "Balloons created: 2.")
        # One click only: another view selected later gets nothing, and Esc has nothing left to cancel.
        other = self.add_view("OtherView", self.left)
        self.select(other)
        self.press_escape()
        self.assertEqual(self.targets(), ["Left", "Right"])
        self.assertNotIn("Cancelled", self.status_message())

    def test_pieces_selected_before_the_click_are_the_only_ones_marked(self):
        self.create(self.right)
        self.select(self.view)
        self.assertEqual(self.targets(), ["Right"])
        self.assertEqual(self.status_message(), "Balloons created: 1.")

    def test_a_click_on_an_edge_of_the_view_picks_the_view(self):
        self.create()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Edge1")
        self.settle()
        self.assertEqual(self.targets(), ["Left", "Right"])

    def test_escape_cancels_the_wait(self):
        self.create()
        self.press_escape()
        self.assertEqual(self.status_message(), "Create Balloons: Cancelled.")
        self.select(self.view)
        self.assertEqual(self.balloons(), {})

    def test_pressing_the_button_again_cancels_the_wait(self):
        self.create()
        CreateBalloonsCommand().Activated()
        self.settle()
        self.assertEqual(self.status_message(), "Create Balloons: Cancelled.")
        self.select(self.view)
        self.assertEqual(self.balloons(), {})

    def test_selecting_something_outside_techdraw_cancels_the_wait(self):
        self.create()
        self.select(self.left)
        self.assertEqual(self.status_message(), "Create Balloons: Cancelled.")
        self.select(self.view)
        self.assertEqual(self.balloons(), {})

    def test_the_page_or_an_empty_click_keeps_waiting(self):
        balloon = self.create(self.view, self.left)["Left"]
        self.create()
        for obj in (self.page, self.page.Template, balloon):
            self.select(obj)
            self.assertEqual(self.status_message(), "Create Balloons: Click a TechDraw view (Esc to cancel).")
        Gui.Selection.clearSelection()
        self.settle()
        self.select(self.view)
        self.assertEqual(self.targets(), ["Left", "Right"])
        self.assertEqual(self.status_message(), "Balloons created: 1. Already had a balloon: 1.")

    def test_the_other_command_takes_over_the_wait(self):
        balloon = self.create(self.view, self.left)["Left"]
        self.left.PID = "7"
        self.create()
        RefreshBalloonsCommand().Activated()
        self.settle()
        self.assertEqual(self.status_message(), "Refresh Balloons: Click a TechDraw view (Esc to cancel).")
        self.select(self.view)
        self.assertEqual(self.targets(), ["Left"])
        self.assertEqual(balloon.Text, "7")
        self.assertEqual(self.status_message(), "Balloons refreshed: 1.")

    def test_the_bubble_sits_20_mm_from_its_arrow_on_the_paper_at_any_scale(self):
        self.view.ScaleType = "Custom"
        self.view.Scale = 0.5
        self.doc.recompute()
        balloon = self.create(self.view, self.left)["Left"]
        # Balloon coordinates are unscaled view coordinates: 40 at scale 0.5 is 20 on the paper.
        self.assertAlmostEqual(value(balloon.X) - value(balloon.OriginX), 40, places=6)
        self.assertAlmostEqual(value(balloon.Y) - value(balloon.OriginY), 40, places=6)

    def test_the_arrow_does_not_depend_on_the_scale(self):
        at_one = self.create(self.view, self.left)["Left"]
        origin = (value(at_one.OriginX), value(at_one.OriginY))
        self.doc.removeObject(at_one.Name)
        self.view.ScaleType = "Custom"
        self.view.Scale = 0.5
        self.doc.recompute()
        at_half = self.create(self.view, self.left)["Left"]
        self.assertAlmostEqual(value(at_half.OriginX), origin[0], places=6)
        self.assertAlmostEqual(value(at_half.OriginY), origin[1], places=6)

    def test_pieces_without_id_get_no_balloon_and_are_named(self):
        self.right.PID = ""
        printed = []
        self.addCleanup(setattr, App.Console, "PrintMessage", App.Console.PrintMessage)
        App.Console.PrintMessage = printed.append
        balloons = self.create(self.view)
        self.assertEqual(sorted(balloons), ["Left"])
        self.assertEqual(self.status_message(), "Balloons created: 1. Without ID: 1 (run Populate IDs).")
        self.assertEqual("".join(printed), "Create Balloons: without ID: Right\n")

    def test_no_piece_with_id_creates_nothing(self):
        self.left.PID = ""
        undo_count = self.doc.UndoCount
        self.assertEqual(self.create(self.view, self.left), {})
        self.assertEqual(self.status_message(), "Balloons created: 0. Without ID: 1 (run Populate IDs).")
        self.assertEqual(self.doc.UndoCount, undo_count)

    def test_a_view_of_a_projection_group_still_works(self):
        group = self.doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        self.page.addView(group)
        group.Source = [self.left, self.right]
        front = group.addProjection("Front")
        self.doc.recompute()
        balloons = self.create(front)
        self.assertEqual(sorted(balloons), ["Left", "Right"])
        self.assertEqual(balloons["Left"].SourceView.Name, front.Name)
        self.assertIn(balloons["Left"], self.page.Views)

    def test_a_click_on_a_view_of_a_projection_group_picks_it_not_the_group(self):
        group = self.doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        self.page.addView(group)
        group.Source = [self.left, self.right]
        front = group.addProjection("Front")
        self.doc.recompute()
        self.create()
        # The group frame is TechDraw but no view to mark: the wait goes on.
        self.select(group)
        self.assertEqual(self.balloons(), {})
        self.assertEqual(self.status_message(), "Create Balloons: Click a TechDraw view (Esc to cancel).")
        # An edge reached through the group names the view in its path.
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, group.Name, f"{front.Name}.Edge1")
        self.settle()
        balloons = self.balloons()
        self.assertEqual(sorted(balloons), ["Left", "Right"])
        self.assertEqual(balloons["Left"].SourceView.Name, front.Name)

    def test_refresh_follows_the_piece_and_its_id_and_keeps_the_bubble(self):
        balloon = self.create(self.view, self.left)["Left"]
        bubble = (value(balloon.X), value(balloon.Y))
        origin, center = (value(balloon.OriginX), value(balloon.OriginY)), self.left.Shape.CenterOfGravity
        view_center = self.view.getGeometricCenter()
        self.left.AttachmentOffset = App.Placement(App.Vector(30, 30, 30), App.Rotation())
        self.left.PID = "7"
        self.doc.recompute()
        # The view stays centered on its pieces: the arrow moves as the piece does, less the move of that center.
        moved = self.left.Shape.CenterOfGravity.sub(center).sub(self.view.getGeometricCenter().sub(view_center))
        # The view looks along -Y with X to the right: Z is up on the paper.
        self.assertGreater(abs(moved.x) + abs(moved.z), 1)
        self.refresh(balloon)
        self.assertAlmostEqual(value(balloon.OriginX) - origin[0], moved.x, places=6)
        self.assertAlmostEqual(value(balloon.OriginY) - origin[1], moved.z, places=6)
        self.assertEqual(balloon.Text, "7")
        self.assertEqual((value(balloon.X), value(balloon.Y)), bubble)
        self.assertEqual(self.status_message(), "Balloons refreshed: 1.")

    def test_refresh_of_a_selected_view_refreshes_all_its_balloons(self):
        balloons = self.create(self.view)
        other = self.add_view("OtherView", self.left)
        elsewhere = self.create(other)["Left"]
        self.left.PID, self.right.PID = "7", "8"
        self.refresh(self.view)
        self.assertEqual((balloons["Left"].Text, balloons["Right"].Text), ("7", "8"))
        self.assertEqual(elsewhere.Text, "1")
        self.assertEqual(self.status_message(), "Balloons refreshed: 2.")

    def test_refresh_without_a_selection_waits_for_a_click_on_a_view(self):
        balloons = self.create(self.view)
        self.left.PID = "7"
        self.refresh()
        self.assertEqual(self.status_message(), "Refresh Balloons: Click a TechDraw view (Esc to cancel).")
        self.assertEqual(balloons["Left"].Text, "1")
        self.select(self.view)
        self.assertEqual(balloons["Left"].Text, "7")
        self.assertEqual(self.status_message(), "Balloons refreshed: 2.")

    def test_escape_cancels_the_refresh_wait(self):
        balloons = self.create(self.view)
        self.left.PID = "7"
        self.refresh()
        self.press_escape()
        self.assertEqual(self.status_message(), "Refresh Balloons: Cancelled.")
        self.select(self.view)
        self.assertEqual(balloons["Left"].Text, "1")

    def test_refresh_skips_a_balloon_whose_piece_was_deleted(self):
        balloon = self.create(self.view, self.left)["Left"]
        text = balloon.Text
        self.doc.removeObject(self.left.Name)
        self.refresh(balloon)
        self.assertEqual(balloon.Text, text)
        self.assertEqual(self.status_message(), "Balloons refreshed: 0. Piece not found: 1.")

    def test_messages_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        self.create()
        self.assertEqual(self.status_message(), "Crear globos: Hacé clic en una vista de TechDraw (Esc para cancelar).")
        self.press_escape()
        self.assertEqual(self.status_message(), "Crear globos: Cancelado.")
        self.right.PID = ""
        self.create(self.view)
        self.assertEqual(self.status_message(), "Globos creados: 1. Sin ID: 1 (ejecutá Asignar IDs).")
        self.create(self.view)
        self.assertEqual(
            self.status_message(), "Globos creados: 0. Ya tenían globo: 1. Sin ID: 1 (ejecutá Asignar IDs)."
        )
        self.refresh()
        self.assertEqual(
            self.status_message(), "Actualizar globos: Hacé clic en una vista de TechDraw (Esc para cancelar)."
        )
        self.press_escape()
        other = self.add_view("OtherView", self.left)
        self.create(self.view, other)
        self.assertEqual(self.status_message(), "Hay más de una vista de TechDraw seleccionada: seleccioná una.")


if __name__ == "__main__":
    unittest.main()

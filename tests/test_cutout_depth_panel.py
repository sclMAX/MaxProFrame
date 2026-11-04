"""Cutout depth panel: it opens when the new sketch is closed; Cancel deletes a new cutout or restores an edited one."""

import math
import time
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_cutout_flow import HOLE_RADIUS, UP, WALL, CutoutFixture

from freecad.maxproframe import create_extruded_cutout_tool


class DepthPanelFixture(CutoutFixture):
    """Records every depth panel opened."""

    def setUp(self):
        super().setUp()
        self.depth_panels = []
        base = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel
        recorded = self.depth_panels

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_extruded_cutout_tool, "CreateExtrudedCutoutTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.settle()

    def settle(self):
        """Let FreeCAD's delayed style refresh after a language change run before the Sketcher opens."""
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.01)

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def new_cutout(self):
        """Run the command on the top face, draw a hole and close the sketch: (body, sketch, cutout, names before)."""
        body = self.tube()
        top = self.face_towards(body, UP)
        self.doc.recompute()
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        Gui.Control.closeDialog()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        self.assertEqual(gui_doc.getInEdit().Object, sketch)
        self.assertEqual(self.depth_panels, [])
        self.add_hole(sketch, body, top)
        gui_doc.resetEdit()
        self.events()
        return body, sketch, cutout, before

    def hole(self, depth):
        return math.pi * HOLE_RADIUS**2 * depth

    def edit_cutout(self, cutout):
        """Double-click ``cutout``: its depth panel, with no Undo step yet."""
        Gui.Control.closeDialog()
        self.events()
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).setEdit(cutout, 0)
        self.events()
        return self.depth_panels[-1]


class TestCutoutDepthPanel(DepthPanelFixture):
    def test_closing_the_new_sketch_opens_the_depth_panel_on_the_cutout(self):
        body, _, cutout, _ = self.new_cutout()
        self.assertEqual(len(self.depth_panels), 1)
        panel = self.depth_panels[0]
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIs(panel.obj, cutout)
        self.assertTrue(panel.created)
        # The cut is already made with one wall; the depth starts at the wall thickness.
        self.assertEqual(panel.form.combo_cut_type.currentData(), "One wall")
        self.assertAlmostEqual(panel.form.spin_depth.value(), WALL, places=6)
        self.assertFalse(panel.form.spin_depth.isEnabled())
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(WALL), places=3)

    def test_a_distance_depth_is_previewed_and_kept_by_ok_in_one_undo_step(self):
        body, sketch, cutout, _ = self.new_cutout()
        panel = self.depth_panels[0]
        form = panel.form
        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("Distance"))
        self.assertTrue(form.spin_depth.isEnabled())
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(WALL), places=3)
        form.spin_depth.setValue(1.0)
        # Live preview: half the wall is removed.
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.0), places=3)
        self.assertTrue(panel.accept())
        self.assertEqual(cutout.CutType, "Distance")
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.0, places=6)
        self.assertEqual(cutout.getStatusString(), "Valid")
        # One Undo takes back the panel only: the cutout and the drawn hole stay.
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(cutout.CutType, "One wall")
        self.assertEqual(len(sketch.Geometry), 1)
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(WALL), places=3)

    def test_cancel_of_a_new_cutout_asks_then_deletes_the_cutout_and_its_sketch(self):
        body, sketch, cutout, before = self.new_cutout()
        panel = self.depth_panels[0]
        names = (cutout.Name, sketch.Name)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No) as question:
            self.assertFalse(panel.reject())
        question.assert_called_once()
        self.assertEqual(question.call_args.args[2], "Delete the cutout and its sketch?")
        self.assertIsNotNone(self.doc.getObject(names[0]))
        self.assertIsNotNone(self.doc.getObject(names[1]))
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes) as question:
            self.assertTrue(panel.reject())
        question.assert_called_once()
        self.assertEqual(self.names(), before)
        self.assertTrue(body.ViewObject.Visibility)
        # One Undo step brings them back.
        self.doc.undo()
        self.assertEqual(sorted(self.names()), sorted(before + list(names)))

    def test_double_click_edit_shows_the_stored_depth_and_cancel_restores_it(self):
        body, _, cutout, _ = self.new_cutout()
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.assertTrue(self.depth_panels[0].accept())
        question.assert_not_called()
        Gui.Control.closeDialog()
        cutout.CutType = "Distance"
        cutout.ExtrusionLength = 1.5
        self.doc.recompute()
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).setEdit(cutout, 0)
        self.events()
        panel = self.depth_panels[-1]
        self.assertFalse(panel.created)
        self.assertEqual(panel.form.combo_cut_type.currentData(), "Distance")
        self.assertAlmostEqual(panel.form.spin_depth.value(), 1.5, places=6)
        panel.form.combo_cut_type.setCurrentIndex(panel.form.combo_cut_type.findData("Through All"))
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - 2 * self.hole(WALL), places=3)
        with patch.object(QtWidgets.QMessageBox, "question") as question:
            self.assertTrue(panel.reject())
        question.assert_not_called()
        self.assertEqual(cutout.CutType, "Distance")
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.5, places=6)
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.5), places=3)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_edit_sketch_applies_the_panel_opens_the_sketch_and_comes_back(self):
        body, sketch, cutout, _ = self.new_cutout()
        self.assertTrue(self.depth_panels[0].accept())
        panel = self.edit_cutout(cutout)
        form = panel.form
        self.assertEqual(form.button_edit_sketch.text(), "Edit sketch")
        self.assertTrue(form.button_edit_sketch.isEnabled())
        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("Distance"))
        form.spin_depth.setValue(1.0)
        form.button_edit_sketch.click()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        self.assertEqual(gui_doc.getInEdit().Object, sketch)
        # The panel changes are kept, in one Undo step, before the sketch opens.
        self.assertEqual(cutout.CutType, "Distance")
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.0, places=6)
        self.assertEqual(self.doc.UndoCount, 1)
        count = len(self.depth_panels)
        gui_doc.resetEdit()
        self.events()
        # Closing the sketch opens the panel of the edited cutout again, with the kept values.
        self.assertEqual(len(self.depth_panels), count + 1)
        again = self.depth_panels[-1]
        self.assertIs(again.obj, cutout)
        self.assertFalse(again.created)
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(again.form.combo_cut_type.currentData(), "Distance")
        self.assertAlmostEqual(again.form.spin_depth.value(), 1.0, places=6)
        self.assertTrue(again.reject())
        self.assertEqual(cutout.CutType, "Distance")
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.0), places=3)

    def test_edit_sketch_of_a_new_cutout_comes_back_to_a_new_cutout(self):
        _, sketch, cutout, before = self.new_cutout()
        panel = self.depth_panels[0]
        panel.form.button_edit_sketch.click()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        self.assertEqual(gui_doc.getInEdit().Object, sketch)
        gui_doc.resetEdit()
        self.events()
        again = self.depth_panels[-1]
        self.assertIsNot(again, panel)
        self.assertIs(again.obj, cutout)
        # Cancel still offers to delete the new cutout with its sketch.
        self.assertTrue(again.created)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
            self.assertTrue(again.reject())
        self.assertEqual(self.names(), before)

    def test_edit_sketch_is_disabled_without_a_sketch(self):
        _, _, cutout, _ = self.new_cutout()
        self.assertTrue(self.depth_panels[0].accept())
        Gui.Control.closeDialog()
        self.events()
        cutout.Sketch = None
        panel = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel(cutout)
        self.addCleanup(panel.reject)
        self.assertFalse(panel.form.button_edit_sketch.isEnabled())

    def context_action(self, cutout):
        menu = QtWidgets.QMenu()
        self.addCleanup(menu.deleteLater)
        cutout.ViewObject.Proxy.setupContextMenu(cutout.ViewObject, menu)
        actions = [action for action in menu.actions() if action.objectName() == "edit_cutout_sketch"]
        self.assertEqual(len(actions), 1)
        return actions[0]

    def test_the_context_menu_opens_the_sketch(self):
        _, sketch, cutout, _ = self.new_cutout()
        self.assertTrue(self.depth_panels[0].accept())
        Gui.Control.closeDialog()
        self.events()
        action = self.context_action(cutout)
        self.assertEqual(action.text(), "Edit sketch")
        self.assertTrue(action.isEnabled())
        count = len(self.depth_panels)
        action.trigger()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        self.assertEqual(gui_doc.getInEdit().Object, sketch)
        gui_doc.resetEdit()
        self.events()
        # From the tree only the sketch is edited: no cutout panel follows.
        self.assertEqual(len(self.depth_panels), count)
        cutout.Sketch = None
        self.assertFalse(self.context_action(cutout).isEnabled())

    def test_the_depth_panel_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        self.settle()
        self.new_cutout()
        form = self.depth_panels[0].form
        self.assertEqual(form.windowTitle(), "Calado")
        self.assertEqual(
            [form.combo_cut_type.itemText(i) for i in range(form.combo_cut_type.count())],
            ["Pasante", "Distancia", "Una pared"],
        )
        self.assertEqual(form.label_cut_type.text(), "Tipo de corte")
        self.assertEqual(form.label_depth.text(), "Profundidad")
        self.assertEqual(form.button_edit_sketch.text(), "Editar croquis")
        self.assertEqual(self.context_action(self.depth_panels[0].obj).text(), "Editar croquis")


class TestCutoutDepthExpressions(DepthPanelFixture):
    """The depth field takes a FreeCAD expression (Fx), bound to the cutout's ExtrusionLength."""

    def varset(self, depth):
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "Depth")
        varset.Depth = depth
        self.doc.recompute()
        return varset

    def distance_cutout(self, depth):
        """A new cutout kept as a Distance cut of ``depth``, then opened for editing."""
        body, sketch, cutout, _ = self.new_cutout()
        panel = self.depth_panels[0]
        panel.form.combo_cut_type.setCurrentIndex(panel.form.combo_cut_type.findData("Distance"))
        panel.form.spin_depth.setValue(depth)
        self.assertTrue(panel.accept())
        return body, cutout

    def expressions(self, obj):
        return dict(obj.ExpressionEngine)

    def test_the_depth_field_is_bound_to_the_cutout_depth(self):
        _, cutout = self.distance_cutout(1.0)
        varset = self.varset(1.25)
        panel = self.edit_cutout(cutout)
        binding = Gui.ExpressionBinding(panel.form.spin_depth)
        self.assertTrue(binding.isBound())
        self.assertFalse(binding.hasExpression())
        # What the Fx editor does: the expression goes on the bound property and the field shows its value.
        cutout.setExpression("ExtrusionLength", f"{varset.Name}.Depth")
        self.doc.recompute()
        self.assertTrue(binding.hasExpression())
        self.assertAlmostEqual(panel.form.spin_depth.value(), 1.25, places=6)
        self.assertTrue(panel.reject())

    def test_ok_keeps_an_expression_set_in_the_panel_in_one_undo_step(self):
        body, cutout = self.distance_cutout(1.0)
        varset = self.varset(1.25)
        panel = self.edit_cutout(cutout)
        cutout.setExpression("ExtrusionLength", f"{varset.Name}.Depth")
        self.doc.recompute()
        self.assertTrue(panel.accept())
        self.assertEqual(self.expressions(cutout), {"ExtrusionLength": f"{varset.Name}.Depth"})
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.25), places=3)
        # The VarSet drives the depth from now on.
        varset.Depth = 0.5
        self.doc.recompute()
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 0.5, places=6)
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(0.5), places=3)
        varset.Depth = 1.25
        self.doc.recompute()
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.expressions(cutout), {})
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.0, places=6)

    def test_cancel_removes_an_expression_set_in_the_panel(self):
        body, cutout = self.distance_cutout(1.0)
        varset = self.varset(1.25)
        panel = self.edit_cutout(cutout)
        cutout.setExpression("ExtrusionLength", f"{varset.Name}.Depth")
        self.doc.recompute()
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(cutout), {})
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.0, places=6)
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.0), places=3)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_with_undo_off_removes_an_expression_set_in_the_panel(self):
        body, cutout = self.distance_cutout(1.0)
        varset = self.varset(1.25)
        panel = self.edit_cutout(cutout)
        self.doc.UndoMode = 0
        self.addCleanup(setattr, self.doc, "UndoMode", 1)
        cutout.setExpression("ExtrusionLength", f"{varset.Name}.Depth")
        self.doc.recompute()
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(cutout), {})
        self.assertAlmostEqual(cutout.ExtrusionLength.Value, 1.0, places=6)
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(1.0), places=3)

    def test_an_existing_expression_is_shown_and_kept(self):
        body, cutout = self.distance_cutout(1.0)
        varset = self.varset(1.25)
        cutout.setExpression("ExtrusionLength", f"{varset.Name}.Depth")
        self.doc.recompute()
        panel = self.edit_cutout(cutout)
        form = panel.form
        self.assertTrue(Gui.ExpressionBinding(form.spin_depth).hasExpression())
        self.assertAlmostEqual(form.spin_depth.value(), 1.25, places=6)
        # Changing the cut type back and forth leaves the expression in place.
        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("Through All"))
        form.combo_cut_type.setCurrentIndex(form.combo_cut_type.findData("Distance"))
        self.assertTrue(panel.accept())
        self.assertEqual(self.expressions(cutout), {"ExtrusionLength": f"{varset.Name}.Depth"})
        varset.Depth = 0.5
        self.doc.recompute()
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - self.hole(0.5), places=3)


if __name__ == "__main__":
    unittest.main()

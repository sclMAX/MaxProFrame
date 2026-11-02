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


class TestCutoutDepthPanel(CutoutFixture):
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


if __name__ == "__main__":
    unittest.main()

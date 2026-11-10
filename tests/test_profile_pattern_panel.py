"""Profile Pattern command and panel: pick the piece, the edge and the faces, live preview, one Undo step, edit."""

import os
import unittest
import xml.etree.ElementTree as ElementTree
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_profile_pattern import SLAT_X, PatternFixture, center

from freecad.maxproframe import create_profile_pattern_tool
from freecad.maxproframe.create_profile_pattern_tool import ProfilePatternCommand
from freecad.maxproframe.profile_pattern import BETWEEN_FACES, COUNT_AND_PITCH, make_profile_pattern

NO_EDGE = "Click a straight edge for the direction of the copies."


class PatternPanelFixture(PatternFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        base = create_profile_pattern_tool.ProfilePatternTaskPanel
        recorded = self.recorded

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_profile_pattern_tool, "ProfilePatternTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        for panel in self.recorded:
            panel.clean()
        self.events()

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def select(self, *items):
        Gui.Selection.clearSelection()
        for obj, sub in items:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)

    def click(self, obj, sub):
        """A click in the 3D view: it replaces the selection, the observer hears it."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        self.events()

    def run_command(self, *items):
        self.select(*items)
        count = len(self.recorded)
        ProfilePatternCommand().Activated()
        self.assertEqual(len(self.recorded), count + 1)
        self.assertTrue(Gui.Control.activeDialog())
        self.events()
        return self.recorded[-1]

    def set_values(self, panel, mode=COUNT_AND_PITCH, count=None, pitch=None, sense=None):
        form = panel.form
        form.combo_mode.setCurrentIndex(form.combo_mode.findData(mode))
        if count is not None:
            form.spin_count.setValue(count)
        if pitch is not None:
            form.spin_pitch.setValue(pitch)
        if sense is not None:
            form.combo_sense.setCurrentIndex(form.combo_sense.findData(sense))
        panel._update_preview()
        self.events()

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def patterns(self):
        return [obj for obj in self.doc.Objects if "Copies" in obj.PropertiesList]

    def offsets(self):
        return (self.slat.OffsetX.Value, self.slat.OffsetY.Value)


class TestPatternCommand(PatternPanelFixture):
    def test_the_command_has_its_icon_and_needs_a_document(self):
        pixmap = ProfilePatternCommand().GetResources()["Pixmap"]
        self.assertEqual(os.path.basename(pixmap), "profile-pattern.svg")
        self.assertEqual(ElementTree.parse(pixmap).getroot().tag, "{http://www.w3.org/2000/svg}svg")
        self.assertTrue(ProfilePatternCommand().IsActive())

    def test_the_preview_shows_the_copies_and_ok_is_one_undo_step(self):
        before, undos = self.names(), len(self.doc.UndoNames)
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        self.set_values(panel, count=3, pitch=150.0)
        (pattern,) = self.patterns()
        self.assertEqual(sorted(round(center(c).x, 6) for c in pattern.Copies), [250.0, 400.0, 550.0])
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(len(self.doc.UndoNames), undos + 1)
        self.assertEqual(self.doc.UndoNames[0], "Create Profile Pattern")
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.names(), before)

    def test_cancel_leaves_the_document_unchanged(self):
        undos = len(self.doc.UndoNames)
        left, right = self.walls()
        before = self.names()
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        self.click(*left)
        self.click(*right)
        self.set_values(panel, mode=BETWEEN_FACES, count=5)
        self.assertAlmostEqual(center(self.slat).x, 150.0)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.names(), before)
        self.assertEqual(self.offsets(), (0.0, 0.0))
        self.assertAlmostEqual(center(self.slat).x, SLAT_X)
        self.assertEqual(len(self.doc.UndoNames), undos)

    def test_cancel_with_undo_disabled_still_leaves_nothing(self):
        self.doc.UndoMode = 0
        left, right = self.walls()
        before = self.names()
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"), left, right)
        self.set_values(panel, mode=BETWEEN_FACES, count=5)
        self.assertEqual(len(self.patterns()), 1)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.names(), before)
        self.assertEqual(self.offsets(), (0.0, 0.0))

    def test_clicks_pick_the_edge_then_the_two_faces(self):
        left, right = self.walls()
        panel = self.run_command((self.slat, ""))
        self.assertIn(NO_EDGE, panel.form.message_label.text())
        self.assertEqual(self.patterns(), [])
        self.click(self.frame, "Edge1")
        self.assertIn("Edge1", panel.form.edge_label.text())
        self.click(*left)
        self.click(*right)
        self.assertIn(left[0].Label, panel.form.faces_label.text())
        self.assertIn(right[0].Label, panel.form.faces_label.text())
        self.set_values(panel, mode=BETWEEN_FACES, count=5)
        self.assertTrue(panel.accept())
        (pattern,) = self.patterns()
        self.assertAlmostEqual(center(self.slat).x, 150.0)
        self.assertEqual(sorted(round(center(c).x, 6) for c in pattern.Copies), [325.0, 500.0, 675.0, 850.0])
        self.assertIn("125", panel.form.result_label.text())

    def test_a_third_face_starts_the_pair_again(self):
        left, right = self.walls()
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        self.click(*left)
        self.click(*right)
        self.click(*right)
        self.assertEqual(panel.faces, [right])

    def test_ok_without_an_edge_says_what_is_missing(self):
        panel = self.run_command((self.slat, ""))
        self.assertFalse(panel.accept())
        self.assertIn(NO_EDGE, panel.form.message_label.text())

    def test_a_direction_along_the_piece_explains_why_between_faces_is_unavailable(self):
        along = self.make_sketch(((0, 0, 0), (0, 1000, 0)))
        panel = self.run_command((self.slat, ""), (along, "Edge1"))
        form = panel.form
        self.assertIn("across", form.mode_label.text())
        self.assertTrue(form.mode_label.isVisibleTo(form))
        item = form.combo_mode.model().item(form.combo_mode.findData(BETWEEN_FACES))
        self.assertFalse(item.isEnabled())
        self.click(self.frame, "Edge1")
        self.assertFalse(form.mode_label.isVisibleTo(form))
        self.assertTrue(item.isEnabled())

    def test_the_panel_speaks_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((self.slat, ""))
        self.assertIn("Hacé clic en una arista recta para la dirección de las copias.", panel.form.message_label.text())
        self.assertEqual(panel.form.combo_mode.itemText(0), "Cantidad y paso")
        self.assertEqual(panel.form.combo_mode.itemText(1), "Entre caras")

    def test_a_click_on_something_that_is_no_piece_is_explained(self):
        panel = self.run_command()
        self.click(self.frame, "Edge1")
        self.assertIn("Select the piece to repeat", panel.form.message_label.text())
        self.click(self.slat, "Face1")
        self.assertIn(self.slat.Label, panel.form.piece_label.text())


class TestPatternEdit(PatternPanelFixture):
    def existing(self, **values):
        obj = make_profile_pattern(self.slat, (self.frame, "Edge1"), count=3, pitch=100.0, **values)
        self.doc.recompute()
        self.doc.clearUndos()
        return obj

    def edit(self, obj):
        count = len(self.recorded)
        Gui.getDocument(self.doc.Name).setEdit(obj.Name, 0)
        self.events()
        self.assertEqual(len(self.recorded), count + 1)
        return self.recorded[-1]

    def test_double_click_edits_the_pattern_in_one_undo_step(self):
        obj = self.existing()
        panel = self.edit(obj)
        self.assertEqual((panel.form.spin_count.value(), panel.form.spin_pitch.value()), (3, 100.0))
        self.set_values(panel, count=5, sense="Symmetric")
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(len(obj.Copies), 10)
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(len(obj.Copies), 3)
        self.assertEqual(len([o for o in self.doc.Objects if o.TypeId == "App::Link"]), 3)
        self.assertEqual(sorted(round(center(c).x, 6) for c in obj.Copies), [200.0, 300.0, 400.0])

    def test_cancel_of_an_edit_puts_the_pattern_back(self):
        obj = self.existing()
        panel = self.edit(obj)
        self.set_values(panel, pitch=250.0)
        self.assertEqual(sorted(round(center(c).x, 6) for c in obj.Copies), [350.0, 600.0, 850.0])
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(sorted(round(center(c).x, 6) for c in obj.Copies), [200.0, 300.0, 400.0])
        self.assertEqual(self.doc.UndoNames, [])

    def test_ok_with_nothing_changed_adds_no_undo_step(self):
        obj = self.existing()
        panel = self.edit(obj)
        self.assertTrue(panel.accept())
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(len(obj.Copies), 3)


if __name__ == "__main__":
    unittest.main()

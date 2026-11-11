"""Profile Pattern command and panel: pick the piece, the edge and the faces, live preview, one Undo step, edit."""

import os
import unittest
import xml.etree.ElementTree as ElementTree
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from elision_helpers import font_ellipsis
from miter_helpers import use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER
from test_extend_cut_preview import keep_auto_preview
from test_profile_pattern import SLAT_X, PatternFixture, X, center, face_named

from freecad.maxproframe import create_profile_pattern_tool
from freecad.maxproframe.create_profile_pattern_tool import ProfilePatternCommand
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.profile_pattern import BETWEEN_FACES, COUNT_AND_PITCH, make_profile_pattern

NO_EDGE = "Click a straight edge for the direction of the copies."
# Remembered state of the Update automatically check box of the panel.
AUTO_PREVIEW_PARAM = "Profile Pattern Auto Preview"
AUTO_PREVIEW = SimpleNamespace(auto_preview_param=AUTO_PREVIEW_PARAM)


class PatternPanelFixture(PatternFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        # Every test starts with Update automatically at its default, and leaves the remembered state as it was.
        keep_auto_preview(self, AUTO_PREVIEW)
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

    def status(self, panel):
        return panel.form.status_label.text()

    def expressions(self, obj):
        return {path.lstrip("."): expression for path, expression in obj.ExpressionEngine}

    def varset(self, step):
        """A VarSet with a Step length, for an expression on the pitch."""
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "Step")
        varset.Step = step
        self.doc.recompute()
        return varset


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

    def test_with_update_automatically_unchecked_ok_creates_the_pattern_in_one_undo_step(self):
        # S4: picks and values make no pattern until OK, which keeps the panel values.
        keep_auto_preview(self, AUTO_PREVIEW, False)
        before, undos = self.names(), len(self.doc.UndoNames)
        panel = self.run_command((self.slat, ""))
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.click(self.frame, "Edge1")
        self.assertIn("Edge1", panel.form.edge_label.text())
        self.set_values(panel, count=3, pitch=150.0)
        self.assertEqual(self.names(), before)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.close_dialog()
        (pattern,) = self.patterns()
        self.assertEqual(self.copy_centers(pattern), [250.0, 400.0, 550.0])
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
        self.assertIn(left[0].Label, panel.form.face1_label.text())
        self.assertIn(right[0].Label, panel.form.face2_label.text())
        self.set_values(panel, mode=BETWEEN_FACES, count=5)
        self.assertTrue(panel.accept())
        (pattern,) = self.patterns()
        self.assertAlmostEqual(center(self.slat).x, 150.0)
        self.assertEqual(sorted(round(center(c).x, 6) for c in pattern.Copies), [325.0, 500.0, 675.0, 850.0])
        self.assertIn("125", panel.form.result_label.text())

    def test_a_third_face_without_change_keeps_the_pair(self):
        left, right = self.walls()
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        self.click(*left)
        self.click(*right)
        self.click(*right)
        self.assertEqual(panel.faces, [left, right])
        self.assertIn("Change", panel.form.message_label.text())

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
        form.button_edge.click()
        self.click(self.frame, "Edge1")
        self.assertFalse(form.mode_label.isVisibleTo(form))
        self.assertTrue(item.isEnabled())

    def test_the_panel_speaks_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((self.slat, ""))
        self.assertIn("Hacé clic en una arista recta para la dirección de las copias.", panel.form.message_label.text())
        self.assertEqual(panel.form.combo_mode.itemText(0), "Cantidad y paso")
        self.assertEqual(panel.form.combo_mode.itemText(1), "Entre caras")
        self.assertEqual(panel.form.button_edge.text(), "Cambiar")
        self.assertEqual(panel.form.face1_title.text(), "Cara 1")
        self.assertEqual(panel.form.edge_label.text(), "Ninguna")
        panel.form.button_edge.click()
        self.assertEqual(
            panel.form.hint_label.text(), "Hacé clic en una arista recta, del marco por ejemplo, para la dirección."
        )

    def test_a_click_on_something_that_is_no_piece_is_explained(self):
        panel = self.run_command()
        self.click(self.frame, "Edge1")
        self.assertIn("Select the piece to repeat", panel.form.message_label.text())
        self.click(self.slat, "Face1")
        self.assertIn(self.slat.Label, panel.form.piece_label.text())


class TestPatternReferences(PatternPanelFixture):
    """The Change buttons replace the piece, the direction or the faces; long names never widen the panel."""

    def existing(self):
        obj = make_profile_pattern(self.slat, (self.frame, "Edge1"), count=3, pitch=100.0)
        self.doc.recompute()
        self.doc.clearUndos()
        return obj

    def edit(self, obj):
        Gui.getDocument(self.doc.Name).setEdit(obj.Name, 0)
        self.events()
        return self.recorded[-1]

    def other_piece(self):
        other = self.make_profile(self.make_sketch(((SLAT_X, 0, 0), (SLAT_X, 300, 0))), "Edge1", **CENTER)
        self.doc.recompute()
        return other

    def preview(self, panel):
        panel._update_preview()
        self.events()

    def test_long_names_are_elided_in_the_middle_and_do_not_widen_the_panel(self):
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        width = panel.form.sizeHint().width()
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.frame.Label = "Frame_" + "x" * 400 + "_end"
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        label = panel.form.edge_label
        self.assertLessEqual(panel.form.sizeHint().width(), width)
        self.assertEqual(label.toolTip(), f"{self.frame.Label} · Edge1")
        self.assertTrue(label.text().startswith("Frame_"), label.text())
        self.assertTrue(label.text().endswith(" · Edge1"), label.text())
        self.assertIn(font_ellipsis(label.fontMetrics()), label.text())

    def test_a_click_without_change_does_not_replace_the_direction(self):
        obj = self.existing()
        other = self.make_sketch(((1000, 0, 0), (0, 0, 0)))
        panel = self.edit(obj)
        self.click(other, "Edge1")
        self.preview(panel)
        self.assertEqual(panel.edge, (self.frame, "Edge1"))
        self.assertIn("Change", panel.form.message_label.text())
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])

    def test_change_direction_picks_another_edge_in_one_undo_step(self):
        obj = self.existing()
        other = self.make_sketch(((1000, 0, 0), (0, 0, 0)))
        self.doc.clearUndos()
        panel = self.edit(obj)
        panel.form.button_edge.click()
        self.assertTrue(panel.form.button_edge.isChecked())
        self.assertIn("straight edge", panel.form.hint_label.text())
        self.click(self.slat, "Face1")
        self.assertTrue(panel.form.button_edge.isChecked())
        self.click(other, "Edge1")
        self.assertFalse(panel.form.button_edge.isChecked())
        self.assertEqual(panel.edge[0], other)
        self.assertTrue(panel.edge[1].endswith("Edge1"), panel.edge[1])
        self.assertTrue(panel.form.edge_label.text().endswith(" · Edge1"), panel.form.edge_label.text())
        self.preview(panel)
        self.assertEqual(self.copy_centers(obj), [-200.0, -100.0, 0.0])
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])

    def test_change_faces_picks_a_new_pair_and_one_button_is_armed_at_a_time(self):
        left, right = self.walls()
        middle = self.box("Middle", 400)
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"), left, right)
        self.set_values(panel, mode=BETWEEN_FACES, count=3)
        form = panel.form
        form.button_edge.click()
        form.button_faces.click()
        self.assertFalse(form.button_edge.isChecked())
        self.assertTrue(form.button_faces.isChecked())
        inner = (middle, face_named(middle, X, 500))
        self.click(*inner)
        self.assertEqual(panel.faces, [left, right])
        self.assertTrue(form.button_faces.isChecked())
        self.click(*right)
        self.assertFalse(form.button_faces.isChecked())
        self.assertEqual(panel.faces, [inner, right])
        self.assertIn("Middle", form.face1_label.toolTip())
        self.preview(panel)
        self.assertEqual(panel._error, "")
        self.assertTrue(panel.accept())
        (pattern,) = self.patterns()
        self.assertEqual([face for face, _ in pattern.Faces], [middle, right[0]])

    def test_change_piece_relinks_the_copies_in_one_undo_step(self):
        obj = self.existing()
        other = self.other_piece()
        self.doc.clearUndos()
        panel = self.edit(obj)
        panel.form.button_piece.click()
        self.click(other, "Face1")
        self.assertFalse(panel.form.button_piece.isChecked())
        self.assertEqual(panel.piece, other)
        self.assertEqual(panel.form.piece_label.toolTip(), other.Label)
        self.preview(panel)
        self.assertEqual(obj.Piece, other)
        self.assert_copies_are(obj, other)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(obj.Piece, self.slat)
        self.assert_copies_are(obj, self.slat)

    def test_with_update_automatically_unchecked_change_piece_waits_for_ok(self):
        # S4: a Change pick is not previewed; OK applies it in one Undo step.
        obj = self.existing()
        other = self.other_piece()
        self.doc.clearUndos()
        panel = self.edit(obj)
        panel.form.cb_auto_update.setChecked(False)
        panel.form.button_piece.click()
        self.click(other, "Face1")
        self.preview(panel)
        self.assertEqual(panel.piece, other)
        self.assertEqual(obj.Piece, self.slat)
        self.assert_copies_are(obj, self.slat)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(obj.Piece, other)
        self.assert_copies_are(obj, other)
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])

    def test_a_copy_cannot_be_the_piece(self):
        obj = self.existing()
        panel = self.edit(obj)
        panel.form.button_piece.click()
        self.click(obj.Copies[0], "")
        self.assertEqual(panel.piece, self.slat)
        self.assertTrue(panel.form.button_piece.isChecked())
        self.assertIn("copy", panel.form.message_label.text())

    def test_cancel_with_undo_disabled_puts_the_piece_back(self):
        obj = self.existing()
        other = self.other_piece()
        self.doc.UndoMode = 0
        panel = self.edit(obj)
        panel.form.button_piece.click()
        self.click(other, "Face1")
        self.preview(panel)
        self.assert_copies_are(obj, other)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(obj.Piece, self.slat)
        self.assert_copies_are(obj, self.slat)

    def test_between_faces_moves_only_the_current_piece_and_cancel_puts_both_back(self):
        left, right = self.walls()
        other = self.other_piece()
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"), left, right)
        self.set_values(panel, mode=BETWEEN_FACES, count=5)
        self.assertAlmostEqual(center(self.slat).x, 150.0)
        panel.form.button_piece.click()
        self.click(other, "Face1")
        self.preview(panel)
        self.assertAlmostEqual(center(self.slat).x, SLAT_X)
        self.assertAlmostEqual(center(other).x, 150.0)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertAlmostEqual(center(self.slat).x, SLAT_X)
        self.assertAlmostEqual(center(other).x, SLAT_X)
        self.assertEqual(self.offsets(), (0.0, 0.0))


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

    # S4: Update automatically.

    def test_update_automatically_is_checked_by_default_in_a_preview_group(self):
        panel = self.edit(self.existing())
        form = panel.form
        self.assertEqual(form.groupBox_preview.title(), "Preview")
        self.assertEqual(form.cb_auto_update.text(), "Update automatically")
        self.assertTrue(form.cb_auto_update.isChecked())
        self.assertIs(form.status_label.parentWidget(), form.groupBox_preview)

    def test_unchecked_an_edit_waits_for_ok_and_the_choice_is_remembered(self):
        obj = self.existing()
        panel = self.edit(obj)
        panel.form.cb_auto_update.setChecked(False)
        self.assertFalse(get_param_group().GetBool(AUTO_PREVIEW_PARAM, True))
        self.set_values(panel, count=5)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])
        self.assertEqual(obj.Count, 3)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0, 500.0, 600.0])
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        # A new panel opens unchecked.
        panel = self.edit(obj)
        self.assertFalse(panel.form.cb_auto_update.isChecked())

    def test_checking_update_automatically_again_previews_at_once(self):
        obj = self.existing()
        panel = self.edit(obj)
        panel.form.cb_auto_update.setChecked(False)
        self.set_values(panel, count=5)
        self.assertEqual(len(obj.Copies), 3)
        panel.form.cb_auto_update.setChecked(True)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0, 500.0, 600.0])
        self.assertEqual(self.status(panel), "Preview updated")
        self.assertTrue(get_param_group().GetBool(AUTO_PREVIEW_PARAM, False))
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])
        self.assertEqual(self.doc.UndoNames, [])

    # S5: Fx on Count and Pitch.

    def test_count_and_pitch_are_bound_to_the_edited_pattern(self):
        panel = self.edit(self.existing())
        for field in (panel.form.spin_count, panel.form.spin_pitch):
            binding = Gui.ExpressionBinding(field)
            self.assertTrue(binding.isBound())
            self.assertFalse(binding.hasExpression())

    def test_a_new_pattern_binds_count_and_pitch_once_it_exists(self):
        panel = self.run_command((self.slat, ""), (self.frame, "Edge1"))
        (pattern,) = self.patterns()
        self.assertEqual(panel.obj, pattern)
        for field in (panel.form.spin_count, panel.form.spin_pitch):
            self.assertTrue(Gui.ExpressionBinding(field).isBound())

    def test_ok_keeps_an_expression_set_in_the_panel_in_one_undo_step(self):
        varset = self.varset(120.0)
        obj = self.existing()
        panel = self.edit(obj)
        # What the Fx editor does: the expression goes on the bound property and the field shows its value.
        obj.setExpression("Pitch", f"{varset.Name}.Step")
        self.doc.recompute()
        self.events()
        self.assertTrue(Gui.ExpressionBinding(panel.form.spin_pitch).hasExpression())
        self.assertAlmostEqual(panel.form.spin_pitch.value(), 120.0, places=6)
        panel._update_preview()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.expressions(obj), {"Pitch": f"{varset.Name}.Step"})
        self.assertEqual(self.copy_centers(obj), [220.0, 340.0, 460.0])
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        # The VarSet drives the pitch from now on.
        varset.Step = 50.0
        self.doc.recompute()
        self.assertEqual(self.copy_centers(obj), [150.0, 200.0, 250.0])

    def test_cancel_removes_an_expression_set_in_the_panel(self):
        varset = self.varset(120.0)
        obj = self.existing()
        panel = self.edit(obj)
        obj.setExpression("Pitch", f"{varset.Name}.Step")
        self.doc.recompute()
        self.events()
        self.assertEqual(self.copy_centers(obj), [220.0, 340.0, 460.0])
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.expressions(obj), {})
        self.assertAlmostEqual(obj.Pitch.Value, 100.0, places=6)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])
        self.assertEqual(self.doc.UndoNames, [])

    def test_cancel_with_undo_disabled_removes_an_expression_set_in_the_panel(self):
        varset = self.varset(120.0)
        obj = self.existing()
        self.doc.UndoMode = 0
        panel = self.edit(obj)
        obj.setExpression("Pitch", f"{varset.Name}.Step")
        self.doc.recompute()
        self.events()
        self.assertEqual(self.copy_centers(obj), [220.0, 340.0, 460.0])
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.expressions(obj), {})
        self.assertAlmostEqual(obj.Pitch.Value, 100.0, places=6)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])

    def test_an_existing_expression_is_shown_and_kept_by_an_unchanged_ok(self):
        varset = self.varset(120.0)
        obj = self.existing()
        obj.setExpression("Pitch", f"{varset.Name}.Step")
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.edit(obj)
        self.assertTrue(Gui.ExpressionBinding(panel.form.spin_pitch).hasExpression())
        self.assertAlmostEqual(panel.form.spin_pitch.value(), 120.0, places=6)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.expressions(obj), {"Pitch": f"{varset.Name}.Step"})
        self.assertEqual(self.copy_centers(obj), [220.0, 340.0, 460.0])

    def test_a_count_change_beside_a_pitch_expression_keeps_the_expression(self):
        varset = self.varset(120.0)
        obj = self.existing()
        obj.setExpression("Pitch", f"{varset.Name}.Step")
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.edit(obj)
        self.set_values(panel, count=4)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(self.expressions(obj), {"Pitch": f"{varset.Name}.Step"})
        self.assertEqual(self.copy_centers(obj), [220.0, 340.0, 460.0, 580.0])
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])


if __name__ == "__main__":
    unittest.main()

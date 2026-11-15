"""Miter Ends panel: no geometry while its own recompute runs (odd/tasks/panel-recompute-deadlock.md, S2, S3, S4).

FreeCAD's progress bar pumps Qt events inside a recompute (L2): the hooks below type in the Gap, let its timer fire,
toggle Extend and press OK there. None of it may run geometry then; it waits for the recompute to end, and the
preview ends matching the last values.
"""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import keep_auto_preview, use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture
from test_extend_cut_preview import wait
from test_recompute_gate import during, hook_execute, watch

from freecad.maxproframe import create_end_miter_tool
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, EndMiterTaskPanel
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# Long enough for the Gap timer to fire inside the recompute.
INSIDE = 3 * GAP_DELAY_MS / 1000
# The Gap delay, the recompute and the one that follows it, with room for a loaded machine.
SETTLE = 2.0


class EndMiterRecomputeGateTest(MiterFixture):
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
        self.hooks, state = hook_execute(self, TrimmedProfile)
        self.geometry = watch(
            self, create_end_miter_tool, ("make_end_miter_profile", "real_stretch", "_clicked_pieces"), state
        )
        self.previews = watch(
            self, EndMiterTaskPanel, ("_rebuild_preview", "_highlight_members", "_draw_markers"), state
        )

    def close_panels(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def ran_during(self):
        return during(self.geometry) + during(self.previews)

    def profiles(self, edges):
        members = [self.make_profile(self.make_sketch(edge), "Edge1", **CENTER) for edge in edges]
        self.doc.clearUndos()
        return members

    def run_command(self, members):
        Gui.Selection.clearSelection()
        for member in members:
            Gui.Selection.addSelection(self.doc.Name, member.Name)
        created = []
        base = create_end_miter_tool.EndMiterTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_end_miter_tool, "EndMiterTaskPanel", Recording):
            create_end_miter_tool.CreateEndMiterCommand().Activated()
        self.panels.extend(created)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def click(self, obj, sub="Face3"):
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        QtWidgets.QApplication.processEvents()

    def trims(self):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "End Miter"]

    def trim_of(self, body):
        (found,) = [obj for obj in self.trims() if obj.TrimmedBody == body]
        return found

    def assert_miters(self, members, extend, gap):
        self.assertEqual({trim.TrimmedBody.Name for trim in self.trims()}, {member.Name for member in members})
        for trim in self.trims():
            self.assertEqual(trim.getStatusString(), "Valid")
            self.assertEqual(trim.MiterExtend, extend)
            self.assertAlmostEqual(trim.MiterGap.Value, gap)
        first, second = (self.trim_of(member) for member in members)
        self.assertAlmostEqual(first.Shape.distToShape(second.Shape)[0], gap, places=5)

    def type_inside(self, panel, gap):
        """A hook: ``gap`` typed in the Gap, and its timer due, inside the recompute."""

        def type_gap(fp):
            panel.form.sb_gap.setValue(gap)
            wait(INSIDE)

        return type_gap

    def test_a_gap_typed_while_extend_recomputes_the_preview_waits_for_it_and_is_previewed_then(self):
        # S2, L2: Extend previews at once; the Gap typed meanwhile and its timer fire inside that recompute.
        p1, p2 = self.profiles(CHAINED)
        panel = self.run_command([p1, p2])
        self.hooks.append(self.type_inside(panel, 0.5))

        panel.form.cb_extend.setChecked(False)
        wait(SETTLE)

        self.assertEqual([], self.hooks)
        self.assertEqual([], self.ran_during())
        self.assertIn(("_rebuild_preview", False), self.previews)
        self.assert_miters([p1, p2], False, 0.5)
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def test_extend_toggled_while_the_preview_recomputes_is_previewed_once_it_ends(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.run_command([p1, p2])
        self.hooks.append(lambda fp: panel.form.cb_extend.setChecked(False))

        panel.form.sb_gap.setValue(0.5)
        wait(SETTLE)

        self.assertEqual([], self.ran_during())
        self.assert_miters([p1, p2], False, 0.5)
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def test_ok_pressed_while_the_preview_recomputes_creates_the_miters_with_the_last_gap_once_it_ends(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.run_command([p1, p2])
        returned = []

        def type_and_ok(fp):
            self.type_inside(panel, 0.5)(fp)
            returned.append(panel.accept())

        self.hooks.append(type_and_ok)

        panel.form.sb_gap.setValue(0.2)
        wait(SETTLE)

        self.assertEqual([False], returned)
        self.assertEqual([], self.ran_during())
        self.assertFalse(Gui.Control.activeDialog())
        self.assert_miters([p1, p2], True, 0.5)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_pressed_while_the_preview_recomputes_leaves_the_document_unchanged_once_it_ends(self):
        p1, p2 = self.profiles(CHAINED)
        names = sorted(obj.Name for obj in self.doc.Objects)
        panel = self.run_command([p1, p2])
        returned = []
        self.hooks.append(lambda fp: returned.append(panel.reject()))

        panel.form.sb_gap.setValue(0.2)
        wait(SETTLE)

        self.assertEqual([False], returned)
        self.assertEqual([], self.ran_during())
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))
        self.assertTrue(p1.ViewObject.Visibility and p2.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_preview_and_ok_without_a_recompute_in_between_are_unchanged(self):
        # S4: the Gap previewed after the delay, OK keeping it in one Undo step.
        p1, p2 = self.profiles(CHAINED)
        panel = self.run_command([p1, p2])
        panel.form.sb_gap.setValue(0.5)
        self.assertEqual("Pending changes", panel.form.status_label.text())
        wait()
        self.assertEqual("Preview updated", panel.form.status_label.text())
        self.assert_miters([p1, p2], True, 0.5)
        self.assertTrue(panel.accept())
        self.assert_miters([p1, p2], True, 0.5)
        self.assertEqual(self.doc.UndoCount, 1)


if __name__ == "__main__":
    unittest.main()

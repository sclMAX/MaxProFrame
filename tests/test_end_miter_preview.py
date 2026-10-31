"""End Miter panel: live preview of the miters, the Update automatically check box and joint markers."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture
from test_end_miter_translations import use_language

from freecad.maxproframe import create_end_miter_tool
from freecad.maxproframe.ff_tools import get_param_group

AUTO_PREVIEW = "Miter Auto Preview"

RECTANGLE = (
    ((0, 0, 0), (300, 0, 0)),
    ((300, 0, 0), (300, 200, 0)),
    ((300, 200, 0), (0, 200, 0)),
    ((0, 200, 0), (0, 0, 0)),
)
# Three profiles meet at the origin; the second and fourth also form a corner at (0, 200).
THREE_AT_ORIGIN = (
    ((200, 0, 0), (0, 0, 0)),
    ((0, 0, 0), (0, 200, 0)),
    ((0, 0, 0), (-200, 0, 0)),
    ((0, 200, 0), (200, 200, 0)),
)


def keep_auto_preview(test, value=None):
    """Restore the remembered check box state after ``test``; ``value`` None starts from the default."""
    param = get_param_group(writable=True)
    stored = AUTO_PREVIEW in param.GetBools()
    previous = param.GetBool(AUTO_PREVIEW, True)

    def restore():
        if stored:
            param.SetBool(AUTO_PREVIEW, previous)
        else:
            param.RemBool(AUTO_PREVIEW)

    test.addCleanup(restore)
    if value is None:
        param.RemBool(AUTO_PREVIEW)
    else:
        param.SetBool(AUTO_PREVIEW, value)


class TestEndMiterPreview(MiterFixture):
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

    def close_panels(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            try:
                Gui.Selection.removeObserver(panel)
            except Exception:
                pass
        QtWidgets.QApplication.processEvents()

    def profiles(self, edges):
        sketches = [self.make_sketch(edge) for edge in edges]
        members = [self.make_profile(sketch, "Edge1", **CENTER) for sketch in sketches]
        self.doc.clearUndos()
        return members

    def open_panel(self, members=()):
        panel = create_end_miter_tool.EndMiterTaskPanel(members)
        self.panels.append(panel)
        Gui.Selection.addObserver(panel)
        QtWidgets.QApplication.processEvents()
        return panel

    def run_command(self, members):
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
        return created[0]

    def trims(self):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "End Miter"]

    def trim_of(self, body):
        found = [obj for obj in self.trims() if obj.TrimmedBody == body]
        self.assertEqual(len(found), 1, body.Name)
        return found[0]

    def click(self, obj, sub="Face3", ctrl=False):
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
            QtWidgets.QApplication.processEvents()

    def selected(self):
        return {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}

    def test_update_automatically_is_checked_by_default_and_remembered(self):
        panel = self.open_panel()
        self.assertTrue(panel.form.cb_auto_update.isChecked())
        self.assertEqual(panel.form.cb_auto_update.text(), "Update automatically")
        panel.form.cb_auto_update.setChecked(False)
        panel.reject()
        self.assertFalse(get_param_group().GetBool(AUTO_PREVIEW, True))
        self.assertFalse(self.open_panel().form.cb_auto_update.isChecked())

    def test_checked_preview_follows_selection_extend_and_gap(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1])
        self.assertEqual(self.trims(), [])
        self.assertEqual(panel.form.status_label.text(), "No preview")
        self.click(p2)
        self.assertEqual(panel.members, [p1, p2])
        self.assertEqual({trim.TrimmedBody.Name for trim in self.trims()}, {p1.Name, p2.Name})
        self.assertEqual(panel.form.status_label.text(), "Preview updated")
        for trim in self.trims():
            self.assertEqual(trim.getStatusString(), "Valid")
            self.assertTrue(trim.MiterExtend)
        panel.form.sb_gap.setValue(0.5)
        panel.form.cb_extend.setChecked(False)
        self.assertEqual(len(self.trims()), 2)
        for profile in (p1, p2):
            trim = self.trim_of(profile)
            self.assertFalse(trim.MiterExtend)
            self.assertAlmostEqual(trim.MiterGap.Value, 0.5)
        self.assertAlmostEqual(self.trim_of(p1).Shape.distToShape(self.trim_of(p2).Shape)[0], 0.5, places=5)

    def test_removing_a_profile_removes_stale_previews_and_shows_it_again(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        self.assertEqual(len(self.trims()), 2)
        self.assertFalse(p1.ViewObject.Visibility)
        panel.form.members_list.item(1).setSelected(True)
        panel.remove_selected()
        self.assertEqual(panel.members, [p1])
        self.assertEqual(self.trims(), [])
        self.assertTrue(p1.ViewObject.Visibility)
        self.assertTrue(p2.ViewObject.Visibility)
        self.assertEqual(panel.form.status_label.text(), "No preview")

    def test_unchecked_keeps_the_preview_and_shows_pending_changes(self):
        p1, p2, p3, p4 = self.profiles(RECTANGLE)
        panel = self.open_panel([p1, p2])
        panel.form.cb_auto_update.setChecked(False)
        names = {trim.Name for trim in self.trims()}
        self.assertEqual(len(names), 2)
        self.assertEqual(panel.form.status_label.text(), "Preview updated")
        panel.form.sb_gap.setValue(1.0)
        self.click(p3)
        self.assertEqual(panel.members, [p1, p2, p3])
        self.assertEqual({trim.Name for trim in self.trims()}, names)
        for trim in self.trims():
            self.assertAlmostEqual(trim.MiterGap.Value, 0.0)
        self.assertEqual(panel.form.status_label.text(), "Pending changes")

    def test_checking_again_recalculates_the_preview(self):
        p1, p2, p3, _ = self.profiles(RECTANGLE)
        panel = self.open_panel([p1, p2])
        panel.form.cb_auto_update.setChecked(False)
        self.click(p3)
        panel.form.sb_gap.setValue(1.0)
        self.assertEqual(len(self.trims()), 2)
        panel.form.cb_auto_update.setChecked(True)
        self.assertEqual({trim.TrimmedBody.Name for trim in self.trims()}, {p1.Name, p2.Name, p3.Name})
        for trim in self.trims():
            self.assertAlmostEqual(trim.MiterGap.Value, 1.0)
        self.assertEqual(panel.form.status_label.text(), "Preview updated")

    def test_ok_with_pending_changes_commits_current_values_in_one_undo_step(self):
        members = self.profiles(RECTANGLE)
        panel = self.open_panel(members[:2])
        panel.form.cb_auto_update.setChecked(False)
        for member in members[2:]:
            self.click(member)
        panel.form.sb_gap.setValue(0.5)
        self.assertEqual(panel.form.status_label.text(), "Pending changes")
        self.assertTrue(panel.accept())
        self.assertEqual(len(self.trims()), 4)
        for profile in members:
            trim = self.trim_of(profile)
            self.assertEqual(trim.getStatusString(), "Valid")
            self.assertAlmostEqual(trim.MiterGap.Value, 0.5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.trims(), [])

    def test_ok_without_any_preview_creates_the_miters(self):
        p1, p2 = self.profiles(CHAINED)
        keep_auto_preview(self, False)
        panel = self.open_panel([p1, p2])
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.assertEqual(self.trims(), [])
        self.assertEqual(panel.form.status_label.text(), "Pending changes")
        self.assertTrue(panel.accept())
        self.assertEqual({trim.TrimmedBody.Name for trim in self.trims()}, {p1.Name, p2.Name})
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_removes_the_preview_and_leaves_the_document_unchanged(self):
        members = self.profiles(RECTANGLE)
        names = sorted(obj.Name for obj in self.doc.Objects)
        panel = self.run_command(members)
        self.assertEqual(len(self.trims()), 4)
        self.assertTrue(all(not member.ViewObject.Visibility for member in members))
        self.assertTrue(panel.reject())
        Gui.Control.closeDialog()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(sorted(obj.Name for obj in self.doc.Objects), names)
        self.assertTrue(all(member.ViewObject.Visibility for member in members))
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertEqual(panel.markers(), [])

    def test_clicking_a_preview_maps_to_its_profile(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        previews = {self.trim_of(p1).Name, self.trim_of(p2).Name}
        self.click(self.trim_of(p1))
        self.assertEqual(panel.members, [p1, p2])
        self.assertEqual(panel.form.members_list.count(), 2)
        self.assertEqual({trim.Name for trim in self.trims()}, previews)
        self.assertEqual(self.selected(), {name: () for name in previews})

    def test_ctrl_click_on_a_preview_drops_its_profile(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        self.click(self.trim_of(p1), ctrl=True)
        self.assertEqual(panel.members, [p2])
        self.assertEqual(self.trims(), [])
        self.assertTrue(p1.ViewObject.Visibility)
        self.assertEqual(self.selected(), {p2.Name: ()})

    def test_deselecting_a_preview_drops_its_profile(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        panel.removeSelection(self.doc.Name, self.trim_of(p2).Name, "Face3")
        QtWidgets.QApplication.processEvents()
        self.assertEqual(panel.members, [p1])
        self.assertEqual(self.trims(), [])

    def test_markers_show_joints_and_skipped_points(self):
        members = self.profiles(THREE_AT_ORIGIN)
        panel = self.open_panel(members)
        panel.form.cb_auto_update.setChecked(False)
        joint, skipped = create_end_miter_tool.JOINT_COLOR, create_end_miter_tool.SKIPPED_COLOR
        self.assertEqual(skipped, (1.0, 0.0, 0.0))
        self.assertNotEqual(joint, skipped)
        markers = panel.markers()
        self.assertEqual(len(markers), 2)
        found = {(round(p.x, 3) + 0.0, round(p.y, 3) + 0.0, round(p.z, 3) + 0.0): color for p, color in markers}
        self.assertEqual(found, {(0.0, 200.0, 0.0): joint, (0.0, 0.0, 0.0): skipped})
        # Markers follow the selection even when the preview is out of date.
        self.click(members[0], ctrl=True)
        self.assertEqual(panel.form.status_label.text(), "Pending changes")
        found = {(round(p.x, 3) + 0.0, round(p.y, 3) + 0.0, round(p.z, 3) + 0.0): color for p, color in panel.markers()}
        self.assertEqual(found, {(0.0, 200.0, 0.0): joint, (0.0, 0.0, 0.0): joint})
        panel.reject()
        self.assertEqual(panel.markers(), [])

    def test_markers_are_removed_on_ok(self):
        p1, p2 = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        self.assertEqual(len(panel.markers()), 1)
        self.assertTrue(panel.accept())
        self.assertEqual(panel.markers(), [])

    def test_markers_are_drawn_over_the_3d_view(self):
        try:
            scene = Gui.getDocument(self.doc.Name).ActiveView.getSceneGraph()
        except Exception:
            self.skipTest("no 3D view")
        p1, p2 = self.profiles(CHAINED)
        children = scene.getNumChildren()
        panel = self.open_panel([p1, p2])
        self.assertEqual(scene.getNumChildren(), children + 1)
        overlay = scene.getChild(children)
        self.assertEqual(overlay.getTypeId().getName(), "Annotation")
        self.assertTrue(panel.reject())
        self.assertEqual(scene.getNumChildren(), children)


if __name__ == "__main__":
    unittest.main()

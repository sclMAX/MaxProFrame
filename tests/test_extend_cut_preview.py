"""Extend / Cut panel: live preview of the trims, the Update automatically check box and the target/profile colors."""

import time
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtCore, QtWidgets
from test_extend_cut_geometry import NEAR
from test_extend_cut_panel import PanelFixture

from freecad.maxproframe import create_extend_cut_tool
from freecad.maxproframe.create_extend_cut_tool import HIGHLIGHT_COLORS, PROFILE, TARGET, ExtendCutTaskPanel
from freecad.maxproframe.create_notch_tool import NotchTaskPanel
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.trimmed_profile import TrimmedProfile

ORANGE = (1.0, 0.5, 0.0)
BLUE = (0.0, 0.4, 1.0)


def keep_auto_preview(test, panel_class, value=None):
    """Restore the remembered check box of ``panel_class`` after ``test``; ``value`` None starts from the default."""
    name = panel_class.auto_preview_param
    param = get_param_group(writable=True)
    stored = name in param.GetBools()
    previous = param.GetBool(name, True)

    def restore():
        if stored:
            param.SetBool(name, previous)
        else:
            param.RemBool(name)

    test.addCleanup(restore)
    if value is None:
        param.RemBool(name)
    else:
        param.SetBool(name, value)


def wait(seconds=0.6):
    # Lets the preview timer fire: processEvents alone does not wait for it.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def view_colors(objects):
    """ShapeColor, LineColor and Transparency of every object, by name."""
    return {
        obj.Name: (obj.ViewObject.ShapeColor, obj.ViewObject.LineColor, obj.ViewObject.Transparency) for obj in objects
    }


def scene_graph(test, doc):
    try:
        return Gui.getDocument(doc.Name).ActiveView.getSceneGraph()
    except Exception:
        test.skipTest("no 3D view")


def overlay_colors(node):
    """The color of every group of a highlight overlay node."""
    found = []
    for index in range(node.getNumChildren()):
        color = node.getChild(index).getChild(0).rgb[0].getValue()
        found.append(tuple(round(value, 3) for value in color))
    return found


class PreviewFixture(PanelFixture):
    def setUp(self):
        super().setUp()
        keep_auto_preview(self, ExtendCutTaskPanel)
        keep_auto_preview(self, NotchTaskPanel)

    def status(self, panel):
        return panel.form.status_label.text()

    def trim_of(self, body):
        found = [obj for obj in self.extend_cuts() if obj.TrimmedBody == body]
        self.assertEqual(len(found), 1, body.Name)
        return found[0]

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def setup_two(self):
        """A target and two profiles: the short one is extended to the near face, the long one cut."""
        target = self.target()
        short, long = self.profile(0, 300), self.profile(0, 500)
        self.doc.clearUndos()
        return target, self.near_face(target), short, long


class TestExtendCutPreview(PreviewFixture):
    def test_update_automatically_is_checked_by_default_and_remembered(self):
        panel = self.run_command()
        self.assertTrue(panel.form.cb_auto_update.isChecked())
        self.assertEqual(panel.form.cb_auto_update.text(), "Update automatically")
        self.assertEqual(panel.form.groupBox_preview.title(), "Preview")
        panel.form.cb_auto_update.setChecked(False)
        self.assertTrue(panel.reject())
        self.close_panels()
        param = get_param_group()
        self.assertFalse(param.GetBool(ExtendCutTaskPanel.auto_preview_param, True))
        # The Notch check box is remembered on its own.
        self.assertNotIn(NotchTaskPanel.auto_preview_param, get_param_group(writable=True).GetBools())
        self.assertFalse(self.run_command().form.cb_auto_update.isChecked())

    def test_opening_previews_the_trims_that_ok_keeps(self):
        target, face, short, long = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""), (long, ""))
        self.assertEqual(self.status(panel), "Preview updated")
        previews = {body.Name: self.trim_of(body) for body in (short, long)}
        for body, preview in zip((short, long), previews.values()):
            self.assertEqual(preview.getStatusString(), "Valid")
            self.assertEqual(preview.TrimmingBoundary, [(target, (face,))])
            self.assertAlmostEqual(preview.Shape.BoundBox.XMin, 0.0, places=5)
            self.assertAlmostEqual(preview.Shape.BoundBox.XMax, NEAR, places=5)
            self.assertFalse(body.ViewObject.Visibility)
        volumes = {name: obj.Shape.Volume for name, obj in previews.items()}
        self.assertTrue(panel.accept())
        self.assertEqual(sorted(obj.Name for obj in self.extend_cuts()), sorted(obj.Name for obj in previews.values()))
        for name, obj in previews.items():
            self.assertAlmostEqual(obj.Shape.Volume, volumes[name], places=5)
            self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), names)

    def test_checked_changes_recompute_the_preview_once_they_pause(self):
        target, face, short, long = self.setup_two()
        panel = self.run_command((target, face), (short, ""))
        self.assertEqual(len(self.extend_cuts()), 1)
        with patch.object(panel, "_rebuild_preview", wraps=panel._rebuild_preview) as rebuild:
            self.click(long, "Face1")
            panel.form.sb_gap.setValue(1.0)
            panel.form.sb_gap.setValue(2.0)
            self.assertEqual(rebuild.call_count, 0)
            self.assertEqual(self.status(panel), "Pending changes")
            wait()
            self.assertEqual(rebuild.call_count, 1)
        self.assertEqual(self.status(panel), "Preview updated")
        for body in (short, long):
            self.assertAlmostEqual(self.trim_of(body).TrimGap.Value, 2.0)
            self.assertAlmostEqual(self.trim_of(body).Shape.BoundBox.XMax, NEAR - 2.0, places=5)
        # Ctrl+click drops a profile: its preview goes and the profile shows again.
        self.click(short, "Face1", ctrl=True)
        wait()
        self.assertEqual([obj.TrimmedBody for obj in self.extend_cuts()], [long])
        self.assertTrue(short.ViewObject.Visibility)
        # So does the Remove button.
        panel.form.profiles_list.item(0).setSelected(True)
        panel.remove_selected()
        wait()
        self.assertEqual(self.extend_cuts(), [])
        self.assertTrue(long.ViewObject.Visibility)
        self.assertEqual(self.status(panel), "No preview")

    def test_unchecked_keeps_the_preview_and_shows_pending_changes(self):
        target, face, short, long = self.setup_two()
        panel = self.run_command((target, face), (short, ""))
        panel.form.cb_auto_update.setChecked(False)
        names = self.names()
        with patch.object(panel, "_rebuild_preview", wraps=panel._rebuild_preview) as rebuild:
            self.click(long, "Face1")
            panel.form.sb_gap.setValue(1.0)
            wait()
            rebuild.assert_not_called()
        self.assertEqual(panel.profiles, [short, long])
        self.assertEqual(self.names(), names)
        self.assertAlmostEqual(self.trim_of(short).TrimGap.Value, 0.0)
        self.assertTrue(long.ViewObject.Visibility)
        self.assertEqual(self.status(panel), "Pending changes")

    def test_checking_again_recomputes_the_preview(self):
        target, face, short, long = self.setup_two()
        panel = self.run_command((target, face), (short, ""))
        panel.form.cb_auto_update.setChecked(False)
        self.click(long, "Face1")
        panel.form.sb_gap.setValue(1.0)
        wait()
        panel.form.cb_auto_update.setChecked(True)
        self.assertEqual({obj.TrimmedBody.Name for obj in self.extend_cuts()}, {short.Name, long.Name})
        for obj in self.extend_cuts():
            self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
            self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 1.0, places=5)
        self.assertEqual(self.status(panel), "Preview updated")

    def test_ok_with_pending_changes_creates_the_current_values_in_one_undo_step(self):
        target, face, short, long = self.setup_two()
        panel = self.run_command((target, face), (short, ""))
        panel.form.cb_auto_update.setChecked(False)
        self.click(long, "Face1")
        panel.form.sb_gap.setValue(2.0)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.assertEqual({obj.TrimmedBody.Name for obj in self.extend_cuts()}, {short.Name, long.Name})
        for obj in self.extend_cuts():
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
            self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 2.0, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.extend_cuts(), [])

    def test_ok_right_after_a_change_keeps_it(self):
        target, face, short, _ = self.setup_two()
        panel = self.run_command((target, face), (short, ""))
        panel.form.sb_gap.setValue(0.7)
        self.assertTrue(panel.accept())
        wait(0.4)
        (obj,) = self.extend_cuts()
        self.assertAlmostEqual(obj.TrimGap.Value, 0.7)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_removes_the_preview_and_leaves_the_document_unchanged(self):
        target, face, short, long = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""), (long, ""))
        self.assertEqual(len(self.extend_cuts()), 2)
        self.assertTrue(panel.reject())
        Gui.Control.closeDialog()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility)
        self.assertTrue(long.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_without_undo_removes_the_preview(self):
        self.doc.UndoMode = 0
        target, face, short, _ = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""))
        self.assertEqual(len(self.extend_cuts()), 1)
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility)

    def test_closing_the_dialog_without_ok_or_cancel_leaves_the_document_unchanged(self):
        target, face, short, long = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""), (long, ""))
        self.assertEqual(len(self.extend_cuts()), 2)
        panel.closed()
        self.assertTrue(panel._closed)
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility and long.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertEqual(panel.highlights(), [])

    def test_freecad_dropping_the_form_stops_the_panel(self):
        # FreeCAD can close the task dialog without OK, Cancel or closed(), and then sets form to None.
        target, face, short, long = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""))
        panel.form.sb_gap.setValue(0.4)
        Gui.Control.closeDialog()
        QtWidgets.QApplication.processEvents()
        panel.form = None
        with patch.object(panel, "_rebuild_preview") as rebuild:
            self.click(long, "Face1")
            wait()
        rebuild.assert_not_called()
        self.assertTrue(panel._closed)
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_deleting_the_panel_form_cleans_up(self):
        target, face, short, _ = self.setup_two()
        names = self.names()
        panel = ExtendCutTaskPanel([(target, (face,)), (short, ())])
        self.panels.append(panel)
        self.assertEqual(len(self.extend_cuts()), 1)
        panel.form.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(panel._closed)
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility)
        self.assertEqual(panel.highlights(), [])

    def test_a_failing_preview_creates_nothing_and_ok_keeps_the_panel_open(self):
        tube = self.doc.addObject("Part::Feature", "Tube")
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(400, 0, -50))
        lateral = next(
            f"Face{index}"
            for index, face in enumerate(tube.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        body = self.profile(0, 300)
        self.doc.recompute()
        self.doc.clearUndos()
        names = self.names()
        panel = self.run_command((tube, lateral), (body, ""))
        error = f"the target face {lateral} of {tube.Label} is not planar"
        self.assertEqual(self.names(), names)
        self.assertIn(error, self.message(panel))
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(body.ViewObject.Visibility)
        self.assertFalse(panel.accept())
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIn(error, self.message(panel))
        self.assertEqual(self.names(), names)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(body.ViewObject.Visibility)

    def test_ok_with_a_trim_that_fails_to_recompute_keeps_the_panel_open(self):
        target, face, short, _ = self.setup_two()
        names = self.names()
        panel = self.run_command((target, face), (short, ""))
        self.assertEqual(self.status(panel), "Preview updated")
        # FreeCAD caches execute when the proxy is set: break a method that execute looks up instead.
        with patch.object(TrimmedProfile, "extend_cut_plane", side_effect=RuntimeError("broken trim")):
            panel.form.sb_gap.setValue(0.5)
            self.assertFalse(panel.accept())
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.names(), names)
        self.assertTrue(short.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertIn("broken trim", self.message(panel))
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.assertEqual([obj.TrimmedBody for obj in self.extend_cuts()], [short])
        self.assertEqual(self.doc.UndoCount, 1)

    def test_clicking_a_preview_trim_stands_for_its_profile(self):
        target, face, short, long = self.setup_two()
        panel = self.run_command((target, face), (short, ""), (long, ""))
        previews = sorted(obj.Name for obj in self.extend_cuts())
        self.click(self.trim_of(short), "Face1")
        wait()
        self.assertEqual(panel.profiles, [short, long])
        self.assertEqual(panel.form.profiles_list.count(), 2)
        self.assertEqual(sorted(obj.Name for obj in self.extend_cuts()), previews)
        self.assertEqual(self.message(panel), "")
        self.click(self.trim_of(short), "Face2", ctrl=True)
        self.assertEqual(panel.profiles, [long])
        wait()
        self.assertEqual([obj.TrimmedBody for obj in self.extend_cuts()], [long])
        self.assertTrue(short.ViewObject.Visibility)


class TestExtendCutColors(PreviewFixture):
    def test_the_panel_says_which_color_is_which(self):
        panel = self.run_command()
        self.assertEqual(panel.form.colors_label.text(), "Target in orange, profiles in blue.")
        self.assertEqual(HIGHLIGHT_COLORS[TARGET], ORANGE)
        self.assertEqual(HIGHLIGHT_COLORS[PROFILE], BLUE)

    def test_target_and_profiles_are_highlighted_while_open_and_restored_after_ok(self):
        target, face, short, long = self.setup_two()
        before = view_colors((target, short, long))
        panel = self.run_command((target, face), (short, ""))
        panel.form.cb_auto_update.setChecked(False)
        self.click(long, "Face1")
        # A previewed profile is shown by its preview trim, a pending one by itself.
        self.assertEqual(
            panel.highlights(), [(target, face, TARGET), (self.trim_of(short), "", PROFILE), (long, "", PROFILE)]
        )
        self.assertEqual(view_colors((target, short, long)), before)
        self.assertTrue(panel.accept())
        self.assertEqual(panel.highlights(), [])
        self.assertEqual(view_colors((target, short, long)), before)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_highlighting_leaves_colors_and_undo_unchanged_after_cancel(self):
        target, face, short, long = self.setup_two()
        before = view_colors((target, short, long))
        panel = self.run_command((target, ""), (short, ""), (long, ""))
        self.assertEqual(
            panel.highlights(),
            [(target, "", TARGET), (self.trim_of(short), "", PROFILE), (self.trim_of(long), "", PROFILE)],
        )
        self.assertTrue(panel.reject())
        self.assertEqual(panel.highlights(), [])
        self.assertEqual(view_colors((target, short, long)), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_highlights_are_drawn_over_the_3d_view_in_two_colors(self):
        scene = scene_graph(self, self.doc)
        target, face, short, _ = self.setup_two()
        children = scene.getNumChildren()
        panel = self.run_command((target, face), (short, ""))
        self.assertEqual(scene.getNumChildren(), children + 1)
        overlay = scene.getChild(children)
        self.assertEqual(overlay.getTypeId().getName(), "Annotation")
        self.assertEqual(overlay_colors(overlay), [ORANGE, BLUE])
        self.assertTrue(panel.reject())
        self.assertEqual(scene.getNumChildren(), children)

    def test_highlights_follow_the_clicks_after_the_selection_dispatch(self):
        scene = scene_graph(self, self.doc)
        target, face, short, _ = self.setup_two()
        children = scene.getNumChildren()
        panel = self.run_command()
        self.assertEqual(scene.getNumChildren(), children)
        Gui.Selection.addSelection(self.doc.Name, target.Name, face)
        self.assertEqual(scene.getNumChildren(), children)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(scene.getNumChildren(), children + 1)
        self.assertEqual(overlay_colors(scene.getChild(children)), [ORANGE])
        self.click(short, "Face1")
        self.assertEqual(scene.getNumChildren(), children + 1)
        self.assertEqual(overlay_colors(scene.getChild(children)), [ORANGE, BLUE])
        self.assertEqual(panel.highlights(), [(target, face, TARGET), (short, "", PROFILE)])

    def test_editing_highlights_the_target_and_the_edited_trim_without_a_preview(self):
        target, face, short, _ = self.setup_two()
        obj = create_extend_cut_tool.make_extend_cut_profile(short, (target, (face,)))
        self.doc.recompute()
        self.doc.clearUndos()
        before = view_colors((target, short, obj))
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertFalse(panel.form.groupBox_preview.isVisibleTo(panel.form))
        self.assertEqual(panel.highlights(), [(target, face, TARGET), (obj, "", PROFILE)])
        self.assertTrue(panel.reject())
        self.assertEqual(panel.highlights(), [])
        self.assertEqual(view_colors((target, short, obj)), before)
        self.assertEqual(self.doc.UndoCount, 0)


class TestExtendCutPreviewTranslations(PreviewFixture):
    def test_preview_and_colors_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.groupBox_preview.title(), "Previsualización")
        self.assertEqual(form.cb_auto_update.text(), "Actualizar automáticamente")
        self.assertEqual(form.colors_label.text(), "Destino en naranja, perfiles en azul.")
        self.assertEqual(form.status_label.text(), "Sin previsualización")


if __name__ == "__main__":
    unittest.main()

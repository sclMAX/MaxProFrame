"""Notch panel: the preview is off by default and remembered on its own, previews match OK, colors and clicks."""

import unittest

from miter_helpers import use_language
from test_extend_cut_preview import BLUE, ORANGE, keep_auto_preview, overlay_colors, scene_graph, view_colors, wait
from test_notch_geometry import HALF
from test_notch_panel import NotchPanelFixture

from freecad.maxproframe.create_extend_cut_tool import PROFILE, TARGET, ExtendCutTaskPanel
from freecad.maxproframe.create_notch_tool import NotchTaskPanel
from freecad.maxproframe.ff_tools import get_param_group


class NotchPreviewFixture(NotchPanelFixture):
    def setUp(self):
        super().setUp()
        keep_auto_preview(self, NotchTaskPanel)
        keep_auto_preview(self, ExtendCutTaskPanel)

    def status(self, panel):
        return panel.form.status_label.text()

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def setup_joint(self):
        trimmed, boundary = self.t_joint()
        self.doc.clearUndos()
        return trimmed, boundary


class TestNotchPreview(NotchPreviewFixture):
    def test_update_automatically_is_unchecked_by_default_and_remembered_apart_from_extend_cut(self):
        panel = self.run_command()
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.assertNotEqual(NotchTaskPanel.auto_preview_param, ExtendCutTaskPanel.auto_preview_param)
        panel.form.cb_auto_update.setChecked(True)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertTrue(get_param_group().GetBool(NotchTaskPanel.auto_preview_param, False))
        self.assertNotIn(ExtendCutTaskPanel.auto_preview_param, get_param_group(writable=True).GetBools())
        self.assertTrue(self.run_command().form.cb_auto_update.isChecked())

    def test_unchecked_by_default_nothing_is_computed_and_ok_creates_the_notches(self):
        trimmed, boundary = self.setup_joint()
        names = self.names()
        panel = self.run_command((boundary, ""), (trimmed, ""))
        wait()
        self.assertEqual(self.names(), names)
        self.assertTrue(trimmed.ViewObject.Visibility)
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        (trim,) = self.trims()
        self.assertEqual(trim.getStatusString(), "Valid")
        self.assertAlmostEqual(trim.Shape.BoundBox.XMin, HALF, places=5)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_checked_previews_the_notch_that_ok_keeps(self):
        trimmed, boundary = self.setup_joint()
        keep_auto_preview(self, NotchTaskPanel, True)
        panel = self.run_command((boundary, ""), (trimmed, ""))
        self.assertEqual(self.status(panel), "Preview updated")
        (preview,) = self.trims()
        self.assertEqual(preview.TrimmedProfileType, "Notch")
        self.assertAlmostEqual(preview.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(preview.Shape.common(boundary.Shape).Volume, 0.0, places=5)
        self.assertFalse(trimmed.ViewObject.Visibility)
        volume = preview.Shape.Volume
        self.assertTrue(panel.accept())
        self.assertEqual([obj.Name for obj in self.trims()], [preview.Name])
        self.assertAlmostEqual(preview.Shape.Volume, volume, places=5)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_removes_the_preview_and_leaves_the_document_unchanged(self):
        trimmed, boundary = self.setup_joint()
        keep_auto_preview(self, NotchTaskPanel, True)
        names = self.names()
        panel = self.run_command((boundary, ""), (trimmed, ""))
        self.assertEqual(len(self.trims()), 1)
        self.assertTrue(panel.reject())
        self.assertEqual(self.names(), names)
        self.assertTrue(trimmed.ViewObject.Visibility)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_clicking_a_preview_notch_stands_for_its_profile(self):
        trimmed, boundary = self.setup_joint()
        keep_auto_preview(self, NotchTaskPanel, True)
        panel = self.run_command((boundary, ""), (trimmed, ""))
        (preview,) = self.trims()
        self.click(preview, "Face1")
        wait()
        self.assertEqual(panel.profiles, [trimmed])
        self.assertEqual(panel.target, (boundary, ()))
        self.assertEqual([obj.Name for obj in self.trims()], [preview.Name])
        self.click(preview, "Face2", ctrl=True)
        wait()
        self.assertEqual(panel.profiles, [])
        self.assertEqual(self.trims(), [])
        self.assertTrue(trimmed.ViewObject.Visibility)


class TestNotchColors(NotchPreviewFixture):
    def test_target_and_profiles_are_highlighted_and_colors_are_restored(self):
        scene = scene_graph(self, self.doc)
        trimmed, boundary = self.setup_joint()
        before = view_colors((trimmed, boundary))
        children = scene.getNumChildren()
        panel = self.run_command((boundary, ""), (trimmed, ""))
        self.assertEqual(panel.form.colors_label.text(), "Target in orange, profiles in blue.")
        self.assertEqual(panel.highlights(), [(boundary, "", TARGET), (trimmed, "", PROFILE)])
        self.assertEqual(scene.getNumChildren(), children + 1)
        self.assertEqual(overlay_colors(scene.getChild(children)), [ORANGE, BLUE])
        self.assertTrue(panel.reject())
        self.assertEqual(scene.getNumChildren(), children)
        self.assertEqual(view_colors((trimmed, boundary)), before)
        self.assertEqual(self.doc.UndoCount, 0)


class TestNotchPreviewTranslations(NotchPreviewFixture):
    def test_preview_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command()
        self.assertEqual(panel.form.cb_auto_update.text(), "Actualizar automáticamente")
        self.assertEqual(panel.form.colors_label.text(), "Destino en naranja, perfiles en azul.")
        self.assertEqual(panel.form.status_label.text(), "Sin previsualización")


if __name__ == "__main__":
    unittest.main()

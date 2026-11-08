"""Cutout depth panel: the checkable Pattern group, its title, its expressions and its warnings."""

import time
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_cutout_depth_panel import DepthPanelFixture
from test_cutout_flow import WALL
from test_drill_hole_panel import RecomputeCounter

from freecad.maxproframe import extruded_cutout

PATTERN_FIELDS = (
    ("spin_backward_count", "AlongBackwardCount"),
    ("spin_backward_pitch", "AlongBackwardPitch"),
    ("spin_forward_count", "AlongForwardCount"),
    ("spin_forward_pitch", "AlongForwardPitch"),
)
PAST_THE_FACE = "A cutout reaches past the end of the face."
SQUARE_FACE = "Cutout / Hole: the face is square to the profile axis, the pattern has no direction."


class PatternPanelFixture(DepthPanelFixture):
    def new_panel(self):
        """(body, cutout, panel) of a new cutout: a circle of radius 5 mm at the middle of the tube's top face."""
        body, sketch, cutout, _ = self.new_cutout()
        return body, cutout, self.depth_panels[0]

    def set_pattern(self, panel, backward=None, forward=None):
        form = panel.form
        form.groupBox_pattern.setChecked(True)
        for side, values in (("backward", backward), ("forward", forward)):
            if values is not None:
                getattr(form, f"spin_{side}_count").setValue(values[0])
                getattr(form, f"spin_{side}_pitch").setValue(values[1])
        self.events()

    def cut(self, body, cutout):
        """Number of holes of the one wall cut of ``cutout``."""
        return round((body.Shape.Volume - cutout.Shape.Volume) / self.hole(WALL), 3)

    def warning(self, panel):
        label = panel.form.warning_label
        return label.text() if not label.isHidden() else ""

    def wait_until(self, condition, seconds=5.0):
        """Process events until ``condition()`` holds; fail the test if it never does."""
        deadline = time.monotonic() + seconds
        while not condition():
            if time.monotonic() > deadline:
                self.fail(f"Condition not met within {seconds} s.")
            QtWidgets.QApplication.processEvents()
            time.sleep(0.01)

    def slots(self, value):
        """A VarSet with an integer ``Slots`` property set to ``value``."""
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyInteger", "Slots")
        varset.Slots = value
        return varset


class TestCutoutPatternPanel(PatternPanelFixture):
    def test_a_new_cutout_opens_with_the_pattern_unchecked_and_its_fields_hidden(self):
        body, cutout, panel = self.new_panel()
        form = panel.form
        self.assertTrue(form.groupBox_pattern.isCheckable())
        self.assertFalse(form.groupBox_pattern.isChecked())
        self.assertEqual(form.groupBox_pattern.title(), "Pattern")
        self.assertTrue(form.pattern_fields.isHidden())
        self.assertEqual([getattr(form, name).value() for name, _ in PATTERN_FIELDS], [0, 50.0, 0, 50.0])
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Cutouts per side", "Pitch")
        )
        self.assertEqual((form.label_backward.text(), form.label_forward.text()), ("← Backward", "Forward →"))
        self.assertEqual(self.cut(body, cutout), 1)
        self.assertEqual(self.warning(panel), "")

    def test_one_backward_every_50_and_two_forward_every_30_make_four_cutouts_titled_by_the_total(self):
        """S1, S2: "<- 1@50mm (croquis) 2@30mm" and "Patrón: 4 calados"."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, backward=(1, 50.0), forward=(2, 30.0))
        self.assertFalse(panel.form.pattern_fields.isHidden())
        self.assertEqual(panel.form.groupBox_pattern.title(), "Pattern: 4 cutouts")
        self.assertEqual(self.cut(body, cutout), 4)
        self.assertEqual(self.warning(panel), "")
        self.assertTrue(panel.accept())
        self.assertEqual([getattr(cutout, prop) for _, prop in PATTERN_FIELDS][::2], [1, 2])
        self.assertEqual((cutout.AlongBackwardPitch.Value, cutout.AlongForwardPitch.Value), (50.0, 30.0))
        self.assertEqual(self.cut(body, cutout), 4)

    def test_checked_with_no_count_the_title_is_one_cutout(self):
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel)
        self.assertEqual(panel.form.groupBox_pattern.title(), "Pattern: 1 cutout")
        self.assertEqual(self.cut(body, cutout), 1)

    def test_unchecking_cuts_the_sketch_alone_and_keeps_the_field_values(self):
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, backward=(1, 50.0), forward=(2, 30.0))
        panel.form.groupBox_pattern.setChecked(False)
        self.events()
        form = panel.form
        self.assertEqual(form.groupBox_pattern.title(), "Pattern")
        self.assertTrue(form.pattern_fields.isHidden())
        self.assertEqual([getattr(form, name).value() for name, _ in PATTERN_FIELDS], [1, 50.0, 2, 30.0])
        self.assertEqual((cutout.AlongBackwardCount, cutout.AlongForwardCount), (0, 0))
        self.assertEqual(self.cut(body, cutout), 1)

    def test_an_edited_cutout_with_a_pattern_opens_checked_and_cancel_restores_it(self):
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, backward=(1, 50.0), forward=(2, 30.0))
        self.assertTrue(panel.accept())
        panel = self.edit_cutout(cutout)
        form = panel.form
        self.assertTrue(form.groupBox_pattern.isChecked())
        self.assertFalse(form.pattern_fields.isHidden())
        self.assertEqual(form.groupBox_pattern.title(), "Pattern: 4 cutouts")
        self.assertEqual([getattr(form, name).value() for name, _ in PATTERN_FIELDS], [1, 50.0, 2, 30.0])
        form.spin_forward_count.setValue(5)
        self.events()
        self.assertEqual(self.cut(body, cutout), 7)
        self.assertTrue(panel.reject())
        self.assertEqual((cutout.AlongBackwardCount, cutout.AlongForwardCount), (1, 2))
        self.assertEqual(self.cut(body, cutout), 4)

    def test_every_pattern_field_is_bound_and_shows_an_expression(self):
        """S4: the Fx icon on each field; an expression drives the count and the title follows."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel)
        for name, _ in PATTERN_FIELDS:
            with self.subTest(field=name):
                self.assertTrue(Gui.ExpressionBinding(getattr(panel.form, name)).isBound())
                field = getattr(panel.form, name)
                self.assertEqual(field.minimumWidth(), field.maximumWidth())
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyInteger", "Slots")
        varset.Slots = 3
        cutout.setExpression("AlongForwardCount", f"{varset.Name}.Slots")
        self.doc.recompute()
        self.events()
        self.assertEqual(panel.form.spin_forward_count.value(), 3)
        panel.form.spin_backward_count.setValue(1)
        self.events()
        self.assertEqual(panel.form.groupBox_pattern.title(), "Pattern: 5 cutouts")
        self.assertTrue(panel.accept())
        self.assertEqual(dict(cutout.ExpressionEngine).get("AlongForwardCount"), f"{varset.Name}.Slots")
        self.assertEqual(self.cut(body, cutout), 5)

    def test_unchecking_removes_an_expression_on_a_count_and_cancel_brings_it_back(self):
        """S3 with S4: unchecked, the sketch alone is cut even when an expression drove a count."""
        body, cutout, panel = self.new_panel()
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyInteger", "Slots")
        varset.Slots = 3
        self.set_pattern(panel)
        cutout.setExpression("AlongForwardCount", f"{varset.Name}.Slots")
        self.doc.recompute()
        self.assertTrue(panel.accept())
        self.assertEqual(self.cut(body, cutout), 4)
        panel = self.edit_cutout(cutout)
        panel.form.groupBox_pattern.setChecked(False)
        self.events()
        self.assertNotIn("AlongForwardCount", dict(cutout.ExpressionEngine))
        self.assertEqual(cutout.AlongForwardCount, 0)
        self.assertEqual(self.cut(body, cutout), 1)
        self.assertTrue(panel.reject())
        self.assertEqual(dict(cutout.ExpressionEngine).get("AlongForwardCount"), f"{varset.Name}.Slots")
        self.assertEqual(self.cut(body, cutout), 4)

    def test_a_count_expression_at_zero_opens_checked_and_survives_ok(self):
        """An expression on a count is a pattern the user set up, even while it evaluates to 0."""
        body, cutout, panel = self.new_panel()
        varset = self.slots(0)
        self.set_pattern(panel)
        cutout.setExpression("AlongForwardCount", f"{varset.Name}.Slots")
        self.doc.recompute()
        self.assertTrue(panel.accept())
        panel = self.edit_cutout(cutout)
        self.assertTrue(panel.form.groupBox_pattern.isChecked())
        self.assertFalse(panel.form.pattern_fields.isHidden())
        panel.form.spin_depth.setValue(panel.form.spin_depth.value() + 1.0)
        self.events()
        self.assertTrue(panel.accept())
        self.assertEqual(dict(cutout.ExpressionEngine).get("AlongForwardCount"), f"{varset.Name}.Slots")
        varset.Slots = 2
        self.doc.recompute()
        self.assertEqual(self.cut(body, cutout), 3)

    def test_overlapping_cutouts_give_no_warning(self):
        """L7: a sketch may be meant to overlap its copies, and the panel shows them: no overlap warning."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, backward=(1, 8.0), forward=(2, 8.0))
        self.assertEqual(self.warning(panel), "")
        self.assertTrue(panel.accept())
        self.assertEqual(cutout.getStatusString(), "Valid")

    def test_a_cutout_past_the_end_of_the_face_warns(self):
        """S5: the face runs from x = -50 to 350 and the sketch is at x = 150."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, forward=(3, 60.0))
        self.assertEqual(self.warning(panel), "")
        panel.form.spin_forward_count.setValue(4)
        self.events()
        self.assertEqual(self.warning(panel), PAST_THE_FACE)
        panel.form.groupBox_pattern.setChecked(False)
        self.events()
        self.assertEqual(self.warning(panel), "")

    def test_a_cutout_past_the_start_of_the_face_warns(self):
        """S5 backward: 4 x 60 mm back from x = 150 reaches x = -90, past the face start at x = -50."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, backward=(3, 60.0))
        self.assertEqual(self.warning(panel), "")
        panel.form.spin_backward_count.setValue(4)
        self.events()
        self.assertEqual(self.warning(panel), PAST_THE_FACE)
        panel.form.spin_backward_count.setValue(3)
        self.events()
        self.assertEqual(self.warning(panel), "")

    def test_a_pattern_on_an_end_face_warns_that_it_has_no_direction(self):
        """The face is square to the profile axis: copies warn why they are not cut, the sketch alone does not."""
        body, cutout, panel = self.new_panel()
        cutout.baseObject = (body, [self.face_towards(body, App.Vector(1, 0, 0))])
        self.set_pattern(panel, forward=(2, 30.0))
        self.assertEqual(self.warning(panel), SQUARE_FACE)
        self.assertNotEqual(cutout.getStatusString(), "Valid")
        panel.form.spin_forward_count.setValue(0)
        self.events()
        self.assertEqual(self.warning(panel), "")


class TestCutoutPatternPreview(PatternPanelFixture):
    """A pitch typed while the preview recomputes: no recompute inside another, the last values win."""

    def hook_execute(self):
        """Hooks run once each, after the next cutout recomputes; call it before the cutout is made."""
        execute = extruded_cutout.ExtrudedCutout.execute
        hooks = []

        def execute_and_hook(proxy, fp):
            result = execute(proxy, fp)
            if hooks:
                hooks.pop(0)(fp)
            return result

        patcher = patch.object(extruded_cutout.ExtrudedCutout, "execute", execute_and_hook)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hooks

    def counted_panel(self):
        hooks = self.hook_execute()
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, forward=(2, 30.0))
        counter = RecomputeCounter(panel.doc)
        panel.doc = counter
        return hooks, body, cutout, panel, counter

    def test_a_pitch_typed_during_a_recompute_is_cut_in_the_end_without_a_nested_recompute(self):
        hooks, body, cutout, panel, counter = self.counted_panel()

        def type_pitch(fp):
            panel.form.spin_forward_pitch.setValue(40.0)
            self.events()

        hooks.append(type_pitch)
        panel.form.spin_forward_pitch.setValue(35.0)
        self.wait_until(lambda: not panel._recomputing and not hooks)
        self.assertEqual(counter.nested, 0)
        self.assertAlmostEqual(cutout.AlongForwardPitch.Value, 40.0, places=6)
        self.assertEqual(self.cut(body, cutout), 3)
        center = body.Shape.getElement(self.face_towards(body, App.Vector(0, 0, 1))).CenterOfMass
        for offset, cut in ((40.0, True), (80.0, True), (35.0, False), (70.0, False)):
            with self.subTest(offset=offset):
                inside = cutout.Shape.isInside(center + App.Vector(offset, 0, -WALL / 2), 1e-7, True)
                self.assertEqual(not inside, cut)

    def test_ok_pressed_during_a_recompute_keeps_the_last_values_once_it_ends(self):
        hooks, body, cutout, panel, counter = self.counted_panel()
        returned = []

        def press(fp):
            panel.form.spin_forward_pitch.setValue(40.0)
            returned.append(panel.accept())

        hooks.append(press)
        panel.form.spin_forward_pitch.setValue(35.0)
        self.wait_until(lambda: not Gui.Control.activeDialog())
        self.assertEqual(returned, [False])
        self.assertEqual(counter.nested, 0)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertAlmostEqual(cutout.AlongForwardPitch.Value, 40.0, places=6)
        self.assertEqual(self.cut(body, cutout), 3)

    def test_ok_pressed_during_a_recompute_still_closes_when_the_warnings_fail(self):
        """An error while the panel updates its warnings never strands the OK pressed meanwhile."""
        hooks, body, cutout, panel, counter = self.counted_panel()

        def press(fp):
            returned.append(panel.accept())

        returned = []
        hooks.append(press)
        with patch.object(panel, "_pattern_warnings", side_effect=RuntimeError("lookup failed")):
            try:
                panel.form.spin_forward_pitch.setValue(35.0)
            except RuntimeError:
                pass
            self.wait_until(lambda: not Gui.Control.activeDialog())
        self.assertEqual(returned, [False])
        self.assertFalse(Gui.Control.activeDialog())
        self.assertAlmostEqual(cutout.AlongForwardPitch.Value, 35.0, places=6)

    def test_a_pitch_typed_during_the_ok_recompute_is_kept_without_a_nested_recompute(self):
        hooks, body, cutout, panel, counter = self.counted_panel()

        def type_pitch(fp):
            panel.form.spin_forward_pitch.setValue(40.0)
            self.events()

        hooks.append(type_pitch)
        # Something else changed meanwhile: the OK recompute runs the cutout again.
        cutout.touch()
        self.assertTrue(panel.accept())
        self.assertEqual(hooks, [])
        self.assertEqual(counter.nested, 0)
        self.assertAlmostEqual(cutout.AlongForwardPitch.Value, 40.0, places=6)
        self.assertEqual(self.cut(body, cutout), 3)


class TestCutoutPatternPanelSpanish(PatternPanelFixture):
    def test_the_pattern_group_and_its_messages_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        body, cutout, panel = self.new_panel()
        form = panel.form
        self.assertEqual(form.groupBox_pattern.title(), "Patrón")
        self.assertEqual(
            (form.label_pattern_count.text(), form.label_pattern_pitch.text()), ("Calados por lado", "Paso")
        )
        self.assertEqual((form.label_backward.text(), form.label_forward.text()), ("← Atrás", "Adelante →"))
        self.set_pattern(panel)
        self.assertEqual(form.groupBox_pattern.title(), "Patrón: 1 calado")
        self.set_pattern(panel, backward=(1, 50.0), forward=(2, 8.0))
        self.assertEqual(form.groupBox_pattern.title(), "Patrón: 4 calados")
        self.assertEqual(self.warning(panel), "")
        form.spin_forward_pitch.setValue(60.0)
        form.spin_forward_count.setValue(4)
        self.events()
        self.assertEqual(self.warning(panel), "Un calado sobrepasa el extremo de la cara.")


if __name__ == "__main__":
    unittest.main()

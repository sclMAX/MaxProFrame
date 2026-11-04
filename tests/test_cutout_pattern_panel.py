"""Cutout depth panel: the checkable Pattern group, its title, its expressions and its warnings."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from test_cutout_depth_panel import DepthPanelFixture
from test_cutout_flow import WALL

PATTERN_FIELDS = (
    ("spin_backward_count", "AlongBackwardCount"),
    ("spin_backward_pitch", "AlongBackwardPitch"),
    ("spin_forward_count", "AlongForwardCount"),
    ("spin_forward_pitch", "AlongForwardPitch"),
)
OVERLAP = "The cutouts overlap: the pitch (8 mm) is smaller than the sketch along the profile (10 mm)."
PAST_THE_FACE = "A cutout reaches past the end of the face."


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

    def test_a_pitch_smaller_than_the_sketch_warns_without_stopping_ok(self):
        """S5: the circle is 10 mm long along the profile."""
        body, cutout, panel = self.new_panel()
        self.set_pattern(panel, forward=(2, 8.0))
        self.assertEqual(self.warning(panel), OVERLAP)
        panel.form.spin_forward_pitch.setValue(10.0)
        self.events()
        self.assertEqual(self.warning(panel), "")
        panel.form.spin_backward_count.setValue(1)
        panel.form.spin_backward_pitch.setValue(8.0)
        self.events()
        self.assertEqual(self.warning(panel), OVERLAP)
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
        self.assertEqual(
            self.warning(panel),
            "Los calados se superponen: el paso (8 mm) es menor que el croquis a lo largo del perfil (10 mm).",
        )
        form.spin_forward_pitch.setValue(60.0)
        form.spin_forward_count.setValue(4)
        self.events()
        self.assertEqual(self.warning(panel), "Un calado sobrepasa el extremo de la cara.")


if __name__ == "__main__":
    unittest.main()

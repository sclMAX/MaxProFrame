"""Edit Profile fields take FreeCAD expressions (Fx), each bound to the edited profile's property."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.expression_fields import expressions_of
from freecad.maxproframe.profile import Profile, ViewProviderProfile

FIELDS = {
    "sb_width": "ProfileWidth",
    "sb_height": "ProfileHeight",
    "sb_main_thickness": "Thickness",
    "sb_flange_thickness": "ThicknessFlange",
    "sb_radius1": "RadiusLarge",
    "sb_radius2": "RadiusSmall",
    "sb_length": "ProfileLength",
    "sb_weight": "LinearWeight",
    "sb_unitprice": "UnitPrice",
    "sb_offset_x": "OffsetX",
    "sb_offset_y": "OffsetY",
}
SECTION = ("ProfileWidth", "ProfileHeight", "Thickness", "ThicknessFlange", "RadiusLarge", "RadiusSmall")


class TestProfileEditExpressions(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.doc = App.newDocument("EditExpressionsTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1
        if Gui.activeDocument() is None:
            self.skipTest("Real GUI document required for the expression binding")
        self.profile = self.doc.addObject("Part::FeaturePython", "Profile")
        self.profile.addExtension("Part::AttachExtensionPython")
        Profile(
            self.profile,
            init_w=40.0,
            init_h=40.0,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=4.0,
            init_r2=2.0,
            init_len=250.0,
            init_wg=2.3,
            init_unit_price=3.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="Square Hollow",
            size_name="40x2.0",
            bevels_combined=False,
            catalog_family="Square Hollow",
        )
        ViewProviderProfile(self.profile.ViewObject)
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.addProperty("App::PropertyLength", "Width")
        self.varset.Width = 60.24
        self.varset.addProperty("App::PropertyFloat", "Weight")
        self.varset.Weight = 5.5
        self.doc.recompute()
        self.doc.clearUndos()
        self.panels = []

    def tearDown(self):
        for panel in self.panels:
            for form in panel.form:
                form.close()

    def edit_panel(self):
        panel = EditProfileTaskPanel(self.profile)
        self.panels.append(panel)
        panel.open()
        return panel

    def field(self, panel, name):
        return getattr(panel.form_proxy, name)

    def drive_width(self):
        """What the Fx editor does: the expression goes on the bound property at once."""
        self.profile.setExpression("ProfileWidth", f"{self.varset.Name}.Width")
        self.doc.recompute()

    def expressions(self):
        return {prop: expr for prop, expr in expressions_of(self.profile, FIELDS.values()).items() if expr}

    def width(self):
        return self.profile.Shape.BoundBox.XLength

    def test_edit_fields_are_bound_to_the_profile_properties(self):
        panel = self.edit_panel()
        for name, prop in FIELDS.items():
            binding = Gui.ExpressionBinding(self.field(panel, name))
            self.assertTrue(binding.isBound(), name)
            self.assertFalse(binding.hasExpression(), name)
            unit = "" if prop in ("LinearWeight", "UnitPrice") else " mm"
            value = getattr(self.profile, prop)
            self.profile.setExpression(prop, f"{getattr(value, 'Value', value)}{unit}")
            self.assertTrue(binding.hasExpression(), f"{name} -> {prop}")
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(), {})

    def test_create_mode_fields_are_not_bound(self):
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self.addCleanup(panel.reject)
        for name in FIELDS:
            self.assertFalse(Gui.ExpressionBinding(self.field(panel, name)).isBound(), name)

    def test_ok_keeps_an_expression_set_in_the_panel_in_one_undo_step(self):
        panel = self.edit_panel()
        self.drive_width()
        self.assertAlmostEqual(self.field(panel, "sb_width").value(), 60.2, places=6)
        self.assertTrue(panel.accept())
        self.assertEqual(self.expressions(), {"ProfileWidth": f"{self.varset.Name}.Width"})
        self.assertAlmostEqual(self.width(), 60.24, places=6)
        # The VarSet drives the width from now on.
        self.varset.Width = 70.0
        self.doc.recompute()
        self.assertAlmostEqual(self.profile.ProfileWidth, 70.0, places=6)
        self.assertAlmostEqual(self.width(), 70.0, places=6)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.expressions(), {})
        self.assertAlmostEqual(self.profile.ProfileWidth, 40.0, places=6)

    def test_an_existing_expression_is_shown_and_kept_while_another_field_changes(self):
        self.drive_width()
        self.doc.clearUndos()
        panel = self.edit_panel()
        sb_width = self.field(panel, "sb_width")
        self.assertTrue(Gui.ExpressionBinding(sb_width).hasExpression())
        self.assertAlmostEqual(sb_width.value(), 60.2, places=6)
        self.field(panel, "sb_length").setValue(500.0)
        # The typed field applies; the expression-driven one is not overwritten with the rounded field value.
        self.assertEqual(self.profile.ProfileLength, 500.0)
        self.assertEqual(self.profile.ProfileWidth, 60.24)
        self.assertTrue(panel.accept())
        self.assertEqual(self.expressions(), {"ProfileWidth": f"{self.varset.Name}.Width"})
        self.assertEqual(self.profile.ProfileWidth, 60.24)
        self.assertAlmostEqual(self.width(), 60.24, places=6)
        self.assertAlmostEqual(self.profile.Shape.BoundBox.ZLength, 500.0, places=6)
        self.varset.Width = 50.0
        self.doc.recompute()
        self.assertAlmostEqual(self.width(), 50.0, places=6)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_set_properties_never_writes_over_an_expression_driven_property(self):
        self.drive_width()
        values = (99.0, 41.0, 2.0, 0.0, 4.0, 2.0, 300.0, 2.3, 3.0, False, 1, 1, "Metal", "Square Hollow", "40x2.0")
        self.profile.Proxy.set_properties(self.profile, *values, catalog_family="Square Hollow")
        # Before any recompute: the typed width is not written, the other values are.
        self.assertEqual(self.profile.ProfileWidth, 60.24)
        self.assertEqual((self.profile.ProfileHeight, self.profile.ProfileLength), (41.0, 300.0))
        self.assertEqual(self.expressions(), {"ProfileWidth": f"{self.varset.Name}.Width"})

    def test_size_change_clears_the_section_expressions_and_keeps_the_others(self):
        panel = self.edit_panel()
        self.drive_width()
        self.profile.setExpression("LinearWeight", f"{self.varset.Name}.Weight")
        self.doc.recompute()
        panel.form_proxy.combo_size.setCurrentText("15x1.5")
        self.assertEqual(self.profile.SizeName, "15x1.5")
        # The catalog refills the section: its values apply and their expressions go.
        self.assertEqual(self.expressions(), {"LinearWeight": f"{self.varset.Name}.Weight"})
        self.assertEqual(self.profile.ProfileWidth, 15.0)
        self.assertEqual(self.profile.Thickness, 1.5)
        self.assertFalse(Gui.ExpressionBinding(self.field(panel, "sb_width")).hasExpression())
        self.assertTrue(Gui.ExpressionBinding(self.field(panel, "sb_weight")).hasExpression())
        self.assertEqual(self.profile.LinearWeight, 5.5)
        self.assertEqual(self.field(panel, "sb_weight").value(), 5.5)
        self.assertTrue(panel.accept())
        self.assertEqual(self.expressions(), {"LinearWeight": f"{self.varset.Name}.Weight"})
        self.assertAlmostEqual(self.width(), 15.0, places=6)
        self.assertEqual(self.profile.LinearWeight, 5.5)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_removes_an_expression_set_in_the_panel(self):
        panel = self.edit_panel()
        self.drive_width()
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(), {})
        self.assertEqual(self.profile.ProfileWidth, 40.0)
        self.assertAlmostEqual(self.width(), 40.0, places=6)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_with_undo_off_removes_an_expression_set_in_the_panel(self):
        panel = self.edit_panel()
        self.doc.UndoMode = 0
        self.addCleanup(setattr, self.doc, "UndoMode", 1)
        self.drive_width()
        self.field(panel, "sb_length").setValue(500.0)
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(), {})
        self.assertEqual(self.profile.ProfileWidth, 40.0)
        self.assertEqual(self.profile.ProfileLength, 250.0)
        self.assertAlmostEqual(self.width(), 40.0, places=6)
        self.assertAlmostEqual(self.profile.Shape.BoundBox.ZLength, 250.0, places=6)

    def test_cancel_restores_an_existing_expression_cleared_by_a_size_change(self):
        self.drive_width()
        self.doc.clearUndos()
        panel = self.edit_panel()
        panel.form_proxy.combo_size.setCurrentText("15x1.5")
        self.assertEqual(self.expressions(), {})
        self.assertTrue(panel.reject())
        self.assertEqual(self.expressions(), {"ProfileWidth": f"{self.varset.Name}.Width"})
        self.assertEqual(self.profile.SizeName, "40x2.0")
        self.assertAlmostEqual(self.width(), 60.24, places=6)


if __name__ == "__main__":
    unittest.main()

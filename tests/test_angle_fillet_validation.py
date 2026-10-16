import FreeCAD as App
import Part
import math
import unittest

from freecad.frameforge.profile import Profile


class TestAngleFilletValidation(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("AngleFilletValidation")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def create_profile(
        self,
        family,
        width,
        height,
        thickness,
        outer_radius,
        inner_radius,
        make_fillet=True,
    ):
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj,
            width,
            height,
            thickness,
            thickness,
            outer_radius,
            inner_radius,
            100,
            0,
            0,
            make_fillet,
            1,
            1,
            "Metal",
            family,
            "Test",
            False,
        )
        return obj

    def test_radius_small_less_than_thickness_is_valid(self):
        obj = self.create_profile("Equal Leg Angles", 40, 40, 4, 6, 2, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())

    def test_radius_small_equal_thickness_is_valid(self):
        obj = self.create_profile("Equal Leg Angles", 20, 20, 4, 12, 4, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())

        # Catalog boundary 40x40x3 where Radius2=3.0 == Thickness=3.0
        with self.subTest(catalog_entry="40x40x3"):
            obj_40 = self.create_profile("Equal Leg Angles", 40, 40, 3, 6, 3, make_fillet=True)
            self.doc.recompute()
            self.assertEqual(obj_40.getStatusString(), "Valid")
            self.assertFalse(obj_40.Shape.isNull())
            self.assertTrue(obj_40.Shape.isValid())

    def test_radius_small_greater_than_thickness_raises_value_error(self):
        obj = self.create_profile("Equal Leg Angles", 40, 40, 4, 6, 5, make_fillet=True)
        expected_msg = "RadiusSmall (5.0) cannot exceed Thickness (4.0) for filleted angle profiles"
        with self.assertRaises(ValueError) as ctx:
            obj.Proxy.execute(obj)
        self.assertEqual(str(ctx.exception), expected_msg)

        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), expected_msg)
        self.assertIn("Invalid", obj.State)
        self.assertEqual(obj.RadiusSmall, 5.0)

        # Catalog entry 45x45x3 where Radius2=3.5 > Thickness=3.0
        with self.subTest(catalog_entry="45x45x3"):
            obj_45 = self.create_profile("Equal Leg Angles", 45, 45, 3, 7, 3.5, make_fillet=True)
            expected_45 = "RadiusSmall (3.5) cannot exceed Thickness (3.0) for filleted angle profiles"
            with self.assertRaises(ValueError) as ctx:
                obj_45.Proxy.execute(obj_45)
            self.assertEqual(str(ctx.exception), expected_45)
            self.doc.recompute()
            self.assertEqual(obj_45.getStatusString(), expected_45)
            self.assertIn("Invalid", obj_45.State)

        # Catalog entry 50x50x3 where Radius2=3.5 > Thickness=3.0
        with self.subTest(catalog_entry="50x50x3"):
            obj_50 = self.create_profile("Equal Leg Angles", 50, 50, 3, 7, 3.5, make_fillet=True)
            expected_50 = "RadiusSmall (3.5) cannot exceed Thickness (3.0) for filleted angle profiles"
            with self.assertRaises(ValueError) as ctx:
                obj_50.Proxy.execute(obj_50)
            self.assertEqual(str(ctx.exception), expected_50)
            self.doc.recompute()
            self.assertEqual(obj_50.getStatusString(), expected_50)
            self.assertIn("Invalid", obj_50.State)

    def test_radii_overlap_on_equal_angle_raises_value_error(self):
        # min(W, H) - Thickness = 20 - 4 = 16. R + r = 13 + 4 = 17 > 16.
        obj = self.create_profile("Equal Leg Angles", 20, 20, 4, 13, 4, make_fillet=True)
        expected = (
            "Fillet radii overlap: RadiusLarge (13.0) + RadiusSmall (4.0) = 17.0 "
            "exceeds available leg length min(ProfileWidth=20.0, ProfileHeight=20.0) - Thickness (4.0) = 16.0"
        )
        with self.assertRaises(ValueError) as ctx:
            obj.Proxy.execute(obj)
        self.assertEqual(str(ctx.exception), expected)

        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), expected)
        self.assertIn("Invalid", obj.State)

    def test_touching_radii_boundaries_on_both_width_and_height_are_valid(self):
        # Touching on height leg (H - TW = 20 - 4 = 16, R + r = 12 + 4 = 16)
        obj_h = self.create_profile("Unequal Leg Angles", 30, 20, 4, 12, 4, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(obj_h.getStatusString(), "Valid")
        self.assertFalse(obj_h.Shape.isNull())
        self.assertTrue(obj_h.Shape.isValid())

        # Touching on width leg (W - TW = 20 - 4 = 16, R + r = 12 + 4 = 16)
        obj_w = self.create_profile("Unequal Leg Angles", 20, 30, 4, 12, 4, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(obj_w.getStatusString(), "Valid")
        self.assertFalse(obj_w.Shape.isNull())
        self.assertTrue(obj_w.Shape.isValid())

    def test_radii_overlap_on_unequal_angle_short_height_leg_raises_value_error(self):
        # Short leg is Height=20, available = 20 - 4 = 16. R + r = 13 + 4 = 17 > 16.
        obj = self.create_profile("Unequal Leg Angles", 30, 20, 4, 13, 4, make_fillet=True)
        expected = (
            "Fillet radii overlap: RadiusLarge (13.0) + RadiusSmall (4.0) = 17.0 "
            "exceeds available leg length min(ProfileWidth=30.0, ProfileHeight=20.0) - Thickness (4.0) = 16.0"
        )
        with self.assertRaises(ValueError) as ctx:
            obj.Proxy.execute(obj)
        self.assertEqual(str(ctx.exception), expected)

        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), expected)
        self.assertIn("Invalid", obj.State)

    def test_radii_overlap_on_unequal_angle_short_width_leg_raises_value_error(self):
        # Short leg is Width=20, available = 20 - 4 = 16. R + r = 13 + 4 = 17 > 16.
        obj = self.create_profile("Unequal Leg Angles", 20, 30, 4, 13, 4, make_fillet=True)
        expected = (
            "Fillet radii overlap: RadiusLarge (13.0) + RadiusSmall (4.0) = 17.0 "
            "exceeds available leg length min(ProfileWidth=20.0, ProfileHeight=30.0) - Thickness (4.0) = 16.0"
        )
        with self.assertRaises(ValueError) as ctx:
            obj.Proxy.execute(obj)
        self.assertEqual(str(ctx.exception), expected)

        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), expected)
        self.assertIn("Invalid", obj.State)

    def test_negative_radii_raise_value_error(self):
        obj_neg_R = self.create_profile("Equal Leg Angles", 40, 40, 4, -1.0, 2.0, make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_neg_R.Proxy.execute(obj_neg_R)
        self.assertEqual(str(ctx.exception), "RadiusLarge cannot be negative, got -1.0")

        obj_neg_r = self.create_profile("Equal Leg Angles", 40, 40, 4, 6.0, -0.5, make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_neg_r.Proxy.execute(obj_neg_r)
        self.assertEqual(str(ctx.exception), "RadiusSmall cannot be negative, got -0.5")

    def test_zero_radii_raise_value_error(self):
        obj_zero_R = self.create_profile("Equal Leg Angles", 40, 40, 4, 0.0, 2.0, make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_zero_R.Proxy.execute(obj_zero_R)
        self.assertEqual(
            str(ctx.exception),
            "RadiusLarge must be greater than zero for filleted angle profiles, got 0.0",
        )

        obj_zero_r = self.create_profile("Equal Leg Angles", 40, 40, 4, 6.0, 0.0, make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_zero_r.Proxy.execute(obj_zero_r)
        self.assertEqual(
            str(ctx.exception),
            "RadiusSmall must be greater than zero for filleted angle profiles, got 0.0",
        )

    def test_non_finite_radii_raise_value_error(self):
        obj_nan_R = self.create_profile("Equal Leg Angles", 40, 40, 4, float("nan"), 2.0, make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_nan_R.Proxy.execute(obj_nan_R)
        self.assertEqual(str(ctx.exception), "RadiusLarge must be a finite number, got nan")

        obj_inf_r = self.create_profile("Equal Leg Angles", 40, 40, 4, 6.0, float("inf"), make_fillet=True)
        with self.assertRaises(ValueError) as ctx:
            obj_inf_r.Proxy.execute(obj_inf_r)
        self.assertEqual(str(ctx.exception), "RadiusSmall must be a finite number, got inf")

    def test_tube_control_allows_inner_radius_greater_than_thickness(self):
        # Square Hollow tube with outer radius 10, inner radius 8, thickness 2.
        # r (8) > Thickness (2) must NOT raise ValueError for tubes!
        tube = self.create_profile("Square Hollow", 20, 20, 2, 10, 8, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(tube.getStatusString(), "Valid")
        self.assertFalse(tube.Shape.isNull())
        self.assertTrue(tube.Shape.isValid())

        # Rectangular Hollow tube control
        rect_tube = self.create_profile("Rectangular Hollow", 30, 20, 2, 10, 8, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(rect_tube.getStatusString(), "Valid")
        self.assertFalse(rect_tube.Shape.isNull())
        self.assertTrue(rect_tube.Shape.isValid())

    def test_fillet_disabled_ignores_oversized_radii(self):
        # When MakeFillet is False, oversized radii (r > Thickness, R + r > leg - Thickness) are ignored
        obj = self.create_profile("Equal Leg Angles", 20, 20, 4, 50, 10, make_fillet=False)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())

    def test_valid_to_invalid_to_valid_lifecycle_preserves_shape_and_parameters(self):
        # Step 1: Valid initial profile
        obj = self.create_profile("Equal Leg Angles", 20, 20, 4, 6, 2, make_fillet=True)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        initial_brep = obj.Shape.exportBrepToString()
        initial_placement = App.Placement(obj.Placement)
        initial_weight = obj.ApproxWeight
        initial_price = obj.Price
        initial_undo_count = self.doc.UndoCount

        # Step 2: Edit to invalid (RadiusSmall = 5 > Thickness = 4)
        obj.RadiusSmall = 5.0
        self.doc.recompute()
        self.assertIn("Invalid", obj.State)
        expected_msg = "RadiusSmall (5.0) cannot exceed Thickness (4.0) for filleted angle profiles"
        self.assertEqual(obj.getStatusString(), expected_msg)
        # Parameter value must NOT be silently changed or clamped
        self.assertEqual(obj.RadiusSmall, 5.0)
        # Previous stored shape BREP, placement, metadata, and undo count remain identical
        self.assertEqual(obj.Shape.exportBrepToString(), initial_brep)
        self.assertEqual(obj.Placement, initial_placement)
        self.assertEqual(obj.ApproxWeight, initial_weight)
        self.assertEqual(obj.Price, initial_price)
        self.assertEqual(self.doc.UndoCount, initial_undo_count)

        # Step 3: Edit back to valid (RadiusSmall = 3 <= Thickness = 4)
        obj.RadiusSmall = 3.0
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertNotIn("Invalid", obj.State)
        # Shape should be recomputed with new geometry
        self.assertNotEqual(obj.Shape.exportBrepToString(), initial_brep)
        self.assertTrue(obj.Shape.isValid())

    def test_document_undo_transaction_restores_valid_state(self):
        self.doc.openTransaction("create_profile")
        obj = self.create_profile("Equal Leg Angles", 20, 20, 4, 6, 2, make_fillet=True)
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")

        # Start transaction with bad edit
        self.doc.openTransaction("bad_edit")
        obj.RadiusSmall = 6.0
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertIn("Invalid", obj.State)

        # Undo the bad edit
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(obj.RadiusSmall, 2.0)


if __name__ == "__main__":
    unittest.main()

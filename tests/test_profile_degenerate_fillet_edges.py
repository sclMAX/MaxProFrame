import math
import unittest

import FreeCAD as App

from freecad.maxproframe.profile import Profile


class TestDegenerateFilletEdges(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DegenerateFilletEdges")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def create_profile(self, family, width, height, thickness, outer_radius, inner_radius):
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(obj, width, height, thickness, thickness, outer_radius, inner_radius,
                100, 0, 0, True, 1, 1, "Metal", family, "Test", False)
        obj.Proxy.execute(obj)
        return obj

    def check_section(self, family, width, height, thickness, outer_radius, inner_radius):
        obj = self.create_profile(family, width, height, thickness, outer_radius, inner_radius)
        shape = obj.Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.BoundBox.XLength, width)
        self.assertAlmostEqual(shape.BoundBox.YLength, height)
        self.assertAlmostEqual(shape.BoundBox.ZLength, 100)
        corner = 1 - math.pi / 4
        if family in ("Equal Leg Angles", "Unequal Leg Angles"):
            area = thickness * (width + height - thickness) + corner * (outer_radius**2 - 2 * inner_radius**2)
        else:
            area = width * height - (width - 2 * thickness) * (height - 2 * thickness)
            area -= 4 * corner * (outer_radius**2 - inner_radius**2)
            # A missing inner wire must not silently turn the hollow section solid.
            self.assertFalse(shape.isInside(App.Vector(0, 0, 50), 1e-7, True))
        self.assertAlmostEqual(shape.Volume, area * 100, places=5)
        self.assertEqual(obj.Family, family)
        self.assertEqual(obj.CatalogFamily, family)
        self.assertEqual(tuple(self.doc.Objects), (obj,))

    def test_equal_angle_fillets_can_meet_without_straight_segments(self):
        self.check_section("Equal Leg Angles", 20, 20, 4, 12, 4)

    def test_unequal_angle_fillets_can_meet_on_one_leg(self):
        self.check_section("Unequal Leg Angles", 30, 20, 4, 12, 4)

    def test_square_hollow_fillets_can_form_concentric_circles(self):
        self.check_section("Square Hollow", 20, 20, 2, 10, 8)

    def test_rectangular_hollow_fillets_can_meet_on_short_sides(self):
        self.check_section("Rectangular Hollow", 30, 20, 2, 10, 8)

    def test_equal_angle_ordinary_fillets_are_unchanged(self):
        self.check_section("Equal Leg Angles", 40, 40, 4, 6, 2)

    def test_unequal_angle_ordinary_fillets_are_unchanged(self):
        self.check_section("Unequal Leg Angles", 50, 40, 4, 6, 2)

    def test_square_hollow_ordinary_fillets_are_unchanged(self):
        self.check_section("Square Hollow", 40, 40, 2, 6, 4)

    def test_rectangular_hollow_ordinary_fillets_are_unchanged(self):
        self.check_section("Rectangular Hollow", 50, 40, 2, 6, 4)


if __name__ == "__main__":
    unittest.main()

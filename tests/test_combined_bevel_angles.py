import unittest

import FreeCAD as App
import Part

from freecad.frameforge._utils import get_readable_cutting_angles
from freecad.frameforge.profile import Profile


class TestCuttingAngleFormatting(unittest.TestCase):
    def test_unavailable_standard_angles_are_reported_as_na(self):
        self.assertEqual(get_readable_cutting_angles("N/A", "N/A", "N/A", "N/A"), ("N/A", "N/A"))

    def test_numeric_and_trimmed_formats_are_preserved(self):
        cases = (
            ((0.0, 0.0, 0.0, 0.0), ("0.0", "0.0")),
            ((0.0, -15.0, 0.0, 20.0), ("-15.0", "20.0")),
            ((-15.0, 0.0, 20.0, 0.0), ("-15.0", "20.0")),
            ((15.0, 0.0, 0.0, 20.0), ("15.0", "* 20.0")),
            ((10.0, 20.0, 30.0, 40.0), ("10.0 / 20.0", "30.0 / 40.0")),
            ((0.0, 0.0, 0.0, 0.0, 15.0), ("0.0", "@ 15.0")),
            ((10.0, 0.0, 0.0, 0.0, 15.0), ("10.0", "@ 15.0")),
            ((0.0, 0.0, 0.0, 0.0, 15.0, 20.0), ("@ 15.0", "@ 20.0")),
            (("N/A", "N/A", "N/A", "N/A", 15.0, 20.0), ("@ 15.0", "@ 20.0")),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(get_readable_cutting_angles(*args), expected)


class TestProfileCuttingAngles(unittest.TestCase):
    def assert_profile_recompute(self, combined, expected_angles):
        doc = App.newDocument("CombinedBevelAnglesTest")
        self.addCleanup(App.closeDocument, doc.Name)
        doc.UndoMode = 1
        axis = doc.addObject("Part::Feature", "Axis")
        axis.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 250))
        doc.recompute()
        endpoints = [tuple(vertex.Point) for vertex in axis.Shape.Vertexes]
        placement = tuple(axis.Placement.toMatrix().A)
        obj = doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj,
            init_w=50.0,
            init_h=50.0,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=250.0,
            init_wg=8.0,
            init_unit_price=3.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="Square Hollow",
            size_name="Probe",
            bevels_combined=combined,
            catalog_family="Square Hollow (No Fillet)",
            link_sub=(axis, ("Edge1",)),
        )
        doc.clearUndos()
        doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), expected_angles)
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())
        self.assertAlmostEqual(obj.Shape.Volume, 96000.0, places=5)
        self.assertEqual([tuple(vertex.Point) for vertex in axis.Shape.Vertexes], endpoints)
        self.assertEqual(tuple(axis.Placement.toMatrix().A), placement)
        self.assertEqual(obj.CatalogFamily, "Square Hollow (No Fillet)")
        self.assertEqual(obj.LinearWeight, 8.0)
        self.assertEqual(obj.ApproxWeight, 2.0)
        self.assertEqual(obj.Price, 0.75)
        self.assertEqual(doc.UndoCount, 0)
        if combined:
            for name in ("BevelACutY", "BevelACutX", "BevelBCutY", "BevelBCutX"):
                self.assertNotIn(name, obj.PropertiesList)
            for name in ("BevelStartCut", "BevelStartRotate", "BevelEndCut", "BevelEndRotate"):
                self.assertEqual(getattr(obj, name), 0.0)
        else:
            for name in ("BevelACutY", "BevelACutX", "BevelBCutY", "BevelBCutX"):
                self.assertEqual(getattr(obj, name), 0.0)

    def test_combined_bevel_profile_recomputes_with_na_angles(self):
        self.assert_profile_recompute(True, ("N/A", "N/A"))

    def test_normal_profile_keeps_numeric_angles(self):
        self.assert_profile_recompute(False, ("0.0", "0.0"))


if __name__ == "__main__":
    unittest.main()

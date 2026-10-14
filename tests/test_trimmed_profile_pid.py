import unittest

import FreeCAD as App
import Part

from freecad.frameforge.profile import Profile
from freecad.frameforge.trimmed_profile import TrimmedProfile


class TestTrimmedProfilePID(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TrimmedPIDTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1
        axis = self.doc.addObject("Part::Feature", "Axis")
        axis.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 250))
        self.base = self.doc.addObject("Part::FeaturePython", "BaseProfile")
        self.base.addExtension("Part::AttachExtensionPython")
        Profile(
            self.base,
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
            bevels_combined=False,
            catalog_family="Square Hollow (No Fillet)",
            link_sub=(axis, ("Edge1",)),
        )
        self.base.PID = "42"
        plane = self.doc.addObject("Part::Feature", "CutPlane")
        plane.Shape = Part.makePlane(200, 200, App.Vector(-100, -100, 200), App.Vector(0, 0, 1))
        self.trimmed = self.doc.addObject("Part::FeaturePython", "TrimmedProfile")
        TrimmedProfile(self.trimmed)
        self.trimmed.TrimmedBody = self.base
        self.trimmed.TrimmingBoundary = [(plane, ("Face1",))]
        self.trimmed.TrimmedProfileType = "End Trim"
        self.trimmed.CutType = "Simple fit"
        self.doc.recompute()
        self.assertEqual(self.trimmed.getStatusString(), "Valid")
        self.doc.clearUndos()

    def assert_recompute_preserves_source_and_metadata(self, source_pid, source_type, copied_pid):
        source_shape = self.base.Shape.exportBrepToString()
        source_placement = self.base.Placement.toMatrix().A
        source_fields = {
            name: getattr(self.base, name)
            for name in (
                "Family", "CatalogFamily", "SizeName", "Material", "LinearWeight", "ApproxWeight",
                "ProfileWidth", "ProfileHeight", "ProfileLength", "UnitPrice", "Price",
            )
        }
        self.base.touch()
        self.trimmed.touch()
        self.doc.recompute()
        self.assertEqual(self.base.getStatusString(), "Valid")
        self.assertEqual(self.trimmed.getStatusString(), "Valid")
        self.assertEqual(self.base.PID, source_pid)
        self.assertEqual(self.base.getTypeIdOfProperty("PID"), source_type)
        self.assertEqual(self.trimmed.PID, copied_pid)
        self.assertEqual(self.trimmed.getTypeIdOfProperty("PID"), "App::PropertyString")
        self.assertEqual(self.base.Shape.exportBrepToString(), source_shape)
        self.assertEqual(self.base.Placement.toMatrix().A, source_placement)
        for name, value in source_fields.items():
            self.assertEqual(getattr(self.base, name), value)
        for name in ("Family", "CatalogFamily", "SizeName", "Material", "ApproxWeight", "Price"):
            self.assertEqual(getattr(self.trimmed, name), getattr(self.base, name))
        self.assertEqual(self.trimmed.Width.Value, 50.0)
        self.assertEqual(self.trimmed.Height.Value, 50.0)
        self.assertEqual(self.trimmed.Length.Value, 200.0)
        self.assertFalse(self.trimmed.Shape.isNull())
        self.assertTrue(self.trimmed.Shape.isValid())
        self.assertAlmostEqual(self.trimmed.Shape.Volume, 76800.0, places=5)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_integer_pid_is_copied_as_text_without_changing_source(self):
        self.base.removeProperty("PID")
        self.base.addProperty("App::PropertyInteger", "PID", "Profile", "Legacy ID").PID = 42
        self.assert_recompute_preserves_source_and_metadata(42, "App::PropertyInteger", "42")

    def test_text_pid_keeps_leading_zeroes(self):
        self.base.PID = "0042"
        self.assert_recompute_preserves_source_and_metadata("0042", "App::PropertyString", "0042")


if __name__ == "__main__":
    unittest.main()

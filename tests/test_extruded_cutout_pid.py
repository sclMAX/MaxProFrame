import unittest

import FreeCAD as App
import Part

from freecad.frameforge.extruded_cutout import ExtrudedCutout
from freecad.frameforge.profile import Profile


class TestExtrudedCutoutPID(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("CutoutPIDTest")
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
        self.doc.recompute()
        face_index = next(
            index for index, face in enumerate(self.base.Shape.Faces, 1)
            if face.normalAt(0, 0).z > 0.99
        )
        box = self.base.Shape.BoundBox
        sketch = self.doc.addObject("Sketcher::SketchObject", "CutSketch")
        sketch.Placement.Base = App.Vector(0, 0, box.ZMax)
        points = [
            App.Vector(box.XMin - 5, box.YMin - 5, 0),
            App.Vector((box.XMin + box.XMax) / 2, box.YMin - 5, 0),
            App.Vector((box.XMin + box.XMax) / 2, box.YMax + 5, 0),
            App.Vector(box.XMin - 5, box.YMax + 5, 0),
        ]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(points[index], points[(index + 1) % 4]), False)
        self.cutout = self.doc.addObject("Part::FeaturePython", "ExtrudedCutout")
        ExtrudedCutout(self.cutout, sketch, (self.base, (f"Face{face_index}",)))
        self.cutout.CutType = "Distance"
        self.cutout.ExtrusionLength = 50
        self.doc.recompute()
        self.assertEqual(self.cutout.getStatusString(), "Valid")
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
        self.cutout.touch()
        self.doc.recompute()
        self.assertEqual(self.base.getStatusString(), "Valid")
        self.assertEqual(self.cutout.getStatusString(), "Valid")
        self.assertEqual(self.base.PID, source_pid)
        self.assertEqual(self.base.getTypeIdOfProperty("PID"), source_type)
        self.assertEqual(self.cutout.PID, copied_pid)
        self.assertEqual(self.cutout.getTypeIdOfProperty("PID"), "App::PropertyString")
        self.assertEqual(self.base.Shape.exportBrepToString(), source_shape)
        self.assertEqual(self.base.Placement.toMatrix().A, source_placement)
        for name, value in source_fields.items():
            self.assertEqual(getattr(self.base, name), value)
        for name in ("Family", "CatalogFamily", "SizeName", "Material", "ApproxWeight", "Price"):
            self.assertEqual(getattr(self.cutout, name), getattr(self.base, name))
        self.assertEqual(self.cutout.Width.Value, 50.0)
        self.assertEqual(self.cutout.Height.Value, 50.0)
        self.assertEqual(self.cutout.Length.Value, 250.0)
        self.assertFalse(self.cutout.Shape.isNull())
        self.assertTrue(self.cutout.Shape.isValid())
        self.assertAlmostEqual(self.cutout.Shape.Volume, 86400.0, places=5)
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

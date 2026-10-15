import unittest

import FreeCAD as App
import Part

from freecad.frameforge.profile import Profile
from freecad.frameforge.trimmed_profile import TrimmedProfile
from freecad.frameforge.version import __version__ as ff_version


class CountingPlaneProxy:
    def __init__(self, obj):
        obj.addProperty("App::PropertyInteger", "ExecutionCount", "Probe")
        # Recording a callback must not touch the boundary and schedule another.
        obj.setPropertyStatus("ExecutionCount", "Output")
        obj.Proxy = self

    def execute(self, obj):
        obj.ExecutionCount += 1


class TestTrimmedProfileMigration(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TrimmedMigrationTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1

    def assert_same_shape(self, actual, expected):
        # Include faces and edges: the native cutting plane has zero volume.
        for difference in (actual.cut(expected), expected.cut(actual)):
            self.assertAlmostEqual(difference.Volume, 0.0, places=5)
            self.assertAlmostEqual(difference.Area, 0.0, places=5)
            self.assertAlmostEqual(difference.Length, 0.0, places=5)

    def assert_migration(self, versionless, executable_boundary=False):
        axis = self.doc.addObject("Part::Feature", "Axis")
        axis.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 250))
        source = self.doc.addObject("Part::FeaturePython", "Source")
        source.addExtension("Part::AttachExtensionPython")
        Profile(
            source, init_w=50.0, init_h=50.0, init_mt=2.0, init_ft=0.0,
            init_r1=0.0, init_r2=0.0, init_len=250.0, init_wg=8.0,
            init_unit_price=3.0, init_mf=False, init_anchor_x=1, init_anchor_y=1,
            material="Metal", fam="Square Hollow", size_name="MigrationProbe",
            bevels_combined=False, catalog_family="Square Hollow (No Fillet)",
            link_sub=(axis, ("Edge1",)),
        )
        source.PID = "0042"
        boundary = self.doc.addObject(
            "Part::FeaturePython" if executable_boundary else "Part::Feature", "CutPlane"
        )
        boundary.Shape = Part.makePlane(200, 200, App.Vector(-100, -100, 200), App.Vector(0, 0, 1))
        if executable_boundary:
            CountingPlaneProxy(boundary)
        else:
            self.assertFalse(hasattr(boundary, "Proxy"))
        trimmed = self.doc.addObject("Part::FeaturePython", "TrimmedProfile")
        TrimmedProfile(trimmed)
        trimmed.TrimmedBody = source
        trimmed.TrimmingBoundary = [(boundary, ("Face1",))]
        trimmed.TrimmedProfileType = "End Trim"
        trimmed.CutType = "Simple fit"
        self.doc.recompute()
        self.assertEqual(trimmed.getStatusString(), "Valid")
        self.assertAlmostEqual(trimmed.Shape.Volume, 76800.0, places=5)

        fields = (
            "PID", "Family", "CatalogFamily", "SizeName", "Material", "LinearWeight", "ApproxWeight",
            "ProfileWidth", "ProfileHeight", "ProfileLength", "UnitPrice", "Price",
        )
        source_fields = {name: getattr(source, name) for name in fields}
        derived_fields = {
            name: getattr(trimmed, name)
            for name in ("PID", "Family", "CatalogFamily", "SizeName", "Material", "ApproxWeight", "Price",
                         "CuttingAngleA", "CuttingAngleB")
        }
        objects = (axis, source, boundary, trimmed)
        before = [(obj.Shape.copy(), list(obj.Placement.toMatrix().A), obj.ViewObject.Visibility)
                  for obj in objects]
        endpoints = [list(v.Point) for v in axis.Shape.Vertexes]
        executions_before = boundary.ExecutionCount if executable_boundary else None
        version_before = trimmed.FrameforgeVersion
        if versionless:
            trimmed.removeProperty("FrameforgeVersion")
            self.assertFalse(hasattr(trimmed, "FrameforgeVersion"))
        self.doc.clearUndos()
        trimmed.touch()
        self.doc.recompute()

        self.assertEqual(trimmed.getStatusString(), "Valid")
        self.assertNotIn("Invalid", trimmed.State)
        self.assertEqual(trimmed.FrameforgeVersion, ff_version if versionless else version_before)
        self.assertEqual(source.getStatusString(), "Valid")
        for obj, (shape, placement, visibility) in zip(objects, before):
            with self.subTest(object=obj.Name):
                self.assert_same_shape(obj.Shape, shape)
                self.assertEqual(list(obj.Placement.toMatrix().A), placement)
                self.assertEqual(obj.ViewObject.Visibility, visibility)
        for name, value in source_fields.items():
            self.assertEqual(getattr(source, name), value, name)
        for name, value in derived_fields.items():
            self.assertEqual(getattr(trimmed, name), value, name)
        self.assertEqual(trimmed.PID, "0042")
        self.assertEqual(trimmed.CatalogFamily, "Square Hollow (No Fillet)")
        self.assertFalse(trimmed.Shape.isNull())
        self.assertTrue(trimmed.Shape.isValid())
        self.assertAlmostEqual(trimmed.Shape.Volume, 76800.0, places=5)
        self.assertAlmostEqual(trimmed.Width.Value, 50.0, places=5)
        self.assertAlmostEqual(trimmed.Height.Value, 50.0, places=5)
        self.assertAlmostEqual(trimmed.Length.Value, 200.0, places=5)
        self.assertEqual([list(v.Point) for v in axis.Shape.Vertexes], endpoints)
        self.assertEqual(self.doc.UndoCount, 0)
        if executable_boundary:
            self.assertEqual(boundary.ExecutionCount, executions_before + (1 if versionless else 0))

    def test_versionless_native_boundary_migrates_without_changing_model(self):
        self.assert_migration(versionless=True)

    def test_current_native_boundary_keeps_existing_recompute_behavior(self):
        self.assert_migration(versionless=False)

    def test_versionless_executable_boundary_still_executes(self):
        self.assert_migration(versionless=True, executable_boundary=True)


if __name__ == "__main__":
    unittest.main()

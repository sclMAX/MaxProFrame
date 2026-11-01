"""Every MaxProFrame object records the MaxProFrame version that created it, never a FrameForge one."""

import os
import re
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER
from test_notch_geometry import BOUNDARY_EDGE, TRIMMED_EDGE, TrimFixture

from freecad.maxproframe.create_link import makeLink
from freecad.maxproframe.extruded_cutout import ExtrudedCutout
from freecad.maxproframe.section_outline import build_section_face
from freecad.maxproframe.version import __version__

ROOT = os.path.join(os.path.dirname(__file__), os.pardir)


class TestVersionProperty(TrimFixture):
    def assert_version(self, obj, group):
        self.assertEqual(obj.MaxProFrameVersion, "1.0.0")
        self.assertEqual(obj.getGroupOfProperty("MaxProFrameVersion"), group)
        self.assertEqual(
            obj.getDocumentationOfProperty("MaxProFrameVersion"), "MaxProFrame version used to create the object"
        )
        self.assertNotIn("FrameforgeVersion", obj.PropertiesList)
        for name in obj.PropertiesList:
            self.assertNotEqual(obj.getGroupOfProperty(name).lower(), "frameforge", name)

    def test_version_module_and_package_metadata_are_1_0_0(self):
        self.assertEqual(__version__, "1.0.0")
        for name, pattern in (
            ("package.xml", r"<version>([^<]+)</version>"),
            ("pyproject.toml", r'^version = "([^"]+)"'),
        ):
            with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
                self.assertEqual(re.findall(pattern, handle.read(), re.MULTILINE), ["1.0.0"], name)

    def test_profiles_trims_links_and_cutouts_record_the_maxproframe_version(self):
        profile = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        boundary = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
        trim = self.notch(profile, boundary)
        App.setActiveDocument(self.doc.Name)
        link = makeLink(boundary)
        cutout = self.cutout(boundary)

        for obj, group in ((profile, "Profile"), (trim, "Profile"), (cutout, "Profile"), (link, "MaxProFrame")):
            with self.subTest(obj.Name):
                self.assert_version(obj, group)
        self.assertEqual(link.getGroupOfProperty("PID"), "MaxProFrame")

    def test_a_profile_without_version_is_not_migrated(self):
        profile = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        profile.removeProperty("MaxProFrameVersion")
        profile.touch()
        self.doc.recompute()
        self.assertEqual(profile.getStatusString(), "Valid")
        self.assertNotIn("MaxProFrameVersion", profile.PropertiesList)
        self.assertNotIn("FrameforgeVersion", profile.PropertiesList)

    def test_section_outline_still_builds_a_face(self):
        face = build_section_face(dict(Family="Square Hollow", ProfileWidth=40.0, ProfileHeight=40.0, Thickness=2.0))
        self.assertAlmostEqual(face.Area, 40.0 * 40.0 - 36.0 * 36.0, places=6)

    def cutout(self, base):
        face_index = next(
            index
            for index, face in enumerate(base.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).z > 0.99
        )
        box = base.Shape.BoundBox
        sketch = self.doc.addObject("Sketcher::SketchObject", "CutSketch")
        sketch.Placement.Base = App.Vector(0, 0, box.ZMax)
        x_mid = (box.XMin + box.XMax) / 2
        points = [
            App.Vector(box.XMin - 5, box.YMin + 10, 0),
            App.Vector(x_mid, box.YMin + 10, 0),
            App.Vector(x_mid, box.YMin + 20, 0),
            App.Vector(box.XMin - 5, box.YMin + 20, 0),
        ]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(points[index], points[(index + 1) % 4]), False)
        cutout = self.doc.addObject("Part::FeaturePython", "ExtrudedCutout")
        ExtrudedCutout(cutout, sketch, (base, (f"Face{face_index}",)))
        cutout.CutType = "Distance"
        cutout.ExtrusionLength = 5
        self.doc.recompute()
        self.assertEqual(cutout.getStatusString(), "Valid")
        return cutout


if __name__ == "__main__":
    unittest.main()

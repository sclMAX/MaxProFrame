"""End Trim objects are placed in the trimmed profile's own container."""

import unittest

import FreeCAD as App
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture

from freecad.maxproframe.create_trimmed_profiles_tool import TrimProfileCommand


class TestEndTrimContainer(MiterFixture):
    def test_trim_stays_in_the_profile_container_inside_nested_parts(self):
        App.setActiveDocument(self.doc.Name)
        outer = self.doc.addObject("App::Part", "Outer")
        inner = self.doc.addObject("App::Part", "Inner")
        outer.addObject(inner)
        outer.Placement.Base = App.Vector(0, 500, 0)
        inner.Placement.Base = App.Vector(1000, 0, 0)
        sketches = [self.make_sketch(edge) for edge in CHAINED]
        p1, p2 = (self.make_profile(sketch, "Edge1", **CENTER) for sketch in sketches)
        inner.addObjects(sketches + [p1, p2])
        self.doc.recompute()

        trim = TrimProfileCommand().make_trimmed_profile(trimmedBody=p1, trimmingBoundary=[(p2, ("Face1",))])
        self.doc.recompute()

        self.assertEqual(trim.getStatusString(), "Valid")
        self.assertEqual(trim.getParentGeoFeatureGroup(), inner)
        placed = trim.getParentGeoFeatureGroup().getGlobalPlacement().multVec(trim.Shape.BoundBox.Center)
        expected = inner.getGlobalPlacement().multVec(p1.Shape.BoundBox.Center)
        self.assertLess((placed - expected).Length, 60.0)


if __name__ == "__main__":
    unittest.main()

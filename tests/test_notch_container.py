"""Notch objects are placed in the trimmed profile's own container."""

import unittest

import FreeCAD as App
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture

from freecad.maxproframe import create_extend_cut_tool, create_profiles_tool
from freecad.maxproframe.create_notch_tool import make_notch_profile


class TestNotchContainer(MiterFixture):
    def test_notch_stays_in_the_profile_container_inside_nested_parts(self):
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

        trim = make_notch_profile(p1, p2)
        self.doc.recompute()

        self.assertEqual(trim.getStatusString(), "Valid")
        self.assertEqual(trim.getParentGeoFeatureGroup(), inner)
        placed = trim.getParentGeoFeatureGroup().getGlobalPlacement().multVec(trim.Shape.BoundBox.Center)
        expected = inner.getGlobalPlacement().multVec(p1.Shape.BoundBox.Center)
        self.assertLess((placed - expected).Length, 60.0)

    def test_notch_tool_places_trims_with_the_create_profile_helper(self):
        # Notch trims are made by the shared target joint factory, which places them with the Create Profile helper.
        self.assertIs(create_extend_cut_tool.place_in_container_of, create_profiles_tool.place_in_container_of)


if __name__ == "__main__":
    unittest.main()

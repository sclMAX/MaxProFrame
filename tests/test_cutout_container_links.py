"""Drill holes and cutouts join their profile's Part without dragging profiles of other Parts.

A Part pulls in every object reachable through local-scope links of an object it receives.
A trim cut against a profile of another Part links to it, so a hole on that trim must join
its Part before it links to the trim.
"""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, MiterFixture

from freecad.maxproframe.create_extruded_cutout_tool import make_extruded_cutout
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.trimmed_profile import TrimmedProfile


class TestCutoutContainerLinks(MiterFixture):
    def setUp(self):
        super().setUp()
        # A side frame profile in its own Part, and a back profile trimmed against it in another Part.
        self.side = self.doc.addObject("App::Part", "Side")
        self.back = self.doc.addObject("App::Part", "Back")
        side_path = self.make_sketch(((0, 0, 0), (0, 200, 0)))
        back_path = self.make_sketch(((200, 0, 0), (0, 0, 0)))
        self.side_profile = self.make_profile(side_path, "Edge1", **CENTER)
        back_profile = self.make_profile(back_path, "Edge1", **CENTER)
        self.side.addObjects([side_path, self.side_profile])
        self.back.addObjects([back_path, back_profile])
        self.trim = self.doc.addObject("Part::FeaturePython", "Miter")
        self.back.addObject(self.trim)
        TrimmedProfile(self.trim)
        self.trim.TrimmedBody = back_profile
        self.trim.TrimmingBoundary = [(self.side_profile, ("Edge1",))]
        self.trim.TrimmedProfileType = "End Miter"
        self.doc.recompute()
        self.side_group = list(self.side.Group)
        self.back_group = list(self.back.Group)

    def face_and_vertex(self):
        """The largest planar face of the trim and the name of one of its vertices."""
        faces = [
            (index, face)
            for index, face in enumerate(self.trim.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Plane)
        ]
        index, face = max(faces, key=lambda item: item[1].Area)
        point = face.Vertexes[0].Point
        for number, vertex in enumerate(self.trim.Shape.Vertexes, start=1):
            if vertex.Point.isEqual(point, 1e-6):
                return f"Face{index}", f"Vertex{number}"
        self.fail("no vertex of the face")

    def assert_only_joins_the_back(self, obj):
        self.assertEqual(obj.getParentGeoFeatureGroup(), self.back)
        self.assertEqual(self.side.Group, self.side_group)
        self.assertEqual(self.back.Group, self.back_group + [obj])
        self.assertEqual(self.side_profile.getParentGeoFeatureGroup(), self.side)

    def test_a_drill_hole_on_a_trim_against_another_part_leaves_that_part_untouched(self):
        face, vertex = self.face_and_vertex()
        hole = make_drill_hole((self.trim, (face,)), vertex)
        self.doc.recompute()
        self.assert_only_joins_the_back(hole)
        self.assertEqual(hole.baseObject, (self.trim, [face]))

    def test_a_cutout_on_a_trim_against_another_part_leaves_that_part_untouched(self):
        face, _ = self.face_and_vertex()
        cutout = make_extruded_cutout(None, (self.trim, [face]))
        self.doc.recompute()
        self.assert_only_joins_the_back(cutout)
        self.assertEqual(cutout.baseObject, (self.trim, [face]))

    def test_a_drill_hole_on_a_profile_outside_any_part_stays_at_the_document_root(self):
        path = self.make_sketch(((0, 0, 100), (200, 0, 100)))
        profile = self.make_profile(path, "Edge1", **CENTER)
        top = max(
            (f"Face{i}" for i, f in enumerate(profile.Shape.Faces, start=1) if isinstance(f.Surface, Part.Plane)),
            key=lambda name: profile.Shape.getElement(name).Area,
        )
        point = profile.Shape.getElement(top).Vertexes[0].Point
        vertex = next(
            f"Vertex{i}" for i, v in enumerate(profile.Shape.Vertexes, start=1) if v.Point.isEqual(point, 1e-6)
        )
        hole = make_drill_hole((profile, (top,)), vertex)
        self.doc.recompute()
        self.assertIsNone(hole.getParentGeoFeatureGroup())
        self.assertEqual(self.side.Group, self.side_group)
        self.assertEqual(self.back.Group, self.back_group)


if __name__ == "__main__":
    unittest.main()

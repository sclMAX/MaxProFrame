"""Profile Pattern on a VarSet-sized table: a new size keeps the pattern valid and the slats evenly spaced.

The frame of four mitered sides FreeCAD renames on a new size ("?Edge1", "?Face2"), as in the user's Mesa8p:
the pattern still follows its edge and its two faces (S3, S4, S5).
"""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import SIZE
from test_extend_cut_lost_face import LENGTH, WIDTH, LostFaceFixture

from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.profile_pattern import (
    BETWEEN_FACES,
    EDGE,
    FACE,
    element_snapshot,
    find_element,
    make_profile_pattern,
)

Y = App.Vector(0, 1, 0)
COUNT = 8


def span(shape, axis):
    values = [vertex.Point.dot(axis) for vertex in shape.Vertexes]
    return min(values), max(values)


class TestPatternOnAResizedTable(LostFaceFixture):
    def side_edge(self):
        """A straight edge of the left side along Y of the Part."""
        side = self.miters[0]
        for index, edge in enumerate(side.Shape.Edges, 1):
            if isinstance(edge.Curve, Part.Line) and edge.Curve.Direction.cross(Y).Length < 1e-9:
                return side, f"Edge{index}"
        self.fail("no edge along Y")

    def inner_faces(self):
        """Inner faces of the bottom and top sides: (object, name)."""
        faces = []
        for side, sense in ((self.miters[1], 1), (self.miters[3], -1)):
            normal = App.Vector(0, sense, 0)
            found = [
                (index, face)
                for index, face in enumerate(side.Shape.Faces, 1)
                if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).dot(normal) > 1 - 1e-9
            ]
            index, _ = max(found, key=lambda item: item[1].CenterOfMass.dot(normal))
            faces.append((side, f"Face{index}"))
        return faces

    def gaps(self, obj):
        low = self.miters[1].Shape.BoundBox.YMax
        high = self.miters[3].Shape.BoundBox.YMin
        spans = sorted(span(Part.getShape(piece), Y) for piece in [self.trim, *obj.Copies])
        ends = [low, *(end for s in spans for end in s), high]
        return [round(ends[i + 1] - ends[i], 4) for i in range(0, len(ends), 2)]

    def slat_quantities(self, width):
        profiles, links = [], []
        traverse_assembly(profiles, links, self.part)
        # A slat runs between the inner faces of the sides: the width less one section.
        slats = [row for row in profiles if round(float(row["length"]), 1) == round(width - SIZE, 1)]
        return [row["quantity"] for row in group_profiles(slats)]

    def test_between_faces_keeps_equal_gaps_after_each_new_size(self):
        obj = make_profile_pattern(
            self.trim, self.side_edge(), mode=BETWEEN_FACES, count=COUNT, faces=self.inner_faces()
        )
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        for width, length in ((1300.0, LENGTH), (1300.0, 2600.0), (900.0, 1800.0), (WIDTH, LENGTH)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)
                gaps = self.gaps(obj)
                self.assertEqual(len(gaps), COUNT + 1)
                self.assertLess(max(gaps) - min(gaps), 1e-3, gaps)
                self.assertEqual(self.slat_quantities(width), [COUNT])

    def test_count_and_pitch_stays_valid_after_a_new_size(self):
        obj = make_profile_pattern(self.trim, self.side_edge(), count=3, pitch=200.0)
        self.doc.recompute()
        for width, length in ((1300.0, 2600.0), (900.0, 1800.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assertTrue(obj.isValid(), obj.getStatusString())
                self.assert_all_valid(self.doc)
                self.assertEqual(self.slat_quantities(width), [4])

    def test_undo_and_redo_of_a_new_size_keep_the_gaps(self):
        self.doc.UndoMode = 1
        obj = make_profile_pattern(
            self.trim, self.side_edge(), mode=BETWEEN_FACES, count=COUNT, faces=self.inner_faces()
        )
        self.doc.recompute()
        self.doc.clearUndos()
        self.doc.openTransaction("Resize")
        self.resize(self.doc, 1300.0, 2600.0)
        self.doc.commitTransaction()
        resized = self.gaps(obj)
        for step in ("undo", "redo"):
            with self.subTest(step=step):
                getattr(self.doc, step)()
                self.doc.recompute()
                self.assert_all_valid(self.doc)
                gaps = self.gaps(obj)
                self.assertLess(max(gaps) - min(gaps), 1e-3, gaps)
        self.assertEqual(self.gaps(obj), resized)

    def assert_links_follow_the_frame(self, obj):
        """The links of ``obj`` name, without FreeCAD's lost mark, the edge along Y and the two inner faces."""
        side, sub = obj.Edge[0], obj.Edge[1][0]
        self.assertEqual((side, sub), self.side_edge())
        self.assertEqual([(face_obj, subs[0]) for face_obj, subs in obj.Faces], self.inner_faces())

    def test_the_pattern_links_the_edge_and_faces_found_again(self):
        obj = make_profile_pattern(
            self.trim, self.side_edge(), mode=BETWEEN_FACES, count=COUNT, faces=self.inner_faces()
        )
        self.doc.recompute()
        for width, length in ((1300.0, 2600.0), (900.0, 1800.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_links_follow_the_frame(obj)

    def test_count_and_pitch_keeps_the_sense_of_its_edge(self):
        obj = make_profile_pattern(self.trim, self.side_edge(), count=3, pitch=200.0)
        self.doc.recompute()

        def steps():
            start = self.trim.Shape.BoundBox.Center.y
            return [round(Part.getShape(link).BoundBox.Center.y - start, 4) for link in obj.Copies]

        before = steps()
        self.assertEqual(sorted(abs(step) for step in before), [200.0, 400.0, 600.0])
        for width, length in ((1300.0, 2600.0), (900.0, 1800.0), (WIDTH, LENGTH)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assertTrue(obj.isValid(), obj.getStatusString())
                self.assertEqual(steps(), before)

    def test_an_edge_picked_through_a_link_follows_a_new_size(self):
        """The edge of a side seen through a Link to the frame's Part: "FrameLink" + "Profile_Mt.?Edge1"."""
        link = self.doc.addObject("App::Link", "FrameLink")
        link.LinkedObject = self.part
        link.Placement = App.Placement(App.Vector(5000, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))
        self.doc.recompute()
        side, edge = self.side_edge()
        obj = make_profile_pattern(self.trim, (link, f"{side.Name}.{edge}"), count=3, pitch=200.0)
        self.doc.recompute()

        def steps():
            start = self.trim.Shape.BoundBox.Center
            return [tuple(round(c, 4) for c in Part.getShape(copy).BoundBox.Center - start) for copy in obj.Copies]

        before = steps()
        for width, length in ((1300.0, 2600.0), (900.0, 1800.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assertTrue(obj.isValid(), obj.getStatusString())
                self.assertEqual(obj.Edge[1], [f"{side.Name}.{edge}"])
                self.assertEqual(steps(), before)

    def test_a_document_opened_follows_a_new_size(self):
        obj = make_profile_pattern(
            self.trim, self.side_edge(), mode=BETWEEN_FACES, count=COUNT, faces=self.inner_faces()
        )
        self.doc.recompute()
        opened = self.reopen(self.doc)
        self.resize(opened, 1300.0, 2600.0)
        self.assert_all_valid(opened)
        pattern = opened.getObject(obj.Name)
        low = opened.getObject(self.miters[1].Name).Shape.BoundBox.YMax
        high = opened.getObject(self.miters[3].Name).Shape.BoundBox.YMin
        spans = sorted(span(Part.getShape(piece), Y) for piece in [opened.getObject(self.trim.Name), *pattern.Copies])
        ends = [low, *(end for s in spans for end in s), high]
        gaps = [ends[i + 1] - ends[i] for i in range(0, len(ends), 2)]
        self.assertEqual(len(gaps), COUNT + 1)
        self.assertLess(max(gaps) - min(gaps), 1e-3, gaps)

    def test_a_name_on_another_element_is_found_again_where_it_was(self):
        """FreeCAD can give the name to another element: the one on the line or plane remembered is taken."""
        side, edge = self.side_edge()
        kept = element_snapshot(side, edge, EDGE)
        along_y = [
            f"Edge{index}"
            for index, other in enumerate(side.Shape.Edges, 1)
            if isinstance(other.Curve, Part.Line) and other.Curve.Direction.cross(Y).Length < 1e-9
        ]
        others = [name for name in along_y if name != edge]
        self.assertTrue(others)
        for other in others:
            with self.subTest(edge=other):
                self.assertEqual(find_element(side, other, kept, EDGE), (edge, True))
        face_obj, face = self.inner_faces()[0]
        kept = element_snapshot(face_obj, face, FACE)
        other = next(f"Face{index}" for index in range(1, len(face_obj.Shape.Faces) + 1) if f"Face{index}" != face)
        self.assertEqual(find_element(face_obj, other, kept, FACE), (face, True))
        self.assertEqual(find_element(face_obj, f"?{face}", kept, FACE), (face, True))

    def test_a_face_with_no_face_where_it_was_fails_naming_its_object(self):
        obj = make_profile_pattern(
            self.trim, self.side_edge(), mode=BETWEEN_FACES, count=COUNT, faces=self.inner_faces()
        )
        self.doc.recompute()
        face = obj.Faces[0][1][0]
        # The bottom side gets a wider section with the new size: no face of it is where the first face was.
        bottom = self.miters[1].TrimmedBody
        bottom.ProfileWidth = SIZE + 10.0
        bottom.ProfileHeight = SIZE + 10.0
        self.resize(self.doc, 1300.0, 2600.0)
        self.assertFalse(obj.isValid())
        self.assertEqual(
            obj.getStatusString(),
            f"Profile Pattern: {self.miters[1].Label} has no planar face where its face {face} was.",
        )


if __name__ == "__main__":
    unittest.main()

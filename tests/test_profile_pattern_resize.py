"""Profile Pattern on a VarSet-sized table: a new size keeps the pattern valid and the slats evenly spaced.

The frame of four mitered sides FreeCAD renames on a new size ("?Edge1", "?Face2"), as in the user's Mesa8p:
the pattern still follows its edge and its two faces (S3, S4, S5).
"""

import unittest

import FreeCAD as App
import Part
from test_extend_cut_lost_face import LENGTH, WIDTH, LostFaceFixture

from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.profile_pattern import BETWEEN_FACES, make_profile_pattern

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
        slats = [row for row in profiles if round(float(row["length"]), 1) == round(width - 80.0, 1)]
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


if __name__ == "__main__":
    unittest.main()

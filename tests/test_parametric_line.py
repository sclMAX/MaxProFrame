"""A parametric line links its vertices globally: moving it never drags the profiles it measures."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.parametric_line import CreateParametricLineCommand, ParametricLine

GLOBAL = "App::PropertyLinkSubGlobal"


class TestParametricLine(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ParametricLineTest")
        name = self.doc.Name
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
        App.setActiveDocument(name)

    def part(self, name, base):
        part = self.doc.addObject("App::Part", name)
        part.Placement.Base = App.Vector(*base)
        box = self.doc.addObject("Part::Box", f"{name}Box")
        part.addObject(box)
        return part, box

    def line(self, v1, v2):
        CreateParametricLineCommand().make_parametric_line([v1, v2])
        return self.doc.ActiveObject

    def ends(self, line):
        return [tuple(round(c, 6) for c in v.Point) for v in line.Shape.Vertexes]

    def test_new_line_links_vertices_globally(self):
        _, a = self.part("Left", (0, 0, 0))
        _, b = self.part("Right", (100, 0, 0))
        line = self.line((a, "Vertex1"), (b, "Vertex1"))
        self.assertEqual(line.getTypeIdOfProperty("Vertex1"), GLOBAL)
        self.assertEqual(line.getTypeIdOfProperty("Vertex2"), GLOBAL)
        self.assertEqual(line.Vertex1, (a, ["Vertex1"]))
        self.assertEqual(line.Vertex2, (b, ["Vertex1"]))

    def test_moving_line_into_a_part_keeps_linked_profiles_in_their_parts(self):
        left, a = self.part("Left", (0, 0, 0))
        right, b = self.part("Right", (100, 0, 0))
        line = self.line((a, "Vertex1"), (b, "Vertex1"))
        target = self.doc.addObject("App::Part", "Target")
        target.addObject(line)
        self.doc.recompute()
        self.assertEqual(target.Group, [line])
        self.assertEqual(left.Group, [a])
        self.assertEqual(right.Group, [b])

    def test_ends_sit_on_global_vertices_when_parts_are_placed(self):
        _, a = self.part("Left", (0, 0, 0))
        right, b = self.part("Right", (100, 0, 0))
        line = self.line((a, "Vertex1"), (b, "Vertex1"))
        self.assertEqual(self.ends(line), [(0, 0, 10), (100, 0, 10)])
        right.Placement.Base = App.Vector(200, 30, 0)
        # A Part placement does not touch the line; the next recompute of the line follows it.
        line.touch()
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(0, 0, 10), (200, 30, 10)])

    def test_line_inside_a_placed_part_draws_in_that_part_coordinates(self):
        _, a = self.part("Left", (0, 0, 0))
        _, b = self.part("Right", (100, 0, 0))
        line = self.line((a, "Vertex1"), (b, "Vertex1"))
        holder = self.doc.addObject("App::Part", "Holder")
        holder.Placement.Base = App.Vector(0, 50, 0)
        holder.addObject(line)
        line.touch()
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(0, -50, 10), (100, -50, 10)])
        global_ends = [holder.Placement.multVec(v.Point) for v in line.Shape.Vertexes]
        self.assertEqual([tuple(round(c, 6) for c in p) for p in global_ends], [(0, 0, 10), (100, 0, 10)])

    def test_root_line_between_root_objects_keeps_its_ends(self):
        a = self.doc.addObject("Part::Box", "A")
        b = self.doc.addObject("Part::Box", "B")
        b.Placement.Base = App.Vector(0, 0, 40)
        self.doc.recompute()
        line = self.line((a, "Vertex2"), (b, "Vertex8"))
        self.assertEqual(self.ends(line), [(0, 0, 0), (10, 10, 40)])

    def test_saved_local_links_migrate_to_global_on_restore(self):
        _, a = self.part("Left", (0, 0, 0))
        right, b = self.part("Right", (100, 0, 0))
        legacy = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        legacy.addProperty("App::PropertyLinkSub", "Vertex1", "ParametricLine", "First Vertex")
        legacy.addProperty("App::PropertyLinkSub", "Vertex2", "ParametricLine", "Second Vertex")
        legacy.Proxy = ParametricLine.__new__(ParametricLine)
        legacy.Vertex1 = (a, "Vertex1")
        legacy.Vertex2 = (b, "Vertex1")
        self.doc.recompute()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "legacy.FCStd")
        self.doc.saveAs(path)
        name = self.doc.Name
        App.closeDocument(name)
        self.doc = App.openDocument(path)
        self.addCleanup(lambda n=self.doc.Name: App.closeDocument(n) if n in App.listDocuments() else None)
        line = self.doc.getObject("ParametricLine")
        a, b = self.doc.getObject("LeftBox"), self.doc.getObject("RightBox")
        self.assertEqual(line.getTypeIdOfProperty("Vertex1"), GLOBAL)
        self.assertEqual(line.getTypeIdOfProperty("Vertex2"), GLOBAL)
        self.assertEqual(line.Vertex1, (a, ["Vertex1"]))
        self.assertEqual(line.Vertex2, (b, ["Vertex1"]))
        self.assertEqual(line.getGroupOfProperty("Vertex1"), "ParametricLine")
        self.assertEqual(line.getDocumentationOfProperty("Vertex2"), "Second Vertex")
        target = self.doc.addObject("App::Part", "Target")
        target.addObject(line)
        self.doc.getObject("Right").Placement.Base = App.Vector(300, 0, 0)
        line.touch()
        self.doc.recompute()
        self.assertEqual(self.doc.getObject("Right").Group, [b])
        self.assertEqual(self.ends(line), [(0, 0, 10), (300, 0, 10)])

    def test_migration_handles_missing_empty_and_global_links(self):
        line = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        line.addProperty("App::PropertyLinkSub", "Vertex1", "ParametricLine", "First Vertex")
        ParametricLine.onDocumentRestored(None, line)
        self.assertEqual(line.getTypeIdOfProperty("Vertex1"), GLOBAL)
        self.assertEqual(line.getTypeIdOfProperty("Vertex2"), GLOBAL)
        self.assertIsNone(line.Vertex1)
        self.assertIsNone(line.Vertex2)
        box = self.doc.addObject("Part::Box", "Box")
        line.Vertex1 = (box, "Vertex1")
        ParametricLine.onDocumentRestored(None, line)
        self.assertEqual(line.Vertex1, (box, ["Vertex1"]))

    def test_body_feature_in_nested_parts_uses_global_points(self):
        outer = self.doc.addObject("App::Part", "Outer")
        outer.Placement.Base = App.Vector(0, 0, 100)
        inner = self.doc.addObject("App::Part", "Inner")
        inner.Placement.Base = App.Vector(50, 0, 0)
        outer.addObject(inner)
        body = self.doc.addObject("PartDesign::Body", "Body")
        body.Placement.Base = App.Vector(0, 7, 0)
        inner.addObject(body)
        feature = self.doc.addObject("PartDesign::AdditiveBox", "PBox")
        body.addObject(feature)
        root = self.doc.addObject("Part::Box", "Root")
        self.doc.recompute()
        # FreeCAD's own resolver of the global point, through the whole path.
        oracle = Part.getShape(outer, "Inner.Body.PBox.Vertex1", needSubElement=True).Vertexes[0].Point
        line = self.line((feature, "Vertex1"), (root, "Vertex2"))
        self.assertEqual(self.ends(line), [tuple(round(c, 6) for c in oracle), (0, 0, 0)])
        self.assertEqual(inner.Group, [body])


if __name__ == "__main__":
    unittest.main()

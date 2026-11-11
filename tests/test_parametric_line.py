"""A parametric line links its vertices globally: moving it never drags the profiles it measures.

A line joins two vertices, or runs from one vertex along a global axis or a custom vector, with a length.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.parametric_line import CreateParametricLineCommand, ParametricLine, make_line_from_vertex

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

    def global_ends(self, line):
        placement = line.getGlobalPlacement() if line.getParentGeoFeatureGroup() else App.Placement()
        return [tuple(round(c, 6) for c in placement.multVec(v.Point)) for v in line.Shape.Vertexes]

    def test_new_line_links_vertices_globally(self):
        _, a = self.part("Left", (0, 0, 0))
        _, b = self.part("Right", (100, 0, 0))
        line = self.line((a, "Vertex1"), (b, "Vertex1"))
        self.assertEqual(line.Direction, "Vertex2")
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

    def test_migrated_line_is_listed_once_by_its_vertices_and_can_be_deleted(self):
        a = self.doc.addObject("Part::Box", "A")
        b = self.doc.addObject("Part::Box", "B")
        line = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        line.addProperty("App::PropertyLinkSub", "Vertex1", "ParametricLine", "First Vertex")
        line.addProperty("App::PropertyLinkSub", "Vertex2", "ParametricLine", "Second Vertex")
        line.Vertex1 = (a, "Vertex1")
        line.Vertex2 = (b, "Vertex2")
        ParametricLine.onDocumentRestored(None, line)
        self.assertEqual(line.Vertex1, (a, ["Vertex1"]))
        self.assertEqual(line.Vertex2, (b, ["Vertex2"]))
        self.assertEqual(a.InList.count(line), 1)
        self.assertEqual(b.InList.count(line), 1)
        self.doc.removeObject(line.Name)
        self.assertIsNone(self.doc.getObject("ParametricLine"))
        self.assertEqual(a.InList, [])
        self.assertEqual(b.InList, [])
        self.doc.removeObject("A")
        self.doc.removeObject("B")
        self.assertEqual(self.doc.Objects, [])

    def test_restored_line_of_an_earlier_version_still_joins_its_two_vertices(self):
        line = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        line.addProperty(GLOBAL, "Vertex1", "ParametricLine", "First Vertex")
        line.addProperty(GLOBAL, "Vertex2", "ParametricLine", "Second Vertex")
        a = self.doc.addObject("Part::Box", "A")
        b = self.doc.addObject("Part::Box", "B")
        b.Placement.Base = App.Vector(0, 0, 40)
        line.Vertex1 = (a, "Vertex2")
        line.Vertex2 = (b, "Vertex8")
        ParametricLine.onDocumentRestored(None, line)
        line.Proxy = ParametricLine.__new__(ParametricLine)
        self.assertEqual(line.Direction, "Vertex2")
        self.assertEqual(line.CustomDirection, App.Vector(0, 0, -1))
        self.assertEqual(line.getGroupOfProperty("Length"), "ParametricLine")
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(0, 0, 0), (10, 10, 40)])

    # From a vertex along a direction.

    def test_line_from_a_vertex_runs_along_each_global_axis(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        expected = {
            "+X": (730, 10, 0),
            "-X": (-710, 10, 0),
            "+Y": (10, 730, 0),
            "-Y": (10, -710, 0),
            "+Z": (10, 10, 720),
            "-Z": (10, 10, -720),
        }
        for direction, end in expected.items():
            with self.subTest(direction=direction):
                line = make_line_from_vertex((box, "Vertex8"), direction, 720)
                self.assertEqual(line.Direction, direction)
                self.assertEqual(line.Vertex1, (box, ["Vertex8"]))
                self.assertIsNone(line.Vertex2)
                self.assertEqual(line.getTypeIdOfProperty("Vertex1"), GLOBAL)
                self.assertEqual(self.ends(line), [(10, 10, 0), end])

    def test_custom_vector_gives_only_the_direction(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        line = make_line_from_vertex((box, "Vertex8"), "Custom", 10, App.Vector(30, 0, -40))
        self.assertEqual(line.CustomDirection, App.Vector(30, 0, -40))
        self.assertEqual(self.ends(line), [(10, 10, 0), (16, 10, -8)])

    def test_angle_in_a_global_plane_counterclockwise_from_its_first_axis(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        for plane, angle, end in (
            ("XY", 0, (20, 10, 0)),
            ("XY", 90, (10, 20, 0)),
            ("XZ", 90, (10, 10, 10)),
            ("XZ", -90, (10, 10, -10)),
            ("YZ", 0, (10, 20, 0)),
            ("YZ", 180, (10, 0, 0)),
            ("XY", 30, (18.660254, 15, 0)),
        ):
            with self.subTest(plane=plane, angle=angle):
                line = make_line_from_vertex((box, "Vertex8"), "Angle", 10, plane=plane, angle=angle)
                self.assertEqual((line.Direction, line.Plane, line.Angle.Value), ("Angle", plane, angle))
                self.assertEqual(self.ends(line), [(10, 10, 0), end])

    def test_the_angle_takes_expressions_and_keeps_the_custom_vector(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        line = make_line_from_vertex((box, "Vertex8"), "Angle", 10, App.Vector(1, 2, 3), plane="XZ", angle=0)
        line.setExpression("Angle", "Box.Height * 9")
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(10, 10, 0), (10, 10, 10)])
        self.assertEqual(line.CustomDirection, App.Vector(1, 2, 3))

    def test_start_follows_the_vertex_and_length_takes_expressions(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        line = make_line_from_vertex((box, "Vertex8"), "-Z", 100)
        line.setExpression("Length", "Box.Height * 72")
        box.Length = 50
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(50, 10, 0), (50, 10, -720)])

    def test_axes_stay_global_for_a_vertex_and_a_line_in_rotated_parts(self):
        source, box = self.part("Source", (100, 0, 0))
        source.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 90)
        self.doc.recompute()
        start = tuple(round(c, 6) for c in source.Placement.multVec(box.Shape.Vertexes[7].Point))
        line = make_line_from_vertex((box, "Vertex8"), "+X", 50)
        holder = self.doc.addObject("App::Part", "Holder")
        holder.Placement = App.Placement(App.Vector(0, 50, 0), App.Rotation(App.Vector(1, 0, 0), 90))
        holder.addObject(line)
        line.touch()
        self.doc.recompute()
        self.assertEqual(self.global_ends(line), [start, (start[0] + 50, start[1], start[2])])

    def test_zero_vector_or_zero_length_draws_no_line(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        for direction, length, custom in (("Custom", 10, App.Vector(0, 0, 0)), ("-Z", 0, None)):
            with self.subTest(direction=direction, length=length):
                line = make_line_from_vertex((box, "Vertex8"), direction, length, custom)
                self.assertTrue(line.Shape.isNull())

    def test_a_line_made_invalid_keeps_no_stale_shape(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        for prop, value in (("Length", 0), ("CustomDirection", App.Vector(0, 0, 0))):
            with self.subTest(prop=prop):
                line = make_line_from_vertex((box, "Vertex8"), "Custom", 10, App.Vector(0, 0, -1))
                self.assertEqual(self.ends(line), [(10, 10, 0), (10, 10, -10)])
                setattr(line, prop, value)
                self.doc.recompute()
                self.assertTrue(line.Shape.isNull())

    def test_a_new_line_from_a_vertex_defaults_to_100_mm(self):
        box = self.doc.addObject("Part::Box", "Box")
        line = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        ParametricLine(line)
        line.Vertex1 = (box, "Vertex8")
        line.Direction = "-Z"
        self.doc.recompute()
        self.assertEqual(line.Length.Value, 100)
        self.assertEqual(self.ends(line), [(10, 10, 0), (10, 10, -100)])

    def test_line_from_a_vertex_survives_save_and_reopen(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        line = make_line_from_vertex((box, "Vertex8"), "Custom", 10, App.Vector(30, 0, -40))
        line.setExpression("Length", "Box.Height * 2")
        self.doc.recompute()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "direction.FCStd")
        name = line.Name
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.addCleanup(lambda n=self.doc.Name: App.closeDocument(n) if n in App.listDocuments() else None)
        line = self.doc.getObject(name)
        self.assertEqual((line.Direction, line.CustomDirection), ("Custom", App.Vector(30, 0, -40)))
        self.doc.getObject("Box").Height = 15
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(10, 10, 0), (28, 10, -24)])

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

    def test_a_line_saved_before_the_angle_mode_gets_it_and_keeps_its_direction(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        line = make_line_from_vertex((box, "Vertex8"), "Custom", 10, App.Vector(30, 0, -40))
        # What an earlier version saved: no Angle direction, no Plane and no Angle.
        line.Direction = ["Vertex2", "+X", "-X", "+Y", "-Y", "+Z", "-Z", "Custom"]
        line.Direction = "Custom"
        line.removeProperty("Plane")
        line.removeProperty("Angle")
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "before-angle.FCStd")
        name = line.Name
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.addCleanup(lambda n=self.doc.Name: App.closeDocument(n) if n in App.listDocuments() else None)
        line = self.doc.getObject(name)
        self.assertEqual(line.Direction, "Custom")
        self.assertIn("Angle", line.getEnumerationsOfProperty("Direction"))
        self.assertEqual((line.Plane, line.Angle.Value), ("XY", 0))
        line.Direction = "Angle"
        self.doc.recompute()
        self.assertEqual(self.ends(line), [(10, 10, 0), (20, 10, 0)])


if __name__ == "__main__":
    unittest.main()

"""Cutout command with one face and one sketch preselected: the cutout is created directly, as before."""

import math
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from test_cutout_flow import HOLE_RADIUS, UP, WALL, CutoutFixture

from freecad.maxproframe import create_extruded_cutout_tool
from freecad.maxproframe.create_extruded_cutout_tool import AddExtrudedCutoutCommandClass
from freecad.maxproframe.trimmed_profile import TrimmedProfile


class TestDirectCutout(CutoutFixture):
    def hole_sketch(self, body, top):
        sketch = self.doc.addObject("Sketcher::SketchObject", "HoleSketch")
        center = body.Shape.getElement(top).CenterOfMass
        sketch.Placement.Base = App.Vector(0, 0, center.z)
        sketch.addGeometry(Part.Circle(App.Vector(center.x, center.y, 0), UP, HOLE_RADIUS))
        self.doc.recompute()
        return sketch

    def run_direct(self):
        """Run the command on the current selection; return the cut type panels it opened."""
        created = []
        base = create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_extruded_cutout_tool, "CreateExtrudedCutoutTaskPanel", Recording):
            AddExtrudedCutoutCommandClass().Activated()
        return created

    def test_a_face_and_a_sketch_make_the_cutout_directly_in_either_order(self):
        for order in ("face first", "sketch first"):
            with self.subTest(order=order):
                self.close_dialog()
                body = self.tube()
                part = self.doc.addObject("App::Part", "Part")
                part.addObjects([body.AttachmentSupport[0][0], body])
                top = self.face_towards(body, UP)
                sketch = self.hole_sketch(body, top)
                items = [(body, top), (sketch, "")]
                self.select(*(items if order == "face first" else items[::-1]))
                before = self.names()
                panels = self.run_direct()
                cutout = self.doc.getObject(f"{body.Name}_Ex")
                self.assertEqual([obj.Name for obj in self.doc.Objects if obj.Name not in before], [cutout.Name])
                # The cut type panel opens on the new cutout.
                self.assertTrue(Gui.Control.activeDialog())
                self.assertEqual([panel.obj for panel in panels], [cutout])
                self.assertEqual(cutout.baseObject, (body, [top]))
                self.assertEqual(cutout.Sketch, sketch)
                self.assertEqual(cutout.CutType, "Through All")
                self.assertEqual(cutout.getParentGeoFeatureGroup(), part)
                self.assertEqual(sketch.getParentGeoFeatureGroup(), part)
                self.assertEqual(sketch.MapMode, "Deactivated")
                self.assertEqual(sketch.ExternalGeometry, [])
                self.doc.recompute()
                self.assertEqual(cutout.getStatusString(), "Valid")
                removed = 2 * math.pi * HOLE_RADIUS**2 * WALL
                self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)

    def trim_against_another_part(self):
        """(side Part, back Part, trim in back cut against the side profile)."""
        side = self.doc.addObject("App::Part", "Side")
        back = self.doc.addObject("App::Part", "Back")
        side_path = self.make_sketch(((0, 0, 0), (0, 200, 0)))
        back_path = self.make_sketch(((200, 0, 0), (0, 0, 0)))
        side_profile = self.make_profile(side_path, "Edge1")
        back_profile = self.make_profile(back_path, "Edge1")
        side.addObjects([side_path, side_profile])
        back.addObjects([back_path, back_profile])
        trim = self.doc.addObject("Part::FeaturePython", "Miter")
        back.addObject(trim)
        TrimmedProfile(trim)
        trim.TrimmedBody = back_profile
        trim.TrimmingBoundary = [(side_profile, ("Edge1",))]
        trim.TrimmedProfileType = "End Miter"
        self.doc.recompute()
        return side, back, trim

    def test_a_sketch_in_the_part_with_external_geometry_of_the_trim_leaves_another_part_untouched(self):
        # The sketch is already in the trim's Part: adding it again would drag what its external geometry links to.
        side, back, trim = self.trim_against_another_part()
        top = self.face_towards(trim, UP)
        sketch = self.hole_sketch(trim, top)
        back.addObject(sketch)
        sketch.AttachmentSupport = [(trim, top)]
        sketch.MapMode = "FlatFace"
        sketch.addExternal(trim.Name, "Edge1")
        self.doc.recompute()
        side_group, back_group = list(side.Group), list(back.Group)
        self.select((trim, top), (sketch, ""))
        self.run_direct()
        cutout = self.doc.getObject(f"{trim.Name}_Ex")
        self.assertEqual(side.Group, side_group)
        self.assertEqual(sorted(o.Name for o in back.Group), sorted(o.Name for o in back_group + [cutout]))
        self.assertEqual(sketch.getParentGeoFeatureGroup(), back)

    def test_a_cutout_on_a_trim_against_another_part_leaves_that_part_untouched(self):
        # A Part receiving an object pulls in what it links to locally: the trim's boundary is in another Part.
        side, back, trim = self.trim_against_another_part()
        top = self.face_towards(trim, UP)
        sketch = self.hole_sketch(trim, top)
        side_group, back_group = list(side.Group), list(back.Group)
        self.select((trim, top), (sketch, ""))
        self.run_direct()
        cutout = self.doc.getObject(f"{trim.Name}_Ex")
        self.assertEqual(side.Group, side_group)
        self.assertEqual(sorted(o.Name for o in back.Group), sorted(o.Name for o in back_group + [cutout, sketch]))
        self.assertEqual(cutout.getParentGeoFeatureGroup(), back)
        self.assertEqual(sketch.getParentGeoFeatureGroup(), back)


if __name__ == "__main__":
    unittest.main()

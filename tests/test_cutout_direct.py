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


if __name__ == "__main__":
    unittest.main()

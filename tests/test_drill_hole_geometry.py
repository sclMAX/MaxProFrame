"""Drill Hole geometry: round holes on a planar face, placed from a vertex of that face."""

import math
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from miter_helpers import use_language
from test_end_miter_geometry import CENTER
from test_notch_geometry import TrimFixture

from freecad.maxproframe._utils import is_extrudedcutout
from freecad.maxproframe.drill_hole import make_drill_hole

UP = App.Vector(0, 0, 1)
# The profile: a 50 x 50 x 2 square tube along X, from -50 to 350 (300 long plus 50 at each end).
PATH = ((0, 0, 0), (300, 0, 0))
WALL = 2.0
DIAMETER = 10.0
# Removed by one hole of DIAMETER through one wall.
ONE_HOLE = math.pi * (DIAMETER / 2) ** 2 * WALL


class DrillHoleFixture(TrimFixture):
    def setUp(self):
        super().setUp()
        # Messages are checked in English: an earlier test may leave FreeCAD in Spanish.
        use_language(self, "English", "en_US")

    def tube(self):
        return self.make_profile(self.make_sketch(PATH), "Edge1", **CENTER)

    def vertex_at(self, obj, point):
        """Name of the vertex of ``obj`` at ``point``."""
        for index, vertex in enumerate(obj.Shape.Vertexes, start=1):
            if vertex.Point.isEqual(App.Vector(*point), 1e-6):
                return f"Vertex{index}"
        self.fail(f"no vertex at {point}")

    def hole(self, body, face, vertex, along, across, **values):
        obj = make_drill_hole((body, (face,)), vertex)
        obj.OffsetAlong = along
        obj.OffsetAcross = across
        obj.Diameter = values.pop("diameter", DIAMETER)
        for name, value in values.items():
            setattr(obj, name, value)
        self.doc.recompute()
        return obj

    def empty(self, shape, *point):
        return not shape.isInside(App.Vector(*point), 1e-7, True)


class TestDrillHoleGeometry(DrillHoleFixture):
    def test_a_hole_is_drilled_through_the_wall_under_the_face_at_the_offsets_from_the_vertex(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(obj.CutType, "One wall")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        # Hole center (-20, 0): empty in the top wall, the bottom wall is intact.
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        self.assertFalse(self.empty(obj.Shape, -20, 0, -24))
        self.assertFalse(self.empty(obj.Shape, -20 + DIAMETER, 0, 24))

    def test_offsets_go_into_the_face_from_whichever_corner_is_picked(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (350, 25, 25))
        obj = self.hole(body, top, corner, 30.0, 10.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, 320, 15, 24))

    def test_a_linear_pattern_drills_count_holes_one_pitch_apart_along_the_profile(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0, Count=3, Pitch=40.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * ONE_HOLE, places=3)
        for x in (-20, 20, 60):
            self.assertTrue(self.empty(obj.Shape, x, 0, 24), x)
        self.assertFalse(self.empty(obj.Shape, 100, 0, 24))

    def test_through_all_drills_every_wall_under_the_hole(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        obj = self.hole(body, top, self.vertex_at(body, (-50, -25, 25)), 30.0, 25.0, CutType="Through All")
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 2 * ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, -24))

    def test_a_distance_depth_drills_that_deep_only(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, (-50, -25, 25))
        obj = self.hole(body, top, corner, 30.0, 25.0, CutType="Distance", ExtrusionLength=1.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE / 2, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24.5))
        self.assertFalse(self.empty(obj.Shape, -20, 0, 23.5))

    def test_a_curved_face_is_refused_with_the_reason(self):
        body = self.tube()
        body.Family = "Pipe"
        self.doc.recompute()
        curved = next(
            f"Face{index}"
            for index, face in enumerate(body.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        obj = self.hole(body, curved, "Vertex1", 30.0, 0.0)
        self.assertIn(f"Drill Hole: {curved} of {body.Label} is not planar.", obj.getStatusString())

    def test_a_hole_is_a_cutout_of_its_profile_for_the_cut_list(self):
        body = self.tube()
        body.PID = "P7"
        top = self.face_towards(body, UP)
        obj = self.hole(body, top, self.vertex_at(body, (-50, -25, 25)), 30.0, 25.0)
        self.assertTrue(is_extrudedcutout(obj))
        self.assertEqual((obj.PID, obj.SizeName, obj.Family), (body.PID, body.SizeName, body.Family))
        self.assertAlmostEqual(obj.Length.Value, 400.0, places=5)
        self.assertEqual(obj.Label, f"{body.Label}_Dh")


class TestDrillHoleCentered(DrillHoleFixture):
    """CenterAlong and CenterAcross measure the offsets from the middle of the face (S3), away from the corner (S4).

    The top face of the tube runs from x = -50 to 350 and y = -25 to 25: its middle is (150, 0).
    """

    CORNER = (-50, -25, 25)
    FAR_CORNER = (350, 25, 25)

    def centered(self, corner, along, across, **values):
        body = self.tube()
        obj = self.hole(body, self.face_towards(body, UP), self.vertex_at(body, corner), along, across, **values)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        return obj

    def test_a_new_hole_measures_from_its_corner(self):
        body = self.tube()
        obj = make_drill_hole((body, (self.face_towards(body, UP),)), self.vertex_at(body, self.CORNER))
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, False))
        self.assertEqual(obj.getGroupOfProperty("CenterAlong"), "DrillHole")
        self.assertEqual(obj.getGroupOfProperty("CenterAcross"), "DrillHole")
        self.assertEqual(
            obj.getDocumentationOfProperty("CenterAlong"),
            "Measure the offset along from the middle of the face length",
        )
        self.assertEqual(
            obj.getDocumentationOfProperty("CenterAcross"),
            "Measure the offset across from the middle of the face width",
        )

    def test_center_along_measures_the_offset_along_from_the_middle_of_the_face_length(self):
        obj = self.centered(self.CORNER, 0.0, 10.0, CenterAlong=True)
        self.assertTrue(self.empty(obj.Shape, 150, -15, 24))
        self.assertFalse(self.empty(obj.Shape, -50, -15, 24))

    def test_center_across_measures_the_offset_across_from_the_middle_of_the_face_width(self):
        obj = self.centered(self.CORNER, 30.0, 0.0, CenterAcross=True)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        self.assertFalse(self.empty(obj.Shape, -20, -25 + 5.5, 24))

    def test_both_centers_put_the_hole_in_the_middle_of_the_face_with_offsets_zero(self):
        for corner in (self.CORNER, self.FAR_CORNER):
            with self.subTest(corner=corner):
                obj = self.centered(corner, 0.0, 0.0, CenterAlong=True, CenterAcross=True)
                self.assertTrue(self.empty(obj.Shape, 150, 0, 24))

    def test_offsets_from_the_middle_are_positive_away_from_the_corner_and_negative_toward_it(self):
        # S4: from CORNER away is +x and +y; from FAR_CORNER away is -x and -y.
        for corner, along, across, center in (
            (self.CORNER, 30.0, 10.0, (180, 10)),
            (self.CORNER, -30.0, -10.0, (120, -10)),
            (self.FAR_CORNER, 30.0, 10.0, (120, -10)),
            (self.FAR_CORNER, -30.0, -10.0, (180, 10)),
        ):
            with self.subTest(corner=corner, along=along, across=across):
                obj = self.centered(corner, along, across, CenterAlong=True, CenterAcross=True)
                self.assertTrue(self.empty(obj.Shape, *center, 24), center)
                self.assertFalse(self.empty(obj.Shape, 150, 0, 24))

    def test_a_row_of_holes_starts_at_the_middle_and_goes_away_from_the_corner(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, self.FAR_CORNER)
        obj = self.hole(body, top, corner, 0.0, 0.0, CenterAlong=True, CenterAcross=True, Count=3, Pitch=40.0)
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * ONE_HOLE, places=3)
        for x in (150, 110, 70):
            self.assertTrue(self.empty(obj.Shape, x, 0, 24), x)

    def test_a_hole_saved_before_the_centers_keeps_its_place_and_gains_them_off(self):
        # S5: a document saved before CenterAlong and CenterAcross opens with the holes where they were.
        body = self.tube()
        obj = self.hole(body, self.face_towards(body, UP), self.vertex_at(body, self.CORNER), 30.0, 25.0)
        for name in ("CenterAlong", "CenterAcross"):
            obj.removeProperty(name)
        self.assertFalse(hasattr(obj, "CenterAlong"))
        obj.touch()
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        obj.Proxy.onDocumentRestored(obj)
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, False))
        self.assertEqual(obj.getGroupOfProperty("CenterAcross"), "DrillHole")
        obj.touch()
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(obj.Shape, -20, 0, 24))
        # Restored again: nothing changes.
        obj.Proxy.onDocumentRestored(obj)
        self.assertEqual((obj.CenterAlong, obj.CenterAcross), (False, False))

    def test_a_saved_document_without_the_centers_opens_with_the_holes_in_place(self):
        # S5 through a real save and open.
        body = self.tube()
        obj = self.hole(body, self.face_towards(body, UP), self.vertex_at(body, self.FAR_CORNER), 30.0, 10.0)
        for name in ("CenterAlong", "CenterAcross"):
            obj.removeProperty(name)
        folder = tempfile.mkdtemp(prefix="drill_hole_restore_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "old.FCStd")
        self.doc.saveCopy(path)
        doc = App.openDocument(path)
        self.addCleanup(App.closeDocument, doc.Name)
        restored = doc.getObject(obj.Name)
        self.assertEqual((restored.CenterAlong, restored.CenterAcross), (False, False))
        restored.touch()
        doc.recompute()
        self.assertEqual(restored.getStatusString(), "Valid")
        self.assertAlmostEqual(restored.Shape.Volume, doc.getObject(body.Name).Shape.Volume - ONE_HOLE, places=3)
        self.assertTrue(self.empty(restored.Shape, 320, 15, 24))


if __name__ == "__main__":
    unittest.main()

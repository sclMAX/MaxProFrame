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
        # Three holes: the one at the point and two forward.
        obj = self.hole(body, top, corner, 30.0, 25.0, AlongForwardCount=2, AlongForwardPitch=40.0)
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
    """CenterAlong and CenterAcross measure the offsets from the middle of the face (S3).

    A centered direction is fixed (S7): along toward the end of the profile (+x), across +y on the top face.
    A direction measured from the corner goes into the face from it (S4).
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

    def test_centered_offsets_are_positive_toward_the_profile_end_and_a_fixed_side_whatever_the_corner(self):
        # S7: from the middle, positive along is +x (the end of the profile) and across +y, from either corner.
        for corner in (self.CORNER, self.FAR_CORNER):
            for along, across, center in ((30.0, 10.0, (180, 10)), (-30.0, -10.0, (120, -10))):
                with self.subTest(corner=corner, along=along, across=across):
                    obj = self.centered(corner, along, across, CenterAlong=True, CenterAcross=True)
                    self.assertTrue(self.empty(obj.Shape, *center, 24), center)
                    self.assertFalse(self.empty(obj.Shape, 150, 0, 24))

    def test_a_direction_measured_from_the_corner_stays_positive_into_the_face(self):
        # S7, S4: only a centered direction is fixed; the other one goes into the face from the corner.
        for corner, centers, center in (
            (self.FAR_CORNER, {"CenterAlong": True}, (180, 15)),
            (self.FAR_CORNER, {"CenterAcross": True}, (320, 10)),
            (self.CORNER, {"CenterAlong": True}, (180, -15)),
            (self.CORNER, {"CenterAcross": True}, (-20, 10)),
            (self.FAR_CORNER, {}, (320, 15)),
            (self.CORNER, {}, (-20, -15)),
        ):
            with self.subTest(corner=corner, centers=centers):
                obj = self.centered(corner, 30.0, 10.0, **centers)
                self.assertTrue(self.empty(obj.Shape, *center, 24), center)

    def test_a_centered_row_of_holes_goes_toward_the_profile_end_whatever_the_corner(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        corner = self.vertex_at(body, self.FAR_CORNER)
        obj = self.hole(
            body,
            top,
            corner,
            0.0,
            0.0,
            CenterAlong=True,
            CenterAcross=True,
            AlongForwardCount=2,
            AlongForwardPitch=40.0,
        )
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, body.Shape.Volume - 3 * ONE_HOLE, places=3)
        for x in (150, 190, 230):
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


# The pattern properties of a drill hole: a count and a pitch for each side of each axis, and the hole at the point.
PATTERN_SIDES = ("AlongBackward", "AlongForward", "AcrossBackward", "AcrossForward")
PATTERN_PROPERTIES = tuple(f"{side}{kind}" for side in PATTERN_SIDES for kind in ("Count", "Pitch")) + ("HoleAtPoint",)
NO_HOLE = "Drill Hole: no hole to drill. Check Hole at the point or set a count in the pattern."


class PatternFixture(DrillHoleFixture):
    CORNER = (-50, -25, 25)
    FAR_CORNER = (350, 25, 25)

    def round_faces(self, shape):
        return sum(isinstance(face.Surface, Part.Cylinder) for face in shape.Faces)

    def assert_holes(self, obj, points, solid=()):
        """``obj`` drilled exactly one hole at each of ``points`` (x, y) of the top wall, and none at ``solid``."""
        self.assertEqual(obj.getStatusString(), "Valid")
        base = obj.baseObject[0].Shape
        # One round face for each hole through the top wall.
        self.assertEqual(self.round_faces(obj.Shape) - self.round_faces(base), len(points))
        self.assertAlmostEqual(obj.Shape.Volume, base.Volume - len(points) * ONE_HOLE, places=3)
        for point in points:
            self.assertTrue(self.empty(obj.Shape, *point, 24), point)
        for point in solid:
            self.assertFalse(self.empty(obj.Shape, *point, 24), point)

    def pattern_hole(self, corner, along, across, **values):
        body = self.tube()
        return self.hole(body, self.face_towards(body, UP), self.vertex_at(body, corner), along, across, **values)


class TestDrillHolePattern(PatternFixture):
    """S2, S3: holes on each side of the point, along and across (a grid), and the hole at the point (L6).

    Forward is the positive direction of the offset: into the face from CORNER (+x along, +y across), toward
    the end of the path (+x) and +y across from the middle of the top face, (150, 0).
    """

    USER_EXAMPLE = dict(AlongBackwardCount=3, AlongBackwardPitch=20.0, AlongForwardCount=5, AlongForwardPitch=30.0)

    def test_a_new_hole_has_the_pattern_properties_and_no_count_or_pitch(self):
        body = self.tube()
        obj = make_drill_hole((body, (self.face_towards(body, UP),)), self.vertex_at(body, self.CORNER))
        for name in PATTERN_PROPERTIES:
            self.assertEqual(obj.getGroupOfProperty(name), "DrillHole", name)
        self.assertEqual([getattr(obj, f"{side}Count") for side in PATTERN_SIDES], [0, 0, 0, 0])
        self.assertEqual([getattr(obj, f"{side}Pitch").Value for side in PATTERN_SIDES], [50.0] * 4)
        self.assertIs(obj.HoleAtPoint, True)
        self.assertEqual(obj.getTypeIdOfProperty("AlongForwardCount"), "App::PropertyIntegerConstraint")
        self.assertEqual(obj.getTypeIdOfProperty("AlongForwardPitch"), "App::PropertyLength")
        for name in ("Count", "Pitch"):
            self.assertNotIn(name, obj.PropertiesList)
        self.assertEqual(
            [obj.getDocumentationOfProperty(name) for name in PATTERN_PROPERTIES],
            [
                "Number of holes backward of the point, along the profile",
                "Distance between the holes backward of the point, along the profile",
                "Number of holes forward of the point, along the profile",
                "Distance between the holes forward of the point, along the profile",
                "Number of holes backward of the point, across the profile",
                "Distance between the holes backward of the point, across the profile",
                "Number of holes forward of the point, across the profile",
                "Distance between the holes forward of the point, across the profile",
                "Drill a hole at the point the offsets give",
            ],
        )
        # A count stays from 0 to 1000.
        obj.AlongForwardCount = 2000
        self.assertEqual(obj.AlongForwardCount, 1000)
        obj.AlongForwardCount = -1
        self.assertEqual(obj.AlongForwardCount, 0)

    def test_the_users_example_drills_three_backward_the_point_and_five_forward_from_a_corner(self):
        # S2: "<- 3 (cada 20mm) (centro) 5 (cada 30mm) ->", the point 100 mm into the face from the corner.
        obj = self.pattern_hole(self.CORNER, 100.0, 25.0, **self.USER_EXAMPLE)
        self.assert_holes(
            obj,
            [(x, 0) for x in (-10, 10, 30, 50, 80, 110, 140, 170, 200)],
            solid=((-30, 0), (65, 0), (230, 0), (50, 15)),
        )

    def test_the_users_example_from_the_face_center_goes_forward_toward_the_end_of_the_path(self):
        obj = self.pattern_hole(self.FAR_CORNER, 0.0, 0.0, CenterAlong=True, CenterAcross=True, **self.USER_EXAMPLE)
        self.assert_holes(
            obj,
            [(x, 0) for x in (90, 110, 130, 150, 180, 210, 240, 270, 300)],
            solid=((70, 0), (165, 0), (330, 0)),
        )

    def test_holes_along_and_across_make_a_grid(self):
        for corner, values, points, solid in (
            (
                self.FAR_CORNER,
                dict(CenterAlong=True, CenterAcross=True, AcrossForwardCount=1, AcrossForwardPitch=15.0),
                [(x, y) for x in (150, 190, 230) for y in (0, 15)],
                ((150, -15), (270, 0)),
            ),
            (
                self.CORNER,
                dict(AcrossBackwardCount=1, AcrossBackwardPitch=15.0, AcrossForwardCount=1, AcrossForwardPitch=15.0),
                [(x, y) for x in (-20, 20, 60) for y in (-15, 0, 15)],
                ((100, 0), (0, 0)),
            ),
        ):
            with self.subTest(corner=corner, values=values):
                along = 30.0 if corner == self.CORNER else 0.0
                across = 25.0 if corner == self.CORNER else 0.0
                obj = self.pattern_hole(corner, along, across, AlongForwardCount=2, AlongForwardPitch=40.0, **values)
                self.assert_holes(obj, points, solid)

    def test_without_the_hole_at_the_point_a_centered_pair_has_no_hole_in_the_middle(self):
        # S3: a row along, or across, without the hole at the point still sits on the point's line.
        centered = dict(CenterAlong=True, CenterAcross=True, HoleAtPoint=False)
        for values, points in (
            (
                dict(AlongBackwardCount=1, AlongBackwardPitch=30.0, AlongForwardCount=1, AlongForwardPitch=30.0),
                [(120, 0), (180, 0)],
            ),
            (
                dict(AcrossBackwardCount=1, AcrossBackwardPitch=15.0, AcrossForwardCount=1, AcrossForwardPitch=15.0),
                [(150, -15), (150, 15)],
            ),
        ):
            with self.subTest(values=values):
                obj = self.pattern_hole(self.CORNER, 0.0, 0.0, **centered, **values)
                self.assert_holes(obj, points, solid=((150, 0),))

    def test_no_hole_at_all_is_an_error_with_a_message(self):
        obj = self.pattern_hole(self.CORNER, 30.0, 25.0, HoleAtPoint=False)
        self.assertNotEqual(obj.getStatusString(), "Valid")
        self.assertIn(NO_HOLE, obj.getStatusString())

    def test_more_than_1000_holes_is_an_error_with_a_message(self):
        for values, total in (
            (dict(AlongForwardCount=1000), 1001),
            (dict(AlongForwardCount=40, AcrossForwardCount=24), 1025),
        ):
            with self.subTest(values=values):
                obj = self.pattern_hole(self.CORNER, 30.0, 25.0, **values)
                self.assertNotEqual(obj.getStatusString(), "Valid")
                self.assertIn(f"Drill Hole: the pattern makes {total} holes, at most 1000.", obj.getStatusString())


class TestDrillHoleCountPitchMigration(PatternFixture):
    """S4: a drill hole saved by 1.5.0 with Count and Pitch opens with the same holes."""

    def old_hole(self):
        """A drill hole as 1.5.0 saved it: Count 4 and Pitch 60 mm, each driven by a VarSet: (body, hole)."""
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyInteger", "Holes")
        varset.Holes = 4
        varset.addProperty("App::PropertyLength", "Spacing")
        varset.Spacing = 60.0
        body = self.tube()
        obj = self.hole(body, self.face_towards(body, UP), self.vertex_at(body, self.CORNER), 30.0, 25.0)
        for name in PATTERN_PROPERTIES:
            obj.removeProperty(name)
        obj.addProperty("App::PropertyIntegerConstraint", "Count", "DrillHole", "Number of holes").Count = (
            4,
            1,
            1000,
            1,
        )
        obj.addProperty("App::PropertyLength", "Pitch", "DrillHole", "Distance between two holes, along the profile")
        obj.Pitch = 60.0
        obj.setExpression("Count", f"{varset.Name}.Holes")
        obj.setExpression("Pitch", f"{varset.Name}.Spacing")
        self.doc.recompute()
        return body, obj

    def reopen(self, obj):
        folder = tempfile.mkdtemp(prefix="drill_hole_count_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "v150.FCStd")
        self.doc.saveCopy(path)
        doc = App.openDocument(path)
        self.addCleanup(App.closeDocument, doc.Name)
        return doc, doc.getObject(obj.Name)

    def test_a_saved_count_and_pitch_open_as_holes_forward_with_the_same_centers_and_expressions(self):
        body, obj = self.old_hole()
        holes = [(x, 0) for x in (-20, 40, 100, 160)]
        doc, restored = self.reopen(obj)
        for name in ("Count", "Pitch"):
            self.assertNotIn(name, restored.PropertiesList)
        self.assertEqual(
            [getattr(restored, name) for name in PATTERN_PROPERTIES],
            [
                0,
                App.Units.Quantity("50 mm"),
                3,
                App.Units.Quantity("60 mm"),
                0,
                App.Units.Quantity("50 mm"),
                0,
                App.Units.Quantity("50 mm"),
                True,
            ],
        )
        # Set as "(VarSet.Holes) - 1"; FreeCAD drops the parentheses it does not need.
        self.assertEqual(
            dict(restored.ExpressionEngine),
            {"AlongForwardCount": "VarSet.Holes - 1", "AlongForwardPitch": "VarSet.Spacing"},
        )
        restored.touch()
        doc.recompute()
        self.assertEqual(restored.AlongForwardCount, 3)
        self.assert_holes(restored, holes, solid=((220, 0), (10, 0)))
        # The expressions still drive the holes.
        varset = doc.getObject("VarSet")
        varset.Holes = 5
        varset.Spacing = 50.0
        doc.recompute()
        self.assertEqual(restored.AlongForwardCount, 4)
        self.assert_holes(restored, [(x, 0) for x in (-20, 30, 80, 130, 180)])

    def test_a_saved_count_and_pitch_without_expressions_open_as_holes_forward(self):
        body, obj = self.old_hole()
        obj.setExpression("Count", None)
        obj.setExpression("Pitch", None)
        obj.Count = 1
        self.doc.recompute()
        doc, restored = self.reopen(obj)
        self.assertNotIn("Count", restored.PropertiesList)
        self.assertEqual((restored.AlongForwardCount, restored.AlongForwardPitch.Value), (0, 60.0))
        self.assertEqual(dict(restored.ExpressionEngine), {})
        restored.touch()
        doc.recompute()
        self.assert_holes(restored, [(-20, 0)], solid=((40, 0),))


if __name__ == "__main__":
    unittest.main()

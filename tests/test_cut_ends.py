"""Cut ends: the angle of each end, the face it is seen on and how both ends sit, read on the finished solid."""

import math
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, CHAINED
from test_extend_cut_geometry import ExtendCutFixture

from freecad.maxproframe.cut_ends import cut_ends
from freecad.maxproframe.extruded_cutout import ExtrudedCutout
from freecad.maxproframe.profile import Profile

ALONG_X = ((0, 0, 0), (300, 0, 0))
# A target crossing the X axis at x = 400, running at 60 degrees from it: its faces are 30 degrees off square.
SLANTED_TARGET = ((400 - 200 / math.tan(math.radians(60)), -200, 0), (400 + 200 / math.tan(math.radians(60)), 200, 0))


class CutEndsFixture(ExtendCutFixture):
    def tube(self, sketch, edge="Edge1", family="Rectangular Hollow", width=80.0, height=40.0, extension=0.0, **bevels):
        """An 80x40 tube (or ``family``) on ``edge`` of ``sketch``, its ends offset by ``extension``, beveled."""
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (sketch, edge)
        obj.MapPathParameter = 1
        Profile(
            obj,
            init_w=width,
            init_h=height,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam=family,
            size_name=f"{width:g}x{height:g}x2",
            bevels_combined=False,
            catalog_family=family,
            link_sub=(sketch, (edge,)),
            init_offset_a=extension,
            init_offset_b=extension,
        )
        for name, value in bevels.items():
            setattr(obj, name, value)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj

    def tube_along_x(self, **bevels):
        return self.tube(self.make_sketch(ALONG_X), **bevels)

    def hole_in_the_middle(self, body):
        """A Through All cutout of a 10x10 square in the middle of ``body``, far from both ends."""
        face_index = next(
            index
            for index, face in enumerate(body.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(App.Vector(0, 0, 1)) < 1e-6
        )
        box = body.Shape.BoundBox
        sketch = self.doc.addObject("Sketcher::SketchObject", "CutSketch")
        sketch.Placement.Base = App.Vector(0, 0, box.ZMax)
        middle = (box.XMin + box.XMax) / 2
        points = [App.Vector(middle + x, y, 0) for x, y in ((-5, -5), (5, -5), (5, 5), (-5, 5))]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(points[index], points[(index + 1) % 4]), False)
        cutout = self.doc.addObject("Part::FeaturePython", "ExtrudedCutout")
        ExtrudedCutout(cutout, sketch, (body, (f"Face{face_index}",)))
        self.doc.recompute()
        self.assertEqual(cutout.getStatusString(), "Valid")
        self.assertLess(cutout.Shape.Volume, body.Shape.Volume - 1.0)
        return cutout


class TestCutFace(CutEndsFixture):
    def test_a_bevel_about_the_height_axis_is_seen_on_the_width_faces(self):
        self.assertEqual(cut_ends(self.tube_along_x(BevelBCutY=45.0)), ("0.0", "45.0 <80", "|_/"))

    def test_a_bevel_about_the_width_axis_is_seen_on_the_height_faces(self):
        self.assertEqual(cut_ends(self.tube_along_x(BevelACutX=10.0)), ("10.0 <40", "0.0", "|_/"))

    def test_a_compound_bevel_gives_the_angle_seen_on_each_face(self):
        # Tilted 45 about Y then 10 about X: the width faces see atan(1 / cos 10) = 45.4.
        obj = self.tube_along_x(BevelBCutY=45.0, BevelBCutX=10.0)
        self.assertEqual(cut_ends(obj), ("0.0", "45.4 <80 + 10.0 <40", ""))

    def test_square_ends_have_no_face(self):
        self.assertEqual(cut_ends(self.tube_along_x()), ("0.0", "0.0", ""))

    def test_a_tube_with_rounded_corners_reads_like_a_sharp_one(self):
        # The fixture tube has sharp corners (radii 0); catalog tubes have rounded ones.
        obj = self.tube_along_x(MakeFillet=True, RadiusLarge=4.0, RadiusSmall=2.0, BevelACutY=45.0, BevelBCutY=45.0)
        self.assertGreater(len(obj.Shape.Faces), 6)
        self.assertEqual(cut_ends(obj), ("45.0 <80", "45.0 <80", "\\_/"))

    def test_a_round_profile_gives_one_angle_without_face(self):
        pipe = self.tube(self.make_sketch(ALONG_X), family="Pipe", width=40.0, height=40.0, BevelBCutY=30.0)
        self.assertEqual(cut_ends(pipe), ("0.0", "30.0", "|_/"))


class TestEndOrientation(CutEndsFixture):
    # BevelBCutY turns the other way than BevelACutY, and BevelACutX the other way than BevelBCutX
    # (profile.py: B2Y = -BevelBCutY, B1X = -BevelACutX): equal values on one face make a trapezoid.
    def test_ends_tilted_apart_on_one_face_are_a_trapezoid(self):
        obj = self.tube_along_x(BevelACutY=45.0, BevelBCutY=45.0)
        self.assertEqual(cut_ends(obj), ("45.0 <80", "45.0 <80", "\\_/"))

    def test_ends_tilted_the_same_way_on_one_face_are_a_parallelogram(self):
        obj = self.tube_along_x(BevelACutX=30.0, BevelBCutX=-30.0)
        self.assertEqual(cut_ends(obj), ("30.0 <40", "30.0 <40", "/_/"))

    def test_one_square_end_and_one_tilted_end(self):
        self.assertEqual(cut_ends(self.tube_along_x(BevelACutY=30.0))[2], "|_/")

    def test_ends_on_different_faces_have_no_symbol(self):
        obj = self.tube_along_x(BevelACutY=30.0, BevelBCutX=20.0)
        self.assertEqual(cut_ends(obj), ("30.0 <80", "20.0 <40", ""))


class TestFinishedSolid(CutEndsFixture):
    def test_an_end_miter_reads_like_the_beveled_profile(self):
        sketch = self.make_sketch(*CHAINED)
        p1, p2 = self.tube(sketch, "Edge1", extension=80.0), self.tube(sketch, "Edge2", extension=80.0)
        m1, m2 = self.make_miter(p1, p2), self.make_miter(p2, p1)
        self.doc.recompute()
        self.assertEqual(m1.getStatusString(), "Valid")
        # Both profiles lie with their 80 mm side in the sketch plane, where the corner turns.
        self.assertAlmostEqual(p1.Shape.BoundBox.YLength, 80.0, places=5)
        # Attached at the end of its edge, a profile starts (end 1, bevel A) where its edge ends: at the corner.
        beveled = self.tube(self.make_sketch(CHAINED[0]), BevelACutY=45.0)
        self.assertEqual(cut_ends(beveled), ("45.0 <80", "0.0", "|_/"))
        self.assertEqual(cut_ends(m1), cut_ends(beveled))
        self.assertEqual(cut_ends(m2), ("0.0", "45.0 <80", "|_/"))

    def test_an_extend_cut_on_a_slanted_face_reads_like_the_beveled_profile(self):
        body = self.tube_along_x()
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        obj = self.valid_extend_cut(body, target)
        beveled = self.tube_along_x(BevelACutY=30.0)
        self.assertEqual(cut_ends(beveled), ("30.0 <80", "0.0", "|_/"))
        self.assertEqual(cut_ends(obj), cut_ends(beveled))

    def test_a_cutout_away_from_the_ends_keeps_the_angles(self):
        beveled = self.tube_along_x(BevelACutY=45.0, BevelBCutY=45.0)
        cutout = self.hole_in_the_middle(beveled)
        self.assertEqual(cut_ends(cutout), ("45.0 <80", "45.0 <80", "\\_/"))

    def test_a_profile_in_a_placed_part_reads_like_the_same_profile_outside(self):
        inside = self.tube_along_x(BevelACutY=45.0, BevelBCutX=10.0)
        part = self.in_placed_part(inside, App.Vector(100, 50, 20))
        part.Placement.Rotation = App.Rotation(App.Vector(1, 1, 0), 30)
        self.doc.recompute()
        self.assertEqual(cut_ends(inside), ("45.0 <80", "10.0 <40", ""))
        # A trim of a profile in a placed Part, against a target outside it.
        body = self.tube_along_x()
        part = self.in_placed_part(body, App.Vector(100, 0, 0))
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        obj = self.valid_extend_cut(body, target)
        self.assertIs(obj.getParentGeoFeatureGroup(), part)
        self.assertEqual(cut_ends(obj), ("30.0 <80", "0.0", "|_/"))

    def test_a_notch_keeps_its_old_marks(self):
        trimmed = self.tube_along_x()
        diamond = self.make_profile(
            self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", rotation=45.0, extension=0.0, **CENTER
        )
        obj = self.notch(trimmed, diamond)
        self.assertIn("P", obj.CuttingAngleA + obj.CuttingAngleB)
        self.assertEqual(cut_ends(obj), (obj.CuttingAngleA, obj.CuttingAngleB, ""))


if __name__ == "__main__":
    unittest.main()

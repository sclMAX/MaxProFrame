"""Notch: the profile copies the target shape and keeps the piece that reaches its far end."""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, SIZE, MiterFixture

from freecad.maxproframe.create_notch_tool import make_notch_profile
from freecad.maxproframe.profile import Profile

# A T joint: the trimmed profile runs along X through the boundary profile, which runs along Y.
TRIMMED_EDGE = ((0, 0, 0), (300, 0, 0))
BOUNDARY_EDGE = ((0, -200, 0), (0, 200, 0))
HALF = 25.0


class TrimFixture(MiterFixture):
    def t_joint(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        boundary = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
        return trimmed, boundary

    def face_towards(self, obj, direction):
        """Name of the planar face of obj whose outward normal points along direction, farthest out."""
        candidates = [
            (face.CenterOfMass.dot(direction), f"Face{index}")
            for index, face in enumerate(obj.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(direction) < 1e-6
        ]
        return max(candidates)[1]

    def in_placed_part(self, body, offset):
        """Move ``body`` and its sketch into a Part placed at ``offset``."""
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        part.Placement.Base = offset
        self.doc.recompute()
        return part

    def global_box(self, obj):
        """Bounding box of ``obj`` in document coordinates, its container placement applied."""
        shape = obj.Shape.copy()
        group = obj.getParentGeoFeatureGroup()
        if group is not None:
            shape.transformShape(group.getGlobalPlacement().toMatrix())
        return shape.BoundBox

    def notch(self, body, target, gap=0.0):
        obj = make_notch_profile(body, target)
        obj.TrimGap = gap
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj


class TestNotchGeometry(TrimFixture):
    def test_notch_removes_everything_past_the_target_and_leaves_no_overlap(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)

        self.assertEqual(obj.TrimmedProfileType, "Notch")
        self.assertEqual(obj.TrimmingBoundary, [(boundary, ("",))])
        self.assertFalse(hasattr(obj, "CutType"))
        self.assertAlmostEqual(obj.Shape.common(boundary.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("0.0", "@ P"))

    def test_notch_copies_the_target_shape_when_it_is_rotated(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        diamond = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", rotation=45.0, **CENTER)
        obj = self.notch(trimmed, diamond)

        self.assertAlmostEqual(obj.Shape.common(diamond.Shape).Volume, 0.0, places=5)
        # The cut follows the diamond: the profile corners reach along its faces, short of the tip.
        tip = HALF * 2**0.5
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, tip - HALF, places=5)
        self.assertGreater(obj.Shape.distToShape(Part.Vertex(App.Vector(tip, 0, 0)))[0], 1.0)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_the_piece_reaching_the_far_end_is_kept_even_when_it_is_the_shorter_one(self):
        # The profile runs from 0 to 60; the target (outer faces at 15 and 65) holds most of it.
        # The center of gravity rule kept the 45 mm inside the target; the far end is at 0.
        body = self.make_profile(self.make_sketch(((0, 0, 0), (60, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((40, -200, 0), (40, 200, 0))), "Edge1", **CENTER)
        obj = self.notch(body, target)

        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, 15.0, places=5)
        self.assertAlmostEqual(obj.Shape.common(target.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Length.Value, 15.0, places=5)

    def test_the_far_end_is_kept_whatever_the_edge_direction(self):
        for name, edge in {"forward": TRIMMED_EDGE, "reversed": ((300, 0, 0), (0, 0, 0))}.items():
            with self.subTest(name):
                trimmed = self.make_profile(self.make_sketch(edge), "Edge1", **CENTER)
                boundary = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
                obj = self.notch(trimmed, boundary)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)

    def test_both_ends_are_two_chained_notches(self):
        trimmed, boundary = self.t_joint()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        first = self.notch(trimmed, boundary)
        obj = self.notch(first, far)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, 250 - HALF, places=5)
        self.assertAlmostEqual(obj.Length.Value, 250 - 2 * HALF, places=5)
        self.assertEqual((obj.CuttingAngleA, obj.CuttingAngleB), ("@ P", "@ P"))

    def test_trimmed_body_is_hidden_and_properties_follow_the_profile(self):
        trimmed, boundary = self.t_joint()
        trimmed.PID = "0042"
        obj = self.notch(trimmed, boundary)
        self.assertFalse(trimmed.ViewObject.Visibility)
        self.assertEqual(obj.PID, "0042")
        for name in ("Family", "CatalogFamily", "SizeName", "Material"):
            self.assertEqual(getattr(obj, name), getattr(trimmed, name), name)
        self.assertAlmostEqual(obj.Width.Value, 50.0)
        self.assertAlmostEqual(obj.Height.Value, 50.0)

    def test_the_joint_types_no_longer_list_end_trim(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)
        self.assertEqual(obj.getEnumerationsOfProperty("TrimmedProfileType"), ["Notch", "End Miter", "Extend Cut"])


GAP = 1.0
# Catalog beams with tapered flanges and fillets: (family, width, height, web, flange, radius 1, radius 2).
BEAMS = {
    "IPN 80": ("IPN", 42.0, 80.0, 3.9, 5.9, 3.9, 2.3),
    "UPN 80": ("UPN", 80.0, 45.0, 6.0, 8.0, 8.0, 4.0),
}
# Cross-section area of the 50x50x2 test tube.
SECTION_AREA = SIZE**2 - (SIZE - 4.0) ** 2


class TestNotchInPlacedParts(TrimFixture):
    def test_a_target_in_a_placed_part_is_cut_where_it_really_is(self):
        trimmed, boundary = self.t_joint()
        self.in_placed_part(boundary, App.Vector(100, 0, 0))
        obj = self.notch(trimmed, boundary)
        self.assertAlmostEqual(self.global_box(obj).XMin, 100.0 + HALF, places=5)
        self.assertAlmostEqual(self.global_box(obj).XMax, trimmed.Shape.BoundBox.XMax, places=5)

    def test_a_profile_in_a_placed_part_is_cut_where_the_target_really_is(self):
        trimmed, boundary = self.t_joint()
        self.in_placed_part(trimmed, App.Vector(-100, 0, 0))
        obj = self.notch(trimmed, boundary)
        # The Part moves the profile 100 mm back along X: the cut is at x = HALF in the document.
        self.assertAlmostEqual(self.global_box(obj).XMin, HALF, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, 100.0 + HALF, places=5)

    def test_a_gap_is_left_from_a_target_in_a_placed_part(self):
        trimmed, boundary = self.t_joint()
        self.in_placed_part(boundary, App.Vector(100, 0, 0))
        obj = self.notch(trimmed, boundary, gap=5.0)
        self.assertAlmostEqual(self.global_box(obj).XMin, 100.0 + HALF + 5.0, places=4)

    def test_keep_end_is_choosable_only_where_the_target_really_crosses(self):
        trimmed, boundary = self.t_joint()
        # In its own Part the target holds the start of the profile; the Part moves it to the middle.
        self.in_placed_part(boundary, App.Vector(150, 0, 0))
        obj = self.notch(trimmed, boundary)
        self.assertTrue(obj.Proxy.kept_end(obj)[1])
        obj.KeepEnd = "Start"
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(self.global_box(obj).XMin, trimmed.Shape.BoundBox.XMin, places=5)
        self.assertAlmostEqual(self.global_box(obj).XMax, 150.0 - HALF, places=5)


class TestNotchGap(TrimFixture):
    def clearance(self, target, point):
        return target.Shape.distToShape(Part.Vertex(point))[0]

    def assert_uniform_clearance(self, obj, target, gap):
        """The kept body stays ``gap`` from the target, and every edge of its mouth lies at exactly ``gap``."""
        self.assertAlmostEqual(obj.Shape.distToShape(target.Shape)[0], gap, places=4)
        self.assertAlmostEqual(obj.Shape.common(target.Shape).Volume, 0.0, places=5)
        # The mouth: the edges whose ends both lie near the target (the walls run on to the far end).
        mouth = [
            edge for edge in obj.Shape.Edges if all(self.clearance(target, v.Point) < 2 * gap for v in edge.Vertexes)
        ]
        self.assertTrue(mouth)
        for edge in mouth:
            for point in edge.discretize(7):
                self.assertAlmostEqual(self.clearance(target, point), gap, places=3, msg=point)

    def beam(self, edge, size):
        """A catalog beam with fillets along ``edge``, centred on it, from BEAMS."""
        family, width, height, web, flange, large, small = BEAMS[size]
        sketch = self.make_sketch(edge)
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (sketch, "Edge1")
        obj.MapPathParameter = 1
        Profile(
            obj,
            init_w=width,
            init_h=height,
            init_mt=web,
            init_ft=flange,
            init_r1=large,
            init_r2=small,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=True,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam=family,
            size_name=size,
            bevels_combined=False,
            catalog_family=family,
            link_sub=(sketch, ("Edge1",)),
            init_offset_a=SIZE,
            init_offset_b=SIZE,
        )
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(any(isinstance(face.Surface, Part.Cylinder) for face in obj.Shape.Faces))
        return obj

    def test_a_gap_leaves_that_clearance_from_a_beam_with_tapered_flanges_and_fillets(self):
        # A beam ends against the web of the same beam: the notch follows its flanges, tapers and fillets.
        for size in BEAMS:
            with self.subTest(size):
                target = self.beam(BOUNDARY_EDGE, size)
                without = self.notch(self.beam(TRIMMED_EDGE, size), target)
                self.assertAlmostEqual(without.Shape.common(target.Shape).Volume, 0.0, places=5)
                obj = self.notch(self.beam(TRIMMED_EDGE, size), target, GAP)
                self.assert_uniform_clearance(obj, target, GAP)
                self.assertLess(obj.Shape.Volume, without.Shape.Volume)
                self.assertEqual(len(obj.Shape.Solids), 1)

    def test_a_gap_wider_than_the_fillets_still_leaves_that_clearance(self):
        # 5 mm is more than the 3.9 mm fillet between the web and the flanges of an IPN 80.
        target = self.beam(BOUNDARY_EDGE, "IPN 80")
        obj = self.notch(self.beam(TRIMMED_EDGE, "IPN 80"), target, 5.0)
        self.assert_uniform_clearance(obj, target, 5.0)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_a_target_that_is_not_a_profile_is_grown_as_a_solid(self):
        # A plain copy of the beam shape: the near tangent faces need the coarser offset tolerance.
        beam = self.beam(BOUNDARY_EDGE, "IPN 80")
        target = self.doc.addObject("Part::Feature", "Beam")
        target.Shape = beam.Shape.copy()
        beam.ViewObject.Visibility = False
        obj = self.notch(self.beam(TRIMMED_EDGE, "IPN 80"), target, GAP)
        self.assert_uniform_clearance(obj, target, GAP)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_a_trimmed_target_is_grown_from_its_profile(self):
        trimmed, boundary = self.t_joint()
        # The target is cut back to 150 by a crossbar: the grown target stops there too.
        crossbar = self.make_profile(self.make_sketch(((-200, 150, 0), (200, 150, 0))), "Edge1", **CENTER)
        target = self.notch(boundary, crossbar)
        obj = self.notch(trimmed, target, GAP)
        self.assert_uniform_clearance(obj, target, GAP)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF + GAP, places=5)
        # 10 mm past the cut end of the target, inside its uncut profile: the grown target does not reach it.
        side = self.make_profile(self.make_sketch(((0, 160, 0), (300, 160, 0))), "Edge1", **CENTER)
        self.assertAlmostEqual(side.Shape.distToShape(target.Shape)[0], 10.0, places=5)
        self.assertAlmostEqual(self.notch(side, target, GAP).Shape.Volume, side.Shape.Volume, places=5)

    def test_the_gap_defaults_to_zero_and_is_stored_in_trim_gap(self):
        trimmed, boundary = self.t_joint()
        self.assertAlmostEqual(make_notch_profile(trimmed, boundary).TrimGap.Value, 0.0)
        self.assertAlmostEqual(make_notch_profile(trimmed, boundary, GAP).TrimGap.Value, GAP)
        self.assertEqual(
            make_notch_profile(trimmed, boundary).getDocumentationOfProperty("TrimGap"),
            "Extend / Cut: distance left between the profile end and the target plane."
            " Notch: clearance left all around the target profile.",
        )

    def test_a_gap_leaves_that_clearance_from_a_square_tube_target(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)
        volume = obj.Shape.Volume
        obj.TrimGap = GAP
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assert_uniform_clearance(obj, boundary, GAP)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF + GAP, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, trimmed.Shape.BoundBox.XMax, places=5)
        self.assertAlmostEqual(volume - obj.Shape.Volume, SECTION_AREA * GAP, places=3)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_setting_the_gap_back_to_zero_gives_the_notch_without_gap(self):
        trimmed, boundary = self.t_joint()
        obj = self.notch(trimmed, boundary)
        volume = obj.Shape.Volume
        obj.TrimGap = GAP
        self.doc.recompute()
        obj.TrimGap = 0.0
        self.doc.recompute()
        self.assertAlmostEqual(obj.Shape.Volume, volume, places=5)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)

    def test_the_gap_follows_the_faces_and_the_edge_of_a_rotated_tube(self):
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        diamond = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", rotation=45.0, **CENTER)
        without = self.notch(trimmed, diamond).Shape.Volume
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        obj = self.notch(trimmed, diamond, GAP)
        # Around the tip edge too: a sharp offset would leave more than the gap there.
        self.assert_uniform_clearance(obj, diamond, GAP)
        self.assertLess(obj.Shape.Volume, without)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_a_gap_leaves_that_clearance_from_a_rectangular_tube_target(self):
        trimmed, boundary = self.t_joint()
        boundary.ProfileWidth = 30.0
        boundary.ProfileHeight = 80.0
        self.doc.recompute()
        obj = self.notch(trimmed, boundary, GAP)
        self.assert_uniform_clearance(obj, boundary, GAP)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, boundary.Shape.BoundBox.XMax + GAP, places=5)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_a_gap_leaves_that_clearance_from_a_round_pipe_target(self):
        trimmed, boundary = self.t_joint()
        boundary.Family = "Pipe"
        self.doc.recompute()
        self.assertTrue(any(isinstance(face.Surface, Part.Cylinder) for face in boundary.Shape.Faces))
        without = self.notch(trimmed, boundary).Shape.Volume
        trimmed = self.make_profile(self.make_sketch(TRIMMED_EDGE), "Edge1", **CENTER)
        obj = self.notch(trimmed, boundary, GAP)
        self.assert_uniform_clearance(obj, boundary, GAP)
        # The tube corners (25 mm off the pipe axis) meet the pipe grown to a radius of 26 mm.
        self.assertAlmostEqual(obj.Shape.BoundBox.XMin, ((HALF + GAP) ** 2 - HALF**2) ** 0.5, places=3)
        self.assertLess(obj.Shape.Volume, without)
        self.assertEqual(len(obj.Shape.Solids), 1)

    def test_the_gap_keeps_the_chosen_piece_of_a_crossing_target(self):
        # The target (faces at -25 and 25) crosses the profile from -100 to 300.
        cases = {"Auto": (HALF + GAP, 300.0), "Start": (-100.0, -HALF - GAP), "End": (HALF + GAP, 300.0)}
        for keep_end, (x_min, x_max) in cases.items():
            with self.subTest(keep_end):
                body = self.make_profile(
                    self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER
                )
                target = self.make_profile(self.make_sketch(BOUNDARY_EDGE), "Edge1", **CENTER)
                obj = make_notch_profile(body, target)
                obj.TrimGap = GAP
                obj.KeepEnd = keep_end
                self.doc.recompute()
                self.assertEqual(obj.getStatusString(), "Valid")
                self.assertAlmostEqual(obj.Shape.BoundBox.XMin, x_min, places=5)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMax, x_max, places=5)
                self.assertAlmostEqual(obj.Shape.distToShape(target.Shape)[0], GAP, places=4)


if __name__ == "__main__":
    unittest.main()

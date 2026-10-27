import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import FreeCAD as App
import Part
import Sketcher

from freecad.maxproframe.create_custom_profiles_tool import CreateCustomProfileTaskPanel
from freecad.maxproframe.profile import Profile


class TestCustomProfileSections(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TestCustomProfileSections")
        name = self.doc.Name
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)

        # Baseline path along X (100 mm)
        self.path = self.doc.addObject("Sketcher::SketchObject", "Path")
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
        self.path.addConstraint(Sketcher.Constraint("Distance", 0, 100.0))
        self.doc.recompute()

    def _create_custom_profile(
        self,
        name,
        label,
        custom_source,
        length=100.0,
        material="Steel",
        weight=1.5,
        unitprice=10.0,
        path=None,
        edge="Edge1",
    ):
        panel = CreateCustomProfileTaskPanel.__new__(CreateCustomProfileTaskPanel)
        panel.form = SimpleNamespace(
            sb_length=Mock(value=Mock(return_value=float(length))),
            sb_weight=Mock(value=Mock(return_value=float(weight))),
            sb_unitprice=Mock(value=Mock(return_value=float(unitprice))),
            le_material=Mock(text=Mock(return_value=material)),
        )
        panel.custom_profile = custom_source
        target_path = path if path is not None else self.path
        panel.make_profile(target_path, edge, name)
        obj = self.doc.getObject(name)
        obj.Label = label
        return obj

    def _section_point(self, profile, x, y, z):
        # Source-space probes retain their material/hole meaning after the
        # authorized Center/Center bbox translation, before path attachment.
        box = profile.CustomProfile.Shape.BoundBox
        return profile.Placement.multVec(
            App.Vector(
                x - (box.XMin + box.XMax) / 2,
                y - (box.YMin + box.YMax) / 2,
                z,
            )
        )

    def _create_rect_sketch(self, name, x0, y0, x1, y1):
        sk = self.doc.addObject("Sketcher::SketchObject", name)
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for p1, p2 in zip(pts, pts[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        return sk

    # 1. Baseline controls
    def test_baseline_controls_single_contour_and_prebuilt_hollow_face(self):
        # Control 1: Single closed rectangular sketch
        sk_single = self._create_rect_sketch("SkSingle", 0, 0, 20, 20)
        self.doc.recompute()
        prof_single = self._create_custom_profile("ProfSingle", "Single Control", sk_single)
        self.doc.recompute()

        self.assertEqual(prof_single.getStatusString(), "Valid")
        self.assertEqual(len(prof_single.Shape.Solids), 1)
        self.assertTrue(prof_single.Shape.isValid())
        expected_vol_single = 20.0 * 20.0 * 100.0
        self.assertAlmostEqual(prof_single.Shape.Volume, expected_vol_single, places=2)
        pt_mat_single = self._section_point(prof_single, 10, 10, 50)
        self.assertTrue(prof_single.Shape.isInside(pt_mat_single, 0.01, False))

        # Control 2: Prebuilt Part.Face with hole
        outer_w = Part.makePolygon(
            [
                App.Vector(0, 0, 0),
                App.Vector(20, 0, 0),
                App.Vector(20, 20, 0),
                App.Vector(0, 20, 0),
                App.Vector(0, 0, 0),
            ]
        )
        inner_w = Part.makePolygon(
            [
                App.Vector(5, 5, 0),
                App.Vector(15, 5, 0),
                App.Vector(15, 15, 0),
                App.Vector(5, 15, 0),
                App.Vector(5, 5, 0),
            ]
        )
        face_geom = Part.makeFace([outer_w, inner_w], "Part::FaceMakerBullseye")
        face_feature = self.doc.addObject("Part::Feature", "PrebuiltFaceObj")
        face_feature.Shape = face_geom
        self.doc.recompute()

        prof_face = self._create_custom_profile("ProfFace", "Face Control", face_feature)
        self.doc.recompute()

        self.assertEqual(prof_face.getStatusString(), "Valid")
        self.assertEqual(len(prof_face.Shape.Solids), 1)
        self.assertTrue(prof_face.Shape.isValid())
        expected_vol_face = (400.0 - 100.0) * 100.0
        self.assertAlmostEqual(prof_face.Shape.Volume, expected_vol_face, places=2)
        pt_mat_face = self._section_point(prof_face, 2, 2, 50)
        pt_hole_face = self._section_point(prof_face, 10, 10, 50)
        self.assertTrue(prof_face.Shape.isInside(pt_mat_face, 0.01, False))
        self.assertFalse(prof_face.Shape.isInside(pt_hole_face, 0.01, False))

    # 2. Rectangular hollow sketch section
    def test_rectangular_hollow_sketch_section(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkRectHollow")
        outer = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        hole = [(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)]
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        prof = self._create_custom_profile("ProfRectHollow", "Rect Hollow", sk)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())
        expected_vol = (30.0 * 30.0 - 10.0 * 10.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_vol, places=2)
        # Material point is inside
        pt_mat = self._section_point(prof, 5, 5, 50)
        self.assertTrue(prof.Shape.isInside(pt_mat, 0.01, False))
        # Hole center point is empty
        pt_hole = self._section_point(prof, 15, 15, 50)
        self.assertFalse(prof.Shape.isInside(pt_hole, 0.01, False))
        # CustomProfile link preserved
        self.assertEqual(prof.CustomProfile, sk)

    # 3. Circular ring and curved contour sections
    def test_circular_ring_and_curved_contour_sections(self):
        with self.subTest(case="circular_ring"):
            sk_ring = self.doc.addObject("Sketcher::SketchObject", "SkRing")
            sk_ring.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 20.0), False)
            sk_ring.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10.0), False)
            self.doc.recompute()

            prof_ring = self._create_custom_profile("ProfRing", "Ring", sk_ring)
            self.doc.recompute()

            self.assertEqual(prof_ring.getStatusString(), "Valid")
            self.assertEqual(len(prof_ring.Shape.Solids), 1)
            self.assertTrue(prof_ring.Shape.isValid())
            expected_vol = math.pi * (20.0**2 - 10.0**2) * 100.0
            self.assertAlmostEqual(prof_ring.Shape.Volume, expected_vol, places=1)
            pt_hole_ring = prof_ring.Placement.multVec(App.Vector(0, 0, 50))
            pt_mat_ring = prof_ring.Placement.multVec(App.Vector(15, 0, 50))
            self.assertFalse(prof_ring.Shape.isInside(pt_hole_ring, 0.01, False))
            self.assertTrue(prof_ring.Shape.isInside(pt_mat_ring, 0.01, False))

        with self.subTest(case="curved_slot_hole"):
            sk_slot = self.doc.addObject("Sketcher::SketchObject", "SkSlot")
            # Outer circle R=25
            sk_slot.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 25.0), False)
            # Inner slot: 2 arcs R=5 at (-5,0) and (5,0), connected by lines
            sk_slot.addGeometry(
                Part.ArcOfCircle(
                    Part.Circle(App.Vector(-5, 0, 0), App.Vector(0, 0, 1), 5.0), math.pi / 2, 3 * math.pi / 2
                ),
                False,
            )
            sk_slot.addGeometry(Part.LineSegment(App.Vector(-5, -5, 0), App.Vector(5, -5, 0)), False)
            sk_slot.addGeometry(
                Part.ArcOfCircle(Part.Circle(App.Vector(5, 0, 0), App.Vector(0, 0, 1), 5.0), -math.pi / 2, math.pi / 2),
                False,
            )
            sk_slot.addGeometry(Part.LineSegment(App.Vector(5, 5, 0), App.Vector(-5, 5, 0)), False)
            self.doc.recompute()

            prof_slot = self._create_custom_profile("ProfSlot", "Slot", sk_slot)
            self.doc.recompute()

            self.assertEqual(prof_slot.getStatusString(), "Valid")
            self.assertEqual(len(prof_slot.Shape.Solids), 1)
            self.assertTrue(prof_slot.Shape.isValid())
            # Area = pi * 25^2 - (pi * 5^2 + 10 * 10) = 625*pi - (25*pi + 100) = 600*pi - 100
            expected_vol = (600.0 * math.pi - 100.0) * 100.0
            self.assertAlmostEqual(prof_slot.Shape.Volume, expected_vol, places=1)
            pt_hole_slot = prof_slot.Placement.multVec(App.Vector(0, 0, 50))
            pt_mat_slot = prof_slot.Placement.multVec(App.Vector(18, 0, 50))
            self.assertFalse(prof_slot.Shape.isInside(pt_hole_slot, 0.01, False))
            self.assertTrue(prof_slot.Shape.isInside(pt_mat_slot, 0.01, False))

    # 4. Multiple holes in single connected material face
    def test_multiple_holes_in_single_connected_material_face(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkMultiHole")
        # Outer 40x40
        outer = [(0, 0), (40, 0), (40, 40), (0, 40), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        # Hole 1: 10x10 at (5, 5)
        h1 = [(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]
        for p1, p2 in zip(h1, h1[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        # Hole 2: 10x10 at (25, 25)
        h2 = [(25, 25), (35, 25), (35, 35), (25, 35), (25, 25)]
        for p1, p2 in zip(h2, h2[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        prof = self._create_custom_profile("ProfMultiHole", "Multi Hole", sk)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())
        expected_vol = (40.0 * 40.0 - 100.0 - 100.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_vol, places=2)
        # Hole 1 empty
        pt_h1 = self._section_point(prof, 10, 10, 50)
        self.assertFalse(prof.Shape.isInside(pt_h1, 0.01, False))
        # Hole 2 empty
        pt_h2 = self._section_point(prof, 30, 30, 50)
        self.assertFalse(prof.Shape.isInside(pt_h2, 0.01, False))
        # Material between holes
        pt_mat_mid = self._section_point(prof, 20, 20, 50)
        self.assertTrue(prof.Shape.isInside(pt_mat_mid, 0.01, False))

    # 5. Construction geometry ignored
    def test_construction_geometry_ignored(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkWithConst")
        outer = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        hole = [(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        # Construction line diagonals
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 20, 0)), True)
        sk.addGeometry(Part.Circle(App.Vector(10, 10, 0), App.Vector(0, 0, 1), 7.0), True)
        self.doc.recompute()

        prof = self._create_custom_profile("ProfWithConst", "Const Ignored", sk)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())
        expected_vol = (400.0 - 100.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_vol, places=2)

    # 6. Underconstrained sketch accepted
    def test_underconstrained_sketch_accepted(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkUnderconstrained")
        # Add geometries without any constraints added to sk.Constraints
        outer = [(0, 0), (25, 0), (25, 25), (0, 25), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        hole = [(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        self.assertEqual(len(sk.Constraints), 0)
        prof = self._create_custom_profile("ProfUnderconstrained", "Underconstrained", sk)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())
        expected_vol = (625.0 - 100.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_vol, places=2)

    # 7. App::Link to multiwire section supported
    def test_app_link_to_multiwire_section_supported(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkForLink")
        outer = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        hole = [(5, 5), (20, 5), (20, 20), (5, 20), (5, 5)]
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        link = self.doc.addObject("App::Link", "CustomLink")
        link.LinkedObject = sk
        self.doc.recompute()

        prof = self._create_custom_profile("ProfLink", "Link Profile", link)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())
        expected_vol = (900.0 - 225.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_vol, places=2)
        self.assertEqual(prof.CustomProfile, link)

    # 8. Parametric recompute updates profile volume
    def test_parametric_recompute_updates_profile_volume(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkParametric")
        outer = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        # Initial hole 10x10 from (5,5) to (15,15)
        h1 = [(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]
        for p1, p2 in zip(h1, h1[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        prof = self._create_custom_profile("ProfParametric", "Parametric", sk)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        init_vol = (900.0 - 100.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, init_vol, places=2)
        pt_probe = self._section_point(prof, 20, 20, 50)
        # Initially pt_probe is in solid material
        self.assertTrue(prof.Shape.isInside(pt_probe, 0.01, False))

        # Edit sketch: replace hole with 20x20 hole from (5,5) to (25,25)
        sk.deleteAllGeometry()
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        h2 = [(5, 5), (25, 5), (25, 25), (5, 25), (5, 5)]
        for p1, p2 in zip(h2, h2[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        # Same profile object updated parametrically
        self.assertEqual(prof.getStatusString(), "Valid")
        new_vol = (900.0 - 400.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, new_vol, places=2)
        # Now pt_probe is inside the enlarged hole
        self.assertFalse(prof.Shape.isInside(pt_probe, 0.01, False))

    # 9. Valid to invalid to valid shape preservation
    def test_valid_to_invalid_to_valid_shape_preservation(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "SkPreserve")
        outer = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        hole = [(5, 5), (15, 5), (15, 15), (5, 15), (5, 5)]
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        prof = self._create_custom_profile("ProfPreserve", "Preserve", sk)
        self.doc.recompute()
        self.assertEqual(prof.getStatusString(), "Valid")

        initial_brep = prof.Shape.exportBrepToString()
        initial_placement = App.Placement(prof.Placement)
        initial_weight = prof.ApproxWeight
        initial_price = prof.Price
        initial_undo = self.doc.UndoCount

        # Mutate sketch to invalid (open contour)
        sk.deleteAllGeometry()
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)), False)
        sk.addGeometry(Part.LineSegment(App.Vector(20, 0, 0), App.Vector(20, 20, 0)), False)
        self.doc.recompute()

        self.assertIn("Invalid", prof.State)
        self.assertIn("open contours", prof.getStatusString())

        # Shape, placement, metadata, undo unaffected on rejected edit
        self.assertEqual(prof.Shape.exportBrepToString(), initial_brep)
        self.assertEqual(prof.Placement, initial_placement)
        self.assertEqual(prof.ApproxWeight, initial_weight)
        self.assertEqual(prof.Price, initial_price)
        self.assertEqual(self.doc.UndoCount, initial_undo)

        # Restore sketch to valid geometry
        sk.deleteAllGeometry()
        for p1, p2 in zip(outer, outer[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        for p1, p2 in zip(hole, hole[1:]):
            sk.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
        self.doc.recompute()

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertNotIn("Invalid", prof.State)
        self.assertTrue(prof.Shape.isValid())

    # 10. Reject disconnected material regions
    def test_reject_disconnected_material_regions(self):
        expected_err = (
            "Custom profile must contain exactly one connected material region, got multiple disconnected regions"
        )

        with self.subTest(case="two_disjoint_outer_loops"):
            sk_disjoint = self.doc.addObject("Sketcher::SketchObject", "SkDisjoint")
            b1 = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
            b2 = [(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)]
            for p1, p2 in zip(b1, b1[1:]):
                sk_disjoint.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            for p1, p2 in zip(b2, b2[1:]):
                sk_disjoint.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            self.doc.recompute()

            prof = self._create_custom_profile("ProfDisjoint", "Disjoint", sk_disjoint)
            with self.assertRaises(ValueError) as ctx:
                prof.Proxy.execute(prof)
            self.assertEqual(str(ctx.exception), expected_err)
            self.doc.recompute()
            self.assertIn("Invalid", prof.State)
            self.assertEqual(prof.getStatusString(), expected_err)

        with self.subTest(case="nested_material_island"):
            sk_island = self.doc.addObject("Sketcher::SketchObject", "SkIsland")
            outer = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
            hole = [(5, 5), (25, 5), (25, 25), (5, 25), (5, 5)]
            island = [(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)]
            for p1, p2 in zip(outer, outer[1:]):
                sk_island.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            for p1, p2 in zip(hole, hole[1:]):
                sk_island.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            for p1, p2 in zip(island, island[1:]):
                sk_island.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            self.doc.recompute()

            prof_isl = self._create_custom_profile("ProfIsland", "Island", sk_island)
            with self.assertRaises(ValueError) as ctx:
                prof_isl.Proxy.execute(prof_isl)
            self.assertEqual(str(ctx.exception), expected_err)
            self.doc.recompute()
            self.assertIn("Invalid", prof_isl.State)
            self.assertEqual(prof_isl.getStatusString(), expected_err)

    # 11. Reject open contours and empty sketches
    def test_reject_open_contours_and_empty_sketches(self):
        with self.subTest(case="open_contour"):
            sk_open = self.doc.addObject("Sketcher::SketchObject", "SkOpenContour")
            sk_open.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)), False)
            sk_open.addGeometry(Part.LineSegment(App.Vector(20, 0, 0), App.Vector(20, 20, 0)), False)
            self.doc.recompute()

            prof = self._create_custom_profile("ProfOpen", "Open", sk_open)
            expected_msg = "Custom profile contains open contours; all contours must be closed"
            with self.assertRaises(ValueError) as ctx:
                prof.Proxy.execute(prof)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof.State)
            self.assertEqual(prof.getStatusString(), expected_msg)

        with self.subTest(case="mixed_closed_loop_and_stray_open_segment"):
            sk_mixed = self.doc.addObject("Sketcher::SketchObject", "SkMixedStray")
            pts = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
            for p1, p2 in zip(pts, pts[1:]):
                sk_mixed.addGeometry(Part.LineSegment(App.Vector(p1[0], p1[1], 0), App.Vector(p2[0], p2[1], 0)), False)
            sk_mixed.addGeometry(Part.LineSegment(App.Vector(25, 0, 0), App.Vector(35, 10, 0)), False)
            self.doc.recompute()

            prof_mixed = self._create_custom_profile("ProfMixed", "Mixed", sk_mixed)
            expected_msg = "Custom profile contains open contours; all contours must be closed"
            with self.assertRaises(ValueError) as ctx:
                prof_mixed.Proxy.execute(prof_mixed)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_mixed.State)
            self.assertEqual(prof_mixed.getStatusString(), expected_msg)

        with self.subTest(case="non_coplanar_contours"):
            w1 = Part.makePolygon(
                [
                    App.Vector(0, 0, 0),
                    App.Vector(20, 0, 0),
                    App.Vector(20, 20, 0),
                    App.Vector(0, 20, 0),
                    App.Vector(0, 0, 0),
                ]
            )
            w2 = Part.makePolygon(
                [
                    App.Vector(5, 5, 10),
                    App.Vector(15, 5, 10),
                    App.Vector(15, 15, 10),
                    App.Vector(5, 15, 10),
                    App.Vector(5, 5, 10),
                ]
            )
            feat = self.doc.addObject("Part::Feature", "NonCoplanarSource")
            feat.Shape = Part.Compound([w1, w2])
            self.doc.recompute()

            prof_nc = self._create_custom_profile("ProfNonCoplanar", "NonCoplanar", feat)
            expected_msg = "Custom profile contours are not coplanar"
            with self.assertRaises(ValueError) as ctx:
                prof_nc.Proxy.execute(prof_nc)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_nc.State)
            self.assertEqual(prof_nc.getStatusString(), expected_msg)

        with self.subTest(case="empty_sketch"):
            sk_empty = self.doc.addObject("Sketcher::SketchObject", "SkEmptySection")
            self.doc.recompute()

            prof_emp = self._create_custom_profile("ProfEmpty", "Empty", sk_empty)
            expected_msg = "Custom profile source is empty or contains only construction geometry"
            with self.assertRaises(ValueError) as ctx:
                prof_emp.Proxy.execute(prof_emp)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_emp.State)
            self.assertEqual(prof_emp.getStatusString(), expected_msg)

        with self.subTest(case="construction_only_sketch"):
            sk_const = self.doc.addObject("Sketcher::SketchObject", "SkConstOnly")
            sk_const.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 20, 0)), True)
            self.doc.recompute()

            prof_c = self._create_custom_profile("ProfConstOnly", "ConstOnly", sk_const)
            expected_msg = "Custom profile source is empty or contains only construction geometry"
            with self.assertRaises(ValueError) as ctx:
                prof_c.Proxy.execute(prof_c)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_c.State)
            self.assertEqual(prof_c.getStatusString(), expected_msg)

    # 12. Reject self intersecting and crossing contours
    def test_reject_self_intersecting_and_crossing_contours(self):
        with self.subTest(case="self_intersecting_bowtie"):
            sk_bow = self.doc.addObject("Sketcher::SketchObject", "SkBowtie")
            bowtie = [(0, 0), (20, 20), (20, 0), (0, 20), (0, 0)]
            for p1, p2 in zip(bowtie, bowtie[1:]):
                sk_bow.addGeometry(Part.LineSegment(App.Vector(*p1, 0), App.Vector(*p2, 0)), False)
            self.doc.recompute()

            prof_bow = self._create_custom_profile("ProfBow", "Bow", sk_bow)
            expected_msg = "Custom profile contours must not self-intersect"
            with self.assertRaises(ValueError) as ctx:
                prof_bow.Proxy.execute(prof_bow)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_bow.State)
            self.assertEqual(prof_bow.getStatusString(), expected_msg)

        with self.subTest(case="crossing_contours"):
            sk_cross = self.doc.addObject("Sketcher::SketchObject", "SkCrossing")
            sk_cross.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 15.0), False)
            sk_cross.addGeometry(Part.Circle(App.Vector(10, 0, 0), App.Vector(0, 0, 1), 15.0), False)
            self.doc.recompute()

            prof_cross = self._create_custom_profile("ProfCross", "Cross", sk_cross)
            expected_msg = "Custom profile contours must not intersect or cross each other"
            with self.assertRaises(ValueError) as ctx:
                prof_cross.Proxy.execute(prof_cross)
            self.assertEqual(str(ctx.exception), expected_msg)
            self.doc.recompute()
            self.assertIn("Invalid", prof_cross.State)
            self.assertEqual(prof_cross.getStatusString(), expected_msg)

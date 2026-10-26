import math
import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile


class TestAluminiumAnchorAlignment(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("AluminiumAnchorAlignment")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1

    def assert_bounds_for_anchors(self, family, material, width, height):
        cases = (
            ("Center", "Center", 1, 1, -width / 2.0, width / 2.0, -height / 2.0, height / 2.0),
            ("Left", "Bottom", 0, 0, 0.0, width, 0.0, height),
            ("Right", "Top", 2, 2, -width, 0.0, -height, 0.0),
        )
        baseline_volume = None
        for idx, (anchor_x, anchor_y, ax, ay, xmin, xmax, ymin, ymax) in enumerate(cases):
            with self.subTest(family=family, width=width, height=height, anchor=(anchor_x, anchor_y)):
                axis = self.doc.addObject("Part::Feature", f"Axis_{idx}")
                axis.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 100))
                self.doc.recompute()
                axis_before = axis.Shape.exportBrepToString()
                axis_placement = list(axis.Placement.toMatrix().A)

                obj = self.doc.addObject("Part::FeaturePython", f"Profile_{idx}")
                obj.addExtension("Part::AttachExtensionPython")
                Profile(
                    obj,
                    init_w=width,
                    init_h=height,
                    init_mt=2.0,
                    init_ft=0.0,
                    init_r1=0.0,
                    init_r2=0.0,
                    init_len=100.0,
                    init_wg=1.0,
                    init_unit_price=1.0,
                    init_mf=False,
                    init_anchor_x=ax,
                    init_anchor_y=ay,
                    material=material,
                    fam=family,
                    size_name=f"{int(width)}x{int(height)}",
                    bevels_combined=False,
                    catalog_family=family,
                    link_sub=(axis, ("Edge1",)),
                )
                obj.PID = f"00{idx}"
                self.doc.clearUndos()
                self.doc.recompute()

                self.assertEqual(obj.getStatusString(), "Valid")
                self.assertEqual((obj.AnchorX, obj.AnchorY), (anchor_x, anchor_y))
                self.assertFalse(obj.Shape.isNull())
                self.assertTrue(obj.Shape.isValid())
                self.assertEqual(len(obj.Shape.Solids), 1)
                self.assertGreater(obj.Shape.Volume, 0.0)
                if baseline_volume is None:
                    baseline_volume = obj.Shape.Volume
                else:
                    self.assertAlmostEqual(obj.Shape.Volume, baseline_volume, places=5)
                box = obj.Shape.BoundBox
                self.assertAlmostEqual(box.XMin, xmin, places=5)
                self.assertAlmostEqual(box.XMax, xmax, places=5)
                self.assertAlmostEqual(box.YMin, ymin, places=5)
                self.assertAlmostEqual(box.YMax, ymax, places=5)
                self.assertAlmostEqual(box.ZMin, 0.0, places=5)
                self.assertAlmostEqual(box.ZMax, 100.0, places=5)
                self.assertEqual(axis.Shape.exportBrepToString(), axis_before)
                self.assertEqual(list(axis.Placement.toMatrix().A), axis_placement)
                self.assertEqual(obj.PID, f"00{idx}")
                self.assertEqual(obj.CatalogFamily, family)
                self.assertEqual(self.doc.UndoCount, 0)

    def assert_circular_anchors(self, family):
        diameter = 20.0
        for width in (0.0, 7.0, diameter):
            for length in (0.0, 100.0):
                for ax in range(3):
                    for ay in range(3):
                        for mirror_h, mirror_v in ((False, False), (True, False),
                                                   (False, True), (True, True)):
                            with self.subTest(family=family, width=width, length=length,
                                              anchor=(ax, ay), mirrors=(mirror_h, mirror_v)):
                                obj = self.doc.addObject("Part::FeaturePython", "Circular")
                                obj.addExtension("Part::AttachExtensionPython")
                                Profile(
                                    obj, width, diameter, 2.0, 0.0, 0.0, 0.0,
                                    length, 1.0, 1.0, False, ax, ay, "Metal", family,
                                    "20", False, init_mirror_h=mirror_h,
                                    init_mirror_v=mirror_v,
                                )
                                self.doc.recompute()
                                self.assertEqual(obj.getStatusString(), "Valid")
                                self.assertTrue(obj.Shape.isValid())
                                # Analytic bounds: cached display tessellation undershoots circles.
                                box = obj.Shape.optimalBoundingBox(False)
                                self.assertAlmostEqual(box.XMin, -diameter * ax / 2, places=5)
                                self.assertAlmostEqual(box.XMax, diameter * (1 - ax / 2), places=5)
                                self.assertAlmostEqual(box.YMin, -diameter * ay / 2, places=5)
                                self.assertAlmostEqual(box.YMax, diameter * (1 - ay / 2), places=5)
                                self.assertAlmostEqual(box.ZLength, length, places=5)
                                area = math.pi * (100 - (64 if family == "Pipe" and length else 0))
                                # Preserve the existing zero-length face API (outer wire only).
                                if length:
                                    self.assertEqual(len(obj.Shape.Solids), 1)
                                    self.assertAlmostEqual(obj.Shape.Volume, area * length, places=5)
                                else:
                                    self.assertEqual(len(obj.Shape.Faces), 1)
                                    self.assertAlmostEqual(obj.Shape.Area, area, places=5)
                                self.assertEqual(obj.ProfileWidth, width)
                                self.assertEqual(obj.ProfileHeight, diameter)

    def test_round_bar_horizontal_anchors_use_diameter(self):
        self.assert_circular_anchors("Round Bar")

    def test_pipe_horizontal_anchors_use_diameter(self):
        self.assert_circular_anchors("Pipe")

    def test_circular_rotation_preserves_local_anchors_and_support(self):
        axis = self.doc.addObject("Part::Feature", "Support")
        axis.Shape = Part.makeLine(App.Vector(5, 7, 9), App.Vector(105, 7, 9))
        before = [v.Point for v in axis.Shape.Vertexes]
        placement_before = App.Placement(axis.Placement)
        length_before = axis.Shape.Length
        for family in ("Round Bar", "Pipe"):
            for ax in range(3):
                for ay in range(3):
                    for mh, mv in ((False, False), (True, False), (False, True), (True, True)):
                        obj = self.doc.addObject("Part::FeaturePython", "RotatedCircular")
                        obj.addExtension("Part::AttachExtensionPython")
                        obj.AttachmentSupport = (axis, ["Edge1"])
                        obj.MapMode = "NormalToEdge"
                        Profile(obj, 0, 20, 2, 0, 0, 0, 100, 1, 1, False,
                                ax, ay, "Metal", family, "20", False,
                                link_sub=(axis, ("Edge1",)), init_mirror_h=mh, init_mirror_v=mv)
                        for angle in (0, 37, 90, 180, 270):
                            with self.subTest(family=family, anchor=(ax, ay), mirrors=(mh, mv), angle=angle):
                                obj.RotationAngle = angle
                                self.doc.recompute()
                                self.assertEqual(obj.getStatusString(), "Valid")
                                self.assertAlmostEqual(math.degrees(obj.AttachmentOffset.Rotation.Angle), angle)
                                local = obj.Shape.copy()
                                local.Placement = obj.Placement.inverse().multiply(local.Placement)
                                box = local.optimalBoundingBox(False)
                                self.assertAlmostEqual(box.XMin, -10 * ax, places=5)
                                self.assertAlmostEqual(box.YMin, -10 * ay, places=5)
                                self.assertAlmostEqual(box.XLength, 20, places=5)
                                self.assertAlmostEqual(box.YLength, 20, places=5)
                                center = obj.Placement.multVec(App.Vector(10 - 10 * ax, 10 - 10 * ay, 50))
                                self.assertAlmostEqual(obj.Shape.Solids[0].CenterOfMass.distanceToPoint(center), 0, places=5)
        self.assertEqual([v.Point for v in axis.Shape.Vertexes], before)
        self.assertEqual(axis.Placement, placement_before)
        self.assertAlmostEqual(axis.Shape.Length, length_before)

    def test_square_hollow_control_respects_path_alignment(self):
        self.assert_bounds_for_anchors("Square Hollow", "Metal", 20.0, 20.0)

    def test_aluminium_extrusions_respect_path_alignment(self):
        for family, width, height in (
            ("V-Slot", 20.0, 20.0),
            ("V-Slot", 40.0, 20.0),
            ("T-Slot", 20.0, 20.0),
            ("T-Slot 1-Slot", 20.0, 20.0),
        ):
            self.assert_bounds_for_anchors(family, "Aluminium", width, height)


if __name__ == "__main__":
    unittest.main()

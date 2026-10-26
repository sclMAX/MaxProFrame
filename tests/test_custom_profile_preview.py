"""Regression coverage for custom profile previews without a selected path."""

import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile


class TestCustomProfilePreview(unittest.TestCase):
    def test_zero_length_preview_preserves_section_holes_mirrors_and_source(self):
        self._check_section(length=0.0)

    def test_nonzero_length_custom_profile_still_extrudes_the_section(self):
        self._check_section(length=100.0)

    def test_offset_section_respects_all_nine_anchors(self):
        for ax in range(3):
            for ay in range(3):
                for length in (0.0, 100.0):
                    with self.subTest(anchor=(ax, ay), length=length):
                        self._check_section(length, ax, ay, 37.0, -23.0)

    def test_rotation_and_non_origin_path_attachment_preserve_aligned_section(self):
        doc = App.newDocument("CustomAnchorAttachment")
        self.addCleanup(App.closeDocument, doc.Name)
        source = doc.addObject("Part::Feature", "Source")
        source.Shape = Part.makePlane(20, 10, App.Vector(37, -23, 0))
        original = source.Shape.copy()
        source_placement = App.Placement(source.Placement)
        axis = doc.addObject("Part::Feature", "Axis")
        axis.Shape = Part.makeLine(App.Vector(5, 7, 9), App.Vector(105, 7, 9))
        axis_before = axis.Shape.copy()
        axis_placement = App.Placement(axis.Placement)
        obj = doc.addObject("Part::FeaturePython", "Attached")
        obj.addExtension("Part::AttachExtensionPython")
        obj.AttachmentSupport = (axis, ["Edge1"])
        obj.MapMode = "NormalToEdge"
        Profile(
            obj, 20, 10, 0, 0, 0, 0, 100, 1, 0, False, 2, 1,
            "Test", "Custom Profile", "Source", False,
            link_sub=(axis, ("Edge1",)), custom_profile=source,
            init_rotation=37, init_mirror_h=True, init_mirror_v=True,
        )
        doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.RotationAngle, 37)
        self.assertAlmostEqual(obj.AttachmentOffset.Rotation.Angle * 180 / 3.141592653589793, 37)
        self.assertAlmostEqual(obj.Placement.Base.distanceToPoint(App.Vector(5, 7, 9)), 0)
        direction = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(abs(direction.x), 1)
        local = obj.Shape.copy()
        local.Placement = obj.Placement.inverse().multiply(local.Placement)
        self.assertAlmostEqual(local.BoundBox.XMin, -20)
        self.assertAlmostEqual(local.BoundBox.YMin, -5)
        self.assertAlmostEqual(local.Volume, 20000)
        self.assertEqual(source.Placement, source_placement)
        self.assertAlmostEqual(source.Shape.Area, original.Area)
        self.assertAlmostEqual(source.Shape.common(original).Area, original.Area)
        self.assertEqual(axis.Placement, axis_placement)
        self.assertAlmostEqual(axis.Shape.Length, axis_before.Length)
        self.assertEqual(
            [vertex.Point for vertex in axis.Shape.Vertexes],
            [vertex.Point for vertex in axis_before.Vertexes],
        )

    def _check_section(self, length, ax=0, ay=0, dx=0.0, dy=0.0):
        doc = App.newDocument("CustomProfilePreviewRegression")
        self.addCleanup(lambda: App.closeDocument(doc.Name) if doc.Name in App.listDocuments() else None)

        def rectangle(x0, y0, x1, y1):
            return Part.makePolygon(
                [App.Vector(x + dx, y + dy, 0) for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]
            )

        source = doc.addObject("Part::Feature", "CP1")
        source.Shape = Part.makeFace([rectangle(0, 0, 20, 10), rectangle(2, 2, 6, 5)], "Part::FaceMakerBullseye")
        original = source.Shape.copy()
        for mirror_h, mirror_v in [(False, False), (True, False), (False, True), (True, True)]:
            with self.subTest(length=length, mirror_h=mirror_h, mirror_v=mirror_v):
                obj = doc.addObject("Part::FeaturePython", "CustomPreview")
                obj.addExtension("Part::AttachExtensionPython")
                proxy = Profile(
                    obj,
                    init_w=20.0,
                    init_h=10.0,
                    init_mt=0.0,
                    init_ft=0.0,
                    init_r1=0.0,
                    init_r2=0.0,
                    init_len=length,
                    init_wg=1.0,
                    init_unit_price=0.0,
                    init_mf=False,
                    init_anchor_x=ax,
                    init_anchor_y=ay,
                    material="Test Library",
                    fam="Custom Profile",
                    size_name="CP1",
                    bevels_combined=False,
                    custom_profile=source,
                    init_mirror_h=mirror_h,
                    init_mirror_v=mirror_v,
                )
                proxy.execute(obj)
                self.assertTrue(obj.Shape.isValid())
                self.assertFalse(obj.Shape.isNull())
                self.assertEqual(len(obj.Shape.Solids), int(length > 0))
                self.assertEqual(obj.CustomProfile, source)
                self.assertAlmostEqual(obj.Shape.BoundBox.XLength, 20.0)
                self.assertAlmostEqual(obj.Shape.BoundBox.YLength, 10.0)
                self.assertAlmostEqual(obj.Shape.BoundBox.ZLength, length)
                self.assertAlmostEqual(obj.Shape.BoundBox.XMin, -10.0 * ax)
                self.assertAlmostEqual(obj.Shape.BoundBox.YMin, -5.0 * ay)
                x = (16 if mirror_h else 4) - 10.0 * ax
                y = (6.5 if mirror_v else 3.5) - 5.0 * ay
                if length:
                    self.assertAlmostEqual(obj.Shape.Volume, 188.0 * length)
                    self.assertFalse(obj.Shape.isInside(App.Vector(x, y, 50), 1e-7, False))
                    self.assertTrue(obj.Shape.isInside(App.Vector(10 - 10.0 * ax, 5 - 5.0 * ay, 50), 1e-7, False))
                else:
                    self.assertEqual(len(obj.Shape.Faces), 1)
                    self.assertEqual(len(obj.Shape.Wires), 2)
                    self.assertAlmostEqual(obj.Shape.Area, 188.0)
                    hole_point = Part.Vertex(App.Vector(x, y, 0))
                    self.assertGreater(obj.Shape.distToShape(hole_point)[0], 0.9)
                self.assertAlmostEqual(source.Shape.Area, original.Area)
                self.assertAlmostEqual(source.Shape.common(original).Area, original.Area)
                self.assertEqual(len(source.Shape.Wires), 2)
                self.assertAlmostEqual(source.Shape.BoundBox.XMin, dx)
                self.assertAlmostEqual(source.Shape.BoundBox.YMin, dy)


if __name__ == "__main__":
    unittest.main()

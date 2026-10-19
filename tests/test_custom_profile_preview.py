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

    def _check_section(self, length):
        doc = App.newDocument("CustomProfilePreviewRegression")
        self.addCleanup(lambda: App.closeDocument(doc.Name) if doc.Name in App.listDocuments() else None)

        def rectangle(x0, y0, x1, y1):
            return Part.makePolygon(
                [App.Vector(x, y, 0) for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]
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
                    init_anchor_x=0,
                    init_anchor_y=0,
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
                x, y = (16 if mirror_h else 4), (6.5 if mirror_v else 3.5)
                if length:
                    self.assertAlmostEqual(obj.Shape.Volume, 188.0 * length)
                    self.assertFalse(obj.Shape.isInside(App.Vector(x, y, 50), 1e-7, False))
                    self.assertTrue(obj.Shape.isInside(App.Vector(10, 5, 50), 1e-7, False))
                else:
                    self.assertEqual(len(obj.Shape.Faces), 1)
                    self.assertEqual(len(obj.Shape.Wires), 2)
                    self.assertAlmostEqual(obj.Shape.Area, 188.0)
                    hole_point = Part.Vertex(App.Vector(x, y, 0))
                    self.assertGreater(obj.Shape.distToShape(hole_point)[0], 0.9)
                self.assertAlmostEqual(source.Shape.Area, original.Area)
                self.assertAlmostEqual(source.Shape.common(original).Area, original.Area)
                self.assertEqual(len(source.Shape.Wires), 2)
                self.assertAlmostEqual(source.Shape.BoundBox.XMin, 0.0)
                self.assertAlmostEqual(source.Shape.BoundBox.YMin, 0.0)


if __name__ == "__main__":
    unittest.main()

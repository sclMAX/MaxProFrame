import unittest

import FreeCAD as App
import Part

from freecad.frameforge.profile import Profile


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

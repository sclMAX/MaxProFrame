import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile


class TestProfileEdgeOffset(unittest.TestCase):
    """OffsetX/OffsetY displace the section from its path edge in the edge frame."""

    def setUp(self):
        self.doc = App.newDocument("ProfileEdgeOffset")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Path")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)))
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(70, 70, 0)))
        self.doc.recompute()
        self.count = 0

    def make_profile(self, edge="Edge1", rotation=0.0, mirror_h=False, mirror_v=False, offset_x=None, offset_y=None):
        self.count += 1
        obj = self.doc.addObject("Part::FeaturePython", f"Profile{self.count}")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (self.sketch, edge)
        obj.MapPathParameter = 1
        kwargs = {}
        if offset_x is not None:
            kwargs["init_offset_x"] = offset_x
        if offset_y is not None:
            kwargs["init_offset_y"] = offset_y
        Profile(
            obj,
            init_w=30.0,
            init_h=10.0,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=False,
            init_anchor_x=0,
            init_anchor_y=0,
            material="Metal",
            fam="Square Hollow",
            size_name="30x10",
            bevels_combined=False,
            catalog_family="Square Hollow",
            link_sub=(self.sketch, (edge,)),
            init_mirror_h=mirror_h,
            init_mirror_v=mirror_v,
            init_rotation=rotation,
            **kwargs,
        )
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj

    def edge_frame(self, obj):
        """World direction of the edge frame X and Y axes (attachment without AttachmentOffset)."""
        frame = obj.Placement.multiply(obj.AttachmentOffset.inverse()).Rotation
        return frame.multVec(App.Vector(1, 0, 0)), frame.multVec(App.Vector(0, 1, 0))

    def assert_vector(self, actual, expected):
        self.assertAlmostEqual((actual - expected).Length, 0.0, places=6, msg=f"{actual} != {expected}")

    def test_default_offsets_are_zero_and_keep_geometry(self):
        plain = self.make_profile()
        explicit = self.make_profile(offset_x=0.0, offset_y=0.0)
        self.assertEqual(plain.OffsetX.Value, 0.0)
        self.assertEqual(plain.OffsetY.Value, 0.0)
        self.assertEqual(plain.getTypeIdOfProperty("OffsetX"), "App::PropertyDistance")
        self.assertEqual(plain.getTypeIdOfProperty("OffsetY"), "App::PropertyDistance")
        self.assert_vector(plain.Shape.BoundBox.Center, explicit.Shape.BoundBox.Center)
        self.assert_vector(plain.AttachmentOffset.Base, App.Vector(0, 0, 0))

    def test_offset_moves_section_along_edge_frame(self):
        for edge in ("Edge1", "Edge2"):
            with self.subTest(edge=edge):
                base = self.make_profile(edge=edge)
                moved = self.make_profile(edge=edge, offset_x=12.0, offset_y=-5.0)
                x_axis, y_axis = self.edge_frame(moved)
                expected = base.Shape.BoundBox.Center + x_axis * 12.0 + y_axis * -5.0
                self.assert_vector(moved.Shape.BoundBox.Center, expected)
                self.assertAlmostEqual(moved.Shape.Volume, base.Shape.Volume, places=6)
                # The edge frame X lies in the sketch plane and Y follows the sketch normal.
                self.assertAlmostEqual(x_axis.z, 0.0, places=9)
                self.assert_vector(y_axis, App.Vector(0, 0, 1))

    def test_offset_direction_ignores_rotation_and_mirrors(self):
        for rotation, mirror_h, mirror_v in ((90.0, False, False), (180.0, True, False), (270.0, False, True)):
            with self.subTest(rotation=rotation, mirror_h=mirror_h, mirror_v=mirror_v):
                base = self.make_profile(rotation=rotation, mirror_h=mirror_h, mirror_v=mirror_v)
                moved = self.make_profile(
                    rotation=rotation, mirror_h=mirror_h, mirror_v=mirror_v, offset_x=8.0, offset_y=3.0
                )
                x_axis, y_axis = self.edge_frame(moved)
                delta = moved.Shape.BoundBox.Center - base.Shape.BoundBox.Center
                self.assert_vector(delta, x_axis * 8.0 + y_axis * 3.0)
                self.assertAlmostEqual(moved.AttachmentOffset.Rotation.Angle, base.AttachmentOffset.Rotation.Angle)

    def test_changing_offset_property_recomputes_placement(self):
        obj = self.make_profile()
        before = obj.Shape.BoundBox.Center
        obj.OffsetX = 4.0
        obj.OffsetY = 6.0
        self.doc.recompute()
        x_axis, y_axis = self.edge_frame(obj)
        self.assert_vector(obj.Shape.BoundBox.Center, before + x_axis * 4.0 + y_axis * 6.0)
        obj.OffsetX = 0.0
        obj.OffsetY = 0.0
        self.doc.recompute()
        self.assert_vector(obj.Shape.BoundBox.Center, before)

    def test_set_properties_updates_offsets(self):
        obj = self.make_profile(offset_x=2.0, offset_y=2.0)
        before = self.make_profile().Shape.BoundBox.Center
        obj.Proxy.set_properties(
            obj,
            30.0,
            10.0,
            2.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            1.0,
            False,
            0,
            0,
            "Metal",
            "Square Hollow",
            "30x10",
            init_offset_x=-7.0,
            init_offset_y=1.5,
        )
        self.doc.recompute()
        self.assertEqual(obj.OffsetX.Value, -7.0)
        self.assertEqual(obj.OffsetY.Value, 1.5)
        x_axis, y_axis = self.edge_frame(obj)
        self.assert_vector(obj.Shape.BoundBox.Center, before + x_axis * -7.0 + y_axis * 1.5)


if __name__ == "__main__":
    unittest.main()

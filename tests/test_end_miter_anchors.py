import math
import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile


class TestEndMiterAnchors(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("EndMiterAnchors")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1

    def assert_same_solid(self, actual, expected):
        self.assertAlmostEqual(expected.cut(actual).Volume, 0.0, places=5)
        self.assertAlmostEqual(actual.cut(expected).Volume, 0.0, places=5)

    @staticmethod
    def contact_area(left, right):
        # A solid boolean common can discard coincident boundary faces.
        normal = App.Vector(1, -1, 0)
        normal.normalize()

        def joint_faces(shape):
            return [
                face for face in shape.Faces
                if abs(abs(face.normalAt(0, 0).dot(normal)) - 1.0) < 1e-8
            ]

        return sum(a.common(b).Area for a in joint_faces(left) for b in joint_faces(right))

    @staticmethod
    def half_space(offset, side):
        # Derive the joint from aligned outer section corners, independently
        # of the production intersection/bounding-box calculation: x-y=offset.
        if side == 0:
            points = [(offset - 1000, -1000), (2000, -1000), (2000, 1000), (offset + 1000, 1000)]
        else:
            points = [(-2000, -1000), (offset - 1000, -1000), (offset + 1000, 1000), (-2000, 1000)]
        vertices = [App.Vector(x, y, -1000) for x, y in points]
        return Part.Face(Part.makePolygon(vertices + [vertices[0]])).extrude(App.Vector(0, 0, 2000))

    def assert_joint(self, mixed):
        axes = []
        for direction in (App.Vector(200, 0, 0), App.Vector(0, 200, 0)):
            axis = self.doc.addObject("Part::Feature", "Axis")
            axis.Shape = Part.makeLine(App.Vector(0, 0, 0), direction)
            axes.append(axis)
        self.doc.recompute()
        axis_before = [
            (list(axis.Placement.toMatrix().A), [list(v.Point) for v in axis.Shape.Vertexes])
            for axis in axes
        ]
        rotations = [
            App.Rotation(App.Vector(0, 1, 0), App.Vector(0, 0, 1), App.Vector(1, 0, 0), "ZXY"),
            App.Rotation(App.Vector(1, 0, 0), App.Vector(0, 0, -1), App.Vector(0, 1, 0), "ZXY"),
        ]
        sources = []
        for i, axis in enumerate(axes):
            obj = self.doc.addObject("Part::FeaturePython", "Source")
            obj.addExtension("Part::AttachExtensionPython")
            Profile(
                obj, init_w=50.0, init_h=50.0, init_mt=2.0, init_ft=0.0,
                init_r1=0.0, init_r2=0.0, init_len=200.0, init_wg=8.0,
                init_unit_price=3.0, init_mf=False,
                init_anchor_x=0 if mixed and i == 1 else 1, init_anchor_y=1,
                material="Metal", fam="Square Hollow", size_name="MiterProbe",
                bevels_combined=False, catalog_family="Square Hollow (No Fillet)",
                init_offset_a=50.0, link_sub=(axis, ("Edge1",)),
            )
            obj.PID = "004" + str(i)
            obj.Placement = App.Placement(App.Vector(0, 0, 0), rotations[i])
            sources.append(obj)
        self.doc.recompute()
        fields = (
            "PID", "CatalogFamily", "Family", "SizeName", "Material", "ApproxWeight", "Price",
            "LinearWeight", "UnitPrice", "AnchorX", "AnchorY", "ProfileWidth", "ProfileHeight",
            "ProfileLength", "OffsetA", "OffsetB",
        )
        before = [
            (obj.Shape.copy(), list(obj.Placement.toMatrix().A), {key: getattr(obj, key) for key in fields})
            for obj in sources
        ]
        xmin = 0.0 if mixed else -25.0
        # Independent 50x50x2 tubes, including 50 mm start extensions.
        tubes = [
            Part.makeBox(250, 50, 50, App.Vector(-50, -25, -25)).cut(
                Part.makeBox(252, 46, 46, App.Vector(-51, -23, -23))
            ),
            Part.makeBox(50, 250, 50, App.Vector(xmin, -50, -25)).cut(
                Part.makeBox(46, 252, 46, App.Vector(xmin + 2, -51, -23))
            ),
        ]
        offset = 25.0 if mixed else 0.0
        expected = [tube.common(self.half_space(offset, i)) for i, tube in enumerate(tubes)]
        expected_area = 384.0 * math.sqrt(2.0)
        self.assertAlmostEqual(self.contact_area(*expected), expected_area, places=5)
        for obj, tube in zip(sources, tubes):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assert_same_solid(obj.Shape, tube)

        trimmed = []
        for i in range(2):
            obj = self.doc.addObject("Part::FeaturePython", "Miter")
            TrimmedProfile(obj)
            obj.TrimmedBody = sources[i]
            obj.TrimmingBoundary = [(sources[1 - i], ("Edge1",))]
            obj.TrimmedProfileType = "End Miter"
            trimmed.append(obj)
        self.doc.clearUndos()
        self.doc.recompute()

        for i, obj in enumerate(trimmed):
            with self.subTest(profile=i):
                self.assertEqual(obj.getStatusString(), "Valid")
                self.assertFalse(obj.Shape.isNull())
                self.assertTrue(obj.Shape.isValid())
                self.assert_same_solid(obj.Shape, expected[i])
                self.assertEqual(sources[i].getStatusString(), "Valid")
                self.assert_same_solid(sources[i].Shape, before[i][0])
                self.assertEqual(list(sources[i].Placement.toMatrix().A), before[i][1])
                for key, value in before[i][2].items():
                    self.assertEqual(getattr(sources[i], key), value, key)
                for key in ("PID", "CatalogFamily", "Family", "SizeName", "Material", "ApproxWeight", "Price"):
                    self.assertEqual(getattr(obj, key), getattr(sources[i], key), key)
                self.assertAlmostEqual(obj.Width.Value, 50.0)
                self.assertAlmostEqual(obj.Height.Value, 50.0)
        self.assertAlmostEqual(trimmed[0].Shape.common(trimmed[1].Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(self.contact_area(trimmed[0].Shape, trimmed[1].Shape), expected_area, places=5)
        self.assertAlmostEqual(trimmed[0].Shape.distToShape(trimmed[1].Shape)[0], 0.0, places=5)
        self.assert_same_solid(
            trimmed[0].Shape.fuse(trimmed[1].Shape), expected[0].fuse(expected[1])
        )
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertEqual(axis_before, [
            (list(axis.Placement.toMatrix().A), [list(v.Point) for v in axis.Shape.Vertexes])
            for axis in axes
        ])

    def test_same_anchor_keeps_endpoint_miter_geometry(self):
        self.assert_joint(mixed=False)

    def test_mixed_anchors_align_both_miter_sections(self):
        self.assert_joint(mixed=True)


if __name__ == "__main__":
    unittest.main()

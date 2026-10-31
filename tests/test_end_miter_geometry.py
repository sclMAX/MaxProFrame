"""End Miter cuts follow the real position of each attached profile."""

import math
import threading
import unittest
from types import SimpleNamespace

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile

SIZE = 50.0
CENTER = dict(anchor_x=1, anchor_y=1)
LEFT = dict(anchor_x=0, anchor_y=1)
CHAINED = (((200, 0, 0), (0, 0, 0)), ((0, 0, 0), (0, 200, 0)))
START_START = (((0, 0, 0), (200, 0, 0)), ((0, 0, 0), (0, 200, 0)))


def polar(length, degrees):
    return (length * math.cos(math.radians(degrees)), length * math.sin(math.radians(degrees)), 0)


class MiterFixture(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("EndMiterGeometry")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def make_sketch(self, *edges):
        sketch = self.doc.addObject("Sketcher::SketchObject", "Path")
        for a, b in edges:
            sketch.addGeometry(Part.LineSegment(App.Vector(*a), App.Vector(*b)))
        self.doc.recompute()
        return sketch

    def make_profile(self, sketch, edge, anchor_x=1, anchor_y=1, rotation=0.0, offset_x=0.0, extension=SIZE):
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (sketch, edge)
        obj.MapPathParameter = 1
        Profile(
            obj,
            init_w=SIZE,
            init_h=SIZE,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=False,
            init_anchor_x=anchor_x,
            init_anchor_y=anchor_y,
            material="Metal",
            fam="Square Hollow",
            size_name="50x50x2",
            bevels_combined=False,
            catalog_family="Square Hollow",
            link_sub=(sketch, (edge,)),
            init_rotation=rotation,
            init_offset_a=extension,
            init_offset_b=extension,
            init_offset_x=offset_x,
        )
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj

    def make_miter(self, body, boundary, **props):
        obj = self.doc.addObject("Part::FeaturePython", "Miter")
        TrimmedProfile(obj)
        obj.TrimmedBody = body
        obj.TrimmingBoundary = [(boundary, ("Edge1",))]
        obj.TrimmedProfileType = "End Miter"
        for key, value in props.items():
            setattr(obj, key, value)
        return obj

    def miter_pair(self, edges, first, second, **props):
        sketch = self.make_sketch(*edges)
        p1 = self.make_profile(sketch, "Edge1", **first)
        p2 = self.make_profile(sketch, "Edge2", **second)
        m1, m2 = self.make_miter(p1, p2, **props), self.make_miter(p2, p1, **props)
        self.doc.recompute()
        for obj in (m1, m2):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertTrue(obj.Shape.isValid())
        return (p1, p2), (m1, m2)

    @staticmethod
    def axis(edge):
        a, b = (App.Vector(*p) for p in edge)
        return (b - a).normalize()

    @staticmethod
    def cut_face(shape, axis):
        # The miter face is the planar face, not parallel to the axis, nearest the corner.
        faces = [f for f in shape.Faces if isinstance(f.Surface, Part.Plane) and abs(f.normalAt(0, 0).dot(axis)) > 1e-6]
        return min(faces, key=lambda f: f.CenterOfMass.Length)

    def assert_perfect_joint(self, edges, m1, m2):
        f1 = self.cut_face(m1.Shape, self.axis(edges[0]))
        f2 = self.cut_face(m2.Shape, self.axis(edges[1]))
        self.assertAlmostEqual(m1.Shape.common(m2.Shape).Volume, 0.0, places=4)
        self.assertAlmostEqual(f1.Area, f2.Area, places=3)
        self.assertAlmostEqual(f1.common(f2).Area, f1.Area, places=3)


class TestEndMiterGeometry(MiterFixture):
    def test_start_start_edges_with_left_anchors_meet_face_to_face(self):
        _, (m1, m2) = self.miter_pair(START_START, LEFT, LEFT)
        self.assert_perfect_joint(START_START, m1, m2)

    def test_offset_on_one_profile_moves_the_miter_plane(self):
        _, (m1, m2) = self.miter_pair(CHAINED, dict(CENTER, offset_x=10.0), CENTER)
        self.assert_perfect_joint(CHAINED, m1, m2)

    def test_rotated_profile_with_same_anchor_meets_face_to_face(self):
        _, (m1, m2) = self.miter_pair(CHAINED, dict(LEFT, rotation=180.0), LEFT)
        self.assert_perfect_joint(CHAINED, m1, m2)

    def test_previous_perfect_joints_still_hold(self):
        cases = {
            "chained centered": (CHAINED, CENTER, CENTER),
            "chained left": (CHAINED, LEFT, LEFT),
            "start-start centered": (START_START, CENTER, CENTER),
            "same offsets": (CHAINED, dict(CENTER, offset_x=10.0), dict(CENTER, offset_x=10.0)),
            "60 degrees": ((((200, 0, 0), (0, 0, 0)), ((0, 0, 0), polar(200, 60))), CENTER, CENTER),
            "mixed anchors rotated corner": (((polar(200, 30), (0, 0, 0)), ((0, 0, 0), polar(200, 120))), LEFT, CENTER),
        }
        for name, (edges, first, second) in cases.items():
            with self.subTest(name):
                _, (m1, m2) = self.miter_pair(edges, first, second)
                self.assert_perfect_joint(edges, m1, m2)

    def test_cutting_angles_report_the_miter_angle(self):
        edges = (((200, 0, 0), (0, 0, 0)), ((0, 0, 0), polar(200, 60)))
        _, (m1, m2) = self.miter_pair(edges, CENTER, CENTER)
        for obj in (m1, m2):
            self.assertEqual(obj.CuttingAngleB, "@ 60.0")

    def test_unsupported_trimmed_body_raises_instead_of_looping(self):
        proxy = TrimmedProfile.__new__(TrimmedProfile)
        outcome = {}

        def resolve():
            try:
                proxy.getTarget(SimpleNamespace(Name="Box"))
            except Exception as exc:  # noqa: BLE001
                outcome["error"] = exc

        worker = threading.Thread(target=resolve, daemon=True)
        worker.start()
        worker.join(2.0)
        self.assertFalse(worker.is_alive(), "getTarget never returned")
        self.assertIsInstance(outcome.get("error"), RuntimeError)

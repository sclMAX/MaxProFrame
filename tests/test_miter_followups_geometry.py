"""Miter review follow-ups: bounded extension, joint search, raw cut angles and legacy migration."""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture, polar

from freecad.maxproframe.miter_geometry import Member
from freecad.maxproframe.miter_joints import find_joints

DIAGONAL = 50.0 * 2**0.5
TRAPEZOID = (
    ((0, 0, 0), (400, 0, 0)),
    ((400, 0, 0), (300, 200, 0)),
    ((300, 200, 0), (100, 200, 0)),
    ((100, 200, 0), (0, 0, 0)),
)


def line(a, b):
    return Part.makeLine(App.Vector(*a), App.Vector(*b))


class TestMiterFollowupsGeometry(MiterFixture):
    def v_miter(self, degrees):
        sketch = self.make_sketch(((200, 0, 0), (0, 0, 0)), ((0, 0, 0), polar(200, degrees)))
        p1 = self.make_profile(sketch, "Edge1", extension=0.0)
        p2 = self.make_profile(sketch, "Edge2", extension=0.0)
        miter = self.make_miter(p1, p2)
        self.doc.recompute()
        return miter

    def test_sharp_v_extension_is_refused_as_too_far(self):
        miter = self.v_miter(5.0)
        self.assertTrue(miter.MiterExtend)
        self.assertNotEqual(miter.getStatusString(), "Valid")
        self.assertIn("too far", miter.getStatusString())

    def test_moderate_v_still_extends(self):
        miter = self.v_miter(30.0)
        self.assertEqual(miter.getStatusString(), "Valid")
        self.assertTrue(miter.Shape.isValid())

    def test_trapezoid_frame_has_four_joints(self):
        members = []
        for edge in TRAPEZOID:
            sketch = self.make_sketch(edge)
            profile = self.make_profile(sketch, "Edge1", **CENTER)
            member = Member(sketch.getSubObject("Edge1"), profile.Shape)
            members.append((member.edge, member.section.BoundBox.DiagonalLength))
        joints, skipped = find_joints(members)
        self.assertEqual(skipped, [])
        self.assertEqual(sorted((joint.first, joint.second) for joint in joints), [(0, 1), (0, 3), (1, 2), (2, 3)])
        corners = sorted(tuple(round(c, 6) for c in joint.point) for joint in joints)
        self.assertEqual(corners, sorted(tuple(float(c) for c in edge[0]) for edge in TRAPEZOID))

    def test_nearly_parallel_same_direction_members_form_no_joint(self):
        members = [
            (line((0, 0, 0), (200, 0, 0)), DIAGONAL),
            (line((0, 100, 0), (200, 100.002, 0)), DIAGONAL),
        ]
        self.assertEqual(find_joints(members), ([], []))

    def test_cut_angle_is_raw_and_rounded_only_for_display(self):
        edges = (CHAINED[0], ((0, 0, 0), polar(200, 50.26)))
        _, (m1, m2) = self.miter_pair(edges, CENTER, CENTER)
        for obj in (m1, m2):
            self.assertAlmostEqual(obj.Proxy.miter_planes(obj)[0].cut_angle(), 64.87, places=6)
            self.assertEqual(obj.CuttingAngleB, "@ 64.9")


if __name__ == "__main__":
    unittest.main()

"""Miter review follow-ups: bounded extension, joint search, raw cut angles and legacy migration."""

import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture, polar

from freecad.maxproframe.miter_geometry import Member
from freecad.maxproframe.miter_joints import find_joints

DIAGONAL = 50.0 * 2**0.5
# A 50 x 50 x 2 square hollow section.
SECTION_AREA = 50.0**2 - 46.0**2
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

    def shortened_member(self, offset_b):
        """Member of a profile on x = 0..400 whose end B, at the path start, is moved by ``offset_b``."""
        sketch = self.make_sketch(((0, 0, 0), (400, 0, 0)))
        profile = self.make_profile(sketch, "Edge1", extension=0.0, **CENTER)
        profile.OffsetB = offset_b
        self.doc.recompute()
        return Member(sketch.getSubObject("Edge1"), profile.Shape)

    def test_a_member_takes_its_section_at_mid_edge(self):
        member = self.shortened_member(0.0)
        self.assertAlmostEqual(member.param, member.edge.FirstParameter + member.edge.Length / 2.0, places=6)

    def test_a_member_shortened_past_its_midpoint_takes_its_section_inside_the_body(self):
        # The body runs from x = 300 to 400: the path midpoint x = 200 lies outside it.
        member = self.shortened_member(-300.0)
        self.assertTrue(300.0 <= member.edge.valueAt(member.param).x <= 400.0)
        self.assertTrue(member.section.Faces)
        self.assertAlmostEqual(member.section.Area, SECTION_AREA, places=6)
        # Moved to each path end, the section stays centred on the axis.
        for at_start, x in ((True, 0.0), (False, 400.0)):
            centroid = member.end(at_start)[2]
            self.assertAlmostEqual((centroid - App.Vector(x, 0, 0)).Length, 0.0, places=6)

    def test_an_end_miter_on_a_profile_shortened_past_its_midpoint_meets_face_to_face(self):
        sketch = self.make_sketch(*CHAINED)
        p1 = self.make_profile(sketch, "Edge1", **CENTER)
        p2 = self.make_profile(sketch, "Edge2", **CENTER)
        # End B of p1, at its path start, moves from x = 250 to x = 50: the path midpoint x = 100 lies outside the body.
        p1.OffsetB = -150.0
        self.doc.recompute()
        self.assertAlmostEqual(p1.Shape.BoundBox.XMax, 50.0, places=5)
        m1, m2 = self.make_miter(p1, p2), self.make_miter(p2, p1)
        self.doc.recompute()
        for obj in (m1, m2):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertTrue(obj.Shape.isValid())
        self.assert_perfect_joint(CHAINED, m1, m2)

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

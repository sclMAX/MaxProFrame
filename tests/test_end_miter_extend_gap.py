"""End Miter extension up to the joint and configurable gap between the cut faces."""

import unittest

from test_end_miter_geometry import CENTER, CHAINED, MiterFixture

SECTION_AREA = 543.058  # 50x50x2 tube cut at 45 degrees


class TestEndMiterExtendGap(MiterFixture):
    def test_new_miter_extends_by_default(self):
        _, (m1, _) = self.miter_pair(CHAINED, CENTER, CENTER)
        self.assertTrue(m1.MiterExtend)
        self.assertEqual(m1.MiterGap.Value, 0.0)

    def test_extend_completes_profiles_that_stop_at_the_vertex(self):
        _, (m1, m2) = self.miter_pair(CHAINED, dict(CENTER, extension=0.0), dict(CENTER, extension=0.0))
        self.assert_perfect_joint(CHAINED, m1, m2)
        self.assertAlmostEqual(self.cut_face(m1.Shape, self.axis(CHAINED[0])).Area, SECTION_AREA, places=2)
        self.assertAlmostEqual(m1.Length.Value, 225.0, places=3)

    def test_extend_reaches_a_vertex_beyond_a_short_path(self):
        edges = (((200, 0, 0), (30, 0, 0)), ((0, 0, 0), (0, 200, 0)))
        _, (m1, m2) = self.miter_pair(edges, dict(CENTER, extension=0.0), dict(CENTER, extension=0.0))
        self.assert_perfect_joint(edges, m1, m2)
        self.assertAlmostEqual(m1.Length.Value, 225.0, places=3)

    def test_without_extend_short_profiles_keep_their_length(self):
        (p1, _), (m1, m2) = self.miter_pair(
            CHAINED, dict(CENTER, extension=0.0), dict(CENTER, extension=0.0), MiterExtend=False
        )
        self.assertLess(self.cut_face(m1.Shape, self.axis(CHAINED[0])).Area, SECTION_AREA - 1.0)
        self.assertLessEqual(m1.Shape.Volume, p1.Shape.Volume + 1e-6)

    def test_gap_leaves_that_distance_between_the_cut_faces(self):
        _, (m1, m2) = self.miter_pair(CHAINED, CENTER, CENTER, MiterGap=0.5)
        f1 = self.cut_face(m1.Shape, self.axis(CHAINED[0]))
        f2 = self.cut_face(m2.Shape, self.axis(CHAINED[1]))
        self.assertAlmostEqual(m1.Shape.distToShape(m2.Shape)[0], 0.5, places=5)
        self.assertAlmostEqual(abs(f1.normalAt(0, 0).dot(f2.normalAt(0, 0))), 1.0, places=7)
        self.assertAlmostEqual(f1.Area, f2.Area, places=3)
        # 50 mm pre-extension at the far end; the 0.25 mm shift along the miter normal.
        self.assertAlmostEqual(m1.Length.Value, 275.0 - 0.25 * 2**0.5, places=3)

    def test_extension_beyond_the_limit_is_refused(self):
        edges = (((5000, 0, 0), (4000, 0, 0)), ((0, 0, 0), (0, 200, 0)))
        sketch = self.make_sketch(*edges)
        p1 = self.make_profile(sketch, "Edge1", extension=0.0)
        p2 = self.make_profile(sketch, "Edge2", extension=0.0)
        miter = self.make_miter(p1, p2)
        self.doc.recompute()
        self.assertNotEqual(miter.getStatusString(), "Valid")
        self.assertIn("too far", miter.getStatusString())


if __name__ == "__main__":
    unittest.main()

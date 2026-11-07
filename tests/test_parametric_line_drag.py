"""Dragging a parametric line in a global plane: where the cursor ray meets the plane, and what it snaps to."""

import unittest

import FreeCAD as App

from freecad.maxproframe.parametric_line_drag import edge_on, plane_at, plane_point, snapped_direction

START = App.Vector(10, 20, 30)


class TestPlanePoint(unittest.TestCase):
    def test_the_ray_meets_the_plane_through_the_start(self):
        point = plane_point(START, "XY", App.Vector(50, 60, 100), App.Vector(0, 0, -1))
        self.assertTrue(point.isEqual(App.Vector(50, 60, 30), 1e-9))
        point = plane_point(START, "XZ", App.Vector(0, -100, 0), App.Vector(1, 1, 0))
        self.assertTrue(point.isEqual(App.Vector(120, 20, 0), 1e-9))

    def test_a_ray_along_the_plane_meets_it_nowhere(self):
        self.assertIsNone(plane_point(START, "YZ", App.Vector(0, 0, 0), App.Vector(0, 1, 1)))


class TestEdgeOn(unittest.TestCase):
    def test_a_plane_seen_under_10_degrees_is_edge_on(self):
        self.assertTrue(edge_on("XY", App.Vector(1, 0, 0)))
        self.assertTrue(edge_on("XY", App.Vector(1, 0, -0.17)))
        self.assertFalse(edge_on("XY", App.Vector(1, 0, -0.18)))
        self.assertFalse(edge_on("XY", App.Vector(0, 0, -1)))
        self.assertFalse(edge_on("YZ", App.Vector(-1, -1, -1)))


class TestPlaneAt(unittest.TestCase):
    def test_the_nearest_square_the_ray_crosses(self):
        # The squares run from the start along the positive axes of each plane, 50 long.
        down = App.Vector(0, 0, -1)
        self.assertEqual(plane_at(START, 50, App.Vector(30, 40, 500), down), "XY")
        self.assertIsNone(plane_at(START, 50, App.Vector(-30, 40, 500), down))
        self.assertIsNone(plane_at(START, 50, App.Vector(30, 80, 500), down))
        # This ray crosses the XZ square first, then the XY square.
        origin = START + App.Vector(20, -10, 40)
        self.assertEqual(plane_at(START, 50, origin, App.Vector(0, 1, -1)), "XZ")
        self.assertEqual(plane_at(START, 50, origin, App.Vector(0, 1, -1), planes=("XY", "YZ")), "XY")

    def test_a_plane_left_out_is_not_hit(self):
        down = App.Vector(0, 0, -1)
        self.assertIsNone(plane_at(START, 50, App.Vector(30, 40, 500), down, planes=("XZ", "YZ")))


class TestSnappedDirection(unittest.TestCase):
    def test_on_an_axis_of_the_plane_the_line_runs_along_that_global_axis(self):
        for plane, offset, direction in (
            ("XY", (73, 2, 0), "+X"),
            ("XY", (-3, -126, 0), "-Y"),
            ("XZ", (-50, 0, 1), "-X"),
            ("XZ", (1, 0, -704), "-Z"),
            ("YZ", (0, 3, 98), "+Z"),
        ):
            with self.subTest(plane=plane, offset=offset):
                result = snapped_direction(plane, START, START + App.Vector(*offset))
                self.assertEqual(result[0], direction)
                self.assertEqual(result[2], round(App.Vector(*offset).Length, -1))

    def test_any_other_way_is_an_angle_every_15_degrees(self):
        # 33° in XZ snaps to 30°; -140° in YZ to -135°.
        self.assertEqual(snapped_direction("XZ", START, START + App.Vector(83.9, 0, 54.5)), ("Angle", 30, 100))
        self.assertEqual(snapped_direction("YZ", START, START + App.Vector(0, -76.6, -64.3)), ("Angle", -135, 100))

    def test_the_length_snaps_to_10_mm_or_to_1_mm_fine(self):
        self.assertEqual(snapped_direction("XY", START, START + App.Vector(234.6, 0, 0)), ("+X", 0, 230))
        self.assertEqual(snapped_direction("XY", START, START + App.Vector(234.6, 0, 0), fine=True), ("+X", 0, 235))

    def test_the_length_is_never_shorter_than_one_step(self):
        self.assertEqual(snapped_direction("XY", START, START + App.Vector(0.2, 0, 0)), ("+X", 0, 10))
        self.assertEqual(snapped_direction("XY", START, START), ("+X", 0, 10))
        self.assertEqual(snapped_direction("XY", START, START, fine=True), ("+X", 0, 1))

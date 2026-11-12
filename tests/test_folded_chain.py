"""Chain of tube segments joined by folded corners (odd/tasks/folded-miter.md, T2: S2, S5, S17, S18).

The selected profiles are ordered into one chain from the first selected one, each corner gets its bend angle,
axis and outer wall, and the chain is refused, with a message saying why, when its segments cannot fold into one bar.
"""

import math
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import polar

from freecad.maxproframe.folded_chain import ChainError, build_chain
from freecad.maxproframe.profile import Profile
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# Counterclockwise rectangle: bottom, right, top, left.
RECTANGLE = (
    ((0, 0, 0), (300, 0, 0)),
    ((300, 0, 0), (300, 200, 0)),
    ((300, 200, 0), (0, 200, 0)),
    ((0, 200, 0), (0, 0, 0)),
)
TOLERANCE = 1e-6


def vector(values):
    return App.Vector(*values)


class ChainFixture(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("FoldedChain")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def make_sketch(self, *edges):
        sketch = self.doc.addObject("Sketcher::SketchObject", "Path")
        for a, b in edges:
            sketch.addGeometry(Part.LineSegment(vector(a), vector(b)))
        self.doc.recompute()
        return sketch

    def make_profile(
        self,
        sketch,
        edge,
        family="Square Hollow",
        width=50.0,
        height=50.0,
        thickness=2.0,
        material="Steel",
        anchor_x=1,
        anchor_y=1,
        rotation=0.0,
    ):
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (sketch, edge)
        obj.MapPathParameter = 1
        Profile(
            obj,
            init_w=width,
            init_h=height,
            init_mt=thickness,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=False,
            init_anchor_x=anchor_x,
            init_anchor_y=anchor_y,
            material=material,
            fam=family,
            size_name=f"{width:g}x{height:g}x{thickness:g}",
            bevels_combined=False,
            catalog_family=family,
            link_sub=(sketch, (edge,)),
            init_rotation=rotation,
            init_offset_a=0.0,
            init_offset_b=0.0,
            init_offset_x=0.0,
        )
        self.doc.recompute()
        self.assertEqual("Valid", obj.getStatusString())
        return obj

    def frame(self, edges=RECTANGLE, **props):
        sketch = self.make_sketch(*edges)
        return [self.make_profile(sketch, f"Edge{index + 1}", **props) for index in range(len(edges))]

    def assertVector(self, expected, actual):
        self.assertLess((vector(expected) - actual).Length, TOLERANCE, f"{expected} != {actual}")

    def assertRefused(self, message, tips, **kwargs):
        with self.assertRaises(ChainError) as raised:
            build_chain(tips, **kwargs)
        self.assertEqual(message, str(raised.exception))


class RectangleTest(ChainFixture):
    def test_rectangle_folds_three_corners_and_opens_where_first_and_last_selected_meet(self):
        bottom, right, top, left = self.frame()

        chain = build_chain([bottom, right, top, left])

        self.assertTrue(chain.closed)
        self.assertEqual([bottom, right, top, left], [segment.profile for segment in chain.segments])
        self.assertEqual([bottom, right, top, left], [segment.tip for segment in chain.segments])
        self.assertVector((0, 0, 0), chain.segments[0].start)
        self.assertVector((300, 0, 0), chain.segments[0].end)
        self.assertVector((0, 0, 0), chain.segments[-1].end)
        self.assertEqual([300.0, 200.0, 300.0, 200.0], [round(segment.length, 6) for segment in chain.segments])
        self.assertVector((0, 0, 0), chain.open_point)
        self.assertEqual(3, len(chain.corners))
        for corner, point in zip(chain.corners, ((300, 0, 0), (300, 200, 0), (0, 200, 0))):
            self.assertVector(point, corner.point)
            self.assertAlmostEqual(90.0, corner.bend_angle, places=6)
            self.assertAlmostEqual(1.0, abs(corner.axis.z), places=6)
            self.assertAlmostEqual(50.0, corner.depth, places=6)
        self.assertVector((0, -1, 0), chain.corners[0].outer_normal)
        self.assertVector((1, 0, 0), chain.corners[1].outer_normal)
        self.assertVector((0, 1, 0), chain.corners[2].outer_normal)

    def test_selection_order_does_not_change_the_chain(self):
        bottom, right, top, left = self.frame()

        chain = build_chain([bottom, top, right, left])

        self.assertEqual([bottom, right, top, left], [segment.profile for segment in chain.segments])
        self.assertVector((0, 0, 0), chain.open_point)

    def test_open_corner_given_on_the_first_selected_segment_sets_the_start(self):
        bottom, right, top, left = self.frame()

        chain = build_chain([bottom, right, top, left], open_corner=(bottom, right))

        self.assertEqual([bottom, left, top, right], [segment.profile for segment in chain.segments])
        self.assertVector((300, 0, 0), chain.segments[0].start)
        self.assertVector((0, 0, 0), chain.segments[0].end)
        self.assertVector((300, 0, 0), chain.open_point)
        self.assertEqual(
            [(0, 0, 0), (0, 200, 0), (300, 200, 0)],
            [tuple(round(c, 6) for c in corner.point) for corner in chain.corners],
        )

    def test_open_corner_away_from_the_first_selected_segment_is_refused(self):
        bottom, right, top, left = self.frame()

        self.assertRefused(
            "The open corner must be at one end of the first selected profile (Profile).",
            [bottom, right, top, left],
            open_corner=(right, top),
        )

    def test_open_corner_between_profiles_that_do_not_meet_is_refused(self):
        bottom, right, top, left = self.frame()

        self.assertRefused(
            "Profile and Profile002 do not meet at a corner.", [bottom, right, top, left], open_corner=(bottom, top)
        )

    def test_selected_trims_and_their_tips_are_followed_down_to_the_profiles(self):
        bottom, right, top, left = self.frame()
        miters = []
        for body, boundary in ((bottom, left), (left, bottom)):
            miter = self.doc.addObject("Part::FeaturePython", "Miter")
            TrimmedProfile(miter)
            miter.TrimmedBody = body
            miter.TrimmingBoundary = [(boundary, ("Edge1",))]
            miter.TrimmedProfileType = "End Miter"
            miters.append(miter)
        self.doc.recompute()

        chain = build_chain([bottom, right, top, miters[1]])

        self.assertEqual([bottom, right, top, left], [segment.profile for segment in chain.segments])
        self.assertEqual([miters[0], right, top, miters[1]], [segment.tip for segment in chain.segments])

    def test_rectangular_tube_turned_on_its_side_bends_across_its_width(self):
        bottom, right, top, left = self.frame(family="Rectangular Hollow", width=40.0, height=80.0)
        flat = self.frame(family="Rectangular Hollow", width=40.0, height=80.0, rotation=90.0)

        depths = {round(corner.depth, 6) for corner in build_chain([bottom, right, top, left]).corners}
        flat_depths = {round(corner.depth, 6) for corner in build_chain(flat).corners}

        self.assertEqual(1, len(depths))
        self.assertEqual({40.0, 80.0} - depths, flat_depths)


class OpenChainTest(ChainFixture):
    def test_arbitrary_angles_are_folded(self):
        a = (0, 0, 0)
        b = (200, 0, 0)
        c = tuple(p + q for p, q in zip(b, polar(150, 60)))
        d = tuple(p + q for p, q in zip(c, polar(120, 195)))
        first, second, third = self.frame(edges=((a, b), (b, c), (c, d)))

        chain = build_chain([first, second, third])

        self.assertFalse(chain.closed)
        self.assertIsNone(chain.open_point)
        self.assertEqual([60.0, 135.0], [round(corner.bend_angle, 6) for corner in chain.corners])
        self.assertEqual([200.0, 150.0, 120.0], [round(segment.length, 6) for segment in chain.segments])

    def test_open_chain_starts_at_the_free_end_of_the_first_selected_profile(self):
        first, second = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0))))

        chain = build_chain([second, first])

        self.assertEqual([second, first], [segment.profile for segment in chain.segments])
        self.assertVector((200, 100, 0), chain.segments[0].start)
        self.assertVector((0, 0, 0), chain.segments[-1].end)

    def test_first_selected_profile_inside_an_open_chain_is_refused(self):
        a, b, c = self.frame(
            edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)), ((200, 100, 0), (0, 100, 0)))
        )

        self.assertRefused("Select first a profile at one end of the chain: Profile001 is in its middle.", [b, a, c])

    def test_open_corner_inside_an_open_chain_is_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0))))

        self.assertRefused(
            "Only a closed frame has an open corner: these profiles already have two free ends.",
            [a, b],
            open_corner=(a, b),
        )


class RefusedChainTest(ChainFixture):
    def test_one_profile_is_not_a_chain(self):
        (only,) = self.frame(edges=(((0, 0, 0), (200, 0, 0)),))

        self.assertRefused("Select at least two profiles that meet end to end.", [only])

    def test_the_same_profile_twice_is_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0))))

        self.assertRefused("Profile is selected more than once.", [a, b, a])

    def test_profiles_that_do_not_meet_are_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((300, 0, 0), (300, 100, 0))))

        self.assertRefused("The selected profiles do not form one chain: Profile meets none of the others.", [a, b])

    def test_three_profiles_meeting_at_one_point_are_refused(self):
        a, b, c = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)), ((200, 0, 0), (400, 0, 0))))

        self.assertRefused("More than two of the selected profiles meet at one point.", [a, b, c])

    def test_profiles_in_line_are_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (400, 0, 0))))

        self.assertRefused("Profile and Profile001 are in line: there is nothing to fold.", [a, b])

    def test_profile_turning_back_is_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (100, 0, 0))))

        self.assertRefused("Profile001 turns back on Profile: a corner can fold less than 180 degrees.", [a, b])

    def test_curved_path_is_refused(self):
        sketch = self.make_sketch(((0, 0, 0), (200, 0, 0)))
        sketch.addGeometry(
            Part.ArcOfCircle(Part.Circle(vector((200, 100, 0)), vector((0, 0, 1)), 100), -math.pi / 2, 0)
        )
        self.doc.recompute()
        a = self.make_profile(sketch, "Edge1")
        b = self.make_profile(sketch, "Edge2")

        self.assertRefused("Profile001 follows a curved path: only straight profiles can be folded.", [a, b])

    def test_other_families_are_refused(self):
        sketch = self.make_sketch(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)))
        a = self.make_profile(sketch, "Edge1")
        b = self.make_profile(sketch, "Edge2", family="Flat Sections", width=40.0, height=5.0, thickness=0.0)

        self.assertRefused(
            "Profile001 is a Flat Sections profile: only Square Hollow and Rectangular Hollow tubes can be folded.",
            [a, b],
        )

    def test_different_tubes_are_refused(self):
        sketch = self.make_sketch(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)))
        a = self.make_profile(sketch, "Edge1")
        cases = (
            (
                dict(width=60.0, height=60.0),
                "Profile001 is not the same tube as Profile: 60 x 60 x 2 instead of 50 x 50 x 2.",
            ),
            (dict(thickness=3.0), "Profile002 is not the same tube as Profile: 50 x 50 x 3 instead of 50 x 50 x 2."),
            (dict(material="Aluminium"), "Profile003 is not the same tube as Profile: Aluminium instead of Steel."),
        )
        for props, message in cases:
            with self.subTest(props=props):
                b = self.make_profile(sketch, "Edge2", **props)
                self.assertRefused(message, [a, b])

    def test_section_moved_by_its_anchor_across_a_fold_is_refused(self):
        sketch = self.make_sketch(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)))
        a = self.make_profile(sketch, "Edge1")
        b = self.make_profile(sketch, "Edge2", anchor_x=0)

        self.assertRefused(
            "Profile001 does not continue Profile across the fold: give both the same anchor, offsets and rotation.",
            [a, b],
        )

    def test_rectangular_section_turned_across_a_fold_is_refused(self):
        sketch = self.make_sketch(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0)))
        rect = dict(family="Rectangular Hollow", width=40.0, height=80.0)
        a = self.make_profile(sketch, "Edge1", **rect)
        b = self.make_profile(sketch, "Edge2", rotation=90.0, **rect)

        self.assertRefused(
            "Profile001 does not continue Profile across the fold: give both the same anchor, offsets and rotation.",
            [a, b],
        )

    def test_bend_axis_not_parallel_to_a_wall_is_refused(self):
        a, b = self.frame(edges=(((0, 0, 0), (200, 0, 0)), ((200, 0, 0), (200, 100, 0))), rotation=45.0)

        self.assertRefused(
            "The corner between Profile and Profile001 bends across a corner of the tube: "
            "its walls must be parallel to the bend.",
            [a, b],
        )


if __name__ == "__main__":
    unittest.main()

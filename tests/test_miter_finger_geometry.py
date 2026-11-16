"""Fingers at the inner vertex of an End Miter corner (odd/tasks/miter-fingers.md, T1: S2 S3 S4, D3 D4).

Two separate tubes A and B, each cut by its own End Miter against the other, interlock in the band of their inner
walls (the finger depth s from the face of each inner wall): the band is split along the corner axis into fingers
that alternate which tube covers the overlap of both bands, A (the first face given) owning the first one and Flip
swapping them (D3). Below the band the corner stays the plain miter (S3). With an End Miter Gap the fingers bridge it
and the pieces still interlock (S4). Every cut is a plane square to the wall it goes through (D4): tube cross-sections,
planes parallel to the inner walls and planes across the corner axis, so the non-covering tube is cut back past the
overlap and an oblique corner keeps a small notch at its inner vertex (0.5 s^2 |cot(angle)| per unit of height).
"""

import math
import unittest
from dataclasses import replace

import FreeCAD as App
import Part
from miter_helpers import use_language

from freecad.maxproframe.interlock_geometry import CHAMFER, ROUND, SQUARE, FingerSettings, InterlockError
from freecad.maxproframe.miter_finger_geometry import MiterCorner, MiterTube, check, joined, make_fingers
from freecad.maxproframe.miter_geometry import MiterPlane

# 40 x 30 tubes, 2 mm walls: 40 across the corner plane (Y before turning), 30 along the corner axis (Z).
DEPTH, HIGH, T = 40.0, 30.0, 2.0
RADIUS = 4.0
LENGTH = 150.0
NAMES = ("TubeA", "TubeB")
X, Y, Z = App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)
TOLERANCE = 1e-6
VOLUME_TOLERANCE = 1e-3


def tube(depth=DEPTH, high=HIGH, radius=0.0):
    """A rectangular tube along X from -LENGTH to LENGTH, centered on the X axis: ``depth`` along Y, ``high`` along Z,
    walls T thick with outer corners of ``radius`` (0: sharp)."""

    def rounded(length, width, height, radius, x):
        box = Part.makeBox(length, width, height, App.Vector(x, -width / 2, -height / 2))
        if radius <= TOLERANCE:
            return box
        along = [edge for edge in box.Edges if abs(edge.Vertexes[0].Point.x - edge.Vertexes[1].Point.x) > TOLERANCE]
        return box.makeFillet(radius, along)

    outer = rounded(2 * LENGTH, depth, high, radius, -LENGTH)
    inner = rounded(2 * LENGTH + 2, depth - 2 * T, high - 2 * T, radius - T, -LENGTH - 1)
    return outer.cut(inner)


def planar_face(shape, normal):
    """The planar face of ``shape`` whose outward normal is ``normal``, farthest along it."""
    found = [
        face
        for face in shape.Faces
        if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).getAngle(normal) < 1e-6
    ]
    return max(found, key=lambda face: face.CenterOfMass.dot(normal))


def away(angle):
    """The axis of B from the corner, at the inner ``angle`` (degrees) from A's axis away from it (-X)."""
    alpha = math.radians(angle)
    return App.Vector(-math.cos(alpha), math.sin(alpha), 0)


def inner_normal_b(angle):
    """The outward normal of B's inner wall face (A's -Y face turned with B), toward the inside of the corner."""
    alpha = math.radians(angle)
    return App.Vector(-math.sin(alpha), -math.cos(alpha), 0)


class MiterFingerFixture(unittest.TestCase):
    def setUp(self):
        # Refusals are checked in English: an earlier test may leave FreeCAD in another language.
        use_language(self, "English", "en_US")

    @staticmethod
    def miter_corner(angle=90.0, gap=0.0, radius=0.0, depth=DEPTH, high_b=HIGH, inner=True):
        """(MiterCorner, (plain A, plain B), (plane A, plane B)): A along X to the corner at the origin, B leaving it at
        the inner ``angle``, both cut by their End Miter planes (the bisector through the crossing of their axes,
        each shifted half the ``gap`` into its tube, as TrimmedProfile._end_miter does)."""
        e_b = away(angle)
        template_a = tube(depth, HIGH, radius)
        template_b = tube(depth, high_b, radius)
        template_b.rotate(App.Vector(), Z, -angle)
        section_a, section_b = planar_face(template_a, -X), planar_face(template_b, e_b)
        plane_a = MiterPlane(App.Vector(), (-X - e_b).normalize(), -X, section_a).shifted(gap / 2)
        plane_b = MiterPlane(App.Vector(), (e_b + X).normalize(), e_b, section_b).shifted(gap / 2)
        a = template_a.cut(plane_a.removal_volume(template_a))
        b = template_b.cut(plane_b.removal_volume(template_b))
        n_a, n_b = (Y, inner_normal_b(angle)) if inner else (-Y, -inner_normal_b(angle))
        corner = MiterCorner(
            MiterTube(NAMES[0], planar_face(a, n_a), T, X, section_a, (plane_a.origin, plane_a.normal)),
            MiterTube(NAMES[1], planar_face(b, n_b), T, -e_b, section_b, (plane_b.origin, plane_b.normal)),
        )
        return corner, (a, b), (plane_a, plane_b)

    def interlocked(self, settings, angle=90.0, gap=0.0, radius=0.0):
        """(shapes, (A, B) with their fingers, (plain A, plain B), planes)."""
        corner, plain, planes = self.miter_corner(angle, gap, radius)
        shapes = make_fingers(settings, corner)
        return shapes, (joined(plain[0], shapes.a), joined(plain[1], shapes.b)), plain, planes

    def assertOneValidSolid(self, shape):
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)

    def assertRefused(self, settings, corner, message):
        with self.assertRaises(InterlockError) as caught:
            check(settings, corner)
        self.assertEqual(str(caught.exception), message)
        with self.assertRaises(InterlockError):
            make_fingers(settings, corner)


def past(plane, shape):
    """What of ``shape`` lies past the End Miter ``plane`` (the side its tube loses)."""
    return shape.common(plane.removal_volume(shape))


def beyond(plane, shape):
    """What of ``shape`` lies on the side of ``plane`` its tube keeps."""
    flipped = MiterPlane(plane.origin, -plane.normal, plane.inward, plane.section)
    return shape.common(flipped.removal_volume(shape))


def deeper_than(corner, depth, shape):
    """The region deeper than ``depth`` from both inner wall faces of ``corner`` (into both tubes), covering ``shape``."""
    region = None
    for side in (corner.a, corner.b):
        normal = side.face.normalAt(0, 0)
        origin = side.face.CenterOfMass - normal * depth
        half = MiterPlane(origin, normal, normal, None).removal_volume(shape)
        region = half if region is None else region.common(half)
    return region


class FingerOwnersTest(MiterFingerFixture):
    """S2, D3: the finger levels alternate, A (the first face given) owns the first one, Flip swaps them."""

    def probes(self, level_w, s=T):
        """Two points of the overlap of both bands at height ``level_w``, past A's miter and before it (90 degrees:
        the inner vertex is (-20, 20))."""
        corner = App.Vector(-DEPTH / 2, DEPTH / 2, level_w)
        return corner + App.Vector(0.75 * s, -0.25 * s, 0), corner + App.Vector(0.25 * s, -0.75 * s, 0)

    def test_owners_alternate_from_the_first_face_and_flip_swaps_them(self):
        for count, flip, owners in ((3, False, [0, 1, 0]), (3, True, [1, 0, 1]), (2, False, [0, 1]), (2, True, [1, 0])):
            with self.subTest(count=count, flip=flip):
                shapes, (a, b), _, _ = self.interlocked(FingerSettings(count=count, flip=flip))
                self.assertEqual(shapes.owners, owners)
                self.assertEqual(len(shapes.a.fingers), owners.count(0))
                self.assertEqual(len(shapes.b.fingers), owners.count(1))
                bounds = FingerSettings(count=count).bounds(HIGH)
                for (low, high), owner in zip(zip(bounds, bounds[1:]), owners):
                    for point in self.probes((low + high) / 2):
                        # The owner covers the whole overlap there, on both sides of the miter; the other one gave it.
                        self.assertEqual(a.isInside(point, 1e-7, False), owner == 0, (count, flip, low, point))
                        self.assertEqual(b.isInside(point, 1e-7, False), owner == 1, (count, flip, low, point))

    def test_the_automatic_depth_is_the_wall_or_the_corner_radius(self):
        corner, _, _ = self.miter_corner()
        self.assertAlmostEqual(make_fingers(FingerSettings(), corner).depth, T)
        corner, _, _ = self.miter_corner(radius=RADIUS)
        self.assertAlmostEqual(make_fingers(FingerSettings(), corner).depth, RADIUS)
        self.assertAlmostEqual(make_fingers(FingerSettings(depth=5.0), corner).depth, 5.0)

    def test_the_tip_planes_are_where_each_tube_fingers_end(self):
        # S5 for T2: at 90 degrees with s = 2 the overlap is the 2 x 2 square at the inner vertex (-20, 20); A's fingers
        # end on its cross-section 2 - g/2 past the vertex, B's likewise along B (down).
        shapes, _, _, _ = self.interlocked(FingerSettings(clearance=0.4))
        (point_a, along_a), (point_b, along_b) = shapes.a.tip, shapes.b.tip
        self.assertAlmostEqual(along_a.getAngle(X), 0.0)
        self.assertAlmostEqual(along_b.getAngle(-Y), 0.0)
        self.assertAlmostEqual(point_a.x, -DEPTH / 2 + T - 0.2)
        self.assertAlmostEqual(point_b.y, DEPTH / 2 - T + 0.2)


class FingerSolidsTest(MiterFingerFixture):
    """S2, S3, S4, D4: each tube with its fingers is one valid solid, the tubes do not overlap and keep the clearance,
    each one reaches into the other (across the gap too), and below the band the corner is the plain miter."""

    CASES = (
        # angle, corner radius, miter gap, settings
        (90.0, 0.0, 0.0, FingerSettings()),
        (90.0, RADIUS, 0.0, FingerSettings(clearance=0.4)),
        (90.0, 0.0, 1.0, FingerSettings(count=2, clearance=0.2)),
        (120.0, 0.0, 0.0, FingerSettings(count=2, flip=True, tip=CHAMFER, tip_size=1.0, clearance=0.4)),
        (60.0, RADIUS, 0.5, FingerSettings(tip=CHAMFER, tip_size=1.0, clearance=0.2)),
        (120.0, RADIUS, 1.0, FingerSettings(flip=True, tip=ROUND, tip_size=1.5, clearance=0.2)),
        (60.0, 0.0, 0.0, FingerSettings(count=3, depth=3.0)),
    )

    def test_each_tube_is_one_solid_and_they_interlock_without_overlap(self):
        for angle, radius, gap, settings in self.CASES:
            with self.subTest(angle=angle, radius=radius, gap=gap, settings=settings):
                shapes, (a, b), plain, planes = self.interlocked(settings, angle, gap, radius)
                self.assertOneValidSolid(a)
                self.assertOneValidSolid(b)
                self.assertLess(a.common(b).Volume, VOLUME_TOLERANCE)
                g = settings.clearance
                for mine, other, plane, other_plane in ((a, b, planes[0], planes[1]), (b, a, planes[1], planes[0])):
                    fingers = past(plane, mine)
                    # S4: the fingers cross the gap into the other tube's side of its own miter plane.
                    self.assertGreater(beyond(other_plane, fingers).Volume, 1.0)
                    # The clearance opens every mating face pair by all of it.
                    self.assertGreaterEqual(fingers.distToShape(other)[0], g - 1e-6)

    def test_below_the_band_the_corner_is_the_plain_miter(self):
        # S3: deeper than the band (and what the clearance and the other tube's fingers past its band take: at most
        # 1.5 s at these angles), each tube is exactly the End Miter cut.
        for angle, radius, gap, settings in self.CASES:
            with self.subTest(angle=angle, radius=radius, gap=gap, settings=settings):
                shapes, (a, b), plain, _ = self.interlocked(settings, angle, gap, radius)
                corner, _, _ = self.miter_corner(angle, gap, radius)
                s, g = shapes.depth, settings.clearance
                below = s + g + 1e-3 if angle == 90.0 else 2 * s + g
                region = deeper_than(corner, below, plain[0].fuse(plain[1]))
                for new, old in ((a, plain[0]), (b, plain[1])):
                    changed = new.cut(old).common(region).Volume + old.cut(new).common(region).Volume
                    self.assertLess(changed, VOLUME_TOLERANCE)
                    self.assertAlmostEqual(new.common(region).Volume, old.common(region).Volume, places=3)

    def test_the_tubes_fill_the_band_but_for_the_notch_of_an_oblique_corner(self):
        # D4: every cut square to its wall; with no clearance the band is filled at 90 degrees, and an oblique corner
        # keeps the notch the cross-section cut of the tube that does not cover a level leaves at the inner vertex:
        # a triangle of legs s and s |cot(angle)|, the whole height of the tubes (R = 0: the band is the inner wall).
        for angle in (90.0, 60.0, 120.0):
            for count in (2, 3):
                with self.subTest(angle=angle, count=count):
                    shapes, (a, b), plain, _ = self.interlocked(FingerSettings(count=count), angle)
                    s = shapes.depth
                    void = plain[0].fuse(plain[1]).cut(a.fuse(b)).Volume
                    expected = 0.5 * s * s * abs(1 / math.tan(math.radians(angle))) * HIGH
                    self.assertAlmostEqual(void, expected, places=3)

    def test_chamfered_and_round_tips_take_material_from_the_fingers_only(self):
        square = self.interlocked(FingerSettings(clearance=0.2))
        for tip in (CHAMFER, ROUND):
            with self.subTest(tip=tip):
                tipped = self.interlocked(FingerSettings(clearance=0.2, tip=tip, tip_size=1.0))
                for index in (0, 1):
                    self.assertOneValidSolid(tipped[1][index])
                    self.assertLess(tipped[1][index].Volume, square[1][index].Volume - 1e-3)
                    # The cuts in the other tube stay those of square tips.
                    self.assertAlmostEqual(
                        tipped[1][index].cut(square[1][index]).Volume, 0.0, places=6, msg=(tip, index)
                    )


class FingerRefusalTest(MiterFingerFixture):
    """Refusals naming the two tubes: settings that do not fit, faces that are no End Miter corner."""

    def test_settings_that_do_not_fit_are_refused(self):
        corner, _, _ = self.miter_corner()
        self.assertRefused(
            FingerSettings(count=1),
            corner,
            "The interlock of the corner between TubeA and TubeB needs at least 2 fingers.",
        )
        self.assertRefused(
            FingerSettings(tip=CHAMFER, tip_size=6.0),
            corner,
            "The finger tips of the corner between TubeA and TubeB must be between 0 and 5 mm.",
        )
        for depth in (1.0, 20.0):
            with self.subTest(depth=depth):
                self.assertRefused(
                    FingerSettings(depth=depth),
                    corner,
                    "The finger depth of the corner between TubeA and TubeB must be between 2 and 19.9 mm.",
                )
        check(FingerSettings(depth=19.9), corner)

    def test_fingers_reaching_through_the_other_tube_at_a_sharp_angle_are_refused(self):
        # At 30 degrees A's fingers reach s (1 + cos 30) = 18.5 mm into B, past the inside of its 20 mm deep wall (18).
        corner, _, _ = self.miter_corner(angle=30.0, depth=20.0)
        self.assertRefused(
            FingerSettings(depth=9.9),
            corner,
            "The fingers of the corner between TubeA and TubeB do not fit at this angle: make the depth smaller.",
        )
        check(FingerSettings(depth=9.0), corner)

    def test_fingers_that_do_not_reach_across_the_gap_are_refused(self):
        corner, _, _ = self.miter_corner(gap=6.0)
        self.assertRefused(
            FingerSettings(),
            corner,
            "The fingers of the corner between TubeA and TubeB do not reach across the miter gap: make the gap smaller "
            "or the depth larger.",
        )
        check(FingerSettings(depth=6.0), corner)

    def test_faces_that_are_no_end_miter_corner_are_refused(self):
        message = "The faces of TubeA and TubeB are not the inner walls of an End Miter corner between them."
        corner, _, _ = self.miter_corner(inner=False)
        self.assertRefused(FingerSettings(), corner, message)
        corner, _, _ = self.miter_corner()
        # B's inner wall 5 mm back along its axis: it no longer ends on its miter plane at the inner vertex.
        moved = corner.b.face.copy()
        moved.translate(-corner.b.direction * 5)
        self.assertRefused(FingerSettings(), MiterCorner(corner.a, replace(corner.b, face=moved)), message)
        # Both faces parallel: no corner between them.
        self.assertRefused(FingerSettings(), MiterCorner(corner.a, replace(corner.b, face=corner.a.face)), message)

    def test_tubes_of_another_size_along_the_corner_are_refused(self):
        corner, _, _ = self.miter_corner(high_b=40.0)
        self.assertRefused(
            FingerSettings(),
            corner,
            "TubeA and TubeB are not the same size along their corner: their fingers cannot match.",
        )


if __name__ == "__main__":
    unittest.main()

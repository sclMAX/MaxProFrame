"""FoldedBar and UnfoldedBar objects (odd/tasks/folded-miter.md, T5: S2 S3 S4 S13 S19, with S14 S17 S20 as properties)
and the FoldedCorner objects of a bar (odd/tasks/folded-corners.md, T3: S7 S10 S11).

A closed rectangle of four tubes with three folded corners and an open one becomes one FoldedBar: one valid solid
where the frame was drawn, recomputed when one of its corners changes, saved and opened again with the document. Each
corner is a FoldedCorner object of its own (outer radius, clearance, key, K-factor; the open one of a closed frame
too); the bar keeps no bend setting. It hides the segment tips and is one piece for the BOM, the cut list and the IDs,
of its developed length. The UnfoldedBar is the straight bar from X = 0 that FreeCAD's own STEP export writes.
"""

import math
import os
import shutil
import tempfile
import unittest
from unittest import mock

import FreeCAD as App
import Part
from test_unfolded_geometry import PLAIN, UnfoldFixture, bend

from freecad.maxproframe import folded_bar
from freecad.maxproframe._utils import get_profiles_and_links_from_document, get_profiles_and_links_from_object
from freecad.maxproframe.best_fit import CutPart, best_fit_decreasing
from freecad.maxproframe.create_bom import make_cut_list, traverse_assembly
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.folded_bar import bar_chain, make_folded_bar, make_unfolded_bar
from freecad.maxproframe.folded_chain import ChainError, build_chain
from freecad.maxproframe.folded_corner import is_folded_corner
from freecad.maxproframe.folded_geometry import fold, fold_bar
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.profile_pattern import container_placement, placed
from freecad.maxproframe.unfolded_geometry import CornerSettings, UnfoldError, check_settings, unfold

VOLUME_TOLERANCE = 1e-3
LENGTH_TOLERANCE = 1e-4
STOCK_PARAM = "Stock Length"
KERF = 1.0
# folded-corners S7, S10: every bend setting left the bar for its corners (no migration, S11).
REMOVED_BAR_PROPERTIES = (
    "BendConfiguration",
    "BendMaterial",
    "WallThickness",
    "InsideRadius",
    "KFactor",
    "CornerRadii",
    "OpenCorner",
    "Clearance",
    "Key",
    "KeyDiameter",
)
# odd/tasks/folded-bar-tools.md T9 (S4): what the bar says when its folded solid is broken.
BROKEN_MESSAGE = (
    "{} does not fold into a valid solid: check the cuts on its tubes (a hole or cutout touching an edge or another "
    "cut)."
)
CORNER_PROPERTIES = {
    "PieceA": "App::PropertyLink",
    "PieceB": "App::PropertyLink",
    "OuterRadius": "App::PropertyLength",
    "Clearance": "App::PropertyLength",
    "Key": "App::PropertyBool",
    "KeyDiameter": "App::PropertyLength",
    "KFactor": "App::PropertyFloat",
    "Open": "App::PropertyBool",
}


def open_box():
    """A solid whose shell misses a face: not valid, and no fix makes it a solid again."""
    return Part.Solid(Part.Shell(Part.makeBox(10, 10, 10).Faces[:-1]))


def corner_values(corner):
    """(OuterRadius, Clearance, Key, KeyDiameter, KFactor) of a FoldedCorner, rounded."""
    return (
        round(corner.OuterRadius.Value, 9),
        round(corner.Clearance.Value, 9),
        corner.Key,
        round(corner.KeyDiameter.Value, 9),
        round(corner.KFactor, 9),
    )


def settings_values(settings):
    return (
        round(settings.outer_radius, 9),
        round(settings.clearance, 9),
        settings.key,
        round(settings.key_diameter, 9),
        round(settings.k_factor, 9),
    )


class FoldedBarFixture(UnfoldFixture):
    def make_bar(self, container=None, corners=None, open_corner=None, **options):
        """The rectangle frame (in ``container`` when given) folded at three corners, open at the first one.

        ``corners``: the CornerSettings of every folded corner, or one per corner; else ``bend(**options)``.
        """
        profiles = self.frame()
        if container is not None:
            container.addObjects([profiles[0].AttachmentSupport[0][0], *profiles])
        bar = make_folded_bar(profiles, bend(**options) if corners is None else corners, open_corner=open_corner)
        self.assertEqual("Valid", bar.getStatusString())
        return profiles, bar

    def folded_corners(self, bar):
        """The corner objects of ``bar`` that fold, in its order."""
        return [corner for corner in bar.Corners if not corner.Open]

    def open_pairs(self, bar):
        """(PieceA, PieceB) of the open corner objects of ``bar``."""
        return [(corner.PieceA, corner.PieceB) for corner in bar.Corners if corner.Open]

    def corner_objects(self):
        return [obj for obj in self.doc.Objects if is_folded_corner(obj)]

    def assertSameVolume(self, expected, shape):
        self.assertAlmostEqual(expected.Volume, shape.Volume, delta=VOLUME_TOLERANCE)

    def assertOneSolid(self, obj):
        self.assertEqual("Valid", obj.getStatusString())
        self.assertEqual(1, len(obj.Shape.Solids))
        self.assertTrue(obj.Shape.isValid())


class FoldedBarObjectTest(FoldedBarFixture):
    def test_rectangle_folds_into_one_solid_that_hides_its_tips(self):
        profiles, bar = self.make_bar()

        chain = build_chain(profiles)
        # fold(chain, bend()) is fold_bar of this unfold.
        expected = unfold(chain, bend())
        self.assertOneSolid(bar)
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
        self.assertEqual(profiles, list(bar.Segments))
        for tip in profiles:
            self.assertFalse(tip.Visibility, tip.Label)
        self.assertTrue(bar.Visibility)
        self.assertEqual(1, bar.getEditorMode("DevelopedLength").count("ReadOnly"))
        # Like a profile, for the BOM and the cut list.
        self.assertEqual(("Square Hollow", "50x50x2", "Steel", ""), (bar.Family, bar.SizeName, bar.Material, bar.PID))

    def test_the_bar_keeps_no_bend_setting(self):
        # folded-corners S7, S10: the corners hold them; the wall thickness and the material are the profile's.
        _, bar = self.make_bar(**PLAIN)

        self.assertEqual([], [name for name in REMOVED_BAR_PROPERTIES if name in bar.PropertiesList])
        self.assertEqual("App::PropertyLinkList", bar.getTypeIdOfProperty("Corners"))

    def test_one_corner_object_per_folded_corner_and_the_open_one_of_a_closed_frame(self):
        # S10: corner objects in chain order (corner 1 at the start of the bar), then the open corner, whose sizes
        # are the first corner's.
        bottom, right, top, left = profiles = self.frame()
        settings = [
            CornerSettings(outer_radius=6.0, clearance=0.2, key=False, k_factor=0.4),
            CornerSettings(outer_radius=7.0, key=False, k_factor=0.0),
            CornerSettings(outer_radius=5.0, key=False, key_diameter=10.0, k_factor=0.45),
        ]

        bar = make_folded_bar(profiles, settings)

        self.assertOneSolid(bar)
        corners = list(bar.Corners)
        self.assertEqual(4, len(corners))
        self.assertEqual(corners, self.corner_objects())
        self.assertEqual(
            [(bottom, right), (right, top), (top, left), (bottom, left)],
            [(corner.PieceA, corner.PieceB) for corner in corners],
        )
        self.assertEqual([False, False, False, True], [corner.Open for corner in corners])
        self.assertEqual(
            [settings_values(chosen) for chosen in settings + settings[:1]],
            [corner_values(corner) for corner in corners],
        )
        for corner in corners:
            self.assertEqual("App::FeaturePython", corner.TypeId)
            self.assertNotIn("Shape", corner.PropertiesList)
            self.assertEqual(CORNER_PROPERTIES, {name: corner.getTypeIdOfProperty(name) for name in CORNER_PROPERTIES})
        expected = unfold(build_chain(profiles), settings)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
        self.assertSameVolume(fold_bar(build_chain(profiles), expected), bar.Shape)

    def test_one_settings_for_every_corner_and_an_open_chain_without_open_corner(self):
        edges = (((0, 0, 0), (300, 0, 0)), ((300, 0, 0), (300, 200, 0)), ((300, 200, 0), (0, 200, 0)))
        first, second, third = profiles = self.frame(edges=edges)

        bar = make_folded_bar(profiles, bend(radius=4.0, **PLAIN))

        self.assertOneSolid(bar)
        self.assertEqual([(first, second), (second, third)], [(c.PieceA, c.PieceB) for c in bar.Corners])
        self.assertEqual([], self.open_pairs(bar))
        self.assertEqual([settings_values(bend(radius=4.0, **PLAIN))] * 2, [corner_values(c) for c in bar.Corners])

    def test_wrong_number_of_corner_settings_is_refused_before_anything_is_made(self):
        profiles = self.frame()
        count = len(self.doc.Objects)

        with self.assertRaises(ValueError):
            make_folded_bar(profiles, [bend(), bend()])

        self.assertEqual(count, len(self.doc.Objects))

    def test_the_key_and_the_relief_have_no_other_setting(self):
        # S20 (L26, L36): the key is a half circle sized by its diameter only; the relief is always on.
        profiles, bar = self.make_bar(**PLAIN)

        for name in ("NeckWidth", "Relief", "ReliefRadius"):
            self.assertNotIn(name, bar.PropertiesList)
            self.assertNotIn(name, bar.Corners[0].PropertiesList)
        count = len(self.doc.Objects)
        for options in (dict(neck_width=5.0), dict(relief=False), dict(relief_radius=2.0)):
            with self.subTest(options=options):
                with self.assertRaises(TypeError):
                    make_folded_bar(profiles, bend(**PLAIN), **options)
                self.assertEqual(count, len(self.doc.Objects))
                with self.assertRaises(TypeError):
                    unfold(build_chain(profiles), bend(), **options)
                with self.assertRaises(TypeError):
                    check_settings(build_chain(profiles), bend(), **options)

    def test_open_corner_given_sets_the_start_of_the_bar(self):
        bottom, right, top, left = self.frame()

        bar = make_folded_bar([bottom, right, top, left], bend(**PLAIN), open_corner=(bottom, right))

        chain = build_chain([bottom, right, top, left], open_corner=(bottom, right))
        expected = unfold(chain, bend(**PLAIN))
        self.assertOneSolid(bar)
        self.assertEqual([(bottom, right)], self.open_pairs(bar))
        self.assertEqual(
            [(bottom, left), (left, top), (top, right)],
            [(corner.PieceA, corner.PieceB) for corner in self.folded_corners(bar)],
        )
        self.assertEqual([segment.tip for segment in chain.segments], list(bar.Segments))
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)

    def test_changing_a_corner_recomputes_the_bar(self):
        profiles, bar = self.make_bar()
        unfolded = make_unfolded_bar(bar)
        chain = build_chain(profiles)
        corners = self.folded_corners(bar)

        def no_key():
            for corner in corners:
                corner.Key = False

        def radius():
            corners[1].OuterRadius = 7.0

        def clearance():
            corners[2].Clearance = 0.3

        # The key goes first: the bars without it fold faster.
        for change, settings in (
            (no_key, bend(key=False)),
            (radius, [bend(key=False), bend(radius=5.0, key=False), bend(key=False)]),
            (clearance, [bend(key=False), bend(radius=5.0, key=False), bend(clearance=0.3, key=False)]),
        ):
            with self.subTest(change=change.__name__):
                change()
                self.doc.recompute()
                self.assertOneSolid(bar)
                # fold(chain, settings) is fold_bar of this unfold.
                expected = unfold(chain, settings)
                self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
                self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
                self.assertOneSolid(unfolded)
                self.assertSameVolume(expected.shape, unfolded.Shape)

    def test_an_expression_on_a_corner_drives_the_bar(self):
        # S9, S10: the corner properties take expressions.
        profiles, bar = self.make_bar(**PLAIN)
        corner = self.folded_corners(bar)[0]

        corner.setExpression("OuterRadius", "2 * 10 mm")
        self.doc.recompute()

        self.assertAlmostEqual(20.0, corner.OuterRadius.Value, places=9)
        self.assertOneSolid(bar)
        expected = unfold(build_chain(profiles), [bend(radius=18.0, **PLAIN), bend(**PLAIN), bend(**PLAIN)])
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)

    def test_the_open_corner_is_the_one_marked_open(self):
        bottom, right, top, left = profiles = self.frame()
        bar = make_folded_bar(profiles, bend(**PLAIN))
        corners = {frozenset((c.PieceA.Name, c.PieceB.Name)): c for c in bar.Corners}

        corners[frozenset((bottom.Name, left.Name))].Open = False
        corners[frozenset((bottom.Name, right.Name))].Open = True
        self.doc.recompute()

        self.assertOneSolid(bar)
        chain = build_chain(profiles, open_corner=(bottom, right))
        self.assertEqual([segment.tip for segment in chain.segments], list(bar.Segments))
        self.assertAlmostEqual(unfold(chain, bend(**PLAIN)).length, bar.DevelopedLength.Value, places=6)

    def test_corner_identity_survives_a_trim_made_after_the_bar(self):
        # The corner objects link the profiles, not the tips: an end miter made on one later keeps every corner.
        bottom, right, top, left = profiles = self.frame()
        bar = make_folded_bar(profiles, bend(**PLAIN))
        corners = list(bar.Corners)
        miter = make_end_miter_profile(bottom, [left])
        self.doc.recompute()
        bar.touch()
        self.doc.recompute()

        self.assertEqual([miter, right, top, left], list(bar.Segments))
        self.assertEqual(corners, list(bar.Corners))
        self.assertEqual((bottom, right), (corners[0].PieceA, corners[0].PieceB))
        self.assertOneSolid(bar)
        corners[0].OuterRadius = 7.0
        self.doc.recompute()

        self.assertOneSolid(bar)
        chain = build_chain([miter, right, top, left])
        expected = unfold(chain, [bend(radius=5.0, **PLAIN), bend(**PLAIN), bend(**PLAIN)])
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)

    def test_a_corner_removed_from_the_document_leaves_the_bar_in_error(self):
        profiles, bar = self.make_bar(**PLAIN)
        corner = self.folded_corners(bar)[1]

        self.doc.removeObject(corner.Name)
        self.doc.recompute()

        self.assertEqual(3, len(bar.Corners))
        self.assertIn("Invalid", bar.State)
        self.assertEqual(
            "The corner between Profile001 and Profile002 has no Folded Corner object.", bar.getStatusString()
        )

    def test_deleting_the_bar_deletes_its_corners_and_undo_brings_them_back(self):
        self.doc.UndoMode = 1
        profiles, bar = self.make_bar(**PLAIN)
        names = sorted(corner.Name for corner in bar.Corners)
        self.assertEqual(4, len(names))

        self.doc.openTransaction("Delete")
        self.doc.removeObject(bar.Name)
        self.doc.commitTransaction()

        self.assertEqual([], self.corner_objects())
        self.doc.undo()
        self.assertEqual(names, sorted(obj.Name for obj in self.corner_objects()))
        bar = self.doc.getObject(bar.Name)
        self.assertEqual(names, sorted(corner.Name for corner in bar.Corners))

    def test_the_tree_shows_segments_and_corners_under_the_bar(self):
        profiles, bar = self.make_bar(**PLAIN)

        self.assertEqual(profiles + list(bar.Corners), bar.ViewObject.Proxy.claimChildren())
        for corner in bar.Corners:
            self.assertEqual("FoldedBar.svg", os.path.basename(corner.ViewObject.Proxy.getIcon()))

    def test_deleting_the_bar_in_the_gui_shows_its_pieces_again(self):
        profiles, bar = self.make_bar(**PLAIN)

        self.assertTrue(bar.ViewObject.Proxy.onDelete(bar.ViewObject, []))
        self.doc.removeObject(bar.Name)

        self.assertTrue(all(tip.Visibility for tip in profiles))
        self.assertEqual([], self.corner_objects())

    def test_wall_thickness_comes_from_the_profile(self):
        # odd/tasks/folded-corners.md S6, S7: the outer radius less the 2 mm wall of the tube is the inside radius.
        profiles = self.frame()

        bar = make_folded_bar(profiles, CornerSettings(outer_radius=6.0, k_factor=0.33, key=False))

        self.assertOneSolid(bar)
        expected = unfold(build_chain(profiles), bend(radius=4.0, k_factor=0.33, key=False))
        self.assertEqual([4.0] * 3, [corner.inside_radius for corner in expected.corners])
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
        self.assertSameVolume(fold_bar(build_chain(profiles), expected), bar.Shape)

    def test_selection_that_cannot_fold_leaves_the_bar_in_error_with_the_chain_message(self):
        bottom, right, top, left = self.frame()
        with self.assertRaises(ChainError) as raised:
            build_chain([bottom, top])

        bar = make_folded_bar([bottom, top], bend())

        self.assertIn("Invalid", bar.State)
        self.assertEqual(str(raised.exception), bar.getStatusString())
        self.assertEqual([], list(bar.Corners))
        # Nothing folded: the tips stay shown.
        self.assertTrue(all(tip.Visibility for tip in (bottom, right, top, left)))

    def test_settings_that_cannot_unfold_leave_the_bar_in_error_with_the_unfold_message(self):
        profiles, bar = self.make_bar(**PLAIN)
        with self.assertRaises(UnfoldError) as raised:
            unfold(build_chain(profiles), bend(radius=1.0, **PLAIN))

        for corner in bar.Corners:
            corner.OuterRadius = 3.0
        self.doc.recompute()

        self.assertIn("Invalid", bar.State)
        self.assertEqual(str(raised.exception), bar.getStatusString())

    def test_tube_too_short_for_its_corners_leaves_the_bar_in_error(self):
        # S23: the right tube (Profile001) cannot hold two bends of r = 130.
        profiles, bar = self.make_bar(**PLAIN)

        for corner in bar.Corners:
            corner.OuterRadius = 132.0
        self.doc.recompute()

        self.assertIn("Invalid", bar.State)
        self.assertEqual("Profile001 is too short for the radius of its corners.", bar.getStatusString())
        for corner in bar.Corners:
            corner.OuterRadius = 122.0
        self.doc.recompute()
        self.assertOneSolid(bar)

    def test_bar_in_a_moved_part_stays_where_the_frame_is(self):
        part = self.doc.addObject("App::Part", "Part")
        part.Placement = App.Placement(App.Vector(100, 50, 20), App.Rotation(App.Vector(0, 0, 1), 30))
        self.doc.recompute()

        profiles, bar = self.make_bar(container=part, **PLAIN)

        self.assertIn(bar, part.Group)
        expected = fold(build_chain(profiles), bend(**PLAIN))
        found = placed(bar.Shape, container_placement(bar))
        self.assertSameVolume(expected, found)
        self.assertLess((expected.BoundBox.Center - found.BoundBox.Center).Length, LENGTH_TOLERANCE)
        self.assertAlmostEqual(expected.BoundBox.DiagonalLength, found.BoundBox.DiagonalLength, delta=LENGTH_TOLERANCE)

    def test_users_40x40_tube_folds_with_an_outer_radius_of_130(self):
        # S15 (L40): two 40x40x1.5 tubes at 90 degrees bent with the largest inside radius, 38.5 / (1 - cos 45) - 3 =
        # 128.45 mm rounded down to 128.4 (outer radius 129.9): the bend axis lies past the inner wall and the inside
        # of the bend passes 1.3 mm outside the inner corner. Folded and unfolded, the bar is one valid solid; the
        # outer corner is round with radius r + t, the inner corner stays sharp with both inner walls whole.
        r, t, e = 128.4, 1.5, 20.0
        profiles = self.frame(
            edges=(((0, 0, 0), (600, 0, 0)), ((600, 0, 0), (600, 600, 0))), width=2 * e, height=2 * e, thickness=t
        )
        bar = make_folded_bar(profiles, CornerSettings(outer_radius=r + t, k_factor=0.4, key=False))
        unfolded = make_unfolded_bar(bar)
        self.doc.recompute()

        self.assertOneSolid(bar)
        self.assertOneSolid(unfolded)
        developed = 1200 + 2 * (e - r - t) + math.radians(90) * (r + 0.4 * t)
        self.assertAlmostEqual(developed, bar.DevelopedLength.Value, places=6)
        self.assertAlmostEqual(developed, unfolded.Shape.BoundBox.XLength, delta=LENGTH_TOLERANCE)
        shape = bar.Shape
        box = shape.BoundBox
        for value, expected in ((box.XMin, 0), (box.XMax, 600 + e), (box.YMin, -e), (box.YMax, 600)):
            self.assertAlmostEqual(expected, value, delta=LENGTH_TOLERANCE)
        cylinders = [face.Surface.Radius for face in shape.Faces if isinstance(face.Surface, Part.Cylinder)]
        self.assertTrue(any(abs(radius - (r + t)) < LENGTH_TOLERANCE for radius in cylinders), cylinders)
        self.assertTrue(any(abs(radius - r) < LENGTH_TOLERANCE for radius in cylinders), cylinders)

        def inside(x, y, z=0.0):
            return shape.isInside(App.Vector(x, y, z), 1e-6, True)

        # The bend axis: r + t inside both outer faces (x = 620, y = -20); the bent wall on the bisector.
        center = App.Vector(600 + e - r - t, -e + r + t, 0)
        bisector = App.Vector(1, -1, 0).normalize()
        for w in (0.0, e - t / 2, -(e - t / 2)):
            middle = center + bisector * (r + t / 2)
            self.assertTrue(inside(middle.x, middle.y, w), w)
            past = center + bisector * (r + t + 0.1)
            self.assertFalse(inside(past.x, past.y, w), w)
        self.assertFalse(inside(600 + e - 0.1, -e + 0.1))
        # The inner corner (580, 20): material on both inner walls up to it, on both sides of the miter line
        # (x + y = 600), and none past it.
        for w in (0.0, 10.0, -10.0):
            for x, y in ((579.9, 19.9), (580.5, 19.0), (581.0, 19.5), (580.1, 20.1), (560.0, 19.25), (580.75, 40.0)):
                self.assertTrue(inside(x, y, w), (x, y, w))
            self.assertFalse(inside(579.9, 20.1, w), w)


class SegmentsRefreshTest(FoldedBarFixture):
    def drill_right(self, right):
        """A 10 mm hole in the top wall of ``right``, 100 mm along it (as in test_unfolded_geometry)."""
        faces = [
            (index, face)
            for index, face in enumerate(right.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).z > 1 - 1e-9
        ]
        top_face, _ = max(faces, key=lambda item: item[1].CenterOfMass.z)
        vertex = next(
            f"Vertex{index}"
            for index, found in enumerate(right.Shape.Vertexes, 1)
            if found.Point.isEqual(App.Vector(275, 0, 25), 1e-6)
        )
        hole = make_drill_hole((right, (f"Face{top_face}",)), vertex)
        hole.OffsetAlong = 100.0
        hole.OffsetAcross = 25.0
        hole.Diameter = 10.0
        return hole

    def test_hole_drilled_in_a_segment_after_the_bar_is_carried_into_it(self):
        profiles, bar = self.make_bar(**PLAIN)
        volume, length = bar.Shape.Volume, bar.DevelopedLength.Value
        bottom, right, top, left = profiles

        hole = self.drill_right(right)
        bar.touch()
        self.doc.recompute()

        self.assertEqual("Valid", hole.getStatusString())
        self.assertOneSolid(bar)
        # The bar follows the new tip, so it recomputes after it from now on.
        self.assertEqual([bottom, hole, top, left], list(bar.Segments))
        self.assertIn(hole, bar.OutList)
        self.assertFalse(hole.Visibility)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, places=9)
        self.assertAlmostEqual(volume - math.pi * 5**2 * 2.0, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertSameVolume(fold(build_chain([bottom, hole, top, left]), bend(**PLAIN)), bar.Shape)


class SoundShapeTest(FoldedBarFixture):
    """T9 (S2, S4, L14): holes tangent to the edge of a wall or to each other fold into a sound solid, and a bar that
    would fold into a broken one is in error, saying why, instead of drawing it."""

    def drill_tangent_row(self, right):
        """10 mm holes across the top wall of ``right`` at its center: one at the point, one 10 mm back (tangent to it)
        and one 20 mm forward (tangent to the edge of the 50 mm wall)."""
        face = next(
            index
            for index, found in enumerate(right.Shape.Faces, 1)
            if isinstance(found.Surface, Part.Plane) and found.normalAt(0, 0).z > 1 - 1e-9 and found.BoundBox.ZMin > 24
        )
        vertex = next(
            f"Vertex{index}"
            for index, found in enumerate(right.Shape.Vertexes, 1)
            if found.Point.isEqual(App.Vector(275, 0, 25), 1e-6)
        )
        hole = make_drill_hole((right, (f"Face{face}",)), vertex)
        hole.CenterAlong = True
        hole.CenterAcross = True
        hole.Diameter = 10.0
        hole.CutType = "One wall"
        hole.AcrossBackwardCount = 1
        hole.AcrossBackwardPitch = 10.0
        hole.AcrossForwardCount = 1
        hole.AcrossForwardPitch = 20.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())
        self.assertSound(hole.Shape)
        return hole

    def assertSound(self, shape):
        """One valid solid FreeCAD can draw: the geometry check finds nothing and every edge has its curve."""
        self.assertTrue(shape.isValid())
        self.assertEqual(1, len(shape.Solids))
        try:
            shape.check(True)
        except Exception as error:
            self.fail(f"the geometry check fails: {error}")
        for index, edge in enumerate(shape.Edges, 1):
            try:
                edge.Curve
            except Exception as error:
                self.fail(f"Edge{index} has no curve: {error}")

    def test_holes_tangent_to_the_edge_and_to_each_other_unfold_and_fold_into_sound_solids(self):
        bottom, right, top, left = self.frame()
        plain = unfold(build_chain([bottom, right, top, left]), bend(**PLAIN))
        hole = self.drill_tangent_row(right)
        drilled = right.Shape.Volume - hole.Shape.Volume
        chain = build_chain([bottom, hole, top, left])

        unfolded = unfold(chain, bend(**PLAIN))
        folded = fold_bar(chain, unfolded)

        self.assertSound(unfolded.shape)
        self.assertSound(folded)
        self.assertAlmostEqual(plain.shape.Volume - drilled, unfolded.shape.Volume, delta=VOLUME_TOLERANCE)

    def test_a_bar_made_after_tangent_holes_and_its_unfolded_bar_are_sound(self):
        bottom, right, top, left = self.frame()
        hole = self.drill_tangent_row(right)

        bar = make_folded_bar([bottom, hole, top, left], bend(**PLAIN))
        unfolded = make_unfolded_bar(bar)

        self.assertOneSolid(bar)
        self.assertSound(bar.Shape)
        self.assertOneSolid(unfolded)
        self.assertSound(unfolded.Shape)

    def test_a_fold_that_breaks_the_solid_leaves_the_bar_in_error_and_its_shape_as_before(self):
        profiles, bar = self.make_bar(**PLAIN)
        volume = bar.Shape.Volume

        with mock.patch.object(folded_bar, "fold_bar", return_value=open_box()):
            bar.touch()
            self.doc.recompute()

        self.assertIn("Invalid", bar.State)
        self.assertEqual(BROKEN_MESSAGE.format(bar.Label), bar.getStatusString())
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertTrue(bar.Shape.isValid())
        for tip in profiles:
            self.assertFalse(tip.Visibility, tip.Label)
        # Folded again, it is sound.
        bar.touch()
        self.doc.recompute()
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_an_unfold_that_breaks_the_solid_leaves_the_unfolded_bar_in_error(self):
        _, bar = self.make_bar(**PLAIN)
        unfolded = make_unfolded_bar(bar)
        volume = unfolded.Shape.Volume
        broken = unfold(bar_chain(bar), bend(**PLAIN))
        broken.shape = open_box()

        with mock.patch.object(bar.Proxy, "unfolded_bar", return_value=broken):
            unfolded.touch()
            self.doc.recompute()

        self.assertIn("Invalid", unfolded.State)
        self.assertEqual(BROKEN_MESSAGE.format(bar.Label), unfolded.getStatusString())
        self.assertAlmostEqual(volume, unfolded.Shape.Volume, delta=VOLUME_TOLERANCE)


class UnfoldedBarObjectTest(FoldedBarFixture):
    def test_unfolded_bar_is_the_straight_bar_from_x_zero(self):
        profiles, bar = self.make_bar(**PLAIN)

        unfolded = make_unfolded_bar(bar)

        expected = unfold(build_chain(profiles), bend(**PLAIN))
        self.assertOneSolid(unfolded)
        self.assertEqual(bar, unfolded.FoldedBar)
        self.assertSameVolume(expected.shape, unfolded.Shape)
        box = unfolded.Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(bar.DevelopedLength.Value, box.XLength, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(50.0, box.YLength, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(50.0, box.ZLength, delta=LENGTH_TOLERANCE)

    def test_unfolded_bar_takes_the_label_of_its_folded_bar(self):
        _, bar = self.make_bar(**PLAIN)
        bar.Label = "LateralDerecho"

        unfolded = make_unfolded_bar(bar)

        self.assertEqual("LateralDerecho_Unfolded", unfolded.Label)
        self.assertEqual("LateralDerecho", bar.Label)

    def test_renaming_the_folded_bar_renames_an_unfolded_bar_that_keeps_its_given_label(self):
        _, bar = self.make_bar(**PLAIN)
        bar.Label = "Marco1"
        unfolded = make_unfolded_bar(bar)

        bar.Label = "MarcoRenombrado"

        self.assertEqual("MarcoRenombrado_Unfolded", unfolded.Label)

    def test_renaming_the_folded_bar_keeps_an_unfolded_bar_renamed_by_hand(self):
        _, bar = self.make_bar(**PLAIN)
        bar.Label = "Marco1"
        unfolded = make_unfolded_bar(bar)
        unfolded.Label = "Pieza A"

        bar.Label = "MarcoRenombrado"

        self.assertEqual("Pieza A", unfolded.Label)
        self.assertEqual("MarcoRenombrado", bar.Label)

    def test_step_export_reads_back_one_solid_of_the_same_volume_and_length(self):
        import Import

        _, bar = self.make_bar(**PLAIN)
        unfolded = make_unfolded_bar(bar)
        folder = tempfile.mkdtemp(prefix="mpf_folded_bar_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "UnfoldedBar.step")

        Import.export([unfolded], path)

        shape = Part.read(path)
        self.assertEqual(1, len(shape.Solids))
        solid = shape.Solids[0]
        self.assertTrue(solid.isValid())
        self.assertAlmostEqual(unfolded.Shape.Volume, solid.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(0.0, solid.BoundBox.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(bar.DevelopedLength.Value, solid.BoundBox.XLength, delta=LENGTH_TOLERANCE)


class RestoreTest(FoldedBarFixture):
    def test_saved_document_opens_with_both_bars_valid_and_the_same_shapes(self):
        profiles, bar = self.make_bar(clearance=0.2, **PLAIN)
        unfolded = make_unfolded_bar(bar)
        saved = {obj.Name: (obj.Shape.Volume, obj.Shape.BoundBox.DiagonalLength) for obj in (bar, unfolded)}
        developed = bar.DevelopedLength.Value
        folder = tempfile.mkdtemp(prefix="mpf_folded_bar_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        names = (bar.Name, unfolded.Name)
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)

        self.doc = App.openDocument(path)

        bar, unfolded = (self.doc.getObject(name) for name in names)
        self.assertAlmostEqual(developed, bar.DevelopedLength.Value, places=9)
        self.assertEqual([0.2] * 4, [round(corner.Clearance.Value, 9) for corner in bar.Corners])
        self.assertEqual(4, len(bar.Segments))
        for recomputed in (False, True):
            if recomputed:
                bar.touch()
                unfolded.touch()
                self.doc.recompute()
                # Opened offscreen, every object shows (a hidden plain profile too): the recompute hides the tips.
                for tip in bar.Segments:
                    self.assertFalse(tip.Visibility, tip.Label)
            with self.subTest(recomputed=recomputed):
                for obj in (bar, unfolded):
                    self.assertOneSolid(obj)
                    volume, diagonal = saved[obj.Name]
                    self.assertAlmostEqual(volume, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
                    self.assertAlmostEqual(diagonal, obj.Shape.BoundBox.DiagonalLength, delta=LENGTH_TOLERANCE)

    def test_unfolded_bar_recomputes_alone_after_opening(self):
        _, bar = self.make_bar(**PLAIN)
        unfolded = make_unfolded_bar(bar)
        volume = unfolded.Shape.Volume
        folder = tempfile.mkdtemp(prefix="mpf_folded_bar_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        name = unfolded.Name
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        unfolded = self.doc.getObject(name)

        unfolded.touch()
        self.doc.recompute()

        self.assertOneSolid(unfolded)
        self.assertAlmostEqual(volume, unfolded.Shape.Volume, delta=VOLUME_TOLERANCE)


class BomTest(FoldedBarFixture):
    def rows(self, *objects):
        data, links = [], []
        for obj in objects:
            traverse_assembly(data, links, obj)
        return data, links

    def number(self, *containers):
        profiles, links = [], []
        for obj in containers:
            get_profiles_and_links_from_object(profiles, links, obj)
        doc_profiles, doc_links = get_profiles_and_links_from_document()
        populate_ids(
            profiles, links, doc_profiles, doc_links, "all_numbers", False, True, False, False, "fill_document"
        )
        return profiles

    def assertOnePiece(self, bar, rows, pid=""):
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(
            (pid, bar.Label, "Square Hollow", "50x50x2", "Steel", f"{bar.DevelopedLength.Value:.1f}", "1"),
            (row["ID"], row["label"], row["family"], row["size_name"], row["material"], row["length"], row["quantity"]),
        )

    def test_folded_bar_is_one_piece_of_its_developed_length_in_a_part(self):
        part = self.doc.addObject("App::Part", "Part")
        profiles, bar = self.make_bar(container=part, **PLAIN)
        make_unfolded_bar(bar)

        rows, links = self.rows(part)

        self.assertOnePiece(bar, rows)
        self.assertEqual([], links)
        self.assertEqual(("", "", ""), (rows[0]["cut_angle_1"], rows[0]["cut_angle_2"], rows[0]["ends"]))
        self.assertEqual("Yes", rows[0]["cutout"])
        self.assertAlmostEqual(bar.DevelopedLength.Value / 1000, float(rows[0]["approx_weight"]), places=6)

    def test_folded_bar_is_one_piece_outside_a_part_too(self):
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        profiles, bar = self.make_bar(container=group, **PLAIN)
        unfolded = make_unfolded_bar(bar)
        group.addObject(unfolded)

        for objects in ((group,), (bar,), (bar, unfolded, *profiles)):
            with self.subTest(objects=[obj.Label for obj in objects]):
                rows, links = self.rows(*objects)
                self.assertOnePiece(bar, rows)
                self.assertEqual([], links)

    def test_populate_ids_numbers_the_bar_as_one_piece(self):
        part = self.doc.addObject("App::Part", "Part")
        profiles, bar = self.make_bar(container=part, **PLAIN)

        self.assertEqual([bar], self.number(part))

        self.assertEqual("1", bar.PID)
        self.assertEqual(["", "", "", ""], [profile.PID for profile in profiles])
        self.assertEqual([bar], get_profiles_and_links_from_document()[0])
        bar.touch()
        self.doc.recompute()
        self.assertEqual("1", bar.PID)
        self.assertOnePiece(bar, self.rows(part)[0], pid="1")

    def test_populate_ids_groups_a_bar_in_error(self):
        bottom, right, top, left = self.frame()
        bar = make_folded_bar([bottom, top], bend())
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        group.addObject(bar)

        self.number(group)

        self.assertEqual("1", bar.PID)

    def test_cut_list_lists_the_bar_once_with_its_id_and_developed_length(self):
        part = self.doc.addObject("App::Part", "Part")
        _, bar = self.make_bar(container=part, **PLAIN)
        self.number(part)
        rows, _ = self.rows(part)
        sheet = self.doc.addObject("Spreadsheet::Sheet", "CutList")

        parts = [CutPart(row["label"], float(row["length"]), KERF, row) for row in rows]
        make_cut_list({"Steel_Square Hollow_50x50x2": best_fit_decreasing(6000.0, parts)}, spreadsheet=sheet)
        # The sheet alone: numbering touched the bar, whose recompute changes nothing here.
        sheet.recompute()

        self.assertEqual(
            ["0", "1", f"{bar.DevelopedLength.Value:.1f}", "1"],
            [sheet.getContents(f"{column}2").removeprefix("'") for column in "BCDH"],
        )
        self.assertEqual("", sheet.getContents("C3"))


class PlainFrameBomTest(FoldedBarFixture):
    """Frames without a folded bar list as before."""

    def test_plain_frame_lists_each_profile_with_its_length(self):
        profiles = self.frame()
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        group.addObjects(profiles)
        profiles[1].Visibility = False

        data, links = [], []
        traverse_assembly(data, links, group)

        # Outside a Part a hidden profile is listed too.
        self.assertEqual([profile.Label for profile in profiles], [row["label"] for row in data])
        self.assertEqual([f"{profile.Length.Value:.1f}" for profile in profiles], [row["length"] for row in data])
        self.assertEqual([], links)
        found, _ = [], []
        get_profiles_and_links_from_object(found, _, group)
        self.assertEqual(profiles, found)

    def test_plain_frame_in_a_part_skips_hidden_profiles(self):
        profiles = self.frame()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([profiles[0].AttachmentSupport[0][0], *profiles])
        profiles[1].Visibility = False

        data, links = [], []
        traverse_assembly(data, links, part)

        shown = [profiles[0], *profiles[2:]]
        self.assertEqual([profile.Label for profile in shown], [row["label"] for row in data])
        found, _ = [], []
        get_profiles_and_links_from_object(found, _, part)
        self.assertEqual(shown, found)
        self.assertEqual(profiles, get_profiles_and_links_from_document()[0])


class StockWarningTest(FoldedBarFixture):
    def setUp(self):
        super().setUp()
        param = get_param_group()
        had = STOCK_PARAM in param.GetFloats()
        previous = param.GetFloat(STOCK_PARAM, 6000.0)
        self.addCleanup(lambda: param.SetFloat(STOCK_PARAM, previous) if had else param.RemFloat(STOCK_PARAM))

    def warnings(self, action):
        found = []
        with mock.patch.object(App.Console, "PrintWarning", side_effect=found.append):
            action()
        return found

    def test_bar_longer_than_the_stock_warns_on_recompute_and_in_the_bom(self):
        _, bar = self.make_bar(**PLAIN)
        get_param_group().SetFloat(STOCK_PARAM, 500.0)
        message = (
            f"{bar.Label}: its developed length ({bar.DevelopedLength.Value:.1f} mm) is longer than the stock "
            "length of the cut list (500.0 mm).\n"
        )

        def recompute():
            bar.touch()
            self.doc.recompute()

        self.assertEqual([message], self.warnings(recompute))
        self.assertEqual([message], self.warnings(lambda: traverse_assembly([], [], bar)))

    def test_bar_that_fits_the_stock_does_not_warn(self):
        _, bar = self.make_bar(**PLAIN)
        get_param_group().SetFloat(STOCK_PARAM, 6000.0)

        def recompute():
            bar.touch()
            self.doc.recompute()

        self.assertEqual([], self.warnings(recompute))
        self.assertEqual([], self.warnings(lambda: traverse_assembly([], [], bar)))


if __name__ == "__main__":
    unittest.main()

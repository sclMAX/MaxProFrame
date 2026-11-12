"""FoldedBar and UnfoldedBar objects (odd/tasks/folded-miter.md, T5: S2 S3 S4 S13 S19, with S14 S17 S20 as properties).

A closed rectangle of four tubes with three folded corners and an open one becomes one FoldedBar: one valid solid
where the frame was drawn, recomputed when its bend settings change, saved and opened again with the document. It
hides the segment tips and is one piece for the BOM, the cut list and the IDs, of its developed length. The
UnfoldedBar is the straight bar from X = 0 that FreeCAD's own STEP export writes.
"""

import math
import os
import shutil
import tempfile
import unittest
from unittest import mock

import FreeCAD as App
import Part
from test_unfolded_geometry import PLAIN, STEEL, UnfoldFixture

from freecad.maxproframe._utils import get_profiles_and_links_from_document, get_profiles_and_links_from_object
from freecad.maxproframe.bend_config import BendConfiguration
from freecad.maxproframe.best_fit import CutPart, best_fit_decreasing
from freecad.maxproframe.create_bom import make_cut_list, traverse_assembly
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.folded_bar import check_settings, make_folded_bar, make_unfolded_bar
from freecad.maxproframe.folded_chain import ChainError, build_chain
from freecad.maxproframe.folded_geometry import fold, fold_bar
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.profile_pattern import container_placement, placed
from freecad.maxproframe.unfolded_geometry import UnfoldError, unfold

VOLUME_TOLERANCE = 1e-3
LENGTH_TOLERANCE = 1e-4
STOCK_PARAM = "Stock Length"
KERF = 1.0


class FoldedBarFixture(UnfoldFixture):
    def make_bar(self, container=None, **options):
        """The rectangle frame (in ``container`` when given) folded at three corners, open at the first one."""
        profiles = self.frame()
        if container is not None:
            container.addObjects([profiles[0].AttachmentSupport[0][0], *profiles])
        bar = make_folded_bar(profiles, STEEL, **options)
        self.assertEqual("Valid", bar.getStatusString())
        return profiles, bar

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
        # fold(chain, STEEL) is fold_bar of this unfold.
        expected = unfold(chain, STEEL)
        self.assertOneSolid(bar)
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
        self.assertEqual(profiles, list(bar.Segments))
        self.assertEqual([], list(bar.OpenCorner))
        for tip in profiles:
            self.assertFalse(tip.Visibility, tip.Label)
        self.assertTrue(bar.Visibility)
        # A copy of the configuration: the document does not need the configurations file of this computer.
        self.assertEqual(
            ("Steel 50x50x2", "Steel", 2.0, 3.0, 0.4),
            (bar.BendConfiguration, bar.BendMaterial, bar.WallThickness.Value, bar.InsideRadius.Value, bar.KFactor),
        )
        self.assertEqual([0.0, 0.0, 0.0], list(bar.CornerRadii))
        self.assertEqual((0.0, True, 0.0), (bar.Clearance.Value, bar.Key, bar.KeyDiameter.Value))
        self.assertEqual(1, bar.getEditorMode("DevelopedLength").count("ReadOnly"))
        # Like a profile, for the BOM and the cut list.
        self.assertEqual(("Square Hollow", "50x50x2", "Steel", ""), (bar.Family, bar.SizeName, bar.Material, bar.PID))

    def test_the_key_has_no_neck_setting(self):
        # S20 (L26): the key is a half circle, sized by its diameter only.
        profiles, bar = self.make_bar(key=False)

        self.assertNotIn("NeckWidth", bar.PropertiesList)
        with self.assertRaises(TypeError) as raised:
            make_folded_bar(profiles, STEEL, neck_width=5.0)
        self.assertEqual("Unknown folded bar options: neck_width", str(raised.exception))
        with self.assertRaises(TypeError):
            unfold(build_chain(profiles), STEEL, neck_width=5.0)

    def test_the_relief_has_no_setting(self):
        # S8, S20 (L36): the relief is always on, its radius the inside radius of each corner.
        profiles, bar = self.make_bar(key=False)

        self.assertNotIn("Relief", bar.PropertiesList)
        self.assertNotIn("ReliefRadius", bar.PropertiesList)
        count = len(self.doc.Objects)
        for options, message in (
            (dict(relief=False), "Unknown folded bar options: relief"),
            (dict(relief_radius=2.0), "Unknown folded bar options: relief_radius"),
            (dict(relief=True, relief_radius=2.0), "Unknown folded bar options: relief, relief_radius"),
        ):
            with self.subTest(options=options):
                with self.assertRaises(TypeError) as raised:
                    make_folded_bar(profiles, STEEL, **options)
                self.assertEqual(message, str(raised.exception))
                self.assertEqual(count, len(self.doc.Objects))
                with self.assertRaises(TypeError):
                    unfold(build_chain(profiles), STEEL, **options)
                with self.assertRaises(TypeError):
                    check_settings(build_chain(profiles), STEEL, **options)

    def test_open_corner_given_sets_the_start_of_the_bar(self):
        bottom, right, top, left = self.frame()

        bar = make_folded_bar([bottom, right, top, left], STEEL, open_corner=(bottom, right), **PLAIN)

        chain = build_chain([bottom, right, top, left], open_corner=(bottom, right))
        expected = unfold(chain, STEEL, **PLAIN)
        self.assertOneSolid(bar)
        self.assertEqual([bottom, right], list(bar.OpenCorner))
        self.assertEqual([segment.tip for segment in chain.segments], list(bar.Segments))
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)

    def test_options_set_the_bar_properties(self):
        profiles, bar = self.make_bar(radius=4.0, corner_radii={1: 5.0}, clearance=0.2, key=False)

        chain = build_chain(profiles)
        self.assertOneSolid(bar)
        self.assertEqual(4.0, bar.InsideRadius.Value)
        self.assertEqual([0.0, 5.0, 0.0], list(bar.CornerRadii))
        self.assertAlmostEqual(0.2, bar.Clearance.Value, places=9)
        self.assertFalse(bar.Key)
        options = dict(radius=4.0, corner_radii={1: 5.0}, clearance=0.2, key=False)
        expected = unfold(chain, STEEL, **options)
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)

    def test_changing_a_bend_property_recomputes_the_bar(self):
        profiles, bar = self.make_bar()
        unfolded = make_unfolded_bar(bar)
        chain = build_chain(profiles)

        # The key goes first: the bars without it fold faster.
        for prop, value, options in (
            ("Key", False, dict(key=False)),
            ("InsideRadius", 4.0, dict(radius=4.0, key=False)),
            ("CornerRadii", [0.0, 5.0, 0.0], dict(radius=4.0, corner_radii={1: 5.0}, key=False)),
        ):
            with self.subTest(prop=prop):
                setattr(bar, prop, value)
                self.doc.recompute()
                self.assertOneSolid(bar)
                # fold(chain, STEEL, **options) is fold_bar of this unfold.
                expected = unfold(chain, STEEL, **options)
                self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
                self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
                self.assertOneSolid(unfolded)
                self.assertSameVolume(expected.shape, unfolded.Shape)

    def test_selection_that_cannot_fold_leaves_the_bar_in_error_with_the_chain_message(self):
        bottom, right, top, left = self.frame()
        with self.assertRaises(ChainError) as raised:
            build_chain([bottom, top])

        bar = make_folded_bar([bottom, top], STEEL)

        self.assertIn("Invalid", bar.State)
        self.assertEqual(str(raised.exception), bar.getStatusString())
        # Nothing folded: the tips stay shown.
        self.assertTrue(all(tip.Visibility for tip in (bottom, right, top, left)))

    def test_settings_that_cannot_unfold_leave_the_bar_in_error_with_the_unfold_message(self):
        profiles, bar = self.make_bar(**PLAIN)
        with self.assertRaises(UnfoldError) as raised:
            unfold(build_chain(profiles), STEEL, radius=1.0, **PLAIN)

        bar.InsideRadius = 1.0
        self.doc.recompute()

        self.assertIn("Invalid", bar.State)
        self.assertEqual(str(raised.exception), bar.getStatusString())

    def test_bar_in_a_moved_part_stays_where_the_frame_is(self):
        part = self.doc.addObject("App::Part", "Part")
        part.Placement = App.Placement(App.Vector(100, 50, 20), App.Rotation(App.Vector(0, 0, 1), 30))
        self.doc.recompute()

        profiles, bar = self.make_bar(container=part, **PLAIN)

        self.assertIn(bar, part.Group)
        expected = fold(build_chain(profiles), STEEL, **PLAIN)
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
        configuration = BendConfiguration("Steel 40x40x1.5", "Steel", t, r, 0.4)

        bar = make_folded_bar(profiles, configuration, key=False)
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
        self.assertSameVolume(fold(build_chain([bottom, hole, top, left]), STEEL, **PLAIN), bar.Shape)


class UnfoldedBarObjectTest(FoldedBarFixture):
    def test_unfolded_bar_is_the_straight_bar_from_x_zero(self):
        profiles, bar = self.make_bar(**PLAIN)

        unfolded = make_unfolded_bar(bar)

        expected = unfold(build_chain(profiles), STEEL, **PLAIN)
        self.assertOneSolid(unfolded)
        self.assertEqual(bar, unfolded.FoldedBar)
        self.assertSameVolume(expected.shape, unfolded.Shape)
        box = unfolded.Shape.BoundBox
        self.assertAlmostEqual(0.0, box.XMin, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(bar.DevelopedLength.Value, box.XLength, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(50.0, box.YLength, delta=LENGTH_TOLERANCE)
        self.assertAlmostEqual(50.0, box.ZLength, delta=LENGTH_TOLERANCE)

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
        self.assertAlmostEqual(0.2, bar.Clearance.Value, places=9)
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
        bar = make_folded_bar([bottom, top], STEEL)
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

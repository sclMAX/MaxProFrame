"""Profile Pattern: Links to a piece repeated along a straight edge, by count and pitch or between two faces."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from test_end_miter_geometry import CENTER, MiterFixture

from freecad.maxproframe._utils import is_pattern_link
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.profile_pattern import make_profile_pattern
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# The slat runs along Y at x = 100: 50 mm wide along X, the direction of the frame edge.
SLAT_X = 100.0
X = App.Vector(1, 0, 0)
Y = App.Vector(0, 1, 0)


def global_shape(obj):
    """The shape of ``obj`` (a Link too) in document coordinates, through the Parts holding it."""
    shape = Part.getShape(obj).copy()
    group = obj.getParentGeoFeatureGroup()
    if group is not None:
        shape.Placement = group.getGlobalPlacement().multiply(shape.Placement)
    return shape


def center(obj):
    return global_shape(obj).BoundBox.Center


def face_named(obj, normal, at):
    """Name of the planar face of ``obj`` square to ``normal`` at ``at`` along it."""
    for index, face in enumerate(obj.Shape.Faces, start=1):
        if not isinstance(face.Surface, Part.Plane):
            continue
        if face.normalAt(0, 0).cross(normal).Length < 1e-9 and abs(face.CenterOfMass.dot(normal) - at) < 1e-6:
            return f"Face{index}"
    raise AssertionError(f"no face of {obj.Label} at {at}")


def edge_along(obj, axis):
    """Name of the first straight edge of ``obj`` along ``axis``."""
    for index, edge in enumerate(obj.Shape.Edges, start=1):
        if isinstance(edge.Curve, Part.Line) and edge.Curve.Direction.cross(axis).Length < 1e-9:
            return f"Edge{index}"
    raise AssertionError(f"no edge of {obj.Label} along {axis}")


class PatternFixture(MiterFixture):
    def setUp(self):
        super().setUp()
        # The frame edge the pattern follows, along +X.
        self.frame = self.make_sketch(((0, 0, 0), (1000, 0, 0)))
        self.slat = self.make_profile(self.make_sketch(((SLAT_X, 0, 0), (SLAT_X, 600, 0))), "Edge1", **CENTER)
        self.slat.PID = "7"
        self.doc.recompute()

    def box(self, name, x):
        """A 100 mm box from ``x`` along X: its faces at x and x + 100 limit a Between faces pattern."""
        box = self.doc.addObject("Part::Box", name)
        box.Length, box.Width, box.Height = 100, 600, 50
        box.Placement.Base = App.Vector(x, 0, -25)
        self.doc.recompute()
        return box

    def walls(self):
        """(left, right) faces at x = 0 and x = 1000: the free length between them is 1000."""
        left, right = self.box("Left", -100), self.box("Right", 1000)
        return (left, face_named(left, X, 0)), (right, face_named(right, X, 1000))

    def pattern(self, piece=None, edge=None, **values):
        obj = make_profile_pattern(piece or self.slat, edge or (self.frame, "Edge1"), **values)
        self.doc.recompute()
        return obj

    def copy_centers(self, obj, axis=X):
        return sorted(round(center(link).dot(axis), 6) for link in obj.Copies)

    def assert_valid(self, obj):
        self.assertTrue(obj.isValid(), obj.getStatusString())

    def links(self):
        return sorted(o.Name for o in self.doc.Objects if o.TypeId == "App::Link")


class TestCountAndPitch(PatternFixture):
    def test_the_copies_follow_the_edge_at_the_pitch_center_to_center(self):
        obj = self.pattern(count=3, pitch=150.0)
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [250.0, 400.0, 550.0])
        for link in obj.Copies:
            self.assertEqual(link.TypeId, "App::Link")
            self.assertEqual(link.LinkedObject, self.slat)
            # Only moved along the edge: the same Y and Z as the original.
            self.assertTrue(center(link).sub(center(self.slat)).cross(X).Length < 1e-6)
        self.assertEqual(round(center(self.slat).x, 6), SLAT_X)

    def test_inverted_copies_go_against_the_edge(self):
        obj = self.pattern(count=3, pitch=150.0, sense="Inverted")
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [-350.0, -200.0, -50.0])

    def test_symmetric_puts_the_count_on_each_side_of_the_original(self):
        obj = self.pattern(count=2, pitch=100.0, sense="Symmetric")
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [-100.0, 0.0, 200.0, 300.0])

    def test_editing_the_count_adds_and_removes_links_and_the_pitch_moves_them(self):
        obj = self.pattern(count=3, pitch=100.0)
        before = set(self.links())
        obj.Count = 5
        self.doc.recompute()
        self.assertEqual(len(obj.Copies), 5)
        self.assertEqual(len(self.links()), 5)
        self.assertTrue(before < set(self.links()))
        obj.Count = 2
        obj.Pitch = 200.0
        self.doc.recompute()
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [300.0, 500.0])
        # The links left over are gone from the document, not only from the pattern.
        self.assertEqual(sorted(link.Name for link in obj.Copies), self.links())
        self.assertEqual(self.touched(), [])

    def touched(self):
        return [o.Name for o in self.doc.Objects if "Touched" in o.State]

    def test_a_change_on_the_original_shows_on_every_copy(self):
        obj = self.pattern(count=2, pitch=100.0)
        self.assertEqual(len(obj.Copies), 2)
        self.slat.OffsetB = 150.0
        self.doc.recompute()
        length = global_shape(self.slat).BoundBox.YLength
        self.assertAlmostEqual(length, 800.0)
        for link in obj.Copies:
            self.assertAlmostEqual(global_shape(link).BoundBox.YLength, length)
            self.assertAlmostEqual(global_shape(link).Volume, self.slat.Shape.Volume)

    def test_the_copies_carry_the_id_of_the_original(self):
        obj = self.pattern(count=2, pitch=100.0)
        self.assertEqual([link.PID for link in obj.Copies], ["7", "7"])
        self.slat.PID = "12"
        self.doc.recompute()
        self.assertEqual([link.PID for link in obj.Copies], ["12", "12"])

    def test_deleting_the_pattern_removes_its_links_and_keeps_the_original(self):
        obj = self.pattern(count=3, pitch=100.0)
        self.assertEqual(len(self.links()), 3)
        self.doc.removeObject(obj.Name)
        self.doc.recompute()
        self.assertEqual(self.links(), [])
        self.assertIsNotNone(self.doc.getObject(self.slat.Name))
        self.assertEqual(round(center(self.slat).x, 6), SLAT_X)

    def test_a_drill_hole_is_repeated_with_its_hole(self):
        top = face_named(self.slat, App.Vector(0, 0, 1), 25)
        point = self.slat.Shape.getElement(top).Vertexes[0].Point
        vertex = next(
            f"Vertex{i}" for i, v in enumerate(self.slat.Shape.Vertexes, start=1) if v.Point.isEqual(point, 1e-6)
        )
        hole = make_drill_hole((self.slat, (top,)), vertex)
        hole.OffsetAlong, hole.OffsetAcross = 100.0, 25.0
        self.doc.recompute()
        self.assert_valid(hole)
        self.assertLess(hole.Shape.Volume, self.slat.Shape.Volume - 1.0)
        obj = self.pattern(piece=hole, count=2, pitch=100.0)
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0])
        for link in obj.Copies:
            self.assertEqual(link.LinkedObject, hole)
            self.assertAlmostEqual(global_shape(link).Volume, hole.Shape.Volume)

    def test_a_saved_pattern_opens_and_still_follows_its_values(self):
        obj = self.pattern(count=2, pitch=100.0)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        saved, copy = os.path.join(folder, "pattern.FCStd"), os.path.join(folder, "opened.FCStd")
        self.doc.saveAs(saved)
        # Opened from another file: a document of its own, read back from disk.
        shutil.copy(saved, copy)
        doc = App.openDocument(copy)
        self.addCleanup(App.closeDocument, doc.Name)
        obj = doc.getObject(obj.Name)
        self.assertTrue(all(is_pattern_link(link) for link in obj.Copies))
        obj.Count = 3
        doc.recompute()
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])

    def test_a_piece_in_a_moved_part_is_repeated_along_the_global_edge(self):
        part = self.doc.addObject("App::Part", "Table")
        part.addObjects([self.slat, *self.slat.OutList])
        part.Placement = App.Placement(App.Vector(0, 0, 500), App.Rotation(Y, 90))
        self.doc.recompute()
        start = center(self.slat)
        obj = self.pattern(count=2, pitch=100.0)
        self.assert_valid(obj)
        self.assertEqual(obj.getParentGeoFeatureGroup(), part)
        for link in obj.Copies:
            self.assertEqual(link.getParentGeoFeatureGroup(), part)
        moves = sorted(round(center(link).sub(start).x, 6) for link in obj.Copies)
        self.assertEqual(moves, [100.0, 200.0])
        for link in obj.Copies:
            self.assertTrue(center(link).sub(start).cross(X).Length < 1e-6)


class TestBetweenFaces(PatternFixture):
    def test_every_piece_the_original_too_sits_between_the_faces_with_equal_gaps(self):
        obj = self.pattern(mode="Between faces", count=5, faces=self.walls())
        self.assert_valid(obj)
        self.assertEqual(len(obj.Copies), 4)
        # 5 pieces 50 wide in 1000: 6 gaps of 125, the original in the slot next to the first face.
        self.assertAlmostEqual(center(self.slat).x, 150.0)
        self.assertEqual(self.copy_centers(obj), [325.0, 500.0, 675.0, 850.0])
        self.assertAlmostEqual(obj.Gap.Value, 125.0)
        self.assertAlmostEqual(obj.Spacing.Value, 175.0)
        # Moved by its own offsets: still on its path.
        self.assertEqual(self.slat.MapMode, "NormalToEdge")
        self.assertAlmostEqual(abs(self.slat.OffsetX.Value) + abs(self.slat.OffsetY.Value), 50.0)
        self.assertEqual(self.touched(), [])

    def touched(self):
        return [o.Name for o in self.doc.Objects if "Touched" in o.State]

    def test_the_original_takes_the_slot_next_to_the_first_face_picked(self):
        left, right = self.walls()
        obj = self.pattern(mode="Between faces", count=5, faces=(right, left))
        self.assert_valid(obj)
        self.assertAlmostEqual(center(self.slat).x, 850.0)
        self.assertEqual(self.copy_centers(obj), [150.0, 325.0, 500.0, 675.0])

    def test_the_gaps_are_measured_between_the_pieces_not_their_centers(self):
        # A wider piece: 80 along X. 4 pieces in 1000 leave 5 gaps of (1000 - 320) / 5 = 136.
        self.slat.ProfileWidth = 80.0
        self.doc.recompute()
        obj = self.pattern(mode="Between faces", count=4, faces=self.walls())
        self.assert_valid(obj)
        pieces = [global_shape(self.slat).BoundBox] + [global_shape(link).BoundBox for link in obj.Copies]
        bounds = sorted((round(box.XMin, 6), round(box.XMax, 6)) for box in pieces)
        self.assertEqual(bounds, [(136.0, 216.0), (352.0, 432.0), (568.0, 648.0), (784.0, 864.0)])

    def test_a_count_change_moves_every_piece_again(self):
        obj = self.pattern(mode="Between faces", count=5, faces=self.walls())
        obj.Count = 3
        self.doc.recompute()
        self.assert_valid(obj)
        # 3 pieces: 4 gaps of (1000 - 150) / 4 = 212.5.
        self.assertAlmostEqual(center(self.slat).x, 237.5)
        self.assertEqual(self.copy_centers(obj), [500.0, 762.5])

    def test_a_trimmed_piece_moves_by_the_offsets_of_its_profile(self):
        stop = self.box("Stop", -100)
        stop.Placement.Base = App.Vector(-100, 500, -25)
        stop.Length, stop.Width = 1200, 100
        self.doc.recompute()
        trim = make_extend_cut_profile(self.slat, (stop, (face_named(stop, Y, 500),)))
        self.doc.recompute()
        self.assert_valid(trim)
        obj = self.pattern(piece=trim, mode="Between faces", count=5, faces=self.walls())
        self.assert_valid(obj)
        self.assertAlmostEqual(center(trim).x, 150.0)
        self.assertEqual(self.copy_centers(obj), [325.0, 500.0, 675.0, 850.0])
        for link in obj.Copies:
            self.assertEqual(link.LinkedObject, trim)
            self.assertAlmostEqual(global_shape(link).BoundBox.YMax, 500.0)

    def test_a_direction_along_the_piece_is_explained_and_moves_nothing(self):
        along = self.make_sketch(((0, 0, 0), (0, 1000, 0)))
        obj = self.pattern(edge=(along, "Edge1"), mode="Between faces", count=3, faces=self.walls())
        self.assertFalse(obj.isValid())
        self.assertIn("across", obj.getStatusString())
        self.assertEqual(round(center(self.slat).x, 6), SLAT_X)
        self.assertEqual((self.slat.OffsetX.Value, self.slat.OffsetY.Value), (0.0, 0.0))

    def test_too_many_pieces_for_the_room_is_explained(self):
        obj = self.pattern(mode="Between faces", count=30, faces=self.walls())
        self.assertFalse(obj.isValid())
        self.assertIn("do not fit", obj.getStatusString())
        self.assertEqual(round(center(self.slat).x, 6), SLAT_X)


class TestPatternContainer(MiterFixture):
    def setUp(self):
        super().setUp()
        # A side frame profile in its own Part, and a back profile trimmed against it in another Part.
        self.side = self.doc.addObject("App::Part", "Side")
        self.back = self.doc.addObject("App::Part", "Back")
        side_path = self.make_sketch(((0, 0, 0), (0, 200, 0)))
        back_path = self.make_sketch(((200, 0, 0), (0, 0, 0)))
        self.side_profile = self.make_profile(side_path, "Edge1", **CENTER)
        back_profile = self.make_profile(back_path, "Edge1", **CENTER)
        self.side.addObjects([side_path, self.side_profile])
        self.back.addObjects([back_path, back_profile])
        self.trim = self.doc.addObject("Part::FeaturePython", "Miter")
        self.back.addObject(self.trim)
        TrimmedProfile(self.trim)
        self.trim.TrimmedBody = back_profile
        self.trim.TrimmingBoundary = [(self.side_profile, ("Edge1",))]
        self.trim.TrimmedProfileType = "End Miter"
        self.doc.recompute()
        self.side_group = list(self.side.Group)
        self.back_group = list(self.back.Group)

    def test_a_pattern_of_a_piece_trimmed_against_another_part_leaves_that_part_untouched(self):
        edge = edge_along(self.side_profile, Y)
        start = center(self.trim)
        obj = make_profile_pattern(self.trim, (self.side_profile, edge), count=2, pitch=100.0)
        self.doc.recompute()
        self.assertTrue(obj.isValid(), obj.getStatusString())
        self.assertEqual(self.side.Group, self.side_group)
        self.assertEqual(self.side_profile.getParentGeoFeatureGroup(), self.side)
        self.assertEqual(self.back.Group, self.back_group + [obj, *obj.Copies])
        moves = sorted(round(abs(center(link).sub(start).y), 6) for link in obj.Copies)
        self.assertEqual(moves, [100.0, 200.0])


if __name__ == "__main__":
    unittest.main()

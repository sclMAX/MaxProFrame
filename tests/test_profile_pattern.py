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
from freecad.maxproframe.create_extruded_cutout_tool import make_cutout_sketch, make_extruded_cutout
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.profile_pattern import make_profile_pattern
from freecad.maxproframe.trimmed_profile import TrimmedProfile

# The slat runs along Y at x = 100: 50 mm wide along X, the direction of the frame edge.
SLAT_X = 100.0
X = App.Vector(1, 0, 0)
Y = App.Vector(0, 1, 0)
Z = App.Vector(0, 0, 1)


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

    def touched(self):
        return [o.Name for o in self.doc.Objects if "Touched" in o.State]

    def drill(self, piece, along=100.0):
        """A drill hole on the top face of ``piece``, ``along`` mm along it from a corner of that face."""
        top = face_named(piece, Z, 25)
        point = piece.Shape.getElement(top).Vertexes[0].Point
        vertex = next(f"Vertex{i}" for i, v in enumerate(piece.Shape.Vertexes, start=1) if v.Point.isEqual(point, 1e-6))
        hole = make_drill_hole((piece, (top,)), vertex)
        hole.OffsetAlong, hole.OffsetAcross = along, 25.0
        self.doc.recompute()
        self.assert_valid(hole)
        self.assertLess(hole.Shape.Volume, piece.Shape.Volume - 1.0)
        return hole

    def cut_out(self, piece):
        """A cutout of a 10 mm circle in the middle of the top face of ``piece``."""
        top = face_named(piece, Z, 25)
        middle = piece.Shape.getElement(top).CenterOfMass
        sketch = make_cutout_sketch(piece, top)
        self.doc.recompute()
        local = sketch.Placement.inverse().multVec(middle)
        sketch.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), Z, 10.0))
        cutout = make_extruded_cutout(sketch, (piece, [top]))
        self.doc.recompute()
        self.assert_valid(cutout)
        self.assertLess(cutout.Shape.Volume, piece.Shape.Volume - 1.0)
        return cutout

    def extend_cut(self, piece, y):
        """An Extend Cut of ``piece`` up to the face at ``y`` of a stop box beyond it."""
        stop = self.box(f"Stop{int(y)}", -100)
        stop.Placement.Base = App.Vector(-100, y, -25)
        stop.Length, stop.Width = 1200, 100
        self.doc.recompute()
        trim = make_extend_cut_profile(piece, (stop, (face_named(stop, Y, y),)))
        self.doc.recompute()
        self.assert_valid(trim)
        return trim

    def assert_copies_are(self, obj, piece):
        """Every copy of ``obj`` shows ``piece``: links it, and has its volume and length."""
        self.assert_valid(obj)
        for link in obj.Copies:
            self.assertEqual(link.LinkedObject, piece)
            self.assertAlmostEqual(global_shape(link).Volume, piece.Shape.Volume, places=6)
            self.assertAlmostEqual(global_shape(link).BoundBox.YLength, piece.Shape.BoundBox.YLength, places=6)


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

    def test_lowering_the_count_of_a_pattern_in_a_part_leaves_nothing_to_recompute(self):
        part = self.doc.addObject("App::Part", "Table")
        part.addObjects([self.slat, *self.slat.OutList, self.frame])
        self.doc.recompute()
        obj = self.pattern(count=5, pitch=100.0)
        self.assertEqual(obj.getParentGeoFeatureGroup(), part)
        self.assertEqual(self.touched(), [])
        kept = [o.Name for o in part.Group if o not in obj.Copies[3:]]
        # As the property editor does: the value, then one recompute.
        obj.Count = 3
        self.doc.recompute()
        self.assert_valid(obj)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0])
        self.assertEqual(sorted(link.Name for link in obj.Copies), self.links())
        # Only the copies left over leave the Part: not what they linked.
        self.assertEqual([o.Name for o in part.Group], kept)
        self.assertEqual(self.touched(), [])

    def test_lowering_the_count_recomputed_after_its_undo_step_leaves_no_orphan(self):
        self.doc.UndoMode = 1
        part = self.doc.addObject("App::Part", "Table")
        part.addObjects([self.slat, *self.slat.OutList, self.frame])
        self.doc.recompute()
        self.doc.clearUndos()
        self.doc.openTransaction("Create")
        obj = self.pattern(count=5, pitch=100.0)
        self.doc.commitTransaction()
        self.doc.openTransaction("Edit Count")
        obj.Count = 2
        self.doc.commitTransaction()
        # Recomputed outside the step that changed the count, as a later refresh does.
        self.doc.recompute()
        self.assertEqual(self.doc.UndoNames, ["Edit Count", "Create"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(sorted(link.Name for link in obj.Copies), self.links())
        self.assertTrue(all(link.getParentGeoFeatureGroup() == part for link in obj.Copies))
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0, 400.0, 500.0, 600.0])

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

    def assert_part_shape_holds_every_copy(self, part):
        if App.GuiUp:
            # As the tree does when it shows the Part: what one of its objects claims leaves the shape of the Part.
            part.ViewObject.claimChildren()
        centers = sorted(round(solid.BoundBox.Center.x, 6) for solid in Part.getShape(part).Solids)
        self.assertEqual(centers, [SLAT_X, 200.0, 300.0, 400.0])

    def test_the_shape_of_a_part_holds_the_piece_and_every_copy(self):
        """TechDraw and exports take the shape of the Part: a view of the Part shows the whole pattern."""
        part = self.doc.addObject("App::Part", "Table")
        part.addObjects([self.slat, *self.slat.OutList, self.frame])
        self.doc.recompute()
        self.pattern(count=3, pitch=100.0)
        self.assert_part_shape_holds_every_copy(part)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        saved, copy = os.path.join(folder, "part.FCStd"), os.path.join(folder, "opened.FCStd")
        self.doc.saveAs(saved)
        # Opened from another file: a document of its own, read back from disk.
        shutil.copy(saved, copy)
        doc = App.openDocument(copy)
        self.addCleanup(App.closeDocument, doc.Name)
        self.assert_part_shape_holds_every_copy(doc.getObject(part.Name))


class TestPatternGroupsItsCopies(PatternFixture):
    """The pattern lists its copies under it, and a Part reaches them through it, as through a folder."""

    def in_part(self):
        part = self.doc.addObject("App::Part", "Table")
        part.addObjects([self.slat, *self.slat.OutList, self.frame])
        self.doc.recompute()
        obj = self.pattern(count=3, pitch=100.0)
        if App.GuiUp:
            # As the tree does when it shows the Part: the copies the pattern lists leave the list of the Part.
            part.ViewObject.claimChildren()
        return part, obj

    @unittest.skipUnless(App.GuiUp, "the tree needs the GUI")
    def test_the_copies_are_listed_under_the_pattern_not_beside_it(self):
        part, obj = self.in_part()
        self.assertEqual(obj.ViewObject.claimChildren(), list(obj.Copies))
        listed = part.ViewObject.claimChildren()
        self.assertIn(obj, listed)
        self.assertFalse(set(obj.Copies) & set(listed))

    def test_a_copy_is_reached_through_the_pattern_where_it_is(self):
        part, obj = self.in_part()
        self.assertTrue(obj.Visibility)
        self.assertIn(f"{obj.Name}.", part.getSubObjects())
        # FreeCAD hands the sub-objects out as a tuple.
        # Without the GUI the Part lists the copies itself: the pattern does not hand them out again.
        handed = [f"{link.Name}." for link in obj.Copies] if App.GuiUp else []
        self.assertEqual(list(obj.getSubObjects()), handed)
        for link in obj.Copies:
            # retType 1: the object; the default (0) gives its shape.
            self.assertEqual(part.getSubObject(f"{obj.Name}.{link.Name}.", retType=1), link)
            through = Part.getShape(part, f"{obj.Name}.{link.Name}.")
            self.assertTrue(through.BoundBox.Center.isEqual(center(link), 1e-6))

    def test_a_folder_that_lists_the_copies_itself_holds_each_copy_once(self):
        """A folder lists all it holds, the copies too: the pattern does not hand them out again."""
        folder = self.doc.addObject("App::DocumentObjectGroup", "Slats")
        folder.addObjects([self.slat, *self.slat.OutList, self.frame])
        self.doc.recompute()
        obj = self.pattern(count=3, pitch=100.0)
        self.assertTrue(all(link.getParentGroup() == folder for link in obj.Copies))
        centers = sorted(round(solid.BoundBox.Center.x, 6) for solid in Part.getShape(folder).Solids)
        self.assertEqual(centers, [SLAT_X, 200.0, 300.0, 400.0])

    def test_hiding_the_pattern_hides_its_copies_and_showing_it_shows_them(self):
        part, obj = self.in_part()
        if App.GuiUp:
            # The eye of the tree: a pattern shown is drawn shown, not greyed out.
            self.assertTrue(obj.ViewObject.isVisible())
        obj.Visibility = False
        if App.GuiUp:
            self.assertFalse(obj.ViewObject.isVisible())
        self.assertEqual([link.Visibility for link in obj.Copies], [False] * 3)
        obj.Count = 4
        self.doc.recompute()
        self.assertEqual([link.Visibility for link in obj.Copies], [False] * 4)
        obj.Visibility = True
        if App.GuiUp:
            self.assertTrue(obj.ViewObject.isVisible())
        self.assertEqual([link.Visibility for link in obj.Copies], [True] * 4)

    def test_a_pattern_saved_hidden_with_its_copies_shown_opens_shown(self):
        """Patterns were hidden before they listed their copies: the Part would leave the copies out of its shape."""
        part, obj = self.in_part()
        # As saved before: the pattern hidden, its copies shown. Set in the file, as onChanged would show them.
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        saved = os.path.join(folder, "pattern.FCStd")
        self.doc.saveAs(saved)
        old = os.path.join(folder, "old.FCStd")
        hide_in_file(saved, old, obj.Name)
        doc = App.openDocument(old)
        self.addCleanup(App.closeDocument, doc.Name)
        opened = doc.getObject(obj.Name)
        self.assertTrue(opened.Visibility)
        if App.GuiUp:
            self.assertTrue(opened.ViewObject.isVisible())
        self.assertEqual([link.Visibility for link in opened.Copies], [True] * 3)
        centers = sorted(round(s.BoundBox.Center.x, 6) for s in Part.getShape(doc.getObject(part.Name)).Solids)
        self.assertEqual(centers, [SLAT_X, 200.0, 300.0, 400.0])


def hide_in_file(source, target, name):
    """Copy the FCStd ``source`` to ``target`` with the object ``name`` hidden, in Document.xml and in
    GuiDocument.xml (the GUI shows or hides it from there), nothing else."""
    import re
    import zipfile

    blocks = {"Document.xml": ("<ObjectData", "Object"), "GuiDocument.xml": ("<ViewProviderData", "ViewProvider")}
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in blocks:
                section, tag = blocks[item.filename]
                text = data.decode("utf-8")
                start = text.index(f'<{tag} name="{name}"', text.index(section))
                end = text.index(f"</{tag}>", start)
                block, done = re.subn(
                    r'(<Property name="Visibility" type="App::PropertyBool"[^>]*>\s*<Bool value=")true',
                    r"\1false",
                    text[start:end],
                )
                assert done == 1, f"{name} is not shown in {item.filename} of {source}"
                data = (text[:start] + block + text[end:]).encode("utf-8")
            dst.writestr(item, data)


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


class TestLaterChanges(PatternFixture):
    """A drill hole, cutout or trim added to the original after the pattern shows on every copy."""

    def test_a_drill_hole_added_to_the_original_shows_on_every_copy(self):
        obj = self.pattern(count=2, pitch=100.0)
        hole = self.drill(self.slat)
        self.assert_copies_are(obj, hole)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0])
        self.assertEqual(self.touched(), [])

    def test_a_cutout_added_to_the_original_shows_on_every_copy(self):
        obj = self.pattern(count=2, pitch=100.0)
        cutout = self.cut_out(self.slat)
        self.assert_copies_are(obj, cutout)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0])
        self.assertEqual(self.touched(), [])

    def test_a_trim_added_to_the_original_shows_on_every_copy(self):
        obj = self.pattern(count=2, pitch=100.0)
        trim = self.extend_cut(self.slat, 500)
        self.assert_copies_are(obj, trim)
        for link in obj.Copies:
            self.assertAlmostEqual(global_shape(link).BoundBox.YMax, 500.0)
        self.assertEqual(self.touched(), [])

    def test_the_copies_follow_the_last_piece_built_on_the_original(self):
        trim = self.extend_cut(self.slat, 500)
        obj = self.pattern(piece=trim, count=2, pitch=100.0)
        self.assert_copies_are(obj, trim)
        hole = self.drill(trim)
        self.assert_copies_are(obj, hole)
        second = self.drill(hole, along=300.0)
        self.assert_copies_are(obj, second)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0])
        self.assertEqual(self.touched(), [])

    def test_removing_the_later_hole_brings_back_the_piece_it_was_made_on(self):
        obj = self.pattern(count=2, pitch=100.0)
        hole = self.drill(self.slat)
        self.assert_copies_are(obj, hole)
        self.doc.removeObject(hole.Name)
        self.doc.recompute()
        self.assert_copies_are(obj, self.slat)
        self.assertEqual(self.copy_centers(obj), [200.0, 300.0])

    def test_between_faces_still_moves_the_original_by_its_profile_when_a_hole_is_added(self):
        obj = self.pattern(mode="Between faces", count=5, faces=self.walls())
        hole = self.drill(self.slat)
        self.assert_copies_are(obj, hole)
        self.assertAlmostEqual(center(hole).x, 150.0)
        self.assertEqual(self.copy_centers(obj), [325.0, 500.0, 675.0, 850.0])
        obj.Count = 3
        self.doc.recompute()
        self.assert_copies_are(obj, hole)
        self.assertAlmostEqual(center(hole).x, 237.5)
        self.assertEqual(self.copy_centers(obj), [500.0, 762.5])
        self.assertEqual(self.touched(), [])


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

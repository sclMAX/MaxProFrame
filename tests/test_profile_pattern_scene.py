"""Profile Pattern on the user's table: slats between the long sides of a TC80x40 frame in a moved, turned Part.

The frame is 1000 x 600 outside, its tubes lying 40 mm wide; the slat, 100 mm wide, is cut by Extend Cut to the
inner faces of both long sides. Five slats between the inner faces of the short sides (920 mm apart) leave six
gaps of 70 mm.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets
from test_piece_table import PieceTableFixture
from test_profile_pattern import edge_along, face_named, global_shape
from test_profile_pattern_panel import PatternPanelFixture

from freecad.maxproframe import create_profile_pattern_tool
from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.create_extruded_cutout_tool import make_cutout_sketch, make_extruded_cutout
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.piece_table import table_rows
from freecad.maxproframe.profile_pattern import BETWEEN_FACES, make_profile_pattern

X = App.Vector(1, 0, 0)
Y = App.Vector(0, 1, 0)
Z = App.Vector(0, 0, 1)
# Where the Part of the table is, and how it is turned about Z.
TABLE_PLACEMENT = App.Placement(App.Vector(250, -120, 400), App.Rotation(Z, 33))
# Inner faces of the short sides, along the long ones (X of the table).
INNER = (40.0, 960.0)
SLAT_X = 300.0
SLAT_WIDTH = 100.0
SLAT_ID = "7"


def extent(shape, axis):
    """(lowest, highest) projection of the vertices of ``shape`` on ``axis``: the slats are straight tubes."""
    values = [vertex.Point.dot(axis) for vertex in shape.Vertexes]
    return min(values), max(values)


class SceneFixture(PieceTableFixture):
    # Whether the slat and its trims are in a Part of their own, Slats, inside the Part of the table.
    slats_part = False

    def setUp(self):
        super().setUp()
        App.setActiveDocument(self.doc.Name)
        self.table = self.doc.addObject("App::Part", "Table")
        frame_path = self.make_sketch(
            ((20, 20, 0), (980, 20, 0)), ((980, 20, 0), (980, 580, 0)), ((980, 580, 0), (20, 580, 0)),
            ((20, 580, 0), (20, 20, 0)),
        )  # fmt: skip
        # TC80x40 lying flat: 40 wide in the plane of the table, 80 high.
        self.bottom, self.right, self.top, self.left = (
            self.tube(frame_path, f"Edge{i}", width=40.0, height=80.0, extension=20.0) for i in range(1, 5)
        )
        self.table.addObjects([frame_path, self.bottom, self.right, self.top, self.left])
        self.holder = self.table
        if self.slats_part:
            self.holder = self.doc.addObject("App::Part", "Slats")
            self.table.addObject(self.holder)
        slat_path = self.make_sketch(((SLAT_X, 0, 0), (SLAT_X, 600, 0)))
        self.slat = self.tube(slat_path, width=SLAT_WIDTH, height=40.0)
        self.slat.PID = SLAT_ID
        self.holder.addObjects([slat_path, self.slat])
        self.table.Placement = TABLE_PLACEMENT
        self.doc.recompute()
        # Cut twice by Extend Cut, to the inner faces of the long sides.
        first = make_extend_cut_profile(self.slat, (self.bottom, (face_named(self.bottom, Y, 40),)))
        self.doc.recompute()
        self.piece = make_extend_cut_profile(first, (self.top, (face_named(self.top, Y, 560),)))
        self.doc.recompute()
        for obj in (first, self.piece):
            self.assertTrue(obj.isValid(), obj.getStatusString())
        self.assertEqual([round(v, 6) for v in extent(self.piece.Shape, Y)], [40.0, 560.0])
        self.edge = (self.bottom, edge_along(self.bottom, X))
        self.faces = [(side, face_named(side, X, at)) for side, at in ((self.left, INNER[0]), (self.right, INNER[1]))]
        edge = self.bottom.Shape.getElement(self.edge[1])
        # The sense of the edge along X of the table, from its first vertex to its last.
        self.sense = 1 if (edge.Vertexes[-1].Point - edge.Vertexes[0].Point).x > 0 else -1

    def pattern(self, piece=None, **values):
        obj = make_profile_pattern(piece or self.piece, self.edge, **values)
        self.doc.recompute()
        self.assertTrue(obj.isValid(), obj.getStatusString())
        return obj

    def between(self, count=5, faces=None):
        return self.pattern(mode=BETWEEN_FACES, count=count, faces=faces or self.faces)

    def pieces(self, obj):
        """The original the pattern shows, then its copies."""
        return [obj.Copies[0].LinkedObject, *obj.Copies]

    def gaps(self, obj):
        """(local, global) free gaps from the first inner face to the second, between the pieces of ``obj``."""
        local = sorted(extent(Part.getShape(piece), X) for piece in self.pieces(obj))
        placement = self.table.getGlobalPlacement()
        axis = placement.Rotation.multVec(X)
        faces = []
        for side, sub in self.faces:
            face = side.Shape.getElement(sub).copy()
            face.Placement = placement.multiply(face.Placement)
            faces.append(face.CenterOfMass.dot(axis))
        world = sorted(extent(global_shape(piece), axis) for piece in self.pieces(obj))
        return self.between_spans(INNER, local), self.between_spans(sorted(faces), world)

    @staticmethod
    def between_spans(limits, spans):
        ends = [limits[0], *(end for span in spans for end in span), limits[1]]
        return [round(ends[i + 1] - ends[i], 6) for i in range(0, len(ends), 2)]

    def assert_gaps(self, obj, gap, count):
        local, world = self.gaps(obj)
        self.assertEqual(local, [gap] * (count + 1))
        self.assertEqual(world, [gap] * (count + 1))
        self.assertAlmostEqual(obj.Gap.Value, gap, places=6)

    def original_span(self):
        return [round(v, 6) for v in extent(self.piece.Shape, X)]

    def touched(self):
        return [o.Name for o in self.doc.Objects if "Touched" in o.State and not o.TypeId.startswith("TechDraw")]

    def top_face(self, piece):
        return face_named(piece, Z, 20)

    def drill(self, piece):
        top = self.top_face(piece)
        point = piece.Shape.getElement(top).Vertexes[0].Point
        vertex = next(f"Vertex{i}" for i, v in enumerate(piece.Shape.Vertexes, start=1) if v.Point.isEqual(point, 1e-6))
        hole = make_drill_hole((piece, (top,)), vertex)
        hole.OffsetAlong, hole.OffsetAcross = 100.0, 50.0
        self.doc.recompute()
        self.assertTrue(hole.isValid(), hole.getStatusString())
        self.assertLess(hole.Shape.Volume, piece.Shape.Volume - 1.0)
        return hole

    def cut_out(self, piece):
        top = self.top_face(piece)
        middle = piece.Shape.getElement(top).CenterOfMass
        sketch = make_cutout_sketch(piece, top)
        self.doc.recompute()
        local = sketch.Placement.inverse().multVec(middle)
        sketch.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), Z, 15.0))
        cutout = make_extruded_cutout(sketch, (piece, [top]))
        self.doc.recompute()
        self.assertTrue(cutout.isValid(), cutout.getStatusString())
        self.assertLess(cutout.Shape.Volume, piece.Shape.Volume - 1.0)
        return cutout

    def assert_copies_show(self, obj, piece):
        for link in obj.Copies:
            self.assertEqual(link.LinkedObject, piece)
            self.assertAlmostEqual(Part.getShape(link).Volume, piece.Shape.Volume, places=6)


class TestBetweenFaces(SceneFixture):
    def test_five_slats_leave_six_equal_gaps_of_70_in_the_table_and_in_the_world(self):
        obj = self.between()
        self.assertEqual(len(obj.Copies), 4)
        self.assert_gaps(obj, 70.0, 5)
        # The original takes the slot next to the first face.
        self.assertEqual(self.original_span(), [110.0, 210.0])
        self.assertEqual(self.touched(), [])

    def test_swapping_the_faces_moves_the_original_to_the_other_end(self):
        obj = self.between(faces=list(reversed(self.faces)))
        self.assert_gaps(obj, 70.0, 5)
        self.assertEqual(self.original_span(), [790.0, 890.0])

    def test_a_new_count_spaces_the_slats_again(self):
        obj = self.between()
        for count, gap in ((3, 155.0), (8, round(120.0 / 9, 6))):
            obj.Count = count
            self.doc.recompute()
            self.assertTrue(obj.isValid(), obj.getStatusString())
            self.assertEqual(len(obj.Copies), count - 1)
            self.assert_gaps(obj, gap, count)
            self.assertEqual(self.touched(), [])

    def test_a_drill_hole_added_to_the_original_shows_on_every_slat(self):
        obj = self.between()
        hole = self.drill(self.piece)
        self.assert_copies_show(obj, hole)
        self.assert_gaps(obj, 70.0, 5)
        self.assertEqual(self.touched(), [])


class TestCountAndPitch(SceneFixture):
    def test_count_and_pitch_120_in_the_edge_sense_inverted_and_symmetric(self):
        start_local = Part.getShape(self.piece).BoundBox.Center
        start_world = global_shape(self.piece).BoundBox.Center
        rotation = self.table.getGlobalPlacement().Rotation
        for sense, count, steps in (
            ("Edge sense", 3, [1, 2, 3]),
            ("Inverted", 3, [-1, -2, -3]),
            ("Symmetric", 2, [-2, -1, 1, 2]),
        ):
            with self.subTest(sense=sense):
                obj = self.pattern(count=count, pitch=120.0, sense=sense)
                moves = sorted(120.0 * step * self.sense for step in steps)
                local = [Part.getShape(link).BoundBox.Center - start_local for link in obj.Copies]
                self.assertEqual(sorted(round(move.x, 6) for move in local), [round(move, 6) for move in moves])
                self.assertEqual([(round(move.y, 6), round(move.z, 6)) for move in local], [(0.0, 0.0)] * len(moves))
                for link in obj.Copies:
                    move = global_shape(link).BoundBox.Center - start_world
                    # Along the edge of the turned table, nothing else.
                    self.assertLess(move.cross(rotation.multVec(X)).Length, 1e-6)
                self.assertEqual(self.touched(), [])
                self.doc.removeObject(obj.Name)
                self.doc.recompute()

    def test_a_drill_hole_and_a_cutout_are_repeated_with_their_holes(self):
        for make in (self.drill, self.cut_out):
            with self.subTest(source=make.__name__):
                source = make(self.piece)
                obj = self.pattern(piece=source, count=2, pitch=120.0)
                self.assert_copies_show(obj, source)
                self.doc.removeObject(obj.Name)
                self.doc.removeObject(source.Name)
                self.doc.recompute()


class TestSlatsInTheirOwnPart(SceneFixture):
    slats_part = True

    def test_the_pattern_and_its_copies_join_the_slats_and_leave_the_table_as_it_was(self):
        table, slats = list(self.table.Group), list(self.holder.Group)
        obj = self.between()
        self.assertEqual(self.table.Group, table)
        self.assertEqual(self.holder.Group, slats + [obj, *obj.Copies])
        self.assert_gaps(obj, 70.0, 5)


class TestIds(SceneFixture):
    def slat_rows(self):
        profiles, links = [], []
        traverse_assembly(profiles, links, self.table)
        self.assertEqual(links, [])
        return [row for row in profiles if row["ID"] == SLAT_ID]

    def test_the_bom_and_the_piece_table_count_five_slats_with_one_id(self):
        obj = self.between()
        rows = self.slat_rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual([(row["ID"], row["quantity"]) for row in group_profiles(rows)], [(SLAT_ID, 5)])
        table, listed, without_id = table_rows([self.add_view("View", self.table)])
        self.assertEqual([row[0] for row in table if row[0] == SLAT_ID], [SLAT_ID])
        self.assertEqual(next(row[2] for row in table if row[0] == SLAT_ID), "5")
        hole = self.drill(self.piece)
        self.assert_copies_show(obj, hole)
        grouped = group_profiles(self.slat_rows())
        self.assertEqual([(row["ID"], row["cutout"], row["quantity"]) for row in grouped], [(SLAT_ID, "Yes", 5)])


class TestPanel(SceneFixture):
    run_command = PatternPanelFixture.run_command
    select = PatternPanelFixture.select
    click = PatternPanelFixture.click
    set_values = PatternPanelFixture.set_values
    events = PatternPanelFixture.events
    close_dialog = PatternPanelFixture.close_dialog
    patterns = PatternPanelFixture.patterns
    names = PatternPanelFixture.names

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        self.doc.clearUndos()
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        base = create_profile_pattern_tool.ProfilePatternTaskPanel
        recorded = self.recorded

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_profile_pattern_tool, "ProfilePatternTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.addCleanup(self.close_dialog)

    def panel_between(self, count=5):
        panel = self.run_command((self.piece, ""), self.edge)
        for face in self.faces:
            self.click(*face)
        self.set_values(panel, mode=BETWEEN_FACES, count=count)
        return panel

    def edit(self, obj):
        count = len(self.recorded)
        Gui.getDocument(obj.Document.Name).setEdit(obj.Name, 0)
        self.events()
        self.assertEqual(len(self.recorded), count + 1)
        return self.recorded[-1]

    def test_cancel_leaves_the_table_as_it_was(self):
        before, span = self.names(), self.original_span()
        panel = self.panel_between()
        (obj,) = self.patterns()
        self.assert_gaps(obj, 70.0, 5)
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual(self.names(), before)
        self.assertEqual(self.original_span(), span)
        self.assertEqual(self.doc.UndoNames, [])

    def test_ok_is_one_undo_step_that_puts_the_original_back(self):
        before, span = self.names(), self.original_span()
        panel = self.panel_between()
        self.assertTrue(panel.accept())
        self.close_dialog()
        (obj,) = self.patterns()
        self.assert_gaps(obj, 70.0, 5)
        self.assertEqual(self.doc.UndoNames, ["Create Profile Pattern"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.names(), before)
        self.assertEqual(self.original_span(), span)

    def test_double_click_edits_the_count(self):
        obj = self.between()
        self.doc.clearUndos()
        panel = self.edit(obj)
        self.set_values(panel, mode=BETWEEN_FACES, count=3)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assert_gaps(obj, 155.0, 3)
        self.assertEqual(self.doc.UndoNames, ["Edit Profile Pattern"])
        self.doc.undo()
        self.doc.recompute()
        self.assert_gaps(obj, 70.0, 5)

    def test_deleting_the_pattern_removes_its_copies_and_undo_brings_them_back(self):
        obj = self.between()
        name, copies = obj.Name, sorted(link.Name for link in obj.Copies)
        self.doc.clearUndos()
        self.doc.openTransaction("Delete")
        self.doc.removeObject(name)
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual([o for o in self.doc.Objects if o.TypeId == "App::Link"], [])
        self.assertTrue(self.piece.isValid())
        self.doc.undo()
        self.doc.recompute()
        obj = self.doc.getObject(name)
        self.assertEqual(sorted(link.Name for link in obj.Copies), copies)
        self.assert_gaps(obj, 70.0, 5)

    def test_a_saved_table_reopens_and_its_pattern_edits(self):
        obj = self.between()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        saved, copy = os.path.join(folder, "table.FCStd"), os.path.join(folder, "opened.FCStd")
        self.doc.saveAs(saved)
        shutil.copy(saved, copy)
        doc = App.openDocument(copy)
        self.addCleanup(App.closeDocument, doc.Name)
        App.setActiveDocument(doc.Name)
        reopened = doc.getObject(obj.Name)
        panel = self.edit(reopened)
        self.assertEqual(panel.form.spin_count.value(), 5)
        self.set_values(panel, mode=BETWEEN_FACES, count=3)
        self.assertTrue(panel.accept())
        self.close_dialog()
        doc.recompute()
        self.assertTrue(reopened.isValid(), reopened.getStatusString())
        self.assertEqual(len(reopened.Copies), 2)
        self.assertAlmostEqual(reopened.Gap.Value, 155.0, places=6)


if __name__ == "__main__":
    unittest.main()

"""Saved documents: a piece saved with its tip-to-tip length opens with its longest side, without a recompute.

Every profile, trimmed profile and cutout takes, as the document opens, the length its saved shape gives
(the tape length), so the BOM, the Cut List and the Piece Table read it at once.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from test_cut_ends import ALONG_X, SLANTED_TARGET
from test_end_miter_geometry import CENTER
from test_tape_length import PATH, SIDE, TapeLengthFixture, slant

from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.parametric_line import CreateParametricLineCommand
from freecad.maxproframe.piece_table import piece_texts


class KeepActive:
    """Keeps the document ``name`` active while another one is opened, as when opening a document loads others."""

    def __init__(self, name):
        self.name = name
        self.seen = False

    def slotCreatedDocument(self, doc):
        # Called before the new document is read: its objects are restored with the other one active.
        if doc.Name != self.name:
            self.seen = True
            App.setActiveDocument(self.name)


class LengthRestoreFixture(TapeLengthFixture):
    def saved_before_tape_length(self, obj, length):
        """``obj`` as a document saved before the tape length has it: ``length`` stored, nothing to recompute."""
        obj.Length = length
        obj.purgeTouched()

    def reopen(self):
        """The document saved to a scratch file and opened again, as a user opens a saved document."""
        folder = tempfile.mkdtemp()
        # Cleanups run last first: the opened document closes before its folder is removed.
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "pieces.FCStd")
        self.doc.saveCopy(path)
        opened = App.openDocument(path)
        self.addCleanup(lambda: App.closeDocument(opened.Name) if opened.Name in App.listDocuments() else None)
        return opened

    def assert_nothing_to_recompute(self, doc):
        self.assertEqual([obj.Name for obj in doc.Objects if "Touched" in obj.State], [])

    def assert_shape_kept(self, saved, opened):
        self.assertAlmostEqual(opened.Shape.Volume, saved.Shape.Volume, places=6)
        self.assertTrue(opened.Shape.BoundBox.isInside(saved.Shape.BoundBox.Center))


class TestLengthRestore(LengthRestoreFixture):
    def test_a_parallelogram_saved_tip_to_tip_opens_with_its_side(self):
        obj = self.parallelogram()
        self.saved_before_tape_length(obj, PATH + slant(12.0))
        opened = self.reopen()
        piece = opened.getObject(obj.Name)
        self.assertAlmostEqual(piece.Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)
        self.assert_shape_kept(obj, piece)

    def test_a_trimmed_piece_and_its_cutout_open_with_the_longest_side(self):
        body = self.square_tube(BevelBCutY=30.0)
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        trim = self.valid_extend_cut(body, target)
        cutout = self.hole_in_the_middle(trim)
        expected = trim.Length.Value
        self.assertAlmostEqual(cutout.Length.Value, expected, places=6)
        tip_to_tip = self.tip_to_tip(trim)
        self.assertAlmostEqual(tip_to_tip - expected, slant(30.0), places=6)
        for obj in (trim, cutout):
            self.saved_before_tape_length(obj, tip_to_tip)
        opened = self.reopen()
        for obj in (trim, cutout):
            with self.subTest(obj.Name):
                self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, expected, places=6)
        self.assert_nothing_to_recompute(opened)
        self.assert_shape_kept(trim, opened.getObject(trim.Name))

    def test_a_cutout_of_a_parallelogram_opens_with_the_side(self):
        body = self.parallelogram()
        cutout = self.hole_in_the_middle(body)
        for obj in (body, cutout):
            self.saved_before_tape_length(obj, PATH + slant(12.0))
        opened = self.reopen()
        for obj in (body, cutout):
            with self.subTest(obj.Name):
                self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)

    def test_a_drill_hole_of_a_parallelogram_opens_with_the_side(self):
        body = self.parallelogram()
        top = max(
            (f"Face{i}" for i, f in enumerate(body.Shape.Faces, start=1) if isinstance(f.Surface, Part.Plane)),
            key=lambda name: body.Shape.getElement(name).Area,
        )
        point = body.Shape.getElement(top).Vertexes[0].Point
        vertex = next(f"Vertex{i}" for i, v in enumerate(body.Shape.Vertexes, start=1) if v.Point.isEqual(point, 1e-6))
        hole = make_drill_hole((body, (top,)), vertex)
        hole.OffsetAlong = PATH / 2
        self.doc.recompute()
        self.assertAlmostEqual(hole.Length.Value, PATH, places=6)
        for obj in (body, hole):
            self.saved_before_tape_length(obj, PATH + slant(12.0))
        opened = self.reopen()
        for obj in (body, hole):
            with self.subTest(obj.Name):
                self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)

    def test_the_bom_and_the_piece_table_read_the_side_at_once(self):
        obj = self.parallelogram()
        obj.PID = "3"
        self.saved_before_tape_length(obj, PATH + slant(12.0))
        piece = self.reopen().getObject(obj.Name)
        data, links = [], []
        traverse_assembly(data, links, piece)
        self.assertEqual(data[0]["length"], f"{PATH:.1f}")
        self.assertEqual(piece_texts(piece)[1], f"{PATH:.1f}")

    def test_a_piece_on_a_parametric_line_in_another_part_opens_with_its_side(self):
        sketch = self.make_sketch(ALONG_X)
        CreateParametricLineCommand().make_parametric_line([(sketch, "Vertex1"), (sketch, "Vertex2")])
        line = self.doc.ActiveObject
        lines = self.doc.addObject("App::Part", "Lines")
        lines.addObjects([sketch, line])
        lines.Placement.Base = App.Vector(0, 0, 50)
        self.doc.recompute()
        obj = self.tube(line, width=SIDE, height=SIDE, BevelACutY=12.0, BevelBCutY=-12.0)
        pieces = self.doc.addObject("App::Part", "Pieces")
        pieces.addObject(obj)
        self.doc.recompute()
        self.assertAlmostEqual(obj.Length.Value, PATH, places=6)
        self.saved_before_tape_length(obj, PATH + slant(12.0))
        opened = self.reopen()
        self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)

    def test_a_document_opened_while_another_is_active_measures_its_own_pieces(self):
        obj = self.parallelogram()
        self.saved_before_tape_length(obj, PATH + slant(12.0))
        other = App.newDocument("OtherDocument")
        self.addCleanup(lambda: App.closeDocument(other.Name) if other.Name in App.listDocuments() else None)
        # The other document has an object of the same name on another path, as a second chair would.
        sketch = other.addObject("Sketcher::SketchObject", self.doc.getObject("Path").Name)
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 100, 0)))
        other.recompute()
        observer = KeepActive(other.Name)
        App.addDocumentObserver(observer)
        self.addCleanup(App.removeDocumentObserver, observer)
        opened = self.reopen()
        self.assertTrue(observer.seen)
        self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)

    def test_a_piece_whose_path_is_gone_keeps_its_saved_length(self):
        obj = self.parallelogram()
        stored = PATH + slant(12.0)
        self.saved_before_tape_length(obj, stored)
        obj.Target = (obj.Target[0], ("Edge9",))
        obj.purgeTouched()
        opened = self.reopen()
        piece = opened.getObject(obj.Name)
        self.assertAlmostEqual(piece.Length.Value, stored, places=6)
        self.assertTrue(piece.isValid(), piece.getStatusString())

    def test_a_piece_saved_without_shape_keeps_its_saved_length(self):
        obj = self.parallelogram()
        stored = PATH + slant(12.0)
        obj.Shape = Part.Shape()
        self.saved_before_tape_length(obj, stored)
        opened = self.reopen()
        piece = opened.getObject(obj.Name)
        self.assertAlmostEqual(piece.Length.Value, stored, places=6)
        self.assertTrue(piece.isValid(), piece.getStatusString())

    def test_a_piece_already_measured_opens_unchanged(self):
        obj = self.parallelogram()
        opened = self.reopen()
        self.assertAlmostEqual(opened.getObject(obj.Name).Length.Value, PATH, places=6)
        self.assert_nothing_to_recompute(opened)


if __name__ == "__main__":
    unittest.main()

"""Extend / Cut keeps its target face after the frame changes.

A table frame of four mitered profiles drawn on one sketch, sized by a VarSet, and a slat cut by two Extend / Cut
on the inner faces of two sides. A new size moves those faces and FreeCAD loses their names ("?Face2"): the slat
still ends on them.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
import Sketcher
from test_end_miter_geometry import CENTER, SIZE, MiterFixture

from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile

HALF = SIZE / 2.0
WIDTH, LENGTH = 1100.0, 2200.0
# The slat runs across the frame this far above its bottom side.
SLAT_RISE = 100.0
# The Part holding the frame is moved and turned: the checks are made in document coordinates.
PART_PLACEMENT = App.Placement(App.Vector(100, 200, 30), App.Rotation(App.Vector(0, 0, 1), 30))
PLACES = 4


class LostFaceFixture(MiterFixture):
    def setUp(self):
        super().setUp()
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.addProperty("App::PropertyLength", "Ancho")
        self.varset.addProperty("App::PropertyLength", "Largo")
        self.varset.Ancho, self.varset.Largo = WIDTH, LENGTH
        self.part = self.doc.addObject("App::Part", "Part")
        self.part.Placement = PART_PLACEMENT
        self.sketch = self.frame_sketch()
        # Sides ending at their path ends: each miter extends its side up to the corner, as in a drawn frame.
        sides = [self.in_part(self.profile(f"Edge{index}")) for index in (1, 2, 3, 4)]
        # Each side mitered against both neighbours, as the End Miter command makes a closed frame.
        self.miters = [
            make_end_miter_profile(side, [(sides[index - 1], ("",)), (sides[(index + 1) % 4], ("",))])
            for index, side in enumerate(sides)
        ]
        self.doc.recompute()
        # The pieces the slat is cut against: the left and right sides, or pieces made on them.
        self.left, self.right = self.cut_targets(self.miters[0], self.miters[2])
        self.doc.recompute()
        self.slat = self.in_part(self.profile("Edge5"))
        first = make_extend_cut_profile(self.slat, (self.left, (self.inner_face(self.left, 1),)))
        self.doc.recompute()
        self.trim = make_extend_cut_profile(first, (self.right, (self.inner_face(self.right, -1),)))
        self.trims = [first, self.trim]
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, WIDTH)

    def cut_targets(self, left, right):
        """The pieces the slat is cut against, given the left and right sides."""
        return left, right

    def profile(self, edge):
        return self.make_profile(self.sketch, edge, extension=0.0, **CENTER)

    def in_part(self, obj):
        self.part.addObject(obj)
        return obj

    def frame_sketch(self):
        """A rectangle centred on the origin, its width and length set by the VarSet, and the slat across it."""
        sketch = self.part.newObject("Sketcher::SketchObject", "Sketch")
        x, y = WIDTH / 2.0, LENGTH / 2.0
        corners = [App.Vector(-x, y, 0), App.Vector(-x, -y, 0), App.Vector(x, -y, 0), App.Vector(x, y, 0)]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]))
        slat_y = -y + SLAT_RISE
        sketch.addGeometry(Part.LineSegment(App.Vector(-x, slat_y, 0), App.Vector(x, slat_y, 0)))
        constraints = [Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1) for index in range(4)]
        constraints += [Sketcher.Constraint("Vertical", 0), Sketcher.Constraint("Vertical", 2)]
        constraints += [Sketcher.Constraint("Horizontal", 1), Sketcher.Constraint("Horizontal", 3)]
        constraints += [Sketcher.Constraint("Symmetric", 0, 1, 2, 1, -1, 1)]
        constraints += [Sketcher.Constraint("PointOnObject", 4, 1, 0), Sketcher.Constraint("PointOnObject", 4, 2, 2)]
        constraints += [Sketcher.Constraint("Horizontal", 4), Sketcher.Constraint("DistanceY", 1, 1, 4, 1, SLAT_RISE)]
        for constraint in constraints:
            sketch.addConstraint(constraint)
        sketch.renameConstraint(sketch.addConstraint(Sketcher.Constraint("DistanceX", 1, 1, 1, 2, WIDTH)), "Width")
        sketch.renameConstraint(sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 2, 0, 1, LENGTH)), "Length")
        sketch.setExpression(".Constraints.Width", "VarSet.Ancho")
        sketch.setExpression(".Constraints.Length", "VarSet.Largo")
        self.doc.recompute()
        return sketch

    @staticmethod
    def inner_face(obj, sense):
        """Name of the flat face of ``obj`` looking along X by ``sense`` (in the Part) farthest that way: the inner one."""
        direction = App.Vector(sense, 0, 0)
        faces = [
            (index, face)
            for index, face in enumerate(obj.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).dot(direction) > 1 - 1e-9
        ]
        index, _ = max(faces, key=lambda item: item[1].CenterOfMass.dot(direction))
        return f"Face{index}"

    def resize(self, doc, width, length):
        doc.getObject("VarSet").Ancho, doc.getObject("VarSet").Largo = width, length
        doc.recompute()

    def assert_all_valid(self, doc):
        self.assertEqual({obj.Label: obj.getStatusString() for obj in doc.Objects if not obj.isValid()}, {})
        self.assertEqual([obj.Label for obj in doc.Objects if "Touched" in obj.State], [])

    def assert_slat_between_the_sides(self, doc, width):
        """The slat, in document coordinates, ends on the inner faces of the sides, ``width`` apart at their axes."""
        part = doc.getObject("Part").getGlobalPlacement()
        across = part.Rotation.multVec(App.Vector(1, 0, 0))
        trim = doc.getObject(self.trim.Name)
        slat = trim.Shape.transformed(part.toMatrix())
        reach = [vertex.Point.dot(across) for vertex in slat.Vertexes]
        for miter, sense, end in ((self.left, 1, min(reach)), (self.right, -1, max(reach))):
            face = doc.getObject(miter.Name).Shape.getElement(self.inner_face(doc.getObject(miter.Name), sense))
            self.assertAlmostEqual(end, face.transformed(part.toMatrix()).CenterOfMass.dot(across), places=PLACES)
        center = part.multVec(App.Vector(0, 0, 0)).dot(across)
        self.assertAlmostEqual(min(reach), center - width / 2.0 + HALF, places=PLACES)
        self.assertAlmostEqual(max(reach), center + width / 2.0 - HALF, places=PLACES)
        self.assertAlmostEqual(trim.Length.Value, width - SIZE, places=PLACES)

    def reopen(self, doc):
        """``doc`` saved to a scratch file and opened again."""
        folder = tempfile.mkdtemp()
        # Cleanups run last first: the opened document closes before its folder is removed.
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "frame.FCStd")
        doc.saveCopy(path)
        opened = App.openDocument(path)
        self.addCleanup(lambda: App.closeDocument(opened.Name) if opened.Name in App.listDocuments() else None)
        return opened


class TestExtendCutLostFace(LostFaceFixture):
    def test_the_slat_follows_the_sides_when_the_frame_grows_or_shrinks(self):
        for width, length in ((1200.0, 2300.0), (1000.0, 2100.0), (WIDTH, LENGTH)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)

    def test_the_trim_links_the_face_it_found_again(self):
        self.resize(self.doc, 1200.0, 2300.0)
        for trim, miter, sense in ((self.trims[0], self.left, 1), (self.trims[1], self.right, -1)):
            self.assertEqual(trim.TrimmingBoundary, [(miter, (self.inner_face(miter, sense),))])

    def test_a_document_opened_and_resized_moves_the_slat(self):
        opened = self.reopen(self.doc)
        self.resize(opened, 1200.0, 2300.0)
        self.assert_all_valid(opened)
        self.assert_slat_between_the_sides(opened, 1200.0)

    def test_a_document_resized_saved_and_opened_again_follows_the_next_size(self):
        self.resize(self.doc, 1200.0, 2300.0)
        opened = self.reopen(self.doc)
        self.resize(opened, 1000.0, 2100.0)
        self.assert_all_valid(opened)
        self.assert_slat_between_the_sides(opened, 1000.0)

    def test_a_trim_deleted_and_undone_follows_the_next_size(self):
        self.doc.UndoMode = 1
        self.doc.openTransaction("delete")
        self.doc.removeObject(self.trim.Name)
        self.doc.commitTransaction()
        self.doc.undo()
        self.resize(self.doc, 1200.0, 2300.0)
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, 1200.0)

    def test_a_resize_undone_then_another_size_moves_the_slat(self):
        self.doc.UndoMode = 1
        self.doc.openTransaction("resize")
        self.resize(self.doc, 1200.0, 2300.0)
        self.doc.commitTransaction()
        self.doc.undo()
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, WIDTH)
        for width, length in ((1000.0, 2100.0), (1200.0, 2300.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)

    def test_a_document_opened_unchanged_recomputes_to_the_same_shapes(self):
        opened = self.reopen(self.doc)
        for obj in opened.Objects:
            obj.touch()
        opened.recompute()
        self.assert_all_valid(opened)
        for trim in self.trims:
            again = opened.getObject(trim.Name)
            self.assertEqual(again.TrimmingBoundary[0][1], trim.TrimmingBoundary[0][1])
            self.assertAlmostEqual(again.Shape.Volume, trim.Shape.Volume, places=6)
            for side in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"):
                self.assertAlmostEqual(
                    getattr(again.Shape.BoundBox, side), getattr(trim.Shape.BoundBox, side), places=6, msg=side
                )
            self.assertAlmostEqual(again.Length.Value, trim.Length.Value, places=6)

    def test_a_side_with_no_face_where_the_slat_ended_still_fails_naming_it(self):
        # The left side gets a wider section with the new size: no face of it is where the slat ended.
        left = self.left.TrimmedBody
        left.ProfileWidth = SIZE + 10.0
        left.ProfileHeight = SIZE + 10.0
        self.resize(self.doc, 1200.0, 2300.0)
        first = self.trims[0]
        self.assertFalse(first.isValid())
        status = first.getStatusString()
        self.assertTrue(status.startswith("Extend / Cut: the target face "), status)
        self.assertIn(f" of {self.left.Label} is not planar.", status)


if __name__ == "__main__":
    unittest.main()

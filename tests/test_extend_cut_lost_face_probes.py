"""Extend / Cut follows its target face after a resize in other set-ups: targets that are a drill hole, a Notch
or another Extend / Cut, a Part moved in the same recompute, several documents with the same names.

Rebuilt from the scenarios an independent verifier probed on the first fix.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
import Sketcher
from PySide import QtWidgets
from test_extend_cut_lost_face import HALF, LENGTH, PART_PLACEMENT, PLACES, WIDTH, LostFaceFixture

from freecad.maxproframe.create_extend_cut_tool import ExtendCutTaskPanel, make_extend_cut_profile
from freecad.maxproframe.create_notch_tool import make_notch_profile
from freecad.maxproframe.drill_hole import make_drill_hole

SIZES = ((1200.0, 2300.0), (1000.0, 2100.0), (WIDTH, LENGTH))
# Shrinking first: FreeCAD gives the name of the inner face of a side to its outer face.
SHRINK_FIRST = ((1000.0, 2100.0), (900.0, 1900.0), (1200.0, 2300.0), (WIDTH, LENGTH))
# The crossbar a Notch cuts the left side with runs across it at this height, in the Part.
CROSSBAR_Y = 700.0
# The post starts on the top side, on the Y axis, and its path stops this far above the slat path.
POST_GAP = 200.0


class ProbeFixture(LostFaceFixture):
    @staticmethod
    def face_towards(obj, direction):
        """Name of the flat face of ``obj`` looking along ``direction`` farthest that way."""
        faces = [
            (index, face)
            for index, face in enumerate(obj.Shape.Faces, 1)
            if isinstance(face.Surface, Part.Plane) and face.normalAt(0, 0).dot(direction) > 1 - 1e-9
        ]
        index, _ = max(faces, key=lambda item: item[1].CenterOfMass.dot(direction))
        return f"Face{index}"

    def assert_follows_every_size(self, sizes=SIZES):
        for width, length in sizes:
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)


class TestTargetIsADrillHole(ProbeFixture):
    def cut_targets(self, left, right):
        self.doc.recompute()
        top = self.face_towards(left, App.Vector(0, 0, 1))
        corner = left.Shape.getElement(top).Vertexes[0].Point
        vertex = next(
            f"Vertex{index}" for index, v in enumerate(left.Shape.Vertexes, 1) if v.Point.isEqual(corner, 1e-6)
        )
        hole = make_drill_hole((left, (top,)), vertex)
        # In the middle of the top face: the hole leaves the inner face alone.
        hole.CenterAlong = hole.CenterAcross = True
        return hole, right

    def test_the_slat_cut_against_a_drill_hole_follows_the_sides(self):
        self.assertEqual(self.left.Proxy.__class__.__name__, "DrillHole")
        self.assert_follows_every_size()

    def test_the_slat_cut_against_a_drill_hole_follows_a_shrink_first(self):
        self.assert_follows_every_size(SHRINK_FIRST)


class TestTargetIsANotch(ProbeFixture):
    def cut_targets(self, left, right):
        sketch = self.part.newObject("Sketcher::SketchObject", "Crossbar")
        sketch.addGeometry(
            Part.LineSegment(
                App.Vector(-WIDTH / 2.0 - 200.0, CROSSBAR_Y, 0), App.Vector(-WIDTH / 2.0 + 200.0, CROSSBAR_Y, 0)
            )
        )
        self.doc.recompute()
        crossbar = self.in_part(self.make_profile(sketch, "Edge1", extension=0.0, anchor_x=1, anchor_y=1))
        return make_notch_profile(left, crossbar), right

    def test_the_slat_cut_against_a_notch_follows_the_sides(self):
        self.assertEqual(self.left.TrimmedProfileType, "Notch")
        self.assert_follows_every_size()

    def test_the_slat_cut_against_a_notch_follows_a_shrink_first(self):
        self.assert_follows_every_size(SHRINK_FIRST)


class TestTargetIsAnExtendCut(ProbeFixture):
    def setUp(self):
        super().setUp()
        # A post from the top side down to the slat, cut against the face of the slat looking at it.
        geometry = self.sketch.addGeometry(Part.LineSegment(App.Vector(0, LENGTH / 2.0, 0), App.Vector(0, -500, 0)))
        for constraint in (
            Sketcher.Constraint("PointOnObject", geometry, 1, 3),
            Sketcher.Constraint("PointOnObject", geometry, 1, -2),
            Sketcher.Constraint("Vertical", geometry),
            Sketcher.Constraint("DistanceY", 4, 1, geometry, 2, POST_GAP),
        ):
            self.sketch.addConstraint(constraint)
        self.doc.recompute()
        self.post = self.in_part(self.profile(f"Edge{geometry + 1}"))
        self.post_trim = make_extend_cut_profile(
            self.post, (self.trim, (self.face_towards(self.trim, App.Vector(0, 1, 0)),))
        )
        self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assert_post_on_the_slat(LENGTH)

    def assert_post_on_the_slat(self, length):
        """The post, in document coordinates, ends on the face of the slat looking at it."""
        part = self.part.getGlobalPlacement()
        along = part.Rotation.multVec(App.Vector(0, 1, 0))
        post = self.post_trim.Shape.transformed(part.toMatrix())
        slat_face = part.multVec(App.Vector(0, -length / 2.0 + 100.0 + HALF, 0)).dot(along)
        self.assertAlmostEqual(min(vertex.Point.dot(along) for vertex in post.Vertexes), slat_face, places=PLACES)

    def test_a_post_cut_against_the_slat_follows_it(self):
        for width, length in SIZES:
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)
                self.assert_post_on_the_slat(length)


class TestPartMovesWithTheResize(ProbeFixture):
    def test_the_part_moved_and_turned_in_the_same_recompute(self):
        for index, (width, length) in enumerate(SIZES, 1):
            with self.subTest(width=width, length=length):
                self.part.Placement = App.Placement(
                    App.Vector(50 * index, -70 * index, 10 * index), App.Rotation(App.Vector(0, 0, 1), 30 + 25 * index)
                ).multiply(PART_PLACEMENT)
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                self.assert_slat_between_the_sides(self.doc, width)


class TestDocumentsAndDeletedTrims(ProbeFixture):
    def test_two_documents_with_the_same_names_keep_their_own_faces(self):
        first, second = self.reopen(self.doc), self.reopen(self.doc)
        self.assertEqual(
            [obj.Name for obj in first.Objects if obj.TypeId == "Part::FeaturePython"],
            [obj.Name for obj in second.Objects if obj.TypeId == "Part::FeaturePython"],
        )
        self.resize(first, 1200.0, 2300.0)
        self.assert_all_valid(first)
        self.assert_slat_between_the_sides(first, 1200.0)
        # The other one is as it was, and follows its own next size.
        self.assert_all_valid(second)
        self.assert_slat_between_the_sides(second, WIDTH)
        self.resize(second, 1000.0, 2100.0)
        self.assert_all_valid(second)
        self.assert_slat_between_the_sides(second, 1000.0)
        self.assert_slat_between_the_sides(first, 1200.0)

    def test_a_document_closed_and_another_opened_with_its_name_follows_its_own_faces(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "closed.FCStd")
        self.doc.saveCopy(path)
        first = App.openDocument(path)
        name = first.Name
        self.resize(first, 1200.0, 2300.0)
        App.closeDocument(name)
        again = App.openDocument(path)
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
        self.assertEqual(again.Name, name)
        self.resize(again, 1000.0, 2100.0)
        self.assert_all_valid(again)
        self.assert_slat_between_the_sides(again, 1000.0)

    def test_a_trim_deleted_and_made_again_on_another_face_ends_on_the_new_face(self):
        self.doc.UndoMode = 0
        name, first = self.trim.Name, self.trims[0]
        self.doc.removeObject(name)
        outer = self.face_towards(self.right, App.Vector(1, 0, 0))
        trim = make_extend_cut_profile(first, (self.right, (outer,)))
        self.assertEqual(trim.Name, name)
        part = self.part.getGlobalPlacement()
        across = part.Rotation.multVec(App.Vector(1, 0, 0))
        center = part.multVec(App.Vector(0, 0, 0)).dot(across)
        for width, length in ((WIDTH, LENGTH), (1200.0, 2300.0), (1000.0, 2100.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_all_valid(self.doc)
                slat = trim.Shape.transformed(part.toMatrix())
                reach = max(vertex.Point.dot(across) for vertex in slat.Vertexes)
                self.assertAlmostEqual(reach, center + width / 2.0 + HALF, places=PLACES)
                self.assertAlmostEqual(trim.Length.Value, width, places=PLACES)


class TestPanelEdit(ProbeFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def slat_reach(self, width):
        """Where the slat ends past the right side, in document coordinates, and where its outer face is."""
        part = self.part.getGlobalPlacement()
        across = part.Rotation.multVec(App.Vector(1, 0, 0))
        slat = self.trim.Shape.transformed(part.toMatrix())
        center = part.multVec(App.Vector(0, 0, 0)).dot(across)
        return max(vertex.Point.dot(across) for vertex in slat.Vertexes), center + width / 2.0 + HALF

    def assert_on_the_outer_face(self, width):
        self.assert_all_valid(self.doc)
        reach, outer = self.slat_reach(width)
        self.assertAlmostEqual(reach, outer, places=PLACES)

    def test_a_face_set_in_the_panel_is_followed_through_undo_and_redo(self):
        self.doc.UndoMode = 1
        self.doc.clearUndos()
        App.setActiveDocument(self.doc.Name)
        outer = self.face_towards(self.right, App.Vector(1, 0, 0))
        panel = ExtendCutTaskPanel(edited=self.trim)
        self.addCleanup(panel.clean)
        panel.set_target(self.right, (outer,))
        self.assertTrue(panel.accept())
        self.assert_on_the_outer_face(WIDTH)
        self.doc.openTransaction("resize")
        self.resize(self.doc, 1000.0, 2100.0)
        self.doc.commitTransaction()
        self.assert_on_the_outer_face(1000.0)
        for _ in range(2):
            self.doc.undo()
            self.doc.recompute()
        self.assert_all_valid(self.doc)
        self.assert_slat_between_the_sides(self.doc, WIDTH)
        for _ in range(2):
            self.doc.redo()
            self.doc.recompute()
        self.assert_on_the_outer_face(1000.0)
        for width, length in ((900.0, 1900.0), (1200.0, 2300.0)):
            with self.subTest(width=width, length=length):
                self.resize(self.doc, width, length)
                self.assert_on_the_outer_face(width)


if __name__ == "__main__":
    unittest.main()

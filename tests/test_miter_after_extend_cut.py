"""End Miter after Extend / Cut: a trimmed profile is mitered where its real stretch ends."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import keep_auto_preview, use_language
from PySide import QtCore, QtWidgets
from test_end_miter_geometry import CENTER, SIZE, MiterFixture
import test_end_miter_panel

from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.miter_geometry import real_stretch

HALF = SIZE / 2.0
# The crossbar C runs along Y from (CROSS_X, 0); the side A runs along X from 0 to 500.
CROSS_X = 300.0


class MiterAfterExtendCutFixture(MiterFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self.close_panels)

    # Reused helpers; the class itself is not imported, so its tests do not run again here.
    close_panels = test_end_miter_panel.TestEndMiterPanel.close_panels
    open_panel = test_end_miter_panel.TestEndMiterPanel.open_panel
    trims = test_end_miter_panel.TestEndMiterPanel.trims
    trim_of = test_end_miter_panel.TestEndMiterPanel.trim_of

    def profile(self, a, b, extension=0.0):
        return self.make_profile(self.make_sketch((a, b)), "Edge1", extension=extension, **CENTER)

    @staticmethod
    def face_towards(obj, direction):
        faces = [(index, face) for index, face in enumerate(obj.Shape.Faces, 1) if isinstance(face.Surface, Part.Plane)]
        index, _ = max(faces, key=lambda item: item[1].normalAt(0, 0).dot(direction))
        return f"Face{index}"

    def shortened_corner(self, extension=0.0):
        """Side A cut on the far face of crossbar C, keeping the piece beyond it: A_Tr runs from C to x = 500.

        The path of A still runs from 0 to 500, so its end nearest C is the wrong one (x = 500).
        """
        side = self.profile((0, 0, 0), (500, 0, 0), extension)
        crossbar = self.profile((CROSS_X, 0, 0), (CROSS_X, 300, 0))
        trim = make_extend_cut_profile(side, (crossbar, (self.face_towards(crossbar, App.Vector(1, 0, 0)),)))
        trim.KeepEnd = "End"
        self.doc.recompute()
        self.assertEqual(trim.getStatusString(), "Valid")
        self.assertAlmostEqual(trim.Shape.BoundBox.XMin, CROSS_X + HALF, places=5)
        self.assertAlmostEqual(trim.Shape.BoundBox.XMax, 500.0 + extension, places=5)
        self.doc.clearUndos()
        return side, crossbar, trim


class TestMiterAfterExtendCut(MiterAfterExtendCutFixture):
    def test_the_panel_finds_the_corner_of_a_shortened_profile_and_ok_miters_it(self):
        side, crossbar, trim = self.shortened_corner()
        panel = self.open_panel([trim, crossbar])
        self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
        self.assertTrue(panel.accept())
        side_miter, cross_miter = self.trim_of(trim), self.trim_of(crossbar)
        for obj in (side_miter, cross_miter):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertTrue(obj.Shape.isValid())
        # The corner is where both axes cross, (CROSS_X, 0): each profile reaches its outer edge there.
        box = side_miter.Shape.BoundBox
        self.assertAlmostEqual(box.XMin, CROSS_X - HALF, places=4)
        self.assertAlmostEqual(box.XMax, 500.0, places=4)
        box = cross_miter.Shape.BoundBox
        self.assertAlmostEqual(box.YMin, -HALF, places=4)
        self.assertAlmostEqual(box.YMax, 300.0, places=4)
        self.assertAlmostEqual(side_miter.Shape.common(cross_miter.Shape).Volume, 0.0, places=3)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_the_untouched_end_of_a_shortened_profile_with_end_offsets_keeps_its_reach(self):
        side, crossbar, trim = self.shortened_corner(extension=SIZE)
        panel = self.open_panel([trim, crossbar])
        self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
        self.assertTrue(panel.accept())
        box = self.trim_of(trim).Shape.BoundBox
        self.assertAlmostEqual(box.XMin, CROSS_X - HALF, places=4)
        self.assertAlmostEqual(box.XMax, 500.0 + SIZE, places=4)

    def test_a_miter_of_untrimmed_profiles_is_unchanged(self):
        side = self.profile((CROSS_X, 0, 0), (500, 0, 0))
        crossbar = self.profile((CROSS_X, 0, 0), (CROSS_X, 300, 0))
        panel = self.open_panel([side, crossbar])
        self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
        self.assertTrue(panel.accept())
        box = self.trim_of(side).Shape.BoundBox
        self.assertAlmostEqual(box.XMin, CROSS_X - HALF, places=4)
        self.assertAlmostEqual(box.XMax, 500.0, places=4)

    def test_a_profile_cut_back_at_its_end_is_mitered_there(self):
        side = self.profile((0, 0, 0), (500, 0, 0))
        crossbar = self.profile((CROSS_X, 0, 0), (CROSS_X, 300, 0))
        trim = make_extend_cut_profile(side, (crossbar, (self.face_towards(crossbar, App.Vector(-1, 0, 0)),)))
        self.doc.recompute()
        self.assertAlmostEqual(trim.Shape.BoundBox.XMax, CROSS_X - HALF, places=5)
        panel = self.open_panel([trim, crossbar])
        self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
        self.assertTrue(panel.accept())
        box = self.trim_of(trim).Shape.BoundBox
        self.assertAlmostEqual(box.XMin, 0.0, places=4)
        self.assertAlmostEqual(box.XMax, CROSS_X + HALF, places=4)

    def test_a_profile_trimmed_twice_is_mitered_where_the_last_trim_ends_it(self):
        side, crossbar, first = self.shortened_corner()
        stop = self.profile((450, 0, 0), (450, 300, 0))
        second = make_extend_cut_profile(first, (stop, (self.face_towards(stop, App.Vector(-1, 0, 0)),)))
        self.doc.recompute()
        self.assertAlmostEqual(second.Shape.BoundBox.XMax, 450 - HALF, places=5)
        panel = self.open_panel([second, crossbar])
        self.assertEqual(panel.members, [second, crossbar])
        self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
        self.assertTrue(panel.accept())
        box = self.trim_of(second).Shape.BoundBox
        self.assertAlmostEqual(box.XMin, CROSS_X - HALF, places=4)
        self.assertAlmostEqual(box.XMax, 450 - HALF, places=4)


class TestExistingMiters(MiterAfterExtendCutFixture):
    def test_a_miter_saved_on_a_shortened_trim_recomputes_at_its_real_end(self):
        # A document made before the fix holds the same objects: the miter recomputes on the real stretch.
        side, crossbar, trim = self.shortened_corner()
        miter = self.make_miter(trim, crossbar)
        partner = self.make_miter(crossbar, trim)
        self.doc.recompute()
        for obj in (miter, partner):
            self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(miter.Shape.BoundBox.XMin, CROSS_X - HALF, places=4)
        self.assertAlmostEqual(miter.Shape.common(partner.Shape).Volume, 0.0, places=3)

    def test_a_miter_at_an_end_the_trim_did_not_move_is_the_same_as_without_the_trim(self):
        corner = self.profile((0, 0, 0), (0, 300, 0))
        shapes = []
        for trimmed in (False, True):
            side = self.profile((0, 0, 0), (500, 0, 0), extension=SIZE)
            body = side
            if trimmed:
                stop = self.profile((400, -200, 0), (400, 200, 0))
                body = make_extend_cut_profile(side, (stop, (self.face_towards(stop, App.Vector(-1, 0, 0)),)))
                self.doc.recompute()
                self.assertAlmostEqual(body.Shape.BoundBox.XMax, 400 - HALF, places=5)
            miter = self.make_miter(body, corner)
            self.doc.recompute()
            self.assertEqual(miter.getStatusString(), "Valid")
            shapes.append(miter.Shape)
        plain, trimmed = shapes
        self.assertAlmostEqual(plain.BoundBox.XMin, trimmed.BoundBox.XMin, places=6)
        # Near the corner both miters are the same solid.
        near = Part.makeBox(200, 200, 200, App.Vector(-100, -100, -100))
        self.assertAlmostEqual(plain.common(near).Volume, trimmed.common(near).Volume, places=4)


class TestRealStretch(unittest.TestCase):
    def test_an_oblique_cut_of_a_round_tube_reaches_its_tip(self):
        edge = Part.LineSegment(App.Vector(0, 0, 0), App.Vector(200, 0, 0)).toShape()
        base = Part.makeCylinder(20, 200, App.Vector(0, 0, 0), App.Vector(1, 0, 0))
        # Remove x > 100 + y: the cut face is an ellipse whose tip, at y = 20, reaches x = 120.
        cutter = Part.makeBox(400, 400, 400, App.Vector(100, -200, -200))
        cutter.rotate(App.Vector(100, 0, 0), App.Vector(0, 0, 1), 45)
        shape = base.cut(cutter)
        stretch = real_stretch(edge, shape, base)
        self.assertAlmostEqual(stretch.Vertexes[0].Point.x, 0.0, places=6)
        self.assertAlmostEqual(stretch.Vertexes[-1].Point.x, 120.0, places=1)

    def test_a_curved_path_is_kept(self):
        arc = Part.ArcOfCircle(Part.Circle(App.Vector(), App.Vector(0, 0, 1), 100), 0, 1.5).toShape()
        base = Part.makeBox(10, 10, 10)
        self.assertIs(real_stretch(arc, base, base), arc)


class TestOneEntryPerProfile(MiterAfterExtendCutFixture):
    def test_a_profile_and_its_trim_are_listed_once_as_the_trim(self):
        side, crossbar, trim = self.shortened_corner()
        for members in ([side, trim, crossbar], [trim, side, crossbar]):
            with self.subTest(order=[obj.Name for obj in members]):
                panel = self.open_panel(members)
                self.assertEqual(panel.members, [trim, crossbar])
                widget = panel.form.members_list
                self.assertEqual(
                    [widget.item(row).text() for row in range(widget.count())],
                    [f"{trim.Label} ({trim.Name})", f"{crossbar.Label} ({crossbar.Name})"],
                )
                self.assertEqual(panel.form.message_label.text(), "1 joint will be created.")
                self.close_panels()

    def click(self, panel, obj, ctrl=False):
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            panel.addSelection(self.doc.Name, obj.Name, "Face1", None)

    def test_clicking_the_profile_under_a_listed_trim_changes_nothing(self):
        side, crossbar, trim = self.shortened_corner()
        panel = self.open_panel([trim, crossbar])
        self.click(panel, side)
        self.assertEqual(panel.members, [trim, crossbar])
        self.click(panel, side, ctrl=True)
        self.assertEqual(panel.members, [trim, crossbar])

    def test_clicking_a_trim_replaces_the_listed_profile_it_is_built_on(self):
        side, crossbar, trim = self.shortened_corner()
        panel = self.open_panel([side, crossbar])
        self.click(panel, trim)
        self.assertEqual(panel.members, [crossbar, trim])
        self.click(panel, trim, ctrl=True)
        self.assertEqual(panel.members, [crossbar])


if __name__ == "__main__":
    unittest.main()

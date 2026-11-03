"""End Miter after Extend / Cut: a trimmed profile is mitered where its real stretch ends."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import keep_auto_preview, use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER, SIZE, MiterFixture
import test_end_miter_panel

from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile

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


if __name__ == "__main__":
    unittest.main()

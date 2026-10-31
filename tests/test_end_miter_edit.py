"""End Miter on extruded cutouts, and editing an existing End Miter from the miter panel."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture

from freecad.maxproframe import create_end_miter_tool, create_trimmed_profiles_tool
from freecad.maxproframe.extruded_cutout import ExtrudedCutout


class TestEndMiterOnCutout(MiterFixture):
    def make_cutout(self, profile):
        # A hole through the middle of the profile, away from the corner.
        face_index = next(index for index, face in enumerate(profile.Shape.Faces, 1) if face.normalAt(0, 0).z > 0.99)
        box = profile.Shape.BoundBox
        sketch = self.doc.addObject("Sketcher::SketchObject", "CutSketch")
        sketch.Placement.Base = App.Vector(0, 0, box.ZMax)
        points = [App.Vector(90, -10, 0), App.Vector(110, -10, 0), App.Vector(110, 10, 0), App.Vector(90, 10, 0)]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(points[index], points[(index + 1) % 4]), False)
        cutout = self.doc.addObject("Part::FeaturePython", "ExtrudedCutout")
        ExtrudedCutout(cutout, sketch, (profile, (f"Face{face_index}",)))
        self.doc.recompute()
        self.assertEqual(cutout.getStatusString(), "Valid")
        return cutout

    def test_miter_with_a_cutout_body_or_boundary_recomputes(self):
        sketch = self.make_sketch(*CHAINED)
        p1 = self.make_profile(sketch, "Edge1", **CENTER)
        p2 = self.make_profile(sketch, "Edge2", **CENTER)
        cutout = self.make_cutout(p1)
        m1, m2 = self.make_miter(cutout, p2), self.make_miter(p2, cutout)
        self.doc.recompute()
        for obj in (m1, m2):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertTrue(obj.Shape.isValid())
        self.assertEqual(m1.PID, str(p1.PID))
        self.assertAlmostEqual(m1.Width.Value, 50.0)
        self.assert_perfect_joint(CHAINED, m1, m2)
        # The hole survives the miter of the cutout: two 20x20 openings in 2 mm walls.
        plain = self.make_miter(p1, p2)
        self.doc.recompute()
        self.assertAlmostEqual(plain.Shape.Volume - m1.Shape.Volume, 1600.0, places=3)


class TestEditEndMiter(MiterFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        QtWidgets.QApplication.processEvents()

    def pair(self, extend=True, gap=0.0):
        sketches = [self.make_sketch(edge) for edge in CHAINED]
        p1, p2 = (self.make_profile(sketch, "Edge1", **CENTER) for sketch in sketches)
        m1 = create_end_miter_tool.make_end_miter_profile(p1, [p2], extend, gap)
        m2 = create_end_miter_tool.make_end_miter_profile(p2, [p1], extend, gap)
        self.doc.recompute()
        self.doc.clearUndos()
        return (p1, p2), (m1, m2)

    def open_editor(self, obj, module, name):
        created = []
        base = getattr(module, name)

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(module, name, Recording):
            obj.ViewObject.Proxy.edit()
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def open_miter_editor(self, obj):
        return self.open_editor(obj, create_end_miter_tool, "EndMiterTaskPanel")

    def test_editing_an_end_miter_opens_the_miter_panel_with_its_values(self):
        (p1, p2), (m1, _) = self.pair(extend=False, gap=0.4)
        panel = self.open_miter_editor(m1)
        self.assertIsInstance(panel, create_end_miter_tool.EndMiterTaskPanel)
        self.assertEqual(panel.members, [p1, p2])
        self.assertEqual(panel.form.members_list.count(), 2)
        self.assertFalse(panel.form.cb_extend.isChecked())
        self.assertAlmostEqual(panel.form.sb_gap.value(), 0.4)
        self.assertFalse(panel.form.remove_button.isVisibleTo(panel.form))

    def test_ok_applies_extend_and_gap_to_both_sides_of_the_joint_in_one_step(self):
        _, (m1, m2) = self.pair()
        panel = self.open_miter_editor(m1)
        panel.form.cb_extend.setChecked(False)
        panel.form.sb_gap.setValue(0.5)
        self.assertTrue(panel.accept())
        self.assertFalse(Gui.Control.activeDialog())
        for obj in (m1, m2):
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertFalse(obj.MiterExtend)
            self.assertAlmostEqual(obj.MiterGap.Value, 0.5)
        self.assertAlmostEqual(m1.Shape.distToShape(m2.Shape)[0], 0.5, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        for obj in (m1, m2):
            self.assertTrue(obj.MiterExtend)
            self.assertAlmostEqual(obj.MiterGap.Value, 0.0)

    def test_cancel_restores_every_miter(self):
        _, (m1, m2) = self.pair(gap=0.2)
        volumes = [m1.Shape.Volume, m2.Shape.Volume]
        panel = self.open_miter_editor(m1)
        panel.form.cb_extend.setChecked(False)
        panel.form.sb_gap.setValue(3.0)
        self.assertTrue(panel.reject())
        self.assertFalse(Gui.Control.activeDialog())
        self.doc.recompute()
        for obj, volume in zip((m1, m2), volumes):
            self.assertTrue(obj.MiterExtend)
            self.assertAlmostEqual(obj.MiterGap.Value, 0.2)
            self.assertAlmostEqual(obj.Shape.Volume, volume, places=5)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_editing_an_end_trim_still_opens_the_trim_panel(self):
        (p1, p2), _ = self.pair()
        trim = create_trimmed_profiles_tool.TrimProfileCommand().make_trimmed_profile(p1, [(p2, ("Face1",))])
        self.doc.recompute()
        panel = self.open_editor(trim, create_trimmed_profiles_tool, "CreateTrimmedProfileTaskPanel")
        self.assertIsInstance(panel, create_trimmed_profiles_tool.CreateTrimmedProfileTaskPanel)
        self.assertEqual(panel.mode, "edition")
        self.assertTrue(panel.reject())


if __name__ == "__main__":
    unittest.main()

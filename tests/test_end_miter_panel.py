"""End Miter panel: always-active command, whole-profile selection and joints between many profiles."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from test_end_miter_geometry import CENTER, CHAINED, MiterFixture
from test_end_miter_translations import use_language

from freecad.maxproframe import create_end_miter_tool
from freecad.maxproframe.trimmed_profile import TrimmedProfile

RECTANGLE = (
    ((0, 0, 0), (300, 0, 0)),
    ((300, 0, 0), (300, 200, 0)),
    ((300, 200, 0), (0, 200, 0)),
    ((0, 200, 0), (0, 0, 0)),
)
# Three profiles meet at the origin; the second and fourth also form a corner at (0, 200).
THREE_AT_ORIGIN = (
    ((200, 0, 0), (0, 0, 0)),
    ((0, 0, 0), (0, 200, 0)),
    ((0, 0, 0), (-200, 0, 0)),
    ((0, 200, 0), (200, 200, 0)),
)


class TestEndMiterPanel(MiterFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        # Messages are asserted in English, whatever language earlier tests left behind.
        use_language(self, "English", "en_US")
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self.close_panels)
        self.corner = App.Vector()

    def close_panels(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            try:
                Gui.Selection.removeObserver(panel)
            except Exception:
                pass
        QtWidgets.QApplication.processEvents()

    def cut_face(self, shape, axis):
        # Each trim has two miter faces: take the one at the corner under test.
        faces = [
            f for f in shape.Faces if f.Surface.TypeId == "Part::GeomPlane" and abs(f.normalAt(0, 0).dot(axis)) > 1e-6
        ]
        return min(faces, key=lambda f: (f.CenterOfMass - self.corner).Length)

    def profiles(self, edges, **props):
        # One sketch per path: a sketch numbers its edges by wire, not by geometry order.
        sketches = [self.make_sketch(edge) for edge in edges]
        return sketches, [self.make_profile(sketch, "Edge1", **dict(CENTER, **props)) for sketch in sketches]

    def open_panel(self, members=()):
        panel = create_end_miter_tool.EndMiterTaskPanel(members)
        self.panels.append(panel)
        Gui.Selection.addObserver(panel)
        return panel

    def run_command(self):
        created = []
        base = create_end_miter_tool.EndMiterTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_end_miter_tool, "EndMiterTaskPanel", Recording):
            create_end_miter_tool.CreateEndMiterCommand().Activated()
        self.panels.extend(created)
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def trims(self):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "End Miter"]

    def trim_of(self, body):
        found = [obj for obj in self.trims() if obj.TrimmedBody == body]
        self.assertEqual(len(found), 1, body.Name)
        return found[0]

    @staticmethod
    def boundaries(trim):
        return {link[0].Name for link in trim.TrimmingBoundary}

    def test_command_is_active_with_a_document_and_no_selection(self):
        self.assertEqual(Gui.Selection.getSelectionEx(), [])
        self.assertTrue(create_end_miter_tool.CreateEndMiterCommand().IsActive())

    def test_preselected_profiles_are_preloaded(self):
        _, (p1, p2) = self.profiles(CHAINED)
        Gui.Selection.addSelection(self.doc.Name, p1.Name, "Face1")
        Gui.Selection.addSelection(self.doc.Name, p2.Name)
        panel = self.run_command()
        self.assertEqual(panel.members, [p1, p2])
        self.assertEqual(panel.form.members_list.count(), 2)

    def test_clicking_a_face_adds_the_whole_topmost_object(self):
        _, (p1, p2) = self.profiles(CHAINED)
        trimmed = self.doc.addObject("Part::FeaturePython", "Trim")
        TrimmedProfile(trimmed)
        trimmed.TrimmedBody = p2
        trimmed.TrimmingBoundary = [(p1, ("Face1",))]
        self.doc.recompute()
        panel = self.open_panel()
        Gui.Selection.addSelection(self.doc.Name, p1.Name, "Face3")
        Gui.Selection.addSelection(self.doc.Name, trimmed.Name, "Edge2")
        Gui.Selection.addSelection(self.doc.Name, p1.AttachmentSupport[0][0].Name, "Edge1")
        QtWidgets.QApplication.processEvents()
        self.assertEqual(panel.members, [p1, trimmed])
        selected = {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}
        self.assertEqual(selected, {p1.Name: (), trimmed.Name: ()})

    def test_ctrl_click_on_a_listed_profile_removes_it(self):
        _, (p1, p2) = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        QtWidgets.QApplication.processEvents()
        ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=ctrl):
            Gui.Selection.addSelection(self.doc.Name, p1.Name, "Face3")
            QtWidgets.QApplication.processEvents()
        self.assertEqual(panel.members, [p2])
        self.assertEqual(panel.form.members_list.count(), 1)
        selected = {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}
        self.assertEqual(selected, {p2.Name: ()})

    def test_deselecting_a_face_of_a_listed_profile_removes_it(self):
        _, (p1, p2) = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        QtWidgets.QApplication.processEvents()
        panel.removeSelection(self.doc.Name, p2.Name, "Face3")
        QtWidgets.QApplication.processEvents()
        self.assertEqual(panel.members, [p1])
        selected = {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}
        self.assertEqual(selected, {p1.Name: ()})

    def test_rectangle_creates_one_trim_per_profile_with_perfect_joints(self):
        _, members = self.profiles(RECTANGLE)
        panel = self.open_panel(members)
        self.assertIn("4 joints will be created", panel.form.message_label.text())
        self.assertTrue(panel.accept())
        self.assertEqual(len(self.trims()), 4)
        trims = [self.trim_of(p) for p in members]
        for index, trim in enumerate(trims):
            self.assertEqual(trim.getStatusString(), "Valid")
            neighbours = {members[index - 1].Name, members[(index + 1) % 4].Name}
            self.assertEqual(self.boundaries(trim), neighbours)
        for index in range(4):
            following = (index + 1) % 4
            self.corner = App.Vector(*RECTANGLE[index][1])
            with self.subTest(corner=self.corner):
                edges = (RECTANGLE[index], RECTANGLE[following])
                self.assert_perfect_joint(edges, trims[index], trims[following])

    def test_point_where_three_profiles_meet_is_skipped_and_reported(self):
        _, (p1, p2, p3, p4) = self.profiles(THREE_AT_ORIGIN)
        panel = self.open_panel([p1, p2, p3, p4])
        message = panel.form.message_label.text()
        self.assertIn("1 joint will be created", message)
        self.assertIn("Skipped (0.0, 0.0, 0.0)", message)
        self.assertIn("three or more profiles meet here and are not mitered", message)
        for profile in (p1, p2, p3):
            self.assertIn(profile.Label, message)
        self.assertTrue(panel.accept())
        self.assertEqual({trim.TrimmedBody.Name for trim in self.trims()}, {p2.Name, p4.Name})
        self.assertEqual(self.boundaries(self.trim_of(p2)), {p4.Name})
        self.assertEqual(self.boundaries(self.trim_of(p4)), {p2.Name})

    def test_extend_and_gap_values_are_applied(self):
        _, (p1, p2) = self.profiles(CHAINED)
        panel = self.open_panel([p1, p2])
        self.assertTrue(panel.form.cb_extend.isChecked())
        self.assertEqual(panel.form.sb_gap.value(), 0.0)
        self.assertEqual(panel.form.sb_gap.minimum(), 0.0)
        panel.form.cb_extend.setChecked(False)
        panel.form.sb_gap.setValue(0.5)
        self.assertTrue(panel.accept())
        for profile in (p1, p2):
            trim = self.trim_of(profile)
            self.assertFalse(trim.MiterExtend)
            self.assertAlmostEqual(trim.MiterGap.Value, 0.5)
        self.assertAlmostEqual(self.trim_of(p1).Shape.distToShape(self.trim_of(p2).Shape)[0], 0.5, places=5)

    def test_trims_stay_in_the_profile_container_inside_nested_parts(self):
        outer = self.doc.addObject("App::Part", "Outer")
        inner = self.doc.addObject("App::Part", "Inner")
        outer.addObject(inner)
        outer.Placement.Base = App.Vector(0, 500, 0)
        inner.Placement.Base = App.Vector(1000, 0, 0)
        sketches, members = self.profiles(CHAINED)
        inner.addObjects(sketches + members)
        self.doc.recompute()
        panel = self.open_panel(members)
        self.assertTrue(panel.accept())
        for profile in members:
            trim = self.trim_of(profile)
            self.assertEqual(trim.getParentGeoFeatureGroup(), inner)
            placed = trim.getParentGeoFeatureGroup().getGlobalPlacement().multVec(trim.Shape.BoundBox.Center)
            expected = inner.getGlobalPlacement().multVec(profile.Shape.BoundBox.Center)
            self.assertLess((placed - expected).Length, 60.0)

    def test_cancel_creates_nothing_and_stops_listening(self):
        _, (p1, p2) = self.profiles(CHAINED)
        before = len(self.doc.Objects)
        panel = self.open_panel([p1])
        self.assertTrue(panel.reject())
        Gui.Selection.addSelection(self.doc.Name, p2.Name, "Face1")
        self.assertEqual(len(self.doc.Objects), before)
        self.assertEqual(self.trims(), [])
        self.assertEqual(panel.members, [p1])

    def test_single_undo_removes_every_trim(self):
        _, members = self.profiles(RECTANGLE)
        undo_count = self.doc.UndoCount
        panel = self.open_panel(members)
        self.assertTrue(panel.accept())
        self.assertEqual(len(self.trims()), 4)
        self.assertEqual(self.doc.UndoCount, undo_count + 1)
        self.doc.undo()
        self.assertEqual(self.trims(), [])


if __name__ == "__main__":
    unittest.main()

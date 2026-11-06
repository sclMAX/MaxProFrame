"""Create a Parametric Line: two vertices are joined at once; any other vertices open the direction panel."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtWidgets

from freecad.maxproframe import expression_fields, parametric_line_panel
from freecad.maxproframe.parametric_line import CreateParametricLineCommand, make_line_from_vertex

# Corners of the frame sketch: a 400 x 200 rectangle at z = 0.
CORNERS = [(0, 0, 0), (400, 0, 0), (400, 200, 0), (0, 200, 0)]


class ParametricLinePanelFixture(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ParametricLinePanel")
        name = self.doc.Name
        App.setActiveDocument(name)
        Gui.ActiveDocument = Gui.getDocument(name)
        self.addCleanup(self.close)
        self.recorded = []
        recorded = self.recorded

        class Recording(parametric_line_panel.ParametricLineTaskPanel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(parametric_line_panel, "ParametricLineTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Frame")
        for start, end in zip(CORNERS, CORNERS[1:] + CORNERS[:1]):
            self.sketch.addGeometry(Part.LineSegment(App.Vector(*start), App.Vector(*end)))
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Placement.Base = App.Vector(1000, 0, 0)
        self.doc.recompute()
        self.doc.clearUndos()

    def close(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        self.events()
        Gui.Selection.clearSelection()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def corner(self, point):
        """Name of the sketch vertex at ``point``."""
        for index, vertex in enumerate(self.sketch.Shape.Vertexes, 1):
            if vertex.Point.isEqual(App.Vector(*point), 1e-6):
                return f"Vertex{index}"
        raise AssertionError(f"no sketch vertex at {point}")

    def select(self, *items):
        Gui.Selection.clearSelection()
        for obj, sub in items:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)

    def run_command(self, *items):
        """Run the command on ``items``: the panel it opens, or None."""
        self.select(*items)
        count = len(self.recorded)
        self.assertTrue(CreateParametricLineCommand().IsActive())
        CreateParametricLineCommand().Activated()
        self.events()
        return self.recorded[-1] if len(self.recorded) > count else None

    def lines(self):
        return [obj for obj in self.doc.Objects if obj.Name.startswith("ParametricLine")]

    def ends(self, line):
        return [tuple(round(c, 6) for c in v.Point) for v in line.Shape.Vertexes]

    def corners(self, *points):
        return [(self.sketch, self.corner(point)) for point in points]


class TestCommandRouting(ParametricLinePanelFixture):
    def test_two_vertices_of_different_objects_are_joined_at_once(self):
        panel = self.run_command(*self.corners(CORNERS[0]), (self.box, "Vertex1"))
        self.assertIsNone(panel)
        self.assertFalse(Gui.Control.activeDialog())
        [line] = self.lines()
        self.assertEqual(line.Direction, "Vertex2")
        self.assertEqual(self.ends(line), [(0, 0, 0), (1000, 0, 10)])

    def test_two_vertices_of_one_object_that_is_not_a_sketch_are_joined_at_once(self):
        self.assertIsNone(self.run_command((self.box, "Vertex1"), (self.box, "Vertex8")))
        [line] = self.lines()
        self.assertEqual(line.Direction, "Vertex2")

    def test_two_vertices_of_the_same_sketch_one_vertex_or_more_open_the_panel(self):
        for points in ((CORNERS[0], CORNERS[1]), (CORNERS[2],), tuple(CORNERS)):
            with self.subTest(count=len(points)):
                panel = self.run_command(*self.corners(*points))
                self.assertIsNotNone(panel)
                self.assertTrue(Gui.Control.activeDialog())
                self.assertEqual(len(panel.lines), len(points))
                self.assertTrue(panel.reject())
                self.events()
                self.assertEqual(self.lines(), [])

    def test_three_vertices_of_different_objects_open_the_panel(self):
        panel = self.run_command(*self.corners(CORNERS[0], CORNERS[1]), (self.box, "Vertex1"))
        self.assertEqual(len(panel.lines), 3)
        self.assertTrue(panel.reject())

    def test_the_command_needs_a_selected_vertex(self):
        Gui.Selection.clearSelection()
        self.assertFalse(CreateParametricLineCommand().IsActive())
        Gui.Selection.addSelection(self.doc.Name, self.box.Name, "Edge1")
        self.assertFalse(CreateParametricLineCommand().IsActive())


class TestCreatePanel(ParametricLinePanelFixture):
    def test_four_corners_preview_one_leg_each_and_ok_keeps_them_in_one_undo_step(self):
        panel = self.run_command(*self.corners(*CORNERS))
        self.assertEqual(panel.direction(), "-Z")
        self.assertEqual([self.ends(line)[1] for line in panel.lines], [(x, y, -1000) for x, y, _ in CORNERS])
        panel.form.spin_length.setValue(720)
        self.assertEqual([self.ends(line) for line in panel.lines], [[c, (c[0], c[1], -720)] for c in CORNERS])
        self.assertTrue(panel.accept())
        self.events()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(len(self.lines()), 4)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.lines(), [])

    def test_each_axis_and_a_custom_vector(self):
        panel = self.run_command(*self.corners(CORNERS[1]))
        combo = panel.form.combo_direction
        self.assertEqual(
            [combo.itemData(i) for i in range(combo.count())], ["+X", "-X", "+Y", "-Y", "+Z", "-Z", "Custom"]
        )
        panel.form.spin_length.setValue(10)
        combo.setCurrentIndex(combo.findData("+Y"))
        self.assertFalse(panel.form.spin_x.isEnabled())
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (400, 10, 0)])
        combo.setCurrentIndex(combo.findData("Custom"))
        self.assertTrue(panel.form.spin_x.isEnabled())
        panel.form.spin_z.setValue(0)
        self.assertEqual(panel.form.status_label.text(), "The custom vector is zero: give X, Y or Z.")
        panel.form.spin_x.setValue(3)
        panel.form.spin_z.setValue(-4)
        self.assertEqual(panel.form.status_label.text(), "")
        self.assertTrue(panel.accept())
        [line] = self.lines()
        self.assertEqual((line.Direction, line.CustomDirection), ("Custom", App.Vector(3, 0, -4)))
        self.assertEqual(self.ends(line), [(400, 0, 0), (406, 0, -8)])

    def test_cancel_leaves_no_line_and_no_undo_step(self):
        for undo_mode in (1, 0):
            with self.subTest(undo_mode=undo_mode):
                self.doc.UndoMode = undo_mode
                self.addCleanup(setattr, self.doc, "UndoMode", 1)
                panel = self.run_command(*self.corners(*CORNERS))
                panel.form.spin_length.setValue(500)
                self.assertTrue(panel.reject())
                self.events()
                self.assertEqual(self.lines(), [])
                self.assertEqual(self.doc.UndoCount, 0)
                self.assertFalse(Gui.Control.activeDialog())

    def test_the_length_expression_is_given_to_every_line(self):
        panel = self.run_command(*self.corners(CORNERS[0], CORNERS[1]))
        # What the Fx editor of the Length field does: it sets the expression on the line it is bound to.
        panel.lines[0].setExpression("Length", "Box.Height * 72")
        panel.form.spin_length.setValue(720)
        self.assertTrue(panel.accept())
        for line in self.lines():
            self.assertEqual(expression_fields.expression_of(line, "Length"), "Box.Height * 72")
        self.box.Height = 5
        self.doc.recompute()
        self.assertEqual([self.ends(line)[1] for line in self.lines()], [(0, 0, -360), (400, 0, -360)])

    def test_the_panel_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command(*self.corners(CORNERS[0]))
        combo = panel.form.combo_direction
        self.assertEqual(panel.form.windowTitle(), "Línea paramétrica")
        self.assertEqual(combo.itemText(combo.findData("Custom")), "Vector personalizado")
        self.assertTrue(panel.reject())


class TestEditPanel(ParametricLinePanelFixture):
    def leg(self):
        line = make_line_from_vertex((self.sketch, self.corner(CORNERS[2])), "-Z", 700)
        self.doc.clearUndos()
        return line

    def edit(self, obj):
        count = len(self.recorded)
        Gui.getDocument(self.doc.Name).setEdit(obj, 0)
        self.events()
        self.assertEqual(len(self.recorded), count + 1)
        self.assertTrue(Gui.Control.activeDialog())
        return self.recorded[-1]

    def test_double_click_shows_the_values_and_ok_keeps_the_change_in_one_undo_step(self):
        line = self.leg()
        panel = self.edit(line)
        self.assertEqual((panel.direction(), panel.form.spin_length.value()), ("-Z", 700))
        panel.form.spin_length.setValue(750)
        self.assertTrue(panel.accept())
        self.events()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(Gui.getDocument(self.doc.Name).getInEdit())
        self.assertEqual(self.ends(line), [(400, 200, 0), (400, 200, -750)])
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(line.Length.Value, 700)

    def test_cancel_restores_the_line(self):
        for undo_mode in (1, 0):
            with self.subTest(undo_mode=undo_mode):
                line = self.leg()
                self.doc.UndoMode = undo_mode
                self.addCleanup(setattr, self.doc, "UndoMode", 1)
                panel = self.edit(line)
                combo = panel.form.combo_direction
                combo.setCurrentIndex(combo.findData("+X"))
                panel.form.spin_length.setValue(10)
                self.assertTrue(panel.reject())
                self.events()
                self.assertEqual((line.Direction, line.Length.Value), ("-Z", 700))
                self.assertEqual(self.ends(line), [(400, 200, 0), (400, 200, -700)])
                self.assertEqual(self.doc.UndoCount, 0)

    def test_a_line_joining_two_vertices_opens_no_panel(self):
        CreateParametricLineCommand().make_parametric_line(
            [(self.sketch, self.corner(CORNERS[0])), (self.box, "Vertex1")]
        )
        line = self.doc.ActiveObject
        Gui.getDocument(self.doc.Name).setEdit(line, 0)
        self.events()
        self.assertEqual(self.recorded, [])


if __name__ == "__main__":
    unittest.main()

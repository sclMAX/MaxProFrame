"""Create a Parametric Line: two vertices are joined at once; any other vertices, or none, open the direction panel.

While a new-line panel is open, a click on a vertex adds a line from it and a second click removes it.
"""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtGui, QtWidgets

from freecad.maxproframe import expression_fields, parametric_line_panel
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.parametric_line import CreateParametricLineCommand, make_line_from_vertex

# Corners of the frame sketch: a 400 x 200 rectangle at z = 0.
CORNERS = [(0, 0, 0), (400, 0, 0), (400, 200, 0), (0, 200, 0)]
# Values a new-line panel remembers from its last OK: strings, then floats.
STRING_PARAMS = ("Parametric Line Direction", "Parametric Line Plane")
FLOAT_PARAMS = (
    "Parametric Line Length",
    "Parametric Line Angle",
    "Parametric Line Custom X",
    "Parametric Line Custom Y",
    "Parametric Line Custom Z",
)
NOT_A_VERTEX = "Click a vertex: only a vertex starts a line."


def keep_remembered_values(test):
    """Start ``test`` with no remembered direction, vector or length and put back the stored ones after it."""
    param = get_param_group(writable=True)
    kinds = ((STRING_PARAMS, param.GetStrings, param.GetString, param.SetString, param.RemString, ""),)
    kinds += ((FLOAT_PARAMS, param.GetFloats, param.GetFloat, param.SetFloat, param.RemFloat, 0.0),)
    saved = []
    for names, listed, get, put, remove, empty in kinds:
        for name in names:
            saved.append((name, name in listed(), get(name, empty), put, remove))

    def restore():
        for name, stored, value, put, remove in saved:
            if stored:
                put(name, value)
            else:
                remove(name)

    test.addCleanup(restore)
    for name, _, _, _, remove in saved:
        remove(name)


class OtherDialog:
    """Another task dialog, open while the command runs."""

    def __init__(self):
        self.form = QtGui.QWidget()

    def accept(self):
        return True

    def reject(self):
        return True


class ParametricLinePanelFixture(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ParametricLinePanel")
        name = self.doc.Name
        App.setActiveDocument(name)
        Gui.ActiveDocument = Gui.getDocument(name)
        self.addCleanup(self.close)
        keep_remembered_values(self)
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

    def click(self, obj, sub):
        """A click on ``sub`` of ``obj`` in the 3D view."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        self.events()

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

    def test_the_command_is_enabled_whenever_a_document_is_open(self):
        Gui.Selection.clearSelection()
        self.assertTrue(CreateParametricLineCommand().IsActive())
        Gui.Selection.addSelection(self.doc.Name, self.box.Name, "Edge1")
        self.assertTrue(CreateParametricLineCommand().IsActive())

    def test_another_open_task_dialog_leaves_no_line_and_no_open_transaction(self):
        other = OtherDialog()
        Gui.Control.showDialog(other)
        for items in ((), self.corners(CORNERS[0]), (*self.corners(CORNERS[0]), (self.box, "Vertex1"))):
            with self.subTest(count=len(items)):
                self.select(*items)
                CreateParametricLineCommand().Activated()
                self.events()
                self.assertEqual(self.recorded, [])
                self.assertEqual(self.lines(), [])
                self.assertFalse(self.doc.HasPendingTransaction)
                self.assertEqual(self.doc.UndoCount, 0)
                self.assertTrue(Gui.Control.activeDialog())


class TestPickVertices(ParametricLinePanelFixture):
    def test_with_no_vertex_selected_the_panel_opens_empty_and_ok_leaves_no_undo_step(self):
        for items in ((), ((self.box, "Edge1"),)):
            with self.subTest(count=len(items)):
                panel = self.run_command(*items)
                self.assertIsNotNone(panel)
                self.assertEqual(panel.lines, [])
                self.assertTrue(panel.accept())
                self.events()
                self.assertFalse(Gui.Control.activeDialog())
                self.assertEqual(self.lines(), [])
                self.assertFalse(self.doc.HasPendingTransaction)
                self.assertEqual(self.doc.UndoCount, 0)

    def test_a_click_on_a_vertex_adds_a_line_and_a_second_click_removes_it(self):
        panel = self.run_command()
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.click(self.box, "Vertex1")
        self.assertEqual(
            [self.ends(line) for line in self.lines()], [[(0, 0, 0), (0, 0, -100)], [(1000, 0, 10), (1000, 0, -90)]]
        )
        self.click(self.sketch, self.corner(CORNERS[0]))
        [line] = self.lines()
        self.assertEqual(panel.lines, [line])
        self.assertEqual(self.ends(line), [(1000, 0, 10), (1000, 0, -90)])
        # The start of a previewed line lies on its vertex: a click there removes that line too.
        self.click(self.sketch, self.corner(CORNERS[1]))
        self.click(panel.lines[-1], "Vertex1")
        self.assertEqual(panel.lines, [line])
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.lines(), [line])
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.lines(), [])

    def test_a_click_on_a_vertex_inside_a_part_starts_the_line_on_that_vertex(self):
        part = self.doc.addObject("App::Part", "Holder")
        part.Placement.Base = App.Vector(0, 0, 500)
        inner = self.doc.addObject("Part::Box", "Inner")
        part.addObject(inner)
        self.doc.recompute()
        panel = self.run_command()
        self.click(part, f"{inner.Name}.Vertex1")
        [line] = panel.lines
        self.assertEqual(line.Vertex1, (inner, ["Vertex1"]))
        self.assertEqual(self.ends(line), [(0, 0, 510), (0, 0, 410)])
        self.assertTrue(panel.reject())

    def test_a_preselected_vertex_starts_a_line_and_its_click_removes_it(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        self.assertEqual(len(panel.lines), 1)
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertEqual(panel.lines, [])
        self.assertEqual(self.lines(), [])
        self.assertTrue(panel.reject())

    def test_a_click_on_anything_else_adds_nothing_and_asks_for_a_vertex(self):
        panel = self.run_command()
        for sub in ("Edge1", "Face1", ""):
            with self.subTest(sub=sub):
                self.click(self.box, sub)
                self.assertEqual(self.lines(), [])
                self.assertEqual(panel.form.status_label.text(), NOT_A_VERTEX)
        self.click(self.box, "Vertex1")
        self.assertEqual(len(self.lines()), 1)
        self.assertEqual(panel.form.status_label.text(), "")
        self.assertTrue(panel.reject())
        self.events()
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.doc.UndoCount, 0)

    def test_the_length_field_follows_the_first_remaining_line(self):
        panel = self.run_command()
        binding = Gui.ExpressionBinding(panel.form.spin_length)
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.click(self.sketch, self.corner(CORNERS[1]))
        self.assertTrue(binding.isBound())
        self.click(self.sketch, self.corner(CORNERS[0]))
        [line] = panel.lines
        # What the Fx editor does: it sets the expression on the line the field is bound to.
        line.setExpression("Length", "Box.Height * 3")
        self.doc.recompute()
        self.assertTrue(binding.hasExpression())
        self.assertAlmostEqual(panel.form.spin_length.value(), 30, places=6)
        # The expression goes to the lines added next.
        self.click(self.sketch, self.corner(CORNERS[2]))
        self.assertEqual(
            [expression_fields.expression_of(line, "Length") for line in panel.lines], ["Box.Height * 3"] * 2
        )
        self.assertTrue(panel.accept())
        self.assertEqual([self.ends(line)[1] for line in self.lines()], [(400, 0, -30), (400, 200, -30)])

    def test_clicks_once_the_panel_is_closed_add_nothing(self):
        panel = self.run_command()
        self.assertTrue(panel.accept())
        self.events()
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.doc.UndoCount, 0)


class TestRememberedValues(ParametricLinePanelFixture):
    def test_a_new_panel_starts_at_100_mm_along_minus_z_the_first_time(self):
        panel = self.run_command(*self.corners(CORNERS[2]))
        self.assertEqual((panel.direction(), panel.form.spin_length.value()), ("-Z", 100))
        self.assertEqual(self.ends(panel.lines[0]), [(400, 200, 0), (400, 200, -100)])
        self.assertTrue(panel.reject())

    def test_a_new_panel_starts_with_the_values_last_confirmed_with_ok(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        combo = panel.form.combo_direction
        combo.setCurrentIndex(combo.findData("Custom"))
        panel.form.spin_x.setValue(3)
        panel.form.spin_z.setValue(-4)
        panel.form.spin_length.setValue(250)
        self.assertTrue(panel.accept())
        self.events()
        # Cancel, or OK on a line being edited, does not change what a new panel starts with.
        panel = self.run_command()
        combo = panel.form.combo_direction
        combo.setCurrentIndex(combo.findData("+X"))
        panel.form.spin_length.setValue(50)
        self.assertTrue(panel.reject())
        self.events()
        leg = make_line_from_vertex((self.sketch, self.corner(CORNERS[3])), "+Y", 70)
        Gui.getDocument(self.doc.Name).setEdit(leg, 0)
        self.events()
        self.recorded[-1].form.spin_length.setValue(80)
        self.assertTrue(self.recorded[-1].accept())
        self.events()
        panel = self.run_command()
        form = panel.form
        self.assertEqual(panel.direction(), "Custom")
        self.assertEqual((form.spin_x.value(), form.spin_y.value(), form.spin_z.value()), (3, 0, -4))
        self.assertEqual(form.spin_length.value(), 250)
        self.click(self.sketch, self.corner(CORNERS[1]))
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (550, 0, -200)])
        self.assertTrue(panel.reject())


class TestCreatePanel(ParametricLinePanelFixture):
    def test_four_corners_preview_one_leg_each_and_ok_keeps_them_in_one_undo_step(self):
        panel = self.run_command(*self.corners(*CORNERS))
        self.assertEqual(panel.direction(), "-Z")
        self.assertEqual([self.ends(line)[1] for line in panel.lines], [(x, y, -100) for x, y, _ in CORNERS])
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
            [combo.itemData(i) for i in range(combo.count())], ["+X", "-X", "+Y", "-Y", "+Z", "-Z", "Angle", "Custom"]
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

    def test_an_angle_in_a_global_plane(self):
        panel = self.run_command(*self.corners(CORNERS[1]))
        form = panel.form
        self.assertEqual([form.combo_plane.itemData(i) for i in range(form.combo_plane.count())], ["XY", "XZ", "YZ"])
        self.assertFalse(form.combo_plane.isEnabled())
        self.assertFalse(form.spin_angle.isEnabled())
        form.spin_length.setValue(10)
        form.combo_direction.setCurrentIndex(form.combo_direction.findData("Angle"))
        self.assertTrue(form.combo_plane.isEnabled())
        self.assertTrue(form.spin_angle.isEnabled())
        self.assertFalse(form.spin_x.isEnabled())
        self.assertEqual(form.angle_hint.text(), "0° = +X, 90° = +Y")
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (410, 0, 0)])
        form.combo_plane.setCurrentIndex(form.combo_plane.findData("YZ"))
        self.assertEqual(form.angle_hint.text(), "0° = +Y, 90° = +Z")
        form.spin_angle.setValue(-90)
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (400, 0, -10)])
        self.assertTrue(panel.accept())
        [line] = self.lines()
        self.assertEqual((line.Direction, line.Plane, line.Angle.Value), ("Angle", "YZ", -90))
        self.assertEqual(line.CustomDirection, App.Vector(0, 0, -1))

    def test_a_new_panel_remembers_the_plane_and_the_angle(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        self.assertEqual((panel.form.combo_plane.currentData(), panel.form.spin_angle.value()), ("XY", 0))
        panel.form.combo_direction.setCurrentIndex(panel.form.combo_direction.findData("Angle"))
        panel.form.combo_plane.setCurrentIndex(panel.form.combo_plane.findData("XZ"))
        panel.form.spin_angle.setValue(45)
        self.assertTrue(panel.accept())
        self.events()
        panel = self.run_command()
        self.assertEqual(panel.direction(), "Angle")
        self.assertEqual((panel.form.combo_plane.currentData(), panel.form.spin_angle.value()), ("XZ", 45))
        self.assertTrue(panel.reject())

    def test_the_angle_expression_is_given_to_every_line(self):
        panel = self.run_command(*self.corners(CORNERS[0], CORNERS[1]))
        panel.form.combo_direction.setCurrentIndex(panel.form.combo_direction.findData("Angle"))
        panel.form.spin_length.setValue(10)
        # What the Fx editor of the Angle field does: it sets the expression on the line it is bound to.
        panel.lines[0].setExpression("Angle", "Box.Height * 9")
        panel.form.spin_angle.setValue(5)
        self.assertTrue(panel.accept())
        for line in self.lines():
            self.assertEqual(expression_fields.expression_of(line, "Angle"), "Box.Height * 9")
        self.assertEqual([self.ends(line)[1] for line in self.lines()], [(0, 10, 0), (400, 10, 0)])

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
        self.assertEqual(combo.itemText(combo.findData("Angle")), "Ángulo en un plano")
        combo.setCurrentIndex(combo.findData("Angle"))
        self.assertEqual(panel.form.angle_hint.text(), "0° = +X, 90° = +Y")
        self.click(self.box, "Edge1")
        self.assertEqual(panel.form.status_label.text(), "Hacé clic en un vértice: solo un vértice inicia una línea.")
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

    def test_another_open_task_dialog_leaves_no_edit_and_no_open_transaction(self):
        line = self.leg()
        Gui.Control.showDialog(OtherDialog())
        Gui.getDocument(self.doc.Name).setEdit(line, 0)
        self.events()
        self.assertEqual(self.recorded, [])
        self.assertFalse(self.doc.HasPendingTransaction)
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

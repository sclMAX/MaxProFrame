"""Create a Parametric Line: two vertices are joined at once; any other vertices, or none, open the direction panel.

While a new-line panel is open, a click on a vertex adds a line from it and a second click removes it.
"""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import deliver_language_change, use_language
from PySide import QtGui, QtWidgets

from freecad.maxproframe import expression_fields, parametric_line_drag, parametric_line_panel
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
        # A language change an earlier test left pending would put back the standard text of Apply.
        deliver_language_change()
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
        self.assertTrue(panel.form.hint_label.text().startswith("Hacé clic en un vértice para agregar una línea"))
        self.assertIn("presioná P", panel.form.hint_label.text())
        self.click(self.box, "Edge1")
        self.assertEqual(panel.form.status_label.text(), "Hacé clic en un vértice: solo un vértice inicia una línea.")
        self.assertTrue(panel.reject())


class TestDragInAPlane(ParametricLinePanelFixture):
    """The cursor point in the plane comes from the 3D view; here drag_to gets it directly."""

    def fields(self, panel):
        form = panel.form
        return panel.direction(), form.combo_plane.currentData(), form.spin_angle.value(), form.spin_length.value()

    def test_a_click_on_a_plane_drags_every_line_and_a_second_click_fixes_them(self):
        panel = self.run_command(*self.corners(CORNERS[0], CORNERS[1]))
        panel.start_drag("XZ")
        self.assertEqual(panel.drag_plane, "XZ")
        self.assertTrue(panel.form.plane_buttons["XZ"].isChecked())
        self.assertFalse(panel.form.plane_buttons["XY"].isChecked())
        # Measured from the start of the newest line.
        panel.drag_to(App.Vector(400, 0, -704))
        self.assertEqual(panel.direction(), "-Z")
        self.assertEqual(panel.form.spin_length.value(), 700)
        self.assertEqual([self.ends(line) for line in panel.lines], [[c, (c[0], c[1], -700)] for c in CORNERS[:2]])
        panel.finish_drag()
        self.assertIsNone(panel.drag_plane)
        self.assertFalse(panel.form.plane_buttons["XZ"].isChecked())
        panel.drag_to(App.Vector(400, 0, -50))
        self.assertEqual(panel.form.spin_length.value(), 700)
        self.assertTrue(panel.accept())
        self.assertEqual([(line.Direction, line.Length.Value) for line in self.lines()], [("-Z", 700)] * 2)

    def test_a_way_off_the_axes_is_an_angle_in_the_plane_and_shift_snaps_to_1_mm(self):
        panel = self.run_command(*self.corners(CORNERS[1]))
        panel.start_drag("XZ")
        panel.drag_to(App.Vector(483.9, 0, 54.5))
        self.assertEqual(self.fields(panel), ("Angle", "XZ", 30, 100))
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (486.60254, 0, 50)])
        panel.drag_to(App.Vector(400 + 234.6, 0, 0), fine=True)
        self.assertEqual(self.fields(panel)[::3], ("+X", 235))
        panel.finish_drag()
        self.assertTrue(panel.accept())

    def test_cancel_puts_back_the_values_and_expressions_and_keeps_the_panel_open(self):
        panel = self.run_command(*self.corners(CORNERS[1]))
        panel.lines[0].setExpression("Length", "Box.Height * 10")
        self.doc.recompute()
        panel.start_drag("XY")
        panel.drag_to(App.Vector(630, 3, 0))
        self.assertEqual((panel.direction(), panel.form.spin_length.value()), ("+X", 230))
        self.assertIsNone(expression_fields.expression_of(panel.lines[0], "Length"))
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (630, 0, 0)])
        panel.cancel_drag()
        self.assertIsNone(panel.drag_plane)
        self.assertEqual(panel.direction(), "-Z")
        self.assertEqual(expression_fields.expression_of(panel.lines[0], "Length"), "Box.Height * 10")
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (400, 0, -100)])
        self.assertTrue(Gui.Control.activeDialog())
        self.assertTrue(panel.reject())

    def test_p_and_the_plane_buttons_choose_the_plane(self):
        panel = self.run_command(*self.corners(CORNERS[1]))
        planes = []
        for _ in range(4):
            panel.cycle_plane()
            planes.append(panel.drag_plane)
        self.assertEqual(planes, ["XY", "XZ", "YZ", "XY"])
        panel.form.plane_buttons["YZ"].click()
        self.assertEqual(panel.drag_plane, "YZ")
        panel.cancel_drag()
        panel.form.plane_buttons["XZ"].click()
        self.assertEqual(panel.drag_plane, "XZ")
        self.assertTrue(panel.reject())

    def test_with_no_line_there_is_nothing_to_drag(self):
        panel = self.run_command()
        panel.cycle_plane()
        panel.start_drag("XY")
        self.assertIsNone(panel.drag_plane)
        self.assertFalse(panel.form.plane_buttons["XY"].isEnabled())
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertTrue(panel.form.plane_buttons["XY"].isEnabled())
        self.assertTrue(panel.reject())

    def test_the_drag_measures_from_the_newest_line_whose_vertex_is_still_there(self):
        # R3-004: a newest line that lost its vertex does not stop the drag of the others.
        panel = self.run_command(*self.corners(CORNERS[0], CORNERS[1]))
        panel.lines[-1].Vertex1 = None
        self.assertEqual(panel.drag_anchor(), App.Vector(0, 0, 0))
        panel.start_drag("XY")
        self.assertEqual(panel.drag_plane, "XY")
        panel.drag_to(App.Vector(0, 236, 0))
        self.assertEqual((panel.direction(), panel.form.spin_length.value()), ("+Y", 240))
        self.assertEqual(self.ends(panel.lines[0]), [(0, 0, 0), (0, 240, 0)])
        self.assertTrue(panel.reject())

    def test_a_line_being_edited_is_not_dragged(self):
        leg = make_line_from_vertex((self.sketch, self.corner(CORNERS[3])), "+Y", 70)
        Gui.getDocument(self.doc.Name).setEdit(leg, 0)
        self.events()
        panel = self.recorded[-1]
        self.assertFalse(hasattr(panel.form, "plane_buttons"))
        panel.start_drag("XY")
        self.assertIsNone(panel.drag_plane)
        self.assertTrue(panel.reject())


class FakeView:
    """A top view, 1 mm per pixel, with its screen origin at the global origin."""

    def __init__(self):
        from pivy import coin

        self.scene = coin.SoSeparator()
        self.callbacks = {}

    def getPoint(self, x, y):
        return App.Vector(x, y, 0)

    def getPointOnViewport(self, point):
        return (point.x, point.y)

    def getViewDirection(self):
        return App.Vector(0, 0, -1)

    def getCameraNode(self):
        from pivy import coin

        return coin.SoOrthographicCamera()

    def getSceneGraph(self):
        return self.scene

    def addEventCallbackPivy(self, event_type, handler):
        self.callbacks[str(event_type.getName().getString())] = handler
        return handler

    def removeEventCallbackPivy(self, event_type, callback):
        self.callbacks.pop(str(event_type.getName().getString()), None)


class FakeEvent:
    def __init__(self, position=(0, 0), button=None, down=True, key=None, shift=False):
        from pivy import coin

        self.position, self.button, self.key, self.shift = position, button, key, shift
        self.state = coin.SoButtonEvent.DOWN if down else coin.SoButtonEvent.UP

    def getPosition(self):
        position = self.position

        class Position:
            def getValue(self):
                return position

        return Position()

    def getButton(self):
        return self.button

    def getState(self):
        return self.state

    def getKey(self):
        return self.key

    def wasShiftDown(self):
        return self.shift


class FakeCallback:
    def __init__(self, event):
        self.event = event
        self.handled = False

    def getEvent(self):
        return self.event

    def setHandled(self):
        self.handled = True


class TestDragInTheView(ParametricLinePanelFixture):
    def setUp(self):
        super().setUp()
        from pivy import coin

        self.coin = coin
        self.panel = self.run_command(*self.corners(CORNERS[1]))
        self.view = FakeView()
        self.panel.view_drag = parametric_line_drag.ViewDrag(self.panel, self.view)
        self.panel.view_drag.listen()

    def send(self, kind, **event):
        callback = FakeCallback(FakeEvent(**event))
        self.view.callbacks[kind](callback)
        return callback.handled

    def mouse(self, position, button=None, down=True, shift=False):
        button = self.coin.SoMouseButtonEvent.BUTTON1 if button is None else button
        return self.send("SoMouseButtonEvent", position=position, button=button, down=down, shift=shift)

    def test_the_squares_stay_while_the_drag_moves_and_change_with_the_plane(self):
        # R3-002: a move that changes nothing visible leaves the squares in the scene as they are.
        self.assertTrue(self.mouse((420, 20)))
        # Coin node wrappers do not compare by identity: the drawn squares are told by a name.
        self.view.scene.getChild(0).setName("drawn")
        for y in (60, 120, 236):
            self.send("SoLocation2Event", position=(400, y))
        self.assertEqual(self.panel.form.spin_length.value(), 240)
        self.assertEqual(self.view.scene.getNumChildren(), 1)
        self.assertEqual(self.view.scene.getChild(0).getName().getString(), "drawn")
        self.panel.form.plane_buttons["XZ"].click()
        self.assertEqual(self.panel.drag_plane, "XZ")
        self.assertEqual(self.view.scene.getNumChildren(), 1)
        self.assertEqual(self.view.scene.getChild(0).getName().getString(), "")
        self.assertTrue(self.panel.reject())

    def test_closing_the_panel_lets_go_of_a_click_whose_release_never_came(self):
        # R3-003: the release of a taken click may happen outside the view.
        self.assertTrue(self.mouse((420, 20)))
        self.assertTrue(self.panel.view_drag.click_taken)
        view_drag = self.panel.view_drag
        self.assertTrue(self.panel.reject())
        self.assertFalse(view_drag.click_taken)

    def test_a_view_that_gives_no_ray_takes_no_click_and_raises_nothing(self):
        # R3-005: a view without camera (closing, another view type) is no reason for an error in the callback.
        def no_camera():
            raise RuntimeError("no camera")

        self.view.getCameraNode = no_camera
        self.assertFalse(self.mouse((420, 20)))
        self.panel.start_drag("XY")
        self.send("SoLocation2Event", position=(400, 236))
        self.assertEqual(self.panel.form.spin_length.value(), 100)
        self.assertTrue(self.panel.reject())

    def test_click_a_square_move_and_click_again(self):
        # The squares are drawn at the start of the line, 60 px (here 60 mm) long.
        self.assertEqual(self.view.scene.getNumChildren(), 1)
        self.assertFalse(self.mouse((520, 20)))
        # Seen from the top, XZ and YZ are edge-on: only XY is clicked.
        self.assertTrue(self.mouse((420, 20)))
        self.assertEqual(self.panel.drag_plane, "XY")
        self.assertTrue(self.panel.view_drag.click_taken)
        self.send("SoLocation2Event", position=(400, 236), shift=True)
        self.assertEqual((self.panel.direction(), self.panel.form.spin_length.value()), ("+Y", 236))
        self.assertTrue(self.mouse((400, 236), down=False))
        self.assertTrue(self.mouse((480, 80)))
        self.assertIsNone(self.panel.drag_plane)
        self.assertEqual(self.panel.form.combo_plane.currentData(), "XY")
        self.assertEqual((self.panel.direction(), self.panel.form.spin_angle.value()), ("Angle", 45))
        self.assertEqual(self.panel.form.spin_length.value(), 110)
        self.assertTrue(self.panel.reject())
        self.assertEqual(self.view.callbacks, {})
        self.assertEqual(self.view.scene.getNumChildren(), 0)

    def test_p_cycles_only_the_planes_not_seen_edge_on_and_esc_or_right_click_cancel(self):
        P, ESC = self.coin.SoKeyboardEvent.P, self.coin.SoKeyboardEvent.ESCAPE
        self.assertTrue(self.send("SoKeyboardEvent", key=P))
        self.assertTrue(self.send("SoKeyboardEvent", key=P))
        self.assertEqual(self.panel.drag_plane, "XY")
        self.send("SoLocation2Event", position=(600, 0))
        self.assertTrue(self.send("SoKeyboardEvent", key=ESC))
        self.assertIsNone(self.panel.drag_plane)
        self.assertEqual((self.panel.direction(), self.panel.form.spin_length.value()), ("-Z", 100))
        self.assertFalse(self.send("SoKeyboardEvent", key=ESC))
        self.panel.start_drag("XY")
        self.assertTrue(self.mouse((0, 0), button=self.coin.SoMouseButtonEvent.BUTTON2))
        self.assertIsNone(self.panel.drag_plane)
        self.assertTrue(self.panel.reject())

    def pick_on_release(self, position):
        """The release of a click: FreeCAD selects the vertex under it first, then the callbacks run."""
        self.panel.addSelection(self.doc.Name, self.sketch.Name, self.corner(CORNERS[2]), (400, 200, 0))
        self.events()
        handled = self.mouse(position, down=False)
        self.events()
        return handled

    def test_the_release_of_a_click_on_a_square_picks_no_vertex(self):
        self.assertTrue(self.mouse((420, 20)))
        self.events()
        self.assertTrue(self.pick_on_release((420, 20)))
        self.assertEqual(len(self.panel.lines), 1)
        self.assertFalse(self.panel.view_drag.click_taken)
        self.assertTrue(self.panel.reject())

    def test_the_release_of_the_click_fixing_the_line_picks_no_vertex(self):
        self.assertTrue(self.mouse((420, 20)))
        self.events()
        self.mouse((420, 20), down=False)
        self.events()
        self.send("SoLocation2Event", position=(400, 200))
        self.assertTrue(self.mouse((400, 200)))
        self.events()
        self.assertTrue(self.pick_on_release((400, 200)))
        self.assertEqual(len(self.panel.lines), 1)
        self.assertEqual((self.panel.direction(), self.panel.form.spin_length.value()), ("+Y", 200))
        self.assertTrue(self.panel.reject())

    def test_a_click_off_the_squares_still_picks_a_vertex(self):
        self.assertFalse(self.mouse((0, 200)))
        self.assertFalse(self.pick_on_release((0, 200)))
        self.assertEqual(len(self.panel.lines), 2)
        self.assertTrue(self.panel.reject())

    def test_after_a_zoom_the_squares_are_clicked_where_they_are_drawn_again(self):
        # Zoomed in twice: 0.5 mm per pixel, so the squares are 30 mm long.
        self.view.getPoint = lambda x, y: App.Vector(x * 0.5, y * 0.5, 0)
        self.view.getPointOnViewport = lambda p: (p.x * 2, p.y * 2)
        self.assertFalse(self.mouse((880, 40)))
        self.assertTrue(self.mouse((840, 40)))
        self.assertEqual((self.panel.drag_plane, self.panel.view_drag.size), ("XY", 30))
        self.assertTrue(self.panel.reject())

    def test_cancel_puts_back_the_angle_mode_and_its_expression(self):
        form = self.panel.form
        form.combo_direction.setCurrentIndex(form.combo_direction.findData("Angle"))
        form.combo_plane.setCurrentIndex(form.combo_plane.findData("YZ"))
        self.panel.lines[0].setExpression("Angle", "Box.Height * 3")
        self.doc.recompute()
        self.panel.start_drag("XY")
        self.panel.drag_to(App.Vector(630, 3, 0))
        self.panel.cancel_drag()
        self.assertEqual((self.panel.direction(), self.panel.plane()), ("Angle", "YZ"))
        self.assertEqual(expression_fields.expression_of(self.panel.lines[0], "Angle"), "Box.Height * 3")
        self.assertTrue(self.panel.reject())


class TestApplyAndContinue(ParametricLinePanelFixture):
    """S7: Apply and continue creates the lines in their own Undo step and keeps the panel open for the next ones."""

    def dialog_box(self):
        """The button row of the task dialog: the one button box holding its OK and Cancel."""
        boxes = [
            box
            for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
            if box.button(QtWidgets.QDialogButtonBox.Ok) is not None
            and box.button(QtWidgets.QDialogButtonBox.Cancel) is not None
        ]
        self.assertEqual(len(boxes), 1)
        return boxes[0]

    def apply_button(self):
        return self.dialog_box().button(QtWidgets.QDialogButtonBox.Apply)

    def apply(self):
        """Click Apply and continue, as the user does."""
        button = self.apply_button()
        self.assertTrue(button.isEnabled())
        button.click()
        self.events()

    def test_the_button_shows_only_while_creating_and_is_enabled_while_the_panel_has_a_line(self):
        panel = self.run_command()
        button = self.apply_button()
        self.assertEqual(button.text(), "Apply and continue")
        self.assertFalse(button.isEnabled())
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertTrue(button.isEnabled())
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertFalse(button.isEnabled())
        self.assertTrue(panel.reject())
        self.events()
        leg = make_line_from_vertex((self.sketch, self.corner(CORNERS[3])), "+Y", 70)
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).setEdit(leg, 0)
        self.events()
        self.assertIsNone(self.apply_button())
        self.assertTrue(self.recorded[-1].reject())

    def test_each_apply_is_its_own_undo_step_and_ok_creates_the_newer_lines(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        panel.form.spin_length.setValue(720)
        self.apply()
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(panel.lines, [])
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertEqual((panel.direction(), panel.form.spin_length.value()), ("-Z", 720))
        [first] = self.lines()
        self.assertEqual(self.ends(first), [(0, 0, 0), (0, 0, -720)])
        # The vertex of the applied line starts a new line: the applied one is no line of the panel any more.
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.assertEqual(len(panel.lines), 1)
        self.click(self.sketch, self.corner(CORNERS[0]))
        self.click(self.sketch, self.corner(CORNERS[1]))
        panel.form.combo_direction.setCurrentIndex(panel.form.combo_direction.findData("+X"))
        panel.form.spin_length.setValue(300)
        self.assertEqual(self.ends(first), [(0, 0, 0), (0, 0, -720)])
        self.assertTrue(panel.accept())
        self.events()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(self.doc.UndoCount, 2)
        self.assertEqual(
            [self.ends(line) for line in self.lines()], [[(0, 0, 0), (0, 0, -720)], [(400, 0, 0), (700, 0, 0)]]
        )
        self.doc.undo()
        self.assertEqual(self.lines(), [first])

    def test_ok_after_apply_with_no_new_line_adds_no_undo_step(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        self.apply()
        self.assertTrue(panel.accept())
        self.events()
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertEqual(len(self.lines()), 1)

    def test_cancel_after_apply_removes_only_the_newer_lines(self):
        for undo_mode in (1, 0):
            with self.subTest(undo_mode=undo_mode):
                for line in self.lines():
                    self.doc.removeObject(line.Name)
                self.doc.clearUndos()
                self.doc.UndoMode = undo_mode
                self.addCleanup(setattr, self.doc, "UndoMode", 1)
                panel = self.run_command(*self.corners(CORNERS[0]))
                self.apply()
                self.click(self.sketch, self.corner(CORNERS[1]))
                self.assertEqual(len(self.lines()), 2)
                self.assertTrue(panel.reject())
                self.events()
                [line] = self.lines()
                self.assertEqual(self.ends(line), [(0, 0, 0), (0, 0, -100)])
                if undo_mode:
                    # With Undo off, FreeCAD weekly still counts a step: only the lines tell what Cancel kept.
                    self.assertEqual(self.doc.UndoCount, 1)

    def test_apply_remembers_the_values_and_keeps_the_length_expression_for_the_next_line(self):
        panel = self.run_command(*self.corners(CORNERS[0]))
        panel.lines[0].setExpression("Length", "Box.Height * 72")
        panel.form.combo_direction.setCurrentIndex(panel.form.combo_direction.findData("+Y"))
        self.apply()
        self.click(self.sketch, self.corner(CORNERS[1]))
        self.assertEqual(expression_fields.expression_of(panel.lines[0], "Length"), "Box.Height * 72")
        self.assertEqual(self.ends(panel.lines[0]), [(400, 0, 0), (400, 720, 0)])
        self.assertTrue(panel.reject())
        self.events()
        panel = self.run_command()
        self.assertEqual(panel.direction(), "+Y")
        self.assertTrue(panel.reject())

    def test_the_button_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        # The language change reaches the widgets first: it would put back the standard text of Apply.
        self.events()
        panel = self.run_command(*self.corners(CORNERS[0]))
        self.assertEqual(self.apply_button().text(), "Aplicar y seguir")
        self.assertTrue(self.apply_button().toolTip().startswith("Crear estas líneas en su propio paso de deshacer"))
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

    def test_a_line_without_plane_and_angle_opens_its_panel(self):
        # R3-001: a line made by an earlier version in this session has no Plane and no Angle yet.
        leg = make_line_from_vertex((self.sketch, self.corner(CORNERS[3])), "+Y", 70)
        leg.removeProperty("Plane")
        leg.removeProperty("Angle")
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).setEdit(leg, 0)
        self.events()
        panel = self.recorded[-1]
        self.assertIs(panel.edited, leg)
        self.assertEqual((panel.direction(), panel.plane(), panel.form.spin_angle.value()), ("+Y", "XY", 0))
        self.assertTrue(panel.reject())
        self.assertEqual(self.ends(leg), [(0, 200, 0), (0, 270, 0)])

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

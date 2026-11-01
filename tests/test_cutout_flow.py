"""Cutout command: always active, face panel, sketch on the face with its outline, empty sketch, direct path."""

import math
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER
from test_notch_geometry import TrimFixture

from freecad.maxproframe import create_extruded_cutout_tool
from freecad.maxproframe.create_extruded_cutout_tool import AddExtrudedCutoutCommandClass
from freecad.maxproframe.create_notch_tool import make_notch_profile

UP = App.Vector(0, 0, 1)
SIDE = App.Vector(0, -1, 0)
END = App.Vector(1, 0, 0)
# The profile: a 50 x 50 x 2 square tube along X, from -50 to 350 (300 long plus 50 at each end).
PATH = ((0, 0, 0), (300, 0, 0))
HOLE_RADIUS = 5.0
WALL = 2.0


class CutoutFixture(TrimFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        QtWidgets.QApplication.processEvents()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def tube(self):
        return self.make_profile(self.make_sketch(PATH), "Edge1", **CENTER)

    def select(self, *items):
        Gui.Selection.clearSelection()
        for obj, sub in items:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)

    def click(self, obj, sub):
        """A click in the 3D view: it replaces the selection, the observer hears it."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        QtWidgets.QApplication.processEvents()

    def run_command(self, *items):
        """Run the command on a selection and return the face panel it opens."""
        self.select(*items)
        created = []
        base = create_extruded_cutout_tool.CutoutTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_extruded_cutout_tool, "CutoutTaskPanel", Recording):
            AddExtrudedCutoutCommandClass().Activated()
        self.panels.extend(created)
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def message(self, panel):
        return panel.form.message_label.text()

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def created(self, before):
        """(sketch, cutout) the command added to a document that held ``before``."""
        new = [obj for obj in self.doc.Objects if obj.Name not in before]
        sketches = [obj for obj in new if obj.isDerivedFrom("Sketcher::SketchObject")]
        cutouts = [obj for obj in new if hasattr(obj, "baseObject")]
        self.assertEqual((len(sketches), len(cutouts), len(new)), (1, 1, 2))
        return sketches[0], cutouts[0]

    def outline(self, obj, face):
        """Names of the edges of ``obj`` bounding its face ``face``."""
        edges = obj.Shape.getElement(face).Edges
        return sorted(
            f"Edge{index}"
            for index, edge in enumerate(obj.Shape.Edges, start=1)
            if any(edge.isSame(face_edge) for face_edge in edges)
        )

    def external(self, sketch):
        return [(obj, sorted(subs)) for obj, subs in sketch.ExternalGeometry]

    def add_hole(self, sketch, obj, face):
        """A circle on ``sketch`` centered on the face ``face`` of ``obj``."""
        center = sketch.Placement.inverse().multVec(obj.Shape.getElement(face).CenterOfMass)
        sketch.addGeometry(Part.Circle(App.Vector(center.x, center.y, 0), UP, HOLE_RADIUS))
        self.doc.recompute()


class TestCutoutCommand(CutoutFixture):
    def test_the_command_is_active_with_a_document_whatever_is_selected(self):
        body = self.tube()
        path = body.AttachmentSupport[0][0]
        top = self.face_towards(body, UP)
        selections = (
            [],
            [(body, "")],
            [(path, "")],
            [(body, "Edge1")],
            [(body, top), (body, self.face_towards(body, SIDE))],
            [(body, top), (path, "")],
        )
        for selection in selections:
            with self.subTest(selection=[(obj.Name, sub) for obj, sub in selection]):
                self.select(*selection)
                self.assertTrue(AddExtrudedCutoutCommandClass().IsActive())


class TestCutoutPanel(CutoutFixture):
    def test_a_preselected_planar_face_is_the_face_to_cut(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        panel = self.run_command((body, top))
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(panel.form.face_label.text(), f"{body.Label} ({body.Name}) {top}")
        self.assertEqual(self.message(panel), "")
        self.assertEqual(panel.form.windowTitle(), "Cutout / Hole")
        self.assertEqual(panel.form.groupBox_face.title(), "Face")
        self.assertEqual(
            panel.form.hint_label.text(), "OK creates a sketch on the face and opens it to draw the cutout."
        )

    def test_every_unusable_item_is_explained(self):
        body = self.tube()
        whole = self.tube()
        edge_pick = self.tube()
        path = body.AttachmentSupport[0][0]
        top, side, end = (self.face_towards(body, direction) for direction in (UP, SIDE, END))
        panel = self.run_command((body, top), (body, side), (body, end), (path, ""), (whole, ""), (edge_pick, "Edge1"))
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(
            self.message(panel).split("\n"),
            [
                f"{body.Label}: {side} is not used, a cutout takes one face",
                f"{body.Label}: {end} is an end face (wall thickness)",
                f"{path.Label} is not a profile",
                f"{whole.Label}: pick one of its faces",
                f"{edge_pick.Label}: Edge1 is not a face",
            ],
        )

    def test_a_curved_face_is_explained(self):
        pipe = self.tube()
        pipe.Family = "Pipe"
        self.doc.recompute()
        curved = next(
            f"Face{index}"
            for index, face in enumerate(pipe.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        panel = self.run_command((pipe, curved))
        self.assertIsNone(panel.face)
        self.assertEqual(self.message(panel), f"{pipe.Label}: {curved} is not planar")

    def test_clicks_pick_the_face_and_explain_unusable_picks(self):
        body = self.tube()
        top, side, end = (self.face_towards(body, direction) for direction in (UP, SIDE, END))
        panel = self.run_command()
        self.assertIsNone(panel.face)
        self.assertEqual(
            panel.form.face_label.text(), "Click a planar face of a profile, a trimmed profile or a cutout."
        )
        self.click(body, top)
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(self.message(panel), "")
        self.click(body, end)
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(self.message(panel), f"{body.Label}: {end} is an end face (wall thickness)")
        self.click(body, side)
        self.assertEqual(panel.face, (body, side))
        self.assertEqual(self.message(panel), "")

    def test_a_pick_inside_a_part_names_the_face_of_the_profile(self):
        body = self.tube()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        self.doc.recompute()
        top = self.face_towards(body, UP)
        panel = self.run_command()
        self.click(part, f"{body.Name}.{top}")
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(self.message(panel), "")

    def test_ok_without_a_face_keeps_the_panel_open_and_creates_nothing(self):
        self.tube()
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command()
        self.assertFalse(panel.accept())
        self.assertEqual(self.message(panel), "Select a planar face of a profile, a trimmed profile or a cutout.")
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_leaves_the_document_unchanged_and_stops_listening(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.reject())
        self.click(body, self.face_towards(body, SIDE))
        self.assertEqual(panel.face, (body, top))
        self.assertEqual(self.names(), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(body.ViewObject.Visibility)


class TestCutoutCreation(CutoutFixture):
    def test_ok_creates_the_sketch_and_the_cutout_in_the_face_container_in_one_undo_step(self):
        body = self.tube()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([body.AttachmentSupport[0][0], body])
        part.Placement.Base = App.Vector(0, 500, 0)
        self.doc.recompute()
        top = self.face_towards(body, UP)
        self.doc.clearUndos()
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        self.assertEqual(sketch.getParentGeoFeatureGroup(), part)
        self.assertEqual(cutout.getParentGeoFeatureGroup(), part)
        self.assertEqual(sketch.MapMode, "FlatFace")
        self.assertEqual(sketch.AttachmentSupport, [(body, (top,))])
        face = body.Shape.getElement(top)
        self.assertAlmostEqual(sketch.Placement.Base.z, face.CenterOfMass.z, places=6)
        self.assertLess(sketch.Placement.Rotation.multVec(UP).getAngle(face.normalAt(0, 0)), 1e-9)
        self.assertEqual(cutout.baseObject, (body, [top]))
        self.assertEqual(cutout.Sketch, sketch)
        # The guided flow cuts one wall by default (S4).
        self.assertEqual(cutout.CutType, "One wall")
        self.assertEqual(cutout.getStatusString(), "Valid")
        self.assertEqual(sketch.getStatusString(), "Valid")
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.names(), before)

    def test_the_sketch_holds_the_face_outline_as_construction_geometry(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        outline = self.outline(body, top)
        self.assertEqual(len(outline), 4)
        self.assertEqual(self.external(sketch), [(body, outline)])
        self.assertEqual(sketch.Geometry, [])
        # Construction geometry builds no wire: the empty sketch leaves the tube uncut.
        self.assertEqual(sketch.Shape.Edges, [])
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume, places=6)

    def test_a_hole_drawn_on_the_new_sketch_cuts_the_tube(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        self.add_hole(sketch, body, top)
        self.assertEqual(cutout.getStatusString(), "Valid")
        # One wall: the hole goes through the top wall only.
        removed = math.pi * HOLE_RADIUS**2 * WALL
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume - removed, places=3)

    def test_ok_opens_the_new_sketch_for_editing_once_the_panel_is_closed(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, _ = self.created(before)
        # FreeCAD closes the panel after OK; the sketch editor opens next.
        Gui.Control.closeDialog()
        for _ in range(3):
            QtWidgets.QApplication.processEvents()
        in_edit = Gui.getDocument(self.doc.Name).getInEdit()
        self.assertIsNotNone(in_edit)
        self.assertEqual(in_edit.Object, sketch)

    def test_a_face_of_a_trim_or_of_a_cutout_can_be_cut(self):
        body = self.tube()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        target = make_notch_profile(body, far)
        self.doc.recompute()
        for base in ("trim", "cutout"):
            with self.subTest(base=base):
                self.close_dialog()
                top = self.face_towards(target, UP)
                before = self.names()
                panel = self.run_command((target, top))
                self.assertEqual(self.message(panel), "")
                self.assertTrue(panel.accept())
                sketch, cutout = self.created(before)
                self.assertEqual(sketch.AttachmentSupport, [(target, (top,))])
                self.assertEqual(self.external(sketch), [(target, self.outline(target, top))])
                self.assertEqual(cutout.baseObject, (target, [top]))
                self.assertEqual(cutout.getStatusString(), "Valid")
                self.assertAlmostEqual(cutout.Shape.Volume, target.Shape.Volume, places=6)
                target = cutout


class TestEmptySketch(CutoutFixture):
    def test_an_empty_or_open_sketch_leaves_the_base_shape_uncut_without_error(self):
        body = self.tube()
        top = self.face_towards(body, UP)
        before = self.names()
        panel = self.run_command((body, top))
        self.assertTrue(panel.accept())
        sketch, cutout = self.created(before)
        self.assertEqual(cutout.getStatusString(), "Valid")
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume, places=6)
        sketch.addGeometry(Part.LineSegment(App.Vector(-10, 0, 0), App.Vector(10, 0, 0)))
        self.doc.recompute()
        self.assertEqual(cutout.getStatusString(), "Valid")
        self.assertAlmostEqual(cutout.Shape.Volume, body.Shape.Volume, places=6)
        self.assertEqual(cutout.PID, body.PID)


class TestCutoutTranslations(CutoutFixture):
    def test_panel_text_and_messages_are_spanish(self):
        body = self.tube()
        path = body.AttachmentSupport[0][0]
        top, side, end = (self.face_towards(body, direction) for direction in (UP, SIDE, END))
        whole = self.tube()
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.windowTitle(), "Calado")
        self.assertEqual(form.groupBox_face.title(), "Cara")
        self.assertEqual(
            form.face_label.text(), "Hacé clic en una cara plana de un perfil, un perfil recortado o un calado."
        )
        self.assertEqual(form.hint_label.text(), "Aceptar crea un croquis en la cara y lo abre para dibujar el calado.")
        self.assertFalse(panel.accept())
        self.assertEqual(
            self.message(panel), "Seleccioná una cara plana de un perfil, un perfil recortado o un calado."
        )
        self.close_dialog()
        panel = self.run_command((body, top), (body, side), (body, end), (path, ""), (whole, ""))
        self.assertEqual(
            self.message(panel).split("\n"),
            [
                f"{body.Label}: {side} no se usa, un calado lleva una sola cara",
                f"{body.Label}: {end} es una cara de extremo (espesor de pared)",
                f"{path.Label} no es un perfil",
                f"{whole.Label}: elegí una de sus caras",
            ],
        )

    def test_a_curved_face_is_explained_in_spanish(self):
        pipe = self.tube()
        pipe.Family = "Pipe"
        self.doc.recompute()
        curved = next(
            f"Face{index}"
            for index, face in enumerate(pipe.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((pipe, curved))
        self.assertEqual(self.message(panel), f"{pipe.Label}: {curved} no es plana")


if __name__ == "__main__":
    unittest.main()

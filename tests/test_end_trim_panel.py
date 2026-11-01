"""End Trim command and panel: availability, selection messages, Undo, and recompute without a GUI."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtWidgets
from test_end_trim_geometry import BOUNDARY_EDGE, TRIMMED_EDGE, TrimFixture

from freecad.maxproframe import create_trimmed_profiles_tool
from freecad.maxproframe.create_trimmed_profiles_tool import TrimProfileCommand
from freecad.maxproframe.ff_tools import get_param_group

CENTER = dict(anchor_x=1, anchor_y=1)


class Headless:
    """An object as seen by recompute in FreeCAD's console mode: it has no ViewObject."""

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, name):
        if name == "ViewObject":
            raise AssertionError("recompute touched ViewObject")
        value = getattr(self._obj, name)
        if name == "TrimmedBody" and value is not None:
            return Headless(value)
        return value

    def __setattr__(self, name, value):
        setattr(self._obj, name, value)


class TestEndTrimPanel(TrimFixture):
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
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        QtWidgets.QApplication.processEvents()

    def select(self, *items):
        Gui.Selection.clearSelection()
        for obj, sub in items:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)

    def run_command(self, *items):
        """Run the Trim command on a selection and return its panel."""
        self.select(*items)
        return self.capture_panel(TrimProfileCommand().Activated)

    def capture_panel(self, action):
        created = []
        base = create_trimmed_profiles_tool.CreateTrimmedProfileTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_trimmed_profiles_tool, "CreateTrimmedProfileTaskPanel", Recording):
            action()
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def message(self, panel):
        return panel.form.message_label.text()

    def trims(self):
        return [obj for obj in self.doc.Objects if hasattr(obj, "TrimmedBody")]

    def outer_face(self, obj):
        return self.face_towards(obj, App.Vector(1, 0, 0))

    def keep_default_cut_type(self, value):
        param = get_param_group(writable=True)
        stored = "Default Cut Type" in param.GetStrings()
        previous = param.GetString("Default Cut Type")

        def restore():
            if stored:
                param.SetString("Default Cut Type", previous)
            else:
                param.RemString("Default Cut Type")

        self.addCleanup(restore)
        param.SetString("Default Cut Type", value)

    def test_a_new_trim_is_named_after_its_profile_and_remembers_the_cut_type(self):
        trimmed, boundary = self.t_joint()
        self.keep_default_cut_type("Perfect fit")
        panel = self.run_command((trimmed, ""), (boundary, self.outer_face(boundary)))
        self.assertEqual(panel.fp.Name, f"{trimmed.Name}_Tr")
        self.assertTrue(panel.form.rb_perfectfit.isChecked())
        panel.form.rb_simplefit.setChecked(True)
        self.assertEqual(panel.fp.CutType, "Simple fit")
        self.assertTrue(panel.accept())
        self.assertEqual(get_param_group().GetString("Default Cut Type"), "Simple fit")

    def test_editing_shows_the_cut_type_of_the_trim(self):
        trimmed, boundary = self.t_joint()
        self.keep_default_cut_type("Perfect fit")
        trim = self.trim(trimmed, [(boundary, (self.outer_face(boundary),))], "Simple fit")
        dialog = self.capture_panel(trim.ViewObject.Proxy.edit)
        self.assertTrue(dialog.form.rb_simplefit.isChecked())
        self.assertEqual(trim.CutType, "Simple fit")

    def test_the_command_is_active_whatever_is_selected(self):
        trimmed, boundary = self.t_joint()
        sketch = trimmed.AttachmentSupport[0][0]
        for selection in ([], [(trimmed, "")], [(trimmed, "Edge1")], [(sketch, "")], [(boundary, "Face1")]):
            with self.subTest(selection=[(obj.Name, sub) for obj, sub in selection]):
                self.select(*selection)
                self.assertTrue(TrimProfileCommand().IsActive())

    def test_a_whole_profile_selected_in_the_tree_is_the_trimmed_body(self):
        trimmed, boundary = self.t_joint()
        panel = self.run_command((trimmed, ""), (boundary, self.outer_face(boundary)))
        self.assertIs(panel.fp.TrimmedBody, trimmed)
        self.assertEqual(panel.fp.TrimmingBoundary, [(boundary, (self.outer_face(boundary),))])
        self.assertEqual(self.message(panel), "")

    def test_a_non_profile_first_selection_is_explained_and_not_trimmed(self):
        trimmed, boundary = self.t_joint()
        sketch = trimmed.AttachmentSupport[0][0]
        panel = self.run_command((sketch, ""))
        self.assertIsNone(panel.fp.TrimmedBody)
        self.assertIn(f"{sketch.Label} is not a profile", self.message(panel))

    def test_boundaries_must_be_faces_and_valid_faces_are_kept(self):
        trimmed, boundary = self.t_joint()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        face = self.outer_face(boundary)
        panel = self.run_command((trimmed, ""), (boundary, face), (far, "Edge1"), (far, ""))
        self.assertEqual(panel.fp.TrimmingBoundary, [(boundary, (face,))])
        text = self.message(panel)
        self.assertIn(f"{far.Label}: Edge1 is not a face", text)
        self.assertIn(f"{far.Label}: select a face, not the whole object", text)

    def test_the_trimmed_profile_is_not_its_own_boundary(self):
        trimmed, boundary = self.t_joint()
        panel = self.run_command((trimmed, ""))
        self.select((trimmed, "Face1"), (boundary, self.outer_face(boundary)))
        panel.add_trimming_bodies()
        self.assertEqual(panel.fp.TrimmingBoundary, [(boundary, (self.outer_face(boundary),))])
        self.assertIn(f"{trimmed.Label} cannot trim itself", self.message(panel))

    def test_ok_creates_the_trim_in_one_undo_step(self):
        trimmed, boundary = self.t_joint()
        self.doc.clearUndos()
        panel = self.run_command((trimmed, ""), (boundary, self.outer_face(boundary)))
        self.assertTrue(panel.accept())
        self.assertEqual(len(self.trims()), 1)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.trims(), [])

    def test_ok_without_a_trimmed_profile_keeps_the_panel_open(self):
        self.t_joint()
        panel = self.run_command()
        self.assertFalse(panel.accept())
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIn("Select the profile to trim", self.message(panel))

    def test_cancel_after_creation_leaves_the_document_unchanged(self):
        trimmed, boundary = self.t_joint()
        self.doc.clearUndos()
        panel = self.run_command((trimmed, ""), (boundary, self.outer_face(boundary)))
        self.assertTrue(panel.reject())
        self.assertEqual(self.trims(), [])
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(trimmed.ViewObject.Visibility)

    def test_cancel_after_editing_restores_the_trim_without_an_undo_step(self):
        trimmed, boundary = self.t_joint()
        far = self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)
        trim = self.trim(trimmed, [(boundary, (self.outer_face(boundary),))], "Simple fit")
        volume = trim.Shape.Volume
        self.doc.clearUndos()
        dialog = self.capture_panel(trim.ViewObject.Proxy.edit)
        self.assertEqual(dialog.mode, "edition")
        self.select((far, self.face_towards(far, App.Vector(-1, 0, 0))))
        dialog.add_trimming_bodies()
        self.assertEqual(len(trim.TrimmingBoundary), 2)
        self.assertTrue(dialog.reject())
        self.assertEqual(trim.TrimmingBoundary, [(boundary, (self.outer_face(boundary),))])
        self.assertAlmostEqual(trim.Shape.Volume, volume, places=5)
        self.assertEqual(self.doc.UndoCount, 0)


class TestEndTrimRecompute(TrimFixture):
    def test_recompute_does_not_need_a_view_object(self):
        trimmed, boundary = self.t_joint()
        trim = self.trim(trimmed, [(boundary, (self.face_towards(boundary, App.Vector(1, 0, 0)),))], "Simple fit")
        volume = trim.Shape.Volume
        trim.Shape = Part.Shape()
        trim.Proxy.execute(Headless(trim))
        self.assertAlmostEqual(trim.Shape.Volume, volume, places=5)

    def test_a_boundary_that_cuts_nothing_leaves_the_profile_uncut_with_a_warning(self):
        trimmed, _ = self.t_joint()
        tube = self.doc.addObject("Part::Feature", "Tube")
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(150, 0, -50))
        lateral = next(
            f"Face{index}"
            for index, face in enumerate(tube.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        warnings = []
        with patch.object(App.Console, "PrintWarning", side_effect=warnings.append):
            trim = self.trim(trimmed, [(tube, (lateral,))], "Simple fit")
        self.assertAlmostEqual(trim.Shape.Volume, trimmed.Shape.Volume, places=5)
        self.assertTrue(any(trim.Label in text and "left uncut" in text for text in warnings), warnings)


if __name__ == "__main__":
    unittest.main()

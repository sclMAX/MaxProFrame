"""Notch command and panel: availability, target then profiles, messages, Undo, edit and recompute without a GUI."""

import os
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtCore, QtWidgets
from test_notch_geometry import HALF, TrimFixture

from freecad.maxproframe import create_notch_tool
from freecad.maxproframe.create_notch_tool import NotchCommand, make_notch_profile

CENTER = dict(anchor_x=1, anchor_y=1)
CTRL = QtCore.Qt.KeyboardModifier.ControlModifier


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


class NotchPanelFixture(TrimFixture):
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
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        for panel in self.panels:
            panel.clean()
        QtWidgets.QApplication.processEvents()

    def select(self, *items):
        Gui.Selection.clearSelection()
        for obj, sub in items:
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)

    def click(self, obj, sub, ctrl=False):
        """A click in the 3D view: without Ctrl it replaces the selection, the observer hears it."""
        modifiers = CTRL if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        if not ctrl:
            Gui.Selection.clearSelection()
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
            QtWidgets.QApplication.processEvents()

    def run_command(self, *items):
        """Run the Notch command on a selection and return its panel."""
        self.select(*items)
        return self.capture_panel(NotchCommand().Activated)

    def capture_panel(self, action):
        created = []
        base = create_notch_tool.NotchTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_notch_tool, "NotchTaskPanel", Recording):
            action()
        self.panels.extend(created)
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def message(self, panel):
        return panel.form.message_label.text()

    def trims(self):
        return [obj for obj in self.doc.Objects if hasattr(obj, "TrimmedBody")]

    def outer_face(self, obj):
        return self.face_towards(obj, App.Vector(1, 0, 0))

    def far(self):
        return self.make_profile(self.make_sketch(((250, -200, 0), (250, 200, 0))), "Edge1", **CENTER)


class TestNotchCommand(NotchPanelFixture):
    def test_the_command_is_active_whatever_is_selected(self):
        trimmed, boundary = self.t_joint()
        sketch = trimmed.AttachmentSupport[0][0]
        for selection in ([], [(trimmed, "")], [(trimmed, "Edge1")], [(sketch, "")], [(boundary, "Face1")]):
            with self.subTest(selection=[(obj.Name, sub) for obj, sub in selection]):
                self.select(*selection)
                self.assertTrue(NotchCommand().IsActive())

    def test_the_command_replaces_trim_profile_on_the_toolbar(self):
        from freecad.maxproframe.InitGui import MaxProFrame

        tools = MaxProFrame.toolbox_maxproframe
        self.assertNotIn("MaxProFrame_TrimProfiles", tools)
        self.assertEqual(tools.index("MaxProFrame_Notch"), tools.index("MaxProFrame_ExtendCut") + 1)
        self.assertIn("MaxProFrame_Notch", Gui.listCommands())
        resources = NotchCommand().GetResources()
        self.assertEqual(resources["MenuText"], "Notch")
        self.assertEqual(resources["Accel"], "M, C")
        self.assertTrue(resources["Pixmap"].endswith("corner-notch.svg"))
        self.assertTrue(os.path.isfile(resources["Pixmap"]))


class TestNotchPanel(NotchPanelFixture):
    def test_the_gap_row_is_hidden(self):
        panel = self.run_command()
        self.assertFalse(panel.form.sb_gap.isVisibleTo(panel.form))
        self.assertFalse(panel.form.gap_label.isVisibleTo(panel.form))

    def test_a_target_face_picks_the_whole_target_profile_and_the_rest_are_profiles(self):
        trimmed, boundary = self.t_joint()
        panel = self.run_command((boundary, self.outer_face(boundary)), (trimmed, ""))
        self.assertEqual(panel.target, (boundary, ()))
        self.assertEqual(panel.profiles, [trimmed])
        self.assertEqual(panel.form.profiles_list.count(), 1)
        self.assertIn(boundary.Label, panel.form.target_label.text())
        self.assertEqual(self.message(panel), "")

    def test_any_pick_of_a_profile_is_a_whole_target(self):
        trimmed, boundary = self.t_joint()
        for sub in ("", "Edge1"):
            with self.subTest(sub=sub):
                panel = self.run_command((boundary, sub), (trimmed, "Face1"))
                self.assertEqual(panel.target, (boundary, ()))
                self.assertEqual(panel.profiles, [trimmed])
                self.assertEqual(self.message(panel), "")
                self.close_dialog()

    def test_a_non_profile_first_selection_is_explained_and_not_the_target(self):
        trimmed, _ = self.t_joint()
        sketch = trimmed.AttachmentSupport[0][0]
        panel = self.run_command((sketch, ""))
        self.assertIsNone(panel.target)
        self.assertIn(f"{sketch.Label} is not a profile", self.message(panel))

    def test_a_face_of_a_non_profile_is_not_a_target(self):
        trimmed, _ = self.t_joint()
        wall = self.doc.addObject("Part::Feature", "Wall")
        wall.Shape = Part.makeBox(10, 400, 400, App.Vector(100, -200, -200))
        panel = self.run_command((wall, "Face1"), (trimmed, ""))
        self.assertIsNone(panel.target)
        self.assertIn(f"{wall.Label} is not a profile", self.message(panel))

    def test_invalid_profiles_are_explained_and_valid_ones_are_kept(self):
        trimmed, boundary = self.t_joint()
        sketch = trimmed.AttachmentSupport[0][0]
        panel = self.run_command((boundary, self.outer_face(boundary)), (trimmed, ""), (sketch, ""))
        self.assertEqual(panel.profiles, [trimmed])
        self.assertIn(f"{sketch.Label} is not a profile", self.message(panel))

    def test_clicks_set_the_target_then_add_whole_profiles(self):
        trimmed, boundary = self.t_joint()
        other = self.make_profile(self.make_sketch(((0, 100, 0), (300, 100, 0))), "Edge1", **CENTER)
        panel = self.run_command()
        self.assertIsNone(panel.target)
        self.click(boundary, self.outer_face(boundary))
        self.assertEqual(panel.target, (boundary, ()))
        self.click(trimmed, "Face2")
        self.click(other, "Edge3")
        self.click(trimmed, "Face1")
        self.assertEqual(panel.profiles, [trimmed, other])
        self.assertEqual(panel.form.profiles_list.count(), 2)

    def test_ctrl_click_on_a_listed_profile_removes_it(self):
        trimmed, boundary = self.t_joint()
        other = self.make_profile(self.make_sketch(((0, 100, 0), (300, 100, 0))), "Edge1", **CENTER)
        panel = self.run_command((boundary, ""), (trimmed, ""), (other, ""))
        self.click(trimmed, "Face2", ctrl=True)
        self.assertEqual(panel.profiles, [other])
        self.assertEqual(panel.form.profiles_list.count(), 1)

    def test_the_target_cannot_notch_itself(self):
        trimmed, boundary = self.t_joint()
        panel = self.run_command((boundary, self.outer_face(boundary)))
        self.click(boundary, "Face1")
        self.assertEqual(panel.profiles, [])
        self.assertIn(f"{boundary.Label} cannot trim itself", self.message(panel))

    def test_ok_creates_one_notch_per_profile_in_one_undo_step(self):
        trimmed, boundary = self.t_joint()
        other = self.make_profile(self.make_sketch(((0, 100, 0), (300, 100, 0))), "Edge1", **CENTER)
        self.doc.clearUndos()
        panel = self.run_command((boundary, self.outer_face(boundary)), (trimmed, ""), (other, ""))
        self.assertTrue(panel.accept())
        trims = self.trims()
        self.assertEqual(sorted(obj.Name for obj in trims), sorted([f"{trimmed.Name}_Tr", f"{other.Name}_Tr"]))
        for obj in trims:
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertEqual(obj.TrimmedProfileType, "Notch")
            self.assertEqual(obj.TrimmingBoundary, [(boundary, ("",))])
            self.assertAlmostEqual(obj.Shape.BoundBox.XMin, HALF, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.trims(), [])

    def test_ok_places_each_notch_in_its_profile_container(self):
        trimmed, boundary = self.t_joint()
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([trimmed.AttachmentSupport[0][0], trimmed])
        self.doc.recompute()
        panel = self.run_command((boundary, ""), (trimmed, ""))
        self.assertTrue(panel.accept())
        (trim,) = self.trims()
        self.assertEqual(trim.getParentGeoFeatureGroup(), part)

    def test_ok_without_target_or_profiles_keeps_the_panel_open(self):
        _, boundary = self.t_joint()
        panel = self.run_command()
        self.assertFalse(panel.accept())
        self.assertIn("Select the target profile", self.message(panel))
        panel.set_target(boundary, ())
        self.assertFalse(panel.accept())
        self.assertIn("Select the profiles to notch", self.message(panel))
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.trims(), [])

    def test_cancel_after_creation_leaves_the_document_unchanged(self):
        trimmed, boundary = self.t_joint()
        self.doc.clearUndos()
        before = len(self.doc.Objects)
        panel = self.run_command((boundary, self.outer_face(boundary)), (trimmed, ""))
        self.assertTrue(panel.reject())
        self.assertEqual(self.trims(), [])
        self.assertEqual(len(self.doc.Objects), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(trimmed.ViewObject.Visibility)


class TestEditNotch(NotchPanelFixture):
    def existing(self):
        trimmed, boundary = self.t_joint()
        far = self.far()
        trim = make_notch_profile(trimmed, boundary)
        self.doc.recompute()
        self.assertEqual(trim.getStatusString(), "Valid")
        self.doc.clearUndos()
        return trimmed, boundary, far, trim

    def test_editing_opens_the_notch_panel_and_changes_the_target_in_one_undo_step(self):
        trimmed, boundary, far, trim = self.existing()
        panel = self.capture_panel(trim.ViewObject.Proxy.edit)
        self.assertIs(panel.edited, trim)
        self.assertEqual(panel.profiles, [trimmed])
        self.assertEqual(panel.target, (boundary, ()))
        self.assertEqual(panel.form.windowTitle(), "Edit Notch")
        self.assertFalse(panel.form.sb_gap.isVisibleTo(panel.form))
        self.click(far, self.face_towards(far, App.Vector(-1, 0, 0)))
        self.assertEqual(panel.target, (far, ()))
        self.assertTrue(panel.accept())
        self.assertEqual(trim.TrimmingBoundary, [(far, ("",))])
        self.assertAlmostEqual(trim.Shape.BoundBox.XMax, 250 - HALF, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(trim.TrimmingBoundary, [(boundary, ("",))])

    def test_cancel_after_editing_restores_the_notch_without_an_undo_step(self):
        trimmed, boundary, far, trim = self.existing()
        volume = trim.Shape.Volume
        panel = self.capture_panel(trim.ViewObject.Proxy.edit)
        self.click(far, "Face1")
        self.assertEqual(panel.target, (far, ()))
        self.assertTrue(panel.reject())
        self.assertEqual(trim.TrimmingBoundary, [(boundary, ("",))])
        self.assertAlmostEqual(trim.Shape.Volume, volume, places=5)
        self.assertEqual(self.doc.UndoCount, 0)


class TestNotchTranslations(NotchPanelFixture):
    def test_panel_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.windowTitle(), "Encastrar")
        self.assertEqual(form.groupBox_target.title(), "Destino")
        self.assertEqual(form.target_label.text(), "Hacé clic en el perfil destino o seleccionalo en el árbol.")
        self.assertEqual(form.hint_label.text(), "Hacé clic en los perfiles a encastrar. Ctrl+clic quita uno.")
        self.assertFalse(panel.accept())
        self.assertEqual(form.message_label.text(), "Seleccioná el perfil destino.")
        _, boundary = self.t_joint()
        panel.set_target(boundary, ())
        self.assertFalse(panel.accept())
        self.assertEqual(form.message_label.text(), "Seleccioná los perfiles a encastrar.")

    def test_edit_title_and_hint_are_spanish(self):
        trimmed, boundary = self.t_joint()
        trim = make_notch_profile(trimmed, boundary)
        self.doc.recompute()
        use_language(self, "Spanish", "es_ES")
        panel = self.capture_panel(trim.ViewObject.Proxy.edit)
        self.assertEqual(panel.form.windowTitle(), "Editar encastre")
        self.assertEqual(panel.form.hint_label.text(), "Hacé clic en un perfil para cambiar el destino.")

    def test_panel_text_stays_english_in_english(self):
        panel = self.run_command()
        self.assertEqual(panel.form.windowTitle(), "Notch")
        self.assertEqual(panel.form.target_label.text(), "Click the target profile, or select it in the tree.")
        self.assertEqual(panel.form.hint_label.text(), "Click the profiles to notch. Ctrl+click drops one.")


class TestNotchRecompute(TrimFixture):
    def test_recompute_does_not_need_a_view_object(self):
        trimmed, boundary = self.t_joint()
        trim = self.notch(trimmed, boundary)
        volume = trim.Shape.Volume
        trim.Shape = Part.Shape()
        trim.Proxy.execute(Headless(trim))
        self.assertAlmostEqual(trim.Shape.Volume, volume, places=5)

    def test_a_target_that_cuts_nothing_leaves_the_profile_uncut_with_a_warning(self):
        trimmed, _ = self.t_joint()
        tube = self.doc.addObject("Part::Feature", "Tube")
        # Beside the profile: the target does not touch it.
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(150, 200, -50))
        warnings = []
        with patch.object(App.Console, "PrintWarning", side_effect=warnings.append):
            trim = self.notch(trimmed, tube)
        self.assertAlmostEqual(trim.Shape.Volume, trimmed.Shape.Volume, places=5)
        self.assertTrue(any(trim.Label in text and "left uncut" in text for text in warnings), warnings)


if __name__ == "__main__":
    unittest.main()

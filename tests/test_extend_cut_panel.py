"""Extend / Cut command and panel: target and profiles from the selection or clicks, OK, Cancel and edit."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from miter_helpers import use_language
from PySide import QtCore, QtWidgets
from test_end_miter_geometry import CENTER
from test_extend_cut_geometry import FAR, NEAR, ExtendCutFixture

from freecad.maxproframe import create_extend_cut_tool
from freecad.maxproframe.create_extend_cut_tool import ExtendCutCommand, make_extend_cut_profile
from freecad.maxproframe.create_notch_tool import make_notch_profile

CTRL = QtCore.Qt.KeyboardModifier.ControlModifier


class PanelFixture(ExtendCutFixture):
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
        self.addCleanup(self.close_panels)

    def close_panels(self):
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

    def capture_panel(self, action):
        created = []
        base = create_extend_cut_tool.ExtendCutTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch.object(create_extend_cut_tool, "ExtendCutTaskPanel", Recording):
            action()
        self.panels.extend(created)
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def run_command(self, *items):
        self.select(*items)
        return self.capture_panel(ExtendCutCommand().Activated)

    def near_face(self, target):
        return self.face_towards(target, App.Vector(-1, 0, 0))

    def extend_cuts(self):
        return [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Extend Cut"]

    def message(self, panel):
        return panel.form.message_label.text()


class TestExtendCutCommand(PanelFixture):
    def test_the_command_is_active_with_a_document_whatever_is_selected(self):
        target = self.target()
        body = self.profile(0, 300)
        sketch = body.AttachmentSupport[0][0]
        for selection in ([], [(body, "")], [(sketch, "")], [(target, "Edge1")], [(target, "Face1"), (body, "")]):
            with self.subTest(selection=[(obj.Name, sub) for obj, sub in selection]):
                self.select(*selection)
                self.assertTrue(ExtendCutCommand().IsActive())

    def test_the_joint_commands_read_miter_extend_cut_notch_on_the_toolbar(self):
        from freecad.maxproframe.InitGui import MaxProFrame

        tools = MaxProFrame.toolbox_maxproframe
        start = tools.index("MaxProFrame_EndMiter")
        self.assertEqual(
            tools[start : start + 3], ["MaxProFrame_EndMiter", "MaxProFrame_ExtendCut", "MaxProFrame_Notch"]
        )
        resources = ExtendCutCommand().GetResources()
        self.assertEqual(resources["MenuText"], "Extend / Cut")
        self.assertTrue(resources["Pixmap"].endswith("corner-end-trim.svg"))


class TestExtendCutPanel(PanelFixture):
    def test_preselection_gives_a_face_target_and_the_profiles(self):
        target = self.target()
        p1, p2 = self.profile(0, 300), self.profile(0, 500)
        face = self.near_face(target)
        panel = self.run_command((target, face), (p1, ""), (p2, "Face1"))
        self.assertEqual(panel.target, (target, (face,)))
        self.assertEqual(panel.profiles, [p1, p2])
        self.assertEqual(panel.form.profiles_list.count(), 2)
        self.assertIn(target.Label, panel.form.target_label.text())
        self.assertIn(face, panel.form.target_label.text())
        self.assertEqual(self.message(panel), "")

    def test_a_whole_profile_selected_first_is_the_target(self):
        target = self.target()
        body = self.profile(0, 300)
        panel = self.run_command((target, ""), (body, ""))
        self.assertEqual(panel.target, (target, ()))
        self.assertEqual(panel.profiles, [body])

    def test_clicks_set_the_target_then_add_whole_profiles(self):
        target = self.target()
        p1, p2 = self.profile(0, 300), self.profile(0, 500)
        panel = self.run_command()
        self.assertIsNone(panel.target)
        face = self.near_face(target)
        self.click(target, face)
        self.assertEqual(panel.target, (target, (face,)))
        self.click(p1, "Face2")
        self.click(p2, "Edge3")
        self.click(p1, "Face1")
        self.assertEqual(panel.profiles, [p1, p2])
        self.assertEqual(panel.form.profiles_list.count(), 2)

    def test_ctrl_click_on_a_listed_profile_removes_it(self):
        target = self.target()
        p1, p2 = self.profile(0, 300), self.profile(0, 500)
        panel = self.run_command((target, self.near_face(target)), (p1, ""), (p2, ""))
        self.click(p1, "Face2", ctrl=True)
        self.assertEqual(panel.profiles, [p2])
        self.assertEqual(panel.form.profiles_list.count(), 1)

    def test_the_target_and_its_trim_chain_cannot_be_cut(self):
        target = self.target()
        far = self.profile(1000, 600)
        trim = make_notch_profile(target, far)
        self.doc.recompute()
        panel = self.run_command((trim, self.near_face(trim)))
        for obj in (trim, target):
            with self.subTest(obj=obj.Name):
                self.click(obj, "Face1")
                self.assertEqual(panel.profiles, [])
                self.assertIn(f"{obj.Label} cannot trim itself", self.message(panel))

    def test_an_invalid_target_is_explained(self):
        target = self.target()
        sketch = target.AttachmentSupport[0][0]
        panel = self.run_command((target, "Edge1"))
        self.assertIsNone(panel.target)
        self.assertIn(f"{target.Label}: Edge1 is not a face", self.message(panel))
        self.close_panels()
        panel = self.run_command((sketch, ""))
        self.assertIsNone(panel.target)
        self.assertIn(f"{sketch.Label} is not a profile", self.message(panel))

    def test_ok_creates_one_extend_cut_per_profile_in_one_undo_step(self):
        target = self.target()
        p1, p2 = self.profile(0, 300), self.profile(1000, 600)
        self.doc.clearUndos()
        panel = self.run_command((target, ""), (p1, ""), (p2, ""))
        panel.form.sb_gap.setValue(2.0)
        self.assertTrue(panel.accept())
        trims = self.extend_cuts()
        self.assertEqual(sorted(obj.Name for obj in trims), sorted([f"{p1.Name}_Tr", f"{p2.Name}_Tr"]))
        for obj in trims:
            self.assertEqual(obj.getStatusString(), "Valid")
            self.assertEqual(obj.TrimmingBoundary, [(target, ("",))])
            self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        by_body = {obj.TrimmedBody: obj for obj in trims}
        self.assertAlmostEqual(by_body[p1].Shape.BoundBox.XMax, NEAR - 2.0, places=5)
        self.assertAlmostEqual(by_body[p2].Shape.BoundBox.XMin, FAR + 2.0, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.extend_cuts(), [])

    def test_ok_places_each_trim_in_its_profile_container(self):
        target = self.target()
        p1 = self.profile(0, 300)
        part = self.doc.addObject("App::Part", "Part")
        part.addObjects([p1.AttachmentSupport[0][0], p1])
        self.doc.recompute()
        panel = self.run_command((target, self.near_face(target)), (p1, ""))
        self.assertTrue(panel.accept())
        (trim,) = self.extend_cuts()
        self.assertEqual(trim.getParentGeoFeatureGroup(), part)

    def test_ok_without_target_or_profiles_keeps_the_panel_open(self):
        target = self.target()
        panel = self.run_command()
        self.assertFalse(panel.accept())
        self.assertIn("Select the target face or profile", self.message(panel))
        panel.set_target(target, ())
        self.assertFalse(panel.accept())
        self.assertIn("Select the profiles to extend or cut", self.message(panel))
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.extend_cuts(), [])

    def test_a_failing_ok_creates_nothing_and_keeps_the_panel_open(self):
        tube = self.doc.addObject("Part::Feature", "Tube")
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(400, 0, -50))
        lateral = next(
            f"Face{index}"
            for index, face in enumerate(tube.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        body = self.profile(0, 300)
        self.doc.recompute()
        self.doc.clearUndos()
        before = len(self.doc.Objects)
        panel = self.run_command((tube, lateral), (body, ""))
        self.assertFalse(panel.accept())
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIn(f"the target face {lateral} of {tube.Label} is not planar", self.message(panel))
        self.assertEqual(len(self.doc.Objects), before)
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertTrue(body.ViewObject.Visibility)

    def test_cancel_creates_nothing_and_stops_listening(self):
        target = self.target()
        body = self.profile(0, 300)
        self.doc.clearUndos()
        before = len(self.doc.Objects)
        panel = self.run_command((target, self.near_face(target)))
        self.assertTrue(panel.reject())
        self.click(body, "Face1")
        self.assertEqual(panel.profiles, [])
        self.assertEqual(len(self.doc.Objects), before)
        self.assertEqual(self.doc.UndoCount, 0)


class TestEditExtendCut(PanelFixture):
    def existing(self, gap=0.0):
        target = self.target()
        body = self.profile(0, 300)
        obj = make_extend_cut_profile(body, (target, (self.near_face(target),)), gap)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.doc.clearUndos()
        return target, body, obj

    def test_editing_changes_target_and_gap_in_one_undo_step(self):
        target, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertIs(panel.edited, obj)
        self.assertEqual(panel.profiles, [body])
        self.assertEqual(panel.target, (target, (self.near_face(target),)))
        far_face = self.face_towards(target, App.Vector(1, 0, 0))
        self.click(target, far_face)
        self.assertEqual(panel.target, (target, (far_face,)))
        panel.form.sb_gap.setValue(3.0)
        self.assertTrue(panel.accept())
        self.assertEqual(obj.TrimmingBoundary, [(target, (far_face,))])
        self.assertAlmostEqual(obj.TrimGap.Value, 3.0)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, FAR - 3.0, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(obj.TrimmingBoundary, [(target, (self.near_face(target),))])
        self.assertAlmostEqual(obj.TrimGap.Value, 0.0)

    def test_cancel_after_editing_changes_nothing_and_leaves_no_undo_step(self):
        target, body, obj = self.existing(gap=1.0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertEqual(panel.form.sb_gap.value(), 1.0)
        self.click(target, self.face_towards(target, App.Vector(1, 0, 0)))
        panel.form.sb_gap.setValue(4.0)
        self.assertTrue(panel.reject())
        self.assertEqual(obj.TrimmingBoundary, [(target, (self.near_face(target),))])
        self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 1.0, places=5)
        self.assertEqual(self.doc.UndoCount, 0)


class TestExtendCutTranslations(PanelFixture):
    def test_panel_text_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command()
        form = panel.form
        self.assertEqual(form.windowTitle(), "Extender / cortar")
        self.assertEqual(form.groupBox_target.title(), "Destino")
        self.assertEqual(form.target_label.text(), "Hacé clic en una cara o seleccioná un perfil en el árbol.")
        self.assertEqual(form.groupBox_profiles.title(), "Perfiles")
        self.assertEqual(form.hint_label.text(), "Hacé clic en los perfiles a extender o cortar. Ctrl+clic quita uno.")
        self.assertEqual(form.remove_button.text(), "Quitar")
        self.assertEqual(form.gap_label.text(), "Separación")
        self.assertFalse(panel.accept())
        self.assertEqual(form.message_label.text(), "Seleccioná la cara o el perfil destino.")

    def test_messages_and_edit_title_are_spanish(self):
        target = self.target()
        body = self.profile(0, 300)
        sketch = body.AttachmentSupport[0][0]
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((target, "Edge1"), (sketch, ""))
        text = self.message(panel)
        self.assertIn(f"{target.Label}: Edge1 no es una cara", text)
        self.assertIn(f"{sketch.Label} no es un perfil", text)
        panel.set_target(target, ())
        self.assertFalse(panel.accept())
        self.assertEqual(self.message(panel), "Seleccioná los perfiles a extender o cortar.")
        self.close_panels()
        obj = make_extend_cut_profile(body, (target, ()), 0.0)
        self.doc.recompute()
        edit = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertEqual(edit.form.windowTitle(), "Editar extender / cortar")
        self.assertEqual(edit.form.hint_label.text(), "Hacé clic en una cara para cambiar el destino.")

    def test_panel_text_stays_english_in_english(self):
        panel = self.run_command()
        self.assertEqual(panel.form.windowTitle(), "Extend / Cut")
        self.assertEqual(panel.form.groupBox_target.title(), "Target")
        self.assertEqual(panel.form.target_label.text(), "Click a face, or select a profile in the tree.")


if __name__ == "__main__":
    unittest.main()

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

from freecad.maxproframe import create_extend_cut_tool, create_notch_tool
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

    def tube(self):
        """A round tube crossing the X axis at 400, and its curved face."""
        tube = self.doc.addObject("Part::Feature", "Tube")
        tube.Shape = Part.makeCylinder(10, 100, App.Vector(400, 0, -50))
        lateral = next(
            f"Face{index}"
            for index, face in enumerate(tube.Shape.Faces, start=1)
            if isinstance(face.Surface, Part.Cylinder)
        )
        return tube, lateral

    @staticmethod
    def force_target(panel, obj, sub):
        """A target the clicks refuse, to make OK fail: the recompute errors stay the last line of defense."""
        panel.target = (obj, (sub,))
        panel._show([])
        panel._changed()
        panel._update_preview()


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

    def sketch_area(self):
        """A closed sketch showing its inner face, like the guide sketch of a frame."""
        square = ((0, -100, 0), (300, -100, 0), (300, 100, 0), (0, 100, 0))
        sketch = self.make_sketch(*zip(square, square[1:] + square[:1]))
        sketch.MakeInternals = True
        self.doc.recompute()
        return sketch

    def test_a_sketch_internal_face_is_highlighted(self):
        # A click inside a closed sketch picks InternalFace1, which Shape.getElement does not know.
        lines = create_extend_cut_tool._edge_lines(self.sketch_area(), "InternalFace1")
        self.assertEqual(len(lines), 4)

    def test_a_click_inside_a_sketch_is_refused_and_keeps_the_target(self):
        sketch = self.sketch_area()
        target = self.target()
        face = self.near_face(target)
        body = self.profile(0, 300)
        panel = self.run_command()
        self.click(sketch, "InternalFace1")
        self.assertIsNone(panel.target)
        self.assertEqual(self.message(panel), f"{sketch.Label}: a sketch cannot be the target")
        self.click(target, face)
        self.click(body, "")
        panel.form.change_target_button.setChecked(True)
        self.click(sketch, "InternalFace1")
        self.assertEqual(panel.target, (target, (face,)))
        self.assertEqual(panel.profiles, [body])
        self.assertTrue(panel.form.change_target_button.isChecked())
        self.assertEqual(self.message(panel), f"{sketch.Label}: a sketch cannot be the target")

    def test_a_click_on_a_curved_face_is_refused(self):
        tube, lateral = self.tube()
        panel = self.run_command()
        self.click(tube, lateral)
        self.assertIsNone(panel.target)
        self.assertEqual(self.message(panel), f"{tube.Label}: {lateral} is not a planar face")

    def test_a_face_parallel_to_a_profile_is_refused_as_target_and_as_profile(self):
        target = self.target()
        face = self.near_face(target)
        top = self.face_towards(target, App.Vector(0, 0, 1))
        body = self.profile(0, 300)
        message = f"{body.Label} runs parallel to the target: it cannot reach it"
        panel = self.run_command((target, face), (body, ""))
        panel.form.change_target_button.setChecked(True)
        self.click(target, top)
        self.assertEqual(panel.target, (target, (face,)))
        self.assertEqual(self.message(panel), message)
        self.close_panels()
        panel = self.run_command((target, top))
        self.click(body, "")
        self.assertEqual(panel.profiles, [])
        self.assertEqual(self.message(panel), message)

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
        tube, lateral = self.tube()
        body = self.profile(0, 300)
        self.doc.recompute()
        self.doc.clearUndos()
        before = len(self.doc.Objects)
        panel = self.run_command()
        panel.profiles = [body]
        self.force_target(panel, tube, lateral)
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


class TestExtendCutApplyAndContinue(PanelFixture):
    """S1-S5: Apply and continue cuts one end, keeps the profiles and waits for the target of the other end."""

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
        QtWidgets.QApplication.processEvents()

    def between(self):
        """A right target at X = 400 (faces 375, 425), a left one at X = -200 (faces -225, -175), and two
        profiles from 0 to 300 between them."""
        right = self.target()
        left = self.make_profile(self.make_sketch(((-200, -200, 0), (-200, 200, 0))), "Edge1", **CENTER)
        p1 = self.profile(0, 300)
        p2 = self.make_profile(self.make_sketch(((0, 100, 0), (300, 100, 0))), "Edge1", extension=0.0, **CENTER)
        return right, left, p1, p2

    def test_the_button_shows_only_while_creating_and_needs_a_target_and_a_profile(self):
        right, _, p1, _ = self.between()
        panel = self.run_command()
        button = self.apply_button()
        self.assertEqual(button.text(), "Apply and continue")
        self.assertFalse(button.isEnabled())
        self.click(right, self.near_face(right))
        self.assertFalse(button.isEnabled())
        self.click(p1, "")
        self.assertTrue(button.isEnabled())
        self.assertTrue(panel.reject())
        self.close_panels()
        existing = self.extend_cut(p1, right, (self.near_face(right),))
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).setEdit(existing, 0)
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(self.apply_button())

    def test_both_ends_between_two_targets_each_in_its_own_undo_step(self):
        right, left, p1, p2 = self.between()
        self.doc.clearUndos()
        panel = self.run_command((right, self.near_face(right)), (p1, ""), (p2, ""))
        panel.form.sb_gap.setValue(2.0)
        self.apply()
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(self.doc.UndoCount, 1)
        first = {obj.TrimmedBody: obj for obj in self.extend_cuts()}
        self.assertEqual(set(first), {p1, p2})
        # The profiles stay, each now its trim; the target goes, and the next click sets it.
        self.assertIsNone(panel.target)
        self.assertEqual(panel.profiles, [first[p1], first[p2]])
        self.assertEqual(panel.form.sb_gap.value(), 2.0)
        self.assertFalse(self.apply_button().isEnabled())
        self.click(left, self.face_towards(left, App.Vector(1, 0, 0)))
        self.assertEqual(panel.target[0], left)
        self.assertTrue(panel.accept())
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.doc.UndoCount, 2)
        for body in (p1, p2):
            [last] = [obj for obj in self.extend_cuts() if obj.TrimmedBody == first[body]]
            self.assertEqual(last.getStatusString(), "Valid")
            self.assertAlmostEqual(last.Shape.BoundBox.XMin, -175.0 + 2.0, places=5)
            self.assertAlmostEqual(last.Shape.BoundBox.XMax, NEAR - 2.0, places=5)
        self.doc.undo()
        self.assertEqual(sorted(obj.Name for obj in self.extend_cuts()), sorted(o.Name for o in first.values()))

    def test_ok_after_apply_with_no_new_target_adds_no_undo_step(self):
        right, _, p1, _ = self.between()
        self.doc.clearUndos()
        panel = self.run_command((right, self.near_face(right)), (p1, ""))
        self.apply()
        self.assertTrue(panel.accept())
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertEqual(len(self.extend_cuts()), 1)

    def test_cancel_after_apply_removes_only_the_newer_trims(self):
        right, left, p1, _ = self.between()
        self.doc.clearUndos()
        panel = self.run_command((right, self.near_face(right)), (p1, ""))
        self.apply()
        [kept] = self.extend_cuts()
        self.click(left, self.face_towards(left, App.Vector(1, 0, 0)))
        panel._update_preview(force=True)
        self.assertEqual(len(self.extend_cuts()), 2)
        self.assertTrue(panel.reject())
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.extend_cuts(), [kept])
        self.assertEqual(self.doc.UndoCount, 1)

    def test_a_profile_already_cut_against_the_target_is_not_cut_again(self):
        right, _, p1, p2 = self.between()
        face = self.near_face(right)
        done = self.extend_cut(p1, right, (face,))
        # A profile clicked while that target is set is not added.
        panel = self.run_command((right, face))
        self.click(done, "")
        self.assertEqual(panel.profiles, [])
        self.assertEqual(self.message(panel), f"{p1.Label} is already cut against this target")
        self.click(p2, "")
        self.assertEqual(panel.profiles, [p2])
        self.assertTrue(panel.reject())
        self.close_panels()
        # After Apply and continue, the same target clicked again is not taken.
        panel = self.run_command((right, face), (p2, ""))
        self.apply()
        self.click(right, face)
        self.assertIsNone(panel.target)
        self.assertEqual(self.message(panel), f"{p2.Label} is already cut against this target")
        self.assertTrue(panel.reject())

    def test_a_failing_second_apply_keeps_the_first_cuts_and_the_panel_open(self):
        # R3-001: an apply that fails leaves the earlier one as it is, with no other Undo step.
        right, left, p1, _ = self.between()
        self.doc.clearUndos()
        panel = self.run_command((right, self.near_face(right)), (p1, ""))
        self.apply()
        [first] = self.extend_cuts()
        self.click(left, self.face_towards(left, App.Vector(1, 0, 0)))
        with patch.object(create_extend_cut_tool, "_failures", return_value="boom"):
            self.assertFalse(panel.apply_and_continue())
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIn("boom", self.message(panel))
        self.assertEqual(self.extend_cuts(), [first])
        self.assertEqual(panel.profiles, [first])
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertTrue(panel.reject())

    def test_a_profile_without_its_preview_stays_uncut_after_apply(self):
        # R3-005: a profile whose preview is gone is kept as it is instead of failing the apply.
        right, _, p1, p2 = self.between()
        panel = self.run_command((right, self.near_face(right)), (p1, ""), (p2, ""))
        panel._update_preview(force=True)
        with patch.object(panel, "_update_preview"):
            panel._drop_preview(p2.Name)
            self.assertTrue(panel.apply_and_continue())
        [cut] = self.extend_cuts()
        self.assertEqual(cut.TrimmedBody, p1)
        self.assertEqual(panel.profiles, [cut, p2])
        self.assertTrue(panel.reject())

    def test_a_whole_target_and_a_face_of_it_are_the_same_target(self):
        # R3-003: a profile cut against a face is not cut again against the whole profile, nor the other way.
        right, _, p1, p2 = self.between()
        face_cut = self.extend_cut(p1, right, (self.near_face(right),))
        whole_cut = self.extend_cut(p2, right, ())
        panel = self.run_command((right, ""))
        self.click(face_cut, "")
        self.assertEqual(self.message(panel), f"{p1.Label} is already cut against this target")
        self.assertTrue(panel.reject())
        self.close_panels()
        panel = self.run_command((right, self.near_face(right)))
        self.click(whole_cut, "")
        self.assertEqual(panel.profiles, [])
        self.assertEqual(self.message(panel), f"{p2.Label} is already cut against this target")
        self.assertTrue(panel.reject())

    def test_notch_has_apply_and_continue_too(self):
        right, _, p1, _ = self.between()
        created = []
        base = create_notch_tool.NotchTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        self.select((right, ""), (p1, ""))
        with patch.object(create_notch_tool, "NotchTaskPanel", Recording):
            create_notch_tool.NotchCommand().Activated()
        self.panels.extend(created)
        [panel] = created
        self.assertEqual(self.apply_button().text(), "Apply and continue")
        panel._update_preview(force=True)
        self.apply()
        notches = [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Notch"]
        self.assertEqual(len(notches), 1)
        self.assertIsNone(panel.target)
        self.assertEqual(panel.profiles, notches)
        self.assertTrue(panel.reject())
        # R3-002: Cancel after an apply keeps the applied notch.
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Notch"], notches
        )

    def test_the_button_is_spanish(self):
        use_language(self, "Spanish", "es_ES")
        QtWidgets.QApplication.processEvents()
        self.run_command()
        self.assertEqual(self.apply_button().text(), "Aplicar y seguir")
        self.assertTrue(self.apply_button().toolTip().startswith("Crear estos cortes en su propio paso de deshacer"))


class EditFixture(PanelFixture):
    def existing(self, gap=0.0):
        target = self.target()
        body = self.profile(0, 300)
        obj = make_extend_cut_profile(body, (target, (self.near_face(target),)), gap)
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        self.doc.clearUndos()
        return target, body, obj


class TestEditExtendCut(EditFixture):

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


class TestExtendCutGapExpressions(EditFixture):
    """While editing, the Gap takes a FreeCAD expression (Fx) bound to the trim's TrimGap."""

    def varset(self, gap):
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "Gap")
        varset.Gap = gap
        self.doc.recompute()
        self.doc.clearUndos()
        return varset

    def edit(self, obj):
        return self.capture_panel(obj.ViewObject.Proxy.edit)

    def set_gap_expression(self, obj, varset):
        """What the Fx editor does: the expression goes on the bound property at once."""
        obj.setExpression("TrimGap", f"{varset.Name}.Gap")
        self.doc.recompute()

    def test_the_edit_gap_is_bound_and_the_create_gap_is_not(self):
        target = self.target()
        body = self.profile(0, 300)
        panel = self.run_command((target, self.near_face(target)), (body, ""))
        # One preview per profile: no single property to bind.
        self.assertFalse(Gui.ExpressionBinding(panel.form.sb_gap).isBound())
        panel.form.sb_gap.setValue(2.0)
        self.assertTrue(panel.accept())
        (created,) = self.extend_cuts()
        self.assertAlmostEqual(created.TrimGap.Value, 2.0)
        self.assertEqual(dict(created.ExpressionEngine), {})
        varset = self.varset(3.0)
        panel = self.edit(created)
        self.assertTrue(Gui.ExpressionBinding(panel.form.sb_gap).isBound())
        self.set_gap_expression(created, varset)
        self.assertTrue(Gui.ExpressionBinding(panel.form.sb_gap).hasExpression())
        self.assertAlmostEqual(panel.form.sb_gap.value(), 3.0, places=6)
        self.assertTrue(panel.reject())

    def test_ok_keeps_an_expression_set_in_the_panel_in_one_undo_step(self):
        _, _, obj = self.existing()
        varset = self.varset(2.0)
        panel = self.edit(obj)
        self.set_gap_expression(obj, varset)
        self.assertTrue(panel.accept())
        self.assertEqual(dict(obj.ExpressionEngine), {"TrimGap": f"{varset.Name}.Gap"})
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 2.0, places=5)
        varset.Gap = 3.0
        self.doc.recompute()
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 3.0, places=5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(dict(obj.ExpressionEngine), {})
        self.assertAlmostEqual(obj.TrimGap.Value, 0.0)

    def test_ok_with_only_an_expression_set_keeps_it_in_one_undo_step(self):
        # The expression gives the gap it already had: only the expression changes.
        _, _, obj = self.existing(gap=1.0)
        varset = self.varset(1.0)
        panel = self.edit(obj)
        self.set_gap_expression(obj, varset)
        self.assertTrue(panel.accept())
        self.assertEqual(dict(obj.ExpressionEngine), {"TrimGap": f"{varset.Name}.Gap"})
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_removes_an_expression_set_in_the_panel(self):
        _, _, obj = self.existing(gap=1.0)
        varset = self.varset(2.0)
        panel = self.edit(obj)
        self.set_gap_expression(obj, varset)
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertTrue(panel.reject())
        self.assertEqual(dict(obj.ExpressionEngine), {})
        self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 1.0, places=5)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_with_undo_off_removes_an_expression_set_in_the_panel(self):
        _, _, obj = self.existing(gap=1.0)
        varset = self.varset(2.0)
        panel = self.edit(obj)
        self.doc.UndoMode = 0
        self.addCleanup(setattr, self.doc, "UndoMode", 1)
        self.set_gap_expression(obj, varset)
        self.assertAlmostEqual(obj.TrimGap.Value, 2.0)
        self.assertTrue(panel.reject())
        self.assertEqual(dict(obj.ExpressionEngine), {})
        self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, NEAR - 1.0, places=5)

    def test_an_existing_expression_is_shown_and_kept_while_the_target_changes(self):
        target, _, obj = self.existing()
        varset = self.varset(2.0)
        self.set_gap_expression(obj, varset)
        self.doc.clearUndos()
        panel = self.edit(obj)
        self.assertTrue(Gui.ExpressionBinding(panel.form.sb_gap).hasExpression())
        self.assertAlmostEqual(panel.form.sb_gap.value(), 2.0, places=6)
        far_face = self.face_towards(target, App.Vector(1, 0, 0))
        self.click(target, far_face)
        self.assertTrue(panel.accept())
        self.assertEqual(obj.TrimmingBoundary, [(target, (far_face,))])
        self.assertEqual(dict(obj.ExpressionEngine), {"TrimGap": f"{varset.Name}.Gap"})
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, FAR - 2.0, places=5)
        varset.Gap = 3.0
        self.doc.recompute()
        self.assertAlmostEqual(obj.Shape.BoundBox.XMax, FAR - 3.0, places=5)
        self.assertEqual(self.doc.UndoCount, 1)

    def test_an_expression_set_after_a_failing_ok_is_in_the_undo_step(self):
        target, _, obj = self.existing()
        tube, lateral = self.tube()
        varset = self.varset(2.0)
        panel = self.edit(obj)
        self.force_target(panel, tube, lateral)
        self.assertFalse(panel.accept())
        # The panel stays open: the Fx editor still changes the trim inside the edit transaction.
        self.click(target, self.near_face(target))
        self.set_gap_expression(obj, varset)
        self.assertTrue(panel.accept())
        self.assertEqual(dict(obj.ExpressionEngine), {"TrimGap": f"{varset.Name}.Gap"})
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(dict(obj.ExpressionEngine), {})


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

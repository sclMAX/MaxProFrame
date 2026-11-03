"""Extend / Cut panel polish: Flip side state, Change target, tree icon and label, and the live edit preview."""

import unittest

import FreeCAD as App
from miter_helpers import use_language
from PySide import QtWidgets
from test_end_miter_geometry import CENTER
from test_extend_cut_geometry import FAR, NEAR
from test_extend_cut_preview import wait
from test_keep_end_panel import KeepEndFixture

from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile


class TestFlipButtonState(KeepEndFixture):
    def select_rows(self, panel, *rows):
        widget = panel.form.profiles_list
        widget.clearSelection()
        for row in rows:
            widget.item(row).setSelected(True)

    def test_flip_side_is_enabled_only_while_a_row_is_selected(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.assertFalse(panel.form.flip_button.isEnabled())
        self.select_rows(panel, 0)
        self.assertTrue(panel.form.flip_button.isEnabled())
        panel.form.flip_button.click()
        # The flipped rows stay selected, so the button stays usable.
        self.assertTrue(panel.form.flip_button.isEnabled())
        self.select_rows(panel)
        self.assertFalse(panel.form.flip_button.isEnabled())

    def test_a_rebuilt_list_without_a_selection_disables_flip_side(self):
        target, face, body = self.crossing()
        other = self.profile(0, 400)
        panel = self.run_command((target, face), (body, ""), (other, ""))
        self.select_rows(panel, 1)
        self.assertTrue(panel.form.flip_button.isEnabled())
        panel.form.remove_button.click()
        self.assertEqual(panel.profiles, [body])
        self.assertFalse(panel.form.flip_button.isEnabled())

    def test_editing_enables_flip_side_only_with_the_row_selected(self):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertFalse(panel.form.flip_button.isEnabled())
        self.select_rows(panel, 0)
        self.assertTrue(panel.form.flip_button.isEnabled())


class TestChangeTarget(KeepEndFixture):
    def run_command(self, *items):
        panel = super().run_command(*items)
        # The language switch of setUp is delivered on the first event loop pass and resets the Designer texts.
        QtWidgets.QApplication.processEvents()
        panel._show([])
        return panel

    def far_face(self, target):
        return self.face_towards(target, App.Vector(1, 0, 0))

    def test_change_target_makes_the_next_click_the_target_then_clicks_add_profiles(self):
        target, face, body = self.crossing()
        other = self.profile(0, 300)
        panel = self.run_command((target, face), (body, ""))
        button = panel.form.change_target_button
        self.assertEqual(button.text(), "Change target")
        self.assertTrue(button.isEnabled())
        button.click()
        self.assertTrue(button.isChecked())
        self.assertEqual(panel.form.target_label.text(), "Click the new target face, or select a profile in the tree.")
        far = self.far_face(target)
        self.click(target, far)
        self.assertFalse(button.isChecked())
        self.assertEqual(panel.target, (target, (far,)))
        self.assertEqual(panel.form.target_label.text(), f"{target.Label} ({target.Name}) {far}")
        self.assertEqual(panel.profiles, [body])
        wait()
        self.assertEqual(self.trim_of(body).TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.box(self.trim_of(body).Shape), (0.0, FAR))
        self.click(other, "Face1")
        self.assertEqual(panel.profiles, [body, other])
        self.assertEqual(panel.target, (target, (far,)))
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.doc.UndoCount, 1)

    def test_pressing_change_target_again_cancels_it(self):
        target, face, body = self.crossing()
        other = self.profile(0, 300)
        panel = self.run_command((target, face), (body, ""))
        button = panel.form.change_target_button
        button.click()
        button.click()
        self.assertFalse(button.isChecked())
        self.assertEqual(panel.form.target_label.text(), f"{target.Label} ({target.Name}) {face}")
        self.click(other, "Face1")
        self.assertEqual(panel.target, (target, (face,)))
        self.assertEqual(panel.profiles, [body, other])

    def test_a_listed_profile_is_refused_as_target_and_change_target_stays_armed(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        button = panel.form.change_target_button
        button.click()
        self.click(body, "Face1")
        self.assertEqual(self.message(panel), f"{body.Label} cannot trim itself")
        self.assertTrue(button.isChecked())
        self.assertEqual(panel.target, (target, (face,)))
        far = self.far_face(target)
        self.click(target, far)
        self.assertFalse(button.isChecked())
        self.assertEqual(panel.target, (target, (far,)))

    def test_change_target_is_disabled_without_a_target_and_hidden_while_editing(self):
        target, face, body = self.crossing()
        panel = self.run_command()
        self.assertFalse(panel.form.change_target_button.isEnabled())
        self.click(target, face)
        self.assertTrue(panel.form.change_target_button.isEnabled())
        self.close_panels()
        obj = make_extend_cut_profile(body, (target, (face,)))
        self.doc.recompute()
        edit = self.capture_panel(obj.ViewObject.Proxy.edit)
        # While editing every click already changes the target.
        self.assertFalse(edit.form.change_target_button.isVisibleTo(edit.form))

    def test_notch_changes_its_target_profile(self):
        from test_keep_end_panel import TestFlipSide

        from freecad.maxproframe.create_notch_tool import NotchCommand

        body = self.make_profile(self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        other = self.make_profile(self.make_sketch(((200, -200, 0), (200, 200, 0))), "Edge1", **CENTER)
        self.doc.clearUndos()
        self.select((target, ""), (body, ""))
        panel = TestFlipSide.capture_notch(self, NotchCommand().Activated)
        panel.form.change_target_button.click()
        self.assertEqual(panel.form.target_label.text(), "Click the new target profile, or select it in the tree.")
        self.click(other, "Face1")
        self.assertEqual(panel.target, (other, ()))
        self.assertEqual(panel.profiles, [body])
        self.assertTrue(panel.accept())
        notch = [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Notch"]
        self.assertEqual([obj.TrimmingBoundary for obj in notch], [[(other, ("",))]])


class TestChangeTargetTranslations(KeepEndFixture):
    def settle(self, panel):
        # The pending language switch resets the Designer texts on the first event loop pass; redraw after it.
        QtWidgets.QApplication.processEvents()
        panel._show([])

    def test_change_target_texts_are_spanish(self):
        target, face, body = self.crossing()
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((target, face), (body, ""))
        button = panel.form.change_target_button
        self.assertEqual(button.text(), "Cambiar destino")
        self.settle(panel)
        button.click()
        self.assertEqual(
            panel.form.target_label.text(), "Hacé clic en la nueva cara destino o seleccioná un perfil en el árbol."
        )

    def test_notch_change_target_text_is_spanish(self):
        from test_keep_end_panel import TestFlipSide

        from freecad.maxproframe.create_notch_tool import NotchCommand

        body = self.make_profile(self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        self.doc.clearUndos()
        use_language(self, "Spanish", "es_ES")
        self.select((target, ""), (body, ""))
        panel = TestFlipSide.capture_notch(self, NotchCommand().Activated)
        self.assertEqual(panel.form.change_target_button.text(), "Cambiar destino")
        self.settle(panel)
        panel.form.change_target_button.click()
        self.assertEqual(
            panel.form.target_label.text(), "Hacé clic en el nuevo perfil destino o seleccionalo en el árbol."
        )


class TestTreeIconAndLabel(KeepEndFixture):
    def test_new_trims_are_labelled_after_their_profile(self):
        from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
        from freecad.maxproframe.create_notch_tool import make_notch_profile

        target, face, body = self.crossing()
        body.Label = "Profile_TC40x40x1.5_001"
        panel = self.run_command((target, face), (body, ""))
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).Label, "Profile_TC40x40x1.5_001_Tr")
        other = self.profile(0, 300)
        other.Label = "Profile_RT20x40_002"
        self.assertEqual(make_notch_profile(other, target).Label, "Profile_RT20x40_002_Tr")
        self.assertEqual(make_end_miter_profile(other, []).Label, "Profile_RT20x40_002_Mt")

    def test_each_joint_shows_the_icon_of_its_command(self):
        import os

        from freecad.maxproframe.create_end_miter_tool import CreateEndMiterCommand
        from freecad.maxproframe.create_extend_cut_tool import ExtendCutCommand
        from freecad.maxproframe.create_notch_tool import NotchCommand

        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        commands = (("Extend Cut", ExtendCutCommand), ("Notch", NotchCommand), ("End Miter", CreateEndMiterCommand))
        for joint, command in commands:
            obj.TrimmedProfileType = joint
            icon = obj.ViewObject.Proxy.getIcon()
            self.assertEqual(icon, command().GetResources()["Pixmap"], joint)
            self.assertTrue(os.path.isfile(icon), icon)


class TestLiveEditPreview(KeepEndFixture):
    def existing(self, gap=0.0):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)), gap)
        obj.Label = "My trim"
        self.doc.recompute()
        self.doc.clearUndos()
        return target, face, body, obj

    def flip(self, panel):
        self.flip_rows(panel, 0)

    def test_flipping_while_editing_shows_the_other_piece_at_once_with_the_discarded_one(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))
        self.flip(panel)
        self.assertEqual(obj.KeepEnd, "End")
        self.assertEqual(self.box(obj.Shape), (NEAR, 500.0))
        [(trim, piece)] = panel.discarded()
        self.assertIs(trim, obj)
        self.assertEqual(self.box(piece), (0.0, NEAR))
        self.assertTrue(panel.accept())
        self.assertEqual(obj.KeepEnd, "End")
        self.assertEqual(self.box(obj.Shape), (NEAR, 500.0))
        self.assertEqual(obj.Label, "My trim")
        self.assertEqual(self.doc.UndoCount, 1)
        self.assertEqual(panel.discarded(), [])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))

    def test_target_and_gap_changes_while_editing_are_previewed(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        far = self.face_towards(target, App.Vector(1, 0, 0))
        self.click(target, far)
        panel.form.sb_gap.setValue(3.0)
        wait()
        self.assertEqual(obj.TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.box(obj.Shape), (0.0, FAR - 3.0))
        self.assertTrue(panel.accept())
        self.assertEqual(self.box(obj.Shape), (0.0, FAR - 3.0))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_after_a_live_edit_restores_the_trim(self):
        target, face, body, obj = self.existing(gap=1.0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip(panel)
        panel.form.sb_gap.setValue(4.0)
        wait()
        self.assertAlmostEqual(obj.TrimGap.Value, 4.0)
        self.assertTrue(panel.reject())
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertAlmostEqual(obj.TrimGap.Value, 1.0)
        self.assertEqual(obj.TrimmingBoundary, [(target, (face,))])
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR - 1.0))
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertEqual(panel.discarded(), [])

    def test_cancel_restores_the_trim_with_undo_disabled(self):
        target, face, body, obj = self.existing()
        self.doc.UndoMode = 0
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip(panel)
        self.assertEqual(obj.KeepEnd, "End")
        self.assertTrue(panel.reject())
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))

    def test_closing_the_edit_without_ok_or_cancel_restores_the_trim(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip(panel)
        panel.closed()
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))
        self.assertEqual(self.doc.UndoCount, 0)


if __name__ == "__main__":
    unittest.main()

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
from freecad.maxproframe.create_notch_tool import make_notch_profile


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

    def test_toggling_change_target_keeps_the_messages(self):
        target, face, body = self.crossing()
        sketch = body.AttachmentSupport[0][0]
        panel = super().run_command((target, face), (body, ""), (sketch, ""))
        # The pending language switch resets the Designer texts (see run_command): show the messages again.
        QtWidgets.QApplication.processEvents()
        panel._show_messages()
        message = f"{sketch.Label} is not a profile"
        self.assertEqual(self.message(panel), message)
        panel.form.change_target_button.click()
        self.assertEqual(self.message(panel), message)
        panel.form.change_target_button.click()
        self.assertEqual(self.message(panel), message)

    def test_a_target_lost_while_armed_disarms_change_target(self):
        target, face, body = self.crossing()
        other = self.profile(0, 300)
        panel = self.run_command((target, face), (body, ""))
        button = panel.form.change_target_button
        button.click()
        for obj in [o for o in self.doc.Objects if getattr(o, "TrimmedBody", None) is not None]:
            self.doc.removeObject(obj.Name)
        self.doc.removeObject(target.Name)
        panel._show([])
        self.assertFalse(button.isChecked())
        self.assertFalse(button.isEnabled())
        new_target = self.target()
        new_face = self.near_face(new_target)
        self.click(new_target, new_face)
        self.assertEqual(panel.target, (new_target, (new_face,)))
        self.assertFalse(button.isChecked())
        self.click(other, "Face1")
        self.assertEqual(panel.profiles, [body, other])
        self.assertEqual(panel.target, (new_target, (new_face,)))

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


class TestEditUpdateAutomatically(KeepEndFixture):
    def notch_setup(self):
        body = self.make_profile(self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        other = self.make_profile(self.make_sketch(((200, -200, 0), (200, 200, 0))), "Edge1", **CENTER)
        notch = make_notch_profile(body, target)
        self.doc.recompute()
        self.doc.clearUndos()
        return body, target, other, notch

    def edit_notch(self, notch):
        from test_keep_end_panel import TestFlipSide

        return TestFlipSide.capture_notch(self, notch.ViewObject.Proxy.edit)

    def test_editing_an_extend_cut_shows_update_automatically_checked_by_default(self):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        self.doc.recompute()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertTrue(panel.form.groupBox_preview.isVisibleTo(panel.form))
        self.assertTrue(panel.form.cb_auto_update.isChecked())
        self.assertEqual(self.status(panel), "Preview updated")

    def test_editing_with_update_automatically_unchecked_waits_for_ok(self):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        panel.form.cb_auto_update.setChecked(False)
        self.flip_rows(panel, 0)
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))
        self.assertEqual(self.status(panel), "Pending changes")
        panel.form.cb_auto_update.setChecked(True)
        self.assertEqual(obj.KeepEnd, "End")
        self.assertEqual(self.box(obj.Shape), (NEAR, 500.0))
        self.assertEqual(self.status(panel), "Preview updated")
        self.assertTrue(panel.accept())
        self.assertEqual(self.doc.UndoCount, 1)

    def test_editing_a_notch_waits_like_creating_one_and_previews_once_checked(self):
        body, target, other, notch = self.notch_setup()
        volume = notch.Shape.Volume
        panel = self.edit_notch(notch)
        self.assertTrue(panel.form.groupBox_preview.isVisibleTo(panel.form))
        self.assertFalse(panel.form.cb_auto_update.isChecked())
        self.click(other, "Face1")
        wait()
        self.assertEqual(panel.target, (other, ()))
        self.assertEqual(notch.TrimmingBoundary, [(target, ("",))])
        self.assertEqual(self.status(panel), "Pending changes")
        panel.form.cb_auto_update.setChecked(True)
        self.assertEqual(notch.TrimmingBoundary, [(other, ("",))])
        self.assertEqual(self.status(panel), "Preview updated")
        self.assertEqual(len(panel.discarded()), 1)
        self.assertTrue(panel.reject())
        self.assertEqual(notch.TrimmingBoundary, [(target, ("",))])
        self.assertAlmostEqual(notch.Shape.Volume, volume, places=5)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_a_notch_edit_previewed_live_is_kept_by_ok_in_one_undo_step(self):
        body, target, other, notch = self.notch_setup()
        panel = self.edit_notch(notch)
        panel.form.cb_auto_update.setChecked(True)
        self.flip_rows(panel, 0)
        self.assertEqual(notch.KeepEnd, "Start")
        self.assertEqual(self.box(notch.Shape), (-100.0, -25.0))
        self.assertTrue(panel.accept())
        self.assertEqual(notch.KeepEnd, "Start")
        self.assertEqual(self.doc.UndoCount, 1)


class TestEditRobustness(KeepEndFixture):
    def existing(self):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        self.doc.recompute()
        self.doc.clearUndos()
        return target, face, body, obj

    def parallel_face(self, target):
        # Parallel to the profile axis: an Extend / Cut cannot end on it.
        return self.face_towards(target, App.Vector(0, 0, 1))

    def test_a_failed_ok_keeps_the_trim_and_shows_the_change_as_pending(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        panel.form.cb_auto_update.setChecked(False)
        parallel = self.parallel_face(target)
        self.click(target, parallel)
        self.assertFalse(panel.accept())
        self.assertNotEqual(self.message(panel), "")
        self.assertEqual(obj.TrimmingBoundary, [(target, (face,))])
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))
        self.assertEqual(self.doc.UndoCount, 0)
        self.assertEqual(panel.target, (target, (parallel,)))
        self.assertEqual(self.status(panel), "Pending changes")
        self.click(target, face)
        self.assertTrue(panel.accept())
        self.assertEqual(obj.TrimmingBoundary, [(target, (face,))])

    def test_after_a_failed_live_ok_the_preview_applies_the_panel_again(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.click(target, self.parallel_face(target))
        wait()
        self.assertFalse(panel.accept())
        self.assertEqual(obj.TrimmingBoundary, [(target, (face,))])
        self.assertEqual(self.status(panel), "Pending changes")
        far = self.face_towards(target, App.Vector(1, 0, 0))
        self.click(target, far)
        wait()
        self.assertEqual(obj.TrimmingBoundary, [(target, (far,))])
        self.assertEqual(self.status(panel), "Preview updated")

    def test_ok_without_a_net_change_leaves_no_undo_step(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertTrue(panel.accept())
        self.assertEqual(self.doc.UndoCount, 0)
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip_rows(panel, 0)
        self.flip_rows(panel, 0)
        self.assertTrue(panel.accept())
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.doc.UndoCount, 0)

    def test_cancel_after_the_edited_trim_was_deleted_does_not_fail(self):
        target, face, body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip_rows(panel, 0)
        name = obj.Name
        self.doc.removeObject(name)
        self.assertTrue(panel.reject())
        self.assertIsNone(self.doc.getObject(name))

    def test_a_reopened_document_shows_the_command_icon_of_each_trim(self):
        import os
        import tempfile

        target, face, body, obj = self.existing()
        other = self.profile(0, 300)
        notch = make_notch_profile(other, target)
        self.doc.recompute()
        path = os.path.join(tempfile.mkdtemp(), "icons.FCStd")
        self.doc.saveCopy(path)
        reopened = App.openDocument(path)
        self.addCleanup(App.closeDocument, reopened.Name)
        icons = {
            name: os.path.basename(reopened.getObject(name).ViewObject.Proxy.getIcon())
            for name in (obj.Name, notch.Name)
        }
        self.assertEqual(icons, {obj.Name: "corner-end-trim.svg", notch.Name: "corner-notch.svg"})


if __name__ == "__main__":
    unittest.main()

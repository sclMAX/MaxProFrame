"""Flip side in the Extend / Cut and Notch panels, and the discarded pieces drawn in their own color."""

import unittest
from unittest import mock

import FreeCAD as App
from miter_helpers import use_language
from test_extend_cut_geometry import NEAR
from test_extend_cut_preview import BLUE, ORANGE, PreviewFixture, keep_auto_preview, overlay_colors, scene_graph

from freecad.maxproframe import create_extend_cut_tool as tool
from freecad.maxproframe.create_extend_cut_tool import (
    DISCARDED,
    HIGHLIGHT_COLORS,
    ExtendCutTaskPanel,
    make_extend_cut_profile,
)

RED = (1.0, 0.1, 0.1)
NO_SIDE = "{}: the target does not cross the profile, there is no side to choose."


class KeepEndFixture(PreviewFixture):
    def crossing(self):
        """A target and a profile from 0 to 500 its near face (x = 375) crosses."""
        target = self.target()
        body = self.profile(0, 500)
        self.doc.clearUndos()
        return target, self.near_face(target), body

    def rows(self, panel):
        widget = panel.form.profiles_list
        return [widget.item(row).text() for row in range(widget.count())]

    def flip_rows(self, panel, *rows):
        widget = panel.form.profiles_list
        widget.clearSelection()
        for row in rows:
            widget.item(row).setSelected(True)
        panel.form.flip_button.click()

    def box(self, shape):
        return round(shape.BoundBox.XMin, 5), round(shape.BoundBox.XMax, 5)


class TestFlipSide(KeepEndFixture):
    def test_flip_side_keeps_the_other_piece_and_ok_stores_it_in_one_undo_step(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.assertEqual(panel.form.flip_button.text(), "Flip side")
        self.assertEqual(self.box(self.trim_of(body).Shape), (0.0, NEAR))
        self.flip_rows(panel, 0)
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name}), side flipped"])
        self.assertTrue(panel.form.profiles_list.item(0).isSelected())
        self.assertEqual(self.trim_of(body).KeepEnd, "End")
        self.assertEqual(self.box(self.trim_of(body).Shape), (NEAR, 500.0))
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "End")
        self.assertEqual(self.box(self.trim_of(body).Shape), (NEAR, 500.0))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_flipping_twice_goes_back_to_auto(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.flip_rows(panel, 0)
        self.flip_rows(panel, 0)
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name})"])
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "Auto")
        self.assertEqual(self.box(self.trim_of(body).Shape), (0.0, NEAR))

    def test_double_clicking_a_row_flips_it(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        widget = panel.form.profiles_list
        widget.itemDoubleClicked.emit(widget.item(0))
        self.assertEqual(self.trim_of(body).KeepEnd, "End")

    def test_only_the_selected_profiles_flip(self):
        target, face, body = self.crossing()
        other = self.profile(0, 600)
        panel = self.run_command((target, face), (body, ""), (other, ""))
        self.flip_rows(panel, 1)
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "Auto")
        self.assertEqual(self.trim_of(other).KeepEnd, "End")
        self.assertEqual(self.box(self.trim_of(other).Shape), (NEAR, 600.0))

    def test_a_profile_the_target_does_not_cross_is_explained_and_left_auto(self):
        target = self.target()
        short = self.profile(0, 300)
        panel = self.run_command((target, self.near_face(target)), (short, ""))
        self.flip_rows(panel, 0)
        self.assertEqual(self.message(panel), NO_SIDE.format(short.Label))
        self.assertEqual(self.rows(panel), [f"{short.Label} ({short.Name})"])
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(short).KeepEnd, "Auto")
        self.assertEqual(self.box(self.trim_of(short).Shape), (0.0, NEAR))

    def test_flip_side_works_with_update_automatically_unchecked(self):
        keep_auto_preview(self, ExtendCutTaskPanel, False)
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.flip_rows(panel, 0)
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name}), side flipped"])
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "End")
        self.assertEqual(self.box(self.trim_of(body).Shape), (NEAR, 500.0))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_flip_without_a_target_asks_for_it(self):
        _, _, body = self.crossing()
        panel = self.run_command()
        panel._add_profile(body)
        panel._show([])
        self.flip_rows(panel, 0)
        self.assertEqual(self.message(panel), "Select the target face or profile.")

    def test_notch_flips_the_kept_piece(self):
        from test_end_miter_geometry import CENTER

        from freecad.maxproframe.create_notch_tool import NotchCommand

        body = self.make_profile(self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        self.doc.clearUndos()
        self.select((target, ""), (body, ""))
        panel = self.capture_notch(NotchCommand().Activated)
        self.flip_rows(panel, 0)
        self.assertTrue(panel.accept())
        notch = [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Notch"]
        self.assertEqual([obj.KeepEnd for obj in notch], ["Start"])
        self.assertEqual(self.box(notch[0].Shape), (-100.0, -25.0))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_notch_with_a_new_target_puts_the_flip_back_to_auto(self):
        from test_end_miter_geometry import CENTER

        from freecad.maxproframe.create_notch_tool import NotchCommand

        body = self.make_profile(self.make_sketch(((-100, 0, 0), (300, 0, 0))), "Edge1", extension=0.0, **CENTER)
        target = self.make_profile(self.make_sketch(((0, -200, 0), (0, 200, 0))), "Edge1", **CENTER)
        other = self.make_profile(self.make_sketch(((200, -200, 0), (200, 200, 0))), "Edge1", **CENTER)
        self.doc.clearUndos()
        self.select((target, ""), (body, ""))
        panel = self.capture_notch(NotchCommand().Activated)
        self.flip_rows(panel, 0)
        panel.set_target(other, ())
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name})"])
        self.assertTrue(panel.accept())
        notch = [obj for obj in self.doc.Objects if getattr(obj, "TrimmedProfileType", None) == "Notch"]
        self.assertEqual([obj.KeepEnd for obj in notch], ["Auto"])
        self.assertEqual(self.doc.UndoCount, 1)

    def capture_notch(self, action):
        from unittest.mock import patch

        from freecad.maxproframe import create_notch_tool

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
        return created[0]


class TestEditFlipSide(KeepEndFixture):
    def existing(self, keep_end="Auto"):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        obj.KeepEnd = keep_end
        self.doc.recompute()
        self.doc.clearUndos()
        return body, obj

    def test_editing_flips_the_side_in_one_undo_step(self):
        body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip_rows(panel, 0)
        # The edited trim previews the flip at once (Cancel puts it back).
        self.assertEqual(obj.KeepEnd, "End")
        self.assertTrue(panel.accept())
        self.assertEqual(obj.KeepEnd, "End")
        self.assertEqual(self.box(obj.Shape), (NEAR, 500.0))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_cancel_after_flipping_changes_nothing(self):
        body, obj = self.existing()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.flip_rows(panel, 0)
        self.assertTrue(panel.reject())
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))
        self.assertEqual(self.doc.UndoCount, 0)

    def test_editing_a_flipped_trim_shows_it_and_can_flip_back(self):
        body, obj = self.existing("End")
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name}), side flipped"])
        self.flip_rows(panel, 0)
        self.assertTrue(panel.accept())
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.box(obj.Shape), (0.0, NEAR))


class TestRetargetResetsSide(KeepEndFixture):
    def far_face(self, target):
        return self.face_towards(target, App.Vector(1, 0, 0))

    def test_a_new_target_puts_flipped_profiles_back_to_auto(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.flip_rows(panel, 0)
        panel.set_target(target, (self.far_face(target),))
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name})"])
        self.assertEqual(self.status(panel), "Pending changes")
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "Auto")

    def test_the_same_target_again_keeps_the_flip(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.flip_rows(panel, 0)
        panel.set_target(target, (face,))
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name}), side flipped"])
        self.assertTrue(panel.accept())
        self.assertEqual(self.trim_of(body).KeepEnd, "End")

    def test_editing_a_flipped_trim_with_a_new_target_stores_auto(self):
        target, face, body = self.crossing()
        obj = make_extend_cut_profile(body, (target, (face,)))
        obj.KeepEnd = "End"
        self.doc.recompute()
        self.doc.clearUndos()
        panel = self.capture_panel(obj.ViewObject.Proxy.edit)
        far_face = self.far_face(target)
        self.click(target, far_face)
        self.assertEqual(self.rows(panel), [f"{body.Label} ({body.Name})"])
        self.assertTrue(panel.accept())
        self.assertEqual(obj.TrimmingBoundary, [(target, (far_face,))])
        self.assertEqual(obj.KeepEnd, "Auto")
        self.assertEqual(self.doc.UndoCount, 1)


class TestDiscardedPieces(KeepEndFixture):
    def test_the_discarded_piece_follows_the_flip(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        preview = self.trim_of(body)
        self.assertEqual([(obj, self.box(shape)) for obj, shape in panel.discarded()], [(preview, (NEAR, 500.0))])
        self.flip_rows(panel, 0)
        self.assertEqual([(obj, self.box(shape)) for obj, shape in panel.discarded()], [(preview, (0.0, NEAR))])
        self.assertTrue(panel.accept())
        self.assertEqual(panel.discarded(), [])

    def test_an_extended_profile_discards_nothing(self):
        target = self.target()
        short = self.profile(0, 300)
        panel = self.run_command((target, self.near_face(target)), (short, ""))
        self.assertEqual(panel.discarded(), [])
        self.assertTrue(panel.reject())

    def test_cancel_drops_the_discarded_pieces(self):
        target, face, body = self.crossing()
        panel = self.run_command((target, face), (body, ""))
        self.assertTrue(panel.reject())
        self.assertEqual(panel.discarded(), [])

    def test_a_piece_that_cannot_be_computed_is_not_drawn_and_ok_still_creates_the_trim(self):
        target, face, body = self.crossing()
        with mock.patch.object(tool, "_cut_off_piece", side_effect=RuntimeError("boolean failed")):
            panel = self.run_command((target, face), (body, ""))
            self.assertEqual(panel.discarded(), [])
            self.assertEqual(panel.form.message_label.text(), "")
            self.assertEqual(panel.form.status_label.text(), "Preview updated")
            self.assertTrue(panel.accept())
        trim = self.trim_of(body)
        self.assertEqual(self.box(trim.Shape), (0.0, NEAR))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_only_the_piece_that_cannot_be_computed_is_skipped_with_a_warning(self):
        target, face, first = self.crossing()
        second = self.profile(0, 500)
        real = tool._cut_off_piece

        def cut(trim):
            if trim.TrimmedBody == first:
                raise RuntimeError("boolean failed")
            return real(trim)

        warnings = []
        with (
            mock.patch.object(tool, "_cut_off_piece", side_effect=cut),
            mock.patch.object(App.Console, "PrintWarning", side_effect=warnings.append),
        ):
            panel = self.run_command((target, face), (first, ""), (second, ""))
            self.assertEqual(
                [(obj, self.box(shape)) for obj, shape in panel.discarded()], [(self.trim_of(second), (NEAR, 500.0))]
            )
            self.assertTrue(panel.accept())
        self.assertEqual(
            warnings, [f"{self.trim_of(first).Label}: the discarded piece cannot be shown: boolean failed\n"]
        )
        self.assertEqual(self.box(self.trim_of(first).Shape), (0.0, NEAR))
        self.assertEqual(self.box(self.trim_of(second).Shape), (0.0, NEAR))
        self.assertEqual(self.doc.UndoCount, 1)

    def test_discarded_pieces_are_drawn_in_red_and_the_panel_says_so(self):
        scene = scene_graph(self, self.doc)
        target, face, body = self.crossing()
        children = scene.getNumChildren()
        panel = self.run_command((target, face), (body, ""))
        self.assertEqual(HIGHLIGHT_COLORS[DISCARDED], RED)
        self.assertEqual(panel.form.colors_label.text(), "Target in orange, profiles in blue, discarded pieces in red.")
        self.assertEqual(overlay_colors(scene.getChild(children)), [ORANGE, BLUE, RED])
        self.assertTrue(panel.reject())
        self.assertEqual(scene.getNumChildren(), children)


class TestKeepEndTranslations(KeepEndFixture):
    def test_flip_texts_are_spanish(self):
        target, face, body = self.crossing()
        short = self.profile(0, 300)
        use_language(self, "Spanish", "es_ES")
        panel = self.run_command((target, face), (body, ""), (short, ""))
        self.assertEqual(panel.form.flip_button.text(), "Invertir lado")
        self.assertEqual(
            panel.form.colors_label.text(), "Destino en naranja, perfiles en azul, piezas descartadas en rojo."
        )
        self.flip_rows(panel, 0, 1)
        self.assertEqual(self.rows(panel)[0], f"{body.Label} ({body.Name}), lado invertido")
        self.assertEqual(self.message(panel), f"{short.Label}: el destino no cruza el perfil, no hay lado que elegir.")


if __name__ == "__main__":
    unittest.main()

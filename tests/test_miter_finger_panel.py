"""The Interlock panel makes Fingers at an End Miter corner between two tubes (odd/tasks/miter-fingers.md, T4: S1 S2
S6 S7, D2 D3).

The inner walls of two tubes, each cut by its own End Miter against the other, clicked (or preselected) make one
Fingers Interlock at the inner vertex of their corner: two straight tubes, or a free end of a Folded Bar and a straight
tube (the user's case). The panel tries the miter corner before a T joint, so such a pair never shows the T-joint
refusal (S7); a tube without its End Miter against the other says which one is missing and what makes it (S6). The
Fingers fields are the ones of a folded corner (S2): they update both finger pieces live; the first face clicked is
tube A, which owns the first finger, and Flip swaps (D3). Apply and continue, Cancel and editing by double click work
as for the other kinds; folded corners still make folded-corner Fingers and T joints still make Tabs.
"""

import time

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_folded_bar_tools import face_at
from test_interlock_panel import BOTTOM_INNER, FIRST, HINT_ONE
from test_tab_interlock_panel import (
    CROSS_EAST,
    HINT_NONE,
    LEGS_RIGHT_INNER,
    LEGS_TOP_INNER,
    RAIL_TOP,
    TabPanelFixture,
)

from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.interlock import interlock_settings, is_miter_interlock
from freecad.maxproframe.interlock_geometry import FingerSettings
from freecad.maxproframe.miter_finger_interlock import MiterFace, make_miter_fingers, miter_pieces
from freecad.maxproframe.profile_pattern import newest_piece

# Two straight 50 x 50 x 2 tubes meeting at a 90 degree corner at (0, -600), far from the bars of the fixtures: A along
# +X up to the corner, B up along +Y from it. Their inner walls: A's top face (y = -575), B's left face (x = -25).
A_EDGE = ((-300, -600, 0), (0, -600, 0))
B_EDGE = ((0, -600, 0), (0, -300, 0))
A_INNER = App.Vector(-150, -575, 0)
B_INNER = App.Vector(-25, -450, 0)
# The next corner along X, for Apply and continue.
NEXT = 1000.0
VOLUME_TOLERANCE = 1e-3
# What the panel says.
HINT_MITER = (
    "Click the inner wall of the other tube at the End Miter corner for fingers, or the other face of the T joint for "
    "tabs."
)
MISSING_ONE = "The fingers of the corner between {} and {} need an End Miter of {} against {}: make it with Miter Ends."
GAPS = "The End Miters of {} and {} have different gaps: give them the same Gap."
TWICE = "The corner between {} and {} already has fingers: {}."
NO_FINGER = "The interlock of the corner between {} and {} needs at least 2 fingers."
# The T-joint refusal the user saw at a miter corner (L1): never for a miter corner.
OFF_RAIL = "do not fall on the flat part"
# The tooltips of the fields at a miter corner.
COUNT_TIP = "Number of fingers, at least 2; the tube of the first face clicked owns the first one"
FLIP_TIP = "Swap the tubes: the tube of the second face clicked owns the first finger"
DEPTH_TIP = "Depth of the finger band across the inner walls; Automatic: the step depth of a Stepped joint"


def shifted(edge, x):
    return tuple((point[0] + x, point[1], point[2]) for point in edge)


class MiterPanelFixture(TabPanelFixture):
    def straight_corner(self, offset=0.0, labels=("TubeA", "TubeB"), only=None, gaps=(0.0, 0.0)):
        """(A, B, A's End Miter, B's End Miter) of the straight corner moved ``offset`` along X; ``only`` 0 or 1: only
        that tube is mitered (the other one is its profile); ``gaps``: the Gap of each End Miter."""
        a = self.loose(shifted(A_EDGE, offset), labels[0])
        b = self.loose(shifted(B_EDGE, offset), labels[1])
        pieces = [a, b]
        for index, (body, other) in enumerate(((a, b), (b, a))):
            if only is None or only == index:
                pieces[index] = make_end_miter_profile(body, [other], True, gaps[index])
        self.doc.recompute()
        for obj in pieces:
            self.assertEqual("Valid", obj.getStatusString())
        return (a, b, *pieces)

    def user_corner(self):
        """The user's layout, both free ends of the bar mitered against the loose bottom tube: ((bottom, right, top,
        left), bar, (bottom miter, right miter, left miter))."""
        (bottom, right, top, left), bar = self.make_legs()
        miters = (
            make_end_miter_profile(bottom, [right, left], True, 0.0),
            make_end_miter_profile(right, [bottom], True, 0.0),
            make_end_miter_profile(left, [bottom], True, 0.0),
        )
        self.doc.recompute()
        for obj in miters:
            self.assertEqual("Valid", obj.getStatusString())
        self.assertEqual([miters[1], top, miters[2]], list(bar.Segments))
        return (bottom, right, top, left), bar, miters

    def assertMiterFingers(self, made, a, b, under_a, under_b):
        """``made`` is a Fingers Interlock at the End Miter corner of the profiles ``a`` (it owns the first finger)
        and ``b``, its pieces valid on ``under_a`` and ``under_b``, interlocked; no Folded Bar lists it."""
        self.assertTrue(is_miter_interlock(made))
        self.assertEqual("Fingers", made.Kind)
        self.assertEqual((a, b), (made.PieceA, made.PieceB))
        piece_a, piece_b = miter_pieces(made)
        self.assertEqual((under_a, under_b), (piece_a.baseObject[0], piece_b.baseObject[0]))
        self.assertEqual((piece_a, piece_b), (newest_piece(a), newest_piece(b)))
        for obj in (piece_a, piece_b):
            self.assertOneSolid(obj)
        self.assertLess(piece_a.Shape.common(piece_b.Shape).Volume, VOLUME_TOLERANCE)
        self.assertGreater(piece_a.Shape.common(under_b.Shape).Volume, 1.0)
        self.assertGreater(piece_b.Shape.common(under_a.Shape).Volume, 1.0)
        self.assertFalse(any(made in getattr(obj, "Interlocks", ()) for obj in self.doc.Objects))
        return piece_a, piece_b

    def assertFingersShown(self, panel):
        """The panel shows the Fingers fields: Depth and Flip, not the tab Length."""
        form = panel.form
        layout = form.groupBox_settings.layout()
        self.assertEqual("Fingers", form.combo_kind.currentData())
        self.assertEqual("Fingers", form.groupBox_settings.title())
        self.assertEqual("Corner", form.groupBox_corner.title())
        self.assertEqual("Finger width", layout.labelForField(form.spin_finger_width).text())
        for widget in (form.spin_count, form.spin_finger_width, form.combo_tip, form.spin_tip_size, form.spin_depth):
            self.assertFalse(widget.isHidden())
        for widget in (form.spin_clearance, form.cb_flip, layout.labelForField(form.spin_depth)):
            self.assertFalse(widget.isHidden())
        for widget in (form.spin_length, layout.labelForField(form.spin_length)):
            self.assertTrue(widget.isHidden())

    @staticmethod
    def gains(made):
        """How much each finger piece of ``made`` adds to the piece under it: the owner of more levels adds more."""
        return [piece.Shape.Volume - piece.baseObject[0].Shape.Volume for piece in miter_pieces(made)]

    def double_click(self, obj):
        count = len(self.recorded)
        self.assertTrue(obj.ViewObject.Proxy.doubleClicked(obj.ViewObject))
        self.assertEqual(count + 1, len(self.recorded))
        self.events()
        return self.recorded[-1]

    def wait_for(self, condition, seconds=3.0):
        """Process events until ``condition()`` is true or ``seconds`` pass."""
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.02)
        return condition()


class MiterPickTest(MiterPanelFixture):
    def test_the_inner_walls_of_two_mitered_tubes_make_fingers_at_their_corner(self):
        a, b, miter_a, miter_b = self.straight_corner()
        names, undos = self.names(), len(self.doc.UndoNames)
        panel = self.run_command()
        self.assertRefused(panel, HINT_NONE)

        self.click(miter_a, A_INNER)
        self.assertRefused(panel, HINT_MITER)
        self.assertEqual([], self.interlocks())
        self.click(miter_b, B_INNER)

        (made,) = self.interlocks()
        self.assertMiterFingers(made, a, b, miter_a, miter_b)
        self.assertEqual(FIRST, interlock_settings(made))
        self.assertFields(panel, FIRST)
        self.assertFingersShown(panel)
        self.assertEqual("Corner: TubeA → TubeB", panel.form.label_corner.text())
        self.assertNotIn(OFF_RAIL, self.message(panel))
        self.assertAccepts(panel)

        # Cancel leaves the document as it was, in no Undo step.
        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertEqual([], self.interlocks())
        self.assertEqual(names, self.names())
        self.assertEqual((miter_a, miter_b), (newest_piece(a), newest_piece(b)))
        self.assertEqual(undos, len(self.doc.UndoNames))

        # Preselected; OK keeps it in one Undo step.
        panel = self.run_command((miter_a, A_INNER), (miter_b, B_INNER))
        (made,) = self.interlocks()
        self.assertMiterFingers(made, a, b, miter_a, miter_b)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual([made], self.interlocks())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])

    def test_the_first_face_clicked_owns_the_first_finger_and_flip_swaps(self):
        a, b, miter_a, miter_b = self.straight_corner()
        panel = self.run_command((miter_b, B_INNER), (miter_a, A_INNER))

        (made,) = self.interlocks()
        # D3: B clicked first is tube A of the corner: of three fingers, it owns two.
        self.assertMiterFingers(made, b, a, miter_b, miter_a)
        self.assertEqual("Corner: TubeB → TubeA", panel.form.label_corner.text())
        first, second = self.gains(made)
        self.assertGreater(first, second + 1.0)

        panel.form.cb_flip.setChecked(True)
        self.events()

        self.assertTrue(made.Flip)
        self.assertMiterFingers(made, b, a, miter_b, miter_a)
        # The same fingers, the other way round: both tubes are alike.
        self.assertAlmostEqual(first, self.gains(made)[1], delta=0.01)
        self.assertAlmostEqual(second, self.gains(made)[0], delta=0.01)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_the_free_end_of_a_folded_bar_and_a_straight_tube_make_fingers(self):
        # The user's case (L1): the inner wall of the bar's right tube, then the top face of the bottom tube.
        (bottom, right, top, _), bar, (bottom_miter, right_miter, left_miter) = self.user_corner()
        panel = self.run_command()

        self.click(bar, LEGS_RIGHT_INNER)
        self.assertRefused(panel, HINT_ONE)
        self.click(bottom_miter, BOTTOM_INNER)

        (made,) = self.interlocks()
        piece_a, _ = self.assertMiterFingers(made, right, bottom, right_miter, bottom_miter)
        self.assertNotIn(OFF_RAIL, self.message(panel))
        self.assertAccepts(panel)
        # The bar folds the fingers of its free end and does not list the Interlock.
        self.assertEqual([piece_a, top, left_miter], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertEqual([], list(bar.Interlocks))
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual([made], self.interlocks())

    def test_a_missing_end_miter_or_unequal_gaps_say_what_to_do_and_make_nothing(self):
        a, b, miter_a, plain_b = self.straight_corner(only=0)
        c, d, miter_c, miter_d = self.straight_corner(NEXT, ("TubeC", "TubeD"), gaps=(0.5, 0.0))
        names = self.names()

        for picks, message in (
            (((miter_a, A_INNER), (plain_b, B_INNER)), MISSING_ONE.format("TubeA", "TubeB", "TubeB", "TubeA")),
            (((plain_b, B_INNER), (miter_a, A_INNER)), MISSING_ONE.format("TubeB", "TubeA", "TubeB", "TubeA")),
            (
                ((miter_c, A_INNER + App.Vector(NEXT, 0, 0)), (miter_d, B_INNER + App.Vector(NEXT, 0, 0))),
                GAPS.format("TubeC", "TubeD"),
            ),
        ):
            with self.subTest(message=message):
                panel = self.run_command()
                for obj, point in picks:
                    self.click(obj, point)

                self.assertRefused(panel, message)
                self.assertEqual(names, self.names())
                self.assertTrue(panel.reject())
                self.close_dialog()

    def test_one_interlock_per_corner(self):
        a, b, miter_a, miter_b = self.straight_corner()
        made = make_miter_fingers(
            MiterFace(miter_a, face_at(miter_a, A_INNER), None), MiterFace(miter_b, face_at(miter_b, B_INNER), None)
        )
        self.doc.recompute()
        piece_a, piece_b = miter_pieces(made)

        for picks, labels in (
            (((piece_a, A_INNER), (piece_b, B_INNER)), ("TubeA", "TubeB")),
            (((piece_b, B_INNER), (piece_a, A_INNER)), ("TubeB", "TubeA")),
        ):
            with self.subTest(labels=labels):
                panel = self.run_command(*picks)

                self.assertRefused(panel, TWICE.format(*labels, made.Label))
                self.assertEqual([made], self.interlocks())
                self.assertTrue(panel.reject())
                self.close_dialog()

    def test_a_t_joint_still_makes_tabs_and_a_folded_corner_folded_fingers(self):
        rail, crossbar, trim = self.straight_t()
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        (tabs,) = self.interlocks()
        self.assertEqual("Tabs", tabs.Kind)
        self.assertEqual((crossbar, rail), (tabs.PieceA, tabs.PieceB))
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())
        self.close_dialog()

        # The folded corner of a bar whose free ends are mitered.
        (_, right, top, _), bar, _ = self.user_corner()
        panel = self.run_command((bar, LEGS_RIGHT_INNER), (bar, LEGS_TOP_INNER))
        (fingers,) = [obj for obj in self.interlocks() if obj is not tabs]
        self.assertFalse(is_miter_interlock(fingers))
        self.assertNotIn("AtEndMiter", fingers.PropertiesList)
        self.assertEqual((right, top), (fingers.PieceA, fingers.PieceB))
        self.assertEqual([fingers], list(bar.Interlocks))
        self.assertOneSolid(bar)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_faces_clicked_while_the_panel_recomputes_wait_for_it(self):
        # odd/tasks/panel-recompute-deadlock.md S3: no geometry while the panel's recompute runs; the clicks wait.
        a, b, miter_a, miter_b = self.straight_corner()
        panel = self.run_command()
        panel._recomputing = True
        self.click(miter_a, A_INNER)
        self.click(miter_b, B_INNER)
        self.events()
        self.assertEqual([], self.interlocks())
        self.assertEqual(2, len(panel._clicks))

        panel._recomputing = False

        self.assertTrue(self.wait_for(lambda: bool(self.interlocks())))
        (made,) = self.interlocks()
        self.assertMiterFingers(made, a, b, miter_a, miter_b)
        self.events()
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())


class MiterFieldsTest(MiterPanelFixture):
    def test_the_fields_update_both_finger_pieces(self):
        a, b, miter_a, miter_b = self.straight_corner()
        panel = self.run_command((miter_a, A_INNER), (miter_b, B_INNER))
        (made,) = self.interlocks()
        piece_a, piece_b = miter_pieces(made)
        form = panel.form
        self.assertEqual(COUNT_TIP, form.spin_count.toolTip())
        self.assertEqual(FLIP_TIP, form.cb_flip.toolTip())
        self.assertEqual(DEPTH_TIP, form.spin_depth.toolTip())

        for change, fields in (
            (lambda: form.spin_count.setValue(4), dict(count=4)),
            (lambda: form.spin_clearance.setValue(0.2), dict(clearance=0.2)),
            (lambda: form.spin_depth.setValue(3.0), dict(depth=3.0)),
            (
                lambda: (
                    form.combo_tip.setCurrentIndex(form.combo_tip.findData("Chamfer")),
                    form.spin_tip_size.setValue(1.0),
                ),
                dict(tip="Chamfer", tip_size=1.0),
            ),
        ):
            with self.subTest(fields=fields):
                before = (piece_a.Shape.Volume, piece_b.Shape.Volume)
                expected = FingerSettings(**{**vars(interlock_settings(made)), **fields})
                change()
                self.events()

                self.assertEqual(expected, interlock_settings(made))
                self.assertMiterFingers(made, a, b, miter_a, miter_b)
                self.assertNotAlmostEqual(before[0], piece_a.Shape.Volume, delta=VOLUME_TOLERANCE)
                self.assertNotAlmostEqual(before[1], piece_b.Shape.Volume, delta=VOLUME_TOLERANCE)
                self.assertAccepts(panel)

        # A refusal of the pieces shows in the panel and disables OK.
        form.spin_count.setValue(1)
        self.events()
        self.assertIn("Invalid", piece_a.State)
        self.assertRefused(panel, NO_FINGER.format("TubeA", "TubeB"))
        form.spin_count.setValue(3)
        self.events()
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_the_panel_speaks_spanish_at_a_miter_corner(self):
        use_language(self, "Spanish", "es_ES")
        _, _, miter_a, miter_b = self.straight_corner()

        panel = self.run_command((miter_a, A_INNER), (miter_b, B_INNER))

        form = panel.form
        self.assertEqual("Esquina", form.groupBox_corner.title())
        self.assertEqual("Esquina: TubeA → TubeB", form.label_corner.text())
        self.assertEqual("Aletas", form.groupBox_settings.title())
        self.assertEqual("Fingers", form.combo_kind.currentData())
        self.assertEqual("Aletas", form.combo_kind.currentText())
        self.assertAccepts(panel)


class MiterApplyContinueTest(MiterPanelFixture):
    def test_apply_and_continue_takes_the_next_miter_corner(self):
        a, b, miter_a, miter_b = self.straight_corner()
        c, d, miter_c, miter_d = self.straight_corner(NEXT, ("TubeC", "TubeD"))
        undos = len(self.doc.UndoNames)
        panel = self.run_command((miter_a, A_INNER), (miter_b, B_INNER))
        panel.form.spin_count.setValue(4)
        self.events()
        (first,) = self.interlocks()
        used = FingerSettings(count=4, clearance=0.5)

        self.apply()

        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])
        self.assertEqual(used, interlock_settings(first))
        self.assertEqual("", panel.form.label_corner.text())
        self.assertEqual(HINT_NONE, self.message(panel))
        self.assertTrue(panel.ok_button_enabled())
        self.assertFalse(self.apply_button().isEnabled())

        self.click(miter_c, A_INNER + App.Vector(NEXT, 0, 0))
        self.click(miter_d, B_INNER + App.Vector(NEXT, 0, 0))
        second = [obj for obj in self.interlocks() if obj is not first]
        self.assertEqual(1, len(second))
        self.assertMiterFingers(second[0], c, d, miter_c, miter_d)
        self.assertEqual(used, interlock_settings(second[0]))
        self.assertEqual("Corner: TubeC → TubeD", panel.form.label_corner.text())
        self.apply()
        self.assertEqual(undos + 2, len(self.doc.UndoNames))

        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual({first.Name, second[0].Name}, {obj.Name for obj in self.interlocks()})
        self.assertMiterFingers(first, a, b, miter_a, miter_b)
        self.assertEqual(undos + 2, len(self.doc.UndoNames))
        # The settings applied last start the next Interlock.
        panel = self.run_command()
        self.assertFields(panel, used)


class MiterEditTest(MiterPanelFixture):
    def test_a_double_click_on_a_miter_interlock_or_its_pieces_edits_it(self):
        a, b, miter_a, miter_b = self.straight_corner()
        made = make_miter_fingers(
            MiterFace(miter_a, face_at(miter_a, A_INNER), None),
            MiterFace(miter_b, face_at(miter_b, B_INNER), None),
            Count=3,
            Clearance=0.3,
        )
        self.doc.recompute()
        piece_a, piece_b = miter_pieces(made)
        settings, undos = interlock_settings(made), len(self.doc.UndoNames)
        volumes = (piece_a.Shape.Volume, piece_b.Shape.Volume)

        for opener in (lambda: self.edit(made), lambda: self.double_click(made), lambda: self.double_click(piece_b)):
            with self.subTest(opener=opener):
                panel = opener()
                self.assertIs(made, panel.edited)
                self.assertFields(panel, settings)
                self.assertFingersShown(panel)
                self.assertEqual(FLIP_TIP, panel.form.cb_flip.toolTip())
                self.assertEqual("Corner: TubeA → TubeB", panel.form.label_corner.text())
                self.assertIsNone(self.apply_button())
                self.assertAccepts(panel)
                panel.form.spin_count.setValue(2)
                self.events()
                self.assertEqual(2, made.Count)
                self.assertMiterFingers(made, a, b, miter_a, miter_b)
                self.assertNotAlmostEqual(volumes[0], piece_a.Shape.Volume, delta=VOLUME_TOLERANCE)
                self.assertNotAlmostEqual(volumes[1], piece_b.Shape.Volume, delta=VOLUME_TOLERANCE)

                self.assertTrue(panel.reject())
                self.close_dialog()
                self.assertEqual(settings, interlock_settings(made))
                self.assertEqual(undos, len(self.doc.UndoNames))
                self.doc.recompute()
                self.assertAlmostEqual(volumes[0], piece_a.Shape.Volume, delta=VOLUME_TOLERANCE)
                self.assertAlmostEqual(volumes[1], piece_b.Shape.Volume, delta=VOLUME_TOLERANCE)

        panel = self.double_click(piece_a)
        self.assertIs(made, panel.edited)
        # No picking while editing.
        self.click(miter_b, B_INNER)
        panel.form.spin_count.setValue(1)
        self.events()
        self.assertRefused(panel, NO_FINGER.format("TubeA", "TubeB"))
        panel.form.spin_count.setValue(4)
        panel.form.cb_flip.setChecked(True)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(FingerSettings(count=4, clearance=0.3, flip=True), interlock_settings(made))
        self.assertEqual([made], self.interlocks())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Interlock", self.doc.UndoNames[0])
        self.assertMiterFingers(made, a, b, miter_a, miter_b)

"""The Interlock command and its panel (odd/tasks/joint-tabs.md, T3: S1 S6 S7).

Interlock sits on the Folded Miters toolbar. Its panel takes two faces of a Folded Bar, preselected or clicked while
it is open: the inner walls of the two tubes at one folded corner, the faces on the inside of the corner. Those make
one Interlock on that corner, previewed on the bar; anything else creates nothing and says what to pick (S6). The
finger settings update the Interlock live, TipSize only for a Chamfer or Round tip; a refusal of the bar shows in the
panel and keeps OK disabled. OK keeps the Interlock in one Undo step, Cancel leaves the document as it was. A double
click edits an Interlock in the same panel, without picking; the settings last used start the next Interlock.
Deleting a bar deletes its Interlocks, as its corners, and undo brings them back.
"""

from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_folded_bar import VOLUME_TOLERANCE
from test_folded_bar_panel import keep_params
from test_folded_bar_tools import face_at
from test_interlock import InterlockObjectFixture
from test_unfolded_geometry import PLAIN

from freecad.maxproframe import create_interlock_tool, interlock
from freecad.maxproframe.create_interlock_tool import InterlockCommand
from freecad.maxproframe.ff_tools import ICONPATH, get_param_group
from freecad.maxproframe.InitGui import MaxProFrame
from freecad.maxproframe.interlock import interlock_settings, is_interlock, make_interlock
from freecad.maxproframe.interlock_geometry import FingerSettings

# The settings last used, for the next Interlock (L11).
INTERLOCK_PARAMS = (
    ("String", "Interlock Kind"),
    ("Int", "Interlock Count"),
    ("Float", "Interlock Finger Width"),
    ("String", "Interlock Tip"),
    ("Float", "Interlock Tip Size"),
    ("Float", "Interlock Depth"),
    ("Float", "Interlock Clearance"),
    ("Bool", "Interlock Flip"),
)
# The first Interlock ever: the clearance of a first Folded Corner, so the fingers show in the folded bar.
FIRST = FingerSettings(clearance=0.5)
# Points of the rectangle (50 x 50 tubes on a 300 x 200 path, open at its start, between left and bottom): the
# inner and the outer wall and a side wall of each tube.
BOTTOM_INNER = App.Vector(150, 25, 0)
BOTTOM_OUTER = App.Vector(150, -25, 0)
BOTTOM_SIDE = App.Vector(150, 0, 25)
RIGHT_INNER = App.Vector(275, 100, 0)
TOP_INNER = App.Vector(150, 175, 0)
LEFT_INNER = App.Vector(25, 100, 0)
# S6: what the panel says.
# odd/tasks/t-joint-tabs.md, T4: the hint with no face names both kinds.
HINT_NONE = (
    "Click the inner walls of the two tubes at a folded corner of a Folded Bar for fingers, or a wall of a crossbar "
    "and the face of the rail it butts against for tabs."
)
HINT_ONE = "Click the inner wall of the other tube at that corner."
INNER = "Click the inner wall of {}: its face on the inside of the folded corner."
NOT_A_BAR = "{} is not a Folded Bar: click the inner walls of two tubes of a Folded Bar."
NOT_MEETING = "{} and {} do not meet at a folded corner of {}: click the inner walls of two tubes that do."
OPEN = "{} and {} meet at the open corner of {}, which does not fold: click the inner walls at a folded corner."
TAKEN = "The corner between {} and {} has an interlock already: double-click {} to edit it."
COUNT_REFUSED = "The interlock of the corner between Profile and Profile001 needs at least 2 fingers."
# Three even fingers on the 50 mm tube with 0.5 mm clearance: (50 / 3 - 0.5) / 2 rounded down to 0.1 mm.
TIP_REFUSED = "The finger tips of the corner between Profile and Profile001 must be between 0 and 8 mm."


class InterlockPanelFixture(InterlockObjectFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_params(self, INTERLOCK_PARAMS)
        param = get_param_group(writable=True)
        for kind, name in INTERLOCK_PARAMS:
            getattr(param, f"Rem{kind}")(name)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        recorded = self.recorded

        class Recording(create_interlock_tool.InterlockTaskPanel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        patcher = patch.object(create_interlock_tool, "InterlockTaskPanel", Recording)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        self.events()
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        for panel in self.recorded:
            panel.clean()
        self.events()

    def events(self):
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def add_selection(self, obj, point):
        Gui.Selection.addSelection(self.doc.Name, obj.Name, face_at(obj, point), point.x, point.y, point.z)

    def run_command(self, *picks):
        """Open the panel with the faces ``picks`` ((object, point on it)) preselected."""
        Gui.Selection.clearSelection()
        for obj, point in picks:
            self.add_selection(obj, point)
        count = len(self.recorded)
        InterlockCommand().Activated()
        self.assertEqual(count + 1, len(self.recorded))
        self.assertTrue(Gui.Control.activeDialog())
        self.events()
        return self.recorded[-1]

    def click(self, obj, point):
        self.add_selection(obj, point)
        self.events()

    def edit(self, obj):
        count = len(self.recorded)
        Gui.getDocument(self.doc.Name).setEdit(obj.Name, 0)
        self.assertEqual(count + 1, len(self.recorded))
        self.events()
        return self.recorded[-1]

    def interlocks(self):
        return [obj for obj in self.doc.Objects if is_interlock(obj)]

    def message(self, panel):
        return panel.form.message_label.text()

    def assertAccepts(self, panel):
        self.assertEqual("", self.message(panel))
        self.assertIsNotNone(panel._ok_button)
        self.assertTrue(panel.ok_button_enabled())

    def assertRefused(self, panel, message):
        self.assertEqual(message, self.message(panel))
        self.assertIsNotNone(panel._ok_button)
        self.assertFalse(panel.ok_button_enabled())
        self.assertFalse(panel.accept())

    def assertFields(self, panel, fingers):
        form = panel.form
        self.assertEqual("Fingers", form.combo_kind.currentData())
        self.assertEqual(
            fingers,
            FingerSettings(
                count=form.spin_count.value(),
                finger_width=form.spin_finger_width.value(),
                tip=form.combo_tip.currentData(),
                tip_size=form.spin_tip_size.value(),
                depth=form.spin_depth.value(),
                clearance=form.spin_clearance.value(),
                flip=form.cb_flip.isChecked(),
            ),
        )


class InterlockCommandTest(InterlockPanelFixture):
    def test_the_command_is_registered_with_its_icon_after_extend_cut(self):
        self.assertIn("MaxProFrame_Interlock", Gui.listCommands())
        # On the MaxProFrame toolbar right after Extend / Cut: Tabs work on straight tubes too.
        tools = MaxProFrame.toolbox_maxproframe
        self.assertEqual(tools.index("MaxProFrame_Interlock"), tools.index("MaxProFrame_ExtendCut") + 1)
        self.assertNotIn("MaxProFrame_Interlock", MaxProFrame.toolbox_folded)
        info = Gui.Command.get("MaxProFrame_Interlock").getInfo()
        self.assertEqual("Interlock.svg", info["pixmap"].rsplit("/", 1)[-1])
        self.assertTrue(info["pixmap"].startswith(ICONPATH))
        self.assertEqual("Interlock", info["menuText"])
        self.assertIn("inner wall", info["toolTip"])
        self.assertTrue(InterlockCommand().IsActive())


class InterlockPickTest(InterlockPanelFixture):
    def test_the_preselected_inner_walls_of_a_folded_corner_make_one_interlock_and_ok_keeps_it(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        volume, undos = bar.Shape.Volume, len(self.doc.UndoNames)

        panel = self.run_command((bar, RIGHT_INNER), (bar, BOTTOM_INNER))

        (made,) = self.interlocks()
        self.assertEqual([made], list(bar.Interlocks))
        # In chain order, whatever the order of the clicks: the tube before the corner owns the first finger.
        self.assertEqual((bottom, right), (made.PieceA, made.PieceB))
        self.assertEqual(FIRST, interlock_settings(made))
        self.assertFields(panel, FIRST)
        self.assertEqual("Corner: Profile → Profile001", panel.form.label_corner.text())
        self.assertFolds(bar, list(bar.Segments), FIRST)
        self.assertGreater(abs(volume - bar.Shape.Volume), VOLUME_TOLERANCE)
        self.assertAccepts(panel)

        self.assertTrue(panel.accept())
        self.close_dialog()

        self.assertEqual([made], self.interlocks())
        self.assertEqual([made], list(bar.Interlocks))
        self.assertOneSolid(bar)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])

    def test_the_inner_walls_clicked_while_the_panel_is_open_make_the_interlock(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        panel = self.run_command()
        self.assertRefused(panel, HINT_NONE)

        self.click(bar, BOTTOM_INNER)
        self.assertRefused(panel, HINT_ONE)
        self.assertEqual([], self.interlocks())

        self.click(bar, RIGHT_INNER)
        (made,) = self.interlocks()
        self.assertEqual((bottom, right), (made.PieceA, made.PieceB))
        self.assertFolds(bar, list(bar.Segments), FIRST)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual([made], list(bar.Interlocks))

    def test_cancel_removes_the_interlock_and_gives_the_bar_back_in_no_undo_step(self):
        _, bar = self.make_bar(**PLAIN)
        volume, undos = bar.Shape.Volume, len(self.doc.UndoNames)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        self.assertEqual(1, len(self.interlocks()))

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual([], self.interlocks())
        self.assertEqual([], list(bar.Interlocks))
        self.assertEqual(undos, len(self.doc.UndoNames))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.doc.recompute()
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_wrong_picks_make_nothing_and_say_what_to_pick(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        box = self.doc.addObject("Part::Box", "Box")
        box.Placement.Base = App.Vector(0, 0, 100)
        self.doc.recompute()
        taken = make_interlock(bar, right, self.doc.getObject("Profile002"))
        self.doc.recompute()
        self.assertOneSolid(bar)

        for picks, message in (
            # One face only.
            (((bar, BOTTOM_INNER),), HINT_ONE),
            # An outer wall, a side wall.
            (((bar, RIGHT_INNER), (bar, BOTTOM_OUTER)), INNER.format("Profile")),
            (((bar, RIGHT_INNER), (bar, BOTTOM_SIDE)), INNER.format("Profile")),
            # Two tubes that do not meet; the open corner of the closed frame.
            (((bar, BOTTOM_INNER), (bar, TOP_INNER)), NOT_MEETING.format("Profile", "Profile002", bar.Label)),
            (((bar, LEFT_INNER), (bar, BOTTOM_INNER)), OPEN.format("Profile003", "Profile", bar.Label)),
            # Not a Folded Bar.
            (((bar, BOTTOM_INNER), (box, App.Vector(5, 5, 110))), NOT_A_BAR.format("Box")),
            # A corner with an interlock.
            (((bar, RIGHT_INNER), (bar, TOP_INNER)), TAKEN.format("Profile001", "Profile002", taken.Label)),
        ):
            with self.subTest(message=message):
                panel = self.run_command()
                for obj, point in picks:
                    self.click(obj, point)

                self.assertRefused(panel, message)
                self.assertEqual([taken], self.interlocks())
                self.assertEqual([taken], list(bar.Interlocks))
                self.assertTrue(panel.reject())
                self.close_dialog()


class InterlockSettingsTest(InterlockPanelFixture):
    def test_the_fields_update_the_interlock_and_recompute_the_bar(self):
        _, bar = self.make_bar(**PLAIN)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        (made,) = self.interlocks()
        form = panel.form
        # TipSize leads a Chamfer or Round tip in; a Square tip has none.
        self.assertFalse(form.spin_tip_size.isEnabled())

        # (change, settings it makes, whether the folded bar changes, TipSize enabled after).
        for change, fields, reshapes, tip_size in (
            (lambda: form.spin_count.setValue(5), dict(count=5), True, False),
            (lambda: form.cb_flip.setChecked(True), dict(flip=True), True, False),
            (
                lambda: form.combo_tip.setCurrentIndex(form.combo_tip.findData("Chamfer")),
                dict(tip="Chamfer"),
                False,
                True,
            ),
            (lambda: form.spin_tip_size.setValue(1.0), dict(tip_size=1.0), True, True),
            (lambda: form.combo_tip.setCurrentIndex(form.combo_tip.findData("Round")), dict(tip="Round"), None, True),
            (
                lambda: form.combo_tip.setCurrentIndex(form.combo_tip.findData("Square")),
                dict(tip="Square"),
                None,
                False,
            ),
        ):
            with self.subTest(fields=fields):
                before = bar.Shape.copy()
                expected = FingerSettings(**{**vars(interlock_settings(made)), **fields})
                change()
                self.events()

                self.assertEqual(expected, interlock_settings(made))
                self.assertFolds(bar, list(bar.Segments), expected)
                if reshapes:
                    self.assertGreater(before.cut(bar.Shape).Volume, VOLUME_TOLERANCE)
                self.assertEqual(tip_size, form.spin_tip_size.isEnabled())
                self.assertAccepts(panel)

    def test_a_refusal_of_the_bar_shows_in_the_panel_and_disables_ok(self):
        _, bar = self.make_bar(**PLAIN)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        (made,) = self.interlocks()
        form = panel.form

        form.spin_count.setValue(1)
        self.events()
        self.assertEqual(1, made.Count)
        self.assertIn("Invalid", bar.State)
        self.assertRefused(panel, COUNT_REFUSED)

        form.spin_count.setValue(3)
        form.combo_tip.setCurrentIndex(form.combo_tip.findData("Chamfer"))
        form.spin_tip_size.setValue(20.0)
        self.events()
        self.assertRefused(panel, TIP_REFUSED)

        form.spin_tip_size.setValue(8.0)
        self.events()
        self.assertOneSolid(bar)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())


class InterlockEditTest(InterlockPanelFixture):
    def test_a_double_click_edits_the_interlock_and_cancel_puts_its_values_back(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        values = dict(Count=4, Tip="Chamfer", TipSize=1.0, Clearance=0.4)
        made = make_interlock(bar, bottom, right, **values)
        self.doc.recompute()
        settings, volume, undos = interlock_settings(made), bar.Shape.Volume, len(self.doc.UndoNames)
        self.assertIsNotNone(interlock.EDIT_PANEL)

        panel = self.edit(made)

        self.assertIs(made, panel.edited)
        self.assertFields(panel, settings)
        self.assertTrue(panel.form.spin_tip_size.isEnabled())
        self.assertEqual("Corner: Profile → Profile001", panel.form.label_corner.text())
        self.assertAccepts(panel)
        panel.form.spin_count.setValue(5)
        self.events()
        self.assertEqual(5, made.Count)
        self.assertFolds(bar, list(bar.Segments), interlock_settings(made))

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertEqual(settings, interlock_settings(made))
        self.assertEqual(undos, len(self.doc.UndoNames))
        self.doc.recompute()
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

        panel = self.edit(made)
        # No picking while editing: a click on the bar changes nothing.
        self.click(bar, TOP_INNER)
        panel.form.cb_flip.setChecked(True)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(FingerSettings(4, 0.0, "Chamfer", 1.0, 0.0, 0.4, True), interlock_settings(made))
        self.assertEqual([made], self.interlocks())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Interlock", self.doc.UndoNames[0])

    def test_the_settings_last_used_start_the_next_interlock(self):
        _, bar = self.make_bar(**PLAIN)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        panel.form.spin_count.setValue(4)
        panel.form.spin_clearance.setValue(0.3)
        panel.form.cb_flip.setChecked(True)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        used = FingerSettings(count=4, clearance=0.3, flip=True)

        panel = self.run_command((bar, RIGHT_INNER), (bar, TOP_INNER))
        self.assertFields(panel, used)
        second = [obj for obj in self.interlocks() if obj.PieceA.Name == "Profile001"]
        self.assertEqual([used], [interlock_settings(obj) for obj in second])
        # Cancel remembers nothing.
        panel.form.spin_count.setValue(6)
        self.events()
        self.assertTrue(panel.reject())
        self.close_dialog()

        panel = self.run_command()
        self.assertFields(panel, used)


class InterlockDeleteTest(InterlockPanelFixture):
    def test_deleting_the_bar_deletes_its_interlocks_and_undo_brings_them_back(self):
        (bottom, right, top, _), bar = self.make_bar(**PLAIN)
        made = [make_interlock(bar, bottom, right, Clearance=0.4), make_interlock(bar, right, top, Clearance=0.4)]
        self.doc.recompute()
        self.assertOneSolid(bar)
        names = sorted(obj.Name for obj in made)

        self.doc.openTransaction("Delete")
        self.doc.removeObject(bar.Name)
        self.doc.commitTransaction()

        self.assertEqual([], self.interlocks())
        self.doc.undo()
        self.assertEqual(names, sorted(obj.Name for obj in self.interlocks()))
        bar = self.doc.getObject(bar.Name)
        self.assertEqual(names, sorted(obj.Name for obj in bar.Interlocks))


class InterlockApplyContinueTest(InterlockPanelFixture):
    """Apply and continue: one Interlock after another without running the command again, with the same settings."""

    def dialog_box(self):
        """The button row of the task dialog: the one button box holding its OK and Cancel."""
        boxes = [
            box
            for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
            if box.button(QtWidgets.QDialogButtonBox.Ok) is not None
            and box.button(QtWidgets.QDialogButtonBox.Cancel) is not None
        ]
        self.assertEqual(1, len(boxes))
        return boxes[0]

    def apply_button(self):
        return self.dialog_box().button(QtWidgets.QDialogButtonBox.Apply)

    def apply(self):
        """Click Apply and continue, as the user does."""
        button = self.apply_button()
        self.assertTrue(button.isEnabled())
        button.click()
        self.events()

    def test_the_button_shows_only_while_creating_next_to_ok_and_is_enabled_once_the_interlock_is_made(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        panel = self.run_command()
        button = self.apply_button()
        self.assertIsNotNone(button)
        self.assertEqual("Apply and continue", button.text())
        self.assertIs(button.parentWidget(), self.dialog_box().button(QtWidgets.QDialogButtonBox.Ok).parentWidget())
        self.assertFalse(button.isEnabled())
        self.click(bar, BOTTOM_INNER)
        self.assertFalse(button.isEnabled())
        self.click(bar, RIGHT_INNER)
        self.assertTrue(button.isEnabled())
        # A refusal of the bar disables it as it disables OK.
        panel.form.spin_count.setValue(1)
        self.events()
        self.assertEqual(COUNT_REFUSED, self.message(panel))
        self.assertFalse(button.isEnabled())
        self.assertTrue(panel.reject())
        self.close_dialog()

        made = make_interlock(bar, bottom, right)
        self.doc.recompute()
        self.edit(made)
        self.assertIsNone(self.apply_button())

    def test_apply_and_continue_keeps_the_interlock_in_its_own_undo_step_and_takes_the_next_corner(self):
        (bottom, right, top, _), bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        panel.form.spin_count.setValue(4)
        panel.form.cb_flip.setChecked(True)
        self.events()
        (first,) = self.interlocks()
        used = FingerSettings(count=4, clearance=0.5, flip=True)

        self.apply()

        # The dialog stays open, waiting for the walls of the next corner, with the same settings.
        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])
        self.assertEqual(used, interlock_settings(first))
        self.assertEqual("", panel.form.label_corner.text())
        self.assertEqual(HINT_NONE, self.message(panel))
        # OK closes the panel from now on; Apply and continue waits for the next Interlock.
        self.assertTrue(panel.ok_button_enabled())
        self.assertFalse(self.apply_button().isEnabled())
        self.assertFields(panel, used)
        self.assertEqual([], Gui.Selection.getSelectionEx())

        self.click(bar, RIGHT_INNER)
        self.click(bar, TOP_INNER)
        second = [obj for obj in self.interlocks() if obj is not first]
        self.assertEqual(1, len(second))
        self.assertEqual((right, top), (second[0].PieceA, second[0].PieceB))
        self.assertEqual(used, interlock_settings(second[0]))
        self.assertEqual("Corner: Profile001 → Profile002", panel.form.label_corner.text())
        # The fields change only the newer Interlock.
        panel.form.spin_count.setValue(3)
        self.events()
        self.assertEqual(3, second[0].Count)
        self.assertEqual(4, first.Count)

        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual({first.Name, second[0].Name}, {obj.Name for obj in bar.Interlocks})
        self.assertOneSolid(bar)
        self.assertEqual(undos + 2, len(self.doc.UndoNames))
        # The settings applied last start the next Interlock.
        panel = self.run_command()
        self.assertFields(panel, FingerSettings(count=3, clearance=0.5, flip=True))

    def test_cancel_after_apply_and_continue_removes_only_the_newer_interlock(self):
        (bottom, right, _, _), bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        (first,) = self.interlocks()
        self.apply()
        self.click(bar, RIGHT_INNER)
        self.click(bar, TOP_INNER)
        self.assertEqual(2, len(self.interlocks()))

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual([first], self.interlocks())
        self.assertEqual([first], list(bar.Interlocks))
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.doc.recompute()
        self.assertOneSolid(bar)

    def test_ok_or_cancel_with_nothing_picked_after_apply_and_continue_just_close(self):
        _, bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        for close in ("accept", "reject"):
            with self.subTest(close=close):
                panel = self.run_command(
                    (bar, BOTTOM_INNER) if close == "accept" else (bar, RIGHT_INNER),
                    (bar, RIGHT_INNER) if close == "accept" else (bar, TOP_INNER),
                )
                self.apply()
                kept = list(self.interlocks())
                count = len(self.doc.UndoNames)
                # One wall clicked: still nothing made, OK still closes.
                self.click(bar, LEFT_INNER)
                self.assertEqual(HINT_ONE, self.message(panel))
                self.assertTrue(panel.ok_button_enabled())
                self.assertFalse(self.apply_button().isEnabled())

                self.assertTrue(getattr(panel, close)())
                self.close_dialog()

                self.assertEqual(kept, self.interlocks())
                self.assertEqual(count, len(self.doc.UndoNames))
        self.assertEqual(undos + 2, len(self.doc.UndoNames))

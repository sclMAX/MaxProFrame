"""The Interlock panel makes Tabs Interlocks too, deducing the kind from the two faces (odd/tasks/t-joint-tabs.md, T4:
S1 S2 S3 S4).

Two faces clicked (or preselected) make one Interlock: the inner walls of the two tubes at a folded corner of a
Folded Bar make Fingers as before; a wall of a crossbar and the face of the rail it butts against make Tabs, clicked in
either order, on straight pieces, trims and Folded Bars. A refused pair makes nothing and the panel says why, OK
disabled. The Tabs fields are the Fingers ones, Depth and Flip hidden, with the tab Length (Automatic: the rail wall
thickness); they update the Interlock live. The settings last kept start the next Interlock of the same kind. Apply and
continue, Cancel and editing by double click work as for Fingers.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets
from test_folded_bar_panel import keep_params
from test_folded_bar_tools import BEND_MESSAGE, face_at
from test_interlock_panel import InterlockPanelFixture
from test_tab_interlock_folded_bar import CROSSBAR_UP, RAIL_BELOW, RIGHT_OUTER, TOP_UNDER, TabsOnBarFixture
from test_unfolded_geometry import T

from freecad.maxproframe._utils import piece_stack
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.interlock import interlock_settings
from freecad.maxproframe.interlock_geometry import FingerSettings, TabSettings
from freecad.maxproframe.profile_pattern import newest_piece
from freecad.maxproframe.tab_interlock import make_tab_interlock, tab_pieces

Y = App.Vector(0, 1, 0)
# The settings last kept for the next Tabs Interlock, apart from the Fingers ones.
TAB_PARAMS = (
    ("Int", "Interlock Tabs Count"),
    ("Float", "Interlock Tabs Width"),
    ("String", "Interlock Tabs Tip"),
    ("Float", "Interlock Tabs Tip Size"),
    ("Float", "Interlock Tabs Length"),
    ("Float", "Interlock Tabs Clearance"),
)
# A straight T below the bars of the fixtures (50 x 50 x 2 tubes): the rail along X, its top face at y = -500; the
# crossbar along Y from y = -490, cut against that face.
RAIL_EDGE = ((-100, -525, 0), (400, -525, 0))
CROSSBAR_EDGE = ((150, -490, 0), (150, -200, 0))
# The two side walls of the crossbar (x = 175 and x = 125); the top and the bottom face of the rail.
CROSS_EAST = App.Vector(175, -300, 0)
CROSS_WEST = App.Vector(125, -300, 0)
RAIL_TOP = App.Vector(50, -500, 0)
RAIL_BOTTOM = App.Vector(50, -550, 0)
# The legs bar of the fixtures (right, top, left; open at the bottom): the inner walls at the right-top corner.
LEGS_RIGHT_INNER = App.Vector(275, 100, 0)
LEGS_TOP_INNER = App.Vector(150, 175, 0)
# The first Tabs Interlock ever.
FIRST_TABS = TabSettings()
FIRST_FINGERS = FingerSettings(clearance=0.5)
# What the panel says.
HINT_NONE = (
    "Click the inner walls of the two tubes at a folded corner of a Folded Bar for fingers, or a wall of a crossbar "
    "and the face of the rail it butts against for tabs."
)
HINT_FINGERS = "Click the inner wall of the other tube at that corner."
HINT_TABS = (
    "Click the other face of the T joint: the face of the rail the crossbar butts against, or the wall of the "
    "crossbar that carries the tabs."
)
NO_END = "There is no T joint between Crossbar and Rail: Crossbar does not end on the face of Rail."
SAME_TUBE = "Both faces are on Crossbar: click a wall of the crossbar and the face of the rail it butts against."
MISFIT = "The tabs of the T joint between Crossbar and Rail do not fit: make them fewer or narrower."
TWICE = "The T joint between Crossbar and Rail already has tabs on that face: {}."


class TabPanelFixture(InterlockPanelFixture, TabsOnBarFixture):
    def setUp(self):
        super().setUp()
        keep_params(self, TAB_PARAMS)
        param = get_param_group(writable=True)
        for kind, name in TAB_PARAMS:
            getattr(param, f"Rem{kind}")(name)

    def straight_t(self):
        """(rail, crossbar profile, its Extend / Cut against the top face of the rail)."""
        rail = self.loose(RAIL_EDGE, "Rail")
        crossbar = self.loose(CROSSBAR_EDGE, "Crossbar")
        return rail, crossbar, self.trimmed(crossbar, rail, Y)

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def assertTabsFields(self, panel, tabs):
        form = panel.form
        self.assertEqual("Tabs", form.combo_kind.currentData())
        self.assertEqual(
            tabs,
            TabSettings(
                count=form.spin_count.value(),
                tab_width=form.spin_finger_width.value(),
                tip=form.combo_tip.currentData(),
                tip_size=form.spin_tip_size.value(),
                length=form.spin_length.value(),
                clearance=form.spin_clearance.value(),
            ),
        )

    def assertTabsMade(self, interlock, crossbar, rail, crossbar_under, rail_under):
        """``interlock`` joins the profile ``crossbar`` (tabs on ``crossbar_under``) to ``rail`` (slots in
        ``rail_under``), both pieces whole."""
        self.assertEqual("Tabs", interlock.Kind)
        self.assertEqual((crossbar, rail), (interlock.PieceA, interlock.PieceB))
        tabs, slots = tab_pieces(interlock)
        self.assertEqual((crossbar_under, rail_under), (tabs.baseObject[0], slots.baseObject[0]))
        self.assertEqual((crossbar_under, rail_under), (interlock.CrossbarFace[0], interlock.RailFace[0]))
        for obj in (tabs, slots):
            self.assertOneSolid(obj)
        self.assertGreater(tabs.Shape.Volume, crossbar_under.Shape.Volume)
        self.assertLess(slots.Shape.Volume, rail_under.Shape.Volume)
        return tabs, slots

    # Apply and continue, as the user clicks it.

    def dialog_box(self):
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
        button = self.apply_button()
        self.assertTrue(button.isEnabled())
        button.click()
        self.events()


class TabPickTest(TabPanelFixture):
    def test_a_crossbar_wall_and_the_rail_face_make_tabs_clicked_in_either_order(self):
        rail, crossbar, trim = self.straight_t()
        names, undos = self.names(), len(self.doc.UndoNames)

        for picks in (((trim, CROSS_EAST), (rail, RAIL_TOP)), ((rail, RAIL_TOP), (trim, CROSS_EAST))):
            with self.subTest(first=picks[0][0].Label):
                panel = self.run_command()
                self.assertRefused(panel, HINT_NONE)
                self.click(*picks[0])
                self.assertRefused(panel, HINT_TABS)
                self.assertEqual([], self.interlocks())

                self.click(*picks[1])

                (made,) = self.interlocks()
                tabs, slots = self.assertTabsMade(made, crossbar, rail, trim, rail)
                self.assertEqual((tabs, slots), (newest_piece(crossbar), newest_piece(rail)))
                self.assertEqual(FIRST_TABS, interlock_settings(made))
                self.assertTabsFields(panel, FIRST_TABS)
                self.assertEqual("T joint: Crossbar → Rail", panel.form.label_corner.text())
                # Automatic: the tabs go through the rail wall, flush with its inside face.
                self.assertAlmostEqual(trim.Length.Value + T, tabs.Length.Value, places=6)
                self.assertAccepts(panel)

                # Cancel leaves the document as it was, in no Undo step.
                self.assertTrue(panel.reject())
                self.close_dialog()
                self.assertEqual([], self.interlocks())
                self.assertEqual(names, self.names())
                self.assertEqual(trim, newest_piece(crossbar))
                self.assertEqual(undos, len(self.doc.UndoNames))

        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        self.assertTrue(panel.accept())
        self.close_dialog()
        (made,) = self.interlocks()
        self.assertTabsMade(made, crossbar, rail, trim, rail)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])

    def test_the_preselected_faces_make_the_tabs_interlock(self):
        rail, crossbar, trim = self.straight_t()

        panel = self.run_command((rail, RAIL_TOP), (trim, CROSS_WEST))

        (made,) = self.interlocks()
        self.assertTabsMade(made, crossbar, rail, trim, rail)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_the_rail_can_be_a_tube_of_a_folded_bar(self):
        (right, top, left), bar = self.legs()
        crossbar = self.loose(CROSSBAR_UP, "Crossbar")
        trim = self.trimmed(crossbar, top, -Y)
        panel = self.run_command()

        # An inner wall at a folded corner may start Fingers too.
        self.click(bar, TOP_UNDER)
        self.assertRefused(panel, HINT_FINGERS)
        self.click(trim, App.Vector(175, 50, 0))

        (made,) = self.interlocks()
        _, slots = self.assertTabsMade(made, crossbar, top, trim, top)
        self.assertEqual([right, slots, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertEqual([], list(bar.Interlocks))
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_the_crossbar_can_end_a_folded_bar(self):
        (right, top, left), bar = self.legs()
        rail = self.loose(RAIL_BELOW, "Rail")
        trim = self.trimmed(right, rail, Y)
        length = bar.DevelopedLength.Value

        panel = self.run_command((rail, App.Vector(150, 0, 0)), (bar, RIGHT_OUTER))

        (made,) = self.interlocks()
        tabs, _ = self.assertTabsMade(made, right, rail, trim, rail)
        self.assertEqual([tabs, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(length + T, bar.DevelopedLength.Value, delta=1e-4)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_faces_that_make_no_interlock_make_nothing_and_say_why(self):
        _, bar = self.legs()
        rail, _, trim = self.straight_t()
        names = self.names()

        for picks, message in (
            (((trim, CROSS_EAST), (rail, RAIL_BOTTOM)), NO_END),
            (((trim, CROSS_EAST), (trim, CROSS_WEST)), SAME_TUBE),
            (((bar, self.bend_point(bar, 45.0)),), BEND_MESSAGE),
        ):
            with self.subTest(message=message):
                panel = self.run_command()
                for obj, point in picks:
                    self.click(obj, point)

                self.assertRefused(panel, message)
                self.assertEqual(names, self.names())
                self.assertTrue(panel.reject())
                self.close_dialog()

    def test_when_neither_order_makes_tabs_the_order_that_finds_the_t_joint_says_why(self):
        rail, _, trim = self.straight_t()
        names = self.names()
        param = get_param_group(writable=True)
        param.SetString("Interlock Kind", "Tabs")
        param.SetInt("Interlock Tabs Count", 3)
        param.SetFloat("Interlock Tabs Width", 20.0)

        # The rail clicked first: as clicked, the rail would be the crossbar and ends nowhere near the crossbar.
        panel = self.run_command((rail, RAIL_TOP), (trim, CROSS_EAST))

        self.assertRefused(panel, MISFIT)
        self.assertEqual(names, self.names())
        # The settings make it: the newest face waits for the next one.
        panel.form.spin_count.setValue(2)
        self.events()
        self.assertEqual([], self.interlocks())
        Gui.Selection.clearSelection()
        self.click(rail, RAIL_TOP)
        (made,) = self.interlocks()
        self.assertEqual(TabSettings(count=2, tab_width=20.0), interlock_settings(made))
        self.assertAccepts(panel)

    def test_a_second_interlock_on_the_same_faces_is_refused(self):
        rail, crossbar, trim = self.straight_t()
        made = make_tab_interlock(trim, face_at(trim, CROSS_EAST), rail, face_at(rail, RAIL_TOP))
        self.doc.recompute()
        tabs, slots = tab_pieces(made)

        # In either order: the side of a slot is no end of the rail.
        for picks in (((tabs, CROSS_EAST), (slots, RAIL_TOP)), ((slots, RAIL_TOP), (tabs, CROSS_EAST))):
            with self.subTest(first=picks[0][0].Label):
                panel = self.run_command(*picks)

                self.assertRefused(panel, TWICE.format(made.Label))
                self.assertEqual([made], self.interlocks())
                self.assertTrue(panel.reject())
                self.close_dialog()


class TabFieldsTest(TabPanelFixture):
    def test_tabs_show_the_length_and_hide_depth_and_flip(self):
        rail, _, trim = self.straight_t()
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        form = panel.form

        self.assertEqual([("Fingers", "Fingers"), ("Tabs", "Tabs")], [
            (form.combo_kind.itemText(i), form.combo_kind.itemData(i)) for i in range(form.combo_kind.count())
        ])  # fmt: skip
        # The kind is the one the faces make: not a choice.
        self.assertFalse(form.combo_kind.isEnabled())
        self.assertEqual("Tabs", form.groupBox_settings.title())
        self.assertEqual("T joint", form.groupBox_corner.title())
        layout = form.groupBox_settings.layout()
        self.assertEqual("Tab width", layout.labelForField(form.spin_finger_width).text())
        self.assertEqual("Length", layout.labelForField(form.spin_length).text())
        self.assertEqual("Automatic", form.spin_length.specialValueText())
        self.assertEqual("Automatic", form.spin_length.text())
        for widget in (form.spin_depth, layout.labelForField(form.spin_depth), form.cb_flip):
            self.assertTrue(widget.isHidden())
        for widget in (form.spin_length, layout.labelForField(form.spin_length), form.spin_count, form.spin_tip_size):
            self.assertFalse(widget.isHidden())
        self.assertTrue(panel.accept())
        self.close_dialog()

        # Fingers show Depth and Flip, not the length.
        _, bar = self.legs()
        panel = self.run_command((bar, LEGS_RIGHT_INNER), (bar, LEGS_TOP_INNER))
        form = panel.form
        self.assertEqual("Fingers", form.combo_kind.currentData())
        self.assertEqual("Fingers", form.groupBox_settings.title())
        self.assertEqual("Corner", form.groupBox_corner.title())
        layout = form.groupBox_settings.layout()
        self.assertEqual("Finger width", layout.labelForField(form.spin_finger_width).text())
        for widget in (form.spin_depth, form.cb_flip):
            self.assertFalse(widget.isHidden())
        for widget in (form.spin_length, layout.labelForField(form.spin_length)):
            self.assertTrue(widget.isHidden())
        self.assertTrue(panel.accept())

    def test_the_fields_update_the_tabs_interlock_and_recompute(self):
        rail, _, trim = self.straight_t()
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        (made,) = self.interlocks()
        tabs, slots = tab_pieces(made)
        form = panel.form
        self.assertFalse(form.spin_tip_size.isEnabled())

        # (change, settings it makes, whether the pieces change).
        for change, fields, reshapes in (
            (lambda: form.spin_count.setValue(3), dict(count=3), True),
            (lambda: form.spin_length.setValue(3.0), dict(length=3.0), True),
            (lambda: form.spin_clearance.setValue(0.2), dict(clearance=0.2), True),
            (lambda: form.spin_finger_width.setValue(8.0), dict(tab_width=8.0), True),
            # A Chamfer tip of size 0 is a square one.
            (
                lambda: form.combo_tip.setCurrentIndex(form.combo_tip.findData("Chamfer")),
                dict(tip="Chamfer"),
                False,
            ),
            (lambda: form.spin_tip_size.setValue(0.5), dict(tip_size=0.5), True),
        ):
            with self.subTest(fields=fields):
                before = (tabs.Shape.Volume, slots.Shape.Volume)
                expected = TabSettings(**{**vars(interlock_settings(made)), **fields})
                change()
                self.events()

                self.assertEqual(expected, interlock_settings(made))
                if reshapes:
                    self.assertNotEqual(before, (tabs.Shape.Volume, slots.Shape.Volume))
                for obj in (tabs, slots):
                    self.assertOneSolid(obj)
                self.assertAccepts(panel)
        self.assertTrue(form.spin_tip_size.isEnabled())
        self.assertAlmostEqual(trim.Length.Value + 3.0, tabs.Length.Value, places=6)

        # A refusal of the pieces shows in the panel and disables OK.
        form.spin_finger_width.setValue(20.0)
        self.events()
        self.assertIn("Invalid", tabs.State)
        self.assertRefused(panel, MISFIT)
        form.spin_count.setValue(2)
        self.events()
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())

    def test_the_settings_last_kept_start_the_next_interlock_of_the_same_kind(self):
        (right, top, _), bar = self.legs()
        rail, crossbar, trim = self.straight_t()
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        panel.form.spin_count.setValue(3)
        panel.form.spin_clearance.setValue(0.2)
        panel.form.spin_length.setValue(3.0)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        used = TabSettings(count=3, clearance=0.2, length=3.0)
        param = get_param_group()
        self.assertEqual(3, param.GetInt("Interlock Tabs Count"))
        # The Fingers settings are their own.
        self.assertNotIn("Interlock Count", param.GetInts())

        # The next panel starts with the Tabs kept; a folded corner takes the Fingers ones.
        panel = self.run_command()
        self.assertTabsFields(panel, used)
        self.click(bar, LEGS_RIGHT_INNER)
        self.click(bar, LEGS_TOP_INNER)
        (fingers,) = [obj for obj in self.interlocks() if obj.Kind == "Fingers"]
        self.assertEqual((right, top), (fingers.PieceA, fingers.PieceB))
        self.assertEqual(FIRST_FINGERS, interlock_settings(fingers))
        self.assertFields(panel, FIRST_FINGERS)
        self.assertFalse(panel.form.spin_depth.isHidden())
        panel.form.spin_count.setValue(4)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(3, param.GetInt("Interlock Tabs Count"))

        # Fingers kept last: the next panel shows them; a T joint takes the Tabs ones.
        panel = self.run_command()
        self.assertFields(panel, FingerSettings(count=4, clearance=0.5))
        first = next(obj for obj in self.interlocks() if obj.Kind == "Tabs")
        tabs, slots = tab_pieces(first)
        self.click(tabs, CROSS_WEST)
        self.click(slots, RAIL_TOP)
        second = [obj for obj in self.interlocks() if obj.Kind == "Tabs" and obj is not first]
        self.assertEqual(1, len(second))
        self.assertEqual(used, interlock_settings(second[0]))
        self.assertTabsFields(panel, used)
        self.assertTrue(panel.accept())


class TabApplyContinueTest(TabPanelFixture):
    def test_apply_and_continue_on_both_walls_of_a_crossbar_then_ok(self):
        rail, crossbar, trim = self.straight_t()
        undos = len(self.doc.UndoNames)
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        panel.form.spin_count.setValue(3)
        self.events()
        (first,) = self.interlocks()
        used = TabSettings(count=3)

        self.apply()

        self.assertTrue(Gui.Control.activeDialog())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Interlock", self.doc.UndoNames[0])
        self.assertEqual(used, interlock_settings(first))
        self.assertEqual("", panel.form.label_corner.text())
        self.assertEqual(HINT_NONE, self.message(panel))
        self.assertTrue(panel.ok_button_enabled())
        self.assertFalse(self.apply_button().isEnabled())
        self.assertTabsFields(panel, used)
        tabs, slots = tab_pieces(first)

        # The other wall of the crossbar, on the pieces shown now.
        self.click(tabs, CROSS_WEST)
        self.click(slots, RAIL_TOP)
        second = [obj for obj in self.interlocks() if obj is not first]
        self.assertEqual(1, len(second))
        more_tabs, more_slots = self.assertTabsMade(second[0], crossbar, rail, tabs, slots)
        self.assertEqual(used, interlock_settings(second[0]))
        self.assertEqual("T joint: Crossbar → Rail", panel.form.label_corner.text())
        self.apply()
        self.assertEqual(undos + 2, len(self.doc.UndoNames))

        self.assertTrue(panel.ok_button_enabled())
        self.assertTrue(panel.accept())
        self.close_dialog()

        self.assertEqual({first.Name, second[0].Name}, {obj.Name for obj in self.interlocks()})
        self.assertEqual([more_tabs, tabs, trim, crossbar], list(piece_stack(more_tabs)))
        self.assertEqual([more_slots, slots, rail], list(piece_stack(more_slots)))
        self.assertEqual(undos + 2, len(self.doc.UndoNames))
        panel = self.run_command()
        self.assertTabsFields(panel, used)

    def test_cancel_after_apply_and_continue_removes_only_the_newer_interlock(self):
        rail, crossbar, trim = self.straight_t()
        undos = len(self.doc.UndoNames)
        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))
        (first,) = self.interlocks()
        self.apply()
        tabs, slots = tab_pieces(first)
        self.click(tabs, CROSS_WEST)
        self.click(slots, RAIL_TOP)
        (second,) = [obj for obj in self.interlocks() if obj is not first]
        newer = [second.Name, *(obj.Name for obj in tab_pieces(second))]

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual([first], self.interlocks())
        self.assertEqual([None] * 3, [self.doc.getObject(name) for name in newer])
        self.assertEqual((tabs, slots), (newest_piece(crossbar), newest_piece(rail)))
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.doc.recompute()
        self.assertTabsMade(first, crossbar, rail, trim, rail)


class TabEditTest(TabPanelFixture):
    def test_a_double_click_on_a_tabs_interlock_or_its_pieces_edits_it(self):
        rail, crossbar, trim = self.straight_t()
        made = make_tab_interlock(trim, face_at(trim, CROSS_EAST), rail, face_at(rail, RAIL_TOP), Count=3)
        self.doc.recompute()
        tabs, slots = tab_pieces(made)
        settings, volume, undos = interlock_settings(made), tabs.Shape.Volume, len(self.doc.UndoNames)

        for opener in (lambda: self.edit(made), lambda: self.double_click(tabs)):
            with self.subTest(opener=opener):
                panel = opener()
                self.assertIs(made, panel.edited)
                self.assertTabsFields(panel, settings)
                self.assertTrue(panel.form.cb_flip.isHidden())
                self.assertEqual("T joint: Crossbar → Rail", panel.form.label_corner.text())
                self.assertIsNone(self.apply_button())
                self.assertAccepts(panel)
                panel.form.spin_count.setValue(2)
                self.events()
                self.assertEqual(2, made.Count)
                self.assertNotAlmostEqual(volume, tabs.Shape.Volume, delta=1e-3)

                self.assertTrue(panel.reject())
                self.close_dialog()
                self.assertEqual(settings, interlock_settings(made))
                self.assertEqual(undos, len(self.doc.UndoNames))
                self.doc.recompute()
                self.assertAlmostEqual(volume, tabs.Shape.Volume, delta=1e-3)

        panel = self.double_click(slots)
        self.assertIs(made, panel.edited)
        # No picking while editing.
        self.click(rail, RAIL_BOTTOM)
        panel.form.spin_length.setValue(3.0)
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual(TabSettings(count=3, length=3.0), interlock_settings(made))
        self.assertEqual([made], self.interlocks())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Interlock", self.doc.UndoNames[0])
        self.assertAlmostEqual(trim.Length.Value + 3.0, tabs.Length.Value, places=6)

    def double_click(self, piece):
        count = len(self.recorded)
        self.assertTrue(piece.ViewObject.Proxy.doubleClicked(piece.ViewObject))
        self.assertEqual(count + 1, len(self.recorded))
        self.events()
        return self.recorded[-1]

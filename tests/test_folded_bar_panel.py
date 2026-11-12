"""Folded miter commands and the Folded Bar panel (odd/tasks/folded-miter.md, T6: S1 S2 S6 S8 S9 S12, with the
S14 S17 S20 S21 settings the panel shows).

Folded Bar folds the selected tubes with a bend configuration of the store, previewed live like End Miter; every
reason the chain does not fold, and an own miter at a folded corner, is shown and keeps OK disabled. Double-click
edits a bar in one Undo step. Unfold Bar makes the straight bar of a selected Folded Bar. Create BOM and Populate IDs
take a selected Folded Bar.

S22 (T9): like Create Miter Ends, Folded Bar is active with a document, opens its panel at once and takes the tube
pieces clicked while the panel is open.
"""

import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtCore, QtWidgets
from test_end_miter_geometry import polar
from test_extend_cut_preview import keep_auto_preview
from test_folded_bar import FoldedBarFixture
from test_unfolded_geometry import PLAIN

from freecad.maxproframe import bend_config_dialog, create_folded_bar_tool
from freecad.maxproframe._utils import is_foldedbar, is_unfoldedbar
from freecad.maxproframe.bend_config import (
    LAST_USED_PARAM,
    BendConfiguration,
    BendConfigurationStore,
    get_last_used_configuration,
    set_last_used_configuration,
)
from freecad.maxproframe.create_bom_tool import CreateBOMCommand, CreateBOMTaskPanel
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.create_folded_bar_tool import FoldedBarCommand, UnfoldBarCommand
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.folded_bar import make_folded_bar
from freecad.maxproframe.InitGui import MaxProFrame
from freecad.maxproframe.populate_ids_tool import PopulateIDsCommand, PopulateIDsTaskPanel, QtGui, ResetIDsCommand

STEEL = BendConfiguration("Steel 50x50x2", "Steel", 2.0, 3.0, 0.4)
STEEL_R4 = BendConfiguration("Steel r4", "Steel", 2.0, 4.0, 0.4)
ALU_3 = BendConfiguration("Alu 3", "Aluminium", 3.0, 4.0, 0.33)
AUTO_PREVIEW = SimpleNamespace(auto_preview_param="Folded Bar Auto Preview")
COMMANDS = ("MaxProFrame_FoldedBar", "MaxProFrame_UnfoldBar", "MaxProFrame_BendConfigurations")
NOT_A_CHAIN = "The selected profiles do not form one chain: Profile meets none of the others."
# 50 mm deep tube, 2 mm walls, key of a quarter of the depth: 2 <= r <= 50 - 4 - 12.5.
RADIUS_RANGE = "The inside bend radius must be between 2 and 33.5 mm."
KEY_WITHOUT_ROOM = (
    "The key does not fit in the notch between Profile and Profile001 with this inside radius: make the radius "
    "smaller or turn the key off."
)
WIDE_WITHOUT_RELIEF = (
    "The corner between Profile001 and Profile002 bends 135 degrees: without the relief it bends up to "
    "106.3 degrees. Turn the relief on."
)
OWN_MITER = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it or make that corner the open one."
OWN_MITER_OPEN_CHAIN = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it."
NO_CONFIGURATION = "Add a bend configuration: press Manage configurations."
TOO_FEW = "Select at least two profiles that meet end to end."
BOM_PARAMS = (
    ("Bool", "Full Parent Path"),
    ("Bool", "Include Links in BOM"),
    ("Bool", "Group BOM Items by Material/Size/Family"),
    ("Bool", "Generate Cut List"),
    ("Float", "Stock Length"),
    ("Float", "Kerf"),
)


def keep_params(test, entries):
    """Put back the MaxProFrame parameters ``entries`` ((kind, name)) as they were before ``test``."""
    param = get_param_group(writable=True)
    saved = []
    for kind, name in entries:
        stored = name in getattr(param, f"Get{kind}s")()
        saved.append((kind, name, stored, getattr(param, f"Get{kind}")(name) if stored else None))

    def restore():
        for kind, name, stored, value in saved:
            if stored:
                getattr(param, f"Set{kind}")(name, value)
            else:
                getattr(param, f"Rem{kind}")(name)

    test.addCleanup(restore)


class FoldedPanelFixture(FoldedBarFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self, AUTO_PREVIEW)
        keep_params(self, [("String", LAST_USED_PARAM)])
        set_last_used_configuration("")
        folder = tempfile.mkdtemp(prefix="mpf_folded_panel_")
        self.addCleanup(shutil.rmtree, folder, True)
        environment = patch.dict(os.environ, {"MAXPROFRAME_USER_PROFILES_DIR": folder})
        environment.start()
        self.addCleanup(environment.stop)
        self.store = BendConfigurationStore(folder)
        for configuration in (STEEL, STEEL_R4, ALU_3):
            self.store.save(configuration)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        recorded = self.recorded
        # Every selection change FreeCAD reports to a panel: none once the panel stopped listening.
        self.notified = []
        notified = self.notified
        base = create_folded_bar_tool.FoldedBarTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

            def addSelection(self, *args):
                notified.append((self, "add", args[1]))
                return super().addSelection(*args)

            def removeSelection(self, *args):
                notified.append((self, "remove", args[1]))
                return super().removeSelection(*args)

        recorder = patch.object(create_folded_bar_tool, "FoldedBarTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
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

    def select(self, *objects):
        Gui.Selection.clearSelection()
        for obj in objects:
            Gui.Selection.addSelection(self.doc.Name, obj.Name)

    def run_command(self, *objects):
        self.select(*objects)
        count = len(self.recorded)
        FoldedBarCommand().Activated()
        self.assertEqual(count + 1, len(self.recorded))
        self.assertTrue(Gui.Control.activeDialog())
        self.events()
        return self.recorded[-1]

    def edit(self, bar):
        count = len(self.recorded)
        Gui.getDocument(self.doc.Name).setEdit(bar.Name, 0)
        self.assertEqual(count + 1, len(self.recorded))
        self.events()
        return self.recorded[-1]

    def bars(self):
        return [obj for obj in self.doc.Objects if is_foldedbar(obj)]

    def names(self):
        return sorted(obj.Name for obj in self.doc.Objects)

    def messages(self, panel):
        return panel.form.message_label.text()

    def assertRefused(self, panel, message):
        self.assertIn(message, self.messages(panel).split("\n"))
        # The dialog's own OK button, kept by modifyStandardButtons.
        self.assertIsNotNone(panel._ok_button)
        self.assertFalse(panel.ok_button_enabled())
        self.assertFalse(panel.accept())

    def assertAccepts(self, panel):
        self.assertEqual("", self.messages(panel))
        self.assertIsNotNone(panel._ok_button)
        self.assertTrue(panel.ok_button_enabled())

    def wide_chain(self):
        """Open chain of three tubes with a 60 and a 135 degree corner."""
        a = (0, 0, 0)
        b = (200, 0, 0)
        c = tuple(p + q for p, q in zip(b, polar(150, 60)))
        d = tuple(p + q for p, q in zip(c, polar(120, 195)))
        return self.frame(edges=((a, b), (b, c), (c, d)))

    def miter(self, body, boundary):
        miter = make_end_miter_profile(body, [boundary])
        self.doc.recompute()
        self.assertEqual("Valid", miter.getStatusString())
        return miter


class CommandTest(FoldedPanelFixture):
    def test_commands_are_registered_with_their_icons_and_on_a_workbench_toolbar(self):
        known = set(Gui.listCommands())
        self.assertEqual([], [name for name in COMMANDS if name not in known])
        self.assertEqual(list(COMMANDS), MaxProFrame.toolbox_folded)
        icons = {
            "MaxProFrame_FoldedBar": "FoldedBar.svg",
            "MaxProFrame_UnfoldBar": "UnfoldedBar.svg",
            "MaxProFrame_BendConfigurations": "BendConfigurations.svg",
        }
        for name, icon in icons.items():
            with self.subTest(command=name):
                pixmap = Gui.Command.get(name).getInfo()["pixmap"]
                self.assertEqual(icon, os.path.basename(pixmap))
                self.assertEqual("{http://www.w3.org/2000/svg}svg", ElementTree.parse(pixmap).getroot().tag)

    def test_folded_bar_is_active_with_a_document_whatever_is_selected(self):
        # S22: like Create Miter Ends, the pieces are clicked once the panel is open.
        bottom, right, top, left = self.frame()
        miter = self.miter(bottom, left)
        sketch = bottom.AttachmentSupport[0][0]
        for selection in ((), (bottom,), (bottom, right), (miter, right, top, left), (right, sketch), (sketch,)):
            with self.subTest(selection=[obj.Label for obj in selection]):
                self.select(*selection)
                self.assertTrue(FoldedBarCommand().IsActive())

    def test_unfold_bar_needs_one_folded_bar(self):
        profiles, bar = self.make_bar(**PLAIN)
        for selection, active in (((), False), ((bar,), True), ((bar, profiles[0]), False), ((profiles[0],), False)):
            with self.subTest(selection=[obj.Label for obj in selection]):
                self.select(*selection)
                self.assertEqual(active, UnfoldBarCommand().IsActive())

    def test_bend_configurations_is_always_active(self):
        self.select()
        self.assertTrue(bend_config_dialog.BendConfigurationsCommand().IsActive())

    def test_unfold_bar_makes_the_unfolded_bar_in_one_undo_step(self):
        _, bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        self.select(bar)

        UnfoldBarCommand().Activated()

        (unfolded,) = [obj for obj in self.doc.Objects if is_unfoldedbar(obj)]
        self.assertEqual(bar, unfolded.FoldedBar)
        self.assertOneSolid(unfolded)
        self.assertAlmostEqual(bar.DevelopedLength.Value, unfolded.Shape.BoundBox.XLength, delta=1e-4)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Unfold Bar", self.doc.UndoNames[0])


class CreatePanelTest(FoldedPanelFixture):
    def test_panel_defaults_come_from_the_last_used_configuration(self):
        set_last_used_configuration(STEEL_R4.name)
        bottom, right, top, left = self.frame()

        panel = self.run_command(bottom, right, top, left)

        form = panel.form
        self.assertEqual(["Alu 3", "Steel 50x50x2", "Steel r4"], panel.configuration_names())
        self.assertEqual("Steel r4", form.combo_configuration.currentData())
        self.assertEqual(4.0, form.spin_radius.value())
        self.assertEqual(4, form.members_list.count())
        # A closed frame opens at a corner of the first selected profile: where it meets the last one by default.
        self.assertTrue(form.combo_open_corner.isVisibleTo(form))
        self.assertEqual(
            [["Profile", "Profile003"], ["Profile", "Profile001"]],
            [[obj.Label for obj in form.combo_open_corner.itemData(i)] for i in range(form.combo_open_corner.count())],
        )
        self.assertEqual(0, form.combo_open_corner.currentIndex())
        self.assertEqual([0.0, 0.0, 0.0], [spin.value() for spin in panel.corner_spins()])
        self.assertEqual(
            (0.0, True, True, 0.0, 0.0),
            (
                form.spin_clearance.value(),
                form.cb_key.isChecked(),
                form.cb_relief.isChecked(),
                form.spin_key_diameter.value(),
                form.spin_relief_radius.value(),
            ),
        )
        # S20 (L26): the key is a half circle, sized by its diameter only: no neck field.
        self.assertFalse(hasattr(form, "spin_neck_width"))
        notch = form.groupBox_notch.layout()
        self.assertEqual(
            ["Clearance", "Key diameter", "Relief radius"],
            [
                notch.itemAt(row, QtWidgets.QFormLayout.LabelRole).widget().text()
                for row in range(notch.rowCount())
                if notch.itemAt(row, QtWidgets.QFormLayout.LabelRole) is not None
            ],
        )
        self.assertTrue(form.cb_auto_update.isChecked())
        self.assertAccepts(panel)

    def test_without_a_last_used_configuration_the_first_one_is_chosen(self):
        panel = self.run_command(*self.frame())

        self.assertEqual("Alu 3", panel.form.combo_configuration.currentData())
        self.assertEqual(4.0, panel.form.spin_radius.value())
        self.assertRefused(panel, "Alu 3 is for 3 mm walls; Profile has 2 mm walls.")

    def test_choosing_a_configuration_takes_its_radius(self):
        panel = self.run_command(*self.frame())
        form = panel.form

        form.combo_configuration.setCurrentIndex(form.combo_configuration.findData(STEEL.name))

        self.assertEqual(3.0, form.spin_radius.value())
        self.assertAccepts(panel)

    def test_preview_shows_the_bar_before_ok_and_hides_the_tips(self):
        set_last_used_configuration(STEEL.name)
        profiles = self.frame()

        panel = self.run_command(*profiles)

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertTrue(all(not tip.Visibility for tip in profiles))
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def test_ok_creates_one_folded_bar_with_the_panel_values_and_remembers_the_configuration(self):
        set_last_used_configuration(STEEL_R4.name)
        bottom, right, top, left = self.frame()
        undos = len(self.doc.UndoNames)
        panel = self.run_command(bottom, right, top, left)
        form = panel.form
        form.combo_configuration.setCurrentIndex(form.combo_configuration.findData(STEEL.name))
        form.spin_radius.setValue(4.0)
        panel.corner_spins()[1].setValue(5.0)
        form.spin_clearance.setValue(0.2)
        form.cb_key.setChecked(False)
        form.spin_relief_radius.setValue(3.5)

        self.assertTrue(panel.accept())
        self.close_dialog()

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual(
            ("Steel 50x50x2", "Steel", 2.0, 4.0, 0.4),
            (bar.BendConfiguration, bar.BendMaterial, bar.WallThickness.Value, bar.InsideRadius.Value, bar.KFactor),
        )
        self.assertEqual([0.0, 5.0, 0.0], list(bar.CornerRadii))
        self.assertEqual(
            (0.2, False, True, 0.0, 3.5),
            (round(bar.Clearance.Value, 9), bar.Key, bar.Relief, bar.KeyDiameter.Value, bar.ReliefRadius.Value),
        )
        self.assertEqual([bottom, right, top, left], list(bar.Segments))
        self.assertEqual([bottom, left], list(bar.OpenCorner))
        self.assertEqual(STEEL.name, get_last_used_configuration())
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Folded Bar", self.doc.UndoNames[0])

    def test_with_update_automatically_unchecked_ok_creates_the_bar(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        set_last_used_configuration(STEEL.name)
        profiles = self.frame()
        before = self.names()
        panel = self.run_command(*profiles)
        self.assertEqual(before, self.names())
        self.assertEqual("Pending changes", panel.form.status_label.text())

        self.assertTrue(panel.accept())

        (bar,) = self.bars()
        self.assertOneSolid(bar)

    def test_cancel_leaves_the_document_unchanged(self):
        set_last_used_configuration(STEEL_R4.name)
        profiles = self.frame()
        before, undos = self.names(), len(self.doc.UndoNames)
        panel = self.run_command(*profiles)
        panel.form.combo_configuration.setCurrentIndex(panel.form.combo_configuration.findData(STEEL.name))
        self.assertEqual(1, len(self.bars()))

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(before, self.names())
        self.assertTrue(all(tip.Visibility for tip in profiles))
        self.assertEqual(undos, len(self.doc.UndoNames))
        self.assertEqual(STEEL_R4.name, get_last_used_configuration())

    def test_cancel_with_undo_disabled_still_leaves_nothing(self):
        self.doc.UndoMode = 0
        set_last_used_configuration(STEEL.name)
        profiles = self.frame()
        before = self.names()
        panel = self.run_command(*profiles)

        self.assertTrue(panel.reject())

        self.assertEqual(before, self.names())
        self.assertTrue(all(tip.Visibility for tip in profiles))

    def test_refused_selection_shows_the_chain_message_and_disables_ok(self):
        set_last_used_configuration(STEEL.name)
        bottom, right, top, left = self.frame()

        panel = self.run_command(bottom, top)

        self.assertRefused(panel, NOT_A_CHAIN)
        self.assertEqual([], self.bars())

    def test_radius_out_of_its_limits_shows_them_and_disables_ok(self):
        set_last_used_configuration(STEEL.name)
        panel = self.run_command(*self.frame())

        panel.form.spin_radius.setValue(1.0)

        self.assertRefused(panel, RADIUS_RANGE)
        # At the largest radius the key has no room left on the miter line.
        panel.form.spin_radius.setValue(33.5)
        self.assertRefused(panel, KEY_WITHOUT_ROOM)
        panel.form.cb_key.setChecked(False)
        self.assertAccepts(panel)

    def test_relief_off_at_a_wide_corner_shows_why_and_disables_ok(self):
        set_last_used_configuration(STEEL.name)
        panel = self.run_command(*self.wide_chain())
        self.assertFalse(panel.form.combo_open_corner.isVisibleTo(panel.form))
        self.assertAccepts(panel)

        panel.form.cb_relief.setChecked(False)

        self.assertRefused(panel, WIDE_WITHOUT_RELIEF)
        panel.form.cb_relief.setChecked(True)
        self.assertAccepts(panel)

    def test_own_miter_at_a_folded_corner_is_reported_until_that_corner_opens(self):
        set_last_used_configuration(STEEL.name)
        bottom, right, top, left = self.frame()
        miter = self.miter(bottom, right)

        panel = self.run_command(miter, right, top, left)

        self.assertRefused(panel, OWN_MITER)
        form = panel.form
        form.combo_open_corner.setCurrentIndex(1)
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())
        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([miter, right], list(bar.OpenCorner))

    def test_own_miter_at_a_folded_corner_of_an_open_chain_is_reported(self):
        set_last_used_configuration(STEEL.name)
        first, second, third = self.wide_chain()
        miter = self.miter(first, second)

        panel = self.run_command(miter, second, third)

        self.assertRefused(panel, OWN_MITER_OPEN_CHAIN)

    def test_end_miters_at_the_open_corner_are_no_conflict(self):
        set_last_used_configuration(STEEL.name)
        bottom, right, top, left = self.frame()
        bottom_miter = self.miter(bottom, left)
        left_miter = self.miter(left, bottom)

        panel = self.run_command(bottom_miter, right, top, left_miter)

        self.assertAccepts(panel)

    def test_open_corner_choice_changes_the_start_of_the_bar(self):
        set_last_used_configuration(STEEL.name)
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)

        panel.form.combo_open_corner.setCurrentIndex(1)
        self.assertTrue(panel.accept())

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([bottom, right], list(bar.OpenCorner))
        # The bar starts at the open corner of the first selected profile and runs away from it.
        self.assertEqual([bottom, left, top, right], list(bar.Segments))

    def test_no_configuration_says_how_to_add_one(self):
        for configuration in (STEEL, STEEL_R4, ALU_3):
            self.store.delete(configuration.name)

        panel = self.run_command(*self.frame())

        self.assertRefused(panel, NO_CONFIGURATION)

    def test_manage_configurations_reloads_the_combo_keeping_the_choice(self):
        set_last_used_configuration(STEEL.name)
        panel = self.run_command(*self.frame())
        added = BendConfiguration("Steel r5", "Steel", 2.0, 5.0, 0.45)

        def add_one(dialog):
            dialog.store.save(added)
            return 0

        with patch.object(bend_config_dialog.BendConfigurationsDialog, "exec_", add_one):
            panel.form.button_manage.click()

        self.assertIn("Steel r5", panel.configuration_names())
        self.assertEqual(STEEL.name, panel.form.combo_configuration.currentData())


class PickAsYouGoTest(FoldedPanelFixture):
    """S22: the pieces clicked while the panel is open join the bar, as in Create Miter Ends."""

    def setUp(self):
        super().setUp()
        set_last_used_configuration(STEEL.name)

    def click(self, obj, sub="Face1", point=None, ctrl=False):
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            if point is None:
                Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
            else:
                Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, *point)
            self.events()

    def listed(self, panel):
        form = panel.form
        return [form.members_list.item(row).text() for row in range(form.members_list.count())]

    def selected(self):
        return {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}

    def test_with_nothing_selected_the_panel_opens_and_says_why_ok_is_disabled(self):
        panel = self.run_command()

        self.assertEqual([], panel.selection)
        self.assertEqual([], self.listed(panel))
        self.assertRefused(panel, TOO_FEW)
        self.assertEqual("No preview", panel.form.status_label.text())
        self.assertEqual([], self.bars())

    def test_clicked_profiles_join_the_list_in_order_and_the_chain_and_preview_follow(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command()
        form = panel.form

        self.click(bottom, "Face3")
        self.assertEqual(["Profile"], self.listed(panel))
        self.assertRefused(panel, TOO_FEW)
        self.assertEqual([], self.bars())

        self.click(right)
        self.assertEqual(["Profile", "Profile001"], self.listed(panel))
        self.assertAccepts(panel)
        self.assertFalse(form.combo_open_corner.isVisibleTo(form))
        self.assertEqual([0.0], [spin.value() for spin in panel.corner_spins()])
        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([bottom, right], list(bar.Segments))
        self.assertFalse(bottom.Visibility or right.Visibility)
        self.assertEqual("Preview updated", form.status_label.text())
        # The listed pieces show selected: here as the preview that hides them.
        self.assertEqual({bar.Name: ()}, self.selected())

        self.click(top)
        self.click(left, "Edge2")
        self.assertEqual(["Profile", "Profile001", "Profile002", "Profile003"], self.listed(panel))
        self.assertEqual([bottom, right, top, left], panel.selection)
        self.assertTrue(form.combo_open_corner.isVisibleTo(form))
        self.assertEqual(
            ["Between Profile and Profile003", "Between Profile and Profile001"],
            [form.combo_open_corner.itemText(i) for i in range(form.combo_open_corner.count())],
        )
        self.assertEqual(3, len(panel.corner_spins()))
        self.assertTrue(all(spin.isVisibleTo(form) for spin in panel.corner_spins()))
        self.assertAccepts(panel)
        self.assertEqual([bar], self.bars())
        self.assertEqual([bottom, right, top, left], list(bar.Segments))
        self.assertEqual([bottom, left], list(bar.OpenCorner))
        self.assertOneSolid(bar)
        self.assertFalse(any(tip.Visibility for tip in (bottom, right, top, left)))

        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual([bar], self.bars())
        self.assertOneSolid(bar)
        self.assertEqual({}, self.selected())

    def test_a_profile_clicked_again_stays_listed_once(self):
        bottom, right, top, _ = self.frame()
        panel = self.run_command(bottom, right)

        self.click(bottom, "Face2")

        self.assertEqual([bottom, right], panel.selection)

    def test_ctrl_click_on_a_listed_profile_removes_it(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        bottom, right, top, _ = self.frame()
        panel = self.run_command(bottom, right, top)

        self.click(right, "Face3", ctrl=True)

        self.assertEqual([bottom, top], panel.selection)
        self.assertEqual(["Profile", "Profile002"], self.listed(panel))
        self.assertRefused(panel, NOT_A_CHAIN)
        self.assertEqual({bottom.Name: (), top.Name: ()}, self.selected())

    def test_deselecting_a_listed_profile_removes_it(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        bottom, right, top, _ = self.frame()
        panel = self.run_command(bottom, right, top)
        self.assertEqual({bottom.Name: (), right.Name: (), top.Name: ()}, self.selected())

        Gui.Selection.removeSelection(self.doc.Name, top.Name)
        self.events()

        self.assertEqual([bottom, right], panel.selection)
        self.assertEqual(["Profile", "Profile001"], self.listed(panel))
        self.assertEqual([0.0], [spin.value() for spin in panel.corner_spins()])
        self.assertEqual({bottom.Name: (), right.Name: ()}, self.selected())

    def test_clearing_the_selection_keeps_the_list(self):
        bottom, right, _, _ = self.frame()
        panel = self.run_command(bottom, right)

        Gui.Selection.clearSelection()
        self.events()

        self.assertEqual([bottom, right], panel.selection)
        self.assertEqual(1, len(self.bars()))

    def test_ctrl_click_on_the_preview_removes_the_piece_under_it_and_shows_it_again(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        (bar,) = self.bars()

        # A click on the preview, over the middle of the left tube.
        self.click(bar, "Face1", point=(0.0, 100.0, 0.0), ctrl=True)

        self.assertEqual([bottom, right, top], panel.selection)
        self.assertAccepts(panel)
        self.assertEqual([bar], self.bars())
        self.assertEqual([bottom, right, top], list(bar.Segments))
        self.assertEqual([], list(bar.OpenCorner))
        self.assertEqual(2, len(panel.corner_spins()))
        self.assertOneSolid(bar)
        self.assertTrue(left.Visibility)
        self.assertFalse(any(tip.Visibility for tip in (bottom, right, top)))
        self.assertEqual({bar.Name: ()}, self.selected())

        # Without a chain there is no preview: every tube shows again.
        self.click(bar, "Face1", point=(300.0, 100.0, 0.0), ctrl=True)

        self.assertEqual([bottom, top], panel.selection)
        self.assertRefused(panel, NOT_A_CHAIN)
        self.assertEqual([], self.bars())
        self.assertTrue(all(tip.Visibility for tip in (bottom, right, top, left)))
        self.assertEqual("No preview", panel.form.status_label.text())

        self.click(right)
        self.assertEqual([bottom, top, right], panel.selection)
        (bar,) = self.bars()
        self.assertOneSolid(bar)

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.assertEqual([], self.bars())
        self.assertTrue(all(tip.Visibility for tip in (bottom, right, top, left)))

    def test_what_is_not_a_tube_piece_is_ignored(self):
        bottom, right, _, _ = self.frame()
        sketch = bottom.AttachmentSupport[0][0]
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        panel = self.run_command(bottom, sketch)
        self.assertEqual([bottom], panel.selection)

        for obj, sub in ((sketch, "Edge2"), (box, "Face1"), (box, "")):
            with self.subTest(clicked=obj.Label):
                self.click(obj, sub)
                self.assertEqual([bottom], panel.selection)
                self.assertEqual(["Profile"], self.listed(panel))

    def test_a_piece_made_from_a_listed_profile_takes_its_place(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top)
        miter = self.miter(bottom, left)
        self.events()

        self.click(miter)
        self.click(bottom)

        self.assertEqual([miter, right, top], panel.selection)
        self.assertEqual(["Profile_Mt", "Profile001", "Profile002"], self.listed(panel))

    def test_ok_cancel_and_closing_stop_listening_and_leave_nothing_selected(self):
        for close in ("accept", "reject", "closeDialog"):
            with self.subTest(close=close):
                for bar in self.bars():
                    self.doc.removeObject(bar.Name)
                profiles = self.frame()
                panel = self.run_command(*profiles[:2])
                self.click(profiles[2])
                self.assertEqual(profiles[:3], panel.selection)
                if close == "closeDialog":
                    Gui.Control.closeDialog()
                else:
                    self.assertTrue(getattr(panel, close)())
                self.close_dialog()
                if close != "closeDialog":
                    self.assertEqual({}, self.selected())
                del self.notified[:]

                self.click(profiles[3])
                Gui.Selection.removeSelection(self.doc.Name, profiles[3].Name)
                self.events()

                self.assertEqual([], [entry for entry in self.notified if entry[0] is panel])
                self.assertEqual(profiles[:3], panel.selection)
                self.assertEqual(1 if close == "accept" else 0, len(self.bars()))
                Gui.Selection.clearSelection()

    def test_editing_a_bar_does_not_follow_the_selection(self):
        # As End Miter's edit: the pieces of an edited bar are not changed by clicks.
        profiles, bar = self.make_bar(**PLAIN)
        other = self.frame()
        panel = self.edit(bar)

        self.click(other[0])
        Gui.Selection.removeSelection(self.doc.Name, other[0].Name)
        self.events()
        self.assertEqual([], [entry for entry in self.notified if entry[0] is panel])
        # Even told directly, the edited bar keeps its pieces.
        panel.addSelection(self.doc.Name, other[1].Name, "Face1", (0.0, 0.0, 0.0))
        panel.removeSelection(self.doc.Name, profiles[1].Name, "")
        self.events()

        self.assertEqual(profiles, panel.selection)
        self.assertEqual(4, panel.form.members_list.count())
        panel.form.spin_clearance.setValue(0.3)
        self.assertTrue(panel.accept())
        self.assertEqual(profiles, list(bar.Segments))
        self.assertAlmostEqual(0.3, bar.Clearance.Value, places=9)


class EditPanelTest(FoldedPanelFixture):
    def test_double_click_edits_the_bar_in_one_undo_step(self):
        _, bar = self.make_bar(radius=4.0, corner_radii={2: 5.0})
        undos = len(self.doc.UndoNames)

        panel = self.edit(bar)

        form = panel.form
        self.assertEqual(STEEL.name, form.combo_configuration.currentData())
        self.assertEqual(4.0, form.spin_radius.value())
        self.assertEqual([0.0, 0.0, 5.0], [spin.value() for spin in panel.corner_spins()])
        form.spin_clearance.setValue(0.3)
        form.cb_key.setChecked(False)
        self.assertTrue(panel.accept())
        self.close_dialog()

        self.assertEqual(1, len(self.bars()))
        self.assertAlmostEqual(0.3, bar.Clearance.Value, places=9)
        self.assertFalse(bar.Key)
        self.assertEqual(4.0, bar.InsideRadius.Value)
        self.assertEqual([0.0, 0.0, 5.0], list(bar.CornerRadii))
        self.assertOneSolid(bar)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Folded Bar", self.doc.UndoNames[0])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual((0.0, True), (bar.Clearance.Value, bar.Key))

    def test_ok_without_changes_adds_no_undo_step(self):
        _, bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        panel = self.edit(bar)

        self.assertTrue(panel.accept())

        self.assertEqual(undos, len(self.doc.UndoNames))
        self.assertEqual([], list(bar.OpenCorner))

    def test_edit_opens_the_other_corner_of_the_first_piece(self):
        bottom, right, top, left = self.frame()
        bar = make_folded_bar([bottom, right, top, left], STEEL, **PLAIN)
        panel = self.edit(bar)

        panel.form.combo_open_corner.setCurrentIndex(1)
        self.assertTrue(panel.accept())

        self.assertOneSolid(bar)
        self.assertEqual([bottom, right], list(bar.OpenCorner))
        self.assertEqual([bottom, left, top, right], list(bar.Segments))

    def test_cancel_puts_the_edited_bar_back(self):
        _, bar = self.make_bar(**PLAIN)
        volume = bar.Shape.Volume
        panel = self.edit(bar)
        panel.form.spin_clearance.setValue(0.3)
        panel.update_preview()
        self.assertAlmostEqual(0.3, bar.Clearance.Value, places=9)

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()

        self.assertEqual(0.0, bar.Clearance.Value)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=1e-3)

    def test_bar_whose_configuration_is_not_stored_keeps_its_copy(self):
        _, bar = self.make_bar(**PLAIN)
        self.store.delete(STEEL.name)

        panel = self.edit(bar)

        self.assertEqual(STEEL.name, panel.form.combo_configuration.currentData())
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())
        self.assertEqual("Steel", bar.BendMaterial)


class OutputCommandsTest(FoldedPanelFixture):
    def test_create_bom_takes_a_selected_folded_bar(self):
        keep_params(self, BOM_PARAMS)
        _, bar = self.make_bar(**PLAIN)
        self.select(bar)
        self.assertTrue(CreateBOMCommand().IsActive())
        panel = CreateBOMTaskPanel()
        panel.open()

        self.assertTrue(panel.accept())

        (sheet,) = self.doc.getObjectsByLabel(f"{bar.Label}_BOM")
        self.assertEqual(bar.Label, sheet.getContents("N3").removeprefix("'"))
        self.assertEqual(f"{bar.DevelopedLength.Value:.1f}", sheet.getContents("E3").removeprefix("'"))
        self.assertEqual("", sheet.getContents("N4"))

    def test_create_bom_still_takes_profiles_and_refuses_a_sketch(self):
        profiles = self.frame()
        self.select(profiles[0])
        self.assertTrue(CreateBOMCommand().IsActive())
        self.select(profiles[0].AttachmentSupport[0][0])
        self.assertFalse(CreateBOMCommand().IsActive())

    def test_populate_ids_takes_a_selected_folded_bar(self):
        _, bar = self.make_bar(**PLAIN)
        self.select(bar)
        self.assertTrue(PopulateIDsCommand().IsActive())

        panel = PopulateIDsTaskPanel()

        self.assertEqual([bar], panel.sel_profiles)

    def test_populate_ids_still_takes_profiles_and_refuses_a_sketch(self):
        profiles = self.frame()
        self.select(profiles[0])
        self.assertTrue(PopulateIDsCommand().IsActive())
        self.select(profiles[0].AttachmentSupport[0][0])
        self.assertFalse(PopulateIDsCommand().IsActive())

    def test_reset_ids_takes_a_selected_folded_bar(self):
        profiles, bar = self.make_bar(**PLAIN)
        bar.PID = "7"
        self.select(bar)
        self.assertTrue(ResetIDsCommand().IsActive())

        with patch.object(QtGui.QMessageBox, "question", return_value=QtGui.QMessageBox.Yes):
            ResetIDsCommand().Activated()

        self.assertEqual("", bar.PID)
        self.select(profiles[0].AttachmentSupport[0][0])
        self.assertFalse(ResetIDsCommand().IsActive())


if __name__ == "__main__":
    unittest.main()

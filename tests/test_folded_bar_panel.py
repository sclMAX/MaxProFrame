"""Folded miter commands and the Folded Bar panel (odd/tasks/folded-miter.md, T6: S1 S2 S6 S8 S9 S12, with the
S14 S17 S20 S21 settings the panel shows).

Folded Bar folds the selected tubes with a bend configuration of the store, previewed live like End Miter; every
reason the chain does not fold, and an own miter at a folded corner, is shown and keeps OK disabled. Double-click
edits a bar in one Undo step. Unfold Bar makes the straight bar of a selected Folded Bar. Create BOM and Populate IDs
take a selected Folded Bar.
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
from PySide import QtWidgets
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
WIDE_WITHOUT_RELIEF = (
    "The corner between Profile001 and Profile002 bends 135 degrees: without the relief it bends up to "
    "106.3 degrees. Turn the relief on."
)
OWN_MITER = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it or make that corner the open one."
OWN_MITER_OPEN_CHAIN = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it."
NO_CONFIGURATION = "Add a bend configuration: press Manage configurations."
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
        base = create_folded_bar_tool.FoldedBarTaskPanel

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

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

    def test_folded_bar_needs_two_or_more_profiles_or_pieces_made_from_them(self):
        bottom, right, top, left = self.frame()
        miter = self.miter(bottom, left)
        sketch = bottom.AttachmentSupport[0][0]
        for selection, active in (
            ((), False),
            ((bottom,), False),
            ((bottom, right), True),
            ((miter, right, top, left), True),
            ((right, sketch), False),
        ):
            with self.subTest(selection=[obj.Label for obj in selection]):
                self.select(*selection)
                self.assertEqual(active, FoldedBarCommand().IsActive())

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
            (0.0, True, True, 0.0, 0.0, 0.0),
            (
                form.spin_clearance.value(),
                form.cb_key.isChecked(),
                form.cb_relief.isChecked(),
                form.spin_key_diameter.value(),
                form.spin_neck_width.value(),
                form.spin_relief_radius.value(),
            ),
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
            (0.2, False, True, 0.0, 0.0, 3.5),
            (
                round(bar.Clearance.Value, 9),
                bar.Key,
                bar.Relief,
                bar.KeyDiameter.Value,
                bar.NeckWidth.Value,
                bar.ReliefRadius.Value,
            ),
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
        panel.form.spin_radius.setValue(33.5)
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

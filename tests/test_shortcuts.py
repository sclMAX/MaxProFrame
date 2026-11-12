"""Keyboard shortcuts of the MaxProFrame commands: M, then one letter, none shared with another command."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from test_toolbar_translations import action

from freecad.maxproframe import (  # noqa: F401  (importing registers the commands)
    create_bom_tool,
    create_drill_hole_tool,
    create_edit_balloons_tool,
    create_end_miter_tool,
    create_extend_cut_tool,
    create_extruded_cutout_tool,
    create_link,
    create_notch_tool,
    create_profile_pattern_tool,
    create_profiles_tool,
    library_manager_dialog,
    parametric_line,
    populate_ids_tool,
    utilities,
)
from freecad.maxproframe.ff_tools import COMMANDS
from freecad.maxproframe.InitGui import MaxProFrame

# The shortcuts the README lists; the commands left out are used seldom or reset data, and have none.
SHORTCUTS = {
    "MaxProFrame_CreateProfiles": "M, P",
    "MaxProFrame_ParametricLine": "M, L",
    "MaxProFrame_EndMiter": "M, M",
    "MaxProFrame_ExtendCut": "M, E",
    "MaxProFrame_Notch": "M, N",
    "MaxProFrame_AddExtrudeCutout": "M, H",
    "MaxProFrame_DrillHole": "M, D",
    "MaxProFrame_Link": "M, K",
    "MaxProFrame_PopulateIDs": "M, U",
    "MaxProFrame_CreateBalloons": "M, O",
    "MaxProFrame_CreateBOM": "M, B",
    "MaxProFrame_RecomputeFrameForgeObjects": "M, R",
    "MaxProFrame_ExportTechDraw": "M, T",
}
WITHOUT_SHORTCUT = (
    "MaxProFrame_ManageProfileLibraries",
    "MaxProFrame_ResetIDs",
    "MaxProFrame_RefreshBalloons",
    "MaxProFrame_CreatePieceTable",
    "MaxProFrame_ProfilePattern",
    "MaxProFrame_FoldedBar",
    "MaxProFrame_UnfoldBar",
    "MaxProFrame_BendConfigurations",
)


def declared(name):
    """The shortcut command ``name`` declares: what FreeCAD gives it unless the user changed it."""
    return COMMANDS[name].GetResources().get("Accel", "")


class TestShortcuts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A workbench registers its commands, and their shortcuts, once loaded: load every one installed, so
        # the check covers the commands of all of them and not only those an earlier test happened to load.
        if "MaxProFrame" not in Gui.listWorkbenches():
            Gui.addWorkbench(MaxProFrame())
        # BIM queues its modal welcome dialog on its first activation; a later test would wait on it forever.
        bim = App.ParamGet("User parameter:BaseApp/Preferences/Mod/BIM")
        first_time = bim.GetBool("FirstTime", True)
        bim.SetBool("FirstTime", False)
        cls.addClassCleanup(bim.SetBool, "FirstTime", first_time)
        previous = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        cls.failed = {}
        for name in sorted(Gui.listWorkbenches()):
            try:
                Gui.activateWorkbench(name)
            except Exception as error:
                cls.failed[name] = str(error)
        Gui.activateWorkbench(previous or "MaxProFrame")
        cls.dialogs = cls.run_queued_tasks()

    @staticmethod
    def run_queued_tasks():
        """Run what the workbenches queued on activation; the modal dialogs it opened, closed."""
        dialogs = []

        def close_modal():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is not None:
                dialogs.append(dialog.windowTitle() or dialog.objectName() or type(dialog).__name__)
                dialog.close()
                QtCore.QTimer.singleShot(200, close_modal)

        QtCore.QTimer.singleShot(200, close_modal)
        for _ in range(10):
            QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(300)
        QtWidgets.QApplication.processEvents()
        return dialogs

    def test_every_workbench_loads_without_a_dialog(self):
        # The clash check below covers only the workbenches that load; none may leave a dialog open.
        self.assertEqual((self.failed, self.dialogs), ({}, []))

    def test_each_command_declares_its_shortcut(self):
        # The declared shortcut, not FreeCAD's: a user may have changed it in Tools > Customize > Keyboard.
        self.maxDiff = None
        self.assertEqual({name: declared(name) for name in SHORTCUTS}, SHORTCUTS)
        self.assertEqual({name: declared(name) for name in WITHOUT_SHORTCUT}, dict.fromkeys(WITHOUT_SHORTCUT, ""))

    def test_every_maxproframe_command_is_in_the_scheme(self):
        ours = sorted(name for name in Gui.listCommands() if name.startswith("MaxProFrame_"))
        self.assertEqual(ours, sorted([*SHORTCUTS, *WITHOUT_SHORTCUT]))
        self.assertEqual(sorted(COMMANDS), ours)

    def test_no_command_of_another_workbench_uses_a_shortcut_of_ours(self):
        taken = {}
        for name in Gui.listCommands():
            if not name.startswith("MaxProFrame_"):
                taken.setdefault(Gui.Command.get(name).getShortcut(), []).append(name)
        self.assertEqual({text: taken[text] for text in SHORTCUTS.values() if text in taken}, {})

    def test_the_tooltip_shows_the_shortcut_next_to_the_title(self):
        # FreeCAD adds it after the title: "Drill Hole (M, D)", also above a tooltip of our own markup.
        Gui.activateWorkbench("MaxProFrame")
        missing = {
            name: action(name).toolTip()[:120]
            for name, text in SHORTCUTS.items()
            if f"</b> ({text})</p>" not in action(name).toolTip()
        }
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()

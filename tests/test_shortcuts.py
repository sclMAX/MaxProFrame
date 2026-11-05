"""Keyboard shortcuts of the MaxProFrame commands: M, then one letter, none shared with another command."""

import unittest

import FreeCADGui as Gui

from freecad.maxproframe import (  # noqa: F401  (importing registers the commands)
    create_bom_tool,
    create_drill_hole_tool,
    create_edit_balloons_tool,
    create_end_miter_tool,
    create_extend_cut_tool,
    create_extruded_cutout_tool,
    create_link,
    create_notch_tool,
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
WITHOUT_SHORTCUT = ("MaxProFrame_ManageProfileLibraries", "MaxProFrame_ResetIDs", "MaxProFrame_RefreshBalloons")


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
        previous = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        for name in sorted(Gui.listWorkbenches()):
            try:
                Gui.activateWorkbench(name)
            except Exception:
                pass
        Gui.activateWorkbench(previous or "MaxProFrame")

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


if __name__ == "__main__":
    unittest.main()

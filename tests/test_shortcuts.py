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
    "MaxProFrame_PopulateIDs": "M, I",
    "MaxProFrame_CreateBalloons": "M, O",
    "MaxProFrame_CreateBOM": "M, B",
    "MaxProFrame_RecomputeFrameForgeObjects": "M, R",
    "MaxProFrame_ExportTechDraw": "M, T",
}
WITHOUT_SHORTCUT = ("MaxProFrame_ManageProfileLibraries", "MaxProFrame_ResetIDs", "MaxProFrame_RefreshBalloons")


def shortcut(name):
    return Gui.Command.get(name).getShortcut()


class TestShortcuts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # FreeCAD gives the commands their shortcuts once a workbench showing them is active.
        if "MaxProFrame" not in Gui.listWorkbenches():
            Gui.addWorkbench(MaxProFrame())
        previous = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        Gui.activateWorkbench("MaxProFrame")
        if previous and previous != "MaxProFrame":
            cls.addClassCleanup(Gui.activateWorkbench, previous)

    def test_each_command_has_its_shortcut(self):
        self.maxDiff = None
        self.assertEqual({name: shortcut(name) for name in SHORTCUTS}, SHORTCUTS)
        self.assertEqual({name: shortcut(name) for name in WITHOUT_SHORTCUT}, dict.fromkeys(WITHOUT_SHORTCUT, ""))

    def test_every_maxproframe_command_is_in_the_scheme(self):
        ours = sorted(name for name in Gui.listCommands() if name.startswith("MaxProFrame_"))
        self.assertEqual(ours, sorted([*SHORTCUTS, *WITHOUT_SHORTCUT]))

    def test_no_other_command_uses_a_shortcut_of_ours_or_m_alone(self):
        # M alone would run before any M, letter sequence could be typed.
        taken = {}
        for name in Gui.listCommands():
            text = shortcut(name)
            if text and not name.startswith("MaxProFrame_"):
                taken.setdefault(text, []).append(name)
        clashes = {text: taken[text] for text in [*SHORTCUTS.values(), "M"] if text in taken}
        self.assertEqual(clashes, {})


if __name__ == "__main__":
    unittest.main()

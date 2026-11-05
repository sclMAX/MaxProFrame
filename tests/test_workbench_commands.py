"""The MaxProFrame toolbars and menus use commands of other workbenches: they exist once it is active."""

import builtins
import unittest
from unittest.mock import patch

import FreeCADGui as Gui

from freecad.maxproframe.InitGui import MaxProFrame

TOOLBARS = (
    "toolbox_drawing",
    "toolbox_maxproframe",
    "toolbox_group",
    "toolbox_part",
    "toolbox_output",
    "toolbox_utilities",
)


class TestWorkbenchCommands(unittest.TestCase):
    def test_every_toolbar_command_exists_once_the_workbench_is_active(self):
        # Sketcher_NewSketch, Part_Fuse, Part_Cut and PartDesign_Body come from workbenches FreeCAD loads
        # on their first use: MaxProFrame loads them, so opened first it shows them with no unknown command.
        previous = Gui.activeWorkbench().name()
        self.addCleanup(Gui.activateWorkbench, previous)
        Gui.activateWorkbench("MaxProFrame")
        known = set(Gui.listCommands())
        wanted = [command for name in TOOLBARS for command in getattr(MaxProFrame, name)]
        self.assertEqual([command for command in wanted if command not in known], [])

    def test_the_workbench_loads_the_workbenches_its_toolbars_borrow_commands_from(self):
        # FreeCAD under test starts in PartDesign, which loaded them already: what the workbench imports shows
        # it does not rely on that.
        imported = []
        real_import = builtins.__import__

        def recording_import(name, *args, **kwargs):
            imported.append(name)
            return real_import(name, *args, **kwargs)

        workbench = MaxProFrame()
        with (
            patch.object(builtins, "__import__", recording_import),
            patch.object(MaxProFrame, "appendToolbar", create=True),
            patch.object(MaxProFrame, "appendMenu", create=True),
        ):
            workbench.Initialize()
        self.assertTrue({"PartGui", "SketcherGui", "PartDesignGui"} <= set(imported), imported)


if __name__ == "__main__":
    unittest.main()

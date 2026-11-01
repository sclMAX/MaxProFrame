"""Cutout / Hole command: name, tool tip and icon, shipped with the workbench."""

import os
import unittest

from freecad.maxproframe.create_extruded_cutout_tool import AddExtrudedCutoutCommandClass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = "freecad/maxproframe/resources/icons/cutout-hole.svg"


class TestCutoutCommandResources(unittest.TestCase):
    def setUp(self):
        self.resources = AddExtrudedCutoutCommandClass().GetResources()

    def test_the_command_is_named_cutout_hole_and_explains_the_guided_flow(self):
        self.assertEqual(self.resources["MenuText"], "Cutout / Hole")
        tool_tip = self.resources["ToolTip"]
        self.assertTrue(tool_tip.startswith("<b>Cutout / Hole</b>"))
        self.assertIn("Draw the hole and close the sketch to cut it.", tool_tip)
        self.assertIn("Or preselect one face and one sketch", tool_tip)

    def test_the_icon_is_the_tube_with_a_hole_and_is_installed(self):
        pixmap = self.resources["Pixmap"]
        self.assertEqual(os.path.basename(pixmap), "cutout-hole.svg")
        self.assertTrue(os.path.isfile(pixmap))
        with open(os.path.join(ROOT, "CMakeLists.txt"), encoding="utf-8") as handle:
            self.assertIn(ICON, handle.read().split())


if __name__ == "__main__":
    unittest.main()

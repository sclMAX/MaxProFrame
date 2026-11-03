"""Drill Hole command: icon shipped with the workbench and shown for each drill hole in the tree."""

import os
import unittest

from freecad.maxproframe.create_drill_hole_tool import DrillHoleCommand
from freecad.maxproframe.drill_hole import ViewProviderDrillHole

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = "freecad/maxproframe/resources/icons/drill-hole.svg"


class TestDrillHoleCommandResources(unittest.TestCase):
    def setUp(self):
        self.resources = DrillHoleCommand().GetResources()

    def test_the_icon_is_the_drill_on_a_tube_and_is_installed(self):
        pixmap = self.resources["Pixmap"]
        self.assertEqual(os.path.basename(pixmap), "drill-hole.svg")
        self.assertTrue(os.path.isfile(pixmap))
        with open(os.path.join(ROOT, "CMakeLists.txt"), encoding="utf-8") as handle:
            self.assertIn(ICON, handle.read().split())

    def test_the_tree_shows_drill_holes_with_the_command_icon(self):
        icon = ViewProviderDrillHole.__new__(ViewProviderDrillHole).getIcon()
        self.assertEqual(icon, self.resources["Pixmap"])


if __name__ == "__main__":
    unittest.main()

"""The MaxProFrame toolbars and menus use commands of other workbenches: they exist once it is active."""

import builtins
import unittest
from unittest.mock import patch

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from freecad.maxproframe.InitGui import MaxProFrame

TOOLBARS = (
    "toolbox_drawing",
    "toolbox_maxproframe",
    "toolbox_folded",
    "toolbox_group",
    "toolbox_part",
    "toolbox_output",
    "toolbox_utilities",
)

# Toolbar title -> its commands: every toolbar stays as it was before the single menu.
TOOLBAR_COMMANDS = {
    "Drawing Primitives": MaxProFrame.toolbox_drawing,
    "MaxProFrame": MaxProFrame.toolbox_maxproframe,
    "Folded Miters": MaxProFrame.toolbox_folded,
    "Profiles Group": MaxProFrame.toolbox_group,
    "Part Primitives": MaxProFrame.toolbox_part,
    "MaxProFrame Output": MaxProFrame.toolbox_output,
    "MaxProFrame Utilities": MaxProFrame.toolbox_utilities,
}

# One MaxProFrame menu: its submenus, in order, with the commands of their toolbars.
SUBMENUS = (
    ("Profiles and Cuts", MaxProFrame.toolbox_maxproframe),
    ("Folded Miters", MaxProFrame.toolbox_folded),
    ("Profiles Group", MaxProFrame.toolbox_group),
    ("Output", MaxProFrame.toolbox_output),
    ("Utilities", MaxProFrame.toolbox_utilities),
)


def _name(action):
    """The name FreeCAD keeps in the data() of a menu action: a command, or the untranslated title of a menu."""
    data = action.data()
    if data is None:
        return ""
    return data if isinstance(data, str) else bytes(data).decode()


def _submenus(widget):
    """Name -> QMenu of the menus a menu bar or menu holds, in its order. The menus are looked up as its children:
    a menu got through QAction.menu() is left deleted."""
    QtWidgets.QApplication.processEvents()
    children = {
        _name(menu.menuAction()): menu
        for menu in widget.findChildren(QtWidgets.QMenu, options=QtCore.Qt.FindDirectChildrenOnly)
    }
    return {_name(action): children[_name(action)] for action in widget.actions() if _name(action) in children}


def _menu_bar_menus():
    """Name -> QMenu of every top-level menu of the main window, in order."""
    return _submenus(Gui.getMainWindow().menuBar())


def _entries(menu):
    """Names of the entries of a menu, in order; separators are named Separator."""
    return ["Separator" if action.isSeparator() else _name(action) for action in menu.actions()]


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

    def _activate(self):
        previous = Gui.activeWorkbench().name()
        self.addCleanup(Gui.activateWorkbench, previous)
        Gui.activateWorkbench("MaxProFrame")

    def test_one_maxproframe_menu_holds_every_group_as_a_submenu(self):
        self._activate()
        menus = _menu_bar_menus()
        # The standard menus of every workbench are named with an accelerator (&File, &Edit, ...).
        own = [name for name in menus if not name.startswith("&")]
        self.assertEqual(own, ["MaxProFrame"])
        top = menus["MaxProFrame"]
        self.assertEqual(_entries(top), [name for name, _ in SUBMENUS])
        submenus = _submenus(top)
        self.assertEqual([(name, menu.title()) for name, menu in submenus.items()], [(n, n) for n, _ in SUBMENUS])
        for name, commands in SUBMENUS:
            with self.subTest(submenu=name):
                self.assertEqual(_entries(submenus[name]), list(commands))

    def test_the_old_menus_are_gone(self):
        self._activate()
        menus = _menu_bar_menus()
        for name in (
            "Drawing Primitives",
            "Part Primitives",
            "MaxProFrame Output",
            "MaxProFrame Utilities",
            "Folded Miters",
            "Profiles Group",
        ):
            with self.subTest(menu=name):
                self.assertNotIn(name, list(menus))

    def test_interlock_follows_extend_cut_in_profiles_and_cuts(self):
        # Tabs at a T joint need an Extend / Cut first, and they work on any tube, not only on a Folded Bar.
        self._activate()
        items = Gui.activeWorkbench().getToolbarItems()
        cuts = items["MaxProFrame"]
        self.assertEqual(cuts.index("MaxProFrame_Interlock"), cuts.index("MaxProFrame_ExtendCut") + 1)
        self.assertEqual(items["Folded Miters"], ["MaxProFrame_FoldedBar", "MaxProFrame_UnfoldBar"])

    def test_every_toolbar_stays_with_its_commands(self):
        self._activate()
        workbench = Gui.activeWorkbench()
        self.assertEqual(workbench.listToolbars()[-len(TOOLBAR_COMMANDS) :], list(TOOLBAR_COMMANDS))
        items = workbench.getToolbarItems()
        for title, commands in TOOLBAR_COMMANDS.items():
            with self.subTest(toolbar=title):
                self.assertEqual(items[title], list(commands))

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

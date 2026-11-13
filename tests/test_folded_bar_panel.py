"""Folded miter commands and the Folded Bar panel (odd/tasks/folded-miter.md, T6: S1 S2 S8 S9 S12; T9: S22) with the
corner list of odd/tasks/folded-corners.md, T4 (S1 S2 S3 S4 S5 S7 S9) and its corner overlay, T6 (S13).

Folded Bar folds the picked tubes, previewed live like End Miter; every reason the chain does not fold, and an own
miter at a folded corner, is shown and keeps OK disabled. The panel lists the corners of the bar in chain order; the
selected corners are drawn over the 3D view (the tubes selected while there is no preview) and their outer radius, clearance, key, key diameter and K-factor are
edited in the Corner fields (Fx with one corner selected). Remove takes off the end tube of the first or last corner
of an open bar and opens a closed frame at the selected corner. A new corner starts with the values last set, kept in
the MaxProFrame parameters. Double-click edits a bar in one Undo step. Unfold Bar makes the straight bar of a selected
Folded Bar. Create BOM and Populate IDs take a selected Folded Bar.
"""

import importlib.util
import os
import unittest
import xml.etree.ElementTree as ElementTree
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from pivy import coin
from PySide import QtCore, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest

from test_end_miter_geometry import polar
from test_expression_fields import assert_readable, use_dark_theme
from test_extend_cut_preview import keep_auto_preview, scene_graph
from test_folded_bar import FoldedBarFixture, corner_values
from test_folded_chain import RECTANGLE
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe import create_folded_bar_tool
from freecad.maxproframe._utils import is_foldedbar, is_unfoldedbar
from freecad.maxproframe.create_bom_tool import CreateBOMCommand, CreateBOMTaskPanel
from freecad.maxproframe.create_end_miter_tool import GAP_DELAY_MS, make_end_miter_profile
from freecad.maxproframe.create_folded_bar_tool import FoldedBarCommand, UnfoldBarCommand
from freecad.maxproframe.ff_tools import ICONPATH, get_param_group
from freecad.maxproframe.folded_bar import make_folded_bar
from freecad.maxproframe.InitGui import MaxProFrame
from freecad.maxproframe.populate_ids_tool import PopulateIDsCommand, PopulateIDsTaskPanel, QtGui, ResetIDsCommand
from freecad.maxproframe.unfolded_geometry import CornerSettings

AUTO_PREVIEW = SimpleNamespace(auto_preview_param="Folded Bar Auto Preview")
COMMANDS = ("MaxProFrame_FoldedBar", "MaxProFrame_UnfoldBar")
# folded-corners S5: the values last set, for the next corner.
CORNER_PARAMS = (
    ("Float", "Folded Corner Outer Radius"),
    ("Float", "Folded Corner Clearance"),
    ("Bool", "Folded Corner Key"),
    ("Float", "Folded Corner Key Diameter"),
    ("Float", "Folded Corner K-Factor"),
)
# The fields that take an expression (S9), and the corner property each one is bound to.
FX_FIELDS = (
    ("spin_outer_radius", "OuterRadius"),
    ("spin_clearance", "Clearance"),
    ("spin_key_diameter", "KeyDiameter"),
    ("spin_k_factor", "KFactor"),
)
NOT_A_CHAIN = "The selected profiles do not form one chain: Profile meets none of the others."
# 50 mm deep tube, 2 mm walls, 90 degree corners: 2 <= r <= 48 / (1 - cos 45) - 4 = 159.88, plus the wall for the
# outer radius, rounded down to 0.1 mm, with or without the key (S15, L40; folded-corners S6).
RADIUS_RANGE = "The outer radius of the corner between Profile and Profile001 must be between 4 and 161.8 mm."
# The tab of the default key (12.5 mm) stands out of its flank only with less clearance than half of it.
KEY_TOO_BIG = "The key does not fit in the notch between Profile and Profile001: make it smaller."
OWN_MITER = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it or make that corner the open one."
OWN_MITER_OPEN_CHAIN = "Profile_Mt cuts Profile at its folded corner with Profile001: delete it."
# S23: the right tube of the rectangle (200 mm, 250 on its outer wall) holds two bends of r = 120, not of r = 130.
TOO_SHORT = "Profile001 is too short for the radius of its corners."
TOO_FEW = "Select at least two profiles that meet end to end."
# The rows of the rectangle picked bottom, right, top, left with the first-ever values: open where it starts.
RECTANGLE_ROWS = [
    "1 · Profile → Profile001 · R 10 mm · key · clearance 0.5 mm",
    "2 · Profile001 → Profile002 · R 10 mm · key · clearance 0.5 mm",
    "3 · Profile002 → Profile003 · R 10 mm · key · clearance 0.5 mm",
    "Open · Profile003 → Profile",
]
# Four tubes of an open chain: the rectangle without the lower half of its left side.
OPEN_FOUR = RECTANGLE[:3] + (((0, 200, 0), (0, 100, 0)),)
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
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


def keep_selection_color(test, color):
    """Set FreeCAD's selection color (packed RGBA) for ``test``, as it was afterwards."""
    param = App.ParamGet(VIEW_PARAMS)
    stored = "SelectionColor" in param.GetUnsigneds()
    previous = param.GetUnsigned("SelectionColor")

    def restore():
        if stored:
            param.SetUnsigned("SelectionColor", previous)
        else:
            param.RemUnsigned("SelectionColor")

    test.addCleanup(restore)
    param.SetUnsigned("SelectionColor", color)


def _children(node, kind):
    return [node.getChild(index) for index in range(node.getNumChildren()) if node.getChild(index).isOfType(kind)]


def overlay_points(node):
    """The points of the faces of each corner drawn by the overlay ``node``, one list per corner."""
    found = []
    for group in _children(node, coin.SoSeparator.getClassTypeId()):
        (coordinates,) = _children(group, coin.SoCoordinate3.getClassTypeId())
        found.append([App.Vector(*coordinates.point[i].getValue()) for i in range(coordinates.point.getNum())])
    return found


def overlay_materials(node):
    """((r, g, b), transparency) of the faces of each corner drawn by the overlay ``node``."""
    found = []
    for group in _children(node, coin.SoSeparator.getClassTypeId()):
        (material,) = _children(group, coin.SoMaterial.getClassTypeId())
        color = tuple(round(value, 3) for value in material.diffuseColor[0].getValue())
        found.append((color, material.transparency[0]))
    return found


def stored_params():
    """The values the panel remembers for the next corner, None where none is stored."""
    param = get_param_group()
    return tuple(
        getattr(param, f"Get{kind}")(name) if name in getattr(param, f"Get{kind}s")() else None
        for kind, name in CORNER_PARAMS
    )


class PumpingDocument:
    """The panel's document, whose recompute pumps Qt events as FreeCAD's progress bar does (folded-corners S15, L23):
    ``during`` runs once, inside the first recompute, as keys typed and clicks made meanwhile; ``state.during`` is
    set for the whole recompute."""

    def __init__(self, doc, during, state):
        self._doc = doc
        self._during = during
        self._state = state

    def __getattr__(self, name):
        return getattr(self._doc, name)

    def recompute(self, *args):
        during, self._during = self._during, None
        if during is None:
            return self._doc.recompute(*args)
        self._state.during = True
        try:
            during()
            return self._doc.recompute(*args)
        finally:
            self._state.during = False


class FoldedPanelFixture(FoldedBarFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self, AUTO_PREVIEW)
        # Every test starts from the first-ever values of a corner.
        keep_params(self, CORNER_PARAMS)
        param = get_param_group(writable=True)
        for kind, name in CORNER_PARAMS:
            getattr(param, f"Rem{kind}")(name)
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

    def selected(self):
        return {s.ObjectName: s.SubElementNames for s in Gui.Selection.getSelectionEx()}

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

    def rows(self, panel):
        """The text of each row of the corner list."""
        widget = panel.form.corner_list
        return [widget.item(row).text() for row in range(widget.count())]

    def pick(self, panel, *rows):
        """Select ``rows`` of the corner list, as clicks with Ctrl held do."""
        widget = panel.form.corner_list
        widget.clearSelection()
        for row in rows:
            widget.item(row).setSelected(True)
        self.events()

    def fx_shown(self, spin):
        """Whether ``spin`` shows its Fx icon: FreeCAD's icon is a label inside the field's line edit."""
        return any(not label.isHidden() for label in spin.lineEdit().findChildren(QtWidgets.QLabel))

    def scene(self):
        """(scene graph of the 3D view, its number of children now): an overlay added later is the next child."""
        scene = scene_graph(self, self.doc)
        return scene, scene.getNumChildren()

    def overlay(self, scene, children):
        """The corner overlay drawn over the 3D view since ``children`` were counted, or None."""
        self.assertIn(scene.getNumChildren(), (children, children + 1))
        if scene.getNumChildren() == children:
            return None
        node = scene.getChild(children)
        # An annotation is drawn over the shapes: always visible.
        self.assertEqual("Annotation", node.getTypeId().getName())
        return node

    def assertAround(self, points, vertex, half=100.0):
        """``points`` span ``vertex`` and stay within ``half`` of it along every axis."""
        self.assertTrue(points)
        for axis in "xyz":
            values = [getattr(point, axis) for point in points]
            center = getattr(vertex, axis)
            self.assertLessEqual(min(values), center + 1e-6, axis)
            self.assertGreaterEqual(max(values), center - 1e-6, axis)
            self.assertLessEqual(max(abs(value - center) for value in values), half, axis)

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

    def three_corner_bar(self):
        """The rectangle folded with three different corners, open at its start."""
        settings = [
            CornerSettings(outer_radius=6.0, clearance=0.2, key=False, key_diameter=0.0, k_factor=0.4),
            CornerSettings(outer_radius=7.0, clearance=0.2, key=True, key_diameter=10.0, k_factor=0.0),
            CornerSettings(outer_radius=8.0, clearance=0.2, key=False, key_diameter=0.0, k_factor=0.45),
        ]
        profiles, bar = self.make_bar(corners=settings)
        return profiles, bar


class CommandTest(FoldedPanelFixture):
    def test_commands_are_registered_with_their_icons_and_on_a_workbench_toolbar(self):
        known = set(Gui.listCommands())
        self.assertEqual([], [name for name in COMMANDS if name not in known])
        self.assertEqual(list(COMMANDS), MaxProFrame.toolbox_folded)
        icons = {"MaxProFrame_FoldedBar": "FoldedBar.svg", "MaxProFrame_UnfoldBar": "UnfoldedBar.svg"}
        for name, icon in icons.items():
            with self.subTest(command=name):
                pixmap = Gui.Command.get(name).getInfo()["pixmap"]
                self.assertEqual(icon, os.path.basename(pixmap))
                self.assertEqual("{http://www.w3.org/2000/svg}svg", ElementTree.parse(pixmap).getroot().tag)

    def test_bend_configurations_are_gone(self):
        # folded-corners S7: thickness and material come from the profile; no command, dialog, store or icon.
        self.assertNotIn("MaxProFrame_BendConfigurations", Gui.listCommands())
        for module in ("bend_config", "bend_config_dialog"):
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(f"freecad.maxproframe.{module}"))
        self.assertFalse(os.path.exists(os.path.join(ICONPATH, "BendConfigurations.svg")))

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


class CornerListTest(FoldedPanelFixture):
    """folded-corners S1, S7: the corners in chain order, with their values; the tube read-only."""

    def test_the_list_shows_the_corners_in_chain_order_and_the_open_one(self):
        panel = self.run_command(*self.frame())

        form = panel.form
        self.assertEqual(RECTANGLE_ROWS, self.rows(panel))
        self.assertEqual(QtWidgets.QAbstractItemView.ExtendedSelection, form.corner_list.selectionMode())
        self.assertEqual([], form.corner_list.selectedItems())
        # The tube list, the radius rows, the open corner choice and the bend configurations are gone.
        for name in (
            "members_list",
            "groupBox_members",
            "groupBox_bend",
            "groupBox_notch",
            "combo_configuration",
            "button_manage",
            "spin_radius",
            "combo_open_corner",
            "label_corner_radii",
        ):
            with self.subTest(widget=name):
                self.assertFalse(hasattr(form, name))
        self.assertFalse(hasattr(panel, "corner_spins"))
        self.assertFalse(hasattr(panel, "configuration_names"))
        self.assertEqual("Corners", form.groupBox_corners.title())
        self.assertAccepts(panel)

    def test_the_values_of_each_corner_show_in_its_row(self):
        panel = self.run_command(*self.frame())
        self.pick(panel, 1)

        panel.form.spin_outer_radius.setValue(30.0)
        panel.form.spin_clearance.setValue(0.2)
        panel.form.cb_key.setChecked(False)

        rows = self.rows(panel)
        self.assertEqual("2 · Profile001 → Profile002 · R 30 mm · no key · clearance 0.2 mm", rows[1])
        self.assertEqual(RECTANGLE_ROWS[0], rows[0])
        self.assertEqual(RECTANGLE_ROWS[2:], rows[2:])

    def test_with_fewer_than_two_tubes_the_list_says_to_pick_the_next(self):
        bottom, right, _, _ = self.frame()
        panel = self.run_command()

        self.assertEqual(["Click the tube where the bar starts."], self.rows(panel))
        item = panel.form.corner_list.item(0)
        self.assertFalse(item.flags() & QtCore.Qt.ItemIsSelectable)
        Gui.Selection.addSelection(self.doc.Name, bottom.Name, "Face1")
        self.events()
        self.assertEqual(["Click the next tube, after Profile."], self.rows(panel))
        Gui.Selection.addSelection(self.doc.Name, right.Name, "Face1")
        self.events()
        self.assertEqual(["1 · Profile → Profile001 · R 10 mm · key · clearance 0.5 mm"], self.rows(panel))

    def test_tubes_that_do_not_form_a_chain_are_named(self):
        bottom, _, top, _ = self.frame()

        panel = self.run_command(bottom, top)

        self.assertEqual(["Tubes picked: Profile, Profile002"], self.rows(panel))
        self.assertRefused(panel, NOT_A_CHAIN)

    def test_the_panel_shows_the_material_and_wall_of_the_tubes_read_only(self):
        panel = self.run_command()
        form = panel.form
        self.assertEqual("", form.label_tube.text())
        self.assertIsInstance(form.label_tube, QtWidgets.QLabel)
        self.assertEqual("Tube", form.groupBox_corners.layout().labelForField(form.label_tube).text())
        self.close_dialog()

        panel = self.run_command(*self.frame(material="Aluminio", thickness=1.5))

        self.assertEqual("Aluminio · 1.5 mm", panel.form.label_tube.text())


class CornerSelectionTest(FoldedPanelFixture):
    """folded-corners S2, S3: the selected corners fill the fields and show in the 3D view."""

    def test_selecting_a_corner_fills_the_fields_and_editing_changes_that_corner_only(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        form = panel.form
        fields = (form.spin_outer_radius, form.spin_clearance, form.cb_key, form.spin_key_diameter, form.spin_k_factor)
        # Nothing selected: nothing to edit.
        self.assertFalse(any(field.isEnabled() for field in fields))

        self.pick(panel, 1)

        self.assertTrue(all(field.isEnabled() for field in fields))
        self.assertEqual(
            (7.0, 0.2, True, 10.0, 0.0),
            (
                form.spin_outer_radius.value(),
                form.spin_clearance.value(),
                form.cb_key.isChecked(),
                form.spin_key_diameter.value(),
                form.spin_k_factor.value(),
            ),
        )
        self.assertEqual("Automatic", form.spin_k_factor.text())
        self.pick(panel, 0)
        self.assertEqual((6.0, False), (form.spin_outer_radius.value(), form.cb_key.isChecked()))
        self.assertEqual("Default", form.spin_key_diameter.text())
        self.assertFalse(form.spin_key_diameter.isEnabled())
        self.assertAlmostEqual(0.4, form.spin_k_factor.value(), places=9)

        self.pick(panel, 1)
        form.spin_outer_radius.setValue(9.0)
        form.spin_k_factor.setValue(0.42)
        panel.update_preview()

        self.assertEqual(
            [(6.0, 0.2, False, 0.0, 0.4), (9.0, 0.2, True, 10.0, 0.42), (8.0, 0.2, False, 0.0, 0.45)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )
        self.assertEqual("2 · Profile001 → Profile002 · R 9 mm · key · clearance 0.2 mm", self.rows(panel)[1])
        self.assertOneSolid(bar)

    def test_a_selected_corner_is_drawn_over_the_preview_around_its_vertex(self):
        # folded-corners S13: the bend and a stretch of each tube, in the selection color, over the 3D view.
        keep_selection_color(self, 0x3366CC00)
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        (bar,) = self.bars()
        scene, children = self.scene()
        self.assertIsNone(self.overlay(scene, children))
        self.assertEqual({bar.Name: ()}, self.selected())

        # Corner 2: the right tube (x = 300) and the top one (y = 200), 50 mm tubes on their paths.
        self.pick(panel, 1)

        overlay = self.overlay(scene, children)
        self.assertIsNotNone(overlay)
        (points,) = overlay_points(overlay)
        self.assertAround(points, App.Vector(300, 200, 0))
        # The whole bend and a stretch of each tube past it.
        self.assertLessEqual(min(point.y for point in points), 140)
        self.assertLessEqual(min(point.x for point in points), 240)
        ((color, transparency),) = overlay_materials(overlay)
        self.assertEqual((0.2, 0.4, 0.8), color)
        self.assertTrue(0 < transparency < 1)
        # The overlay is no FreeCAD selection, and the tubes stay listed.
        self.assertEqual({}, self.selected())
        self.assertEqual([bottom, right, top, left], panel.selection)

        # Another corner replaces it.
        self.pick(panel, 0)
        (points,) = overlay_points(self.overlay(scene, children))
        self.assertAround(points, App.Vector(300, 0, 0))
        # No corner selected: no overlay, the listed tubes shown selected as the preview again.
        self.pick(panel)
        self.assertIsNone(self.overlay(scene, children))
        self.assertEqual({bar.Name: ()}, self.selected())
        self.assertEqual([bottom, right, top, left], panel.selection)

    def test_several_selected_corners_are_all_drawn(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        scene, children = self.scene()

        self.pick(panel, 0, 2)

        first, third = overlay_points(self.overlay(scene, children))
        self.assertAround(first, App.Vector(300, 0, 0))
        self.assertAround(third, App.Vector(0, 200, 0))
        self.assertEqual({}, self.selected())
        self.assertEqual([bottom, right, top, left], panel.selection)

    def test_the_open_corner_is_drawn_at_both_ends_of_the_bar(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        scene, children = self.scene()

        self.pick(panel, 3)

        (points,) = overlay_points(self.overlay(scene, children))
        self.assertAround(points, App.Vector(0, 0, 0))
        # The start of the bottom tube and the end of the left one, both cut at the open corner.
        self.assertTrue(any(point.x >= 50 and abs(point.y) <= 26 for point in points))
        self.assertTrue(any(point.y >= 50 and abs(point.x) <= 26 for point in points))

    def test_editing_draws_the_selected_corner_and_leaves_the_selection_empty(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        scene, children = self.scene()
        self.assertIsNone(self.overlay(scene, children))

        self.pick(panel, 2)

        (points,) = overlay_points(self.overlay(scene, children))
        self.assertAround(points, App.Vector(0, 200, 0))
        self.assertEqual({}, self.selected())
        self.pick(panel)
        self.assertIsNone(self.overlay(scene, children))

    def test_ok_cancel_and_closing_remove_the_corner_overlay(self):
        for close in ("accept", "reject", "closed", "closeDialog"):
            with self.subTest(close=close):
                for bar in self.bars():
                    self.doc.removeObject(bar.Name)
                panel = self.run_command(*self.frame())
                scene, children = self.scene()
                self.pick(panel, 1)
                self.assertIsNotNone(self.overlay(scene, children))

                if close == "closeDialog":
                    Gui.Control.closeDialog()
                else:
                    self.assertIsNot(False, getattr(panel, close)())
                self.events()

                self.assertIsNone(self.overlay(scene, children))
                self.close_dialog()

    def test_with_no_preview_a_selected_corner_highlights_the_tubes_themselves(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        self.assertEqual([], self.bars())
        scene, children = self.scene()

        self.pick(panel, 0)
        self.assertEqual({bottom.Name: (), right.Name: ()}, self.selected())
        self.pick(panel, 3)
        self.assertEqual({left.Name: (), bottom.Name: ()}, self.selected())
        self.assertEqual([bottom, right, top, left], panel.selection)
        # Nothing folded to draw: no overlay.
        self.assertIsNone(self.overlay(scene, children))

    def test_several_corners_show_their_common_values_and_mixed_ones(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        form = panel.form

        self.pick(panel, 0, 1, 2)

        self.assertEqual(0.2, form.spin_clearance.value())
        self.assertFalse(form.spin_clearance.property("mixedValues"))
        for name in ("spin_outer_radius", "spin_key_diameter", "spin_k_factor"):
            with self.subTest(field=name):
                self.assertTrue(getattr(form, name).property("mixedValues"))
        self.assertTrue(form.cb_key.property("mixedValues"))
        self.assertEqual("Interlocking key — Mixed values", form.cb_key.text())
        mixed = [label.text() for label in form.spin_outer_radius.findChildren(QtWidgets.QLabel)]
        self.assertIn("Mixed values", mixed)
        self.pick(panel, 0, 2)
        self.assertFalse(form.cb_key.property("mixedValues"))
        self.assertEqual("Interlocking key", form.cb_key.text())
        self.assertFalse(form.cb_key.isChecked())
        self.assertFalse(form.spin_key_diameter.property("mixedValues"))
        self.assertTrue(form.spin_k_factor.property("mixedValues"))

    def test_a_value_typed_applies_to_every_selected_corner(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        form = panel.form
        self.pick(panel, 0, 2)

        form.spin_outer_radius.setValue(9.0)
        form.cb_key.setChecked(True)
        panel.update_preview()

        self.assertFalse(form.spin_outer_radius.property("mixedValues"))
        self.assertEqual(
            [(9.0, 0.2, True, 0.0, 0.4), (7.0, 0.2, True, 10.0, 0.0), (9.0, 0.2, True, 0.0, 0.45)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )
        self.assertTrue(panel.accept())
        self.assertOneSolid(bar)

    def test_fx_is_offered_with_one_corner_selected_once_its_object_exists(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        panel = self.run_command(*self.frame())
        form = panel.form
        spins = [getattr(form, name) for name, _ in FX_FIELDS]
        self.pick(panel, 0)
        # No preview yet: no corner object to bind to.
        self.assertEqual([False] * 4, [self.fx_shown(spin) for spin in spins])

        panel.update_preview(force=True)

        self.assertEqual([True] * 4, [self.fx_shown(spin) for spin in spins])
        self.assertTrue(all(Gui.ExpressionBinding(spin).isBound() for spin in spins))
        self.pick(panel, 0, 1)
        self.assertEqual([False] * 4, [self.fx_shown(spin) for spin in spins])
        self.pick(panel)
        self.assertEqual([False] * 4, [self.fx_shown(spin) for spin in spins])
        self.pick(panel, 1)
        self.assertEqual([True] * 4, [self.fx_shown(spin) for spin in spins])


class RemoveTest(FoldedPanelFixture):
    """folded-corners S4: Remove takes off an end tube of an open bar, or opens a closed frame at the corner."""

    def test_an_open_bar_loses_the_end_tube_of_its_first_or_last_corner(self):
        first, second, third, fourth = self.frame(edges=OPEN_FOUR)
        panel = self.run_command(first, second, third, fourth)
        form = panel.form
        self.pick(panel, 1)
        form.spin_outer_radius.setValue(20.0)
        self.pick(panel)
        self.assertFalse(form.button_remove.isEnabled())
        # A middle corner cannot be removed, alone or with another.
        self.pick(panel, 1)
        self.assertFalse(form.button_remove.isEnabled())
        self.pick(panel, 0, 1)
        self.assertFalse(form.button_remove.isEnabled())

        self.pick(panel, 0)
        self.assertTrue(form.button_remove.isEnabled())
        form.button_remove.click()
        self.events()

        self.assertEqual([second, third, fourth], panel.selection)
        self.assertEqual(
            [
                "1 · Profile001 → Profile002 · R 20 mm · key · clearance 0.5 mm",
                "2 · Profile002 → Profile003 · R 10 mm · key · clearance 0.5 mm",
            ],
            self.rows(panel),
        )
        (bar,) = self.bars()
        self.assertEqual([second, third, fourth], list(bar.Segments))
        self.assertTrue(first.Visibility)
        self.assertOneSolid(bar)

        self.pick(panel, 1)
        form.button_remove.click()
        self.events()

        self.assertEqual([second, third], panel.selection)
        self.assertTrue(panel.accept())
        self.assertEqual([second, third], list(bar.Segments))
        self.assertEqual([(second, third)], [(corner.PieceA, corner.PieceB) for corner in bar.Corners])
        self.assertEqual(list(bar.Corners), self.corner_objects())
        self.assertTrue(first.Visibility and fourth.Visibility)
        self.assertOneSolid(bar)

    def test_a_closed_frame_opens_at_the_removed_corner(self):
        bottom, right, top, left = self.frame()
        undos = len(self.doc.UndoNames)
        panel = self.run_command(bottom, right, top, left)
        form = panel.form
        self.pick(panel, 3)
        # The open corner is open already.
        self.assertFalse(form.button_remove.isEnabled())
        self.pick(panel, 0, 1)
        self.assertFalse(form.button_remove.isEnabled())
        self.pick(panel, 0)
        form.spin_outer_radius.setValue(20.0)

        self.pick(panel, 1)
        form.button_remove.click()
        self.events()

        # The bar starts at the open corner: corner 1 is now the one after it, the old open corner folds with the
        # values last set (S5).
        self.assertEqual(
            [
                "1 · Profile002 → Profile003 · R 10 mm · key · clearance 0.5 mm",
                "2 · Profile003 → Profile · R 20 mm · key · clearance 0.5 mm",
                "3 · Profile → Profile001 · R 20 mm · key · clearance 0.5 mm",
                "Open · Profile001 → Profile002",
            ],
            self.rows(panel),
        )
        self.assertEqual([top, left, bottom, right], panel.selection)
        self.assertTrue(panel.accept())
        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([top, left, bottom, right], list(bar.Segments))
        # The corner object keeps its pieces in the order it was made with, now marked open.
        self.assertEqual([(right, top)], self.open_pairs(bar))
        self.assertEqual([10.0, 20.0, 20.0], [corner.OuterRadius.Value for corner in self.folded_corners(bar)])
        self.assertEqual(4, len(self.corner_objects()))
        self.assertEqual(undos + 1, len(self.doc.UndoNames))

    def test_editing_opens_the_frame_at_a_corner_of_its_first_tube(self):
        bottom, right, top, left = self.frame()
        bar = make_folded_bar([bottom, right, top, left], bend(**PLAIN))
        panel = self.edit(bar)
        self.assertEqual("Open · Profile003 → Profile", self.rows(panel)[3])

        self.pick(panel, 0)
        panel.form.button_remove.click()
        self.events()
        self.assertTrue(panel.accept())

        # The first tube stays first: the bar now runs from it the other way round.
        self.assertOneSolid(bar)
        self.assertEqual([(bottom, right)], self.open_pairs(bar))
        self.assertEqual(4, len(self.corner_objects()))
        self.assertEqual([bottom, left, top, right], list(bar.Segments))

    def test_cancel_with_undo_disabled_puts_back_the_tube_and_the_corner_removed_while_editing(self):
        self.doc.UndoMode = 0
        first, second, third = profiles = self.frame(edges=RECTANGLE[:3])
        bar = make_folded_bar(profiles, [bend(radius=4.0, **PLAIN), bend(radius=5.0, **PLAIN)])
        values = [((c.PieceA, c.PieceB), corner_values(c)) for c in bar.Corners]
        panel = self.edit(bar)
        self.pick(panel, 0)
        panel.form.button_remove.click()
        self.events()
        panel.update_preview()
        self.assertEqual([second, third], list(bar.Segments))
        self.assertEqual(1, len(self.corner_objects()))
        self.assertTrue(first.Visibility)

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(profiles, list(bar.Segments))
        self.assertEqual(values, [((c.PieceA, c.PieceB), corner_values(c)) for c in bar.Corners])
        self.assertEqual(sorted(c.Name for c in bar.Corners), sorted(c.Name for c in self.corner_objects()))
        self.assertOneSolid(bar)
        self.assertFalse(first.Visibility)


class CornerValuesTest(FoldedPanelFixture):
    """folded-corners S5: values per corner; a new corner starts with the values last set, remembered."""

    def test_the_corner_fields_and_the_first_ever_values(self):
        bottom, right, top, left = self.frame()
        undos = len(self.doc.UndoNames)
        panel = self.run_command(bottom, right, top, left)

        form = panel.form
        layout = form.groupBox_corner.layout()
        self.assertEqual("Corner", form.groupBox_corner.title())
        self.assertEqual(
            ["Outer radius", "Clearance", "Key diameter", "K-factor"],
            [
                layout.labelForField(getattr(form, name)).text()
                for name in ("spin_outer_radius", "spin_clearance", "spin_key_diameter", "spin_k_factor")
            ],
        )
        self.assertEqual("Interlocking key", form.cb_key.text())
        self.assertEqual("Default", form.spin_key_diameter.specialValueText())
        self.assertEqual("Automatic", form.spin_k_factor.specialValueText())
        # Nothing selected: the fields show what a new corner gets.
        self.assertEqual(
            (10.0, 0.5, True, 0.0, 0.0),
            (
                form.spin_outer_radius.value(),
                form.spin_clearance.value(),
                form.cb_key.isChecked(),
                form.spin_key_diameter.value(),
                form.spin_k_factor.value(),
            ),
        )
        self.assertTrue(form.cb_auto_update.isChecked())
        self.assertTrue(panel.accept())
        self.close_dialog()

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([(10.0, 0.5, True, 0.0, 0.0)] * 4, [corner_values(corner) for corner in bar.Corners])
        for name in ("InsideRadius", "CornerRadii", "Clearance", "Key", "OpenCorner", "BendConfiguration"):
            self.assertNotIn(name, bar.PropertiesList)
        self.assertEqual([bottom, right, top, left], list(bar.Segments))
        self.assertEqual([(bottom, left)], self.open_pairs(bar))
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Create Folded Bar", self.doc.UndoNames[0])

    def test_a_new_corner_starts_with_the_values_last_set_and_ok_remembers_them(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right)
        form = panel.form
        self.pick(panel, 0)
        form.spin_outer_radius.setValue(30.0)
        form.spin_clearance.setValue(0.2)
        form.cb_key.setChecked(False)
        form.spin_k_factor.setValue(0.45)

        Gui.Selection.addSelection(self.doc.Name, top.Name, "Face1")
        self.events()

        self.assertEqual(
            [
                "1 · Profile → Profile001 · R 30 mm · no key · clearance 0.2 mm",
                "2 · Profile001 → Profile002 · R 30 mm · no key · clearance 0.2 mm",
            ],
            self.rows(panel),
        )
        self.pick(panel, 1)
        form.spin_outer_radius.setValue(25.0)
        self.assertEqual((None,) * 5, stored_params())
        self.assertTrue(panel.accept())
        self.close_dialog()
        (bar,) = self.bars()
        self.assertEqual(
            [(30.0, 0.2, False, 0.0, 0.45), (25.0, 0.2, False, 0.0, 0.45)],
            [corner_values(corner) for corner in bar.Corners],
        )
        self.assertEqual((25.0, 0.2, False, 0.0, 0.45), stored_params())

        # The next bar starts with them.
        others = self.frame()
        panel = self.run_command(*others[:3])
        self.assertEqual(
            [
                "1 · Profile004 → Profile005 · R 25 mm · no key · clearance 0.2 mm",
                "2 · Profile005 → Profile006 · R 25 mm · no key · clearance 0.2 mm",
            ],
            self.rows(panel),
        )

    def test_cancel_remembers_nothing(self):
        panel = self.run_command(*self.frame())
        self.pick(panel, 0)
        panel.form.spin_outer_radius.setValue(30.0)

        self.assertTrue(panel.reject())

        self.assertEqual((None,) * 5, stored_params())


class CreatePanelTest(FoldedPanelFixture):
    def test_preview_shows_the_bar_before_ok_and_hides_the_tips(self):
        profiles = self.frame()

        panel = self.run_command(*profiles)

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertTrue(all(not tip.Visibility for tip in profiles))
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def test_ok_creates_one_folded_bar_with_the_values_of_each_corner(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top, left)
        form = panel.form
        self.pick(panel, 0, 1, 2)
        form.spin_outer_radius.setValue(6.0)
        form.spin_clearance.setValue(0.2)
        form.cb_key.setChecked(False)
        self.pick(panel, 1)
        form.spin_outer_radius.setValue(7.0)
        form.spin_key_diameter.setValue(0.0)

        self.assertTrue(panel.accept())
        self.close_dialog()

        (bar,) = self.bars()
        self.assertOneSolid(bar)
        # The open corner has the sizes of the first one.
        self.assertEqual(
            [(6.0, 0.2, False, 0.0, 0.0), (7.0, 0.2, False, 0.0, 0.0), (6.0, 0.2, False, 0.0, 0.0)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )
        self.assertEqual([(6.0, 0.2, False, 0.0, 0.0)], [corner_values(c) for c in bar.Corners if c.Open])
        self.assertEqual((7.0, 0.2, False, 0.0, 0.0), stored_params())

    def test_with_update_automatically_unchecked_ok_creates_the_bar(self):
        keep_auto_preview(self, AUTO_PREVIEW, False)
        profiles = self.frame()
        before = self.names()
        panel = self.run_command(*profiles)
        self.assertEqual(before, self.names())
        self.assertEqual("Pending changes", panel.form.status_label.text())

        self.assertTrue(panel.accept())

        (bar,) = self.bars()
        self.assertOneSolid(bar)

    def test_cancel_leaves_the_document_unchanged(self):
        profiles = self.frame()
        before, undos = self.names(), len(self.doc.UndoNames)
        panel = self.run_command(*profiles)
        self.pick(panel, 0)
        panel.form.spin_outer_radius.setValue(8.0)
        panel.update_preview()
        self.assertEqual(1, len(self.bars()))

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(before, self.names())
        self.assertTrue(all(tip.Visibility for tip in profiles))
        self.assertEqual(undos, len(self.doc.UndoNames))

    def test_cancel_with_undo_disabled_still_leaves_nothing(self):
        self.doc.UndoMode = 0
        profiles = self.frame()
        before = self.names()
        panel = self.run_command(*profiles)

        self.assertTrue(panel.reject())

        self.assertEqual(before, self.names())
        self.assertTrue(all(tip.Visibility for tip in profiles))

    def test_refused_selection_shows_the_chain_message_and_disables_ok(self):
        bottom, right, top, left = self.frame()

        panel = self.run_command(bottom, top)

        self.assertRefused(panel, NOT_A_CHAIN)
        self.assertEqual([], self.bars())

    def test_radius_out_of_its_limits_shows_them_and_disables_ok(self):
        panel = self.run_command(*self.frame())
        form = panel.form
        self.pick(panel, 0, 1, 2)
        form.spin_clearance.setValue(0.0)

        form.spin_outer_radius.setValue(3.0)

        self.assertRefused(panel, RADIUS_RANGE)
        form.spin_outer_radius.setValue(162.0)
        self.assertRefused(panel, RADIUS_RANGE)
        # Past the old limit (35.5 mm with the key) the key fits below the bend axis point; with 6.5 mm of clearance
        # it does not fit.
        form.spin_outer_radius.setValue(48.0)
        self.assertAccepts(panel)
        form.spin_clearance.setValue(6.5)
        self.assertRefused(panel, KEY_TOO_BIG)
        form.cb_key.setChecked(False)
        self.assertAccepts(panel)

    def test_tube_too_short_for_its_corners_is_named_and_disables_ok(self):
        panel = self.run_command(*self.frame())
        self.pick(panel, 0, 1, 2)
        panel.form.cb_key.setChecked(False)

        panel.form.spin_outer_radius.setValue(132.0)

        self.assertRefused(panel, TOO_SHORT)
        panel.form.spin_outer_radius.setValue(122.0)
        self.assertAccepts(panel)

    def test_a_wide_corner_folds_with_the_relief(self):
        # The relief is always on (L36): a 135 degree corner folds.
        panel = self.run_command(*self.wide_chain())

        self.assertEqual(2, len(self.rows(panel)))
        self.assertAccepts(panel)

    def test_own_miter_at_a_folded_corner_is_reported_until_that_corner_opens(self):
        bottom, right, top, left = self.frame()
        miter = self.miter(bottom, right)

        panel = self.run_command(miter, right, top, left)

        self.assertRefused(panel, OWN_MITER)
        self.pick(panel, 0)
        panel.form.button_remove.click()
        self.events()
        self.assertAccepts(panel)
        self.assertTrue(panel.accept())
        (bar,) = self.bars()
        self.assertOneSolid(bar)
        # The corner objects name the profiles: the miter keeps the corner of its profile.
        self.assertEqual([(bottom, right)], self.open_pairs(bar))

    def test_own_miter_at_a_folded_corner_of_an_open_chain_is_reported(self):
        first, second, third = self.wide_chain()
        miter = self.miter(first, second)

        panel = self.run_command(miter, second, third)

        self.assertRefused(panel, OWN_MITER_OPEN_CHAIN)

    def test_end_miters_at_the_open_corner_are_no_conflict(self):
        bottom, right, top, left = self.frame()
        bottom_miter = self.miter(bottom, left)
        left_miter = self.miter(left, bottom)

        panel = self.run_command(bottom_miter, right, top, left_miter)

        self.assertAccepts(panel)


class PickAsYouGoTest(FoldedPanelFixture):
    """S22: the pieces clicked while the panel is open join the bar, as in Create Miter Ends."""

    def click(self, obj, sub="Face1", point=None, ctrl=False):
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=modifiers):
            if point is None:
                Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
            else:
                Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, *point)
            self.events()

    def test_with_nothing_selected_the_panel_opens_and_says_why_ok_is_disabled(self):
        panel = self.run_command()

        self.assertEqual([], panel.selection)
        self.assertRefused(panel, TOO_FEW)
        self.assertEqual("No preview", panel.form.status_label.text())
        self.assertEqual([], self.bars())

    def test_clicked_profiles_join_the_list_in_order_and_the_chain_and_preview_follow(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command()
        form = panel.form

        self.click(bottom, "Face3")
        self.assertEqual([bottom], panel.selection)
        self.assertRefused(panel, TOO_FEW)
        self.assertEqual([], self.bars())

        self.click(right)
        self.assertEqual([bottom, right], panel.selection)
        self.assertEqual(RECTANGLE_ROWS[:1], self.rows(panel))
        self.assertAccepts(panel)
        (bar,) = self.bars()
        self.assertOneSolid(bar)
        self.assertEqual([bottom, right], list(bar.Segments))
        self.assertFalse(bottom.Visibility or right.Visibility)
        self.assertEqual("Preview updated", form.status_label.text())
        # The listed pieces show selected: here as the preview that hides them.
        self.assertEqual({bar.Name: ()}, self.selected())

        self.click(top)
        self.click(left, "Edge2")
        self.assertEqual([bottom, right, top, left], panel.selection)
        self.assertEqual(RECTANGLE_ROWS, self.rows(panel))
        self.assertAccepts(panel)
        self.assertEqual([bar], self.bars())
        self.assertEqual([bottom, right, top, left], list(bar.Segments))
        self.assertEqual([(bottom, left)], self.open_pairs(bar))
        self.assertEqual(4, len(bar.Corners))
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
        self.assertEqual(["Tubes picked: Profile, Profile002"], self.rows(panel))
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
        self.assertEqual(RECTANGLE_ROWS[:1], self.rows(panel))
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
        # The corners of the left tube left with it.
        self.assertEqual([], self.open_pairs(bar))
        self.assertEqual([(bottom, right), (right, top)], [(c.PieceA, c.PieceB) for c in bar.Corners])
        self.assertEqual(list(bar.Corners), self.corner_objects())
        self.assertEqual(RECTANGLE_ROWS[:2], self.rows(panel))
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
        self.assertEqual([], self.corner_objects())
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
                self.assertEqual(["Click the next tube, after Profile."], self.rows(panel))

    def test_a_piece_made_from_a_listed_profile_takes_its_place(self):
        bottom, right, top, left = self.frame()
        panel = self.run_command(bottom, right, top)
        miter = self.miter(bottom, left)
        self.events()

        self.click(miter)
        self.click(bottom)

        self.assertEqual([miter, right, top], panel.selection)

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
        self.assertEqual(4, panel.form.corner_list.count())
        self.pick(panel, 0, 1, 2)
        panel.form.spin_clearance.setValue(0.3)
        self.assertTrue(panel.accept())
        self.assertEqual(profiles, list(bar.Segments))
        self.assertEqual([0.3] * 3, [round(corner.Clearance.Value, 9) for corner in self.folded_corners(bar)])


class EditPanelTest(FoldedPanelFixture):
    def clearances(self, bar):
        return [round(corner.Clearance.Value, 9) for corner in bar.Corners]

    def test_double_click_edits_the_bar_in_one_undo_step(self):
        _, bar = self.make_bar(corners=[bend(radius=4.0), bend(radius=4.0), bend(radius=5.0)])
        undos = len(self.doc.UndoNames)

        panel = self.edit(bar)

        self.assertEqual(
            [
                "1 · Profile → Profile001 · R 6 mm · key · clearance 0 mm",
                "2 · Profile001 → Profile002 · R 6 mm · key · clearance 0 mm",
                "3 · Profile002 → Profile003 · R 7 mm · key · clearance 0 mm",
                "Open · Profile003 → Profile",
            ],
            self.rows(panel),
        )
        self.pick(panel, 0, 1, 2)
        panel.form.spin_clearance.setValue(0.3)
        panel.form.cb_key.setChecked(False)
        self.assertTrue(panel.accept())
        self.close_dialog()

        self.assertEqual(1, len(self.bars()))
        self.assertEqual(
            [(6.0, 0.3, False, 0.0, 0.4), (6.0, 0.3, False, 0.0, 0.4), (7.0, 0.3, False, 0.0, 0.4)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )
        self.assertOneSolid(bar)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Folded Bar", self.doc.UndoNames[0])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(
            [(6.0, 0.0, True, 0.0, 0.4), (6.0, 0.0, True, 0.0, 0.4), (7.0, 0.0, True, 0.0, 0.4)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )

    def test_ok_without_changes_adds_no_undo_step(self):
        profiles, bar = self.make_bar(**PLAIN)
        values = [corner_values(corner) for corner in bar.Corners]
        undos = len(self.doc.UndoNames)
        panel = self.edit(bar)
        self.pick(panel, 1)

        self.assertTrue(panel.accept())

        self.assertEqual(undos, len(self.doc.UndoNames))
        self.assertEqual([(profiles[0], profiles[3])], self.open_pairs(bar))
        self.assertEqual(values, [corner_values(corner) for corner in bar.Corners])

    def test_cancel_puts_the_edited_bar_back(self):
        _, bar = self.make_bar(**PLAIN)
        volume = bar.Shape.Volume
        panel = self.edit(bar)
        self.pick(panel, 0, 1, 2)
        panel.form.spin_clearance.setValue(0.3)
        panel.update_preview()
        self.assertEqual([0.3] * 3, self.clearances(bar)[:3])

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()

        self.assertEqual([0.0] * 4, self.clearances(bar))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=1e-3)

    def test_cancel_with_undo_disabled_puts_the_corners_back_and_removes_the_new_ones(self):
        self.doc.UndoMode = 0
        _, bar = self.make_bar(**PLAIN)
        missing = self.folded_corners(bar)[1]
        self.doc.removeObject(missing.Name)
        self.doc.recompute()
        self.assertIn("Invalid", bar.State)
        names = [corner.Name for corner in bar.Corners]
        panel = self.edit(bar)
        # The corner without object gets the values last set.
        self.assertEqual("2 · Profile001 → Profile002 · R 10 mm · key · clearance 0.5 mm", self.rows(panel)[1])
        self.pick(panel, 0, 1, 2)
        panel.form.spin_clearance.setValue(0.3)
        panel.update_preview()
        self.assertOneSolid(bar)
        self.assertEqual(4, len(bar.Corners))
        self.assertEqual([0.3] * 3, self.clearances(bar)[:3])

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(names, [corner.Name for corner in bar.Corners])
        self.assertEqual(sorted(names), sorted(corner.Name for corner in self.corner_objects()))
        self.assertEqual([0.0] * 3, self.clearances(bar))
        self.assertIn("Invalid", bar.State)


class ExpressionTest(FoldedPanelFixture):
    """folded-corners S9: the fields of one corner take expressions, bound to its Folded Corner object."""

    def test_the_fields_are_bound_to_the_selected_corner(self):
        panel = self.run_command(*self.frame())
        (bar,) = self.bars()
        corner = self.folded_corners(bar)[1]
        form = panel.form
        self.pick(panel, 1)

        corner.setExpression("OuterRadius", "2 * 6 mm")
        corner.setExpression("KFactor", "0.45")
        self.doc.recompute()
        self.events()

        self.assertTrue(Gui.ExpressionBinding(form.spin_outer_radius).hasExpression())
        self.assertTrue(Gui.ExpressionBinding(form.spin_k_factor).hasExpression())
        self.assertFalse(Gui.ExpressionBinding(form.spin_clearance).hasExpression())
        self.assertEqual(12.0, form.spin_outer_radius.value())
        self.assertEqual("2 · Profile001 → Profile002 · R 12 mm · key · clearance 0.5 mm", self.rows(panel)[1])
        # The other corners have no expression.
        self.pick(panel, 0)
        self.assertFalse(Gui.ExpressionBinding(form.spin_outer_radius).hasExpression())
        self.assertEqual(10.0, form.spin_outer_radius.value())

    def test_ok_keeps_an_expression_in_the_one_undo_step(self):
        undos = len(self.doc.UndoNames)
        panel = self.run_command(*self.frame())
        (bar,) = self.bars()
        corner = self.folded_corners(bar)[1]
        self.pick(panel, 1)
        corner.setExpression("OuterRadius", "2 * 6 mm")
        self.doc.recompute()
        self.events()
        self.pick(panel, 0)
        panel.form.spin_clearance.setValue(0.3)

        self.assertTrue(panel.accept())

        self.assertEqual({"OuterRadius": "2 * 6 mm"}, dict(corner.ExpressionEngine))
        self.assertEqual([10.0, 12.0, 10.0], [c.OuterRadius.Value for c in self.folded_corners(bar)])
        self.assertEqual([0.3, 0.5, 0.5], [round(c.Clearance.Value, 9) for c in self.folded_corners(bar)])
        self.assertOneSolid(bar)
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.doc.undo()
        self.assertEqual([], self.bars())

    def test_ok_with_only_an_expression_set_while_editing_keeps_it_in_one_undo_step(self):
        _, bar = self.make_bar(**PLAIN)
        undos = len(self.doc.UndoNames)
        panel = self.edit(bar)
        corner = self.folded_corners(bar)[0]
        self.pick(panel, 0)

        corner.setExpression("Clearance", "0.4 mm")
        self.doc.recompute()
        self.events()
        self.assertTrue(panel.accept())

        self.assertEqual({"Clearance": "0.4 mm"}, dict(corner.ExpressionEngine))
        self.assertEqual(undos + 1, len(self.doc.UndoNames))
        self.assertEqual("Edit Folded Bar", self.doc.UndoNames[0])
        self.doc.undo()
        self.assertEqual({}, dict(corner.ExpressionEngine))

    def test_cancel_with_undo_off_removes_an_expression_set_while_editing(self):
        _, bar = self.make_bar(**PLAIN)
        values = [corner_values(c) for c in bar.Corners]
        panel = self.edit(bar)
        self.doc.UndoMode = 0
        corner = self.folded_corners(bar)[0]
        self.pick(panel, 0)
        corner.setExpression("OuterRadius", "2 * 6 mm")
        self.doc.recompute()
        self.events()
        self.assertEqual(12.0, corner.OuterRadius.Value)

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual({}, dict(corner.ExpressionEngine))
        self.assertEqual(values, [corner_values(c) for c in bar.Corners])
        self.assertOneSolid(bar)

    def test_cancel_of_a_new_bar_with_an_expression_leaves_the_document_unchanged(self):
        profiles = self.frame()
        before = self.names()
        panel = self.run_command(*profiles)
        (bar,) = self.bars()
        self.pick(panel, 0)
        self.folded_corners(bar)[0].setExpression("OuterRadius", "2 * 6 mm")
        self.doc.recompute()

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(before, self.names())
        self.assertTrue(all(tip.Visibility for tip in profiles))


class NoFreezeTest(FoldedPanelFixture):
    """folded-corners S15: no geometry while the preview recomputes; a typed value applies once the field is done."""

    def watch_geometry(self, state):
        """For every check of the corners and every corner drawn over the 3D view, whether it ran during the
        recompute: an OCC boolean run there waits forever for the threads of the recompute's own (L23)."""
        calls = []
        for name in ("check_settings", "corner_box"):
            real = getattr(create_folded_bar_tool, name)

            def watched(*args, real=real, name=name, **kwargs):
                calls.append((name, state.during))
                return real(*args, **kwargs)

            patcher = patch.object(create_folded_bar_tool, name, watched)
            patcher.start()
            self.addCleanup(patcher.stop)
        return calls

    def recompute_with(self, panel, during):
        """Preview ``panel`` now, ``during`` running inside its recompute; (geometry run during it, all of it)."""
        state = SimpleNamespace(during=False)
        calls = self.watch_geometry(state)
        with patch.object(panel, "doc", PumpingDocument(self.doc, during, state)):
            panel.update_preview()
        return [name for name, during in calls if during], calls

    def wait_for_preview(self, panel):
        """Let the preview delay pass until the panel says the preview is up to date."""
        for _ in range(40):
            self.events()
            if panel.form.status_label.text() == "Preview updated":
                return
            QtTest.QTest.qWait(GAP_DELAY_MS // 2)
        self.assertEqual("Preview updated", panel.form.status_label.text())

    def show(self, panel):
        """Show the panel in an active window, as FreeCAD does, to type in its fields."""
        Gui.Control.showTaskView()
        window = panel.form.window()
        window.show()
        window.activateWindow()
        for _ in range(200):
            if panel.form.spin_clearance.isVisible():
                break
            self.events()
            QtCore.QThread.msleep(10)
        self.assertTrue(panel.form.spin_clearance.isVisible())
        # No field keeps the focus while the dialog closes (cleanups run in reverse order).
        self.addCleanup(self.leave_fields)

    def leave_fields(self):
        focused = QtWidgets.QApplication.focusWidget()
        if focused is not None:
            focused.clearFocus()
        self.events()

    def type_in(self, spin, text):
        """Type ``text`` over the value of ``spin``, as keys, without completing the field."""
        spin.setFocus()
        spin.selectAll()
        QtTest.QTest.keyClicks(spin, text)
        self.events()

    def test_changes_made_during_the_recompute_wait_for_it_and_then_apply(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        form = panel.form
        scene, children = self.scene()
        self.pick(panel, 1)
        form.spin_outer_radius.setValue(9.0)

        def keys_and_clicks():
            # Corner 2: a clearance typed and its key turned off; then corner 1 selected.
            form.spin_clearance.setValue(0.3)
            form.cb_key.click()
            self.pick(panel, 0)

        during, calls = self.recompute_with(panel, keys_and_clicks)

        self.assertEqual([], during)
        self.assertIn("check_settings", [name for name, _ in calls])
        self.wait_for_preview(panel)
        self.assertEqual(
            [(6.0, 0.2, False, 0.0, 0.4), (9.0, 0.3, False, 10.0, 0.0), (8.0, 0.2, False, 0.0, 0.45)],
            [corner_values(corner) for corner in self.folded_corners(bar)],
        )
        self.assertEqual("2 · Profile001 → Profile002 · R 9 mm · no key · clearance 0.3 mm", self.rows(panel)[1])
        self.assertEqual("", self.messages(panel))
        # Corner 1 selected: its values in the fields, drawn over the 3D view.
        self.assertEqual(
            (6.0, 0.2, False), (form.spin_outer_radius.value(), form.spin_clearance.value(), form.cb_key.isChecked())
        )
        (points,) = overlay_points(self.overlay(scene, children))
        self.assertAround(points, App.Vector(300, 0, 0))
        self.assertOneSolid(bar)

    def test_remove_clicked_during_the_recompute_opens_the_frame_once_it_returns(self):
        (_, right, top, _), bar = self.three_corner_bar()
        panel = self.edit(bar)
        self.pick(panel, 1)
        panel.form.spin_outer_radius.setValue(9.0)

        during, _ = self.recompute_with(panel, panel.form.button_remove.click)

        self.assertEqual([], during)
        self.events()
        self.assertEqual("Open · Profile001 → Profile002", self.rows(panel)[3])
        self.assertEqual("Preview updated", panel.form.status_label.text())
        self.assertEqual([{right.Name, top.Name}], [{a.Name, b.Name} for a, b in self.open_pairs(bar)])
        self.assertOneSolid(bar)

    def test_a_preview_due_during_the_recompute_runs_once_it_returns(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        form = panel.form
        self.pick(panel, 1)
        # The preview delay starts.
        form.spin_outer_radius.setValue(9.0)

        def long_recompute():
            # A value typed, and the preview delay over before the recompute ends.
            form.spin_clearance.setValue(0.3)
            QtTest.QTest.qWait(GAP_DELAY_MS * 2)

        self.recompute_with(panel, long_recompute)
        self.events()

        # Not dropped: the preview ran right after the recompute, with the value typed.
        self.assertEqual("Preview updated", form.status_label.text())
        self.assertEqual((9.0, 0.3, True, 10.0, 0.0), corner_values(self.folded_corners(bar)[1]))

    def test_ok_pressed_during_the_recompute_waits_for_it_and_keeps_the_value_typed(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        self.pick(panel, 1)
        panel.form.spin_outer_radius.setValue(9.0)
        pressed = []

        def type_and_ok():
            panel.form.spin_clearance.setValue(0.3)
            pressed.append(panel.accept())

        self.recompute_with(panel, type_and_ok)
        self.events()

        self.assertEqual([False], pressed)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual((9.0, 0.3, True, 10.0, 0.0), corner_values(self.folded_corners(bar)[1]))
        self.assertOneSolid(bar)

    def test_a_value_typed_applies_when_the_field_is_done(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        self.show(panel)
        spin = panel.form.spin_clearance
        point = spin.locale().decimalPoint()
        self.pick(panel, 1)
        row = "2 · Profile001 → Profile002 · R 7 mm · key · clearance 0.2 mm"
        self.assertEqual(row, self.rows(panel)[1])

        self.type_in(spin, "0" + point + "5")
        QtTest.QTest.qWait(GAP_DELAY_MS * 2)
        self.events()

        # Nothing yet: neither the row nor the corner.
        self.assertEqual(row, self.rows(panel)[1])
        self.assertEqual(0.2, corner_values(self.folded_corners(bar)[1])[1])
        self.assertEqual("Preview updated", panel.form.status_label.text())
        # Leaving the field completes it.
        panel.form.spin_outer_radius.setFocus()
        self.events()
        self.assertEqual("2 · Profile001 → Profile002 · R 7 mm · key · clearance 0.5 mm", self.rows(panel)[1])
        self.wait_for_preview(panel)
        self.assertEqual(0.5, corner_values(self.folded_corners(bar)[1])[1])

        # Enter completes it too, and FreeCAD's task view takes it as OK: the bar keeps the value.
        self.type_in(spin, "0" + point + "4")
        self.assertEqual(0.5, corner_values(self.folded_corners(bar)[1])[1])
        QtTest.QTest.keyClick(spin, QtCore.Qt.Key_Return)
        self.events()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(0.4, corner_values(self.folded_corners(bar)[1])[1])
        self.assertOneSolid(bar)

    def test_an_arrow_key_applies_at_once(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        self.show(panel)
        spin = panel.form.spin_clearance
        self.pick(panel, 1)
        spin.setFocus()

        QtTest.QTest.keyClick(spin, QtCore.Qt.Key_Up)
        self.events()

        self.assertEqual("2 · Profile001 → Profile002 · R 7 mm · key · clearance 1.2 mm", self.rows(panel)[1])
        self.wait_for_preview(panel)
        self.assertEqual(1.2, corner_values(self.folded_corners(bar)[1])[1])

    def test_the_value_under_mixed_values_typed_again_goes_to_every_selected_corner(self):
        # The outer radii are 6, 7 and 8 mm: corners 1 and 3 show Mixed values over 6 mm.
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        self.show(panel)
        spin = panel.form.spin_outer_radius
        self.pick(panel, 0, 2)
        self.assertTrue(spin.property("mixedValues"))

        self.type_in(spin, "6")
        panel.form.spin_clearance.setFocus()
        self.wait_for_preview(panel)

        self.assertFalse(spin.property("mixedValues"))
        self.assertEqual([6.0, 7.0, 6.0], [corner_values(corner)[0] for corner in self.folded_corners(bar)])


class DarkThemeTest(FoldedPanelFixture):
    """folded-corners S14 and S3 in FreeCAD's dark theme: the values of one corner read, a mixed value is hidden."""

    def setUp(self):
        super().setUp()
        use_dark_theme(self)

    def picture(self, widget):
        """What ``widget`` paints, with its children."""
        image = QtGui.QImage(widget.size(), QtGui.QImage.Format_ARGB32)
        image.fill(0)
        widget.render(image)
        return image

    def test_one_selected_corner_shows_its_values_readable(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)

        self.pick(panel, 2)

        for name, _ in FX_FIELDS:
            spin = getattr(panel.form, name)
            with self.subTest(field=name):
                self.assertTrue(self.fx_shown(spin))
                assert_readable(self, spin)

    def test_a_mixed_field_shows_mixed_values_and_not_the_value_under_it(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)
        spin = panel.form.spin_outer_radius
        # The panel laid out in an active window, as FreeCAD shows it; the task view may show it a moment later.
        Gui.Control.showTaskView()
        window = spin.window()
        window.show()
        window.activateWindow()
        for _ in range(200):
            if spin.isVisible():
                break
            self.events()
            QtCore.QThread.msleep(10)
        self.assertTrue(spin.isVisible())

        # The outer radii are 6, 7 and 8 mm: the field holds the value of the first corner selected.
        self.pick(panel, 0, 1)
        self.assertTrue(spin.property("mixedValues"))
        self.assertEqual(6.0, spin.value())
        six = self.picture(spin)
        self.pick(panel, 1, 2)
        self.assertTrue(spin.property("mixedValues"))
        self.assertEqual(7.0, spin.value())

        # Whatever the value under it, a mixed field paints the same: only Mixed values, light on the dark field.
        self.assertTrue(six == self.picture(spin))
        text = six.copy(spin.lineEdit().geometry())
        lightness = [
            QtGui.QColor(text.pixel(x, y)).lightness() for x in range(text.width()) for y in range(text.height())
        ]
        self.assertGreaterEqual(max(lightness), 200)
        # Typing in it shows the value.
        spin.setFocus()
        self.events()
        self.assertTrue(spin.hasFocus())
        seven = self.picture(spin)
        spin.setValue(6.0)
        self.assertFalse(seven == self.picture(spin))


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

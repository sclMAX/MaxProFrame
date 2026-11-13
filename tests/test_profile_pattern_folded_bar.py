"""Profile Pattern of a whole Folded Bar (odd/tasks/folded-bar-tools.md, T6: S3).

The layout is the user's (L1): a Folded Bar of three tubes (right, top, left) with the bottom tube loose. Profile
Pattern takes the whole bar as the piece it repeats, never one of its hidden tubes: a click on the bar, or the bar
selected before the command, is the piece; a straight edge of the bar gives the direction, and Count and pitch places
copies of the bar (Links to it) along it. Between faces moves a piece through the offsets of its profile, which a bar
has not: the panel says to use Count and pitch. Cancel leaves no pattern and the bar as it was. The BOM counts each
copy as one more folded bar of its developed length, with the bar's ID.
"""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import test_profile_pattern_panel as pattern_panel
from miter_helpers import use_language
from PySide import QtWidgets
from test_extend_cut_preview import keep_auto_preview
from test_folded_bar_tools import FoldedBarToolsFixture, face_at, global_shape
from test_unfolded_geometry import PLAIN

from freecad.maxproframe import create_profile_pattern_tool
from freecad.maxproframe._utils import get_profiles_and_links_from_document, get_profiles_and_links_from_object
from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.profile_pattern import BETWEEN_FACES, edge_direction, make_profile_pattern

PITCH = 100.0
COPIES = 2
# A point on the outer wall of the right tube of the bar.
RIGHT_WALL = App.Vector(325, 100, 0)
NO_EDGE = "Click a straight edge for the direction of the copies."
USE_COUNT_AND_PITCH = (
    "Between faces moves the piece by the offsets of its profile, and {} has no path edge to offset from. "
    "Use Count and pitch."
)
SAME_PLACE = 1e-6
Z = App.Vector(0, 0, 1)


def edge_along(obj, axis):
    """(name, middle point) of a straight edge of ``obj`` along ``axis``, in global coordinates."""
    for index, edge in enumerate(global_shape(obj).Edges, 1):
        if isinstance(edge.Curve, Part.Line) and edge.Curve.Direction.cross(axis).Length < 1e-9:
            return f"Edge{index}", edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
    raise AssertionError(f"no straight edge of {obj.Label} along {axis}")


def box_of(obj):
    box = global_shape(obj).BoundBox
    return (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)


class PatternBarFixture(FoldedBarToolsFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        super().setUp()
        use_language(self, "English", "en_US")
        keep_auto_preview(self, pattern_panel.AUTO_PREVIEW)
        self.doc.UndoMode = 1
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.recorded = []
        base = create_profile_pattern_tool.ProfilePatternTaskPanel
        recorded = self.recorded

        class Recording(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                recorded.append(self)

        recorder = patch.object(create_profile_pattern_tool, "ProfilePatternTaskPanel", Recording)
        recorder.start()
        self.addCleanup(recorder.stop)
        self.addCleanup(self.close_dialog)

    close_dialog = pattern_panel.PatternPanelFixture.close_dialog
    events = pattern_panel.PatternPanelFixture.events
    select = pattern_panel.PatternPanelFixture.select
    run_command = pattern_panel.PatternPanelFixture.run_command
    set_values = pattern_panel.PatternPanelFixture.set_values
    names = pattern_panel.PatternPanelFixture.names
    patterns = pattern_panel.PatternPanelFixture.patterns

    def click(self, obj, sub, point):
        """A click in the 3D view at the global ``point``: it replaces the selection, the observer hears it."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub, point.x, point.y, point.z)
        self.events()

    def click_bar(self, bar):
        self.click(bar, face_at(bar, RIGHT_WALL), RIGHT_WALL)

    def bar_state(self, bar):
        """What the bar shows: its tubes, its shape and the tubes hidden."""
        return (
            [segment.Name for segment in bar.Segments],
            round(bar.Shape.Volume, 6),
            box_of(bar),
            [segment.Visibility for segment in bar.Segments],
        )


class PatternOfABarTest(PatternBarFixture):
    def test_a_click_on_the_bar_picks_the_whole_bar_and_count_and_pitch_repeats_it(self):
        (_, right, top, left), bar = self.make_legs()
        before = self.bar_state(bar)
        panel = self.run_command()

        self.click_bar(bar)

        self.assertIs(bar, panel.piece)
        self.assertEqual(bar.Label, panel.form.piece_label.toolTip())
        self.assertEqual(NO_EDGE, panel.form.message_label.text())

        edge, middle = edge_along(bar, Z)
        self.click(bar, edge, middle)
        self.assertIs(bar, panel.edge[0])
        self.assertEqual(f"{bar.Label} · {edge}", panel.form.edge_label.toolTip())
        self.assertEqual("", panel.form.message_label.text())
        self.set_values(panel, count=COPIES, pitch=PITCH)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.doc.recompute()

        (pattern,) = self.patterns()
        self.assertTrue(pattern.isValid(), pattern.getStatusString())
        self.assertIs(bar, pattern.Piece)
        self.assertEqual([bar] * COPIES, [copy.LinkedObject for copy in pattern.Copies])
        direction = edge_direction(bar, edge)
        expected = []
        for step in range(1, COPIES + 1):
            move = direction * (step * PITCH)
            box = box_of(bar)
            expected.append(tuple(value + (move.x, move.y, move.z)[index % 3] for index, value in enumerate(box)))
        for copy, box in zip(pattern.Copies, expected):
            with self.subTest(copy=copy.Label):
                for found, wanted in zip(box_of(copy), box):
                    self.assertAlmostEqual(wanted, found, delta=SAME_PLACE)
                self.assertAlmostEqual(bar.Shape.Volume, copy.Shape.Volume, delta=1e-3)
        # The bar is unchanged and still folds its tubes, hidden.
        self.assertEqual(before, self.bar_state(bar))
        self.assertEqual([right, top, left], list(bar.Segments))

    def test_a_bar_selected_before_the_command_is_the_piece(self):
        _, bar = self.make_legs()

        panel = self.run_command((bar, face_at(bar, RIGHT_WALL)))

        self.assertIs(bar, panel.piece)
        self.assertEqual(bar.Label, panel.form.piece_label.toolTip())
        self.assertEqual(NO_EDGE, panel.form.message_label.text())

    def test_between_faces_with_a_bar_says_to_use_count_and_pitch(self):
        _, bar = self.make_legs()
        before = self.bar_state(bar)
        message = USE_COUNT_AND_PITCH.format(bar.Label)
        panel = self.run_command()
        self.click_bar(bar)
        edge, middle = edge_along(bar, Z)
        self.click(bar, edge, middle)

        self.assertEqual(message, panel.form.mode_label.text())
        self.set_values(panel, mode=BETWEEN_FACES, count=3)

        self.assertEqual(message, panel.form.mode_label.text())
        self.assertFalse(panel.accept())
        self.assertIn(message, panel.form.message_label.text())
        self.assertEqual(before, self.bar_state(bar))

    def test_cancel_leaves_no_pattern_and_the_bar_as_before(self):
        _, bar = self.make_legs()
        before, names, undos = self.bar_state(bar), self.names(), len(self.doc.UndoNames)
        panel = self.run_command()
        self.click_bar(bar)
        edge, middle = edge_along(bar, Z)
        self.click(bar, edge, middle)
        self.set_values(panel, count=COPIES, pitch=PITCH)
        (pattern,) = self.patterns()
        self.assertEqual(COPIES, len(pattern.Copies))

        self.assertTrue(panel.reject())
        self.close_dialog()
        self.doc.recompute()

        self.assertEqual([], self.patterns())
        self.assertEqual(names, self.names())
        self.assertEqual(before, self.bar_state(bar))
        self.assertEqual(undos, len(self.doc.UndoNames))


class PatternFollowsTheBarTest(FoldedBarToolsFixture):
    def test_a_piece_made_on_a_tube_of_the_bar_later_shows_on_every_copy_without_a_fight(self):
        (bottom, right, top, left), bar = self.make_legs()
        edge, _ = edge_along(bar, Z)
        pattern = make_profile_pattern(bar, (bar, edge), count=COPIES, pitch=PITCH)
        self.doc.recompute()

        miter = make_end_miter_profile(right, [bottom])
        self.doc.recompute()

        # The bar folds the miter, the copies still link the whole bar and show it.
        self.assertEqual([miter, top, left], list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertTrue(pattern.isValid(), pattern.getStatusString())
        self.assertEqual([bar] * COPIES, [copy.LinkedObject for copy in pattern.Copies])
        self.assertAlmostEqual(-25.0, bar.Shape.BoundBox.YMin, delta=SAME_PLACE)
        for copy in pattern.Copies:
            with self.subTest(copy=copy.Label):
                self.assertAlmostEqual(-25.0, global_shape(copy).BoundBox.YMin, delta=SAME_PLACE)
                self.assertAlmostEqual(bar.Shape.Volume, copy.Shape.Volume, delta=1e-3)
        self.assertFalse(miter.Visibility)
        self.assertFalse(right.Visibility)
        # Neither follow relinks the other's objects: a recompute after that one changes nothing.
        self.assertEqual([], [obj.Name for obj in self.doc.Objects if "Touched" in obj.State])
        self.doc.recompute()
        self.assertEqual([miter, top, left], list(bar.Segments))
        self.assertEqual([bar] * COPIES, [copy.LinkedObject for copy in pattern.Copies])
        self.assertEqual([], [obj.Name for obj in self.doc.Objects if "Touched" in obj.State])


class PatternOfABarBomTest(FoldedBarToolsFixture):
    def test_the_bom_counts_each_copy_as_one_more_folded_bar_of_its_developed_length_with_its_id(self):
        part = self.doc.addObject("App::Part", "Part")
        _, bar = self.make_bar(container=part, **PLAIN)
        edge, _ = edge_along(bar, Z)
        pattern = make_profile_pattern(bar, (bar, edge), count=COPIES, pitch=PITCH)
        self.doc.recompute()
        self.assertTrue(pattern.isValid(), pattern.getStatusString())

        profiles, links = [], []
        get_profiles_and_links_from_object(profiles, links, part)
        doc_profiles, doc_links = get_profiles_and_links_from_document()
        populate_ids(
            profiles, links, doc_profiles, doc_links, "all_numbers", False, True, False, False, "fill_document"
        )
        self.doc.recompute()
        rows, _ = [], []
        traverse_assembly(rows, _, part)

        length = f"{bar.DevelopedLength.Value:.1f}"
        self.assertEqual("1", bar.PID)
        self.assertEqual(
            [(bar.Label, "1", length)] + [(copy.Label, "1", length) for copy in pattern.Copies],
            [(row["label"], row["ID"], row["length"]) for row in rows],
        )
        self.assertEqual(
            [("1", "Square Hollow", "50x50x2", length, COPIES + 1)],
            [
                (row["ID"], row["family"], row["size_name"], row["length"], row["quantity"])
                for row in group_profiles(rows)
            ],
        )


if __name__ == "__main__":
    unittest.main()

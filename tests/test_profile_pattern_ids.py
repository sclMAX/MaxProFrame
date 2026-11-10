"""Profile Pattern copies are pieces of the original: same ID in the BOM, the Cut List, the Piece Table and Populate IDs."""

import unittest

import FreeCAD as App
from test_cut_list import cell
from test_piece_table import PieceTableFixture
from test_reset_ids import ResetIDsChecks

from freecad.maxproframe._utils import get_profiles_and_links_from_document, get_profiles_and_links_from_object
from freecad.maxproframe.create_bom import group_links, group_profiles, traverse_assembly
from freecad.maxproframe.create_link import makeLink
from freecad.maxproframe.piece_table import table_rows
from freecad.maxproframe.populate_ids import populate_ids, set_profile_pid
from freecad.maxproframe.profile_pattern import make_profile_pattern

# populate_ids arguments after the four lists: numbering, allow duplicated, group identical, count, keep existing,
# scheme.
NUMBERS = ("all_numbers", False, False, False, False, "fill_document")
GROUPED_WITH_COUNT = ("all_numbers", False, True, True, False, "fill_document")


class PatternIdsFixture(PieceTableFixture):
    def setUp(self):
        super().setUp()
        App.setActiveDocument(self.doc.Name)
        # The tube runs along X; the copies follow a frame edge along Y.
        self.frame = self.make_sketch(((0, 0, 0), (0, 1000, 0)))
        self.group = self.doc.addObject("App::DocumentObjectGroup", "Frame")

    def patterned_tube(self, pid="1", count=3):
        """A tube with ID ``pid`` in the group, and its pattern of ``count`` copies 200 mm apart."""
        tube = self.tube_with_id(pid)
        self.group.addObject(tube)
        pattern = make_profile_pattern(tube, (self.frame, "Edge1"), count=count, pitch=200.0)
        self.doc.recompute()
        self.assertTrue(pattern.isValid(), pattern.getStatusString())
        self.assertEqual(len(pattern.Copies), count)
        return tube, pattern

    def bom_data(self, *objs):
        profiles, links = [], []
        for obj in objs:
            traverse_assembly(profiles, links, obj)
        return profiles, links

    def selection(self, *objs):
        profiles, links = [], []
        for obj in objs:
            get_profiles_and_links_from_object(profiles, links, obj)
        return profiles, links

    def populate(self, *objs, options=NUMBERS):
        doc_profiles, doc_links = get_profiles_and_links_from_document()
        populate_ids(*self.selection(*objs), doc_profiles, doc_links, *options)


class TestPatternInBom(PatternIdsFixture):
    def test_the_bom_lists_each_copy_as_a_piece_of_the_original_with_its_id(self):
        tube, pattern = self.patterned_tube()
        profiles, links = self.bom_data(self.group)
        self.assertEqual(links, [])
        self.assertEqual([row["ID"] for row in profiles], ["1"] * 4)
        self.assertEqual(
            sorted(row["label"] for row in profiles), sorted([tube.Label] + [c.Label for c in pattern.Copies])
        )
        self.assertEqual(
            {(row["size_name"], row["length"]) for row in profiles}, {("80x40x2", f"{tube.Length.Value:.1f}")}
        )
        grouped = group_profiles(profiles)
        self.assertEqual([(row["ID"], row["quantity"]) for row in grouped], [("1", 4)])

    def test_the_cut_list_counts_the_copies_with_the_original(self):
        self.patterned_tube()
        sheet = self.cut_list(self.bom_data(self.group)[0])
        self.assertEqual([cell(sheet, f"{column}2") for column in "CH"], ["1", "4"])
        self.assertEqual(cell(sheet, "C3"), "")

    def test_a_cutout_added_after_the_pattern_keeps_the_original_and_its_copies_in_one_row(self):
        part = self.doc.addObject("App::Part", "Table")
        tube = self.tube_with_id("1")
        part.addObjects([tube, *tube.OutList])
        pattern = make_profile_pattern(tube, (self.frame, "Edge1"), count=3, pitch=200.0)
        self.doc.recompute()
        cutout = self.hole_in_the_middle(tube)
        part.addObject(cutout)
        self.doc.recompute()
        profiles, links = self.bom_data(part)
        self.assertEqual(links, [])
        self.assertEqual(
            sorted(row["label"] for row in profiles), sorted([cutout.Label] + [c.Label for c in pattern.Copies])
        )
        grouped = group_profiles(profiles)
        self.assertEqual([(row["ID"], row["cutout"], row["quantity"]) for row in grouped], [("1", "Yes", 4)])

    def test_an_attached_link_stays_a_part_of_its_own(self):
        tube = self.tube_with_id("1")
        link = makeLink(tube)
        link.PID = "A"
        profiles, links = self.bom_data(tube, link)
        self.assertEqual([row["ID"] for row in profiles], ["1"])
        self.assertEqual([(row["ID"], row["quantity"]) for row in group_links(links)], [("A", 1)])


class TestPatternInPieceTable(PatternIdsFixture):
    def test_the_piece_table_counts_the_copies_with_the_original(self):
        tube, _ = self.patterned_tube()
        rows, listed, without_id = table_rows([self.add_view("View", self.group)])
        self.assertEqual([row[:3] for row in rows], [("1", "80x40x2", "4")])
        self.assertEqual((listed, without_id), (4, []))


class TestPatternIds(PatternIdsFixture):
    def test_populate_ids_gives_the_copies_the_id_of_the_original(self):
        tube, pattern = self.patterned_tube(pid="")
        other = self.tube_with_id("")
        self.group.addObject(other)
        self.populate(self.group)
        self.assertEqual(tube.PID, "1")
        self.assertEqual([c.PID for c in pattern.Copies], ["1"] * 3)
        # The copies take no number of their own.
        self.assertEqual(other.PID, "2")

    def test_the_count_of_an_id_includes_the_copies(self):
        tube, pattern = self.patterned_tube(pid="")
        self.populate(self.group, options=GROUPED_WITH_COUNT)
        self.assertEqual(tube.PID, "1 x4")
        self.assertEqual([c.PID for c in pattern.Copies], ["1 x4"] * 3)

    def test_selecting_only_copies_numbers_their_original(self):
        tube, pattern = self.patterned_tube(pid="")
        self.populate(*pattern.Copies)
        self.assertEqual(tube.PID, "1")
        self.assertEqual([c.PID for c in pattern.Copies], ["1"] * 3)

    def test_an_id_set_through_a_copy_goes_to_the_original_and_every_copy(self):
        tube, pattern = self.patterned_tube(pid="1")
        set_profile_pid(pattern.Copies[1], "")
        self.assertEqual(tube.PID, "")
        self.assertEqual([c.PID for c in pattern.Copies], [""] * 3)

    def test_resetting_through_a_copy_counts_every_id_it_clears(self):
        tube, pattern = self.patterned_tube(pid="1")
        cutout = self.hole_in_the_middle(tube)
        self.assertEqual([cutout.PID] + [c.PID for c in pattern.Copies], ["1"] * 4)
        owned = [o for o in self.doc.Objects if "PID" in o.PropertiesList]
        before = {o.Name: o.PID for o in owned}
        asked, printed = ResetIDsChecks.reset(self, pattern.Copies[0])
        cleared = [o for o in owned if before[o.Name] != o.PID]
        # The copies, the cutout they show and its profile: every one loses ID 1.
        self.assertEqual(
            sorted(o.Name for o in cleared), sorted([tube.Name, cutout.Name, *(c.Name for c in pattern.Copies)])
        )
        question = "Reset the IDs of the selection?\n\nIDs to clear: 5. Undo (Ctrl+Z) restores them."
        self.assertEqual(asked, [("Reset IDs", question)])
        lines = printed.splitlines()
        self.assertEqual(lines[0], "Reset IDs: IDs cleared: 5.")
        self.assertEqual(sorted(lines[1:]), sorted(f"  {o.Label}: 1" for o in cleared))

    def test_attached_links_are_still_numbered_on_their_own(self):
        tube = self.tube_with_id("")
        link = makeLink(tube)
        self.populate(tube, link)
        self.assertEqual((tube.PID, link.PID), ("1", "2"))


if __name__ == "__main__":
    unittest.main()

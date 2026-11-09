"""BOM and Cut List: cut angles with their face, the Ends column, identical pieces of a bar on one row, legends."""

import unittest

from test_cut_ends import CutEndsFixture

from freecad.maxproframe.best_fit import CutPart, best_fit_decreasing
from freecad.maxproframe.create_bom import make_bom, make_cut_list, traverse_assembly

KERF = 1.0
# Every mark the angle and Ends columns can print, in legend order.
LEGEND_MARKS = ["<", "+", "\\_/", "/_/", "|_/", "@", "P", "*", "?"]


def cell(sheet, address):
    """Text of a cell as written, without the quote that keeps it text."""
    return sheet.getContents(address).removeprefix("'")


class CutListFixture(CutEndsFixture):
    def pieces(self, *profiles):
        data, links = [], []
        for obj in profiles:
            traverse_assembly(data, links, obj)
        return data

    def cut_list(self, profiles, stock_length=6000.0):
        parts = [CutPart(p["label"], float(p["length"]), KERF, p) for p in profiles]
        sheet = self.doc.addObject("Spreadsheet::Sheet", "CutList")
        make_cut_list({"Metal_Rectangular Hollow_80x40x2": best_fit_decreasing(stock_length, parts)}, spreadsheet=sheet)
        self.doc.recompute()
        return sheet

    def bom(self, profiles):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "BOM")
        make_bom(profiles, [], spreadsheet=sheet)
        self.doc.recompute()
        return sheet

    def legend(self, sheet):
        """The marks listed under Legend, in order."""
        row = next(row for row in range(1, 200) if cell(sheet, f"A{row}") == "Legend") + 1
        marks = []
        while cell(sheet, f"A{row}"):
            marks.append(cell(sheet, f"A{row}"))
            row += 1
        return marks

    def tube_with_id(self, pid, **bevels):
        obj = self.tube_along_x(**bevels)
        obj.PID = pid
        return obj


class TestCutListGrouping(CutListFixture):
    def test_identical_pieces_of_one_bar_are_one_row(self):
        profiles = self.pieces(*(self.tube_with_id("1", BevelACutY=45.0) for _ in range(2)))
        sheet = self.cut_list(profiles)
        row = [cell(sheet, f"{column}2") for column in "BCEFGH"]
        self.assertEqual(row, ["0", "1", "45.0 <80", "0.0", "|_/", "2"])

    def test_pieces_without_id_keep_one_row_each(self):
        # Without an ID nothing tells that two pieces of the same length and angles are the same piece.
        profiles = self.pieces(*(self.tube_with_id("", BevelACutY=45.0) for _ in range(2)))
        sheet = self.cut_list(profiles)
        rows = [[cell(sheet, f"{column}{row}") for column in "BCEFGH"] for row in (2, 3)]
        self.assertEqual(rows, [["0", "", "45.0 <80", "0.0", "|_/", "1"]] * 2)
        self.assertAlmostEqual(float(cell(sheet, "D2")), float(profiles[0]["length"]))
        self.assertEqual(cell(sheet, "C3"), "")

    def test_the_same_id_on_two_bars_keeps_one_row_per_bar(self):
        profiles = self.pieces(*(self.tube_with_id("1", BevelACutY=45.0) for _ in range(2)))
        sheet = self.cut_list(profiles, stock_length=500.0)
        rows = [[cell(sheet, f"{column}{row}") for column in "BCH"] for row in (2, 3)]
        self.assertEqual(rows, [["0", "1", "1"], ["1", "1", "1"]])

    def test_stock_statistics_still_count_every_piece(self):
        profiles = self.pieces(*(self.tube_with_id("1") for _ in range(2)))
        sheet = self.cut_list(profiles)
        row = next(row for row in range(1, 50) if cell(sheet, f"A{row}") == "Stock statistics") + 1
        self.assertEqual(cell(sheet, f"A{row}"), "Metal_Rectangular Hollow_80x40x2")
        used = sum(float(p["length"]) + KERF for p in profiles)
        self.assertAlmostEqual(float(cell(sheet, f"B{row}")), used)
        self.assertEqual([cell(sheet, f"{column}{row}") for column in "CD"], ["6000", "1"])

    def test_the_cut_list_header_has_the_ends_before_the_quantity(self):
        sheet = self.cut_list(self.pieces(self.tube_with_id("1")))
        header = [cell(sheet, f"{column}1") for column in "ABCDEFGH"]
        self.assertEqual(
            header, ["Material", "Stock", "CutPart ID", "Length", "CutAngle1", "CutAngle2", "Ends", "Quantity"]
        )


class TestBOMAngles(CutListFixture):
    def test_the_bom_writes_the_face_of_each_angle_and_the_ends(self):
        sheet = self.bom(self.pieces(self.tube_with_id("7", BevelACutY=45.0, BevelBCutY=45.0, BevelBCutX=10.0)))
        header = [cell(sheet, f"{column}2") for column in "FGHIJ"]
        self.assertEqual(header, ["CutAngle1", "CutAngle2", "Ends", "Drill/Cutout", "Quantity"])
        row = [cell(sheet, f"{column}3") for column in "BFGHJ"]
        self.assertEqual(row, ["7", "45.0 <80", "45.4 <80 + 10.0 <40", "", "1"])

    def test_the_bom_writes_the_ends_symbol(self):
        sheet = self.bom(self.pieces(self.tube_with_id("7", BevelACutY=45.0, BevelBCutY=45.0)))
        self.assertEqual([cell(sheet, f"{column}3") for column in "FGH"], ["45.0 <80", "45.0 <80", "\\_/"])


class TestLegends(CutListFixture):
    def test_both_legends_list_exactly_the_printed_marks(self):
        profiles = self.pieces(self.tube_with_id("1", BevelACutY=30.0, BevelBCutX=-30.0))
        for name, sheet in (("BOM", self.bom(profiles)), ("Cut List", self.cut_list(profiles))):
            with self.subTest(name):
                self.assertEqual(self.legend(sheet), LEGEND_MARKS)


if __name__ == "__main__":
    unittest.main()

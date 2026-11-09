"""BOM and Cut List: cut angles with their face, the Ends column, identical pieces and bars grouped, legends."""

import unittest

from miter_helpers import use_language
from test_cut_ends import CutEndsFixture

from freecad.maxproframe.best_fit import CutPart, best_fit_decreasing
from freecad.maxproframe.create_bom import group_links, group_profiles, make_bom, make_cut_list, traverse_assembly
from freecad.maxproframe.create_bom_tool import CreateBOMTaskPanel

KERF = 1.0
MATERIAL = "Metal_Rectangular Hollow_80x40x2"
# Every mark the angle and Ends columns can print, in legend order.
LEGEND_MARKS = ["<", "+", "\\_/", "/_/", "|_/", "@", "P", "*", "?"]


def cell(sheet, address):
    """Text of a cell as written, without the quote that keeps it text."""
    return sheet.getContents(address).removeprefix("'")


def piece(pid, angle_1="0.0", angle_2="0.0", ends="", length="4000.0"):
    """The Cut List data of a piece, as traverse_assembly gives it, without building the piece."""
    angles = {"cut_angle_1": angle_1, "cut_angle_2": angle_2, "ends": ends}
    return {"label": f"Piece {pid}", "ID": pid, "length": length, **angles}


class CutListFixture(CutEndsFixture):
    def pieces(self, *profiles):
        data, links = [], []
        for obj in profiles:
            traverse_assembly(data, links, obj)
        return data

    def cut_list(self, profiles, stock_length=6000.0):
        parts = [CutPart(p["label"], float(p["length"]), KERF, p) for p in profiles]
        sheet = self.doc.addObject("Spreadsheet::Sheet", "CutList")
        make_cut_list({MATERIAL: best_fit_decreasing(stock_length, parts)}, spreadsheet=sheet)
        self.doc.recompute()
        return sheet

    def bom(self, profiles):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "BOM")
        make_bom(profiles, [], spreadsheet=sheet)
        self.doc.recompute()
        return sheet

    def legend(self, sheet, title="Legend"):
        """The marks listed under the legend ``title``, in order."""
        return [mark for mark, _ in self.legend_rows(sheet, title)]

    def legend_rows(self, sheet, title="Legend"):
        """(mark, text) of each row under the legend ``title``, in order."""
        row = next(row for row in range(1, 200) if cell(sheet, f"A{row}") == title) + 1
        rows = []
        while cell(sheet, f"A{row}"):
            rows.append((cell(sheet, f"A{row}"), cell(sheet, f"B{row}")))
            row += 1
        return rows

    def statistics(self, sheet, title="Stock statistics"):
        """The Stock statistics row of the material: Length Used, Stock Used, Stock Count."""
        row = next(row for row in range(1, 50) if cell(sheet, f"A{row}") == title) + 1
        self.assertEqual(cell(sheet, f"A{row}"), MATERIAL)
        return [cell(sheet, f"{column}{row}") for column in "BCD"]

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
        self.assertAlmostEqual(float(cell(sheet, "D2")), float(profiles[0]["length"]))
        self.assertEqual(cell(sheet, "C3"), "")

    def test_pieces_without_id_keep_one_row_each(self):
        # Without an ID nothing tells that two pieces of the same length and angles are the same piece.
        profiles = self.pieces(*(self.tube_with_id("", BevelACutY=45.0) for _ in range(2)))
        sheet = self.cut_list(profiles)
        rows = [[cell(sheet, f"{column}{row}") for column in "BCEFGH"] for row in (2, 3)]
        self.assertEqual(rows, [["0", "", "45.0 <80", "0.0", "|_/", "1"]] * 2)

    def test_the_same_id_on_two_bars_keeps_one_row_per_bar(self):
        # Bar 0 gets pieces 1 and 2, bar 1 the other piece 1: the bars differ, so each keeps its block.
        sheet = self.cut_list([piece("1"), piece("1"), piece("2", length="1000.0")])
        rows = [[cell(sheet, f"{column}{row}") for column in "BCH"] for row in (2, 3, 4)]
        self.assertEqual(rows, [["0", "1", "1"], ["0", "2", "1"], ["1", "1", "1"]])

    def test_stock_statistics_still_count_every_piece(self):
        profiles = self.pieces(*(self.tube_with_id("1") for _ in range(2)))
        sheet = self.cut_list(profiles)
        used, stock, count = self.statistics(sheet)
        self.assertAlmostEqual(float(used), sum(float(p["length"]) + KERF for p in profiles))
        self.assertEqual([stock, count], ["6000", "1"])

    def test_the_cut_list_header_has_the_ends_before_the_quantity(self):
        sheet = self.cut_list(self.pieces(self.tube_with_id("1")))
        header = [cell(sheet, f"{column}1") for column in "ABCDEFGH"]
        self.assertEqual(
            header, ["Material", "Stock", "CutPart ID", "Length", "CutAngle1", "CutAngle2", "Ends", "Quantity"]
        )

    def test_a_piece_turned_end_for_end_shares_the_row_larger_angle_first(self):
        profiles = self.pieces(
            self.tube_with_id("11", BevelACutY=4.0, BevelBCutY=45.0),
            self.tube_with_id("11", BevelACutY=45.0, BevelBCutY=4.0),
        )
        sheet = self.cut_list(profiles)
        rows = [[cell(sheet, f"{column}{row}") for column in "BCEFGH"] for row in (2, 3)]
        self.assertEqual(rows, [["0", "11", "45.0 <80", "4.0 <80", "\\_/", "2"], ["", "", "", "", "", ""]])


class TestAngleOrder(CutListFixture):
    """The Cut List prints the larger leading number first, whatever mark comes before it."""

    def angles(self, angle_1, angle_2):
        sheet = self.cut_list([piece("1", angle_1, angle_2)])
        return [cell(sheet, f"{column}2") for column in "EF"]

    def test_a_marked_angle_is_ordered_by_its_number(self):
        self.assertEqual(self.angles("4.0", "@ 45.0"), ["@ 45.0", "4.0"])
        self.assertEqual(self.angles("@ 4.0", "45.0 <80"), ["45.0 <80", "@ 4.0"])

    def test_an_angle_without_number_goes_last(self):
        self.assertEqual(self.angles("@ P", "30.0"), ["30.0", "@ P"])
        self.assertEqual(self.angles("?", "0.0"), ["0.0", "?"])

    def test_equal_numbers_keep_string_order(self):
        self.assertEqual(self.angles("45.0 <80", "45.0 <40"), ["45.0 <40", "45.0 <80"])
        self.assertEqual(self.angles("@ 45.0", "45.0 <80"), ["45.0 <80", "@ 45.0"])


class TestIdenticalBars(CutListFixture):
    """Bars of one material cut alike take one block, with the number of bars and their indexes."""

    def block(self, sheet, row):
        return [cell(sheet, f"{column}{row}") for column in "ABCH"]

    def title(self, used, left, bars=""):
        return f"{MATERIAL} / used = {used}, left = {left}" + (f" ×{bars} bars" if bars else "")

    def test_two_identical_bars_take_one_block(self):
        sheet = self.cut_list([piece("1", "45.0 <80", ends="|_/"), piece("1", "45.0 <80", ends="|_/")])
        self.assertEqual(self.block(sheet, 2), [self.title("4001.0", "1999.0", 2), "0, 1", "1", "1"])
        self.assertEqual([cell(sheet, f"{column}2") for column in "EFG"], ["45.0 <80", "0.0", "|_/"])
        self.assertEqual(self.block(sheet, 3), ["", "", "", ""])

    def test_identical_bars_apart_share_the_block_of_the_first(self):
        # Equal lengths keep their order: bars 0 and 2 get ID 1, bar 1 gets ID 2.
        sheet = self.cut_list([piece("1"), piece("2"), piece("1")])
        self.assertEqual(self.block(sheet, 2), [self.title("4001.0", "1999.0", 2), "0, 2", "1", "1"])
        self.assertEqual(self.block(sheet, 3), [self.title("4001.0", "1999.0"), "1", "2", "1"])
        self.assertEqual(self.block(sheet, 4), ["", "", "", ""])

    def test_different_bars_stay_apart(self):
        sheet = self.cut_list([piece("1"), piece("2")])
        self.assertEqual(self.block(sheet, 2), [self.title("4001.0", "1999.0"), "0", "1", "1"])
        self.assertEqual(self.block(sheet, 3), [self.title("4001.0", "1999.0"), "1", "2", "1"])

    def test_bars_with_other_angles_stay_apart(self):
        sheet = self.cut_list([piece("1", "45.0 <80"), piece("1", "30.0 <80")])
        self.assertEqual([cell(sheet, f"B{row}") for row in (2, 3)], ["0", "1"])

    def test_stock_statistics_still_count_every_bar(self):
        sheet = self.cut_list([piece("1"), piece("2"), piece("1")])
        used, stock, count = self.statistics(sheet)
        self.assertAlmostEqual(float(used), 3 * 4001.0)
        self.assertEqual([stock, count], ["18000", "3"])


class TestBOMGrouping(CutListFixture):
    def test_grouped_ids_keep_the_order_they_come_in(self):
        base = self.pieces(self.tube_with_id("1"))[0]
        ids = ["8", "3", "5", "1", "7", "2", "6", "4", "3"]
        grouped = group_profiles([dict(base, ID=pid, label=f"P{pid}") for pid in ids])
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["ID"], "8, 3, 5, 1, 7, 2, 6, 4")
        link = {"parent": "", "part": "Bracket", "quantity": "1", "price": 1.0}
        links = [dict(link, ID=pid, label=f"L{pid}") for pid in ids]
        self.assertEqual(group_links(links)[0]["ID"], "8, 3, 5, 1, 7, 2, 6, 4")

    def test_a_part_without_id_is_listed_when_not_grouped(self):
        # traverse_assembly gives a plain Part or PartDesign object no ID.
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        profiles, links = [], []
        traverse_assembly(profiles, links, box)
        sheet = self.doc.addObject("Spreadsheet::Sheet", "BOM")
        make_bom(profiles, links, spreadsheet=sheet)
        self.doc.recompute()
        self.assertEqual([cell(sheet, f"{column}6") for column in "ABCEF"], ["", "", "Box", "1", "Box"])


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

    def test_the_bom_keeps_the_start_angle_first(self):
        sheet = self.bom(self.pieces(self.tube_with_id("11", BevelACutY=4.0, BevelBCutY=45.0)))
        self.assertEqual([cell(sheet, f"{column}3") for column in "FGH"], ["4.0 <80", "45.0 <80", "\\_/"])


class TestLegends(CutListFixture):
    def test_both_legends_list_exactly_the_printed_marks(self):
        profiles = self.pieces(self.tube_with_id("1", BevelACutY=30.0, BevelBCutX=-30.0))
        for name, sheet in (("BOM", self.bom(profiles)), ("Cut List", self.cut_list(profiles))):
            with self.subTest(name):
                self.assertEqual(self.legend(sheet), LEGEND_MARKS)


class TestSpanish(CutListFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")
        tube = self.tube_with_id("1", BevelACutY=45.0)
        tube.Cutout = True
        self.profiles = self.pieces(tube)

    def test_the_create_bom_panel_is_in_spanish(self):
        form = CreateBOMTaskPanel().form
        self.addCleanup(form.deleteLater)
        texts = [
            form.windowTitle(),
            form.groupBox.title(),
            form.label.text(),
            form.full_parent_path.text(),
            form.include_links_cb.text(),
            form.group_profiles_cb.text(),
            form.groupBox_2.title(),
            form.cut_list_cb.text(),
            form.label_2.text(),
            form.label_3.text(),
        ]
        self.assertEqual(
            texts,
            [
                "Crear lista de materiales",
                "Lista de materiales",
                "Nombre de la lista de materiales",
                "Ruta completa del conjunto",
                "Incluir enlaces",
                "Agrupar perfiles / enlaces",
                "Lista de cortes",
                "Generar lista de cortes",
                "Longitud de la barra",
                "Ancho de corte (kerf)",
            ],
        )

    def test_the_bom_is_in_spanish(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "BOM")
        link = {"parent": "", "ID": "L1", "label": "Link", "part": "Bracket", "quantity": "1", "price": "N/A"}
        make_bom(self.profiles, [link], spreadsheet=sheet)
        self.doc.recompute()
        self.assertEqual(cell(sheet, "A1"), "Perfiles")
        header = [cell(sheet, f"{column}2") for column in "ABCDEFGHIJKLMN"]
        self.assertEqual(
            header,
            [
                "Conjunto",
                "ID",
                "Familia",
                "Medida",
                "Longitud",
                "Ángulo de corte 1",
                "Ángulo de corte 2",
                "Extremos",
                "Agujero/Calado",
                "Cantidad",
                "Material",
                "Peso aprox.",
                "Precio/U",
                "Nombre",
            ],
        )
        self.assertEqual([cell(sheet, f"{column}3") for column in "FGHI"], ["45,0 <80", "0,0", "|_/", "Sí"])
        self.assertEqual(cell(sheet, "A5"), "Piezas")
        header = [cell(sheet, f"{column}6") for column in "ABCDEF"]
        self.assertEqual(header, ["Conjunto", "ID", "Pieza/Tipo", "Precio/U", "Cantidad", "Nombre"])
        legend = dict(self.legend_rows(sheet, "Leyenda"))
        self.assertEqual(list(legend), LEGEND_MARKS)
        self.assertEqual(legend["|_/"], "Extremos: un extremo recto, el otro inclinado sobre una cara")
        self.assertEqual(legend["<"][:9], "45,0 <80:")

    def test_the_cut_list_is_in_spanish(self):
        sheet = self.cut_list(self.profiles)
        header = [cell(sheet, f"{column}1") for column in "ABCDEFGH"]
        self.assertEqual(
            header,
            [
                "Material",
                "Barra",
                "ID de pieza",
                "Longitud",
                "Ángulo de corte 1",
                "Ángulo de corte 2",
                "Extremos",
                "Cantidad",
            ],
        )
        used = float(self.profiles[0]["length"]) + KERF
        title = f"{MATERIAL} / usado = {used:.1f}, sobrante = {6000.0 - used:.1f}".replace(".", ",")
        self.assertEqual(cell(sheet, "A2"), title)
        row = next(row for row in range(1, 50) if cell(sheet, f"A{row}") == "Estadísticas de barras")
        header = [cell(sheet, f"{column}{row}") for column in "BCD"]
        self.assertEqual(header, ["Longitud usada", "Longitud de barras", "Cantidad de barras"])
        self.assertEqual(self.legend(sheet, "Leyenda"), LEGEND_MARKS)

    def test_the_marks_and_the_ids_stay_as_they_are(self):
        sheet = self.cut_list(self.profiles)
        self.assertEqual([cell(sheet, f"{column}2") for column in "CEFG"], ["1", "45,0 <80", "0,0", "|_/"])

    def test_identical_bars_say_how_many_bars(self):
        sheet = self.cut_list([piece("1"), piece("1")])
        self.assertEqual(cell(sheet, "A2"), f"{MATERIAL} / usado = 4001,0, sobrante = 1999,0 ×2 barras")
        self.assertEqual(cell(sheet, "B2"), "0, 1")


class TestNumbersFollowTheLanguage(CutListFixture):
    """Numbers inside texts take the decimal separator of the FreeCAD language; number cells stay numbers."""

    def written(self, language, qt_locale):
        use_language(self, language, qt_locale)
        profiles = [piece("1", "45.0 <80 + 10.5 <40", "@ 4.0", length="1440.5"), piece("2", length="724.6")]
        cut_list = self.cut_list(profiles)
        row = dict(profiles[0], parent="", family="Rectangular Hollow", size_name="80x40x2", material="Metal")
        bom = self.bom([dict(row, cutout="", approx_weight="1.5", price="2.5", quantity="1")])
        return cut_list, bom

    def assert_numbers_stay_numbers(self, cut_list, bom):
        self.assertEqual(cut_list.get("D2"), 1440.5)
        self.assertEqual(bom.get("E3"), 1440.5)
        self.assertEqual([bom.get(address) for address in ("L3", "M3")], [1.5, 2.5])

    def test_spanish_writes_a_decimal_comma(self):
        cut_list, bom = self.written("Spanish", "es_ES")
        self.assertEqual(cell(cut_list, "A2"), f"{MATERIAL} / usado = 2167,1, sobrante = 3832,9")
        self.assertEqual([cell(cut_list, f"{column}2") for column in "EF"], ["45,0 <80 + 10,5 <40", "@ 4,0"])
        self.assertEqual([cell(bom, f"{column}3") for column in "FG"], ["45,0 <80 + 10,5 <40", "@ 4,0"])
        self.assert_numbers_stay_numbers(cut_list, bom)

    def test_english_writes_a_decimal_point(self):
        cut_list, bom = self.written("English", "en_US")
        self.assertEqual(cell(cut_list, "A2"), f"{MATERIAL} / used = 2167.1, left = 3832.9")
        self.assertEqual([cell(cut_list, f"{column}2") for column in "EF"], ["45.0 <80 + 10.5 <40", "@ 4.0"])
        self.assertEqual([cell(bom, f"{column}3") for column in "FG"], ["45.0 <80 + 10.5 <40", "@ 4.0"])
        self.assert_numbers_stay_numbers(cut_list, bom)


if __name__ == "__main__":
    unittest.main()

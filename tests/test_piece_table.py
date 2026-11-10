"""Piece Table: a table of the pieces of the selected TechDraw views, on the page of the first one."""

import os
import unittest
import xml.etree.ElementTree as ElementTree
from unittest import mock

import FreeCAD as App
import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtCore, QtGui, QtWidgets
from test_balloons import page_template
from test_cut_list import CutListFixture, cell

from freecad.maxproframe import create_piece_table_tool
from freecad.maxproframe.create_edit_balloons_tool import cancel_view_pick
from freecad.maxproframe.create_piece_table_tool import CreatePieceTableCommand

HEADER = ["ID", "Piece", "Quantity", "Length", "CutAngle1", "CutAngle2"]
COLUMNS = "ABCDEF"


class PieceTableFixture(CutListFixture):
    def setUp(self):
        super().setUp()
        self.doc.UndoMode = 1
        self.page = self.add_page("Page")
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        # Runs before the document closes: a pick left waiting must not outlive the test.
        self.addCleanup(self.settle)
        self.addCleanup(cancel_view_pick)

    def add_page(self, name):
        page = self.doc.addObject("TechDraw::DrawPage", name)
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", f"{name}Template")
        template.Template = page_template()
        page.Template = template
        return page

    def add_view(self, name, *sources, page=None):
        view = self.doc.addObject("TechDraw::DrawViewPart", name)
        (page or self.page).addView(view)
        view.Source = list(sources)
        self.doc.recompute()
        return view

    def settle(self):
        """Run the work a pick defers out of the selection callback."""
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

    def select(self, *objs):
        Gui.Selection.clearSelection()
        for obj in objs:
            Gui.Selection.addSelection(obj)
        self.settle()

    def run_command(self, *objs):
        self.select(*objs)
        CreatePieceTableCommand().Activated()
        self.settle()

    def press_escape(self):
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(Gui.getMainWindow(), event)
        self.settle()

    def status_message(self):
        return Gui.getMainWindow().statusBar().currentMessage()

    def tables(self):
        return [o for o in self.doc.Objects if o.TypeId == "TechDraw::DrawViewSpreadsheet"]

    def sheets(self):
        return [o for o in self.doc.Objects if o.TypeId == "Spreadsheet::Sheet"]

    def table(self):
        """The only table of the document."""
        tables = self.tables()
        self.assertEqual(len(tables), 1)
        self.assertEqual(self.sheets(), [tables[0].Source])
        return tables[0]

    def rows(self, sheet):
        """Every row of ``sheet`` up to the first empty one, header included."""
        rows, row = [], 1
        while cell(sheet, f"A{row}"):
            rows.append([cell(sheet, f"{column}{row}") for column in COLUMNS])
            row += 1
        return rows

    def length(self, obj):
        return f"{obj.Length.Value:.1f}"


class TestPieceTable(PieceTableFixture):
    def test_the_command_is_enabled_with_just_a_document(self):
        tube = self.tube_with_id("1")
        view = self.add_view("View", tube)
        for selection in ((), (tube,), (view,)):
            self.select(*selection)
            self.assertTrue(CreatePieceTableCommand().IsActive())

    def test_the_command_has_its_icon(self):
        pixmap = CreatePieceTableCommand().GetResources()["Pixmap"]
        self.assertEqual(os.path.basename(pixmap), "piece-table.svg")
        self.assertEqual(ElementTree.parse(pixmap).getroot().tag, "{http://www.w3.org/2000/svg}svg")

    def test_a_view_gets_one_row_per_id_with_its_quantity_on_its_page(self):
        first, second = (self.tube_with_id("1", BevelACutY=45.0) for _ in range(2))
        other = self.tube_with_id("2")
        view = self.add_view("View", first, second, other)
        self.run_command(view)
        table = self.table()
        self.assertIn(table, self.page.Views)
        self.assertEqual(
            self.rows(table.Source),
            [
                HEADER,
                ["1", "80x40x2", "2", self.length(first), "45.0 <80", "0.0"],
                ["2", "80x40x2", "1", self.length(other), "0.0", "0.0"],
            ],
        )
        self.assertEqual((table.CellStart, table.CellEnd), ("A1", "F3"))
        self.assertEqual(self.status_message(), "Piece table created. Rows: 2. Pieces: 3.")

    def test_the_rows_follow_the_ids_in_order(self):
        tubes = [self.tube_with_id(pid) for pid in ("10", "2", "1")]
        self.run_command(self.add_view("View", *tubes))
        self.assertEqual([row[0] for row in self.rows(self.table().Source)[1:]], ["1", "2", "10"])

    def test_the_piece_is_the_name_of_the_profile_only(self):
        tube = self.tube_with_id("1")
        tube.SizeName = "TC80x40x1.5"
        tube.Label = "Profile_TC80x40x1.5_001"
        self.run_command(self.add_view("View", tube))
        self.assertEqual(self.rows(self.table().Source)[1][1], "TC80x40x1.5")

    def test_the_angles_tell_their_faces_compound_too(self):
        tube = self.tube_with_id("7", BevelACutY=45.0, BevelBCutY=45.0, BevelBCutX=10.0)
        self.run_command(self.add_view("View", tube))
        self.assertEqual(self.rows(self.table().Source)[1][4:], ["45.0 <80", "45.4 <80 + 10.0 <40"])

    def test_several_selected_views_make_one_table_on_the_page_of_the_first(self):
        shared, alone = self.tube_with_id("1"), self.tube_with_id("2")
        other_page = self.add_page("OtherPage")
        first = self.add_view("First", shared, page=other_page)
        second = self.add_view("Second", shared, alone)
        self.run_command(first, second)
        table = self.table()
        self.assertIn(table, other_page.Views)
        self.assertNotIn(table, self.page.Views)
        # A piece shown in both views is one piece.
        self.assertEqual(
            [row[:3] for row in self.rows(table.Source)[1:]], [["1", "80x40x2", "1"], ["2", "80x40x2", "1"]]
        )
        self.assertEqual(self.status_message(), "Piece table created. Rows: 2. Pieces: 2.")

    def test_only_the_pieces_of_the_selected_views_are_listed(self):
        shown, hidden = self.tube_with_id("1"), self.tube_with_id("2")
        view = self.add_view("View", shown)
        self.add_view("Other", hidden)
        self.run_command(view)
        self.assertEqual([row[0] for row in self.rows(self.table().Source)[1:]], ["1"])

    def test_pieces_without_id_get_no_row_and_are_named(self):
        with_id, without = self.tube_with_id("1"), self.tube_with_id("")
        without.Label = "Loose"
        printed = []
        self.addCleanup(setattr, App.Console, "PrintMessage", App.Console.PrintMessage)
        App.Console.PrintMessage = printed.append
        self.run_command(self.add_view("View", with_id, without))
        self.assertEqual([row[0] for row in self.rows(self.table().Source)[1:]], ["1"])
        self.assertEqual(
            self.status_message(), "Piece table created. Rows: 1. Pieces: 1. Without ID: 1 (run Populate IDs)."
        )
        self.assertEqual("".join(printed), "Piece Table: without ID: Loose\n")

    def test_no_piece_with_id_creates_nothing(self):
        view = self.add_view("View", self.tube_with_id(""))
        undo_count = self.doc.UndoCount
        self.run_command(view)
        self.assertEqual((self.tables(), self.sheets()), ([], []))
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertEqual(self.status_message(), "No piece with ID. Without ID: 1 (run Populate IDs).")

    def test_a_link_gets_its_own_id_and_the_name_of_what_it_links(self):
        tube = self.tube_with_id("1")
        tube.SizeName = "TC80x40x1.5"
        link = self.doc.addObject("App::Link", "TubeLink")
        link.LinkedObject = tube
        link.addExtension("Part::AttachExtensionPython")
        link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID").PID = "5"
        self.run_command(self.add_view("View", link))
        self.assertEqual(self.rows(self.table().Source)[1], ["5", "TC80x40x1.5", "1", self.length(tube), "0.0", "0.0"])

    def test_running_it_again_refreshes_the_same_table(self):
        first, second = self.tube_with_id("1"), self.tube_with_id("2")
        view = self.add_view("View", first, second)
        self.run_command(view)
        table = self.table()
        table.X, table.Y = 120.0, 80.0
        second.PID = "1"
        self.run_command(view)
        self.assertIs(self.table(), table)
        self.assertEqual(self.rows(table.Source)[1:], [["1", "80x40x2", "2", self.length(first), "0.0", "0.0"]])
        self.assertEqual(table.CellEnd, "F2")
        # The table stays where it was put.
        self.assertEqual((table.X.Value, table.Y.Value), (120.0, 80.0))
        self.assertEqual(self.status_message(), "Piece table refreshed. Rows: 1. Pieces: 2.")

    def test_other_views_get_their_own_table(self):
        first, second = self.tube_with_id("1"), self.tube_with_id("2")
        view, other = self.add_view("View", first), self.add_view("Other", second)
        self.run_command(view)
        self.run_command(other)
        self.run_command(other, view)
        self.assertEqual(len(self.tables()), 3)
        self.run_command(view, other)
        self.assertEqual(len(self.tables()), 3)
        self.assertEqual(self.status_message(), "Piece table refreshed. Rows: 2. Pieces: 2.")

    def test_one_undo_step_adds_the_table_and_undo_removes_it(self):
        view = self.add_view("View", self.tube_with_id("1"))
        undo_count = self.doc.UndoCount
        self.run_command(view)
        self.assertEqual(self.doc.UndoCount, undo_count + 1)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.doc.undo()
        self.assertEqual((self.tables(), self.sheets()), ([], []))
        self.assertEqual(self.page.Views, [view])

    def test_undo_of_a_refresh_brings_back_the_previous_rows(self):
        first, second = self.tube_with_id("1"), self.tube_with_id("2")
        view = self.add_view("View", first, second)
        self.run_command(view)
        table = self.table()
        before = self.rows(table.Source)
        second.PID = "1"
        undo_count = self.doc.UndoCount
        self.run_command(view)
        self.assertEqual(self.doc.UndoCount, undo_count + 1)
        self.doc.undo()
        self.assertIs(self.table(), table)
        self.assertEqual(self.rows(table.Source), before)
        self.assertEqual(table.CellEnd, "F3")

    def test_the_page_shows_the_table(self):
        tube = self.tube_with_id("1", BevelACutY=45.0)
        tube.SizeName = "TC80x40x1.5"
        self.run_command(self.add_view("View", tube))
        self.doc.recompute()
        symbol = self.table().Symbol
        for text in ("Piece", "TC80x40x1.5", "45.0 &lt;80"):
            self.assertIn(text, symbol)

    def test_without_a_view_it_waits_for_a_click_on_one(self):
        view = self.add_view("View", self.tube_with_id("1"))
        self.run_command()
        self.assertEqual(self.tables(), [])
        self.assertEqual(self.status_message(), "Piece Table: Click a TechDraw view (Esc to cancel).")
        self.select(view)
        self.assertIn(self.table(), self.page.Views)
        self.assertEqual(self.status_message(), "Piece table created. Rows: 1. Pieces: 1.")

    def test_escape_cancels_the_wait(self):
        view = self.add_view("View", self.tube_with_id("1"))
        self.run_command()
        self.press_escape()
        self.assertEqual(self.status_message(), "Piece Table: Cancelled.")
        self.select(view)
        self.assertEqual(self.tables(), [])

    def test_pressing_the_button_again_cancels_the_wait(self):
        view = self.add_view("View", self.tube_with_id("1"))
        self.run_command()
        CreatePieceTableCommand().Activated()
        self.settle()
        self.assertEqual(self.status_message(), "Piece Table: Cancelled.")
        self.select(view)
        self.assertEqual(self.tables(), [])

    def test_a_click_on_a_detail_view_says_it_gets_no_table_and_waits(self):
        view = self.add_view("View", self.tube_with_id("1"))
        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        self.page.addView(detail)
        detail.BaseView = view
        detail.Source = view.Source
        self.doc.recompute()
        self.run_command()
        self.select(detail)
        self.assertEqual(self.tables(), [])
        self.assertEqual(
            self.status_message(), "Piece Table: A detail view gets no table: click another view (Esc to cancel)."
        )
        self.select(view)
        self.assertEqual(len(self.tables()), 1)

    def test_a_failure_leaves_the_document_as_it_was_and_says_why(self):
        view = self.add_view("View", self.tube_with_id("1"))
        undo_count = self.doc.UndoCount
        printed = []
        self.addCleanup(setattr, App.Console, "PrintError", App.Console.PrintError)
        App.Console.PrintError = printed.append
        patch = mock.patch.object(create_piece_table_tool, "write_table", side_effect=RuntimeError("boom"))
        patch.start()
        self.addCleanup(patch.stop)
        self.run_command(view)
        self.assertEqual((self.tables(), self.sheets()), ([], []))
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.status_message(), "Piece Table: boom")
        self.assertEqual("".join(printed), "Piece Table: boom\n")


class TestPieceTableSpanish(PieceTableFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")

    def test_titles_lengths_and_angles_are_spanish(self):
        tube = self.tube_with_id("7", BevelACutY=45.0, BevelBCutY=45.0, BevelBCutX=10.0)
        loose = self.tube_with_id("")
        self.run_command(self.add_view("View", tube, loose))
        self.assertEqual(
            self.rows(self.table().Source),
            [
                ["ID", "Pieza", "Cantidad", "Longitud", "Ángulo de corte 1", "Ángulo de corte 2"],
                ["7", "80x40x2", "1", self.length(tube).replace(".", ","), "45,0 <80", "45,4 <80 + 10,0 <40"],
            ],
        )
        self.assertEqual(
            self.status_message(), "Tabla de piezas creada. Filas: 1. Piezas: 1. Sin ID: 1 (ejecutá Asignar IDs)."
        )

    def test_messages_are_spanish(self):
        view = self.add_view("View", self.tube_with_id("1"))
        self.run_command()
        self.assertEqual(
            self.status_message(), "Tabla de piezas: Hacé clic en una vista de TechDraw (Esc para cancelar)."
        )
        self.press_escape()
        self.assertEqual(self.status_message(), "Tabla de piezas: Cancelado.")
        self.run_command(view)
        self.run_command(view)
        self.assertEqual(self.status_message(), "Tabla de piezas actualizada. Filas: 1. Piezas: 1.")
        self.run_command(self.add_view("Loose", self.tube_with_id("")))
        self.assertEqual(self.status_message(), "Ninguna pieza con ID. Sin ID: 1 (ejecutá Asignar IDs).")


if __name__ == "__main__":
    unittest.main()

import os

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe.create_edit_balloons_tool import (
    apply_in_transaction,
    cancel_view_pick,
    find_page,
    is_usable_view,
    pick_view,
    show_status,
)
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, translate
from freecad.maxproframe.piece_table import table_rows, write_table

COMMAND = "MaxProFrame_CreatePieceTable"


def is_piece_table(obj):
    return obj.TypeId == "TechDraw::DrawViewSpreadsheet" and "SourceViews" in obj.PropertiesList


def find_table(views):
    """The table made before for the same ``views``, in any order, else None."""
    names = sorted(view.Name for view in views)
    for obj in views[0].Document.Objects:
        if is_piece_table(obj) and obj.Source is not None and sorted(obj.SourceViews) == names:
            return obj
    return None


def add_table(page, views):
    """A new sheet, shown on ``page`` by a spreadsheet view that remembers ``views``."""
    doc = page.Document
    sheet = doc.addObject("Spreadsheet::Sheet", "PieceTable")
    table = doc.addObject("TechDraw::DrawViewSpreadsheet", "PieceTableView")
    table.addProperty(
        "App::PropertyStringList", "SourceViews", "MaxProFrame", "Views whose pieces the table lists"
    ).SourceViews = [view.Name for view in views]
    table.Source = sheet
    page.addView(table)
    return table


def create_piece_table(views):
    """List the pieces of ``views`` in their table, made on the page of the first view if they have none yet."""
    title = translate("frameforge", "Piece Table")
    rows, listed, without_id = table_rows(views)
    existing = find_table(views)

    if rows:

        def apply():
            table = existing or add_table(find_page(views[0]), views)
            table.CellStart = "A1"
            table.CellEnd = write_table(table.Source, rows)
            table.Source.recompute()
            table.recompute()

        if not apply_in_transaction(views[0].Document, "Piece Table", title, apply):
            return
        if existing:
            message = translate("frameforge", "Piece table refreshed. Rows: {}. Pieces: {}.")
        else:
            message = translate("frameforge", "Piece table created. Rows: {}. Pieces: {}.")
        message = message.format(len(rows), listed)
    else:
        message = translate("frameforge", "No piece with ID.")

    if without_id:
        message += " " + translate("frameforge", "Without ID: {} (run Populate IDs).").format(len(without_id))
        App.Console.PrintMessage(
            "{}: {}: {}\n".format(title, translate("frameforge", "without ID"), ", ".join(o.Label for o in without_id))
        )
    show_status(message)


class CreatePieceTableCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "piece-table.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_CreatePieceTable", "Piece Table"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_CreatePieceTable",
                "<b>Insert a table of the pieces of TechDraw views</b><br><br>"
                "Select one or more views, or click the button and then a view: one row per ID with the piece, "
                "its quantity, length and cut angles. Run it again on the same views to refresh their table.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        # Any click still awaited is cancelled; if it was this command's, pressing it again only cancels.
        if cancel_view_pick() == COMMAND:
            return
        views = [s for s in Gui.Selection.getSelection() if is_usable_view(s)]
        if views:
            create_piece_table(views)
        else:
            pick_view(
                COMMAND,
                translate("frameforge", "Piece Table"),
                lambda view: create_piece_table([view]),
                translate("frameforge", "A detail view gets no table: click another view (Esc to cancel)."),
            )


add_command(COMMAND, CreatePieceTableCommand())

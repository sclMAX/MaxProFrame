"""The rows of the Piece Table: the pieces shown in TechDraw views, one row per ID, and the sheet holding them."""

import re

from freecad.maxproframe._utils import is_extrudedcutout, is_link, is_profile, is_trimmedbody
from freecad.maxproframe.create_bom import decimal_text, localized
from freecad.maxproframe.create_edit_balloons_tool import piece_id, pieces_of, view_sources
from freecad.maxproframe.cut_ends import cut_ends
from freecad.maxproframe.ff_tools import QT_TRANSLATE_NOOP, translate

# The column titles, in order (translated when written).
HEADER = (
    QT_TRANSLATE_NOOP("frameforge", "ID"),
    QT_TRANSLATE_NOOP("frameforge", "Piece"),
    QT_TRANSLATE_NOOP("frameforge", "Quantity"),
    QT_TRANSLATE_NOOP("frameforge", "Length"),
    QT_TRANSLATE_NOOP("frameforge", "CutAngle1"),
    QT_TRANSLATE_NOOP("frameforge", "CutAngle2"),
)
COLUMNS = "ABCDEF"


def is_cut_piece(obj):
    """A piece with a length and cut ends: a profile, a trim of it or a cutout."""
    return is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj)


def piece_name(obj):
    """The name of the profile of ``obj``, its size: TC80x40x1.5 for Profile_TC80x40x1.5_001_Tr.

    A link takes the name of what it links; an object without size, its label.
    """
    if is_link(obj) and obj.LinkedObject is not None:
        return piece_name(obj.LinkedObject)
    return getattr(obj, "SizeName", "") or obj.Label


def piece_texts(obj):
    """(piece, length, cut angle 1, cut angle 2) of ``obj`` as the BOM writes them, in the FreeCAD language.

    A link has those of the piece it links; what has no cut ends (a Part) only its name.
    """
    target = obj.LinkedObject if is_link(obj) else obj
    if target is None or not is_cut_piece(target):
        return piece_name(obj), "", "", ""
    angle_1, angle_2, _ = cut_ends(target)
    return piece_name(obj), decimal_text(target.Length.Value), localized(angle_1), localized(angle_2)


def id_order(pid):
    """Sort key of an ID: numbers by value (2 before 10), letters as Populate IDs counts them (Z before AA)."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, len(part), part) for part in re.split(r"(\d+)", pid) if part
    )


def table_rows(views):
    """(rows, pieces listed, pieces without ID) of the pieces shown in ``views``.

    One row per ID, in ID order: the ID, the piece, how many pieces have it, the length and both cut angles, as
    texts. A piece shown in several views counts once; a piece without ID gets no row.
    """
    pieces = pieces_of([source for view in views for source in view_sources(view)])
    groups, without_id = {}, []
    for obj in pieces:
        pid = piece_id(obj)
        if pid:
            groups.setdefault(pid, []).append(obj)
        else:
            without_id.append(obj)
    rows = []
    for pid in sorted(groups, key=id_order):
        piece, length, angle_1, angle_2 = piece_texts(groups[pid][0])
        rows.append((pid, piece, str(len(groups[pid])), length, angle_1, angle_2))
    return rows, sum(len(group) for group in groups.values()), without_id


def write_table(sheet, rows):
    """Write the header and ``rows`` on ``sheet``, clearing any other cell; returns the address of the last cell.

    The cells are set and cleared one by one: Undo does not bring back what Sheet.clearAll removed.
    """
    cells = {f"{column}1": translate("frameforge", title) for column, title in zip(COLUMNS, HEADER)}
    for number, row in enumerate(rows, start=2):
        for column, text in zip(COLUMNS, row):
            if text:
                # The quote keeps the text as written: an ID 01, a length 1442,0.
                cells[f"{column}{number}"] = "'" + text
    for address in sheet.getUsedCells():
        if address not in cells:
            sheet.clear(address)
    for address, content in cells.items():
        sheet.set(address, content)
    return f"{COLUMNS[-1]}{len(rows) + 1}"

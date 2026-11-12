import math
import re
from collections import defaultdict
from itertools import groupby

import Assembly
import FreeCAD
import FreeCADGui as Gui
import Part
from PySide import QtCore

from freecad.maxproframe._utils import (
    folded_into_bar,
    is_extrudedcutout,
    is_foldedbar,
    is_fusion,
    is_group,
    is_link,
    is_part,
    is_part_or_part_design,
    is_pattern_link,
    is_profile,
    is_trimmedbody,
    is_unfoldedbar,
)
from freecad.maxproframe.cut_ends import ONE_SQUARE, PARALLELOGRAM, TRAPEZOID, cut_ends
from freecad.maxproframe.ff_tools import QT_TRANSLATE_NOOP, translate

# The marks the angle and Ends columns print, with what they mean (translated when written).
LEGEND = (
    (
        "<",
        QT_TRANSLATE_NOOP(
            "frameforge", "45.0 <80: the angle is seen on the 80 mm faces of the profile (the cut runs across the 80)"
        ),
    ),
    ("+", QT_TRANSLATE_NOOP("frameforge", "Compound cut: the angle seen on each face")),
    (
        TRAPEZOID,
        QT_TRANSLATE_NOOP("frameforge", "Ends: both ends tilted on the same face in opposite directions (trapezoid)"),
    ),
    (
        PARALLELOGRAM,
        QT_TRANSLATE_NOOP("frameforge", "Ends: both ends tilted on the same face the same way (parallelogram)"),
    ),
    (ONE_SQUARE, QT_TRANSLATE_NOOP("frameforge", "Ends: one end square, the other tilted on one face")),
    (
        "@",
        QT_TRANSLATE_NOOP(
            "frameforge",
            "Angle of a TrimmedProfile whose end is not one flat cut -> check length, angles and cut direction",
        ),
    ),
    ("P", QT_TRANSLATE_NOOP("frameforge", "Perfect Cut, you have to notch it !")),
    (
        "*",
        QT_TRANSLATE_NOOP("frameforge", "Angles 1 and 2 are rotated 90° along the edge (end that is not one flat cut)"),
    ),
    ("?", QT_TRANSLATE_NOOP("frameforge", "Can't compute the angle, do it yourself !")),
)
# Sort value of an angle without a number ("@ P", "?"): above every negated number, so it comes last.
NO_NUMBER = math.inf


def traverse_assembly(profiles_data, links_data, obj, parent="", full_parent_path=False):
    p = {}
    if is_fusion(obj):
        for child in obj.Shapes:
            traverse_assembly(
                profiles_data,
                links_data,
                child,
                parent=(f"{parent} / " if full_parent_path else "") + obj.Label,
                full_parent_path=full_parent_path,
            )

    elif is_group(obj):
        for child in obj.Group:
            traverse_assembly(
                profiles_data,
                links_data,
                child,
                parent=(f"{parent} / " if full_parent_path else "") + obj.Label,
                full_parent_path=full_parent_path,
            )

    elif is_part(obj):
        for child in obj.Group:
            # TODO: Fix this ugly way to find children
            # I didn't find another way when into a Part
            # It makes it mandatory to have visible object when generating BOM
            if child.getParentGroup() in (obj, None) and child.Visibility:
                traverse_assembly(
                    profiles_data,
                    links_data,
                    child,
                    parent=(f"{parent} / " if full_parent_path else "") + obj.Label,
                    full_parent_path=full_parent_path,
                )

    elif is_pattern_link(obj):
        # A Profile Pattern copy: one more piece of what it copies, with its ID, under its own name.
        if obj.LinkedObject is not None:
            start = len(profiles_data)
            traverse_assembly(profiles_data, links_data, obj.LinkedObject, parent, full_parent_path)
            for row in profiles_data[start:]:
                row["label"] = obj.Label

    elif is_unfoldedbar(obj) or folded_into_bar(obj):
        # The straight bar and the pieces folded into a bar are that bar.
        pass

    elif is_foldedbar(obj):
        # One piece of its developed length, laser cut: no saw angles, its notches are its cutouts.
        from freecad.maxproframe.folded_bar import warn_if_longer_than_stock

        warn_if_longer_than_stock(obj)
        cat_fam = getattr(obj, "CatalogFamily", None)
        p["parent"] = parent
        p["ID"] = obj.PID
        p["label"] = obj.Label
        p["family"] = cat_fam if cat_fam else obj.Family
        p["size_name"] = obj.SizeName
        p["material"] = obj.Material
        p["length"] = f"{obj.DevelopedLength.Value:.1f}"
        p["cut_angle_1"], p["cut_angle_2"], p["ends"] = "", "", ""
        p["cutout"] = translate("frameforge", "Yes")
        p["approx_weight"] = str(obj.ApproxWeight)
        p["price"] = str(obj.Price)
        p["quantity"] = "1"

        profiles_data.append(p)

    elif is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj):
        p["parent"] = parent
        p["ID"] = obj.PID
        p["label"] = obj.Label
        if obj.CustomProfile:
            family_name = getattr(
                getattr(obj.CustomProfile, "LinkedObject", obj.CustomProfile), "Label", "CustomProfile"
            )
        else:
            cat_fam = getattr(obj, "CatalogFamily", None)
            family_name = cat_fam if cat_fam else getattr(obj, "Family", "N/A")
        p["family"] = family_name
        p["size_name"] = obj.SizeName
        p["material"] = obj.Material
        p["length"] = f"{obj.Length.Value:.1f}"
        p["cut_angle_1"], p["cut_angle_2"], p["ends"] = cut_ends(obj)
        p["cutout"] = translate("frameforge", "Yes") if obj.Cutout else ""
        p["approx_weight"] = str(obj.ApproxWeight)
        p["price"] = str(obj.Price)
        p["quantity"] = "1"

        profiles_data.append(p)

    elif is_link(obj):
        links_data.append(
            {
                "parent": parent,
                "ID": obj.PID,
                "label": obj.Label,
                "part": obj.LinkedObject.Label,
                "quantity": "1",
                "price": getattr(obj.LinkedObject, "Price", "N/A"),
            }
        )

    elif is_part_or_part_design(obj):
        links_data.append(
            {
                "parent": parent,
                "label": obj.Label,
                "part": obj.Label,
                "quantity": "1",
                "price": getattr(obj, "Price", "N/A"),
            }
        )


def group_profiles(profiles_data):
    key_func = lambda x: (
        x["parent"],
        x["family"],
        round(float(x["length"]), 1),
        x["material"],
        x["size_name"],
        # round(float(x["price"]), 1), # TODO: Workaround for Lenght problem
        x["cut_angle_1"],
        x["cut_angle_2"],
        x["ends"],
        x["cutout"],
    )

    profiles_data_sorted = sorted(profiles_data, key=key_func)

    profiles_data_grouped = []

    for k, group in groupby(profiles_data_sorted, key=key_func):
        group = list(group)
        g = group[0]
        d = {}

        d["parent"] = g["parent"]
        d["ID"] = ", ".join(dict.fromkeys(g["ID"] for g in group))
        d["label"] = ", ".join([g["label"] for g in group])
        d["family"] = g["family"]
        d["size_name"] = g["size_name"]
        d["material"] = g["material"]
        d["length"] = g["length"]
        d["cut_angle_1"] = g["cut_angle_1"]
        d["cut_angle_2"] = g["cut_angle_2"]
        d["ends"] = g["ends"]
        d["cutout"] = g["cutout"]
        d["approx_weight"] = g["approx_weight"]
        d["price"] = g["price"]
        d["quantity"] = len(group)

        profiles_data_grouped.append(d)

    return profiles_data_grouped


def group_links(links_data):
    out_list = []
    links_data_grouped = defaultdict(list)

    for lnk in links_data:
        key = (lnk["parent"], lnk["part"], lnk["price"])
        links_data_grouped[key].append(lnk)

    for k, group in links_data_grouped.items():
        ol = {}
        ol["parent"] = k[0]
        ol["ID"] = ", ".join(dict.fromkeys(g.get("ID", "") for g in group))
        ol["label"] = ", ".join([g["label"] for g in group])
        ol["part"] = k[1]
        ol["price"] = k[2]
        ol["quantity"] = len(group)

        out_list.append(ol)

    return out_list


def make_bom(profiles_data, links_data, bom_name="BOM", spreadsheet=None):
    doc = FreeCAD.ActiveDocument

    if spreadsheet is None:
        spreadsheet = doc.addObject("Spreadsheet::Sheet", bom_name)

    spreadsheet.set("A1", translate("frameforge", "Profiles"))

    spreadsheet.set("A2", translate("frameforge", "Parent"))
    spreadsheet.set("B2", translate("frameforge", "ID"))
    spreadsheet.set("C2", translate("frameforge", "Family"))
    spreadsheet.set("D2", translate("frameforge", "SizeName"))
    spreadsheet.set("E2", translate("frameforge", "Length"))
    spreadsheet.set("F2", translate("frameforge", "CutAngle1"))
    spreadsheet.set("G2", translate("frameforge", "CutAngle2"))
    spreadsheet.set("H2", translate("frameforge", "Ends"))
    spreadsheet.set("I2", translate("frameforge", "Drill/Cutout"))
    spreadsheet.set("J2", translate("frameforge", "Quantity"))
    spreadsheet.set("K2", translate("frameforge", "Material"))
    spreadsheet.set("L2", translate("frameforge", "ApproxWeight"))
    spreadsheet.set("M2", translate("frameforge", "Price/U"))
    spreadsheet.set("N2", translate("frameforge", "Name"))

    row = 3

    for prof in profiles_data:
        spreadsheet.set("A" + str(row), prof["parent"])
        spreadsheet.set("B" + str(row), prof["ID"])
        spreadsheet.set("C" + str(row), prof["family"])
        spreadsheet.set("D" + str(row), prof["size_name"])
        spreadsheet.set("E" + str(row), prof["length"])
        spreadsheet.set("F" + str(row), "'" + localized(prof["cut_angle_1"]))
        spreadsheet.set("G" + str(row), "'" + localized(prof["cut_angle_2"]))
        spreadsheet.set("H" + str(row), "'" + prof["ends"])
        spreadsheet.set("I" + str(row), "'" + str(prof["cutout"]))
        spreadsheet.set("J" + str(row), str(prof["quantity"]))
        spreadsheet.set("K" + str(row), prof["material"])
        spreadsheet.set("L" + str(row), prof["approx_weight"])
        spreadsheet.set("M" + str(row), prof["price"])
        spreadsheet.set("N" + str(row), prof["label"])

        row += 1

    if len(links_data) > 0:
        row += 1
        spreadsheet.set("A" + str(row), translate("frameforge", "Parts"))
        row += 1
        spreadsheet.set("A" + str(row), translate("frameforge", "Parent"))
        spreadsheet.set("B" + str(row), translate("frameforge", "ID"))
        spreadsheet.set("C" + str(row), translate("frameforge", "Part/Type"))
        spreadsheet.set("D" + str(row), translate("frameforge", "Price/U"))
        spreadsheet.set("E" + str(row), translate("frameforge", "Quantity"))
        spreadsheet.set("F" + str(row), translate("frameforge", "Name"))
        row += 1

        for lnk in links_data:
            spreadsheet.set("A" + str(row), lnk["parent"])
            # A Part or PartDesign object has no ID.
            spreadsheet.set("B" + str(row), lnk.get("ID", ""))
            spreadsheet.set("C" + str(row), lnk["part"])
            spreadsheet.set("D" + str(row), str(lnk["price"]))
            spreadsheet.set("E" + str(row), str(lnk["quantity"]))
            spreadsheet.set("F" + str(row), lnk["label"])

            row += 1

    write_legend(spreadsheet, row + 2)


def decimal_text(value):
    """``value`` with one decimal and the decimal separator of the FreeCAD language: 1442.0 or 1442,0."""
    locale = QtCore.QLocale()
    locale.setNumberOptions(QtCore.QLocale.OmitGroupSeparator)
    return locale.toString(float(value), "f", 1)


def localized(text):
    """``text`` with the decimal separator of the FreeCAD language in each number: 45.0 <80 or 45,0 <80."""
    point = QtCore.QLocale().decimalPoint()
    return re.sub(r"(?<=\d)\.(?=\d)", lambda _: point, str(text))


def larger_angle_first(prof):
    """Both cut angles of ``prof``, ordered by their leading number, larger first.

    An angle without number ("@ P", "?") goes last; equal numbers keep string order.
    """

    def key(angle):
        number = re.search(r"\d+(?:\.\d+)?", str(angle))
        return (-float(number.group()) if number else NO_NUMBER, str(angle))

    return tuple(sorted((prof["cut_angle_1"], prof["cut_angle_2"]), key=key))


def group_stock_parts(stock):
    """(piece, quantity) of each set of identical pieces (ID, length, angles, ends) of ``stock``, first seen first.

    A piece turned end for end is the same piece: angles are compared larger first.
    A piece without ID keeps its own row: nothing tells it is the same piece as another of its length and angles.
    """
    groups = {}
    for index, cut_part in enumerate(stock.parts):
        prof = cut_part.obj
        key = (prof["ID"] or index, prof["length"], *larger_angle_first(prof), prof["ends"])
        groups.setdefault(key, [prof, 0])[1] += 1
    return [tuple(group) for group in groups.values()]


def identical_bars(stocks):
    """(bar indexes, grouped pieces) of each cutting plan of ``stocks``, first seen first.

    Bars whose grouped pieces (ID, length, angles, ends, quantity) are the same, in any order, share one plan.
    """
    plans = {}
    for index, stock in enumerate(stocks):
        parts = group_stock_parts(stock)
        rows = [(prof["ID"], prof["length"], *larger_angle_first(prof), prof["ends"], qty) for prof, qty in parts]
        plans.setdefault(tuple(sorted(rows)), ([], parts))[0].append(index)
    return list(plans.values())


def write_legend(spreadsheet, row):
    """The Legend title at ``row``, then one row per mark."""
    spreadsheet.set("A" + str(row), translate("frameforge", "Legend"))
    for offset, (mark, text) in enumerate(LEGEND, start=1):
        spreadsheet.set("A" + str(row + offset), "'" + mark)
        spreadsheet.set("B" + str(row + offset), translate("frameforge", text))


def make_cut_list(sorted_stocks, cutlist_name="CutList", spreadsheet=None):
    doc = FreeCAD.ActiveDocument

    if spreadsheet is None:
        spreadsheet = doc.addObject("Spreadsheet::Sheet", cutlist_name)

    spreadsheet.set("A1", translate("frameforge", "Material"))
    spreadsheet.set("B1", translate("frameforge", "Stock"))
    spreadsheet.set("C1", translate("frameforge", "CutPart ID"))
    spreadsheet.set("D1", translate("frameforge", "Length"))
    spreadsheet.set("E1", translate("frameforge", "CutAngle1"))
    spreadsheet.set("F1", translate("frameforge", "CutAngle2"))
    spreadsheet.set("G1", translate("frameforge", "Ends"))
    spreadsheet.set("H1", translate("frameforge", "Quantity"))

    row = 2

    for material, stocks in sorted_stocks.items():
        # Bars cut alike take one block, its title with the number of bars, Stock with their indexes.
        for bars, parts in identical_bars(stocks):
            stock = stocks[bars[0]]
            title = translate("frameforge", "{} / used = {}, left = {}").format(
                material, decimal_text(stock.used), decimal_text(stock.left)
            )
            if len(bars) > 1:
                title += " " + translate("frameforge", "×{} bars").format(len(bars))
            spreadsheet.set("A" + str(row), title)

            for prof, quantity in parts:
                cut_angle_1, cut_angle_2 = larger_angle_first(prof)
                spreadsheet.set("B" + str(row), ", ".join(map(str, bars)))
                spreadsheet.set("C" + str(row), prof["ID"])
                spreadsheet.set("D" + str(row), str(prof["length"]))
                spreadsheet.set("E" + str(row), "'" + localized(cut_angle_1))
                spreadsheet.set("F" + str(row), "'" + localized(cut_angle_2))
                spreadsheet.set("G" + str(row), "'" + prof["ends"])
                spreadsheet.set("H" + str(row), str(quantity))

                row += 1

        row += 1

    row += 1
    spreadsheet.set("A" + str(row), translate("frameforge", "Stock statistics"))
    spreadsheet.set("B" + str(row), translate("frameforge", "Length Used"))
    spreadsheet.set("C" + str(row), translate("frameforge", "Stock Used"))
    spreadsheet.set("D" + str(row), translate("frameforge", "Stock Count"))
    row += 1
    for stocks in sorted_stocks:
        spreadsheet.set("A" + str(row), stocks)
        spreadsheet.set("B" + str(row), f"{sum([s.used for s in sorted_stocks[stocks]])}")
        spreadsheet.set("C" + str(row), f"{sum([s.length for s in sorted_stocks[stocks]])}")
        spreadsheet.set("D" + str(row), f"{len(sorted_stocks[stocks])}")

        row += 1

    write_legend(spreadsheet, row + 1)

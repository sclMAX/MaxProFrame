import os
from collections import Counter

import FreeCAD
import FreeCADGui
import TechDrawGui
from PySide import QtCore, QtGui

import freecad.maxproframe._utils as ffu
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    PROFILESPATH,
    QT_TRANSLATE_NOOP,
    UIPATH,
    add_command,
    translate,
)

# TechDraw PDF Gen


class ExportTechDrawCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "gen_techdraw.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ExportTechDraw", "Export all TechDraw Pages as PDF"),
            "Accel": "M, T",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ExportTechDraw",
                "Export all TechDraw Pages as PDF",
            ),
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        doc = FreeCAD.ActiveDocument

        if doc is None:
            raise RuntimeError("No active document")

        # Output directory
        if doc.FileName:
            out_dir = QtGui.QFileDialog.getExistingDirectory(None, "Export folder", os.path.dirname(doc.FileName))
        else:
            out_dir = FreeCAD.getUserAppDataDir()

        for obj in doc.Objects:
            if obj.TypeId == "TechDraw::DrawPage":
                pdf_name = "".join(c for c in obj.Label if c.isalnum() or c in (" ", ".", "_")).rstrip()
                pdf_path = os.path.join(out_dir, f"{pdf_name}.pdf")

                TechDrawGui.exportPageAsPdf(obj, pdf_path)

                FreeCAD.Console.PrintMessage(f"Exported: {pdf_path}\n")

        FreeCAD.Console.PrintMessage("All TechDraw pages exported.\n")


add_command("MaxProFrame_ExportTechDraw", ExportTechDrawCommand())


class RecomputeFrameForgeObjectsCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "recompute.svg"),
            "MenuText": QT_TRANSLATE_NOOP(
                "MaxProFrame_RecomputeFrameForgeObjects",
                "Recursively recompute all profiles and related MaxProFrame objects",
            ),
            "Accel": "M, R",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_RecomputeFrameForgeObjects",
                "Recursively recompute all profiles and related MaxProFrame objects",
            ),
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        stats = []

        def recursive_recompute(objs):
            for obj in objs:
                if ffu.is_profile(obj) or ffu.is_trimmedbody(obj) or ffu.is_extrudedcutout(obj):
                    recursive_recompute(obj.OutList)

                    FreeCAD.Console.PrintMessage(f"{obj.Label} ...")

                    obj.recompute()

                    stats.append(obj.Label)
                    FreeCAD.Console.PrintMessage("ok\n")

        recursive_recompute(FreeCAD.ActiveDocument.Objects)

        cs = Counter(stats)
        for k in cs:
            FreeCAD.Console.PrintMessage(f"{k} = {cs[k]}\n")
        # FreeCAD.ActiveDocument.recompute()


add_command("MaxProFrame_RecomputeFrameForgeObjects", RecomputeFrameForgeObjectsCommand())

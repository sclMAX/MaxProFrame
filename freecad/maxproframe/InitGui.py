import os

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe.ff_tools import ICONPATH, TRANSLATIONSPATH, translate

# Add translations path
Gui.addLanguagePath(TRANSLATIONSPATH)
Gui.updateLocale()


class MaxProFrame(Gui.Workbench):
    """
    MaxProFrame workbench for FreeCAD.
    """

    import os as _os

    from freecad.maxproframe.ff_tools import ICONPATH as _ICONPATH

    MenuText = "MaxProFrame"
    ToolTip = "Create Profiles, Miters, and Cuts from Sketches and Edges"
    Icon = _os.path.join(_ICONPATH, "metalwb.svg")

    toolbox_drawing = ["Sketcher_NewSketch", "MaxProFrame_ParametricLine"]

    toolbox_maxproframe = [
        "MaxProFrame_CreateProfiles",
        "MaxProFrame_ManageProfileLibraries",
        "MaxProFrame_Notch",
        "MaxProFrame_ExtendCut",
        "MaxProFrame_EndMiter",
        "MaxProFrame_AddExtrudeCutout",
    ]

    toolbox_group = ["Std_Group", "Std_Part"]

    toolbox_part = ["MaxProFrame_Link", "Part_Fuse", "Part_Cut", "PartDesign_Body"]

    toolbox_output = [
        "MaxProFrame_PopulateIDs",
        "MaxProFrame_ResetIDs",
        "MaxProFrame_CreateBalloons",
        "MaxProFrame_RefreshBalloons",
        "MaxProFrame_CreateBOM",
    ]

    toolbox_utilities = ["MaxProFrame_RecomputeFrameForgeObjects", "MaxProFrame_ExportTechDraw"]

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Initialize(self):
        """
        This function is called at the first activation of the workbench.
        here is the place to import all the commands
        """
        from freecad.maxproframe import (
            create_bom_tool,
            create_edit_balloons_tool,
            create_end_miter_tool,
            create_extend_cut_tool,
            create_extruded_cutout_tool,
            create_link,
            create_notch_tool,
            create_profiles_tool,
            edit_profile_tool,
            library_manager_dialog,
            parametric_line,
            populate_ids_tool,
            utilities,
        )
        from freecad.maxproframe.ff_tools import translate

        App.Console.PrintMessage(translate("frameforge", "Switching to MaxProFrame") + "\n")

        self.appendToolbar(translate("frameforge", "Drawing Primitives"), self.toolbox_drawing)
        self.appendMenu(translate("frameforge", "Drawing Primitives"), self.toolbox_drawing)

        self.appendToolbar(translate("frameforge", "MaxProFrame"), self.toolbox_maxproframe)
        self.appendMenu(translate("frameforge", "MaxProFrame"), self.toolbox_maxproframe)

        self.appendToolbar(translate("frameforge", "Profiles Group"), self.toolbox_group)
        self.appendMenu(translate("frameforge", "Profiles Group"), self.toolbox_group)

        self.appendToolbar(translate("frameforge", "Part Primitives"), self.toolbox_part)
        self.appendMenu(translate("frameforge", "Part Primitives"), self.toolbox_part)

        self.appendToolbar(translate("frameforge", "MaxProFrame Output"), self.toolbox_output)
        self.appendMenu(translate("frameforge", "MaxProFrame Output"), self.toolbox_output)

        self.appendToolbar(translate("frameforge", "MaxProFrame Utilities"), self.toolbox_utilities)
        self.appendMenu(translate("frameforge", "MaxProFrame Utilities"), self.toolbox_utilities)

    def Activated(self):
        """
        code which should be computed when a user switch to this workbench
        """
        from freecad.maxproframe.ff_tools import translate

        App.Console.PrintMessage(translate("frameforge", "Workbench MaxProFrame activated.") + "\n")

    def Deactivated(self):
        """
        code which should be computed when this workbench is deactivated
        """
        from freecad.maxproframe.ff_tools import translate

        App.Console.PrintMessage(translate("frameforge", "Workbench MaxProFrame de-activated.") + "\n")


Gui.addWorkbench(MaxProFrame())

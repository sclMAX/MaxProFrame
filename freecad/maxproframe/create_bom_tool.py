import os
from collections import defaultdict

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe._utils import (
    is_extrudedcutout,
    is_foldedbar,
    is_fusion,
    is_group,
    is_link,
    is_part,
    is_profile,
    is_trimmedbody,
)
from freecad.maxproframe.best_fit import CutPart, Stock, best_fit_decreasing
from freecad.maxproframe.create_bom import (
    group_links,
    group_profiles,
    make_bom,
    make_cut_list,
    traverse_assembly,
)
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    PROFILESPATH,
    QT_TRANSLATE_NOOP,
    UIPATH,
    add_command,
    get_param_group,
    translate,
)
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile
from freecad.maxproframe.ui_forms import load_form


class CreateBOMTaskPanel:
    def __init__(self):
        self.form = keep_alive_until_destroyed(load_form(os.path.join(UIPATH, "create_bom.ui")))
        self._translate_form()

        param = get_param_group()
        if not param.IsEmpty():
            self.form.full_parent_path.setChecked(param.GetBool("Full Parent Path", False))
            self.form.include_links_cb.setChecked(param.GetBool("Include Links in BOM", False))
            self.form.group_profiles_cb.setChecked(param.GetBool("Group BOM Items by Material/Size/Family", False))
            self.form.cut_list_cb.setChecked(param.GetBool("Generate Cut List", False))
            self.form.stock_length_sb.setValue(param.GetFloat("Stock Length", 6000.0))
            self.form.kerf_sb.setValue(param.GetFloat("Kerf", 1.0))

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, translate("frameforge", "Create BOM")),
            (form.groupBox.setTitle, translate("frameforge", "BOM")),
            (form.label.setText, translate("frameforge", "BOM Name")),
            (form.full_parent_path.setText, translate("frameforge", "Full Parent Path")),
            (form.include_links_cb.setText, translate("frameforge", "Include Links")),
            (form.group_profiles_cb.setText, translate("frameforge", "Group Profiles / Links")),
            (form.groupBox_2.setTitle, translate("frameforge", "Cut List")),
            (form.cut_list_cb.setText, translate("frameforge", "Generate Cut List")),
            (form.label_2.setText, translate("frameforge", "Stock Material Length")),
            (form.label_3.setText, translate("frameforge", "Kerf")),
        ):
            setter(text)

    def open(self):
        App.Console.PrintMessage(translate("frameforge", "Opening CreateBOM\n"))

        # create a TrimmedProfile object
        App.ActiveDocument.openTransaction("Make BOM")

    def reject(self):
        App.Console.PrintMessage(translate("frameforge", "Rejecting CreateBOM\n"))

        self.clean()
        App.ActiveDocument.abortTransaction()

        return True

    def accept(self):
        sel = Gui.Selection.getSelection()

        bom_spreadsheet = None
        cutlist_spreadsheet = None

        if len(sel) >= 2:
            if sel[0].TypeId == "Spreadsheet::Sheet":
                # TODO : WarningBox
                bom_spreadsheet = sel[0]

            if sel[1].TypeId == "Spreadsheet::Sheet":
                # TODO : WarningBox
                cutlist_spreadsheet = sel[1]

            sel = [s for s in sel if s.TypeId != "Spreadsheet::Sheet"]

        if all(
            [
                (
                    is_fusion(s)
                    or is_part(s)
                    or is_group(s)
                    or is_profile(s)
                    or is_trimmedbody(s)
                    or is_extrudedcutout(s)
                    or is_foldedbar(s)
                    or is_link(s)
                )
                for s in sel
            ]
        ):
            param = get_param_group(writable=True)
            param.SetBool("Full Parent Path", self.form.full_parent_path.isChecked())
            param.SetBool("Include Links in BOM", self.form.include_links_cb.isChecked())
            param.SetBool("Group BOM Items by Material/Size/Family", self.form.group_profiles_cb.isChecked())
            param.SetBool("Generate Cut List", self.form.cut_list_cb.isChecked())
            param.SetFloat("Stock Length", self.form.stock_length_sb.value())
            param.SetFloat("Kerf", self.form.kerf_sb.value())

            if self.form.bom_name_te.text() != "":
                bom_name = self.form.bom_name_te.text()
            elif len(sel) == 1:
                bom_name = f"{sel[0].Label}_BOM"
            else:
                bom_name = "BOM"

            profiles_data = []
            links_data = []
            for obj in sel:
                traverse_assembly(
                    profiles_data, links_data, obj, full_parent_path=self.form.full_parent_path.isChecked()
                )

            if self.form.group_profiles_cb.isChecked():
                bom_data = group_profiles(profiles_data)
                links_data = group_links(links_data)
            else:
                bom_data = profiles_data

            if not self.form.include_links_cb.isChecked():
                links_data = []

            # BOM
            make_bom(bom_data, links_data, bom_name=bom_name, spreadsheet=bom_spreadsheet)

            # Cut List
            if self.form.cut_list_cb.isChecked():
                grouped_profiles = defaultdict(list)
                for p in profiles_data:
                    key = (p["family"], p["material"], p["size_name"])
                    grouped_profiles[key].append(p)

                sorted_stocks = {}
                for k, group in grouped_profiles.items():
                    parts = [CutPart(p["label"], float(p["length"]), self.form.kerf_sb.value(), p) for p in list(group)]

                    sorted_stocks[f"{k[1]}_{k[0]}_{k[2]}"] = best_fit_decreasing(
                        self.form.stock_length_sb.value(), parts
                    )

                make_cut_list(sorted_stocks, cutlist_name=bom_name + "_CutList", spreadsheet=cutlist_spreadsheet)

            App.ActiveDocument.commitTransaction()
            App.ActiveDocument.recompute()

            return True

        else:
            App.ActiveDocument.abortTransaction()
            return False

    def clean(self):
        pass


class CreateBOMCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "bom.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_CreateBOM", "Create BOM"),
            "Accel": "M, B",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_CreateBOM",
                "<b>Create a spreadsheet with profiles</b><br><br>Select fusions or profiles. To update an existing spreadsheet, first select the existing BOM and cut list.",
            ),
        }

    def IsActive(self):
        if App.ActiveDocument:
            if len(Gui.Selection.getSelection()) >= 1:
                return all(
                    [
                        is_fusion(sel)
                        or is_part(sel)
                        or is_group(sel)
                        or is_profile(sel)
                        or is_trimmedbody(sel)
                        or is_extrudedcutout(sel)
                        or is_foldedbar(sel)
                        or is_link(sel)
                        or sel.TypeId == "Spreadsheet::Sheet"
                        for sel in Gui.Selection.getSelection()
                    ]
                )

        return False

    def Activated(self):
        panel = CreateBOMTaskPanel()
        Gui.Control.showDialog(panel)


add_command("MaxProFrame_CreateBOM", CreateBOMCommand())

# Expected behaviour:

# POPULATE
# Number/Letter for Profiles/Links
# - All numbers
# - All letters
# - Number for Profiles, Letters for Link
# - Number for Link, Letters for Profiles

# Allow duplicated numbering
# Keep existing

# Start at specific number/letter
# Fill when available (document)
# Fill when available (selection)
# Start at last of document


# Algorithm:

# - get all documents objects (flat)
# - get all selected objects (flat)


# RESET
# Reset All / Reset Selected if objects are selected


import os
import re
from collections import defaultdict

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import (
    get_profiles_and_links_from_document,
    get_profiles_and_links_from_object,
    is_extrudedcutout,
    is_fusion,
    is_group,
    is_link,
    is_part,
    is_profile,
    is_trimmedbody,
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
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.version import __version__ as ff_version


class PopulateIDsTaskPanel:
    def __init__(self):
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(os.path.join(UIPATH, "populate_ids.ui")))
        self._translate_form()
        self.form.le_first_letter.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression("[A-Za-z]*"), self.form.le_first_letter)
        )

        param = get_param_group()
        if not param.IsEmpty():
            self.form.cb_allow_duplicated.setChecked(param.GetBool("Allow Duplicating IDs", False))
            self.form.cb_group_ids_for_identical.setChecked(param.GetBool("Group IDs", False))
            self.form.cb_include_part_count_in_pid.setChecked(param.GetBool("Include Count", False))
            self.form.cb_keep_existing.setChecked(param.GetBool("Keep Existing IDs", False))
            self.form.cb_numbering_type.setCurrentIndex(param.GetInt("IDs numbering type", 0))
            self.form.cb_numbering_scheme.setCurrentIndex(param.GetInt("IDs numbering scheme", 0))
            self.form.sp_first_number.setValue(param.GetInt("First Number ID", 1))
            self.form.le_first_letter.setText(param.GetString("First Letter ID", "A"))

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, translate("frameforge", "Populate IDs")),
            (form.label.setText, translate("frameforge", "Numbering Type")),
            (form.cb_allow_duplicated.setText, translate("frameforge", "Allow duplicated")),
            (form.cb_group_ids_for_identical.setText, translate("frameforge", "Group profiles ID if identical")),
            (
                form.cb_group_ids_for_identical.setToolTip,
                translate("frameforge", "All identical profiles will share the same ID"),
            ),
            (form.cb_include_part_count_in_pid.setText, translate("frameforge", "Include Part count in PID")),
            (form.cb_keep_existing.setText, translate("frameforge", "Keep existing IDs")),
            (
                form.cb_keep_existing.setToolTip,
                translate("frameforge", "Pieces that already have an ID keep it: only the others are numbered"),
            ),
            (form.label_2.setText, translate("frameforge", "Numbering Scheme")),
            (form.groupBox.setTitle, translate("frameforge", "First indexes")),
            (form.label_3.setText, translate("frameforge", "Start at specific number")),
            (form.label_4.setText, translate("frameforge", "Start at specific letter")),
            (form.label_5.setText, translate("frameforge", "Profiles Prefix")),
            (form.label_6.setText, translate("frameforge", "Links Prefix")),
        ):
            setter(text)
        for combo, texts in (
            (
                form.cb_numbering_type,
                (
                    translate("frameforge", "All Numbers"),
                    translate("frameforge", "All Letters"),
                    translate("frameforge", "Numbers for Profiles, Letters for Links"),
                    translate("frameforge", "Numbers for Links, Letters for Profiles"),
                ),
            ),
            (
                form.cb_numbering_scheme,
                (
                    translate("frameforge", "Fill when available (inside selection)"),
                    translate("frameforge", "Fill when available (whole document)"),
                    translate("frameforge", "Start at current document numbering"),
                    translate("frameforge", "Start at specific number/letter"),
                ),
            ),
        ):
            for index, text in enumerate(texts):
                combo.setItemText(index, text)

    def open(self):
        App.Console.PrintMessage(translate("frameforge", "Opening Populate IDs\n"))

        # create a TrimmedProfile object
        App.ActiveDocument.openTransaction("Populate IDs")

    def reject(self):
        App.Console.PrintMessage(translate("frameforge", "Rejecting Populate IDs\n"))

        self.clean()
        App.ActiveDocument.abortTransaction()

        return True

    def accept(self):
        sel = Gui.Selection.getSelection()

        if all(
            [
                is_fusion(sel)
                or is_part(sel)
                or is_group(sel)
                or is_profile(sel)
                or is_trimmedbody(sel)
                or is_extrudedcutout(sel)
                or is_link(sel)
                for sel in Gui.Selection.getSelection()
            ]
        ):
            # Only "Start at specific number/letter" reads the first letter, and only when letters are used.
            start_letter = self.form.le_first_letter.text().strip()
            uses_letters = self.form.cb_numbering_type.currentIndex() != 0
            starts_at = self.form.cb_numbering_scheme.currentIndex() == 3
            if starts_at and uses_letters and not re.fullmatch("[A-Za-z]+", start_letter):
                self._show_message(translate("frameforge", "Enter a first letter: A to Z only."))
                return False
            self._show_message("")

            param = get_param_group(writable=True)
            param.SetBool("Allow Duplicating IDs", self.form.cb_allow_duplicated.isChecked())
            param.SetBool("Group IDs", self.form.cb_group_ids_for_identical.isChecked())
            param.SetBool("Include Count", self.form.cb_include_part_count_in_pid.isChecked())
            param.SetBool("Keep Existing IDs", self.form.cb_keep_existing.isChecked())
            param.SetInt("IDs numbering type", self.form.cb_numbering_type.currentIndex())
            param.SetInt("IDs numbering scheme", self.form.cb_numbering_scheme.currentIndex())

            param.SetInt("First Number ID", self.form.sp_first_number.value())
            param.SetString("First Letter ID", self.form.le_first_letter.text())

            sel_profiles, sel_links = [], []
            for s in sel:
                get_profiles_and_links_from_object(sel_profiles, sel_links, s)

            doc_profiles, doc_links = get_profiles_and_links_from_document()

            # handle compat here, Link don't have specific proxy
            for l in doc_links:
                if not hasattr(l, "PID"):
                    l.addProperty(
                        "App::PropertyString",
                        "PID",
                        "MaxProFrame",
                        "Profile ID",
                    ).PID = ""

                if not hasattr(l, "MaxProFrameVersion"):
                    l.addProperty(
                        "App::PropertyString",
                        "MaxProFrameVersion",
                        "MaxProFrame",
                        "MaxProFrame version used to create the object",
                    ).MaxProFrameVersion = ff_version

            numbering_type = [
                "all_numbers",
                "all_letters",
                "number_for_profiles_letters_for_links",
                "letters_for_profiles_number_for_links",
            ][self.form.cb_numbering_type.currentIndex()]
            allow_duplicated = self.form.cb_allow_duplicated.isChecked()
            group_ids_for_identical = self.form.cb_group_ids_for_identical.isChecked()
            include_part_count_in_pid = self.form.cb_include_part_count_in_pid.isChecked()
            keep_existing = self.form.cb_keep_existing.isChecked()
            numbering_scheme = ["fill_selection", "fill_document", "continue_document", "start_at"][
                self.form.cb_numbering_scheme.currentIndex()
            ]

            populate_ids(
                sel_profiles,
                sel_links,
                doc_profiles,
                doc_links,
                numbering_type,
                allow_duplicated,
                group_ids_for_identical,
                include_part_count_in_pid,
                keep_existing,
                numbering_scheme,
                start_number=str(self.form.sp_first_number.value()),
                start_letter=start_letter,
            )

            App.ActiveDocument.commitTransaction()
            # App.ActiveDocument.recompute()

            return True

        else:
            App.ActiveDocument.abortTransaction()
            return False

    def _show_message(self, text):
        self.form.message_label.setText(text)
        self.form.message_label.setVisible(bool(text))

    def clean(self):
        pass


class PopulateIDsCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "populate-ids.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_PopulateIDs", "Populate IDs"),
            "Accel": "M, U",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_PopulateIDs",
                "<b>Populate IDs of selected MaxProFrame objects</b><br><br>Select profiles, links, groups or parts.",
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
                        or is_link(sel)
                        for sel in Gui.Selection.getSelection()
                    ]
                )

        return False

    def Activated(self):
        panel = PopulateIDsTaskPanel()
        Gui.Control.showDialog(panel)


class ResetIDsCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "reset-ids.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ResetIDs", "Reset IDs"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ResetIDs",
                "<b>Reset IDs of selected MaxProFrame objects</b><br><br>Select profiles, links, groups or parts.",
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
                        or is_link(sel)
                        for sel in Gui.Selection.getSelection()
                    ]
                )

        return False

    def Activated(self):
        sel = Gui.Selection.getSelection()

        if all(
            [
                is_fusion(sel)
                or is_part(sel)
                or is_group(sel)
                or is_profile(sel)
                or is_trimmedbody(sel)
                or is_extrudedcutout(sel)
                or is_link(sel)
                for sel in Gui.Selection.getSelection()
            ]
        ):

            App.ActiveDocument.openTransaction("Reset IDs")
            sel_profiles, sel_links = [], []
            for s in sel:
                get_profiles_and_links_from_object(sel_profiles, sel_links, s)

            for o in sel_profiles + sel_links:
                o.PID = ""

            App.ActiveDocument.commitTransaction()
            # App.ActiveDocument.recompute()


add_command("MaxProFrame_PopulateIDs", PopulateIDsCommand())
add_command("MaxProFrame_ResetIDs", ResetIDsCommand())

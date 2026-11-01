import os

import FreeCAD as App

from freecad.maxproframe.create_extend_cut_tool import (
    ExtendCutTaskPanel,
    _selected_items,
    make_target_joint,
    show_panel,
    trimmed_body_problem,
)
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, translate


def make_notch_profile(body, target):
    """Notch of ``body`` into the whole ``target`` profile, placed in the body's own container."""
    return make_target_joint(body, (target, ()), "Notch")


class NotchTaskPanel(ExtendCutTaskPanel):
    """The Extend / Cut panel for a Notch: the target is a whole profile and there is no gap.

    A click on any face or edge of a profile picks the whole profile as the target.
    """

    joint = "Notch"
    has_gap = False
    auto_preview_param = "Notch Auto Preview"
    # A notch is a heavy boolean: its preview waits until asked for.
    auto_preview_default = False

    def texts(self):
        return {
            "title": translate("frameforge", "Notch"),
            "edit_title": translate("frameforge", "Edit Notch"),
            "hint": translate("frameforge", "Click the profiles to notch. Ctrl+click drops one."),
            "edit_hint": translate("frameforge", "Click a profile to change the target."),
            "no_target": translate("frameforge", "Click the target profile, or select it in the tree."),
            "missing_target": translate("frameforge", "Select the target profile."),
            "missing_profiles": translate("frameforge", "Select the profiles to notch."),
        }

    def _target_faces(self, obj, subs):
        # The notch copies the whole target: a face or an edge only picks it.
        return (), trimmed_body_problem(None, obj)

    def _make(self, body, gap):
        return make_notch_profile(body, self.target[0])


class NotchCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "corner-end-trim.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_Notch", "Notch"),
            "Accel": "M, C",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_Notch",
                "<b>Notch</b><br><br>Select a target profile, then the profiles to notch into it.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        show_panel(NotchTaskPanel(_selected_items()))


add_command("MaxProFrame_Notch", NotchCommand())

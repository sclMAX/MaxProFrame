import glob
import json
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.frameforge.create_profiles_tool import BaseProfileTaskPanel
from freecad.frameforge.library_manager import get_canonical_family
from freecad.frameforge.profile import ANCHOR_X, ANCHOR_Y, Profile, ViewProviderProfile


class EditProfileTaskPanel(BaseProfileTaskPanel):
    def __init__(self, profile):
        self._initializing = True
        self.profile = profile
        self.dump = profile.dumpContent()
        self._original_appearance = None

        super().__init__()

    def initialize_ui(self):
        self._initializing = True
        super().initialize_ui()

        self.form_proxy.groupBox_5.setEnabled(False)

        self.enable_signals(False)

        target_material = getattr(self.profile, "Material", "")
        cat_fam = getattr(self.profile, "CatalogFamily", None)
        target_family = cat_fam if (cat_fam is not None and cat_fam != "") else getattr(self.profile, "Family", "")
        target_size = getattr(self.profile, "SizeName", "")

        # Reload associated material/family/sizes before setting values; preserve behavior if catalog missing
        if hasattr(self, "profiles") and self.profiles and target_material in self.profiles:
            self.form_proxy.combo_material.setCurrentText(target_material)
            self.form_proxy.combo_family.clear()
            self.form_proxy.combo_family.addItems([f for f in self.profiles[target_material]])
            if target_family in self.profiles[target_material]:
                self.form_proxy.combo_family.setCurrentText(target_family)
                fam_dict = self.profiles[target_material][target_family]
                if isinstance(fam_dict, dict) and "sizes" in fam_dict:
                    self.form_proxy.combo_size.clear()
                    self.form_proxy.combo_size.addItems([s for s in fam_dict["sizes"]])
                    self.form_proxy.combo_size.setCurrentText(target_size)
            else:
                if target_family and self.form_proxy.combo_family.findText(target_family) == -1:
                    self.form_proxy.combo_family.addItem(target_family)
                self.form_proxy.combo_family.setCurrentText(target_family)
                if target_size and self.form_proxy.combo_size.findText(target_size) == -1:
                    self.form_proxy.combo_size.addItem(target_size)
                self.form_proxy.combo_size.setCurrentText(target_size)
        else:
            if target_material and self.form_proxy.combo_material.findText(target_material) == -1:
                self.form_proxy.combo_material.addItem(target_material)
            self.form_proxy.combo_material.setCurrentText(target_material)

            if target_family and self.form_proxy.combo_family.findText(target_family) == -1:
                self.form_proxy.combo_family.addItem(target_family)
            self.form_proxy.combo_family.setCurrentText(target_family)

            if target_size and self.form_proxy.combo_size.findText(target_size) == -1:
                self.form_proxy.combo_size.addItem(target_size)
            self.form_proxy.combo_size.setCurrentText(target_size)

        self.form_proxy.sb_width.setValue(self.profile.ProfileWidth)
        self.form_proxy.sb_height.setValue(self.profile.ProfileHeight)
        self.form_proxy.sb_main_thickness.setValue(self.profile.Thickness)
        self.form_proxy.sb_flange_thickness.setValue(self.profile.ThicknessFlange)
        self.form_proxy.sb_radius1.setValue(self.profile.RadiusLarge)
        self.form_proxy.sb_radius2.setValue(self.profile.RadiusSmall)
        if hasattr(self.form_proxy, "sb_lip_length"):
            lip_val = float(getattr(self.profile, "LipLength", 0.0))
            self.form_proxy.sb_lip_length.setValue(lip_val)
        self.form_proxy.sb_length.setValue(self.profile.ProfileLength)
        self.form_proxy.sb_weight.setValue(self.profile.LinearWeight)
        try:
            self.form_proxy.sb_unitprice.setValue(self.profile.UnitPrice)
        except:
            App.Console.PrintMessage(f"Frameforge : can't find Unit Price for {self.profile.Label}\n")
        self.form_proxy.cb_make_fillet.setChecked(self.profile.MakeFillet)
        if hasattr(self.profile, "AnchorX"):
            ax = ANCHOR_X.index(self.profile.AnchorX) if self.profile.AnchorX in ANCHOR_X else 1
            ay = ANCHOR_Y.index(self.profile.AnchorY) if self.profile.AnchorY in ANCHOR_Y else 1
        else:
            ax = 1 if getattr(self.profile, "CenteredOnWidth", False) else 0
            ay = 1 if getattr(self.profile, "CenteredOnHeight", False) else 0
        self.set_anchor(ax, ay)
        self.set_rotation(getattr(self.profile, "RotationAngle", 0.0))
        self.form_proxy.cb_mirror_h.setChecked(getattr(self.profile, "MirrorH", False))
        self.form_proxy.cb_mirror_v.setChecked(getattr(self.profile, "MirrorV", False))

        family_data = (
            self.profiles.get(target_material, {}).get(target_family)
            if hasattr(self, "profiles") and self.profiles
            else None
        )
        if family_data is not None:
            canonical_family = get_canonical_family(target_family, family_data)
        else:
            canonical_family = getattr(self.profile, "Family", target_family)
        self._update_family_controls(canonical_family)

        # self.form_proxy.cb_combined_bevel.setChecked()

        self.update_image()
        self.enable_signals(True)
        self._initializing = False

    def open(self):
        if getattr(self.profile, "ViewObject", None) is not None:
            self._original_appearance = (
                self.profile.ViewObject.ShapeColor,
                self.profile.ViewObject.Transparency,
            )

        App.ActiveDocument.openTransaction("Edit Profile")

        self.initialize_ui()

        if getattr(self.profile, "ViewObject", None) is not None:
            self.profile.ViewObject.Transparency = 50
            self.profile.ViewObject.ShapeColor = (0.8, 0.2, 0.1)

    def reject(self):
        App.ActiveDocument.abortTransaction()
        Gui.ActiveDocument.resetEdit()

        return True

    def accept(self):
        self.proceed()

        if getattr(self.profile, "ViewObject", None) is not None and self._original_appearance is not None:
            color, transparency = self._original_appearance
            self.profile.ViewObject.ShapeColor = color
            self.profile.ViewObject.Transparency = transparency

        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()
        Gui.ActiveDocument.resetEdit()

        return True

    def proceed(self):
        if getattr(self, "_initializing", False):
            return
        self.update_profile(self.profile)

        self.profile.recompute()

import glob
import json
import os
import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.maxproframe.create_profiles_tool import BaseProfileTaskPanel
from freecad.maxproframe.expression_fields import bind, expression_of, expressions_of, restore_expressions
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import get_canonical_family
from freecad.maxproframe.profile import ANCHOR_X, ANCHOR_Y, Profile, ViewProviderProfile

# Each field takes an expression (Fx) bound to the profile property it edits.
BOUND_FIELDS = (
    ("sb_width", "ProfileWidth"),
    ("sb_height", "ProfileHeight"),
    ("sb_main_thickness", "Thickness"),
    ("sb_flange_thickness", "ThicknessFlange"),
    ("sb_radius1", "RadiusLarge"),
    ("sb_radius2", "RadiusSmall"),
    ("sb_lip_length", "LipLength"),
    ("sb_length", "ProfileLength"),
    ("sb_weight", "LinearWeight"),
    ("sb_unitprice", "UnitPrice"),
    ("sb_offset_x", "OffsetX"),
    ("sb_offset_y", "OffsetY"),
)
# The section a material, family or size change refills from the catalog.
CATALOG_SECTION = (
    "ProfileWidth",
    "ProfileHeight",
    "Thickness",
    "ThicknessFlange",
    "RadiusLarge",
    "RadiusSmall",
    "LipLength",
)


def _value(obj, prop):
    value = getattr(obj, prop)
    return getattr(value, "Value", value)


class EditProfileTaskPanel(BaseProfileTaskPanel):
    def __init__(self, profile):
        self._initializing = True
        self.profile = profile
        self.dump = profile.dumpContent()
        self._original_appearance = None
        self._bound_fields = [(name, prop) for name, prop in BOUND_FIELDS if hasattr(profile, prop)]
        props = [prop for _name, prop in self._bound_fields]
        self._initial_expressions = expressions_of(profile, props)
        self._initial_values = {prop: _value(profile, prop) for prop in props}

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
            App.Console.PrintMessage(f"MaxProFrame: can't find Unit Price for {self.profile.Label}\n")
        self.form_proxy.cb_make_fillet.setChecked(self.profile.MakeFillet)
        if hasattr(self.profile, "AnchorX"):
            ax = ANCHOR_X.index(self.profile.AnchorX) if self.profile.AnchorX in ANCHOR_X else 1
            ay = ANCHOR_Y.index(self.profile.AnchorY) if self.profile.AnchorY in ANCHOR_Y else 1
        else:
            ax = 1 if getattr(self.profile, "CenteredOnWidth", False) else 0
            ay = 1 if getattr(self.profile, "CenteredOnHeight", False) else 0
        self.set_anchor(ax, ay)
        self.set_rotation(getattr(self.profile, "RotationAngle", 0.0))
        offset_x = getattr(self.profile, "OffsetX", None)
        offset_y = getattr(self.profile, "OffsetY", None)
        self.set_offset(
            offset_x.Value if offset_x is not None else 0.0, offset_y.Value if offset_y is not None else 0.0
        )
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
        size_data = family_data.get("sizes", {}).get(target_size) if isinstance(family_data, dict) else None
        self._update_section_size_controls(canonical_family, size_data)

        # self.form_proxy.cb_combined_bevel.setChecked()

        self._update_material_info()
        self.form[0].label_2.setText(
            translate("frameforge", "Profile" if canonical_family == "Custom Profile" else "Size")
        )
        self.update_image()
        for name, prop in self._bound_fields:
            if hasattr(self.form_proxy, name):
                bind(getattr(self.form_proxy, name), self.profile, prop)
        self.enable_signals(True)
        if hasattr(self, "btn_mirror_h"):
            self.btn_mirror_h.setChecked(self.form_proxy.cb_mirror_h.isChecked())
        if hasattr(self, "btn_mirror_v"):
            self.btn_mirror_v.setChecked(self.form_proxy.cb_mirror_v.isChecked())
        if hasattr(self, "btn_pre_extend") and hasattr(self.form_proxy, "cb_pre_extend"):
            self.btn_pre_extend.setChecked(self.form_proxy.cb_pre_extend.isChecked())
        self._initializing = False
        self._refresh_alignment()

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

    def on_size_changed(self, index):
        # The catalog refills the section fields: that changes them, so their expressions go.
        if not getattr(self, "_initializing", False) and self.form_proxy.combo_size.currentText() != "":
            for prop in CATALOG_SECTION:
                if expression_of(self.profile, prop) is not None:
                    self.profile.setExpression(prop, None)
        super().on_size_changed(index)
        self._show_expression_values()

    def _show_expression_values(self):
        """Expression-driven fields show their property, not the catalog value filled over them."""
        for name, prop in self._bound_fields:
            if expression_of(self.profile, prop) is not None and hasattr(self.form_proxy, name):
                field = getattr(self.form_proxy, name)
                blocked = field.blockSignals(True)
                field.setValue(_value(self.profile, prop))
                field.blockSignals(blocked)

    def reject(self):
        self._release_layout_item_wrappers()
        App.ActiveDocument.abortTransaction()
        # Abort undoes the panel; set expressions and values again in case the transaction held nothing.
        changed = restore_expressions(self.profile, self._initial_expressions)
        for prop, value in self._initial_values.items():
            if self._initial_expressions[prop] is None and _value(self.profile, prop) != value:
                setattr(self.profile, prop, value)
                changed = True
        if changed:
            self.profile.Document.recompute()
        Gui.ActiveDocument.resetEdit()

        return True

    def accept(self):
        self.proceed()
        self._release_layout_item_wrappers()

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
        old_family = self._family_label_part()
        old_size = getattr(self.profile, "SizeName", "")
        self.update_profile(self.profile)
        self._replace_part_in_label(old_size, getattr(self.profile, "SizeName", ""))
        self._replace_part_in_label(old_family, self._family_label_part())

        self.profile.recompute()

    def _family_label_part(self):
        """The family as Create Profiles writes it in the label."""
        family = getattr(self.profile, "CatalogFamily", None) or getattr(self.profile, "Family", "")
        return family.replace(" ", "_")

    def _replace_part_in_label(self, old, new):
        """Swap old for new when the label holds it as a whole "_"-separated part."""
        if not old or not new or old == new:
            return
        pattern = rf"(?:^|(?<=_)){re.escape(old)}(?=_|$)"
        matches = list(re.finditer(pattern, self.profile.Label))
        if not matches:
            return
        # Family and size follow the prefix and sketch parts, so replace the last occurrence.
        last = matches[-1]
        label = self.profile.Label
        self.profile.Label = label[: last.start()] + new + label[last.end() :]

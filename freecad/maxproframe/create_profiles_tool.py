import glob
import json
import os
import re
from abc import ABC, abstractmethod

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    PROFILESPATH,
    UIPATH,
    FormProxy,
    add_command,
    get_param_group,
    move_profile_to_parent_if_supported,
    translate,
)
from freecad.maxproframe.library_manager import LibraryManager, get_canonical_family
from freecad.maxproframe.profile import Profile, ViewProviderCustomProfile, ViewProviderProfile
from freecad.maxproframe.section_library import get_or_import_section_sketch


def load_ui_file(path):
    if hasattr(Gui, "PySideUic") and hasattr(Gui.PySideUic, "loadUi"):
        return Gui.PySideUic.loadUi(path)
    from PySide import QtCore, QtUiTools, QtWidgets

    _ = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    f = QtCore.QFile(path)
    if f.open(QtCore.QFile.ReadOnly):
        try:
            loader = QtUiTools.QUiLoader()
            return loader.load(f)
        finally:
            f.close()
    raise RuntimeError(f"Unable to load UI file: {path}")


class BaseProfileTaskPanel(ABC):
    def __init__(self):
        self._objects = {}

        self.form = [
            load_ui_file(os.path.join(UIPATH, "create_profiles1.ui")),
            load_ui_file(os.path.join(UIPATH, "create_profiles2.ui")),
        ]

        self.form_proxy = FormProxy(self.form)

        self.load_data()
        # self.initialize_ui() # Must be call in Child class, AFTER openTransaction

    def load_data(self):
        self.library_manager = LibraryManager()
        self.profiles = self.library_manager.get_all_profiles()

    def enable_signals(self, enable):
        # Block signals during initialization to prevent unintended side effects
        self.form_proxy.combo_material.blockSignals(not enable)
        self.form_proxy.combo_family.blockSignals(not enable)
        self.form_proxy.combo_size.blockSignals(not enable)

        self.form_proxy.cb_make_fillet.blockSignals(not enable)
        self.form_proxy.sb_width.blockSignals(not enable)
        self.form_proxy.sb_height.blockSignals(not enable)
        self.form_proxy.sb_main_thickness.blockSignals(not enable)
        self.form_proxy.sb_flange_thickness.blockSignals(not enable)
        self.form_proxy.sb_radius1.blockSignals(not enable)
        self.form_proxy.sb_radius2.blockSignals(not enable)
        if hasattr(self.form_proxy, "sb_lip_length"):
            self.form_proxy.sb_lip_length.blockSignals(not enable)
        self.form_proxy.sb_length.blockSignals(not enable)
        self.form_proxy.cb_mirror_h.blockSignals(not enable)
        self.form_proxy.cb_mirror_v.blockSignals(not enable)
        self.form_proxy.combo_rotation.blockSignals(not enable)
        for ax in range(3):
            for ay in range(3):
                getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").blockSignals(not enable)

    def initialize_ui(self):
        self._initializing = True
        try:

            def execute_if_has_bool(key, func):
                if key in [k for t, k, v in param.GetContents()]:
                    func(param.GetBool(key))

            # Center anchor radio buttons in grid cells (create_profiles2.ui)
            form2 = self.form[1]
            grid_anchor = form2.group_anchor.layout()
            for ax in range(3):
                for ay in range(3):
                    btn = getattr(form2, f"rb_anchor_{ax}_{ay}")
                    grid_anchor.setAlignment(btn, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

            self.form_proxy.label_image.setPixmap(QtGui.QPixmap(os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")))

            # sig/slot
            self.form_proxy.combo_material.currentIndexChanged.connect(self.on_material_changed)
            self.form_proxy.combo_family.currentIndexChanged.connect(self.on_family_changed)
            self.form_proxy.combo_size.currentIndexChanged.connect(self.on_size_changed)

            self.form_proxy.combo_material.addItems([k for k in self.profiles])

            for deg in ("0", "90", "180", "270"):
                self.form_proxy.combo_rotation.addItem(deg)
            self.form_proxy.combo_rotation.setCurrentIndex(0)

            param = get_param_group()
            if not param.IsEmpty():
                default_material_index = self.form_proxy.combo_material.findText(
                    param.GetString("Default Profile Material")
                )
                if default_material_index > -1:
                    self.form_proxy.combo_material.setCurrentIndex(default_material_index)

                    default_family_index = self.form_proxy.combo_family.findText(
                        param.GetString("Default Profile Family")
                    )
                    if default_family_index > -1:
                        self.form_proxy.combo_family.setCurrentIndex(default_family_index)

                        default_size_index = self.form_proxy.combo_size.findText(
                            param.GetString("Default Profile Size")
                        )
                        if default_size_index > -1:
                            self.form_proxy.combo_size.setCurrentIndex(default_size_index)

                execute_if_has_bool("Default Sketch in Name", self.form_proxy.cb_sketch_in_name.setChecked)
                execute_if_has_bool("Default Family in Name", self.form_proxy.cb_family_in_name.setChecked)
                execute_if_has_bool("Default Size in Name", self.form_proxy.cb_size_in_name.setChecked)
                execute_if_has_bool(
                    "Default Prefix Profile in Name", self.form_proxy.cb_prefix_profile_in_name.setChecked
                )
                execute_if_has_bool("Default Make Fillet", self.form_proxy.cb_make_fillet.setChecked)
                execute_if_has_bool("Default Mirror Horizontally", self.form_proxy.cb_mirror_h.setChecked)
                execute_if_has_bool("Default Mirror Vertically", self.form_proxy.cb_mirror_v.setChecked)
                execute_if_has_bool("Default Pre Extend", self.form_proxy.cb_pre_extend.setChecked)
                keys = [k for t, k, v in param.GetContents()]
                if "Default AnchorX" in keys:
                    ax = max(0, min(2, param.GetInt("Default AnchorX", 1)))
                    ay = max(0, min(2, param.GetInt("Default AnchorY", 1)))
                    self.set_anchor(ax, ay)
                elif "Default Width Centered" in keys or "Default Height Centered" in keys:
                    ax = 1 if param.GetBool("Default Width Centered", False) else 0
                    ay = 1 if param.GetBool("Default Height Centered", False) else 0
                    self.set_anchor(ax, ay)
                if "Default RotationAngle" in keys:
                    try:
                        val = float(param.GetString("Default RotationAngle", "0"))
                        self.form_proxy.combo_rotation.setCurrentText(str(int(val) if val == int(val) else val))
                    except (TypeError, ValueError):
                        self.form_proxy.combo_rotation.setCurrentText("0")
                execute_if_has_bool("Default Centered Bevel", self.form_proxy.cb_combined_bevel.setChecked)

            self.form_proxy.cb_make_fillet.stateChanged.connect(self.on_cb_make_fillet_changed)

            self.form_proxy.cb_mirror_h.stateChanged.connect(self.on_input_changed)
            self.form_proxy.cb_mirror_v.stateChanged.connect(self.on_input_changed)
            self.form_proxy.cb_pre_extend.stateChanged.connect(self.on_input_changed)
            self.form_proxy.combo_rotation.currentIndexChanged.connect(self.on_input_changed)
            for ax in range(3):
                for ay in range(3):
                    getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").clicked.connect(self.on_input_changed)

            self.form_proxy.sb_width.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_height.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_main_thickness.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_flange_thickness.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_radius1.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_radius2.valueChanged.connect(self.on_input_changed)
            if hasattr(self.form_proxy, "sb_lip_length"):
                self.form_proxy.sb_lip_length.valueChanged.connect(self.on_input_changed)
            self.form_proxy.sb_length.valueChanged.connect(self.on_input_changed)

            self.form_proxy.cb_sketch_in_name.stateChanged.connect(self.on_input_changed)
            self.form_proxy.cb_family_in_name.stateChanged.connect(self.on_input_changed)
            self.form_proxy.cb_size_in_name.stateChanged.connect(self.on_input_changed)
            self.form_proxy.cb_prefix_profile_in_name.stateChanged.connect(self.on_input_changed)
        finally:
            self._initializing = False

    def on_input_changed(self):
        self.proceed()

    def _update_family_controls(self, canonical_family):
        is_c = canonical_family == "C"
        if hasattr(self.form_proxy, "sb_lip_length"):
            self.form_proxy.sb_lip_length.setVisible(is_c)
        if hasattr(self.form_proxy, "label_lip_length"):
            self.form_proxy.label_lip_length.setText(translate("frameforge", "Lip Length"))
            self.form_proxy.label_lip_length.setVisible(is_c)

        if hasattr(self.form_proxy, "label_8"):
            if is_c:
                self.form_proxy.label_8.setText(translate("frameforge", "Exterior radius"))
            else:
                self.form_proxy.label_8.setText(translate("frameforge", "Large Radius"))

        if hasattr(self.form_proxy, "label_7"):
            self.form_proxy.label_7.setVisible(not is_c)
        if hasattr(self.form_proxy, "sb_flange_thickness"):
            self.form_proxy.sb_flange_thickness.setVisible(not is_c)
        if hasattr(self.form_proxy, "label_9"):
            self.form_proxy.label_9.setVisible(not is_c)
        if hasattr(self.form_proxy, "sb_radius2"):
            self.form_proxy.sb_radius2.setVisible(not is_c)

    def get_anchor(self):
        """Return (anchor_x, anchor_y) 0=left/bottom, 1=center, 2=right/top."""
        for ax in range(3):
            for ay in range(3):
                if getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").isChecked():
                    return (ax, ay)
        return (1, 1)

    def set_anchor(self, anchor_x, anchor_y):
        ax = max(0, min(2, anchor_x))
        ay = max(0, min(2, anchor_y))
        getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").setChecked(True)

    def get_rotation(self):
        """Return rotation angle in degrees (float)."""
        try:
            return float(self.form_proxy.combo_rotation.currentText())
        except (TypeError, ValueError):
            return 0.0

    def set_rotation(self, degrees):
        t = str(int(degrees) if degrees == int(degrees) else degrees)
        i = self.form_proxy.combo_rotation.findText(t)
        if i >= 0:
            self.form_proxy.combo_rotation.setCurrentIndex(i)
        else:
            self.form_proxy.combo_rotation.setCurrentText(t)

    def on_material_changed(self, index):
        material = str(self.form_proxy.combo_material.currentText())

        self.enable_signals(False)

        self.form_proxy.combo_family.clear()
        self.form_proxy.combo_family.addItems([f for f in self.profiles[material]])

        self.enable_signals(True)

        self.form_proxy.combo_family.setCurrentIndex(0)
        self.on_family_changed(None)

    def on_family_changed(self, index):
        material = str(self.form_proxy.combo_material.currentText())
        family = str(self.form_proxy.combo_family.currentText())

        family_data = (
            self.profiles.get(material, {}).get(family) if hasattr(self, "profiles") and self.profiles else None
        )
        canonical = get_canonical_family(family, family_data)
        self._update_family_controls(canonical)

        is_custom = canonical == "Custom Profile"

        fillet_val = False if is_custom else bool(self.profiles.get(material, {}).get(family, {}).get("fillet", False))
        self.form_proxy.cb_make_fillet.setChecked(fillet_val)
        self.form_proxy.cb_make_fillet.setEnabled(False if is_custom else fillet_val)

        self.update_image()

        fam_dict = self.profiles.get(material, {}).get(family, {})
        norm_val = fam_dict.get("norm", "Custom" if is_custom else "")
        unit_val = fam_dict.get("unit", "Metric Units" if is_custom else "")

        self.form_proxy.label_norm.setText(norm_val)
        self.form_proxy.label_unit.setText(unit_val)

        self.form_proxy.combo_size.blockSignals(True)
        self.form_proxy.combo_size.clear()
        sizes = fam_dict.get("sizes", {})
        self.form_proxy.combo_size.addItems([s for s in sizes])
        self.form_proxy.combo_size.blockSignals(False)

        self.form_proxy.combo_size.setCurrentIndex(0)
        self.on_size_changed(None)

    def on_size_changed(self, index):
        material = str(self.form_proxy.combo_material.currentText())
        family = str(self.form_proxy.combo_family.currentText())
        size = str(self.form_proxy.combo_size.currentText())

        if size != "":
            family_dict = self.profiles.get(material, {}).get(family, {})
            canonical = get_canonical_family(family, family_data=family_dict)
            profile = family_dict.get("sizes", {}).get(size, {})

            SETTING_MAP = {
                "Height": self.form_proxy.sb_height,
                "Width": self.form_proxy.sb_width,
                "Thickness": self.form_proxy.sb_main_thickness,
                "Flange Thickness": self.form_proxy.sb_flange_thickness,
                "Radius1": self.form_proxy.sb_radius1,
                "Radius2": self.form_proxy.sb_radius2,
                "Weight": self.form_proxy.sb_weight,
            }
            if hasattr(self.form_proxy, "sb_lip_length"):
                SETTING_MAP["Lip Length"] = self.form_proxy.sb_lip_length

            self.enable_signals(False)

            self.form_proxy.sb_height.setEnabled(False)
            self.form_proxy.sb_height.setValue(0.0)
            self.form_proxy.sb_width.setEnabled(False)
            self.form_proxy.sb_width.setValue(0.0)
            self.form_proxy.sb_main_thickness.setEnabled(False)
            self.form_proxy.sb_main_thickness.setValue(0.0)
            self.form_proxy.sb_flange_thickness.setEnabled(False)
            self.form_proxy.sb_flange_thickness.setValue(0.0)
            self.form_proxy.sb_radius1.setEnabled(False)
            self.form_proxy.sb_radius1.setValue(0.0)
            self.form_proxy.sb_radius2.setEnabled(False)
            self.form_proxy.sb_radius2.setValue(0.0)
            if hasattr(self.form_proxy, "sb_lip_length"):
                self.form_proxy.sb_lip_length.setEnabled(False)
                self.form_proxy.sb_lip_length.setValue(0.0)
            self.form_proxy.sb_weight.setEnabled(False)
            self.form_proxy.sb_weight.setValue(0.0)

            if canonical == "Custom Profile":
                GEOMETRY_METADATA = {"asset_path", "object_name", "asset_id", "Area", "Size"}
                for s in profile:
                    if s in GEOMETRY_METADATA:
                        continue
                    if s in SETTING_MAP:
                        sb = SETTING_MAP[s]
                        try:
                            sb.setValue(float(profile[s]))
                        except (ValueError, TypeError):
                            pass
                        sb.setEnabled(False)
                    else:
                        raise ValueError("Setting Unkown")
            else:
                for s in profile:
                    if s == "Size":
                        continue

                    if s not in SETTING_MAP:
                        raise ValueError("Setting Unkown")

                    sb = SETTING_MAP[s]
                    sb.setEnabled(True)

                    sb.setValue(float(profile[s]))

            self.enable_signals(True)
            self.on_input_changed()

    def on_cb_make_fillet_changed(self, state):
        self.update_image()
        self.on_input_changed()

    def update_image(self):
        material = str(self.form_proxy.combo_material.currentText())
        family_key = str(self.form_proxy.combo_family.currentText())

        family_data = (
            self.profiles.get(material, {}).get(family_key) if hasattr(self, "profiles") and self.profiles else None
        )
        if family_data is not None:
            canonical_family = get_canonical_family(family_key, family_data)
        else:
            profile = getattr(self, "profile", None)
            if profile is not None:
                saved_catalog_family = getattr(profile, "CatalogFamily", None) or getattr(profile, "Family", "")
                if family_key == saved_catalog_family and hasattr(profile, "Family") and profile.Family:
                    canonical_family = profile.Family
                else:
                    canonical_family = get_canonical_family(family_key, None)
            else:
                canonical_family = get_canonical_family(family_key, None)

        img_name = canonical_family.replace(" ", "_")
        if self.form_proxy.cb_make_fillet.isChecked():
            img_name += "_Fillet"
        img_name += ".png"

        # Check material-specific image directory first, fallback to Metal, then Warehouse.png
        img_path = os.path.join(PROFILEIMAGES_PATH, material, img_name)
        if not os.path.exists(img_path):
            img_path = os.path.join(PROFILEIMAGES_PATH, "Metal", img_name)
        if not os.path.exists(img_path):
            img_path = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")

        self.current_image_path = img_path
        self.form_proxy.label_image.setPixmap(QtGui.QPixmap(img_path))

    def update_profile(self, profile):
        material_name = self.form_proxy.combo_material.currentText()
        selected_family = self.form_proxy.combo_family.currentText()
        family_data = (
            self.profiles.get(material_name, {}).get(selected_family)
            if hasattr(self, "profiles") and self.profiles
            else None
        )
        if family_data is not None:
            canonical_family = get_canonical_family(selected_family, family_data)
        else:
            # Catalog unavailable or missing family entry in present library:
            # preserve saved canonical Family when selected identity unchanged, without guessing suffix
            saved_catalog_family = getattr(profile, "CatalogFamily", None) or getattr(profile, "Family", "")
            if selected_family == saved_catalog_family and hasattr(profile, "Family") and profile.Family:
                canonical_family = profile.Family
            else:
                canonical_family = get_canonical_family(selected_family, None)

        kwargs = {
            "init_mirror_h": self.form_proxy.cb_mirror_h.isChecked(),
            "init_mirror_v": self.form_proxy.cb_mirror_v.isChecked(),
            "init_rotation": self.get_rotation(),
            "catalog_family": selected_family,
        }
        if canonical_family == "Custom Profile":
            folder_root = self.library_manager._get_registered_folder(material_name)
            size_name = self.form_proxy.combo_size.currentText()
            size_data = family_data.get("sizes", {}).get(size_name, {}) if isinstance(family_data, dict) else {}
            asset_path = size_data.get("asset_path")
            object_name = size_data.get("object_name", "Section")
            asset_id = size_data.get("asset_id", "")
            if folder_root and asset_path:
                target_doc = (
                    getattr(profile, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument
                )
                pre_sketch_names = {
                    o.Name
                    for o in getattr(target_doc, "Objects", [])
                    if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("Sketcher::SketchObject")
                }
                local_sk = get_or_import_section_sketch(
                    library_root=folder_root,
                    asset_path=asset_path,
                    object_name=object_name,
                    target_doc=target_doc,
                    asset_id=asset_id,
                    profile_code=size_name,
                )
                if local_sk is not None and local_sk.Name not in pre_sketch_names:
                    if hasattr(self, "_session_imported_sketches"):
                        self._session_imported_sketches.add((target_doc.Name, local_sk.Name))
                if local_sk is not None:
                    profile.CustomProfile = local_sk
        elif hasattr(profile, "CustomProfile") and profile.CustomProfile is not None:
            profile.CustomProfile = None

        if canonical_family == "C" and hasattr(self.form_proxy, "sb_lip_length"):
            kwargs["init_lip_length"] = self.form_proxy.sb_lip_length.value()

        profile.Proxy.set_properties(
            profile,
            self.form_proxy.sb_width.value(),
            self.form_proxy.sb_height.value(),
            self.form_proxy.sb_main_thickness.value(),
            self.form_proxy.sb_flange_thickness.value(),
            self.form_proxy.sb_radius1.value(),
            self.form_proxy.sb_radius2.value(),
            self.form_proxy.sb_length.value(),
            self.form_proxy.sb_weight.value(),
            self.form_proxy.sb_unitprice.value(),
            self.form_proxy.cb_make_fillet.isChecked(),  # and self.form_proxy.family.currentText() not in ["Flat Sections", "Square", "Round Bar"],
            *self.get_anchor(),
            material_name,
            canonical_family,
            self.form_proxy.combo_size.currentText(),
            **kwargs,
        )

    @abstractmethod
    def proceed(self):
        pass

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def reject(self):
        return True

    @abstractmethod
    def accept(self):
        return True


class CreateProfileTaskPanel(BaseProfileTaskPanel):
    def __init__(self):
        self._session_imported_sketches = set()
        self._target_doc = None
        self._has_pending_changes = False
        super().__init__()

    @property
    def btn_apply(self):
        if "btn_apply" in self.form_proxy.members:
            return self.form_proxy.btn_apply
        return None

    @property
    def label_apply_status(self):
        if "label_apply_status" in self.form_proxy.members:
            return self.form_proxy.label_apply_status
        return None

    def initialize_ui(self):
        super().initialize_ui()
        if "btn_apply" in self.form_proxy.members:
            self.form_proxy.btn_apply.setText(translate("frameforge", "Apply"))
            self.form_proxy.btn_apply.setToolTip(translate("frameforge", "Apply changes and update preview"))
            self.form_proxy.btn_apply.clicked.connect(self.apply)
        if "groupBox_apply" in self.form_proxy.members:
            self.form_proxy.groupBox_apply.setTitle(translate("frameforge", "Preview"))
        self._set_initial_state()

    def _set_initial_state(self):
        self._has_pending_changes = False
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "No preview"))

    def _set_pending_state(self):
        self._has_pending_changes = True
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "Unapplied changes"))

    def _set_applied_state(self):
        self._has_pending_changes = False
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "Applied"))

    def on_input_changed(self):
        if getattr(self, "_initializing", False):
            return
        self._set_pending_state()

    def open(self):
        self._session_imported_sketches = set()
        self._target_doc = getattr(App, "ActiveDocument", None)

        App.ActiveDocument.openTransaction("Add Profile")

        self.initialize_ui()

        self.update_selection()
        self._set_initial_state()

    def reject(self):
        self.clean()

        App.ActiveDocument.abortTransaction()

        if hasattr(self, "_session_imported_sketches"):
            for doc_name, sk_name in list(self._session_imported_sketches):
                doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
                if doc is not None and hasattr(doc, "getObject") and doc.getObject(sk_name) is not None:
                    try:
                        doc.removeObject(sk_name)
                    except Exception:
                        pass
            self._session_imported_sketches.clear()

        self._objects.clear()

        return True

    def apply(self):
        has_sel = len(Gui.Selection.getSelectionEx()) if hasattr(Gui, "Selection") else 0
        if has_sel or self.form_proxy.sb_length.value() > 0:
            self.proceed()
            self._set_applied_state()
            return True
        else:
            App.Console.PrintMessage(translate("frameforge", "Select Edges or set Length to create a profile\n"))

            diag = QtGui.QMessageBox(
                QtGui.QMessageBox.Warning,
                "Create Profile",
                translate("frameforge", "Select Edges or set Length to create a profile"),
            )
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            diag.exec_()

            return False

    def accept(self):
        has_sel = len(Gui.Selection.getSelectionEx()) if hasattr(Gui, "Selection") else 0
        if has_sel or self.form_proxy.sb_length.value() > 0:
            App.Console.PrintMessage(translate("frameforge", "Accepting CreateProfile\n"))

            param = get_param_group(writable=True)
            param.SetString("Default Profile Material", self.form_proxy.combo_material.currentText())
            param.SetString("Default Profile Family", self.form_proxy.combo_family.currentText())
            param.SetString("Default Profile Size", self.form_proxy.combo_size.currentText())

            param.SetBool("Default Sketch in Name", self.form_proxy.cb_sketch_in_name.isChecked())
            param.SetBool("Default Family in Name", self.form_proxy.cb_family_in_name.isChecked())
            param.SetBool("Default Size in Name", self.form_proxy.cb_size_in_name.isChecked())
            param.SetBool("Default Prefix Profile in Name", self.form_proxy.cb_prefix_profile_in_name.isChecked())

            param.SetBool("Default Make Fillet", self.form_proxy.cb_make_fillet.isChecked())
            param.SetBool("Default Mirror Horizontally", self.form_proxy.cb_mirror_h.isChecked())
            param.SetBool("Default Mirror Vertically", self.form_proxy.cb_mirror_v.isChecked())
            param.SetBool("Default Pre Extend", self.form_proxy.cb_pre_extend.isChecked())

            ax, ay = self.get_anchor()
            param.SetInt("Default AnchorX", ax)
            param.SetInt("Default AnchorY", ay)
            param.SetString("Default RotationAngle", self.form_proxy.combo_rotation.currentText())
            param.SetBool("Default Centered Bevel", self.form_proxy.cb_combined_bevel.isChecked())

            param.RemBool("Default Reverse Attachement")

            self.proceed()
            self.clean()

            if hasattr(self, "_session_imported_sketches"):
                self._session_imported_sketches.clear()

            for o in self._objects.values():
                if getattr(o, "ViewObject", None) is not None:
                    o.ViewObject.Transparency = 0
                    o.ViewObject.ShapeColor = (0.44, 0.47, 0.5)

            App.ActiveDocument.commitTransaction()
            App.ActiveDocument.recompute()

            return True

        else:
            App.Console.PrintMessage(
                translate("frameforge", "Not Accepting CreateProfile\nSelect Edges or set Length\n")
            )

            diag = QtGui.QMessageBox(
                QtGui.QMessageBox.Warning,
                "Create Profile",
                translate("frameforge", "Select Edges or set Length to create a profile"),
            )
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            diag.exec_()

            return False

    def clean(self):
        if hasattr(Gui, "Selection"):
            Gui.Selection.removeObserver(self)
            Gui.Selection.removeSelectionGate()

    def _clean_unreferenced_session_sources(self):
        if not hasattr(self, "_session_imported_sketches") or not self._session_imported_sketches:
            return

        active_referenced_names = set()
        for prof in self._objects.values():
            if prof is None:
                continue
            cp = getattr(prof, "CustomProfile", None)
            if cp is not None and hasattr(cp, "Name"):
                active_referenced_names.add(cp.Name)

        to_remove = []
        for doc_name, sk_name in list(self._session_imported_sketches):
            doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
            if doc is None and doc_name in App.listDocuments():
                doc = App.listDocuments()[doc_name]
            if doc is None:
                to_remove.append((doc_name, sk_name))
                continue

            sk_obj = doc.getObject(sk_name)
            if sk_obj is None:
                to_remove.append((doc_name, sk_name))
                continue

            if sk_name in active_referenced_names:
                continue

            in_list = getattr(sk_obj, "InList", []) or []
            active_in_list = []
            for ref in in_list:
                try:
                    if ref is None or not hasattr(ref, "Name"):
                        continue
                    ref_doc = getattr(ref, "Document", None) or doc
                    if ref_doc is None or not hasattr(ref_doc, "getObject"):
                        continue
                    if hasattr(ref_doc, "Name") and hasattr(App, "listDocuments"):
                        if ref_doc.Name not in App.listDocuments():
                            continue
                    if ref_doc.getObject(ref.Name) is not None:
                        active_in_list.append(ref)
                except Exception:
                    pass
            if active_in_list:
                continue

            try:
                doc.removeObject(sk_name)
            except Exception:
                pass
            to_remove.append((doc_name, sk_name))

        for item in to_remove:
            self._session_imported_sketches.discard(item)

    def proceed(self):
        if getattr(self, "_initializing", False):
            return

        seen_profiles = []

        selection_list = Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else []

        p_name = "Profile_" if self.form_proxy.cb_prefix_profile_in_name.isChecked() else ""

        if len(selection_list) == 1 and self.form_proxy.cb_sketch_in_name.isChecked():
            sketch_sel = selection_list[0]

            p_name += sketch_sel.Object.Name + "_"

        if self.form_proxy.cb_family_in_name.isChecked():
            p_name += self.form_proxy.combo_family.currentText().replace(" ", "_") + "_"

        if self.form_proxy.cb_size_in_name.isChecked():
            p_name += self.form_proxy.combo_size.currentText() + "_"

        p_name += "000"

        if len(selection_list):
            # create part or group and
            container = None
            if self.form_proxy.rb_profiles_in_part.isChecked():
                container = App.activeDocument().addObject("App::Part", "Part")
            # elif self.form_proxy.rb_profiles_in_group.isChecked(): # not working
            #     container = App.activeDocument().addObject('App::DocumentObjectGroup','Group')

            # creates profiles
            for sketch_sel in selection_list:
                # move the sketch inside the container
                if container:
                    container.addObject(sketch_sel.Object)

                if len(sketch_sel.SubElementNames) > 0:
                    edges = sketch_sel.SubElementNames
                else:  # use on the whole sketch
                    edges = [f"Edge{idx + 1}" for idx, e in enumerate(sketch_sel.Object.Shape.Edges)]

                for i, edge in enumerate(edges):
                    k = self.create_or_update_profile(sketch_sel.Object, edge, p_name)
                    seen_profiles.append(k)

        elif self.form_proxy.sb_length.value() > 0:
            k = self.create_or_update_profile(None, None, p_name)
            seen_profiles.append(k)

        for k in list(self._objects.keys()):
            o = self._objects[k]

            if k in seen_profiles:
                o.recompute()

            else:
                doc = getattr(o, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument
                try:
                    doc.removeObject(o.Name)
                except Exception:
                    pass
                del self._objects[k]

        self._clean_unreferenced_session_sources()

    def has_name_prefix(self, internal_name, target_str):
        pattern = r"\d+$"

        prefix_obj = re.sub(pattern, "", internal_name)
        prefix_target = re.sub(pattern, "", target_str)

        return prefix_obj == prefix_target

    def create_or_update_profile(self, sketch, edge, name):
        key = (sketch, edge)

        if key in self._objects:
            o = self._objects[key]
            if self.has_name_prefix(o.Name, name):
                self.update_profile(o)

            else:
                # Create the new profile first BEFORE removing the old one!
                # If creating the new profile fails, the old preview object is preserved.
                new_o = self.make_profile(sketch, edge, name)
                doc = getattr(o, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument
                try:
                    doc.removeObject(o.Name)
                except Exception:
                    pass
                self._objects[key] = new_o

        else:
            o = self.make_profile(sketch, edge, name)
            self._objects[key] = o

        return key

    def make_profile(self, sketch, edge, name):
        material_name = self.form_proxy.combo_material.currentText()
        selected_family = self.form_proxy.combo_family.currentText()
        family_data = (
            self.profiles.get(material_name, {}).get(selected_family)
            if hasattr(self, "profiles") and self.profiles
            else None
        )
        canonical_family = get_canonical_family(selected_family, family_data)

        # Validate and resolve/import custom section sketch BEFORE creating profile object
        custom_profile_sketch = None
        if canonical_family == "Custom Profile":
            size_name = self.form_proxy.combo_size.currentText()
            size_data = family_data.get("sizes", {}).get(size_name, {}) if isinstance(family_data, dict) else {}
            folder_root = self.library_manager._get_registered_folder(material_name)
            asset_path = size_data.get("asset_path")
            object_name = size_data.get("object_name", "Section")
            asset_id = size_data.get("asset_id", "")
            if folder_root and asset_path:
                target_doc = (
                    getattr(sketch, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument
                )
                pre_sketch_names = {
                    obj.Name
                    for obj in getattr(target_doc, "Objects", [])
                    if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
                }
                custom_profile_sketch = get_or_import_section_sketch(
                    library_root=folder_root,
                    asset_path=asset_path,
                    object_name=object_name,
                    target_doc=target_doc,
                    asset_id=asset_id,
                    profile_code=size_name,
                )
                if custom_profile_sketch is not None and custom_profile_sketch.Name not in pre_sketch_names:
                    if hasattr(self, "_session_imported_sketches"):
                        self._session_imported_sketches.add((target_doc.Name, custom_profile_sketch.Name))

        # Create an object in current document
        obj = None
        try:
            target_doc = getattr(sketch, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument
            obj = target_doc.addObject("Part::FeaturePython", name)
            obj.addExtension("Part::AttachExtensionPython")

            if getattr(obj, "ViewObject", None) is not None:
                obj.ViewObject.Transparency = 80
                obj.ViewObject.ShapeColor = (0.0, 0.8, 0.0)

            # move it to the sketch's parent if possible
            if sketch is not None and len(sketch.Parents) > 0:
                sk_parent = sketch.Parents[-1][0]
                move_profile_to_parent_if_supported(obj, sk_parent)

            if sketch is not None and edge is not None:
                # Tuple assignment for edge
                feature = sketch
                link_sub = (feature, (edge))
                obj.MapMode = "NormalToEdge"

                try:
                    obj.AttachmentSupport = (feature, edge)
                except AttributeError:  # for Freecad <= 0.21 support
                    obj.Support = (feature, edge)

            else:
                link_sub = None

            init_offset = 0.0
            if self.form_proxy.cb_pre_extend.isChecked():
                init_offset = max(self.form_proxy.sb_width.value(), self.form_proxy.sb_height.value())

            obj.MapPathParameter = 1

            kwargs = {
                "init_mirror_h": self.form_proxy.cb_mirror_h.isChecked(),
                "init_mirror_v": self.form_proxy.cb_mirror_v.isChecked(),
                "init_rotation": self.get_rotation(),
                "init_offset_a": init_offset,
                "init_offset_b": init_offset,
                "catalog_family": selected_family,
            }
            if canonical_family == "Custom Profile" and custom_profile_sketch is not None:
                kwargs["custom_profile"] = custom_profile_sketch
            if canonical_family == "C" and hasattr(self.form_proxy, "sb_lip_length"):
                kwargs["init_lip_length"] = self.form_proxy.sb_lip_length.value()

            Profile(
                obj,
                self.form_proxy.sb_width.value(),
                self.form_proxy.sb_height.value(),
                self.form_proxy.sb_main_thickness.value(),
                self.form_proxy.sb_flange_thickness.value(),
                self.form_proxy.sb_radius1.value(),
                self.form_proxy.sb_radius2.value(),
                self.form_proxy.sb_length.value(),
                self.form_proxy.sb_weight.value(),
                self.form_proxy.sb_unitprice.value(),
                self.form_proxy.cb_make_fillet.isChecked(),  # and self.form_proxy.family.currentText() not in ["Flat Sections", "Square", "Round Bar"],
                *self.get_anchor(),
                material_name,
                canonical_family,
                self.form_proxy.combo_size.currentText(),
                self.form_proxy.cb_combined_bevel.isChecked(),
                link_sub,
                **kwargs,
            )

            # Create a ViewObject in current GUI
            if getattr(obj, "ViewObject", None) is not None:
                if canonical_family == "Custom Profile":
                    ViewProviderCustomProfile(obj.ViewObject)
                else:
                    ViewProviderProfile(obj.ViewObject)

            return obj

        except Exception:
            if obj is not None and hasattr(obj, "Name"):
                try:
                    App.ActiveDocument.removeObject(obj.Name)
                except Exception:
                    pass
            raise

    def addSelection(self, doc, obj, sub, other):
        self.update_selection()
        if not getattr(self, "_initializing", False):
            self.on_input_changed()

    def clearSelection(self, other):
        self.update_selection()
        if not getattr(self, "_initializing", False):
            self.on_input_changed()

    def update_selection(self):
        selection_list = Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else []
        if len(selection_list) > 0:
            self.form_proxy.sb_length.setEnabled(False)
            self.form_proxy.sb_length.setValue(0.0)

            obj_name = ""
            for sel in selection_list:
                selected_obj_name = sel.ObjectName
                subs = ""
                for sub in sel.SubElementNames:
                    subs += "{},".format(sub)

                obj_name += selected_obj_name
                obj_name += " / "
                obj_name += subs
                # obj_name += '\n'

        else:
            self.form_proxy.sb_length.setEnabled(True)
            obj_name = "Not Attached / Define length"

        self.form_proxy.label_attach.setText(obj_name)


class CreateProfilesCommand:
    """Create Profiles with standards dimensions"""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "warehouse_profiles.svg"),
            "Accel": "Shift+S",  # a default shortcut (optional)
            "MenuText": "Create Profile",
            "ToolTip": "Create new profiles from Edges",
        }

    def Activated(self):
        """Do something here"""
        panel = CreateProfileTaskPanel()

        Gui.Selection.addObserver(panel)

        Gui.Control.showDialog(panel)

    def IsActive(self):
        """Here you can define if the command must be active or not (greyed) if certain conditions
        are met or not. This function is optional."""
        return App.ActiveDocument is not None


if hasattr(Gui, "addCommand"):
    add_command("MaxProFrame_CreateProfiles", CreateProfilesCommand())

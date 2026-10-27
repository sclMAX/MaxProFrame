import glob
import json
import os
import re
from abc import ABC, abstractmethod

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.alignment_widget import AlignmentWidget
from freecad.maxproframe.custom_profile_cards import custom_section_cache_key, render_custom_section_thumbnail
from freecad.maxproframe.custom_section_geometry import build_custom_section_face
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
from freecad.maxproframe.section_library import find_existing_section_sketch, get_or_import_section_sketch
from freecad.maxproframe.section_outline import build_section_face


def _bind_ui_children(form, path):
    # Native PySideUic aliases can retain QWidgetItem wrappers after successive
    # task dialogs. Resolve declared children by their actual QObject type/name,
    # before any layout moves or FormProxy snapshots use those aliases.
    from xml.etree import ElementTree

    for element in ElementTree.parse(path).iter():
        if element.tag in ("widget", "layout"):
            kind = getattr(QtWidgets, element.get("class", ""), None)
            name = element.get("name", "")
            if kind is not None and name:
                child = form.findChild(kind, name)
                if child is not None:
                    setattr(form, name, child)
    return form


def load_ui_file(path):
    if hasattr(Gui, "PySideUic") and hasattr(Gui.PySideUic, "loadUi"):
        return _bind_ui_children(Gui.PySideUic.loadUi(path), path)
    from PySide import QtCore, QtUiTools, QtWidgets

    _ = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    f = QtCore.QFile(path)
    if f.open(QtCore.QFile.ReadOnly):
        try:
            loader = QtUiTools.QUiLoader()
            return _bind_ui_children(loader.load(f), path)
        finally:
            f.close()
    raise RuntimeError(f"Unable to load UI file: {path}")


class _TranslatedFamilyPresentation(QtWidgets.QStyledItemDelegate):
    """Translate only native painting; combo text and catalog keys stay canonical."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = translate("frameforge", option.text)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Paint:
            option = QtWidgets.QStyleOptionComboBox()
            watched.initStyleOption(option)
            option.currentText = translate("frameforge", watched.currentText())
            painter = QtWidgets.QStylePainter(watched)
            painter.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, option)
            painter.drawControl(QtWidgets.QStyle.CE_ComboBoxLabel, option)
            painter.end()
            return True
        return super().eventFilter(watched, event)


class _TaskPreviewLabel(QtWidgets.QLabel):
    """Keep original image data public; fit and optionally tint only at paint time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self.is_custom = False

    def setPixmap(self, pixmap):
        self._source = pixmap
        self.update()

    def pixmap(self):
        return self._source

    def sizeHint(self):
        return QtCore.QSize(160, 100)

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def paintEvent(self, event):
        # Let QLabel render its native styled background, not a cached palette.
        super().paintEvent(event)
        source = self.pixmap()
        if source is None or source.isNull():
            return
        if self.is_custom:
            source = source.copy()
            tint = QtGui.QPainter(source)
            tint.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
            tint.fillRect(source.rect(), self.palette().color(self.foregroundRole()))
            tint.end()
        rect = self.contentsRect()
        fitted = source.scaled(rect.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        painter = QtGui.QPainter(self)
        painter.drawPixmap(
            rect.x() + (rect.width() - fitted.width()) // 2, rect.y() + (rect.height() - fitted.height()) // 2, fitted
        )
        painter.end()


class BaseProfileTaskPanel(ABC):
    def __init__(self):
        self._objects = {}

        self.form = [
            load_ui_file(os.path.join(UIPATH, "create_profiles1.ui")),
            load_ui_file(os.path.join(UIPATH, "create_profiles2.ui")),
        ]

        # Replace before FormProxy discovers children, so no stale label survives.
        old_image = self.form[0].label_image
        image = _TaskPreviewLabel(old_image.parentWidget())
        image.setObjectName(old_image.objectName())
        image.setAlignment(old_image.alignment())
        old_image.parentWidget().layout().replaceWidget(old_image, image)
        old_image.hide()
        old_image.setObjectName("")
        old_image.deleteLater()
        self.form[0].label_image = image
        self._thumbnail_cache = {}
        self._section_cache = {}
        self._alignment_custom_face = None
        self._alignment_geometry_key = None
        self._preview_family = None
        self._rendering_thumbnail = False
        self.form_proxy = FormProxy(self.form)
        self._configure_presentation()

        self.load_data()
        # self.initialize_ui() # Must be call in Child class, AFTER openTransaction

    def _configure_presentation(self):
        """Rearrange the shared widgets without changing their identities or signals."""
        first, second = self.form
        second.horizontalLayout.setDirection(QtWidgets.QBoxLayout.TopToBottom)
        second.horizontalLayout_4.setDirection(QtWidgets.QBoxLayout.TopToBottom)
        self.family_presentation = _TranslatedFamilyPresentation(first.combo_family)
        first.combo_family.setItemDelegate(self.family_presentation)
        first.combo_family.installEventFilter(self.family_presentation)
        # Keep the designer widgets (and FormProxy membership) when moving rows.
        catalog = first.groupBox.layout()
        rows = QtWidgets.QFormLayout()
        for label, combo in (
            (first.label_10, first.combo_material),
            (first.label, first.combo_family),
            (first.label_2, first.combo_size),
        ):
            catalog.removeWidget(label)
            catalog.removeWidget(combo)
            rows.addRow(label, combo)
        catalog.insertLayout(0, rows)
        first.label_10.setText("Library")
        self.material_info = QtWidgets.QLabel(first.groupBox)
        self.material_info.setWordWrap(True)
        catalog.insertWidget(1, self.material_info)
        self.custom_info = QtWidgets.QLabel(first.groupBox)
        self.custom_info.setTextFormat(QtCore.Qt.PlainText)
        self.custom_info.setWordWrap(True)
        catalog.addWidget(self.custom_info)
        self.custom_info.hide()
        first.label_image.setMinimumHeight(0)
        first.label_image.setMaximumHeight(100)
        first.label_image.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        # The metadata block no longer needs expansion spacers.
        metadata = first.verticalLayout
        for index in reversed(range(metadata.count())):
            if metadata.itemAt(index).spacerItem() is not None:
                metadata.takeAt(index)
        first.sb_length.setSuffix(" mm")
        first.groupBox_4.setTitle("Placement")
        placement = first.groupBox_4.layout()
        self.alignment_widget = AlignmentWidget(first.groupBox_4)
        placement.addRow(self.alignment_widget)
        self.alignment_widget.anchorClicked.connect(self._on_alignment_clicked)
        for widget in (second.group_anchor, second.widget_rotation):
            second.groupBox_3.layout().removeWidget(widget)
            placement.addRow(widget)

        self.advanced_button = QtWidgets.QToolButton(second)
        self.advanced_button.setObjectName("button_advanced")
        self.advanced_button.setText(translate("frameforge", "Advanced"))
        self.advanced_button.setCheckable(True)
        self.advanced_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.advanced_button.setArrowType(QtCore.Qt.RightArrow)
        self.advanced_content = QtWidgets.QWidget(second)
        advanced_layout = QtWidgets.QVBoxLayout(self.advanced_content)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        second.layout().removeWidget(second.groupBox_5)
        advanced_layout.addWidget(second.groupBox_5)
        # Transfer widgets, not the owned child layout: removeItem can delete
        # the C++ layout immediately under PySide6.
        price_row = QtWidgets.QFormLayout()
        first.horizontalLayout_2.removeWidget(first.label_3)
        first.horizontalLayout_2.removeWidget(first.sb_unitprice)
        price_row.addRow(first.label_3, first.sb_unitprice)
        advanced_layout.addLayout(price_row)
        first.label_3.setText("Price per metre")
        self.advanced_content.hide()
        second.layout().insertWidget(1, self.advanced_button)
        second.layout().insertWidget(2, self.advanced_content)
        self.advanced_button.toggled.connect(self.advanced_content.setVisible)
        self.advanced_button.toggled.connect(
            lambda expanded: self.advanced_button.setArrowType(
                QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
            )
        )
        # UI files use the generic Dialog context; product copy uses frameforge.
        for form in self.form:
            form.setWindowTitle(translate("frameforge", form.windowTitle()))
            for widget in form.findChildren(QtWidgets.QWidget):
                for getter, setter in (("text", "setText"), ("title", "setTitle"), ("toolTip", "setToolTip")):
                    if hasattr(widget, getter) and hasattr(widget, setter):
                        text = getattr(widget, getter)()
                        if text:
                            getattr(widget, setter)(translate("frameforge", text))

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
            self.form_proxy.combo_rotation.currentTextChanged.connect(self.on_input_changed)
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
        self._refresh_alignment()

    def _on_alignment_clicked(self, ax, ay):
        self.set_anchor(ax, ay)
        self.on_input_changed()

    def _profile_target_document(self, source=None):
        return getattr(source, "Document", None) or getattr(self, "_target_doc", None) or App.ActiveDocument

    def _existing_alignment_source(self):
        material = self.form_proxy.combo_material.currentText()
        family = self.form_proxy.combo_family.currentText()
        size = self.form_proxy.combo_size.currentText()
        data = self.profiles.get(material, {}).get(family, {}).get("sizes", {}).get(size, {})
        folder = self.library_manager._get_registered_folder(material)
        if not folder or not data.get("asset_path"):
            return None
        target = getattr(self, "profile", None)
        if target is None:
            selections = Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else []
            target = next((selection.Object for selection in selections if self._selection_edges(selection)), None)
        try:
            return find_existing_section_sketch(
                folder,
                data["asset_path"],
                data.get("object_name", "Section"),
                self._profile_target_document(target),
                data.get("asset_id", ""),
            )
        except (OSError, ValueError):
            # The catalog inspector already provides the unavailable-asset state.
            return None

    def _refresh_alignment(self):
        if (
            getattr(self, "_initializing", False)
            or self._rendering_thumbnail
            or getattr(self, "_accept_finalizing", False)
        ):
            return
        parameters = {"Family": self._preview_family}
        for prop, control in (
            ("ProfileWidth", "sb_width"),
            ("ProfileHeight", "sb_height"),
            ("Thickness", "sb_main_thickness"),
            ("ThicknessFlange", "sb_flange_thickness"),
            ("RadiusLarge", "sb_radius1"),
            ("RadiusSmall", "sb_radius2"),
            ("LipLength", "sb_lip_length"),
        ):
            if hasattr(self.form_proxy, control):
                parameters[prop] = getattr(self.form_proxy, control).value()
        parameters["MakeFillet"] = self.form_proxy.cb_make_fillet.isChecked()
        face = self._alignment_custom_face
        source = None
        profile = getattr(self, "profile", None)
        if (
            profile is not None
            and self._preview_family == "Custom Profile"
            and self.form_proxy.combo_family.currentText() == (getattr(profile, "CatalogFamily", "") or profile.Family)
            and self.form_proxy.combo_size.currentText() == profile.SizeName
            and self.form_proxy.combo_material.currentText() == profile.Material
        ):
            source = getattr(profile, "CustomProfile", None)
        if source is None and self._preview_family == "Custom Profile":
            source = self._existing_alignment_source()
        source_key = source.Shape.exportBrepToString() if source is not None else None
        key = (tuple(sorted(parameters.items())), source_key, face.exportBrepToString() if face is not None else None)
        if key != self._alignment_geometry_key:
            try:
                if source is not None:
                    face = build_custom_section_face(source)
                section = build_section_face(parameters, custom_face=face)
                self.alignment_widget.set_section(section)
                self.alignment_widget.setToolTip(
                    translate(
                        "frameforge", "Click a section bounding-box anchor. Keyboard: use the anchor controls below."
                    )
                )
            except Exception as error:
                self.alignment_widget.set_section(None)
                self.alignment_widget.setToolTip(translate("frameforge", "No Preview") + ": " + str(error))
            self._alignment_geometry_key = key
        self.alignment_widget.set_state(
            self.get_anchor(),
            self.get_rotation(),
            self.form_proxy.cb_mirror_h.isChecked(),
            self.form_proxy.cb_mirror_v.isChecked(),
        )

    def on_input_changed(self):
        if not getattr(self, "_initializing", False) and not self._rendering_thumbnail:
            self._refresh_alignment()
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
        if hasattr(self, "_saved_anchor") and self._saved_anchor is not None:
            return self._saved_anchor
        for ax in range(3):
            for ay in range(3):
                if getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").isChecked():
                    return (ax, ay)
        return (1, 1)

    def set_anchor(self, anchor_x, anchor_y):
        ax = max(0, min(2, anchor_x))
        ay = max(0, min(2, anchor_y))
        getattr(self.form_proxy, f"rb_anchor_{ax}_{ay}").setChecked(True)
        if hasattr(self, "alignment_widget"):
            self.alignment_widget.set_state(
                (ax, ay),
                self.get_rotation(),
                self.form_proxy.cb_mirror_h.isChecked(),
                self.form_proxy.cb_mirror_v.isChecked(),
            )

    def get_rotation(self):
        """Return rotation angle in degrees (float)."""
        if hasattr(self, "_saved_rotation") and self._saved_rotation is not None:
            return self._saved_rotation
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

    def _update_material_info(self):
        library = str(self.form_proxy.combo_material.currentText())
        if library in self.profiles:
            material, _density = self.library_manager.get_library_material_info(library)
            self.material_info.setText(translate("frameforge", "Material: %s") % material)
        else:
            self.material_info.setText(translate("frameforge", "Material unavailable"))

    def on_material_changed(self, index):
        material = str(self.form_proxy.combo_material.currentText())

        self.enable_signals(False)

        self._update_material_info()
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
        self.form[0].label_2.setText(translate("frameforge", "Profile" if is_custom else "Size"))
        self.form_proxy.combo_family.setToolTip(translate("frameforge", canonical))

        fillet_val = False if is_custom else bool(self.profiles.get(material, {}).get(family, {}).get("fillet", False))
        self.form_proxy.cb_make_fillet.setChecked(fillet_val)
        self.form_proxy.cb_make_fillet.setEnabled(False if is_custom else fillet_val)

        self.update_image()

        fam_dict = self.profiles.get(material, {}).get(family, {})
        norm_val = fam_dict.get("norm", "Custom" if is_custom else "")
        unit_val = fam_dict.get("unit", "Metric Units" if is_custom else "")

        self.form_proxy.label_norm.setText(translate("frameforge", norm_val))
        self.form_proxy.label_unit.setText(translate("frameforge", unit_val))

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
                GEOMETRY_METADATA = {"asset_path", "object_name", "asset_id", "Area", "Size", "Description"}
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
            self.update_image()
            self.on_input_changed()

    def on_cb_make_fillet_changed(self, state):
        self.update_image()
        self.on_input_changed()

    def update_image(self):
        if self._rendering_thumbnail:
            return
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

        self._preview_family = canonical_family
        is_custom = canonical_family == "Custom Profile"
        self.form_proxy.label_image.is_custom = is_custom
        self.custom_info.setVisible(is_custom)
        if is_custom:
            code = str(self.form_proxy.combo_size.currentText())
            size = (family_data or {}).get("sizes", {}).get(code, {})
            description = str(size.get("Description", ""))
            weight = size.get("Weight", getattr(getattr(self, "profile", None), "LinearWeight", ""))
            self.custom_info.setText("\n".join(filter(None, (code, description, "%s kg/m" % weight))))
            self._rendering_thumbnail = True
            try:
                folder = self.library_manager._get_registered_folder(material)
                asset, name = size.get("asset_path"), size.get("object_name", "Section")
                pixmap = render_custom_section_thumbnail(
                    folder,
                    asset,
                    name,
                    width=160,
                    height=100,
                    cache=self._thumbnail_cache,
                    section_cache=self._section_cache,
                )
                self._alignment_custom_face = None
                if folder and asset:
                    try:
                        self._alignment_custom_face = self._section_cache.get(
                            custom_section_cache_key(folder, asset, name)
                        )
                    except (OSError, ValueError):
                        pass
                self.form_proxy.label_image.setPixmap(pixmap)
            finally:
                self._rendering_thumbnail = False
            self._refresh_alignment()
            return
        self.custom_info.clear()
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
        self._alignment_custom_face = None
        self._refresh_alignment()

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
                target_doc = self._profile_target_document(profile)
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


class _SnapshotWidget:
    def __init__(self, text="", value=0.0, checked=False):
        self._text = text
        self._value = value
        self._checked = checked

    def currentText(self):
        return self._text

    def value(self):
        return self._value

    def isChecked(self):
        return self._checked

    def text(self):
        return self._text

    def setText(self, *args, **kwargs):
        pass

    def setVisible(self, *args, **kwargs):
        pass

    def setEnabled(self, *args, **kwargs):
        pass


class _SnapshotFormProxy:
    def __init__(self, real_proxy):
        self._widgets = {}
        for member in getattr(real_proxy, "members", {}):
            try:
                w = getattr(real_proxy, member)
                text = ""
                if hasattr(w, "currentText"):
                    try:
                        text = str(w.currentText())
                    except Exception:
                        pass
                elif hasattr(w, "text"):
                    try:
                        text = str(w.text())
                    except Exception:
                        pass
                val = 0.0
                if hasattr(w, "value"):
                    try:
                        val = float(w.value())
                    except Exception:
                        pass
                checked = False
                if hasattr(w, "isChecked"):
                    try:
                        checked = bool(w.isChecked())
                    except Exception:
                        pass
                self._widgets[member] = _SnapshotWidget(text=text, value=val, checked=checked)
            except Exception:
                pass
        self.members = dict(getattr(real_proxy, "members", {}))

    def __getattr__(self, name):
        if name in self._widgets:
            return self._widgets[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class CreateProfileTaskPanel(BaseProfileTaskPanel):
    def __init__(self):
        self._session_imported_sketches = set()
        self._target_doc = None
        self._has_pending_changes = False
        self._accept_finalizing = False
        self._reject_called = False
        self._saved_anchor = None
        self._saved_rotation = None
        self._saved_selection = None
        self._saved_form_proxy = None
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
        self.action_guidance = QtWidgets.QLabel(
            translate("frameforge", "Apply: update preview. OK: confirm. Cancel: discard."), self.form[0]
        )
        self.action_guidance.setWordWrap(True)
        self.form_proxy.groupBox_apply.layout().addWidget(self.action_guidance)
        self._set_initial_state()

    def _set_initial_state(self):
        self._has_pending_changes = False
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "No preview"))

    def _set_pending_state(self):
        self._has_pending_changes = True
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "Pending changes"))

    def _set_applied_state(self):
        self._has_pending_changes = False
        if "label_apply_status" in self.form_proxy.members:
            self.form_proxy.label_apply_status.setText(translate("frameforge", "Preview updated"))

    def on_input_changed(self):
        if getattr(self, "_initializing", False) or self._rendering_thumbnail:
            return
        self._refresh_alignment()
        self._set_pending_state()
        self._update_placement_guidance()

    def open(self):
        self._session_imported_sketches = set()
        self._target_doc = getattr(App, "ActiveDocument", None)
        self._accept_finalizing = False
        self._reject_called = False
        self._saved_anchor = None
        self._saved_rotation = None
        self._saved_selection = None
        self._saved_form_proxy = None

        App.ActiveDocument.openTransaction("Add Profile")

        self.initialize_ui()

        self.update_selection()
        self._set_initial_state()

    def reject(self):
        self._reject_called = True
        self._accept_finalizing = False

        self.clean()

        target_doc = getattr(self, "_target_doc", None) or getattr(App, "ActiveDocument", None)
        if target_doc is not None and (not hasattr(App, "listDocuments") or target_doc.Name in App.listDocuments()):
            try:
                target_doc.abortTransaction()
            except Exception:
                pass

        if hasattr(self, "_session_imported_sketches"):
            for doc_name, sk_name in list(self._session_imported_sketches):
                doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
                if doc is None and hasattr(App, "listDocuments") and doc_name in App.listDocuments():
                    doc = App.listDocuments()[doc_name]
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
                translate("frameforge", "Create Profile"),
                translate("frameforge", "Select Edges or set Length to create a profile"),
            )
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            diag.exec_()

            return False

    def _needs_first_custom_import(self):
        try:
            material_name = self.form_proxy.combo_material.currentText()
            selected_family = self.form_proxy.combo_family.currentText()
            family_data = (
                self.profiles.get(material_name, {}).get(selected_family)
                if hasattr(self, "profiles") and self.profiles
                else None
            )
            canonical_family = get_canonical_family(selected_family, family_data)
            if canonical_family != "Custom Profile":
                return False

            size_name = self.form_proxy.combo_size.currentText()
            size_data = family_data.get("sizes", {}).get(size_name, {}) if isinstance(family_data, dict) else {}
            folder_root = self.library_manager._get_registered_folder(material_name)
            asset_path = size_data.get("asset_path")
            object_name = size_data.get("object_name", "Section")
            asset_id = size_data.get("asset_id", "")
            if not (folder_root and asset_path):
                return False

            target_doc = getattr(self, "_target_doc", None) or App.ActiveDocument
            if target_doc is None:
                return False

            canonical_root = os.path.realpath(os.path.abspath(folder_root))
            norm_asset_path = os.path.normpath(asset_path).replace("\\", "/")
            target_aid = str(asset_id) if asset_id is not None else ""

            for obj in getattr(target_doc, "Objects", []):
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject"):
                    p_prov = getattr(obj, "FF_Provenance", None)
                    p_aid = getattr(obj, "FF_AssetId", None)
                    p_oname = getattr(obj, "FF_ObjectName", None)
                    p_apath = getattr(obj, "FF_AssetPath", None)
                    if (
                        p_prov == canonical_root
                        and p_apath == norm_asset_path
                        and p_oname == str(object_name)
                        and (not target_aid or p_aid == target_aid)
                    ):
                        return False

            return True
        except Exception:
            return False

    def _is_active_gui_dialog(self):
        try:
            return bool(hasattr(Gui, "Control") and Gui.Control.activeDialog())
        except Exception:
            return False

    def accept(self, defer=None):
        has_sel = len(Gui.Selection.getSelectionEx()) if hasattr(Gui, "Selection") else 0
        if not (has_sel or self.form_proxy.sb_length.value() > 0):
            App.Console.PrintMessage(
                translate("frameforge", "Not Accepting CreateProfile\nSelect Edges or set Length\n")
            )

            diag = QtGui.QMessageBox(
                QtGui.QMessageBox.Warning,
                translate("frameforge", "Create Profile"),
                translate("frameforge", "Select Edges or set Length to create a profile"),
            )
            diag.setWindowModality(QtCore.Qt.ApplicationModal)
            diag.exec_()

            return False

        if getattr(self, "_accept_finalizing", False):
            return True

        if defer is None:
            defer = self._is_active_gui_dialog() and self._needs_first_custom_import()

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

        if defer:
            self._accept_finalizing = True
            self._saved_anchor = (ax, ay)
            self._saved_rotation = self.get_rotation()
            self._saved_selection = list(Gui.Selection.getSelectionEx()) if hasattr(Gui, "Selection") else []
            self._saved_form_proxy = _SnapshotFormProxy(self.form_proxy)
            self.clean()
            QtCore.QTimer.singleShot(0, self._finalize_accept)
            return True

        self.clean()
        return self._finalize_accept()

    def _finalize_accept(self):
        if getattr(self, "_reject_called", False):
            self._accept_finalizing = False
            return False

        if hasattr(self, "_saved_form_proxy") and self._saved_form_proxy is not None:
            self.form_proxy = self._saved_form_proxy

        target_doc = getattr(self, "_target_doc", None) or App.ActiveDocument
        if target_doc is None:
            self._accept_finalizing = False
            return False
        if hasattr(App, "listDocuments") and target_doc.Name not in App.listDocuments():
            self._accept_finalizing = False
            return False

        try:
            self.proceed()

            if hasattr(self, "_session_imported_sketches"):
                self._session_imported_sketches.clear()

            for o in self._objects.values():
                if getattr(o, "ViewObject", None) is not None:
                    o.ViewObject.Transparency = 0
                    o.ViewObject.ShapeColor = (0.44, 0.47, 0.5)

            target_doc.commitTransaction()
            target_doc.recompute()
            return True
        except Exception as err:
            App.Console.PrintError(f"Create Profile error: {err}\n")
            try:
                diag = QtGui.QMessageBox(
                    QtGui.QMessageBox.Critical,
                    "Create Profile",
                    f"{translate('frameforge', 'Failed to create profile')}: {err}",
                )
                diag.setWindowModality(QtCore.Qt.ApplicationModal)
                diag.exec_()
            except Exception:
                pass

            if target_doc is not None and (not hasattr(App, "listDocuments") or target_doc.Name in App.listDocuments()):
                try:
                    target_doc.abortTransaction()
                except Exception:
                    pass

            if hasattr(self, "_session_imported_sketches"):
                for doc_name, sk_name in list(self._session_imported_sketches):
                    doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
                    if doc is None and hasattr(App, "listDocuments") and doc_name in App.listDocuments():
                        doc = App.listDocuments()[doc_name]
                    if doc is not None and hasattr(doc, "getObject") and doc.getObject(sk_name) is not None:
                        try:
                            doc.removeObject(sk_name)
                        except Exception:
                            pass
                self._session_imported_sketches.clear()

            for o in list(self._objects.values()):
                if o is not None:
                    try:
                        doc = getattr(o, "Document", None) or target_doc
                        if doc is not None and hasattr(doc, "removeObject") and hasattr(o, "Name"):
                            doc.removeObject(o.Name)
                    except Exception:
                        pass
            self._objects.clear()
            return False
        finally:
            self._accept_finalizing = False

    def clean(self):
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.removeObserver(self)
            except Exception:
                pass
            try:
                Gui.Selection.removeSelectionGate()
            except Exception:
                pass

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

        selection_list = (
            getattr(self, "_saved_selection", None)
            if getattr(self, "_saved_selection", None) is not None
            else (Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else [])
        )

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

                edges = self._selection_edges(sketch_sel)

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
                target_doc = self._profile_target_document(sketch)
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
            target_doc = self._profile_target_document(sketch)
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

    @staticmethod
    def _selection_edges(selection):
        """The same path expansion is used by creation and its placement summary."""
        if selection.SubElementNames:
            return selection.SubElementNames
        shape = getattr(selection.Object, "Shape", None)
        return [f"Edge{index + 1}" for index, _edge in enumerate(getattr(shape, "Edges", ()))]

    def _update_placement_guidance(self):
        selections = Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else []
        details = [(selection.ObjectName, self._selection_edges(selection)) for selection in selections]
        count = sum(len(edges) for _name, edges in details)
        if selections:
            source = "1 edge selected" if count == 1 else "%s edges selected"
            text = translate("frameforge", source)
            if count != 1:
                text = text % count
            tooltip = "\n".join(f"{name}: {', '.join(edges)}" for name, edges in details)
        else:
            text = translate(
                "frameforge", "Define a length" if self.form_proxy.sb_length.value() <= 0 else "Manual length"
            )
            tooltip = translate(
                "frameforge", "Select edges or a whole object to use its edges, or enter a positive length."
            )
        self.form_proxy.label_attach.setText(text)
        self.form_proxy.label_attach.setToolTip(tooltip)

    def update_selection(self):
        if self._rendering_thumbnail:
            return
        selection_list = Gui.Selection.getSelectionEx() if hasattr(Gui, "Selection") else []
        self.form_proxy.sb_length.setEnabled(not selection_list)
        if selection_list:
            self.form_proxy.sb_length.setValue(0.0)
        self._update_placement_guidance()


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

import copy
import os

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui

from freecad.frameforge.ff_tools import ICONPATH, PROFILEIMAGES_PATH, TRANSLATIONSPATH, translate
from freecad.frameforge.library_manager import (
    KNOWN_FAMILIES,
    STANDARD_DENSITIES,
    LibraryManager,
    calculate_linear_weight,
    sanitize_library_name,
)


def is_dark_theme(widget):
    """Detects if the current Qt palette corresponds to a dark theme."""
    bg = widget.palette().color(QtGui.QPalette.Window)
    return bg.lightness() < 128


class NewLibraryDialog(QtWidgets.QDialog):
    """Modal dialog for creating or duplicating a library with material selection."""

    def __init__(
        self,
        parent=None,
        title="New Library",
        default_name="",
        default_material="Steel",
        is_duplicate=False,
    ):
        super().__init__(parent)
        self.setWindowTitle(translate("frameforge", title))
        self.resize(380, 160)

        layout = QtWidgets.QVBoxLayout(self)

        # Name row
        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Library Name:")))
        self.le_name = QtWidgets.QLineEdit(default_name)
        layout.addWidget(self.le_name)

        # Material row
        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Material / Density:")))
        self.combo_material = QtWidgets.QComboBox()
        for mat, dens in STANDARD_DENSITIES.items():
            self.combo_material.addItem(
                f"{translate('frameforge', mat)} ({dens} g/cm³)", (mat, dens)
            )

        # Preselect default material
        for i in range(self.combo_material.count()):
            mat_key, _ = self.combo_material.itemData(i)
            if mat_key.lower() == default_material.lower():
                self.combo_material.setCurrentIndex(i)
                break
        layout.addWidget(self.combo_material)

        self.cb_recalc = None
        if is_duplicate:
            self.cb_recalc = QtWidgets.QCheckBox(
                translate("frameforge", "Recalculate theoretical weights for new material")
            )
            self.cb_recalc.setChecked(True)
            layout.addWidget(self.cb_recalc)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_values(self):
        name = self.le_name.text().strip()
        mat_data = self.combo_material.itemData(self.combo_material.currentIndex())
        mat = mat_data[0] if mat_data else "Steel"
        dens = mat_data[1] if mat_data else 7.85
        recalc = self.cb_recalc.isChecked() if self.cb_recalc else False
        return name, mat, dens, recalc


class ProfileLibraryManagerDialog(QtWidgets.QDialog):
    """
    Dialog for managing FrameForge profile libraries:
    Stock vs User-defined catalogs, families, and dimensional sizes with weight calculations.
    """

    TABLE_COLUMNS = [
        ("Size", "Code"),
        ("Height", "Height [mm]"),
        ("Width", "Width [mm]"),
        ("Thickness", "Thickness [mm]"),
        ("Flange Thickness", "Flange Thickness [mm]"),
        ("Radius1", "Radius 1 [mm]"),
        ("Radius2", "Radius 2 [mm]"),
        ("Weight", "Weight [kg/m]"),
    ]

    @classmethod
    def ensure_translations_loaded(cls):
        """Ensures that the locale translation file from TRANSLATIONSPATH is loaded in QApplication."""
        if getattr(cls, "_translator_installed", False):
            return
        cls._translator_installed = True
        try:
            translator = QtCore.QTranslator()
            locale = QtCore.QLocale()
            for prefix in ["frameforge", "FrameForge"]:
                if translator.load(locale, prefix, "_", TRANSLATIONSPATH):
                    QtWidgets.QApplication.installTranslator(translator)
                    cls._translator = translator
                    break
        except Exception:
            pass

    def __init__(self, parent=None, library_manager=None):
        super().__init__(parent)
        self.ensure_translations_loaded()
        self.manager = library_manager or LibraryManager()
        self.current_lib_meta = None
        self.current_lib_data = {}
        self.current_family = None
        self.is_dirty = False

        self.setWindowTitle(translate("frameforge", "FrameForge - Profile Library Manager"))
        self.resize(920, 580)

        self._build_ui()
        self.refresh_libraries()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # Header description
        header = QtWidgets.QLabel(
            translate(
                "frameforge",
                "<b>Profile Library Management</b><br>"
                "Create, duplicate and modify custom libraries (e.g. Aluminum Tubes) with specific dimensions and material weights.",
            )
        )
        header.setWordWrap(True)
        header.setStyleSheet("padding-bottom: 6px;")
        main_layout.addWidget(header)

        # Content Splitter (Left: Libraries, Right: Details/Sizes)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- LEFT PANEL: Libraries list & actions ---
        self.left_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.left_splitter.setHandleWidth(6)
        self.left_splitter.setStyleSheet("QSplitter::handle:horizontal { background: palette(mid); }")
        lib_widget = QtWidgets.QWidget()
        lib_layout = QtWidgets.QVBoxLayout(lib_widget)
        lib_layout.setContentsMargins(0, 0, 0, 0)

        lib_header = QtWidgets.QHBoxLayout()
        lib_header.addWidget(QtWidgets.QLabel(translate("frameforge", "<b>Available Libraries:</b>")), 1)
        self.btn_new_lib = self._compact_button("list-add.svg", "New Library", self._on_new_library)
        self.btn_dup_lib = self._compact_button("duplicate.svg", "Duplicate Library", self._on_duplicate_library)
        self.btn_del_lib = self._compact_button("list-remove.svg", "Delete Library", self._on_delete_library)
        for button in (self.btn_new_lib, self.btn_dup_lib, self.btn_del_lib):
            lib_header.addWidget(button)
        lib_layout.addLayout(lib_header)
        self.list_libraries = QtWidgets.QListWidget()
        self.list_libraries.currentItemChanged.connect(self._on_library_selection_changed)
        lib_layout.addWidget(self.list_libraries, 1)

        family_widget = QtWidgets.QWidget()
        family_layout = QtWidgets.QVBoxLayout(family_widget)
        family_layout.setContentsMargins(0, 0, 0, 0)
        family_header = QtWidgets.QHBoxLayout()
        family_header.addWidget(QtWidgets.QLabel(translate("frameforge", "<b>Library Families:</b>")), 1)
        self.btn_add_family = self._compact_button("list-add.svg", "Add Family", self._on_add_family)
        self.btn_del_family = self._compact_button("list-remove.svg", "Delete Family", self._on_delete_family)
        family_header.addWidget(self.btn_add_family)
        family_header.addWidget(self.btn_del_family)
        family_layout.addLayout(family_header)
        self.list_families = QtWidgets.QListWidget()
        self.list_families.setIconSize(QtCore.QSize(60, 30))
        self.list_families.currentItemChanged.connect(self._on_family_selection_changed)
        family_layout.addWidget(self.list_families, 1)

        # Hidden raw-key selector retained for legacy callers; the list is the visible selector.
        self.combo_family = QtWidgets.QComboBox(family_widget)
        self.combo_family.hide()
        self.combo_family.currentIndexChanged.connect(self._on_family_changed)

        self.left_splitter.addWidget(lib_widget)
        self.left_splitter.addWidget(family_widget)
        self.left_splitter.setSizes([180, 320])
        splitter.addWidget(self.left_splitter)

        # --- RIGHT PANEL: Families and Sizes Table ---
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Header: Family Preview Icon on left, Banner & Metadata on right
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.lbl_family_icon = QtWidgets.QLabel()
        self.lbl_family_icon.setFixedSize(120, 60)
        self.lbl_family_icon.setAlignment(QtCore.Qt.AlignCenter)
        header_layout.addWidget(self.lbl_family_icon)

        header_details_layout = QtWidgets.QVBoxLayout()
        header_details_layout.setContentsMargins(0, 0, 0, 0)
        header_details_layout.setSpacing(4)

        # Top banner for library type (Stock read-only vs User editable)
        self.lbl_lib_banner = QtWidgets.QLabel()
        self.lbl_lib_banner.setStyleSheet("padding: 4px; font-weight: bold; border-radius: 3px;")
        header_details_layout.addWidget(self.lbl_lib_banner)

        # Metadata row: Norma & Fillet & Size compact actions
        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addWidget(QtWidgets.QLabel(translate("frameforge", "Standard / Ref:")))
        self.le_norm = QtWidgets.QLineEdit()
        self.le_norm.textChanged.connect(self._mark_dirty)
        meta_row.addWidget(self.le_norm, 1)

        self.cb_fillet = QtWidgets.QCheckBox(translate("frameforge", "With Fillet"))
        self.cb_fillet.toggled.connect(self._on_fillet_toggled)
        meta_row.addWidget(self.cb_fillet)

        self.btn_add_size = self._compact_button("list-add.svg", "Add Size", self._on_add_size)
        self.btn_del_size = self._compact_button("list-remove.svg", "Remove Size", self._on_delete_size)
        meta_row.addWidget(self.btn_add_size)
        meta_row.addWidget(self.btn_del_size)

        header_details_layout.addLayout(meta_row)
        header_layout.addLayout(header_details_layout, 1)

        right_layout.addLayout(header_layout)

        # Sizes Table
        self.table_sizes = QtWidgets.QTableWidget()
        self.table_sizes.setColumnCount(len(self.TABLE_COLUMNS))
        self.table_sizes.setHorizontalHeaderLabels([translate("frameforge", col[1]) for col in self.TABLE_COLUMNS])
        self.table_sizes.horizontalHeader().setStretchLastSection(True)
        self.table_sizes.itemChanged.connect(self._on_table_item_changed)
        right_layout.addWidget(self.table_sizes, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([320, 640])

        # Bottom Bar: Status and Save / Close
        bottom_layout = QtWidgets.QHBoxLayout()
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: #006600;")
        bottom_layout.addWidget(self.lbl_status, 1)

        self.btn_save = QtWidgets.QPushButton(translate("frameforge", "Save Changes"))
        self.btn_save.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #1976d2;
                color: #ffffff;
                border: 1px solid #1565c0;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #2196f3;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        self.btn_save.clicked.connect(self._on_save_library)
        self.btn_close = QtWidgets.QPushButton(translate("frameforge", "Close"))
        self.btn_close.clicked.connect(self.close)

        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_close)
        main_layout.addLayout(bottom_layout)

    def _compact_button(self, icon_name, tooltip, callback):
        button = QtWidgets.QPushButton()
        button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, icon_name)))
        button.setToolTip(translate("frameforge", tooltip))
        button.setFixedSize(26, 26)
        button.clicked.connect(callback)
        return button

    def refresh_libraries(self, select_name=None):
        self.list_libraries.blockSignals(True)
        self.list_libraries.clear()

        libs = self.manager.list_libraries()
        target_item = None

        for lib in libs:
            tag = translate("frameforge", "[User] ") if lib["is_user"] else translate("frameforge", "[System] ")
            item = QtWidgets.QListWidgetItem(f"{tag}{lib['name']}")
            item.setData(QtCore.Qt.UserRole, lib)
            self.list_libraries.addItem(item)
            if select_name and lib["name"].lower() == select_name.lower():
                target_item = item

        self.list_libraries.blockSignals(False)

        if target_item:
            self.list_libraries.setCurrentItem(target_item)
        elif self.list_libraries.count() > 0:
            self.list_libraries.setCurrentRow(0)

    def _on_library_selection_changed(self, current, previous):
        if not current:
            return

        if self.is_dirty and previous:
            try:
                self._commit_current_family_edits()
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, translate("frameforge", "Warning"), str(e))

            reply = QtWidgets.QMessageBox.question(
                self,
                translate("frameforge", "Unsaved Changes"),
                translate(
                    "frameforge",
                    "You have unsaved changes. Do you want to save them before switching libraries?",
                ),
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save,
            )
            if reply == QtWidgets.QMessageBox.Save:
                self._on_save_library()
                if self.is_dirty:
                    self.list_libraries.blockSignals(True)
                    self.list_libraries.setCurrentItem(previous)
                    self.list_libraries.blockSignals(False)
                    return
            elif reply == QtWidgets.QMessageBox.Cancel:
                self.list_libraries.blockSignals(True)
                self.list_libraries.setCurrentItem(previous)
                self.list_libraries.blockSignals(False)
                return

        lib_meta = current.data(QtCore.Qt.UserRole)
        # Reset current family so previous library's family doesn't commit into new library
        self.current_family = None
        self.current_lib_meta = lib_meta

        try:
            self.current_lib_data = self.manager.get_library(lib_meta["name"])
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Error"), str(e))
            return

        is_user = lib_meta["is_user"]
        self.btn_del_lib.setEnabled(is_user)
        self.btn_save.setEnabled(is_user)
        self.btn_add_family.setEnabled(is_user)

        self._update_banner(is_user, lib_meta["name"])

        self._populate_families()
        self.is_dirty = False
        self._set_status("")

    def _update_banner(self, is_user, name):
        dark = is_dark_theme(self)
        mat, dens = self.manager.get_library_material_info(name)
        mat_display = f"{translate('frameforge', mat)} ({dens} g/cm³)"
        if is_user:
            self.lbl_lib_banner.setText(
                translate("frameforge", "User Library: %s | Material: %s (Editable)")
                % (name, mat_display)
            )
            if dark:
                self.lbl_lib_banner.setStyleSheet(
                    "background-color: #1b3824; color: #81c784; border: 1px solid #2e7d32; padding: 5px 8px; border-radius: 4px; font-weight: bold;"
                )
            else:
                self.lbl_lib_banner.setStyleSheet(
                    "background-color: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; padding: 5px 8px; border-radius: 4px; font-weight: bold;"
                )
        else:
            self.lbl_lib_banner.setText(
                translate(
                    "frameforge",
                    "System Library: %s | Material: %s (Read-only - Use 'Duplicate' to customize)",
                )
                % (name, mat_display)
            )
            if dark:
                self.lbl_lib_banner.setStyleSheet(
                    "background-color: #2b3036; color: #cfd8dc; border: 1px solid #455a64; padding: 5px 8px; border-radius: 4px; font-weight: bold;"
                )
            else:
                self.lbl_lib_banner.setStyleSheet(
                    "background-color: #eceff1; color: #37474f; border: 1px solid #cfd8dc; padding: 5px 8px; border-radius: 4px; font-weight: bold;"
                )

    def _set_status(self, text, is_error=False, is_warning=False):
        dark = is_dark_theme(self)
        if is_error:
            color = "#ef5350" if dark else "#c62828"
        elif is_warning:
            color = "#ffb74d" if dark else "#e65100"
        else:
            color = "#81c784" if dark else "#2e7d32"
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.lbl_status.setText(text)

    def _populate_families(self, select_family=None):
        self.combo_family.blockSignals(True)
        self.list_families.blockSignals(True)
        self.combo_family.clear()
        self.list_families.clear()

        families = sorted(k for k in self.current_lib_data if not k.startswith("_"))
        for fam_key in families:
            self.combo_family.addItem(fam_key)
            img_name = f"{fam_key.replace(' ', '_')}.png"
            img_path = os.path.join(PROFILEIMAGES_PATH, "Metal", img_name)
            if not os.path.isfile(img_path):
                img_path = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            item = QtWidgets.QListWidgetItem(translate("frameforge", fam_key))
            if os.path.isfile(img_path):
                item.setIcon(QtGui.QIcon(img_path))
            item.setData(QtCore.Qt.UserRole, fam_key)
            self.list_families.addItem(item)

        if families:
            row = families.index(select_family) if select_family in families else 0
            self.combo_family.setCurrentIndex(row)
            self.list_families.setCurrentRow(row)
        self.combo_family.blockSignals(False)
        self.list_families.blockSignals(False)
        self._on_family_changed()

    def _on_family_selection_changed(self, current, previous):
        self.combo_family.blockSignals(True)
        self.combo_family.setCurrentIndex(
            self.combo_family.findText(current.data(QtCore.Qt.UserRole)) if current else -1
        )
        self.combo_family.blockSignals(False)
        self._on_family_changed()

    def _on_family_changed(self):
        # Synchronize legacy combo-driven selection without emitting a second change.
        self.list_families.blockSignals(True)
        self.list_families.setCurrentRow(self.combo_family.currentIndex())
        self.list_families.blockSignals(False)
        try:
            self._commit_current_family_edits()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Warning"), str(e))

        family_name = self.combo_family.currentText()
        self.current_family = family_name

        is_user = bool(self.current_lib_meta and self.current_lib_meta.get("is_user"))
        has_family = bool(family_name and family_name in self.current_lib_data)

        self.btn_del_family.setEnabled(is_user and has_family)
        self.btn_add_size.setEnabled(is_user and has_family)
        self.btn_del_size.setEnabled(is_user and has_family)
        self.le_norm.setEnabled(is_user and has_family)
        self.cb_fillet.setEnabled(is_user and has_family)

        if not has_family:
            self.table_sizes.setRowCount(0)
            self.le_norm.setText("")
            self.cb_fillet.setChecked(False)
            self._update_family_icon()
            return

        fam_data = self.current_lib_data[family_name]
        self.le_norm.blockSignals(True)
        self.cb_fillet.blockSignals(True)

        self.le_norm.setText(fam_data.get("norm", ""))
        self.cb_fillet.setChecked(bool(fam_data.get("fillet", False)))

        self.le_norm.blockSignals(False)
        self.cb_fillet.blockSignals(False)

        self._update_family_icon()

        sizes_dict = fam_data.get("sizes", {})
        self._populate_sizes_table(sizes_dict)

    def _get_family_image_path(self, family_name=None, fillet=None):
        fam = family_name or self.current_family
        if not fam:
            warehouse = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            return warehouse if os.path.isfile(warehouse) else ""

        if fillet is None:
            fillet = self.cb_fillet.isChecked() if hasattr(self, "cb_fillet") else False

        lib_name = (self.current_lib_meta or {}).get("name", "Metal")
        base_name = fam.replace(" ", "_")

        candidates = []
        if fillet:
            candidates.append(f"{base_name}_Fillet.png")
        candidates.append(f"{base_name}.png")

        dirs = [lib_name, "Metal"]
        for c in candidates:
            for d in dirs:
                p = os.path.join(PROFILEIMAGES_PATH, d, c)
                if os.path.isfile(p):
                    return p

        warehouse = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
        if os.path.isfile(warehouse):
            return warehouse
        return ""

    def _update_family_icon(self):
        dark = is_dark_theme(self)
        if dark:
            self.lbl_family_icon.setStyleSheet(
                "background-color: #202428; border: 1px solid #455a64; border-radius: 4px;"
            )
        else:
            self.lbl_family_icon.setStyleSheet(
                "background-color: #f5f7f8; border: 1px solid #cfd8dc; border-radius: 4px;"
            )

        if not self.current_family or self.current_family not in self.current_lib_data:
            self.lbl_family_icon.clear()
            self.lbl_family_icon.setToolTip("")
            return

        img_path = self._get_family_image_path(self.current_family)
        if img_path and os.path.isfile(img_path):
            pixmap = QtGui.QPixmap(img_path)
            if not pixmap.isNull():
                target_w = max(self.lbl_family_icon.width() - 8, 20)
                target_h = max(self.lbl_family_icon.height() - 8, 20)
                scaled = pixmap.scaled(
                    QtCore.QSize(target_w, target_h),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self.lbl_family_icon.setPixmap(scaled)
                self.lbl_family_icon.setToolTip(translate("frameforge", self.current_family))
                return

        self.lbl_family_icon.clear()
        self.lbl_family_icon.setToolTip("")

    def _on_fillet_toggled(self, checked):
        self._mark_dirty()
        self._update_family_icon()

    def _populate_sizes_table(self, sizes_dict):
        self.table_sizes.blockSignals(True)
        self.table_sizes.setRowCount(0)

        is_editable = bool(self.current_lib_meta and self.current_lib_meta["is_user"])

        for size_key, size_props in sizes_dict.items():
            row = self.table_sizes.rowCount()
            self.table_sizes.insertRow(row)

            for col_idx, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
                val = size_key if prop_key == "Size" else str(size_props.get(prop_key, "0"))
                item = QtWidgets.QTableWidgetItem(val)
                if not is_editable:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table_sizes.setItem(row, col_idx, item)

        self.table_sizes.blockSignals(False)
        self.table_sizes.resizeColumnsToContents()
        for col in range(self.table_sizes.columnCount()):
            w = max(self.table_sizes.columnWidth(col), 85)
            self.table_sizes.setColumnWidth(col, w)

    def _commit_current_family_edits(self):
        """Commits table and metadata edits from widgets into current_lib_data for current_family."""
        if not self.current_family or self.current_family not in self.current_lib_data:
            return
        if not (self.current_lib_meta and self.current_lib_meta["is_user"]):
            return

        sizes = {}
        seen_codes = set()
        duplicates = []
        for row in range(self.table_sizes.rowCount()):
            size_item = self.table_sizes.item(row, 0)
            if not size_item:
                continue
            size_name = size_item.text().strip()
            if not size_name:
                continue

            if size_name in seen_codes:
                duplicates.append(size_name)
            seen_codes.add(size_name)

            size_entry = {}
            for col_idx, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
                if prop_key == "Size":
                    continue
                item = self.table_sizes.item(row, col_idx)
                size_entry[prop_key] = item.text().strip() if item else "0"

            sizes[size_name] = size_entry

        if duplicates:
            raise ValueError(
                translate(
                    "frameforge",
                    "Duplicate size codes found: %s. Each size must have a unique code.",
                )
                % (", ".join(duplicates))
            )

        self.current_lib_data[self.current_family]["norm"] = self.le_norm.text().strip()
        self.current_lib_data[self.current_family]["fillet"] = self.cb_fillet.isChecked()
        self.current_lib_data[self.current_family]["sizes"] = sizes

    def _mark_dirty(self):
        self.is_dirty = True
        self._set_status(translate("frameforge", "Unsaved changes."), is_warning=True)

    def _recalculate_row_weight(self, row):
        if not self.current_family or not self.current_lib_meta:
            return

        lib_name = self.current_lib_meta.get("name", "")
        _, density = self.manager.get_library_material_info(lib_name)

        try:
            h_item = self.table_sizes.item(row, 1)
            w_item = self.table_sizes.item(row, 2)
            t_item = self.table_sizes.item(row, 3)
            tf_item = self.table_sizes.item(row, 4)

            if not (h_item and w_item and t_item):
                return

            h_str = h_item.text().strip()
            w_str = w_item.text().strip()
            t_str = t_item.text().strip()
            tf_str = tf_item.text().strip() if tf_item else ""

            if not (h_str and w_str and t_str):
                return

            h = float(h_str)
            w = float(w_str)
            t = float(t_str)
            tf = float(tf_str) if tf_str else 0.0

            calc_weight = calculate_linear_weight(
                family=self.current_family,
                width=w,
                height=h,
                thickness=t,
                density_g_cm3=density,
                flange_thickness=tf,
            )

            self.table_sizes.blockSignals(True)
            weight_item = self.table_sizes.item(row, 7)
            if not weight_item:
                weight_item = QtWidgets.QTableWidgetItem(str(calc_weight))
                self.table_sizes.setItem(row, 7, weight_item)
            else:
                weight_item.setText(str(calc_weight))
            self.table_sizes.blockSignals(False)
        except Exception:
            pass

    def _on_table_item_changed(self, item):
        self._mark_dirty()
        if item and item.column() in (1, 2, 3, 4):
            self._recalculate_row_weight(item.row())

    def _on_new_library(self):
        dlg = NewLibraryDialog(self, title="New Library", default_material="Steel")
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        name, mat, dens, _ = dlg.get_values()
        if not name:
            return

        initial_weight = "1.037"
        try:
            initial_weight = str(
                calculate_linear_weight(
                    family="Square Hollow",
                    width=50,
                    height=50,
                    thickness=2,
                    density_g_cm3=dens,
                )
            )
        except Exception:
            pass

        default_data = {
            "_metadata": {"name": name, "material": mat, "density": dens},
            "Square Hollow": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Flange Thickness": "0",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": initial_weight,
                    }
                },
            },
        }

        try:
            self.manager.save_user_library(
                name, default_data, overwrite=False, material=mat, density=dens
            )
        except FileExistsError:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "A library named '%s' or equivalent file already exists.") % name,
            )
            return

        self.refresh_libraries(select_name=name)
        self._set_status(translate("frameforge", "Library '%s' created successfully.") % name)

    def _on_duplicate_library(self):
        if not self.current_lib_meta:
            return

        source_name = self.current_lib_meta["name"]
        source_mat, _ = self.manager.get_library_material_info(source_name)
        default_name = translate("frameforge", "%s Custom") % source_name

        dlg = NewLibraryDialog(
            self,
            title="Duplicate Library",
            default_name=default_name,
            default_material=source_mat,
            is_duplicate=True,
        )
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        new_name, target_mat, target_dens, recalc = dlg.get_values()
        if not new_name:
            return

        try:
            self.manager.duplicate_library(
                source_name,
                new_name,
                overwrite=False,
                target_material=target_mat,
                target_density=target_dens,
                recalculate_weights=recalc,
            )
        except FileExistsError:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "A library named '%s' or equivalent file already exists.") % new_name,
            )
            return

        self.refresh_libraries(select_name=new_name)
        self._set_status(translate("frameforge", "Library duplicated as '%s'.") % new_name)

    def _on_delete_library(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        name = self.current_lib_meta["name"]
        reply = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Confirm deletion"),
            translate("frameforge", "Are you sure you want to delete library '%s'?") % name,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.manager.delete_user_library(name)
            self.refresh_libraries()
            self._set_status(translate("frameforge", "Library '%s' deleted.") % name)

    def _on_add_family(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        fam, ok = QtWidgets.QInputDialog.getItem(
            self,
            translate("frameforge", "Add Family"),
            translate("frameforge", "Select geometric family:"),
            KNOWN_FAMILIES,
            0,
            False,
        )
        if not ok or not fam:
            return

        if fam not in self.current_lib_data:
            self.current_lib_data[fam] = {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {},
            }
            self._populate_families(select_family=fam)
            self._mark_dirty()

    def _on_delete_family(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        fam = self.combo_family.currentText()
        if not fam:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Delete Family"),
            translate("frameforge", "Delete family '%s' and all its dimensions?") % fam,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            del self.current_lib_data[fam]
            self._populate_families()
            self._mark_dirty()

    def _on_add_size(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return
        if not self.current_family or self.current_family not in self.current_lib_data:
            self._set_status(
                translate("frameforge", "You must select or create a family before adding dimensions."),
                is_warning=True,
            )
            return

        existing_codes = set()
        for r in range(self.table_sizes.rowCount()):
            item = self.table_sizes.item(r, 0)
            if item and item.text().strip():
                existing_codes.add(item.text().strip())

        base_code = "New_50x50x2"
        candidate_code = base_code
        counter = 1
        while candidate_code in existing_codes:
            candidate_code = f"{base_code}_{counter}"
            counter += 1

        row = self.table_sizes.rowCount()
        self.table_sizes.insertRow(row)

        calc_w = "0"
        try:
            lib_name = self.current_lib_meta.get("name", "")
            _, density = self.manager.get_library_material_info(lib_name)
            calc_w = str(
                calculate_linear_weight(
                    family=self.current_family,
                    width=50.0,
                    height=50.0,
                    thickness=2.0,
                    density_g_cm3=density,
                    flange_thickness=0.0,
                )
            )
        except Exception:
            pass

        default_vals = [candidate_code, "50", "50", "2", "0", "0", "0", calc_w]
        for col, val in enumerate(default_vals):
            self.table_sizes.setItem(row, col, QtWidgets.QTableWidgetItem(val))

        self.table_sizes.selectRow(row)
        self._mark_dirty()

    def _on_delete_size(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        row = self.table_sizes.currentRow()
        if row >= 0:
            self.table_sizes.removeRow(row)
            self._mark_dirty()

    def _on_calc_weight(self):
        """Calculates theoretical linear weight for selected row or all rows."""
        row = self.table_sizes.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(
                self, translate("frameforge", "Information"), translate("frameforge", "Select a row to calculate weight.")
            )
            return

        # Prompt for material density
        density_items = [f"{mat} ({dens} g/cm³)" for mat, dens in STANDARD_DENSITIES.items()]
        item, ok = QtWidgets.QInputDialog.getItem(
            self,
            translate("frameforge", "Material Density"),
            translate("frameforge", "Select material for weight calculation:"),
            density_items,
            0,
            False,
        )
        if not ok:
            return

        # Extract density
        mat_key = item.rsplit(" (", 1)[0]
        density = STANDARD_DENSITIES.get(mat_key, 2.70)

        family = self.combo_family.currentText()
        try:
            h = float(self.table_sizes.item(row, 1).text())
            w = float(self.table_sizes.item(row, 2).text())
            t = float(self.table_sizes.item(row, 3).text())
            tf = float(self.table_sizes.item(row, 4).text()) if self.table_sizes.item(row, 4) else 0.0

            calc_weight = calculate_linear_weight(
                family=family, width=w, height=h, thickness=t, density_g_cm3=density, flange_thickness=tf
            )
            # Column 7 is Weight
            self.table_sizes.setItem(row, 7, QtWidgets.QTableWidgetItem(str(calc_weight)))
            self._mark_dirty()
            self._set_status(translate("frameforge", "Calculated weight: %s kg/m (%s)") % (calc_weight, mat_key))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Error"), translate("frameforge", "Could not calculate weight: %s") % e)
            self._set_status(translate("frameforge", "Error calculating weight: %s") % e, is_error=True)

    def _on_save_library(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        if self.table_sizes.rowCount() > 0 and (not self.current_family or self.current_family not in self.current_lib_data):
            self._set_status(
                translate("frameforge", "Cannot save orphan dimensions without an active family."),
                is_error=True,
            )
            return

        # Commit active family edits before saving
        try:
            self._commit_current_family_edits()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Error"), str(e))
            self.lbl_status.setText(str(e))
            return

        lib_name = self.current_lib_meta["name"]
        self.manager.save_user_library(lib_name, self.current_lib_data, overwrite=True)
        self.is_dirty = False
        self._set_status(translate("frameforge", "Library '%s' saved successfully.") % lib_name)


class ManageProfileLibrariesCommand:
    """GuiCommand to open the Profile Library Manager Dialog."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "manage_profile_libraries.svg"),
            "MenuText": translate("frameforge", "Manage Profile Libraries"),
            "ToolTip": translate("frameforge", "Create, edit and manage custom profile libraries and dimensions"),
        }

    def Activated(self):
        dialog = ProfileLibraryManagerDialog(parent=Gui.getMainWindow())
        dialog.exec_()

    def IsActive(self):
        return True


if hasattr(Gui, "addCommand"):
    Gui.addCommand("FrameForge_ManageProfileLibraries", ManageProfileLibrariesCommand())

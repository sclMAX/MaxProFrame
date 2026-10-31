import copy
import html
import math
import os
import unicodedata

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe.dxf_section_dialog import DXFSectionReview, DXFUnitsDialog
from freecad.maxproframe.dxf_section_import import import_dxf_section, inspect_dxf
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    QT_TRANSLATE_NOOP,
    TRANSLATIONSPATH,
    add_command,
    get_param_group,
    translate,
)
from freecad.maxproframe.help_viewer import install_help_shortcut, show_help
from freecad.maxproframe.library_manager import (
    KNOWN_FAMILIES,
    STANDARD_DENSITIES,
    LibraryManager,
    calculate_linear_weight,
    sanitize_library_name,
)
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed

try:
    from freecad.maxproframe.custom_section_geometry import build_custom_section_face
except ImportError:
    build_custom_section_face = None

try:
    from freecad.maxproframe.section_capture import capture_section_sketch, save_section_asset
except ImportError:
    capture_section_sketch = None
    save_section_asset = None

try:
    from freecad.maxproframe.section_library import (
        SectionEditSession,
        compute_sketch_dimensions_and_weight,
        purge_unreferenced_assets,
        resolve_and_validate_asset_path,
    )
except ImportError:
    SectionEditSession = None
    compute_sketch_dimensions_and_weight = None
    purge_unreferenced_assets = None
    resolve_and_validate_asset_path = None

try:
    from freecad.maxproframe.library_manager import FILLET_FAMILIES, get_canonical_family
except ImportError:
    FILLET_FAMILIES = frozenset(
        [
            "Square Hollow",
            "Rectangular Hollow",
            "Equal Leg Angles",
            "Unequal Leg Angles",
            "HEA",
            "HEB",
            "HEM",
            "IPE",
            "IPN",
            "UPE",
            "UPN",
            "C",
        ]
    )

    def get_canonical_family(family_key, family_data=None):
        if family_data and isinstance(family_data, dict) and "canonical_family" in family_data:
            return family_data["canonical_family"]
        return family_key


class _HeaderBadge(QtWidgets.QLabel):
    """Content-sized label that can shrink without losing its full public text."""

    _TEXT_INSET_X = 9
    _TEXT_INSET_Y = 6

    def __init__(self):
        super().__init__()
        self.setTextFormat(QtCore.Qt.PlainText)
        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)

    def minimumSizeHint(self):
        self.ensurePolished()
        return QtCore.QSize(
            0,
            max(
                self.fontMetrics().height() + 2 * self._TEXT_INSET_Y,
                self.sizeHint().height(),
            ),
        )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setFixedHeight(self.minimumSizeHint().height())
            self.updateGeometry()

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOption()
        option.initFrom(self)
        painter.drawPrimitive(QtWidgets.QStyle.PE_Widget, option)
        rect = self.rect().adjusted(self._TEXT_INSET_X, self._TEXT_INSET_Y, -self._TEXT_INSET_X, -self._TEXT_INSET_Y)
        text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.ElideRight, max(0, rect.width()))
        self.style().drawItemText(
            painter,
            rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            option.palette,
            self.isEnabled(),
            text,
            self.foregroundRole(),
        )


class NewLibraryDialog(QtWidgets.QDialog):
    """Modal dialog for creating or duplicating a library with material selection."""

    def __init__(
        self,
        parent=None,
        title="New Library",
        default_name="",
        default_material="Steel",
        is_duplicate=False,
        is_folder=False,
        user_dir=None,
        default_density=None,
    ):
        super().__init__(parent)
        self._destination_manager = LibraryManager(user_dir=user_dir)
        self._custom_destination = None
        self._help_topic = "duplicate" if is_duplicate else "new-library"
        self.setWindowTitle(translate("frameforge", title))
        self.resize(380, 160)

        layout = QtWidgets.QVBoxLayout(self)

        if is_folder:
            lbl_info = QtWidgets.QLabel(
                translate(
                    "frameforge",
                    "Folder libraries require an empty folder on disk. Existing legacy data is not automatically moved.",
                )
            )
            lbl_info.setWordWrap(True)
            lbl_info.setStyleSheet("padding-bottom: 4px;")
            layout.addWidget(lbl_info)

        # Name row
        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Library Name:")))
        self.le_name = QtWidgets.QLineEdit(default_name)
        layout.addWidget(self.le_name)

        # Material row
        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Material / Density:")))
        self.combo_material = QtWidgets.QComboBox()
        for mat, dens in STANDARD_DENSITIES.items():
            self.combo_material.addItem(f"{translate('frameforge', mat)} ({dens} g/cm³)", (mat, dens))

        if default_material not in STANDARD_DENSITIES:
            density = default_density if default_density is not None else 7.85
            self.combo_material.addItem(f"{default_material} ({density} g/cm³)", (default_material, density))

        # Preselect default material, retaining the source's explicit density.
        for i in range(self.combo_material.count()):
            mat_key, _ = self.combo_material.itemData(i)
            if mat_key.lower() == default_material.lower():
                if default_density is not None:
                    self.combo_material.setItemData(i, (mat_key, default_density))
                    self.combo_material.setItemText(i, f"{translate('frameforge', mat_key)} ({default_density} g/cm³)")
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

        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Library Folder:")))
        destination_row = QtWidgets.QHBoxLayout()
        self.le_destination = QtWidgets.QLineEdit()
        self.le_destination.setReadOnly(True)
        destination_row.addWidget(self.le_destination, 1)
        self.btn_destination = QtWidgets.QPushButton(translate("frameforge", "Choose Folder…"))
        self.btn_destination.clicked.connect(self._choose_destination)
        destination_row.addWidget(self.btn_destination)
        layout.addLayout(destination_row)
        self.le_name.textChanged.connect(self._update_destination)
        self._update_destination()

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(self._on_help)
        layout.addWidget(btn_box)
        install_help_shortcut(self, self._on_help)

    def _on_help(self):
        show_help(self, self._help_topic)

    def _update_destination(self):
        path = self._custom_destination or self._destination_manager.get_default_library_folder(self.le_name.text())
        self.le_destination.setText(path)
        self.le_destination.setToolTip(path)

    def _choose_destination(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, translate("frameforge", "Select Empty Folder for Library"), self.get_destination()
        )
        if path:
            self._custom_destination = os.path.abspath(path)
            self._update_destination()

    def get_destination(self):
        return self.le_destination.text()

    def get_values(self):
        name = self.le_name.text().strip()
        mat_data = self.combo_material.itemData(self.combo_material.currentIndex())
        mat = mat_data[0] if mat_data else "Steel"
        dens = mat_data[1] if mat_data else 7.85
        recalc = self.cb_recalc.isChecked() if self.cb_recalc else False
        return name, mat, dens, recalc


class AddFamilyDialog(QtWidgets.QDialog):
    """Modal dialog for selecting a profile family and choosing fillet variant at creation time."""

    def __init__(self, parent=None, current_lib_meta=None):
        super().__init__(parent)
        self.setWindowTitle(translate("frameforge", "Add Family"))
        self.resize(360, 420)
        self.current_lib_meta = current_lib_meta

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel(translate("frameforge", "Select geometric family:")))

        self.list_families = QtWidgets.QListWidget()
        self.list_families.setIconSize(QtCore.QSize(60, 30))
        for fam_key in KNOWN_FAMILIES:
            img_name = f"{fam_key.replace(' ', '_')}.png"
            img_path = os.path.join(PROFILEIMAGES_PATH, "Metal", img_name)
            if not os.path.isfile(img_path):
                img_path = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            item = QtWidgets.QListWidgetItem(translate("frameforge", fam_key))
            if os.path.isfile(img_path):
                item.setIcon(QtGui.QIcon(img_path))
            item.setData(QtCore.Qt.UserRole, fam_key)
            self.list_families.addItem(item)

        self.list_families.currentItemChanged.connect(self._on_family_selected)
        layout.addWidget(self.list_families, 1)

        # Preview diagram
        preview_container = QtWidgets.QHBoxLayout()
        self.lbl_preview = QtWidgets.QLabel()
        self.lbl_preview.setFixedSize(120, 60)
        self.lbl_preview.setAlignment(QtCore.Qt.AlignCenter)
        preview_container.addStretch()
        preview_container.addWidget(self.lbl_preview)
        preview_container.addStretch()
        layout.addLayout(preview_container)

        # Fillet option
        self.cb_fillet = QtWidgets.QCheckBox(translate("frameforge", "With Fillet"))
        self.cb_fillet.toggled.connect(self._on_fillet_toggled)
        layout.addWidget(self.cb_fillet)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.helpRequested.connect(self._on_help)
        layout.addWidget(btn_box)
        install_help_shortcut(self, self._on_help)

        if self.list_families.count() > 0:
            self.list_families.setCurrentRow(0)

    def _on_help(self):
        show_help(self, "families")

    def select_family(self, fam_key):
        for row in range(self.list_families.count()):
            item = self.list_families.item(row)
            if item.data(QtCore.Qt.UserRole) == fam_key or item.text() == fam_key:
                self.list_families.setCurrentItem(item)
                break

    def _on_family_selected(self, current, previous):
        if not current:
            self.cb_fillet.setEnabled(False)
            self.cb_fillet.setChecked(False)
            self._update_preview()
            return
        fam_key = current.data(QtCore.Qt.UserRole)
        can_fillet = (fam_key in FILLET_FAMILIES) or (fam_key == "C")
        self.cb_fillet.setEnabled(can_fillet)
        if not can_fillet and self.cb_fillet.isChecked():
            self.cb_fillet.setChecked(False)
        self._update_preview()

    def _on_fillet_toggled(self, checked):
        self._update_preview()

    def _update_preview(self):
        current = self.list_families.currentItem()
        if not current:
            self.lbl_preview.clear()
            return
        fam_key = current.data(QtCore.Qt.UserRole)
        fillet = self.cb_fillet.isChecked() and self.cb_fillet.isEnabled()
        base_name = fam_key.replace(" ", "_")
        candidates = []
        if fillet:
            candidates.append(f"{base_name}_Fillet.png")
        candidates.append(f"{base_name}.png")

        img_path = None
        lib_name = (self.current_lib_meta or {}).get("name", "Metal")
        for c in candidates:
            for d in [lib_name, "Metal"]:
                p = os.path.join(PROFILEIMAGES_PATH, d, c)
                if os.path.isfile(p):
                    img_path = p
                    break
            if not img_path:
                p = os.path.join(PROFILEIMAGES_PATH, c)
                if os.path.isfile(p):
                    img_path = p
                    break
            if img_path:
                break
        if not img_path:
            wh = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            if os.path.isfile(wh):
                img_path = wh

        if img_path and os.path.isfile(img_path):
            pix = QtGui.QPixmap(img_path)
            if not pix.isNull():
                target_w = max(self.lbl_preview.width() - 8, 20)
                target_h = max(self.lbl_preview.height() - 8, 20)
                scaled = pix.scaled(
                    QtCore.QSize(target_w, target_h),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self.lbl_preview.setPixmap(scaled)
                return
        self.lbl_preview.clear()

    def get_values(self):
        current = self.list_families.currentItem()
        if not current:
            return None, False
        fam_key = current.data(QtCore.Qt.UserRole)
        fillet = self.cb_fillet.isChecked() and self.cb_fillet.isEnabled()
        return fam_key, fillet


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
        ("Lip Length", "Lip Length [mm]"),
    ]

    # Legacy inspection/cleanup attributes; native translators are never stored here.
    _translator = None
    _translator_installed = False

    @classmethod
    def uninstall_translations(cls):
        """Compatibility no-op: application translators belong to FreeCAD.

        Older callers use this during dialog cleanup. Closing one consumer must
        not remove translations used by other windows or the workbench.
        """
        pass

    @classmethod
    def ensure_translations_loaded(cls):
        """Let FreeCAD own catalogs, selected language and application lifetime.

        Do not cache discovery success here: an unavailable catalog can become
        available later. A dialog must never remove application translations.
        """
        Gui.addLanguagePath(TRANSLATIONSPATH)
        Gui.updateLocale()

    @property
    def is_dirty(self):
        return getattr(self, "_is_dirty", False)

    @is_dirty.setter
    def is_dirty(self, value):
        self._is_dirty = bool(value)
        button = getattr(self, "btn_save", None)
        if button is not None:
            metadata = self.current_lib_meta or {}
            button.setEnabled(self._is_dirty and bool(metadata.get("is_user")))

    def __init__(self, parent=None, library_manager=None):
        super().__init__(parent)
        keep_alive_until_destroyed(self)
        self.ensure_translations_loaded()
        self.manager = library_manager or LibraryManager()
        self.current_lib_meta = None
        self.current_lib_data = {}
        self.current_family = None
        self.is_dirty = False
        self._staged_deleted_assets = set()
        self._staged_new_assets = set()
        self._active_edit_session = None
        self._profile_editor = None
        self._previous_workbench = None
        self._dxf_review = None
        self._dxf_previous_doc = None
        self._dxf_restore_visible = False
        self._is_hidden_for_sketch_edit = False
        self._sketch_edit_observer = None
        self._sketch_edit_poll_timer = None
        self._is_closed = False

        self.setWindowTitle("MaxProFrame")
        self.setWindowFlags(
            (self.windowFlags() & ~QtCore.Qt.WindowType_Mask)
            | QtCore.Qt.Window
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )
        self.setMinimumSize(800, 500)
        self.resize(920, 580)

        self._build_ui()
        self._restore_window_geometry()
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
        header_row = QtWidgets.QHBoxLayout()
        header_row.addWidget(header, 1)
        self.btn_help = QtWidgets.QToolButton()
        self.btn_help.setText("?")
        self.btn_help.setToolTip(translate("frameforge", "Help (F1)"))
        self.btn_help.clicked.connect(self._on_help)
        header_row.addWidget(self.btn_help, 0, QtCore.Qt.AlignTop)
        main_layout.addLayout(header_row)
        install_help_shortcut(self, self._on_help)

        # Content Splitter (Left: Libraries, Right: Details/Sizes)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter = splitter
        main_layout.addWidget(splitter, 1)

        # --- LEFT PANEL: Libraries list & actions ---
        self.left_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.left_splitter.setHandleWidth(6)
        lib_widget = QtWidgets.QWidget()
        lib_layout = QtWidgets.QVBoxLayout(lib_widget)
        lib_layout.setContentsMargins(0, 0, 0, 0)

        lib_header = QtWidgets.QHBoxLayout()
        lib_header.addWidget(QtWidgets.QLabel(translate("frameforge", "<b>Available Libraries:</b>")), 1)
        self.btn_new_lib = self._compact_button("list-add.svg", "New Library", self._on_new_library)
        self.btn_import_lib = self._compact_button("import_library.svg", "Import Library", self._on_import_library)
        # The menu owns activation: a toolbar click must not also import a ZIP.
        self.btn_import_lib.clicked.disconnect(self._on_import_library)
        self.btn_import_lib.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        import_menu = QtWidgets.QMenu(self.btn_import_lib)
        import_menu.addAction(translate("frameforge", "Import ZIP…"), self._on_import_library)
        import_menu.addAction(translate("frameforge", "Register Folder Library"), self._on_register_folder_library)
        self.btn_import_lib.setMenu(import_menu)
        self.btn_export_lib = self._compact_button("export_library.svg", "Export Library", self._on_export_library)
        self.btn_export_lib.setEnabled(False)
        self.btn_dup_lib = self._compact_button("duplicate.svg", "Duplicate Library", self._on_duplicate_library)
        self.btn_del_lib = self._compact_button("list-remove.svg", "Delete Library", self._on_delete_library)
        for button in (
            self.btn_new_lib,
            self.btn_del_lib,
            self.btn_import_lib,
            self.btn_dup_lib,
            self.btn_export_lib,
        ):
            lib_header.addWidget(button)
        lib_layout.addLayout(lib_header)
        self.list_libraries = QtWidgets.QListWidget()
        self.list_libraries.setToolTip(
            translate("frameforge", "Select a library to see its families. [System] libraries are read-only.")
        )
        self.list_libraries.currentItemChanged.connect(self._on_library_selection_changed)
        self.list_libraries.itemSelectionChanged.connect(self._update_section_buttons)
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
        self.list_families.setToolTip(translate("frameforge", "Select a family to see its profiles."))
        self.list_families.currentItemChanged.connect(self._on_family_selection_changed)
        self.list_families.itemSelectionChanged.connect(self._update_section_buttons)
        family_layout.addWidget(self.list_families, 1)
        self.lbl_families_empty = QtWidgets.QLabel()
        self.lbl_families_empty.setWordWrap(True)
        self.lbl_families_empty.hide()
        family_layout.addWidget(self.lbl_families_empty)

        # Hidden raw-key selector retained for legacy callers; the list is the visible selector.
        self.combo_family = QtWidgets.QComboBox(family_widget)
        self.combo_family.hide()
        self.combo_family.currentIndexChanged.connect(self._on_family_changed)

        self.left_splitter.addWidget(lib_widget)
        self.left_splitter.addWidget(family_widget)
        self.left_splitter.setSizes([180, 320])
        self.left_splitter.setStretchFactor(0, 1)
        self.left_splitter.setStretchFactor(1, 1)
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
        self.lbl_lib_banner = _HeaderBadge()
        self.lbl_lib_banner.setStyleSheet("padding: 5px 8px; border-radius: 4px; font-weight: bold;")

        self.lbl_family_name = _HeaderBadge()
        self.lbl_family_name.setStyleSheet("padding: 5px 8px; border-radius: 4px;")
        family_badge_row = QtWidgets.QHBoxLayout()
        family_badge_row.setContentsMargins(0, 0, 0, 0)
        family_badge_row.setSpacing(4)
        family_badge_row.addWidget(self.lbl_lib_banner)
        family_badge_row.addWidget(QtWidgets.QLabel("-"))
        family_badge_row.addWidget(self.lbl_family_name)
        family_badge_row.addStretch(1)
        header_details_layout.addLayout(family_badge_row)

        # Metadata and compact size actions
        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addWidget(QtWidgets.QLabel(translate("frameforge", "Standard / Ref:")))
        self.le_norm = QtWidgets.QLineEdit()
        self.le_norm.setToolTip(
            translate("frameforge", "Standard or catalog reference of this family, for example EN 10219.")
        )
        self.le_norm.textChanged.connect(self._mark_dirty)
        meta_row.addWidget(self.le_norm, 1)

        self.btn_add_size = self._compact_button("list-add.svg", "Add Size", self._on_add_size)
        self.btn_del_size = self._compact_button("list-remove.svg", "Remove Size", self._on_delete_size)
        self.btn_capture_section = self._compact_button(
            "capture_section.svg", "Capture Section", self._on_capture_section
        )
        self.btn_import_dxf = self._compact_button("import_dxf.svg", "Import DXF", self._on_import_dxf)
        self.btn_edit_section = self._compact_button("duplicate.svg", "Edit Section", self._on_edit_section)
        self.btn_apply_edit = self._compact_button("recompute.svg", "Apply Section Edit", self.apply_section_edit)
        self.btn_apply_edit.setEnabled(False)

        meta_row.addWidget(self.btn_add_size)
        meta_row.addWidget(self.btn_del_size)
        meta_row.addWidget(self.btn_capture_section)
        meta_row.addWidget(self.btn_import_dxf)
        # Keep legacy callers without orphan top-level widgets after removing the toolbar entries.
        for button in (self.btn_edit_section, self.btn_apply_edit):
            button.setParent(self)
            button.hide()

        header_details_layout.addLayout(meta_row)
        header_layout.addLayout(header_details_layout, 1)

        right_layout.addLayout(header_layout)

        search_row = QtWidgets.QHBoxLayout()
        self.le_search = QtWidgets.QLineEdit()
        self.le_search.setPlaceholderText(translate("frameforge", "Search this family…"))
        self.le_search.setClearButtonEnabled(True)
        self.le_search.setToolTip(translate("frameforge", "Filter the profiles of this family by code or description."))
        self.le_search.textChanged.connect(self._filter_profiles)
        search_row.addWidget(self.le_search, 1)
        self.lbl_profile_count = QtWidgets.QLabel()
        search_row.addWidget(self.lbl_profile_count)
        right_layout.addLayout(search_row)
        self.lbl_profiles_empty = QtWidgets.QLabel()
        right_layout.addWidget(self.lbl_profiles_empty)
        # Next step for an empty family, kept apart from the empty-state message itself.
        self.lbl_profiles_hint = QtWidgets.QLabel()
        self.lbl_profiles_hint.setWordWrap(True)
        self.lbl_profiles_hint.hide()
        right_layout.addWidget(self.lbl_profiles_hint)

        # Sizes Table
        self.table_sizes = QtWidgets.QTableWidget()
        self.table_sizes.setToolTip(
            translate("frameforge", "Profiles of this family: one row per size, dimensions in mm and weight in kg/m.")
        )
        self.table_sizes.setColumnCount(len(self.TABLE_COLUMNS))
        self.table_sizes.setHorizontalHeaderLabels([translate("frameforge", col[1]) for col in self.TABLE_COLUMNS])
        self.table_sizes.horizontalHeader().setStretchLastSection(True)
        self.table_sizes.itemChanged.connect(self._on_table_item_changed)
        self.table_sizes.itemSelectionChanged.connect(self._update_section_buttons)
        right_layout.addWidget(self.table_sizes, 1)

        # Custom Profile Cards view
        from freecad.maxproframe.custom_profile_cards import CustomProfileCardsView

        self.cards_view = CustomProfileCardsView(dialog=self)
        self.cards_view.setObjectName("custom_profile_cards")
        right_layout.addWidget(self.cards_view, 1)
        self.cards_view.hide()
        self.table_sizes.itemSelectionChanged.connect(self.cards_view.on_table_selection_changed)

        splitter.addWidget(right_widget)
        splitter.setSizes([320, 640])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Bottom Bar: Status and Save / Close
        bottom_layout = QtWidgets.QHBoxLayout()
        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        bottom_layout.addWidget(self.lbl_status, 1)

        self.btn_save = QtWidgets.QPushButton(translate("frameforge", "Save Changes"))
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip(translate("frameforge", "Save the pending changes of this library."))
        self.btn_save.clicked.connect(self._on_save_library)
        self.btn_close = QtWidgets.QPushButton(translate("frameforge", "Close"))
        self.btn_close.setToolTip(translate("frameforge", "Close the library manager."))
        self.btn_close.clicked.connect(self.close)

        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_close)
        main_layout.addLayout(bottom_layout)

        # Guide topic per area; help_topic() reads it from the focused widget or its parents.
        for topic, widgets in (
            (
                "libraries",
                (
                    self.list_libraries,
                    self.btn_new_lib,
                    self.btn_del_lib,
                    self.btn_import_lib,
                    self.btn_dup_lib,
                    self.btn_export_lib,
                ),
            ),
            ("families", (self.list_families, self.btn_add_family, self.btn_del_family, self.le_norm)),
            ("sizes", (self.table_sizes, self.le_search, self.btn_add_size, self.btn_del_size)),
            ("custom-profiles", (self.cards_view, self.btn_capture_section, self.btn_import_dxf)),
            ("saving", (self.btn_save,)),
        ):
            for widget in widgets:
                widget.setProperty("helpTopic", topic)

    def help_topic(self):
        """Guide topic for the focused area, otherwise for the current selection."""
        widget = self.focusWidget()
        while widget is not None and widget is not self:
            topic = widget.property("helpTopic")
            if topic:
                return topic
            widget = widget.parentWidget()
        if self.current_family and self.current_family in self.current_lib_data:
            fam_data = self.current_lib_data[self.current_family]
            if get_canonical_family(self.current_family, fam_data) == "Custom Profile":
                return "custom-profiles"
            return "sizes"
        if self.current_lib_meta and not self.current_lib_meta.get("is_user"):
            return "duplicate"
        return "libraries"

    def _on_help(self):
        show_help(self, self.help_topic())

    def _compact_button(self, icon, tooltip, callback):
        button = QtWidgets.QToolButton()
        if isinstance(icon, QtGui.QIcon):
            button.setIcon(icon)
        elif isinstance(icon, QtWidgets.QStyle.StandardPixmap):
            button.setIcon(self.style().standardIcon(icon))
        else:
            button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, icon)))
        button.setToolTip(translate("frameforge", tooltip))
        button.setFixedSize(26, 26)
        button.clicked.connect(callback)
        return button

    def refresh_libraries(self, select_name=None):
        try:
            libs = self.manager.list_libraries()
        except Exception as err:
            QtWidgets.QMessageBox.critical(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Failed to load libraries: %s") % str(err),
            )
            self._set_status(translate("frameforge", "Error loading libraries: %s") % str(err), is_error=True)
            return False

        self._refresh_load_error = None
        self._in_refresh = True
        target_item = None
        fallback_item = None
        item_to_select = None
        try:
            self.list_libraries.blockSignals(True)
            self.list_libraries.clear()

            current_name = self.current_lib_meta.get("name") if self.current_lib_meta else None

            for lib in libs:
                if lib.get("is_folder"):
                    tag = translate("frameforge", "[Folder] ")
                elif lib.get("is_user"):
                    tag = translate("frameforge", "[User] ")
                else:
                    tag = translate("frameforge", "[System] ")
                item = QtWidgets.QListWidgetItem(f"{tag}{lib['name']}")
                item.setData(QtCore.Qt.UserRole, lib)
                if lib.get("folder_path"):
                    item.setToolTip(lib["folder_path"])
                self.list_libraries.addItem(item)
                if select_name and lib["name"].lower() == select_name.lower():
                    target_item = item
                if current_name and lib["name"].lower() == current_name.lower():
                    fallback_item = item

            self.list_libraries.blockSignals(False)

            item_to_select = target_item
            if not item_to_select and self.list_libraries.count() > 0:
                item_to_select = fallback_item or self.list_libraries.item(0)

            if item_to_select:
                self.list_libraries.setCurrentItem(item_to_select)
        finally:
            self._in_refresh = False

        if getattr(self, "_refresh_load_error", None):
            if fallback_item and fallback_item != item_to_select:
                self.list_libraries.blockSignals(True)
                self.list_libraries.setCurrentItem(fallback_item)
                self.list_libraries.blockSignals(False)
            return False

        return True

    def _prompt_dirty_save(self, closing=False):
        """
        Handles unsaved changes before switching, creating, registering, or unregistering.
        Returns True if action can proceed, False if aborted/canceled or save failed.
        Note: Choosing Discard grants permission to proceed with the action without saving,
        but does not clear self.is_dirty immediately; dirty state is preserved if the action
        subsequently cancels or fails.
        """
        if not self.is_dirty:
            return True

        # Closing must leave even raw invalid card edits untouched on Cancel.
        # Save performs its own commit and validation after the user chooses it.
        if not closing:
            try:
                self._commit_current_family_edits()
            except ValueError as e:
                QtWidgets.QMessageBox.warning(self, translate("frameforge", "Warning"), str(e))

        reply = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Unsaved Changes"),
            (
                translate("frameforge", "You have unsaved changes. Do you want to save them before closing?")
                if closing
                else translate(
                    "frameforge",
                    "You have unsaved changes. Do you want to save them before switching libraries?",
                )
            ),
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save,
        )
        if reply == QtWidgets.QMessageBox.Save:
            self._on_save_library()
            return not self.is_dirty
        elif reply == QtWidgets.QMessageBox.Discard:
            return True
        else:
            return False

    def _on_library_selection_changed(self, current, previous):
        if not current:
            return

        if not getattr(self, "_in_refresh", False) and self.is_dirty and previous:
            if not self._prompt_dirty_save():
                self.list_libraries.blockSignals(True)
                self.list_libraries.setCurrentItem(previous)
                self.list_libraries.blockSignals(False)
                return

        lib_meta = current.data(QtCore.Qt.UserRole)
        if not lib_meta:
            return

        try:
            new_data = self.manager.get_library(lib_meta["name"])
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Error loading library '%s': %s") % (lib_meta["name"], str(e)),
            )
            self._set_status(
                translate("frameforge", "Error loading library '%s': %s") % (lib_meta["name"], str(e)),
                is_error=True,
            )
            if getattr(self, "_in_refresh", False):
                self._refresh_load_error = e
            if previous:
                self.list_libraries.blockSignals(True)
                self.list_libraries.setCurrentItem(previous)
                self.list_libraries.blockSignals(False)
            return

        # Commit state only after get_library succeeds
        self._cancel_dxf_review()
        self._cleanup_uncommitted_staged_new_assets()

        if self._active_edit_session is not None:
            self._active_edit_session.close(discard_uncommitted=True)
            self._active_edit_session = None

        self._staged_deleted_assets.clear()
        self._staged_new_assets.clear()

        self.current_family = None
        self.current_lib_meta = lib_meta
        self.current_lib_data = new_data

        is_user = lib_meta.get("is_user", False)
        is_folder = lib_meta.get("is_folder", False)
        folder_path = lib_meta.get("folder_path")

        self.btn_del_lib.setEnabled(is_user)
        self.btn_export_lib.setEnabled(is_user)
        self.btn_add_family.setEnabled(is_user)

        if is_folder:
            self.btn_del_lib.setToolTip(translate("frameforge", "Unregister Folder Library"))
            self.btn_dup_lib.setEnabled(True)
            self.btn_dup_lib.setToolTip(translate("frameforge", "Duplicate Library"))
        else:
            self.btn_del_lib.setToolTip(translate("frameforge", "Delete Library"))
            self.btn_dup_lib.setEnabled(True)
            self.btn_dup_lib.setToolTip(translate("frameforge", "Duplicate Library"))

        self._update_banner(is_user, lib_meta["name"], is_folder=is_folder, folder_path=folder_path)

        self._populate_families()
        self._update_section_buttons()
        self.is_dirty = False
        self._set_status("")

    def _update_banner(self, is_user, name, is_folder=False, folder_path=None):
        mat, dens = self.manager.get_library_material_info(name)
        mat_display = translate("frameforge", mat)
        if is_folder:
            self.lbl_lib_banner.setText(f"{name} | {mat_display}")
            self.lbl_lib_banner.setToolTip(f"{dens} g/cm³\n{folder_path or ''}")
        elif is_user:
            self.lbl_lib_banner.setText(f"{name} | {mat_display}")
            self.lbl_lib_banner.setToolTip(f"{dens} g/cm³")
        else:
            self.lbl_lib_banner.setText(f"{name} | {mat_display} | {translate('frameforge', 'Read-only')}")
            self.lbl_lib_banner.setToolTip(f"{dens} g/cm³")
        self.lbl_lib_banner.setFixedHeight(
            max(self.lbl_lib_banner.minimumSizeHint().height(), self.lbl_family_name.minimumSizeHint().height())
        )
        self.lbl_family_name.setFixedHeight(
            max(self.lbl_lib_banner.minimumSizeHint().height(), self.lbl_family_name.minimumSizeHint().height())
        )
        self.lbl_lib_banner.setToolTip(f"{self.lbl_lib_banner.text()}\n{self.lbl_lib_banner.toolTip()}")

    def _set_status(self, text, is_error=False, is_warning=False):
        # Retain severity metadata without imposing a color scheme.
        self.lbl_status.setProperty("is_error", bool(is_error))
        self.lbl_status.setProperty("is_warning", bool(is_warning))
        self.lbl_status.setText(text)

    def _get_family_display_name(self, family_key, family_data=None):
        if not family_key:
            return ""
        if family_data is None:
            family_data = self.current_lib_data.get(family_key, {})
        if isinstance(family_data, dict) and "canonical_family" in family_data:
            canonical = family_data["canonical_family"]
            has_fillet = bool(family_data.get("fillet", False))
            if has_fillet:
                return f"{translate('frameforge', canonical)} ({translate('frameforge', 'Fillet')})"
            elif family_key.endswith(" (No Fillet)"):
                return f"{translate('frameforge', canonical)} ({translate('frameforge', 'No Fillet')})"
            else:
                return translate("frameforge", canonical)
        return translate("frameforge", family_key)

    def _populate_families(self, select_family=None):
        self.combo_family.blockSignals(True)
        self.list_families.blockSignals(True)
        self.combo_family.clear()
        self.list_families.clear()

        families = sorted(k for k in self.current_lib_data if not k.startswith("_"))
        for fam_key in families:
            self.combo_family.addItem(fam_key)
            fam_data = self.current_lib_data.get(fam_key, {})
            has_fillet = bool(fam_data.get("fillet", False)) if isinstance(fam_data, dict) else False
            is_explicit = bool(isinstance(fam_data, dict) and "canonical_family" in fam_data)

            if is_explicit and has_fillet:
                img_path = self._get_family_image_path(fam_key, fillet=True)
            else:
                img_path = self._get_family_image_path(fam_key, fillet=False)

            display_name = self._get_family_display_name(fam_key, fam_data)
            item = QtWidgets.QListWidgetItem(display_name)
            if img_path and os.path.isfile(img_path):
                item.setIcon(QtGui.QIcon(img_path))
            item.setData(QtCore.Qt.UserRole, fam_key)
            self.list_families.addItem(item)

        if families:
            row = families.index(select_family) if select_family in families else 0
            self.combo_family.setCurrentIndex(row)
            self.list_families.setCurrentRow(row)
        if self.current_lib_meta and self.current_lib_meta.get("is_user"):
            self.lbl_families_empty.setText(
                translate("frameforge", "This library has no families yet. Add one with +.")
            )
        else:
            self.lbl_families_empty.setText(
                translate("frameforge", "This system library is read-only. Duplicate it to create your own families.")
            )
        self.lbl_families_empty.setVisible(not families)
        self.combo_family.blockSignals(False)
        self.list_families.blockSignals(False)
        self._on_family_changed()

    def _on_family_selection_changed(self, current, previous):
        if not current:
            return
        try:
            self._commit_current_family_edits()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Warning"), str(e))
            if previous:
                self.list_families.blockSignals(True)
                self.list_families.setCurrentItem(previous)
                self.list_families.blockSignals(False)
            return

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
            if self.current_family:
                self.list_families.blockSignals(True)
                prev_idx = self.combo_family.findText(self.current_family)
                if prev_idx >= 0:
                    self.combo_family.setCurrentIndex(prev_idx)
                    self.list_families.setCurrentRow(prev_idx)
                self.list_families.blockSignals(False)
            return

        family_name = self.combo_family.currentText()
        self.current_family = family_name

        is_user = bool(self.current_lib_meta and self.current_lib_meta.get("is_user"))
        has_family = bool(family_name and family_name in self.current_lib_data)

        fam_data = self.current_lib_data.get(family_name, {}) if has_family else {}
        canonical = get_canonical_family(family_name, fam_data) if has_family else ""
        is_custom_geom = canonical == "Custom Profile"

        self.btn_del_family.setEnabled(is_user and has_family)
        self.btn_add_size.setEnabled(is_user and has_family and not is_custom_geom)
        self.btn_del_size.setEnabled(is_user and has_family)
        self.le_norm.setEnabled(is_user and has_family)
        display_name = self._get_family_display_name(family_name, fam_data) if has_family else ""
        self.lbl_family_name.setText(display_name)
        self.lbl_family_name.setToolTip(display_name)
        self.lbl_family_name.setVisible(has_family)

        self._update_section_buttons()

        if not has_family:
            self.table_sizes.setRowCount(0)
            self.le_norm.setText("")
            self._update_family_icon()
            self.cards_view.hide()
            self._filter_profiles()
            return

        self.le_norm.blockSignals(True)
        self.le_norm.setText(fam_data.get("norm", ""))
        self.le_norm.blockSignals(False)

        self._update_family_icon()

        sizes_dict = fam_data.get("sizes", {})
        self._populate_sizes_table(sizes_dict)

    def _get_family_image_path(self, family_name=None, fillet=None):
        fam = family_name or self.current_family
        if not fam:
            warehouse = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
            return warehouse if os.path.isfile(warehouse) else ""

        fam_data = self.current_lib_data.get(fam, {}) if isinstance(self.current_lib_data, dict) else {}
        canonical = get_canonical_family(fam, fam_data)

        if fillet is None:
            fillet = bool(fam_data.get("fillet", False)) if isinstance(fam_data, dict) else False

        lib_name = (self.current_lib_meta or {}).get("name", "Metal")
        base_name = canonical.replace(" ", "_")

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
            p = os.path.join(PROFILEIMAGES_PATH, c)
            if os.path.isfile(p):
                return p

        warehouse = os.path.join(PROFILEIMAGES_PATH, "Warehouse.png")
        if os.path.isfile(warehouse):
            return warehouse
        return ""

    def _update_family_icon(self):
        if not self.current_family or self.current_family not in self.current_lib_data:
            self.lbl_family_icon.clear()
            self.lbl_family_icon.setToolTip("")
            return

        fam_data = self.current_lib_data.get(self.current_family, {})
        img_path = self._get_family_image_path(self.current_family)
        display_name = self._get_family_display_name(self.current_family, fam_data)
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
                self.lbl_family_icon.setToolTip(display_name)
                return

        self.lbl_family_icon.clear()
        self.lbl_family_icon.setToolTip("")

    def _update_size_columns(self):
        # Keep stable column indices and all cell values for persistence/autocalc.
        fields = {
            "Round Bar": {"Height"},
            "Pipe": {"Height", "Thickness"},
            "Flat Sections": {"Height", "Width"},
            "Square": {"Height", "Width"},
            "Square Hollow": {"Height", "Width", "Thickness", "Radius1", "Radius2"},
            "Rectangular Hollow": {"Height", "Width", "Thickness", "Radius1", "Radius2"},
            "Equal Leg Angles": {"Height", "Width", "Thickness", "Radius1", "Radius2"},
            "Unequal Leg Angles": {"Height", "Width", "Thickness", "Radius1", "Radius2"},
            "C": {"Height", "Width", "Thickness", "Lip Length", "Radius1"},
        }
        for family in ("HEA", "HEB", "HEM", "IPE"):
            fields[family] = {"Height", "Width", "Thickness", "Flange Thickness", "Radius1"}
        for family in ("UPE", "UPN", "IPN"):
            fields[family] = {key for key, _ in self.TABLE_COLUMNS if key != "Lip Length"}
        for family in ("V-Slot", "T-Slot", "T-Slot 3-Slots", "T-Slot 2-Slots", "T-Slot 2-Slots Opp", "T-Slot 1-Slot"):
            fields[family] = {"Height", "Width"}

        fields["Custom Profile"] = {"Height", "Width"}

        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data)

        # Unknown/custom geometries retain the full editor rather than lose access.
        visible = set(fields.get(canonical, {key for key, _ in self.TABLE_COLUMNS}))
        visible.update(("Size", "Weight"))
        if canonical != "C":
            visible.discard("Lip Length")
        if canonical == "Custom Profile":
            visible.intersection_update({"Size", "Height", "Width", "Weight"})
        if not fam_data.get("fillet", False):
            visible.difference_update(("Radius1", "Radius2"))
        for index, (key, label) in enumerate(self.TABLE_COLUMNS):
            if key == "Height" and canonical in ("Round Bar", "Pipe"):
                label = "Diameter [mm]"
            elif key == "Radius1" and canonical == "C":
                label = "Exterior Radius [mm]"
            self.table_sizes.horizontalHeaderItem(index).setText(translate("frameforge", label))
            self.table_sizes.setColumnHidden(index, key not in visible)

        # Reorder presentation only; logical indices still drive editing and serialization.
        order = [0, 1, 2, 8, 3, 5, 7, 4, 6] if canonical == "C" else list(range(len(self.TABLE_COLUMNS)))
        header = self.table_sizes.horizontalHeader()
        for visual_index, logical_index in enumerate(order):
            header.moveSection(header.visualIndex(logical_index), visual_index)

    def _populate_sizes_table(self, sizes_dict):
        self.table_sizes.blockSignals(True)
        self.table_sizes.setRowCount(0)

        is_editable = bool(self.current_lib_meta and self.current_lib_meta["is_user"])
        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data)
        is_geometry_family = canonical == "Custom Profile"

        for size_key, size_props in sizes_dict.items():
            row = self.table_sizes.rowCount()
            self.table_sizes.insertRow(row)

            is_geom_row = is_geometry_family or (isinstance(size_props, dict) and "asset_path" in size_props)

            for col_idx, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
                val = size_key if prop_key == "Size" else str(size_props.get(prop_key, "0"))
                item = QtWidgets.QTableWidgetItem(val)
                if not is_editable:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                elif is_geom_row and prop_key != "Size":
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)

                if col_idx == 0:
                    item.setData(QtCore.Qt.UserRole, copy.deepcopy(size_props))

                self.table_sizes.setItem(row, col_idx, item)

        self._update_size_columns()
        self.table_sizes.blockSignals(False)
        self.table_sizes.resizeColumnsToContents()
        for col in range(self.table_sizes.columnCount()):
            w = max(self.table_sizes.columnWidth(col), 85)
            self.table_sizes.setColumnWidth(col, w)

        if canonical == "Custom Profile":
            self.table_sizes.hide()
            if hasattr(self, "cards_view") and self.cards_view is not None:
                self.cards_view.load_from_table(self.table_sizes, self)
                self.cards_view.show()
        else:
            if hasattr(self, "cards_view") and self.cards_view is not None:
                self.cards_view.hide()
            self.table_sizes.show()
        self._filter_profiles()

    @staticmethod
    def _search_key(text):
        return "".join(c for c in unicodedata.normalize("NFD", str(text).casefold()) if not unicodedata.combining(c))

    def _filter_profiles(self):
        if not hasattr(self, "table_sizes"):
            return
        query = self._search_key(self.le_search.text().strip())
        visible = 0
        for row in range(self.table_sizes.rowCount()):
            item = self.table_sizes.item(row, 0)
            props = item.data(QtCore.Qt.UserRole) if item else {}
            description = props.get("Description", "") if isinstance(props, dict) else ""
            matches = not query or any(
                query in self._search_key(value) for value in (item.text() if item else "", description)
            )
            self.table_sizes.setRowHidden(row, not matches)
            visible += int(matches)
        self.cards_view.filter_from_table()
        total = self.table_sizes.rowCount()
        self.lbl_profile_count.setText(translate("frameforge", "%s of %s profiles") % (visible, total))
        self.lbl_profiles_empty.setText(
            translate("frameforge", "This family has no profiles.")
            if not total
            else translate("frameforge", "No matching profiles.")
        )
        self.lbl_profiles_empty.setVisible(not visible)
        hint = ""
        if not total and self.current_family and self.current_family in self.current_lib_data:
            fam_data = self.current_lib_data[self.current_family]
            if not (self.current_lib_meta and self.current_lib_meta.get("is_user")):
                hint = translate("frameforge", "Duplicate the library to edit it.")
            elif get_canonical_family(self.current_family, fam_data) == "Custom Profile":
                hint = translate("frameforge", "Capture a section or import a DXF to add one.")
            else:
                hint = translate("frameforge", "Add a size with +.")
        self.lbl_profiles_hint.setText(hint)
        self.lbl_profiles_hint.setVisible(bool(hint))
        self._update_section_buttons()

    @staticmethod
    def _has_list_selection(widget):
        current = widget.currentItem()
        return bool(current and not current.isHidden() and current in widget.selectedItems())

    def _selected_profile_row(self):
        row = self.table_sizes.currentRow()
        if row < 0 or self.table_sizes.isRowHidden(row):
            return -1
        return row if any(index.row() == row for index in self.table_sizes.selectedIndexes()) else -1

    def _commit_current_family_edits(self):
        """Commits table and metadata edits from widgets into current_lib_data for current_family."""
        if not self.current_family or self.current_family not in self.current_lib_data:
            return
        if not (self.current_lib_meta and self.current_lib_meta["is_user"]):
            return

        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data)

        if canonical == "Custom Profile" and hasattr(self, "cards_view") and self.cards_view is not None:
            self.cards_view.sync_to_table()

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

            # Retrieve original metadata stored in UserRole:
            orig_props = size_item.data(QtCore.Qt.UserRole)
            if isinstance(orig_props, dict):
                size_entry = copy.deepcopy(orig_props)
            else:
                size_entry = {}

            # Update from table columns
            for col_idx, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
                if prop_key == "Size":
                    continue
                if prop_key == "Lip Length" and canonical != "C":
                    continue
                item = self.table_sizes.item(row, col_idx)
                if item:
                    size_entry[prop_key] = item.text().strip()
                elif prop_key not in size_entry:
                    size_entry[prop_key] = "0"

            was_blocked = self.table_sizes.blockSignals(True)
            try:
                size_item.setData(QtCore.Qt.UserRole, copy.deepcopy(size_entry))
            finally:
                self.table_sizes.blockSignals(was_blocked)
            sizes[size_name] = size_entry

        if duplicates:
            raise ValueError(
                translate(
                    "frameforge",
                    "Duplicate size codes found: %s. Each size must have a unique code.",
                )
                % (", ".join(duplicates))
            )

        if canonical == "Custom Profile":
            for name, entry in sizes.items():
                w_str = str(entry.get("Weight", "")).strip()
                try:
                    w_val = float(w_str)
                    if not math.isfinite(w_val) or w_val <= 0.0:
                        raise ValueError(f"Weight must be a positive finite number, got '{w_str}'.")
                except Exception:
                    raise ValueError(
                        translate(
                            "frameforge",
                            "Invalid weight '%s' for custom profile '%s'. Weight must be a positive finite number.",
                        )
                        % (w_str, name)
                    )

        self.current_lib_data[self.current_family]["norm"] = self.le_norm.text().strip()
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

            fam_data = self.current_lib_data.get(self.current_family, {})
            canonical = get_canonical_family(self.current_family, fam_data)
            if canonical == "Custom Profile":
                return

            if canonical == "C":
                r1_item = self.table_sizes.item(row, 5)
                lip_item = self.table_sizes.item(row, 8) if self.table_sizes.columnCount() > 8 else None
                r1_str = r1_item.text().strip() if r1_item else ""
                lip_str = lip_item.text().strip() if lip_item else ""
                r1 = float(r1_str) if r1_str else 0.0
                lip = float(lip_str) if lip_str else 0.0
                is_fillet = bool(fam_data.get("fillet", False))
                calc_weight = calculate_linear_weight(
                    family=canonical,
                    width=w,
                    height=h,
                    thickness=t,
                    density_g_cm3=density,
                    flange_thickness=tf,
                    lip_length=lip,
                    radius=r1,
                    make_fillet=is_fillet,
                )
            else:
                calc_weight = calculate_linear_weight(
                    family=canonical,
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
        if not item:
            return
        col = item.column()
        if col in (1, 2, 3, 4):
            self._recalculate_row_weight(item.row())
        elif col in (5, 8):
            fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
            canonical = get_canonical_family(self.current_family, fam_data)
            if canonical == "C":
                self._recalculate_row_weight(item.row())

        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data) if self.current_family else ""
        if canonical == "Custom Profile" and hasattr(self, "cards_view") and self.cards_view is not None:
            self.cards_view.on_table_item_changed(item)
        self._filter_profiles()

    def _on_new_library(self):
        if not self._prompt_dirty_save():
            return

        dlg = NewLibraryDialog(self, title="New Library", default_material="Steel", user_dir=self.manager.user_dir)
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
            self.manager.create_folder_library(
                dlg.get_destination(), name, data=default_data, material=mat, density=dens
            )
        except (FileExistsError, ValueError, OSError) as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Could not create library '%s': %s") % (name, str(err)),
            )
            return

        if not self.refresh_libraries(select_name=name):
            return
        self._set_status(translate("frameforge", "Library '%s' created successfully.") % name)

    def _on_import_library(self):
        if not self._prompt_dirty_save():
            return
        archive, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, translate("frameforge", "Import Library ZIP"), "", "ZIP (*.zip)"
        )
        if not archive:
            return
        try:
            meta = self.manager.import_library_zip(archive)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Could not import library: %s") % str(err),
            )
            return
        if self.refresh_libraries(select_name=meta["name"]):
            self._set_status(translate("frameforge", "Library '%s' imported successfully.") % meta["name"])

    def _on_export_library(self):
        if not self.current_lib_meta or not self.current_lib_meta.get("is_user"):
            return
        if self.is_dirty:
            reply = QtWidgets.QMessageBox.question(
                self,
                translate("frameforge", "Unsaved Changes"),
                translate("frameforge", "Save changes before exporting the library?"),
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Save,
            )
            if reply != QtWidgets.QMessageBox.Save:
                return
            self._on_save_library()
            if self.is_dirty:
                return
        name = self.current_lib_meta["name"]
        archive, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, translate("frameforge", "Export Library ZIP"), sanitize_library_name(name) + ".zip", "ZIP (*.zip)"
        )
        if not archive:
            return
        if not archive.lower().endswith(".zip"):
            archive += ".zip"
        try:
            self.manager.export_library_zip(name, archive)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Could not export library '%s': %s") % (name, str(err)),
            )
            return
        self._set_status(translate("frameforge", "Library '%s' exported successfully.") % name)

    def _on_register_folder_library(self):
        if not self._prompt_dirty_save():
            return

        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, translate("frameforge", "Select Existing Folder Library Directory")
        )
        if not folder_path:
            return

        try:
            meta = self.manager.register_folder_library(folder_path)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Could not register folder library: %s") % str(err),
            )
            return

        reg_name = meta.get("name") if isinstance(meta, dict) else None
        if not self.refresh_libraries(select_name=reg_name):
            return
        self._set_status(translate("frameforge", "Folder library '%s' registered successfully.") % reg_name)

    def _on_duplicate_library(self):
        if not self.current_lib_meta:
            return

        if not self._prompt_dirty_save():
            return

        source_name = self.current_lib_meta["name"]
        source_mat, source_density = self.manager.get_library_material_info(source_name)
        if self.current_lib_meta:
            default_name = translate("frameforge", "%s Custom") % source_name

            dlg = NewLibraryDialog(
                self,
                title="Duplicate Library",
                default_name=default_name,
                default_material=source_mat,
                default_density=source_density,
                is_duplicate=True,
                user_dir=self.manager.user_dir,
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
                    target_folder_path=dlg.get_destination(),
                )
            except (FileExistsError, ValueError, OSError) as err:
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("frameforge", "Error"),
                    translate("frameforge", "Could not duplicate library '%s': %s") % (source_name, str(err)),
                )
                return

            if not self.refresh_libraries(select_name=new_name):
                return
            self._set_status(translate("frameforge", "Library duplicated as '%s'.") % new_name)

    def _on_delete_library(self):
        if not self._has_list_selection(self.list_libraries):
            return
        if not self.current_lib_meta or not self.current_lib_meta.get("is_user", False):
            return

        if not self._prompt_dirty_save():
            return

        is_folder = self.current_lib_meta.get("is_folder", False)
        name = self.current_lib_meta["name"]

        if is_folder:
            folder_path = self.current_lib_meta.get("folder_path")
            reply = QtWidgets.QMessageBox.question(
                self,
                translate("frameforge", "Confirm Unregister"),
                translate(
                    "frameforge",
                    "Unregister folder library '%s'?\n\nAll files and sketches on disk will be kept intact.",
                )
                % name,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

            try:
                self.manager.unregister_folder_library(folder_path or name)
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("frameforge", "Error"),
                    translate("frameforge", "Could not unregister folder library '%s': %s") % (name, str(e)),
                )
                return

            self.is_dirty = False
            if not self.refresh_libraries():
                return
            self._set_status(translate("frameforge", "Folder library '%s' unregistered.") % name)
        else:
            reply = QtWidgets.QMessageBox.question(
                self,
                translate("frameforge", "Confirm deletion"),
                translate("frameforge", "Are you sure you want to delete library '%s'?") % name,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                try:
                    self.manager.delete_user_library(name)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(
                        self,
                        translate("frameforge", "Error"),
                        translate("frameforge", "Could not delete library '%s': %s") % (name, str(e)),
                    )
                    return

                self.is_dirty = False
                if not self.refresh_libraries():
                    return
                self._set_status(translate("frameforge", "Library '%s' deleted.") % name)

    def _on_add_family(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        dlg = AddFamilyDialog(self, current_lib_meta=self.current_lib_meta)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        canonical_family, with_fillet = dlg.get_values()
        if not canonical_family:
            return

        # Check for duplicates by canonical type + fillet setting
        for existing_key, existing_data in self.current_lib_data.items():
            if existing_key.startswith("_") or not isinstance(existing_data, dict):
                continue
            existing_canonical = get_canonical_family(existing_key, existing_data)
            existing_fillet = bool(existing_data.get("fillet", False))
            if existing_canonical == canonical_family and existing_fillet == with_fillet:
                fillet_label = (
                    translate("frameforge", "With Fillet") if with_fillet else translate("frameforge", "No Fillet")
                )
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("frameforge", "Warning"),
                    translate(
                        "frameforge",
                        "A family variant for '%s' (%s) already exists in this library.",
                    )
                    % (translate("frameforge", canonical_family), fillet_label),
                )
                return

        # Determine dictionary key
        if with_fillet:
            new_family_key = f"{canonical_family} (Fillet)"
        else:
            if canonical_family in self.current_lib_data:
                new_family_key = f"{canonical_family} (No Fillet)"
            else:
                new_family_key = canonical_family

        # Guard against destination-key collision before insertion
        if new_family_key in self.current_lib_data:
            fillet_label = (
                translate("frameforge", "With Fillet") if with_fillet else translate("frameforge", "No Fillet")
            )
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate(
                    "frameforge",
                    "A family variant for '%s' (%s) already exists in this library.",
                )
                % (translate("frameforge", canonical_family), fillet_label),
            )
            return

        self.current_lib_data[new_family_key] = {
            "canonical_family": canonical_family,
            "norm": "Custom",
            "unit": "Metric Units",
            "fillet": with_fillet,
            "sizes": {},
        }
        self._populate_families(select_family=new_family_key)
        self._mark_dirty()

    def _on_delete_family(self):
        if not self._has_list_selection(self.list_families):
            return
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        fam = self.combo_family.currentText()
        if not fam:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Delete Family"),
            translate("frameforge", "Delete family '%s' and all its dimensions?")
            % self._get_family_display_name(fam, self.current_lib_data.get(fam, {})),
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
            fam_data = self.current_lib_data.get(self.current_family, {})
            canonical = get_canonical_family(self.current_family, fam_data)
            calc_w = str(
                calculate_linear_weight(
                    family=canonical,
                    width=50.0,
                    height=50.0,
                    thickness=2.0,
                    density_g_cm3=density,
                    flange_thickness=0.0,
                )
            )
        except Exception:
            pass

        default_vals = {
            "Size": candidate_code,
            "Height": "50",
            "Width": "50",
            "Thickness": "2",
            "Flange Thickness": "0",
            "Radius1": "0",
            "Radius2": "0",
            "Weight": calc_w,
            "Lip Length": "0",
        }
        for col, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
            val = default_vals.get(prop_key, "0")
            self.table_sizes.setItem(row, col, QtWidgets.QTableWidgetItem(val))

        self.table_sizes.selectRow(row)
        self._mark_dirty()
        self._filter_profiles()

    def _on_delete_size(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        row = self._selected_profile_row()
        if row < 0:
            return

        size_item = self.table_sizes.item(row, 0)
        if not size_item:
            return

        # Escape the whole question so user-supplied codes cannot become rich text.
        question = translate("frameforge", "Remove size '%s'?") % size_item.text()
        reply = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Remove Size"),
            "<p>" + html.escape(question) + "</p>",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        props = size_item.data(QtCore.Qt.UserRole)
        is_folder = bool(self.current_lib_meta.get("is_folder") and self.current_lib_meta.get("folder_path"))
        folder_path = self.current_lib_meta.get("folder_path")

        if isinstance(props, dict) and "asset_path" in props:
            ap = props["asset_path"]
            if is_folder and folder_path:
                try:
                    from freecad.maxproframe.section_library import resolve_and_validate_asset_path

                    resolve_and_validate_asset_path(folder_path, ap)
                except Exception as err:
                    QtWidgets.QMessageBox.warning(
                        self,
                        translate("frameforge", "Error"),
                        translate("frameforge", "Cannot delete size with invalid asset path: %s") % str(err),
                    )
                    self._set_status(
                        translate("frameforge", "Cannot delete size with invalid asset path: %s") % str(err),
                        is_error=True,
                    )
                    return
            self._staged_deleted_assets.add(ap)

        self.table_sizes.removeRow(row)
        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data)
        if canonical == "Custom Profile" and hasattr(self, "cards_view") and self.cards_view is not None:
            self.cards_view.load_from_table(self.table_sizes, self)
        self._mark_dirty()
        self._filter_profiles()

    def _on_calc_weight(self):
        """Calculates theoretical linear weight for selected row or all rows."""
        row = self.table_sizes.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(
                self,
                translate("frameforge", "Information"),
                translate("frameforge", "Select a row to calculate weight."),
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
        fam_data = self.current_lib_data.get(family, {})
        canonical = get_canonical_family(family, fam_data)
        try:
            h = float(self.table_sizes.item(row, 1).text())
            w = float(self.table_sizes.item(row, 2).text())
            t = float(self.table_sizes.item(row, 3).text())
            tf = float(self.table_sizes.item(row, 4).text()) if self.table_sizes.item(row, 4) else 0.0
            if canonical == "C":
                r1_item = self.table_sizes.item(row, 5)
                r1 = float(r1_item.text()) if (r1_item and r1_item.text().strip()) else 0.0
                lip_item = self.table_sizes.item(row, 8) if self.table_sizes.columnCount() > 8 else None
                lip = float(lip_item.text()) if (lip_item and lip_item.text().strip()) else 0.0
                is_fillet = bool(fam_data.get("fillet", False))
                calc_weight = calculate_linear_weight(
                    family=canonical,
                    width=w,
                    height=h,
                    thickness=t,
                    density_g_cm3=density,
                    flange_thickness=tf,
                    lip_length=lip,
                    radius=r1,
                    make_fillet=is_fillet,
                )
            else:
                calc_weight = calculate_linear_weight(
                    family=canonical,
                    width=w,
                    height=h,
                    thickness=t,
                    density_g_cm3=density,
                    flange_thickness=tf,
                )
            # Column 7 is Weight
            self.table_sizes.setItem(row, 7, QtWidgets.QTableWidgetItem(str(calc_weight)))
            self._mark_dirty()
            self._set_status(translate("frameforge", "Calculated weight: %s kg/m (%s)") % (calc_weight, mat_key))
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self, translate("frameforge", "Error"), translate("frameforge", "Could not calculate weight: %s") % e
            )
            self._set_status(translate("frameforge", "Error calculating weight: %s") % e, is_error=True)

    def _on_save_library(self):
        if not self.current_lib_meta or not self.current_lib_meta["is_user"]:
            return

        if self.table_sizes.rowCount() > 0 and (
            not self.current_family or self.current_family not in self.current_lib_data
        ):
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
        is_folder = bool(self.current_lib_meta.get("is_folder") and self.current_lib_meta.get("folder_path"))
        folder_path = self.current_lib_meta.get("folder_path")

        try:
            if is_folder:
                from freecad.maxproframe.section_library import (
                    purge_unreferenced_assets,
                    resolve_and_validate_asset_path,
                )

                # Pre-validate all staged deletions before writing manifest
                for ap in self._staged_deleted_assets:
                    try:
                        resolve_and_validate_asset_path(folder_path, ap)
                    except Exception as err:
                        QtWidgets.QMessageBox.warning(
                            self,
                            translate("frameforge", "Error"),
                            translate("frameforge", "Error saving library: %s") % str(err),
                        )
                        self._set_status(translate("frameforge", "Error saving library: %s") % str(err), is_error=True)
                        return

                # Pre-validate all remaining asset paths before writing manifest
                for fam_k, fam_v in self.current_lib_data.items():
                    if fam_k.startswith("_") or not isinstance(fam_v, dict):
                        continue
                    sizes = fam_v.get("sizes", {})
                    if isinstance(sizes, dict):
                        for s_k, s_v in sizes.items():
                            if isinstance(s_v, dict):
                                ap = s_v.get("asset_path")
                                if ap and isinstance(ap, str):
                                    try:
                                        resolve_and_validate_asset_path(folder_path, ap)
                                    except Exception as err:
                                        QtWidgets.QMessageBox.warning(
                                            self,
                                            translate("frameforge", "Error"),
                                            translate("frameforge", "Error saving library: %s") % str(err),
                                        )
                                        self._set_status(
                                            translate("frameforge", "Error saving library: %s") % str(err),
                                            is_error=True,
                                        )
                                        return

                self.manager.save_folder_library(
                    folder_path,
                    self.current_lib_data,
                    overwrite=True,
                )
                if self._staged_deleted_assets:
                    purge_unreferenced_assets(
                        folder_path,
                        self._staged_deleted_assets,
                        self.current_lib_data,
                    )
                    self._staged_deleted_assets.clear()

                self._staged_new_assets.clear()
            else:
                self.manager.save_user_library(lib_name, self.current_lib_data, overwrite=True)
            self.is_dirty = False
            self._set_status(translate("frameforge", "Library '%s' saved successfully.") % lib_name)
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Error saving library: %s") % str(e),
            )
            self._set_status(translate("frameforge", "Error saving library: %s") % str(e), is_error=True)

    def _update_section_buttons(self):
        is_user = bool(self.current_lib_meta and self.current_lib_meta.get("is_user"))
        is_folder = bool(self.current_lib_meta and self.current_lib_meta.get("is_folder"))
        fam_data = self.current_lib_data.get(self.current_family, {}) if self.current_family else {}
        canonical = get_canonical_family(self.current_family, fam_data) if self.current_family else ""
        is_custom_geom = canonical == "Custom Profile"
        has_row = self._selected_profile_row() >= 0
        if hasattr(self, "btn_del_size"):
            self.btn_del_size.setEnabled(is_user and has_row)
        if hasattr(self, "btn_del_lib"):
            self.btn_del_lib.setEnabled(is_user and self._has_list_selection(self.list_libraries))
        if hasattr(self, "btn_del_family"):
            self.btn_del_family.setEnabled(is_user and self._has_list_selection(self.list_families))

        for name in ("btn_capture_section", "btn_import_dxf", "btn_edit_section", "btn_apply_edit"):
            button = getattr(self, name, None)
            if button is not None:
                button.setVisible(is_custom_geom and name not in ("btn_edit_section", "btn_apply_edit"))

        if hasattr(self, "btn_add_size"):
            self.btn_add_size.setEnabled(is_user and bool(self.current_family) and not is_custom_geom)
        if hasattr(self, "btn_import_dxf"):
            self.btn_import_dxf.setEnabled(is_user and is_folder)
        if hasattr(self, "btn_capture_section"):
            self.btn_capture_section.setEnabled(is_user and is_folder)
        if hasattr(self, "btn_edit_section"):
            self.btn_edit_section.setEnabled(is_user and is_folder and is_custom_geom and has_row)
        if hasattr(self, "btn_apply_edit"):
            self.btn_apply_edit.setEnabled(bool(self._active_edit_session and is_user and is_folder and is_custom_geom))

    def _on_capture_section(self):
        if self._dxf_review is not None:
            self._dxf_review.raise_()
            return
        if not self.current_lib_meta or not self.current_lib_meta.get("is_user"):
            return
        if not self.current_lib_meta.get("is_folder") or not self.current_lib_meta.get("folder_path"):
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Custom section capture is only available for folder libraries."),
            )
            return

        if self._is_closed or self._active_edit_session is not None:
            return
        from freecad.maxproframe.sketch_section_dialog import SketchSectionReview

        meta = self.current_lib_meta
        material, density = self.manager.get_library_material_info(meta["name"])
        review = keep_alive_until_destroyed(SketchSectionReview(meta["name"], material, density, self._add_dxf_section))
        review.library_root = os.path.realpath(meta["folder_path"])
        restore_visible = self.isVisible()
        self._dxf_review = review

        def finish(*_):
            if self._dxf_review is review:
                self._dxf_review = None
                if restore_visible and not self._is_closed:
                    self.show()
                    self.raise_()
                review.deleteLater()

        review.finished.connect(finish)
        self.hide()
        review.show()
        review.move(self.pos())

    @staticmethod
    def _section_size_entry(asset_meta, height, width, weight, weight_format=".2f"):
        return {
            "Height": f"{height:.1f}",
            "Width": f"{width:.1f}",
            "Thickness": "0.0",
            "Flange Thickness": "0.0",
            "Radius1": "0.0",
            "Radius2": "0.0",
            "Weight": format(weight, weight_format),
            "Lip Length": "0.0",
            "asset_path": asset_meta["asset_path"],
            "object_name": asset_meta["object_name"],
            "asset_id": asset_meta["asset_id"],
        }

    def _insert_section_row(self, candidate_code, size_entry):
        # Shared capture insertion keeps metadata, read-only cells and selection together.
        row = self.table_sizes.rowCount()
        self.table_sizes.insertRow(row)

        for col, (prop_key, _) in enumerate(self.TABLE_COLUMNS):
            val = candidate_code if prop_key == "Size" else size_entry.get(prop_key, "0")
            item = QtWidgets.QTableWidgetItem(str(val))
            if prop_key != "Size":
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            if col == 0:
                item.setData(QtCore.Qt.UserRole, copy.deepcopy(size_entry))
            self.table_sizes.setItem(row, col, item)

        self.table_sizes.selectRow(row)
        if hasattr(self, "cards_view") and self.cards_view is not None:
            self.cards_view.load_from_table(self.table_sizes, self)
            self.cards_view.select_card(row)
        self._mark_dirty()
        self._filter_profiles()

    def _activate_custom_section_family(self):
        if "Custom Profile" not in self.current_lib_data:
            self.current_lib_data["Custom Profile"] = {
                "norm": "Custom",
                "fillet": False,
                "canonical_family": "Custom Profile",
                "sizes": {},
            }
            self._populate_families(select_family="Custom Profile")
            self._mark_dirty()
        elif self.current_family != "Custom Profile":
            idx = self.combo_family.findText("Custom Profile")
            if idx >= 0:
                self.combo_family.setCurrentIndex(idx)

    def _on_import_dxf(self):
        if self._dxf_review is not None:
            self._dxf_review.show()
            self._dxf_review.raise_()
            return
        meta = self.current_lib_meta
        if (
            self._is_closed
            or not meta
            or not meta.get("is_user")
            or not meta.get("is_folder")
            or not meta.get("folder_path")
        ):
            return
        # Resolve an existing sketch edit explicitly before starting another owned document.
        if self._active_edit_session is not None:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Finish the active section edit before importing DXF."),
            )
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, translate("frameforge", "Import DXF"), "", "DXF (*.dxf *.DXF)"
        )
        if not path:
            return
        doc = None
        previous_doc = App.ActiveDocument.Name if App.ActiveDocument else None
        try:
            metadata = inspect_dxf(path)
            units = DXFUnitsDialog(metadata, self)
            if units.exec_() != QtWidgets.QDialog.Accepted or units.confirmed_unit() is None:
                return
            # Modal confirmation may have processed a close or library switch.
            if self._is_closed or self.current_lib_meta is not meta:
                return
            doc = App.newDocument("DXFReview")
            sketch = import_dxf_section(path, doc, unit_override=units.confirmed_unit())
            material, density = self.manager.get_library_material_info(meta["name"])
            review = keep_alive_until_destroyed(
                DXFSectionReview(sketch, meta["name"], material, density, self._add_dxf_section)
            )
            review.library_root = os.path.realpath(meta["folder_path"])
            App.setActiveDocument(doc.Name)
            Gui.setActiveDocument(doc.Name)
            view = Gui.getDocument(doc.Name).activeView()
            view.viewTop()
            view.fitAll()
            self._dxf_review = review
            self._dxf_previous_doc = previous_doc
            self._dxf_restore_visible = self.isVisible()
            review.finished.connect(lambda *_: self._finish_dxf_review(review))
            self.hide()
            review.show()
            # Keep the small controls at the viewport edge, not over the sketch.
            review.move(self.pos())
        except Exception as err:
            if doc is not None and doc.Name in App.listDocuments():
                App.closeDocument(doc.Name)
            if previous_doc in App.listDocuments():
                App.setActiveDocument(previous_doc)
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Import DXF"),
                translate("frameforge", "Could not import DXF: %s") % str(err),
            )

    def _add_dxf_section(self, code):
        review = self._dxf_review
        if review is None or self._is_closed:
            return
        meta = self.current_lib_meta or {}
        if os.path.realpath(meta.get("folder_path", "")) != review.library_root:
            self._cancel_dxf_review()
            return
        try:
            if not code:
                raise ValueError(translate("frameforge", "Enter a non-empty size code."))
            # Read current table codes as well as the inactive Custom family without committing edits.
            codes = set(self.current_lib_data.get("Custom Profile", {}).get("sizes", {}))
            if self.current_family == "Custom Profile":
                codes = {self.table_sizes.item(row, 0).text().strip() for row in range(self.table_sizes.rowCount())}
            if code in codes:
                raise ValueError(
                    translate("frameforge", "Duplicate size codes found: %s. Each size must have a unique code.") % code
                )
            # Reuse existing table/card validation without consuming unsaved catalog state.
            original_data = copy.deepcopy(self.current_lib_data)
            try:
                self._commit_current_family_edits()
            finally:
                self.current_lib_data = original_data
            build_custom_section_face(review.sketch)
            _, density = self.manager.get_library_material_info(meta["name"])
            height, width, weight, _ = compute_sketch_dimensions_and_weight(review.sketch, density)
            # No catalog/family/dirty changes until all validation and native serialization succeed.
            asset_meta = save_section_asset(meta["folder_path"], review.sketch, name=code)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                review,
                translate("frameforge", "Import DXF"),
                translate("frameforge", "Could not add section: %s") % str(err),
            )
            return
        self._staged_new_assets.add(asset_meta["asset_path"])
        self._activate_custom_section_family()
        size_entry = self._section_size_entry(asset_meta, height, width, weight, ".8g")
        description = review.le_description.text().strip()
        if description:
            size_entry["Description"] = description
        self._insert_section_row(code, size_entry)
        review.accept()

    def _cancel_dxf_review(self):
        if self._dxf_review is not None:
            self._dxf_review.reject()

    def _finish_dxf_review(self, review):
        if self._dxf_review is not review:
            return
        self._dxf_review = None
        if review.document_name in App.listDocuments():
            App.closeDocument(review.document_name)
        if self._dxf_previous_doc in App.listDocuments():
            App.setActiveDocument(self._dxf_previous_doc)
        self._dxf_previous_doc = None
        if self._dxf_restore_visible and not self._is_closed:
            self.show()
            self.raise_()
        self._dxf_restore_visible = False
        review.deleteLater()

    def _on_edit_section(self, force_gui=False):
        if self._dxf_review is not None:
            self._dxf_review.raise_()
            return
        if not self.current_lib_meta or not self.current_lib_meta.get("is_user"):
            return
        if not self.current_lib_meta.get("is_folder") or not self.current_lib_meta.get("folder_path"):
            return

        row = self.table_sizes.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(
                self,
                translate("frameforge", "Information"),
                translate("frameforge", "Select a section row to edit."),
            )
            return

        size_item = self.table_sizes.item(row, 0)
        if not size_item:
            return

        size_props = size_item.data(QtCore.Qt.UserRole)
        if not isinstance(size_props, dict) or "asset_path" not in size_props:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Selected row does not have a linked section geometry asset."),
            )
            return

        folder_path = self.current_lib_meta["folder_path"]
        asset_path = size_props["asset_path"]

        from freecad.maxproframe.section_library import SectionEditSession, resolve_and_validate_asset_path

        try:
            resolve_and_validate_asset_path(folder_path, asset_path)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Security Warning"),
                translate("frameforge", "Invalid asset path: %s") % str(err),
            )
            return

        # Close any previous active session and watcher
        self._detach_sketch_edit_watcher()
        if self._active_edit_session is not None:
            self._active_edit_session.close(discard_uncommitted=True)
            self._active_edit_session = None

        # Bind stable original row identity BEFORE session opens via QPersistentModelIndex
        p_index = QtCore.QPersistentModelIndex(self.table_sizes.model().index(row, 0))

        session = SectionEditSession(
            library_root=folder_path,
            asset_path=asset_path,
            size_code=size_item.text().strip(),
            family=self.current_family,
            library_name=self.current_lib_meta.get("name", ""),
            asset_id=size_props.get("asset_id", ""),
            persistent_index=p_index,
        )
        try:
            session.open()
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Failed to open section for editing: %s") % str(err),
            )
            return

        # Attempt entering Sketcher and activating sketch edit mode in GUI only when dialog is visible
        was_visible = bool(self.isVisible() or force_gui)
        entered_gui_edit = False

        if Gui is not None and was_visible:
            try:
                if hasattr(Gui, "activeWorkbench"):
                    try:
                        wb = Gui.activeWorkbench()
                        self._previous_workbench = wb.name() if hasattr(wb, "name") else type(wb).__name__
                    except Exception:
                        self._previous_workbench = None
                if hasattr(App, "setActiveDocument"):
                    App.setActiveDocument(session.working_doc_name)
                if hasattr(Gui, "setActiveDocument"):
                    Gui.setActiveDocument(session.working_doc_name)
                if hasattr(Gui, "activateWorkbench"):
                    Gui.activateWorkbench("SketcherWorkbench")
                gui_doc = Gui.getDocument(session.working_doc_name) if hasattr(Gui, "getDocument") else None
                if gui_doc is None or not hasattr(gui_doc, "setEdit"):
                    raise RuntimeError(
                        translate("frameforge", "Active FreeCAD GUI document not available for editing.")
                    )
                set_edit_ok = gui_doc.setEdit(session.working_sketch_name)
                if not set_edit_ok:
                    raise RuntimeError(translate("frameforge", "Failed to enter edit mode for sketch."))
                in_edit = gui_doc.getInEdit() if hasattr(gui_doc, "getInEdit") else None
                if (
                    in_edit is None
                    or getattr(in_edit, "Object", None) is None
                    or in_edit.Object.Name != session.working_sketch_name
                ):
                    raise RuntimeError(translate("frameforge", "Sketch edit mode could not be verified."))
                entered_gui_edit = True
            except Exception as err:
                session.close(discard_uncommitted=True)
                self._detach_sketch_edit_watcher()
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("frameforge", "Error"),
                    translate("frameforge", "Failed to open section for editing: %s") % str(err),
                )
                return

        self._active_edit_session = session
        self.btn_apply_edit.setEnabled(True)
        self._set_status(
            translate("frameforge", "Section opened in FreeCAD. Edit sketch, then click 'Apply Section Edit'."),
            is_warning=True,
        )

        if entered_gui_edit:
            # Watch FreeCAD GUI to restore dialog when sketch editing ends
            self._is_hidden_for_sketch_edit = True
            try:
                if Gui is not None and hasattr(Gui, "addDocumentObserver"):
                    obs = _SectionEditGuiObserver(self, session.working_doc_name)
                    self._sketch_edit_observer = obs
                    Gui.addDocumentObserver(obs)
            except Exception:
                pass

            poll_timer = QtCore.QTimer(self)
            poll_timer.setInterval(150)

            def _check_in_edit():
                if not getattr(self, "_is_hidden_for_sketch_edit", False):
                    return
                if self._active_edit_session is None:
                    self._on_sketch_edit_finished()
                    return
                d_name = self._active_edit_session.working_doc_name
                if App is not None and d_name not in App.listDocuments():
                    self._on_sketch_edit_finished()
                    return
                if Gui is not None and hasattr(Gui, "getDocument"):
                    try:
                        g_doc = Gui.getDocument(d_name)
                        if g_doc is not None and hasattr(g_doc, "getInEdit") and g_doc.getInEdit() is None:
                            self._on_sketch_edit_finished()
                    except Exception:
                        pass

            poll_timer.timeout.connect(_check_in_edit)
            self._sketch_edit_poll_timer = poll_timer
            poll_timer.start()

            # Hide library manager dialog only after confirmed edit entry
            self.hide()
        return True

    def apply_section_edit(self):
        """Applies edits made to the working sketch in FreeCAD back to the library table."""
        self._detach_sketch_edit_watcher()
        self._is_hidden_for_sketch_edit = False
        if self._active_edit_session is None:
            QtWidgets.QMessageBox.information(
                self,
                translate("frameforge", "Information"),
                translate("frameforge", "No active section edit session. Click 'Edit Section' first."),
            )
            return

        session = self._active_edit_session

        # Verify library context still matches
        current_folder = self.current_lib_meta.get("folder_path") if self.current_lib_meta else None
        if not current_folder or os.path.realpath(current_folder) != os.path.realpath(session.library_root):
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Active edit session belongs to a different library."),
            )
            return

        if self.current_family != session.family:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Active edit session belongs to a different family."),
            )
            return

        # Validate stable original row identity via persistent_index (Blocker E2)
        p_idx = getattr(session, "persistent_index", None)
        if p_idx is None or not p_idx.isValid():
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Target section row was removed or is invalid."),
            )
            session.close(discard_uncommitted=True)
            self._active_edit_session = None
            self.btn_apply_edit.setEnabled(False)
            return

        target_row = p_idx.row()
        if target_row < 0 or target_row >= self.table_sizes.rowCount():
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Warning"),
                translate("frameforge", "Target section row index is out of bounds."),
            )
            session.close(discard_uncommitted=True)
            self._active_edit_session = None
            self.btn_apply_edit.setEnabled(False)
            return

        lib_name = self.current_lib_meta.get("name", "") if self.current_lib_meta else session.library_name
        _, density = self.manager.get_library_material_info(lib_name)

        try:
            result = session.apply(density_g_cm3=density)
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self,
                translate("frameforge", "Error"),
                translate("frameforge", "Failed to apply section edit: %s") % str(err),
            )
            return

        size_item = self.table_sizes.item(target_row, 0)
        props = size_item.data(QtCore.Qt.UserRole) if size_item else {}
        if not isinstance(props, dict):
            props = {}

        # Old asset staged for deferred removal on Save
        old_asset = props.get("asset_path")
        if old_asset and old_asset != result["asset_path"]:
            self._staged_deleted_assets.add(old_asset)

        props["asset_path"] = result["asset_path"]
        props["object_name"] = result["object_name"]
        props["asset_id"] = result["asset_id"]
        props["Height"] = result["Height"]
        props["Width"] = result["Width"]
        props["Weight"] = result["Weight"]

        self._staged_new_assets.add(result["asset_path"])

        # Update table items
        self.table_sizes.blockSignals(True)
        if size_item:
            size_item.setData(QtCore.Qt.UserRole, copy.deepcopy(props))
        # Height (col 1), Width (col 2), Weight (col 7)
        self.table_sizes.setItem(target_row, 1, QtWidgets.QTableWidgetItem(result["Height"]))
        self.table_sizes.setItem(target_row, 2, QtWidgets.QTableWidgetItem(result["Width"]))
        self.table_sizes.setItem(target_row, 7, QtWidgets.QTableWidgetItem(result["Weight"]))
        for col_idx in (1, 2, 7):
            it = self.table_sizes.item(target_row, col_idx)
            if it:
                it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEditable)
        self.table_sizes.blockSignals(False)

        if hasattr(self, "cards_view") and self.cards_view is not None:
            self.cards_view.refresh_card(target_row)

        self._mark_dirty()
        self._set_status(translate("frameforge", "Section edits applied. Save library to publish changes."))
        return True

    def _cleanup_uncommitted_staged_new_assets(self):
        """Cleans up owned newly created/staged assets that were never committed to disk."""
        if not self.current_lib_meta or not self.current_lib_meta.get("folder_path"):
            self._staged_new_assets.clear()
            return
        folder_path = self.current_lib_meta["folder_path"]
        from freecad.maxproframe.section_library import resolve_and_validate_asset_path

        for rel_path in list(self._staged_new_assets):
            try:
                full_path = resolve_and_validate_asset_path(folder_path, rel_path)
                if os.path.isfile(full_path):
                    os.remove(full_path)
            except Exception:
                pass
        self._staged_new_assets.clear()

    def _detach_sketch_edit_watcher(self):
        if getattr(self, "_sketch_edit_poll_timer", None) is not None:
            try:
                self._sketch_edit_poll_timer.stop()
                self._sketch_edit_poll_timer.deleteLater()
            except Exception:
                pass
            self._sketch_edit_poll_timer = None

        if getattr(self, "_sketch_edit_observer", None) is not None:
            try:
                self._sketch_edit_observer.detach()
                if Gui is not None and hasattr(Gui, "removeDocumentObserver"):
                    Gui.removeDocumentObserver(self._sketch_edit_observer)
            except Exception:
                pass
            self._sketch_edit_observer = None

    def _on_sketch_edit_finished(self):
        self._detach_sketch_edit_watcher()
        self._is_hidden_for_sketch_edit = False

        if getattr(self, "_is_closed", False):
            return

        if self._active_edit_session is not None:
            doc_name = self._active_edit_session.working_doc_name
            if App is not None and doc_name not in App.listDocuments():
                try:
                    self._active_edit_session.close(discard_uncommitted=True)
                except Exception:
                    pass
                self._active_edit_session = None
                if hasattr(self, "btn_apply_edit"):
                    self.btn_apply_edit.setEnabled(False)

        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except (RuntimeError, AttributeError):
            pass

        if self._active_edit_session is not None:
            self._set_status(
                translate("frameforge", "Section opened in FreeCAD. Edit sketch, then click 'Apply Section Edit'."),
                is_warning=True,
            )
        else:
            self._restore_previous_workbench()
            if self.is_dirty:
                self._set_status(translate("frameforge", "Unsaved changes."), is_warning=True)
            else:
                self._set_status("")

    def _restore_previous_workbench(self):
        prev = getattr(self, "_previous_workbench", None)
        self._previous_workbench = None
        if Gui is not None and hasattr(Gui, "activateWorkbench"):
            target = prev or "MaxProFrame"
            try:
                Gui.activateWorkbench(target)
            except Exception:
                try:
                    Gui.activateWorkbench("MaxProFrame")
                except Exception:
                    pass

    def _cleanup_edit_session_and_staged_assets(self):
        self._cancel_dxf_review()
        if self._profile_editor is not None:
            self._profile_editor.reject()
        self._detach_sketch_edit_watcher()
        self._is_hidden_for_sketch_edit = False
        self._restore_previous_workbench()
        if getattr(self, "_active_edit_session", None) is not None:
            try:
                self._active_edit_session.close(discard_uncommitted=True)
            except Exception:
                pass
            self._active_edit_session = None
        if hasattr(self, "cards_view") and self.cards_view is not None:
            if hasattr(self.cards_view, "_thumbnail_cache"):
                self.cards_view._thumbnail_cache.clear()
        self._cleanup_uncommitted_staged_new_assets()

    def _restore_window_geometry(self):
        try:
            param = get_param_group(writable=False)
            geo_hex = param.GetString("LibraryManagerGeometry", "")
            if geo_hex:
                geo_bytes = QtCore.QByteArray.fromHex(geo_hex.encode("ascii"))
                if not geo_bytes.isEmpty():
                    self.restoreGeometry(geo_bytes)
            splitter_hex = param.GetString("LibraryManagerSplitterState", "")
            if splitter_hex and hasattr(self, "main_splitter"):
                splitter_bytes = QtCore.QByteArray.fromHex(splitter_hex.encode("ascii"))
                if not splitter_bytes.isEmpty():
                    self.main_splitter.restoreState(splitter_bytes)
        except Exception:
            pass

    def _save_window_geometry(self):
        try:
            geo = self.saveGeometry()
            param = get_param_group(writable=True)
            if geo and not geo.isEmpty():
                param.SetString("LibraryManagerGeometry", bytes(geo.toHex()).decode("ascii"))
            if hasattr(self, "main_splitter"):
                sp = self.main_splitter.saveState()
                if sp and not sp.isEmpty():
                    param.SetString("LibraryManagerSplitterState", bytes(sp.toHex()).decode("ascii"))
        except Exception:
            pass

    def done(self, result):
        if self._is_closed or getattr(self, "_close_in_progress", False):
            return
        self._close_in_progress = True
        try:
            if not self._prompt_dirty_save(closing=True):
                return
            self._save_window_geometry()
            self._is_closed = True
            self._cleanup_edit_session_and_staged_assets()
            super().done(result)
        finally:
            self._close_in_progress = False

    def closeEvent(self, event):
        # QDialog's default closeEvent calls reject()/done() again. Route the
        # window close through the same guard without re-entering Qt's path.
        self.done(QtWidgets.QDialog.Rejected)
        if self._is_closed:
            event.accept()
        else:
            event.ignore()


class _SectionEditGuiObserver:
    """Watches FreeCAD GUI edit state to restore the library manager dialog when sketch editing ends."""

    def __init__(self, dialog, doc_name):
        self.dialog = dialog
        self.doc_name = doc_name
        self._active = True

    def detach(self):
        self._active = False

    def slotResetEdit(self, view_provider):
        if not self._active:
            return
        try:
            obj = getattr(view_provider, "Object", None)
            if obj is not None:
                doc = getattr(obj, "Document", None)
                if doc is not None and doc.Name != self.doc_name:
                    return
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, self._restore)

    def slotDeletedDocument(self, gui_doc):
        if not self._active:
            return
        try:
            doc_name = getattr(gui_doc, "Name", None)
            if doc_name and doc_name != self.doc_name:
                return
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, self._restore)

    def _restore(self):
        if not self._active:
            return
        self.detach()
        if Gui is not None and hasattr(Gui, "removeDocumentObserver"):
            try:
                Gui.removeDocumentObserver(self)
            except Exception:
                pass
        if self.dialog is not None:
            try:
                self.dialog._on_sketch_edit_finished()
            except Exception:
                pass


def _is_live_manager(dialog):
    """Safely checks if a dialog wrapper and underlying C++ QObject are alive and active."""
    if dialog is None:
        return False
    try:
        if getattr(dialog, "_is_closed", False):
            return False
        _ = dialog.windowTitle()
        return bool(
            dialog.isVisible()
            or getattr(dialog, "_active_edit_session", None) is not None
            or getattr(dialog, "_dxf_review", None) is not None
        )
    except (RuntimeError, AttributeError, ReferenceError):
        return False


class ManageProfileLibrariesCommand:
    """GuiCommand to open the Profile Library Manager Dialog."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "manage_profile_libraries.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ManageProfileLibraries", "Manage Profile Libraries"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ManageProfileLibraries",
                "Create, edit and manage custom profile libraries and dimensions",
            ),
        }

    def Activated(self):
        mw = Gui.getMainWindow() if (Gui is not None and hasattr(Gui, "getMainWindow")) else None

        existing = getattr(mw, "_frameforge_library_manager", None) if mw is not None else None
        if _is_live_manager(existing):
            try:
                existing.show()
                existing.raise_()
                existing.activateWindow()
                return
            except (RuntimeError, AttributeError):
                pass

        if mw is not None:
            mw._frameforge_library_manager = None

        dialog = ProfileLibraryManagerDialog(parent=mw)
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        def _retire(*_):
            if mw is not None and getattr(mw, "_frameforge_library_manager", None) is dialog:
                mw._frameforge_library_manager = None

        dialog.finished.connect(_retire)
        dialog.destroyed.connect(_retire)

        if mw is not None:
            mw._frameforge_library_manager = dialog

        dialog.show()
        try:
            dialog.raise_()
            dialog.activateWindow()
        except (RuntimeError, AttributeError):
            pass

    def IsActive(self):
        return True


if hasattr(Gui, "addCommand"):
    add_command("MaxProFrame_ManageProfileLibraries", ManageProfileLibrariesCommand())

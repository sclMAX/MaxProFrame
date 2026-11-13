"""Folded miter commands: Folded Bar (create and edit, previewed live) and Unfold Bar.

See odd/tasks/folded-miter.md, T6. The panel folds the selected tube pieces with a bend configuration of the store
(S6), with its inside radius (S9, S14), the open corner of a closed frame (S17), the clearance and the key (S8, S20;
the relief is always cut, its radius the inside radius of each corner). Whatever keeps the chain from folding is shown
and keeps OK disabled: the chain messages, an own miter at a folded corner (S12) and the unfold messages (S9, S15).
The bar keeps its sizes in its Folded Corner objects (odd/tasks/folded-corners.md, T3): the panel turns its fields into
the settings of each corner (outer radius = inside radius + the wall of the tube, K-factor of the configuration) and
reads them back from the corners of an edited bar, until T4 lists the corners themselves.

Like Create Miter Ends (S22, T9), the command opens the panel at once, with the selected pieces if any, and the panel
takes the pieces clicked while it is open: a click adds one at the end of the list, Ctrl+click or deselecting drops it.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import is_foldedbar
from freecad.maxproframe.bend_config import (
    BendConfigurationStore,
    get_last_used_configuration,
    set_last_used_configuration,
)
from freecad.maxproframe.create_end_miter_tool import (
    GAP_DELAY_MS,
    _alive,
    _alive_document,
    _built_on,
    _ctrl_held,
    _failures,
)
from freecad.maxproframe.expression_fields import length_field
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, get_param_group, translate
from freecad.maxproframe.folded_bar import bar_chain, folded_corners, make_folded_bar, make_unfolded_bar, update_corners
from freecad.maxproframe.folded_chain import (
    ChainError,
    base_profile,
    build_chain,
    cut_at_fold_message,
    cuts_at_folds,
)
from freecad.maxproframe.profile_pattern import container_placement, newest_piece, placed
from freecad.maxproframe.qt_lifetime import invalidate_wrapper_on_destroy, keep_alive_until_destroyed
from freecad.maxproframe.unfolded_geometry import CornerSettings, UnfoldError, check_settings

# Remembered state of the panel's "Update automatically" check box.
AUTO_PREVIEW_PARAM = "Folded Bar Auto Preview"
# Largest radius, clearance or key size the fields take (mm).
MAX_SIZE = 1000.0
# Corner object properties the panel sets; of the bar it sets Segments and Corners.
PROPERTIES = ("PieceA", "PieceB", "OuterRadius", "Clearance", "Key", "KeyDiameter", "KFactor", "Open")


def _plain(value):
    """A property value as the panel compares it."""
    if hasattr(value, "Name") and hasattr(value, "Document"):
        return value.Name
    if hasattr(value, "Value"):
        return round(value.Value, 9)
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, (list, tuple)):
        return tuple(item.Name if hasattr(item, "Name") else _plain(item) for item in value)
    return value


def _corner_key(chain, corner):
    """A corner by the two profiles meeting there, whatever the order of the chain."""
    return frozenset(chain.segments[index].profile.Name for index in (corner.before, corner.after))


def _snapshot(bar):
    """What the panel may change on ``bar``: its Segments and Corners, and the PROPERTIES of each corner object."""
    corners = [obj for obj in bar.Corners if obj is not None]
    return {
        "Segments": list(bar.Segments),
        "Corners": corners,
        "values": {obj.Name: {prop: getattr(obj, prop) for prop in PROPERTIES} for obj in corners},
    }


def _plain_snapshot(snapshot):
    return (
        _plain(snapshot["Segments"]),
        _plain(snapshot["Corners"]),
        tuple(
            (name, tuple((prop, _plain(value)) for prop, value in values.items()))
            for name, values in sorted(snapshot["values"].items())
        ),
    )


def show_panel(panel):
    Gui.Control.showDialog(panel)


class FoldedBarTaskPanel:
    """The bend configuration, the radii, the open corner and the notch of a Folded Bar, previewed.

    Without ``edited`` the preview is the Folded Bar OK keeps, made from the pieces ``selection`` (the first one
    starts the bar) inside one transaction that Cancel aborts. With ``edited`` the bar itself is the preview: OK keeps
    the changes in one Undo step, or none when nothing changed; Cancel puts it back. ``store`` holds the bend
    configurations (the user's by default).

    As a selection observer (added by the command, as End Miter's) the new bar takes the pieces clicked while the
    panel is open; an edited bar keeps its pieces, as an edited End Miter does.
    """

    auto_preview_param = AUTO_PREVIEW_PARAM
    auto_preview_default = True

    def __init__(self, selection=(), edited=None, store=None):
        self.edited = edited
        self.obj = edited
        self.store = store or BendConfigurationStore()
        # (piece, Visibility) of what the preview hides: Cancel shows it again, undo or not.
        self._visibility = []
        self.selection = list(edited.Segments) if edited is not None else []
        if edited is None:
            for obj in selection:
                self.add_member(obj)
        self.doc = edited.Document if edited is not None else (
            self.selection[0].Document if self.selection else App.ActiveDocument
        )  # fmt: skip
        self._closed = False
        # Selection changes the panel makes itself are not the user's clicks.
        self._syncing = False
        self._transaction_open = False
        self._recomputing = False
        self._deferred = None
        self._previewed = None
        self._problems = []
        self._error = ""
        self._chain = None
        self._ok_button = None
        self._configurations = {}
        self._store_names = set()
        self._store_error = ""
        # Inside radius of the corners given their own, by the pair of profiles meeting there (S14).
        self._overrides = {}
        # K-factor of the corners of an edited bar, by pair: kept until another configuration is chosen.
        self._kept_k_factors = {}
        self._row_keys = []
        self._corner_rows = []
        if edited is not None:
            self._before = _snapshot(edited)
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(GAP_DELAY_MS)
        self._timer.timeout.connect(self.update_preview)
        self.form = keep_alive_until_destroyed(self._build_form())
        self.form.destroyed.connect(self._form_gone)
        self._fill()
        self._connect()
        self._refresh()
        if edited is not None:
            self._previewed = self._wanted()
        self.update_preview()

    # Form.

    def _build_form(self):
        form = QtGui.QWidget()
        form.setWindowTitle(translate("MaxProFrame", "Folded Bar"))
        layout = QtGui.QVBoxLayout(form)

        form.groupBox_members = QtGui.QGroupBox(translate("MaxProFrame", "Tube pieces, from the start of the bar"))
        members = QtGui.QVBoxLayout(form.groupBox_members)
        form.members_list = QtGui.QListWidget()
        form.members_list.setMaximumHeight(90)
        members.addWidget(form.members_list)
        layout.addWidget(form.groupBox_members)

        form.groupBox_bend = QtGui.QGroupBox(translate("MaxProFrame", "Bend"))
        bend = QtGui.QFormLayout(form.groupBox_bend)
        form.combo_configuration = QtGui.QComboBox()
        form.button_manage = QtGui.QPushButton(translate("MaxProFrame", "Manage configurations"))
        row = QtGui.QHBoxLayout()
        row.addWidget(form.combo_configuration, 1)
        row.addWidget(form.button_manage)
        bend.addRow(translate("MaxProFrame", "Configuration"), row)
        form.spin_radius = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_radius.setToolTip(translate("MaxProFrame", "Inside bend radius of every folded corner"))
        bend.addRow(translate("MaxProFrame", "Inside radius"), form.spin_radius)
        layout.addWidget(form.groupBox_bend)

        form.groupBox_corners = QtGui.QGroupBox(translate("MaxProFrame", "Corners"))
        form.corners_layout = QtGui.QFormLayout(form.groupBox_corners)
        form.label_open_corner = QtGui.QLabel(translate("MaxProFrame", "Open corner"))
        form.combo_open_corner = QtGui.QComboBox()
        form.combo_open_corner.setToolTip(
            translate("MaxProFrame", "Where the closed frame stays open: the bar starts there, at the first piece")
        )
        form.corners_layout.addRow(form.label_open_corner, form.combo_open_corner)
        form.label_corner_radii = QtGui.QLabel(translate("MaxProFrame", "Inside radius of each folded corner:"))
        form.corners_layout.addRow(form.label_corner_radii)
        layout.addWidget(form.groupBox_corners)

        form.groupBox_notch = QtGui.QGroupBox(translate("MaxProFrame", "Notch"))
        notch = QtGui.QFormLayout(form.groupBox_notch)
        form.spin_clearance = length_field(0.0, MAX_SIZE, 0.0)
        form.spin_clearance.setToolTip(
            translate("MaxProFrame", "Gap between the notch flanks and around the key, half on each side")
        )
        notch.addRow(translate("MaxProFrame", "Clearance"), form.spin_clearance)
        form.cb_key = QtGui.QCheckBox(translate("MaxProFrame", "Interlocking key"))
        notch.addRow(form.cb_key)
        form.spin_key_diameter = self._default_field(
            translate(
                "MaxProFrame",
                "Diameter of the key, a half circle on the miter line; Default: a quarter of the tube depth across "
                "the bent wall",
            )
        )
        notch.addRow(translate("MaxProFrame", "Key diameter"), form.spin_key_diameter)
        layout.addWidget(form.groupBox_notch)

        form.groupBox_preview = QtGui.QGroupBox(translate("MaxProFrame", "Preview"))
        preview = QtGui.QVBoxLayout(form.groupBox_preview)
        form.cb_auto_update = QtGui.QCheckBox(translate("MaxProFrame", "Update automatically"))
        form.cb_auto_update.setChecked(get_param_group().GetBool(self.auto_preview_param, self.auto_preview_default))
        form.status_label = QtGui.QLabel()
        preview.addWidget(form.cb_auto_update)
        preview.addWidget(form.status_label)
        layout.addWidget(form.groupBox_preview)

        form.message_label = QtGui.QLabel()
        form.message_label.setWordWrap(True)
        layout.addWidget(form.message_label)
        return form

    @staticmethod
    def _default_field(tooltip):
        """A size field whose 0 is the default size, shown as Default."""
        spin = length_field(0.0, MAX_SIZE, 0.0)
        spin.setSpecialValueText(translate("MaxProFrame", "Default"))
        spin.setToolTip(tooltip)
        return spin

    def _fill(self):
        """Show the pieces, the configurations and the values of the edited bar, or the defaults."""
        form = self.form
        for obj in self.selection:
            form.members_list.addItem(obj.Label)
        obj = self.edited
        if obj is None:
            self._load_configurations(get_last_used_configuration())
            configuration = self._configuration()
            form.spin_radius.setValue(configuration.inside_radius if configuration is not None else 0.0)
            form.cb_key.setChecked(True)
        else:
            # The bar keeps no configuration: the last one used is offered.
            self._load_configurations(get_last_used_configuration())
            self._fill_from_corners(obj)
        self._fill_open_corners()
        self._enable_sizes()

    def _fill_from_corners(self, bar):
        """The fields from the corner objects of ``bar``: its first folded corner gives the bar radius and the notch,
        the corners whose inside radius differs get their own row."""
        form = self.form
        try:
            chain = bar_chain(bar)
        except ChainError:
            return
        found = [(corner, obj) for corner, obj in zip(chain.corners, folded_corners(bar, chain)) if obj is not None]
        if not found:
            return

        def inside(corner, obj):
            return round(obj.OuterRadius.Value - chain.segments[corner.before].thickness, 9)

        first_corner, first = found[0]
        radius = inside(first_corner, first)
        form.spin_radius.setValue(radius)
        form.spin_clearance.setValue(first.Clearance.Value)
        form.cb_key.setChecked(first.Key)
        form.spin_key_diameter.setValue(first.KeyDiameter.Value)
        for corner, obj in found:
            key = _corner_key(chain, corner)
            self._kept_k_factors[key] = obj.KFactor
            if inside(corner, obj) != radius:
                self._overrides[key] = inside(corner, obj)

    def _load_configurations(self, selected):
        """List the stored configurations, ``selected`` chosen."""
        combo = self.form.combo_configuration
        self._configurations, self._store_error = {}, ""
        try:
            stored = self.store.configurations()
        except ValueError as error:
            stored, self._store_error = [], str(error)
        self._store_names = {configuration.name for configuration in stored}
        combo.blockSignals(True)
        combo.clear()
        for configuration in stored:
            self._configurations[configuration.name] = configuration
            combo.addItem(configuration.name, configuration.name)
        for index in range(combo.count()):
            configuration = self._configurations[combo.itemData(index)]
            combo.setItemData(
                index,
                translate("MaxProFrame", "{}: {:g} mm walls, inside radius {:g} mm, K-factor {:g}").format(
                    configuration.material, configuration.thickness, configuration.inside_radius,
                    configuration.k_factor,
                ),
                QtCore.Qt.ToolTipRole,
            )  # fmt: skip
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def configuration_names(self):
        """The names the configuration list offers, in its order."""
        combo = self.form.combo_configuration
        return [combo.itemData(index) for index in range(combo.count())]

    def _configuration(self):
        return self._configurations.get(self.form.combo_configuration.currentData())

    def _fill_open_corners(self):
        """The two corners of the first piece, of a closed frame: where it meets the last piece first (S17).

        The choice made is kept while the list offers it.
        """
        combo = self.form.combo_open_corner
        chosen = [obj.Name for obj in self._open_corner() or ()]
        combo.blockSignals(True)
        combo.clear()
        try:
            chain = build_chain(self.selection)
        except ChainError:
            chain = None
        if chain is not None and chain.closed:
            by_profile = {base_profile(obj).Name: obj for obj in self.selection}
            first = self.selection[0]
            for segment in (chain.segments[-1], chain.segments[1]):
                other = by_profile[segment.profile.Name]
                text = translate("MaxProFrame", "Between {} and {}").format(first.Label, other.Label)
                combo.addItem(text, [first, other])
                if [first.Name, other.Name] == chosen:
                    combo.setCurrentIndex(combo.count() - 1)
        combo.blockSignals(False)
        visible = combo.count() > 0
        self.form.label_open_corner.setVisible(visible)
        combo.setVisible(visible)

    def _open_corner(self):
        data = self.form.combo_open_corner.currentData() if self.form.combo_open_corner.count() else None
        return list(data) if data else None

    def _connect(self):
        form = self.form
        form.combo_configuration.currentIndexChanged.connect(self._configuration_changed)
        form.button_manage.clicked.connect(self.manage_configurations)
        form.combo_open_corner.currentIndexChanged.connect(self._changed)
        form.cb_key.toggled.connect(self._changed)
        for spin in (
            form.spin_radius,
            form.spin_clearance,
            form.spin_key_diameter,
        ):
            spin.valueChanged.connect(self._changed)
        form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)

    def _enable_sizes(self):
        form = self.form
        form.spin_key_diameter.setEnabled(form.cb_key.isChecked())

    # Corner radii.

    def corner_spins(self):
        """The radius field of each folded corner, in chain order (0: the bar's inside radius)."""
        return [spin for _, spin in self._corner_rows[: len(self._row_keys)]]

    def _show_corner_rows(self, chain):
        """One radius field per folded corner of ``chain``, showing its override; the rows follow the chain.

        Rows are added as the chain grows and hidden when it shrinks.
        """
        layout = self.form.corners_layout
        count = len(chain.corners) if chain is not None else 0
        while len(self._corner_rows) < count:
            index = len(self._corner_rows)
            label = QtGui.QLabel()
            spin = length_field(0.0, MAX_SIZE, 0.0)
            spin.setSpecialValueText(translate("MaxProFrame", "Bar radius"))
            for widget in (label, spin):
                invalidate_wrapper_on_destroy(widget)
            spin.valueChanged.connect(lambda value, index=index: self._corner_radius_changed(index, value))
            layout.addRow(label, spin)
            self._corner_rows.append((label, spin))
        self._row_keys = [_corner_key(chain, corner) for corner in chain.corners] if count else []
        for index, (label, spin) in enumerate(self._corner_rows):
            if index >= count:
                continue
            corner = chain.corners[index]
            names = (chain.segments[corner.before].profile.Label, chain.segments[corner.after].profile.Label)
            label.setText(translate("MaxProFrame", "{} to {}").format(*names))
            spin.blockSignals(True)
            spin.setValue(self._overrides.get(self._row_keys[index], 0.0))
            spin.blockSignals(False)
        shown = bool(count)
        self.form.label_corner_radii.setVisible(shown)
        for index, (label, spin) in enumerate(self._corner_rows):
            label.setVisible(index < count)
            spin.setVisible(index < count)
        self.form.groupBox_corners.setVisible(shown or self.form.combo_open_corner.count() > 0)

    def _corner_radius_changed(self, index, value):
        if not self._active() or index >= len(self._row_keys):
            return
        key = self._row_keys[index]
        if value > 0:
            self._overrides[key] = value
        else:
            self._overrides.pop(key, None)
        self._changed()

    # Checks.

    def _settings(self, chain):
        """The ``CornerSettings`` of each folded corner of ``chain`` from the panel values.

        The outer radius is the inside radius of the corner (its own, else the bar's) plus the wall of its tube; the
        K-factor is the configuration's, or the one an edited corner keeps while no other configuration is chosen.
        """
        form = self.form
        configuration = self._configuration()
        k_factor = float(configuration.k_factor) if configuration is not None else 0.0
        settings = []
        for corner in chain.corners:
            key = _corner_key(chain, corner)
            inside = self._overrides.get(key, form.spin_radius.value())
            settings.append(
                CornerSettings(
                    outer_radius=inside + chain.segments[corner.before].thickness,
                    clearance=form.spin_clearance.value(),
                    key=form.cb_key.isChecked(),
                    key_diameter=form.spin_key_diameter.value(),
                    k_factor=float(self._kept_k_factors.get(key, k_factor)),
                )
            )
        return settings

    def _check(self):
        """(messages of what keeps the bar from folding, chain or None)."""
        problems = []
        try:
            chain = build_chain(self.selection, open_corner=self._open_corner())
        except ChainError as error:
            return [str(error)], None
        configuration = self._configuration()
        if self._store_error:
            problems.append(self._store_error)
        if configuration is None:
            problems.append(translate("MaxProFrame", "Add a bend configuration: press Manage configurations."))
        problems += [cut_at_fold_message(chain, cut) for cut in cuts_at_folds(chain)]
        if configuration is not None:
            try:
                check_settings(chain, self._settings(chain))
            except UnfoldError as error:
                problems.append(str(error))
        return problems, chain

    def problems(self):
        """What keeps OK disabled now."""
        return list(self._problems) + ([self._error] if self._error and not self._pending() else [])

    def _refresh(self):
        """Check the panel values; show the messages, the corner rows, the status and OK."""
        self._problems, self._chain = self._check()
        self._show_corner_rows(self._chain)
        self._show_messages()

    def _show_messages(self):
        error = [self._error] if self._error and not self._pending() else []
        self.form.message_label.setText("\n".join(self._problems + error))
        if self._pending():
            status = translate("MaxProFrame", "Pending changes")
        elif self.obj is not None and _alive(self.obj):
            status = translate("MaxProFrame", "Preview updated")
        else:
            status = translate("MaxProFrame", "No preview")
        self.form.status_label.setText(status)
        self._enable_ok()

    def _pending(self):
        return self._previewed != self._wanted()

    def can_accept(self):
        return not self._closed and not self.problems()

    def ok_button_enabled(self):
        """Whether OK can be pressed: the dialog's button when it is shown."""
        if self._ok_button is not None:
            return self._ok_button.isEnabled()
        return self.can_accept()

    def _enable_ok(self):
        if self._ok_button is not None:
            self._ok_button.setEnabled(self.can_accept())

    # Changes.

    def _configuration_changed(self, *args):
        if not self._active():
            return
        configuration = self._configuration()
        # The chosen configuration gives its K-factor to every corner.
        self._kept_k_factors = {}
        if configuration is not None:
            self.form.spin_radius.blockSignals(True)
            self.form.spin_radius.setValue(configuration.inside_radius)
            self.form.spin_radius.blockSignals(False)
        self._changed()

    def _changed(self, *args):
        if not self._active():
            return
        self._enable_sizes()
        self._refresh()
        self._timer.start()

    def _on_auto_update_toggled(self, checked):
        get_param_group(writable=True).SetBool(self.auto_preview_param, checked)
        self.update_preview()

    def manage_configurations(self):
        """The Bend Configurations dialog; the list is read again when it closes, the choice kept when it can be."""
        from freecad.maxproframe.bend_config_dialog import BendConfigurationsDialog

        current = self.form.combo_configuration.currentData()
        dialog = BendConfigurationsDialog(store=self.store, parent=self.form, selected=current)
        dialog.exec_()
        dialog.deleteLater()
        if not self._active():
            return
        self._load_configurations(current)
        if self.form.combo_configuration.currentData() != current:
            self._configuration_changed()
        else:
            self._changed()

    # Preview.

    def _wanted(self):
        """What the bar must be: None while something keeps it from folding."""
        if self._problems or self._chain is None:
            return None
        chain = self._chain
        tips = tuple(segment.tip.Name for segment in chain.segments)
        corners = tuple(
            (tuple(sorted(_corner_key(chain, corner))), tuple(_plain(value) for value in vars(settings).values()))
            for corner, settings in zip(chain.corners, self._settings(chain))
        )
        opened = (chain.segments[0].profile.Name, chain.segments[-1].profile.Name) if chain.closed else None
        return (("Segments", tips), ("Corners", corners), ("Open", opened))

    def update_preview(self, *args, force=False):
        """Make the bar match the panel when Update automatically is checked (or ``force``)."""
        if not self._active():
            return
        if self._recomputing:
            return
        self._recomputing = True
        try:
            if force or self.form.cb_auto_update.isChecked():
                self._preview(force)
        finally:
            self._recomputing = False
        if self._active():
            self._show_messages()
        deferred, self._deferred = self._deferred, None
        if deferred is not None and self._active() and deferred():
            self._close_dialog()

    def _preview(self, force):
        wanted = self._wanted()
        if wanted is None:
            if self.edited is None and self._preview_of_other_pieces():
                self._drop_preview()
            return
        if not force and wanted == self._previewed and _alive(self.obj):
            return
        self._error = ""
        self._open_transaction()
        # A selected preview changed or remade is no click of the user.
        self._syncing = True
        try:
            if self.obj is None or not _alive(self.obj):
                self.obj = make_folded_bar(self.selection, self._settings(self._chain), open_corner=self._open_corner())
            else:
                if self.edited is None:
                    # The pieces clicked since: the bar follows the chain of the list.
                    self._apply(self.obj, {"Segments": [segment.tip for segment in self._chain.segments]})
                # The corner objects follow the chain and the fields; the open one is where the chain opens.
                update_corners(self.obj, self._chain, self._settings(self._chain))
                self.doc.recompute()
            self._error = _failures([self.obj])
        except Exception as error:
            self._error = str(error)
        finally:
            self._syncing = False
        self._previewed = wanted
        if self.edited is None:
            self._show_unlisted()

    def _preview_bar(self):
        """The previewed new bar, or None (none yet, or editing)."""
        if self.edited is None and self.obj is not None and _alive(self.obj):
            return self.obj
        return None

    def _profiles_in_bar(self):
        """Names of the profiles the preview folds now."""
        bar = self._preview_bar()
        if bar is None:
            return set()
        profiles = (base_profile(segment) for segment in bar.Segments if segment is not None)
        return {profile.Name for profile in profiles if profile is not None}

    def _preview_of_other_pieces(self):
        """Whether a preview shows pieces other than the listed ones."""
        if self._preview_bar() is None:
            return False
        return self._profiles_in_bar() != {base_profile(obj).Name for obj in self.selection}

    def _drop_preview(self):
        """Remove the preview of pieces that no longer fold: the pieces show again."""
        self._syncing = True
        try:
            self.doc.removeObject(self.obj.Name)
        finally:
            self._syncing = False
        self.obj = None
        self._error = ""
        self._previewed = None
        self._show_unlisted()

    def _show_unlisted(self):
        """Show the pieces the preview hid as they were, but the ones it still folds."""
        folded = self._profiles_in_bar()
        for piece, visible in self._visibility:
            if not _alive(piece) or piece.Visibility == visible:
                continue
            profile = base_profile(piece)
            if profile is None or profile.Name not in folded:
                piece.Visibility = visible

    # Pieces clicked while the panel is open (S22), as in End Miter.

    def add_member(self, obj):
        """List ``obj`` at the end; one entry per profile: a piece made from a listed one takes its place."""
        if obj is None or not _alive(obj) or base_profile(obj) is None or obj in self.selection:
            return False
        if any(obj in _built_on(member) for member in self.selection):
            return False
        replaced = [index for index, member in enumerate(self.selection) if member in _built_on(obj)]
        if replaced:
            # The start of the bar stays where it was.
            self.selection[replaced[0]] = obj
            self.selection = [member for index, member in enumerate(self.selection) if index not in replaced[1:]]
        else:
            self.selection.append(obj)
        profile = base_profile(obj)
        for piece in (obj, newest_piece(profile)):
            if all(piece.Name != seen.Name for seen, _ in self._visibility):
                self._visibility.append((piece, piece.Visibility))
        return True

    def _members_changed(self):
        """Show the new list: its chain, open corner, corner rows and messages; the preview follows later."""
        form = self.form
        form.members_list.clear()
        for obj in self.selection:
            form.members_list.addItem(obj.Label)
        self._fill_open_corners()
        self._refresh()

    def _clicked(self, doc, obj, sub, point):
        """The piece a selection change stands for: a click on the preview stands for the piece under it."""
        document = App.getDocument(doc) if doc in App.listDocuments() else None
        if document is None or self.doc is None or document.Name != self.doc.Name:
            return None
        source = document.getObject(getattr(obj, "Name", obj))
        bar = self._preview_bar()
        if source is not None and bar is not None and source.Name == bar.Name:
            return self._member_at(bar, sub, point)
        return source

    def _member_at(self, bar, sub, point):
        """The listed piece nearest to the clicked point of the preview (else to the clicked sub-element)."""
        target = None
        try:
            if point is not None and App.Vector(*point).Length > 0:
                target = App.Vector(*point)
            elif sub:
                element = bar.Shape.getElement(sub)
                center = element.Point if hasattr(element, "Point") else element.CenterOfMass
                target = container_placement(bar).multVec(center)
        except Exception:
            target = None
        if target is None or not self.selection:
            return None
        vertex = Part.Vertex(target)

        def distance(member):
            try:
                return vertex.distToShape(placed(member.Shape, container_placement(member)))[0]
            except Exception:
                return float("inf")

        return min(self.selection, key=distance)

    def _still_selected(self, member):
        """Whether ``member`` keeps an entry in the selection."""
        return any(selection.Object == member for selection in Gui.Selection.getSelectionEx("*"))

    def addSelection(self, doc, obj, sub, point=None):
        if self._syncing or not self._active() or self.edited is not None:
            return
        source = self._clicked(doc, obj, sub, point)
        if source is None or base_profile(source) is None:
            return
        if _ctrl_held() and source in self.selection:
            # Ctrl+click toggles: a listed piece leaves the list.
            self.selection.remove(source)
            self._members_changed()
        elif self.add_member(source):
            self._members_changed()
        # Never change the selection, the document or the 3D view during FreeCAD's observer dispatch.
        QtCore.QTimer.singleShot(0, self._after_selection)

    def removeSelection(self, doc, obj, sub):
        # A piece leaves the list once it has nothing selected; a face of the preview stands for the piece under it.
        if self._syncing or not self._active() or self.edited is not None:
            return
        bar = self._preview_bar()
        on_preview = bar is not None and getattr(obj, "Name", obj) == bar.Name
        source = self._clicked(doc, obj, sub, None)
        if source in self.selection and (on_preview or not self._still_selected(source)):
            self.selection.remove(source)
            self._members_changed()
            QtCore.QTimer.singleShot(0, self._after_selection)

    def clearSelection(self, other):
        pass

    def _after_selection(self):
        if not self._active():
            return
        self.update_preview()
        self._highlight_members()

    def _highlight_members(self):
        """Show every listed piece selected as a whole object; the ones the preview folds as the preview."""
        if not self._active() or self.edited is not None:
            return
        bar = self._preview_bar()
        folded = self._profiles_in_bar()
        shown = []
        for member in self.selection:
            obj = bar if base_profile(member).Name in folded else member
            if obj is not None and _alive(obj) and all(obj.Name != seen.Name for seen in shown):
                shown.append(obj)
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            for obj in shown:
                parents = obj.Parents
                if parents:
                    top, path = parents[0]
                    Gui.Selection.addSelection(obj.Document.Name, top.Name, path)
                else:
                    Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        finally:
            self._syncing = False

    @staticmethod
    def _apply(obj, values):
        for prop, value in values.items():
            if _plain(getattr(obj, prop)) != _plain(value):
                setattr(obj, prop, value)

    def _open_transaction(self):
        if not self._transaction_open:
            self.doc.openTransaction("Edit Folded Bar" if self.edited is not None else "Create Folded Bar")
            self._transaction_open = True

    # Dialog.

    def _active(self):
        return not self._closed

    def _form_gone(self, *args):
        if not self._closed:
            self.closed()

    def closed(self):
        """FreeCAD closed the dialog without OK or Cancel (document closed, another dialog shown)."""
        if not self._closed:
            self.clean()
            self._discard()

    def clean(self):
        self._closed = True
        self._timer.stop()
        # OK, Cancel or any other close: the panel stops taking the clicks (added by the command only).
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _discard(self):
        """Abort the transaction; with undo disabled, remove the new bar or put the edited one back by hand."""
        if not _alive_document(self.doc):
            return
        if self._transaction_open:
            try:
                self.doc.abortTransaction()
            except Exception:
                pass
        self._transaction_open = False
        changed = False
        if self.edited is None:
            if self.obj is not None and _alive(self.obj):
                self.doc.removeObject(self.obj.Name)
                changed = True
            for piece, visible in self._visibility:
                if _alive(piece) and piece.Visibility != visible:
                    piece.Visibility = visible
        elif _alive(self.edited):
            changed = self._restore_edited()
        if changed:
            self.doc.recompute()

    def _restore_edited(self):
        """Put the edited bar and its corner objects back as they were; remove the corner objects made since."""
        bar, before = self.edited, self._before
        changed = False
        made = [obj for obj in bar.Corners if _alive(obj) and obj.Name not in before["values"]]
        for prop in ("Segments", "Corners"):
            kept = [obj for obj in before[prop] if _alive(obj)]
            if _plain(list(getattr(bar, prop))) != _plain(kept):
                setattr(bar, prop, kept)
                changed = True
        for obj in made:
            self.doc.removeObject(obj.Name)
            changed = True
        for name, values in before["values"].items():
            obj = self.doc.getObject(name)
            if obj is None:
                continue
            for prop, value in values.items():
                if _plain(getattr(obj, prop)) != _plain(value):
                    setattr(obj, prop, value)
                    changed = True
        return changed

    def _unchanged(self):
        return _plain_snapshot(_snapshot(self.edited)) == _plain_snapshot(self._before)

    def _close_edit(self):
        if self.edited is None or not _alive_document(self.doc):
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def _close_dialog(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def _defer(self, button):
        """A recompute pumps Qt events: OK or Cancel pressed during it waits for it to end."""
        if not self._recomputing:
            return False
        self._deferred = button
        return True

    def open(self):
        self._highlight_members()

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def modifyStandardButtons(self, box):
        """Keep the OK button: it is disabled while something keeps the bar from folding."""
        # The task view deletes the row when the dialog closes: no wrapper may outlive it.
        invalidate_wrapper_on_destroy(box)
        button = box.button(QtGui.QDialogButtonBox.Ok)
        if button is None:
            return
        invalidate_wrapper_on_destroy(button)
        button.destroyed.connect(self._ok_button_gone)
        self._ok_button = button
        self._enable_ok()

    def _ok_button_gone(self, *args):
        self._ok_button = None

    def reject(self):
        if self._defer(self.reject):
            return False
        self.clean()
        self._discard()
        self._close_edit()
        if self.edited is None:
            # The pieces were selected to show the panel's list: closed, nothing stays selected.
            Gui.Selection.clearSelection()
        return True

    def accept(self):
        if self._defer(self.accept):
            return False
        if self._closed:
            return False
        # OK keeps the current values even when the preview is out of date.
        self._timer.stop()
        self._refresh()
        if self._problems:
            return False
        self.update_preview(force=True)
        if self._error:
            # The panel stays open with the error, to change the values.
            return False
        configuration = self._configuration()
        if configuration.name in self._store_names:
            set_last_used_configuration(configuration.name)
        if self.edited is not None and self._unchanged():
            # Nothing changed in the end: no Undo step.
            self._discard()
        else:
            self.doc.commitTransaction()
        self._transaction_open = False
        self.clean()
        self._close_edit()
        Gui.Selection.clearSelection()
        return True


class FoldedBarCommand:
    """Folded Bar: fold the selected tube pieces into one bar with folded corners."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "FoldedBar.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_FoldedBar", "Folded Bar"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_FoldedBar",
                "<b>Folded Bar</b><br><br>Click two or more tube profiles (or pieces made from them) that meet end to "
                "end, the first one where the bar starts: their corners fold, with a V notch, a key and a relief cut "
                "by the laser and the outer wall bent. A closed frame stays open at one corner. Double-click the bar "
                "to edit it.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        panel = FoldedBarTaskPanel([item.Object for item in Gui.Selection.getSelectionEx()])
        show_panel(panel)
        Gui.Selection.addObserver(panel)


class UnfoldBarCommand:
    """Unfold Bar: the straight bar of the selected Folded Bar, to export for a tube laser."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "UnfoldedBar.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_UnfoldBar", "Unfold Bar"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_UnfoldBar",
                "<b>Unfold Bar</b><br><br>Select a Folded Bar: its straight bar with every cut is made from X = 0 "
                "along X, to export with File > Export (STEP, IGES, BREP) for a tube laser.",
            ),
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        selection = Gui.Selection.getSelection()
        return len(selection) == 1 and is_foldedbar(selection[0])

    def Activated(self):
        bar = Gui.Selection.getSelection()[0]
        doc = bar.Document
        doc.openTransaction("Unfold Bar")
        make_unfolded_bar(bar)
        doc.commitTransaction()


add_command("MaxProFrame_FoldedBar", FoldedBarCommand())
add_command("MaxProFrame_UnfoldBar", UnfoldBarCommand())

"""Bend Configurations: the dialog that lists, adds, edits and deletes the bend configurations of folded miters.

Every change goes through ``bend_config.BendConfigurationStore`` (S6, S11): an invalid configuration shows the
store's message and nothing is saved. See odd/tasks/folded-miter.md, T6.
"""

import os

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from freecad.maxproframe.bend_config import BendConfiguration, BendConfigurationStore, validated
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command, translate

MAX_THICKNESS = 100.0
MAX_RADIUS = 1000.0


def _length_spin(maximum):
    spin = QtWidgets.QDoubleSpinBox()
    spin.setRange(0.0, maximum)
    spin.setDecimals(2)
    spin.setSuffix(" mm")
    return spin


class BendConfigurationsDialog(QtWidgets.QDialog):
    """The stored configurations on the left; the one shown on the right, saved with Save.

    New starts a configuration from the values shown, without a name. Save adds it, or replaces the configuration
    shown (renaming it when its name changed). ``store`` is the user's store by default; ``selected`` is the name of
    the configuration shown first.
    """

    def __init__(self, store=None, parent=None, selected=None):
        super().__init__(parent)
        self.store = store or BendConfigurationStore()
        # Name of the stored configuration shown, None for a new one.
        self._editing = None
        self.setWindowTitle(translate("MaxProFrame", "Bend Configurations"))
        layout = QtWidgets.QVBoxLayout(self)
        columns = QtWidgets.QHBoxLayout()
        layout.addLayout(columns)

        left = QtWidgets.QVBoxLayout()
        self.list_configurations = QtWidgets.QListWidget()
        left.addWidget(self.list_configurations)
        buttons = QtWidgets.QHBoxLayout()
        self.button_new = QtWidgets.QPushButton(translate("MaxProFrame", "New"))
        self.button_delete = QtWidgets.QPushButton(translate("MaxProFrame", "Delete"))
        buttons.addWidget(self.button_new)
        buttons.addWidget(self.button_delete)
        left.addLayout(buttons)
        columns.addLayout(left)

        fields = QtWidgets.QFormLayout()
        self.edit_name = QtWidgets.QLineEdit()
        self.edit_material = QtWidgets.QLineEdit()
        self.spin_thickness = _length_spin(MAX_THICKNESS)
        self.spin_radius = _length_spin(MAX_RADIUS)
        self.spin_k_factor = QtWidgets.QDoubleSpinBox()
        self.spin_k_factor.setRange(0.0, 1.0)
        self.spin_k_factor.setDecimals(3)
        self.spin_k_factor.setSingleStep(0.01)
        self.spin_k_factor.setToolTip(
            translate("MaxProFrame", "Where the neutral axis sits in the wall: 0 inside face, 1 outside face")
        )
        fields.addRow(translate("MaxProFrame", "Name"), self.edit_name)
        fields.addRow(translate("MaxProFrame", "Material"), self.edit_material)
        fields.addRow(translate("MaxProFrame", "Wall thickness"), self.spin_thickness)
        fields.addRow(translate("MaxProFrame", "Inside bend radius"), self.spin_radius)
        fields.addRow(translate("MaxProFrame", "K-factor"), self.spin_k_factor)
        self.button_save = QtWidgets.QPushButton(translate("MaxProFrame", "Save"))
        fields.addRow(self.button_save)
        columns.addLayout(fields)

        self.message_label = QtWidgets.QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.list_configurations.currentItemChanged.connect(self._current_changed)
        self.button_new.clicked.connect(self.new)
        self.button_delete.clicked.connect(self.delete)
        self.button_save.clicked.connect(self.save)
        self._reload(selected)

    def _reload(self, selected=None):
        """List the stored configurations and show ``selected`` (else the first; a new one when there is none)."""
        try:
            stored = self.store.configurations()
            message = ""
        except ValueError as error:
            stored, message = [], str(error)
        self._stored = {configuration.name: configuration for configuration in stored}
        self.list_configurations.blockSignals(True)
        self.list_configurations.clear()
        for configuration in stored:
            self.list_configurations.addItem(configuration.name)
        self.list_configurations.blockSignals(False)
        if stored:
            self.select(selected if selected in self._stored else stored[0].name)
        else:
            self.new()
        self._show_message(message)

    def names(self):
        return [self.list_configurations.item(row).text() for row in range(self.list_configurations.count())]

    def select(self, name):
        """Show the stored configuration ``name``."""
        items = self.list_configurations.findItems(name, QtCore.Qt.MatchExactly)
        if items:
            self.list_configurations.setCurrentItem(items[0])
            self._show(self._stored[name])

    def _current_changed(self, current, previous=None):
        if current is not None and current.text() in self._stored:
            self._show(self._stored[current.text()])

    def _show(self, configuration):
        self._editing = configuration.name
        self.edit_name.setText(configuration.name)
        self.edit_material.setText(configuration.material)
        self.spin_thickness.setValue(configuration.thickness)
        self.spin_radius.setValue(configuration.inside_radius)
        self.spin_k_factor.setValue(configuration.k_factor)
        self.button_delete.setEnabled(True)
        self._show_message("")

    def new(self):
        """A new configuration from the values shown: only the name is left to type."""
        self._editing = None
        self.list_configurations.blockSignals(True)
        self.list_configurations.setCurrentRow(-1)
        self.list_configurations.clearSelection()
        self.list_configurations.blockSignals(False)
        self.edit_name.clear()
        self.button_delete.setEnabled(False)
        self._show_message("")
        self.edit_name.setFocus()

    def _shown(self):
        return BendConfiguration(
            self.edit_name.text(),
            self.edit_material.text(),
            self.spin_thickness.value(),
            self.spin_radius.value(),
            self.spin_k_factor.value(),
        )

    def save(self):
        """Store the configuration shown; whether it was saved (else the message says why)."""
        try:
            configuration = validated(self._shown())
            if configuration.name != self._editing and configuration.name in self.store_names():
                raise ValueError(
                    translate("MaxProFrame", "There is already a configuration called {}.").format(configuration.name)
                )
            saved = self.store.save(configuration)
            if self._editing is not None and self._editing != saved.name:
                # Renamed: the configuration keeps one name.
                self.store.delete(self._editing)
        except (ValueError, KeyError) as error:
            self._show_message(str(error.args[0]) if error.args else str(error))
            return False
        self._reload(saved.name)
        return True

    def store_names(self):
        return {configuration.name for configuration in self.store.configurations()}

    def confirm_delete(self, name):
        answer = QtWidgets.QMessageBox.question(
            self,
            translate("MaxProFrame", "Bend Configurations"),
            translate("MaxProFrame", "Delete the bend configuration {}? The bars made with it keep their copy.").format(
                name
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return answer == QtWidgets.QMessageBox.Yes

    def delete(self):
        """Delete the configuration shown once confirmed; whether it was deleted."""
        name = self._editing
        if name is None or not self.confirm_delete(name):
            return False
        try:
            self.store.delete(name)
        except (ValueError, KeyError) as error:
            self._show_message(str(error.args[0]) if error.args else str(error))
            return False
        self._reload()
        return True

    def _show_message(self, text):
        self.message_label.setText(text)


class BendConfigurationsCommand:
    """Bend Configurations: manage the saved bend configurations of folded miters."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "BendConfigurations.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_BendConfigurations", "Bend Configurations"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_BendConfigurations",
                "<b>Bend Configurations</b><br><br>Add, edit and delete the saved bend configurations of folded "
                "bars: material, wall thickness, inside bend radius and K-factor.",
            ),
        }

    def IsActive(self):
        return True

    def Activated(self):
        dialog = BendConfigurationsDialog(parent=Gui.getMainWindow())
        dialog.exec_()
        dialog.deleteLater()


add_command("MaxProFrame_BendConfigurations", BendConfigurationsCommand())

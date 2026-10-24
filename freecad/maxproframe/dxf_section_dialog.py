"""Small unit confirmation and modeless native-section review controls."""

import FreeCAD as App

try:
    from PySide import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from freecad.maxproframe.ff_tools import translate


class DXFUnitsDialog(QtWidgets.QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("frameforge", "Confirm DXF Units"))
        layout = QtWidgets.QVBoxLayout(self)
        self.lbl_declared = QtWidgets.QLabel(
            translate("frameforge", "Declared INSUNITS: %s; millimeters per drawing unit: %s")
            % (metadata.get("insunits"), metadata.get("unit_mm"))
        )
        layout.addWidget(self.lbl_declared)
        instruction = QtWidgets.QLabel(
            translate("frameforge", "Confirm the drawing units. Override incorrect metadata before importing.")
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.combo_units = QtWidgets.QComboBox()
        self.combo_units.addItem(translate("frameforge", "Select confirmed units"), None)
        for unit in ("mm", "cm", "m", "inch", "ft"):
            self.combo_units.addItem(unit, unit)
        known = {1.0: "mm", 10.0: "cm", 1000.0: "m", 25.4: "inch", 304.8: "ft"}
        unit = known.get(metadata.get("unit_mm"))
        if unit:
            self.combo_units.setCurrentIndex(self.combo_units.findData(unit))
        layout.addWidget(self.combo_units)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.combo_units.currentIndexChanged.connect(self._update_confirmation)
        layout.addWidget(self.buttons)
        self._update_confirmation()

    def _update_confirmation(self):
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(self.confirmed_unit() is not None)

    def confirmed_unit(self):
        return self.combo_units.currentData()


class DXFSectionReview(QtWidgets.QDialog):
    """Controls only; the actual fixed sketch is visible in FreeCAD's viewport.

    The manager owns the document and publication callback, never this window.
    """

    def __init__(self, sketch, library_name, material, density, add_callback):
        super().__init__(None, QtCore.Qt.Tool)
        self.sketch = sketch
        self.document_name = sketch.Document.Name
        self.add_callback = add_callback
        self.setWindowTitle(translate("frameforge", "Review DXF Section"))
        self.setModal(False)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        destination = QtWidgets.QGroupBox(translate("frameforge", "Destination"))
        destination_layout = QtWidgets.QVBoxLayout(destination)
        self.lbl_destination = QtWidgets.QLabel(
            translate("frameforge", "Library: %s\nMaterial: %s (%s g/cm³)")
            % (library_name, translate("frameforge", material), density)
        )
        self.lbl_destination.setTextFormat(QtCore.Qt.PlainText)
        self.lbl_destination.setWordWrap(True)
        destination_layout.addWidget(self.lbl_destination)
        layout.addWidget(destination)
        label = QtWidgets.QLabel(
            translate(
                "frameforge", "Review the fixed XY sketch in FreeCAD. Adding stages it; Save Changes publishes it."
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        profile = QtWidgets.QGroupBox(translate("frameforge", "Profile data"))
        form = QtWidgets.QFormLayout(profile)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.le_code = QtWidgets.QLineEdit()
        form.addRow(translate("frameforge", "Code:"), self.le_code)
        self.le_description = QtWidgets.QLineEdit()
        form.addRow(translate("frameforge", "Description (optional):"), self.le_description)
        layout.addWidget(profile)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.btn_add = QtWidgets.QPushButton(translate("frameforge", "Add as Custom"))
        self.btn_add.clicked.connect(lambda: self.add_callback(self.le_code.text().strip()))
        self.btn_add.setDefault(True)
        cancel = QtWidgets.QPushButton(translate("frameforge", "Cancel"))
        cancel.clicked.connect(self.reject)
        cancel.setAutoDefault(False)
        buttons.addWidget(cancel)
        buttons.addWidget(self.btn_add)
        layout.addLayout(buttons)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.check_document)
        self.timer.start()
        self.finished.connect(self.timer.stop)
        self.setMinimumWidth(460)
        self.le_code.setFocus()

    def check_document(self):
        if self.document_name not in App.listDocuments():
            self.reject()

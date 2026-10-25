"""One isolated properties/Sketcher session, published only by library Save Changes."""

import copy
import math

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

from freecad.maxproframe.ff_tools import translate


class CustomProfileEditor(QtWidgets.QDialog):
    EditGeometry = 2

    def __init__(self, manager, row):
        super().__init__(manager)
        self.manager = manager
        self.index = QtCore.QPersistentModelIndex(manager.table_sizes.model().index(row, 0))
        self.library = copy.deepcopy(manager.current_lib_meta)
        self.family = manager.current_family
        self._geometry = False
        self._finishing = False
        self.setObjectName("custom_properties_dialog")
        self.setWindowTitle(translate("frameforge", "Edit Profile"))
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        item = manager.table_sizes.item(row, 0)
        props = item.data(QtCore.Qt.UserRole) or {}
        self.code = QtWidgets.QLineEdit(item.text())
        self.description = QtWidgets.QLineEdit(str(props.get("Description", "")))
        self.weight = QtWidgets.QLineEdit(manager.table_sizes.item(row, 7).text())
        for field, name in ((self.code, "code"), (self.description, "description"), (self.weight, "weight")):
            field.setObjectName("property_" + name)
        form.addRow(translate("frameforge", "Code:"), self.code)
        form.addRow(translate("frameforge", "Description:"), self.description)
        form.addRow(translate("frameforge", "Weight (kg/m):"), self.weight)
        layout.addLayout(form)
        self.btn_geometry = QtWidgets.QPushButton(translate("frameforge", "Edit Section"))
        self.btn_geometry.setObjectName("edit_profile_section")
        self.btn_geometry.setEnabled(bool(self.library.get("is_folder") and props.get("asset_path")))
        self.btn_geometry.clicked.connect(lambda: self.done(self.EditGeometry))
        layout.addWidget(self.btn_geometry)
        self.hint = QtWidgets.QLabel(
            translate("frameforge", "Confirming geometry recalculates weight from the library material.")
        )
        self.hint.setWordWrap(True)
        self.hint.hide()
        layout.addWidget(self.hint)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(translate("frameforge", "Accept"))
        self.buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate("frameforge", "Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.check_geometry)

    def run(self):
        self.manager._profile_editor = self
        while self.exec_() == self.EditGeometry:
            if self.start_geometry():
                return
        if self.manager._profile_editor is self:
            self.manager._profile_editor = None
        self.deleteLater()

    def _valid_target(self):
        return (
            self.index.isValid()
            and self.manager.current_lib_meta == self.library
            and self.manager.current_family == self.family
            and not self.manager._is_closed
        )

    def _validate(self):
        if not self._valid_target() or not self.library.get("is_user"):
            raise ValueError(translate("frameforge", "Target section row was removed or is invalid."))
        code = self.code.text().strip()
        if not code:
            raise ValueError(translate("frameforge", "Enter a non-empty size code."))
        table = self.manager.table_sizes
        if any(
            row != self.index.row() and table.item(row, 0) and table.item(row, 0).text().strip() == code
            for row in range(table.rowCount())
        ):
            raise ValueError(
                translate("frameforge", "Duplicate size codes found: %s. Each size must have a unique code.") % code
            )
        if not self._geometry:
            value = self.weight.text().strip()
            try:
                number = float(value)
                if not math.isfinite(number) or number <= 0:
                    raise ValueError(value)
            except ValueError:
                raise ValueError(
                    translate(
                        "frameforge",
                        "Invalid weight '%s' for custom profile '%s'. Weight must be a positive finite number.",
                    )
                    % (value, code)
                )

    def start_geometry(self):
        if not self._valid_target():
            return False
        table = self.manager.table_sizes
        table.setCurrentCell(self.index.row(), 0)
        table.selectRow(self.index.row())
        if not self.manager._on_edit_section(force_gui=True):
            return False
        # This window owns termination. Remove legacy restore callbacks before leaving the manager.
        self.manager._detach_sketch_edit_watcher()
        self.manager._is_hidden_for_sketch_edit = False
        self._geometry = True
        self.setParent(Gui.getMainWindow(), QtCore.Qt.Tool)
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setModal(False)
        self.btn_geometry.hide()
        self.hint.show()
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(translate("frameforge", "OK"))
        self.manager.hide()
        self.show()
        self.raise_()
        self.timer.start()
        return True

    def accept(self):
        if self._finishing:
            return
        try:
            self._validate()
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, translate("frameforge", "Edit Profile"), str(error))
            return
        if self._geometry:
            session = self.manager._active_edit_session
            if session is None or session.working_doc_name not in App.listDocuments():
                self.reject()
                return
            # Stop closure detection before resetting edit: native Close is not our OK.
            self._finishing = True
            self.timer.stop()
            gui_doc = Gui.getDocument(session.working_doc_name)
            if gui_doc.getInEdit() is not None:
                gui_doc.resetEdit()
            if not self.manager.apply_section_edit():
                self._finishing = False
                gui_doc.setEdit(session.working_sketch_name)
                self.timer.start()
                return
        table = self.manager.table_sizes
        row = self.index.row()
        item = table.item(row, 0)
        code = self.code.text().strip()
        description = self.description.text()
        props = copy.deepcopy(item.data(QtCore.Qt.UserRole) or {})
        if props.get("Description", "") != description:
            props["Description"] = description
            item.setData(QtCore.Qt.UserRole, props)
            self.manager._mark_dirty()
        if item.text() != code:
            item.setText(code)
            self.manager._mark_dirty()
        if not self._geometry:
            weight = table.item(row, 7)
            if weight.text() != self.weight.text().strip():
                weight.setText(self.weight.text().strip())
                self.manager._mark_dirty()
        self._finish()
        super().accept()

    def reject(self):
        if self._finishing:
            return
        self._finish()
        super().reject()

    def _finish(self):
        self._finishing = True
        self.timer.stop()
        if self._geometry:
            self.manager._detach_sketch_edit_watcher()
            session = self.manager._active_edit_session
            self.manager._active_edit_session = None
            if session:
                session.close(discard_uncommitted=True)
            self.manager._is_hidden_for_sketch_edit = False
            self.manager.btn_apply_edit.setEnabled(False)
            if not self.manager._is_closed:
                self.manager.show()
                self.manager.raise_()
                self.manager.activateWindow()
        if self.manager._profile_editor is self:
            self.manager._profile_editor = None
        if self._geometry:
            self.deleteLater()

    def check_geometry(self):
        if self._finishing or not self._geometry:
            return
        session = self.manager._active_edit_session
        if not self._valid_target() or session is None or session.working_doc_name not in App.listDocuments():
            self.reject()
            return
        gui_doc = Gui.getDocument(session.working_doc_name)
        if gui_doc.getInEdit() is not None:
            return
        self.timer.stop()
        answer = QtWidgets.QMessageBox.question(
            self,
            translate("frameforge", "Discard profile edit?"),
            translate("frameforge", "Discard the current profile edit? Earlier library changes will be kept."),
            QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        if answer == QtWidgets.QMessageBox.Discard:
            self.reject()
        else:
            if not gui_doc.setEdit(session.working_sketch_name):
                self.reject()
                return
            self.timer.start()

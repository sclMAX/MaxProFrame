"""Native stable/RC checks for the pencil's single isolated edit session."""

import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import test_custom_profile_cards as fixtures
from PySide import QtCore, QtWidgets


class TestUnifiedCustomProfileEditor(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TestCustomProfileCards("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.dialog = self.fixture.dialog
        self.app = self.fixture.app
        asset = self.fixture._create_published_asset("unified", width=80, height=40)
        self.dialog.current_lib_data["Custom Profile"]["sizes"] = {
            "A": {
                "Weight": "12.34",
                "Description": "Original",
                "asset_path": asset,
                "object_name": "Section",
                "asset_id": "unified",
                "vendor": "preserve",
            },
            "B": {
                "Weight": "2.5",
                "Description": "Sibling",
                "asset_path": asset,
                "object_name": "Section",
                "asset_id": "unified",
            },
        }
        self.fixture._select_family("Custom Profile")
        self.dialog.btn_save.click()
        self.original_files = self.files()
        self.card = self.dialog.cards_view.card_by_code("A")
        self.error = None
        self.addCleanup(self.cleanup_editor)

    def files(self):
        return {
            str(p.relative_to(self.fixture.folder_lib_path)): p.read_bytes()
            for p in Path(self.fixture.folder_lib_path).rglob("*")
            if p.is_file()
        }

    def cleanup_editor(self):
        editor = getattr(self.dialog, "_profile_editor", None)
        if editor:
            editor.reject()
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
            self.dialog.close()

    def open_properties(self, action):
        def interact():
            modal = self.app.activeModalWidget()
            try:
                action(modal)
            except BaseException as exc:
                self.error = exc
                modal.reject()

        QtCore.QTimer.singleShot(0, interact)
        self.card.btn_edit_properties.click()
        if self.error:
            raise self.error

    def fields(self, editor):
        return [
            editor.findChild(QtWidgets.QLineEdit, name)
            for name in ("property_code", "property_description", "property_weight")
        ]

    def begin_geometry(self):
        def transition(modal):
            for field, value in zip(self.fields(modal), ("A-new", "Pending description", "77.5")):
                field.setText(value)
            button = modal.findChild(QtWidgets.QPushButton, "edit_profile_section")
            self.assertIsNotNone(button)
            self.assertTrue(button.isEnabled())
            button.click()

        self.open_properties(transition)
        editor = self.dialog._profile_editor
        self.assertIsNotNone(editor)
        self.assertTrue(editor.isVisible())
        self.assertFalse(editor.isModal())
        self.assertIsNone(self.app.activeModalWidget())
        self.assertTrue(self.dialog.isHidden())
        self.assertEqual([f.text() for f in self.fields(editor)], ["A-new", "Pending description", "77.5"])
        session = self.dialog._active_edit_session
        self.assertIsNotNone(session)
        working = App.getDocument(session.working_doc_name)
        self.assertIsNotNone(Gui.getDocument(working.Name).getInEdit())
        if os.environ.get("FF_REPORTS"):
            editor.grab().save(os.path.join(os.environ["FF_REPORTS"], "edit-profile.png"))
        return editor, working, working.getObject(session.working_sketch_name)

    def change_geometry(self, sketch):
        index = next(i for i, c in enumerate(sketch.Constraints) if c.Type == "Distance" and abs(c.Value - 40) < 0.001)
        sketch.setDatum(index, App.Units.Quantity("55 mm"))
        sketch.Document.recompute()

    def test_properties_only_accept_and_cancel_do_not_open_sketcher(self):
        def accept(modal):
            self.assertIsNotNone(modal.findChild(QtWidgets.QPushButton, "edit_profile_section"))
            self.fields(modal)[1].setText("Properties only")
            box = modal.findChild(QtWidgets.QDialogButtonBox)
            self.assertIsNone(box.button(QtWidgets.QDialogButtonBox.Save))
            box.button(QtWidgets.QDialogButtonBox.Ok).click()

        self.open_properties(accept)
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertIsNone(self.dialog._profile_editor)
        self.assertEqual(self.card.description_edit.text(), "Properties only")
        self.assertTrue(self.dialog.is_dirty)
        self.assertEqual(self.files(), self.original_files)
        before = copy.deepcopy(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole))
        self.open_properties(lambda modal: (self.fields(modal)[1].setText("Canceled"), modal.reject()))
        self.assertEqual(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole), before)

    def test_geometry_ok_stages_whole_session_and_closes_working_copy(self):
        editor, working, sketch = self.begin_geometry()
        name = working.Name
        self.change_geometry(sketch)
        editor.accept()
        staged = self.files()
        editor.accept()  # A queued second activation must not apply the same session twice.
        self.assertEqual(self.files(), staged)
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertIsNone(self.dialog._profile_editor)
        self.assertNotIn(name, App.listDocuments())
        self.assertTrue(self.dialog.isVisible())
        card = self.dialog.cards_view.card_by_code("A-new")
        self.assertEqual(card.description_edit.text(), "Pending description")
        self.assertAlmostEqual(float(card.weight_edit.text()), 34.54, places=2)
        self.assertTrue(self.dialog.is_dirty)
        self.assertTrue(self.dialog.btn_save.isEnabled())
        published = self.fixture.manager.get_library("CustomFolderLib")["Custom Profile"]["sizes"]
        self.assertIn("A", published)
        self.assertNotIn("A-new", published)
        for path, data in self.original_files.items():
            self.assertEqual(Path(self.fixture.folder_lib_path, path).read_bytes(), data)
        self.dialog.btn_save.click()
        saved = self.fixture.manager.get_library("CustomFolderLib")["Custom Profile"]["sizes"]
        self.assertEqual(saved["A-new"]["vendor"], "preserve")
        self.assertEqual(saved["A-new"]["Description"], "Pending description")
        self.assertEqual(saved["B"]["Weight"], "2.5")

    def test_cancel_and_window_close_preserve_earlier_pending_changes(self):
        for close in (False, True):
            with self.subTest(close=close):
                self.dialog.table_sizes.item(1, 7).setText("3.5")
                self.assertTrue(self.dialog.is_dirty)
                before = copy.deepcopy(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole))
                editor, working, sketch = self.begin_geometry()
                name = working.Name
                self.change_geometry(sketch)
                editor.close() if close else editor.reject()
                self.assertNotIn(name, App.listDocuments())
                self.assertIsNone(self.dialog._profile_editor)
                self.assertIsNone(self.dialog._active_edit_session)
                self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "A")
                self.assertEqual(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole), before)
                self.assertEqual(self.dialog.table_sizes.item(1, 7).text(), "3.5")
                self.assertTrue(self.dialog.is_dirty)
                self.assertEqual(self.files(), self.original_files)

    def test_invalid_fields_and_geometry_keep_session_open_without_staging(self):
        editor, working, sketch = self.begin_geometry()
        original = copy.deepcopy(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole))
        self.fields(editor)[0].setText("B")
        editor.accept()
        self.assertTrue(editor.isVisible())
        self.assertEqual(self.files(), self.original_files)
        self.fields(editor)[0].setText("A-new")
        # Removing an edge makes the wire open and unsuitable for a section.
        sketch.delGeometry(0)
        working.recompute()
        editor.accept()
        self.assertTrue(editor.isVisible())
        self.assertIsNotNone(self.dialog._active_edit_session)
        self.assertIsNotNone(Gui.getDocument(working.Name).getInEdit())
        self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "A")
        self.assertEqual(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole), original)
        self.assertEqual(self.files(), self.original_files)
        self.assertFalse(self.dialog.is_dirty)

    def test_native_sketch_close_discards_without_implicit_acceptance(self):
        editor, working, sketch = self.begin_geometry()
        name = working.Name
        self.change_geometry(sketch)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
            Gui.getDocument(name).resetEdit()
            editor.check_geometry()
        self.assertNotIn(name, App.listDocuments())
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertIsNone(self.dialog._profile_editor)
        self.assertEqual(self.files(), self.original_files)
        self.assertEqual(self.card.code_edit.text(), "A")
        self.assertFalse(self.dialog.is_dirty)

    def test_native_close_can_resume_editing_and_missing_asset_keeps_fields(self):
        editor, working, sketch = self.begin_geometry()
        self.change_geometry(sketch)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Cancel):
            Gui.getDocument(working.Name).resetEdit()
            editor.check_geometry()
        self.assertIsNotNone(Gui.getDocument(working.Name).getInEdit())
        self.assertTrue(editor.isVisible())
        editor.reject()
        item = self.dialog.table_sizes.item(0, 0)
        props = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        props.pop("asset_path")
        item.setData(QtCore.Qt.UserRole, props)

        def properties_only(modal):
            self.assertFalse(modal.findChild(QtWidgets.QPushButton, "edit_profile_section").isEnabled())
            self.fields(modal)[1].setText("Still editable")
            modal.accept()

        self.open_properties(properties_only)
        self.assertEqual(self.card.description_edit.text(), "Still editable")
        self.assertIsNone(self.dialog._active_edit_session)

    def test_separate_geometry_actions_are_not_visible(self):
        self.dialog.show()
        self.app.processEvents()
        self.assertTrue(self.dialog.btn_edit_section.isHidden())
        self.assertTrue(self.dialog.btn_apply_edit.isHidden())
        for button in (self.dialog.btn_edit_section, self.dialog.btn_apply_edit):
            self.assertIs(button.parentWidget(), self.dialog)
            self.assertFalse(button.isWindow())

    def wait_native_timer(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(350, loop.quit)
        loop.exec_()

    def assert_session_detached(self, editor):
        self.assertFalse(editor.timer.isActive())
        self.assertIsNone(self.dialog._sketch_edit_observer)
        self.assertIsNone(self.dialog._sketch_edit_poll_timer)
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertIsNone(self.dialog._profile_editor)

    def test_independent_native_close_timer(self):
        editor, working, sketch = self.begin_geometry()
        self.change_geometry(sketch)
        name = working.Name
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard) as question:
            Gui.getDocument(name).resetEdit()
            self.wait_native_timer()
            self.assertEqual(question.call_count, 1)
        self.assertNotIn(name, App.listDocuments())
        self.assertIsNone(self.dialog._profile_editor)
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertIsNone(self.dialog._sketch_edit_observer)
        self.assertIsNone(self.dialog._sketch_edit_poll_timer)
        self.assertEqual(self.files(), self.original_files)
        self.assertFalse(self.dialog.is_dirty)

    def test_independent_external_document_close(self):
        editor, working, sketch = self.begin_geometry()
        self.change_geometry(sketch)
        App.closeDocument(working.Name)
        self.wait_native_timer()
        self.assertIsNone(self.dialog._profile_editor)
        self.assertIsNone(self.dialog._active_edit_session)
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.files(), self.original_files)
        self.assertFalse(self.dialog.is_dirty)

    def test_independent_prior_stage_and_stale_callbacks(self):
        editor, working, sketch = self.begin_geometry()
        self.change_geometry(sketch)
        editor.accept()
        editor.accept()
        editor.check_geometry()
        self.assert_session_detached(editor)
        before = self.files()
        props = copy.deepcopy(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole))
        staged = set(self.dialog._staged_new_assets)
        self.card = self.dialog.cards_view.card_by_code("A-new")
        editor, working, sketch = self.begin_geometry()
        self.fields(editor)[0].setText("Discard this name")
        sketch.toggleConstruction(0)
        working.recompute()
        editor.reject()
        editor.check_geometry()
        editor.accept()
        self.assert_session_detached(editor)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.dialog._staged_new_assets, staged)
        self.assertEqual(self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole), props)
        self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "A-new")
        self.assertTrue(self.dialog.btn_save.isEnabled())

    def test_independent_geometry_repair(self):
        editor, working, sketch = self.begin_geometry()
        sketch.toggleConstruction(0)
        working.recompute()
        editor.accept()
        self.assertFalse(editor._finishing)
        self.assertTrue(editor.timer.isActive())
        self.assertIsNotNone(Gui.getDocument(working.Name).getInEdit())
        self.assertEqual(self.files(), self.original_files)
        sketch.toggleConstruction(0)
        working.recompute()
        editor.accept()
        self.assert_session_detached(editor)
        self.assertTrue(self.dialog.btn_save.isEnabled())

    def test_independent_missing_file_transition(self):
        item = self.dialog.table_sizes.item(0, 0)
        props = copy.deepcopy(item.data(QtCore.Qt.UserRole))
        props["asset_path"] = "sections/does-not-exist.FCStd"
        item.setData(QtCore.Qt.UserRole, props)

        def accept_returned():
            modal = self.app.activeModalWidget()
            try:
                self.assertIsNotNone(modal)
                self.assertEqual(self.fields(modal)[1].text(), "Survives failed transition")
                modal.accept()
            except BaseException as error:
                self.error = error
                if modal:
                    modal.reject()

        def try_missing(modal):
            self.fields(modal)[1].setText("Survives failed transition")
            modal.findChild(QtWidgets.QPushButton, "edit_profile_section").click()
            QtCore.QTimer.singleShot(0, accept_returned)

        self.open_properties(try_missing)
        self.assertEqual(self.card.description_edit.text(), "Survives failed transition")
        self.assertEqual(self.files(), self.original_files)
        self.assertIsNone(self.dialog._active_edit_session)
        self.card.set_editable(False)
        self.card.btn_edit_properties.click()
        self.assertIsNone(self.dialog._profile_editor)

    def test_independent_manager_finalization(self):
        editor, working, sketch = self.begin_geometry()
        name = working.Name
        self.change_geometry(sketch)
        self.dialog.close()
        self.assertTrue(self.dialog._is_closed)
        self.assert_session_detached(editor)
        self.assertNotIn(name, App.listDocuments())
        self.assertEqual(self.files(), self.original_files)
        self.wait_native_timer()
        self.assertFalse(self.dialog.isVisible())

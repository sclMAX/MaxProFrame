"""Tests for Profile Library Manager window lifecycle, modeless modality,
single-owner persistence, and S10/S9 cleanup.
"""

import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError:
        QtCore = QtGui = QtWidgets = None

try:
    from PySide6 import QtTest
except ImportError:
    try:
        from PySide2 import QtTest
    except ImportError:
        try:
            from PySide import QtTest
        except ImportError:
            QtTest = None


def _qWait(ms):
    if QtTest is not None and hasattr(QtTest, "QTest") and hasattr(QtTest.QTest, "qWait"):
        QtTest.QTest.qWait(ms)
    elif QtCore is not None:
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        loop.exec_()


try:
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import Sketcher
except ImportError:
    App = Gui = Part = Sketcher = None

from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    ManageProfileLibrariesCommand,
    ProfileLibraryManagerDialog,
)


def _find_live_manager():
    """Finds the active visible ProfileLibraryManagerDialog from top-level widgets."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        try:
            if isinstance(w, ProfileLibraryManagerDialog) and w.isVisible():
                return w
        except (RuntimeError, AttributeError):
            pass
    return None


def _is_live(w):
    """Safely checks if a widget wrapper and C++ object are alive and visible."""
    if w is None:
        return False
    try:
        return bool(w.isVisible())
    except (RuntimeError, AttributeError, ReferenceError):
        # Intentional C++ deletion via WA_DeleteOnClose
        return False


@unittest.skipIf(App is None or QtWidgets is None, "FreeCAD and PySide required for lifecycle tests")
class TestLibraryManagerWindowLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_lifecycle_")
        self.addCleanup(self.workspace.cleanup)
        self.test_root = self.workspace.name
        self.user_dir = os.path.join(self.test_root, "user")
        self.stock_dir = os.path.join(self.test_root, "stock")
        self.reg_path = os.path.join(self.test_root, "registry", "folders.json")
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.stock_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.reg_path), exist_ok=True)

        self.manager = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )

        self.folder_lib_path = os.path.join(self.test_root, "ProbeLib")
        self.manager.create_folder_library(
            self.folder_lib_path,
            "ProbeLib",
            material="Steel",
            density=7.85,
            data={
                "Square Hollow": {
                    "canonical_family": "Square Hollow",
                    "norm": "EN 10219",
                    "fillet": False,
                    "sizes": {
                        "40x40x2": {
                            "Height": "40",
                            "Width": "40",
                            "Thickness": "2",
                        }
                    },
                }
            },
        )

        self.mw = Gui.getMainWindow() if (Gui is not None and hasattr(Gui, "getMainWindow")) else None
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # Patch LibraryManager constructor in library_manager_dialog to return isolated manager
        self.mgr_patcher = patch(
            "freecad.maxproframe.library_manager_dialog.LibraryManager",
            return_value=self.manager,
        )
        self.mgr_patcher.start()
        self.addCleanup(self.mgr_patcher.stop)

        # Patch message boxes during lifecycle
        self.msg_stack = ExitStack()
        for method in ("warning", "critical", "information"):
            self.msg_stack.enter_context(patch.object(QtWidgets.QMessageBox, method))
        # Closing dirty dialogs is a user decision, not an arbitrary Mock value.
        self.question = self.msg_stack.enter_context(
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard)
        )
        self.addCleanup(self.msg_stack.close)

        self.created_docs = []
        self.addCleanup(self._cleanup_all)

    def _cleanup_all(self):
        # Include hidden edit/review owners, but never touch another test's manager.
        # Run before message patches and temporary library files are retired (LIFO).
        self.question.return_value = QtWidgets.QMessageBox.Discard
        for dlg in self.app.topLevelWidgets():
            try:
                owned = isinstance(dlg, ProfileLibraryManagerDialog) and dlg.manager is self.manager
            except RuntimeError:
                continue  # Qt may already have deleted a closed dialog.
            if owned:
                dlg.close()  # Public close owns review/session/staged-asset cleanup.
                self.assertFalse(_is_live(dlg), "Test-owned manager refused discard cleanup.")
        self.app.processEvents()
        Gui.Selection.clearSelection()
        ProfileLibraryManagerDialog.uninstall_translations()
        for name in reversed(self.created_docs):
            try:
                if App is not None and name in App.listDocuments():
                    App.closeDocument(name)
            except Exception:
                pass

    def test_command_opens_modeless_from_start_with_persistent_ownership(self):
        """Rule 1: ManageProfileLibrariesCommand opens modeless (show, never exec_),
        retaining persistent ownership on main window.
        """
        exec_called = []

        def fail_exec(*args, **kwargs):
            exec_called.append(True)
            raise AssertionError("exec_() must never be called; command must be modeless from start via show().")

        cmd = ManageProfileLibrariesCommand()
        with patch.object(ProfileLibraryManagerDialog, "exec_", side_effect=fail_exec):
            cmd.Activated()

        self.assertEqual(len(exec_called), 0, "Command called exec_() instead of show().")
        dialog = _find_live_manager()
        self.assertIsNotNone(dialog, "Dialog must be discoverable in public Qt widget tree.")
        self.assertTrue(dialog.isVisible(), "Dialog must be visible after Activated().")
        self.assertFalse(dialog.isModal(), "Dialog must be modeless (isModal() False).")
        self.assertIsNone(self.app.activeModalWidget(), "No active modal widget must be registered in QApplication.")
        if self.mw is not None:
            self.assertEqual(dialog.parentWidget(), self.mw, "Dialog must be parented to FreeCAD main window.")
            self.assertTrue(self.mw.isEnabled(), "Main window must remain enabled while modeless dialog is open.")
            self.assertIs(getattr(self.mw, "_frameforge_library_manager", None), dialog)

        dialog.close()

    def test_reinvoking_command_while_open_raises_and_preserves_dirty_state(self):
        """Rule 2: Re-invoking command while open raises/reuses single live manager
        without duplicating dialog or losing dirty/uncommitted state.
        """
        cmd1 = ManageProfileLibrariesCommand()
        cmd1.Activated()
        dialog1 = _find_live_manager()
        self.assertIsNotNone(dialog1)
        self.assertTrue(dialog1.isVisible())

        # Select library and introduce dirty state
        dialog1.refresh_libraries(select_name="ProbeLib")
        dialog1.le_norm.setText("DIRTY_UNSAVED_NORM")
        self.assertTrue(dialog1.is_dirty, "Dialog must reflect dirty state.")

        # Re-invoke command using a new command instance
        cmd2 = ManageProfileLibrariesCommand()
        with patch.object(dialog1, "raise_") as mock_raise, patch.object(dialog1, "activateWindow") as mock_activate:
            cmd2.Activated()

        dialog2 = _find_live_manager()
        live_managers = [
            w for w in self.app.topLevelWidgets()
            if isinstance(w, ProfileLibraryManagerDialog) and _is_live(w)
        ]
        self.assertEqual(live_managers, [dialog1], "Reinvoke must leave exactly one visible manager.")
        self.assertIs(dialog2, dialog1, "Re-invoking command must reuse existing live dialog instance.")
        self.assertEqual(mock_raise.call_count, 1, "Re-invoking must raise existing window.")
        self.assertEqual(mock_activate.call_count, 1, "Re-invoking must activate existing window.")
        self.assertTrue(dialog1.is_dirty, "Dirty flag must be preserved on re-activation.")
        self.assertEqual(dialog1.le_norm.text(), "DIRTY_UNSAVED_NORM", "Unsaved edits must be preserved.")

        dialog1.close()

    def test_user_sequence_capture_edit_close_leaves_no_modal_or_leaked_staging(self):
        """Rule 3: Exact user sequence: capture section -> edit section -> close dialog
        leaves QApplication.activeModalWidget None, working doc destroyed, uncommitted
        staging purged, and library on disk unchanged (S10/S9).
        """
        # Create source document with a valid rectangle sketch
        doc = App.newDocument("TestLifecycleSource")
        self.created_docs.append(doc.Name)
        s = doc.addObject("Sketcher::SketchObject", "SourceRect")
        pts = [(0, 0), (50, 0), (50, 25), (0, 25)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        for i in [0, 2]:
            s.addConstraint(Sketcher.Constraint("Horizontal", i))
        for i in [1, 3]:
            s.addConstraint(Sketcher.Constraint("Vertical", i))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        s.addConstraint(Sketcher.Constraint("Distance", 0, 50.0))
        s.addConstraint(Sketcher.Constraint("Distance", 1, 25.0))
        doc.recompute()
        self.assertEqual(s.solve(), 0)

        # Snapshot disk state before
        disk_before = {
            os.path.relpath(os.path.join(r, f), self.test_root): open(os.path.join(r, f), "rb").read()
            for r, _, fs in os.walk(self.folder_lib_path)
            for f in fs
        }

        # Select sketch in Gui.Selection
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, s.Name)

        # Activate command
        cmd = ManageProfileLibrariesCommand()
        cmd.Activated()
        dialog = _find_live_manager()
        self.assertIsNotNone(dialog)
        dialog.refresh_libraries(select_name="ProbeLib")

        # 1. Capture section
        self.assertTrue(dialog.btn_capture_section.isEnabled())
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        self.assertEqual(dialog.current_family, "Custom Profile")
        self.assertEqual(dialog.table_sizes.rowCount(), 1)
        self.assertEqual(dialog.table_sizes.currentRow(), 0)
        staged_assets = list(getattr(dialog, "_staged_new_assets", set()))
        self.assertEqual(len(staged_assets), 1, "Capture must stage one new asset.")
        rel_staged = staged_assets[0]
        # Resolved relative to folder library root, NOT cwd
        full_staged = os.path.join(self.folder_lib_path, rel_staged)
        self.assertTrue(os.path.isfile(full_staged), "Staged file must exist on disk before save/close.")

        # 2. Edit section
        self.assertTrue(dialog.btn_edit_section.isEnabled())
        dialog.btn_edit_section.click()
        session = dialog._active_edit_session
        self.assertIsNotNone(session, "Edit session must be active.")
        working_doc_name = session.working_doc_name
        self.assertIn(working_doc_name, App.listDocuments(), "Working copy document must exist in FreeCAD.")
        self.assertFalse(dialog.isModal(), "Dialog must remain modeless during edit session.")
        self.assertIsNone(self.app.activeModalWidget(), "activeModalWidget must be None during edit session.")

        # Cancel must retain ownership, working state, staged bytes and counters.
        ManageProfileLibrariesCommand().Activated()
        source_geometry = s.GeometryCount
        staged_bytes = Path(full_staged).read_bytes()
        rows_before = dialog.table_sizes.rowCount()
        self.question.reset_mock()
        self.question.return_value = QtWidgets.QMessageBox.Cancel
        dialog.btn_close.click()
        self.question.assert_called_once()
        self.assertTrue(_is_live(dialog))
        self.assertIs(getattr(self.mw, "_frameforge_library_manager", None), dialog)
        self.assertTrue(dialog.is_dirty)
        self.assertIs(dialog._active_edit_session, session)
        self.assertIn(working_doc_name, App.listDocuments())
        self.assertEqual(dialog.table_sizes.rowCount(), rows_before)
        self.assertEqual(set(dialog._staged_new_assets), set(staged_assets))
        self.assertEqual(Path(full_staged).read_bytes(), staged_bytes)

        # 3. Explicitly discard without Apply/Save through the same close button.
        self.question.reset_mock()
        self.question.return_value = QtWidgets.QMessageBox.Discard
        dialog.btn_close.click()
        self.question.assert_called_once()

        # Invariants after close
        self.assertFalse(_is_live(dialog), "Dialog must not be live/visible after close.")
        self.assertNotIn(working_doc_name, App.listDocuments(), "Working document must be destroyed on close.")
        self.assertFalse(os.path.exists(full_staged), "Uncommitted staged asset must be purged on close (S9).")
        self.assertIsNone(self.app.activeModalWidget(), "activeModalWidget must be None after close (S10).")
        if self.mw is not None:
            self.assertTrue(self.mw.isEnabled(), "Main window must remain enabled after close.")

        self.assertIn(doc.Name, App.listDocuments(), "Source document must survive discard.")
        self.assertIs(doc.getObject(s.Name), s)
        self.assertEqual(s.GeometryCount, source_geometry)
        # Verify disk library catalog is unchanged
        disk_after = {
            os.path.relpath(os.path.join(r, f), self.test_root): open(os.path.join(r, f), "rb").read()
            for r, _, fs in os.walk(self.folder_lib_path)
            for f in fs
        }
        self.assertEqual(disk_before, disk_after, "Closing without Save must preserve saved catalog and disk assets.")

    def _start_custom_edit(self):
        doc = App.newDocument("CustomEditSource")
        self.created_docs.append(doc.Name)
        sketch = doc.addObject("Sketcher::SketchObject", "CustomSection")
        sketch.Label = "My custom profile"
        points = [(0, 0), (30, 0), (30, 20), (0, 20)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)
        ManageProfileLibrariesCommand().Activated()
        dialog = _find_live_manager()
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="ProbeLib")
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        code = dialog.table_sizes.item(0, 0).text()
        dialog.btn_edit_section.click()
        session = dialog._active_edit_session
        self.assertIsNotNone(session)
        self.created_docs.append(session.working_doc_name)
        working = App.getDocument(session.working_doc_name)
        return dialog, working, code

    def test_edit_uses_profile_name_for_document_and_sketch(self):
        dialog, working, code = self._start_custom_edit()
        self.assertEqual(working.Label, code)
        self.assertEqual(working.getObject(dialog._active_edit_session.working_sketch_name).Label, code)

    def test_edit_enters_sketcher_and_hides_without_closing(self):
        dialog, working, code = self._start_custom_edit()
        self.assertFalse(dialog.isVisible())
        self.assertIn(working.Name, App.listDocuments())
        self.assertEqual(Gui.activeWorkbench().name(), "SketcherWorkbench")
        self.assertEqual(
            Gui.getDocument(working.Name).getInEdit().Object.Name, dialog._active_edit_session.working_sketch_name
        )

    def test_finishing_sketch_restores_same_library_without_applying(self):
        dialog, working, code = self._start_custom_edit()
        self.assertFalse(dialog.isVisible(), "Dialog must be hidden during custom section edit session.")
        session = dialog._active_edit_session
        props_before = dict(dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole))
        staged_before = set(dialog._staged_new_assets)
        assets_before = {
            os.path.relpath(os.path.join(root, name), self.folder_lib_path): Path(os.path.join(root, name)).read_bytes()
            for root, _, files in os.walk(self.folder_lib_path)
            for name in files
        }
        Gui.getDocument(working.Name).resetEdit()
        _qWait(400)
        self.assertTrue(dialog.isVisible())
        self.assertIs(dialog._active_edit_session, session)
        self.assertIn(working.Name, App.listDocuments())
        self.assertEqual(dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole), props_before)
        self.assertEqual(dialog._staged_new_assets, staged_before)
        self.assertIsNone(session.staged_asset_path)
        self.assertEqual(
            assets_before,
            {
                os.path.relpath(os.path.join(root, name), self.folder_lib_path): Path(
                    os.path.join(root, name)
                ).read_bytes()
                for root, _, files in os.walk(self.folder_lib_path)
                for name in files
            },
        )
        ManageProfileLibrariesCommand().Activated()
        self.assertIs(_find_live_manager(), dialog)

    def test_reinvoking_command_while_dialog_hidden_in_edit_reuses_same_instance(self):
        """Re-invoking command while dialog is hidden in active sketch editing must reuse
        the same instance and restore/raise it without creating duplicate dialogs.
        """
        dialog, working, code = self._start_custom_edit()
        self.assertFalse(dialog.isVisible(), "Dialog must be hidden during edit.")
        session = dialog._active_edit_session
        self.assertIsNotNone(session)

        cmd = ManageProfileLibrariesCommand()
        cmd.Activated()

        self.assertIs(_find_live_manager(), dialog, "Reinvoking must restore and reuse same dialog.")
        self.assertIs(dialog._active_edit_session, session, "Active edit session must be preserved.")
        self.assertEqual(dialog._active_edit_session.working_doc_name, working.Name)

    def test_edit_failure_preserves_dialog_visibility(self):
        """If starting an edit session fails, the dialog must remain visible and not hidden."""
        doc = App.newDocument("FailEditSource")
        self.created_docs.append(doc.Name)
        sketch = doc.addObject("Sketcher::SketchObject", "CustomSection")
        sketch.Label = "Fail edit profile"
        points = [(0, 0), (30, 0), (30, 20), (0, 20)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)

        cmd = ManageProfileLibrariesCommand()
        cmd.Activated()
        dialog = _find_live_manager()
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="ProbeLib")
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        self.assertTrue(dialog.btn_edit_section.isEnabled())

        with patch(
            "freecad.maxproframe.section_library.SectionEditSession.open",
            side_effect=RuntimeError("Simulated open failure"),
        ):
            dialog.btn_edit_section.click()

        self.assertTrue(dialog.isVisible(), "Dialog must remain visible when edit fails.")
        self.assertIsNone(dialog._active_edit_session, "Edit session must be None on failure.")

    def test_setedit_failure_preserves_dialog_visibility_and_cleans_working_doc(self):
        """When setEdit raises an error or fails to enter edit mode, the dialog must remain
        visible, the failed session and working copy must be closed without leaks, and
        watchers must be safely detached.
        """
        doc = App.newDocument("SetEditFailSource")
        self.created_docs.append(doc.Name)
        sketch = doc.addObject("Sketcher::SketchObject", "CustomSection")
        sketch.Label = "SetEdit Fail Profile"
        points = [(0, 0), (30, 0), (30, 20), (0, 20)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)

        cmd = ManageProfileLibrariesCommand()
        cmd.Activated()
        dialog = _find_live_manager()
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="ProbeLib")
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        self.assertTrue(dialog.btn_edit_section.isEnabled())

        orig_get_doc = Gui.getDocument

        def mock_get_doc(name):
            gdoc = orig_get_doc(name)
            if gdoc is not None and name.startswith("Edit_"):

                class FailGuiDoc:
                    def __getattr__(self, attr):
                        if attr == "setEdit":
                            raise RuntimeError("Simulated setEdit failure")
                        return getattr(gdoc, attr)

                return FailGuiDoc()
            return gdoc

        with patch.object(Gui, "getDocument", side_effect=mock_get_doc):
            dialog.btn_edit_section.click()

        self.assertTrue(dialog.isVisible(), "Dialog must remain visible when setEdit fails.")
        self.assertIsNone(dialog._active_edit_session, "Session must be None after setEdit failure.")
        self.assertFalse(dialog.btn_apply_edit.isEnabled(), "Apply button must be disabled.")
        leaked_docs = [d for d in App.listDocuments() if d.startswith("Edit_")]
        self.assertEqual(leaked_docs, [], f"Working copy document leaked: {leaked_docs}")
        self.assertFalse(getattr(dialog, "_is_hidden_for_sketch_edit", False))
        self.assertIsNone(getattr(dialog, "_sketch_edit_observer", None))
        self.assertIsNone(getattr(dialog, "_sketch_edit_poll_timer", None))

    def test_setedit_returning_false_or_wrong_in_edit_cleans_working_doc(self):
        """When setEdit returns False or getInEdit does not match working sketch,
        the dialog must remain visible, working doc closed, and session invalidated.
        """
        doc = App.newDocument("SetEditFalseSource")
        self.created_docs.append(doc.Name)
        sketch = doc.addObject("Sketcher::SketchObject", "CustomSection")
        sketch.Label = "SetEdit False Profile"
        points = [(0, 0), (30, 0), (30, 20), (0, 20)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)

        cmd = ManageProfileLibrariesCommand()
        cmd.Activated()
        dialog = _find_live_manager()
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="ProbeLib")
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        self.assertTrue(dialog.btn_edit_section.isEnabled())

        orig_get_doc = Gui.getDocument

        def mock_get_doc(name):
            gdoc = orig_get_doc(name)
            if gdoc is not None and name.startswith("Edit_"):

                class FalseGuiDoc:
                    def __getattr__(self, attr):
                        if attr == "setEdit":
                            return lambda *args, **kwargs: False
                        return getattr(gdoc, attr)

                return FalseGuiDoc()
            return gdoc

        with patch.object(Gui, "getDocument", side_effect=mock_get_doc):
            dialog.btn_edit_section.click()

        self.assertTrue(dialog.isVisible(), "Dialog must remain visible when setEdit returns False.")
        self.assertIsNone(dialog._active_edit_session, "Session must be None after setEdit False.")
        self.assertFalse(dialog.btn_apply_edit.isEnabled())
        leaked_docs = [d for d in App.listDocuments() if d.startswith("Edit_")]
        self.assertEqual(leaked_docs, [], f"Working copy document leaked: {leaked_docs}")
        self.assertFalse(getattr(dialog, "_is_hidden_for_sketch_edit", False))
        self.assertIsNone(getattr(dialog, "_sketch_edit_observer", None))
        self.assertIsNone(getattr(dialog, "_sketch_edit_poll_timer", None))

    def test_custom_edit_apply_and_save_publishes_updated_asset_and_catalog(self):
        """End-to-end regression: capture section -> edit section (hidden) -> exit edit mode
        (dialog restored, unapplied) -> click Apply Section Edit -> click Save Changes
        publishes updated asset and catalog cleanly, and close cleans up working document.
        """
        dialog, working, code = self._start_custom_edit()
        session = dialog._active_edit_session
        self.assertFalse(dialog.isVisible(), "Dialog must be hidden during edit.")

        # Simulate user exiting sketcher edit mode
        Gui.getDocument(working.Name).resetEdit()
        _qWait(400)
        self.assertTrue(dialog.isVisible(), "Dialog must restore when exiting sketch edit.")
        self.assertIs(dialog._active_edit_session, session, "Edit session must remain active before apply.")
        self.assertTrue(dialog.btn_apply_edit.isEnabled(), "Apply button must be enabled.")

        # Click Apply Section Edit
        dialog.btn_apply_edit.click()
        self.assertTrue(dialog.is_dirty, "Applying edit must mark dialog dirty.")
        self.assertEqual(
            len(dialog._staged_new_assets), 2, "Capture and edited assets must both be staged before save."
        )

        # Click Save Changes
        dialog.btn_save.click()
        self.assertFalse(dialog.is_dirty, "Saving must clear dirty flag.")
        self.assertEqual(len(dialog._staged_new_assets), 0, "Saving must commit staged assets.")

        # Verify catalog on disk contains Custom Profile
        cat = self.manager.get_library("ProbeLib")
        self.assertIn("Custom Profile", cat)
        self.assertIn(code, cat["Custom Profile"]["sizes"])

        # Close dialog cleanly cleans up working copy
        working_name = working.Name
        dialog.btn_close.click()
        self.assertNotIn(working_name, App.listDocuments(), "Close must destroy working copy document.")

    def test_edit_when_dialog_unshown_skips_sketcher_entry_and_hiding(self):
        """When ProfileLibraryManagerDialog is not visible (headless/direct usage by older tests),
        _on_edit_section opens the session without entering Sketcher workbench or hiding,
        preventing task dialog conflicts and offscreen modal hangs.
        """
        doc = App.newDocument("UnshownEditSource")
        self.created_docs.append(doc.Name)
        sketch = doc.addObject("Sketcher::SketchObject", "CustomSection")
        sketch.Label = "Unshown Custom Profile"
        points = [(0, 0), (30, 0), (30, 20), (0, 20)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)

        orig_wb = Gui.activeWorkbench().name()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.isVisible(), "Directly instantiated dialog is not visible.")
        dialog.refresh_libraries(select_name="ProbeLib")
        dialog.btn_capture_section.click()
        dialog._dxf_review.btn_add.click()
        self.assertTrue(dialog.btn_edit_section.isEnabled())

        dialog.btn_edit_section.click()

        session = dialog._active_edit_session
        self.assertIsNotNone(session, "Edit session must be active.")
        self.created_docs.append(session.working_doc_name)
        self.assertFalse(dialog.isVisible(), "Unshown dialog remains unshown.")
        self.assertFalse(dialog._is_hidden_for_sketch_edit, "Not marked hidden for sketch edit.")
        self.assertIsNone(dialog._sketch_edit_observer, "No GUI observer attached for unshown edit.")
        self.assertIsNone(dialog._sketch_edit_poll_timer, "No poll timer started for unshown edit.")
        self.assertEqual(Gui.activeWorkbench().name(), orig_wb, "Workbench must remain untouched.")
        gui_working = Gui.getDocument(session.working_doc_name)
        if gui_working is not None and hasattr(gui_working, "getInEdit"):
            self.assertIsNone(gui_working.getInEdit(), "Sketcher edit mode was not entered.")

    def test_close_resets_gui_edit_mode_before_document_destruction(self):
        """Closing a SectionEditSession resets GUI edit mode before closing the document,
        preventing dangling ViewProviderEdit pointers in FreeCAD GUI.
        """
        dialog, working, code = self._start_custom_edit()
        session = dialog._active_edit_session
        self.assertIsNotNone(session)
        gui_doc = Gui.getDocument(working.Name)
        self.assertIsNotNone(gui_doc.getInEdit(), "Working sketch is in edit mode.")

        working_name = working.Name
        session.close(discard_uncommitted=True)
        self.assertNotIn(working_name, App.listDocuments(), "Document must be closed.")
        self.assertIsNone(session.working_doc_name)

    def test_next_activation_after_close_creates_fresh_manager_without_staged_assets(self):
        """Rule 4: After close, persistent references are retired and next activation
        creates a fresh valid manager instance without stale edit sessions or assets.
        """
        cmd1 = ManageProfileLibrariesCommand()
        cmd1.Activated()
        dialog1 = _find_live_manager()
        self.assertIsNotNone(dialog1)
        self.assertTrue(dialog1.isVisible())

        # Close dialog
        dialog1.close()
        self.assertFalse(_is_live(dialog1), "Dialog must not be live after close().")

        # Ownership on main window must be retired
        if self.mw is not None:
            self.assertIsNone(getattr(self.mw, "_frameforge_library_manager", None))
        self.assertIsNone(_find_live_manager())

        # Next activation must create a fresh dialog
        cmd2 = ManageProfileLibrariesCommand()
        cmd2.Activated()
        dialog2 = _find_live_manager()

        self.assertIsNotNone(dialog2)
        self.assertTrue(dialog2.isVisible())
        self.assertFalse(dialog2.isModal())
        self.assertIsNone(self.app.activeModalWidget())
        self.assertIsNone(dialog2._active_edit_session, "Fresh manager must have no active edit session.")
        self.assertEqual(
            len(getattr(dialog2, "_staged_new_assets", set())), 0, "Fresh manager must have 0 staged assets."
        )

        dialog2.close()


if __name__ == "__main__":
    unittest.main()

"""Tests for Profile Library Manager window lifecycle, modeless modality,
single-owner persistence, and S10/S9 cleanup.
"""
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError:
        QtCore = QtGui = QtWidgets = None

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
        for method in ("warning", "critical", "information", "question"):
            self.msg_stack.enter_context(patch.object(QtWidgets.QMessageBox, method))
        self.addCleanup(self.msg_stack.close)

        # Clean prior window reference on main window
        if self.mw is not None:
            try:
                setattr(self.mw, "_frameforge_library_manager", None)
            except Exception:
                pass

        self.created_docs = []
        self.addCleanup(self._cleanup_all)

    def _cleanup_all(self):
        # Close any lingering manager dialog to prevent test suite contamination
        dlg = _find_live_manager()
        if dlg is not None:
            try:
                dlg.close()
            except Exception:
                pass
        if self.mw is not None:
            try:
                setattr(self.mw, "_frameforge_library_manager", None)
            except Exception:
                pass
        for name in list(self.created_docs):
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
            for r, _, fs in os.walk(self.folder_lib_path) for f in fs
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

        # 3. Close dialog without Apply/Save (user cancels / discards by closing)
        dialog.btn_close.click()

        # Invariants after close
        self.assertFalse(_is_live(dialog), "Dialog must not be live/visible after close.")
        self.assertNotIn(working_doc_name, App.listDocuments(), "Working document must be destroyed on close.")
        self.assertFalse(os.path.exists(full_staged), "Uncommitted staged asset must be purged on close (S9).")
        self.assertIsNone(self.app.activeModalWidget(), "activeModalWidget must be None after close (S10).")
        if self.mw is not None:
            self.assertTrue(self.mw.isEnabled(), "Main window must remain enabled after close.")

        # Verify disk library catalog is unchanged
        disk_after = {
            os.path.relpath(os.path.join(r, f), self.test_root): open(os.path.join(r, f), "rb").read()
            for r, _, fs in os.walk(self.folder_lib_path) for f in fs
        }
        self.assertEqual(disk_before, disk_after, "Closing without Save must preserve saved catalog and disk assets.")

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
        self.assertEqual(len(getattr(dialog2, "_staged_new_assets", set())), 0, "Fresh manager must have 0 staged assets.")

        dialog2.close()


if __name__ == "__main__":
    unittest.main()

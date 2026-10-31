import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel, _SnapshotFormProxy
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.section_library import compute_sketch_dimensions_and_weight, save_section_asset


class TestCreateProfileConfirmGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.doc_names = []
        self.panels = []
        self.recorded_modals = []

        # Create isolated temporary user workspace
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_gui_user_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)

        # Create isolated custom folder library
        self.folder_lib_name = "CustomFolderLib"
        self.folder_lib_path = os.path.join(self.test_user_dir, self.folder_lib_name)
        self.manager.create_folder_library(
            self.folder_lib_path,
            self.folder_lib_name,
            material="Steel",
            density=7.85,
            data={
                "Square Hollow": {
                    "norm": "EN 10219",
                    "unit": "Metric Units",
                    "fillet": False,
                    "sizes": {
                        "40x40x2": {
                            "Height": "40",
                            "Width": "40",
                            "Thickness": "2",
                            "Flange Thickness": "0",
                            "Radius1": "0",
                            "Radius2": "0",
                            "Weight": "2.4",
                        }
                    },
                },
                "Custom Profile": {
                    "canonical_family": "Custom Profile",
                    "sizes": {},
                },
            },
        )

        # Modal message interception to prevent blocking offscreen tests
        def _record_box(box, *args, **kwargs):
            title = box.windowTitle() if hasattr(box, "windowTitle") else ""
            text = box.text() if hasattr(box, "text") else ""
            self.recorded_modals.append((str(title), str(text)))
            return QtWidgets.QMessageBox.Ok

        def _record_static(parent, title, text, *args, **kwargs):
            self.recorded_modals.append((str(title), str(text)))
            return QtWidgets.QMessageBox.Ok

        self.messages = ExitStack()
        self.messages.enter_context(patch.object(QtWidgets.QMessageBox, "exec_", _record_box))
        if hasattr(QtGui, "QMessageBox") and QtGui.QMessageBox is not QtWidgets.QMessageBox:
            self.messages.enter_context(patch.object(QtGui.QMessageBox, "exec_", _record_box))

        for method_name in ("warning", "critical", "information", "question"):
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method_name, _record_static))
            if hasattr(QtGui, "QMessageBox") and QtGui.QMessageBox is not QtWidgets.QMessageBox:
                self.messages.enter_context(patch.object(QtGui.QMessageBox, method_name, _record_static))

        # Direct interception at create_profiles_tool imported QtGui.QMessageBox
        import freecad.maxproframe.create_profiles_tool as cpt

        target_msgbox = getattr(getattr(cpt, "QtGui", None), "QMessageBox", None)
        if target_msgbox is not None and target_msgbox is not QtWidgets.QMessageBox:
            self.messages.enter_context(patch.object(target_msgbox, "exec_", _record_box))
            for method_name in ("warning", "critical", "information", "question"):
                if hasattr(target_msgbox, method_name):
                    self.messages.enter_context(patch.object(target_msgbox, method_name, _record_static))

        # Snapshot preferences
        self.canonical_param_group = get_param_group(writable=True)
        self.saved_canonical_pref_contents = self._snapshot_param_group(self.canonical_param_group)

        # Patch LibraryManager in create_profiles_tool
        self.mgr_patch = patch(
            "freecad.maxproframe.create_profiles_tool.LibraryManager",
            return_value=self.manager,
        )
        self.mgr_patch.start()

        # Build self-contained custom section sketch WITH AN INTERIOR HOLE
        # Outer rectangle: 60.0 x 40.0; Inner hole rectangle: 20.0 x 10.0 centered at (20..40, 15..25)
        # Expected cross-section area: (60*40) - (20*10) = 2400 - 200 = 2200 mm^2
        temp_doc = self._new_doc("TempSectionDoc")
        sk_hollow = self._create_hollow_rect_sketch(
            temp_doc, "HollowSection", outer_w=60.0, outer_h=40.0, hole_w=20.0, hole_h=10.0
        )
        self._publish_section_to_library(self.folder_lib_path, "CP-HOLE1", sk_hollow, object_name="Section")
        temp_name = temp_doc.Name
        App.closeDocument(temp_name)
        if temp_name in self.doc_names:
            self.doc_names.remove(temp_name)

        # Record checksums of library files for immutability check
        self.initial_lib_checksums = self._snapshot_library_files()

    def tearDown(self):
        # Close any open dialog
        if hasattr(Gui, "Control") and Gui.Control.activeDialog():
            try:
                Gui.Control.closeDialog()
            except Exception:
                pass
        self._pump_events(100)

        # Clean tracked panels
        for panel in list(self.panels):
            try:
                panel.clean()
            except Exception:
                pass
            forms = getattr(panel, "form", None)
            if forms:
                for form in forms:
                    try:
                        if form is not None:
                            form.hide()
                    except Exception:
                        pass
        self.panels.clear()

        if hasattr(self, "mgr_patch"):
            try:
                self.mgr_patch.stop()
            except Exception:
                pass

        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        # Close fixture documents
        open_docs = App.listDocuments()
        for doc_name in list(self.doc_names):
            if doc_name in open_docs:
                try:
                    App.closeDocument(doc_name)
                except Exception:
                    pass
        self.doc_names.clear()

        # Restore preferences
        if hasattr(self, "canonical_param_group") and hasattr(self, "saved_canonical_pref_contents"):
            self._restore_param_group(self.canonical_param_group, self.saved_canonical_pref_contents)

        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        if hasattr(self, "manager") and hasattr(self, "folder_lib_path"):
            try:
                self.manager.unregister_folder_library(self.folder_lib_path)
            except Exception:
                pass

        if os.path.exists(self.folder_lib_path):
            shutil.rmtree(self.folder_lib_path, ignore_errors=True)
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir, ignore_errors=True)

    # --- Helper methods ---

    def _snapshot_param_group(self, group):
        raw = group.GetContents() or []
        return [(t, k, v) for t, k, v in raw]

    def _restore_param_group(self, group, saved_contents):
        current_contents = group.GetContents() or []
        keys_to_clear = {k for _, k, _ in current_contents} | {k for _, k, _ in saved_contents}
        for k in keys_to_clear:
            group.RemString(k)
            group.RemBool(k)
            group.RemInt(k)
            group.RemFloat(k)
            if hasattr(group, "RemUnsigned"):
                group.RemUnsigned(k)
        for t, k, v in saved_contents:
            if t == "String":
                group.SetString(k, str(v))
            elif t == "Bool":
                group.SetBool(k, bool(v))
            elif t == "Integer":
                group.SetInt(k, int(v))
            elif t == "Float":
                group.SetFloat(k, float(v))
            elif t == "Unsigned" and hasattr(group, "SetUnsigned"):
                group.SetUnsigned(k, int(v))

    def _new_doc(self, name_prefix="TestDoc"):
        doc = App.newDocument(name_prefix)
        doc.UndoMode = 1
        self.doc_names.append(doc.Name)
        return doc

    def _create_hollow_rect_sketch(self, doc, name, outer_w=60.0, outer_h=40.0, hole_w=20.0, hole_h=10.0):
        """Creates a SketchObject with an outer boundary and an interior rectangular hole."""
        s = doc.addObject("Sketcher::SketchObject", name)
        # Outer wire (indices 0..3)
        outer_pts = [(0, 0), (outer_w, 0), (outer_w, outer_h), (0, outer_h)]
        for i in range(4):
            a, b = outer_pts[i], outer_pts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))

        # Inner hole wire (indices 4..7)
        offset_x = (outer_w - hole_w) / 2.0
        offset_y = (outer_h - hole_h) / 2.0
        inner_pts = [
            (offset_x, offset_y),
            (offset_x + hole_w, offset_y),
            (offset_x + hole_w, offset_y + hole_h),
            (offset_x, offset_y + hole_h),
        ]
        for i in range(4):
            a, b = inner_pts[i], inner_pts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", 4 + i, 2, 4 + ((i + 1) % 4), 1))

        doc.recompute()
        return s

    def _publish_section_to_library(self, lib_folder, size_code, sketch, object_name="Section"):
        meta = save_section_asset(lib_folder, sketch, name=object_name)
        actual_name = meta["object_name"]
        rel_path = meta["asset_path"]
        aid = meta["asset_id"]

        height, width, weight, area = compute_sketch_dimensions_and_weight(sketch, density_g_cm3=7.85)

        manifest_path = os.path.join(lib_folder, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        if "Custom Profile" not in manifest_data:
            manifest_data["Custom Profile"] = {
                "canonical_family": "Custom Profile",
                "sizes": {},
            }
        manifest_data["Custom Profile"]["sizes"][size_code] = {
            "Height": f"{height:.1f}",
            "Width": f"{width:.1f}",
            "Weight": f"{weight:.2f}",
            "Area": area,
            "asset_path": rel_path.replace("\\", "/"),
            "object_name": actual_name,
            "asset_id": aid,
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        return rel_path, actual_name, aid

    def _snapshot_library_files(self):
        result = {}
        for root, _, files in os.walk(self.folder_lib_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.folder_lib_path)
                with open(full_path, "rb") as fh:
                    result[rel_path] = hashlib.sha256(fh.read()).hexdigest()
        return result

    def _find_dialog_button(self, button_role):
        """Finds standard button in QDialogButtonBox child of Task View dock or MainWindow."""
        mw = Gui.getMainWindow()
        # 1. Target the Task View dock widget directly where the active dialog button box lives
        for dock in mw.findChildren(QtWidgets.QDockWidget):
            if dock.objectName() == "Tasks" or "task" in dock.objectName().lower():
                for box in dock.findChildren(QtWidgets.QDialogButtonBox):
                    try:
                        btn = box.button(button_role)
                        if btn is not None:
                            return btn
                    except Exception:
                        continue
        # 2. Fallback to MainWindow search if dock is not found
        for box in mw.findChildren(QtWidgets.QDialogButtonBox):
            try:
                btn = box.button(button_role)
                if btn is not None:
                    return btn
            except Exception:
                continue
        return None

    def _dismiss_active_modals(self):
        """Auto-dismisses any active native modal dialogs in offscreen mode, recording their contents."""
        for top in QtWidgets.QApplication.topLevelWidgets():
            try:
                if top.isVisible() and (top.isModal() or top.inherits("QMessageBox")):
                    t = str(top.windowTitle() if hasattr(top, "windowTitle") else "")
                    m = str(top.text() if hasattr(top, "text") else "")
                    if (t, m) not in self.recorded_modals:
                        self.recorded_modals.append((t, m))
                    if hasattr(top, "done"):
                        top.done(QtWidgets.QMessageBox.Ok)
            except Exception:
                pass

    def _pump_events(self, duration_ms=200):
        """Pumps Qt event loop to ensure scheduled timers and events process."""
        start = time.time()
        while (time.time() - start) * 1000 < duration_ms:
            QtWidgets.QApplication.processEvents()
            self._dismiss_active_modals()
            QtCore.QThread.msleep(10)

    def _select_profile(self, panel, library, family, size):
        mat_idx = panel.form_proxy.combo_material.findText(library)
        self.assertGreaterEqual(mat_idx, 0, f"{library} must be present in combo_material.")
        panel.form_proxy.combo_material.setCurrentIndex(mat_idx)

        fam_idx = panel.form_proxy.combo_family.findText(family)
        self.assertGreaterEqual(fam_idx, 0, f"{family} must be present in combo_family.")
        panel.form_proxy.combo_family.setCurrentIndex(fam_idx)

        sz_idx = panel.form_proxy.combo_size.findText(size)
        self.assertGreaterEqual(sz_idx, 0, f"{size} must be present in combo_size.")
        panel.form_proxy.combo_size.setCurrentIndex(sz_idx)

    def _click_alignment(self, panel, ax, ay):
        widget = panel.alignment_widget
        point = widget.anchor_position(ax, ay)
        for kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            self.app.sendEvent(
                widget, QtGui.QMouseEvent(kind, point, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            )
        self.assertEqual(panel.get_anchor(), (ax, ay))

    # --- Tests ---

    def test_real_ok_click_without_apply_creates_valid_custom_profile(self):
        """Requested behavior: Clicking real QDialogButtonBox OK button without Apply creates valid custom profile."""
        doc = self._new_doc("DocRealOkNoApply")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        # Confirm dialog is active
        self.assertTrue(bool(Gui.Control.activeDialog()), "Task dialog must be active after showDialog.")

        # Select custom profile with hole
        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)

        self._click_alignment(panel, 2, 0)
        panel.form_proxy.combo_rotation.setCurrentText("37")
        panel.form_proxy.cb_mirror_h.setChecked(True)
        # In live preview mode, setting length and orientation creates the live 3D preview.
        self.assertGreater(len(doc.Objects), 0, "Live preview geometry must exist before OK confirmation.")

        # Find real native QDialogButtonBox Ok button
        ok_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Ok)
        self.assertIsNotNone(ok_button, "Native QDialogButtonBox Ok button must exist.")

        # Click the real native Ok button
        ok_button.click()

        # Pump Qt event loop to let queued finalization execute
        self._pump_events(300)

        # 1. Dialog must be closed
        self.assertFalse(bool(Gui.Control.activeDialog()), "Task dialog must be closed after OK confirmation.")

        # 2. Exactly one Profile object created
        profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles), 1, "Exactly one Profile object must be created.")
        prof = profiles[0]
        self.assertEqual((str(prof.AnchorX), str(prof.AnchorY)), ("Right", "Bottom"))
        self.assertAlmostEqual(prof.RotationAngle, 37)
        self.assertTrue(prof.MirrorH)

        # 3. Valid solid with source holes
        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertTrue(prof.Shape.isValid(), "Shape must be valid.")
        self.assertEqual(len(prof.Shape.Solids), 1, "Must contain exactly one solid.")
        # Hollow rectangular extrusion: area = (60*40 - 20*10) = 2200 mm^2; volume for 100mm = 220,000 mm^3
        self.assertAlmostEqual(prof.Shape.Volume, 220000.0, delta=100.0)

        # 4. Correct length
        self.assertAlmostEqual(float(prof.ProfileLength), 100.0, places=2)

        # 5. Identity preserved: links to imported sketch with provenance properties
        self.assertIsNotNone(prof.CustomProfile, "Profile must link to imported sketch.")
        sk = prof.CustomProfile
        self.assertEqual(getattr(sk, "FF_ObjectName", None), "Section")
        self.assertEqual(getattr(sk, "FF_Provenance", None), os.path.realpath(self.folder_lib_path))
        self.assertEqual(sk.Label, "CP-HOLE1")

        # 6. Source library immutability
        final_checksums = self._snapshot_library_files()
        self.assertEqual(final_checksums, self.initial_lib_checksums, "Source library files must remain untouched.")

        # 7. No auxiliary documents open
        self.assertEqual(list(App.listDocuments().keys()), [doc.Name], "No auxiliary documents should remain open.")

        # 8. Undo behavior: undoing transaction removes the profile
        doc.undo()
        doc.recompute()
        remaining_profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(remaining_profiles), 0, "Undoing must remove the committed profile.")

    def test_live_preview_then_real_ok_click_preserves_previous_behavior(self):
        """Preserve previous behavior: the live preview, then clicking real OK button confirms profile."""
        doc = self._new_doc("DocApplyThenOk")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)
        self._pump_events(50)

        # Preview profile created live with preview transparency
        profiles_after_apply = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles_after_apply), 1)
        preview_prof = profiles_after_apply[0]
        self.assertEqual(preview_prof.ViewObject.Transparency, 80)
        self._click_alignment(panel, 0, 2)

        # Click real native Ok button
        ok_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Ok)
        self.assertIsNotNone(ok_button)
        ok_button.click()
        self._pump_events(300)

        # Dialog closed, profile confirmed with normal transparency (0)
        self.assertFalse(bool(Gui.Control.activeDialog()))
        profiles_after_ok = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles_after_ok), 1)
        confirmed_prof = profiles_after_ok[0]
        self.assertEqual(confirmed_prof.ViewObject.Transparency, 0)
        self.assertEqual((str(confirmed_prof.AnchorX), str(confirmed_prof.AnchorY)), ("Left", "Top"))
        self.assertTrue(confirmed_prof.Shape.isValid())
        self.assertAlmostEqual(confirmed_prof.Shape.Volume, 220000.0, delta=100.0)

    def test_real_ok_click_standard_profile_acceptance(self):
        """Preserve standard profile behavior: OK on standard catalog profile accepts without queuing issues."""
        doc = self._new_doc("DocStandardOk")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        # Standard profile: set length
        panel.form_proxy.sb_length.setValue(150.0)

        ok_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Ok)
        self.assertIsNotNone(ok_button)
        ok_button.click()
        self._pump_events(200)

        self.assertFalse(bool(Gui.Control.activeDialog()))
        profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles), 1)
        self.assertTrue(profiles[0].Shape.isValid())
        self.assertAlmostEqual(float(profiles[0].ProfileLength), 150.0, places=2)

    def test_cancel_button_rolls_back_preview_and_session(self):
        """Cancel/reject rolls back preview geometry and restores document state."""
        doc = self._new_doc("DocCancelGui")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)
        self._pump_events(50)

        # Preview profile exists
        existing_profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(existing_profiles), 1)

        # Find Cancel / Close button
        cancel_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Cancel)
        if cancel_button is None:
            cancel_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Close)

        if cancel_button is not None:
            cancel_button.click()
        else:
            panel.reject()
            Gui.Control.closeDialog()

        self._pump_events(100)

        self.assertFalse(bool(Gui.Control.activeDialog()))
        # All preview profiles rolled back
        profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles), 0, "Cancel must discard all preview profiles.")

    def test_duplicate_accept_guard(self):
        """Guard: Duplicate accept calls while a callback is scheduled are guarded and do not duplicate profiles."""
        doc = self._new_doc("DocDuplicateGuard")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)

        # Trigger queued accept (schedules finalization callback)
        first_result = panel.accept(defer=True)
        self.assertTrue(first_result, "First accept must return True and schedule finalization.")
        self.assertTrue(panel._accept_finalizing, "_accept_finalizing must be True while callback is queued.")

        # Simulate second duplicate accept attempt while callback is still pending
        second_result = panel.accept(defer=True)
        self.assertTrue(second_result, "Duplicate accept must return True immediately without duplicating.")

        # Now let the queued callback execute
        self._pump_events(300)

        # Exactly one profile should be created
        profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles), 1, "Duplicate accept must not create multiple profiles.")

    def test_reject_before_pending_callback_cancels_finalization(self):
        """Guard: Reject before queued callback execution cancels profile creation."""
        doc = self._new_doc("DocRejectPending")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)

        cancel_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Cancel)
        if cancel_button is None:
            cancel_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Close)
        self.assertIsNotNone(cancel_button, "Native QDialogButtonBox Cancel / Close button must exist.")

        finalize_results = []
        finalize_accept = panel._finalize_accept

        def record_finalization():
            result = finalize_accept()
            finalize_results.append(result)
            return result

        # Install the spy before scheduling so the timer captures it; keep it alive through the pump.
        with patch.object(panel, "_finalize_accept", wraps=record_finalization) as finalize_spy:
            self.assertTrue(panel.accept(defer=True))
            self.assertTrue(panel._accept_finalizing, "_accept_finalizing must be True while callback is queued.")
            finalize_spy.assert_not_called()
            self.assertFalse(panel._reject_called)

            # Cancel synchronously through the native controller before the timer fires.
            cancel_button.click()
            self.assertTrue(panel._reject_called, "Native Cancel / Close must call reject.")
            self.assertFalse(panel._accept_finalizing, "Reject must clear _accept_finalizing flag.")
            self.assertFalse(bool(Gui.Control.activeDialog()), "Cancel must close the native task dialog.")
            finalize_spy.assert_not_called()

            self._pump_events(300)
            finalize_spy.assert_called_once_with()
            self.assertEqual(finalize_results, [False], "Queued finalization must return cancellation.")

        self.assertFalse(bool(Gui.Control.activeDialog()))
        profiles = [o for o in doc.Objects if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile"]
        self.assertEqual(len(profiles), 0, "No profile should be created when reject occurs before queued callback.")
        self.assertEqual(len(doc.Objects), 0, "Cancellation must not leave imported sketches or other objects.")
        self.assertEqual(list(App.listDocuments().keys()), [doc.Name], "No auxiliary documents should remain open.")
        self.assertEqual(self._snapshot_library_files(), self.initial_lib_checksums)

    def test_snapshot_form_proxy_raises_attribute_error_on_unknown(self):
        """Correction: _SnapshotFormProxy must raise AttributeError on unknown members."""
        doc = self._new_doc("DocSnapshotTest")
        App.setActiveDocument(doc.Name)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        proxy = _SnapshotFormProxy(panel.form_proxy)
        # Existing known members work
        self.assertEqual(proxy.combo_size.currentText(), panel.form_proxy.combo_size.currentText())
        # Unknown members must raise AttributeError instead of fabricating false widgets
        with self.assertRaises(AttributeError):
            _ = proxy.non_existent_widget_12345
        self.assertFalse(hasattr(proxy, "non_existent_widget_12345"))

    def test_real_ok_missing_asset_reports_error_and_rolls_back(self):
        """Correction: Missing asset on real OK click reports error and rolls back transaction cleanly."""
        doc = self._new_doc("DocMissingAsset")
        App.setActiveDocument(doc.Name)

        # Create a pre-existing object to verify baseline preservation
        doc.addObject("Sketcher::SketchObject", "PreExistingSketch")
        doc.recompute()
        baseline_obj_names = [o.Name for o in doc.Objects]
        baseline_undo_count = doc.UndoCount

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Control.showDialog(panel)
        self._pump_events(50)

        self._select_profile(panel, self.folder_lib_name, "Custom Profile", "CP-HOLE1")
        panel.form_proxy.sb_length.setValue(100.0)

        # Delete the FCStd asset file AFTER configuration so no doc-local source exists
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        rel_asset_path = manifest_data["Custom Profile"]["sizes"]["CP-HOLE1"]["asset_path"]
        abs_asset_path = os.path.join(self.folder_lib_path, rel_asset_path)
        self.assertTrue(os.path.isfile(abs_asset_path), "Asset file must exist prior to deletion.")
        os.remove(abs_asset_path)
        self.assertFalse(os.path.isfile(abs_asset_path), "Asset file must be removed.")

        # Snapshot document state and remaining library files
        doc_names_before = list(App.listDocuments().keys())
        missing_lib_checksums = self._snapshot_library_files()
        self.recorded_modals.clear()

        # Click actual native Ok button
        ok_button = self._find_dialog_button(QtWidgets.QDialogButtonBox.Ok)
        self.assertIsNotNone(ok_button)
        ok_button.click()
        self._pump_events(300)

        # Assert error was visibly reported via modal QMessageBox
        self.assertGreaterEqual(
            len(self.recorded_modals),
            1,
            "An error dialog must be displayed when asset is missing on OK finalization.",
        )
        modal_title, modal_msg = self.recorded_modals[-1]
        self.assertIn("Create Profile", modal_title)
        self.assertIn("Failed to create profile", modal_msg)

        # Assert no new profile, source sketch, or auxiliary document
        current_obj_names = [o.Name for o in doc.Objects]
        self.assertEqual(current_obj_names, baseline_obj_names, "No new objects should remain after rollback.")
        self.assertEqual(
            list(App.listDocuments().keys()),
            doc_names_before,
            "No auxiliary documents should remain open.",
        )

        # Pre-existing objects untouched
        self.assertIsNotNone(doc.getObject("PreExistingSketch"))

        # Rollback leaves expected UndoCount / no open transaction
        self.assertEqual(
            doc.UndoCount,
            baseline_undo_count,
            "Transaction must be aborted; UndoCount should remain at baseline.",
        )

        # Remaining library files unchanged
        self.assertEqual(self._snapshot_library_files(), missing_lib_checksums)

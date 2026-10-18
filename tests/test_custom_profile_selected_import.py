"""Deterministic public native tests for custom profile selected import, naming, and tree visibility (T7).

Covers:
- S11: Single selected custom profile import without accumulating unselected catalog sketches
- S12: Inserted auxiliary section sketch visible Label displays the library profile code
- S13: Newly imported auxiliary section sketch starts hidden in project tree (ShowInTree=False)
       and viewport (Visibility=False) while profile remains valid
- Preservation (S7, S8, S9): Multi-edge share, same asset reuse, cancel/reject transaction rollback,
  preservation of existing user sketches, and standard parametric profile creation.
"""

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.section_capture import save_section_asset
from freecad.maxproframe.section_library import (
    compute_sketch_dimensions_and_weight,
)


class TestCustomProfileSelectedImport(unittest.TestCase):
    @staticmethod
    def _snapshot_param_group(group):
        raw = group.GetContents() or []
        return [(t, k, v) for t, k, v in raw]

    @staticmethod
    def _restore_param_group(group, saved_contents):
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

    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        # 1. Initialize tracking collections BEFORE any fixture documents or UI objects are created
        self.doc_names = []
        self.panels = []
        self.recorded_modals = []
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # 2. Workspace and directories
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_cp_import_")
        self.test_root = self.workspace.name
        self.user_dir = os.path.join(self.test_root, "user")
        self.stock_dir = os.path.join(self.test_root, "stock")
        self.reg_dir = os.path.join(self.test_root, "registry")
        self.reg_path = os.path.join(self.reg_dir, "folders.json")
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.stock_dir, exist_ok=True)
        os.makedirs(self.reg_dir, exist_ok=True)

        self.manager = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )

        # Standard stock parametric library for preservation checks (StockSteel)
        stock_data = {
            "_metadata": {"name": "StockSteel", "material": "Steel", "density": 7.85},
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
        }
        with open(os.path.join(self.stock_dir, "StockSteel.json"), "w", encoding="utf-8") as f:
            json.dump(stock_data, f)
        with open(os.path.join(self.stock_dir, "stock_steel.json"), "w", encoding="utf-8") as f:
            json.dump(stock_data, f)

        # Primary registered folder library with 3 distinct custom profiles
        self.folder_lib_path = os.path.join(self.test_root, "CustomFolderLib")
        self.manager.create_folder_library(
            self.folder_lib_path,
            "CustomFolderLib",
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

        # Fail-on-modal guard: record calls so swallowed Qt slot exceptions are caught
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

        # Snapshot canonical (MaxProFrame) and legacy (Frameforge) preferences safely
        self.canonical_param_group = get_param_group(writable=True)
        self.legacy_param_group = App.ParamGet("User parameter:BaseApp/Preferences/Frameforge")
        self.param_group = self.canonical_param_group
        self.saved_canonical_pref_contents = self._snapshot_param_group(self.canonical_param_group)
        self.saved_legacy_pref_contents = self._snapshot_param_group(self.legacy_param_group)
        self.saved_pref_contents = self.saved_canonical_pref_contents

        # Patch LibraryManager in create_profiles_tool to return isolated test manager
        self.mgr_patch = patch(
            "freecad.maxproframe.create_profiles_tool.LibraryManager",
            return_value=self.manager,
        )
        self.mgr_patch.start()

        # Build 3 distinct valid closed rectangular sections and publish to folder library via save_section_asset
        temp_doc = self._new_doc("TempSectionsDoc")
        sk_901 = self._create_rect_sketch(temp_doc, "Sketch901", width=30.0, height=20.0)
        self._publish_section_to_library(self.folder_lib_path, "CP-901", sk_901, object_name="Section")

        sk_902 = self._create_rect_sketch(temp_doc, "Sketch902", width=50.0, height=30.0)
        self._publish_section_to_library(self.folder_lib_path, "CP-902", sk_902, object_name="Section")

        sk_903 = self._create_rect_sketch(temp_doc, "Sketch903", width=80.0, height=40.0)
        self._publish_section_to_library(self.folder_lib_path, "CP-903", sk_903, object_name="Section")

        temp_name = temp_doc.Name
        App.closeDocument(temp_name)
        if temp_name in self.doc_names:
            self.doc_names.remove(temp_name)

    def tearDown(self):
        # 1. Clean and close any tracked task panels
        for panel in list(self.panels):
            try:
                panel.clean()
            except Exception:
                pass
            if hasattr(panel, "form"):
                for form in getattr(panel, "form", []):
                    try:
                        form.hide()
                    except Exception:
                        pass
        self.panels.clear()

        # 2. Stop LibraryManager patch
        if hasattr(self, "mgr_patch"):
            try:
                self.mgr_patch.stop()
            except Exception:
                pass

        # 3. Clear Gui.Selection
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        # 4. Close ONLY fixture-created doc_names (stored strings before closing)
        open_docs = App.listDocuments()
        for doc_name in list(self.doc_names):
            if doc_name in open_docs:
                try:
                    App.closeDocument(doc_name)
                except Exception:
                    pass
        self.doc_names.clear()

        # 5. Restore MaxProFrame (canonical) and Frameforge (legacy) preferences if any were modified
        if hasattr(self, "canonical_param_group") and hasattr(self, "saved_canonical_pref_contents"):
            self._restore_param_group(self.canonical_param_group, self.saved_canonical_pref_contents)
        if hasattr(self, "legacy_param_group") and hasattr(self, "saved_legacy_pref_contents"):
            self._restore_param_group(self.legacy_param_group, self.saved_legacy_pref_contents)
        if hasattr(self, "param_group") and hasattr(self, "saved_pref_contents"):
            if self.param_group is not getattr(self, "canonical_param_group", None) and self.param_group is not getattr(self, "legacy_param_group", None):
                self._restore_param_group(self.param_group, self.saved_pref_contents)

        # 6. Close message patches
        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        # 7. Clean up workspace
        try:
            self.workspace.cleanup()
        except Exception:
            pass

    # --- Helper methods ---

    def _new_doc(self, name_prefix="TestDoc"):
        doc = App.newDocument(name_prefix)
        self.doc_names.append(doc.Name)
        return doc

    def _create_rect_sketch(self, doc, name="RectSection", width=30.0, height=20.0):
        s = doc.addObject("Sketcher::SketchObject", name)
        pts = [(0, 0), (width, 0), (width, height), (0, height)]
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
        s.addConstraint(Sketcher.Constraint("Distance", 0, float(width)))
        s.addConstraint(Sketcher.Constraint("Distance", 1, float(height)))
        doc.recompute()
        return s

    def _create_line_path(self, doc, name="Path", length=100.0):
        p = doc.addObject("Sketcher::SketchObject", name)
        p.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(length, 0, 0)), False)
        p.addConstraint(Sketcher.Constraint("Distance", 0, float(length)))
        self.assertEqual(p.solve(), 0, "Path fixture must solve before profile attachment.")
        doc.recompute()
        self.assertEqual(len(p.Shape.Edges), 1, "Path fixture must expose one valid edge.")
        return p

    def _create_two_edge_path(self, doc, name="TwoEdgePath", len1=100.0, len2=100.0):
        p = doc.addObject("Sketcher::SketchObject", name)
        p.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(len1, 0, 0)), False)
        p.addGeometry(Part.LineSegment(App.Vector(len1, 0, 0), App.Vector(len1, len2, 0)), False)
        p.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        p.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        p.addConstraint(Sketcher.Constraint("Distance", 0, float(len1)))
        p.addConstraint(Sketcher.Constraint("Distance", 1, float(len2)))
        p.addConstraint(Sketcher.Constraint("Horizontal", 0))
        p.addConstraint(Sketcher.Constraint("Vertical", 1))
        self.assertEqual(p.solve(), 0, "TwoEdgePath fixture must solve cleanly.")
        doc.recompute()
        self.assertEqual(len(p.Shape.Edges), 2, "TwoEdgePath fixture must expose exactly two edges.")
        return p

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

    def _assert_no_modals(self, context=""):
        if self.recorded_modals:
            modals_repr = ", ".join(f"[{t}: {m}]" for t, m in self.recorded_modals)
            self.recorded_modals.clear()
            self.fail(f"Unexpected modal dialog(s) recorded in {context}: {modals_repr}")

    def _select_profile(self, panel, library, family, size):
        mat_idx = panel.form_proxy.combo_material.findText(library)
        self.assertGreaterEqual(mat_idx, 0, f"{library} must be present in combo_material.")
        panel.form_proxy.combo_material.setCurrentIndex(mat_idx)
        self._assert_no_modals(f"combo_material -> {library}")

        fam_idx = panel.form_proxy.combo_family.findText(family)
        self.assertGreaterEqual(fam_idx, 0, f"{family} must be present in combo_family.")
        panel.form_proxy.combo_family.setCurrentIndex(fam_idx)
        self._assert_no_modals(f"combo_family -> {family}")

        size_idx = panel.form_proxy.combo_size.findText(size)
        self.assertGreaterEqual(size_idx, 0, f"{size} must be present in combo_size.")
        panel.form_proxy.combo_size.setCurrentIndex(size_idx)
        self._assert_no_modals(f"combo_size -> {size}")

    def _get_profiles(self, doc):
        return [
            o for o in doc.Objects
            if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]

    # --- Rule S11: Selected Custom Profile import only (no orphan accumulation) ---

    def test_s11_single_selected_custom_profile_import_no_orphans(self):
        """S11: Reproduce insertion through real CreateProfileTaskPanel workflow with a multi-CP library;

        import ONLY the selected section sketch into the project document; do not accumulate
        sketches for unselected catalog entries triggered by combo initialization or size switching.
        """
        project_doc = self._new_doc("ProjectS11Doc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0)

        disk_before = self._snapshot_library_files()

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("panel.open")

        # Drive real Qt combo selections: switch to CustomFolderLib, Custom Profile, then select CP-902
        self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-902")

        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")
        self._assert_no_modals("panel.accept")

        project_doc.recompute()

        # Verify exactly one Profile object created with CP-902 geometry
        profiles = self._get_profiles(project_doc)
        self.assertEqual(len(profiles), 1, "Exactly one Profile object should be created.")
        prof = profiles[0]

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertTrue(prof.Shape.isValid())
        self.assertEqual(len(prof.Shape.Solids), 1)

        # CP-902 is 50.0 x 30.0 x 100.0 = 150,000.0 mm^3
        self.assertAlmostEqual(prof.Shape.Volume, 150000.0, places=2)
        self.assertIsNotNone(prof.CustomProfile, "Profile must link to CustomProfile sketch.")

        # S11 core check: exactly ONE section sketch must exist in project document (excluding Path)
        sketches = [
            o for o in project_doc.Objects
            if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("Sketcher::SketchObject")
        ]
        section_sketches = [s for s in sketches if s.Name != path_sk.Name]
        self.assertEqual(
            len(section_sketches),
            1,
            f"Expected exactly 1 section sketch in document, but found {len(section_sketches)}: "
            f"{[s.Name for s in section_sketches]}",
        )
        self.assertEqual(
            prof.CustomProfile.Name,
            section_sketches[0].Name,
            "Profile CustomProfile must reference the single imported section sketch.",
        )

        # Pre-existing path sketch and library files on disk remain unchanged
        self.assertEqual(path_sk.Label, "Path")
        self.assertTrue(path_sk.Shape.isValid())
        self.assertEqual(self._snapshot_library_files(), disk_before, "Library files must remain unchanged.")

    # --- Rule S12: Imported sketch visible label displays library profile code ---

    def test_s12_imported_sketch_label_matches_profile_code(self):
        """S12: The imported section sketch displays the selected library profile code as its visible Label;

        preserve FreeCAD internal identifier sanitization on Name while matching exact profile code on Label.
        """
        project_doc = self._new_doc("ProjectS12Doc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0)

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("panel.open")

        self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-901")

        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")
        self._assert_no_modals("panel.accept")

        project_doc.recompute()

        profiles = self._get_profiles(project_doc)
        self.assertEqual(len(profiles), 1)
        prof = profiles[0]
        self.assertIsNotNone(prof.CustomProfile)

        imported_sketch = prof.CustomProfile

        # S12 core check: visible Label must match the exact library profile code "CP-901"
        self.assertEqual(
            imported_sketch.Label,
            "CP-901",
            f"Imported section sketch Label must match profile code 'CP-901', but got '{imported_sketch.Label}'.",
        )

        # Pre-existing path sketch is not renamed
        self.assertEqual(path_sk.Label, "Path", "Pre-existing sketch Label must not be renamed.")

    # --- Rule S13: Imported auxiliary sketch is hidden by default in tree and viewport ---

    def test_s13_imported_auxiliary_sketch_hidden_in_tree_and_viewport(self):
        """S13: Newly imported auxiliary section sketches are hidden by default in the project tree

        (ShowInTree=False) and viewport (Visibility=False) while remaining linked and valid;
        pre-existing project sketches preserve their visibility and tree display.
        """
        project_doc = self._new_doc("ProjectS13Doc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0)

        # Pre-existing path sketch starts visible
        if getattr(path_sk, "ViewObject", None) is not None:
            self.assertTrue(path_sk.ViewObject.Visibility)
            self.assertTrue(path_sk.ViewObject.ShowInTree)

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("panel.open")

        self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-901")

        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")
        self._assert_no_modals("panel.accept")

        project_doc.recompute()

        profiles = self._get_profiles(project_doc)
        self.assertEqual(len(profiles), 1)
        prof = profiles[0]
        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertIsNotNone(prof.CustomProfile)

        imported_sketch = prof.CustomProfile

        # S13 core check: imported sketch ViewObject has ShowInTree=False and Visibility=False
        view_obj = getattr(imported_sketch, "ViewObject", None)
        self.assertIsNotNone(view_obj, "Imported sketch must have a ViewObject.")
        self.assertFalse(
            view_obj.ShowInTree,
            "Imported auxiliary section sketch must have ShowInTree=False.",
        )
        self.assertFalse(
            view_obj.Visibility,
            "Imported auxiliary section sketch must have Visibility=False.",
        )

        # Pre-existing project sketch visibility and tree display are preserved
        if getattr(path_sk, "ViewObject", None) is not None:
            self.assertTrue(path_sk.ViewObject.Visibility, "Pre-existing path sketch Visibility must remain True.")
            self.assertTrue(path_sk.ViewObject.ShowInTree, "Pre-existing path sketch ShowInTree must remain True.")
        self.assertEqual(path_sk.Label, "Path")

    # --- Preservation Case 1: Multi-edge share, same asset reuse, cancel rollback, user sketch preserved ---

    def test_preservation_multi_edge_custom_profile_reuse_and_cancel_rollback(self):
        """Preservation (S7, S8, S9): Multiple edges sharing the same asset reuse the single imported sketch;

        pre-existing user sketches are not renamed, hidden, or deleted; and panel cancel/reject
        rolls back uncommitted preview objects and restores document state.
        """
        project_doc = self._new_doc("ProjectPreserveDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_two_edge_path(project_doc, "TwoEdgePath", 100.0, 100.0)
        user_sk = self._create_rect_sketch(project_doc, "MyCustomUserSketch", width=25.0, height=25.0)

        # Select both Edge1 and Edge2
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge2")

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("panel.open")

        self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-901")

        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")
        self._assert_no_modals("panel.accept")

        project_doc.recompute()

        profiles = self._get_profiles(project_doc)
        self.assertEqual(len(profiles), 2, "Exactly two Profile objects should be created.")
        prof1, prof2 = profiles[0], profiles[1]
        self.assertEqual(prof1.getStatusString(), "Valid")
        self.assertEqual(prof2.getStatusString(), "Valid")

        # Same asset reuse: both profiles share the exact same section sketch object
        self.assertEqual(
            prof1.CustomProfile.Name,
            prof2.CustomProfile.Name,
            "Both profiles on multiple edges must share the exact same CustomProfile sketch.",
        )

        # Pre-existing user-owned sketch is untouched
        self.assertIn("MyCustomUserSketch", [o.Label for o in project_doc.Objects])
        self.assertEqual(user_sk.Label, "MyCustomUserSketch")
        self.assertEqual(user_sk.Document.Name, project_doc.Name)

        # Now test Cancel/reject transaction rollback:
        # Opening a second panel on Edge1 with a different size, then rejecting, leaves document unchanged.
        doc_objs_before = {o.Name for o in project_doc.Objects}

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel2 = CreateProfileTaskPanel()
        self.panels.append(panel2)
        panel2.open()
        self._assert_no_modals("panel2.open")

        self._select_profile(panel2, "CustomFolderLib", "Custom Profile", "CP-902")

        # Reject/Cancel
        rejected = panel2.reject()
        self.assertTrue(rejected, "Panel reject must return True.")
        self._assert_no_modals("panel2.reject")
        self.panels.remove(panel2)

        project_doc.recompute()
        doc_objs_after = {o.Name for o in project_doc.Objects}
        self.assertEqual(
            doc_objs_after,
            doc_objs_before,
            "Reject/cancel must rollback preview and restore document objects to exact state before open.",
        )
        self.assertEqual(user_sk.Label, "MyCustomUserSketch")

    # --- Preservation Case 2: Standard parametric profile creation ---

    def test_preservation_standard_parametric_profile_creation(self):
        """Preservation (S1, S8): Existing non-custom parametric family creation works as before;

        produces valid Profile with standard dimensional properties, no CustomProfile sketch link,
        and no unexpected modal dialogs.
        """
        project_doc = self._new_doc("ProjectParametricDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0)

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("panel.open")

        self._select_profile(panel, "StockSteel", "Square Hollow", "40x40x2")

        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")
        self._assert_no_modals("panel.accept")

        project_doc.recompute()

        profiles = self._get_profiles(project_doc)
        self.assertEqual(len(profiles), 1, "Exactly one parametric profile should be created.")
        prof = profiles[0]

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertTrue(prof.Shape.isValid())
        self.assertEqual(len(prof.Shape.Solids), 1)

        # Parametric hollow 40x40x2 on length 100 has volume ~30,400 mm^3
        self.assertAlmostEqual(prof.Shape.Volume, 30400.0, places=1)

        # Standard parametric profile must not link to any CustomProfile sketch
        has_cp = hasattr(prof, "CustomProfile") and prof.CustomProfile is not None
        self.assertFalse(has_cp, "Standard parametric profile must not have a CustomProfile link.")

        # No auxiliary section sketches imported into document (only Path exists)
        sketches = [
            o for o in project_doc.Objects
            if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("Sketcher::SketchObject")
        ]
        self.assertEqual(len(sketches), 1, "Only the path sketch should exist in document.")
        self.assertEqual(sketches[0].Name, path_sk.Name)


if __name__ == "__main__":
    unittest.main()

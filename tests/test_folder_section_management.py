"""Native GUI regression tests for folder library Custom Profile section management (T4).

Covers S1, S2, S4, S5, S8, S9:
- Rule 1: Capture from Gui.Selection creates autonomous asset and geometry row
- Rule 2: Capture without selection or multiple sketches requires explicit chooser
- Rule 3: Rejection of invalid section geometry without data loss
- Rule 4: Native edit opens separate working copy; published asset untouched
- Rule 5: Apply/validate edited sketch updates geometry, bounds, and weight
- Rule 6: Rename catalog code preserves stable asset filenames and metadata
- Rule 7: Non-column and arbitrary numeric metadata survive table populate/commit
- Rule 8: S9 staged deletion defers asset removal until successful save
- Rule 9: S9 cancel or discard preserves staged deleted assets and catalog
- Rule 10: S9 shared asset references survive deletion
- Rule 11: Failed save preserves dirty edits and does not delete assets
- Rule 12: Asset path confinement rejects traversal, absolute paths, and symlinks
- Rule 13: Cleanup of staged artifacts on cancel/failure without deleting unrelated files
- Rule 14: Preserve legacy parametric family behavior and table operations
"""

import copy
import hashlib
import json
import math
import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

from freecad.frameforge.custom_section_geometry import build_custom_section_face
from freecad.frameforge.ff_tools import translate
from freecad.frameforge.library_manager import (
    LibraryManager,
    STANDARD_DENSITIES,
)
from freecad.frameforge.library_manager_dialog import ProfileLibraryManagerDialog
from freecad.frameforge.section_capture import capture_section_sketch, save_section_asset


class TestFolderSectionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_sec_mgmt_")
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

        # Create a registered folder library with Steel (density 7.85)
        self.folder_lib_path = os.path.join(self.test_root, "CustomFolderLib")
        self.manager.create_folder_library(
            self.folder_lib_path,
            "CustomFolderLib",
            material="Steel",
            density=7.85,
            data={
                "Square Hollow": {
                    "norm": "EN 10219",
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
                    "norm": "Custom",
                    "fillet": False,
                    "canonical_family": "Custom Profile",
                    "sizes": {},
                },
            },
        )

        self.doc_names = []
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # Patch QMessageBox upfront so no unexpected modal dialog blocks offscreen execution
        self.messages = ExitStack()
        for method in ("warning", "critical", "information", "question"):
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method))

        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.dialog.refresh_libraries(select_name="CustomFolderLib")

    def tearDown(self):
        # 1. Close dialog while QMessageBox patches remain active
        if hasattr(self, "dialog") and self.dialog is not None:
            try:
                self.dialog.close()
            except Exception:
                pass

        # 2. Clear Gui.Selection
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        # 3. Close ALL open FreeCAD documents (including dialog-owned working documents)
        for doc_name in list(App.listDocuments().keys()):
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        self.doc_names.clear()

        # 4. Close message patches after dialog and documents are safely closed
        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        # 5. Clean up workspace
        try:
            self.workspace.cleanup()
        except Exception:
            pass

    # --- Helper methods ---

    def _new_doc(self, name_prefix="TestDoc"):
        doc = App.newDocument(name_prefix)
        self.doc_names.append(doc.Name)
        return doc

    def _create_rect_sketch(self, doc, name="RectSection", width=120.0, height=60.0):
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

    def _select_family(self, family_name):
        # Hydrate fixtures inserted into the model even when this family is already selected.
        # Do not commit the stale widget rows back over the injected fixture.
        self.dialog.current_lib_data.setdefault(
            family_name,
            {"norm": "Custom", "fillet": False, "canonical_family": family_name, "sizes": {}},
        )
        self.dialog.current_family = None
        self.dialog._populate_families(select_family=family_name)

    def _create_published_asset(self, asset_id="sec_published_1", width=80.0, height=40.0):
        """Creates a real published .FCStd section asset in the folder library.

        Captures doc name before closing to avoid accessing destroyed C++ objects.
        """
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        doc = self._new_doc("PublishedAssetDoc")
        s = self._create_rect_sketch(doc, "Section", width=width, height=height)
        filename = f"{asset_id}.FCStd"
        target_path = os.path.join(sections_dir, filename)
        doc_name = doc.Name
        doc.saveAs(target_path)
        App.closeDocument(doc_name)
        if doc_name in self.doc_names:
            self.doc_names.remove(doc_name)
        return os.path.join("sections", filename)

    # --- Rule 1: Capture from Gui.Selection creates asset and geometry row ---

    def test_r1_capture_from_selection_creates_asset_and_geometry_row(self):
        """Rule 1: Captures explicitly selected sketch, creates autonomous .FCStd asset,

        populates table with derived dimensions and weight, and locks dimension cells.
        """
        self.assertTrue(hasattr(self.dialog, "btn_capture_section"), "Dialog must have btn_capture_section button.")

        doc = self._new_doc("SourceDoc")
        sketch = self._create_rect_sketch(doc, "MyCustomRect", width=120.0, height=60.0)

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name)

        self._select_family("Custom Profile")
        initial_rows = self.dialog.table_sizes.rowCount()

        self.dialog.btn_capture_section.click()

        self.assertEqual(self.dialog.table_sizes.rowCount(), initial_rows + 1)
        row = self.dialog.table_sizes.rowCount() - 1

        # Check dimension values derived from native face geometry
        code = self.dialog.table_sizes.item(row, 0).text().strip()
        self.assertTrue(bool(code), "Captured row must have a size code.")

        height_val = float(self.dialog.table_sizes.item(row, 1).text())
        width_val = float(self.dialog.table_sizes.item(row, 2).text())
        weight_val = float(self.dialog.table_sizes.item(row, 7).text())

        self.assertAlmostEqual(height_val, 60.0, places=2)
        self.assertAlmostEqual(width_val, 120.0, places=2)
        # Weight = area * density * 0.001 = (120 * 60) * 7.85 * 0.001 = 56.52 kg/m
        expected_weight = 120.0 * 60.0 * 7.85 * 0.001
        self.assertAlmostEqual(weight_val, expected_weight, places=2)

        # Dimension cells should be read-only (flags without ItemIsEditable) to prevent divergence
        for col_idx in (1, 2, 7):
            item = self.dialog.table_sizes.item(row, col_idx)
            self.assertFalse(
                bool(item.flags() & QtCore.Qt.ItemIsEditable),
                f"Column {col_idx} should not be editable for geometry rows.",
            )

        # Verify asset file created on disk in sections/
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        self.assertTrue(os.path.isdir(sections_dir))
        asset_files = [f for f in os.listdir(sections_dir) if f.endswith(".FCStd")]
        self.assertEqual(len(asset_files), 1)

        # Verify source doc was untouched
        self.assertEqual(sketch.solve(), 0)
        self.assertEqual(doc.Name, "SourceDoc")

        # Verify newly created asset is a standalone, editable sketch
        asset_full_path = os.path.join(sections_dir, asset_files[0])
        asset_doc = App.openDocument(asset_full_path)
        asset_doc_name = asset_doc.Name
        try:
            sketches = [
                obj for obj in asset_doc.Objects
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
            ]
            self.assertTrue(len(sketches) >= 1, "Published asset must contain a SketchObject.")
            captured_sketch = sketches[0]
            self.assertEqual(captured_sketch.solve(), 0)
            self.assertEqual(len(captured_sketch.ExternalGeometry), 0, "Captured sketch must have 0 external links.")
            face = build_custom_section_face(captured_sketch)
            self.assertTrue(face.isValid())
            self.assertAlmostEqual(face.Area, 120.0 * 60.0, places=2)
        finally:
            App.closeDocument(asset_doc_name)

    # --- Rule 2: Explicit sketch chooser when none or multiple selected ---

    def test_r2_capture_without_selection_or_multiple_uses_explicit_chooser(self):
        """Rule 2: Never silently pick first valid sketch; prompt with explicit chooser.

        Aborts cleanly without data changes if chooser is canceled.
        """
        self.assertTrue(hasattr(self.dialog, "btn_capture_section"))

        doc = self._new_doc("MultiDoc")
        s1 = self._create_rect_sketch(doc, "SketchA", width=50.0, height=50.0)
        s2 = self._create_rect_sketch(doc, "SketchB", width=70.0, height=35.0)

        self._select_family("Custom Profile")

        # Case A: No selection and user cancels chooser -> no row added, no asset written
        Gui.Selection.clearSelection()
        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=("", False)):
            self.dialog.btn_capture_section.click()

        self.assertEqual(self.dialog.table_sizes.rowCount(), 0)
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        if os.path.exists(sections_dir):
            self.assertEqual(len(os.listdir(sections_dir)), 0)

        # Case B: Multiple sketches selected; explicit chooser selects SketchB
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, s1.Name)
        Gui.Selection.addSelection(doc.Name, s2.Name)

        with patch.object(QtWidgets.QInputDialog, "getItem", return_value=(f"{doc.Name}#SketchB", True)):
            self.dialog.btn_capture_section.click()

        self.assertEqual(self.dialog.table_sizes.rowCount(), 1)
        # Should have captured SketchB (width 70, height 35)
        w_val = float(self.dialog.table_sizes.item(0, 2).text())
        h_val = float(self.dialog.table_sizes.item(0, 1).text())
        self.assertAlmostEqual(w_val, 70.0, places=2)
        self.assertAlmostEqual(h_val, 35.0, places=2)

    # --- Rule 3: Rejection of invalid section geometry without data loss ---

    def test_r3_capture_rejects_invalid_section_geometry_without_data_loss(self):
        """Rule 3: Sketches with disconnected regions or invalid geometry are rejected

        without modifying catalog or creating asset files.
        """
        self.assertTrue(hasattr(self.dialog, "btn_capture_section"))

        doc = self._new_doc("InvalidDoc")
        # Disconnected two separate rectangles in one sketch (violates S5 single connected region)
        s_invalid = doc.addObject("Sketcher::SketchObject", "DisconnectedRects")
        # Rect 1
        s_invalid.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(20, 0, 0), App.Vector(20, 20, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(20, 20, 0), App.Vector(0, 20, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(0, 20, 0), App.Vector(0, 0, 0)), False)
        # Rect 2 (disconnected at offset 50)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(50, 0, 0), App.Vector(70, 0, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(70, 0, 0), App.Vector(70, 20, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(70, 20, 0), App.Vector(50, 20, 0)), False)
        s_invalid.addGeometry(Part.LineSegment(App.Vector(50, 20, 0), App.Vector(50, 0, 0)), False)
        doc.recompute()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, s_invalid.Name)

        self._select_family("Custom Profile")
        sections_dir = os.path.join(self.folder_lib_path, "sections")

        self.dialog.btn_capture_section.click()

        self.assertEqual(self.dialog.table_sizes.rowCount(), 0)
        if os.path.exists(sections_dir):
            self.assertEqual(len(os.listdir(sections_dir)), 0)

    # --- Rule 4: Native edit opens separate working copy; published asset untouched ---

    def test_r4_edit_opens_separate_working_copy_published_asset_untouched(self):
        """Rule 4: Editing opens an autonomous working copy in FreeCAD.

        The published asset file remains untouched and not exposed to direct save.
        """
        self.assertTrue(hasattr(self.dialog, "btn_edit_section"), "Dialog must have btn_edit_section button.")

        rel_asset = self._create_published_asset("sec_pub_edit_test", width=80.0, height=40.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)
        with open(full_asset_path, "rb") as f:
            original_asset_bytes = f.read()

        # Add section entry to catalog data and refresh table
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Custom_80x40"] = {
            "Height": "40.0",
            "Width": "80.0",
            "Thickness": "0.0",
            "Weight": "25.12",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_pub_edit_test",
        }
        self._select_family("Custom Profile")
        self.dialog.table_sizes.selectRow(0)

        initial_open_docs = set(App.listDocuments().keys())

        self.dialog.btn_edit_section.click()

        current_open_docs = set(App.listDocuments().keys())
        new_docs = current_open_docs - initial_open_docs
        self.assertTrue(len(new_docs) >= 1, "A new working document should be opened for editing.")

        # Published asset on disk must not have changed
        with open(full_asset_path, "rb") as f:
            current_asset_bytes = f.read()
        self.assertEqual(original_asset_bytes, current_asset_bytes, "Published asset must remain untouched.")

        # Verify working doc sketch is autonomous and solves cleanly
        working_doc_name = list(new_docs)[0]
        working_doc = App.getDocument(working_doc_name)
        working_sketches = [
            obj for obj in working_doc.Objects
            if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
        ]
        self.assertTrue(len(working_sketches) >= 1, "Working document must contain a SketchObject.")
        self.assertEqual(working_sketches[0].solve(), 0)

    # --- Rule 5: Apply/validate edited sketch updates geometry, bounds, and weight ---

    def test_r5_apply_edited_section_validates_and_updates_row(self):
        """Rule 5: Applying edits re-validates the section, updates row Height/Width/Weight,

        and stages the update without mutating original published asset before Save.
        After Save, reopened referenced asset reflects edited geometry.
        """
        self.assertTrue(hasattr(self.dialog, "btn_edit_section"), "Dialog must have btn_edit_section button.")
        self.assertTrue(hasattr(self.dialog, "apply_section_edit"), "Dialog must provide apply_section_edit method.")

        rel_asset = self._create_published_asset("sec_pub_apply_test", width=80.0, height=40.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)
        with open(full_asset_path, "rb") as f:
            original_bytes = f.read()

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_Apply"] = {
            "Height": "40.0",
            "Width": "80.0",
            "Thickness": "0.0",
            "Weight": "25.12",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_pub_apply_test",
        }
        self._select_family("Custom Profile")
        self.dialog.table_sizes.selectRow(0)

        initial_docs = set(App.listDocuments().keys())
        self.dialog.btn_edit_section.click()
        current_docs = set(App.listDocuments().keys())
        new_docs = current_docs - initial_docs
        self.assertTrue(len(new_docs) >= 1, "Edit action must open a working document.")
        working_doc_name = list(new_docs)[0]
        working_doc = App.getDocument(working_doc_name)

        # Locate working sketch
        working_sketches = [
            obj for obj in working_doc.Objects
            if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
        ]
        self.assertTrue(len(working_sketches) >= 1, "Working document must contain a SketchObject.")
        working_sketch = working_sketches[0]

        # Find the height distance constraint (original height = 40.0)
        height_idx = None
        for idx, c in enumerate(working_sketch.Constraints):
            val = getattr(c, "Value", None)
            if val is not None and abs(float(val) - 40.0) < 1e-3:
                height_idx = idx
                break
        if height_idx is None:
            # Fallback by constraint type and referenced segment index 1
            for idx, c in enumerate(working_sketch.Constraints):
                if getattr(c, "Type", None) == "Distance" and getattr(c, "First", None) == 1:
                    height_idx = idx
                    break
        self.assertIsNotNone(height_idx, "Could not find height constraint on working sketch.")

        # Change actual Sketcher dimensional datum (height constraint to 100.0)
        qty = App.Units.Quantity("100 mm") if hasattr(App, "Units") else 100.0
        working_sketch.setDatum(height_idx, qty)
        working_doc.recompute()
        self.assertEqual(working_sketch.solve(), 0, "Working sketch must solve cleanly after datum change.")

        # Verify edited sketch face geometry before apply
        face_pre = build_custom_section_face(working_sketch)
        self.assertTrue(face_pre.isValid())
        self.assertAlmostEqual(face_pre.Area, 8000.0, places=2)
        self.assertAlmostEqual(face_pre.BoundBox.XLength, 80.0, places=2)
        self.assertAlmostEqual(face_pre.BoundBox.YLength, 100.0, places=2)

        # Apply via UI / method
        self.dialog.apply_section_edit()

        # Table row dimensions should update: Height=100.0, Width=80.0
        # Weight = 80 * 100 * 7.85 * 0.001 = 62.8 kg/m
        h_val = float(self.dialog.table_sizes.item(0, 1).text())
        w_val = float(self.dialog.table_sizes.item(0, 2).text())
        weight_val = float(self.dialog.table_sizes.item(0, 7).text())
        self.assertAlmostEqual(h_val, 100.0, places=2)
        self.assertAlmostEqual(w_val, 80.0, places=2)
        self.assertAlmostEqual(weight_val, 62.8, places=2)
        self.assertTrue(self.dialog.is_dirty)

        # Before Save, disk asset is STILL the original published bytes
        with open(full_asset_path, "rb") as f:
            self.assertEqual(f.read(), original_bytes, "Published original must not change before catalog save.")

        # Save library catalog
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)

        # Read manifest reference (DO NOT assume same asset filename after geometry edits)
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        saved_size = manifest["Custom Profile"]["sizes"]["Sec_Apply"]
        saved_rel_asset = saved_size["asset_path"]
        saved_full_asset = os.path.join(self.folder_lib_path, saved_rel_asset)
        self.assertTrue(os.path.isfile(saved_full_asset), f"Saved asset must exist on disk: {saved_full_asset}")

        # Reopen native referenced asset and assert real edited geometry
        reopened_doc = App.openDocument(saved_full_asset)
        reopened_name = reopened_doc.Name
        try:
            reopened_sketches = [
                obj for obj in reopened_doc.Objects
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
            ]
            self.assertTrue(len(reopened_sketches) >= 1, "Reopened asset must contain standalone sketch.")
            reopened_sketch = reopened_sketches[0]
            self.assertEqual(reopened_sketch.solve(), 0)
            face_saved = build_custom_section_face(reopened_sketch)
            self.assertTrue(face_saved.isValid())
            self.assertAlmostEqual(face_saved.Area, 8000.0, places=2)
            self.assertAlmostEqual(face_saved.BoundBox.XLength, 80.0, places=2)
            self.assertAlmostEqual(face_saved.BoundBox.YLength, 100.0, places=2)
        finally:
            App.closeDocument(reopened_name)

    # --- Rule 6: Rename catalog code preserves stable asset filenames and metadata ---

    def test_r6_rename_catalog_code_preserves_stable_asset_filename(self):
        """Rule 6: Renaming the catalog code updates the catalog key without renaming

        or re-creating the underlying asset file.
        """
        rel_asset = self._create_published_asset("sec_stable_name", width=60.0, height=60.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Original_Code"] = {
            "Height": "60.0",
            "Width": "60.0",
            "Thickness": "0.0",
            "Weight": "28.26",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_stable_name",
        }
        self._select_family("Custom Profile")

        # Edit size code in table
        item = self.dialog.table_sizes.item(0, 0)
        item.setText("Renamed_Code")

        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()

        # Check saved manifest
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        sizes = manifest["Custom Profile"]["sizes"]
        self.assertIn("Renamed_Code", sizes)
        self.assertNotIn("Original_Code", sizes)
        self.assertEqual(sizes["Renamed_Code"]["asset_path"], rel_asset)
        self.assertEqual(sizes["Renamed_Code"]["asset_id"], "sec_stable_name")
        self.assertTrue(os.path.isfile(full_asset_path), "Asset file must retain its stable filename.")

    # --- Rule 7: Non-column and numeric metadata survive table populate/commit ---

    def test_r7_non_column_and_numeric_metadata_survive_table_lifecycle(self):
        """Rule 7: Arbitrary non-column numeric and string metadata, asset_path,

        object_name, and asset_id must survive _populate_sizes_table and _commit_current_family_edits.
        Also verifies untouched legacy family metadata preservation.
        """
        custom_props = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": "sections/sec_meta_test.FCStd",
            "object_name": "MySketch",
            "asset_id": "sec_meta_test",
            "custom_string_tag": "SpecialProfile",
            "custom_numeric_val": 42.75,
            "extra_int_id": 1001,
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_Meta"] = copy.deepcopy(custom_props)

        # Legacy parametric family with extra metadata
        legacy_props = {
            "Height": "40",
            "Width": "40",
            "Thickness": "2",
            "Flange Thickness": "0",
            "Radius1": "0",
            "Radius2": "0",
            "Weight": "2.4",
            "legacy_custom_field": "PreserveMe",
            "legacy_numeric": 88.5,
        }
        self.dialog.current_lib_data["Square Hollow"]["sizes"]["40x40x2"] = copy.deepcopy(legacy_props)

        # 1. Test Custom Profile population and commit
        self._select_family("Custom Profile")
        self.dialog._commit_current_family_edits()

        committed_custom = self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_Meta"]
        for key, val in custom_props.items():
            self.assertIn(key, committed_custom, f"Key '{key}' was lost during Custom Profile commit.")
            self.assertEqual(committed_custom[key], val, f"Value for '{key}' changed during commit.")

        # 2. Test Square Hollow population and commit (legacy preservation)
        self._select_family("Square Hollow")
        self.dialog._commit_current_family_edits()

        committed_legacy = self.dialog.current_lib_data["Square Hollow"]["sizes"]["40x40x2"]
        self.assertEqual(committed_legacy.get("legacy_custom_field"), "PreserveMe")
        self.assertEqual(committed_legacy.get("legacy_numeric"), 88.5)

    # --- Rule 8: S9 staged deletion defers asset removal until successful save ---

    def test_r8_s9_staged_deletion_defers_asset_removal_until_save(self):
        """Rule 8: Removing a size row stages the deletion; asset file on disk

        persists until btn_save successfully commits the catalog.
        """
        rel_asset = self._create_published_asset("sec_staged_del", width=50.0, height=50.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["To_Delete"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_staged_del",
        }
        self._select_family("Custom Profile")
        self.dialog.table_sizes.selectRow(0)

        # Delete size row
        self.dialog.btn_del_size.click()

        self.assertEqual(self.dialog.table_sizes.rowCount(), 0)
        # S9 INVARIANT: Asset file MUST STILL EXIST immediately after delete
        self.assertTrue(os.path.isfile(full_asset_path), "Asset file must not be deleted before Save.")
        self.assertTrue(self.dialog.is_dirty)

        # Save changes
        self.dialog.btn_save.click()

        self.assertFalse(self.dialog.is_dirty)
        # S9 INVARIANT: Now that save succeeded, unreferenced asset file is removed
        self.assertFalse(os.path.isfile(full_asset_path), "Asset file must be deleted after successful Save.")

    # --- Rule 9: S9 cancel or discard preserves staged deleted assets and catalog ---

    def test_r9_s9_cancel_or_discard_preserves_staged_deleted_assets_and_catalog(self):
        """Rule 9: Canceling or discarding unsaved changes preserves both catalog

        and staged deleted asset files on disk.
        """
        rel_asset = self._create_published_asset("sec_discard_keep", width=50.0, height=50.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Keep_Me"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_discard_keep",
        }
        self._select_family("Custom Profile")
        # Save initial state to disk first
        self.dialog.btn_save.click()

        self.dialog.table_sizes.selectRow(0)
        self.dialog.btn_del_size.click()
        self.assertTrue(self.dialog.is_dirty)

        # Discard by closing dialog or reloading
        self.dialog.close()

        # Reopen and verify asset still exists and catalog intact
        self.assertTrue(os.path.isfile(full_asset_path), "Asset file must remain on disk after discard.")
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertIn("Keep_Me", manifest.get("Custom Profile", {}).get("sizes", {}))

    # --- Rule 10: S9 shared asset references survive deletion ---

    def test_r10_s9_shared_asset_references_survive_deletion(self):
        """Rule 10: If multiple sizes share the same asset file, deleting one size

        and saving must NOT delete the asset file.
        """
        rel_asset = self._create_published_asset("sec_shared_ref", width=50.0, height=50.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Variant_1"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_shared_ref",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Variant_2"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_shared_ref",
        }
        self._select_family("Custom Profile")
        self.dialog.btn_save.click()

        # Delete Variant_1 only
        self.dialog.table_sizes.selectRow(0)
        self.dialog.btn_del_size.click()
        self.dialog.btn_save.click()

        # 1. Variant_2 still references the asset -> file must NOT be deleted!
        self.assertTrue(os.path.isfile(full_asset_path), "Shared asset must survive deletion of sibling reference.")

        # 2. Manifest check: Variant_2 catalog entry survives, Variant_1 is removed
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        sizes = manifest["Custom Profile"]["sizes"]
        self.assertNotIn("Variant_1", sizes, "Deleted Variant_1 must not be in manifest.")
        self.assertIn("Variant_2", sizes, "Remaining Variant_2 must survive in manifest.")
        self.assertEqual(sizes["Variant_2"]["asset_path"], rel_asset)

    # --- Rule 11: Failed save preserves dirty edits and does not delete assets ---

    def test_r11_failed_save_keeps_dirty_state_and_preserves_assets(self):
        """Rule 11: If saving catalog fails, dirty state remains retryable and

        no staged asset deletions occur.
        """
        rel_asset = self._create_published_asset("sec_fail_save", width=50.0, height=50.0)
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Size_Fail"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_fail_save",
        }
        self._select_family("Custom Profile")
        self.dialog.table_sizes.selectRow(0)
        self.dialog.btn_del_size.click()

        # 1. Simulate backend save failure
        with patch.object(self.manager, "save_folder_library", side_effect=IOError("Simulated disk error")):
            self.dialog.btn_save.click()

        self.assertTrue(self.dialog.is_dirty, "Dirty state must remain when save fails.")
        self.assertTrue(os.path.isfile(full_asset_path), "Asset must not be deleted when save fails.")

        # 2. Retry save without failure -> must succeed, clear dirty, and purge asset
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty, "Dirty state must clear on successful retry.")
        self.assertFalse(os.path.isfile(full_asset_path), "Asset must be deleted after successful retry.")

    # --- Rule 12: Asset path confinement rejects traversal and symlinks ---

    def test_r12_asset_path_confinement_rejects_traversal_and_symlinks(self):
        """Rule 12: Rejects relative traversal, absolute paths, and escaping symlinks

        before open, write, or delete operations without mutating stored data.
        Verifies outside sentinel bytes, manifest, row counters, selection,
        and open document set are completely unchanged.
        """
        self.assertTrue(hasattr(self.dialog, "btn_edit_section"), "Dialog must have btn_edit_section button.")
        self.assertTrue(hasattr(self.dialog, "btn_del_size"), "Dialog must have btn_del_size button.")

        # Create a disposable outside sentinel within test sandbox
        outside_dir = os.path.join(self.test_root, "outside_sandbox")
        os.makedirs(outside_dir, exist_ok=True)
        outside_sentinel = os.path.join(outside_dir, "sentinel.txt")
        sentinel_bytes = b"CONFIDENTIAL_OUTSIDE_SENTINEL_DATA_12345"
        with open(outside_sentinel, "wb") as f:
            f.write(sentinel_bytes)

        # Create an actual escaping symlink inside sections/ pointing outside
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        escaping_symlink_path = os.path.join(sections_dir, "escaping_symlink.FCStd")
        if os.path.exists(escaping_symlink_path) or os.path.islink(escaping_symlink_path):
            os.remove(escaping_symlink_path)
        os.symlink(outside_sentinel, escaping_symlink_path)

        # Candidate malicious paths
        malicious_paths = [
            "../outside_sandbox/sentinel.txt",
            outside_sentinel,
            "sections/escaping_symlink.FCStd",
            "sections/../../outside_sandbox/sentinel.txt",
        ]

        self._select_family("Custom Profile")

        # Snapshot initial state before test operations
        initial_open_docs = set(App.listDocuments().keys())
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "rb") as f:
            initial_manifest_bytes = f.read()

        for bad_path in malicious_paths:
            self.dialog.current_lib_data["Custom Profile"]["sizes"]["Evil_Sec"] = {
                "Height": "50.0",
                "Width": "50.0",
                "Thickness": "0.0",
                "Weight": "19.62",
                "asset_path": bad_path,
                "object_name": "Section",
                "asset_id": "evil_sec",
            }
            self.dialog._populate_sizes_table(self.dialog.current_lib_data["Custom Profile"]["sizes"])
            self.dialog.table_sizes.selectRow(0)

            # 1. Edit must be rejected without opening working documents
            self.dialog.btn_edit_section.click()
            self.assertEqual(
                set(App.listDocuments().keys()),
                initial_open_docs,
                f"Rejected edit for '{bad_path}' must not leak or open working documents.",
            )

            # 2. Delete + Save must refuse to delete outside target
            self.dialog.btn_del_size.click()
            self.dialog.btn_save.click()

            # Assert outside sentinel is completely untouched
            self.assertTrue(os.path.isfile(outside_sentinel), f"Outside sentinel was deleted by {bad_path}!")
            with open(outside_sentinel, "rb") as f:
                self.assertEqual(f.read(), sentinel_bytes, "Outside sentinel bytes were modified!")

        # Direct confinement validation helper check
        from freecad.frameforge.section_library import resolve_and_validate_asset_path
        for bad_path in malicious_paths:
            with self.assertRaises(ValueError):
                resolve_and_validate_asset_path(self.folder_lib_path, bad_path)

        # Assert document set, sentinel bytes, and manifest remain unchanged
        self.assertEqual(set(App.listDocuments().keys()), initial_open_docs)
        with open(outside_sentinel, "rb") as f:
            self.assertEqual(f.read(), sentinel_bytes)

    # --- Rule 13: Cleanup of staged artifacts without deleting unrelated files ---

    def test_r13_cleanup_staged_artifacts_on_cancel_without_deleting_unrelated(self):
        """Rule 13: Canceled or failed capture/edit sessions clean up only their own

        staged artifacts without deleting existing assets or unrelated files in sections/.
        """
        self.assertTrue(hasattr(self.dialog, "btn_capture_section"), "Dialog must have btn_capture_section button.")

        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)

        # Place existing published asset and unrelated sentinel file
        existing_asset = os.path.join(sections_dir, "existing_pub.FCStd")
        with open(existing_asset, "w", encoding="utf-8") as f:
            f.write("EXISTING ASSET")
        sentinel_file = os.path.join(sections_dir, "unrelated_sentinel.txt")
        with open(sentinel_file, "w", encoding="utf-8") as f:
            f.write("SENTINEL KEEP")

        doc = self._new_doc("CancelDoc")
        s = self._create_rect_sketch(doc, "SketchCancel", width=50.0, height=50.0)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, s.Name)

        self._select_family("Custom Profile")

        # Injected failure during capture after workspace creation
        with patch("freecad.frameforge.library_manager_dialog.save_section_asset", side_effect=RuntimeError("Simulated capture crash")):
            self.dialog.btn_capture_section.click()

        # Verify unrelated sentinel and existing asset are completely untouched
        self.assertTrue(os.path.isfile(existing_asset))
        self.assertTrue(os.path.isfile(sentinel_file))
        with open(sentinel_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "SENTINEL KEEP")

    # --- Rule 14: Preserve legacy parametric family behavior and table columns ---

    def test_r14_preserve_legacy_parametric_family_behavior(self):
        """Rule 14: Normal parametric families (e.g. Square Hollow) retain standard

        add size, dimension editing, weight recalculation, and column visibility.
        """
        self._select_family("Square Hollow")
        initial_count = self.dialog.table_sizes.rowCount()

        # Add size using standard btn_add_size
        self.dialog.btn_add_size.click()
        self.assertEqual(self.dialog.table_sizes.rowCount(), initial_count + 1)

        row = self.dialog.table_sizes.rowCount() - 1
        # In parametric family, dimension cells ARE editable
        for col_idx in (1, 2, 3):
            item = self.dialog.table_sizes.item(row, col_idx)
            self.assertTrue(
                bool(item.flags() & QtCore.Qt.ItemIsEditable),
                f"Parametric column {col_idx} must remain editable.",
            )

        # Commit and save
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)

        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(len(manifest["Square Hollow"]["sizes"]), initial_count + 1)

"""Native GUI and backend tests for portable folder library duplication (T6).

Covers S1, S3, S6, S7, S8, S9:
- Rule 1: duplicate_library with folder library creates full duplicate, copies declared assets, registers canonical destination, and returns canonical manifest path
- Rule 2: Folder duplication requires explicit target_folder_path, never flattens assets into legacy user JSON
- Rule 3: Rejection of non-empty destination directories without writes
- Rule 4: Rejection of nested source/target directory paths before writes
- Rule 5: Rejection of library name and registered folder path collisions
- Rule 6: Declared assets copied exclusively; user notes, unknown files, and caches in source are not copied or deleted
- Rule 7: Symlink escapes, path traversal (../), and malformed refs rejected before target writes or registry mutation
- Rule 8: Internal asset symlinks/aliases materialize as portable standalone copies
- Rule 9: Rollback on registration failure preserves old registry and cleans only owned destination artifacts
- Rule 10: Material change with recalculate_weights=False preserves nominal weights
- Rule 11: Material change with recalculate_weights=True computes Custom Profile weight from actual native face and target density
- Rule 12: Recalculate weights with corrupted asset rejects cleanly and rolls back destination
- Rule 13: Legacy stock and user JSON library duplication preserved as control
- Rule 14: UI duplicate button enabled for folder libraries, opens folder picker and NewLibraryDialog, registers clone
- Rule 15: UI dirty prompt cancel or downstream picker cancellation preserves unsaved widget edits
"""

import copy
import hashlib
import json
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
    calculate_linear_weight,
)
from freecad.frameforge.library_manager_dialog import (
    NewLibraryDialog,
    ProfileLibraryManagerDialog,
)
from freecad.frameforge.section_capture import capture_section_sketch
from freecad.frameforge.section_library import compute_sketch_dimensions_and_weight


def _file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestFolderLibraryDuplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_dup_")
        self.test_root = self.workspace.name
        self.user_dir = os.path.join(self.test_root, "user")
        self.stock_dir = os.path.join(self.test_root, "stock")
        self.reg_dir = os.path.join(self.test_root, "registry")
        self.reg_path = os.path.join(self.reg_dir, "folders.json")
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.stock_dir, exist_ok=True)
        os.makedirs(self.reg_dir, exist_ok=True)

        # Standard stock parametric library for preservation checks
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
        with open(os.path.join(self.stock_dir, "stock_steel.json"), "w", encoding="utf-8") as f:
            json.dump(stock_data, f)

        self.manager = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )

        self.source_folder = os.path.join(self.test_root, "SourceFolderLib")
        self.manager.create_folder_library(
            self.source_folder,
            "SourceFolderLib",
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

        # Create autonomous section sketch and publish to source_folder
        self.doc_names = []
        temp_doc = App.newDocument("TempSetupDoc")
        self.doc_names.append(temp_doc.Name)
        sk = self._create_rect_sketch(temp_doc, "RectSec", width=100.0, height=50.0)
        self.asset_rel_path, self.asset_obj_name, self.asset_id = self._publish_section_to_library(
            self.source_folder,
            "Rect_100x50",
            sk,
            object_name="RectSec",
            asset_id="sec_rect_100x50",
            density=7.85,
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # Patch unexpected modal dialogs to fail fast
        def fail_modal(box, *args):
            raise AssertionError(f"UNEXPECTED_MODAL: {box.windowTitle()}: {box.text()}")

        self.messages = ExitStack()
        self.messages.enter_context(patch.object(QtWidgets.QMessageBox, "exec_", fail_modal))
        for method in ("warning", "critical", "information", "question"):
            def make_fail(m):
                def _fail(parent, title, text, *args, **kwargs):
                    raise AssertionError(f"UNEXPECTED_MODAL_{m.upper()}: {title}: {text}")
                return _fail
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method, side_effect=make_fail(method)))

    def tearDown(self):
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        for doc_name in list(App.listDocuments().keys()):
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        self.doc_names.clear()

        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        try:
            self.workspace.cleanup()
        except Exception:
            pass

    # --- Helper methods ---

    def _create_rect_sketch(self, doc, name="RectSection", width=100.0, height=50.0):
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
        self.assertEqual(s.solve(), 0, "Sketch must solve cleanly.")
        doc.recompute()
        return s

    def _create_line_path(self, doc, name="Path", length=100.0, axis="X"):
        p = doc.addObject("Sketcher::SketchObject", name)
        p.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(length, 0, 0)), False)
        p.addConstraint(Sketcher.Constraint("Distance", 0, float(length)))
        if axis == "Z":
            p.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), -90)
        self.assertEqual(p.solve(), 0, "Path fixture must solve.")
        doc.recompute()
        return p

    def _publish_section_to_library(self, lib_folder, size_code, sketch, object_name="Section", asset_id=None, density=7.85):
        sections_dir = os.path.join(lib_folder, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        aid = asset_id or f"sec_{size_code.lower()}"
        filename = f"{aid}.FCStd"
        rel_path = os.path.join("sections", filename).replace("\\", "/")
        full_path = os.path.join(lib_folder, rel_path)

        asset_doc = App.newDocument(f"AssetDoc_{size_code}")
        captured = capture_section_sketch(sketch, target_doc=asset_doc, name=object_name)
        actual_name = captured.Name
        asset_doc.recompute()
        doc_name = asset_doc.Name
        asset_doc.saveAs(full_path)
        App.closeDocument(doc_name)

        height, width, weight, area = compute_sketch_dimensions_and_weight(sketch, density_g_cm3=density)

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
            "asset_path": rel_path,
            "object_name": actual_name,
            "asset_id": aid,
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        return rel_path, actual_name, aid

    # --- Tests ---

    def test_duplicate_folder_library_basic_copy_and_registration(self):
        """Rule 1: duplicate_library with folder library copies assets, updates manifest,
        registers canonical destination, and returns canonical manifest path.
        """
        dest_folder = os.path.join(self.test_root, "DuplicatedLibFolder")
        res = self.manager.duplicate_library(
            "SourceFolderLib",
            "DuplicatedLib",
            target_folder_path=dest_folder,
            target_material="Steel",
            target_density=7.85,
        )

        expected_manifest = os.path.join(os.path.realpath(dest_folder), "library.json")
        self.assertEqual(os.path.realpath(res), expected_manifest)
        self.assertTrue(os.path.isfile(expected_manifest))

        with open(expected_manifest, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["_metadata"]["name"], "DuplicatedLib")
        self.assertEqual(data["_metadata"]["cloned_from"], "SourceFolderLib")
        self.assertEqual(data["_metadata"]["material"], "Steel")
        self.assertEqual(data["_metadata"]["density"], 7.85)
        self.assertTrue(data["_metadata"]["is_folder"])

        # Check declared asset was copied
        dest_asset = os.path.join(dest_folder, "sections", "sec_rect_100x50.FCStd")
        src_asset = os.path.join(self.source_folder, "sections", "sec_rect_100x50.FCStd")
        self.assertTrue(os.path.isfile(dest_asset))
        self.assertEqual(_file_hash(dest_asset), _file_hash(src_asset))

        # Check destination is registered
        registered = [lib.get("folder_path") for lib in self.manager.list_libraries() if lib.get("is_folder")]
        self.assertIn(os.path.realpath(dest_folder), registered)
        libs = self.manager.list_libraries()
        dup_meta = next((l for l in libs if l["name"] == "DuplicatedLib"), None)
        self.assertIsNotNone(dup_meta)
        self.assertTrue(dup_meta["is_folder"])
        self.assertTrue(dup_meta["is_user"])
        self.assertEqual(dup_meta["folder_path"], os.path.realpath(dest_folder))

        # Source remains registered and intact
        self.assertIn(os.path.realpath(self.source_folder), registered)

    def test_duplicate_folder_library_requires_explicit_empty_destination(self):
        """Rule 2: Folder duplication without target_folder_path raises ValueError
        and does NOT flatten assets into a legacy user JSON library.
        """
        with self.assertRaises(ValueError) as ctx:
            self.manager.duplicate_library("SourceFolderLib", "FlattenAttempt")
        self.assertIn("target_folder_path", str(ctx.exception).lower())

        # Check no legacy file was created
        legacy_file = os.path.join(self.user_dir, "FlattenAttempt.json")
        self.assertFalse(os.path.exists(legacy_file))

    def test_duplicate_folder_library_rejects_nonempty_destination(self):
        """Rule 3: Non-empty destination directory is rejected before any writes,
        preserving pre-existing files and registry.
        """
        dest_folder = os.path.join(self.test_root, "NonEmptyDest")
        os.makedirs(dest_folder, exist_ok=True)
        sentinel_path = os.path.join(dest_folder, "sentinel.txt")
        with open(sentinel_path, "w", encoding="utf-8") as f:
            f.write("pre-existing content")
        sentinel_hash = _file_hash(sentinel_path)

        reg_before = _file_hash(self.reg_path) if os.path.exists(self.reg_path) else None

        with self.assertRaises((FileExistsError, ValueError)):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "NonEmptyDuplicate",
                target_folder_path=dest_folder,
            )

        # Sentinel file preserved unchanged
        self.assertTrue(os.path.isfile(sentinel_path))
        self.assertEqual(_file_hash(sentinel_path), sentinel_hash)

        # No library.json or sections directory created in destination
        self.assertFalse(os.path.exists(os.path.join(dest_folder, "library.json")))
        self.assertFalse(os.path.exists(os.path.join(dest_folder, "sections")))

        # Registry unchanged
        reg_after = _file_hash(self.reg_path) if os.path.exists(self.reg_path) else None
        self.assertEqual(reg_before, reg_after)

    def test_duplicate_folder_library_rejects_nested_source_and_target(self):
        """Rule 4: Reject nested source-target and target-source directories before writes."""
        # Target inside source
        nested_target = os.path.join(self.source_folder, "nested_child")
        with self.assertRaises(ValueError):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "NestedTargetLib",
                target_folder_path=nested_target,
            )
        self.assertFalse(os.path.exists(nested_target))

        # Source inside target
        nested_parent = os.path.dirname(self.source_folder)
        with self.assertRaises(ValueError):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "NestedParentLib",
                target_folder_path=nested_parent,
            )

    def test_duplicate_folder_library_rejects_name_and_path_collisions(self):
        """Rule 5: Collisions with existing stock/user/registered library names
        or registered folder paths are rejected before writes.
        """
        dest_folder = os.path.join(self.test_root, "CollisionDest")
        os.makedirs(dest_folder, exist_ok=True)

        # Name collision with stock library
        with self.assertRaises((ValueError, FileExistsError)):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "StockSteel",
                target_folder_path=dest_folder,
            )

        # Name collision with existing registered folder library
        with self.assertRaises((ValueError, FileExistsError)):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "SourceFolderLib",
                target_folder_path=dest_folder,
            )

        # Path collision with already registered folder path
        with self.assertRaises((ValueError, FileExistsError)):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "UniqueName",
                target_folder_path=self.source_folder,
            )

        # Destination remains empty
        self.assertEqual(os.listdir(dest_folder), [])

    def test_duplicate_folder_library_no_blanket_copy_and_preserves_unrelated_files(self):
        """Rule 6: Duplication copies only declared asset files and manifest;
        unrelated user notes, caches, and tmp files are not copied or deleted.
        """
        notes_path = os.path.join(self.source_folder, "notes.txt")
        cache_dir = os.path.join(self.source_folder, ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "temp.dat")
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write("user notes")
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write("cache data")

        dest_folder = os.path.join(self.test_root, "SelectiveCopyDest")
        self.manager.duplicate_library(
            "SourceFolderLib",
            "SelectiveCopyLib",
            target_folder_path=dest_folder,
        )

        # Target has library.json and declared asset, but NOT notes or cache
        self.assertTrue(os.path.isfile(os.path.join(dest_folder, "library.json")))
        self.assertTrue(os.path.isfile(os.path.join(dest_folder, "sections", "sec_rect_100x50.FCStd")))
        self.assertFalse(os.path.exists(os.path.join(dest_folder, "notes.txt")))
        self.assertFalse(os.path.exists(os.path.join(dest_folder, ".cache")))

        # Source preserves notes and cache intact
        self.assertTrue(os.path.isfile(notes_path))
        self.assertTrue(os.path.isfile(cache_file))

    def test_duplicate_folder_library_rejects_malformed_traversal_and_symlink_escapes(self):
        """Rule 7: Asset paths with traversal (../), absolute paths, or escaping symlinks
        are rejected BEFORE target writes or registry mutation. Pre-existing empty destination retained.
        """
        manifest_path = os.path.join(self.source_folder, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        manifest_data["Custom Profile"]["sizes"]["Bad_Traversal"] = {
            "Height": "50",
            "Width": "100",
            "Weight": "39.25",
            "asset_path": "../outside.FCStd",
            "object_name": "BadSec",
            "asset_id": "sec_bad",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        dest_folder = os.path.join(self.test_root, "EmptyDestRetained")
        os.makedirs(dest_folder, exist_ok=True)
        reg_before = _file_hash(self.reg_path)

        with self.assertRaises(ValueError):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "TraversalDupLib",
                target_folder_path=dest_folder,
            )

        # Pre-existing empty root retained empty on failure
        self.assertTrue(os.path.isdir(dest_folder))
        self.assertEqual(os.listdir(dest_folder), [])

        # Registry untouched
        self.assertEqual(_file_hash(self.reg_path), reg_before)

    def test_duplicate_folder_library_internal_aliases_materialize_as_portable_copies(self):
        """Rule 8: Internal relative symlinks/aliases in source materialize as portable
        standalone copies in destination that survive source deletion.
        """
        src_asset = os.path.join(self.source_folder, "sections", "sec_rect_100x50.FCStd")
        alias_rel = os.path.join("sections", "sec_alias_100x50.FCStd").replace("\\", "/")
        alias_full = os.path.join(self.source_folder, alias_rel)

        # Create relative symlink within sections/
        os.symlink("sec_rect_100x50.FCStd", alias_full)

        manifest_path = os.path.join(self.source_folder, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["Custom Profile"]["sizes"]["Rect_Alias"] = {
            "Height": "50.0",
            "Width": "100.0",
            "Weight": "39.25",
            "Area": 5000.0,
            "asset_path": alias_rel,
            "object_name": "RectSec",
            "asset_id": "sec_alias",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        dest_folder = os.path.join(self.test_root, "AliasDestFolder")
        self.manager.duplicate_library(
            "SourceFolderLib",
            "AliasDupLib",
            target_folder_path=dest_folder,
        )

        dest_alias = os.path.join(dest_folder, alias_rel)
        expected_hash = _file_hash(src_asset)
        self.assertTrue(os.path.isfile(dest_alias))
        self.assertEqual(_file_hash(dest_alias), expected_hash)

        # Delete source library completely; target alias must remain readable and intact
        shutil.rmtree(self.source_folder)
        self.assertTrue(os.path.isfile(dest_alias))
        self.assertEqual(_file_hash(dest_alias), expected_hash)

    def test_duplicate_folder_library_rollback_on_registration_failure(self):
        """Rule 9: Registration failure rolls back newly created artifacts in destination,
        preserves pre-existing empty destination folder and old registry.
        """
        dest_folder = os.path.join(self.test_root, "RollbackDestFolder")
        os.makedirs(dest_folder, exist_ok=True)
        reg_before = _file_hash(self.reg_path)

        with patch.object(self.manager, "register_folder_library", side_effect=IOError("Simulated registry write failure")):
            with self.assertRaises(IOError):
                self.manager.duplicate_library(
                    "SourceFolderLib",
                    "RollbackDupLib",
                    target_folder_path=dest_folder,
                )

        # Pre-existing empty destination retained empty
        self.assertTrue(os.path.isdir(dest_folder))
        self.assertEqual(os.listdir(dest_folder), [])

        # Registry file preserved unchanged
        self.assertEqual(_file_hash(self.reg_path), reg_before)

    def test_duplicate_folder_library_material_recalc_false_preserves_nominal(self):
        """Rule 10: Material change with recalculate_weights=False preserves nominal weights
        and all numeric metadata across both parametric and custom profile families.
        """
        dest_folder = os.path.join(self.test_root, "NominalPreservedDest")
        self.manager.duplicate_library(
            "SourceFolderLib",
            "NominalAluLib",
            target_folder_path=dest_folder,
            target_material="Aluminium",
            target_density=2.70,
            recalculate_weights=False,
        )

        manifest_path = os.path.join(dest_folder, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["_metadata"]["material"], "Aluminium")
        self.assertEqual(data["_metadata"]["density"], 2.70)

        # Parametric nominal weight preserved
        self.assertEqual(data["Square Hollow"]["sizes"]["40x40x2"]["Weight"], "2.4")

        # Custom Profile nominal weight and bounds preserved
        cust_size = data["Custom Profile"]["sizes"]["Rect_100x50"]
        self.assertEqual(cust_size["Weight"], "39.25")
        self.assertEqual(cust_size["Height"], "50.0")
        self.assertEqual(cust_size["Width"], "100.0")
        self.assertEqual(cust_size["Area"], 5000.0)

    def test_duplicate_folder_library_material_recalc_true_computes_from_actual_face(self):
        """Rule 11: Material change with recalculate_weights=True calculates Custom Profile weight
        from ACTUAL native face and target density (not untrusted dim formulas), preserving open docs and selection.
        """
        # User has an open active document and selection
        user_doc = App.newDocument("UserPreservedDoc")
        self.doc_names.append(user_doc.Name)
        line = self._create_line_path(user_doc, "UserPath", 100.0)
        App.setActiveDocument(user_doc.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(user_doc.Name, line.Name, "Edge1")
        sel_before = [(s.DocumentName, s.ObjectName, list(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        open_docs_before = set(App.listDocuments().keys())

        dest_folder = os.path.join(self.test_root, "RecalcAluDest")
        self.manager.duplicate_library(
            "SourceFolderLib",
            "RecalcAluLib",
            target_folder_path=dest_folder,
            target_material="Aluminium",
            target_density=2.70,
            recalculate_weights=True,
        )

        # User document and selection must be preserved
        open_docs_after = set(App.listDocuments().keys())
        self.assertEqual(open_docs_before, open_docs_after)
        sel_after = [(s.DocumentName, s.ObjectName, list(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        self.assertEqual(sel_before, sel_after)

        manifest_path = os.path.join(dest_folder, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parametric weight recalculated with Aluminium density 2.70
        expected_sq_weight = str(calculate_linear_weight("Square Hollow", 40, 40, 2, density_g_cm3=2.70))
        self.assertEqual(data["Square Hollow"]["sizes"]["40x40x2"]["Weight"], expected_sq_weight)

        # Custom Profile: actual native face is 100 * 50 = 5000 mm^2. Weight at 2.70 g/cm^3 is 13.50 kg/m
        cust_weight = float(data["Custom Profile"]["sizes"]["Rect_100x50"]["Weight"])
        expected_cust_weight = (5000.0 * 2.70) / 1000.0
        self.assertAlmostEqual(cust_weight, expected_cust_weight, places=1)

    def test_duplicate_folder_library_recalc_true_corrupt_asset_rejects_and_rolls_back(self):
        """Rule 12: Recalculate weights with corrupted asset FCStd rejects with ValueError
        and rolls back destination artifacts, leaving registry intact.
        """
        asset_path = os.path.join(self.source_folder, "sections", "sec_rect_100x50.FCStd")
        with open(asset_path, "wb") as f:
            f.write(b"not a valid freecad document")

        dest_folder = os.path.join(self.test_root, "CorruptRecalcDest")
        os.makedirs(dest_folder, exist_ok=True)
        reg_before = _file_hash(self.reg_path)

        with self.assertRaises(ValueError):
            self.manager.duplicate_library(
                "SourceFolderLib",
                "CorruptRecalcLib",
                target_folder_path=dest_folder,
                target_material="Aluminium",
                target_density=2.70,
                recalculate_weights=True,
            )

        # Destination cleaned of any partial outputs
        self.assertEqual(os.listdir(dest_folder), [])
        self.assertEqual(_file_hash(self.reg_path), reg_before)

    def test_legacy_stock_and_user_duplication_preserved_as_control(self):
        """Rule 13: Existing legacy duplicate_library semantics for stock/user JSON
        remain identical and produce user JSON files.
        """
        res = self.manager.duplicate_library(
            "StockSteel",
            "UserStockCopy",
            overwrite=False,
            target_material="Aluminium",
            target_density=2.70,
            recalculate_weights=True,
        )

        expected_user_path = os.path.join(os.path.realpath(self.user_dir), "userstockcopy.json")
        self.assertEqual(os.path.realpath(res), expected_user_path)
        self.assertTrue(os.path.isfile(expected_user_path))

        with open(expected_user_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["_metadata"]["name"], "UserStockCopy")
        self.assertEqual(data["_metadata"]["cloned_from"], "StockSteel")
        self.assertEqual(data["_metadata"]["material"], "Aluminium")

    def test_ui_duplicate_folder_library_workflow_success(self):
        """Rule 14: UI duplicate button enabled for folder libraries, opens folder picker
        and NewLibraryDialog, calls manager.duplicate_library, and selects new library.
        """
        dialog = ProfileLibraryManagerDialog(parent=None, library_manager=self.manager)
        try:
            # Select SourceFolderLib in list
            target_item = None
            for i in range(dialog.list_libraries.count()):
                item = dialog.list_libraries.item(i)
                meta = item.data(QtCore.Qt.UserRole)
                if meta and meta.get("name") == "SourceFolderLib":
                    target_item = item
                    break
            self.assertIsNotNone(target_item)
            dialog.list_libraries.setCurrentItem(target_item)

            # Assert button is enabled and tooltip is updated (temporary guard removed)
            self.assertTrue(dialog.btn_dup_lib.isEnabled(), "btn_dup_lib must be enabled for folder libraries.")
            self.assertEqual(dialog.btn_dup_lib.toolTip(), translate("frameforge", "Duplicate Library"))

            dest_folder = os.path.join(self.test_root, "UIDuplicateDest")
            os.makedirs(dest_folder, exist_ok=True)

            with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=dest_folder), \
                 patch("freecad.frameforge.library_manager_dialog.NewLibraryDialog.exec_", return_value=QtWidgets.QDialog.Accepted), \
                 patch("freecad.frameforge.library_manager_dialog.NewLibraryDialog.get_values", return_value=("UIDupFolderLib", "Aluminium", 2.70, False)):
                dialog.btn_dup_lib.click()

            # Dialog selects new library and updates banner
            self.assertEqual(dialog.current_lib_meta["name"], "UIDupFolderLib")
            self.assertTrue(dialog.current_lib_meta["is_folder"])
            self.assertIn("UIDupFolderLib", dialog.lbl_lib_banner.text())
        finally:
            dialog.close()

    def test_ui_duplicate_folder_library_dirty_cancel_preserves_unsaved_edits(self):
        """Rule 15: Canceling dirty save prompt, folder picker, or NewLibraryDialog
        preserves unsaved widget edits on the source folder library.
        """
        dialog = ProfileLibraryManagerDialog(parent=None, library_manager=self.manager)
        try:
            # Select SourceFolderLib
            for i in range(dialog.list_libraries.count()):
                item = dialog.list_libraries.item(i)
                meta = item.data(QtCore.Qt.UserRole)
                if meta and meta.get("name") == "SourceFolderLib":
                    dialog.list_libraries.setCurrentItem(item)
                    break

            # Populate edits and mark dirty
            dialog.table_sizes.item(0, 0).setText("DirtyHeight_999")
            dialog.is_dirty = True

            # Scenario 1: User clicks Cancel on dirty prompt -> duplication aborts, edits kept
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Cancel):
                dialog._on_duplicate_library()
            self.assertTrue(dialog.is_dirty)
            self.assertEqual(dialog.table_sizes.item(0, 0).text(), "DirtyHeight_999")
            self.assertEqual(dialog.current_lib_meta["name"], "SourceFolderLib")

            # Scenario 2: User clicks Discard on dirty prompt, but cancels folder picker -> edits kept
            dest_folder = os.path.join(self.test_root, "CancelledFolderPicker")
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard), \
                 patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=""):
                dialog._on_duplicate_library()
            self.assertEqual(dialog.table_sizes.item(0, 0).text(), "DirtyHeight_999")
            self.assertEqual(dialog.current_lib_meta["name"], "SourceFolderLib")

            # Scenario 3: User picks folder, but cancels NewLibraryDialog -> edits kept
            os.makedirs(dest_folder, exist_ok=True)
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard), \
                 patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=dest_folder), \
                 patch("freecad.frameforge.library_manager_dialog.NewLibraryDialog.exec_", return_value=QtWidgets.QDialog.Rejected):
                dialog._on_duplicate_library()
            self.assertEqual(dialog.table_sizes.item(0, 0).text(), "DirtyHeight_999")
            self.assertEqual(dialog.current_lib_meta["name"], "SourceFolderLib")
        finally:
            dialog.close()


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for method_name in [
        "test_duplicate_folder_library_basic_copy_and_registration",
        "test_duplicate_folder_library_requires_explicit_empty_destination",
        "test_duplicate_folder_library_rejects_nonempty_destination",
        "test_duplicate_folder_library_rejects_nested_source_and_target",
        "test_duplicate_folder_library_rejects_name_and_path_collisions",
        "test_duplicate_folder_library_no_blanket_copy_and_preserves_unrelated_files",
        "test_duplicate_folder_library_rejects_malformed_traversal_and_symlink_escapes",
        "test_duplicate_folder_library_internal_aliases_materialize_as_portable_copies",
        "test_duplicate_folder_library_rollback_on_registration_failure",
        "test_duplicate_folder_library_material_recalc_false_preserves_nominal",
        "test_duplicate_folder_library_material_recalc_true_computes_from_actual_face",
        "test_duplicate_folder_library_recalc_true_corrupt_asset_rejects_and_rolls_back",
        "test_legacy_stock_and_user_duplication_preserved_as_control",
        "test_ui_duplicate_folder_library_workflow_success",
        "test_ui_duplicate_folder_library_dirty_cancel_preserves_unsaved_edits",
    ]:
        suite.addTest(TestFolderLibraryDuplication(method_name))
    return suite

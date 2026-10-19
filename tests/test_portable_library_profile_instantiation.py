"""Native GUI regression tests for portable library profile instantiation (T5).

Covers S1, S2, S3, S5, S8:
- Case 1: Catalog selection with geometry metadata, safe unit/norm defaults, read-only bounds, and disabled inapplicable controls
- Case 2: Native autonomous exact-object import with holes into target project document
- Case 3: Source sketch reuse across profile instances with BOM and PID grouping
- Case 4: Project save, library removal from isolated sandbox, and reopen/recompute valid geometry without library dependency
- Case 5: Library section edit does not mutate existing project sources; new asset UUID emitted
- Case 6: Path attachment, App::Part container placement, anchors, and mirror semantics
- Case 7: Reject transaction rollback preserves project document and user models
- Case 8: Asset path confinement and preservation of user-owned already-open documents without mutation
- Case 9: Preserve standard parametric chooser behavior and unknown-setting validation
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
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.custom_section_geometry import build_custom_section_face
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.profile import Profile, ViewProviderCustomProfile, ViewProviderProfile
from freecad.maxproframe.section_capture import capture_section_sketch, save_section_asset
from freecad.maxproframe.section_library import (
    SectionEditSession,
    compute_sketch_dimensions_and_weight,
    get_or_import_section_sketch,
    resolve_and_validate_asset_path,
)


class TestPortableLibraryProfileInstantiation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_inst_")
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

        # Primary registered folder library for custom sections
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

        self.doc_names = []
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        # Patch QMessageBox upfront so unexpected modal dialogs do not block offscreen execution
        self.messages = ExitStack()
        for method in ("warning", "critical", "information", "question"):
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method))

        # Patch LibraryManager in create_profiles_tool so panels use the isolated test manager
        self.mgr_patch = patch(
            "freecad.maxproframe.create_profiles_tool.LibraryManager",
            return_value=self.manager,
        )
        self.mgr_patch.start()

    def tearDown(self):
        # 1. Stop LibraryManager patch
        if hasattr(self, "mgr_patch"):
            try:
                self.mgr_patch.stop()
            except Exception:
                pass

        # 2. Clear Gui.Selection
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        # 3. Close ALL open FreeCAD documents safely (record doc.Name before native close)
        for doc_name in list(App.listDocuments().keys()):
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        self.doc_names.clear()

        # 4. Close message patches after dialogs and documents are safely closed
        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        # 5. Clean up isolated temporary workspace
        try:
            self.workspace.cleanup()
        except Exception:
            pass

    # --- Helper methods ---

    def _new_doc(self, name_prefix="TestDoc"):
        doc = App.newDocument(name_prefix)
        doc.UndoMode = 1
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

    def _create_hollow_rect_sketch(
        self, doc, name="HollowSection", outer_w=40.0, outer_h=40.0, inner_w=20.0, inner_h=20.0
    ):
        s = doc.addObject("Sketcher::SketchObject", name)
        # Outer wire
        opts = [(0, 0), (outer_w, 0), (outer_w, outer_h), (0, outer_h)]
        for i in range(4):
            a, b = opts[i], opts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        for i in [0, 2]:
            s.addConstraint(Sketcher.Constraint("Horizontal", i))
        for i in [1, 3]:
            s.addConstraint(Sketcher.Constraint("Vertical", i))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        s.addConstraint(Sketcher.Constraint("Distance", 0, float(outer_w)))
        s.addConstraint(Sketcher.Constraint("Distance", 1, float(outer_h)))

        # Inner hole wire
        ox = (outer_w - inner_w) / 2.0
        oy = (outer_h - inner_h) / 2.0
        ipts = [(ox, oy), (ox + inner_w, oy), (ox + inner_w, oy + inner_h), (ox, oy + inner_h)]
        for i in range(4):
            a, b = ipts[i], ipts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", 4 + i, 2, 4 + ((i + 1) % 4), 1))
        for i in [4, 6]:
            s.addConstraint(Sketcher.Constraint("Horizontal", i))
        for i in [5, 7]:
            s.addConstraint(Sketcher.Constraint("Vertical", i))
        s.addConstraint(Sketcher.Constraint("Distance", 4, float(inner_w)))
        s.addConstraint(Sketcher.Constraint("Distance", 5, float(inner_h)))
        doc.recompute()
        return s

    def _create_line_path(self, doc, name="Path", length=100.0, axis="X"):
        p = doc.addObject("Sketcher::SketchObject", name)
        # Sketcher geometry is local XY; orient the sketch, not an invalid out-of-plane edge.
        p.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(length, 0, 0)), False)
        p.addConstraint(Sketcher.Constraint("Distance", 0, float(length)))
        if axis == "Z":
            p.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), -90)
        self.assertEqual(p.solve(), 0, "Path fixture must solve before profile attachment.")
        doc.recompute()
        self.assertEqual(len(p.Shape.Edges), 1, "Path fixture must expose one valid edge.")
        return p

    def _publish_section_to_library(self, lib_folder, size_code, sketch, object_name="Section", asset_id=None):
        """Saves section sketch into library/sections and updates library.json manifest on disk."""
        sections_dir = os.path.join(lib_folder, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        aid = asset_id or f"sec_{size_code.lower()}"
        filename = f"{aid}.FCStd"
        rel_path = os.path.join("sections", filename)
        full_path = os.path.join(lib_folder, rel_path)

        # Save autonomous asset document
        asset_doc = App.newDocument(f"AssetDoc_{size_code}")
        captured = capture_section_sketch(sketch, target_doc=asset_doc, name=object_name)
        actual_name = captured.Name
        asset_doc.recompute()
        doc_name = asset_doc.Name
        asset_doc.saveAs(full_path)
        App.closeDocument(doc_name)

        height, width, weight, area = compute_sketch_dimensions_and_weight(sketch, density_g_cm3=7.85)

        # Hydrate public manifest on disk
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

    # --- Case 1: Catalog selection with metadata, safe defaults, read-only bounds ---

    def test_catalog_selection_with_metadata_and_safe_defaults(self):
        """Case 1: Folder Custom Profile sizes load without 'Setting Unkown' error;

        geometry metadata (asset_path, object_name, asset_id, Area) is filtered;
        safe unit/norm defaults are assigned; bounds are displayed read-only;
        and inapplicable dimensional/fillet controls are disabled.
        """
        temp_doc = self._new_doc("TempDoc")
        sk = self._create_rect_sketch(temp_doc, "MyRect", width=120.0, height=60.0)
        self._publish_section_to_library(
            self.folder_lib_path,
            "Custom_120x60",
            sk,
            object_name="RectSection",
            asset_id="sec_120x60",
        )
        temp_doc_name = temp_doc.Name
        App.closeDocument(temp_doc_name)
        if temp_doc_name in self.doc_names:
            self.doc_names.remove(temp_doc_name)

        project_doc = self._new_doc("ProjectDoc")
        App.setActiveDocument(project_doc.Name)

        panel = CreateProfileTaskPanel()
        panel.initialize_ui()
        for f in panel.form:
            f.show()

        # Select folder library, Custom Profile, and the published size
        mat_idx = panel.form_proxy.combo_material.findText("CustomFolderLib")
        self.assertGreaterEqual(mat_idx, 0, "CustomFolderLib must be present in combo_material.")
        panel.form_proxy.combo_material.setCurrentIndex(mat_idx)

        fam_idx = panel.form_proxy.combo_family.findText("Custom Profile")
        self.assertGreaterEqual(fam_idx, 0, "Custom Profile must be present in combo_family.")
        panel.form_proxy.combo_family.setCurrentIndex(fam_idx)

        size_idx = panel.form_proxy.combo_size.findText("Custom_120x60")
        self.assertGreaterEqual(size_idx, 0, "Custom_120x60 must be present in combo_size.")
        panel.form_proxy.combo_size.setCurrentIndex(size_idx)

        # Safe defaults check
        norm_text = panel.form_proxy.label_norm.text().strip()
        unit_text = panel.form_proxy.label_unit.text().strip()
        self.assertTrue(len(norm_text) > 0, "Norm label must have safe default text, not empty.")
        self.assertTrue(len(unit_text) > 0, "Unit label must have safe default text, not empty.")

        # Bounds values populated
        self.assertAlmostEqual(panel.form_proxy.sb_width.value(), 120.0, places=2)
        self.assertAlmostEqual(panel.form_proxy.sb_height.value(), 60.0, places=2)
        expected_weight = 120.0 * 60.0 * 7.85 * 0.001
        self.assertAlmostEqual(panel.form_proxy.sb_weight.value(), expected_weight, places=2)

        # Bounds are read-only (disabled for direct editing)
        self.assertFalse(
            panel.form_proxy.sb_width.isEnabled(), "sb_width must be disabled/read-only for custom sections."
        )
        self.assertFalse(
            panel.form_proxy.sb_height.isEnabled(), "sb_height must be disabled/read-only for custom sections."
        )

        # Inapplicable dimensional and fillet controls are disabled
        self.assertFalse(
            panel.form_proxy.sb_main_thickness.isEnabled(), "Thickness must be disabled for custom sections."
        )
        self.assertFalse(panel.form_proxy.sb_flange_thickness.isEnabled(), "Flange Thickness must be disabled.")
        self.assertFalse(panel.form_proxy.sb_radius1.isEnabled(), "Radius1 must be disabled.")
        self.assertFalse(panel.form_proxy.sb_radius2.isEnabled(), "Radius2 must be disabled.")
        self.assertFalse(panel.form_proxy.cb_make_fillet.isEnabled(), "cb_make_fillet must be disabled.")
        self.assertFalse(panel.form_proxy.cb_make_fillet.isChecked(), "cb_make_fillet must be unchecked.")
        if hasattr(panel.form_proxy, "sb_lip_length"):
            self.assertFalse(panel.form_proxy.sb_lip_length.isEnabled(), "Lip Length must be disabled.")

    # --- Case 2: Native autonomous exact-object import with holes ---

    def test_native_autonomous_exact_object_import_with_holes(self):
        """Case 2: Imports EXACT object_name from safely confined native asset;

        never chooses first arbitrary sketch; imported sketch is autonomous and solves cleanly;
        profile volume reflects hollow cross-section geometry.
        """
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        raw_asset_path = os.path.join(sections_dir, "sec_multi_sketch.FCStd")

        # Build asset doc containing two sketches: a dummy first sketch and the target hollow sketch
        asset_build_doc = self._new_doc("AssetBuildDoc")
        _ = self._create_rect_sketch(asset_build_doc, "DummyFirstSketch", width=10.0, height=10.0)
        _ = self._create_hollow_rect_sketch(
            asset_build_doc, "TargetHollowSection", outer_w=40.0, outer_h=40.0, inner_w=20.0, inner_h=20.0
        )
        asset_build_doc.recompute()
        bdoc_name = asset_build_doc.Name
        asset_build_doc.saveAs(raw_asset_path)
        App.closeDocument(bdoc_name)
        if bdoc_name in self.doc_names:
            self.doc_names.remove(bdoc_name)

        # Register in manifest with exact object_name: "TargetHollowSection"
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            mdata = json.load(f)
        mdata["Custom Profile"]["sizes"]["Hollow_40x40"] = {
            "Height": "40.0",
            "Width": "40.0",
            "Weight": "9.42",
            "asset_path": "sections/sec_multi_sketch.FCStd",
            "object_name": "TargetHollowSection",
            "asset_id": "sec_multi_sketch",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(mdata, f, indent=2)

        project_doc = self._new_doc("ProjectHollowDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0, axis="X")

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Hollow_40x40")
        accepted = panel.accept()
        self.assertTrue(accepted, "Panel accept must return True.")

        project_doc.recompute()

        # Verify profile created
        profiles = [
            o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]
        self.assertEqual(len(profiles), 1, "Exactly one Profile object should be created.")
        prof = profiles[0]

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(len(prof.Shape.Solids), 1)
        self.assertTrue(prof.Shape.isValid())

        # Assert imported sketch is autonomous, solves cleanly, and has zero external links
        local_sketch = prof.CustomProfile
        self.assertIsNotNone(local_sketch, "prof.CustomProfile must link to imported sketch.")
        self.assertEqual(
            local_sketch.Document.Name, project_doc.Name, "Imported sketch must reside in project document."
        )
        self.assertEqual(local_sketch.solve(), 0, "Imported sketch must solve cleanly.")
        self.assertEqual(len(local_sketch.ExternalGeometry), 0, "Imported sketch must have 0 external links.")

        # Assert exact object was captured (outer width 40 mm, not dummy sketch width 10 mm)
        self.assertAlmostEqual(local_sketch.Shape.BoundBox.XLength, 40.0, places=2)
        self.assertAlmostEqual(local_sketch.Shape.BoundBox.YLength, 40.0, places=2)

        # Expected hollow volume = (40*40 - 20*20) * 100 = 1200 * 100 = 120,000 mm3
        expected_volume = (40.0 * 40.0 - 20.0 * 20.0) * 100.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_volume, places=1)

    # --- Case 3: Source sketch reuse across instances + BOM/PID grouping ---

    def test_source_reuse_across_profile_instances_and_bom_pid_grouping(self):
        """Case 3: Multiple profile instances from the same unchanged section reuse the

        same document-local sketch source; different libraries/sections disambiguate;
        shared source enables correct BOM quantity grouping and PID numbering.
        """
        # Create second folder library LibB with same size name 'S40' but distinct root/identity
        folder_lib_b = os.path.join(self.test_root, "FolderLibB")
        self.manager.create_folder_library(
            folder_lib_b,
            "FolderLibB",
            material="Steel",
            density=7.85,
            data={
                "Custom Profile": {
                    "canonical_family": "Custom Profile",
                    "sizes": {},
                }
            },
        )

        temp_doc = self._new_doc("TempDoc3")
        sk_a = self._create_rect_sketch(temp_doc, "SecA", width=40.0, height=40.0)
        self._publish_section_to_library(self.folder_lib_path, "S40", sk_a, object_name="SecA", asset_id="sec_liba_s40")
        sk_b = self._create_rect_sketch(temp_doc, "SecB", width=50.0, height=50.0)
        self._publish_section_to_library(folder_lib_b, "S40", sk_b, object_name="SecB", asset_id="sec_libb_s40")
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        project_doc = self._new_doc("ProjectReuseDoc")
        App.setActiveDocument(project_doc.Name)

        # Create 3 path edges in project document
        p1_sk = self._create_line_path(project_doc, "Path1", length=100.0, axis="X")
        p2_sk = self._create_line_path(project_doc, "Path2", length=100.0, axis="X")
        p3_sk = self._create_line_path(project_doc, "Path3", length=100.0, axis="X")

        # Instance 1: LibA -> S40 on Path1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p1_sk.Name, "Edge1")
        panel1 = CreateProfileTaskPanel()
        panel1.open()
        panel1.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel1.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel1.form_proxy.combo_size.setCurrentText("S40")
        panel1.accept()

        # Instance 2: LibA -> S40 on Path2 (SAME section and library)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p2_sk.Name, "Edge1")
        panel2 = CreateProfileTaskPanel()
        panel2.open()
        panel2.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel2.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel2.form_proxy.combo_size.setCurrentText("S40")
        panel2.accept()

        # Instance 3: LibB -> S40 on Path3 (DIFFERENT library with same code name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p3_sk.Name, "Edge1")
        panel3 = CreateProfileTaskPanel()
        panel3.open()
        panel3.form_proxy.combo_material.setCurrentText("FolderLibB")
        panel3.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel3.form_proxy.combo_size.setCurrentText("S40")
        panel3.accept()

        project_doc.recompute()

        all_profs = [
            o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]
        self.assertEqual(len(all_profs), 3, "Three profiles should be created.")

        prof1, prof2, prof3 = all_profs[0], all_profs[1], all_profs[2]

        # Verify source sketch reuse
        self.assertIsNotNone(prof1.CustomProfile)
        self.assertIsNotNone(prof2.CustomProfile)
        self.assertIsNotNone(prof3.CustomProfile)

        # Profile 1 and Profile 2 MUST share the exact same document-local sketch
        self.assertIs(
            prof1.CustomProfile,
            prof2.CustomProfile,
            "Profiles created from the same unchanged section must reuse the same document-local sketch.",
        )

        # Profile 3 MUST NOT share the sketch of Profile 1/2 because it came from FolderLibB
        self.assertIsNot(
            prof1.CustomProfile,
            prof3.CustomProfile,
            "Reuse identity must disambiguate sections from different libraries.",
        )

        # Count total sketches in project document: 3 paths + 1 shared sketch LibA + 1 sketch LibB = 5 sketches
        sketches_in_doc = [
            o for o in project_doc.Objects if hasattr(o, "isDerivedFrom") and o.isDerivedFrom("Sketcher::SketchObject")
        ]
        self.assertEqual(len(sketches_in_doc), 5, "Shared section sketch must be reused, not duplicated.")

        # BOM Grouping assertion
        profiles_data, links_data = [], []
        for p in (prof1, prof2, prof3):
            traverse_assembly(profiles_data, links_data, p)
        grouped = group_profiles(profiles_data)

        # Prof1 and Prof2 must group together with quantity == 2
        liba_group = [g for g in grouped if prof1.Label in g["label"] or prof2.Label in g["label"]]
        self.assertEqual(len(liba_group), 1, "prof1 and prof2 must group into a single BOM row.")
        self.assertEqual(liba_group[0]["quantity"], 2, "Grouped row must have quantity 2.")

        # PID Grouping assertion
        populate_ids(
            [prof1, prof2, prof3],
            [],
            [prof1, prof2, prof3],
            [],
            "all_numbers",
            False,
            True,
            True,
            False,
            "start_at",
            start_number="1",
        )
        pid1 = getattr(prof1, "PID", "")
        pid2 = getattr(prof2, "PID", "")
        pid3 = getattr(prof3, "PID", "")
        self.assertTrue(bool(pid1) and bool(pid2) and bool(pid3), "All profiles must have populated PIDs.")
        # prof1 and prof2 share the same base PID prefix before count suffix
        base1 = pid1.rsplit("-", 1)[0] if "-" in pid1 else pid1
        base2 = pid2.rsplit("-", 1)[0] if "-" in pid2 else pid2
        self.assertEqual(base1, base2, "Profiles sharing local custom section source must share PID group.")

    # --- Case 4: Project save/reopen without library ---

    def test_project_save_reopen_without_library(self):
        """Case 4: Project carries native local sketch; when project document is saved,

        and the library folder is completely removed from disk and registry,
        the reopened project document recomputes cleanly with intact valid geometry.
        """
        temp_doc = self._new_doc("TempDoc4")
        sk = self._create_rect_sketch(temp_doc, "StandaloneSec", width=50.0, height=25.0)
        self._publish_section_to_library(
            self.folder_lib_path,
            "Standalone_50x25",
            sk,
            object_name="StandaloneSec",
            asset_id="sec_standalone_50x25",
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        project_doc = self._new_doc("ProjectSaveDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=150.0, axis="X")

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")
        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Standalone_50x25")
        panel.accept()
        project_doc.recompute()

        # Save project document to disk
        project_file_path = os.path.join(self.test_root, "SavedProject.FCStd")
        pdoc_name = project_doc.Name
        project_doc.saveAs(project_file_path)

        # Record doc name and close project document
        App.closeDocument(pdoc_name)
        if pdoc_name in self.doc_names:
            self.doc_names.remove(pdoc_name)

        # Completely delete the folder library from disk and unregister it
        self.manager.unregister_folder_library(self.folder_lib_path)
        shutil.rmtree(self.folder_lib_path)
        self.assertFalse(os.path.exists(self.folder_lib_path), "Library folder must be removed from disk.")

        # Reopen saved project document in FreeCAD
        reopened_doc = App.openDocument(project_file_path)
        rdoc_name = reopened_doc.Name
        self.doc_names.append(rdoc_name)

        reopened_doc.recompute()

        # Assert profile and local sketch remain valid without library runtime dependency
        profs = [
            o for o in reopened_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]
        self.assertEqual(len(profs), 1, "Reopened project must contain the Profile.")
        prof = profs[0]

        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertTrue(prof.Shape.isValid())
        expected_volume = 50.0 * 25.0 * 150.0
        self.assertAlmostEqual(prof.Shape.Volume, expected_volume, places=1)

        # Local sketch is present and intact
        self.assertIsNotNone(prof.CustomProfile)
        self.assertEqual(prof.CustomProfile.Document.Name, rdoc_name)

    # --- Case 5: Library edit does not mutate existing source ---

    def test_library_edit_does_not_mutate_existing_project_source(self):
        """Case 5: Editing a section in the folder library creates a new asset file/UUID;

        existing project sources never auto-update; new profile instances use the edited section.
        """
        temp_doc = self._new_doc("TempDoc5")
        sk = self._create_rect_sketch(temp_doc, "EditableSec", width=60.0, height=30.0)
        rel_asset, obj_name, asset_id = self._publish_section_to_library(
            self.folder_lib_path,
            "EditTarget",
            sk,
            object_name="EditableSec",
            asset_id="sec_initial_version",
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        project_doc = self._new_doc("ProjectEditGuardDoc")
        App.setActiveDocument(project_doc.Name)
        path1 = self._create_line_path(project_doc, "Path1", length=100.0, axis="X")
        path2 = self._create_line_path(project_doc, "Path2", length=100.0, axis="X")

        # Create Profile 1 before library edit
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path1.Name, "Edge1")
        panel1 = CreateProfileTaskPanel()
        panel1.open()
        panel1.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel1.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel1.form_proxy.combo_size.setCurrentText("EditTarget")

        # Assert selection survived preview before accept
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 1, "Path1 selection must survive preview.")
        panel1.accept()
        project_doc.recompute()

        prof1 = [
            o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ][0]
        initial_vol1 = prof1.Shape.Volume
        initial_w1 = prof1.CustomProfile.Shape.BoundBox.XLength
        initial_h1 = prof1.CustomProfile.Shape.BoundBox.YLength
        self.assertAlmostEqual(initial_w1, 60.0, places=2)
        self.assertAlmostEqual(initial_h1, 30.0, places=2)

        # Mutate the library section using real SectionEditSession workflow (T4)
        session = SectionEditSession(self.folder_lib_path, rel_asset, size_code="EditTarget", asset_id=asset_id)
        wdoc = session.open()
        self.doc_names.append(wdoc.Name)
        wsk = wdoc.getObject(session.working_sketch_name)

        # Dynamic lookup of dimensional distance constraints (width=60.0, height=30.0)
        width_idx, height_idx = None, None
        for idx, c in enumerate(wsk.Constraints):
            val = getattr(c, "Value", None)
            if val is not None:
                if abs(float(val) - 60.0) < 1e-3:
                    width_idx = idx
                elif abs(float(val) - 30.0) < 1e-3:
                    height_idx = idx
        if width_idx is None:
            width_idx = 9
        if height_idx is None:
            height_idx = 10

        # Actual native geometry mutation: change datum distance constraints to 100.0 and 50.0
        wsk.setDatum(width_idx, 100.0)
        wsk.setDatum(height_idx, 50.0)
        wdoc.recompute()
        applied_meta = session.apply(density_g_cm3=7.85)
        session.close(discard_uncommitted=False)

        # Restore active document to project_doc after session close
        App.setActiveDocument(project_doc.Name)

        # Update library manifest with newly emitted asset UUID
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            mdata = json.load(f)
        mdata["Custom Profile"]["sizes"]["EditTarget"] = {
            "Height": applied_meta["Height"],
            "Width": applied_meta["Width"],
            "Weight": applied_meta["Weight"],
            "asset_path": applied_meta["asset_path"],
            "object_name": applied_meta["object_name"],
            "asset_id": applied_meta["asset_id"],
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(mdata, f, indent=2)

        # Verify new asset UUID was emitted
        self.assertNotEqual(applied_meta["asset_id"], asset_id, "Library edit must emit a new asset ID.")

        # Recompute project document: Existing Profile 1 MUST REMAIN UNTOUCHED
        project_doc.recompute()
        self.assertAlmostEqual(prof1.CustomProfile.Shape.BoundBox.XLength, initial_w1, places=2)
        self.assertAlmostEqual(prof1.CustomProfile.Shape.BoundBox.YLength, initial_h1, places=2)
        self.assertAlmostEqual(prof1.Shape.Volume, initial_vol1, places=1)

        # Create Profile 2 AFTER library edit: should use new edited section (100x50)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path2.Name, "Edge1")
        panel2 = CreateProfileTaskPanel()
        panel2.open()
        panel2.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel2.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel2.form_proxy.combo_size.setCurrentText("EditTarget")

        # Assert selection survived preview before accept
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 1, "Path2 selection must survive preview.")
        panel2.accept()
        project_doc.recompute()

        all_profs = [
            o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]
        self.assertEqual(len(all_profs), 2)
        prof2 = [p for p in all_profs if p.Name != prof1.Name][0]

        self.assertAlmostEqual(prof2.CustomProfile.Shape.BoundBox.XLength, 100.0, places=2)
        self.assertAlmostEqual(prof2.CustomProfile.Shape.BoundBox.YLength, 50.0, places=2)
        expected_vol2 = 100.0 * 50.0 * 100.0
        self.assertAlmostEqual(prof2.Shape.Volume, expected_vol2, places=1)

        # Existing prof1 source sketch remains 60x30
        self.assertAlmostEqual(prof1.CustomProfile.Shape.BoundBox.XLength, 60.0, places=2)

    # --- Case 6: Paths, containers, anchors, and mirror semantics ---

    def test_paths_containers_anchors_and_mirror(self):
        """Case 6: Profiles along path edges preserve App::Part container placement,

        in-document sketch linking across containers, and mirror/anchor semantics.
        """
        temp_doc = self._new_doc("TempDoc6")
        sk = self._create_rect_sketch(temp_doc, "AsymmSec", width=80.0, height=40.0)
        self._publish_section_to_library(
            self.folder_lib_path,
            "Asymm_80x40",
            sk,
            object_name="AsymmSec",
            asset_id="sec_asymm_80x40",
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        project_doc = self._new_doc("ProjectContainerDoc")
        App.setActiveDocument(project_doc.Name)

        # Create App::Part container and put path sketch inside it
        part_container = project_doc.addObject("App::Part", "AssemblyPart")
        path_sk = self._create_line_path(project_doc, "ContainedPath", length=200.0, axis="Z")
        part_container.addObject(path_sk)

        # Direct control path with identical geometry for parity comparison
        path_sk_direct = self._create_line_path(project_doc, "DirectPath", length=200.0, axis="Z")
        part_container.addObject(path_sk_direct)
        project_doc.recompute()

        # Select Edge1 of ContainedPath
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Asymm_80x40")

        # Set Mirror options and Anchor (Top-Right: ax=2, ay=2)
        panel.form_proxy.cb_mirror_h.setChecked(True)
        panel.form_proxy.cb_mirror_v.setChecked(True)
        panel.set_anchor(2, 2)
        panel.accept()
        project_doc.recompute()

        prof = [o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")][
            0
        ]

        # Verify profile moved into container
        self.assertTrue(
            part_container.hasObject(prof) or prof in part_container.Group,
            "Profile must be placed inside sketch's parent container.",
        )

        # Verify CustomProfile source sketch links safely across document/container
        self.assertIsNotNone(prof.CustomProfile)
        self.assertEqual(prof.CustomProfile.Document.Name, project_doc.Name)

        # Create direct reference Profile on path_sk_direct with exact same parameters for parity check
        obj_direct = project_doc.addObject("Part::FeaturePython", "DirectProfile")
        obj_direct.addExtension("Part::AttachExtensionPython")
        part_container.addObject(obj_direct)
        Profile(
            obj_direct,
            80.0,
            40.0,
            0.0,
            0.0,
            0.0,
            0.0,
            200.0,
            25.12,
            0.0,
            False,
            2,
            2,  # Anchor Right, Top
            "Steel",
            "Custom Profile",
            "Asymm_80x40",
            False,
            (path_sk_direct, ("Edge1")),
            custom_profile=prof.CustomProfile,
            init_mirror_h=True,
            init_mirror_v=True,
            catalog_family="Custom Profile",
        )
        project_doc.recompute()

        # Parity assertions between library-imported profile and direct custom profile
        self.assertEqual(prof.AnchorX, obj_direct.AnchorX)
        self.assertEqual(prof.AnchorY, obj_direct.AnchorY)
        self.assertEqual(prof.MirrorH, obj_direct.MirrorH)
        self.assertEqual(prof.MirrorV, obj_direct.MirrorV)
        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertEqual(obj_direct.getStatusString(), "Valid")
        self.assertAlmostEqual(prof.Shape.Volume, obj_direct.Shape.Volume, places=2)
        self.assertAlmostEqual(prof.Shape.BoundBox.XLength, obj_direct.Shape.BoundBox.XLength, places=2)
        self.assertAlmostEqual(prof.Shape.BoundBox.YLength, obj_direct.Shape.BoundBox.YLength, places=2)
        self.assertAlmostEqual(prof.Shape.BoundBox.ZLength, obj_direct.Shape.BoundBox.ZLength, places=2)

    def test_importer_preserves_caller_transaction_and_owned_source_cleanup(self):
        """Closing an imported asset must not commit the caller's pending edits."""
        source_doc = self._new_doc("TransactionSource")
        source = self._create_rect_sketch(source_doc, "TransactionSection", width=60.0, height=30.0)
        rel_path, object_name, asset_id = self._publish_section_to_library(
            self.folder_lib_path, "Transaction_60x30", source, "TransactionSection", "transaction_section"
        )
        source_name = source_doc.Name
        App.closeDocument(source_name)
        self.doc_names.remove(source_name)
        asset_path = os.path.join(self.folder_lib_path, rel_path)
        with open(asset_path, "rb") as stream:
            original_asset = stream.read()

        project = self._new_doc("TransactionProject")
        App.setActiveDocument(project.Name)
        box = project.addObject("Part::Box", "ExistingBox")
        box.Length = 125.0
        project.recompute()
        original_label = box.Label
        baseline_names = {obj.Name for obj in project.Objects}
        baseline_docs = set(App.listDocuments())
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project.Name, box.Name, "Edge1")

        def selection():
            return [(s.DocumentName, s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]

        original_selection = selection()
        for edit_before_import in (True, False):
            with self.subTest(edit_before_import=edit_before_import):
                project.openTransaction("Caller-owned edit and import")
                if edit_before_import:
                    box.Label = "Pending caller edit"
                imported = get_or_import_section_sketch(
                    self.folder_lib_path,
                    rel_path,
                    object_name,
                    target_doc=project,
                    asset_id=asset_id,
                    profile_code="Transaction_60x30",
                )
                imported_name = imported.Name
                self.assertEqual(imported.Document.Name, project.Name)
                self.assertEqual(imported.FF_AssetId, asset_id)
                self.assertEqual(imported.FF_ObjectName, object_name)
                self.assertEqual(imported.Label, "Transaction_60x30")
                self.assertFalse(imported.ViewObject.ShowInTree)
                self.assertFalse(imported.ViewObject.Visibility)
                if not edit_before_import:
                    box.Label = "Pending caller edit"
                self.assertEqual(box.Label, "Pending caller edit")
                self.assertEqual(set(App.listDocuments()), baseline_docs, "Importer-owned asset must be closed.")
                self.assertEqual(App.ActiveDocument.Name, project.Name)
                self.assertEqual(selection(), original_selection)
                reused = get_or_import_section_sketch(
                    self.folder_lib_path, rel_path, object_name, target_doc=project, asset_id=asset_id
                )
                self.assertIs(reused, imported)
                self.assertEqual(set(App.listDocuments()), baseline_docs)
                self.assertEqual(selection(), original_selection)

                project.abortTransaction()
                self.assertEqual({obj.Name for obj in project.Objects}, baseline_names)
                self.assertIsNone(project.getObject(imported_name))
                self.assertEqual(project.getObject("ExistingBox").Label, original_label)
                self.assertAlmostEqual(project.getObject("ExistingBox").Length.Value, 125.0)
                self.assertEqual(App.ActiveDocument.Name, project.Name)
                self.assertEqual(selection(), original_selection)
                with open(asset_path, "rb") as stream:
                    self.assertEqual(stream.read(), original_asset, "Import must not write the library asset.")

    # --- Case 7: Reject transaction rollback ---

    def test_reject_transaction_rollback_preserves_project_state(self):
        """Case 7: Canceling/rejecting CreateProfileTaskPanel rolls back preview profiles

        and imported sketches, preserving pre-existing user models and document state.
        """
        temp_doc = self._new_doc("TempDoc7")
        sk = self._create_rect_sketch(temp_doc, "RollbackSec", width=50.0, height=50.0)
        self._publish_section_to_library(
            self.folder_lib_path,
            "Rollback_50x50",
            sk,
            object_name="RollbackSec",
            asset_id="sec_rollback_50x50",
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        project_doc = self._new_doc("ProjectRollbackDoc")
        App.setActiveDocument(project_doc.Name)

        # Create pre-existing user objects
        existing_box = project_doc.addObject("Part::Box", "ExistingBox")
        path_sk = self._create_line_path(project_doc, "Path", length=100.0, axis="X")
        project_doc.recompute()

        baseline_names = set(obj.Name for obj in project_doc.Objects)
        self.assertEqual(len(baseline_names), 2)

        # Open panel and preview profile creation
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Rollback_50x50")
        panel.proceed()

        # During preview, assert preview profile and imported local sketch actually exist
        preview_profs = [
            o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]
        self.assertEqual(len(preview_profs), 1, "Preview profile must exist before reject.")
        preview_prof = preview_profs[0]
        self.assertIsNotNone(
            preview_prof.CustomProfile, "Preview profile CustomProfile source sketch must exist before reject."
        )
        self.assertEqual(preview_prof.CustomProfile.Document.Name, project_doc.Name)
        preview_sketch_name = preview_prof.CustomProfile.Name
        preview_prof_name = preview_prof.Name

        # Reject/Cancel the panel transaction
        panel.reject()

        # Assert document state is completely restored to baseline
        final_names = set(obj.Name for obj in project_doc.Objects)
        self.assertEqual(final_names, baseline_names, "Reject must restore exact original object set.")
        self.assertIn("ExistingBox", final_names)
        self.assertIn("Path", final_names)
        self.assertNotIn(preview_prof_name, final_names)
        self.assertNotIn(preview_sketch_name, final_names)

    # --- Case 8: Confinement and open-doc ownership ---

    def test_confinement_and_open_doc_ownership_preservation(self):
        """Case 8: Rejects path traversal and unconfined assets;

        if asset document is already open in FreeCAD (e.g. user-owned),
        importer does NOT close it or mutate it; only closes docs importer itself opened.
        """
        temp_doc = self._new_doc("TempDoc8")
        sk = self._create_rect_sketch(temp_doc, "ConfinedSec", width=70.0, height=35.0)
        rel_asset, obj_name, asset_id = self._publish_section_to_library(
            self.folder_lib_path,
            "Confined_70x35",
            sk,
            object_name="ConfinedSec",
            asset_id="sec_confined_70x35",
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        # Subcase A: Already-open asset document is user-owned
        full_asset_path = os.path.join(self.folder_lib_path, rel_asset)
        with open(full_asset_path, "rb") as f:
            original_bytes = f.read()

        user_opened_doc = App.openDocument(full_asset_path)
        user_doc_name = user_opened_doc.Name
        self.doc_names.append(user_doc_name)
        user_undo_state = (user_opened_doc.UndoMode, user_opened_doc.UndoCount, user_opened_doc.RedoCount)

        project_doc = self._new_doc("ProjectOwnerDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0, axis="X")

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Confined_70x35")

        # Assert selection survived preview before accept
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 1, "Path selection must survive preview.")
        panel.accept()

        # Verify profile and local source were successfully created
        profs = [o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")]
        self.assertEqual(len(profs), 1, "Profile must be successfully created.")
        prof = profs[0]
        self.assertEqual(prof.getStatusString(), "Valid")
        self.assertIsNotNone(prof.CustomProfile, "Profile must link to imported sketch.")
        self.assertEqual(prof.CustomProfile.Document.Name, project_doc.Name)

        # Verify user-owned document was NOT closed by the importer
        self.assertIn(
            user_doc_name,
            App.listDocuments(),
            "Already-open asset document must remain open after profile creation.",
        )
        self.assertEqual(App.ActiveDocument.Name, project_doc.Name, "Active document must be restored to project.")
        self.assertEqual(
            (user_opened_doc.UndoMode, user_opened_doc.UndoCount, user_opened_doc.RedoCount), user_undo_state
        )

        # Asset file on disk was not mutated
        with open(full_asset_path, "rb") as f:
            after_bytes = f.read()
        self.assertEqual(original_bytes, after_bytes, "Published asset file must not be modified.")

        # Subcase B: Confinement check: path traversal rejection
        baseline_doc_objs = set(obj.Name for obj in project_doc.Objects)
        baseline_open_docs = set(App.listDocuments().keys())
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "rb") as f:
            manifest_bytes_before = f.read()

        with self.assertRaises(ValueError) as ctx:
            resolve_and_validate_asset_path(self.folder_lib_path, "../outside.FCStd")
        self.assertIn("traversal", str(ctx.exception).lower())

        with self.assertRaises(ValueError) as ctx2:
            get_or_import_section_sketch(self.folder_lib_path, "../outside.FCStd", "Section", project_doc)
        self.assertIn("traversal", str(ctx2.exception).lower())

        # Assert no new objects in project doc, no new open documents, no manifest changes
        self.assertEqual(set(obj.Name for obj in project_doc.Objects), baseline_doc_objs)
        self.assertEqual(set(App.listDocuments().keys()), baseline_open_docs)
        with open(manifest_path, "rb") as f:
            self.assertEqual(f.read(), manifest_bytes_before)

    # --- Case 9: Preserve standard parametric chooser behavior ---

    def test_preserve_standard_parametric_chooser_behavior(self):
        """Case 9: Preserves legacy parametric family behavior and controls;

        unknown-setting validation is NOT weakened for standard parametric data.
        """
        project_doc = self._new_doc("ProjectParametricDoc")
        App.setActiveDocument(project_doc.Name)
        path_sk = self._create_line_path(project_doc, "Path", length=100.0, axis="X")

        # Select Edge1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path_sk.Name, "Edge1")

        panel = CreateProfileTaskPanel()
        panel.open()

        # Select standard parametric family from stock library
        panel.form_proxy.combo_material.setCurrentText("StockSteel")
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        panel.form_proxy.combo_size.setCurrentText("40x40x2")

        # Dimensional controls are enabled for parametric profiles
        self.assertTrue(panel.form_proxy.sb_width.isEnabled(), "sb_width must be enabled for parametric profiles.")
        self.assertTrue(panel.form_proxy.sb_height.isEnabled(), "sb_height must be enabled for parametric profiles.")
        self.assertTrue(panel.form_proxy.sb_main_thickness.isEnabled(), "sb_main_thickness must be enabled.")
        self.assertAlmostEqual(panel.form_proxy.sb_width.value(), 40.0, places=2)
        self.assertAlmostEqual(panel.form_proxy.sb_height.value(), 40.0, places=2)
        self.assertAlmostEqual(panel.form_proxy.sb_main_thickness.value(), 2.0, places=2)

        # Create standard parametric profile
        panel.accept()
        project_doc.recompute()

        profs = [o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")]
        self.assertEqual(len(profs), 1)
        prof = profs[0]
        self.assertEqual(prof.Family, "Square Hollow")
        self.assertIsNone(getattr(prof, "CustomProfile", None), "Standard profile must not have CustomProfile link.")
        self.assertEqual(prof.getStatusString(), "Valid")

        # Subcase B: Unknown setting in standard parametric family MUST still raise ValueError("Setting Unkown")
        panel2 = CreateProfileTaskPanel()
        panel2.open()
        panel2.profiles["StockSteel"]["Square Hollow"]["sizes"]["CorruptSize"] = {
            "Height": "40",
            "Width": "40",
            "Thickness": "2",
            "Weight": "2.4",
            "CompletelyUnknownSetting": "123",
        }
        panel2.form_proxy.combo_size.addItem("CorruptSize")

        with self.assertRaises(ValueError) as ctx:
            panel2.form_proxy.combo_size.setCurrentText("CorruptSize")
            panel2.on_size_changed(None)
        self.assertIn("Setting Unkown", str(ctx.exception))
        panel2.reject()


if __name__ == "__main__":
    unittest.main()

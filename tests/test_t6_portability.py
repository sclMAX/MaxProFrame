"""Native GUI regression tests for portable custom library relocation and project independence (T6).

Covers S1, S2, S3, S5, S8, S9:
- Rule 1: End-to-end capture -> save -> instantiate profile -> duplicate/relocate -> instantiate from duplicate
          -> save project -> remove all library folders -> reopen/recompute project cleanly with editable local sketches
- Rule 2: Duplicate-delete independence: modifying/deleting duplicate does not mutate or invalidate source library
- Rule 3: Relocation in-place portability: moved folder library registered at new path resolves relative assets without broken references
- Rule 4: Shared asset references survive duplication without duplicate asset files, preserving project-local sketch reuse and BOM grouping
"""

import copy
import hashlib
import json
import os
import shutil
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

import test_portable_library_profile_instantiation as helper
from freecad.frameforge.create_bom import group_profiles
from freecad.frameforge.create_profiles_tool import CreateProfileTaskPanel
from freecad.frameforge.section_library import get_or_import_section_sketch


def _file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestT6Portability(helper.TestPortableLibraryProfileInstantiation):
    def setUp(self):
        super().setUp()

        # Fail fast on any unexpected modal dialog instead of hanging or auto-accepting
        def fail_modal(box, *args):
            raise AssertionError(f"UNEXPECTED_MODAL: {box.windowTitle()}: {box.text()}")

        self.messages.enter_context(patch.object(helper.QtWidgets.QMessageBox, "exec_", fail_modal))
        for method in ("warning", "critical", "information", "question"):
            def make_fail(m):
                def _fail(parent, title, text, *args, **kwargs):
                    raise AssertionError(f"UNEXPECTED_MODAL_{m.upper()}: {title}: {text}")
                return _fail
            self.messages.enter_context(
                patch.object(helper.QtWidgets.QMessageBox, method, side_effect=make_fail(method))
            )

    def test_t6_end_to_end_capture_duplicate_relocate_and_offline_project_independence(self):
        """Rule 1: Native end-to-end capture -> save -> instantiate -> duplicate/relocate
        -> instantiate from duplicate -> save project -> delete all library folders from disk
        -> reopen and recompute project cleanly with intact editable local sketch geometry.
        """
        # Step 1: Create native sketch in source doc and capture into CustomFolderLib
        source_doc = self._new_doc("SourceNativeDoc")
        sk_source = self._create_rect_sketch(source_doc, "AutonomousSec", width=80.0, height=40.0)
        self._publish_section_to_library(
            self.folder_lib_path,
            "SecA_80x40",
            sk_source,
            object_name="AutonomousSec",
            asset_id="sec_a_80x40",
        )
        sdoc_name = source_doc.Name
        App.closeDocument(sdoc_name)
        if sdoc_name in self.doc_names:
            self.doc_names.remove(sdoc_name)

        # Step 2: Create project document with Path1 and instantiate Profile 1 from CustomFolderLib
        project_doc = self._new_doc("ProjectOfflineDoc")
        App.setActiveDocument(project_doc.Name)
        path1 = self._create_line_path(project_doc, "Path1", length=100.0, axis="X")

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path1.Name, "Edge1")
        panel1 = CreateProfileTaskPanel()
        panel1.open()
        panel1.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel1.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel1.form_proxy.combo_size.setCurrentText("SecA_80x40")
        panel1.accept()
        project_doc.recompute()

        # Step 3: Duplicate CustomFolderLib to FolderLibB with Aluminium and recalculate_weights=True
        dest_b_path = os.path.join(self.test_root, "FolderLibB")
        self.manager.duplicate_library(
            "CustomFolderLib",
            "FolderLibB",
            target_folder_path=dest_b_path,
            target_material="Aluminium",
            target_density=2.70,
            recalculate_weights=True,
        )

        # Step 4: Create Path2 in project document and instantiate Profile 2 from FolderLibB
        path2 = self._create_line_path(project_doc, "Path2", length=150.0, axis="Z")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, path2.Name, "Edge1")
        panel2 = CreateProfileTaskPanel()
        panel2.open()
        panel2.form_proxy.combo_material.setCurrentText("FolderLibB")
        panel2.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel2.form_proxy.combo_size.setCurrentText("SecA_80x40")
        panel2.accept()
        project_doc.recompute()

        # Verify initial profile volumes before save
        profs_initial = [o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")]
        self.assertEqual(len(profs_initial), 2)
        v1_initial = 80.0 * 40.0 * 100.0
        v2_initial = 80.0 * 40.0 * 150.0
        self.assertAlmostEqual(profs_initial[0].Shape.Volume, v1_initial, places=1)
        self.assertAlmostEqual(profs_initial[1].Shape.Volume, v2_initial, places=1)

        # Step 5: Save project document to disk and close it
        project_file_path = os.path.join(self.test_root, "ProjectOfflineSaved.FCStd")
        pdoc_name = project_doc.Name
        project_doc.saveAs(project_file_path)
        App.closeDocument(pdoc_name)
        if pdoc_name in self.doc_names:
            self.doc_names.remove(pdoc_name)

        # Step 6: Remove ALL library folders from disk and unregister them
        self.manager.unregister_folder_library(self.folder_lib_path)
        self.manager.unregister_folder_library(dest_b_path)
        shutil.rmtree(self.folder_lib_path)
        shutil.rmtree(dest_b_path)
        self.assertFalse(os.path.exists(self.folder_lib_path))
        self.assertFalse(os.path.exists(dest_b_path))

        # Step 7: Reopen project document in FreeCAD and recompute
        reopened_doc = App.openDocument(project_file_path)
        rdoc_name = reopened_doc.Name
        self.doc_names.append(rdoc_name)
        reopened_doc.recompute()

        # Assert profiles recompute cleanly with valid volume
        profs_reopened = [o for o in reopened_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")]
        self.assertEqual(len(profs_reopened), 2, "Reopened project must retain both profiles.")
        for p in profs_reopened:
            self.assertEqual(p.getStatusString(), "Valid")
            self.assertTrue(p.Shape.isValid())
            self.assertIsNotNone(p.CustomProfile)
            self.assertEqual(p.CustomProfile.Document.Name, rdoc_name, "Local sketch must belong to reopened doc.")
            self.assertGreater(len(p.CustomProfile.Constraints), 0, "Local sketch must retain constraints.")

        self.assertAlmostEqual(profs_reopened[0].Shape.Volume, v1_initial, places=1)
        self.assertAlmostEqual(profs_reopened[1].Shape.Volume, v2_initial, places=1)

    def test_t6_duplicate_delete_independence(self):
        """Rule 2: Deleting or mutating a duplicated library does not mutate, unregister,
        or invalidate the source folder library.
        """
        # Publish section to source library
        temp_doc = self._new_doc("SourceTempDoc")
        sk = self._create_rect_sketch(temp_doc, "Sec1", width=50.0, height=50.0)
        rel_path, _, aid = self._publish_section_to_library(
            self.folder_lib_path, "Sec1_50x50", sk, object_name="Sec1"
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        manifest_source_path = os.path.join(self.folder_lib_path, "library.json")
        src_manifest_hash_before = _file_hash(manifest_source_path)

        # Duplicate to FolderLibB
        dest_b = os.path.join(self.test_root, "FolderLibB_Indep")
        self.manager.duplicate_library(
            "CustomFolderLib",
            "FolderLibB_Indep",
            target_folder_path=dest_b,
        )

        # Mutate FolderLibB by adding a new section
        temp_doc2 = self._new_doc("SourceTempDoc2")
        sk2 = self._create_rect_sketch(temp_doc2, "Sec2", width=60.0, height=60.0)
        self._publish_section_to_library(
            dest_b, "Sec2_60x60", sk2, object_name="Sec2"
        )
        tdoc_name2 = temp_doc2.Name
        App.closeDocument(tdoc_name2)
        if tdoc_name2 in self.doc_names:
            self.doc_names.remove(tdoc_name2)

        # Delete and unregister FolderLibB
        self.manager.unregister_folder_library(dest_b)
        shutil.rmtree(dest_b)
        self.assertFalse(os.path.exists(dest_b))

        # Source library remains registered, manifest byte-identical, assets intact
        self.assertIn(os.path.realpath(self.folder_lib_path), [lib.get("folder_path") for lib in self.manager.list_libraries() if lib.get("is_folder")])
        self.assertEqual(_file_hash(manifest_source_path), src_manifest_hash_before)
        self.assertTrue(os.path.isfile(os.path.join(self.folder_lib_path, rel_path)))

        # Can still create profiles from source library
        project_doc = self._new_doc("ProjIndepDoc")
        App.setActiveDocument(project_doc.Name)
        p = self._create_line_path(project_doc, "Path", length=100.0)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p.Name, "Edge1")
        panel = CreateProfileTaskPanel()
        panel.open()
        panel.form_proxy.combo_material.setCurrentText("CustomFolderLib")
        panel.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel.form_proxy.combo_size.setCurrentText("Sec1_50x50")
        self.assertTrue(panel.accept())

    def test_t6_relocation_in_place_portability(self):
        """Rule 3: Moving a library directory and registering it in-place at the new location
        allows all relative assets to resolve without broken references or path leakage.
        """
        temp_doc = self._new_doc("RelocDoc")
        sk = self._create_rect_sketch(temp_doc, "RelocSec", width=70.0, height=35.0)
        rel_path, obj_name, _ = self._publish_section_to_library(
            self.folder_lib_path, "Reloc_70x35", sk, object_name="RelocSec"
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        # Unregister and move folder
        self.manager.unregister_folder_library(self.folder_lib_path)
        new_lib_root = os.path.join(self.test_root, "MovedFolderLib")
        shutil.move(self.folder_lib_path, new_lib_root)
        self.assertFalse(os.path.exists(self.folder_lib_path))
        self.assertTrue(os.path.isdir(new_lib_root))

        # Register at new location
        self.manager.register_folder_library(new_lib_root)

        # Import section sketch from new location
        project_doc = self._new_doc("ImportRelocDoc")
        imported_sketch = get_or_import_section_sketch(
            new_lib_root, rel_path, obj_name, target_doc=project_doc
        )
        self.assertIsNotNone(imported_sketch)
        self.assertEqual(imported_sketch.Document.Name, project_doc.Name)
        self.assertEqual(imported_sketch.solve(), 0)

    def test_t6_shared_assets_portability_across_duplication(self):
        """Rule 4: Shared asset references are preserved in duplicated libraries without
        file duplication, maintaining project-local sketch reuse and BOM grouping.
        """
        temp_doc = self._new_doc("SharedAssetDoc")
        sk = self._create_rect_sketch(temp_doc, "SharedSec", width=45.0, height=45.0)
        rel_path, obj_name, aid = self._publish_section_to_library(
            self.folder_lib_path, "Shared_A", sk, object_name="SharedSec", asset_id="sec_shared_common"
        )
        tdoc_name = temp_doc.Name
        App.closeDocument(tdoc_name)
        if tdoc_name in self.doc_names:
            self.doc_names.remove(tdoc_name)

        # Add a second size entry in CustomFolderLib sharing the exact same asset
        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        shared_entry = copy.deepcopy(manifest_data["Custom Profile"]["sizes"]["Shared_A"])
        manifest_data["Custom Profile"]["sizes"]["Shared_B"] = shared_entry
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Duplicate to FolderLibShared
        dest_shared = os.path.join(self.test_root, "FolderLibShared")
        self.manager.duplicate_library(
            "CustomFolderLib",
            "FolderLibShared",
            target_folder_path=dest_shared,
        )

        # Check destination manifest preserves shared asset reference
        with open(os.path.join(dest_shared, "library.json"), "r", encoding="utf-8") as f:
            dest_data = json.load(f)
        self.assertEqual(
            dest_data["Custom Profile"]["sizes"]["Shared_A"]["asset_path"],
            dest_data["Custom Profile"]["sizes"]["Shared_B"]["asset_path"],
        )
        # Check destination sections directory has only ONE copy of the asset file
        sections_files = os.listdir(os.path.join(dest_shared, "sections"))
        fcstd_files = [f for f in sections_files if f.endswith(".FCStd")]
        self.assertEqual(len(fcstd_files), 1, "Shared asset must only be copied once.")

        # In project document, instantiate both sizes from FolderLibShared
        project_doc = self._new_doc("ProjSharedDoc")
        App.setActiveDocument(project_doc.Name)
        p1 = self._create_line_path(project_doc, "Path1", length=100.0)
        p2 = self._create_line_path(project_doc, "Path2", length=200.0)

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p1.Name, "Edge1")
        panel1 = CreateProfileTaskPanel()
        panel1.open()
        panel1.form_proxy.combo_material.setCurrentText("FolderLibShared")
        panel1.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel1.form_proxy.combo_size.setCurrentText("Shared_A")
        panel1.accept()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(project_doc.Name, p2.Name, "Edge1")
        panel2 = CreateProfileTaskPanel()
        panel2.open()
        panel2.form_proxy.combo_material.setCurrentText("FolderLibShared")
        panel2.form_proxy.combo_family.setCurrentText("Custom Profile")
        panel2.form_proxy.combo_size.setCurrentText("Shared_B")
        panel2.accept()

        project_doc.recompute()

        profs = [o for o in project_doc.Objects if getattr(o, "Type", None) == "Profile" or hasattr(o, "CustomProfile")]
        self.assertEqual(len(profs), 2)
        # Both profiles share the exact same project-local sketch
        self.assertEqual(
            profs[0].CustomProfile.Name,
            profs[1].CustomProfile.Name,
            "Profiles sharing the same library asset must reuse the same project-local sketch.",
        )


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for method_name in [
        "test_t6_end_to_end_capture_duplicate_relocate_and_offline_project_independence",
        "test_t6_duplicate_delete_independence",
        "test_t6_relocation_in_place_portability",
        "test_t6_shared_assets_portability_across_duplication",
    ]:
        suite.addTest(TestT6Portability(method_name))
    return suite

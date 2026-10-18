import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from freecad.maxproframe.library_manager import (
    LibraryManager,
    calculate_linear_weight,
    get_known_families,
    sanitize_library_name,
)


class TestFolderLibraries(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary directory for user profiles and registry
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_user_dir_")
        self.test_registry_dir = os.path.join(self.test_user_dir, ".registry")
        self.test_registry_path = os.path.join(self.test_registry_dir, "folders.json")
        self.manager = LibraryManager(
            user_dir=self.test_user_dir,
            registry_path=self.test_registry_path,
        )

        # Temporary folder for creating test folder libraries
        self.test_libraries_root = tempfile.mkdtemp(prefix="ff_test_folder_libs_")

    def tearDown(self):
        for path in (self.test_user_dir, self.test_libraries_root):
            if os.path.exists(path):
                shutil.rmtree(path)

    def test_create_folder_library_creates_manifest_and_registers(self):
        lib_dir = os.path.join(self.test_libraries_root, "Custom Aluminum")
        manifest_path = self.manager.create_folder_library(
            folder_path=lib_dir,
            name="Custom Aluminum",
            material="Aluminium",
            density=2.70,
        )

        self.assertTrue(os.path.isdir(lib_dir))
        expected_manifest = os.path.join(os.path.realpath(lib_dir), "library.json")
        self.assertEqual(manifest_path, expected_manifest)
        self.assertTrue(os.path.isfile(expected_manifest))

        with open(expected_manifest, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("_metadata", data)
        self.assertEqual(data["_metadata"]["name"], "Custom Aluminum")
        self.assertEqual(data["_metadata"]["material"], "Aluminium")
        self.assertEqual(data["_metadata"]["density"], 2.70)
        self.assertTrue(data["_metadata"]["is_folder"])

        # Check listed libraries
        libs = self.manager.list_libraries()
        folder_lib = next((lib for lib in libs if lib["name"] == "Custom Aluminum"), None)
        self.assertIsNotNone(folder_lib)
        self.assertTrue(folder_lib["is_user"])
        self.assertFalse(folder_lib["can_delete"])
        self.assertTrue(folder_lib["is_folder"])
        self.assertTrue(folder_lib["can_unregister"])
        self.assertEqual(folder_lib["folder_path"], os.path.realpath(lib_dir))
        self.assertEqual(folder_lib["path"], expected_manifest)

    def test_create_folder_library_refuses_overwrite_manifest(self):
        lib_dir = os.path.join(self.test_libraries_root, "ExistingLib")
        os.makedirs(lib_dir, exist_ok=True)
        manifest_file = os.path.join(lib_dir, "library.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({"_metadata": {"name": "Preexisting"}}, f)

        with self.assertRaises(FileExistsError) as ctx:
            self.manager.create_folder_library(
                folder_path=lib_dir,
                name="NewName",
            )
        self.assertIn("already exists", str(ctx.exception))

    def test_create_folder_library_refuses_nonempty_unrelated_folder(self):
        lib_dir = os.path.join(self.test_libraries_root, "UnrelatedContent")
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("Important notes")

        with self.assertRaises(ValueError) as ctx:
            self.manager.create_folder_library(
                folder_path=lib_dir,
                name="ShouldFail",
            )
        self.assertIn("not empty", str(ctx.exception).lower())
        self.assertFalse(os.path.exists(os.path.join(lib_dir, "library.json")))

    def test_create_folder_library_rejects_name_collision(self):
        lib_dir = os.path.join(self.test_libraries_root, "CollidingMetal")
        # Collides with bundled stock "Metal"
        with self.assertRaises(ValueError) as ctx:
            self.manager.create_folder_library(
                folder_path=lib_dir,
                name="Metal",
            )
        self.assertIn("collides with an existing library", str(ctx.exception).lower())
        self.assertFalse(os.path.exists(lib_dir))

    def test_register_folder_library_validates_only_and_does_not_modify_folder(self):
        lib_dir = os.path.join(self.test_libraries_root, "ExternalBundle")
        os.makedirs(lib_dir, exist_ok=True)
        manifest_file = os.path.join(lib_dir, "library.json")
        initial_data = {
            "_metadata": {
                "name": "External Workshop",
                "material": "Steel",
                "density": 7.85,
            },
            "Square Hollow": {
                "norm": "Custom",
                "sizes": {
                    "40x40x2": {
                        "Height": "40",
                        "Width": "40",
                        "Thickness": "2",
                        "Weight": "2.35",
                    }
                },
            },
        }
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        before_stat = os.stat(manifest_file)
        time.sleep(0.01)

        result = self.manager.register_folder_library(lib_dir)
        self.assertEqual(result["name"], "External Workshop")

        after_stat = os.stat(manifest_file)
        self.assertEqual(before_stat.st_mtime_ns, after_stat.st_mtime_ns)
        with open(manifest_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), initial_data)

    def test_register_folder_library_canonical_path_idempotence(self):
        lib_dir = os.path.join(self.test_libraries_root, "IdempotentLib")
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, "library.json"), "w", encoding="utf-8") as f:
            json.dump({"_metadata": {"name": "Idempotent Lib", "material": "Steel"}}, f)

        res1 = self.manager.register_folder_library(lib_dir)
        # Register again using a redundant path with trailing slash and .
        res2 = self.manager.register_folder_library(lib_dir + "/./")

        self.assertEqual(res1["name"], res2["name"])
        # Verify registry file contains exactly one entry
        with open(self.test_registry_path, "r", encoding="utf-8") as f:
            reg_data = json.load(f)
        self.assertEqual(len(reg_data["folders"]), 1)
        self.assertEqual(reg_data["folders"][0], os.path.realpath(lib_dir))

    def test_register_folder_library_missing_folder_or_manifest(self):
        nonexistent = os.path.join(self.test_libraries_root, "NoSuchFolder")
        with self.assertRaises(FileNotFoundError):
            self.manager.register_folder_library(nonexistent)

        empty_folder = os.path.join(self.test_libraries_root, "EmptyFolder")
        os.makedirs(empty_folder, exist_ok=True)
        with self.assertRaises(FileNotFoundError) as ctx:
            self.manager.register_folder_library(empty_folder)
        self.assertIn("library.json", str(ctx.exception))

    def test_register_folder_library_invalid_manifest(self):
        lib_dir = os.path.join(self.test_libraries_root, "CorruptManifest")
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, "library.json"), "w", encoding="utf-8") as f:
            f.write("not valid json {[[")

        with self.assertRaises(ValueError) as ctx:
            self.manager.register_folder_library(lib_dir)
        self.assertIn("invalid json", str(ctx.exception).lower())

        # Test manifest missing display name
        with open(os.path.join(lib_dir, "library.json"), "w", encoding="utf-8") as f:
            json.dump({"_metadata": {}}, f)

        with self.assertRaises(ValueError) as ctx:
            self.manager.register_folder_library(lib_dir)
        self.assertIn("display name", str(ctx.exception).lower())

    def test_register_folder_library_rejects_collision(self):
        lib_dir = os.path.join(self.test_libraries_root, "StockCollision")
        os.makedirs(lib_dir, exist_ok=True)
        with open(os.path.join(lib_dir, "library.json"), "w", encoding="utf-8") as f:
            json.dump({"_metadata": {"name": "Metal", "material": "Steel"}}, f)

        with self.assertRaises(ValueError) as ctx:
            self.manager.register_folder_library(lib_dir)
        self.assertIn("collides with an existing library", str(ctx.exception).lower())

    def test_symlink_manifest_escape_rejected_without_writes(self):
        target_outside = os.path.join(self.test_libraries_root, "outside_target.json")
        with open(target_outside, "w", encoding="utf-8") as f:
            json.dump({"sensitive": "data"}, f)

        lib_dir = os.path.join(self.test_libraries_root, "SymlinkEscape")
        os.makedirs(lib_dir, exist_ok=True)
        symlink_manifest = os.path.join(lib_dir, "library.json")
        os.symlink(target_outside, symlink_manifest)

        # Registration must reject escaping symlink
        with self.assertRaises(ValueError) as ctx:
            self.manager.register_folder_library(lib_dir)
        self.assertIn("escape", str(ctx.exception).lower())

        # Outside file must remain completely untouched
        with open(target_outside, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"sensitive": "data"})

        # create_folder_library must also reject escaping symlink
        lib_dir2 = os.path.join(self.test_libraries_root, "SymlinkEscape2")
        os.makedirs(lib_dir2, exist_ok=True)
        os.symlink(target_outside, os.path.join(lib_dir2, "library.json"))
        with self.assertRaises((FileExistsError, ValueError)):
            self.manager.create_folder_library(
                folder_path=lib_dir2,
                name="ShouldRejectEscape",
            )

        with open(target_outside, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"sensitive": "data"})

    def test_list_libraries_includes_folder_libraries_with_additive_metadata(self):
        # 1. Create a legacy user library
        self.manager.save_user_library("LegacyLib", {"_metadata": {"name": "LegacyLib", "material": "Steel"}})

        # 2. Create a folder library
        folder_dir = os.path.join(self.test_libraries_root, "FolderLib")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="FolderLib",
            material="Wood (Soft)",
            density=0.55,
        )

        libs = self.manager.list_libraries()

        # Legacy library metadata must NOT have folder-specific keys
        legacy_entry = next(lib for lib in libs if lib["name"] == "LegacyLib")
        self.assertNotIn("is_folder", legacy_entry)
        self.assertNotIn("folder_path", legacy_entry)
        self.assertNotIn("can_unregister", legacy_entry)
        self.assertTrue(legacy_entry["can_delete"])

        # Stock library metadata must NOT have folder-specific keys
        stock_entry = next(lib for lib in libs if lib["name"] == "Metal")
        self.assertNotIn("is_folder", stock_entry)
        self.assertNotIn("folder_path", stock_entry)
        self.assertNotIn("can_unregister", stock_entry)
        self.assertFalse(stock_entry["can_delete"])

        # Folder library must have additive keys
        folder_entry = next(lib for lib in libs if lib["name"] == "FolderLib")
        self.assertTrue(folder_entry["is_folder"])
        self.assertEqual(folder_entry["folder_path"], os.path.realpath(folder_dir))
        self.assertTrue(folder_entry["can_unregister"])
        self.assertFalse(folder_entry["can_delete"])
        self.assertTrue(folder_entry["is_user"])
        self.assertEqual(folder_entry["material"], "Wood (Soft)")
        self.assertEqual(folder_entry["density"], 0.55)

    def test_list_libraries_graceful_on_missing_or_unmounted_folder(self):
        folder_dir = os.path.join(self.test_libraries_root, "RemovableDrive")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Removable Lib",
            material="Steel",
        )

        # Simulate drive unmounted / folder deleted
        shutil.rmtree(folder_dir)

        # list_libraries must not crash and must omit missing library
        libs = self.manager.list_libraries()
        names = [lib["name"] for lib in libs]
        self.assertNotIn("Removable Lib", names)

        # Registry on disk must NOT have removed it silently
        with open(self.test_registry_path, "r", encoding="utf-8") as f:
            reg_data = json.load(f)
        self.assertIn(os.path.realpath(folder_dir), reg_data["folders"])

    def test_get_library_loads_folder_catalog(self):
        folder_dir = os.path.join(self.test_libraries_root, "MyCatalog")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="My Catalog",
            material="Aluminium",
            data={
                "Pipe": {
                    "sizes": {
                        "OD50_T2": {
                            "Width": "50",
                            "Height": "50",
                            "Thickness": "2",
                        }
                    }
                }
            },
        )

        loaded = self.manager.get_library("My Catalog")
        self.assertIn("Pipe", loaded)
        self.assertIn("OD50_T2", loaded["Pipe"]["sizes"])
        self.assertEqual(loaded["_metadata"]["name"], "My Catalog")

    def test_save_user_library_routes_to_folder_root_and_preserves_immutability(self):
        folder_dir = os.path.join(self.test_libraries_root, "RoutingLib")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Routing Lib",
            material="Aluminium",
            density=2.70,
        )

        update_data = {
            "Square Hollow": {
                "sizes": {
                    "20x20x2": {"Height": "20", "Width": "20", "Thickness": "2"}
                }
            }
        }

        # Saving by registered folder library name should route to folder library.json
        saved_path = self.manager.save_user_library("Routing Lib", update_data)
        expected_path = os.path.join(os.path.realpath(folder_dir), "library.json")
        self.assertEqual(saved_path, expected_path)

        # Verify no .json file was leaked into legacy self.user_dir
        legacy_files = [f for f in os.listdir(self.test_user_dir) if f.endswith(".json")]
        self.assertEqual(legacy_files, [])

        # Verify manifest content was updated
        with open(expected_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        self.assertIn("Square Hollow", content)
        self.assertEqual(content["_metadata"]["name"], "Routing Lib")
        self.assertEqual(content["_metadata"]["material"], "Aluminium")

        # Verify S4 material immutability: changing material of folder library must be rejected
        with self.assertRaises(ValueError) as ctx:
            self.manager.save_user_library("Routing Lib", update_data, material="Steel")
        self.assertIn("immutable", str(ctx.exception).lower())

    def test_save_failure_leaves_catalog_and_registry_intact(self):
        folder_dir = os.path.join(self.test_libraries_root, "AtomicFolder")
        manifest_path = self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Atomic Folder",
            material="Steel",
        )
        with open(manifest_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        def fail_write(data, stream, **kwargs):
            stream.write('{"corrupted": true')
            raise IOError("Simulated disk error")

        with patch("freecad.maxproframe.library_manager.json.dump", side_effect=fail_write):
            with self.assertRaisesRegex(IOError, "^Simulated disk error$"):
                self.manager.save_user_library("Atomic Folder", {"Pipe": {"sizes": {}}})

        with open(manifest_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)

        # Check no temporary files were left behind in the folder
        entries = os.listdir(folder_dir)
        self.assertEqual(entries, ["library.json"])

    def test_unregister_folder_library_removes_registration_only(self):
        folder_dir = os.path.join(self.test_libraries_root, "KeepFiles")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Keep Files",
            material="Steel",
        )
        manifest_path = os.path.join(folder_dir, "library.json")
        # Add an asset file to simulate sections
        asset_file = os.path.join(folder_dir, "section1.fcstd")
        with open(asset_file, "w") as f:
            f.write("mock fcstd content")

        self.assertTrue(self.manager.unregister_folder_library("Keep Files"))

        # Folder and files must remain completely untouched on disk
        self.assertTrue(os.path.isdir(folder_dir))
        self.assertTrue(os.path.isfile(manifest_path))
        self.assertTrue(os.path.isfile(asset_file))

        # Library should no longer be listed
        libs = self.manager.list_libraries()
        self.assertNotIn("Keep Files", [lib["name"] for lib in libs])

        # Registry file should not contain the path
        with open(self.test_registry_path, "r", encoding="utf-8") as f:
            reg = json.load(f)
        self.assertEqual(reg["folders"], [])

        # Unregistering non-registered library should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            self.manager.unregister_folder_library("Keep Files")

    def test_delete_user_library_rejects_folder_library_with_unregister_diagnostic(self):
        folder_dir = os.path.join(self.test_libraries_root, "ProtectedFolder")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Protected Folder",
            material="Steel",
        )
        manifest_path = os.path.join(folder_dir, "library.json")

        with self.assertRaises(ValueError) as ctx:
            self.manager.delete_user_library("Protected Folder")

        self.assertIn("unregister", str(ctx.exception).lower())
        self.assertTrue(os.path.isfile(manifest_path))

    def test_relocated_bundle_reregister_and_load(self):
        # Create bundle at location 1
        bundle_v1 = os.path.join(self.test_libraries_root, "bundle_v1")
        self.manager.create_folder_library(
            folder_path=bundle_v1,
            name="Portable Bundle",
            material="Aluminium",
            data={
                "Square Hollow": {
                    "sizes": {"60x60x3": {"Height": "60", "Width": "60", "Thickness": "3"}}
                }
            },
        )
        self.manager.unregister_folder_library("Portable Bundle")

        # Relocate bundle to location 2 (e.g. copied to another PC / different folder)
        bundle_v2 = os.path.join(self.test_libraries_root, "bundle_v2_relocated")
        shutil.copytree(bundle_v1, bundle_v2)

        # Register relocated bundle
        res = self.manager.register_folder_library(bundle_v2)
        self.assertEqual(res["name"], "Portable Bundle")

        # Load library and verify all profiles and metadata are available
        data = self.manager.get_library("Portable Bundle")
        self.assertIn("Square Hollow", data)
        self.assertIn("60x60x3", data["Square Hollow"]["sizes"])
        self.assertEqual(data["_metadata"]["name"], "Portable Bundle")

    def test_get_all_profiles_and_material_info_discover_folder_libraries(self):
        folder_dir = os.path.join(self.test_libraries_root, "AllProfilesFolder")
        self.manager.create_folder_library(
            folder_path=folder_dir,
            name="Folder Profiles",
            material="Copper",
            density=8.96,
            data={
                "Round Bar": {
                    "sizes": {"RB20": {"Width": "20", "Height": "20", "Thickness": "0"}}
                }
            },
        )

        all_profiles = self.manager.get_all_profiles()
        self.assertIn("Folder Profiles", all_profiles)
        self.assertIn("Round Bar", all_profiles["Folder Profiles"])
        self.assertNotIn("_metadata", all_profiles["Folder Profiles"])

        mat, dens = self.manager.get_library_material_info("Folder Profiles")
        self.assertEqual(mat, "Copper")
        self.assertEqual(dens, 8.96)


if __name__ == "__main__":
    unittest.main()

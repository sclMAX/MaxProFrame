import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from freecad.maxproframe.library_manager import (
    LibraryManager,
    calculate_linear_weight,
    get_known_families,
    sanitize_library_name,
)


class TestLibraryManager(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary directory for user libraries
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_user_profiles_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)

    def tearDown(self):
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def test_list_libraries_discovers_stock_libraries(self):
        libs = self.manager.list_libraries()
        lib_names = [lib["name"].lower() for lib in libs]

        # Must discover bundled stock libraries
        self.assertIn("metal", lib_names)
        metal_lib = next(lib for lib in libs if lib["name"].lower() == "metal")
        self.assertFalse(metal_lib["is_user"])
        self.assertFalse(metal_lib["can_delete"])

    def test_get_library_loads_stock_content(self):
        data = self.manager.get_library("Metal")
        self.assertIsInstance(data, dict)
        self.assertIn("Square Hollow", data)
        self.assertIn("sizes", data["Square Hollow"])

    def test_stock_alias_resolution_preserves_stock_access(self):
        # User creates a library "Metal!" whose slug is "metal.json"
        user_data = {
            "_metadata": {"name": "Metal!"},
            "CustomMetalFamily": {"sizes": {"CM1": {"Height": "10"}}},
        }
        self.manager.save_user_library("Metal!", user_data)
        # Verify get_library("Metal") still resolves stock catalog
        stock_metal = self.manager.get_library("Metal")
        self.assertIn("Square Hollow", stock_metal)
        self.assertNotIn("CustomMetalFamily", stock_metal)

        # And get_library("Metal!") resolves user catalog
        user_metal = self.manager.get_library("Metal!")
        self.assertIn("CustomMetalFamily", user_metal)
        self.assertEqual(user_metal.get("_metadata", {}).get("name"), "Metal!")

    def test_save_and_load_user_library(self):
        sample_data = {
            "Square Hollow": {
                "norm": "Indumatics Std",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": "1.037",
                    }
                },
            }
        }

        saved_path = self.manager.save_user_library("Indumatics Aluminio", sample_data)
        self.assertTrue(os.path.exists(saved_path))

        # Check listed libraries
        libs = self.manager.list_libraries()
        indumatics = next((lib for lib in libs if lib["name"] == "Indumatics Aluminio"), None)
        self.assertIsNotNone(indumatics)
        self.assertTrue(indumatics["is_user"])
        self.assertTrue(indumatics["can_delete"])

        # Check content retrieved
        loaded = self.manager.get_library("Indumatics Aluminio")
        self.assertEqual(loaded, sample_data)

    def test_atomic_save_preserves_original_on_write_failure(self):
        original_data = {"Square": {"sizes": {"original": {"Height": "10"}}}}
        target_path = self.manager.save_user_library("AtomicTestLib", original_data)
        with open(target_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        def fail_write(data, stream, **kwargs):
            stream.write('{"partial":')
            raise IOError("Simulated disk full")

        with patch("freecad.maxproframe.library_manager.json.dump", side_effect=fail_write):
            with self.assertRaisesRegex(IOError, "^Simulated disk full$"):
                self.manager.save_user_library("AtomicTestLib", {"Square": {"sizes": {}}})

        with open(target_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)
        self.assertEqual(self.manager.get_library("AtomicTestLib"), original_data)
        self.assertEqual(os.listdir(self.test_user_dir), [os.path.basename(target_path)])

    def test_duplicate_library(self):
        # Duplicate stock 'Wood' or 'Metal' to a custom user library
        dup_name = "Metal Modificado"
        self.manager.duplicate_library("Metal", dup_name)

        libs = self.manager.list_libraries()
        dup_lib = next((lib for lib in libs if lib["name"] == dup_name), None)
        self.assertIsNotNone(dup_lib)
        self.assertTrue(dup_lib["is_user"])

    def test_duplicate_library_with_material_recalculation(self):
        steel_data = {
            "_metadata": {"name": "SteelSource", "material": "Steel", "density": 7.85},
            "Square Hollow": {
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Weight": "2.983",
                    }
                },
            },
        }
        self.manager.save_user_library("SteelSource", steel_data)

        self.manager.duplicate_library(
            "SteelSource",
            "AluTarget",
            target_material="Aluminium",
            target_density=2.70,
            recalculate_weights=True,
        )

        alu_lib = self.manager.get_library("AluTarget")
        self.assertEqual(alu_lib["_metadata"]["material"], "Aluminium")
        self.assertEqual(alu_lib["_metadata"]["density"], 2.70)
        recalc_w = float(alu_lib["Square Hollow"]["sizes"]["50x50x2"]["Weight"])
        self.assertAlmostEqual(recalc_w, 1.037, places=2)

    def test_malformed_metadata_density_does_not_crash_list_libraries(self):
        malformed_data = {
            "_metadata": {"name": "BadDensityLib", "material": "Steel", "density": "invalid_number"},
            "Square": {"sizes": {}},
        }
        # First save with valid metadata
        self.manager.save_user_library("BadDensityLib", {"_metadata": {"name": "BadDensityLib"}, "Square": {"sizes": {}}})
        # Directly inject corrupt density in file to test parsing resilience
        path = os.path.join(self.test_user_dir, "baddensitylib.json")
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(malformed_data, f)

        libs = self.manager.list_libraries()
        bad_lib = next(lib for lib in libs if lib["name"] == "BadDensityLib")
        self.assertIsInstance(bad_lib["density"], float)
        self.assertEqual(bad_lib["density"], 7.85)

    def test_partial_legacy_aluminium_metadata_resolves_2_70_density(self):
        partial_data = {
            "_metadata": {"name": "PipesWithoutKeyword", "material": "Aluminium"},
            "Pipe": {"sizes": {}},
        }
        self.manager.save_user_library("PipesWithoutKeyword", partial_data)
        libs = self.manager.list_libraries()
        lib_entry = next(lib for lib in libs if lib["name"] == "PipesWithoutKeyword")
        self.assertEqual(lib_entry["material"], "Aluminium")
        self.assertEqual(lib_entry["density"], 2.70)
        getter_mat, getter_dens = self.manager.get_library_material_info("PipesWithoutKeyword")
        self.assertEqual(getter_mat, "Aluminium")
        self.assertEqual(getter_dens, 2.70)

    def test_save_user_library_enforces_s4_material_immutability(self):
        initial_data = {
            "_metadata": {"name": "ImmutableLib", "material": "Aluminium", "density": 2.70},
            "Square": {"sizes": {}},
        }
        self.manager.save_user_library("ImmutableLib", initial_data)
        with self.assertRaises(ValueError):
            self.manager.save_user_library("ImmutableLib", initial_data, material="Steel")

    def test_cannot_create_user_library_colliding_with_stock_name(self):
        with self.assertRaises(ValueError) as ctx:
            self.manager.save_user_library("Metal", {"_metadata": {"name": "Metal"}})
        self.assertIn("reserved system library name", str(ctx.exception))

    def test_duplicate_library_with_unsupported_family_recalculation_fails_cleanly(self):
        tslot_data = {
            "_metadata": {"name": "TSlotSource", "material": "Aluminium", "density": 2.70},
            "T-Slot": {"sizes": {"TS1": {"Height": "20", "Width": "20", "Thickness": "2", "Weight": "0.5"}}},
        }
        self.manager.save_user_library("TSlotSource", tslot_data)
        with self.assertRaises(ValueError) as ctx:
            self.manager.duplicate_library(
                "TSlotSource", "TSlotClone", target_material="Steel", recalculate_weights=True
            )
        self.assertIn("Cannot recalculate weights for unsupported complex families", str(ctx.exception))

    def test_delete_user_library(self):
        dummy_data = {"Square": {"norm": "-", "sizes": {}}}
        self.manager.save_user_library("Temporal", dummy_data)

        self.assertTrue(self.manager.delete_user_library("Temporal"))

        libs = self.manager.list_libraries()
        self.assertIsNone(next((lib for lib in libs if lib["name"] == "Temporal"), None))

    def test_delete_stock_library_forbidden(self):
        with self.assertRaises(ValueError):
            self.manager.delete_user_library("Metal")

    def test_sanitize_library_name(self):
        self.assertEqual(sanitize_library_name("../evil/path"), "evil_path")
        self.assertEqual(sanitize_library_name("Indumatics Aluminio"), "indumatics_aluminio")
        self.assertEqual(sanitize_library_name("Special @# Char"), "special_char")

    def test_get_all_profiles_dict(self):
        # Combined dictionary matching create_profiles_tool format
        all_profiles = self.manager.get_all_profiles()
        self.assertIn("Metal", all_profiles)

        # Add user library and verify it appears in get_all_profiles
        self.manager.save_user_library("CustomLib", {"Square": {"sizes": {}}})
        all_profiles_after = self.manager.get_all_profiles()
        self.assertIn("CustomLib", all_profiles_after)

    def test_calculate_linear_weight(self):
        # Aluminum density approx 2.7 g/cm3 (0.0027 g/mm3)
        # Tube 50x50x2 mm: Outer area = 2500, Inner area = 46x46 = 2116.
        # Section area = 384 mm2.
        # Volume per meter (1000 mm) = 384,000 mm3 = 384 cm3.
        # Weight = 384 * 2.7 = 1036.8 g = 1.037 kg/m.
        weight = calculate_linear_weight(
            family="Square Hollow",
            width=50.0,
            height=50.0,
            thickness=2.0,
            density_g_cm3=2.7,
        )
        self.assertAlmostEqual(weight, 1.037, places=2)

        # Round Pipe OD 50mm, thickness 2mm
        # Outer radius 25, inner radius 23.
        # Area = pi * (25^2 - 23^2) = pi * (625 - 529) = 96 * pi approx 301.59 mm2.
        # Volume per meter = 301.59 cm3.
        # Weight steel (7.85 g/cm3) = 301.59 * 7.85 / 1000 = 2.367 kg/m.
        weight_pipe = calculate_linear_weight(
            family="Pipe",
            width=50.0,
            height=50.0,
            thickness=2.0,
            density_g_cm3=7.85,
        )
        self.assertAlmostEqual(weight_pipe, 2.37, places=2)

    def test_calculate_linear_weight_rejects_unsupported_geometry(self):
        for family in ("T-Slot", "V-Slot", "Custom Profile", "Arbitrary Slotted Profile"):
            with self.subTest(family=family):
                with self.assertRaises(ValueError) as error:
                    calculate_linear_weight(family, 50, 50, 2)
                self.assertEqual(
                    str(error.exception),
                    f"Theoretical weight calculation is not supported for complex or slotted geometry '{family}'. Please enter weight manually.",
                )

    def test_calculate_linear_weight_preserves_standard_sections(self):
        for family in ("HEA", "HEB", "HEM", "IPE", "IPN", "UPE", "UPN"):
            with self.subTest(family=family):
                self.assertEqual(calculate_linear_weight(family, 50, 50, 2), 19.625)

    def test_save_collision_rejection(self):
        data1 = {"Square": {"sizes": {"orig": {"Height": "10", "Width": "10", "Thickness": "1"}}}}
        data2 = {"Square": {"sizes": {"new": {"Height": "20", "Width": "20", "Thickness": "2"}}}}

        self.manager.save_user_library("Shop A", data1, overwrite=False)

        # 'Shop_A' sanitizes to same filename 'shop_a.json'
        with self.assertRaises(FileExistsError):
            self.manager.save_user_library("Shop_A", data2, overwrite=False)

        # Assert original catalog is unchanged
        loaded = self.manager.get_library("Shop A")
        self.assertIn("orig", loaded["Square"]["sizes"])
        self.assertNotIn("new", loaded["Square"]["sizes"])

    def test_wood_density_calculations(self):
        from freecad.maxproframe.library_manager import STANDARD_DENSITIES

        # Beam 100x100 mm: Area = 10000 mm2 = 100 cm3 per 1000mm length
        weight_soft = calculate_linear_weight("Square", 100.0, 100.0, 0, STANDARD_DENSITIES["Wood (Soft)"])
        weight_hard = calculate_linear_weight("Square", 100.0, 100.0, 0, STANDARD_DENSITIES["Wood (Hard)"])

        self.assertEqual(weight_soft, 5.5)  # 100 * 0.55 = 55.0 / 10 = 5.5 kg/m
        self.assertEqual(weight_hard, 7.5)  # 100 * 0.75 = 75.0 / 10 = 7.5 kg/m
        self.assertNotEqual(weight_soft, 27.0)  # Must NOT be aluminium density 2.70


if __name__ == "__main__":
    unittest.main()

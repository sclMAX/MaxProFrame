import json
import os
import shutil
import tempfile
import unittest

from freecad.frameforge.library_manager import (
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

    def test_duplicate_library(self):
        # Duplicate stock 'Wood' or 'Metal' to a custom user library
        dup_name = "Metal Modificado"
        self.manager.duplicate_library("Metal", dup_name)

        libs = self.manager.list_libraries()
        dup_lib = next((lib for lib in libs if lib["name"] == dup_name), None)
        self.assertIsNotNone(dup_lib)
        self.assertTrue(dup_lib["is_user"])

        dup_data = self.manager.get_library(dup_name)
        self.assertIn("Square Hollow", dup_data)

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


if __name__ == "__main__":
    unittest.main()

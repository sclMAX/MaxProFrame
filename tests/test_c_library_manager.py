import math
import os
import shutil
import tempfile
import unittest

from freecad.frameforge.library_manager import (
    FILLET_FAMILIES,
    KNOWN_FAMILIES,
    LibraryManager,
    calculate_linear_weight,
    get_canonical_family,
)


class TestCLibraryManager(unittest.TestCase):
    """
    S1-S2, T1: Unit tests for C profile library registration, theoretical weight calculation,
    and catalog auto-mass recalculation.
    """

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_c_user_profiles_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)

    def tearDown(self):
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir, ignore_errors=True)

    def test_c_registered_in_known_and_fillet_families(self):
        """S1: Canonical family 'C' must be registered in KNOWN_FAMILIES and FILLET_FAMILIES."""
        self.assertIn("C", KNOWN_FAMILIES)
        self.assertIn("C", FILLET_FAMILIES)

    def test_calculate_linear_weight_plain_c_profile(self):
        """
        S1: Plain C profile area formula e*(H+2B+2L-4e).
        Fixture H=100, B=50, e=2, L=15, density=7.85 g/cm3.
        Plain area = 2 * (100 + 2*50 + 2*15 - 4*2) = 444 mm2.
        Linear weight = 444 * 7.85 / 1000 = 3.4854 -> 3.485 kg/m.
        """
        weight = calculate_linear_weight(
            family="C",
            width=50.0,
            height=100.0,
            thickness=2.0,
            density_g_cm3=7.85,
            lip_length=15.0,
            make_fillet=False,
        )
        self.assertEqual(weight, 3.485)

    def test_calculate_linear_weight_filleted_c_profile(self):
        """
        S1, S2: Filleted C profile subtracts (4-pi)*(R^2-(R-e)^2).
        Fixture H=100, B=50, e=2, L=15, Rext=4, density=7.85 g/cm3.
        r_int = Rext - e = 2.
        Delta = (4 - pi) * (16 - 4) = 12 * (4 - pi) = 10.300888... mm2.
        Filleted area = 444 - 10.300888... = 433.69911... mm2.
        Linear weight = 433.69911... * 7.85 / 1000 = 3.4045... -> 3.405 kg/m.
        """
        weight = calculate_linear_weight(
            family="C",
            width=50.0,
            height=100.0,
            thickness=2.0,
            density_g_cm3=7.85,
            lip_length=15.0,
            radius=4.0,
            make_fillet=True,
        )
        self.assertEqual(weight, 3.405)

    def test_calculate_linear_weight_c_rejects_missing_or_invalid_lip(self):
        """S1: C profile requires valid positive lip_length; missing or <=0 must fail."""
        with self.assertRaises(ValueError) as ctx_none:
            calculate_linear_weight(
                family="C",
                width=50.0,
                height=100.0,
                thickness=2.0,
                lip_length=None,
            )
        self.assertIn("lip", str(ctx_none.exception).lower())

        with self.assertRaises(ValueError) as ctx_zero:
            calculate_linear_weight(
                family="C",
                width=50.0,
                height=100.0,
                thickness=2.0,
                lip_length=0.0,
            )
        self.assertIn("lip", str(ctx_zero.exception).lower())

    def test_calculate_linear_weight_c_rejects_impossible_dimensions(self):
        """S1, S2: Explicit rejection of degenerate C profile dimensions."""
        # Thickness >= width / 2
        with self.assertRaises(ValueError):
            calculate_linear_weight("C", width=10.0, height=100.0, thickness=6.0, lip_length=15.0)

        # Lip length <= thickness
        with self.assertRaises(ValueError):
            calculate_linear_weight("C", width=50.0, height=100.0, thickness=5.0, lip_length=5.0)

        # Lips collide (2*L >= H)
        with self.assertRaises(ValueError):
            calculate_linear_weight("C", width=50.0, height=100.0, thickness=2.0, lip_length=55.0)

        # Filleted: Rext <= thickness (interior radius <= 0)
        with self.assertRaises(ValueError):
            calculate_linear_weight(
                "C", width=50.0, height=100.0, thickness=3.0, lip_length=15.0, radius=3.0, make_fillet=True
            )

        # Filleted: Rext > lip_length
        with self.assertRaises(ValueError):
            calculate_linear_weight(
                "C", width=50.0, height=100.0, thickness=2.0, lip_length=10.0, radius=12.0, make_fillet=True
            )

    def test_duplicate_library_with_recalculate_c_profiles(self):
        """
        S1, S2: library_manager auto-mass recalculation correctly reads C dimensions,
        Lip Length, Radius1, and fillet flag without changing legacy approximations.
        """
        c_library_data = {
            "_metadata": {"name": "CSourceLib", "material": "Steel", "density": 7.85},
            "C (Fillet)": {
                "canonical_family": "C",
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": True,
                "sizes": {
                    "100x50x15x2": {
                        "Height": "100",
                        "Width": "50",
                        "Thickness": "2",
                        "Lip Length": "15",
                        "Radius1": "4",
                        "Weight": "3.405",
                    }
                },
            },
            "C": {
                "canonical_family": "C",
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "100x50x15x2": {
                        "Height": "100",
                        "Width": "50",
                        "Thickness": "2",
                        "Lip Length": "15",
                        "Radius1": "0",
                        "Weight": "3.485",
                    }
                },
            },
            "Square Hollow": {
                "canonical_family": "Square Hollow",
                "norm": "EN",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Weight": "3.014",
                    }
                },
            },
        }

        self.manager.save_user_library("CSourceLib", c_library_data)
        # Duplicate to Aluminium (density 2.70 g/cm3)
        self.manager.duplicate_library(
            "CSourceLib", "CAluLib", target_material="Aluminium", recalculate_weights=True
        )

        cloned = self.manager.get_library("CAluLib")
        # Check C filleted recalculation:
        # Area = 433.69911 mm2 * 2.70 / 1000 = 1.17098... -> 1.171 kg/m
        self.assertEqual(float(cloned["C (Fillet)"]["sizes"]["100x50x15x2"]["Weight"]), 1.171)

        # Check C plain recalculation:
        # Area = 444 mm2 * 2.70 / 1000 = 1.1988 -> 1.199 kg/m
        self.assertEqual(float(cloned["C"]["sizes"]["100x50x15x2"]["Weight"]), 1.199)

        # Check that Square Hollow recalculated as normal:
        # Area = (50*50 - 46*46) = 384 mm2 * 2.70 / 1000 = 1.0368 -> 1.037 kg/m
        self.assertEqual(float(cloned["Square Hollow"]["sizes"]["50x50x2"]["Weight"]), 1.037)

    def test_calculate_linear_weight_preserves_existing_families(self):
        """Preserve: existing calculations for other families remain unchanged."""
        # Square Hollow
        w_sq = calculate_linear_weight("Square Hollow", 50, 50, 2, density_g_cm3=2.7)
        self.assertAlmostEqual(w_sq, 1.037, places=2)

        # Channels
        w_ch = calculate_linear_weight("Channels", 50, 100, 4, density_g_cm3=7.85, flange_thickness=6)
        # Web: (100 - 2*6)*4 = 88*4 = 352. Flanges: 2*50*6 = 600. Total = 952 mm2.
        # Weight = 952 * 7.85 / 1000 = 7.473 kg/m.
        self.assertEqual(w_ch, 7.473)

    def test_duplicate_library_preserves_non_c_with_irrelevant_radius_text(self):
        """
        Preserve, L5: Non-C families with non-numeric Radius1 or Lip Length text
        (e.g. '-' or 'N/A') must not crash duplicate_library weight recalculation.
        """
        lib_data = {
            "_metadata": {"name": "TextRadiusLib", "material": "Steel", "density": 7.85},
            "Square Hollow": {
                "canonical_family": "Square Hollow",
                "norm": "EN",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Radius1": "N/A",
                        "Lip Length": "-",
                        "Weight": "3.014",
                    }
                },
            },
        }
        self.manager.save_user_library("TextRadiusLib", lib_data)
        self.manager.duplicate_library(
            "TextRadiusLib", "TextRadiusClone", target_material="Aluminium", recalculate_weights=True
        )
        cloned = self.manager.get_library("TextRadiusClone")
        # Area = (50*50 - 46*46) = 384 mm2 * 2.70 / 1000 = 1.0368 -> 1.037 kg/m
        self.assertEqual(float(cloned["Square Hollow"]["sizes"]["50x50x2"]["Weight"]), 1.037)

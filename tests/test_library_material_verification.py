import json
import tempfile
import unittest
from pathlib import Path

from freecad.frameforge.library_manager import (
    LibraryManager,
    STANDARD_DENSITIES,
)


class TestMaterialVerification(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manager = LibraryManager(
            user_dir=str(self.root),
            stock_dir=str(self.root / "stock"),
        )

    def test_metadata_fallback_and_lookup_agree(self):
        # S1: explicit material takes priority over name inference.
        path = self.root / "aluminium.json"
        for material, expected_density in STANDARD_DENSITIES.items():
            for density in (None, "bad", "", {}, []):
                with self.subTest(material=material, density=density):
                    metadata = {"name": "Aluminium", "material": material}
                    if density is not None:
                        metadata["density"] = density
                    path.write_text(json.dumps({"_metadata": metadata}))
                    before = path.read_bytes()
                    library = self.manager.list_libraries()[0]
                    expected = (material, expected_density)
                    self.assertEqual(
                        (library["material"], library["density"]), expected
                    )
                    self.assertEqual(
                        self.manager.get_library_material_info("Aluminium"),
                        expected,
                    )
                    self.assertEqual(path.read_bytes(), before)

    def test_explicit_material_is_immutable(self):
        # S4: both entry paths reject changes without rewriting data.
        path = Path(self.manager.save_user_library(
            "Copper", {}, material="Copper"
        ))
        before = path.read_bytes()
        message = (
            "Library material is immutable. Cannot change material of "
            "'Copper' from 'Copper' to 'Steel'. Use duplicate_library instead."
        )
        for data, kwargs in (
            ({}, {"material": "Steel"}),
            ({"_metadata": {"material": "Steel"}}, {}),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError) as caught:
                    self.manager.save_user_library("Copper", data, **kwargs)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(path.read_bytes(), before)

    def test_inferred_legacy_material_is_immutable(self):
        # S4: legacy material must also stay locked.
        path = self.root / "aluminium.json"
        path.write_text(json.dumps({"_metadata": {"name": "Aluminium"}}))
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            self.manager.save_user_library(
                "Aluminium", {}, material="Steel"
            )
        self.assertEqual(path.read_bytes(), before)

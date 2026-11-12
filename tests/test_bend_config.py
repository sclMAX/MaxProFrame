"""Bend configurations of folded miters (odd/tasks/folded-miter.md, T1: S6, S11).

Each configuration (name, material, wall thickness, inside bend radius, K-factor) persists between sessions in a
versioned JSON file next to the profile libraries, written atomically; the last used one lives in FreeCAD params.
"""

import json
import os
import shutil
import tempfile
import unittest

from freecad.maxproframe.bend_config import (
    BendConfiguration,
    BendConfigurationStore,
    get_last_used_configuration,
    set_last_used_configuration,
)
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.library_manager import LibraryManager

STEEL = BendConfiguration("Steel 40x40x2", "Steel", 2.0, 3.0, 0.4)


class BendConfigurationStoreTest(unittest.TestCase):
    def setUp(self):
        self.user_dir = tempfile.mkdtemp(prefix="mpf_bend_config_")
        self.store = BendConfigurationStore(user_dir=self.user_dir)

    def tearDown(self):
        shutil.rmtree(self.user_dir, ignore_errors=True)

    def reopened(self):
        """A store opened again, as in a later FreeCAD session."""
        return BendConfigurationStore(user_dir=self.user_dir)

    def stored_bytes(self):
        with open(self.store.path, "rb") as handle:
            return handle.read()

    def test_saved_configurations_persist_between_sessions(self):
        aluminium = BendConfiguration("Alu 30x20x1.5", "Aluminium", 1.5, 1.5, 0.33)
        self.store.save(STEEL)
        self.store.save(aluminium)

        reopened = self.reopened()
        self.assertEqual([aluminium, STEEL], reopened.configurations())
        self.assertEqual(STEEL, reopened.get("Steel 40x40x2"))

    def test_file_is_versioned_json_next_to_the_profile_libraries(self):
        self.store.save(STEEL)

        self.assertEqual(
            os.path.realpath(self.user_dir), os.path.realpath(os.path.dirname(os.path.dirname(self.store.path)))
        )
        with open(self.store.path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(1, data["version"])
        self.assertEqual(
            [{"name": "Steel 40x40x2", "material": "Steel", "thickness": 2.0, "inside_radius": 3.0, "k_factor": 0.4}],
            data["configurations"],
        )

    def test_the_file_is_not_listed_as_a_profile_library(self):
        self.store.save(STEEL)

        names = [
            library["name"] for library in LibraryManager(user_dir=self.user_dir).list_libraries() if library["is_user"]
        ]
        self.assertEqual([], names)

    def test_no_file_means_no_configurations(self):
        self.assertEqual([], self.store.configurations())
        self.assertIsNone(self.store.get("Steel 40x40x2"))
        self.assertFalse(os.path.exists(self.store.path))

    def test_saving_an_existing_name_replaces_it(self):
        self.store.save(STEEL)
        thicker = BendConfiguration("Steel 40x40x2", "Steel", 2.5, 4.0, 0.45)

        self.store.save(thicker)

        self.assertEqual([thicker], self.reopened().configurations())

    def test_delete_removes_one_configuration(self):
        aluminium = BendConfiguration("Alu 30x20x1.5", "Aluminium", 1.5, 1.5, 0.33)
        self.store.save(STEEL)
        self.store.save(aluminium)

        self.store.delete("Steel 40x40x2")

        self.assertEqual([aluminium], self.reopened().configurations())

    def test_delete_of_an_unknown_name_is_rejected_and_keeps_the_file(self):
        self.store.save(STEEL)
        before = self.stored_bytes()

        with self.assertRaises(KeyError) as raised:
            self.store.delete("Missing")

        self.assertEqual("'Bend configuration \"Missing\" does not exist.'", str(raised.exception))
        self.assertEqual(before, self.stored_bytes())

    def test_save_is_atomic_and_leaves_no_temporary_files(self):
        self.store.save(STEEL)
        self.store.save(BendConfiguration("Other", "Steel", 1.0, 1.0, 0.5))

        self.assertEqual(["configurations.json"], sorted(os.listdir(os.path.dirname(self.store.path))))

    def test_invalid_configurations_are_rejected_and_the_file_is_unchanged(self):
        self.store.save(STEEL)
        before = self.stored_bytes()
        cases = [
            (("", "Steel", 2.0, 3.0, 0.4), "The configuration name must not be empty."),
            (("  ", "Steel", 2.0, 3.0, 0.4), "The configuration name must not be empty."),
            (("Bad", "", 2.0, 3.0, 0.4), "The material must not be empty."),
            (("Bad", "Steel", 0.0, 3.0, 0.4), "The wall thickness must be greater than 0 mm."),
            (("Bad", "Steel", float("nan"), 3.0, 0.4), "The wall thickness must be greater than 0 mm."),
            (("Bad", "Steel", "two", 3.0, 0.4), "The wall thickness must be greater than 0 mm."),
            (("Bad", "Steel", 2.0, 1.9, 0.4), "The inside bend radius must be at least the wall thickness (2 mm)."),
            (
                ("Bad", "Steel", 2.0, float("inf"), 0.4),
                "The inside bend radius must be at least the wall thickness (2 mm).",
            ),
            (("Bad", "Steel", 2.0, 3.0, -0.1), "The K-factor must be between 0 and 1."),
            (("Bad", "Steel", 2.0, 3.0, 1.1), "The K-factor must be between 0 and 1."),
        ]
        for values, message in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError) as raised:
                    self.store.save(BendConfiguration(*values))
                self.assertEqual(message, str(raised.exception))
                self.assertEqual(before, self.stored_bytes())
        self.assertEqual([STEEL], self.reopened().configurations())

    def test_boundary_values_are_accepted(self):
        lower = BendConfiguration("Radius equals thickness", "Steel", 2.0, 2.0, 0.0)
        upper = BendConfiguration("K one", "Steel", 2.0, 2.0, 1.0)

        self.store.save(lower)
        self.store.save(upper)

        self.assertEqual([upper, lower], self.reopened().configurations())

    def test_names_are_trimmed(self):
        self.store.save(BendConfiguration("  Steel 40x40x2 ", " Steel ", 2, 3, 0.4))

        self.assertEqual([STEEL], self.reopened().configurations())

    def test_corrupt_file_is_reported_and_kept(self):
        os.makedirs(os.path.dirname(self.store.path))
        with open(self.store.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        with self.assertRaises(ValueError) as raised:
            self.store.configurations()
        self.assertTrue(str(raised.exception).startswith(f"Corrupt bend configurations file '{self.store.path}':"))
        with self.assertRaises(ValueError):
            self.store.save(STEEL)
        with open(self.store.path, encoding="utf-8") as handle:
            self.assertEqual("{not json", handle.read())

    def test_invalid_entry_in_the_file_is_reported(self):
        os.makedirs(os.path.dirname(self.store.path))
        with open(self.store.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "configurations": [{"name": "X", "material": "Steel", "thickness": -1}]}, handle)

        with self.assertRaises(ValueError) as raised:
            self.store.configurations()
        self.assertEqual(
            f"Corrupt bend configurations file '{self.store.path}': The wall thickness must be greater than 0 mm.",
            str(raised.exception),
        )

    def test_newer_file_version_is_refused(self):
        os.makedirs(os.path.dirname(self.store.path))
        with open(self.store.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 2, "configurations": []}, handle)

        with self.assertRaises(ValueError) as raised:
            self.store.configurations()
        self.assertEqual(
            f"Bend configurations file '{self.store.path}' has version 2; this MaxProFrame reads version 1.",
            str(raised.exception),
        )


class LastUsedConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.params = get_param_group()
        self.previous = self.params.GetString("LastBendConfiguration", "")

    def tearDown(self):
        self.params.SetString("LastBendConfiguration", self.previous)

    def test_last_used_configuration_is_kept_in_freecad_params(self):
        set_last_used_configuration("Steel 40x40x2")

        self.assertEqual("Steel 40x40x2", get_last_used_configuration())
        self.assertEqual("Steel 40x40x2", self.params.GetString("LastBendConfiguration"))

    def test_without_a_last_used_configuration_the_answer_is_empty(self):
        self.params.RemString("LastBendConfiguration")

        self.assertEqual("", get_last_used_configuration())


if __name__ == "__main__":
    unittest.main()

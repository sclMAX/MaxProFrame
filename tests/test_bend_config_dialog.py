"""Bend Configurations dialog (odd/tasks/folded-miter.md, T6: S6, the store of S11).

The dialog lists the stored bend configurations and adds, edits, renames and deletes them through
BendConfigurationStore; an invalid configuration shows the store's message and nothing is saved.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from miter_helpers import use_language
from PySide import QtWidgets

from freecad.maxproframe import bend_config_dialog
from freecad.maxproframe.bend_config import BendConfiguration, BendConfigurationStore
from freecad.maxproframe.bend_config_dialog import BendConfigurationsCommand, BendConfigurationsDialog

STEEL = BendConfiguration("Steel 50x50x2", "Steel", 2.0, 3.0, 0.4)
ALU = BendConfiguration("Alu 3", "Aluminium", 3.0, 4.0, 0.33)


class DialogFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        use_language(self, "English", "en_US")
        self.folder = tempfile.mkdtemp(prefix="mpf_bend_dialog_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.store = BendConfigurationStore(self.folder)

    def open_dialog(self, *configurations):
        for configuration in configurations:
            self.store.save(configuration)
        dialog = BendConfigurationsDialog(store=self.store)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def fill(self, dialog, configuration):
        dialog.edit_name.setText(configuration.name)
        dialog.edit_material.setText(configuration.material)
        dialog.spin_thickness.setValue(configuration.thickness)
        dialog.spin_radius.setValue(configuration.inside_radius)
        dialog.spin_k_factor.setValue(configuration.k_factor)

    def shown(self, dialog):
        return BendConfiguration(
            dialog.edit_name.text(),
            dialog.edit_material.text(),
            dialog.spin_thickness.value(),
            dialog.spin_radius.value(),
            dialog.spin_k_factor.value(),
        )

    def listed(self, dialog):
        return [dialog.list_configurations.item(row).text() for row in range(dialog.list_configurations.count())]


class ListTest(DialogFixture):
    def test_lists_the_stored_configurations_by_name_and_shows_the_first(self):
        dialog = self.open_dialog(STEEL, ALU)

        self.assertEqual(["Alu 3", "Steel 50x50x2"], self.listed(dialog))
        self.assertEqual(ALU, self.shown(dialog))
        self.assertEqual("", dialog.message_label.text())

    def test_selecting_a_configuration_shows_it(self):
        dialog = self.open_dialog(STEEL, ALU)

        dialog.select(STEEL.name)

        self.assertEqual(STEEL, self.shown(dialog))
        self.assertTrue(dialog.button_delete.isEnabled())

    def test_corrupt_file_shows_the_store_message(self):
        os.makedirs(os.path.dirname(self.store.path))
        with open(self.store.path, "w", encoding="utf-8") as handle:
            handle.write("{")

        dialog = self.open_dialog()

        self.assertIn("Corrupt bend configurations file", dialog.message_label.text())
        self.assertEqual([], self.listed(dialog))


class SaveTest(DialogFixture):
    def test_new_configuration_is_added_and_selected(self):
        dialog = self.open_dialog(STEEL)

        dialog.new()
        self.assertEqual("", dialog.edit_name.text())
        self.fill(dialog, ALU)
        self.assertTrue(dialog.save())

        self.assertEqual([ALU, STEEL], self.store.configurations())
        self.assertEqual(["Alu 3", "Steel 50x50x2"], self.listed(dialog))
        self.assertEqual("Alu 3", dialog.list_configurations.currentItem().text())
        self.assertEqual("", dialog.message_label.text())

    def test_editing_a_configuration_replaces_it(self):
        dialog = self.open_dialog(STEEL, ALU)
        dialog.select(STEEL.name)

        dialog.spin_radius.setValue(4.5)
        self.assertTrue(dialog.save())

        self.assertEqual(4.5, self.store.get(STEEL.name).inside_radius)
        self.assertEqual(2, len(self.store.configurations()))

    def test_renaming_a_configuration_replaces_the_old_name(self):
        dialog = self.open_dialog(STEEL, ALU)
        dialog.select(STEEL.name)

        dialog.edit_name.setText("Steel r3")
        self.assertTrue(dialog.save())

        self.assertEqual(["Alu 3", "Steel r3"], [configuration.name for configuration in self.store.configurations()])
        self.assertEqual(["Alu 3", "Steel r3"], self.listed(dialog))

    def test_invalid_configuration_shows_the_store_message_and_saves_nothing(self):
        for field, value, message in (
            ("edit_name", "  ", "The configuration name must not be empty."),
            ("edit_material", "", "The material must not be empty."),
            ("spin_thickness", 0.0, "The wall thickness must be greater than 0 mm."),
            ("spin_radius", 1.5, "The inside bend radius must be at least the wall thickness (2 mm)."),
        ):
            with self.subTest(field=field):
                dialog = self.open_dialog()
                dialog.new()
                self.fill(dialog, STEEL)
                widget = getattr(dialog, field)
                widget.setText(value) if field.startswith("edit") else widget.setValue(value)

                self.assertFalse(dialog.save())

                self.assertEqual(message, dialog.message_label.text())
                self.assertFalse(os.path.exists(self.store.path))
                self.assertEqual([], self.listed(dialog))

    def test_invalid_edit_leaves_the_stored_configuration_as_it_was(self):
        dialog = self.open_dialog(STEEL)
        dialog.select(STEEL.name)

        dialog.spin_radius.setValue(1.0)

        self.assertFalse(dialog.save())
        self.assertEqual(STEEL, self.store.get(STEEL.name))


class DeleteTest(DialogFixture):
    def test_delete_removes_the_selected_configuration_once_confirmed(self):
        dialog = self.open_dialog(STEEL, ALU)
        dialog.select(STEEL.name)

        with patch.object(BendConfigurationsDialog, "confirm_delete", return_value=True):
            self.assertTrue(dialog.delete())

        self.assertEqual([ALU], self.store.configurations())
        self.assertEqual(["Alu 3"], self.listed(dialog))

    def test_delete_not_confirmed_keeps_it(self):
        dialog = self.open_dialog(STEEL, ALU)
        dialog.select(STEEL.name)

        with patch.object(BendConfigurationsDialog, "confirm_delete", return_value=False):
            self.assertFalse(dialog.delete())

        self.assertEqual([ALU, STEEL], self.store.configurations())

    def test_delete_is_disabled_for_a_new_configuration(self):
        dialog = self.open_dialog(STEEL)

        dialog.new()

        self.assertFalse(dialog.button_delete.isEnabled())


class CommandTest(DialogFixture):
    def test_command_opens_the_dialog_on_the_user_store(self):
        self.store.save(STEEL)
        opened = []

        def record(dialog):
            opened.append(dialog)
            return 0

        with (
            patch.dict(os.environ, {"MAXPROFRAME_USER_PROFILES_DIR": self.folder}),
            patch.object(bend_config_dialog.BendConfigurationsDialog, "exec_", record),
        ):
            self.assertTrue(BendConfigurationsCommand().IsActive())
            BendConfigurationsCommand().Activated()

        self.assertEqual(1, len(opened))
        self.assertEqual(self.store.path, opened[0].store.path)
        self.assertEqual(["Steel 50x50x2"], self.listed(opened[0]))
        opened[0].deleteLater()


if __name__ == "__main__":
    unittest.main()

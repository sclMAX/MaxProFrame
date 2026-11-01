"""
Regression tests proving MaxProFrame does not claim any FrameForge names:
no module redirect, no command aliases and no legacy preference reads.
"""

import importlib
import sys
import unittest
import uuid
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui

import freecad.maxproframe as maxproframe

LEGACY_GROUP = "User parameter:BaseApp/Preferences/Frameforge"


class TestNoFrameForgeModuleRedirect(unittest.TestCase):
    def test_import_does_not_alias_frameforge_module(self):
        importlib.import_module("freecad.maxproframe")

        for name, module in sys.modules.items():
            if name == "freecad.frameforge" or name.startswith("freecad.frameforge."):
                self.assertFalse(
                    getattr(module, "__name__", "").startswith("freecad.maxproframe"),
                    f"{name} is aliased to {module.__name__}",
                )
        self.assertIsNot(getattr(sys.modules.get("freecad"), "frameforge", None), maxproframe)

    def test_no_maxproframe_finder_on_meta_path(self):
        for finder in sys.meta_path:
            owner = getattr(type(finder), "__module__", "") or ""
            self.assertFalse(owner.startswith("freecad.maxproframe"), f"{finder!r} installed by {owner}")

    def test_frameforge_import_does_not_resolve_to_maxproframe(self):
        for name in ("freecad.frameforge", "freecad.frameforge.version"):
            with self.subTest(name=name):
                try:
                    module = importlib.import_module(name)
                except ImportError:
                    continue
                self.assertFalse(module.__name__.startswith("freecad.maxproframe"))
                self.assertNotIn("maxproframe", getattr(module, "__file__", "") or "")


class TestNoFrameForgeCommandAliases(unittest.TestCase):
    def test_registered_commands_have_no_frameforge_alias(self):
        from freecad.maxproframe import (  # noqa: F401 - imports register the commands
            create_bom_tool,
            create_edit_balloons_tool,
            create_end_miter_tool,
            create_extruded_cutout_tool,
            create_link,
            create_profiles_tool,
            create_trimmed_profiles_tool,
            edit_profile_tool,
            library_manager_dialog,
            parametric_line,
            populate_ids_tool,
            utilities,
        )

        commands = set(Gui.listCommands())
        canonical = sorted(name for name in commands if name.startswith("MaxProFrame_"))
        self.assertIn("MaxProFrame_RecomputeFrameForgeObjects", canonical)
        self.assertIn("MaxProFrame_CreateProfiles", canonical)
        for name in canonical:
            legacy = "FrameForge_" + name[len("MaxProFrame_") :]
            with self.subTest(command=name):
                self.assertFalse(legacy in commands, f"{legacy} is registered as an alias of {name}")

    def test_add_command_registers_only_the_given_name(self):
        from freecad.maxproframe.ff_tools import add_command

        command = object()
        # FreeCADGui exposes no removeCommand, so record registrations instead of leaking probes.
        with patch.object(Gui, "addCommand") as register:
            add_command("MaxProFrame_CompatProbe", command)

        self.assertEqual([call.args for call in register.call_args_list], [("MaxProFrame_CompatProbe", command)])


class TestNoFrameForgePreferenceFallback(unittest.TestCase):
    def setUp(self):
        self.key = "CompatProbe_" + uuid.uuid4().hex
        self.legacy = App.ParamGet(LEGACY_GROUP)
        self.addCleanup(self._remove_probe_keys)

    def _remove_probe_keys(self):
        for group in (self.legacy, App.ParamGet("User parameter:BaseApp/Preferences/MaxProFrame")):
            group.RemString(self.key)
            group.RemBool(self.key)
            group.RemInt(self.key)
            group.RemFloat(self.key)

    def test_legacy_only_values_are_not_read(self):
        from freecad.maxproframe.ff_tools import get_param_group

        self.legacy.SetString(self.key, "Perfect fit")
        self.legacy.SetBool(self.key, True)
        self.legacy.SetInt(self.key, 3)
        self.legacy.SetFloat(self.key, 1.75)

        reader = get_param_group()

        self.assertEqual(reader.GetString(self.key, "default"), "default")
        self.assertFalse(reader.GetBool(self.key, False))
        self.assertEqual(reader.GetInt(self.key, 7), 7)
        self.assertEqual(reader.GetFloat(self.key, 2.5), 2.5)
        self.assertNotIn(self.key, [key for _type, key, _value in reader.GetContents() or ()])

    def test_writes_go_to_maxproframe_and_leave_legacy_untouched(self):
        from freecad.maxproframe.ff_tools import get_param_group

        self.legacy.SetString(self.key, "legacy")
        legacy_before = self.legacy.GetContents()

        get_param_group(writable=True).SetString(self.key, "new")

        self.assertEqual(get_param_group().GetString(self.key, ""), "new")
        self.assertEqual(
            App.ParamGet("User parameter:BaseApp/Preferences/MaxProFrame").GetString(self.key, ""),
            "new",
        )
        self.assertEqual(self.legacy.GetContents(), legacy_before)


class TestNoFrameForgeProfilesFolder(unittest.TestCase):
    """User libraries come only from MaxProFrame's own folder and variable."""

    def setUp(self):
        import os
        import tempfile

        self.os = os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.legacy = os.path.join(self.temp.name, "FrameForge", "profiles")
        os.makedirs(self.legacy)
        env = {k: v for k, v in os.environ.items() if k not in ("MAXPROFRAME_USER_PROFILES_DIR",)}
        env["FRAMEFORGE_USER_PROFILES_DIR"] = self.legacy
        env["XDG_DATA_HOME"] = self.temp.name
        env_patch = patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_frameforge_folder_and_variable_are_ignored(self):
        from freecad.maxproframe.library_manager import get_default_user_profiles_dir

        with patch.object(App, "getUserAppDataDir", return_value=self.temp.name):
            self.assertEqual(
                get_default_user_profiles_dir(), self.os.path.join(self.temp.name, "MaxProFrame", "profiles")
            )

    def test_maxproframe_variable_is_used(self):
        from freecad.maxproframe.library_manager import get_default_user_profiles_dir

        own = self.os.path.join(self.temp.name, "own")
        with patch.dict(self.os.environ, {"MAXPROFRAME_USER_PROFILES_DIR": own}):
            self.assertEqual(get_default_user_profiles_dir(), own)


if __name__ == "__main__":
    unittest.main()

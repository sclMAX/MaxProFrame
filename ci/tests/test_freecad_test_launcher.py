"""Host-only public CLI checks for the isolated FreeCAD launchers."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "tools" / "freecad-test.py"
IMAGES = {
    "1.1.4": "FreeCAD_1.1.4-Linux-x86_64-py311.AppImage",
    "26.3rc2": "FreeCAD_26.3rc2-Linux-x86_64.AppImage",
}


class FreeCADTestLauncher(unittest.TestCase):
    def test_host_only_checks_are_outside_native_discovery(self):
        repo_root = SOURCE.parents[1]
        self.assertEqual(Path(__file__).resolve().parent, repo_root / "ci" / "tests")
        self.assertFalse((repo_root / "tests" / Path(__file__).name).exists())

    def test_versions_use_separate_profiles_and_same_checkout(self):
        with tempfile.TemporaryDirectory(prefix="freecad launcher ") as tmp:
            root = Path(tmp) / "MaxProFrame"
            (root / "tools").mkdir(parents=True)
            shutil.copy2(SOURCE, root / "tools/freecad-test.py")
            for version, name in IMAGES.items():
                image = Path(tmp) / name
                image.write_text(
                    "#!/usr/bin/env python3\n"
                    "import json, os, sys\n"
                    "print(json.dumps({'env': dict(os.environ), 'args': sys.argv[1:]}))\n"
                    "sys.exit(7)\n"
                )
                image.chmod(0o755)
                result = subprocess.run(
                    [sys.executable, str(root / "tools/freecad-test.py"), version, "part with spaces.FCStd"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(result.stderr, "")
                profile = root / ".freecad-test" / version
                self.assertEqual(result.stdout, f"FreeCAD {version}: {profile / 'FreeCAD.log'}\n")
                recorded = json.loads((profile / "FreeCAD.log").read_text())
                env = recorded["env"]
                for key, relative in {
                    "HOME": "home",
                    "XDG_CONFIG_HOME": "config",
                    "XDG_DATA_HOME": "data",
                    "XDG_CACHE_HOME": "cache",
                    "FREECAD_USER_HOME": "home",
                    "FREECAD_USER_DATA": "data/FreeCAD",
                    "FREECAD_USER_TEMP": "tmp",
                    "TMPDIR": "tmp",
                }.items():
                    self.assertEqual(env[key], str(profile / relative))
                    self.assertTrue(Path(env[key]).is_dir())
                self.assertEqual(
                    recorded["args"],
                    [
                        "--user-cfg",
                        str(profile / "config/user.cfg"),
                        "--system-cfg",
                        str(profile / "config/system.cfg"),
                        "part with spaces.FCStd",
                    ],
                )
                self.assertEqual((profile / "data/FreeCAD/Mod/MaxProFrame").resolve(), root)
            self.assertNotEqual((root / ".freecad-test/1.1.4").resolve(), (root / ".freecad-test/26.3rc2").resolve())

    def test_missing_image_does_not_create_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MaxProFrame"
            (root / "tools").mkdir(parents=True)
            shutil.copy2(SOURCE, root / "tools/freecad-test.py")
            result = subprocess.run(
                [sys.executable, str(root / "tools/freecad-test.py"), "1.1.4"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("AppImage not found:", result.stderr)
            self.assertFalse((root / ".freecad-test").exists())


if __name__ == "__main__":
    unittest.main()

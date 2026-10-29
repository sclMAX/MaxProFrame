import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "ci" / "install_format_hook.py"


class FormatHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "ci").mkdir()
        (self.repo / "ci" / INSTALLER.name).write_text(INSTALLER.read_text())
        self.installer = self.repo / "ci" / INSTALLER.name
        self.hook = self.repo / ".git" / "hooks" / "pre-commit"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self):
        return subprocess.run(["/usr/bin/python3", str(self.installer)], cwd=self.repo, capture_output=True, text=True)

    def test_config_pins_order_and_matches_ci(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text()
        requirements = (ROOT / "ci" / "requirements-format.txt").read_text()
        self.assertIn("isort==6.0.1", requirements)
        self.assertIn("black==25.1.0", requirements)
        self.assertLess(config.index("rev: 6.0.1"), config.index("rev: 25.1.0"))
        self.assertLess(config.index("id: isort"), config.index("id: black"))

    def test_installer_refuses_foreign_hook_and_is_idempotent(self):
        self.hook.write_text("foreign\n")
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.hook.read_text(), "foreign\n")
        self.hook.unlink()
        self.assertEqual(self.install().returncode, 0)
        first = self.hook.read_bytes()
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.hook.read_bytes(), first)

    def test_refuses_custom_hooks_path(self):
        subprocess.run(["git", "config", "core.hooksPath", "other"], cwd=self.repo, check=True)
        self.assertNotEqual(self.install().returncode, 0)
        self.assertFalse(self.hook.exists())

    def test_hook_confines_environment_and_delegates(self):
        self.assertEqual(self.install().returncode, 0)
        python = self.repo / ".git" / "format-tools" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$PRE_COMMIT_HOME" "$VIRTUALENV_APP_DATA" "$PIP_CACHE_DIR" "$PIP_NO_CACHE_DIR" "$@"\nexit 7\n'
        )
        python.chmod(0o755)
        result = subprocess.run([str(self.hook)], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        lines = result.stdout.splitlines()
        common = self.repo / ".git"
        self.assertEqual(
            lines[:4], [str(common / "pre-commit"), str(common / "virtualenv"), str(common / "pip-cache"), "1"]
        )
        self.assertEqual(lines[4:7], ["-m", "pre_commit", "hook-impl"])
        self.assertIn("--hook-type=pre-commit", lines[7:])

    def test_missing_tool_fails(self):
        self.assertEqual(self.install().returncode, 0)
        result = subprocess.run([str(self.hook)], cwd=self.repo, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("format-tools", result.stderr)


if __name__ == "__main__":
    unittest.main()

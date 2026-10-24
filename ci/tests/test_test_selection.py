"""Public selector envelope and native-free macro dispatch contracts."""

import json
import os
import subprocess
import sys
import unittest

from ci.tests import test_policy


class TestSelection(unittest.TestCase):
    def setUp(self):
        self.fixture = test_policy.TestRunTestsPolicy()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.work = self.fixture.work_dir

    def run_host(self, selector=None, env=None):
        command = [
            sys.executable,
            str(test_policy.CI_DIR / "run_tests.py"),
            "--freecad-bin",
            str(self.fixture.fake_bin),
            "--reports",
            str(self.fixture.reports_dir),
        ]
        if selector is not None:
            command += ["--test", selector]
        return subprocess.run(command, env=dict(os.environ, **(env or {})), capture_output=True, text=True)

    def test_explicit_selection_and_default_environment(self):
        dump = self.work / "env.json"
        summary = dict(tests=1, failures=0, errors=0, skipped=0, successful=True)
        env = dict(
            FAKE_ENV_DUMP=str(dump),
            FF_TEST="test_inherited",
            FAKE_SUMMARY_PATH=str(self.fixture.reports_dir / "summary.json"),
            FAKE_SUMMARY_CONTENT=json.dumps(summary),
        )
        for selector in ("test_example", "test_example.Case", "test_example.Case.test_ok", None):
            with self.subTest(selector=selector):
                proc = self.run_host(selector, env)
                self.assertEqual(
                    (proc.returncode, proc.stdout, proc.stderr),
                    (0, "run_tests: Test suite succeeded (1 tests executed).\n", ""),
                )
                child = json.loads(dump.read_text())
                self.assertEqual(child.get("FF_TEST"), selector)

    def test_invalid_selection_preserves_reports_without_launch(self):
        sentinel = self.fixture.reports_dir / "summary.json"
        dump = self.work / "launched.json"
        for selector in ("", "../test_x", "test_x/py", "os.path", "test_x..Case", " test_x", "test_x.C.m.extra"):
            with self.subTest(selector=selector):
                sentinel.write_text("sentinel")
                proc = self.run_host(selector, dict(FAKE_ENV_DUMP=str(dump)))
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertIn("--test must be", proc.stderr)
                self.assertEqual(sentinel.read_text(), "sentinel")
                self.assertFalse(dump.exists())

    def test_macro_dispatch_preserves_outcomes(self):
        root = self.work / "fixture"
        tests = root / "tests"
        tests.mkdir(parents=True)
        (tests / "test_selected.py").write_text(
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_ok(self): pass\n"
            " def test_fail(self): self.fail('selected failure')\n"
            " def test_error(self): raise RuntimeError('selected error')\n"
        )
        (tests / "test_other.py").write_text(
            "import unittest\nclass Other(unittest.TestCase):\n def test_other(self): pass\n"
        )
        driver = self.work / "macro_driver.py"
        driver.write_text(
            "import os, sys, types, runpy\n"
            "sys.modules['FreeCAD'] = types.SimpleNamespace(Version=lambda: ['1','1','4'])\n"
            "for name in ('FreeCADGui', 'Part', 'freecad'):\n"
            " sys.modules[name] = types.ModuleType(name)\n"
            "sys.modules['freecad'].__path__ = []\n"
            "sys.version_info = (3,11,0)\n"
            "runpy.run_path(sys.argv[1])\n"
        )
        cases = [
            (None, 4, 1, 1),
            ("test_selected", 3, 1, 1),
            ("test_selected.Case", 3, 1, 1),
            ("test_selected.Case.test_ok", 1, 0, 0),
            ("test_selected.Case.test_fail", 1, 1, 0),
            ("test_selected.Case.test_error", 1, 0, 1),
            ("test_missing", 1, 0, 1),
            ("test_selected.Unknown", 1, 0, 1),
            ("test_selected.Case.test_missing", 1, 0, 1),
        ]
        for selector, count, failures, errors in cases:
            with self.subTest(selector=selector):
                env = dict(os.environ, FF_ROOT=str(root), FF_REPORTS=str(self.fixture.reports_dir), FF_TARGET="stable")
                env.pop("FF_TEST", None)
                if selector is not None:
                    env["FF_TEST"] = selector
                proc = subprocess.run(
                    [sys.executable, str(driver), str(test_policy.CI_DIR / "run-tests.FCMacro")],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                summary = json.loads((self.fixture.reports_dir / "summary.json").read_text())
                self.assertEqual((summary["tests"], summary["failures"], summary["errors"]), (count, failures, errors))
                self.assertEqual(summary["skipped"], 0)
                self.assertEqual(proc.returncode, int(bool(failures or errors)))
                self.assertEqual(proc.stderr, "")
                self.assertEqual(json.loads(proc.stdout), summary)

    def test_selection_does_not_import_unrelated_packages(self):
        root = self.work / "local"
        tests = root / "tests"
        package = tests / "test_unrelated"
        package.mkdir(parents=True)
        marker = self.work / "imported"
        (package / "__init__.py").write_text(f"open({str(marker)!r}, 'w').close()\n")
        (tests / "test_local.py").write_text(
            "import unittest\nclass Case(unittest.TestCase):\n def test_ok(self): pass\n"
        )
        import io

        from ci.run_tests import selected_suite

        self.addCleanup(lambda: sys.path.remove(str(tests.resolve())))
        self.addCleanup(lambda: sys.modules.pop("test_local", None))
        suite = selected_suite(tests, "test_local.Case.test_ok")
        result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.testsRun, 1)
        self.assertFalse(marker.exists())

"""The native runner writes each failure's traceback as soon as the test fails (issue #148).

A shard killed by its timeout never reaches unittest's final report: the details of a failure seen before the hang
must already be in tests.log.
"""

import os
import subprocess
import sys
import unittest

import test_policy


class ImmediateFailureDetailsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_policy.TestRunTestsPolicy()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.work = self.fixture.work_dir
        self.root = self.work / "fixture"
        tests = self.root / "tests"
        tests.mkdir(parents=True)
        (tests / "test_alpha.py").write_text(
            "import unittest\n"
            "class A(unittest.TestCase):\n"
            " def test_0_fails(self): self.assertEqual('seen', 'expected', 'failure-detail-0')\n"
            " def test_1_errors(self): raise RuntimeError('error-detail-1')\n"
            " def test_2_passes(self): pass\n"
        )
        self.driver = self.work / "macro_driver.py"
        self.driver.write_text(
            "import os, sys, types, runpy\n"
            "sys.modules['FreeCAD'] = types.SimpleNamespace(Version=lambda: ['1','1','4'])\n"
            "for name in ('FreeCADGui', 'Part', 'freecad'):\n"
            " sys.modules[name] = types.ModuleType(name)\n"
            "sys.modules['freecad'].__path__ = []\n"
            "sys.version_info = (3,11,0)\n"
            "runpy.run_path(sys.argv[1])\n"
        )

    def run_macro(self):
        reports = self.fixture.reports_dir
        env = dict(os.environ, FF_ROOT=str(self.root), FF_REPORTS=str(reports), FF_TARGET="stable")
        for name in ("FF_SHARD", "FF_TEST", "FF_SHUFFLE_SEED"):
            env.pop(name, None)
        proc = subprocess.run(
            [sys.executable, str(self.driver), str(test_policy.CI_DIR / "run-tests.FCMacro")],
            env=env,
            capture_output=True,
            text=True,
        )
        # The fixture suite fails on purpose: the macro exits 1.
        self.assertEqual((proc.returncode, proc.stderr), (1, ""))
        return (reports / "tests.log").read_text().splitlines()

    def index(self, lines, text):
        return next(number for number, line in enumerate(lines) if text in line)

    def test_a_failure_and_an_error_are_detailed_before_the_next_test_runs(self):
        lines = self.run_macro()

        passes = self.index(lines, "test_2_passes")
        errors = self.index(lines, "test_1_errors")
        self.assertLess(self.index(lines, "failure-detail-0"), errors)
        self.assertLess(self.index(lines, "error-detail-1"), passes)
        # The final report still lists them, as unittest always did.
        self.assertIn("FAILED (failures=1, errors=1)", lines)


if __name__ == "__main__":
    unittest.main()

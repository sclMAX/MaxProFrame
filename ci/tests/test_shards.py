"""Native suite shards: `run_tests.py --shard INDEX/COUNT` and the macro partition (ci-windows S4)."""

import json
import os
import re
import subprocess
import sys
import unittest

from ci.tests import test_policy

SHARD_ERROR = "--shard must be INDEX/COUNT with 1 <= INDEX <= COUNT, e.g. 1/2"
RESULT_LINE = re.compile(r"^\w+ \(([\w.]+)\) \.\.\. ok$")


class TestShardOption(unittest.TestCase):
    def setUp(self):
        self.fixture = test_policy.TestRunTestsPolicy()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.work = self.fixture.work_dir

    def run_host(self, *extra, env=None):
        command = [
            sys.executable,
            str(test_policy.CI_DIR / "run_tests.py"),
            "--freecad-bin",
            str(self.fixture.fake_bin),
            "--reports",
            str(self.fixture.reports_dir),
            *extra,
        ]
        return subprocess.run(command, env=dict(os.environ, **(env or {})), capture_output=True, text=True)

    def passing_env(self, dump):
        summary = dict(tests=1, failures=0, errors=0, skipped=0, successful=True)
        return dict(
            FAKE_ENV_DUMP=str(dump),
            FF_SHARD="9/9",
            FAKE_SUMMARY_PATH=str(self.fixture.reports_dir / "summary.json"),
            FAKE_SUMMARY_CONTENT=json.dumps(summary),
        )

    def test_shard_is_forwarded_to_the_child_and_announced(self):
        dump = self.work / "env.json"
        for value in ("1/1", "1/2", "2/2", "3/3", "10/12"):
            with self.subTest(shard=value):
                proc = self.run_host("--shard", value, env=self.passing_env(dump))
                self.assertEqual(
                    (proc.returncode, proc.stdout, proc.stderr),
                    (0, f"run_tests: shard {value}\nrun_tests: Test suite succeeded (1 tests executed).\n", ""),
                )
                self.assertEqual(json.loads(dump.read_text())["FF_SHARD"], value)

    def test_without_shard_the_inherited_value_is_dropped(self):
        dump = self.work / "env.json"
        proc = self.run_host(env=self.passing_env(dump))
        self.assertEqual(
            (proc.returncode, proc.stdout, proc.stderr),
            (0, "run_tests: Test suite succeeded (1 tests executed).\n", ""),
        )
        self.assertNotIn("FF_SHARD", json.loads(dump.read_text()))

    def test_invalid_shard_is_rejected_before_launch(self):
        sentinel = self.fixture.reports_dir / "summary.json"
        dump = self.work / "launched.json"
        for value in ("0/2", "3/2", "a/b", "1/0", "0/0", "-1/2", "1/-2", "2", "1/2/3", "", " 1/2", "1/2 ", "01/2"):
            with self.subTest(shard=value):
                sentinel.write_text("sentinel")
                proc = self.run_host("--shard", value, env=dict(FAKE_ENV_DUMP=str(dump)))
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertIn(SHARD_ERROR, proc.stderr)
                self.assertEqual(sentinel.read_text(), "sentinel")
                self.assertFalse(dump.exists())

    def test_help_documents_shard(self):
        done = subprocess.run(
            [sys.executable, str(test_policy.CI_DIR / "run_tests.py"), "--help"], capture_output=True, text=True
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("--shard INDEX/COUNT", done.stdout)
        self.assertIn("exactly one shard", " ".join(done.stdout.split()))


class TestShardPartition(unittest.TestCase):
    """The macro runs only the selected shard; together the shards run the suite exactly once."""

    def setUp(self):
        self.fixture = test_policy.TestRunTestsPolicy()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.work = self.fixture.work_dir
        self.root = self.work / "fixture"
        tests = self.root / "tests"
        tests.mkdir(parents=True)
        for module, classes in (("test_alpha", ("A", "B")), ("test_beta", ("C",)), ("test_gamma", ("D", "E"))):
            body = "import unittest\n"
            for name in classes:
                body += f"class {name}(unittest.TestCase):\n"
                body += "".join(f" def test_{index}(self): pass\n" for index in range(3))
            (tests / f"{module}.py").write_text(body)
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

    def run_macro(self, shard=None, selector=None, seed=None):
        reports = self.fixture.reports_dir
        env = dict(os.environ, FF_ROOT=str(self.root), FF_REPORTS=str(reports), FF_TARGET="stable")
        for name, value in (("FF_SHARD", shard), ("FF_TEST", selector), ("FF_SHUFFLE_SEED", seed)):
            env.pop(name, None)
            if value is not None:
                env[name] = value
        proc = subprocess.run(
            [sys.executable, str(self.driver), str(test_policy.CI_DIR / "run-tests.FCMacro")],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        summary = json.loads((reports / "summary.json").read_text())
        lines = (reports / "tests.log").read_text().splitlines()
        ran = [match.group(1) for match in map(RESULT_LINE.match, lines) if match]
        self.assertEqual(summary["tests"], len(ran))
        return ran

    def test_shards_partition_the_suite_exactly_once(self):
        full = self.run_macro()
        self.assertEqual(len(full), 15)
        for count in (2, 3, 4, 15):
            with self.subTest(count=count):
                shards = [self.run_macro(f"{index}/{count}") for index in range(1, count + 1)]
                together = [test_id for shard in shards for test_id in shard]
                self.assertEqual(sorted(together), sorted(full))
                self.assertEqual(len(set(together)), len(full))
                self.assertTrue(all(shards), "Every shard must run at least one test")
                self.assertLessEqual(max(map(len, shards)) - min(map(len, shards)), 1)

    def test_single_shard_is_the_unsharded_run(self):
        self.assertEqual(self.run_macro("1/1"), self.run_macro())

    def test_partition_is_deterministic(self):
        self.assertEqual(self.run_macro("2/3"), self.run_macro("2/3"))
        self.assertEqual(self.run_macro("1/2"), self.run_macro()[0::2])
        self.assertEqual(self.run_macro("2/2"), self.run_macro()[1::2])

    def test_shard_applies_to_the_selected_tests(self):
        selected = self.run_macro(selector="test_gamma")
        shards = [self.run_macro("1/2", "test_gamma"), self.run_macro("2/2", "test_gamma")]
        self.assertEqual(sorted(shards[0] + shards[1]), sorted(selected))

    def test_shuffle_reorders_inside_the_shard_without_changing_it(self):
        plain = self.run_macro("2/3")
        shuffled = self.run_macro("2/3", seed="12345")
        self.assertEqual(sorted(shuffled), sorted(plain))
        self.assertEqual(shuffled, self.run_macro("2/3", seed="12345"))


if __name__ == "__main__":
    unittest.main()

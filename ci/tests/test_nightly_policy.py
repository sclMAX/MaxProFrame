"""Nightly flakiness policy: seeded shuffle in the runner and static checks of nightly.yml (T3/S4)."""

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

from ci import run_tests
from ci.tests import test_policy

NIGHTLY_PATH = test_policy.REPO_ROOT / ".github" / "workflows" / "nightly.yml"
STABLE_SHA256 = "f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434"
STABLE_URL = "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage"


def write_fake_tests(tests_dir, modules=4, methods=5):
    tests_dir.mkdir(parents=True, exist_ok=True)
    for index in range(modules):
        body = "import unittest\n\nclass Case(unittest.TestCase):\n"
        body += "".join(f"    def test_m{n}(self):\n        pass\n" for n in range(methods))
        (tests_dir / f"test_shuffle_{index}.py").write_text(body, encoding="utf-8")


def order_of(suite):
    names = []
    for test in run_tests.flatten_suite(suite):
        names.append(test.id())
    return names


class TestShuffleOrder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tests_dir = pathlib.Path(tmp.name) / "tests"
        write_fake_tests(self.tests_dir)
        self.addCleanup(self.drop_modules)

    def drop_modules(self):
        for name in [n for n in sys.modules if n.startswith("test_shuffle_")]:
            sys.modules.pop(name)
        sys.path[:] = [p for p in sys.path if p != str(self.tests_dir.resolve())]

    def discover(self, seed=None):
        return run_tests.selected_suite(self.tests_dir, None, shuffle_seed=seed)

    def test_without_seed_order_is_unchanged(self):
        self.assertEqual(order_of(self.discover()), order_of(run_tests.selected_suite(self.tests_dir, None)))
        names = order_of(self.discover())
        self.assertEqual(names, sorted(names))

    def test_same_seed_same_order_different_seed_different_order(self):
        first = order_of(self.discover(7))
        self.assertEqual(first, order_of(self.discover(7)))
        self.assertNotEqual(first, order_of(self.discover(8)))
        self.assertNotEqual(first, order_of(self.discover()))
        self.assertEqual(sorted(first), sorted(order_of(self.discover())))

    def test_shuffle_mixes_modules_and_tests(self):
        modules = [name.split(".")[0] for name in order_of(self.discover(7))]
        runs = sum(1 for a, b in zip(modules, modules[1:]) if a != b) + 1
        self.assertGreater(runs, 4, "tests of different modules must interleave")

    def test_shuffled_suite_still_runs_every_test(self):
        result = unittest.TextTestRunner(stream=io.StringIO()).run(self.discover(3))
        self.assertEqual((result.testsRun, result.wasSuccessful()), (20, True))


class TestShuffleSeedRunner(unittest.TestCase):
    def setUp(self):
        self.fixture = test_policy.TestRunTestsPolicy()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.work = self.fixture.work_dir
        self.dump = self.work / "env.json"
        self.summary = dict(tests=1, failures=0, errors=0, skipped=0, successful=True)

    def run_host(self, extra=(), summary=None, exit_code="0"):
        env = dict(os.environ, FAKE_ENV_DUMP=str(self.dump), FAKE_EXIT_CODE=exit_code)
        env.pop("FF_SHUFFLE_SEED", None)
        env["FAKE_SUMMARY_PATH"] = str(self.fixture.reports_dir / "summary.json")
        env["FAKE_SUMMARY_CONTENT"] = json.dumps(summary or self.summary)
        command = [
            sys.executable,
            str(test_policy.CI_DIR / "run_tests.py"),
            "--freecad-bin",
            str(self.fixture.fake_bin),
            "--reports",
            str(self.fixture.reports_dir),
            *extra,
        ]
        return subprocess.run(command, env=env, capture_output=True, text=True)

    def test_seed_is_exported_and_printed_at_start(self):
        proc = self.run_host(["--shuffle-seed", "12345"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(self.dump.read_text())["FF_SHUFFLE_SEED"], "12345")
        self.assertEqual(
            proc.stdout,
            "run_tests: shuffle seed 12345\nrun_tests: Test suite succeeded (1 tests executed).\n",
        )
        self.assertEqual(proc.stderr, "")

    def test_without_option_nothing_is_exported_or_printed(self):
        proc = self.run_host()
        self.assertEqual(
            (proc.returncode, proc.stdout, proc.stderr),
            (0, "run_tests: Test suite succeeded (1 tests executed).\n", ""),
        )
        self.assertNotIn("FF_SHUFFLE_SEED", json.loads(self.dump.read_text()))

    def test_inherited_seed_is_not_forwarded_without_option(self):
        os.environ["FF_SHUFFLE_SEED"] = "99"
        self.addCleanup(os.environ.pop, "FF_SHUFFLE_SEED", None)
        env = dict(os.environ, FAKE_ENV_DUMP=str(self.dump))
        env.update(FAKE_SUMMARY_PATH=str(self.fixture.reports_dir / "summary.json"))
        env["FAKE_SUMMARY_CONTENT"] = json.dumps(self.summary)
        subprocess.run(
            [sys.executable, str(test_policy.CI_DIR / "run_tests.py"), "--freecad-bin", str(self.fixture.fake_bin)]
            + ["--reports", str(self.fixture.reports_dir)],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotIn("FF_SHUFFLE_SEED", json.loads(self.dump.read_text()))

    def test_seed_is_in_failure_diagnosis_for_every_failure_kind(self):
        failed = dict(self.summary, failures=1, successful=False)
        cases = {
            "suite failure": dict(summary=failed),
            "child exit": dict(exit_code="3"),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                proc = self.run_host(["--shuffle-seed", "4242"], **kwargs)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("run_tests: replay with --shuffle-seed 4242", proc.stderr)

    def test_failure_without_seed_has_no_replay_hint(self):
        proc = self.run_host(summary=dict(self.summary, failures=1, successful=False))
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("shuffle", proc.stderr)

    def test_non_integer_seed_is_rejected_before_launch(self):
        proc = self.run_host(["--shuffle-seed", "abc"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("--shuffle-seed", proc.stderr)
        self.assertFalse(self.dump.exists())

    def test_macro_applies_seed_to_native_suite(self):
        root = self.work / "local"
        write_fake_tests(root / "tests", modules=3, methods=4)
        driver = self.work / "driver.py"
        driver.write_text(
            "import sys, types, runpy\n"
            "sys.modules['FreeCAD'] = types.SimpleNamespace(Version=lambda: ['1','1','4'])\n"
            "for name in ('FreeCADGui', 'Part', 'freecad'):\n"
            " sys.modules[name] = types.ModuleType(name)\n"
            "sys.modules['freecad'].__path__ = []\n"
            "sys.version_info = (3,11,0)\n"
            "runpy.run_path(sys.argv[1])\n",
            encoding="utf-8",
        )

        def macro_order(seed):
            env = dict(os.environ, FF_ROOT=str(root), FF_REPORTS=str(self.fixture.reports_dir), FF_TARGET="stable")
            env.pop("FF_TEST", None)
            env.pop("FF_SHUFFLE_SEED", None)
            if seed is not None:
                env["FF_SHUFFLE_SEED"] = str(seed)
            proc = subprocess.run(
                [sys.executable, str(driver), str(test_policy.CI_DIR / "run-tests.FCMacro")],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            log = (self.fixture.reports_dir / "tests.log").read_text()
            return re.findall(r"^(test_m\d \(test_shuffle_\d\.Case\.test_m\d\))", log, re.M)

        plain = macro_order(None)
        self.assertEqual(len(plain), 12)
        self.assertEqual(plain, sorted(plain, key=lambda s: s.split("(")[1]))
        self.assertEqual(macro_order(7), macro_order(7))
        self.assertNotEqual(macro_order(7), macro_order(8))
        self.assertNotEqual(macro_order(7), plain)


class TestNightlyWorkflowPolicy(unittest.TestCase):
    def setUp(self):
        self.assertTrue(NIGHTLY_PATH.is_file(), f"Workflow missing: {NIGHTLY_PATH}")
        self.content = NIGHTLY_PATH.read_text(encoding="utf-8")
        self.ci = test_policy.WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_name_and_triggers(self):
        self.assertTrue(self.content.startswith("name: Nightly native flakiness\n"))
        self.assertEqual(len(re.findall(r"^\s+- cron:", self.content, re.M)), 1)
        self.assertRegex(self.content, r"- cron: '\d+ \d+ \* \* \*'")
        self.assertNotIn("pull_request", self.content)
        self.assertNotIn("push:", self.content)
        dispatch = self.content.split("workflow_dispatch:", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("repetitions:", dispatch)
        self.assertIn("default: '3'", dispatch)
        self.assertIn("seed:", dispatch)

    def test_permissions_are_read_only(self):
        self.assertIn("\npermissions:\n  contents: read\n", self.content)
        self.assertEqual(self.content.count("permissions:"), 1)
        self.assertNotRegex(self.content, r"(write|admin)\b")

    def test_single_job_on_stable_only(self):
        self.assertEqual(len(re.findall(r"^  [a-z][a-z0-9_-]*:\s*$", self.content.split("\njobs:\n", 1)[1], re.M)), 1)
        self.assertIn("runs-on: ubuntu-24.04", self.content)
        self.assertRegex(self.content, r"timeout-minutes: (\d+)")
        self.assertGreaterEqual(int(re.search(r"timeout-minutes: (\d+)", self.content).group(1)), 60)
        self.assertNotIn("weekly", self.content)
        self.assertNotIn("matrix", self.content)
        self.assertIn("--target stable", self.content)

    def test_runtime_pin_is_read_from_targets_json(self):
        """The nightly pins nothing itself: it reads the stable URL and SHA-256 from ci/targets.json."""
        self.assertNotIn(STABLE_URL, self.content)
        self.assertNotRegex(self.content, r"\b[0-9a-f]{64}\b")
        self.assertNotIn("releases/download", self.content)
        self.assertNotIn("latest", self.content)
        read = self.content.split("- name: Read pinned stable target", 1)[1].split("- name:", 1)[0]
        self.assertIn("id: target", read)
        self.assertIn("ci/targets.json", read)
        self.assertIn('["stable"]', read)
        self.assertIn('"url=', read)
        self.assertIn('"sha256=', read)
        stable = test_policy.load_targets()["stable"]
        self.assertEqual((stable["url"], stable["sha256"]), (STABLE_URL, STABLE_SHA256))

    def test_targets_are_read_after_checkout_and_reach_shell_through_env(self):
        self.assertLess(self.content.index("actions/checkout@"), self.content.index("ci/targets.json"))
        download = self.content.split("- name: Download FreeCAD AppImage", 1)[1].split("- name:", 1)[0]
        self.assertIn("STABLE_URL: ${{ steps.target.outputs.url }}", download)
        self.assertNotIn("${{ steps.target", download.split("run: |", 1)[1])
        verify = self.content.split("- name: Verify FreeCAD AppImage checksum", 1)[1].split("- name:", 1)[0]
        self.assertIn("STABLE_SHA256: ${{ steps.target.outputs.sha256 }}", verify)
        self.assertNotIn("${{ steps.target", verify.split("run: |", 1)[1])

    def test_actions_are_pinned_to_the_same_shas_as_ci(self):
        pin = re.compile(r"uses:\s+(actions/[\w-]+@[0-9a-f]{40} # v[\d.]+)$", re.M)
        ci_pins = set(pin.findall(self.ci))
        uses = re.findall(r"^\s*(?:- )?uses:.*$", self.content, re.M)
        self.assertTrue(uses)
        nightly_pins = pin.findall(self.content)
        self.assertEqual(len(uses), len(nightly_pins), "every action must be pinned by full SHA")
        self.assertLessEqual(set(nightly_pins), ci_pins)
        self.assertIn("actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0", self.content)

    def test_cache_key_scheme_and_checksum_always_verified(self):
        self.assertIn("key: freecad-appimage-${{ steps.target.outputs.sha256 }}", self.content)
        download = self.content.split("- name: Download FreeCAD AppImage", 1)[1].split("- name:", 1)[0]
        self.assertIn("steps.appimage-cache.outputs.cache-hit != 'true'", download)
        verify = self.content.split("- name: Verify FreeCAD AppImage checksum", 1)[1].split("- name:", 1)[0]
        self.assertIn("sha256sum -c -", verify)
        self.assertNotIn("if:", verify, "checksum must be verified on cache hits too")

    def test_headless_dependencies_match_ci(self):
        line = (
            "sudo apt-get install -y --no-install-recommends libegl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 gdb"
        )
        self.assertIn(line, self.content)
        self.assertIn(line, self.ci)

    def test_runs_normal_repetitions_plus_one_shuffled_run(self):
        self.assertIn("--shuffle-seed", self.content)
        self.assertEqual(self.content.count("--shuffle-seed"), 1, "exactly one shuffled invocation")
        self.assertRegex(self.content, r"inputs\.repetitions \|\| '3'")
        self.assertRegex(self.content, r"inputs\.seed \|\| github\.run_id")
        self.assertIn("seq 1", self.content)

    def test_all_runs_execute_and_job_fails_if_any_failed(self):
        self.assertNotIn("continue-on-error", self.content)
        self.assertNotIn("|| true", self.content)
        self.assertNotIn("|| :", self.content)
        self.assertNotIn("set +e", self.content)
        self.assertNotIn("break", self.content)
        self.assertNotIn("exit 0", self.content)
        loop = self.content.split("- name: Run native test repetitions", 1)[1].split("- name:", 1)[0]
        self.assertIn("failed=", loop)
        self.assertRegex(loop, r"(?m)^\s+exit \"?\$failed\"?$|exit 1")
        self.assertIn("if: always()", self.content, "summary and artifact steps run even after failures")

    def test_summary_table_and_failure_artifact(self):
        self.assertIn("GITHUB_STEP_SUMMARY", self.content)
        self.assertIn("| Run | Order / seed | Result | Tests | Crash test |", self.content)
        upload = self.content.split("actions/upload-artifact@", 1)[1]
        self.assertIn("retention-days: 7", upload)
        self.assertIn("nightly-failure-reports", upload)
        self.assertIn("if: always()", upload.split("with:", 1)[0] + "if: always()")
        self.assertIn("failed-reports", self.content)

    def test_no_untrusted_input_interpolated_in_shell(self):
        for line in self.content.splitlines():
            if "${{ inputs." in line or "${{ github.event.inputs" in line:
                self.assertNotIn("run:", line)
        run_blocks = re.findall(r"run: \|\n((?:\s{10,}.*\n)+)", self.content)
        for block in run_blocks:
            self.assertNotIn("${{ inputs", block)
            self.assertNotIn("${{ github.event", block)


class TestNightlyDocs(unittest.TestCase):
    def test_docs_explain_run_replay_and_dispatch(self):
        text = (test_policy.REPO_ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
        self.assertIn("## Nightly flakiness run", text)
        section = text.split("## Nightly flakiness run", 1)[1].split("\n## ", 1)[0]
        for needle in ("--shuffle-seed", "Run workflow", "repetitions", "seed", "nightly-failure-reports", "7 days"):
            self.assertIn(needle, section)


if __name__ == "__main__":
    unittest.main()

"""Host tests for crash diagnosis in ci/run_tests.py (ci-hardening S1).

The diagnosis is diagnostic only: the runner keeps the original failure status
and the opt-out/skip paths never change it.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "ci"
sys.path.insert(0, str(CI_DIR))

TEST_ID = "test_crashy.TestCrashy.test_boom"
RUNNING = "test_fine (test_crashy.TestCrashy.test_fine) ... ok\ntest_boom (test_crashy.TestCrashy.test_boom) ... "
GL_NOISE = "qt.qpa.gl: QOpenGLContext::makeCurrent() failed\nlibEGL warning: DRI3 error\n"
FAKE_FREECAD = """#!{python}
import os, pathlib, signal, sys
reports = pathlib.Path(os.environ["FF_REPORTS"])
if os.environ.get("FAKE_TESTS_LOG") is not None:
    (reports / "tests.log").write_text(os.environ["FAKE_TESTS_LOG"], encoding="utf-8")
if os.environ.get("FAKE_SUMMARY") is not None:
    (reports / "summary.json").write_text(os.environ["FAKE_SUMMARY"], encoding="utf-8")
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
sys.stderr.flush()
if os.environ.get("FAKE_SIGNAL"):
    os.kill(os.getpid(), int(os.environ["FAKE_SIGNAL"]))
sys.exit(int(os.environ.get("FAKE_EXIT_CODE", "0")))
"""
FAKE_GDB = """#!{python}
import json, os, sys
with open(os.environ["FAKE_GDB_DUMP"], "w", encoding="utf-8") as f:
    json.dump({"argv": sys.argv[1:], "ff_test": os.environ.get("FF_TEST"), "ff_reports": os.environ.get("FF_REPORTS"),
               "ff_seed": os.environ.get("FF_SHUFFLE_SEED")}, f)
if os.environ.get("FAKE_GDB_CRASH"):
    print("Program received signal SIGSEGV, Segmentation fault.")
print("#0  fake_native_frame () at fake.c:1")
print("Current thread 0x1 (most recent call first): File fake.py, line 3")
sys.exit(int(os.environ.get("FAKE_GDB_EXIT", "0")))
"""


class TestCrashLogParsing(unittest.TestCase):
    def test_inflight_test_is_last_line_without_result(self):
        import crash_diagnosis

        self.assertEqual(crash_diagnosis.inflight_test(RUNNING), TEST_ID)

    def test_docstring_variant_and_completed_log(self):
        import crash_diagnosis

        log = "test_a (m.C.test_a)\nDoes a thing ... ok\ntest_b (m.C.test_b)\nDoes b thing ... "
        self.assertEqual(crash_diagnosis.inflight_test(log), "m.C.test_b")
        self.assertIsNone(crash_diagnosis.inflight_test("test_a (m.C.test_a) ... ok\ntest_b (m.C.test_b) ... FAIL\n"))
        self.assertIsNone(crash_diagnosis.inflight_test("test_a (m.C.test_a) ... skipped 'x'\n"))
        self.assertIsNone(crash_diagnosis.inflight_test(""))

    def test_stderr_tail_drops_gl_noise_and_repeats(self):
        import crash_diagnosis

        text = "real one\n" + GL_NOISE * 3 + "Segmentation fault\nSegmentation fault\n"
        self.assertEqual(crash_diagnosis.stderr_tail(text), ["real one", "Segmentation fault"])
        self.assertEqual(len(crash_diagnosis.stderr_tail("\n".join(str(i) for i in range(100)))), 20)


class TestCrashDiagnosisRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.tmp.name)
        self.reports = self.work / "reports"
        self.reports.mkdir()
        self.fake_bin = self.work / "fake_freecad"
        self.fake_bin.write_text(FAKE_FREECAD.replace("{python}", sys.executable), encoding="utf-8")
        self.fake_bin.chmod(0o755)
        self.bin_dir = self.work / "bin"
        self.bin_dir.mkdir()
        self.empty_bin = self.work / "empty"
        self.empty_bin.mkdir()
        self.gdb_dump = self.work / "gdb.json"
        self.step_summary = self.work / "step_summary.md"

    def tearDown(self):
        self.tmp.cleanup()

    def _install_gdb(self, exit_code="0"):
        gdb = self.bin_dir / "gdb"
        gdb.write_text(FAKE_GDB.replace("{python}", sys.executable), encoding="utf-8")
        gdb.chmod(0o755)
        return {"PATH": str(self.bin_dir), "FAKE_GDB_DUMP": str(self.gdb_dump), "FAKE_GDB_EXIT": exit_code}

    def _run(self, env_overrides, *extra_args, summary_env=True):
        env = os.environ.copy()
        env.pop("GITHUB_STEP_SUMMARY", None)
        if summary_env:
            env["GITHUB_STEP_SUMMARY"] = str(self.step_summary)
        env.update(env_overrides)
        return subprocess.run(
            [
                sys.executable,
                str(CI_DIR / "run_tests.py"),
                "--freecad-bin",
                str(self.fake_bin),
                "--reports",
                str(self.reports),
                "--timeout",
                "20",
                *extra_args,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def _crash_env(self, **extra):
        env = {"FAKE_SIGNAL": "11", "FAKE_TESTS_LOG": RUNNING, "FAKE_STDERR": "real one\n" + GL_NOISE * 2 + "boom\n"}
        env.update(extra)
        return env

    def test_signal_identifies_test_and_writes_step_summary(self):
        env = self._crash_env(**self._install_gdb())
        proc = self._run(env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SIGSEGV", proc.stderr)
        self.assertIn(TEST_ID, proc.stderr)
        summary = self.step_summary.read_text(encoding="utf-8")
        for expected in ("SIGSEGV", "-11", TEST_ID, "stable", "real one", "boom"):
            self.assertIn(expected, summary)
        self.assertNotIn("QOpenGLContext", summary)

    def test_no_step_summary_file_when_env_unset(self):
        proc = self._run(self._crash_env(**self._install_gdb()), summary_env=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(TEST_ID, proc.stderr)
        self.assertFalse(self.step_summary.exists())

    def test_rerun_only_crashing_test_and_keep_failure_status(self):
        baseline = self._run(self._crash_env(**self._install_gdb(exit_code="0")), "--no-crash-rerun")
        proc = self._run(self._crash_env(**self._install_gdb(exit_code="0")))
        self.assertEqual(proc.returncode, baseline.returncode)
        self.assertNotEqual(proc.returncode, 0)
        dump = json.loads(self.gdb_dump.read_text(encoding="utf-8"))
        self.assertEqual(dump["ff_test"], TEST_ID)
        self.assertNotEqual(dump["ff_reports"], str(self.reports))
        self.assertIn("bt 60", dump["argv"])
        self.assertIn("--args", dump["argv"])
        backtrace = (self.reports / "crash-backtrace.txt").read_text(encoding="utf-8")
        self.assertIn(TEST_ID, backtrace)
        self.assertIn("fake_native_frame", backtrace)
        self.assertIn("crash-backtrace.txt", self.step_summary.read_text(encoding="utf-8"))

    def test_gdb_failure_never_changes_exit_status(self):
        baseline = self._run(self._crash_env(), "--no-crash-rerun")
        proc = self._run(self._crash_env(**self._install_gdb(exit_code="9")))
        self.assertEqual(proc.returncode, baseline.returncode)

    def test_opt_out_flag_skips_rerun(self):
        proc = self._run(self._crash_env(**self._install_gdb()), "--no-crash-rerun")
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(self.gdb_dump.exists())
        self.assertFalse((self.reports / "crash-backtrace.txt").exists())
        self.assertIn(TEST_ID, proc.stderr)
        self.assertIn("rerun disabled", proc.stderr)

    def test_missing_gdb_skips_rerun_and_keeps_exit(self):
        baseline = self._run(self._crash_env(PATH=str(self.empty_bin)), "--no-crash-rerun")
        proc = self._run(self._crash_env(PATH=str(self.empty_bin)))
        self.assertEqual(proc.returncode, baseline.returncode)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("gdb is not installed", proc.stderr)
        self.assertIn("gdb is not installed", self.step_summary.read_text(encoding="utf-8"))
        self.assertFalse((self.reports / "crash-backtrace.txt").exists())

    def test_exit_without_summary_mid_suite_triggers_diagnosis(self):
        env = {"FAKE_EXIT_CODE": "3", "FAKE_TESTS_LOG": RUNNING, **self._install_gdb()}
        proc = self._run(env)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("FreeCAD child process failed with exit code 3.", proc.stderr)
        self.assertIn(TEST_ID, proc.stderr)
        self.assertTrue((self.reports / "crash-backtrace.txt").is_file())

    def test_signal_reported_by_freecad_handler_is_named(self):
        stderr = "Program received signal SIGSEGV, Segmentation fault.\n#0 frame\n"
        env = {"FAKE_EXIT_CODE": "1", "FAKE_TESTS_LOG": RUNNING, "FAKE_STDERR": stderr, **self._install_gdb()}
        proc = self._run(env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("exit code 1 after FreeCAD reported SIGSEGV", proc.stderr)
        self.assertIn("reported SIGSEGV", self.step_summary.read_text(encoding="utf-8"))

    def test_normal_failing_suite_does_not_rerun(self):
        summary = json.dumps({"tests": 2, "failures": 1, "errors": 0, "skipped": 0, "successful": False})
        log = "test_a (m.C.test_a) ... ok\ntest_b (m.C.test_b) ... FAIL\n"
        env = {"FAKE_EXIT_CODE": "1", "FAKE_TESTS_LOG": log, "FAKE_SUMMARY": summary, **self._install_gdb()}
        proc = self._run(env)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "run_tests error: FreeCAD child process failed with exit code 1.\n")
        self.assertFalse(self.gdb_dump.exists())
        self.assertFalse(self.step_summary.exists())

    def test_successful_suite_is_unchanged(self):
        summary = json.dumps({"tests": 2, "failures": 0, "errors": 0, "skipped": 0, "successful": True})
        log = "test_a (m.C.test_a) ... ok\ntest_b (m.C.test_b) ... ok\n"
        proc = self._run({"FAKE_TESTS_LOG": log, "FAKE_SUMMARY": summary, **self._install_gdb()})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "run_tests: Test suite succeeded (2 tests executed).\n")
        self.assertEqual(proc.stderr, "")
        self.assertFalse(self.gdb_dump.exists())
        self.assertFalse(self.step_summary.exists())

    def test_seeded_crash_replays_same_seed_and_full_suite(self):
        baseline = self._run(self._crash_env(), "--shuffle-seed", "41071643172", "--no-crash-rerun")
        env = self._crash_env(FAKE_GDB_CRASH="1", **self._install_gdb())
        proc = self._run(env, "--shuffle-seed", "41071643172")
        self.assertEqual(proc.returncode, baseline.returncode)
        self.assertNotEqual(proc.returncode, 0)
        dump = json.loads(self.gdb_dump.read_text(encoding="utf-8"))
        self.assertEqual(dump["ff_seed"], "41071643172")
        self.assertIsNone(dump["ff_test"])
        self.assertIn("seeded suite replay, seed 41071643172", proc.stderr)
        self.assertIn("seeded suite replay, seed 41071643172", self.step_summary.read_text(encoding="utf-8"))
        backtrace = (self.reports / "crash-backtrace.txt").read_text(encoding="utf-8")
        self.assertIn("seeded suite replay, seed 41071643172", backtrace)
        self.assertNotIn("did not reproduce", backtrace)

    def test_seeded_crash_keeps_original_selection(self):
        env = self._crash_env(FAKE_GDB_CRASH="1", **self._install_gdb())
        self._run(env, "--shuffle-seed", "7", "--test", "test_crashy.TestCrashy")
        dump = json.loads(self.gdb_dump.read_text(encoding="utf-8"))
        self.assertEqual(dump["ff_test"], "test_crashy.TestCrashy")
        self.assertEqual(dump["ff_seed"], "7")

    def test_unseeded_crash_reruns_single_test(self):
        env = self._crash_env(FAKE_GDB_CRASH="1", **self._install_gdb())
        proc = self._run(env)
        dump = json.loads(self.gdb_dump.read_text(encoding="utf-8"))
        self.assertEqual(dump["ff_test"], TEST_ID)
        self.assertIsNone(dump["ff_seed"])
        self.assertIn("single test", proc.stderr)
        self.assertNotIn("seeded suite replay", proc.stderr)

    def test_rerun_without_crash_says_did_not_reproduce(self):
        for extra in ((), ("--shuffle-seed", "5")):
            with self.subTest(extra=extra):
                baseline = self._run(self._crash_env(), *extra, "--no-crash-rerun")
                proc = self._run(self._crash_env(**self._install_gdb()), *extra)
                self.assertEqual(proc.returncode, baseline.returncode)
                self.assertIn("did not reproduce", proc.stderr)
                self.assertIn("did not reproduce", self.step_summary.read_text(encoding="utf-8"))
                backtrace = (self.reports / "crash-backtrace.txt").read_text(encoding="utf-8")
                self.assertIn("did not reproduce", backtrace.splitlines()[1])

    def test_seeded_replay_timeout_is_bounded(self):
        import crash_diagnosis

        self.assertEqual(crash_diagnosis.seeded_timeout(1), crash_diagnosis.RERUN_TIMEOUT)
        self.assertGreaterEqual(crash_diagnosis.seeded_timeout(600), 600)
        self.assertEqual(crash_diagnosis.seeded_timeout(10**6), crash_diagnosis.SEEDED_RERUN_CAP)


if __name__ == "__main__":
    unittest.main()

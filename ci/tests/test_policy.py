"""Host-side CI policy and runner contract tests for MaxProFrame.

Pins specifications S1-S8 from odd/tasks/ci-policy.md:
- S1: Pinned FreeCAD 1.1.4 runtime
- S2: Incremental Black + isort formatting (120 cols) on changed Python files
- S3: Full test suite for code/resources/configs; skip native tests for docs-only
- S4: Independent format and test jobs; failures/timeouts fail CI without retries
- S5: PR to main, push to main, workflow_dispatch triggers on Ubuntu runner
- S6: Minimal read-only permissions, no automated commits/pushes
- S7: 7-day failure artifact retention
- S8: Scope authorization: clean entrypoints, no out-of-scope mutation
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
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class TestChangedFilesPolicy(unittest.TestCase):
    """Tests for python3 ci/changed_files.py (S2, S3, S5, S6)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo_dir = pathlib.Path(self.tmp.name) / "repo"
        self.repo_dir.mkdir()
        self._git("init", "-b", "main")
        self._git("config", "user.email", "ci@example.com")
        self._git("config", "user.name", "CI Test")
        self._git("config", "commit.gpgSign", "false")
        (self.repo_dir / "README.md").write_text("# MaxProFrame\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(
            ["git"] + list(args), cwd=self.repo_dir, capture_output=True, text=True, check=True
        ).stdout.strip()

    def _run_changed_files(self, env_overrides=None):
        script = CI_DIR / "changed_files.py"
        self.assertTrue(script.is_file(), f"Entrypoint missing: {script}")
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [sys.executable, str(script)],
            cwd=self.repo_dir,
            env=env,
            capture_output=True,
            text=True,
        )

    def _run_event(self, event_name, payload, extra_env=None):
        event_path = pathlib.Path(self.tmp.name) / f"{event_name}_event.json"
        event_path.write_text(json.dumps(payload), encoding="utf-8")
        env = {"GITHUB_EVENT_NAME": event_name, "GITHUB_EVENT_PATH": str(event_path)}
        if extra_env:
            env.update(extra_env)
        return self._run_changed_files(env)

    def test_pr_with_modified_python_emits_expected_contract(self):
        self._git("checkout", "-b", "feature")
        py_file = self.repo_dir / "freecad" / "mod.py"
        py_file.parent.mkdir(parents=True, exist_ok=True)
        py_file.write_text("x = 1\n", encoding="utf-8")
        self._git("add", "freecad/mod.py")
        self._git("commit", "-m", "add mod")

        base_sha = self._git("rev-parse", "main")
        head_sha = self._git("rev-parse", "feature")
        output_path = pathlib.Path(self.tmp.name) / "gh_output.txt"

        proc = self._run_event(
            "pull_request",
            {"pull_request": {"base": {"sha": base_sha}, "head": {"sha": head_sha}}},
            {"GITHUB_OUTPUT": str(output_path)},
        )

        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertEqual(proc.stderr, "")
        data = json.loads(proc.stdout)
        self.assertEqual(set(data.keys()), {"base", "head", "python_files", "run_tests"})
        self.assertEqual(data["base"], base_sha)
        self.assertEqual(data["head"], head_sha)
        self.assertEqual(data["python_files"], ["freecad/mod.py"])
        self.assertIs(data["run_tests"], True)
        self.assertTrue(output_path.is_file())
        self.assertIn("run_tests=true", output_path.read_text(encoding="utf-8"))

    def test_push_docs_only_skips_tests(self):
        before_sha = self._git("rev-parse", "HEAD")
        doc_dir = self.repo_dir / "docs"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "index.md").write_text("# Docs\n", encoding="utf-8")
        self._git("add", "docs/index.md")
        self._git("commit", "-m", "docs only")
        after_sha = self._git("rev-parse", "HEAD")

        proc = self._run_event("push", {"before": before_sha, "after": after_sha})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertEqual(proc.stderr, "")
        data = json.loads(proc.stdout)
        self.assertEqual(data["python_files"], [])
        self.assertIs(data["run_tests"], False)

    def test_non_doc_resource_change_triggers_tests_without_python(self):
        before_sha = self._git("rev-parse", "HEAD")
        (self.repo_dir / "requirements.txt").write_text("pytest\n", encoding="utf-8")
        self._git("add", "requirements.txt")
        self._git("commit", "-m", "add requirements")
        after_sha = self._git("rev-parse", "HEAD")

        proc = self._run_event("push", {"before": before_sha, "after": after_sha})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["python_files"], [])
        self.assertIs(data["run_tests"], True)

    def test_deleted_and_renamed_option_like_python_files(self):
        (self.repo_dir / "old_src.py").write_text("y = 2\n", encoding="utf-8")
        (self.repo_dir / "deleted.py").write_text("z = 3\n", encoding="utf-8")
        self._git("add", "old_src.py", "deleted.py")
        self._git("commit", "-m", "add py files")
        before_sha = self._git("rev-parse", "HEAD")

        self._git("rm", "deleted.py")
        self._git("mv", "--", "old_src.py", "--flag_name.py")
        self._git("commit", "-m", "rename and delete")
        after_sha = self._git("rev-parse", "HEAD")

        proc = self._run_event("push", {"before": before_sha, "after": after_sha})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertNotIn("deleted.py", data["python_files"])
        self.assertIn("--flag_name.py", data["python_files"])
        self.assertIs(data["run_tests"], True)

    def test_initial_push_zero_before_uses_empty_tree(self):
        (self.repo_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
        self._git("add", "app.py")
        self._git("commit", "-m", "add app")
        head_sha = self._git("rev-parse", "HEAD")

        proc = self._run_event("push", {"before": "0" * 40, "after": head_sha})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["base"], EMPTY_TREE_SHA)
        self.assertEqual(data["head"], head_sha)
        self.assertIn("app.py", data["python_files"])
        self.assertIs(data["run_tests"], True)

    def test_workflow_dispatch_runs_tests_with_base_ref(self):
        self._git("checkout", "-b", "dispatch-branch")
        (self.repo_dir / "worker.py").write_text("w = 1\n", encoding="utf-8")
        self._git("add", "worker.py")
        self._git("commit", "-m", "add worker")

        proc = self._run_event("workflow_dispatch", {}, {"INPUT_BASE_REF": "main"})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["base"], self._git("rev-parse", "main"))
        self.assertEqual(data["head"], self._git("rev-parse", "HEAD"))
        self.assertEqual(data["python_files"], ["worker.py"])
        self.assertIs(data["run_tests"], True)

    def test_unknown_event_fails_with_diagnostic_stderr_no_stdout(self):
        proc = self._run_changed_files({"GITHUB_EVENT_NAME": "unsupported_event"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotEqual(proc.stderr.strip(), "")
        self.assertEqual(proc.stdout.strip(), "")


class TestCheckFormatPolicy(unittest.TestCase):
    """Tests for python3 ci/check_format.py (S2, S4, S8)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = pathlib.Path(self.tmp.name)
        self.reports_dir = self.work_dir / "reports"
        self.reports_dir.mkdir()
        self.fake_tools_dir = self.work_dir / "fake_tools"
        self.fake_tools_dir.mkdir()

        fake_script = (
            "import os, sys\n"
            "tool = sys.argv[0]\n"
            "log = os.environ.get('FAKE_LOG_' + os.path.basename(tool).upper().replace('.PY', ''))\n"
            "if log:\n"
            "    with open(log, 'a', encoding='utf-8') as f:\n"
            "        f.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "code = int(os.environ.get('FAKE_EXIT_' + os.path.basename(tool).upper().replace('.PY', ''), '0'))\n"
            "sys.exit(code)\n"
        )
        (self.fake_tools_dir / "black.py").write_text(fake_script, encoding="utf-8")
        (self.fake_tools_dir / "isort.py").write_text(fake_script, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run_check_format(self, changes_file, env_overrides=None):
        script = CI_DIR / "check_format.py"
        self.assertTrue(script.is_file(), f"Entrypoint missing: {script}")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.fake_tools_dir) + (os.pathsep + env.get("PYTHONPATH", ""))
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--changes",
                str(changes_file),
                "--reports",
                str(self.reports_dir),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_format_runs_both_tools_with_exact_argv_and_produces_reports(self):
        changes = self.work_dir / "changes.json"
        changes.write_text(json.dumps({"python_files": ["foo.py", "bar/baz.py"]}), encoding="utf-8")
        black_log = self.work_dir / "black.log"
        isort_log = self.work_dir / "isort.log"

        proc = self._run_check_format(
            changes,
            {
                "FAKE_LOG_BLACK": str(black_log),
                "FAKE_LOG_ISORT": str(isort_log),
                "FAKE_EXIT_BLACK": "0",
                "FAKE_EXIT_ISORT": "0",
            },
        )

        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(black_log.is_file())
        self.assertTrue(isort_log.is_file())
        self.assertIn("--check", black_log.read_text(encoding="utf-8"))
        self.assertIn("foo.py", black_log.read_text(encoding="utf-8"))
        self.assertIn("--check-only", isort_log.read_text(encoding="utf-8"))
        self.assertIn("bar/baz.py", isort_log.read_text(encoding="utf-8"))
        self.assertTrue(len(list(self.reports_dir.iterdir())) >= 2)

    def test_black_failure_still_attempts_isort_and_returns_failure(self):
        changes = self.work_dir / "changes.json"
        changes.write_text(json.dumps({"python_files": ["a.py"]}), encoding="utf-8")
        isort_log = self.work_dir / "isort.log"

        proc = self._run_check_format(
            changes,
            {
                "FAKE_LOG_ISORT": str(isort_log),
                "FAKE_EXIT_BLACK": "1",
                "FAKE_EXIT_ISORT": "0",
            },
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(isort_log.is_file(), "isort must still be attempted when Black fails")

    def test_no_python_files_clean_skips_without_running_tools(self):
        changes = self.work_dir / "changes.json"
        changes.write_text(json.dumps({"python_files": []}), encoding="utf-8")
        black_log = self.work_dir / "black.log"

        proc = self._run_check_format(changes, {"FAKE_LOG_BLACK": str(black_log)})
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertFalse(black_log.is_file())

    def test_missing_or_corrupt_changes_fails_non_zero(self):
        proc = self._run_check_format(self.work_dir / "does_not_exist.json")
        self.assertNotEqual(proc.returncode, 0)


class TestRunTestsPolicy(unittest.TestCase):
    """Tests for python3 ci/run_tests.py (S1, S3, S4, S7)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = pathlib.Path(self.tmp.name)
        self.reports_dir = self.work_dir / "reports"
        self.reports_dir.mkdir()

        self.fake_bin = self.work_dir / "fake_freecad"
        self.fake_bin.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, time\n"
            "dump = os.environ.get('FAKE_ENV_DUMP')\n"
            "if dump:\n"
            "    with open(dump, 'w', encoding='utf-8') as f:\n"
            "        json.dump(dict(os.environ), f)\n"
            "argv_dump = os.environ.get('FAKE_ARGV_DUMP')\n"
            "if argv_dump:\n"
            "    with open(argv_dump, 'w', encoding='utf-8') as f:\n"
            "        json.dump(sys.argv[1:], f)\n"
            "sleep_s = float(os.environ.get('FAKE_SLEEP', '0'))\n"
            "if sleep_s > 0:\n"
            "    time.sleep(sleep_s)\n"
            "summary = os.environ.get('FAKE_SUMMARY_CONTENT')\n"
            "summary_path = os.environ.get('FAKE_SUMMARY_PATH')\n"
            "if summary is not None and summary_path:\n"
            "    with open(summary_path, 'w', encoding='utf-8') as f:\n"
            "        f.write(summary)\n"
            "sys.exit(int(os.environ.get('FAKE_EXIT_CODE', '0')))\n",
            encoding="utf-8",
        )
        self.fake_bin.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_tests_host(self, timeout="10", env_overrides=None):
        script = CI_DIR / "run_tests.py"
        self.assertTrue(script.is_file(), f"Entrypoint missing: {script}")
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(self.fake_bin),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                str(timeout),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_environment_isolation_and_successful_run(self):
        env_dump = self.work_dir / "env.json"
        argv_dump = self.work_dir / "argv.json"
        summary_path = self.reports_dir / "summary.json"
        summary_data = {"tests": 15, "failures": 0, "errors": 0, "skipped": 0, "successful": True}

        proc = self._run_tests_host(
            timeout="10",
            env_overrides={
                "FAKE_ENV_DUMP": str(env_dump),
                "FAKE_ARGV_DUMP": str(argv_dump),
                "FAKE_SUMMARY_PATH": str(summary_path),
                "FAKE_SUMMARY_CONTENT": json.dumps(summary_data),
                "DISPLAY": ":99",
                "WAYLAND_DISPLAY": "wayland-0",
                "FREECAD_USER_HOME": "/inherited/fc_home",
                "FRAMEFORGE_USER_PROFILES_DIR": "/inherited/profiles",
            },
        )

        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(env_dump.is_file())
        dumped_env = json.loads(env_dump.read_text(encoding="utf-8"))
        self.assertNotIn("DISPLAY", dumped_env)
        self.assertNotIn("WAYLAND_DISPLAY", dumped_env)
        self.assertEqual(dumped_env.get("QT_QPA_PLATFORM"), "offscreen")
        self.assertEqual(dumped_env.get("FREECAD_QT_QPA_PLATFORM"), "offscreen")
        self.assertNotEqual(dumped_env.get("HOME"), os.environ.get("HOME"))
        self.assertIn("FREECAD_USER_HOME", dumped_env)
        self.assertNotEqual(dumped_env.get("FREECAD_USER_HOME"), "/inherited/fc_home")
        self.assertIn("FRAMEFORGE_USER_PROFILES_DIR", dumped_env)
        self.assertNotEqual(dumped_env.get("FRAMEFORGE_USER_PROFILES_DIR"), "/inherited/profiles")

        self.assertTrue(argv_dump.is_file())
        dumped_argv = json.loads(argv_dump.read_text(encoding="utf-8"))
        self.assertNotIn("-platform", dumped_argv, "Must NOT pass -platform in argv; FreeCAD CLI rejects it")
        self.assertIn("--user-cfg", dumped_argv)
        self.assertTrue(
            any(arg.endswith("run-tests.FCMacro") for arg in dumped_argv),
            "Must pass run-tests.FCMacro in argv",
        )

    def test_run_tests_passes_no_platform_argv_and_sets_offscreen_env(self):
        """FreeCAD 1.1.4 Boost CLI options reject -platform. Runner must omit -platform and set offscreen env."""
        argv_dump = self.work_dir / "argv_noplatform.json"
        env_dump = self.work_dir / "env_noplatform.json"
        summary_path = self.reports_dir / "summary.json"
        summary_data = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "successful": True}

        proc = self._run_tests_host(
            timeout="10",
            env_overrides={
                "FAKE_ARGV_DUMP": str(argv_dump),
                "FAKE_ENV_DUMP": str(env_dump),
                "FAKE_SUMMARY_PATH": str(summary_path),
                "FAKE_SUMMARY_CONTENT": json.dumps(summary_data),
            },
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(argv_dump.is_file())
        dumped_argv = json.loads(argv_dump.read_text(encoding="utf-8"))
        self.assertNotIn("-platform", dumped_argv, "Must not pass -platform in argv")
        self.assertIn("--user-cfg", dumped_argv)
        dumped_env = json.loads(env_dump.read_text(encoding="utf-8"))
        self.assertEqual(dumped_env.get("QT_QPA_PLATFORM"), "offscreen")
        self.assertEqual(dumped_env.get("FREECAD_QT_QPA_PLATFORM"), "offscreen")

    def test_run_tests_resolves_apprun_to_usr_bin_freecad_with_bootstrap_env(self):
        """When --freecad-bin points to AppRun, resolve to usr/bin/freecad without executing AppRun script."""
        dist_root = self.work_dir / "fake_dist"
        apprun = dist_root / "AppRun"
        apprun.parent.mkdir(parents=True, exist_ok=True)
        # Sentinel AppRun must NEVER be executed
        apprun.write_text("#!/bin/sh\necho 'ERROR: AppRun sentinel executed' >&2\nexit 99\n", encoding="utf-8")
        apprun.chmod(0o755)

        bin_dir = dist_root / "usr" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        native_bin = bin_dir / "freecad"

        driver_py = self.work_dir / "dist_driver.py"
        driver_py.write_text(
            "import json, os, sys\n"
            "env_file = os.environ.get('RECORD_ENV')\n"
            "if env_file:\n"
            "    with open(env_file, 'w', encoding='utf-8') as f:\n"
            "        json.dump(dict(os.environ), f)\n"
            "argv_file = os.environ.get('RECORD_ARGV')\n"
            "if argv_file:\n"
            "    with open(argv_file, 'w', encoding='utf-8') as f:\n"
            "        json.dump(sys.argv[1:], f)\n"
            "summary_path = os.environ.get('RECORD_SUMMARY_PATH')\n"
            "if summary_path:\n"
            "    with open(summary_path, 'w', encoding='utf-8') as f:\n"
            "        json.dump({'tests': 5, 'failures': 0, 'errors': 0, 'skipped': 0, 'successful': True}, f)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )

        # Shell launcher invoking host python with -E to ignore fake prefix during host python startup
        native_bin.write_text(
            f'#!/bin/sh\nexec {repr(sys.executable)} -E {repr(str(driver_py))} "$@"\n',
            encoding="utf-8",
        )
        native_bin.chmod(0o755)

        record_env = self.work_dir / "apprun_env.json"
        record_argv = self.work_dir / "apprun_argv.json"
        summary_path = self.reports_dir / "summary.json"

        script = CI_DIR / "run_tests.py"
        env = os.environ.copy()
        env["RECORD_ENV"] = str(record_env)
        env["RECORD_ARGV"] = str(record_argv)
        env["RECORD_SUMMARY_PATH"] = str(summary_path)
        env["FREECAD_USER_HOME"] = "/inherited/home"
        env["FRAMEFORGE_USER_PROFILES_DIR"] = "/inherited/profiles"

        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(apprun),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                "10",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(record_argv.is_file(), "Native binary driver must be executed")
        dumped_argv = json.loads(record_argv.read_text(encoding="utf-8"))
        self.assertNotIn("-platform", dumped_argv)
        self.assertIn("--user-cfg", dumped_argv)

        self.assertTrue(record_env.is_file())
        dumped_env = json.loads(record_env.read_text(encoding="utf-8"))
        self.assertEqual(dumped_env.get("PREFIX"), str(dist_root / "usr"))
        self.assertEqual(dumped_env.get("PYTHONHOME"), str(dist_root / "usr"))
        self.assertEqual(dumped_env.get("PATH_TO_FREECAD_LIBDIR"), str(dist_root / "usr" / "lib"))
        self.assertEqual(dumped_env.get("SSL_CERT_FILE"), str(dist_root / "usr" / "ssl" / "cacert.pem"))
        self.assertEqual(dumped_env.get("GIT_SSL_CAINFO"), str(dist_root / "usr" / "ssl" / "cacert.pem"))
        self.assertEqual(dumped_env.get("FONTCONFIG_FILE"), "/etc/fonts/fonts.conf")
        self.assertEqual(dumped_env.get("FONTCONFIG_PATH"), "/etc/fonts")
        self.assertEqual(dumped_env.get("QT_QPA_PLATFORM"), "offscreen")
        self.assertEqual(dumped_env.get("FREECAD_QT_QPA_PLATFORM"), "offscreen")
        self.assertNotEqual(dumped_env.get("FREECAD_USER_HOME"), "/inherited/home")
        self.assertNotEqual(dumped_env.get("FRAMEFORGE_USER_PROFILES_DIR"), "/inherited/profiles")

    def test_run_tests_apprun_missing_native_binary_fails_clearly(self):
        """When --freecad-bin points to AppRun without usr/bin/freecad, fail before child launch."""
        dist_root = self.work_dir / "broken_dist"
        apprun = dist_root / "AppRun"
        apprun.parent.mkdir(parents=True, exist_ok=True)
        apprun.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        apprun.chmod(0o755)

        script = CI_DIR / "run_tests.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(apprun),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                "10",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("freecad", proc.stderr.lower())

    def test_timeout_kills_process_group_with_code_124(self):
        proc = self._run_tests_host(
            timeout="0.2",
            env_overrides={
                "FAKE_SLEEP": "2.0",
                "FAKE_SUMMARY_PATH": str(self.reports_dir / "summary.json"),
                "FAKE_SUMMARY_CONTENT": json.dumps(
                    {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "successful": True}
                ),
            },
        )
        self.assertEqual(proc.returncode, 124)

    def test_nonzero_child_exit_propagates_failure(self):
        proc = self._run_tests_host(env_overrides={"FAKE_EXIT_CODE": "1"})
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_or_corrupted_summary_fails(self):
        proc = self._run_tests_host(env_overrides={"FAKE_EXIT_CODE": "0"})
        self.assertNotEqual(proc.returncode, 0)

    def test_zero_tests_fails(self):
        summary_path = self.reports_dir / "summary.json"
        proc = self._run_tests_host(
            env_overrides={
                "FAKE_SUMMARY_PATH": str(summary_path),
                "FAKE_SUMMARY_CONTENT": json.dumps(
                    {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "successful": True}
                ),
                "FAKE_EXIT_CODE": "0",
            }
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_suite_failures_in_summary_fails(self):
        summary_path = self.reports_dir / "summary.json"
        proc = self._run_tests_host(
            env_overrides={
                "FAKE_SUMMARY_PATH": str(summary_path),
                "FAKE_SUMMARY_CONTENT": json.dumps(
                    {"tests": 10, "failures": 2, "errors": 0, "skipped": 0, "successful": False}
                ),
                "FAKE_EXIT_CODE": "0",
            }
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_run_tests_rejects_stale_prepopulated_summary(self):
        """A1: Stale summary in reports dir must be purged before launch and never reused on missing child output."""
        summary_path = self.reports_dir / "summary.json"
        stale_summary = {
            "tests": 8,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "successful": True,
        }
        summary_path.write_text(json.dumps(stale_summary), encoding="utf-8")

        proc = self._run_tests_host(env_overrides={"FAKE_EXIT_CODE": "0"})
        self.assertNotEqual(proc.returncode, 0, "Wrapper must not exit 0 on stale pre-existing summary")
        self.assertNotIn("succeeded", proc.stdout.lower(), "Must not claim success from stale summary")
        self.assertFalse(summary_path.is_file(), "Old summary must be purged before run and not reused")

    def test_run_tests_rejects_malformed_or_inconsistent_summary_schemas(self):
        """A2: Schema validation must enforce required fields, exact types, tests>0, and count consistency."""
        cases = [
            ("missing_keys", {"tests": 1, "successful": True}),
            ("negative_failures", {"tests": 1, "failures": -1, "errors": 0, "skipped": 0, "successful": True}),
            (
                "bool_count_str_success",
                {"tests": True, "failures": 0, "errors": 0, "skipped": 0, "successful": "false"},
            ),
            ("over_skipped", {"tests": 1, "failures": 0, "errors": 0, "skipped": 2, "successful": True}),
        ]
        summary_path = self.reports_dir / "summary.json"
        for name, bad_summary in cases:
            with self.subTest(case=name):
                proc = self._run_tests_host(
                    env_overrides={
                        "FAKE_SUMMARY_PATH": str(summary_path),
                        "FAKE_SUMMARY_CONTENT": json.dumps(bad_summary),
                        "FAKE_EXIT_CODE": "0",
                    }
                )
                self.assertNotEqual(proc.returncode, 0, f"Malformed schema case '{name}' must fail")
                self.assertNotIn("succeeded", proc.stdout.lower())
                self.assertNotEqual(proc.stderr.strip(), "")

    def test_run_tests_macro_discovery_ignores_ff_pattern_and_runs_full_suite(self):
        """A3: Macro discovery must hardcode 'test_*.py' and not allow FF_PATTERN env to select subsets."""
        fixture_root = self.work_dir / "fixture_suite"
        fixture_tests = fixture_root / "tests"
        fixture_tests.mkdir(parents=True, exist_ok=True)
        (fixture_tests / "test_pass.py").write_text(
            "import unittest\nclass PassTest(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        (fixture_tests / "test_fail.py").write_text(
            "import unittest\nclass FailTest(unittest.TestCase):\n    def test_bad(self):\n        self.fail('intentional fixture failure')\n",
            encoding="utf-8",
        )

        runpy_fake_bin = self.work_dir / "runpy_fake_freecad"
        runpy_content = (
            "#!/usr/bin/env python3\n"
            "import os, sys, types, runpy\n"
            "sys.modules['FreeCAD'] = types.SimpleNamespace(Version=lambda: ['1', '1', '4'])\n"
            "sys.modules['Part'] = types.ModuleType('Part')\n"
            "sys.modules['FreeCADGui'] = types.ModuleType('FreeCADGui')\n"
            "pkg = types.ModuleType('freecad')\n"
            "pkg.__path__ = []\n"
            "sys.modules['freecad'] = pkg\n"
            "sys.version_info = (3, 11, 0)\n"
            f"os.environ['FF_ROOT'] = {repr(str(fixture_root))}\n"
            "runpy.run_path(sys.argv[-1])\n"
        )
        runpy_fake_bin.write_text(runpy_content, encoding="utf-8")
        runpy_fake_bin.chmod(0o755)

        script = CI_DIR / "run_tests.py"
        env = os.environ.copy()
        env["FF_PATTERN"] = "test_pass.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(runpy_fake_bin),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                "10",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0, "Suite with failing test must exit non-zero")
        summary_file = self.reports_dir / "summary.json"
        self.assertTrue(summary_file.is_file(), "summary.json must be written by macro")
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        self.assertEqual(summary.get("tests"), 2, "Discovery must find both test modules, ignoring FF_PATTERN")
        self.assertEqual(summary.get("failures"), 1, "Must record 1 failure from test_fail.py")
        self.assertIs(summary.get("successful"), False, "Summary must report successful: false")

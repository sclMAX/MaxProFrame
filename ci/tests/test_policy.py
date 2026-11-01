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
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "ci"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
TARGETS_PATH = CI_DIR / "targets.json"


def load_targets():
    """The pinned runtimes; ci/targets.json is the single source of truth (S1)."""
    return json.loads(TARGETS_PATH.read_text(encoding="utf-8"))


def wrong_python(target):
    major, minor = load_targets()[target]["expected_python"]
    return (major, minor + 1, 0)


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
            "cfg_dump = os.environ.get('FAKE_CFG_DUMP')\n"
            "if cfg_dump:\n"
            "    import pathlib\n"
            "    cfg = pathlib.Path(sys.argv[sys.argv.index('--user-cfg') + 1])\n"
            "    pathlib.Path(cfg_dump).write_text(cfg.read_text(encoding='utf-8'), encoding='utf-8')\n"
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

    def test_notification_preferences_exist_at_child_launch(self):
        cfg_dump = self.work_dir / "startup.cfg"
        env_dump = self.work_dir / "env.json"
        argv_dump = self.work_dir / "argv.json"
        proc = self._run_tests_host(
            env_overrides={
                "FAKE_CFG_DUMP": str(cfg_dump),
                "FAKE_ENV_DUMP": str(env_dump),
                "FAKE_ARGV_DUMP": str(argv_dump),
                "FAKE_SUMMARY_PATH": str(self.reports_dir / "summary.json"),
                "FAKE_SUMMARY_CONTENT": json.dumps(
                    {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "successful": True}
                ),
            }
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "run_tests: Test suite succeeded (1 tests executed).\n")
        self.assertEqual(proc.stderr, "")
        root = ET.fromstring(cfg_dump.read_text(encoding="utf-8"))
        self.assertEqual(root.tag, "FCParameters")
        self.assertEqual(root.attrib, {})
        group = root
        for name in ("Root", "BaseApp", "Preferences", "NotificationArea"):
            self.assertEqual(len(group), 1)
            group = group[0]
            self.assertEqual(group.tag, "FCParamGroup")
            self.assertEqual(group.attrib, {"Name": name})
        # Exact leaves exclude NotificationAreaEnabled and any log/severity suppression.
        self.assertEqual(
            [(leaf.tag, leaf.attrib, len(leaf)) for leaf in group],
            [
                ("FCBool", {"Name": "NonIntrusiveNotificationsEnabled", "Value": "0"}, 0),
                ("FCInt", {"Name": "MaxOpenNotifications", "Value": "0"}, 0),
            ],
        )
        env = json.loads(env_dump.read_text(encoding="utf-8"))
        argv = json.loads(argv_dump.read_text(encoding="utf-8"))
        cfg = pathlib.Path(argv[argv.index("--user-cfg") + 1])
        self.assertEqual(cfg.parent, pathlib.Path(env["XDG_CONFIG_HOME"]))
        self.assertNotEqual(cfg.parent, pathlib.Path(os.environ.get("XDG_CONFIG_HOME", ".")))
        self.assertFalse(cfg.exists(), "Temporary profile must be cleaned after the child exits")

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
                "MAXPROFRAME_USER_PROFILES_DIR": "/inherited/profiles",
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
        self.assertIn("MAXPROFRAME_USER_PROFILES_DIR", dumped_env)
        self.assertNotEqual(dumped_env.get("MAXPROFRAME_USER_PROFILES_DIR"), "/inherited/profiles")

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
        env["MAXPROFRAME_USER_PROFILES_DIR"] = "/inherited/profiles"

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
        self.assertNotEqual(dumped_env.get("MAXPROFRAME_USER_PROFILES_DIR"), "/inherited/profiles")

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
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "run_tests error: FreeCAD process timed out after 0.2s (killed process group).\n")
        self.assertFalse((self.reports_dir / "summary.json").exists())

    def test_stale_diagnostics_are_removed_without_changing_child_exit(self):
        for name in ("python-stacks.log", "modal-state.jsonl"):
            (self.reports_dir / name).write_text("stale private evidence", encoding="utf-8")
        proc = self._run_tests_host(env_overrides={"FAKE_EXIT_CODE": "7"})
        self.assertEqual(proc.returncode, 7)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "run_tests error: FreeCAD child process failed with exit code 7.\n")
        for name in ("python-stacks.log", "modal-state.jsonl"):
            self.assertFalse((self.reports_dir / name).exists())

    def test_nonzero_child_exit_propagates_failure(self):
        proc = self._run_tests_host(env_overrides={"FAKE_EXIT_CODE": "1"})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "run_tests error: FreeCAD child process failed with exit code 1.\n")

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

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(
            proc.stderr,
            "run_tests error: Test suite reported failures (2), errors (0), or successful is False.\n",
        )

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

    def test_run_tests_target_defaults_to_stable(self):
        """Runner must default --target to 'stable' and export FF_TARGET=stable to child."""
        env_dump = self.work_dir / "env_target_default.json"
        summary_path = self.reports_dir / "summary.json"
        summary_data = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "successful": True}

        proc = self._run_tests_host(
            timeout="10",
            env_overrides={
                "FAKE_ENV_DUMP": str(env_dump),
                "FAKE_SUMMARY_PATH": str(summary_path),
                "FAKE_SUMMARY_CONTENT": json.dumps(summary_data),
            },
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(env_dump.is_file())
        dumped_env = json.loads(env_dump.read_text(encoding="utf-8"))
        self.assertEqual(dumped_env.get("FF_TARGET"), "stable")

    def test_run_tests_target_explicit_weekly(self):
        """Runner must accept --target weekly and export FF_TARGET=weekly to child."""
        env_dump = self.work_dir / "env_target_weekly.json"
        summary_path = self.reports_dir / "summary.json"
        summary_data = {"tests": 1, "failures": 0, "errors": 0, "skipped": 0, "successful": True}

        script = CI_DIR / "run_tests.py"
        env = os.environ.copy()
        env["FAKE_ENV_DUMP"] = str(env_dump)
        env["FAKE_SUMMARY_PATH"] = str(summary_path)
        env["FAKE_SUMMARY_CONTENT"] = json.dumps(summary_data)

        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(self.fake_bin),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                "10",
                "--target",
                "weekly",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(env_dump.is_file())
        dumped_env = json.loads(env_dump.read_text(encoding="utf-8"))
        self.assertEqual(dumped_env.get("FF_TARGET"), "weekly")

    def test_run_tests_target_rejects_invalid_choice(self):
        """Runner must reject unsupported --target choices with non-zero exit and diagnostic error."""
        script = CI_DIR / "run_tests.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--freecad-bin",
                str(self.fake_bin),
                "--reports",
                str(self.reports_dir),
                "--timeout",
                "10",
                "--target",
                "invalid_target",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid choice", proc.stderr.lower())

    def _run_macro_synthetic(self, target, fc_version, py_version):
        fixture_root = self.work_dir / f"fixture_{target}_{fc_version[0]}"
        fixture_tests = fixture_root / "tests"
        fixture_tests.mkdir(parents=True, exist_ok=True)
        (fixture_tests / "test_dummy.py").write_text(
            "import unittest\nclass DummyTest(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
            encoding="utf-8",
        )

        runpy_fake_bin = self.work_dir / f"runpy_fake_{target}_{fc_version[0]}"
        runpy_content = (
            "#!/usr/bin/env python3\n"
            "import os, sys, types, runpy\n"
            f"sys.modules['FreeCAD'] = types.SimpleNamespace(Version=lambda: {repr(list(fc_version))})\n"
            "sys.modules['Part'] = types.ModuleType('Part')\n"
            "sys.modules['FreeCADGui'] = types.ModuleType('FreeCADGui')\n"
            "pkg = types.ModuleType('freecad')\n"
            "pkg.__path__ = []\n"
            "sys.modules['freecad'] = pkg\n"
            f"sys.version_info = {repr(py_version)}\n"
            f"os.environ['FF_ROOT'] = {repr(str(fixture_root))}\n"
            "runpy.run_path(sys.argv[-1])\n"
        )
        runpy_fake_bin.write_text(runpy_content, encoding="utf-8")
        runpy_fake_bin.chmod(0o755)

        reports_dir = self.work_dir / f"reports_{target}_{fc_version[0]}"
        reports_dir.mkdir(parents=True, exist_ok=True)

        script = CI_DIR / "run_tests.py"
        cmd = [
            sys.executable,
            str(script),
            "--freecad-bin",
            str(runpy_fake_bin),
            "--reports",
            str(reports_dir),
            "--timeout",
            "10",
        ]
        if target is not None:
            cmd.extend(["--target", target])

        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        summary_file = reports_dir / "summary.json"
        summary = None
        if summary_file.is_file():
            try:
                summary = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        stderr_file = reports_dir / "stderr.log"
        child_stderr = stderr_file.read_text(encoding="utf-8") if stderr_file.is_file() else ""
        return proc, summary_file, summary, child_stderr

    def test_macro_accepts_stable_target_with_1_1_4_and_py311(self):
        """Macro must accept stable target when runtime matches FreeCAD 1.1.4 and Python 3.11."""
        proc, summary_file, summary, _ = self._run_macro_synthetic(
            target="stable", fc_version=("1", "1", "4"), py_version=(3, 11, 0)
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(summary_file.is_file(), "summary.json must be generated")
        self.assertTrue((summary_file.parent / "python-stacks.log").is_file())
        self.assertNotIn(
            "stack-diagnostics-unavailable", (summary_file.parent / "startup.log").read_text(encoding="utf-8")
        )
        self.assertEqual(summary.get("tests"), 1)
        self.assertIs(summary.get("successful"), True)

    def _runtime(self, target):
        pinned = load_targets()[target]
        return tuple(pinned["expected_freecad"]), (*pinned["expected_python"], 0)

    def test_macro_accepts_weekly_target_when_runtime_matches_targets_json(self):
        """Macro must accept weekly target when the runtime matches the weekly entry of ci/targets.json."""
        fc_version, py_version = self._runtime("weekly")
        proc, summary_file, summary, _ = self._run_macro_synthetic(
            target="weekly", fc_version=fc_version, py_version=py_version
        )
        self.assertEqual(proc.returncode, 0, f"Stderr: {proc.stderr}")
        self.assertTrue(summary_file.is_file(), "summary.json must be generated")
        self.assertEqual(summary.get("tests"), 1)
        self.assertIs(summary.get("successful"), True)

    def test_macro_rejects_weekly_runtime_when_target_is_stable(self):
        """Macro targeting stable must strictly reject the weekly runtime without writing summary."""
        fc_version, py_version = self._runtime("weekly")
        proc, summary_file, summary, child_stderr = self._run_macro_synthetic(
            target="stable", fc_version=fc_version, py_version=py_version
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(summary_file.is_file(), "Rejected runtime must NOT generate summary.json")
        self.assertIn("incompatible freecad runtime version", child_stderr.lower())

    def test_macro_rejects_stable_runtime_when_target_is_weekly(self):
        """Macro targeting weekly must strictly reject the stable runtime without writing summary."""
        fc_version, py_version = self._runtime("stable")
        proc, summary_file, summary, child_stderr = self._run_macro_synthetic(
            target="weekly", fc_version=fc_version, py_version=py_version
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(summary_file.is_file(), "Rejected runtime must NOT generate summary.json")
        self.assertIn("incompatible freecad runtime version", child_stderr.lower())

    def test_macro_rejects_incompatible_python_on_weekly_target(self):
        """Macro targeting weekly must strictly reject a Python other than the pinned one, without a summary."""
        fc_version, _ = self._runtime("weekly")
        proc, summary_file, summary, child_stderr = self._run_macro_synthetic(
            target="weekly", fc_version=fc_version, py_version=wrong_python("weekly")
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(summary_file.is_file(), "Rejected runtime must NOT generate summary.json")
        self.assertIn("incompatible python runtime version", child_stderr.lower())

    def test_macro_error_names_the_pinned_target_from_targets_json(self):
        """The rejection message keeps naming the pinned baseline/weekly label, now read from ci/targets.json."""
        _, py_version = self._runtime("stable")
        proc, _, _, child_stderr = self._run_macro_synthetic(
            target="stable", fc_version=("0", "0", "0"), py_version=py_version
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Pinned baseline FreeCAD 1.1.4 (Python 3.11) is required.", child_stderr)
        weekly = load_targets()["weekly"]
        fc_version, py_version = self._runtime("weekly")
        proc, _, _, child_stderr = self._run_macro_synthetic(
            target="weekly", fc_version=("0", "0", "0"), py_version=py_version
        )
        label = (
            f"Pinned weekly {weekly['label']} (Version {'.'.join(fc_version)}, "
            f"Python {py_version[0]}.{py_version[1]}) is required."
        )
        self.assertIn(label, child_stderr)

    def test_macro_has_no_hardcoded_runtime_versions(self):
        """Expected versions and labels live in ci/targets.json, not in the macro."""
        macro = (CI_DIR / "run-tests.FCMacro").read_text(encoding="utf-8")
        self.assertIn("targets.json", macro)
        self.assertNotIn("expected_fc = (", macro)
        self.assertNotIn("expected_py = (", macro)
        self.assertNotRegex(macro, r"weekly-\d{4}\.\d{2}\.\d{2}")


class TestTargetsFilePolicy(unittest.TestCase):
    """ci/targets.json is the single source of truth for the pinned native targets (S1)."""

    KEYS = {"label", "url", "sha256", "timeout", "blocking", "shards", "expected_freecad", "expected_python"}

    def test_defines_exactly_stable_and_weekly_with_all_fields(self):
        targets = load_targets()
        self.assertEqual(list(targets), ["stable", "weekly"])
        for name, entry in targets.items():
            self.assertEqual(set(entry), self.KEYS, name)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(entry["url"].startswith("https://github.com/FreeCAD/FreeCAD/releases/download/"))
            self.assertNotIn("latest", entry["url"])
            self.assertEqual(len(entry["expected_freecad"]), 3)
            self.assertTrue(all(isinstance(part, str) and part.isdigit() for part in entry["expected_freecad"]))
            self.assertEqual(len(entry["expected_python"]), 2)
            self.assertTrue(all(isinstance(part, int) for part in entry["expected_python"]))
            self.assertIsInstance(entry["timeout"], int)
            self.assertIsInstance(entry["blocking"], bool)
            self.assertIs(type(entry["shards"]), int)
            self.assertGreaterEqual(entry["shards"], 1)

    def test_stable_pin_is_the_accepted_baseline(self):
        stable = load_targets()["stable"]
        self.assertEqual(stable["label"], "FreeCAD 1.1.4")
        self.assertEqual(
            stable["url"],
            "https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage",
        )
        self.assertEqual(stable["sha256"], "f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434")
        self.assertEqual((stable["timeout"], stable["blocking"], stable["shards"]), (420, True, 2))
        self.assertEqual((stable["expected_freecad"], stable["expected_python"]), (["1", "1", "4"], [3, 11]))

    def test_weekly_is_pinned_to_one_tag_and_informative(self):
        weekly = load_targets()["weekly"]
        tag = weekly["label"].removeprefix("FreeCAD ")
        self.assertRegex(tag, r"^weekly-\d{4}\.\d{2}\.\d{2}$")
        self.assertEqual(
            weekly["url"],
            f"https://github.com/FreeCAD/FreeCAD/releases/download/{tag}/FreeCAD_{tag}-Linux-x86_64.AppImage",
        )
        self.assertEqual((weekly["timeout"], weekly["blocking"], weekly["shards"]), (480, False, 2))

    def test_run_tests_target_choices_come_from_targets_json(self):
        from ci import run_tests

        self.assertEqual(run_tests.target_names(), list(load_targets()))
        script = (CI_DIR / "run_tests.py").read_text(encoding="utf-8")
        self.assertNotIn('choices=["stable", "weekly"]', script)
        self.assertNotRegex(script, r"weekly-\d{4}\.\d{2}\.\d{2}")

    def test_run_tests_help_names_no_specific_weekly_version(self):
        done = subprocess.run(
            [sys.executable, str(CI_DIR / "run_tests.py"), "--help"], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("stable", done.stdout)
        self.assertIn("weekly", done.stdout)
        self.assertNotRegex(done.stdout, r"weekly-\d{4}")


class TestWorkflowStaticPolicy(unittest.TestCase):
    """Static checks for .github/workflows/ci.yml (S1, S4, S5, S6, S7)."""

    def setUp(self):
        self.assertTrue(WORKFLOW_PATH.is_file(), f"Workflow missing: {WORKFLOW_PATH}")
        self.content = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_defines_required_triggers(self):
        self.assertIn("pull_request:", self.content)
        self.assertIn("push:", self.content)
        self.assertIn("workflow_dispatch:", self.content, "S5 requires manual workflow_dispatch trigger")
        self.assertIn("main", self.content)

    def test_workflow_has_separate_independent_jobs(self):
        self.assertIn("jobs:", self.content)
        has_format_job = any(k in self.content for k in ["lint:", "format:", "check-format:"])
        has_test_job = any(k in self.content for k in ["test:", "tests:", "native-tests:"])
        self.assertTrue(
            has_format_job and has_test_job,
            "S4 requires independent jobs for formatting and native tests",
        )

    def test_workflow_pins_permissions_and_freecad_baseline(self):
        self.assertIn("permissions:", self.content, "S6 requires explicit pinned permissions block")
        self.assertIn("contents: read", self.content, "S6 requires minimal read-only permissions")
        self.assertEqual(load_targets()["stable"]["label"], "FreeCAD 1.1.4")
        self.assertNotIn("pip install --upgrade pip", self.content, "CI must not introduce an unpinned pip upgrade")

    def test_workflow_caches_appimage_by_checksum_and_still_verifies(self):
        """AppImages are cached under their pinned SHA-256 and a cache hit is still checksum-verified."""
        self.assertIn("actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9", self.content)
        self.assertIn("key: freecad-appimage-${{ matrix.sha256 }}", self.content)
        download = self.content.split("- name: Download and verify FreeCAD AppImage", 1)[1].split("- name:", 1)[0]
        self.assertIn("steps.appimage-cache.outputs.cache-hit != 'true'", download, "Download only on cache miss")
        verify = self.content.split("- name: Verify FreeCAD AppImage checksum", 1)[1].split("- name:", 1)[0]
        self.assertIn("sha256sum -c -", verify)
        self.assertNotIn("cache-hit", verify, "Checksum must be verified on cache hits too")

    def test_workflow_cancels_superseded_runs_except_on_main(self):
        """Superseded branch/PR runs are cancelled; every main commit keeps its own result."""
        self.assertIn("concurrency:", self.content)
        # A shared main group would still cancel a pending main run, so main commits get unique groups.
        self.assertIn(
            "group: ci-${{ github.workflow }}-${{ github.ref == 'refs/heads/main' && github.sha || github.ref }}",
            self.content,
        )
        self.assertIn("cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}", self.content)

    def test_workflow_builds_matrix_from_targets_json(self):
        """The native job runs a matrix built by a read-only `targets` job from ci/targets.json."""
        self.assertIn("fail-fast: false", self.content, "Matrix must run both targets without early cancellation")
        self.assertIn("matrix: ${{ fromJSON(needs.targets.outputs.matrix) }}", self.content)
        self.assertNotIn("include:", self.content, "Targets must not be listed inside the workflow")
        self.assertNotIn("target: rc", self.content)
        targets_job = self.content.split("\n  targets:\n", 1)[1].split("\n  test:\n", 1)[0]
        self.assertIn("permissions:\n      contents: read", targets_job)
        self.assertIn("persist-credentials: false", targets_job)
        self.assertIn("ci/targets.json", targets_job)
        self.assertIn("matrix: ${{ steps.matrix.outputs.matrix }}", targets_job)
        test_job = self.content.split("\n  test:\n", 1)[1]
        self.assertRegex(test_job, r"(?m)^    needs: targets$")

    def test_workflow_keeps_pinned_values_out_of_the_yaml(self):
        """Nothing about the pinned runtimes is hard-coded in ci.yml any more."""
        self.assertNotIn("latest", self.content)
        self.assertNotIn(".AppImage\n", self.content.replace("FreeCAD.AppImage\n", ""))
        self.assertNotRegex(self.content, r"\b[0-9a-f]{64}\b")
        self.assertNotRegex(self.content, r"weekly-\d{4}\.\d{2}\.\d{2}")
        self.assertNotIn("releases/download", self.content)

    def _targets_outputs(self, targets_json=None, env=None):
        """Run the targets job script against TARGETS_JSON and return its GITHUB_OUTPUT lines as a dict."""
        script = self.content.split("python3 - <<'PY' >> \"$GITHUB_OUTPUT\"\n", 1)[1].split("\n          PY\n", 1)[0]
        script = "\n".join(line[10:] for line in script.splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "ci").mkdir()
            text = TARGETS_PATH.read_text(encoding="utf-8") if targets_json is None else json.dumps(targets_json)
            (pathlib.Path(tmp) / "ci" / "targets.json").write_text(text)
            done = subprocess.run(
                [sys.executable, "-I", "-c", script],
                cwd=tmp,
                env=dict(os.environ, **(env or {})),
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        outputs = dict(line.split("=", 1) for line in done.stdout.splitlines())
        self.assertEqual(sorted(outputs), ["gates", "matrix"])
        return {name: json.loads(value)["include"] for name, value in outputs.items()}

    def test_workflow_matrix_json_matches_targets_json(self):
        """The targets job expands every target into its shards, in order, with the fields the job uses."""
        include = self._targets_outputs()["matrix"]
        targets = load_targets()
        expected = [
            {
                "target": name,
                "shard": shard,
                "shards": data["shards"],
                **{key: data[key] for key in ("label", "url", "sha256", "timeout", "blocking")},
            }
            for name, data in targets.items()
            for shard in range(1, data["shards"] + 1)
        ]
        self.assertEqual(include, expected)
        self.assertEqual(len(include), sum(data["shards"] for data in targets.values()))

    def test_workflow_single_shard_target_keeps_one_job(self):
        stable = dict(load_targets()["stable"], shards=1)
        outputs = self._targets_outputs({"stable": stable})
        self.assertEqual([(e["target"], e["shard"], e["shards"]) for e in outputs["matrix"]], [("stable", 1, 1)])
        self.assertEqual(outputs["gates"], [{"target": "stable", "blocking": True}])

    def test_workflow_gates_one_job_per_target(self):
        gates = self._targets_outputs()["gates"]
        self.assertEqual(
            gates, [{"target": name, "blocking": data["blocking"]} for name, data in load_targets().items()]
        )

    def _job(self, job_id):
        return re.split(r"\n\n  [\w-]+:\n", self.content.split(f"\n  {job_id}:\n", 1)[1], maxsplit=1)[0]

    def test_workflow_check_names_do_not_change(self):
        """Branch protection requires `Native FreeCAD (stable)`: a per-target gate job keeps that exact name."""
        self.assertIn("name: Code Formatting (Black & isort)", self.content)
        gate = self._job("native")
        self.assertIn("    name: Native FreeCAD (${{ matrix.target }})\n", gate)
        self.assertIn("stable", [entry["target"] for entry in self._targets_outputs()["gates"]])
        self.assertEqual(self.content.count("name: Native FreeCAD (${{ matrix.target }})\n"), 1)
        shard_job = self._job("test")
        self.assertIn(
            "    name: Native FreeCAD (${{ matrix.target }}, shard ${{ matrix.shard }}/${{ matrix.shards }})\n",
            shard_job,
        )

    def test_workflow_gate_waits_for_every_shard_and_always_reports(self):
        """A skipped required check counts as passed, so the gate must run even when shards fail."""
        gate = self._job("native")
        self.assertIn("    needs: [targets, test]\n", gate)
        self.assertIn("    if: always()\n", gate)
        self.assertIn("matrix: ${{ fromJSON(needs.targets.outputs.gates) }}", gate)
        self.assertIn("fail-fast: false", gate)
        self.assertIn("SHARDS_RESULT: ${{ needs.test.result }}", gate)
        self.assertIn("BLOCKING: ${{ matrix.blocking }}", gate)
        self.assertNotIn("continue-on-error:", gate)
        self.assertNotIn("uses:", gate)

    def _gate(self, blocking, result):
        gate = self._job("native")
        script = gate.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines())
        env = dict(os.environ, TARGET="stable", BLOCKING=blocking, SHARDS_RESULT=result)
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)

    def test_workflow_gate_fails_only_for_a_blocking_target(self):
        for blocking, result, code in (
            ("true", "success", 0),
            ("true", "failure", 1),
            ("true", "cancelled", 1),
            ("true", "skipped", 1),
            ("false", "success", 0),
            ("false", "failure", 0),
            ("false", "cancelled", 0),
            ("false", "skipped", 0),
        ):
            with self.subTest(blocking=blocking, result=result):
                done = self._gate(blocking, result)
                self.assertEqual(done.returncode, code, done.stdout + done.stderr)
                if code:
                    self.assertIn("::error::Native FreeCAD (stable) is blocking", done.stdout)
                if blocking == "false":
                    self.assertIn("is informative", done.stdout)
                self.assertIn(f"'{result}'", done.stdout)

    def test_workflow_runs_and_reports_each_shard(self):
        shard_job = self._job("test")
        self.assertIn('--shard "${{ matrix.shard }}/${{ matrix.shards }}"', shard_job)
        self.assertIn("name: test-failure-reports-${{ matrix.target }}-shard-${{ matrix.shard }}", shard_job)

    def test_workflow_weekly_is_informative_and_stable_is_blocking(self):
        """Only targets that are not `blocking` in ci/targets.json may continue on error."""
        self.assertEqual(self.content.count("continue-on-error:"), 1)
        self.assertIn("continue-on-error: ${{ !matrix.blocking }}", self.content)
        self.assertNotIn("continue-on-error: true", self.content)
        targets = load_targets()
        self.assertIs(targets["stable"]["blocking"], True)
        self.assertIs(targets["weekly"]["blocking"], False)

    def test_workflow_uses_matrix_values_for_download_timeout_and_target(self):
        self.assertIn("${{ matrix.url }}", self.content)
        self.assertIn("--timeout ${{ matrix.timeout }}", self.content)
        self.assertIn('--target "${{ matrix.target }}"', self.content)

    def test_workflow_pins_official_node24_actions_with_full_shas(self):
        """Workflow must pin official Node 24 actions (checkout v7.0.1, setup-python v7.0.0, upload-artifact v7.0.2, cache v6.1.0) using full SHAs."""
        expected_actions = {
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1": 3,
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0": 2,
            "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2": 2,
        }
        for action_ref, count in expected_actions.items():
            actual_count = self.content.count(action_ref)
            self.assertEqual(
                actual_count,
                count,
                f"Expected exactly {count} occurrences of '{action_ref}', found {actual_count}",
            )

        # Assert no legacy Node 20 action SHAs or versions remain
        legacy_pins = [
            "11bd71901bbe5b1630ceea73d27597364c9af683",  # checkout v4.2.2
            "42375524e23c412d93fb67b49958b491fce71c38",  # setup-python v5.4.0
            "4cec3d8aa04e39d1a68397de0c4cd6fb9dce8ec1",  # upload-artifact v4.6.1
            "v4.2.2",
            "v5.4.0",
            "v4.6.1",
        ]
        for legacy in legacy_pins:
            self.assertNotIn(legacy, self.content, f"Legacy Node 20 reference '{legacy}' must not appear in workflow")

        # Verify all uses: references in workflow use a 40-character hex SHA
        uses_lines = [line.strip() for line in self.content.splitlines() if line.strip().startswith("uses:")]
        self.assertEqual(len(uses_lines), 8, f"Expected exactly 8 uses steps, found {len(uses_lines)}")
        sha_pattern = re.compile(r"^uses:\s+actions/[a-zA-Z0-9_-]+@([0-9a-f]{40})\s+#\s+v[0-9.]+$")
        for line in uses_lines:
            self.assertRegex(
                line, sha_pattern, f"Step '{line}' must match 'uses: actions/<name>@<40-char-sha> # v<semver>'"
            )


class TestPackageMetadataPolicy(unittest.TestCase):
    """Metadata checks for package.xml (S1, S3)."""

    def test_package_xml_declares_minimum_freecad_1_1_4(self):
        package_xml = REPO_ROOT / "package.xml"
        self.assertTrue(package_xml.is_file(), "package.xml must exist")
        content = package_xml.read_text(encoding="utf-8")
        self.assertIn("<freecadmin>1.1.4</freecadmin>", content)
        self.assertNotIn("<freecadmin>0.21.0</freecadmin>", content)


class TestDocumentationPolicy(unittest.TestCase):
    """Documentation consistency checks for README.md and docs/ci.md (S1, S3)."""

    def test_readme_declares_minimum_and_honest_statement(self):
        readme = REPO_ROOT / "README.md"
        content = readme.read_text(encoding="utf-8")
        self.assertIn("1.1.4", content)
        self.assertNotIn("≥ v0.21.x", content)

    def test_ci_docs_document_stable_and_weekly_targets(self):
        ci_doc = REPO_ROOT / "docs" / "ci.md"
        content = ci_doc.read_text(encoding="utf-8")
        weekly = load_targets()["weekly"]
        self.assertIn(weekly["label"].removeprefix("FreeCAD "), content)
        self.assertIn(".".join(weekly["expected_freecad"]), content)
        self.assertIn(weekly["sha256"], content)
        self.assertIn("ci/targets.json", content)
        self.assertIn("single source of truth", content)
        self.assertIn("never anything under `.github/`", content)
        self.assertIn("informative", content.lower())
        self.assertIn("--target", content)

    def test_ci_docs_document_shards_and_gates(self):
        content = (REPO_ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
        self.assertIn("## Parallel shards", content)
        self.assertIn("--shard INDEX/COUNT", content)
        self.assertIn("--shard 1/2", content)
        self.assertIn("`shards`", content)
        self.assertIn("`Native FreeCAD (stable)`", content)
        self.assertIn("`Code Formatting (Black & isort)`", content)
        self.assertIn("needs.test.result", content)
        self.assertIn("test-failure-reports-<target>-shard-<n>", content)

    def test_ci_docs_document_node24_actions_infrastructure(self):
        """CI docs must document Node 24 as action infrastructure, runner requirements, and disclaim hosted execution."""
        ci_doc = REPO_ROOT / "docs" / "ci.md"
        content = ci_doc.read_text(encoding="utf-8")
        self.assertIn("Node 24", content)
        self.assertIn("2.327.1", content)
        self.assertIn("ubuntu-24.04", content)
        self.assertIn("3d3c42e5aac5ba805825da76410c181273ba90b1", content)
        self.assertIn("5fda3b95a4ea91299a34e894583c3862153e4b97", content)
        self.assertIn("cf430e030ddbb5b0abf93d22962f4752f3646cd9", content)
        self.assertIn("Action infrastructure only", content)
        self.assertIn("no hosted CI claim is made", content)

    def test_workbench_icon_uses_vector_svg_not_legacy_xpm(self):
        init_gui = REPO_ROOT / "freecad" / "maxproframe" / "InitGui.py"
        content = init_gui.read_text(encoding="utf-8")
        self.assertIn("metalwb.svg", content)
        self.assertNotIn("static char * metalwb_xpm[]", content)

        svg_path = REPO_ROOT / "freecad" / "maxproframe" / "resources" / "icons" / "metalwb.svg"
        self.assertTrue(svg_path.is_file())
        svg_content = svg_path.read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 64 64"', svg_content)
        self.assertNotIn("icone_atelier_metalwb.svg", svg_content)

        # FreeCAD executes InitGui.py with separate globals and locals dictionaries.
        # Verify that executing InitGui.py with distinct dicts resolves MaxProFrame.Icon to svg_path.
        import types
        from unittest import mock

        fake_fc = types.ModuleType("FreeCAD")
        fake_fc.Qt = types.SimpleNamespace(translate=lambda ctx, txt: txt, QT_TRANSLATE_NOOP=lambda ctx, txt: txt)
        fake_gui = types.ModuleType("FreeCADGui")
        fake_gui.Workbench = object
        fake_gui.addLanguagePath = lambda p: None
        fake_gui.updateLocale = lambda: None
        registered = {}
        fake_gui.addWorkbench = lambda wb: registered.setdefault(wb.__class__.__name__, wb)

        with mock.patch.dict(sys.modules, {"FreeCAD": fake_fc, "FreeCADGui": fake_gui}):
            g_dict = {"__builtins__": __builtins__}
            l_dict = {}
            exec(compile(content, str(init_gui), "exec"), g_dict, l_dict)

        self.assertIn("MaxProFrame", l_dict)
        self.assertEqual(pathlib.Path(l_dict["MaxProFrame"].Icon).resolve(), svg_path.resolve())

    def test_readme_and_funding_include_banner_and_sponsors(self):
        banner_path = REPO_ROOT / "docs" / "images" / "maxproframe-banner.png"
        self.assertTrue(banner_path.is_file())
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/images/maxproframe-banner.png", readme)
        self.assertIn("https://ko-fi.com/sclmax", readme)
        self.assertIn("https://cafecito.app/sclmax", readme)

        funding = (REPO_ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8")
        self.assertIn("ko_fi: sclmax", funding)
        self.assertIn("https://cafecito.app/sclmax", funding)

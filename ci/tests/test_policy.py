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

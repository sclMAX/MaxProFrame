"""Deterministic manual diagnostic boundaries; no FreeCAD required."""

import json
import os
import pathlib
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from ci import native_diagnostics

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestManualMode(unittest.TestCase):
    def test_driver_capture_continues_same_inferior_and_preserves_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / "config.json"
            config.write_text(json.dumps({"bootstrap": {}, "reports": directory}))
            callbacks = {}
            fake = types.ModuleType("gdb")
            fake.events = types.SimpleNamespace(
                **{
                    name: types.SimpleNamespace(connect=lambda cb, name=name: callbacks.update({name: cb}))
                    for name in ("new_thread", "stop", "exited")
                }
            )
            frame = mock.Mock()
            frame.name.return_value = "QEventLoop::exec"
            frame.older.return_value = frame  # Force the depth bound.
            thread = mock.Mock(num=1)
            fake.selected_inferior = lambda: types.SimpleNamespace(pid=123, threads=lambda: [thread])
            fake.newest_frame = lambda: frame
            timer = mock.Mock()
            commands = []

            def execute(command, **kwargs):
                commands.append(command)
                if command == "run":
                    callbacks["new_thread"](None)
                    timer.function()
                    callbacks["stop"](types.SimpleNamespace(stop_signal="SIGSTOP"))
                elif command == "signal 0":
                    callbacks["exited"](types.SimpleNamespace(exit_code=7))
                elif command.startswith("quit "):
                    raise SystemExit(int(command.split()[1]))

            fake.execute = execute

            def make_timer(delay, function):
                self.assertEqual(delay, 150)
                timer.function = function
                return timer

            with (
                mock.patch.dict(sys.modules, {"gdb": fake}),
                mock.patch.dict(os.environ, {"FF_NATIVE_CONFIG": str(config)}),
                mock.patch("threading.Timer", side_effect=make_timer),
                mock.patch("os.kill") as kill,
            ):
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(ROOT / "ci/gdb_driver.py"))
            self.assertEqual(result.exception.code, 7)
            kill.assert_called_once_with(123, 19)
            timer.cancel.assert_called_once()
            self.assertEqual(commands.count("run"), 1)
            self.assertEqual(commands.count("signal 0"), 1)
            rows = [
                json.loads(row) for row in (pathlib.Path(directory) / "native-stacks.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(next(row["frames"] for row in rows if "frames" in row)), 64)
            self.assertEqual(rows[-1], {"phase": "inferior-exit", "code": 7})

    def test_unexpected_signal_records_frames_before_fail_closed_quit(self):
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / "config.json"
            config.write_text(json.dumps({"bootstrap": {}, "reports": directory}))
            callbacks = {}
            fake = types.ModuleType("gdb")
            fake.events = types.SimpleNamespace(
                **{
                    name: types.SimpleNamespace(connect=lambda cb, name=name: callbacks.update({name: cb}))
                    for name in ("new_thread", "stop", "exited")
                }
            )
            frame = mock.Mock()
            frame.name.return_value = "QObject::property"
            frame.older.return_value = None
            fake.selected_inferior = lambda: types.SimpleNamespace(pid=123, threads=lambda: [mock.Mock(num=1)])
            fake.newest_frame = lambda: frame
            commands = []

            def execute(command, **kwargs):
                commands.append(command)
                if command == "run":
                    callbacks["stop"](types.SimpleNamespace(stop_signal="SIGSEGV"))
                elif command.startswith("quit "):
                    raise SystemExit(int(command.split()[1]))

            fake.execute = execute
            with (
                mock.patch.dict(sys.modules, {"gdb": fake}),
                mock.patch.dict(os.environ, {"FF_NATIVE_CONFIG": str(config)}),
                mock.patch("threading.Timer"),
            ):
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(ROOT / "ci/gdb_driver.py"))
            self.assertEqual(result.exception.code, 1)
            self.assertNotIn("signal 0", commands)
            rows = [
                json.loads(row) for row in (pathlib.Path(directory) / "native-stacks.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(row.get("frames") == ["QObject::property"] for row in rows))
            self.assertTrue(any(row.get("signal") == "SIGSEGV" for row in rows))

    def test_workflow_explicit_manual_stable_and_success_artifacts(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("native_diagnostics:", workflow)
        self.assertIn("type: boolean", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("matrix.target == 'stable'", workflow)
        self.assertIn("always() &&", workflow)
        self.assertIn("--native-diagnostics", workflow)

    def test_manual_route_keeps_summary_and_exit_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            debugger = work / "gdb"
            debugger.write_text(
                "#!/usr/bin/env python3\n"
                "import os, subprocess, sys\n"
                "assert os.environ['FF_NATIVE_DIAGNOSTICS'] == '1'\n"
                "sys.exit(subprocess.call(sys.argv[sys.argv.index('--args') + 1:]))\n"
            )
            debugger.chmod(0o755)
            binary = work / "freecad"
            binary.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "if os.environ['CASE'] == 'exit7': sys.exit(7)\n"
                "if os.environ['CASE'] == 'success':\n"
                " pathlib.Path(os.environ['FF_REPORTS'], 'summary.json').write_text(json.dumps(\n"
                "  dict(tests=1, failures=0, errors=0, skipped=0, successful=True)))\n"
            )
            binary.chmod(0o755)
            for case, code, stdout, stderr in (
                ("success", 0, "run_tests: Test suite succeeded (1 tests executed).\n", ""),
                ("exit7", 7, "", "run_tests error: FreeCAD child process failed with exit code 7.\n"),
                ("missing", 1, "", "run_tests error: summary.json was not generated.\n"),
            ):
                with self.subTest(case=case):
                    env = os.environ.copy()
                    env.update(PATH=str(work) + os.pathsep + env["PATH"], CASE=case)
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "ci/run_tests.py"),
                            "--freecad-bin",
                            str(binary),
                            "--reports",
                            str(work / "reports"),
                            "--native-diagnostics",
                            "--timeout",
                            "420",
                        ],
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (code, stdout, stderr))
                    self.assertEqual((work / "reports/summary.json").exists(), case == "success")

    def test_cli_rejects_rc_before_mutating_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            report = pathlib.Path(directory) / "summary.json"
            report.write_text("unchanged")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "ci/run_tests.py"),
                    "--freecad-bin",
                    "/unused",
                    "--reports",
                    directory,
                    "--native-diagnostics",
                    "--target",
                    "rc",
                    "--timeout",
                    "420",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, "")
            self.assertTrue(
                proc.stderr.endswith(
                    "error: --native-diagnostics requires --target stable and --timeout greater than 160\n"
                )
            )
            self.assertEqual(report.read_text(), "unchanged")

    def test_real_inferior_group_cleanup_and_foreign_session_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], start_new_session=True)
            try:
                (pathlib.Path(directory) / "native-inferior.pid").write_text(str(child.pid))
                native_diagnostics.kill_inferior(directory, os.getsid(0))
                self.assertIsNone(child.poll())
                native_diagnostics.kill_inferior(directory, child.pid)
                self.assertEqual(child.wait(timeout=3), -9)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_bootstrap_is_only_set_for_inferior(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(native_diagnostics.shutil, "which", return_value="/usr/bin/gdb"):
                command, env = native_diagnostics.prepare(
                    ["/freecad", "macro"],
                    {"PYTHONHOME": "/image/usr", "LD_LIBRARY_PATH": "/image/lib", "PUBLIC": "kept"},
                    directory,
                    directory,
                )
            self.assertNotIn("PYTHONHOME", env)
            self.assertNotIn("LD_LIBRARY_PATH", env)
            self.assertEqual(env["PUBLIC"], "kept")
            config = json.loads(pathlib.Path(env["FF_NATIVE_CONFIG"]).read_text())
            self.assertEqual(config["bootstrap"], {"PYTHONHOME": "/image/usr"})
            self.assertNotIn("PUBLIC", json.dumps(config))
            self.assertEqual(command[-3:], ["--args", "/freecad", "macro"])

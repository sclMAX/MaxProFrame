"""Windows launch helpers of ci/run_tests.py, exercised on any host (ci-windows S3).

The Windows branch cannot run natively here, so these tests drive the helpers that
main() uses with `windows=True`: isolated profile variables, child launch options,
process-tree kill and the gdb rerun skip.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from ci import run_tests

CI_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_DIR))

FAKE_TASKKILL = """#!{python}
import json, os, signal, sys
with open(os.environ["FAKE_TASKKILL_DUMP"], "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
os.kill(int(sys.argv[sys.argv.index("/PID") + 1]), signal.SIGKILL)
"""


class TestWindowsProfile(unittest.TestCase):
    def test_profile_variables_point_inside_the_isolated_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp) / "home"
            temp = pathlib.Path(tmp) / "tmp"
            home.mkdir()
            temp.mkdir()
            env = run_tests.windows_profile_env(home, temp)
            self.assertEqual(set(env), {"USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"})
            self.assertEqual(env["USERPROFILE"], str(home))
            self.assertEqual(env["APPDATA"], str(home / "AppData" / "Roaming"))
            self.assertEqual(env["LOCALAPPDATA"], str(home / "AppData" / "Local"))
            self.assertEqual((env["TEMP"], env["TMP"]), (str(temp), str(temp)))
            for value in env.values():
                self.assertTrue(pathlib.Path(value).is_dir(), value)


class TestLaunchOptions(unittest.TestCase):
    def test_posix_children_get_their_own_session(self):
        self.assertEqual(run_tests.launch_options(windows=False), {"start_new_session": True})

    def test_windows_children_get_a_process_group_and_utf8_output(self):
        self.assertEqual(
            run_tests.launch_options(windows=True),
            {"creationflags": 0x00000200, "encoding": "utf-8", "errors": "replace"},
        )


class TestKillProcessTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = pathlib.Path(self.tmp.name)
        self.bin_dir = self.work / "bin"
        self.bin_dir.mkdir()
        self.dump = self.work / "taskkill.json"

    def sleeper(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc

    def wait_dead(self, proc):
        deadline = time.monotonic() + 10
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(proc.poll(), "The child must be dead after kill_process_tree")

    def test_windows_kills_the_whole_tree_with_taskkill(self):
        taskkill = self.bin_dir / "taskkill"
        taskkill.write_text(FAKE_TASKKILL.replace("{python}", sys.executable), encoding="utf-8")
        taskkill.chmod(0o755)
        proc = self.sleeper()
        with mock.patch.dict(os.environ, PATH=str(self.bin_dir), FAKE_TASKKILL_DUMP=str(self.dump)):
            run_tests.kill_process_tree(proc, windows=True)
        self.wait_dead(proc)
        self.assertEqual(json.loads(self.dump.read_text()), ["/T", "/F", "/PID", str(proc.pid)])

    def test_windows_without_taskkill_still_kills_the_child(self):
        proc = self.sleeper()
        with mock.patch.dict(os.environ, PATH=str(self.bin_dir)):
            run_tests.kill_process_tree(proc, windows=True)
        self.wait_dead(proc)

    def test_posix_kills_the_process_group(self):
        proc = self.sleeper()
        run_tests.kill_process_tree(proc, windows=False)
        self.wait_dead(proc)
        run_tests.kill_process_tree(proc, windows=False)  # an already finished group is not an error


class TestGdbRerunAvailability(unittest.TestCase):
    def test_windows_skips_the_gdb_rerun_with_a_clear_reason(self):
        import crash_diagnosis

        self.assertEqual(
            crash_diagnosis.gdb_unavailable(windows=True),
            "gdb crash reruns are not available on Windows; crash rerun skipped.",
        )

    def test_missing_gdb_keeps_its_message(self):
        import crash_diagnosis

        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, PATH=empty):
            self.assertEqual(
                crash_diagnosis.gdb_unavailable(windows=False), "gdb is not installed; crash rerun skipped."
            )


if __name__ == "__main__":
    unittest.main()

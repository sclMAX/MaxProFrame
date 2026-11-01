#!/usr/bin/env python3
"""Host runner wrapper for native FreeCAD test suite.

Launches the official FreeCAD 1.1.4 Linux GUI binary in an isolated headless
environment, unsetting display variables and setting offscreen configuration.
Extracted AppRun inputs resolve to the bundled binary with equivalent bootstrap
variables, without vendor platform overrides or unsupported Qt CLI options.
On Windows the portable bin/FreeCAD.exe runs with an isolated user profile.
Enforces process-group (Windows: process-tree) timeouts (exit 124) and validates summary.json.
With --shard INDEX/COUNT only that shard of the discovered tests runs.
"""

import argparse
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile

MAX_LOG_BYTES = 1024 * 1024  # 1MB per log file
WINDOWS = os.name == "nt"
# subprocess.CREATE_NEW_PROCESS_GROUP, which only exists on Windows.
CREATE_NEW_PROCESS_GROUP = 0x00000200


TARGETS_PATH = pathlib.Path(__file__).resolve().parent / "targets.json"


def target_names():
    """Target names pinned in ci/targets.json (the single source of truth for the runtimes)."""
    with open(TARGETS_PATH, encoding="utf-8") as handle:
        return list(json.load(handle))


def windows_profile_env(home, tmp):
    """Windows profile variables inside the isolated HOME and TMP; FreeCAD reads its user dirs from them."""
    home = pathlib.Path(home)
    paths = {
        "USERPROFILE": home,
        "APPDATA": home / "AppData" / "Roaming",
        "LOCALAPPDATA": home / "AppData" / "Local",
        "TEMP": pathlib.Path(tmp),
        "TMP": pathlib.Path(tmp),
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: str(path) for name, path in paths.items()}


def launch_options(windows=WINDOWS):
    """Popen options that let kill_process_tree reach everything the child starts."""
    if windows:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP, "encoding": "utf-8", "errors": "replace"}
    return {"start_new_session": True}


def kill_process_tree(proc, windows=WINDOWS):
    """Kill the child and its descendants: `taskkill /T /F` on Windows (no os.killpg), the process group elsewhere."""
    if windows:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            pass
        proc.kill()
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def write_bounded_file(dest: pathlib.Path, text: str) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_LOG_BYTES:
        encoded = encoded[:MAX_LOG_BYTES] + b"\n... [TRUNCATED DUE TO SIZE LIMIT]\n"
    dest.write_bytes(encoded)


def valid_test_selector(value: str) -> bool:
    """Only a test module and optional class/method, never an import path."""
    return re.fullmatch(r"test_[A-Za-z0-9_]+(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2}", value) is not None


SHARD_PATTERN = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")
SHARD_ERROR = "--shard must be INDEX/COUNT with 1 <= INDEX <= COUNT, e.g. 1/2"


def parse_shard(value):
    """Return (index, count) for INDEX/COUNT, both positive and index <= count; raise ValueError otherwise."""
    match = SHARD_PATTERN.fullmatch(value)
    if match is None or int(match.group(1)) > int(match.group(2)):
        raise ValueError(SHARD_ERROR)
    return int(match.group(1)), int(match.group(2))


def flatten_suite(suite):
    """Yield the individual tests of a (nested) suite in execution order."""
    import unittest

    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten_suite(item)
        else:
            yield item


def shuffled(suite, seed):
    """Deterministically reorder every test across modules and classes for a given seed."""
    import random
    import unittest

    tests = list(flatten_suite(suite))
    random.Random(seed).shuffle(tests)
    return unittest.TestSuite(tests)


def sharded(suite, index, count):
    """Every COUNT-th test of the discovery order from INDEX (1-based): the shards run each test exactly once."""
    import unittest

    if count == 1:
        return suite
    return unittest.TestSuite(list(flatten_suite(suite))[index - 1 :: count])


def selected_suite(tests_dir, selector, shuffle_seed=None, shard=None):
    """Select the suite, keep only SHARD (index, count) and, with a seed, shuffle it reproducibly."""
    suite = _selected_suite(tests_dir, selector)
    if shard is not None:
        suite = sharded(suite, *shard)
    return suite if shuffle_seed is None else shuffled(suite, shuffle_seed)


def _selected_suite(tests_dir, selector):
    """Discover only the local module; resolve attributes without further imports."""
    import importlib.util
    import types
    import unittest

    loader = unittest.TestLoader()
    if selector is None:
        return loader.discover(str(tests_dir), pattern="test_*.py")
    if not valid_test_selector(selector):
        raise ValueError("invalid test selector")
    module_name, _, suffix = selector.partition(".")
    tests_dir = pathlib.Path(tests_dir).resolve()
    module_path = tests_dir / (module_name + ".py")
    if not module_path.is_file() or module_path.resolve().parent != tests_dir:
        # A missing local module must be a real loader error, not an empty suite.
        return loader.loadTestsFromName(module_name, types.ModuleType("missing_local_test"))
    sys.path.insert(0, str(tests_dir))
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:

        def import_error(error=exc):
            raise error

        return unittest.TestSuite([unittest.FunctionTestCase(import_error)])
    if suffix:
        return loader.loadTestsFromName(suffix, module)
    return loader.loadTestsFromModule(module)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native FreeCAD test suite offscreen with isolated configuration.")
    parser.add_argument(
        "--freecad-bin",
        required=True,
        help="Path to the FreeCAD executable, an extracted AppImage AppRun, or on Windows the portable "
        "archive's bin/FreeCAD.exe",
    )
    parser.add_argument(
        "--reports",
        required=True,
        help="Directory to save test logs and summary report",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Process group timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--target",
        choices=target_names(),
        default="stable",
        help="Target FreeCAD runtime to validate and test, as pinned in ci/targets.json (default: stable)",
    )
    parser.add_argument(
        "--native-diagnostics",
        action="store_true",
        help="Manual stable-only GDB capture at 150s, then continue; requires gdb and timeout >160s",
    )
    parser.add_argument(
        "--test",
        help="Run one dotted test_ module[.Class[.method]] from tests/ (default: full discovery)",
    )
    parser.add_argument(
        "--no-crash-rerun",
        action="store_true",
        help="Skip the diagnostic gdb rerun of the crashing test (the crash summary is still written)",
    )
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        help="Run the selected tests in a random order reproducible from this integer seed (default: original order)",
    )
    parser.add_argument(
        "--shard",
        metavar="INDEX/COUNT",
        help="Run only shard INDEX of COUNT (e.g. 1/2): every COUNT-th selected test from INDEX in discovery order, "
        "so each test runs in exactly one shard (default: all selected tests)",
    )
    args = parser.parse_args()
    if args.test is not None and not valid_test_selector(args.test):
        parser.error("--test must be test_module[.Class[.method]] using ASCII identifiers, without paths")
    if args.shard is not None:
        try:
            parse_shard(args.shard)
        except ValueError as exc:
            parser.error(str(exc))
    if args.native_diagnostics and (args.target != "stable" or args.timeout <= 160):
        parser.error("--native-diagnostics requires --target stable and --timeout greater than 160")

    freecad_bin = pathlib.Path(args.freecad_bin).resolve()
    if not freecad_bin.is_file():
        sys.stderr.write(f"run_tests error: FreeCAD binary not found: {freecad_bin}\n")
        sys.exit(1)

    reports_dir = pathlib.Path(args.reports).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    macro_path = repo_root / "ci" / "run-tests.FCMacro"
    if not macro_path.is_file():
        sys.stderr.write(f"run_tests error: Macro file not found: {macro_path}\n")
        sys.exit(1)

    # Clear stale evidence from previous invocations before launching
    for stale_name in (
        "summary.json",
        "tests.log",
        "stdout.log",
        "stderr.log",
        "startup.log",
        "python-stacks.log",
        "modal-state.jsonl",
        "qt-events.jsonl",
        "native-stacks.jsonl",
        "native-inferior.pid",
    ):
        stale_file = reports_dir / stale_name
        if stale_file.is_file():
            stale_file.unlink()

    # Check whether freecad_bin points to an extracted AppRun
    target_bin = freecad_bin
    is_apprun_layout = freecad_bin.name == "AppRun"
    appimage_dist_root = None

    if is_apprun_layout:
        appimage_dist_root = freecad_bin.parent
        native_bin = appimage_dist_root / "usr" / "bin" / "freecad"
        if not native_bin.is_file() or not os.access(native_bin, os.X_OK):
            sys.stderr.write(f"run_tests error: Native FreeCAD executable not found in AppImage layout: {native_bin}\n")
            sys.exit(1)
        target_bin = native_bin

    # Prepare isolated environment
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = pathlib.Path(scratch_dir)
        isolated_home = scratch / "home"
        isolated_config = scratch / "config"
        isolated_data = scratch / "data"
        isolated_cache = scratch / "cache"
        isolated_tmp = scratch / "tmp"
        isolated_fc_home = scratch / "freecad"
        isolated_profiles = scratch / "profiles"

        isolated_home.mkdir()
        isolated_config.mkdir()
        isolated_data.mkdir()
        isolated_cache.mkdir()
        isolated_tmp.mkdir()
        isolated_fc_home.mkdir()
        isolated_profiles.mkdir()

        user_cfg = isolated_config / "user.cfg"
        # Prevent popup reentry from offscreen Qt warnings, including repeated messages.
        # Keep the notification area, Console observers and severity settings intact.
        user_cfg.write_text(
            """<FCParameters>
  <FCParamGroup Name="Root">
    <FCParamGroup Name="BaseApp">
      <FCParamGroup Name="Preferences">
        <FCParamGroup Name="NotificationArea">
          <FCBool Name="NonIntrusiveNotificationsEnabled" Value="0"/>
          <FCInt Name="MaxOpenNotifications" Value="0"/>
        </FCParamGroup>
      </FCParamGroup>
    </FCParamGroup>
  </FCParamGroup>
</FCParameters>
""",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        env["HOME"] = str(isolated_home)
        env["XDG_CONFIG_HOME"] = str(isolated_config)
        env["XDG_DATA_HOME"] = str(isolated_data)
        env["XDG_CACHE_HOME"] = str(isolated_cache)
        env["TMPDIR"] = str(isolated_tmp)
        env["FREECAD_USER_HOME"] = str(isolated_fc_home)
        env["MAXPROFRAME_USER_PROFILES_DIR"] = str(isolated_profiles)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        env["FF_ROOT"] = str(repo_root)
        env["FF_REPORTS"] = str(reports_dir)
        env["FF_TARGET"] = args.target
        if WINDOWS:
            env.update(windows_profile_env(isolated_home, isolated_tmp))
        env.pop("FF_TEST", None)
        if args.test is not None:
            env["FF_TEST"] = args.test
        env.pop("FF_SHARD", None)
        if args.shard is not None:
            env["FF_SHARD"] = args.shard
            sys.stdout.write(f"run_tests: shard {args.shard}\n")
            sys.stdout.flush()
        env.pop("FF_SHUFFLE_SEED", None)
        if args.shuffle_seed is not None:
            env["FF_SHUFFLE_SEED"] = str(args.shuffle_seed)
            sys.stdout.write(f"run_tests: shuffle seed {args.shuffle_seed}\n")
            sys.stdout.flush()
        env.pop("FF_NATIVE_DIAGNOSTICS", None)
        if args.native_diagnostics:
            env["FF_NATIVE_DIAGNOSTICS"] = "1"

        # Reproduce official AppRun environment bootstrap when launched via AppRun without executing AppRun script
        if is_apprun_layout and appimage_dist_root:
            env["PREFIX"] = str(appimage_dist_root / "usr")
            env["PYTHONHOME"] = str(appimage_dist_root / "usr")
            env["PATH_TO_FREECAD_LIBDIR"] = str(appimage_dist_root / "usr" / "lib")
            env["SSL_CERT_FILE"] = str(appimage_dist_root / "usr" / "ssl" / "cacert.pem")
            env["GIT_SSL_CAINFO"] = str(appimage_dist_root / "usr" / "ssl" / "cacert.pem")
            env["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"
            env["FONTCONFIG_PATH"] = "/etc/fonts"

        # Launch native binary without -platform argument (FreeCAD Boost CLI rejects -platform)
        cmd = [
            str(target_bin),
            "--user-cfg",
            str(user_cfg),
            str(macro_path),
        ]

        native = None
        if args.native_diagnostics:
            import native_diagnostics as native

            try:
                cmd, env = native.prepare(cmd, env, scratch, reports_dir)
            except RuntimeError as exc:
                sys.stderr.write(f"run_tests error: {exc}.\n")
                sys.exit(1)

        def replay_hint():
            if args.shuffle_seed is not None:
                sys.stderr.write(f"run_tests: replay with --shuffle-seed {args.shuffle_seed}\n")

        timed_out = False
        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **launch_options(),
        )

        try:
            stdout_text, stderr_text = proc.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if native is not None:
                native.kill_inferior(reports_dir, proc.pid)
            kill_process_tree(proc)
            stdout_text, stderr_text = proc.communicate()

        if native is not None:
            native.kill_inferior(reports_dir, proc.pid)
        write_bounded_file(reports_dir / "stdout.log", stdout_text)
        write_bounded_file(reports_dir / "stderr.log", stderr_text)

        if timed_out:
            killed = "process tree" if WINDOWS else "process group"
            sys.stderr.write(f"run_tests error: FreeCAD process timed out after {args.timeout}s (killed {killed}).\n")
            replay_hint()
            sys.exit(124)

        def diagnose_crash():
            """Diagnostic only: any failure here must not change the runner's exit status."""
            try:
                import crash_diagnosis

                if not crash_diagnosis.is_crash(proc.returncode, reports_dir):
                    return
                test_id = crash_diagnosis.inflight_test(crash_diagnosis.read_text(reports_dir / "tests.log"))
                if args.no_crash_rerun:
                    note = "rerun disabled by --no-crash-rerun."
                elif native is not None:
                    note = "rerun skipped: --native-diagnostics already runs under gdb."
                elif args.shuffle_seed is not None:
                    note = crash_diagnosis.rerun_under_gdb(
                        cmd,
                        env,
                        test_id,
                        reports_dir,
                        scratch,
                        timeout=crash_diagnosis.seeded_timeout(args.timeout),
                        shuffle_seed=args.shuffle_seed,
                    )
                elif test_id is None:
                    note = "rerun skipped: no unfinished test was found in tests.log."
                elif not valid_test_selector(test_id):
                    note = f"rerun skipped: {test_id} is not a selectable tests/ test."
                else:
                    note = crash_diagnosis.rerun_under_gdb(cmd, env, test_id, reports_dir, scratch)
                plain, markdown = crash_diagnosis.report(args.target, proc.returncode, test_id, stderr_text, note)
                crash_diagnosis.publish(plain, markdown, sys.stderr)
            except Exception as exc:
                sys.stderr.write(f"run_tests crash diagnosis failed: {type(exc).__name__}: {exc}\n")

        if proc.returncode != 0:
            sys.stderr.write(f"run_tests error: FreeCAD child process failed with exit code {proc.returncode}.\n")
            diagnose_crash()
            replay_hint()
            sys.exit(proc.returncode)

        # Validate summary report
        summary_file = reports_dir / "summary.json"
        if not summary_file.is_file():
            sys.stderr.write("run_tests error: summary.json was not generated.\n")
            diagnose_crash()
            replay_hint()
            sys.exit(1)

        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as exc:
            sys.stderr.write(f"run_tests error: Failed to parse summary.json: {exc}\n")
            sys.exit(1)

        if not isinstance(summary, dict):
            sys.stderr.write("run_tests error: summary.json must be a JSON object.\n")
            sys.exit(1)

        required_keys = {"tests", "failures", "errors", "skipped", "successful"}
        missing_keys = required_keys - set(summary.keys())
        if missing_keys:
            sys.stderr.write(f"run_tests error: summary.json missing required keys: {sorted(missing_keys)}\n")
            sys.exit(1)

        if not isinstance(summary["successful"], bool):
            sys.stderr.write("run_tests error: 'successful' field must be an exact boolean.\n")
            sys.exit(1)

        for count_field in ("tests", "failures", "errors", "skipped"):
            val = summary[count_field]
            if type(val) is not int or val < 0:
                sys.stderr.write(
                    f"run_tests error: '{count_field}' field must be a non-negative integer (got {repr(val)}).\n"
                )
                sys.exit(1)

        tests_run = summary["tests"]
        failures = summary["failures"]
        errors = summary["errors"]
        skipped = summary["skipped"]
        successful = summary["successful"]

        if tests_run <= 0:
            sys.stderr.write("run_tests error: Zero tests were executed.\n")
            sys.exit(1)

        if skipped > tests_run:
            sys.stderr.write(
                f"run_tests error: Inconsistent counts: skipped ({skipped}) exceeds total tests ({tests_run}).\n"
            )
            sys.exit(1)

        if failures > 0 or errors > 0 or not successful:
            sys.stderr.write(
                f"run_tests error: Test suite reported failures ({failures}), errors ({errors}), or successful is False.\n"
            )
            replay_hint()
            sys.exit(1)

    sys.stdout.write(f"run_tests: Test suite succeeded ({tests_run} tests executed).\n")
    sys.exit(0)


if __name__ == "__main__":
    main()

"""Diagnose a native FreeCAD child that died mid-suite; never changes the job outcome."""

import json
import os
import pathlib
import re
import shutil
import signal
import subprocess

import native_diagnostics

MAX_STDERR_LINES = 20
MAX_REPORT_BYTES = 1024 * 1024
RERUN_TIMEOUT = 120.0
SEEDED_RERUN_CAP = 1800.0
REPORT_NAME = "crash-backtrace.txt"
TEST_START = re.compile(r"^\S+ \(([\w.]+)\)(?: \.\.\. ?(.*))?$")
RESULT = re.compile(r" \.\.\. (?:ok|FAIL|ERROR|skipped|expected failure|unexpected success)")
GDB_CRASH = re.compile(r"Program (?:received|terminated with) signal")
FREECAD_SIGNAL = re.compile(r"received signal (SIG[A-Z0-9]+)")
GL_NOISE = re.compile(r"QOpenGL|libEGL|libGL|MESA|GLX|EGL|qt\.(?:qpa|glx)|DRI\d|OpenGL", re.IGNORECASE)


def inflight_test(tests_log):
    """Id of the last test in unittest verbosity-2 output that has no result yet."""
    pending = None
    for line in tests_log.splitlines():
        start = TEST_START.match(line)
        if start:
            pending = None if start.group(2) else start.group(1)
        elif pending is not None and RESULT.search(line):
            pending = None
    # A crash can cut the last line before its newline: "test (id) ... " is still pending.
    return pending


def stderr_tail(text, limit=MAX_STDERR_LINES):
    """Last meaningful stderr lines, without Qt/GL noise, blanks or consecutive repeats."""
    kept = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or GL_NOISE.search(line) or (kept and kept[-1] == line):
            continue
        kept.append(line)
    return kept[-limit:]


def describe_exit(returncode, stderr_text=""):
    # FreeCAD's own handler prints the signal and exits 1, so the status alone hides it.
    reported = FREECAD_SIGNAL.search(stderr_text)
    if returncode >= 0 and reported:
        return f"exit code {returncode} after FreeCAD reported {reported.group(1)}"
    if returncode < 0:
        try:
            return f"killed by signal {signal.Signals(-returncode).name} (exit {returncode})"
        except ValueError:
            return f"killed by signal {-returncode} (exit {returncode})"
    return f"exit code {returncode}"


def summary_is_valid(reports):
    try:
        data = json.loads((pathlib.Path(reports) / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and {"tests", "failures", "errors", "skipped", "successful"} <= set(data)


def is_crash(returncode, reports):
    """Signal death, or an exit without a valid summary while a test was still running."""
    if returncode < 0:
        return True
    log = read_text(pathlib.Path(reports) / "tests.log")
    return not summary_is_valid(reports) and inflight_test(log) is not None


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def seeded_timeout(run_timeout):
    """A seeded replay runs the whole suite: allow the run's own timeout (plus slack), within a cap."""
    return min(max(RERUN_TIMEOUT, run_timeout * 1.5), SEEDED_RERUN_CAP)


def rerun_under_gdb(command, environment, test_id, reports, scratch, timeout=RERUN_TIMEOUT, shuffle_seed=None):
    """Rerun under gdb and return a one-line note about what happened.

    Without SHUFFLE_SEED only TEST_ID is rerun, outside any shard. With it the original selection, shard and seed
    (FF_TEST / FF_SHARD / FF_SHUFFLE_SEED already in ENVIRONMENT) are replayed, so order-dependent crashes reproduce.
    """
    if shutil.which("gdb") is None:
        return "gdb is not installed; crash rerun skipped."
    rerun_reports = pathlib.Path(scratch) / "rerun-reports"
    rerun_reports.mkdir(exist_ok=True)
    env = environment.copy()
    if shuffle_seed is None:
        env["FF_TEST"] = test_id
        env.pop("FF_SHARD", None)
        mode = "single test"
        what = test_id
    else:
        env["FF_SHUFFLE_SEED"] = str(shuffle_seed)
        mode = f"seeded suite replay, seed {shuffle_seed}"
        what = f"the seeded suite (seed {shuffle_seed}, in-flight test {test_id or 'unknown'})"
    env["FF_REPORTS"] = str(rerun_reports)
    argv, env = native_diagnostics.backtrace_command(command, env)
    header = f"# Diagnostic rerun of {what} under gdb, mode: {mode} (result does not change the job outcome)\n"
    proc = subprocess.Popen(
        argv,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
        status = f"gdb exited with {proc.returncode}"
        if not GDB_CRASH.search(output):
            status += "; the crash did not reproduce under gdb"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = proc.communicate()
        status = f"gdb timed out after {timeout:g}s"
    status = f"{mode}: {status}"
    data = f"{header}# {status}\n{output}".encode("utf-8", errors="replace")[:MAX_REPORT_BYTES]
    (pathlib.Path(reports) / REPORT_NAME).write_bytes(data)
    return f"Backtrace of the rerun saved to {REPORT_NAME} ({status})."


def report(target, returncode, test_id, stderr_text, rerun_note):
    """Return (plain text for stderr, Markdown for the job summary)."""
    tail = stderr_tail(stderr_text)
    test = test_id or "unknown (no unfinished test in tests.log)"
    plain = [
        f"run_tests crash diagnosis: target {target}, FreeCAD {describe_exit(returncode, stderr_text)}.",
        f"run_tests crash diagnosis: test running at the time: {test}",
        f"run_tests crash diagnosis: {rerun_note}",
    ]
    markdown = [
        "## Native FreeCAD crash",
        "",
        f"- Target: `{target}`",
        f"- Exit: {describe_exit(returncode, stderr_text)}",
        f"- Test running at the time: `{test}`",
        f"- Rerun under gdb: {rerun_note}",
        "",
        "Last stderr lines (Qt/GL noise removed):",
        "",
        "```text",
        *(tail or ["(none)"]),
        "```",
        "",
    ]
    return "\n".join(plain) + "\n", "\n".join(markdown)


def publish(plain, markdown, stream):
    stream.write(plain)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(markdown + "\n")
        except OSError as exc:
            stream.write(f"run_tests crash diagnosis: could not write job summary: {exc}\n")

"""Prepare GDB without contaminating its embedded Python with AppImage bootstrap."""

import json
import os
import pathlib
import shutil
import signal

BOOTSTRAP = (
    "PREFIX",
    "PYTHONHOME",
    "PATH_TO_FREECAD_LIBDIR",
    "SSL_CERT_FILE",
    "GIT_SSL_CAINFO",
    "FONTCONFIG_FILE",
    "FONTCONFIG_PATH",
)


def split_bootstrap(environment):
    """Return (environment for GDB itself, AppImage bootstrap for the inferior only)."""
    clean = environment.copy()
    bootstrap = {key: clean.pop(key) for key in BOOTSTRAP if key in clean}
    clean.pop("PYTHONPATH", None)
    clean.pop("LD_LIBRARY_PATH", None)
    return clean, bootstrap


BACKTRACE_SETTINGS = (
    "set pagination off",
    "set confirm off",
    "set debuginfod enabled off",
    "set print frame-arguments none",
    "set startup-with-shell off",
)

# FreeCAD's own SIGSEGV handler hides PYTHONFAULTHANDLER, so the Python stack is
# dumped from inside the stopped inferior. The stop happens before that handler runs.
BACKTRACE_COMMANDS = (
    "run",
    "bt 60",
    "call (int)PyGILState_Ensure()",
    "call (void)PyRun_SimpleString("
    '"import faulthandler,sys;faulthandler.dump_traceback(sys.__stderr__, all_threads=True)")',
)


def backtrace_command(command, environment):
    """Batch GDB argv and environment that run COMMAND once and print native + Python stacks."""
    debugger = shutil.which("gdb")
    if debugger is None:
        raise RuntimeError("crash backtrace requires gdb")
    clean, bootstrap = split_bootstrap(environment)
    argv = [debugger, "--nx", "--quiet", "--batch"]
    for line in (*BACKTRACE_SETTINGS, *("set environment " + k + "=" + v for k, v in bootstrap.items())):
        argv += ["-ex", line]
    for line in BACKTRACE_COMMANDS:
        argv += ["-ex", line]
    return [*argv, "--args", *command], clean


def prepare(command, environment, scratch, reports):
    debugger = shutil.which("gdb")
    if debugger is None:
        raise RuntimeError("manual native diagnostics requires gdb")
    clean, bootstrap = split_bootstrap(environment)
    # Never serialize the inherited environment. Only public AppImage paths.
    config = pathlib.Path(scratch) / "native-config.json"
    config.write_text(json.dumps({"bootstrap": bootstrap, "reports": str(reports)}), encoding="utf-8")
    clean["FF_NATIVE_CONFIG"] = str(config)
    driver = pathlib.Path(__file__).with_name("gdb_driver.py")
    return [debugger, "--nx", "--quiet", "--batch", "-x", str(driver), "--args", *command], clean


def kill_inferior(reports, session_id):
    """GDB may put its inferior in a separate process group, but not session."""
    try:
        pid = int((pathlib.Path(reports) / "native-inferior.pid").read_text())
        if pid > 1 and os.getsid(pid) == session_id:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ValueError):
        pass

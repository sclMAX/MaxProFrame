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


def prepare(command, environment, scratch, reports):
    debugger = shutil.which("gdb")
    if debugger is None:
        raise RuntimeError("manual native diagnostics requires gdb")
    clean = environment.copy()
    bootstrap = {key: clean.pop(key) for key in BOOTSTRAP if key in clean}
    # Never serialize the inherited environment. Only public AppImage paths.
    config = pathlib.Path(scratch) / "native-config.json"
    config.write_text(json.dumps({"bootstrap": bootstrap, "reports": str(reports)}), encoding="utf-8")
    clean.pop("PYTHONPATH", None)
    clean.pop("LD_LIBRARY_PATH", None)
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

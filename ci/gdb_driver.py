"""Executed only inside GDB for the explicitly requested diagnostic run."""

import json
import os
import pathlib
import signal
import threading

import gdb

config = json.loads(pathlib.Path(os.environ["FF_NATIVE_CONFIG"]).read_text())
report = pathlib.Path(config["reports"]) / "native-stacks.jsonl"
for key, value in config["bootstrap"].items():
    gdb.execute("set environment " + key + "=" + value, to_string=True)
for setting in (
    "pagination off",
    "confirm off",
    "debuginfod enabled off",
    "print frame-arguments none",
    "print entry-values no",
    "startup-with-shell off",
):
    gdb.execute("set " + setting, to_string=True)

capturing = False
captured_stop = False
exited = False
exit_code = 1
inferior_pid = 0


def emit(state):
    with report.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(state) + "\n")


def request_capture():
    global capturing
    # Timer runs in debugger Python, independently of FreeCAD and Qt callbacks.
    pid = inferior_pid
    if pid and not exited:
        capturing = True
        try:
            os.kill(pid, signal.SIGSTOP)
        except ProcessLookupError:
            pass


def remember_inferior(event):
    global inferior_pid
    inferior_pid = gdb.selected_inferior().pid
    (report.parent / "native-inferior.pid").write_text(str(inferior_pid))


def stopped(event):
    global capturing, captured_stop
    stop_signal = str(getattr(event, "stop_signal", "unknown"))[:80]
    expected = capturing and stop_signal == "SIGSTOP"
    capturing = False
    captured_stop = expected
    phase = "capture" if expected else "unexpected-stop"
    emit({"phase": phase, "signal": stop_signal})
    capture_frames(phase)


def capture_frames(phase):
    try:
        inferior = gdb.selected_inferior()
        for thread in inferior.threads()[:64]:
            thread.switch()
            frame = gdb.newest_frame()
            names = []
            while frame is not None and len(names) < 64:
                names.append((frame.name() or "<unknown>")[:160])
                frame = frame.older()
            emit({"phase": phase, "thread": thread.num, "frames": names})
    except Exception as exc:
        emit({"phase": phase, "error": type(exc).__name__[:80]})


def finished(event):
    global exited, exit_code
    exited = True
    exit_code = getattr(event, "exit_code", 1)
    emit({"phase": "inferior-exit", "code": exit_code})


gdb.events.new_thread.connect(remember_inferior)
gdb.events.stop.connect(stopped)
gdb.events.exited.connect(finished)
emit({"phase": "armed", "capture_seconds": 150, "policy": "capture-then-continue"})
timer = threading.Timer(150, request_capture)
timer.daemon = True
timer.start()
try:
    gdb.execute("run")
    while not exited:
        if not captured_stop:
            emit({"phase": "unexpected-stop", "policy": "diagnostic-interruption-not-success"})
            gdb.execute("quit 1")
        captured_stop = False
        # SIGSTOP is not passed to the inferior. No dialog/input intervention.
        gdb.execute("signal 0")
finally:
    timer.cancel()
gdb.execute("quit " + str(exit_code))

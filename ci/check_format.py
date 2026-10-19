#!/usr/bin/env python3
"""Incremental code formatter runner for CI.

Consumes planner JSON and runs pinned Black and isort checks only on
the new or modified Python files identified by changed_files.py.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys

MAX_REPORT_BYTES = 1024 * 1024  # 1MB per report file


def write_bounded_log(file_path: pathlib.Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        encoded = encoded[:MAX_REPORT_BYTES] + b"\n... [TRUNCATED DUE TO SIZE LIMIT]\n"
    file_path.write_bytes(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run incremental Black and isort checks on changed Python files.")
    parser.add_argument(
        "--changes",
        required=True,
        help="Path to planner JSON emitted by changed_files.py",
    )
    parser.add_argument(
        "--reports",
        required=True,
        help="Directory to save formatter logs and failure reports",
    )
    args = parser.parse_args()

    changes_path = pathlib.Path(args.changes)
    if not changes_path.is_file():
        sys.stderr.write(f"check_format error: changes file not found: {changes_path}\n")
        sys.exit(1)

    try:
        data = json.loads(changes_path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"check_format error: invalid JSON in {changes_path}: {exc}\n")
        sys.exit(1)

    python_files = data.get("python_files")
    if not isinstance(python_files, list):
        sys.stderr.write("check_format error: 'python_files' key missing or not a list\n")
        sys.exit(1)

    if not python_files:
        sys.stdout.write("check_format: No changed Python files to check. Clean skip.\n")
        sys.exit(0)

    reports_dir = pathlib.Path(args.reports)
    reports_dir.mkdir(parents=True, exist_ok=True)

    failed = False

    # 1. Run Black
    black_cmd = [sys.executable, "-m", "black", "--check", "--"] + python_files
    proc_black = subprocess.run(black_cmd, capture_output=True, text=True)
    black_log = f"=== Black stdout ===\n{proc_black.stdout}\n=== Black stderr ===\n{proc_black.stderr}\nExit: {proc_black.returncode}\n"
    write_bounded_log(reports_dir / "black.log", black_log)
    if proc_black.returncode != 0:
        failed = True
        sys.stderr.write("check_format: Black formatting check failed.\n")

    # 2. Run isort (always attempted even if Black fails)
    isort_cmd = [sys.executable, "-m", "isort", "--check-only", "--"] + python_files
    proc_isort = subprocess.run(isort_cmd, capture_output=True, text=True)
    isort_log = f"=== isort stdout ===\n{proc_isort.stdout}\n=== isort stderr ===\n{proc_isort.stderr}\nExit: {proc_isort.returncode}\n"
    write_bounded_log(reports_dir / "isort.log", isort_log)
    if proc_isort.returncode != 0:
        failed = True
        sys.stderr.write("check_format: isort import sorting check failed.\n")

    if failed:
        sys.exit(1)

    sys.stdout.write(f"check_format: All {len(python_files)} Python files correctly formatted.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()

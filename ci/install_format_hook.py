#!/usr/bin/env python3
"""Install the repository-owned pre-commit launcher without downloading tools."""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = """#!/bin/sh
# MaxProFrame format hook v1
set -eu
common=$(git rev-parse --path-format=absolute --git-common-dir)
hook_dir=$(git rev-parse --path-format=absolute --git-path hooks)
export PRE_COMMIT_HOME="$common/pre-commit"
export VIRTUALENV_APP_DATA="$common/virtualenv"
export PIP_CACHE_DIR="$common/pip-cache"
export PIP_NO_CACHE_DIR=1
python="$common/format-tools/bin/python"
if [ ! -x "$python" ]; then
    echo "MaxProFrame format hook: missing $python; install format-tools first" >&2
    exit 1
fi
exec "$python" -m pre_commit hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit --hook-dir "$hook_dir" -- "$@"
"""


def main():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)

    root = git("rev-parse", "--show-toplevel")
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if root.returncode or common.returncode or pathlib.Path(root.stdout.strip()).resolve() != ROOT:
        sys.exit("format hook: installer must be in the Git worktree root")
    if pathlib.Path(common.stdout.strip()).resolve() != ROOT / ".git":
        sys.exit("format hook: only a normal clone with its .git directory is supported")
    configured = git("config", "--get", "core.hooksPath")
    if configured.returncode != 1:
        sys.exit("format hook: custom core.hooksPath or Git configuration error; refusing installation")
    hook_dir = ROOT / ".git" / "hooks"
    hook = hook_dir / "pre-commit"
    if hook.is_symlink():
        sys.exit("format hook: existing hook is a symlink; refusing installation")
    if hook.exists():
        if not hook.is_file() or hook.read_text() != HOOK:
            sys.exit("format hook: existing hook is not owned by MaxProFrame; refusing installation")
        if not os.access(hook, os.X_OK):
            sys.exit("format hook: owned hook is not executable; refusing to modify it")
        print("format hook: already installed")
        return
    hook_dir.mkdir(exist_ok=True)
    try:
        with hook.open("x", encoding="utf-8") as out:
            out.write(HOOK)
        hook.chmod(0o755)
    except FileExistsError:
        sys.exit("format hook: hook appeared during installation; refusing to overwrite")
    print("format hook: installed; format-tools must be installed separately")


if __name__ == "__main__":
    main()

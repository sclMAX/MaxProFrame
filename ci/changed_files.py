#!/usr/bin/env python3
"""Event-aware Git change planner for CI.

Determines changed files between Git references based on GitHub Actions events:
- pull_request: diff merge-base(base.sha, head.sha) .. head.sha
- push: diff before .. HEAD (or empty tree if before is all zeros)
- workflow_dispatch: diff INPUT_BASE_REF (default HEAD^) .. HEAD, always runs tests

Emits JSON to stdout with exact keys:
    {"base": "<sha>", "head": "<sha>", "python_files": [...], "run_tests": bool}
"""

import json
import os
import pathlib
import subprocess
import sys

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DOC_EXTENSIONS = {".md", ".rst", ".txt"}


def die(message: str) -> None:
    sys.stderr.write(f"changed_files error: {message}\n")
    sys.exit(1)


def git_cmd(*args: str, cwd: pathlib.Path) -> str:
    cmd = ["git"] + list(args)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"git command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout


def resolve_commit(ref: str, cwd: pathlib.Path) -> str:
    cmd = ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"Cannot resolve commit for ref '{ref}': {proc.stderr.strip()}")
    return proc.stdout.strip()


def is_doc_file(path_str: str) -> bool:
    """Checks whether a repo-relative path is strictly documentation."""
    parts = pathlib.PurePosixPath(path_str).parts
    if not parts or any(p == ".." for p in parts):
        return False
    ext = os.path.splitext(path_str)[1].lower()
    if ext not in DOC_EXTENSIONS:
        return False
    top = parts[0].lower()
    if top in ("docs", "odd"):
        return True
    if len(parts) == 1:
        base = os.path.splitext(parts[0])[0].upper()
        if base in ("README", "CHANGELOG", "CONTRIBUTING"):
            return True
    return False


def main() -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if not event_name:
        die("GITHUB_EVENT_NAME environment variable is required")

    try:
        repo_root = pathlib.Path(git_cmd("rev-parse", "--show-toplevel", cwd=pathlib.Path.cwd()).strip())
    except Exception as exc:
        die(f"Failed to find git repository root: {exc}")

    event_path_env = os.environ.get("GITHUB_EVENT_PATH")
    event_data = {}
    if event_path_env:
        event_path = pathlib.Path(event_path_env)
        if not event_path.is_file():
            die(f"Event file not found: {event_path}")
        try:
            event_data = json.loads(event_path.read_text(encoding="utf-8"))
        except Exception as exc:
            die(f"Failed to parse event JSON from {event_path}: {exc}")

    diff_base = ""
    diff_head = ""
    output_base = ""
    output_head = ""
    force_run_tests = False

    if event_name == "pull_request":
        pr = event_data.get("pull_request")
        if not isinstance(pr, dict):
            die("pull_request payload missing 'pull_request' object")
        base_sha = pr.get("base", {}).get("sha")
        head_sha = pr.get("head", {}).get("sha")
        if not base_sha or not head_sha:
            die("pull_request payload missing base or head SHA")
        base_commit = resolve_commit(base_sha, repo_root)
        head_commit = resolve_commit(head_sha, repo_root)
        merge_base = git_cmd("merge-base", base_commit, head_commit, cwd=repo_root).strip()
        diff_base = merge_base
        diff_head = head_commit
        output_base = base_commit
        output_head = head_commit

    elif event_name == "push":
        before = event_data.get("before", "")
        head_commit = resolve_commit("HEAD", repo_root)
        if before and set(before) == {"0"}:
            diff_base = EMPTY_TREE_SHA
            output_base = EMPTY_TREE_SHA
        elif before:
            diff_base = resolve_commit(before, repo_root)
            output_base = diff_base
        else:
            die("push event missing 'before' commit reference")
        diff_head = head_commit
        output_head = head_commit

    elif event_name == "workflow_dispatch":
        base_ref = os.environ.get("INPUT_BASE_REF", "").strip() or "HEAD^"
        diff_base = resolve_commit(base_ref, repo_root)
        diff_head = resolve_commit("HEAD", repo_root)
        output_base = diff_base
        output_head = diff_head
        force_run_tests = True

    else:
        die(f"Unsupported event name: {event_name}")

    # Compute changed files using git diff-tree with NUL delimiter
    cmd = ["git", "diff-tree", "-r", "-z", "--no-commit-id", "--name-status", diff_base, diff_head]
    raw_output = git_cmd(
        "diff-tree", "-r", "-z", "--no-commit-id", "--name-status", diff_base, diff_head, cwd=repo_root
    )

    tokens = raw_output.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()

    all_changed_files = []
    python_candidates = set()

    i = 0
    while i < len(tokens):
        status = tokens[i]
        i += 1
        if not status:
            continue
        status_code = status[0]
        if status_code in ("R", "C"):
            if i + 1 >= len(tokens):
                die("Malformed git diff-tree output for rename/copy")
            old_path = tokens[i]
            new_path = tokens[i + 1]
            i += 2
            all_changed_files.append(old_path)
            all_changed_files.append(new_path)
            if new_path.endswith(".py"):
                python_candidates.add(new_path)
        else:
            if i >= len(tokens):
                die("Malformed git diff-tree output")
            path = tokens[i]
            i += 1
            all_changed_files.append(path)
            if status_code != "D" and path.endswith(".py"):
                python_candidates.add(path)

    # Filter python files: must be relative, exist as regular file on disk, not a symlink
    filtered_python = []
    for p in python_candidates:
        pure = pathlib.PurePosixPath(p)
        if pure.is_absolute() or any(part == ".." for part in pure.parts):
            continue
        full_path = repo_root / p
        if full_path.is_file() and not full_path.is_symlink():
            filtered_python.append(p)

    sorted_python = sorted(filtered_python)

    if force_run_tests:
        run_tests = True
    elif not all_changed_files:
        run_tests = False
    else:
        run_tests = any(not is_doc_file(f) for f in all_changed_files)

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        val = "true" if run_tests else "false"
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"run_tests={val}\n")

    result = {
        "base": output_base,
        "head": output_head,
        "python_files": sorted_python,
        "run_tests": run_tests,
    }
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

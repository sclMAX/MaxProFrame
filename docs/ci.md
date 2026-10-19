# Continuous Integration Policy and Runner Guide

This document describes MaxProFrame's continuous integration (CI) architecture, reproducibility policies, change-planning logic, and local reproduction procedures.

## Quick path

### 1. Plan changed files
```bash
# In PR, push, or manual dispatch context
python3 ci/changed_files.py
```

### 2. Format checks (Black & isort)
```bash
# Install exact pinned versions (Black 25.1.0, isort 6.0.1)
python3 -m pip install -r ci/requirements-format.txt

# Run incremental check on planned changes
python3 ci/check_format.py --changes /path/to/changes.json --reports /path/to/reports
```

### 3. Native FreeCAD tests
```bash
# Run offscreen suite inside official FreeCAD 1.1.4 Linux AppImage (default: --target stable)
python3 ci/run_tests.py \
  --freecad-bin /path/to/squashfs-root/AppRun \
  --reports /path/to/reports \
  --timeout 180

# Run offscreen suite inside official FreeCAD 26.3rc2 Linux AppImage (--target rc)
python3 ci/run_tests.py \
  --freecad-bin /path/to/rc-squashfs-root/AppRun \
  --reports /path/to/reports \
  --timeout 180 \
  --target rc
```

## Policy summary

| Spec | Area | Accepted Policy Rule |
|------|------|----------------------|
| **S1** | Compatibility | Minimum supported: **FreeCAD 1.1.4**. Pinned matrix targets: **stable FreeCAD 1.1.4** (Python 3.11) and **RC FreeCAD 26.3rc2** (reports Version 26.3.0, Python 3.13). Never `latest`. Versions validated strictly per-target. |
| **S2** | Formatting | **Black + isort**, 120-column limit, pinned tool versions. Enforced strictly on **new or modified Python files** (no retroactive repository reformatting). |
| **S3** | Tests | Full test suite executed on changes to code, tests, runtime resources, or execution configs. Native tests are skipped for purely documentation changes. |
| **S4** | Failure | Formatting and native test targets run in **independent matrix jobs** (`fail-fast: false`). Any test failure, error, or timeout fails CI immediately without automatic retries. |
| **S5** | Triggers | Active on Pull Requests targeting `main`, pushes to `main`, and manual execution via `workflow_dispatch`. Standard Ubuntu runner. |
| **S6** | Security | Minimal read-only permissions (`contents: read`). No secrets passed to tests. No automated commits, releases, or package publications. |
| **S7** | Evidence | Small failure reports preserved as unique target-specific artifacts (`test-failure-reports-${{ matrix.target }}`) for **7 days**. Validated on Linux x86_64; Windows/macOS compatibility is not yet proven. |
| **S8** | Scope | Pinned CI scripts, workflow, tests and supporting documentation. A separately authorized importer correction preserves caller transactions (S9); packaging metadata declares minimum 1.1.4. |

## Change detection and diff logic

`ci/changed_files.py` evaluates the repository state without shell interpolation:

- **Pull Requests:** Evaluates `git merge-base(base.sha, head.sha) .. head.sha`.
- **Pushes:** Evaluates `before .. HEAD` directly (safely handling fast-forwards and force pushes). Initial pushes (`before = 000...000`) compare against Git's empty tree SHA (`4b825dc642cb6eb9a060e54bf8d69288fbee4904`).
- **Manual Dispatch:** Evaluates `INPUT_BASE_REF` (default `HEAD^`) against `HEAD`, and always triggers test execution.
- **Documentation Skip:** Changes restricted exclusively to Markdown, reStructuredText, or plain text docs under `docs/`, `odd/`, or root documentation (`README*`, `CHANGELOG*`, `CONTRIBUTING*`) skip native tests. Any change to code, build configs, dependencies (`requirements*.txt`, `pyproject.toml`), or resources triggers the full test suite.
- **Path Safety:** Paths are parsed using NUL-delimited records (`git diff-tree -z`), safely handling spaces, leading hyphens, and option-like names (`--`).

## Native runner and offscreen execution

Official FreeCAD AppImages (such as 1.1.4 and 26.3rc2) ship an `AppRun` script that unconditionally exports `QT_QPA_PLATFORM=xcb` (or falls back to it). In headless environments without X11 or Wayland, this causes Qt initialization failure (exit code 134). Furthermore, FreeCAD's CLI argument parser (Boost Program Options) rejects unrecognized Qt options such as `-platform`, prompting an invisible `QMessageBox` modal dialog in `MainGui.cpp` that blocks headless execution until timeout (exit code 124).

To resolve both issues without patching vendor AppImages:
1. When `--freecad-bin` points to `AppRun` (e.g. `--freecad-bin /path/to/squashfs-root/AppRun`), `ci/run_tests.py` automatically resolves to the native binary (`usr/bin/freecad`), bypassing the vendor `AppRun` script to prevent `QT_QPA_PLATFORM=xcb` from overriding the headless environment.
2. The wrapper reproduces the official AppRun environment bootstrap (`PREFIX`, `PYTHONHOME`, `PATH_TO_FREECAD_LIBDIR`, font and SSL certificate paths) while preserving `QT_QPA_PLATFORM=offscreen`.
3. Execution invokes the native binary with `--user-cfg` and the macro path, omitting any `-platform` command-line argument.
4. Execution occurs inside isolated temporary directories for `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `TMPDIR`, and `FREECAD_USER_HOME` (which suppresses the version migration prompt).
5. Target validation (`--target stable` or `--target rc`):
   - Default is `--target stable`, requiring FreeCAD 1.1.4 and Python 3.11.
   - When `--target rc` is selected, the macro strictly verifies FreeCAD 26.3.0 (`FreeCAD.Version()[:3] == ['26', '3', '0']`) and embedded Python 3.13. Packaging labels (e.g. `26.3rc2`) are distinguished from the runtime's internal Version tuple (`26.3.0`).
   - Any runtime or Python version mismatch terminates execution immediately with exit code 1 and writes no `summary.json`.
6. Process-group timeouts are enforced (exit code 124 on timeout), and `ci/run-tests.FCMacro` emits structured diagnostic checkpoints (`macro-entry`, `validated-version`, `discovery-start`, `completed-summary`) to `startup.log`.
7. Test outcomes require fresh, strictly validated `summary.json` containing positive test counts, zero failures/errors, and consistent non-negative counts. Previous execution artifacts are cleared before launch to avoid stale false-green results.

## Current scope and validation status

- **Host validation:** CI policy tests (`ci/tests/test_policy.py`) verify planner logic, formatting wrappers, runner process isolation, AppRun binary resolution, `--target` parameter routing, and summary validation contracts. Host tests are fully green.
- **Native execution:** CI pins the following official Linux x86_64 AppImage SHA-256 checksums; local native suites used the already-extracted runtimes:
  - Stable: FreeCAD 1.1.4 py311 (`f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`).
  - RC: FreeCAD 26.3rc2 (`2cf4212d5a348574e786da7d5a8faeeb3e83dd4245c23898dede92ce82ce4908`).
  Local results:
  - Stable: **355/355 passed** offscreen (exit code 0, 0 failures, 0 errors, 0 skips).
  - RC (initial run): **354/355 passed** (exit code 1, 1 failure, 0 errors, 0 skips). `test_named_forward_formula_and_metadata` failed its source BREP snapshot comparison after the test itself changed and restored a sketch datum; the diff included a numerical epsilon (`-8.8817841970012523e-16` versus `0.0`) due to registration-time evaluation in `addCleanup` mixing native OCC recompute precision with capture immutability.
  - RC (corrected boundary run): **355/355 passed** offscreen (exit code 0, 0 failures, 0 errors, 0 skips). Causal observation boundaries in `tests/test_t2_independent.py` were corrected to assert exact full source snapshot equality immediately after capture and compare against a fresh post-control baseline after editing the captured copy, without adding tolerances, skips, or application changes. Both native suites are now fully green on their pinned extracted runtimes.
- **Review status:** Independent bounded verification of this stable/RC CI change passed: target-validation probes, six baseline/candidate default-runner comparisons, fixture AST checks and native evidence readback found no candidate-caused blockers. Native review assessment could not resolve the current untracked scope; no native review approval is claimed.
- **Hosted execution:** Matrix jobs test both `stable` and `rc` targets independently (`fail-fast: false`). No claim of hosted GitHub Actions execution is made prior to live pull request verification.

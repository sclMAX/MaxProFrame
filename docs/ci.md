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
# Run offscreen suite inside official FreeCAD 1.1.4 Linux AppImage
python3 ci/run_tests.py \
  --freecad-bin /path/to/squashfs-root/AppRun \
  --reports /path/to/reports \
  --timeout 180
```

## Policy summary

| Spec | Area | Accepted Policy Rule |
|------|------|----------------------|
| **S1** | Compatibility | Initial baseline: **FreeCAD 1.1.4** (Python 3.11). Pinned exact version, never `latest`. Future stable versions validated explicitly. |
| **S2** | Formatting | **Black + isort**, 120-column limit, pinned tool versions. Enforced strictly on **new or modified Python files** (no retroactive repository reformatting). |
| **S3** | Tests | Full test suite executed on changes to code, tests, runtime resources, or execution configs. Native tests are skipped for purely documentation changes. |
| **S4** | Failure | Formatting and native test suites run in **independent jobs**. Any test failure, error, or timeout fails CI immediately without automatic retries. |
| **S5** | Triggers | Active on Pull Requests targeting `main`, pushes to `main`, and manual execution via `workflow_dispatch`. Standard Ubuntu runner. |
| **S6** | Security | Minimal read-only permissions (`contents: read`). No secrets passed to tests. No automated commits, releases, or package publications. |
| **S7** | Evidence | Small failure reports preserved as artifacts for **7 days**. Validated on Linux x86_64; Windows/macOS compatibility is not yet proven. |
| **S8** | Scope | Pinned CI scripts, workflow, tests and supporting documentation. A separately authorized importer correction preserves caller transactions (S9); packaging metadata and unrelated application behavior remain unchanged. |

## Change detection and diff logic

`ci/changed_files.py` evaluates the repository state without shell interpolation:

- **Pull Requests:** Evaluates `git merge-base(base.sha, head.sha) .. head.sha`.
- **Pushes:** Evaluates `before .. HEAD` directly (safely handling fast-forwards and force pushes). Initial pushes (`before = 000...000`) compare against Git's empty tree SHA (`4b825dc642cb6eb9a060e54bf8d69288fbee4904`).
- **Manual Dispatch:** Evaluates `INPUT_BASE_REF` (default `HEAD^`) against `HEAD`, and always triggers test execution.
- **Documentation Skip:** Changes restricted exclusively to Markdown, reStructuredText, or plain text docs under `docs/`, `odd/`, or root documentation (`README*`, `CHANGELOG*`, `CONTRIBUTING*`) skip native tests. Any change to code, build configs, dependencies (`requirements*.txt`, `pyproject.toml`), or resources triggers the full test suite.
- **Path Safety:** Paths are parsed using NUL-delimited records (`git diff-tree -z`), safely handling spaces, leading hyphens, and option-like names (`--`).

## Native runner and offscreen execution

Official FreeCAD 1.1.4 AppImage ships an `AppRun` script that unconditionally exports `QT_QPA_PLATFORM=xcb` (line 14). In headless environments without X11 or Wayland, this causes Qt initialization failure (exit code 134). Furthermore, FreeCAD's CLI argument parser (Boost Program Options) rejects unrecognized Qt options such as `-platform`, prompting an invisible `QMessageBox` modal dialog in `MainGui.cpp` that blocks headless execution until timeout (exit code 124).

To resolve both issues without patching the vendor AppImage:
1. When `--freecad-bin` points to `AppRun` (e.g. `--freecad-bin /path/to/squashfs-root/AppRun`), `ci/run_tests.py` automatically resolves to the native binary (`usr/bin/freecad`), bypassing the vendor `AppRun` script to prevent `QT_QPA_PLATFORM=xcb` from overriding the headless environment.
2. The wrapper reproduces the official AppRun environment bootstrap (`PREFIX`, `PYTHONHOME`, `PATH_TO_FREECAD_LIBDIR`, font and SSL certificate paths) while preserving `QT_QPA_PLATFORM=offscreen`.
3. Execution invokes the native binary with `--user-cfg` and the macro path, omitting any `-platform` command-line argument.
4. Execution occurs inside isolated temporary directories for `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `TMPDIR`, and `FREECAD_USER_HOME` (which suppresses the version migration prompt).
5. Process-group timeouts are enforced (exit code 124 on timeout), and `ci/run-tests.FCMacro` emits structured diagnostic checkpoints (`macro-entry`, `validated-version`, `discovery-start`, `completed-summary`) to `startup.log`.
6. Test outcomes require fresh, strictly validated `summary.json` containing positive test counts, zero failures/errors, and consistent non-negative counts. Previous execution artifacts are cleared before launch to avoid stale false-green results.

## Current scope and validation status

- **Host validation:** CI policy tests (`ci/tests/test_policy.py`) verify planner logic, formatting wrappers, runner process isolation, AppRun binary resolution, and summary validation contracts. Host tests are fully green.
- **Native execution:** Artifact download SHA256 checksum and extraction are verified against the official FreeCAD 1.1.4 Linux x86_64 py311 AppImage. Baseline native launch failed with exit code 134 (unhandled xcb requirement), and initial runner execution timed out with exit code 124 (unhandled modal dialog on `-platform`). The corrected launcher reached macro entry and validated FreeCAD 1.1.4 / Python 3.11. An initial suite run timed out inside the theme-card fixture; a fixture-only isolation change retained every original assertion while removing global event pumping and desktop window display. The next authorized native run completed all **338 tests in 42.512 seconds**, with **2 failures, 0 errors, and 0 skips** (process exit 1); both theme tests passed. The remaining failures concern rollback after cancelling profile insertion: `test_reject_transaction_rollback_preserves_project_state` and `test_path_change_repeated_preview_then_reject` leave preview objects present. A subsequent single authorized run explicitly enabled `UndoMode = 1` in the shared test-document fixture. It still completed **338 tests in 46.827 seconds**, with **the same 2 failures, 0 errors, and 0 skips** (exit 1). Enabling Undo alone therefore does not resolve the failures; their cause remains unproven. The fixture change preserves all assertions, and formatting changes were checked for AST equivalence. The suite is not green, and CI correctly reports failure. A later isolated, instrumented diagnostic ran only the two original failing tests: both passed (2 tests in 0.755 seconds), with no unittest failures/errors/skips or recorded instrumentation errors. Its trace shows cancellation restoring each project's baseline objects. This is not a full-suite pass or a proven fix; test-order/global-state effects and instrumentation differences remain unproven hypotheses. The diagnostic's stderr also contains Qt/OpenGL warnings and internal profile recomputation exceptions, despite unittest reporting no errors. A subsequent diagnostic performed full discovery/imports but executed only the nine portable-profile tests: 8 passed and the rollback case failed (9 tests in 2.997 seconds, no unittest errors/skips or instrumentation errors). Its trace captured a project transaction commit while the importer closed its owned asset document, before cancellation attempted to abort that same project transaction. This identifies a premature-commit mechanism in the reproduced case; the second boundary failure was not included in that nine-test probe. A subsequent bounded importer correction disables undo recording only for importer-owned read-only assets and activates the target before capture. Its public regression first failed for a lazy caller transaction, then the focused run passed all 11 tests, including both original rollback failures and a materialized-transaction control. Independent static/evidence verification found no candidate-caused blocker; all 111 baseline assertions were retained. However, the latest uninstrumented full-suite run timed out after **180 seconds (exit 124)** while `test_custom_profile_cards_independent.IndependentCards.test_selected_edits_apply_and_cancel` was in progress. No completed summary was produced; no automatic retry was performed. The cause and relationship to the importer change remain unproven. After diagnostic-only checkpoints were added (all 21 assertions and original test operations preserved), the single subsequently authorized full-suite run completed **339 tests in 48.594 seconds, with 0 failures, 0 errors, and 0 skips (exit 0)**. Both rollback cases, the new transaction regression and the strengthened user-owned undo-state assertion passed; 78 card checkpoints completed through teardown. This establishes a completed instrumented Linux baseline run, not a proven fix or stability guarantee for the earlier intermittent stall. The earlier timeout remains retained evidence; logging may affect timing. Stderr still contains Qt warnings and internal recomputation exceptions despite unittest reporting no errors. A later fixture-only change replaced desktop focus/global event pumping in the Apply/Cancel functional test with synchronous Qt `FocusIn` delivery through the real event filter, without preselecting the edited card. All 21 original assertions remain, with three additional selection checks; the separate rendering test is unchanged. Its single authorized full-suite run passed **339 tests in 42.777 seconds, with 0 failures, 0 errors, and 0 skips (exit 0)**. This validates the narrower fixture; it does not establish the exact cause of the earlier timeout or long-term stability.
- **Review status:** Independent bounded verification of the importer correction passed. Native review assessment could not resolve the current untracked scope; no native review approval is claimed.
- **Hosted execution:** No claim of hosted GitHub Actions execution is made prior to live pull request verification.

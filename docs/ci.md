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

### Run one test for investigation

Add `--test test_create_profile_confirm_gui.TestCreateProfileConfirmGui.test_snapshot_form_proxy_raises_attribute_error_on_unknown`
to the native runner command to reproduce one method. A `test_` module name or
`test_module.Class` selects the whole module or class. Names are relative to the
project's `tests/` directory, without `.py`, package prefixes or filesystem paths;
components use ASCII identifiers, with at most module, class and method.
Empty or malformed selectors fail before launching FreeCAD or clearing reports.
Unknown valid names produce failed unittest loader tests, never a skip or success.

Without `--test`, discovery still runs the entire suite, even if `FF_TEST` was
inherited. The wrapper forwards only an explicit selection to the existing macro
through `FF_TEST`. Selection does not change runtime validation, timeout,
diagnostics, failure/error handling or summary count checks. A targeted pass is
not evidence that the full suite passes; CI continues to run full discovery.

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

### Isolated notification popup preferences

Before launching either runtime, the wrapper seeds only its temporary `--user-cfg`
under `User parameter:BaseApp/Preferences/NotificationArea`:

- Bool `NonIntrusiveNotificationsEnabled=false` (`FCBool`, value `0`).
- Int `MaxOpenNotifications=0` (`FCInt`, value `0`).

Both are needed: disabling nonintrusive notifications alone leaves the repeated-message
popup branch enabled. The zero maximum blocks the popup show guard even for repeats.
Native evidence captured a reentrant notification mutex wait when showing a popup
produced an offscreen Qt unsupported-raise warning. This seed targets that popup path;
it is not yet proof that native timeouts or the separate SIGSEGV are resolved.

`NotificationAreaEnabled` is untouched (disabling it deletes the widget). Console
observers, logging severity/subscriptions, warnings/errors, critical-message
confirmations and unittest verdicts remain unchanged. No real user preferences
are written; the isolated profile is removed after execution.

Supported preference behavior is confirmed in tagged
[1.1.4 NotificationArea.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/NotificationArea.cpp)
and [26.3rc2 NotificationArea.cpp](https://github.com/FreeCAD/FreeCAD/blob/26.3rc2/src/Gui/NotificationArea.cpp);
the startup XML format follows
[Parameter.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Base/Parameter.cpp).

## Timeout diagnostic evidence

The macro writes evidence into the existing `--reports` directory (included in
failure artifacts), without changing the runner deadline, verdicts or dialogs:

- `python-stacks.log`: one all-thread Python stack dump after 120 seconds from
  macro entry, independently of the Qt event loop. CPython bounds this to 100
  threads, 100 frames per thread and 500 characters per string; no locals or
  source lines are collected. A successful suite cancels the pending dump.
- `modal-state.jsonl`: at most 12 snapshots, every 30 seconds on the GUI thread,
  each limited to 32 top-level widgets. Only bounded class names, visibility,
  modality, active modal class and elapsed time are recorded. No window titles,
  widget text, object names, environment or credentials are collected.

### Structural Qt observer evidence

The optional structural observer helper never pumps events or answers dialogs.
`qt-events.jsonl` retains at most 272 records: the first 192 ordinary widget
Show/Hide/Close/WindowBlocked/WindowUnblocked events, the latest 64 modal widget
events, and 16 deduplicated structural errors. Separate modal/error capacity
prevents ordinary startup widgets from hiding later modal evidence. Modal events
remain a bounded tail, not a complete history. Records contain event number,
class (80 characters), visibility, modality and elapsed time, never widget text.
PySide enums use `.value` before integer conversion. Exception messages are
excluded. An initial modal snapshot supplements existing periodic snapshots.
This helper is inactive unless explicit manual instrumentation installs it.

Diagnostics never pump events, dismiss or answer dialogs. If the GUI thread is
blocked outside a nested event loop, Qt snapshots may stop; the independent stack
watchdog can still provide evidence. A native call holding the GIL may also
prevent Python timer callbacks. Empty/missing evidence can mean early startup
failure or unavailable diagnostics, not proof that no modal existed. Short runner
timeouts can expire before either diagnostic fires. Diagnostic setup/I/O failures
are nonfatal and do not replace summary validation. Old diagnostic files are
cleared with other stale reports before launch.

The hosted stable timeout at 420 seconds remains unexplained: both original local
450-test suites passed. This slice collects evidence, not a preventive dialog fix;
a native modal escaping the existing offscreen fixture remains unproven.

## Explicit manual native investigation (stable only)

Dispatch CI with the boolean `native_diagnostics` enabled (default: false).
Only the stable job installs GDB and passes `--native-diagnostics`; PR, push,
RC and ordinary manual runs retain the normal launch path and deadlines.
Locally, add `--native-diagnostics --target stable --timeout 420` to the native
runner command above. GDB must already be installed; timeouts <=160 are rejected.

The inferior is launched under GDB, not attached by a sibling process. AppImage
Python bootstrap paths are applied to the inferior only, not GDB's Python.
No sudo debugger, ptrace-policy changes or external debug-symbol downloads are used.
At 150 seconds an independent debugger timer requests SIGSTOP, collects up to
64 threads and 64 function names per thread (160 characters/name, no arguments,
locals or source text), then continues the **same** inferior without delivering
SIGSTOP. The original runner deadline and summary validation remain authoritative.
Unexpected debugger stops record their bounded signal and native frames before
interrupting the diagnostic run with failure, not success. In particular SIGSEGV
is never suppressed or continued.
Missing GDB fails explicitly; no retry or fallback suite is launched.

Additional reports:

- `native-stacks.jsonl`: arming, bounded native frames, structural capture errors
  and inferior exit code. An early successful run has no capture frames.
- `native-inferior.pid`: runtime-owned PID used for timeout cleanup, including
  GDB's separate inferior process group within the runner's session.
- `qt-events.jsonl`: bounded structural observer evidence described above.

The stable report artifact is uploaded for this explicit mode even on success,
using the existing `test-failure-reports-stable` name and seven-day retention.
Missing/empty native frames or Qt events cannot exclude a modal or prove a cause.
Diagnostics do not dismiss dialogs, synthesize input, skip tests or repair the GUI.

## GitHub Actions runner infrastructure and Node 24

GitHub Actions JavaScript actions execute on the runner's internal Node.js runtime. GitHub Actions has updated official actions to Node 24 and flags workflows invoking Node 20 actions with runner deprecation warnings.

| Action | Pinned Ref / Full SHA | Declared Action Runtime |
|--------|-----------------------|-------------------------|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`) | Node 24 |
| `actions/setup-python` | `5fda3b95a4ea91299a34e894583c3862153e4b97` (`v7.0.0`) | Node 24 |
| `actions/upload-artifact` | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` (`v7.0.2`) | Node 24 |

### Infrastructure boundary vs project dependencies
- **Action infrastructure only:** Node 24 is strictly an execution requirement of GitHub's hosted runner infrastructure. MaxProFrame does **not** depend on Node.js, npm, or JavaScript. MaxProFrame remains a FreeCAD workbench; its native CI suites run offscreen under Python 3.11 / Python 3.13. Contributors and users do not need Node.js installed locally.
- **Runner requirements:** Node 24 actions require GitHub Actions runner `>= 2.327.1`. GitHub-hosted `ubuntu-24.04` runners satisfy this requirement.
- **Full commit SHAs:** All action references in `.github/workflows/ci.yml` are pinned to immutable 40-character commit SHAs with semantic version comments. Floating or moving major tags (`@v4`, `@v5`, `@v7`) are strictly avoided.

## Current scope and validation status

- **Host validation:** CI policy tests (`ci/tests/test_policy.py`) verify planner logic, formatting wrappers, runner process isolation, AppRun binary resolution, `--target` parameter routing, summary validation contracts, and exact pinned action SHAs. Host tests are fully green.
- **Native execution:** CI pins the following official Linux x86_64 AppImage SHA-256 checksums; local native suites used the already-extracted runtimes:
  - Stable: FreeCAD 1.1.4 py311 (`f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`).
  - RC: FreeCAD 26.3rc2 (`2cf4212d5a348574e786da7d5a8faeeb3e83dd4245c23898dede92ce82ce4908`).
  Local results:
  - Stable: **355/355 passed** offscreen (exit code 0, 0 failures, 0 errors, 0 skips).
  - RC (initial run): **354/355 passed** (exit code 1, 1 failure, 0 errors, 0 skips). `test_named_forward_formula_and_metadata` failed its source BREP snapshot comparison after the test itself changed and restored a sketch datum; the diff included a numerical epsilon (`-8.8817841970012523e-16` versus `0.0`) due to registration-time evaluation in `addCleanup` mixing native OCC recompute precision with capture immutability.
  - RC (corrected boundary run): **355/355 passed** offscreen (exit code 0, 0 failures, 0 errors, 0 skips). Causal observation boundaries in `tests/test_t2_independent.py` were corrected to assert exact full source snapshot equality immediately after capture and compare against a fresh post-control baseline after editing the captured copy, without adding tolerances, skips, or application changes. Both native suites are now fully green on their pinned extracted runtimes.
- **Review status:** Independent bounded verification of this stable/RC CI change passed: target-validation probes, six baseline/candidate default-runner comparisons, fixture AST checks and native evidence readback found no candidate-caused blockers. Native review assessment could not resolve the current untracked scope; no native review approval is claimed.
- **Hosted execution:** Matrix jobs test both `stable` and `rc` targets independently (`fail-fast: false`). Historical evidence: prior hosted CI run `39333298411` on `main` at `7b63d90` passed 355/355 on both targets and 37 host tests under prior actions. For this new Node 24 candidate, hosted execution cannot run locally without publishing/dispatch authorization; no hosted CI claim is made for this candidate.

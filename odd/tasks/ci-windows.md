# CI on Windows and parallel test shards

Add a non-blocking native FreeCAD 1.1.4 job on Windows and split the native suite into parallel shards to cut CI wall time, keeping the required check names.
Worktree `.git/gentle-worktrees/ci-windows`, branch `feat/ci-windows` from origin/main 4f602ba. Local native runner: `/usr/bin/python3 ci/run_tests.py --freecad-bin <main checkout>/.git/ci-policy-runtime/squashfs-root/AppRun --reports <dir>`.

## Specs

- S1. "agreguemos a CI matrix para windows" — step 1 accepted ("si"): a native FreeCAD **1.1.4 stable** job on `windows-latest` using the official portable archive `https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311.7z` (sha256 `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`), pinned in `ci/targets.json` like the Linux targets, downloaded and cached by checksum, checksum always verified.
- S2. The Windows job is **not blocking** (`blocking: false`, same `continue-on-error: ${{ !matrix.blocking }}` mechanism as weekly) and runs on push to `main` and `workflow_dispatch`, **not on pull requests**. macOS is out of scope for this slice.
- S3. `ci/run_tests.py` launches FreeCAD on Windows (portable `bin/FreeCAD.exe`/`freecad.exe`, offscreen, isolated profile through the same environment variables or their Windows equivalents such as `APPDATA`/`LOCALAPPDATA`/`USERPROFILE`), enforces the timeout by killing the whole process tree without `os.killpg`, and skips gdb-only diagnostics where gdb is unavailable with a clear message. Linux behavior is unchanged.
- S4. "configurando corridas en paralelo para optimizar tiempos" — the native suite can be split into N deterministic shards (`--shard INDEX/COUNT`, every discovered test runs in exactly one shard, the union equals the unsharded suite, invalid values are rejected with a clear error). The shard count per target lives in `ci/targets.json`; the workflow expands targets x shards into parallel jobs.
- S5. Required checks keep working: branch protection requires exactly `Native FreeCAD (stable)` and `Code Formatting (Black & isort)`. A gate job named `Native FreeCAD (${{ target }})` per target depends on that target's shards and fails when a blocking target's shard fails; non-blocking targets never fail the workflow. Failure reports are uploaded per shard.
- S6. Docs (`docs/` CI section and `ci/` help text) describe the Windows target, shards and how to run one shard locally.

## Tasks

- T1. [S4, S5] `--shard` in run_tests.py + targets.json shard counts + workflow shard matrix and gate jobs + policy tests — route: worker — commit: 2816ace
- T2. [S1, S2, S3, S6] Windows target, cross-platform run_tests.py launch/timeout, workflow Windows job, docs, policy tests — route: worker (same, after T1) — commit: 0b63207
- T3. [S1-S5] Push branch, dispatch CI on the branch, observe Linux shards + gate + Windows job, fix — route: parent — commit: pending
- T4. Independent verify (Risk item 5: CI/delivery), PR and merge after user OK — route: verify + parent — commit: pending

## Log

- L1. User: "Bien agreguemos a CI matrix para windows y MacOS que opinas? pros y contras?"
- L2. Parent recommended: Windows stable first, non-blocking, fix or skip platform tests, later blocking, then macOS; Windows/macOS only on main and nightly to keep PRs fast.
- L3. User: "si y configurando corridas en paralelo para optimizar tiempos".
- L4. Evidence: branch protection on main requires ["Native FreeCAD (stable)", "Code Formatting (Black & isort)"]; ci/tests/test_policy.py pins `name: Native FreeCAD (${{ matrix.target }})`. Linux stable job takes 3m34s, weekly 4m31s (PR #37). Repo is public (Actions minutes free).
- L5. Worker T1 (S4, S5) commit 2816ace `ci: run the native suite in parallel shards behind per-target gate jobs`. `--shard INDEX/COUNT` = every COUNT-th test of discovery order from INDEX (1/1 = untouched suite; shuffle only reorders inside the shard; invalid values exit 2 before launch). targets.json `shards`: stable 2, weekly 2 (setup ~1 min repeats per shard; a third shard saves <30 s of tests). Workflow: shard jobs `Native FreeCAD (<target>, shard n/N)`, artifacts `test-failure-reports-<target>-shard-<n>`; gate `Native FreeCAD (<target>)` with `needs: [targets, test]`, `if: always()`, fails only for a blocking target when `needs.test.result != success`. RED: 187 tests, 32 failures + 14 errors; GREEN: 187 OK (baseline 170).
- L6. Worker T2 (S1, S2, S3, S6) commit 0b63207 `ci: add a non-blocking native FreeCAD 1.1.4 job on Windows`. targets.json `windows` (portable 7z + sha256, blocking false, shards 3, timeout 600, `platform`, `pull_request: false`); Linux-only steps behind `runner.os == 'Linux'`, Windows steps in pwsh (cache `freecad-portable-<sha256>`, Get-FileHash always, 7z, bin/FreeCAD.exe); run_tests Windows profile vars, new process group + `taskkill /T /F`, gdb rerun skipped on Windows. RED: 205 tests, 13 failures + 24 errors; GREEN: 205 OK. bump_weekly apply on a scratch copy rewrites only weekly label/url/sha256.
- L7. Local native evidence (stable runtime, final tree): `--shard 1/2` 428 tests OK (141 s), `--shard 2/2` 428 OK (142 s), unsharded 856 OK (339 s); shard union = full multiset. The full suite already lists 15 ids twice (`test_unified_custom_profile_editor.TestUnifiedCustomProfileEditor` is discovered twice); each occurrence runs in one shard. Black 25.1.0 / isort 6.0.1 clean. Not verified locally: Windows execution and hosted GitHub semantics (that a failed continue-on-error leg leaves `needs.test.result == success`) — T3.

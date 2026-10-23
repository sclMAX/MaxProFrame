# Stable CI timeout diagnostics
Objective: obtain evidence for the hosted-only stable FreeCAD timeout without changing application/dialog behavior.
Branch: diagnose/stable-ci-timeout | Delivery: ask-on-risk, one diagnostic slice (~250 authored lines) | Runner: ci/run_tests.py

## Specs
- S1: Reported failure: "Run python3 ci/run_tests.py \
run_tests error: FreeCAD process timed out after 420.0s (killed process group).
Error: Process completed with exit code 124."
- S2: Unattended execution constraint: "en CI no tenemo UI ni usauraio debemos preveer esto, capas estamos mostrando un dilogo que nadie ve ni puede cerrar. puede ser este el problema?"
- S3: Implementation authorization: "ok vamos con eso". Runtime setup authorization: "si descarga y configura las imagenes para las pruebas".
- S4: Hosted diagnostic authorization: "si", answering the recommended option to prepare, publish and execute diagnostics in GitHub rather than claim an unproven preventive fix.

## Tasks
- T1 | S1-S4 | delegated (context backstop) | done | Add bounded stack/modal diagnostic evidence and regression tests/docs; preserve timeouts, exit codes, and application behavior. Risk: item 5 (CI execution diagnostics). Commit: 9543689.
- T2 | S1-S4 | independent verify + native assessment/review as offered | done | Host/native checks passed; independent S1-S4 verification passed; native review approved and acknowledged for diagnostic candidate (review-65b0ff7e4a1e4494). Formatting remains for hosted T3. Commit: 9543689; final diagnostic candidate review-1fd9afac95abfec5 approved and acknowledged.
- T3 | S1,S4 | inline delivery | in_progress | Commit reviewed diagnostic slice, non-force push to origin diagnostic branch, dispatch CI on that branch, inspect reports and explain findings. Commit: 9543689; hosted run pending.

## Log
- L1: Original request: "Hola, revisemos como esta CI".
- L2: User failure report quoted verbatim in S1; discussion and unattended constraint quoted in S2. User requested "analicemos soluciones", then authorized implementation as in S3.
- L3: Hosted run 39940596432 at 79dfdb991c5c57501dec1c6905394df4de54f1bc failed stable at 420 s; artifact 12494964640 ends in test_real_ok_missing_asset_reports_error_and_rolls_back. No completed summary; Qt/modal involvement remains a hypothesis.
- L4: Both pinned AppImages downloaded, SHA-256 verified and extracted under ignored .freecad-test/runtimes/{stable,rc}/squashfs-root/AppRun. Original suite at identical source passed locally: stable 450/450 in 61 s; RC 450/450 in 137 s. No skips/failures/errors. Therefore no claim of local reproduction or root-cause fix.
- L5: Accepted diagnostic scope: capture Python stacks and read-only Qt dialog state during a stall, preserve original suite behavior/timeouts, upload existing failure reports. No automatic dialog dismissal, timeout increase, retries, test skipping, production application changes or merge. This is the recommended option accepted by S4; use existing report artifacts rather than introduce another service.
- L6: Preparation: feature branch created from 79dfdb9. Writer delegated due measured parent context backstop. Forecast ~250 authored changed lines; keep one cohesive diagnostic slice, not a generic observability framework.
- L7: T1 writer completed: one stack dump at 120 s, up to 12 read-only Qt snapshots at 30 s intervals, stale diagnostic cleanup, host regressions and docs. RED exit 1 (missing module); GREEN 46 host tests, exit 0. Parent read back all new diagnostic code. T2 assessment explicitly escalated item 5; native scope selected after the initial inventory round trip; independent verifier required. No root-cause claim.
- L8: Parent spot check: 46/46 host tests, exit 0. Eight public CLI comparisons (stable/RC x success, exit7, missing summary, timeout) preserved exact stdout/stderr/exit against base. Instrumented native suites: stable 450/450 in 63s; RC 450/450 in 137s, all zero failures/errors/skips. Stable emitted one Qt snapshot; RC emitted two and an actual one-shot 120s Python stack dump, then succeeded. The stack dump's 'Timeout' label is diagnostic, not a runner failure. Local formatting setup failed: host Python lacks ensurepip; no system installation or retry. Hosted format check pending.
- L9: Commit attempt failed before creating a commit: Git author identity is unset (exit 128). The intended slice remains staged; no push or dispatch occurred. User must supply the repository-local author name/email; do not invent identity or set global Git configuration.
- L10: Independent verify completed S1-S4 with no severe blockers; real synthetic watchdog test produced a stack at 120s then exact runner exit124 at122s, and additional baseline/candidate public-runner probes preserved outcomes. Native review of the diagnostic candidate (target sha256:57d1f67b843f9a581091016518fa9b51a15d5cd52c7484058f0db5aa09e64f2a, lineage review-65b0ff7e4a1e4494) approved across resilience/readability/reliability; exact acknowledgement completed with authority burned. This bookkeeping log update is post-review; no diagnostic code changed. Root cause still unproven. T3 was blocked on author identity at that observation; no publication or hosted result was claimed.
- L11: User supplied "sclMAX, maxi.indumatics@gmail.com". Configured repository-local Git identity only, committed diagnostic candidate as 954368901368baacaa7d8544a6831afaa4d2db69. Final diagnostic worktree target sha256:4dc2cd887aaa64ac12e696f54c993b17026f0aa31d5a6c40913daad0b741f03b was approved and acknowledged under review-1fd9afac95abfec5 before commit. This task-state update is documentation-only; diagnostic code is unchanged. T3 proceeds with branch publication and workflow_dispatch.

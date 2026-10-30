# CI hardening after restoring green native CI
Branch: `ci/hardening` from `main` at `5e0e1ca` (PR #12 merged). Plan approved in `odd/tasks/ci-native-stability.md` L16 (step 1).
Risk: item 5 (CI workflow/environment). Keep accepted CI policy (`odd/tasks/ci-policy.md`): pinned versions, read-only permissions, no automatic retries that hide failures.

## Specs
S1. Approved plan item (a) "Diagnóstico de crash": "si el proceso muere por señal, el runner escribe en el job summary qué test estaba corriendo; en un crash relanza **solo ese test** bajo gdb y sube el backtrace como artefacto". The rerun is diagnostic only: the job must still fail with the original exit status (never turn a crash green).
S2. Approved plan item (b) "Cache de AppImages con `actions/cache`, usando el sha256 como clave". A cache hit must still be verified with `sha256sum -c`.
S3. Approved plan item (c) "`concurrency` por rama con `cancel-in-progress`". Must not cancel runs on `main` pushes (each main commit keeps its own result).
S4. Approved plan item (d) "Workflow nocturno de flakiness: corre la suite nativa N veces, con orden aleatorio en una de ellas, y queda rojo si algo falla aunque sea una vez". Scheduled + manual dispatch, stable target, read-only permissions; random order must be reproducible from a printed seed.

## Tasks
T1 [S1] route=delegated worker mvv0abk4-6-k2xh; status=done; commit=see git log (crash diagnosis); host 84 OK (RED 9F+3E on 12 new); parent e2e forced SIGSEGV: exit 1 preserved, summary + test id + gdb backtrace with Python frame; crash summary + gdb rerun of the crashing test + artifact, test-first in ci/tests.
T2 [S2,S3] route=inline; status=done; commit=see git log (cache+concurrency); host RED 2 failures -> GREEN 86 OK; existing pin-count test updated 6->7 (cache v6.1.0 verified node24); AppImage cache keyed by sha256 with verification on hit; concurrency group cancelling only non-main refs; policy tests.
T3 [S4] route=delegated worker; status=pending; commit=pending; `--shuffle-seed` option in ci/run_tests.py (+macro) and `.github/workflows/nightly.yml`; policy tests; docs/ci.md.

## Log
L1. User: "aplica tus recomendaciones de CI, cuales serian los pasos" → plan proposed; user: "si" (plan), then "ok vamos con A :)" (push/PR first, hardening after merge), then "tu" (merge PR #12). PR #12 merged as 5e0e1ca with two green hosted runs (41060766708, 41061618550).

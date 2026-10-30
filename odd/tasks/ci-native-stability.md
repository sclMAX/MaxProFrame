# Restore green native CI and replace RC with pinned weekly
Branch: `fix/ci-native-stability` from `d850fcc`. Last green hosted run: `5770aa8`.
Risk: item 5 (CI matrix/environment), item 6 for the flaky native crash (proof is statistical).

## Specs
S1. User: "si debemos resolver eso para que CI cumpla su funcion" — native FreeCAD jobs must stop crashing (SIGSEGV on stable, exit 1 on rc since `8492157`).
S2. User: "ademas ajustar para usar freecad estable y la ultima weekly (en lugar de RC)". Decision (ask_user_choice): "Fijada e informativa (recomendado)" — "weekly-2026.10.28 con sha256 fijo; si falla se ve pero no pone la CI en rojo. Stable sigue bloqueante."
S3. Keep accepted CI policy S1 of `odd/tasks/ci-policy.md`: "CI reproducible: versión exacta fijada, no `latest`."

## Tasks
T1 [S1] route=inline; status=in_progress; commit=pending; root cause: `_clean_unreferenced_session_sources` read native `InList` of a source sketch right after a preview `removeObject`; gdb shows SIGSEGV in `App::DocumentObjectPy::getInList()`. Fix: derive live referrers from `doc.Objects` OutList. Baseline: single test crashed 5/10 locally.
T2 [S2,S3] route=inline; status=pending; commit=pending; replace `rc` target with pinned `weekly` (URL+sha256, version/Python asserted by macro), `continue-on-error` only for weekly; update runner choices, macro, policy tests, docs/ci.md.
T3 [S1,S2] route=inline; status=pending; commit=none; full local suite on stable and weekly; hosted CI result after user-authorized push.

## Log
L1. User: "puedes analizar el estado de CI de los ultimos commit que hicimos y darme un detalle" → 4 red commits on main; native suites crash in `test_alignment_create_clicks_apply_cancel_and_source_changes`.
L2. User: "si debemos resolver eso para que CI cumpla su funcion ademas ajustar para usar freecad estable y la ultima weekly (en lugar de RC) que opinas?"
L3. Evidence: crash is flaky (~50% single test), independent of test order; gdb backtrace frame #1 `App::DocumentObjectPy::getInList()` via `getattr(...,"InList")` from a `QComboBox::currentIndexChanged` slot.

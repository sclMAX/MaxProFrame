# Library translation consistency
Keep library UI language consistent without rewriting stored catalog content. Branch: `fix/library-translation-consistency`.
Delivery: ask-on-risk; forecast ~350 authored lines excluding generated QM. Runner: native FreeCAD RC offscreen with isolated profiles; focused cases first.

## Specs
- S1 — User: "revisa toda la ventana de la biblioteca hay inconsistencias, algunas partes estan traducidas y otras no". Audit and correct the library UI, including headers, family badges, counters, empty states, statuses, menus, tooltips and owned dialogs; reproduce the mixed-language behavior with native checks before fixing it.
- S2 — Accepted proposal: "Recomiendo corregir primero la carga y el ciclo de vida del traductor, y después completar los mensajes restantes." User authorization: "si". Respect the FreeCAD-selected language; maintain translations across dialog lifecycle and dynamic updates; retain English behavior when English is selected.
- S3 — Accepted constraint: "Los nombres de bibliotecas, códigos, descripciones y normas guardadas deben conservarse." Preserve those values and canonical keys; translate presentation rather than persisted content.
- S4 — Accepted proposal: "Confirmaciones que muestran claves inglesas de familias." and "Errores internos que llegan al usuario directamente en inglés." Correct library-owned user-facing messages and dynamic family presentation. Preserve backend contracts and external diagnostic details rather than changing geometry, archive or persistence behavior.

## Tasks
- T1 [S1-S3] delegated; done; native RED reproduced mixed-language window; GREEN 6 runtime + 14 existing manager tests, zero skips; work-unit commit pending. Risk: item 3 (translator state is shared with other UI); independent verification remains T3.
- T2 [S1,S3-S4] delegated after T1; in_progress; complete remaining library-owned presentation strings and Spanish TS/QM coverage with tests/docs; commit pending.
- T3 [S1-S4] parent + independent verifier; pending; verify native interaction and English preservation, compare shared translation behavior to base `19e5eed`, record known full-suite limitations and close; commit pending.

## Log
- L1 User request verbatim: "/tmp/gpZPECBt/pi-clipboard-a79bc29a-be8e-478f-9e27-23ef258f9f23.png revisa toda la ventana de la biblioteca hay inconsistencias, algunas partes estan traducidas y otras no"
- L2 User authorization verbatim: "si" (to the correction proposal quoted in Specs).
- L3 Audit: screenshot strings already exist in Spanish TS and current source uses translate(). Mixed static/dynamic language cause not yet reproduced. Loader uses system QLocale, marks installed before load succeeds, and removes a class-shared translator on dialog close. These are hypotheses for reproduction, not established screenshot causality.
- L4 Preserve unrelated user changes: `README.md` modified, `.github/FUNDING.yml` untracked. No edits, staging or publication of those paths.
- L5 Existing full native RC suite has incomplete proof: 180s timeout in family-variant-picker dirty-dialog cleanup and one FAIL in create-profile confirmation GUI. Do not silently retry the unchanged full suite, weaken production prompts, or claim these are caused by this feature. Native focused runner exists at `.git/sketch-capture/run.FCMacro`; extracted runtime is in-project.
- L6 Parent selected one sequential writer because runtime backstop fired and both tasks share translation state/source; no parallel edit surfaces. High-risk T1 receives an isolated work-unit commit and one independent verifier. No push or PR requested for this feature.
- L7 T1 initial evidence: native RED exit 1 reproduced `Square Hollow` badge versus `Tubo Cuadrado Hueco` list after second-manager close; native GREEN exit 0, six cases, zero skips. Native FreeCAD catalog discovery replaces OS-local QTranslator ownership. Parent found existing `uninstall_translations()` caller and old locale-only regression; one bounded compatibility correction is in progress before committing T1. Failed-first-load proof and byte-level persistence are reserved for final verification rather than claimed complete.
- L8 T1 compatibility correction: retained legacy cleanup as a no-op; existing manager module RED 1 failure/14 tests, then GREEN 14/14; runtime regressions GREEN 6/6. English and Spanish public assertions preserved. Source-path diff check passes; unrelated user file `ci/tests/test_policy.py` now has changes including an EOF whitespace warning, which remains untouched.

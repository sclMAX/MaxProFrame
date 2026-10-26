# Interactive alignment anchors
Implement visual section alignment in the isolated branch `feat/interactive-alignment-anchors` (base `2cac86c`).
Delivery: auto-chain / feature-branch-chain, forecast 600–900 authored diff lines; slices: custom anchor correction, then widget integration. Runner: `python3 ci/run_tests.py` with locally verified FreeCAD runtime.

## Specs
S1. User: "ok vamos con la feature". Confirmed choice: "Widget 2D en el panel (recomendado)" — "Sección del perfil con los nueve anclajes clicables, sincronizados con rotación y espejos." Check: click all nine local anchors, synchronize rotation/mirrors and existing controls, preserve Apply/OK/Cancel and Edit behavior.
S2. User confirmed: "Sí, corregir y luego integrar el widget (recomendado)" — "Primero reproducir y corregir el anclaje custom con pruebas; después integrar los nueve puntos para que dibujo y colocación coincidan." Check: offset custom section and all nine anchor positions, mirror combinations, preserve holes and source geometry.
S3. User: "crea un nuevo worktree para implemetar la feature". Work only in this worktree; do not transfer dirty parent changes or publish.

## Tasks
T1 | S2,S3 | delegated, context-backstop | done | RED reported; final preview GREEN 4 tests, custom sections 12 tests and standard anchors 2 tests passed. Differential: 72 standard unchanged + 72 custom only authorized XY shifts. Replacement full suite exit 0, 579 tests. Commit: this custom-anchor work unit; hash recorded in next task transition.
T2 | S1,S3 | delegated, context-backstop | pending | Implement faithful 2D section widget and shared panel integration with tests and user docs; commit pending.
T3 | S1,S2,S3 | parent checks / independent verifier if named high risk | pending | Functional GUI checks, suite, applicable differential checks, native risk assessment/review per user switch, and reviewable work-unit commits.

## Log
L8. Parent job-1 completed exit 0, 579 tests, 145 seconds. git diff --check exit 0. RDD switch on; initial assess unassessable because the new tracker is untracked. Normalize as a work-unit commit including tracker, then assess committed range. Risk: none for this correction: custom anchor behavior change explicitly authorized, differential evidence reports shared standard paths unchanged; no stored-data migration or external contract format change.
L7. Parent reviewed production and probe diff. Worker reports all focused checks exit 0 and 144-case differential comparison exit 0. Prior full-suite evidence irrecoverable, original RED artifact also missing (reported evidence only). User chose "Sí, ejecutar la suite completa (recomendado)" to replace missing full-suite proof. Parent launched job-1 with --timeout 420; reports retained at .git/interactive-anchor-checks/t1-suite in original repository administrative directory. No automatic retry authorized.
L6. First T1 handoff is partial: preview RED exit 1, corrected focused GREEN exit 0 (3 tests), standard anchor exit 0 (2 tests), custom-section module exit 1 (four point-probe failures). Worker continued as task mvps4csp-3-iycx to resolve causality/regressions, collect its existing suite completion and provide differential plus rotation/attachment evidence. T1 not accepted; T2 remains pending. No commits.
L1. Original request: "Analicemos la posibilidad de que los puntos de alineamiento de dibujen en el perfil y sean clicables algo asi /tmp/gpoU8V78/pi-clipboard-1e09c22f-a572-4bac-98a6-ca0274314985.png (soy malo dibujando XD) analiza y veamos pros y contras".
L2. Implementation authorization: "ok vamos con la feature"; UI selection recorded verbatim in S1. The 3D proposal remains out of scope.
L3. Explorer mapped the assigned base, and parent spot-checked profile.py: custom_section_face bypasses bbox normalization and anchor translation while standard extrusions apply it. No executable reproduction yet. User authorized the correction as S2.
L5. Delivery choice: "Cadena sobre rama de feature (recomendado)". Prepare dependent reviewable units; no push or PR authorization.
L4. Preserve anchor IDs and existing helpers get_anchor/set_anchor, initialization guards, snapshot acceptance and explicit Apply semantics. Nine anchors are bbox-based, not center of mass or arbitrary mesh vertices. Avoid rebuilding catalog documents in paint/click and avoid duplicating family geometry logic. Original dirty worktree remains untouched. Geometric correction and visual integration are dependent units, not parallel writers.

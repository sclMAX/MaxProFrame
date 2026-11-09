# Populate IDs follow-ups
Remaining Populate IDs issues found in the review of PR #110, plus the advisory findings of the PR #111 review. Branch: `feat/populate-ids-followups`; base: `d1b638e` (worktree `../MaxProFrame-ids-followups`).
Delivery: work-unit commits on the feature branch; push, PR and merge are the user's decision. Tests: native FreeCAD 1.1.4 (`ci/run_tests.py --freecad-bin /tmp/mpf-fc114/squashfs-root/AppRun`).

## Specs

- **S1 — Selection read at open (finding 4).** Finding as reported: "La selección se lee al apretar OK, no al abrir. Si mientras el panel está abierto hacés clic en la vista 3D, se numera otra cosa. Y si la nueva selección no es válida, se cancela la transacción pero el panel sigue abierto; un OK posterior queda sin deshacer." OK numbers the profiles and links selected when the panel opened; clicks while it is open change nothing; OK never aborts the transaction and leaves the panel open.
- **S2 — Reset IDs on trims and cutouts (finding 5).** Finding as reported: "Reset IDs sobre un corte probablemente no se mantiene. Borra el ID del corte pero no el del perfil de origen, al revés de lo que hace Asignar IDs. Hay que verificarlo." Verify first; if confirmed, Reset IDs clears the ID of a trim or cutout so that it stays cleared after a recompute and in the BOM, as Populate IDs sets it.
- **S3 — Count of identical pieces (finding 6).** Question: "Con 'Agregar la cantidad de piezas al ID', ¿qué cantidad debe mostrar?" Answer: "Todas las del documento (recomendado)" — "Cuenta todas las piezas iguales que quedan con ese ID, estén o no en la selección." The " xN" suffix counts every piece of the document left with that ID, selected or not; pieces outside the selection that already carry that ID get the same count.
- **S4 — Links outside the selection (finding 7).** Finding as reported: "Se modifican links fuera de la selección. Se le agrega PID a todos los links del documento, no solo a los seleccionados." Populate IDs adds the PID property only to the selected links; other links are read, never written.
- **S5 — Identical pieces = same final shape.** Question: "¿Cuándo dos piezas con vaciados (agujeros, rebajes, Notch) cuentan como iguales para compartir ID?" Answer: "Misma forma final (recomendado)" — "Se compara el sólido terminado de cada pieza, sin importar dónde está en el armado: cubre agujeros, su posición, rebajes y barras dadas vuelta." Two profiles share an ID with "Mismo ID para piezas idénticas" only when their finished solids are the same shape regardless of placement (a bar turned end for end is the same piece; the same bar with a hole elsewhere is not), besides the same material, family and size. Links keep their current rule.
- **S6 — Prefixes.** Question: "Los campos 'Prefijo de perfiles' y 'Prefijo de enlaces' hoy están deshabilitados y no hacen nada. ¿Qué hacemos?" Answer: "Implementarlos" — "Ej.: prefijo 'P-' da P-1, P-2; 'L-' da L-A. El prefijo se respeta al buscar huecos y continuar la numeración." The fields are enabled, remembered, translated and documented; gaps and "continue" are computed among the IDs carrying that prefix.
- **S7 — Nightly review advisories.** Findings R3-budget-margin / R4-job-budget-margin (`.github/workflows/nightly.yml:24-26`: 300 minutes barely covers the 294-minute worst case plus setup) and R3-unvalidated-shards (`nightly.yml:105`: timeout and shards read from `ci/targets.json` without validation). Give the job budget a real margin within GitHub's 360-minute limit and fail clearly when timeout or shards are not positive integers.

## Tasks

- **T1 [S1, S4] delegated, done.** Panel stores the selection at open; OK always numbers it and commits one undo step; PID/version properties only on selected links. RED observed for each rule. Commit: see `fix(populate-ids): selection at open, reset of trims`.
- **T2 [S2] delegated, done.** Bug confirmed (ID back after recompute: `'42' != ''`); Reset IDs clears it through `set_profile_pid` on the source profile. Commit: same as T1.
- **T3 [S5, S3] pending.** Shape-based grouping and document-wide count. Risk: item 3 (changes which pieces share an ID in existing documents — requested). Commit: —
- **T4 [S6] pending.** Prefixes. Commit: —
- **T5 [S7] inline, done.** Nightly budget 300 → 330 minutes (worst case 294 + setup); the read step refuses a stable timeout or shards that is not a positive integer. RED observed (6 failures), ci/tests green. Risk: item 5 (CI workflow). Commit: see git log (ci(nightly): budget margin).

## Log

### L1 — Original request (verbatim)
vamos con los pendientes

### L2 — Pending list the request refers to (assistant, previous turn)
"Asignar IDs: quedan las fallas 4 a 7, los campos de prefijo y la comparación de piezas iguales (vaciados distintos, ángulos invertidos). Antes de tocar la comparación, tenemos que definir cuándo dos vaciados cuentan como iguales." / "Revisión del #111: dejó tres avisos que no bloqueaban: el margen justo del tiempo máximo del job y que los valores de ci/targets.json se leen sin validar."

### L3 — Decisions (user answers, verbatim)
1. "Misma forma final (recomendado)". 2. "Implementarlos". 3. "Todas las del documento (recomendado)".

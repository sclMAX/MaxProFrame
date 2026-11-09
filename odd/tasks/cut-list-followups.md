# Cut List follow-ups
Pending items after v1.11.0 (cut list faces, Reset IDs confirmation): untested angle ordering, non-blocking review advisories, numbers that follow the language, and identical stock bars shown once. Branch: `feat/cut-list-followups`; base: `36fd0bd` (v1.11.0).
Delivery: work-unit commits on the feature branch; push, PR and merge are the user's decision. Tests: native FreeCAD 1.1.4 (`python3 ci/run_tests.py --freecad-bin .freecad-test/demo-video/squashfs-root/AppRun --reports $(mktemp -d) --target stable --test <module>`).

## Specs

- **S1 — Angle order is pinned by tests.** Pending from the reviews of PR #119: "Tests del orden de ángulos para las marcas `@`, `P` y `?`, y para el empate entre ángulos iguales." `larger_angle_first` (`freecad/maxproframe/create_bom.py`) is tested through `make_cut_list`: a fallback angle with a mark ("@ 45.0" vs "4.0"), an angle without number ("@ P", "?") goes last, and equal leading numbers keep string order. Readability advisory R2-sort-key-sentinel (create_bom.py:279): the value for "no number" is a named constant, and the docstring says what it does.
- **S2 — Review advisories.** "Los avisos menores que dejaron las reviews." Check each location and fix only what is a real defect or a cheap clarity gain; report the ones left as they are, with the reason. Locations: Reset IDs review — `populate_ids_tool.py` Reset IDs report block (R2-001 WARNING, R2-002..004 suggestions) and "R3-link-count-unproved" (no test proves the count and report when links are selected); PR #119 reviews — `cut_ends.py:76` (R2-axis-tolerance-reuse), `cut_ends.py:116-130` (R3-001 fallback, R3-006), `tests/test_cut_ends.py:34-35` (R3-002), `create_bom.py` BOM headers (R3-003) and grouping (R3-007), `tests/test_cut_list.py:168` (R2-hardcoded-legend-row).
- **S3 — Numbers follow the language.** Question: "En la lista de cortes los largos salen con coma (724,60, formato de la planilla) y el título de cada barra con punto (used = 1442.0). ¿Qué formato querés?" Answer: "Según el idioma (recomendado)" — "Con FreeCAD en español todo con coma (1442,0 y 724,6); en inglés todo con punto." Every number the BOM and Cut List write as text (stock bar title used/left, and any other number written inside a text) uses the decimal separator of the FreeCAD language; numeric cells stay numbers.
- **S4 — Identical bars shown once.** Question: "Cuando dos o más barras tienen exactamente el mismo plan de cortes, ¿las mostramos una sola vez?" Answer: "Sí, una vez con \"×N barras\"" — "Un solo bloque con la cantidad de barras; la lista queda más corta y se corta en tanda." Bars of one material whose rows (ID, length, angles, ends, quantity) are identical take one block; its title says how many bars ("… ×2" / translated "×N barras"), and the Stock column lists the bar indexes it stands for. Stock statistics keep counting every bar.

Decided, not to do: "Dejarlos separados" — the same profile from different libraries stays in separate stocks (the Material field holds the library).

## Tasks

- **T1 [S1] delegated, done.** Commit: see git log on feat/cut-list-followups. TestAngleOrder (test_cut_list.py) pins larger_angle_first through make_cut_list: marked angle ("@ 45.0" vs "4.0"), no number last ("@ P", "?"), ties in string order; sentinel `NO_NUMBER = math.inf` with docstring. Tests passed at once (characterization); a temporary mutation (no-number first, no string tie-break) made 2 of the 3 fail, restored.
- **T2 [S2] delegated, done.** Commit: see git log on feat/cut-list-followups. Fixed: Reset IDs crashed on a selected link without PID inside an open transaction (RED AttributeError; links count/report test added), status timeout named; cut_ends PLANE_TOLERANCE split from AXIS_TOLERANCE and fallback docstring; rounded-corner tube test; BOM grouped IDs in first-seen order (RED '3, 4, 5, 7, 8, 6, 1, 2'); BOM Parts row without ID (RED KeyError 'ID'); legend row found by mark instead of B15. Left: R3-006 (no defect found at the location).
- **T3 [S3] delegated, done.** Commit: see git log on feat/cut-list-followups. decimal_text/localized in create_bom.py: stock title used/left and angle texts take QLocale().decimalPoint(); numeric cells unchanged. RED: Spanish title/angles had a point; GREEN Spanish comma and English point.
- **T4 [S4] delegated, done.** Commit: see git log on feat/cut-list-followups. identical_bars groups bars with the same rows (any order), title "×N bars", Stock "0, 2"; statistics unchanged. RED: two identical bars printed as two blocks.
- **T5 [S1-S4] delegated, done.** Commit: see git log on feat/cut-list-followups. Tutorial BOM Tool section, CHANGELOG `* Unreleased`, Spanish "{} / used = {}, left = {}", "×{} barras", legend "45,0 <80" in both .ts (identical), .qm compiled.

## Log

### L1 — Original request (verbatim)
encaremos los pendientes

### L2 — Pending list it refers to (assistant, previous turn)
"Tests del orden de ángulos para las marcas `@`, `P` y `?`, y para el empate entre ángulos iguales." / "Los avisos menores que dejaron las reviews." / "Lo que dejamos fuera de esta feature: unir el mismo perfil de bibliotecas distintas en un solo stock, el formato de los números (coma o punto) y mostrar \"×2 barras\" cuando dos barras tienen el mismo plan de cortes."

### L3 — User answers
1. Stock across libraries — "Dejarlos separados". 2. Numbers — "Según el idioma (recomendado)". 3. Identical bars — "Sí, una vez con \"×N barras\"".

### L4 — Worker decisions accepted by the parent
S3: angle texts in the BOM and Cut List get the comma too in Spanish ("45,0 <80"), following "todo con coma". S4: bars are identical when they hold the same rows in any order; the printed rows are the first bar's. S2 extra fixes: Reset IDs crashed on a selected link without PID (assignment does not reach the linked object); BOM Parts row KeyError for a Part without ID; grouped BOM IDs kept in arrival order. Checked and dropped: reading `link.PID` in traverse_assembly does not fail, an App::Link reads the PID of its linked object.

### L5 — Native review of PR #122 (approved, advisories)
Fixed: R3-link-pid-guard-reads-through-link — `hasattr(link, "PID")` reads the PID of the linked profile, so Reset IDs on a never-numbered link to a profile asked to clear the profile's ID. `own_pid` reads only the link's own property (RED: asked to clear instead of "no IDs"). Kept: R3-locale-source-not-language — `QLocale()` is the number format FreeCAD itself uses for its fields (the Create BOM panel shows Kerf "1,00"), so the sheets match the UI; tests pin the language and its locale through `use_language`.

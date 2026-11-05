Cutout pattern: a checkable "Pattern" group in the Cutout / Hole panel that repeats the sketch in one row along the profile, with a count and a pitch on each side of the sketch.
Branch: feat/cutout-pattern. One PR.

## Specs

- S1. One row along the profile, a count per side (L2): "una fila a lo largo del perfil, pero con cantidad por lado <- 1@50mm (croquis) 2@30mm". The sketch is the piece at the origin and is always cut; backward and forward each have a count and a pitch; forward is toward the end of the profile path (as Drill Hole along). The example gives 4 cutouts: at -50, 0 (the sketch), +30, +60 mm.
- S2. Title shows only the total (L3): "en el titulo mostremos solo la cantidad de calados \"Patrón: 4 calados\"". Unchecked: "Pattern" (Spanish *Patrón*); checked: "Pattern: 4 cutouts" / "Pattern: 1 cutout" (Spanish "Patrón: 4 calados" / "Patrón: 1 calado").
- S3. Group and compatibility (accepted proposal, L1/L2): a checkable group, unchecked for a new cutout; unchecked, the sketch alone is cut and the fields keep their values. Cutouts saved before open unchanged. Drill holes keep their own pattern properties.
- S4. Expressions (accepted proposal, L1): every new count and pitch field takes Fx, like the depth field.
- S5. Feedback (L1, L7): a warning, not blocking OK, when a cutout reaches past the face; no overlap warning (L7). Too many cutouts (over 1000) fail with a message.

## Tasks

- T1 [x] S1, S3, S5 (limit): model — pattern properties, copies along the path in execute, shared axis_positions. Route: inline, test-first. Commit: feat(cutout) single commit on feat/cutout-pattern.
- T2 [x] S2, S3, S4, S5: panel — Pattern group, title, Fx, warnings. Route: inline, test-first. Commit: feat(cutout) single commit on feat/cutout-pattern.
- T3 [x] S1-S5: Spanish (.ts both, .qm), tutorial, README, CHANGELOG Unreleased. Route: inline. Commit: feat(cutout) single commit on feat/cutout-pattern.

## Log

- L1. Parent proposal (analysis turn): reuse the Drill Hole pattern; axes from the face and the profile path; the sketch is the origin piece; warn without blocking OK when a copy falls off the face or overlaps. Decision asked: grid like Drill Hole, or one row along.
- L2. User: "una fila a lo largo del perfil, pero con cantidad por lado <- 1@50mm (croquis) 2@30mm -> entiende la idea?" Parent restated: 4 cutouts, sketch always cut (no "at the point" option), per side count and pitch, 0 by default, group unchecked.
- L3. User: "Si, pero en el titulo mostremos solo la cantidad de calados \"Patrón: 4 calados\""
- L4. Evidence (parent, inline, test-first): RED test_cutout_pattern 5 errors (no properties), test_cutout_pattern_panel 9 errors (no group). GREEN 6 + 9 OK. Overlap length first measured by discretize (9.98 mm for a 10 mm circle), then exact via optimalBoundingBox on the turned shape. fit_width and length_text moved to expression_fields, axis_positions to extruded_cutout (drill_hole imports it); DrillHole.add_pattern_properties adds none of the cutout's. Full suite 1190 OK on stable and on weekly (--target weekly).
- L5. Native review (readability + reliability, refuted): unchecking was ignored while an expression drove a count. Fix: unchecking removes count expressions (Cancel restores them); RED/GREEN test_unchecking_removes_an_expression_on_a_count_and_cancel_brings_it_back; panel 10 OK, depth panel 14 OK.
- L6. User: "tenemos el mismo problema que ya solucionamos en drill al cambiar la separacion se apilan los cortes" (Recursive calling of recompute). Fix: the depth panel never recomputes inside its own recompute; a change meanwhile recomputes once more, OK/Cancel wait (RED/GREEN TestCutoutPatternPreview, 2 tests). Cutout tests 62 OK, no Recursive message.
- L7. User: "saca el aviso del todo en calados es complicar la implementacion sin sentido el usuario esta viendo en pantalla como quedan los calados y quiazas quiere que se superpongan". Overlap warning, its string (both .ts, .qm rebuilt) and docs removed; RED/GREEN test_overlapping_cutouts_give_no_warning and the Spanish test; pattern panel 12 OK, pattern 6, depth panel 14, drill panel 83, translations 2.

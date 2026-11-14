# Pending follow-ups: panel language change, stepped-corner edge cases, Folded Bar polish
Follow-ups left open by stepped-corners (PRs #152-#154) and folded-bar-tools (PR #149). Branch fix/pending-followups.
Delivery: commits per task; push, PR and merge stay the user's decisions. Slices (~400 lines): slice 1 = T1-T3
(3b8697e..1fe2e3e, 528 lines), slice 2 = T4 (own commit, risk item 1), slice 3 = T5 + T6.

## Specs
- S1 Panels keep their texts on a language change (L1 item 1): "Revisar los demás paneles que usan `loadUi`.
  Probablemente se les borra el texto igual al cambiar el idioma." -> every task panel loaded from a .ui file
  (End Miter, Cutout, Populate IDs, BOM, Create/Edit Profile) loads it like Extend Cut since 55d6beb
  (`Gui.UiLoader` + `setLanguageChangeEnabled(False)`, one shared helper), so a Qt LanguageChange no longer resets
  texts set at runtime (window title, hints, face/target labels, family-dependent labels, translated texts).
- S2 Tests deliver the language change (L1 item 2): "llamar a `deliver_language_change` justo después de
  `use_language` en los fixtures." -> after `use_language` no LanguageChange stays queued for a later, unrelated
  event loop; the full native suite stays green.
- S3 Stepped corners edge cases (L1 item 3):
  - S3a "la banda exterior podría rellenar parte de la muesca de la esquina abierta" + L2 answer "Achicarla con un
    segundo escalón" -> at a convex open corner ≠ 90° with `Stepped`, the other outer band grows into the notch with a
    second step, so the weld groove is smaller than today; still no material past either tube's outer face plane,
    every cut is a tube cross-section or a plane containing w, the bar folds into one sound solid with no overlap, and
    the 90° open corner keeps its exact geometry.
  - S3b "los cortes de punta muy cerca de una esquina abierta en ángulo agudo se pierden" + L2 answer "Conservarlo
    siempre" -> at a stepped open corner only the End Miter of the two ends is replaced; the user's holes, cutouts and
    notches on those end tubes stay, even inside the joint zone and even when they touch the joint.
  - S3c "no hay protección para tubos de punta muy cortos" -> an end tube so short that the stepped open-corner joint
    reaches its folded corner is refused with a message naming that tube, in the style of the other "too short"
    unfold errors; the panel shows it and disables OK like the other unfold errors.
- S4 Older pending items (L1 item 6):
  - S4a "el texto del aviso de Cutout" -> the Cutout prompt, the "Select a planar face ..." refusal and the command
    tooltip mention a folded bar, like Drill Hole ("... a cutout or a folded bar").
  - S4b "\"0.3\" contra \"0,3\" en la lista de esquinas" -> lengths written by `length_text` (Folded Bar corner list,
    tube label, Profile Pattern, Drill Hole messages) use the current locale's decimal separator, matching the fields.
  - S4c "deshacer después de un recompute externo hace perder un tubo" + L2 answer "Guardar los tubos base" -> the
    Folded Bar stores its base tubes; when a segment's piece is removed (undo, delete), that segment falls back to its
    base tube instead of leaving the bar. Bars saved by older versions get their base tubes on restore and recompute
    to the same shape.
  - S4d "en End Miter/Extend Cut queda preseleccionada la barra entera" + L2 answer "Tubos de los dos extremos libres"
    -> a whole Folded Bar selected from the tree (before the command or while the panel is open) adds the tubes at
    the bar's two free ends as profiles in End Miter and Extend Cut; a closed bar (no free ends) shows a clear message.
    An Extend Cut target stays refused, with a message asking for a face instead of the bend message.
- S5 Docs and translations: CHANGELOG, tutorial where behavior is described, Spanish .ts entries and .qm for every new or
  changed text.

## Tasks
- T1 [S1] shared .ui loader helper; End Miter, Cutout, Populate IDs, BOM, Profiles panels use it; tests that each
  panel keeps runtime texts after use_language + deliver_language_change. route=inline; commit=3b8697e [x]
- T2 [S2] `use_language` delivers the LanguageChange itself; full native suite. route=inline; commit=464eee7 [x]
- T3 [S3b, S3c, S3a] unfolded_geometry open stepped joint: keep user cuts, short end tube guard, second step into the
  groove. route=gentle-ai-worker (geometry); commit=1fe2e3e [x]
- T4 [S4c] Folded Bar base tubes + restore of older bars. Risk item 1 (saved document format). route=gentle-ai-worker;
  verify=gentle-ai-verify; commit=fd18329 [x]
- T5 [S4a, S4b, S4d] Cutout texts, locale-aware length_text, whole bar in End Miter/Extend Cut. route=gentle-ai-worker;
  commit=a46f48e [x]
- T6 [S5] CHANGELOG, tutorial, es .ts/.qm, full native suite (pinned stable). route=inline; commit=6257d18 [x]

## Log
- L1 User (2026-11-14), on the list of pending items: "ataquemos 1, 2, 3 y 6". Items: "1. Revisar los demás paneles
  que usan `loadUi`. Probablemente se les borra el texto igual al cambiar el idioma." "2. Tests: llamar a
  `deliver_language_change` justo después de `use_language` en los fixtures." "3. Uniones escalonadas, casos borde:
  la banda exterior podría rellenar parte de la muesca de la esquina abierta; los cortes de punta muy cerca de una
  esquina abierta en ángulo agudo se pierden; no hay protección para tubos de punta muy cortos." "6. Pendientes de
  antes: el texto del aviso de Cutout; \"0.3\" contra \"0,3\" en la lista de esquinas; deshacer después de un
  recompute externo hace perder un tubo; en End Miter/Extend Cut queda preseleccionada la barra entera."
- L2 Decisions asked: groove -> "Achicarla con un segundo escalón"; user cuts in the joint zone -> "Conservarlo siempre
  (Recomendado)"; undo -> "Guardar los tubos base (Recomendado)"; whole bar -> "Tubos de los dos extremos libres
  (Recomendado)". Taken without asking: S4a rewords the shared "Select a planar face ..." string (Drill Hole accepts
  folded bars too); S4b localizes `length_text` everywhere.
- L3 Exploration (3 explorers): .ui loads at create_end_miter_tool.py:188, create_extruded_cutout_tool.py:231,
  populate_ids_tool.py:78, create_bom_tool.py:41, create_profiles_tool.py:76-85; template test
  tests/test_extend_cut_panel.py:820-857. Open-joint code: unfolded_geometry.py `_OpenStep` (~661-792),
  `_segment_changes` :950 (clips the whole tip difference by the zone -> S3b), no zone-vs-corner check (S3c).
  `length_text` expression_fields.py:197. bar_tips folded_bar.py:96, follow_new_pieces :177. End Miter `_preselected`
  :62, Extend Cut `_from_bar` :461.
- L5 T1/T2 evidence: test_panel_language_change RED 5/5 (forms back to English, Populate IDs titled "Diálogo"), GREEN
  5/5 after ui_forms.load_form (3b8697e). Full native suite on 464eee7 (pinned stable 1.1.4, 4 shards, clean worktree):
  506+506+506+505 = 2023 tests OK.
- L4 T3 (worker, committed 1fe2e3e). S3b: `_segment_changes` compares each end's stack piece by piece (`_stack_changes`); only
  the trims against the other end tube (the End Miter at the open corner) and the base reaching the bar end are clipped
  by the end's own zone, every other cut stays whole; zones apply to their end segment only. S3c:
  `_check_open_lengths` refuses "{} is too short for the stepped joint of the open corner." when the joint's reach into
  an end tube (`_OpenStep.reaches`) meets what its folded corner cuts back into it (`_Bend.reach`: V, band, key, at least
  the bend start); at 90° the threshold is exact: 52 mm path refused, 52.01 accepted. S3a decision (second step, A =
  last tube, s2 = t: the outer wall alone, a step below t would cut a wall partly through): A's outer wall
  (x in [a_o, a], y in [0, t]) grows into the notch while it stays clear of B's outer band grown g/2 (x' >= b - g/2,
  y' <= s + g/2); a = max(-(s + g/2 - min(0, t cos θ)) / sin θ, and below 90° -(g/2 + t sin θ) / cos θ); kept only when
  a > a_o (so 90° is unchanged) and s > t. Cuts: step face y = t (contains w), end x = a (A cross-section). Measured,
  s = 4, t = 2, g = 0: opening along the last tube's outer face 6.93 -> 5.77 mm (120°), 4.62 -> 3.46 mm (60°); empty
  volume of the outer skin (both outer walls, 20 mm around the sharp, inside both face planes) 563.5 -> 448.0 mm³
  (120°), 341.8 -> 226.3 mm³ (60°). Pinned 1.1.4: unfolded 66 OK, folded 19 OK, folded_bar 49 OK, panel 90 OK.
- L6 T4 (worker): folded_bar.py hidden LinkList `BaseTubes`; base_tube/bar_tubes/set_segments (single writer of Segments
  and BaseTubes); bar_chain from bar_tips; onDocumentRestored fills BaseTubes from the segments' stacks (purgeTouched
  when untouched). Old drop test split: removed piece -> falls back, removed tube -> drops. RED base_tubes 2F+4E, tools
  1F+1E; GREEN base_tubes 6, tools 14; folded_bar, panel, end_miter/extend_cut/cutout/drill_hole/profile_pattern
  folded-bar suites green. New string (App::Property): "Tube each segment of the bar is made from, in its order".
- L7 T5 (worker): S4a strings old -> new: "Select a planar face of a profile, a trimmed profile or a cutout." -> "... a
  cutout or a folded bar." (Cutout + Drill Hole); Cutout prompt -> the Drill Hole string "Click a planar face of a
  profile, a trimmed profile, a cutout or a folded bar."; Cutout tooltip "..., a cutout or a folded bar, then OK: ...".
  S4b length_text follows QLocale. S4d folded_bar_ends.py; new strings "Click a face of the folded bar." and "{} is
  closed: click its tubes to add them.". Notch (subclass of Extend Cut) inherits S4d: kept, consistent with Extend Cut.
  Pending T6 es: test_cutout_flow 1 and test_toolbar_translations 1 fail until the .ts/.qm entries exist.
  T3 new string (MaxProFrame context): "{} is too short for the stepped joint of the open corner."

- L8 T4 verify (gentle-ai-verify): B1 edit-panel Cancel while the bar waits to fall back (Std_Undo does not recompute)
  rewrote BaseTubes and lost the tube; B2 OK in the same state dropped it (panel listed edited.Segments). Restore of
  older files, release_piece, closed frame, cycles, all-pieces-removed: pass. B3 asked: a hand edit of Segments to a
  subset in order was silently restored. User: "Segments solo lectura (Recomendado)" -> Segments read-only in the
  property editor; tubes are added and removed with the bar panel.
- L9 T6 (worker): es entries for the 6 new strings in frameforge_es.ts/maxproframe_es.ts; 16 es .qm rebuilt by
  compile_translations.py (aliases included, as 207c696); 6 unfinished entries in maxproframe_ru.ts and
  FOLDED_MITER_TEXTS; tutorial (Create the Folded Bar, open corner, Tools on a Folded Bar, decimal separator) and
  CHANGELOG. Green: test_cutout_flow 19, test_toolbar_translations 4, test_folded_bar_translations 9,
  test_russian_translation 6, test_end_miter_translations 4, test_compile_translations 3, test_dxf_section_dialog 3.
- L10 T4 fixes (worker): panel lists bar_tips(edited); Cancel restores Segments/BaseTubes as stored (snapshot holds
  BaseTubes and Tips); Segments read-only (new bars and on restore). RED base_tubes 3F (B1 x2: BaseTubes [top, left];
  B2: 2 tubes listed), L8 checks 3F ('ReadOnly' not found); GREEN base_tubes 12, folded_bar_tools 14,
  folded_bar_panel 90, folded_bar 49, end_miter_folded_bar 13, extend_cut_folded_bar 16, cutout_folded_bar 13.
  Re-verify launched.
- L11 T4 re-verify (gentle-ai-verify): B1/B2 fixed, no blockers; probes P1-P9 pass vs baseline 464eee7; undo of the
  extra "Edit Folded Bar" step after OK while falling back is safe (pinned by test_undo_of_the_ok_step_while_falling_
  back_keeps_the_tube, base_tubes 13 OK). Committed fd18329 (slice 2).
- L12 User: "si toda esta ok, prs push y merge". Native review assess on 1fe2e3e..HEAD: risk high (item 1 escalated),
  reviewDue false (under_budget); independent verify of T4 already done (L8, L11).
- L13 Final full suite on 6257d18 (pinned stable 1.1.4, clean worktree, 4 shards): 513 x 4 = 2052 tests OK. Black/isort
  clean on the 30 changed .py files (the repo-wide check lists 23 pre-existing files outside this change).

# Folded bar tools: every click-to-add tool works on a Folded Bar
A Folded Bar (FoldedBar, folded_bar.py) hides its tubes and shows one fused solid, so End Miter, Drill Hole, Cutout,
Extend Cut / Notch and Profile Pattern refuse a click on it. Branch feat/folded-bar-tools. Delivery: one PR, one commit
per task; push, PR and merge stay the user's decisions.

## Specs
- S1 End Miter (L1): "end mitter no fuinciona con esta estructura, solo me deja seleccionar el perfil suelto." -> a
  click on a Folded Bar in the End Miter panel adds the bar's tube under the clicked point (as its current piece, the
  way a click on that tube would) to the list; also when the bar is preselected before the command (its tube nearest
  the preselected point). The miter at a free end of the bar shows in the preview and stays after OK.
- S2 Drill Hole (L2): "tampoco puedo usar drill si tengo un perfil plegado" -> a click on a straight wall of a Folded
  Bar in the Drill Hole panel drills the tube under it, on that tube's face at the clicked point; the hole shows in the
  bar (preview and after OK).
- S3 Every tool (L3, choice "Todas las herramientas (recomendado)"): Extend Cut, Notch (Extend Cut's subclass) and
  Cutout accept a click on a Folded Bar the same way (its tube under the clicked point, or that tube's face for the
  face-based tools). Profile Pattern takes the whole Folded Bar as the piece it repeats (copying one hidden straight
  tube of a bar means nothing); Between faces with a Folded Bar says to use Count and pitch.
- S4 The bar follows (L4): a piece added to a tube of a Folded Bar by any of these tools (preview included) shows
  folded into the bar at once, without a manual recompute, and the tube stays hidden; a preview piece dropped or a
  panel cancelled leaves the bar as before, never linking a removed object.
- S5 Bends (L4): a click on a bend zone (a point on no single straight tube face) adds nothing and the panel says
  "Click a straight part of the folded bar." (where the tool needs a face or a point; a whole-profile tool takes the
  nearest tube).

## Tasks
- T1 [S4, S5] shared: `folded_bar.segment_at(bar, sub, point)` -> (tube tip, tip face or None) or a reason; bar-follow
  before every recompute (NewestPieceObserver precedent, profile_pattern.py:661-720); relink helper before a preview
  piece is removed; Folded Bar panel `_member_at` reuses it. route=worker; commit=(this commit) [x]
- T2 [S1, S4] End Miter. route=worker (parallel); commit=(T2 commit) [x]
- T3 [S2, S4, S5] Drill Hole. route=worker (parallel); commit=(T3 commit) [x]
- T4 [S3, S4, S5] Cutout (panel and direct face+sketch path). route=worker (parallel); commit=(T4 commit) [x]
- T5 [S3, S4, S5] Extend Cut and Notch (target face on a bar, profiles from a bar, no dependency loop, no cut at a
  folded corner). route=worker (parallel); commit=(T5 commit) [x]
- T6 [S3] Profile Pattern with a whole Folded Bar. route=worker (parallel); commit=(T6 commit) [x]
- T7 [S1-S5] docs (tutorial, README, CHANGELOG), translations, full suite, verify. route=worker (docs) + parent; commit=(T7 docs commit)

- T8 [S4] deleting a miter/trim or cutout from the tree releases it (the bar keeps its tube, hidden), plus the
  verifier's regression tests (reopen untouched, release no-op, End Miter undo/redo). route=worker; commit=(T8 commit) [x]
- T9 [S2, S4] Drill Hole pattern with transversal holes on a Folded Bar tube breaks the bar shape ("Cannot compute
  Inventor representation ... BRepAdaptor_Curve::No geometry"): reproduce, fix the root cause, the bar never shows a
  broken shape silently. route=worker; commit=(T9 commit) [x]

## Log
- L1 (2026-11-13) user, with a screenshot of End Miter ("Ingletes") listing only Profile_TC80x40x1.5_000 next to a
  3-tube Folded Bar: "end mitter no fuinciona con esta estructura, solo me deja seleccionar el perfil suelto."
- L2 (2026-11-13) user: "tampoco puedo usar drill si tengo un perfil plegado"
- L3 Scope question (End Miter and Drill Hole refuse the bar; Extend Cut, Cutout and Profile Pattern have the same
  problem): user chose "Todas las herramientas (recomendado)".
- L4 Exploration (gentle-ai-explore x2): End Miter rejects in create_end_miter_tool.py:498-514 (`_base_profile`);
  Drill Hole `_pick` :794 / `face_problem`; Cutout `face_problem` create_extruded_cutout_tool.py:110-128 (direct path
  `_create_from_selection` :678-720 unguarded); Extend Cut `_add_profile` :401, whole-bar target :374, `_related`
  :150-152 loop risk; Profile Pattern `is_piece` :93-95. FoldedBar._follow_tips (folded_bar.py:239-252) runs only on
  the bar's own recompute; previews removed outside an abort would leave bar.Segments on a removed object
  (folded_chain.py:293-296). Bar side walls span several tubes, so the clicked point, not the face name, picks the
  tube; face-based tools must store the tube's own face name (baseObject / AttachmentSupport / addExternal). Parent
  decisions: S4 hook before every recompute; S5 message; Profile Pattern repeats the whole bar.
- L5 T1 evidence (worker mwex13z2-4-ybt2): folded_bar.py `segment_at(bar, sub, point=None, nearest=False) -> BarPick(tip,
  face, point, reason)`, `straight_part_message()`, `pick_point`, `nearest_piece`, `bar_tips`, `follow_new_pieces(doc)`
  (NewPieceObserver before every doc.recompute(), not obj.recompute()), `release_piece(piece)` before removing a preview
  piece. RED 8 tests (AttributeError segment_at; bar did not follow the miter), GREEN test_folded_bar_tools 8 (parent
  re-run OK, weekly 8 OK), test_folded_bar 35, test_folded_bar_panel 77, test_end_miter_panel 14, test_drill_hole_panel
  99, profile pattern modules 26/12/38/9/15. Open: Spanish/other translations of the new message (T7).
- L6 T6 evidence (worker mwexmd5a-9-yyhf): `is_piece` accepts a Folded Bar; copies link the bar; Between faces reuses
  the existing between_faces_problem message; BOM/Populate IDs count copies as folded bars (qty 3). RED 4 of 5 (bar
  refused), GREEN test_profile_pattern_folded_bar 6 (stable and weekly); pattern modules 38/26/12/9/15 OK. Follow-ups:
  piece hint/tooltip do not mention a folded bar (T7); a hidden tube of a bar picked from the tree is not mapped to
  its bar.
- L7 T4 evidence (worker mwexmctu-7-q03t): create_extruded_cutout_tool.py `face_at`, `_picked_point`, `_folded`; bar
  mapping in `_add_item`, `addSelection`, `_create_from_selection` (bend -> FrameForgeException with the bend message;
  whole-document recompute inside "Create Cutout" when a bar folds the tube); `release_piece` in `_delete_cutout`.
  RED 11 of 12; GREEN test_cutout_folded_bar 12 (stable, weekly; parent re-run 12 OK); 10 existing cutout/drill
  modules OK. Slice boundary: T1 c8e8633 (487 lines) and T6 f3009d4 + T4 are separate review slices per task commit.
- L8 T2 evidence (worker mwexmcmd-5-c4kx): create_end_miter_tool.py `_clicked_piece`, `_preselected`, bar mapping in
  addSelection/removeSelection (nearest tube), `release_piece` in `_drop_preview`, `_discard_preview` recomputes when a
  bar folded a preview. RED 9 of 9 (bar refused), then 4 (Segments lost a piece, bar Touched after Cancel); GREEN
  test_end_miter_folded_bar 9 (stable, weekly; parent re-run 9 OK); end miter panel/preview/edit/extend_gap/
  translations 14/26/6/6/4, folded bar tools/panel 8/77 OK. Open: a whole bar preselected from the tree adds nothing.
- L9 T5 evidence (worker mwexmcy3-8-waa2): create_extend_cut_tool.py bar mapping (target -> tube face, profiles ->
  nearest tube, Notch `face_target = False`), `_related` knows bars (loop refused with "{} cannot trim itself"), new
  `fold_problem` message "{} cannot be cut at its folded corner with {}." (frameforge context; T7 translations),
  `release_piece` in `_drop_preview`, recompute in `_discard_preview`. RED 12 of 12 (+ refusals re-proved with the
  rules disabled: 2 failures); GREEN test_extend_cut_folded_bar 12 (stable, weekly; parent re-run 12 OK); extend cut
  panel/preview/polish/lost-face 45/22/31/10, notch panel/preview 30/9, keep end 22 OK.
- L10 T3 evidence (worker mwexmcpn-6-9fix): create_drill_hole_tool.py bar mapping in addSelection/_add_items (tube
  face, tube vertex), `_from_bar`, `_unfold_bars`, release + recompute in `_drop_preview` / `_discard_preview`;
  drill_hole.py onDelete releases the hole and keeps a folded tube hidden. RED 12 of 14; GREEN
  test_drill_hole_folded_bar 14 (stable, weekly; parent re-run 14 OK); drill hole panel/geometry/rebase/reference/
  resources 99/26/4/10/2 OK. Open for T7: tooltips/prompts of Drill Hole, Profile Pattern do not mention a Folded Bar.
- L11 T7 docs/translations (worker mwey4wrb-a-nkwo): es for "Click a straight part of the folded bar." ("Hacé clic en
  una parte recta de la barra plegada.") and "{} cannot be cut at its folded corner with {}."; Drill Hole prompt and
  tooltip and Profile Pattern piece hint and tooltip name a folded bar (es; ru unfinished, old ru sources vanished);
  17 .qm recompiled; tutorial "### Tools on a Folded Bar", README, CHANGELOG. Approved extra surfaces (parent):
  tests/test_drill_hole_panel.py, tests/test_toolbar_translations.py (string updates), tests/test_russian_translation.py
  (append to FOLDED_MITER_TEXTS). RED test_folded_bar_translations 1 failure; GREEN 7; translation/drill/pattern/cutout
  modules OK. ru left for @c0n5t: 6 entries. Follow-up: Cutout prompt/tooltip and "Select a planar face of a profile,
  a trimmed profile or a cutout." do not mention a folded bar.
- L12 Independent verify (gentle-ai-verify mweyh8tj-b-zpsk): S1-S5 pass; new modules 8/9/14/12/12/6/7 OK; differential
  base 7ddca7c vs HEAD equal (end miter panel 14, drill hole panel 99, extend cut panel 45, profile pattern 26, cutout
  direct 3, drill hole rebase 4, folded bar 35); observer cheap (2000 objects x10: 0.021 s), reopened file untouched.
  Flagged: ru shows 4 reworded texts in English (parent: accepted follow-up for @c0n5t, repo convention, 83 ru entries
  already unfinished). Pre-existing at 7ddca7c but now easy to hit: deleting a miter/trim or cutout from the tree drops
  its tube from the bar (trimmed_profile.py onDelete, extruded_cutout.py onDelete do not release) -> T8; undo after a
  recompute outside the transaction drops a tube (panels recompute inside it; follow-up).
- L13 T8 evidence (worker mweyw30z-c-8nwg): trimmed_profile.py and extruded_cutout.py onDelete release the piece and
  show the base only when no bar folds it. RED test_folded_bar_tools 2 failures (Segments [top, left]); GREEN 13
  (stable, weekly), test_end_miter_folded_bar 10 (undo/redo on and off auto preview), cutout/extend cut folded bar
  12/12, end miter panel/edit 14/6, extend cut panel 45, cutout flow/depth 19/14, drill hole folded bar 14, trimmed
  profile pid 2, folded bar 35 OK. Full suites (job-12/13) stopped: the tree changed under them; re-run after T8.
- L14 (2026-11-13) user, manual test on the branch (FreeCAD 27.1 weekly, document PruebaLaserCut), Drill Hole on
  "Profile_TC80x40x1.5_002 (Profile_002) Face3" of a Folded Bar, centre of the face, diameter 10 mm, pattern
  longitudinal 1 back + 1 forward at 50 mm (3 holes, fine), then "Transversal <- atrás" 1 at 15 mm (6 holes), cut
  type "Una pared", depth 1,5 mm: "al hacer un patron transversal se rompe todo"; the bar renders as broken stray
  edges and the report view shows "<Part> ViewProviderExt.cpp(1545): Cannot compute Inventor representation for the
  shape of PruebaLaserCut#FoldedBar: BRepAdaptor_Curve::No geometry" (3 times). Full suite stable on 697450a:
  1955 tests OK (job-14).
- L15 Full suite weekly on 697450a (job-15): killed at the 3600 s timeout (exit 124) inside the known issue #148 hang
  (test_folded_bar_panel ExpressionTest.test_cancel_of_a_new_bar_with_an_expression_leaves_the_document_unchanged);
  859 tests ok before it, 1 failure = the known #148 test_cancel_with_undo_disabled_puts_the_corners_back...; the
  modules after test_folded_bar_panel did not run on weekly (stable ran them all: 1955 OK).
- L16 (2026-11-13) user: "no corras la suite, lo pruebo primero" -> no full suite after T9; the user tests first.
- L17 T9 evidence (worker mwf0m7hg-d-qssc): root cause removeSplitter() at the end of unfold() and fold_bar() also
  merges edges; a hole tangent to its wall edge (pitch 15 + radius 5 = 20 on a 40 mm wall) or to the next hole (pitch
  10) gives self-intersecting faces ("BOPAlgo SelfIntersect"); pre-existing at 7ddca7c; loose tube fine. Fix:
  unfolded_geometry.refine() merges faces only (UnifySameDomain(shape, False, True, False)); guard sound_solid() +
  folded_bar._sound(): an unsound fold raises UnfoldError "{} does not fold into a valid solid: check the cuts on its
  tubes (a hole or cutout touching an edge or another cut)." (es/ru translations pending). RED
  DrillHoleTransversalPatternTest 2 of 5, SoundShapeTest 4 of 4; GREEN 5 and 4 (stable and weekly); test_folded_bar
  39, drill hole folded bar 19, folded bar tools 13, folded/unfolded geometry 11/41, folded bar panel 77, cutout
  folded bar 12; parent re-run end miter/extend cut/profile pattern folded bar 10/12/6 and the 5 pattern tests OK.
  "BRepAdaptor_Curve::No geometry" itself not reproduced headless: user to confirm on PruebaLaserCut (weekly).
- L18 (2026-11-13) user, manual test of 494f0b7: "Bien el patron ahora funciona ok," -> T9 confirmed. Translation of
  the T9 message: es "{} no se pliega en un sólido válido: revisá los cortes de sus tubos (un agujero o calado que toca
  un borde u otro corte)."; ru unfinished (FOLDED_MITER_TEXTS). RED test_folded_bar_translations 1 failure; GREEN 7;
  test_russian_translation 6, test_compile_translations 3, test_toolbar_translations 4 OK. Status: all tasks done;
  push/PR left to the user. Follow-ups: ru for @c0n5t (7 texts), Cutout prompt/tooltip and "Select a planar face of a
  profile, a trimmed profile or a cutout." without folded bar, corner list "0.3" vs field "0,3", undo after a
  recompute outside the transaction drops a tube, whole bar preselected from the tree adds nothing in End Miter /
  Extend Cut, issue #148.

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
- T2 [S1, S4] End Miter. route=worker (parallel); commit=
- T3 [S2, S4, S5] Drill Hole. route=worker (parallel); commit=
- T4 [S3, S4, S5] Cutout (panel and direct face+sketch path). route=worker (parallel); commit=
- T5 [S3, S4, S5] Extend Cut and Notch (target face on a bar, profiles from a bar, no dependency loop, no cut at a
  folded corner). route=worker (parallel); commit=
- T6 [S3] Profile Pattern with a whole Folded Bar. route=worker (parallel); commit=
- T7 [S1-S5] docs (tutorial, README, CHANGELOG), full suite, verify. route=parent; commit=

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

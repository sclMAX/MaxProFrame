# Interlock at a T joint: tabs on the arriving tube, slots in the receiving one
A second Interlock kind, Tabs: at a T joint (a tube trimmed with Extend / Cut against a face of another tube) the
arriving tube's wall ends in tabs that pass through slots cut in the receiving tube's wall. Branch feat/t-joint-tabs;
work-unit commits on it; push, PR and merge follow the user's standing practice (PR per slice, merge on green CI).

## Specs
Notation: crossbar = the arriving tube (its end trimmed against the rail), rail = the receiving tube; P = the plane
of the rail face the crossbar butts against; t_r = rail wall thickness; d = crossbar axis direction toward the rail.

- S1 Same command, kind deduced (L3 item 3: "si", to the proposal "usar el mismo comando Encastre: si hacés clic en
  las paredes internas de una esquina plegada → Aletas; si hacés clic en la cara del larguero y en el travesaño que
  apoya → Lengüeta y ranura"): the Interlock command keeps making Fingers on a folded corner and makes a Tabs
  Interlock when the two faces clicked are one face of a crossbar and one face of the rail it butts against.
- S2 Picking and repeating (L2, Q2): "Al hacer click en dos caras (una del travesaño y otra del larguero) se crea el
  encastre, con un boton aplicar para poder repetir la operacion en otras caras si se desea" -> the clicked crossbar
  face is the wall that carries the tabs, the clicked rail face is the wall the slots go through; one Interlock per
  pair of faces; Apply and continue (as for Fingers, #165) repeats it on other faces.
- S3 Reused settings (L3 item 2: "resusemos"): the Tabs panel reuses the Fingers fields: Count, Finger width (Even),
  Tip with Tip size, Clearance (around each tab, in its slot).
- S4 Tab length (L2 Q1: "Sobresale un largo configurable"; L3 item 1: "Por defecto el espesor, pero que sea
  configurable."): by default the tab goes through the rail wall (t_r) and ends flush with its inside face; a value
  set by the user makes it longer (or shorter).
- S5 Any angle (L2 Q4: "Cualquier ángulo"): oblique T joints too; the tabs follow the crossbar wall and the slots are
  their footprint on the rail wall, longer at an oblique joint.
- S6 Cut length (L2 Q3: "Hasta la punta (recomendado)"): the Cut List and the Piece Table give the crossbar's length
  up to the tips of its tabs.
- S7 Folded Bar (L4: "\"que el larguero o el travesaño sean un segmento de una Barra plegada.\" incluye este caso"):
  the crossbar, the rail or both can be tubes of a Folded Bar; the bar folds with the tabs and slots and the Unfolded
  Bar carries them.
- S8 Trim gap (L12: "La pestaña cruza la separación (Recomendado)", to the question "¿Qué tiene que pasar con un
  Encastre de pestañas cuando el Trim tiene separación?"): when the crossbar's Extend / Cut trim has a Gap g > 0 the
  crossbar end stops g before P; the Tabs Interlock still holds: each tab is measured from P (the tab grows by g across
  the gap, so it still passes the rail wall as in S4) and the slots stay where they were. The error "No hay una unión
  en T entre ... no termina sobre la cara de ..." no longer appears for a gap; S6 (cut length to the tab tips) holds.
- S9 Flush wall (L14: "si quiero hacer un encastre en esa punta no me deja, dice que no cae en la cara plana pero ese
  deberia se un encastre posible"; answer "Validar la pestaña, no la holgura (Recomendado)"): the "flat part" check
  (D4) applies to the tab footprint itself, not to the slot grown by the clearance; the clearance may run past the
  edge of the rail face. A crossbar wall flush with the rail end or with a rail wall is then accepted on sharp-cornered
  tubes; on tubes with corner radii a flush wall is still refused (the flat face ends where the radius starts).

## Design decisions (parent, from the analysis in L2-L4; not user requirements)
- D1 Objects: the Interlock (Kind = Tabs) holds the settings and links PieceA = crossbar, PieceB = rail (base
  profiles); a new piece on top of the crossbar's stack adds the tabs (suffix _Tb), a new piece on top of the rail's
  stack cuts the slots (suffix _Sl). Both read the Interlock; the crossbar trim keeps targeting the rail piece under
  the slots (no dependency cycle). Deleting the Interlock removes both pieces; undo brings them back.
- D2 Every cut is straight and square to the wall it goes through (any tube laser, as Stepped and Fingers): tab sides
  square to the crossbar wall; slots square to the rail wall, the projection along the rail face normal of the tab
  volume inside the rail wall, grown by the clearance; an oblique joint gets a longer slot.
- D3 Tab length is measured across the rail wall (along the normal of P); Automatic = t_r (flush inside).
- D4 Tabs sit on the flat part of the crossbar wall (outside its corner radii) and their footprint must fall on the
  flat part of the rail face; otherwise the Interlock is refused naming the two tubes, as Fingers refusals do.

## Tasks
- T1 [S3, S4, S5] Tab geometry (pure, any angle): tab solids on the crossbar wall end and slot tools in the rail wall
  from the wall frames, settings and checks with refusal messages; unit tests. route=gentle-ai-worker;
  commit=95f2b83 [x]
- T2 [S1, S6] Objects on straight pieces: Kind Tabs on the Interlock (settings, picked faces), _Tb and _Sl pieces in
  the stacks (piece_stack/base_profile/newest_piece, BOM, Cut List and Piece Table length to the tab tips, Cutout on
  the rail), creation API for the panel, delete/undo; tests. route=gentle-ai-worker + parent; commit=e16d884 [x]
- T3 [S7] Folded Bar: crossbar and/or rail as tubes of a Folded Bar; the bar folds with the tabs and slots, the
  Unfolded Bar carries them; tests. route=gentle-ai-worker; commit=0de527d [x]
- T4 [S1, S2, S3, S4] Panel: deduce the kind from the two faces, Tabs fields (Count, Finger width, Tip, Tip size,
  Length with Automatic, Clearance), refusals, Apply and continue, edit by double click; tests.
  route=gentle-ai-worker; commit=486a155 [x]
- T5 [S1-S7] Tutorial, CHANGELOG (Unreleased), Spanish .ts/.qm, Russian unfinished + PENDING_TEXTS; full native
  suite. route=gentle-ai-worker + parent; commit=75c3484 [x]
- T6 [S8, S4, S6] Tabs across the trim gap: the T joint check accepts a crossbar end parallel to P at distance g =
  its trim's TrimGap; tabs grow by g; straight and Folded Bar tubes; tests (gap 0 unchanged, gap 0.5, Gap edited
  after the Interlock exists, Cut List length); CHANGELOG line. route=gentle-ai-worker; commit=T6 (see Log L13) [x]
- T7 [S9, D4] Off-rail check on the ungrown tab footprint (tab_geometry.py _footprint/_check_slots); slot keeps the
  clearance; tests (flush at the rail end and flush top/bottom on R = 0 tubes accepted with clearance 0.2; slot reaches
  c/2 past the edge; flush wall on a rounded rail still refused; a tab really off the face still refused).
  route=gentle-ai-worker; commit=T7 (see Log L15) [x]

Delivery forecast: ~1500-2000 authored lines; chained PRs, one per task slice. Slice boundaries: T1 = 95f2b83
(928 lines, geometry + tests, one work unit); T2 = e16d884 (~1200 lines, objects + tests, one work unit);
T3 = 0de527d (~510 lines); T4 + T5 = 486a155..75c3484 (~1670 lines, panel + docs/i18n). Chained PRs: one per slice.

## Log
- L1 User: "AHora analicemos agregar encastres a uniones en T [Image#2]" (Image: a frame of TC80x40x1.5 tubes, a
  middle crossbar Profile_TC80x40x1.5_004_Tr butting against the inner face of the rail Profile_TC80x40x1.5_002_Mt;
  both selected.)
- L2 Parent analysis (explorer mwhul2rv-2-q28h): T joint = TrimmedProfile Extend Cut (trimmed_profile.py:274),
  TrimmingBoundary names the rail piece; the Interlock (interlock.py:80) has no Shape and only FoldedBar consumes it;
  no object cuts two pieces at once; ExtrudedCutout/DrillHole are the rail-side precedent; cut_ends needs a flat end
  (a tab makes it fall back to CuttingAngle); tests: tests/test_notch_geometry.py TrimFixture.t_joint(),
  tests/test_extend_cut_geometry.py ExtendCutFixture. Questionnaire answers: Q1 "Sobresale un largo configurable";
  Q2 "Al hacer click en dos caras (una del travesaño y otra del larguero) se crea el encastre, con un boton aplicar
  para poder repetir la operacion en otras caras si se desea"; Q3 "Hasta la punta (recomendado)"; Q4 "Cualquier
  ángulo".
- L3 User: "1. Por defecto el espesor, pero que sea configurable. 2. resusemos. 3. si" (answers to: 1 tab length,
  2 reuse the Fingers settings, 3 same Interlock command deducing the kind).
- L4 User: "\"que el larguero o el travesaño sean un segmento de una Barra plegada.\" incluye este caso" (the parent
  had proposed leaving that case out of the first version); taken as approval to start with it included.
- L5 T1 (worker mwhv9ie6-3-5yjw): interlock_geometry.py TABS/TabSettings(count=2, tab_width, tip, tip_size, length,
  clearance; Even = 2*count+1 parts), tab_geometry.py TJoint(names, crossbar_face, crossbar_thickness, direction,
  rail_face, rail_thickness, end) + check/make_tabs -> TabShapes(tabs, slots). RED: import error; GREEN
  test_tab_geometry 17/17 (parent re-ran: 17 OK); test_interlock_geometry 8, test_interlock 10, test_interlock_panel
  14 OK. Limits: a crossbar end farther than t_r from the rail face is refused; slots sized from square tips; on a
  crossbar wall not square to the rail face the tab passes the inside face on one side by t_c*|n_c.n_r| (all cuts
  square to the wall, D2). Open for T2: interlock_settings Tabs branch (FingerWidth -> tab_width, new Length), bar
  integration (unfolded_geometry ignores Tabs), cut length from the tab extents.
- L6 T2 (worker mwhvxyn0-4-xax1): tab_interlock.py TabPiece (_Tb) / SlotPiece (_Sl) on ExtrudedCutout (baseObject =
  piece under; Interlock link; InterlockRole), make_tab_interlock(crossbar_piece, crossbar_sub, rail_piece, rail_sub,
  point=None, **settings), give_back relinks what pointed at a removed piece; interlock.py Tabs branch, Length,
  CrossbarFace/RailFace + snapshots; cut_ends delegates for _Tb; corner_interlocks skips Tabs. RED: module missing;
  GREEN test_tab_interlock 12. Parent: a cut on top of _Tb took the trim length (worker risk) -> RED 360 != 361.5,
  then measured_piece finds the tab piece and length_along_normal returns a tab piece's own Length; GREEN 13/13.
  Preserve OK: cut_list 27, piece_table 23, cut_ends 15, drill_hole_geometry 26, drill_hole_rebase 4,
  drill_hole_folded_bar 19, cutout_flow 19, cutout_one_wall 11, cutout_folded_bar 13, extend_cut_geometry 20,
  notch_geometry 30, profile_pattern 26, folded_bar 50, interlock 11, interlock_panel 14, tab_geometry 17,
  length_restore 10. New texts for T5 listed in the worker report (6 MaxProFrame, 4 App::Property). Open for T3:
  remove the Folded Bar guard in make_tab_interlock, follow_new_pieces/unfold with _Tb/_Sl; for T4: panel, Kind
  tooltip.
- L7 User: "1. si 2. si" -> accepted the two T1 limits: (1) at an oblique T the tab passes the rail's inside face on
  one side (about 0.75 mm at 60 degrees) because every cut stays square to its wall; (2) a crossbar ending farther
  than one rail wall thickness from the rail face is refused.
- L8 T3 (worker mwhxanuw-5-idar): make_tab_interlock(..., crossbar_point=None, rail_point=None) maps a face clicked on a
  bar to the tube under the point (segment_at; bend -> "Click a straight part of the folded bar."); tabs only on a
  free end of an open bar, else "The T joint between {} and {} is at a folded corner of {}: ..." / "... at the open
  corner of {}: ..." (checked at every recompute). No unfold/fold change needed: follow_new_pieces folds _Tb/_Sl,
  developed length runs to the tab tips. Pre-existing bug fixed: the Unfolded Bar was shifted by how far the first
  tube reaches past its path start (folded_bar._at_its_place) -> CHANGELOG Fixes in T5. RED: API missing (9 errors),
  UnfoldedBarStartTest 0.0 != -10.0; GREEN test_tab_interlock_folded_bar 11/11 (parent re-ran: 11 OK). Preserve OK:
  tab_interlock 13, tab_geometry 17, interlock 11, interlock_panel 14, folded_bar 50, folded_bar_panel 111,
  folded_bar_tools 14, drill_hole_folded_bar 19, cutout_folded_bar 13, extend_cut_folded_bar 16,
  end_miter_folded_bar 13, unfolded_geometry 66, folded_geometry 21, cut_list 27. T5 texts: drop T2's "cannot go on a
  tube of a Folded Bar yet", add the two bar-end refusals.
- L9 T4 (worker mwhy5us4-6-py7n): create_interlock_tool deduces the kind (_deduce: Fingers first, then Tabs);
  tab_interlock.tab_order tries the clicked order then the reverse; Tabs fields Count, Tab width (Even), Tip, Tip
  size, Length ("Automatic"), Clearance; Depth/Flip hidden; settings per kind ("Interlock Tabs ..." parameters);
  Apply and continue / Cancel / edit as Fingers. Bug fixed: a second click on tabbed faces made a bogus Interlock
  (_end_plane took a slot side as the end). Command tooltip deferred to T5 with its translation (option B, parent).
  RED 7 failures + 12 errors; GREEN test_tab_interlock_panel 13/13 (parent re-ran: 13 OK); preserve OK:
  interlock_panel 14, interlock 11, interlock_translations 5 (3 Spanish expectations set to English until T5),
  tab_interlock 13, tab_interlock_folded_bar 11, tab_geometry 17, toolbar_translations 4, workbench_commands 2,
  shortcuts 5, folded_bar_panel 111; russian_translation 6 (parent). T5 texts: worker report list (changed hint,
  Kind tooltip in MaxProFrame and App::Property, Apply tooltip; ~13 new; command tooltip text proposed).
- L10 T5 (worker mwhz6j9i-7-ir99): command tooltip names both kinds; 36 messages (5 changed, 31 new) in es (voseo:
  Lengüetas, ranuras, travesaño, larguero, Unión en T, Longitud) and ru (unfinished, PENDING_TEXTS); es .qm rebuilt
  (843, 4 identical copies); tutorial "### Interlock" split into Fingers / Tabs subsections; README; CHANGELOG
  Unreleased: Improvements "Interlock at a T joint", Fixes "Unfolded Bar starts at X = 0 again". Tests OK:
  toolbar_translations 4, interlock_translations 8, russian_translation 6, compile_translations 4,
  library_translations 3, workbench_translation_loading 2, interlock_panel 14, tab_interlock_panel 13.
- L11 Full native suite on 75c3484: 2172 tests OK (37 min). Native review assess per slice: medium, under budget, not
  due. Chained PRs opened for T1, T2, T3, T4+T5; merge waits for the user's manual test.
- L12 User manual test (screenshot): editing the crossbar's Trim to Separación 0,5 mm makes the _Tb and _Sl pieces fail:
  "Profile_TC80x40x1.5_004_Tr_Tb: No hay una unión en T entre Profile_TC80x40x1.5_004 y Profile_TC80x40x1.5_002:
  Profile_TC80x40x1.5_004 no termina sobre la cara de Profile_TC80x40x1.5_002." (same for _Sl). User answer: "La
  pestaña cruza la separación (Recomendado)" (other options: refuse with a clear message; leave as is). The same edit
  froze FreeCAD: separate fix, odd/tasks/panel-recompute-deadlock.md on fix/panel-recompute-deadlock.
- L13 T6 (worker): the refusal lives in tab_geometry._Layout._check_joint (parent approved tab_geometry.py as edit
  surface). Probes on 75c3484/afe3e0c: TrimGap 0.5 was already Valid on straight and Folded Bar crossbars (stable
  1.1.4 and the user's weekly 27.1.0 2026-10-28 runtime, base code from git archive): tabs reach P + t_r, slots
  unchanged, Length = trim + t_r + g; the refusal fired only for a gap > t_r (1.6 on a 1.5 wall), the end being
  limited to t_r before P (L7 limit 2) on the gapped end. The user's 0.5 failure was not reproduced; hypothesis,
  unproven: the frozen Extend / Cut panel had applied an intermediate or misread Gap (e.g. 5). Fix: TJoint.gap (the
  TrimGap of the Extend / Cut _end_plane takes the end from; 0 for an end face), _check_joint checks the end moved
  back toward the rail by the gap (L7 limit 2 kept past it), tabs start on the gapped end and reach L past P, slots
  and messages unchanged (no translation change). RED: test_tab_geometry 25 errors (TJoint takes no gap);
  TabsAcrossTheGapTest gap 2.0 refused (1 failure + 1 error, "... does not end on the face of Rail."),
  CrossbarOnBarGapTest gap 2.5 refused (1 error); the 0.5 and gap 0 cases passed already (preservation). GREEN
  (stable 1.1.4): tab_geometry 18, tab_interlock 17, tab_interlock_folded_bar 13 OK; weekly 27.1.0: tab_geometry 18,
  TabsAcrossTheGapTest 4, CrossbarOnBarGapTest 2 OK. Preserve OK: tab_interlock_panel 13, interlock 11,
  interlock_geometry 8, interlock_panel 14, interlock_translations 8, cut_list 27, piece_table 23, cut_ends 15.
  Black 25.1.0 / isort 6.0.1 clean. CHANGELOG Unreleased: "Interlock at a T joint with a gap".
- L14 User (manual test, prueba.FCStd): the Tabs Interlock at the end of the rail is refused with "Las ranuras de la
  unión en T entre Profile_TC80x40x1.5_003 y Profile_TC80x40x1.5_002 no caen en la parte plana de la cara de
  Profile_TC80x40x1.5_002." Reproduced (worker probe): square joint (180°), RH 40x80x1.5 with R = 0, crossbar _003
  outer wide wall (Face5, x = -250) flush with the rail end; the tab footprint lies exactly on rail Face1, the clearance
  grows it c/2 = 0.1 mm past x = -250 and _check_slots (tab_geometry.py:217) counts it off the rail; clearance 0
  passes. Same for the narrow walls flush with the rail top/bottom. Not a bug in angle, face pick or normals. User chose
  "Validar la pestaña, no la holgura (Recomendado)" (other options: also cut through the corner radius; leave as is).
- L15 T7 (worker): tab_geometry._Layout._footprint returns (tab, slot) faces on P, the hull before and after _grow;
  _check_slots tests the ungrown tab face against the rail face (off-rail refusal) and keeps the spacing check
  (tabs_misfit) on the grown slot faces, since slots that touch join and leave no rail between the tabs; slot tools
  still use the grown faces; messages unchanged (no .ts change). Tests: test_tab_geometry FlushWallTest (R = 0: wall
  flush with the rail end and narrow wall flush with the rail top accepted at clearance 0.2, slots reaching c/2 past
  the face edge; rounded rail flush wall still refused; crossbar 1 mm past the rail end still refused; centred joint
  R = 0 and R = 3 unchanged) and TabRefusalTest's "clearance alone" case now accepted (S9); test_tab_interlock
  FlushWallInterlockTest (R = 0 Profiles, tab_order + make_tab_interlock Valid, _Tb/_Sl one solid each). RED (stable):
  test_tab_geometry 23 tests, 3 errors (the two flush acceptances, the clearance-alone case: "The slots ... do not fall
  on the flat part ..."); test_tab_interlock 18 tests, 1 failure (tab_order error not None). GREEN (stable):
  tab_geometry 23, tab_interlock 18, tab_interlock_folded_bar 13, tab_interlock_panel 13, interlock_panel 14 OK.
  Black / isort clean. CHANGELOG Unreleased Fixes: "Interlock at a T joint" flush wall.

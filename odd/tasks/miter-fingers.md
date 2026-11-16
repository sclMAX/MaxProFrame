# Interlock fingers at the inner vertex of an End Miter corner
The Interlock command (Spanish *Encastre*) makes Fingers at the inner vertex of an End Miter corner between two
separate tubes, as it does at a folded corner of a Folded Bar. Branch feat/miter-fingers (from main a9550f5);
work-unit commits; PR per slice, merge on green CI (the user's standing practice).

## Specs
Notation: A, B = the two tubes of the corner, each cut by its own End Miter against the other; M = the miter plane;
the inner walls = the walls of A and B on the inside of the corner, meeting at the inner vertex.

- S1 The case (L1: "Porque no puedo hacer un encastre en el vertice interno de un End Miter"; L2: "la feature"): the
  Interlock command makes Fingers when the two faces clicked are the inner walls of two separate tubes that meet at
  an End Miter corner: two straight tubes, or a Folded Bar's free end and a straight tube (the user's screenshot:
  Profile_TC80x40x1.5_001, a free end of FoldedBar, and Profile_TC80x40x1.5_002_Mt).
- S2 Same settings and flow as Fingers at a folded corner: Count, Finger width, Tip with Tip size, Depth, Clearance,
  Flip; one Interlock per corner; Apply and continue; edit by double click.
- S3 Below the fingers (L3 Q1: "Inglete común (Recomendado)"): the fingers take only the band of the inner walls (to
  the finger depth); the rest of the corner stays cut by the End Miters.
- S4 Miter gap (L3 Q2: "Cruzan la separación (Recomendado)"): with an End Miter Gap > 0 the fingers bridge the gap and
  still interlock; the finger Clearance stays a separate setting.
- S5 Cut length (L3 Q3: "Hasta la punta de las aletas (Recomendado)"): the Cut List, the Piece Table and the BOM give
  each tube's length up to the tips of its fingers.
- S6 Required trims (L3 Q4: "Los dos End Miter, uno contra otro (Recomendado)"): both tubes must already be cut by End
  Miters made against each other; the fingers read the miter plane from them. Otherwise the panel says what is
  missing and what to do.
- S7 No misleading refusal (L1 screenshot): two inner walls at a miter corner are never deduced as a T joint; the
  message "Las ranuras de la unión en T ... no caen en la parte plana ..." does not appear for them.

## Design decisions (parent, from the code map in L2; not user requirements)
- D1 Pattern of the T-joint Tabs (odd/tasks/t-joint-tabs.md D1): the Interlock holds the settings and the two
  remembered faces; one piece on top of each tube's newest piece fuses that tube's fingers and cuts the other tube's
  fingers out of it; each piece reads the pieces UNDER the other tube's piece (no dependency cycle).
- D2 The panel shows the kind as Fingers (Aletas). Whether this is Kind Fingers plus a location marker or a new Kind
  value is the T2 writer's choice, recorded in the Log; existing documents must restore unchanged, folded-corner
  Fingers must behave as today, and folded_bar.corner_interlocks must never take a miter-corner Interlock.
- D3 Who owns the first finger: tube A = the first face clicked; Flip swaps, as today.
- D4 Every cut is straight (laser), as Fingers and Stepped today; tubes with corner radii are covered by tests.
- D5 Out of scope: the open corner of a closed Folded Bar (still refused, as today).

## Tasks
- T1 [S2, S3, S4] Geometry (pure, 3D tube frames): finger solids of each tube and the cuts they need in the other,
  from the two tube axes, inner normals, inner-wall span and the (gap-shifted) miter planes; reuse FingerSettings,
  bounds, tips and the stepped-band ideas of unfolded_geometry (_OpenStep, _overlap, _past_miter); checks and
  refusals; unit tests (R = 0 and R > 0, 90 and oblique angles, gap 0 and > 0, flip). route=gentle-ai-worker; commit=T1 (see Log L4) [x]
- T2 [S1, S5, S6, D1, D2] Objects on straight tubes: Interlock kind/marker, finger pieces on the newest pieces,
  remembered faces, finding both End Miters, Length to finger tips, measured_piece, cut_ends, BOM, delete/undo
  give-back, corner_interlocks skip; tests. route=gentle-ai-worker; commit=T2 (see Log L5) [x]
- T3 [S1] Folded Bar free end against a straight tube (the user's case): the bar folds the finger piece, the Unfolded
  Bar carries it, developed length to the tips; tests. route=gentle-ai-worker; commit=T3 (see Log L6) [x]
- T4 [S1, S2, S6, S7] Panel: deduce Fingers at a miter corner before Tabs, refusals for missing miters, fields, hints,
  Apply and continue, edit; tests. route=gentle-ai-worker; commit=T4 (see Log L7) [x]
- T5 [S1-S7] Tutorial, CHANGELOG (Unreleased), Spanish .ts/.qm (Qt lrelease from the AppImage), Russian unfinished +
  PENDING_TEXTS; full native suite. route=gentle-ai-worker + parent; commit=T5 (see Log L8) [x]

## Log
- L1 User (screenshot: FoldedBar, Profile_TC80x40x1.5_004_Tr_Tr, Profile_TC80x40x1.5_002_Mt; Interlock panel on the
  inner walls of the top-right End Miter corner, kind Lengüetas, message "Las ranuras de la unión en T entre
  Profile_TC80x40x1.5_001 y Profile_TC80x40x1.5_002 no caen en la parte plana de la cara de
  Profile_TC80x40x1.5_002."): "Porque no puedo hacer un encastre en el vertice interno de un End Miter". Parent
  explained: Fingers exist only at folded corners of a Folded Bar (odd/tasks/joint-tabs.md); between two tubes the
  panel tries Tabs. Offered a clearer message or the feature.
- L2 User: "la feature". Code map (explorer mwihpyq6): fingers today are cut only in the Unfolded Bar
  (unfolded_geometry._Bend: _step_ends/_step_points/_step_regions/finger_levels/_tips/removed); _OpenStep
  (unfolded_geometry.py:784-983) is the nearest geometry for two separate tube ends (bar coordinates, no MiterGap);
  Tabs pieces (tab_interlock.py _InterlockPiece/_Tb/_Sl, face_snapshot/found_face, give_back) are the pattern for two
  tubes; End Miter plane from TrimmedProfile.miter_planes / miter_geometry.miter_plane; panel _deduce
  (create_interlock_tool.py:603-619) tries Fingers only on PickedFace (folded corner) then tab_order;
  corner_interlocks (folded_bar.py:349) skips only Tabs; lengths: _utils.is_tab_piece/length_along_normal,
  extruded_cutout.measured_piece, cut_ends.
- L3 User answers: Q1 below the fingers "Inglete común (Recomendado)" (other: stepped); Q2 miter gap "Cruzan la
  separación (Recomendado)" (other: refuse); Q3 cut length "Hasta la punta de las aletas (Recomendado)" (other: miter
  length); Q4 required "Los dos End Miter, uno contra otro (Recomendado)" (other: also without a miter).
- L4 T1 (worker): `miter_finger_geometry.py` (pure; imports interlock_geometry and
  unfolded_geometry.automatic_step_depth, changes neither). API for T2: `MiterTube(name, face, thickness, direction,
  section, miter)`: face = the planar outer face of the tube's inner wall (outward, toward the inside of the corner),
  direction = its axis toward the corner, section = its cross-section face anywhere along the axis (MiterPlane.section
  of `TrimmedProfile.miter_planes`), miter = (point, normal) of the plane its End Miter cuts, gap included
  (`plane.shifted(MiterGap / 2)`, either normal sense); `MiterCorner(a, b)` (a = first face, owns the first finger);
  `check(FingerSettings, corner)`, `make_fingers(...)` -> `MiterFingerShapes(a, b, owners, depth)`, each side
  `TubeFingers(fingers, cuts, tip)` (tip = (point, axis direction) of the cross-section its fingers end on, for S5);
  `joined(shape, side)` = fuse fingers, cut cuts, removeSplitter. Geometry: W = n_A x n_B, V = inner vertex at mid
  height; each level's owner covers the overlap of both bands (its section prolonged past its own plane, across the
  gap, to its cross-section through the farthest overlap vertex - g/2); the other tube loses its band from g past the
  overlap and the finger grown by g (g/2 at the tip); levels overlap by g along W; tips as at folded corners. Below
  the band and the trims (s + g/2 at 90, about 1.5 s at 60/120) the corner is the plain miter. Property of D4 (cross-
  section cuts): an oblique corner keeps a notch at the inner vertex, 0.5 s^2 |cot(angle)| x height (0 at 90; 34.6 mm^3
  for s = 2, 30 high, at 60 and 120), as folded-corner fingers. R > 0: each finger keeps its own tube's corner radius,
  so the rounded edges of both tubes do not match exactly past the miter (not measured). New refusals (InterlockError,
  translate "MaxProFrame", for T5): "The faces of {} and {} are not the inner walls of an End Miter corner between
  them." (not planar, a face across its axis, faces not facing each other, planes not parallel, inner vertex off the
  mid-plane, a wall not ending on its plane: tolerance 1e-3 mm), "{} and {} are not the same size along their corner:
  their fingers cannot match.", "The finger depth of the corner between {} and {} must be between {min:g} and {max:g}
  mm." (thicker wall .. half the shallower tube, floor 0.1), "The fingers of the corner between {} and {} do not fit at
  this angle: make the depth smaller." (a finger + g past the inside of the other tube's far wall), "The fingers of the
  corner between {} and {} do not reach across the miter gap: make the gap smaller or the depth larger."; plus
  FingerSettings.check's count, fit and tip messages. Tests tests/test_miter_finger_geometry.py (40 x 30 x 2 tubes,
  R 0 / 4, 90 / 60 / 120 degrees, gap 0 / 0.5 / 1, Count 2 / 3, Flip, Square / Chamfer / Round): one valid solid
  each, no overlap, finger-to-other distance >= g, fingers past the other's plane (gap), unchanged below the band,
  void = notch only, owners/Flip with point probes, tips only on fingers, refusals. RED: ModuleNotFoundError
  (1 error). GREEN (stable 1.1.4): test_miter_finger_geometry 12 OK (about 10 s), test_interlock_geometry 8 OK.
  Mutations caught: no +g at the band start (4 failing tests), no trim (6), owners swapped (4), finger to tip + g/2
  (5), end at the second vertex (5), trim without step clearance (3), band 3 s deep (2). Black 25.1.0 / isort clean.
- L5 T2 (worker): D2 choice = Kind Fingers + marker: a miter-corner Interlock is Kind Fingers with `AtEndMiter` True
  (`interlock.is_miter_interlock`); only it gets the marker and `FaceA`/`FaceB` + `PointA..AnchorB` (added by
  `interlock.add_miter_properties` at creation and on restore; Kind read-only on it), so older documents restore with
  no new property; `interlock.on_folded_corner` (Fingers and not miter) is what `folded_bar.corner_interlocks` takes now
  (Tabs and miter Interlocks left out). New `miter_finger_interlock.py`: `MiterFace(piece, sub, point)`,
  `make_miter_fingers(first, second, **settings)` (settings by FINGER_PROPERTIES name, other names ValueError; first
  = A owns the first finger), `miter_order(first, second, **settings)` -> `MiterOrder(first, second, error, found)`
  (keeps the clicked order; found = either tube has an End Miter against the other; for T4 `_deduce`),
  `miter_pieces(interlock)` -> [A piece, B piece], `interlock_faces`, `interlock_fingers`, `FingerPiece` (on
  tab_interlock._InterlockPiece, which gained a `made(fp)` hook and `interlock_tooltip()`; label suffix _Fg,
  InterlockRole FingersA/FingersB, icon interlock-fingers.svg, the A piece shows the Interlock in the tree). Each piece
  builds the MiterCorner in the frame of the A piece under: faces found on FaceA/FaceB (the pieces under the finger
  pieces, D1, no cycle), the newest End Miter of each stack against the other tube (`_end_miter`), its
  `miter_planes(trim)[i].shifted(MiterGap/2)` origin/normal/section, direction = -inward; B's shapes moved to B's frame.
  `_utils.is_finger_piece` / `sets_its_length` (tab or finger piece) drive length_along_normal, measured_piece and
  cut_ends (the End Miter's angles). Length = under Length + max(0, tip . d - under's reach along d) (S5). Finding:
  with s <= depth/2 the miter point (outer wall) is farther than the finger tips at 60-120 degrees, so Length = the
  End Miter's there; tips set it only at wide corners (150 degrees, Depth 15 on TC80x40: +8.56 mm, tested). Refusals
  (new texts for T5, MaxProFrame): "Both faces are on {}: click the inner wall of each tube of the End Miter corner.",
  "The fingers of the corner between {} and {} cannot go on a tube of a Folded Bar yet." (T3 removes it), "The fingers
  of the corner between {} and {} need two tubes: {} is a {} profile.", "The fingers of the corner between {} and {}
  need an End Miter of each tube against the other: make them with Miter Ends.", "The fingers of the corner between {}
  and {} need an End Miter of {} against {}: make it with Miter Ends.", "The corner between {} and {} already has
  fingers: {}."; App::Property: "Fingers at the inner vertex of an End Miter corner between two tubes", "Piece and
  inner wall of the first tube, which owns the first finger", "Piece and inner wall of the second tube", "The
  Interlock of the End Miter corner this piece adds its fingers for". Tests tests/test_miter_finger_interlock.py (14):
  TC80x40x1.5 tubes, 90/60/120/150 degrees, R 0/3, gap 0/0.5/1, Count/Tip/Flip/Clearance; Valid one-solid pieces, no
  overlap, each takes from the other's End Miter, stacks/newest/no cycle/tree/icon, owners + Flip probes, S6 messages
  (A only, B only, neither; found flag), not-inner faces, same tube, Count 1, unknown setting, one per corner, faces
  clicked on profiles go on the End Miters, Length = extent along the axis, BOM row, piece_texts, Cut List D2,
  cut_ends/angles/Cutout = End Miter's, drill hole on _Fg keeps Length, settings edit, refused setting keeps base
  shapes, MiterGap edited after (0.5/1/0), delete/undo/redo with a hole on _Fg, save/reopen + renamed faces, Folded
  Bar with folded Fingers folds the same with a miter Interlock in the document and in its Interlocks. RED (stable):
  ImportError is_miter_interlock (1 error). GREEN (stable 1.1.4): miter_finger_interlock 14 OK (one probe fix: points
  moved into the wall overlap). Mutations caught: corner_interlocks without the skip (1 error), no tip reach (1 fail),
  sets_its_length = tabs only (5 fails). Preserve OK: miter_finger_geometry 12, interlock 11, interlock_geometry 8,
  tab_interlock 18, cut_list 27, piece_table 23, cut_ends 15, folded_bar 50, end_miter_geometry 6,
  tab_interlock_folded_bar 13, interlock_panel 14. Black 25.1.0 / isort 6.0.1 clean. Open for T4: the edit panel on a
  miter Interlock (double click) is untested; Kind tooltip and command texts.
- L6 T3 (worker): `miter_finger_interlock._located` maps a face clicked on a Folded Bar to the tube under the
  `MiterFace.point` (`tab_interlock._on_bar` / `segment_at`; bend -> "Click a straight part of the folded bar."); T2's
  guard "... cannot go on a tube of a Folded Bar yet." removed (T5: drop its text). New `_check_bar_ends` (in `_corner`,
  so at creation and at every recompute, before the End Miter check): for a tube a bar folds, the end of its chain
  segment nearest the other piece (global distance from the segment start / end to the other piece's shape) must be a
  free end of an open bar, else "The End Miter corner between {} and {} is at a folded corner of {}: the fingers go on a
  free end of a Folded Bar." / "... is at the open corner of {}: ..." (D5; new texts for T5, MaxProFrame). No change to
  folded_bar / unfold / fold needed: follow_new_pieces folds the _Fg piece, the Unfolded Bar carries the fingers and the
  cuts, DevelopedLength runs to the tips (at 90 degrees the miter point is farther, so unchanged; at 150 degrees with
  Depth 10 on 50x50x2 the bar is longer). Tests tests/test_miter_finger_interlock_folded_bar.py (13; make_legs user
  layout with the End Miters the panel makes, TabsOnBarFixture helpers): free end + straight tube at 90 gap 0 and 0.5,
  straight tube clicked first with Flip, 60 / 120 / 150 (Depth 10) oblique bars, two bars' free ends; each: _Fg on the
  bar's End Miter, bar Segments, FoldedBar and Unfolded Bar valid one solid with the fingers added and the other's cuts
  removed (volume deltas, point-for-point via the unfold placements), no overlap with the other tube, DevelopedLength =
  before + (piece Length - End Miter Length) = Unfolded XLength, BOM length; straight side as T2; refusals (folded
  corner on the bar, the tube given itself, closed bar open corner, bend) with nothing made; delete/undo/redo;
  save/reopen. RED (stable 1.1.4): 13 tests, 5 failures + 8 errors ("The faces of FoldedBar and ... are not the inner
  walls ...", "... cannot go on a tube of a Folded Bar yet."). GREEN (stable): 13 OK (~57 s). Mutation caught: segment
  end nearest the other piece inverted (1 failure + 9 errors). Preserve OK (stable): miter_finger_interlock 14,
  folded_bar 50, tab_interlock_folded_bar 13, end_miter_folded_bar 13, unfolded_geometry 66, folded_geometry 21. Black
  25.1.0 / isort 6.0.1 clean. Not covered: a bar changed after the Interlock so its end becomes a folded corner (the
  check runs at recompute, untested).
- L7 T4 (worker): create_interlock_tool `_deduce`: folded corner first (unchanged), then
  `miter_order(MiterFace(first), MiterFace(second), **Fingers settings)`: no error -> Fingers at the miter corner
  (`make_miter_fingers(first, second)`, first click = tube A, D3); error with `found` -> that refusal shown, Tabs never
  tried (S6, S7); else Tabs as before. `self.miter` picks the miter tooltips (Count, Depth, Flip); `_invalid` reads
  `miter_pieces` and the bars folding them; edit/double click (Interlock or either _Fg) unchanged path; Fingers
  settings shared with folded corners. `Click.mitered` (`miter_finger_interlock.end_mitered`: the clicked tube has an
  End Miter in its stack) gives the new other-face hint. `_take_clicks` waits (GAP_DELAY_MS reschedule) while the
  panel or any document recomputes (panel-recompute-deadlock S3). `miter_finger_interlock._check_gaps` (in `_corner`,
  after `_miters`): End Miters with MiterGap differing by > MEET_TOLERANCE refused. New texts for T5 (MaxProFrame):
  "Click the inner wall of the other tube at the End Miter corner for fingers, or the other face of the T joint for
  tabs.", "Number of fingers, at least 2; the tube of the first face clicked owns the first one", "Depth of the finger
  band across the inner walls; Automatic: the step depth of a Stepped joint", "Swap the tubes: the tube of the second
  face clicked owns the first finger", "The End Miters of {} and {} have different gaps: give them the same Gap.".
  Left for T5 (changing them breaks Spanish expectations in tests/test_interlock_translations.py, outside T4's
  surface): pick_hint, the Kind tooltip and the command tooltip still name only folded corners and T joints. Tests:
  new tests/test_miter_finger_panel.py (11: straight corner clicked/preselected, Cancel/OK undo; B first owns the first
  finger, Flip swaps the gains; user's case bar free end + bottom tube, bar folds _Fg, no bar.Interlocks; missing End
  Miter both click orders and unequal gaps -> message, nothing made; one per corner both orders; T joint -> Tabs and
  folded corner of the mitered bar -> folded Fingers; clicks during the panel recompute wait; fields update both
  pieces + Count 1 refusal; Spanish Esquina/Aletas; Apply and continue on two corners; edit via setEdit, double click
  on the Interlock and on each _Fg); test_miter_finger_interlock +5 (click order twice, Extend Cut / End Miter vs a
  third tube = MISSING_ONE, unequal gaps at creation and after, touching A/B/either End Miter recomputes both pieces
  identically (patched `_in_frame` sees both bases once), reopened 150 deg Depth 15 keeps Length); test_interlock +1
  (reopened folded-corner Interlock has no AtEndMiter/FaceA/FaceB/PointA/NormalB/AnchorA, Kind editable). RED (stable
  1.1.4): test_miter_finger_panel 11 tests, 9 failures + 7 errors (T-joint hint/refusal, nothing made, flip tooltip,
  clicks taken during recompute); test_miter_finger_interlock 19, 5 failures (gaps message; touch test's first probe
  patched FingerPiece.execute, which FreeCAD does not call through the class: rewritten, passes, preservation);
  test_interlock 12, 1 error (test used a stale profile after reopen: fixed, preservation). GREEN (stable 1.1.4):
  test_miter_finger_panel 11 OK, interlock_panel 14 OK, tab_interlock_panel 13 OK, miter_finger_interlock 19 OK,
  miter_finger_interlock_folded_bar 13 OK, interlock 12 OK, interlock_translations 8 OK. Black / isort clean.
- L8 T5 (worker, uncommitted on 329dfd0): texts: pick_hint, the Kind tooltip (MaxProFrame and App::Property) and the
  command tooltip name the End Miter corner (old sources replaced in es/ru). S6 gap (B1 of the T4 verify):
  `miter_finger_interlock.unmitered_corner(first, second)` -> the S6 "need an End Miter of each tube against the other"
  InterlockError (via `_miters`) when both faces are flat walls along two different Square/Rectangular Hollow tubes,
  axes not parallel (sin > 0.1) and crossing within half the smaller tube, the crossing within one tube size
  (max ProfileWidth/Height) of an end of each tube, each face normal in the corner plane, toward the other tube's far
  end and on its side of the axis (outer face of the wall); else None (Part.OCCError -> None; centre = volume-weighted
  CenterOfMass of the solids: a profile is a CompSolid). `_deduce` calls it only when Tabs refuse with `found` False
  and `_fingers_meant` is False, so T joints that reach the rail face keep their messages. i18n: 4 changed + 21 new
  messages (17 MaxProFrame, 4 App::Property) in es ("esquina en inglete" = End Miter corner, "inglete" = End Miter,
  "Crear ingletes" = Miter Ends, "Separación" = Gap) and ru (unfinished, PENDING_TEXTS); es .qm with the AppImage
  lrelease (868 finished; HEAD .ts rebuilt byte-identical first), copied to es-AR/es-CO/es-ES (same md5); ru.qm
  rebuilt byte-identical, unchanged; the T2 text "... cannot go on a tube of a Folded Bar yet." was in no catalog.
  Docs: tutorial "#### Fingers at an End Miter corner" (+ Interlock intro, hint), README Folded miters line, CHANGELOG
  Unreleased Improvements "Interlock at an End Miter corner". Tests: test_miter_finger_panel +UnmiteredCornerTest (4:
  no-miter corner both orders, bar free end + bottom tube, other walls of that corner keep `tab_order`'s refusal,
  T joint NO_END and a plain crossbar 10 mm short near the far rail end) and MiterRegressionTest (5, from the T4
  verify: T joint with the crossbar mitered against a third tube makes Tabs both orders; Depth 30 -> "between 2 and
  24.9 mm", outer wall -> not the inner walls, never "T joint"; clicks waiting for a recompute dropped on close;
  Apply and continue miter -> folded corner keeps Count 4 and the folded Flip/Count tooltips; second click inside a
  real TrimmedProfile recompute waits, no geometry during it); test_interlock_translations +3 (miter panel hints,
  tooltips, FaceA doc and the no-miter refusal in Spanish; miter refusal/property texts) and Spanish Kind/hint updated;
  HINT_NONE updated in test_interlock_panel / test_tab_interlock_panel. RED (stable 1.1.4, HEAD scratch + new tests):
  UnmiteredCornerTest 3 tests, 2 failures + 1 cascade error ("There is no T joint between TubeA and TubeB: TubeA does
  not end on the face of TubeB."); interlock_translations 11, 5 failures. GREEN: miter_finger_panel 20 OK,
  interlock_translations 11 OK. Mutations caught: no inner-wall direction/side checks (1 fail + 2 errors), no end
  distance check (1 fail), no busy wait in `_take_clicks` (1 fail). Full native suite (stable 1.1.4, before
  MiterRegressionTest was added): 2283 tests OK in 2626 s. Black 25.1.0 / isort 6.0.1 clean.
- L9 Delivery: PR per slice, each merged on green CI (stable + weekly): T1 #176 (b519e33), T2 #177 (eb8eaeb), T3
  #178 (9e075c1), T4 #179 (9244799), T5 #180 (642decf). Independent verifications (Risk item 3): T2 no blocker
  (old features identical, old documents restore unchanged); T4 one S6 gap (no End Miter at all) fixed in T5; T5 no
  blocker (164 panel probes: T-joint refusals byte-identical except L-like corners without End Miters, which now get
  the S6 message; reach of that rule = one tube size from a tube end, advisory). Full native suite 2283 OK on 1.1.4
  before the last T5 tests. Open: the user's manual test in FreeCAD; optional tightening of the S6 reach.

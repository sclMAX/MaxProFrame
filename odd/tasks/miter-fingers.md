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
  give-back, corner_interlocks skip; tests. route=gentle-ai-worker; commit=
- T3 [S1] Folded Bar free end against a straight tube (the user's case): the bar folds the finger piece, the Unfolded
  Bar carries it, developed length to the tips; tests. route=gentle-ai-worker; commit=
- T4 [S1, S2, S6, S7] Panel: deduce Fingers at a miter corner before Tabs, refusals for missing miters, fields, hints,
  Apply and continue, edit; tests. route=gentle-ai-worker; commit=
- T5 [S1-S7] Tutorial, CHANGELOG (Unreleased), Spanish .ts/.qm (Qt lrelease from the AppImage), Russian unfinished +
  PENDING_TEXTS; full native suite. route=gentle-ai-worker + parent; commit=

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

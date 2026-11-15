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
  refusals; unit tests (R = 0 and R > 0, 90 and oblique angles, gap 0 and > 0, flip). route=gentle-ai-worker; commit=
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

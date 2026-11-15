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
  from the wall frames, settings and checks with refusal messages; unit tests. route=gentle-ai-worker; commit=T1 commit [x]
- T2 [S1, S6, S7] Objects: Kind Tabs on the Interlock, _Tb and _Sl pieces in the stacks (BOM, Cut List length to the
  tab tips, Piece Table, piece_stack/base_profile/newest_piece), Folded Bar folding and Unfolded Bar, delete/undo;
  tests. route=gentle-ai-worker; commit=
- T3 [S1, S2, S3, S4] Panel: deduce the kind from the two faces, Tabs fields (Count, Finger width, Tip, Tip size,
  Length with Automatic, Clearance), refusals, Apply and continue, edit by double click; tests. route=gentle-ai-worker;
  commit=
- T4 [S1-S7] Tutorial, CHANGELOG (Unreleased), Spanish .ts/.qm, Russian unfinished + PENDING_TEXTS; full native suite.
  route=gentle-ai-worker + parent; commit=

Delivery forecast: ~1500-2000 authored lines; chained PRs, one per task slice (T1, T2, T3+T4).

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

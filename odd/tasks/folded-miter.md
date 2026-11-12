# Folded miters (V-notch tube folding) and unfolded bar
A chain of tube profiles is joined by folded corners (laser V-notch with key and relief, outer wall bent with a real
radius) and unfolded into one straight solid with every cut, exported with FreeCAD's own formats for a CNC tube laser.
Status: T1-T7 merged (PR #145, 75e69ca); refinements T8-T11 done, T12 (L39-L40) done on branch `feat/folded-miter-refine`; push and PR are the user's decision.

## Specs
- S1 Folded corner (L1): "quiero analizar tener una feature que permita crear ingletes plegados (realizados con corte
  laser) similares a esto [Image#1]" -> a corner between two consecutive segments of the same tube becomes a folded
  corner: the walls on the inside of the corner get a V notch, the wall on the outside of the corner stays whole and is
  bent. Image#1 shows the notch with an interlocking key (bulb tab on one flank, matching socket on the other) and a
  curved relief next to the bent wall.
- S2 Frame with an open corner (L1): "me gustaria poder marmar una marco por ejemplo como este [Image#2] y luego poder
  crear las uniones en las esquinas (3 porque la cuata deberia estar abierta)" -> the frame is drawn with profiles as
  today; each corner of the chain is chosen as folded or open; in a closed rectangle, 3 corners are folded and the
  4th stays open.
- S3 Unfold to one bar (L1): "luego poder desplegar (por eso queria analizar sheetmetal, para tomar ideas) el perfil
  para que quede como una unica barra con los cortes para poder enviarla a una maquina de corte laser de tubos cnc." ->
  the folded chain produces one straight bar with all its cuts.
- S4 Machine-agnostic export (L2.1): "Lo aremos agnostico a la maquina o cam, usaremos los formatos de exportacion que
  maneja freecad, creamos el marco lo desplegamos (queda como una solido con cortes) exportamos, si en el futuro
  necesitamos un formato particular lo analizaremos llegado el caso." -> the unfolded bar is a single solid with cuts
  that FreeCAD's own export (File > Export: STEP, IGES, BREP...) writes; no machine- or CAM-specific format.
- S5 Arbitrary angles (L2.2): "Angulos arbitrarios." -> folded corners are not limited to 90 degrees.
- S6 Saved configurations (L2.3): "Lo manejaremos con configuraciones (que se guarden)." -> bend compensation comes
  from named configurations that persist between sessions.
- S7 Real radius (L2.4): "Radio real." -> the folded 3D bar shows the bent wall with its real bend radius.

- S8 Clearance, key and relief (L5.1): "Olgura manejemos una solo configurable (como hacemos con el corte en
  inglete), llave y alivio activado y desactivables." -> one clearance value, like the End Miter `MiterGap`
  (`trimmed_profile.py:502`: half of it on each side of the cut), applied to the notch flanks, the key and (L26 "La
  olgura debe aplicarce tambien al corte delcirculo de la esquina.") the round relief cut at the corner: its arcs move
  back the whole clearance (kept disc radius rho - g, concentric with the bend axis; the bent wall face they meet
  does not move), so the folded corner shows the same gap g along the arc as between the flanks (L27); the key
  is on by default and can be turned off; the relief is always on (L36 "sacalo y la casilla tambien, no le veo
  sentido a desactivar el alivio").
- S9 Corner radius (L5.1): "El radio de la esquina tambien debe ser configurable, con limites minimos (teniendo en
  cuenta el espesor) y maximos (teniendo en cuenta el perfil)." -> the inside bend radius can be set; values below a
  minimum derived from the wall thickness or above a maximum derived from the profile section are rejected with a
  message naming the allowed range.
- S10 Profiles (accepted P2, L5.2 "si."): Rectangular Hollow and Square Hollow first; open profiles (C, U, angle)
  later.
- S11 Configurations (accepted P3, L5.3 "si."): name, material, wall thickness, inside bend radius, K-factor; stored
  in a versioned JSON file next to the profile libraries (atomic save, like LibraryManager), last used in FreeCAD
  params.
- S12 Miter conflict (accepted P4, L5.4 "si"): a folded corner must have no miter/trim of its own: the panel reports
  the conflict instead of guessing.
- S13 Objects (accepted P5, L5.5 "si."): `FoldedBar` (folded 3D solid with real radius, one piece, one PID,
  developed length in BOM / cut list, hides the segment tips) and `UnfoldedBar` (straight solid along X derived from
  it, the one you export).

Accepted design proposals (L6 "deacuerdo" to Q1-Q6):
- S14 Radius scope: one radius per bar, defaulting to the configuration's radius, with an optional override on a
  single corner.
- S15 Radius limits (S9; rewritten by L39-L40 "el limite deberia ser el radio maximo tangente a las paredes - 2
  espesores aproximadamente", "son 2 tubos de 40x40 a 90º y el radio es de 130mm porque no podria crear un corte
  asi?"): min = t (wall thickness); max per corner = r_lim - 2t, where r_lim = (depth - t) / (1 - cos(theta/2)) is
  the inside radius whose inside face of the bent wall passes through the inner corner (theta = bend angle, depth
  across the bent wall). 40x40x1.5 at 90 degrees: r_lim 131.45, max 128.45 (outer 129.95, the user's 130). The key
  takes no room from the radius: whether it fits on the miter line is check_key's job (S20). Was: depth - 2t - key.
- S16 Reference: profiles stay where drawn; the fold rounds the outside corner inside the virtual sharp, so the outer
  dimensions of the frame do not change (outside mold line, like sheet metal).
- S17 Open corner and start: a closed loop needs at least one open corner; its ends keep their own End Miter (part of
  the segment tips, moved to the unfolded bar like any other cut). The unfolded bar starts (X = 0) at the open-corner
  end of the first selected segment.
- S18 Continuity: consecutive segments must be the same tube with the same section orientation and anchor across each
  fold; in a 3D chain each bend axis must be parallel to a wall pair of the tube; otherwise the panel explains why.
- S19 Stock: warn when the developed length exceeds the stock length configured for the cut list.
- S20 Key and relief sizes (L11 "editables", answer to the proposal in L11): defaults relative to the tube, editable
  on each bar (not in the bend configuration): V flanks moved back half the clearance each; relief radius = inside bend radius of each corner, computed, not a setting (L36; any other value leaves a gap or
  a collision at the folded corner); was: relief radius = inside bend
  radius; key (rewritten by L26 "La llave debe ubicarce al centro de la linea del bisel y debe ser solo un medio
  circulo (sin cuello).") = a half circle centered on the miter line, at the middle of the miter line seen on the
  side wall of the folded bar (from the outer contour of the bend to the inner corner); when that middle leaves no
  room (it falls in the bend or the relief, or too close to the inner wall), the key slides along the miter line to the
  nearest place where it fits (L32 "Correrla al lugar más cercano donde entre"), standing out of one flank as
  the tab with its half-circle socket in the other flank, no neck (the Neck Width setting and property are removed;
  the feature is unreleased), diameter = 1/4 of the depth across the bent wall; the clearance goes half on the tab,
  half on the socket; the diameter is the key room of S15; a key that does not fit is refused as before.
- S21 (dropped by L36: the relief can no longer be turned off) Relief off at wide angles (L21 "Rechazar la esquina"): without the relief, a corner bending more than
  2 acos(r / (r + t)) is refused: "The corner between {} and {} bends {} degrees: without the relief it bends up to {}
  degrees. Turn the relief on." (106.3 degrees for r = 3, t = 2; 88.8 degrees for r = 5, t = 2).

- S22 Command flow (L26 "Me gustaria que el comando se comporte como el de corte en bicel, aprieto el boton y voy
  seleccionado perfiles."): Folded Bar works like Create Miter Ends (`create_end_miter_tool.py` CreateEndMiterCommand
  / EndMiterTaskPanel): the command is active with a document and nothing selected, opens the panel at once (with the
  preselected profiles, if any), and each profile clicked in the 3D view while the panel is open is added to the list
  (clicking it again or deselecting removes it), updating the chain, its messages and the preview; editing an existing
  bar keeps working.

## Design notes (from exploration, see Log L3)
- Segments are the visible tips of each profile stack (Profile -> trims -> cutouts/holes); `_utils.py:174-228`.
- Corner geometry: each corner needs both segments in one plane and a tube wall parallel to the bend axis; the wall
  on the outside of the turn stays whole, so zig-zag chains are valid (each corner chooses its own wall).
- Developed length = flat lengths + sum of bend allowances theta*(r + K*t) per folded corner (configuration).
- Feature transfer: removed volume of each segment (base profile shape minus its tip) is moved rigidly into the
  straight frame, so holes, cutouts and open-end miters follow without knowing their type (precedent: drill hole
  profile-local snapshot, `drill_hole.py:442-444`).
- Folded shape: straight bar split at bend zones, segments moved back to the skeleton, bend zone = outer wall
  revolved by theta around the bend axis with inside radius r.
- Risks: TNP/renamed sketch edges (store per-segment snapshots, not face names); recompute order of a chain object
  that depends on N tips; BOM counts visible objects only (`create_bom.py:84-97`), tips must be hidden; `cut_ends`
  assumes one straight solid, the folded bar needs its own length/angles.

## T3 design (unfolded bar; parent derivation, L12)
Inputs: `folded_chain.Chain` (T2), a `BendConfiguration` (T1), inside radius per corner (S14: bar radius, optional
per-corner override), clearance g, key on/off, relief on/off, key diameter D, neck width N, relief radius rho (S20).
Per folded corner c between segments i, i+1: h = theta/2; t = tube wall thickness; r = inside radius;
e = signed distance from the path to the OUTSIDE face of the bent wall = (section center offset of segment i, perpendicular
to its path) . outer_normal + depth/2; OSSB = (r + t) tan h (outside setback); BA = theta_rad (r + K t).
- Straight frame: X along the bar, path of every segment on the X axis. Segment i maps rigidly with rotation R_i:
  R_0 takes direction_0 -> +X, x_axis_0 -> +Y, y_axis_0 -> +Z; R_{i+1} = R_i * inverse(Rotation(direction_i,
  direction_{i+1})). Path start of segment i at X_i: X_0 = 0; X_{i+1} = X_i + L_i + 2 e tan h - 2 OSSB + BA (outside
  mold line kept, S16). Bend zone of c on the outer wall: X in [T_c, T_c + BA], T_c = X_i + L_i + e tan h - OSSB.
- Corner frame (returned for each corner): origin at X = T_c on the outside face of the bent wall, w = 0 at the
  section center; u = +X, v = inward (= -R_i outer_normal), w = R_i axis. Cuts are 2D regions in (u, v) extruded
  through the whole tube along w; they never touch the bent wall (v < t).
- V notch: O_i = (0, r + t), O_{i+1} = (BA, r + t), m = (cos h, sin h), m' = (-cos h, sin h). Removed V = the region
  v >= t (up to past the inner wall) with (p - O_i).m >= -g/2 and (p - O_{i+1}).m' >= -g/2 (beyond both flanks;
  convex: clip a rectangle by two half planes). Flank i at height v is at u = -(v - r - t) tan h - (g/2)/cos h.
- Relief (on by default): remove the rectangle u in [0, BA], v in [t, t + rho] minus the discs of radius rho centered
  (0, t + rho) and (BA, t + rho): the curved relief next to the bent wall. Off: nothing more (pure V).
- Key (on by default): flank frame of segment i: origin O_i, x = m (into the V), y = (-sin h, cos h) (along the flank,
  inward); of segment i+1: origin O_{i+1}, x = (cos h, -sin h) (into its material), y = (sin h, cos h). Both get the
  same local key at flank coordinate s_k = (v_k - r - t)/cos h, v_k = middle of [t + rho (t without relief), depth - t]:
  bulb disc centered at x = D, neck rectangle from x = -g to x = D. Tab (kept on segment i) = bulb radius D/2 - g/2,
  neck N - g; socket (cut from segment i+1) = bulb radius D/2 + g/2, neck N + g. Removed = (V - tab) + socket + relief.
  A tab that would not fit inside the V of the flat bar, or a key room band v_k +- D/2 outside [t + rho, depth - t]
  (L13), is refused: "The key does not fit in the notch between {} and {}: make it smaller." (profiles in chain order).
- Bar body: a plane slice (normal to the path, mid length of segment 0) of the first segment's base profile, mapped,
  extruded from X_min to X_max: X_min of the mapped TIP of the first segment, X_max of the mapped TIP of the last one
  (L13: an End Miter with MiterExtend reaches past its base profile).
- Feature transfer: removed volume of each segment = base profile shape - tip shape (global), mapped by its rigid
  placement and cut from the bar; added volume = tip - base, mapped and fused (L13); the bar stays one solid:
  holes, cutouts and the end miters at the open corner and the free ends follow.
- Finally the bar is moved so that its X_min is 0 (S17: the bar starts at X = 0 at the open-corner end of the first
  segment). Developed length = X length of the bar.
- Checks: radius limits S15 (min t, max depth - 2t - D when the key is on, else depth - 2t): "The inside bend radius
  must be between {min:g} and {max:g} mm."; the configuration thickness must equal the tube wall thickness
  ("{config} is for {a:g} mm walls; {tube} has {b:g} mm walls.").

## T4 design (folded bar; parent derivation, L16)
The folded bar is rebuilt from the unfolded bar of T3, so both always hold the same cuts.
- `unfold` also returns, per segment, its rigid placement global -> straight (including the final shift to X = 0).
- Bend strip of corner c: the straight bar inside u in [0, BA], v in [0, t] of the corner frame (the bent wall in the
  bend zone, with the start of the side walls under it). It is replaced by its section at u = 0 (the bar cut by the
  plane u = 0, kept at v <= t), mapped to global by the inverse placement of segment i and revolved by +theta around
  the line through the bend center O (v = r + t, w = 0, at u = 0) with direction corner.axis (rotating d_i to d_i+1).
- The rest of the straight bar (minus every bend strip) is split per segment: at each corner c, segment i+1 owns the
  half space behind its nominal flank ((p - O_i+1).m' <= 0) clipped to u >= 0 (L17: past about 120 degrees, when
  BA < OSSB, that half space would reach back into segment i), and segment i everything else (its key tab included).
  Each part is mapped to global by the inverse placement of its segment.
- The folded solid is the fusion of the segment parts and the revolved strips, one valid solid where the skeleton was
  drawn (S16: the outside of the frame keeps its size; the outer corners are round, radius r + t).
- Checks: folded volume = unfolded volume + sum over corners of theta * (t/2 - K t) * area of the strip section
  (Pappus: the revolved strip has its centroid at r + t/2 from the axis, the flat one is BA long).

## T5 design (objects; parent, L18)
- `FoldedBar` (Part::FeaturePython, module `folded_bar.py`): `Segments` (LinkList, the selected objects in chain order,
  first = first selected), `OpenCorner` (LinkList of 0 or 2, the pair of S17), a copy of the bend configuration
  (`BendConfiguration` name, `Material`, `WallThickness`, `InsideRadius`, `KFactor`) so the document does not depend on
  the configurations file of the computer that opens it, `CornerRadii` (FloatList per corner in chain order, 0 = the bar
  radius, S14), `Clearance`, `Key`, `Relief`, `KeyDiameter`, `NeckWidth`, `ReliefRadius` (0 = the S20 default),
  read-only `DevelopedLength`; `execute` = `fold(...)` and refuses (error status with the ChainError / UnfoldError
  message) a result that is not one solid; it hides the segment tips and carries one PID, Family, SizeName, Material
  like a profile so the BOM and the cut list count it as one piece of `DevelopedLength` (S13).
- `UnfoldedBar` (Part::FeaturePython, same module): `FoldedBar` link; shape = the unfolded straight solid at the
  origin along +X (S4, S13); exported with FreeCAD's own export (STEP round trip test).
- S19: warn (console and BOM/cut list) when `DevelopedLength` exceeds the stock length configured for the cut list.

## Tasks
- T1 S6 S11 inline: bend configuration store (JSON, versioned, atomic save, validation) + API; tests. [x] c53e8b5
- T2 S2 S5 S17 S18 inline: chain builder from selected tips: order, corner angles, plane/wall checks, same section and
  material, folded/open per corner, clear error messages; tests. [x] f5f916c
- T3 S1 S3 S5 S6 S8 S9 S14 S15 S16 S20 worker: unfolded geometry: developed length, V notch at any angle, key, relief, feature transfer;
  tests (90 degree rectangle, arbitrary angles, holes moved, length per configuration). [x] 08711dc
- T4 S7 S14 S16 worker: folded geometry with real radius matching the skeleton; tests. [x] b267940
- T5 S2 S3 S4 S13 S19 inline: `FoldedBar` / `UnfoldedBar` objects: recompute, restore, hides tips, one PID, BOM and cut list as
  one piece; STEP export round trip test. [x] 47f071c
- T6 S1 S2 S6 S8 S9 S12 inline: commands and task panels (create folded bar with live preview, unfold, manage
  configurations); panel tests. [x] 68817bd
- T7 S1-S19 inline: Spanish translations, Russian strings left unfinished for the contributor, tutorial, changelog. [x] 5e2172f
- T8 S8 S15 S20 worker: clearance on the relief arcs; half-circle key centered on the miter line, no neck (geometry,
  FoldedBar property, panel field, translations, tutorial, changelog); tests. [x] 42c94aa
- T10 S15 S20 worker: the key at the middle of the miter line (relief arc to inner corner, L33), sliding to the
  nearest place where it fits; tests, tutorial, changelog. [x] af47317
- T11 S8 S20 S21 worker: relief always on with radius = inside radius of each corner: remove the Relief checkbox,
  the Relief radius field, the ReliefRadius / Relief properties and options, S21's check and message; tests, i18n,
  tutorial, changelog. [x] 4b19bbd
- T12 S15 worker: radius max per corner = (depth - t)/(1 - cos(theta/2)) - 2t, key not subtracted; large radii
  (bend axis outside the tube) verified to unfold and fold; tests, tutorial, changelog. [x] (see L41)
- T9 S22 worker: select-as-you-go Folded Bar command and panel like End Miter; tests, tutorial, changelog. [x] 383c696

## Log
- L1 (2026-11-11) "quiero analizar tener una feature que permita crear ingletes plegados (realizados con corte laser)
  similares a esto [Image#1] para esto me gustaria poder marmar una marco por ejemplo como este [Image#2] y luego poder
  crear las uniones en las esquinas (3 porque la cuata deberia estar abierta) luego poder desplegar (por eso queria
  analizar sheetmetal, para tomar ideas) el perfil para que quede como una unica barra con los cortes para poder
  enviarla a una maquina de corte laser de tubos cnc. Entiendes la idea? pros contras? comentarios?"
  Image#1: square tube, left flat with two V notches with bulb key and curved relief; right folded corner.
  Image#2: rectangular frame of four tube profiles with mitered corners.
- L2 (2026-11-11) "1. Lo aremos agnostico a la maquina o cam, usaremos los formatos de exportacion que maneja freecad,
  creamos el marco lo desplegamos (queda como una solido con cortes) exportamos, si en el futuro necesitamos un formato
  particular lo analizaremos llegado el caso.
  2. Angulos arbitrarios.
  3. Lo manejaremos con configuraciones (que se guarden).
  4. Radio real."
- L3 Exploration (gentle-ai-explore): Profile `profile.py:89`, TrimmedProfile joints `trimmed_profile.py:264,401-419`,
  meeting ends `miter_geometry.py:168-177`, DrillHole local snapshot `drill_hole.py:442-444`, BOM visibility
  `create_bom.py:84-97`, PID `populate_ids.py:152-218`, JSON store `library_manager.py:182-350`, no export code in
  the package, `find_joints` `miter_joints.py:38-82` (no ordered chain walker).
- L5 (2026-11-11) "1. Olgura manejemos una solo configurable (como hacemos con el corte en inglete), llave y alivio
  activado y desactivables. El radio de la esquina tambien debe ser configurable, con limites minimos (teniendo en
  cuenta el espesor) y maximos (teniendo en cuenta el perfil).
  2. si.
  3. si.
  4. si
  5. si.
  ya es tarde, arrancaremos con la implementacion mañana. Si es necesario ahora podemos seguir refinando el diseño."
- L6 (2026-11-11) "deacuerdo" (to proposals Q1-Q6, now S14-S19).
- L4 Research: SheetMetal is an external addon (LGPL 2.1); ideas taken: K-factor bend allowance, bend relief, unfold
  as a derived parametric object. Its unfolder is not used: the bar is unbent, not flattened.
- L7 (2026-11-12) "si" (start the implementation: branch, task document commit, T1).
- L8 T1 evidence: `freecad/maxproframe/bend_config.py` stores configurations in
  `<user profiles dir>/.bend/configurations.json` (hidden folder, so the library list never shows it), version 1,
  atomic replace; radius >= thickness, 0 <= K <= 1; last used in param `LastBendConfiguration`.
  `tests/test_bend_config.py`: RED (module missing, exit 1), GREEN 16 tests on FreeCAD 1.1.4.
- L9 T2 evidence: `freecad/maxproframe/folded_chain.py` `build_chain(selection, open_corner=None)` -> `Chain`
  (segments with path start/end, direction, section axes, size; corners with bend angle = path turn, axis, outer
  wall normal, depth across the bent wall). Decisions within S17: a closed frame opens where the first and the last
  selected profiles meet, else at the path start of the first one; an open chain must start at a free end of the first
  selected profile; open corners only on closed frames (more would split the bar). S18 continuity is physical:
  section center offset and axes rotated by the fold must match (square tubes may swap axes).
  `tests/test_folded_chain.py`: RED (module missing), GREEN 23 tests on FreeCAD 1.1.4. S12 (own miter at a folded
  corner) stays in T6 as planned.
- L10 Review slices: the branch passed ~400 lines with the spec document; slices are the work-unit commits
  (36e6ff8+c53e8b5 store, f5f916c chain). Push/PR is the user's decision.
- L11 (2026-11-12) "editables" (to the proposal: V flanks back half the clearance, relief radius = inside radius,
  bulb key 1/4 of the depth with 60 % neck at mid height of the V, sizes editable on each bar), now S20.
- L12 T3 design derived by the parent (section "T3 design"); T3 is delegated to a worker (context backstop).
- L13 T3 worker questions answered by the parent: the key room check uses the band v_k +- D/2 (the D of S15/S20),
  plus the real tab inside the V; the bar ends come from the tips and the added volume (tip - base) is fused, so an
  End Miter with MiterExtend reaches its miter (S17); key message "The key does not fit in the notch between {} and
  {}: make it smaller.".
- L14 T3 evidence (worker, re-run by the parent): `freecad/maxproframe/unfolded_geometry.py`
  `unfold(chain, configuration, radius=None, corner_radii=None, clearance=0.0, key=True, relief=True, key_diameter=None,
  neck_width=None, relief_radius=None)` -> `UnfoldedBar(shape, length, corners)`; `UnfoldError(ValueError)`;
  `folded_chain.section_offset` made public. Bar ends: reference = base profile plus the bar section stretched 1 mm past
  each end, so the tip's end cuts are exact. R_0 = Rotation(direction, x_axis, y_axis, "XYZ"). RED (module missing),
  GREEN 15 tests (parent re-run /tmp/mpf-t3-check), test_folded_chain 23 OK. Open for T5: a boolean that yields more
  than one solid returns the compound (check it in the object); base-profile bevels only set the bar extent; no 3D chain
  or Part container test yet.
- L15 Full suite on FreeCAD 1.1.4 at f5f916c (T2): 1727 tests OK (job-2, 22 min).
- L16 T4 design derived by the parent (section "T4 design"); T4 delegated to a worker (context backstop).
- L17 T4 evidence (worker, re-run by the parent): `freecad/maxproframe/folded_geometry.py` `fold(chain, configuration,
  **unfold options)` and `fold_bar(chain, unfolded)`; `UnfoldedBar.placements` (global -> straight per segment).
  RED (module missing; placements attribute missing), GREEN test_folded_geometry 10, test_unfolded_geometry 16,
  test_folded_chain 23 (parent re-run: 10 and 16 OK). Deviations: the split half space is clipped to u >= 0; the Pappus
  volume test runs with the relief on (with it off, the rigid side walls next to the bent wall overlap the revolved
  strip) and subtracts the overlap of the plain tips at the open corner. Open: with the relief off, past
  acos(r / (r + t)) (about 53 degrees of half angle, 106 degrees of bend for r=3 t=2) those side walls stick out of the
  round outer corner: decision asked to the user. Commit b267940.
- L18 T5 design written by the parent (section "T5 design"); T5 delegated to a worker. Decision: the bar keeps a copy
  of its bend configuration (portable documents).
- L19 T5 worker questions answered by the parent (design additions): `Material` = the tube's profile material, the
  configuration's material in `BendMaterial`; BOM row: angles and Ends "", Drill/Cutout "Yes", weight and price =
  first profile's LinearWeight / UnitPrice x DevelopedLength / 1000; UnfoldedBar and the pieces folded into a bar are
  not counted (also outside App::Part); `Segments` stores the tips; S19 = console warning on recompute and on the BOM
  row (param "Stock Length", default 6000, read from create_bom_tool's param). Pre-existing: best_fit raises
  "Can't fit" for any piece longer than the stock.
- L20 T5 evidence (worker): `freecad/maxproframe/folded_bar.py` (FoldedBar, UnfoldedBar, make_folded_bar,
  make_unfolded_bar), `_utils.py` (is_foldedbar, is_unfoldedbar, piece_stack, folded_into_bar), `create_bom.py`
  (FoldedBar row), `populate_ids.py` (DevelopedLength key), icons. RED (module missing; then 3 failures: moved Part
  117 mm off, tips visible after reopen), GREEN test_folded_bar 20; 13 BOM / cut list / PID modules OK. Open for T6:
  Create BOM / Populate IDs do not accept a FoldedBar selected directly; relink Segments when a cutout or trim is added
  to a segment later; balloons with a FoldedBar untested; folded_into_bar walks InListRecursive per object.
- L21 (2026-11-12) "apagado", then to the clarification "Con "apagado" no me queda claro..." the choice "Rechazar la
  esquina" (refuse the corner past the widest bend without relief), now S21. Evidence: `_Bend.check_relief` in
  `unfolded_geometry.py`; RED (UnfoldError not raised), GREEN test_unfolded_geometry 18, test_folded_geometry 10
  (its 135 degree test keeps the relief on now), test_folded_bar 20 (its relief-off step goes back to a 4 mm radius).
- L22 Full suite on FreeCAD 1.1.4 with T5 (before S21): 1773 tests OK (job-3). Commits: T5 47f071c, S21 2e2f872.
- L23 T6 evidence (worker): `create_folded_bar_tool.py` (Folded Bar command and panel with live preview, edit on
  double click, Unfold Bar), `bend_config_dialog.py` (Bend Configurations dialog), `folded_chain.cuts_at_folds` (S12:
  "{trim} cuts {profile} at its folded corner with {other}: delete it or make that corner the open one." / "...:
  delete it." on an open chain), `folded_bar.check_settings`, `FoldedBar._follow_tips` (Segments follow the current
  tips; a tip not recomputed yet is recomputed first), Create BOM / Populate IDs accept a FoldedBar, new toolbar and
  menu "Folded Miters" (toolbox_folded). RED (modules missing; bar before the new hole), GREEN test_folded_bar_panel
  31, test_bend_config_dialog 12, test_folded_bar 21, plus 10 related modules OK. Open for T7: add the 3 commands to
  test_toolbar_translations EXPECTED and toolbox_folded to test_workbench_commands TOOLBARS; translate() the
  bend_config validation messages; Reset IDs does not accept a FoldedBar; S12 is checked in the panel only.
- L24 Full suite with T6: 1 failure, test_shortcuts (the 3 new commands were not in its scheme); added them to
  WITHOUT_SHORTCUT (no shortcut requested), test_shortcuts 5 OK. T6 commit 68817bd.
- L25 T7 evidence (worker): 90 entries per catalog (Spanish translated in maxproframe_es.ts / frameforge_es.ts, .qm
  recompiled; Russian unfinished in maxproframe_ru.ts), bend_config.py messages through translate() (English
  unchanged), Reset IDs accepts a FoldedBar, docs/tutorial.md "Folded miters", README bullet, CHANGELOG Unreleased.
  Approved deviation: tests/test_russian_translation.py lists the unfinished folded-miter texts explicitly and checks
  they show in English with FreeCAD in Russian. Property tooltips (App::Property) and undo names stay English like the
  rest of the repo. Full suite with T7: 1826 tests OK. Commit 5e2172f.
- L26 (2026-11-12, after PR #145 merged, with two screenshots of the Folded Bar panel: key off / relief on, and key
  10 mm / relief on with the key near the inner corner) "temas a mejorar:
  - La olgura debe aplicarce tambien al corte delcirculo de la esquina.
  - La llave debe ubicarce al centro de la linea del bisel y debe ser solo un medio circulo (sin cuello).
  - Me gustaria que el comando se comporte como el de corte en bicel, aprieto el boton y voy seleccionado perfiles."
  -> S8, S20 rewritten, S22 added, T8-T9 opened.
- L27 T8 decision (parent, from the worker's question): with the default relief radius = r the kept relief disc is
  concentric with the bend axis and its arc folds onto the inner face of the bent wall, which has no cut face and does
  not move; moving the arc back only g/2 would leave g/2 there. Chosen: kept disc radius rho - g, so the clearance seen
  along the arc equals the clearance between the flanks (S8 reworded).
- L28 T8 decision (parent, from the worker's question): with the key at the middle of the miter line, large inside
  radii push that middle into the bend/relief zone (90 degrees, 50x50x2: the key fits up to about r = 19.5 while S15
  allows 33.5). S15 stays as is; check_key refuses the key, with a distinct message when the radius is the cause:
  "The key does not fit in the notch between {} and {} with this inside radius: make the radius smaller or turn the
  key off."
- L29 T8 evidence (worker): `unfolded_geometry.py` (relief discs rho - g; half-circle key by `_cut_disc`, center at
  `_key_along`, tab d/2 - g/2 from x >= -g/2, socket d/2 + g/2 from x >= 0; check_key: tab size, no room (new message),
  socket band, tab in V; neck removed), `folded_bar.py` (NeckWidth gone), `create_folded_bar_tool.py` (Neck width field
  gone), es/ru catalogs + 16 Spanish .qm recompiled with compile_translations.py, tutorial, changelog. RED: 4 in
  test_unfolded_geometry, 1 test_folded_geometry, 1 test_folded_bar, 2 test_folded_bar_panel. GREEN:
  test_unfolded_geometry 22, test_folded_geometry 11, test_folded_bar 22, test_folded_bar_panel 32,
  test_russian_translation 6, test_toolbar_translations 4, test_workbench_commands 2, test_folded_bar_translations 5,
  test_compile_translations 3. Known: largest radius taking the key at 90 degrees on 50x50x2 is about 19.97 mm.
- L30 T9 evidence (worker): `create_folded_bar_tool.py` (IsActive needs only a document; panel opens at once with the
  preselection and observes the selection; click adds at the end, Ctrl+click / deselect removes; non-tube and other
  document ignored; a trim/cutout of a listed profile takes its place; click on the preview maps to the nearest listed
  piece; preview dropped and tubes shown when the pieces no longer fold; observer removed in clean() from accept,
  reject, closed and form-destroyed; edit mode like End Miter: selection does not change the segments). Tooltip
  "Click two or more ..." (es "Hacé clic en dos o más ...", ru unfinished, .qm recompiled), tutorial, changelog.
  Deviations from End Miter: a replacing piece keeps its list position; duplicate preselection silently de-duplicated.
  RED: test_folded_bar_panel 11 failures + 3 errors in the new tests. GREEN: test_folded_bar_panel 43,
  test_folded_bar 22, test_folded_bar_translations 6, test_russian_translation 6, test_compile_translations 3,
  test_workbench_commands 2, test_end_miter_panel 14; test_toolbar_translations 4 after the parent updated its
  Spanish tooltip expectation. Slice note: T9 (~600 lines, mostly tests) is its own commit past the ~400 slice.
- L31 Full suite on FreeCAD 1.1.4 with T8-T9: 1844 tests OK in 1170 s (`ci/run_tests.py --timeout 2400`; the default
  180 s timeout is too short for the whole suite locally).
- L32 (2026-11-12, screenshot: TC80x40x1.5 bent across its 40 mm side, r = 25, key 8 mm, clearance 0.5, refused
  with the no-room message) "porque dice que la llave no entra ? si el tubo tiene 40mm ?" Explained: the middle of the
  miter line (outer contour of the bend to the inner corner) is 3.7 mm outside the bend axis, inside the bend; the
  straight flank is only 40 - 1.5 - 25 - 1.5 = 12 mm deep; with the middle rule the 8 mm key fits only up to
  r = 16.5. To the question "Donde va la llave cuando el medio del bisel cae dentro del doblez (radios grandes)?" the
  user chose "Correrla al lugar más cercano donde entre (Recomendado)" -> S20 updated, T10 opened.
- L33 (2026-11-12, screenshot of the folded 80x40x1.5 corner with the miter line measured: 43.84 mm from the relief
  arc gap to the inner corner) The side wall goes on below the bend axis inside the kept relief disc, so the miter line
  runs from the relief arc to the inner corner (about 43.6 mm by formula for r = 25, g = 0.5), not from the outer
  contour; the key goes at the middle of THAT line (about 21.9 mm from each end) and fits there in the user's case; it
  slides (L32) only when it does not fit at that middle. T10 worker steered with this correction.
- L34 T10 evidence (worker): `unfolded_geometry.py` (`miter_line`: before flank moved back g/2 from where it leaves
  the relief, or the bottom of the V without relief, to v = depth; key at its middle; `_key_fits` with real 2D shapes
  (below the inner wall, above the bent wall, tab in the V, clear of the relief cut); `_fitting_along` bisection slides
  it; refusals unchanged in wording). User's case 80x40x1.5, r 25, d 8, g 0.5: line 43.840 mm (user measured 43.84),
  middle 2.58 mm below the axis point, no slide. S15 max 33.5 accepts the key again. Removed tests that asserted old
  refusals (key over a 20 mm relief; 60/135 degree 42 mm key). RED (base code): test_unfolded_geometry 1 failure +
  4 errors, panel 1; GREEN: test_unfolded_geometry 24, test_folded_geometry 11, test_folded_bar 22,
  test_folded_bar_panel 43, test_folded_bar_translations 6, test_russian_translation 6. Known: the no-room message is
  now reached only with extreme clearances.
- L35 Full suite on FreeCAD 1.1.4 with T10: 1846 tests OK in 1179 s.
- L36 (2026-11-12, screenshot: inside radius 20, relief radius 10 leaves a crescent void at the folded corner) "no
  entiendo cual es la funcion de esa configuracion, eso no deberia ser un calculo interno en base al radio seteado?"
  Explained: only relief radius = inside radius keeps the kept disc concentric with the bend axis. To the proposal to
  remove the field: "sacalo y la casilla tambien, no le veo sentido a desactivar el alivio" -> S8, S20 updated, S21
  dropped, T11 opened.
- L37 (2026-11-12) "no corras la suite (para no perder tiempo esperando), lo pruebo y vemos si tenemos que ajsutar
  algo" -> after T11 only the worker's focused modules run; the full suite is skipped until the user's manual test.
- L38 T11 evidence (worker): relief always cut, rho = corner radius in `_Bend.relief_region`; removed relief /
  relief_radius (unfolded_geometry, folded_bar options and properties, panel checkbox and field), S21 check and
  message, 4 catalog texts (es/ru, .qm recompiled), tutorial, changelog. RED: test_unfolded_geometry 3, test_folded_bar
  1, test_folded_bar_panel 2, test_folded_bar_translations 1, test_russian_translation 1. GREEN: test_unfolded_geometry
  24, test_folded_geometry 11, test_folded_bar 23, test_folded_bar_panel 43, test_folded_bar_translations 6,
  test_russian_translation 6, test_compile_translations 3, test_toolbar_translations 4. Differential vs 3a53d20:
  8 default cases, 16 solids identical (symmetric difference 0). Full suite skipped (L37).
- L39 (2026-11-12, screenshot: TC80x40x1.5 across 40, radius 30 refused "between 1.5 and 27 mm" while the key fits
  in the preview) "Porque dice que el radio maximo es 27?" Explained: 40 - 2*1.5 - 10 (default key), an S15 rule from
  before the key could sit in the relief disc; proposed max = depth - 2t (37). User, with a screenshot of a bent tube
  with its outer arc R 130 tangent to the walls: "El calculo esta mal ... el limite deberia ser el radio maximo
  tangente a las paredes - 2 espesores aproximadamente" -> outer arc tangent at most where the inner walls start
  (outer radius = depth), inside radius max = depth - 2t = 37 for this tube; S15 rewritten, T12 opened. Full suite
  still skipped (L37).
- L40 (2026-11-12) "espera esa imagen que te mande son 2 tubos de 40x40 a 90º y el radio es de 130mm porque no
  podria crear un corte asi?" -> the limit is not depth - 2t: the bend can be much larger than the tube as long as
  the inside of the bent wall passes outside the inner corner; S15 rewritten (L40 formula), T12 worker steered.
- L41 T12 evidence (worker): `_Bend.check_radius` max = (depth - t)/(1 - cos(theta/2)) - 2t per corner, rounded
  down to 0.1 mm (RADIUS_STEP); 50x50x2 90 deg 159.8, 40x40x1.5 90 deg 128.4, 80x40x1.5 across 40 accepts r = 30
  with the default key. r + t > depth unfolds and folds (one valid solid each, outer arc r + t, sharp inner corner,
  inner walls whole) with no other code change. At the max radius check_key refuses the key ("with this inside
  radius"). RED: test_unfolded_geometry 3 F + 4 E, test_folded_bar 1, panel 1, translations 1. GREEN:
  test_unfolded_geometry 28, test_folded_bar 24, test_folded_bar_panel 43, test_folded_bar_translations 6,
  test_folded_geometry 11, test_russian_translation 6. Full suite skipped (L37). OPEN: two bends overlapping on a
  short tube (2(r + t) longer than the tube) are not refused: the unfolded bar comes out as 2 solids and the folded
  one is wrong (50x50x2 rectangle with 200 mm sides from r = 130); pre-existing check gap, reachable now.

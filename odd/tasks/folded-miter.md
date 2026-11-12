# Folded miters (V-notch tube folding) and unfolded bar
A chain of tube profiles is joined by folded corners (laser V-notch with key and relief, outer wall bent with a real
radius) and unfolded into one straight solid with every cut, exported with FreeCAD's own formats for a CNC tube laser.
Status: implementing (T1 done). Branch: `feat/folded-miter`.

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
  (`trimmed_profile.py:502`: half of it on each side of the cut), applied to the notch flanks and the key; the key and
  the relief are on by default and each one can be turned off.
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
- S15 Radius limits (S9): min = t (wall thickness); max = depth of the tube across the bent wall - 2t - room for the
  key (the relief and the bend zone eat the side walls from the bent wall inward).
- S16 Reference: profiles stay where drawn; the fold rounds the outside corner inside the virtual sharp, so the outer
  dimensions of the frame do not change (outside mold line, like sheet metal).
- S17 Open corner and start: a closed loop needs at least one open corner; its ends keep their own End Miter (part of
  the segment tips, moved to the unfolded bar like any other cut). The unfolded bar starts (X = 0) at the open-corner
  end of the first selected segment.
- S18 Continuity: consecutive segments must be the same tube with the same section orientation and anchor across each
  fold; in a 3D chain each bend axis must be parallel to a wall pair of the tube; otherwise the panel explains why.
- S19 Stock: warn when the developed length exceeds the stock length configured for the cut list.

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

## Tasks
- T1 S6 S11 inline: bend configuration store (JSON, versioned, atomic save, validation) + API; tests. [x] c53e8b5
- T2 S2 S5 S17 S18 inline: chain builder from selected tips: order, corner angles, plane/wall checks, same section and
  material, folded/open per corner, clear error messages; tests. [ ]
- T3 S1 S3 S5 S6 S8 S9 S14 S15 S16 inline: unfolded geometry: developed length, V notch at any angle, key, relief, feature transfer;
  tests (90 degree rectangle, arbitrary angles, holes moved, length per configuration). [ ]
- T4 S7 S14 S16 inline: folded geometry with real radius matching the skeleton; tests. [ ]
- T5 S2 S3 S4 S13 S19 inline: `FoldedBar` / `UnfoldedBar` objects: recompute, restore, hides tips, one PID, BOM and cut list as
  one piece; STEP export round trip test. [ ]
- T6 S1 S2 S6 S8 S9 S12 inline: commands and task panels (create folded bar with live preview, unfold, manage
  configurations); panel tests. [ ]
- T7 S1-S19 inline: Spanish translations, Russian strings left unfinished for the contributor, tutorial, changelog. [ ]

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

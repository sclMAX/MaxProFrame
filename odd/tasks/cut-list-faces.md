# Cut list: grouped pieces, cut face and end orientation
The Cut List groups identical pieces of one stock bar, and every cut angle (Cut List and BOM) tells on which face of the profile it is seen and how both ends sit, computed from the finished solid. Branch: `feat/cut-list-faces`; base: `c40f561`.
Delivery: work-unit commits on the feature branch; push, PR and merge are the user's decision. Tests: native FreeCAD 1.1.4 (`python3 ci/run_tests.py --freecad-bin .freecad-test/demo-video/squashfs-root/AppRun --reports $(mktemp -d) --target stable --test <module>`).

## Specs

- **S1 — Group identical pieces inside a stock bar.** User: "revisemos como se crea la lista de cortes, deberiamos agrupar pertiles iguales?" Accepted proposal (L2): "Juntar en una fila las piezas iguales de la misma barra (mismo ID, largo y ángulos), con `Quantity = N`." and "No juntaría piezas de barras distintas". Today `make_cut_list` writes one row per piece with Quantity 1 (`create_bom.py:248-316`); the same ID on two bars stays one row per bar.
- **S2 — Face of the cut.** User: "Deberiamos indicar sobre que cara va el corte? por ejemplo si tengo un tubo de 80x40 con corte a 45º, los 45º van sobre los 80 o sobre los 40 ?" Notation chosen by the user: "me parece bien \"<80\"". Each end angle is written `45.0 <80`, where 80 is the size in mm of the profile face on which the angle is seen (the cut runs across the 80). A square end stays `0.0`. A compound end (tilted on both faces) gives both: `45.0 <80 + 10.0 <40`. Applies to the CutAngle1/CutAngle2 columns of the Cut List and of the BOM.
- **S3 — End orientation.** Accepted proposal (L2): "una columna \"Extremos\" con `\_/`, `/_/` o `|_/`". `\_/`: both ends tilted on the same face in opposite directions (trapezoid, frame miter); `/_/`: tilted the same way (parallelogram); `|_/`: one end square. Ends tilted on different faces or compound, or both ends square: no symbol (empty).
- **S4 — Computed from the finished solid.** Accepted proposal (L2): "Tomar la cara de cada extremo y proyectar su normal sobre los ejes locales del perfil (ancho y alto). Así se obtienen el ángulo, la cara y el sentido, igual para un bisel, un trim, un inglete o un Extend/Cut". Works for profiles with bevels, TrimmedProfile (miter, Extend/Cut, trims), and ExtrudedCutout, inside App::Part containers too. An end that is not one flat cut (notch, "Perfect Cut") keeps today's mark (`@ P` / `?`).
- **S5 — Legend.** The Cut List legend says "~" for angles from a TrimmedProfile while the code prints "@" (`create_bom.py:310`); the "-" symbol is documented but never printed. The legends of the Cut List and the BOM describe exactly the marks that are printed, including `<` and the Ends column.

Out of scope (L2, for later): merging the same profile from different libraries into one stock, number formatting (comma vs point), "×2 barras" for identical bars, the stored `CuttingAngleA/B` properties of the objects.

## Design (parent, binding for T1-T2)

- **Frame.** `source = profile_source(obj)` (`populate_ids.py:151`); no profile source -> fall back. Bring `obj.Shape` into the source container frame with `trimmed_profile.in_frame_of(source, obj, shape)`, then into the profile local frame with `source.Placement.inverse()`. There X = width, Y = height, Z = axis; end 1 = Z min (start, today's CutAngle1), end 2 = Z max.
- **Face sizes.** From the source section, not properties: slice the source profile shape (local frame) at its mid Z; W = section BoundBox XLength, H = YLength, printed with `:g`-style trimming (80, 40, 1.5 -> "80", "40"; use `f"{v:.1f}".rstrip("0").rstrip(".")`). Section area = that slice's area.
- **End face.** Per end: the planar faces (`Part.Plane`) whose local normal has |nz| > 1e-6 and whose BoundBox reaches the end extreme Z (tol 1e-6 relative to length, at least 1e-6 mm). Exactly one plane (several faces on one coplanar plane are fine) and projected area `sum(face.Area) * |nz|` equal to the section area (rel tol 1e-4) -> a single flat cut; anything else (notch, step, cutout eating the end, Perfect Cut) -> fall back to today's `CuttingAngleA/B` string for that piece and empty Ends.
- **Angles.** Normal n oriented outward by Z sign (end 1: nz < 0, end 2: nz > 0). Angle seen on the faces of size W = `degrees(atan(|nx|/|nz|))`; on the faces of size H = `degrees(atan(|ny|/|nz|))`. A value under 0.05 counts as 0. Strings: both 0 -> `0.0`; one -> `45.0 <80`; both -> `45.0 <80 + 10.0 <40` (W part first). Round families (`Family in ("Round Bar", "Pipe")`): single angle `degrees(acos(|nz|))`, no `<`.
- **Ends.** Both ends tilted on the same single face (both W-only or both H-only): compare the outward normal component on that axis; same sign -> `\_/` (trapezoid), opposite sign -> `/_/` (parallelogram). Exactly one end square and the other tilted on one face -> `|_/`. Otherwise empty. (Derivation: start plane z = kx with solid z > kx has outward (k,0,-1); end plane z = L - kx gives outward (k,0,1): same sign = trapezoid.)
- **Wiring.** `traverse_assembly` keeps `p["obj"] = obj` and fills `cut_angle_1/2` and a new `ends` from `cut_ends`; `group_profiles` keys include `ends`. BOM gets an `Ends` column after CutAngle2; Cut List gets `Ends` after CutAngle2. Cut List: inside each stock bar, rows with same ID, length, angles and ends become one row with Quantity = count, first-seen order kept. Legends list exactly the printed marks (`<`, `+`, `\_/`, `/_/`, `|_/`, `@`, `P`, `?`); drop `-` and `~`, and `*` if no longer printed.

## Tasks

- **T1 [S2, S3, S4] delegated, done.** Commit: f860601. New `cut_ends.py`: per piece, find the planar end faces of the finished solid at each end of the source profile axis, express their normals in the profile local frame (X = width W, Y = height H, Z = axis), return angle + face size per end and the end orientation. Tests with fixtures: beveled profile on each face, miter (TrimmedProfile), Extend/Cut, cutout, profile in a placed App::Part, notch → falls back. Evidence: `tests/test_cut_ends.py` 14 tests OK (RED on the stub returning CuttingAngleA/B).
- **T2 [S1, S2, S3, S5] delegated, done.** Commit: 78818c5. `traverse_assembly` keeps the object; BOM and Cut List write the new angle strings and an `Ends` column; Cut List groups identical pieces of one bar; legends rewritten. Tests through `make_bom`/`make_cut_list` reading the spreadsheet. Evidence: `tests/test_cut_list.py` 7 tests OK (RED on the old sheets); test_reset_ids, test_combined_bevel_angles, test_populate_identical_pieces, test_custom_profile_grouping, test_catalog_family_profiles, test_populate_derived_pid, test_extend_cut_geometry, test_end_miter_geometry, test_notch_geometry, test_qt_wrapper_lifetime OK.
- **T3 [S1-S5] delegated, done.** Commit: see git log (docs: cut angle faces, Ends and grouping). Tutorial (`docs/tutorial.md` BOM/Cut List section), CHANGELOG. Evidence: About Angles / Ends section rewritten, `* Unreleased` entry.

Review slices: (1) f860601 cut_ends + tests, ~304 lines; (2) 78818c5 + the docs commit BOM/Cut List wiring, tests and docs, ~295 lines.

## Log

### L1 — Original request (verbatim)
revisemos como se crea la lista de cortes, deberiamos agrupar pertiles iguales? Deberiamos indicar sobre que cara va el corte? por ejemplo si tengo un tubo de 80x40 con corte a 45º, los 45º van sobre los 80 o sobre los 40 ?que opinas?
(two screenshots: a Cut List where identical pieces 10, 11, 1, 4 take one row each with Quantity 1 and most angles are "@ 45.0" / "@ 4.0"; a BOM of the same model)

### L2 — Accepted proposal (assistant, previous turn), and the user's answer
Proposal: group inside each bar only; write the face as `45° ∠80` and an "Extremos" column with `\_/`, `/_/` or `|_/`; compound end `45°∠80 + 10°∠40`; compute everything from the finished solid by projecting the end face normal on the profile local axes; fix the legend ("~" vs "@"). Left for later: one stock for the same profile from different libraries, number formatting, "×2 barras".
User: me parece bien "<80"

### L3 — Exploration evidence
`profile.py:1193-1195` section in local XY, extruded along local +Z; `W = ProfileWidth` is the X extent, `H = ProfileHeight` the Y extent (`profile.py:468-469`); bevel `*CutY` rotates about local Y (angle seen on the faces of size W), `*CutX` about local X (faces of size H) (`profile.py:1203-1219`). Profile shape is in its container frame; trim/cutout shapes are baked with identity placement (`trimmed_profile.py:584-590`, `extruded_cutout.py:271-282`). No test calls `make_bom`/`make_cut_list` today. `CutPart.obj` is the per-piece dict (`best_fit.py:1-6`).

### L4 — Worker decisions accepted by the parent
`*` stays in the legends: a fallback piece beveled on different faces still prints it. End 1 is the Z-min end of the profile, so a miter or Extend/Cut at the start of the sketch edge now shows in CutAngle1 (before, trims always went to CutAngle2); noted in CHANGELOG and tutorial. A notch that leaves one flat square end now prints `0.0` instead of `@ P`. BOM columns after CutAngle2 move one to the right (Ends is H). Not tested: a trim in another container than its source profile.

### L5 — Native review follow-up (user chose option 1: "1")
Review of f860601..8721aae approved with advisories. Fixed: Cut List grouping merged pieces without ID of equal length and angles (they now keep one row each, RED observed: Quantity '2' vs two rows of '1'); unused `p["obj"]` removed; tutorial says which pieces keep the old marks.

# Profile Pattern
New command that repeats a selected piece as Links along a frame edge: count + pitch (one side, inverted or
symmetric) or a count distributed between two faces with equal gaps; editable afterwards, counted by the BOM.

## Specs
- S1 Command: "tengo que hacer una mesa la cual lleva 20 perfiles como el que esta seleccionado, seria bueno tener un
  comado que permita hacer un patron de perfiles asi selecciono uno y pongo cantida y paso para que se coloquen todos lo
  que necesito" -> a new MaxProFrame command: select one piece (profile, trimmed profile, cutout or drill hole), set the
  count and the pitch, and the copies are placed.
- S2 Copies: "1. A." -> option A of L2: the copies are App::Link objects to the selected piece: light, a change to the
  original (section, trims, cutouts, holes) shows on every copy, and the BOM / Cut List / Piece Table count them as
  pieces of the original with the same ID.
- S3 Direction: "2. ok con posibilidad de invertir." -> the direction is given by clicking a straight edge (e.g. of the
  frame); the sense can be inverted.
- S4 Spacing: "3. Cantidad + paso y repartir entre caras." -> two modes: (a) count + pitch (center to center);
  (b) distribute between two faces: the user picks two planar faces and a total count; the pitch follows.
- S5 Distribute: choice "Entre dos caras, original incluida" and "Mismo hueco" (L5) -> in mode (b) the count includes the
  original; all pieces, the original too, end up between the two faces with equal free gaps between the pieces and
  between each face and its nearest piece; the original is moved (by its own offsets) to its slot.
- S6 Invert / symmetric: "4. Invertir y simetrico (para hacer un patron en ambos sentidos  Patron <- (pieza) -> Patron."
  -> in mode (a) the copies go in the edge's sense, in the inverted sense, or symmetric: the count of copies on each side
  of the original.

## Tasks
- T1 S2 S4 S5 S6 pattern object: parametric object holding the source piece, direction edge, mode, count, pitch, faces,
  invert / symmetric, generating the Links and moving the original in mode (b) — worker — commit: pending
- T2 S1 S3 command + task panel with preview (select piece, click edge, click faces, fields, OK one Undo step, Cancel
  leaves nothing), double-click edit, BOM / Cut List / Piece Table count, icon, toolbar, ES translations, shortcuts
  scheme, CHANGELOG and tutorial — worker — commit: pending

## Log
- L1 (user): "mientras tanto quiero analizar una feature que me aria falta, [Image#6] tengo que hacer una mesa la cual lleva 20 perfiles como el que esta seleccionado, seria bueno tener un comado que permita hacer un patron de perfiles asi selecciono uno y pongo cantida y paso para que se coloquen todos lo que necesito. Que opinas?" (screenshot: Part with a rectangular TC80x40x1.5 frame and one Profile_PGC100_000_Tr_Tr custom-profile slat trimmed between the long sides, selected)
- L2 (agent proposal): command "Patrón de perfiles"; A) copies as Links to the original (light, changes propagate, same ID in the BOM; identical copies, fit for parallel frames) or B) independent profiles each trimmed to the frame; direction by clicking an edge of the frame (or X/Y/Z); count + pitch, later "distribute between two faces"; the selected piece is the first, with an invert option; editable by double-click; one Undo step.
- L3 (user): "1. A. 2. ok con posibilidad de invertir. 3. Cantidad + paso y repartir entre caras. 4. Invertir y simetrico (para hacer un patron en ambos sentidos  Patron <- (pieza) -> Patron."
- L4 (agent question): distribute between faces — original fixed with copies up to one face, or all pieces between two faces with the original included and moved; last piece touching the face or same gap.
- L5 (user): "Entre dos caras, original incluida" and "Mismo hueco".
- L6 (decision): symmetric applies to mode (a); mode (b) already spreads both ways. Moving the original in mode (b) uses its section offsets, so the direction has to lie across the piece (perpendicular to its axis); otherwise the panel explains why mode (b) is unavailable. Gaps are measured between the pieces' extents along the direction (their shape), not their centers.
- L7 (worker, T1+T2): RED observed: test_profile_pattern 14/16 failed against a do-nothing object stub; test_profile_pattern_ids 6/9 failed with the object in place but BOM / Populate IDs unchanged (the Piece Table and the two attached-link preserve cases already passed); test_profile_pattern_panel 11/12 failed against a do-nothing panel stub. GREEN observed: test_profile_pattern 18/18 (2 restore / drill hole cases added after), test_profile_pattern_ids 9/9, test_profile_pattern_panel 13/13. PRESERVE: test_shortcuts 5, test_toolbar_translations 4, test_workbench_commands 2, test_cut_list 27, test_piece_table 23, test_balloons 32, test_version_property 4, test_compat_regression 9, test_populate_ids_count 3, test_populate_identical_pieces 10, test_populate_derived_pid 6, test_populate_ids_prefix 7, test_populate_ids_panel 24, test_reset_ids 18, test_populate_ids_translations 3, test_compile_translations 2, test_workbench_translation_loading 2, test_cutout_container_links 3, all OK; populate_ids_count/prefix/panel first caught a regression (copies resolved by Name on duck-typed pieces, and duplicates dropped), fixed by resolving only copies. Differential (base commit vs change, document without patterns: selection lists, document lists, BOM rows, Populate IDs in three modes, set_profile_pid, makeLink properties): identical. .qm rebuilt with the AppImage lrelease (650 messages), maxproframe_es.ts and frameforge_es.ts identical. Uncommitted (worker may not commit).
- L8 (decision, worker): copies are MaxProFrame Links (makeLink's PID / version / attachment, through a new create_link.add_link) kept in the pattern's Copies list, in the piece's container, placed before linked; their PID is kept equal to the piece's by the pattern's recompute and by Populate / Reset IDs (set_profile_pid on a copy writes the original). A copy counts as a profile row in the BOM / Cut List and as a profile in Populate IDs (never numbered as a link); "Include Part count" counts the copies. Mode (a) Count is copies (per side when Symmetric), mode (b) Count is pieces with the original; the original takes the slot next to the first face clicked; a face position is the projection of its center on the direction. The direction edge is required in both modes. A third face click restarts the pair; faces on the piece, and copies of a pattern, are refused. Deleting the pattern (any removal, not only from the GUI) deletes its copies. Read-only Gap and Spacing (center to center) show the result of Between faces.

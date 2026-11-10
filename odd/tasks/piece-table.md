# Piece Table on a TechDraw page
New command that inserts a table of the pieces shown in the selected TechDraw view(s): ID, piece, quantity,
length and cut angles with their faces, as a native spreadsheet shown on the page, matching the balloon numbers.

## Specs
- S1 Command: "seria interesante tener un comando para poder agregar una tabla en techdraw, que tenga las piezas, largo y angulos"
  -> a new MaxProFrame command adds a table of pieces to a TechDraw page.
- S2 Pieces: "Solo las de la/s vistas seleccionadas." -> only the pieces shown in the selected TechDraw view(s)
  (one or several); one table for the whole selection, on the page of the (first) selected view.
- S3 Columns: "Id, Pieza (solo nombre por ejemplo TC80x40x1.5), cantidad, largo, angulos y caras." -> columns in this
  order: ID, Piece (the profile's name only, e.g. `TC80x40x1.5`, without `Profile_` prefix, index or `_Tr`/`_Mt` suffixes),
  Quantity, Length, and the cut angles with the face each is seen on, as the BOM writes them (`45.0 <80`, compound
  `45.0 <80 + 10.0 <40`), one column per end (CutAngle1, CutAngle2).
- S4 Rendering: "Hoja nativa." -> a `Spreadsheet::Sheet` holding the table, shown on the page with a
  `TechDraw::DrawViewSpreadsheet`.
- S5 Agreed proposal (L2, accepted by L3): pieces grouped by ID with their Quantity, so the numbers match the balloons;
  pieces without ID get no row and are reported as Create Balloons does (count in the status bar, names in the
  Report view, pointing to Populate IDs); running the command again on the same view(s) refreshes the existing table
  instead of adding another; numbers and angle texts use the decimal separator of the FreeCAD language, as the Cut List
  does (`45,0 <80` in Spanish); the command is enabled whenever a document is open: select the view(s) first, or
  click the button and then a view, Esc cancels (as Create Balloons).
- S6 Tape length: "Lo que pasa que normalmente en un taller se mide un lado del tubo con la cinta para cortarlo." and
  the choice "Cambiar en todos lados" (L10) -> the length of a piece (its `Length`, shown by the Piece Table, the BOM and
  the Cut List and used by the stock bars of the Cut List) is the longest side of the piece measured along its axis: the
  longest straight edge of the finished piece parallel to its axis, not the tip-to-tip extent along the axis. On the
  user's chair: piece 2 (45 deg top / 12 deg bottom) 399.1 instead of 407.6, piece 3 (12/12 parallelogram) 429.4
  instead of 437.9; pieces 1, 4, 5 unchanged (420.0, 494.1, 488.4).
- S7 Saved documents: choice "Actualizar al abrir" (L15) -> when a document saved before S6 is opened, every piece
  (profile, trimmed profile, cutout) gets the S6 length at once, without the user editing or recomputing it: the user's
  saved chair shows the longest sides (399.1 / 429.4 for pieces 2 / 3) in the BOM, the Cut List and the Piece Table.

## Tasks
- T1 S2 S3 S5 table data: pieces of the selected views grouped by ID, piece name, quantity, length, angle texts; sheet
  writer — worker — commit: 609969f (done)
- T2 S1 S4 S5 command: selection / click flow, sheet + DrawViewSpreadsheet on the page, refresh, no-ID report, one Undo
  step; icon, toolbar/menu, translations (ES), CHANGELOG and docs — worker — commit: 609969f (done)
- T3 S6 tape length: Length = longest straight edge parallel to the axis, everywhere Length is computed; tests,
  CHANGELOG, docs — worker — commit: 815b883 (done)
- T4 S7 refresh Length on document restore; save/reopen tests; CHANGELOG — worker — commit: pending

## Log
- L1 (user): "seria interesante tener un comando para poder agregar una tabla en techdraw, que tenga las piezas, largo y angulos, que opinas?" (with a screenshot of a TechDraw page with balloons 1-5 on an isometric view of a chair frame)
- L2 (agent proposal): command "Tabla de piezas" on a view (select or click like balloons), only the view's pieces grouped by ID with quantity, columns ID/qty/profile/length/angle1/angle2/ends, re-run refreshes like Refresh Balloons; rendering options native sheet (DrawViewSpreadsheet, recommended) or SVG symbol.
- L3 (user): "1. Solo las de la/s vistas seleccionadas. 2. Id, Pieza (solo nombre por ejemplo TC80x40x1.5), cantidad, largo, angulos y caras. 3. Hoja nativa."
- L4 (decision): "angulos y caras" read as the BOM angle text, which already names the face (`45.0 <80`); the Ends glyph column of the proposal was not requested and is left out.
- L5 (worker, T1+T2): RED observed — tests/test_piece_table.py against a do-nothing stub command: 21/21 failed; Spanish cases failed (2) until the ES strings were added; Undo of a refresh failed with Sheet.clearAll (sheet empty after undo), fixed by setting/clearing cells one by one. GREEN observed — test_piece_table 23/23 OK; PRESERVE test_balloons 32/32, test_toolbar_translations 4/4, test_workbench_commands 2/2, test_compile_translations 2/2, test_workbench_translation_loading 2/2, test_cut_list 27/27 OK. Expected failure until the parent lists the command: test_shortcuts.test_every_maxproframe_command_is_in_the_scheme (MaxProFrame_CreatePieceTable missing from WITHOUT_SHORTCUT). Uncommitted (worker may not commit); .qm rebuilt with the AppImage lrelease, which reproduces the committed .qm byte for byte.
- L6 (worker decisions, not in the specs): Piece = SizeName (falls back to Label); rows sorted by ID (2 before 10, Z before AA); a link row takes its own PID and the name/length/angles of what it links (empty length/angles if it links no profile); the table remembers its views in a SourceViews string list on the DrawViewSpreadsheet; no table is made when no piece has an ID; a detail-view click says "A detail view gets no table" (ViewPicker got an optional detail_message, balloons unchanged); no shortcut.
- L7 (parent): MaxProFrame_CreatePieceTable added to WITHOUT_SHORTCUT (test_shortcuts 5/5); test_piece_table 23/23. T1+T2 committed together as one behavior in 609969f (~705 authored lines incl. 353 test lines and .ts strings): past the ~400-line advisory slice, kept as a single reviewable feature commit.

- L8 (user, manual test): "porque son diferentes las medidas?" (table 407,6 / 437,9 vs drawing dimensions 399 / 429; 494 and 486 on piece 4)
- L9 (user): "entonces la tabla muestra el boundingbox del perfil ?" then "Lo que pasa que normalmente en un taller se mide un lado del tubo con la cinta para cortarlo."
- L10 (user choice among: longest side in the table only / both in the table / change everywhere): "Cambiar en todos lados" -> Table, BOM and Cut List show the longest side; the Cut List stock bars use it too.
- L11 (decision): a section with no straight edge parallel to the axis (round tube or bar) keeps the tip-to-tip length, since no side can be taped along a straight edge there.
- L12 (worker, T3): callers — length_along_normal only feeds the Length property (profile.py:1314, trimmed_profile.py:571, extruded_cutout.py:490 on its trim or profile); no caller uses it for geometry, so it was changed in place. Length readers: create_bom.py:111 (BOM, Cut List rows and stock bars), piece_table.py:47, populate_ids.py:217 (grouping key only for objects without a solid). New `longest_side` in _utils.py: straight edges parallel to the path direction (sine tolerance 1e-6), edges on one line measured together as one side (an Extend Cut of a beveled end leaves the long side in two edges, 0-288.5 and 300-382.7); none -> tip-to-tip extent as before (L11).
- L13 (worker, T3): RED observed — tests/test_tape_length.py 8/12 failed with the old tip-to-tip value (parallelogram 12/12 on 40x40: 308.50 vs 300; 45/12: 324.25 vs 315.75; rounded corners 308.50; Extend Cut parallelogram: 0 vs 23.09 = 40*tan 30; cutout 308.50; BOM/Cut List 308.5; Piece Table '308.5'); 4 preserve cases passed (square 300, trapezoid 380, round tube 311.55, split side 382.68). GREEN observed — test_tape_length 12/12 OK. No pre-existing expectation changed: test_cut_list 27, test_piece_table 23, test_cut_ends 15, test_extend_cut_geometry 20, test_keep_end_geometry 11, test_notch_geometry 30, test_end_miter_extend_gap 6, test_end_miter_geometry 6, test_miter_followups_geometry 8, test_miter_after_extend_cut 12, test_drill_hole_geometry 26, test_extruded_cutout_pid 2, test_trimmed_profile_pid 2, test_populate_identical_pieces 10, test_populate_derived_pid 6, test_reset_ids 18, test_balloons 32 and 8 more modules all OK (their pieces are square-cut, trapezoids or one-end cuts, where the longest side is tip to tip).

- L14 (verify mwau65vj, S6 pass): rule, frames (rotated Parts, ParametricLine in another Part), tolerances (max noise 3.3e-16) and readers OK; 12 tests fail on old code. Advisory: stock bar fitting does not add the ~w*tan(a) waste of the first parallelogram cut in a bar. Open: a document saved before S6 keeps the old Length after open and recompute; only touch()+recompute updates it.
- L15 (user choice among "Actualizar al abrir" / "Dejarlo como está"): "Actualizar al abrir".

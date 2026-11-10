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

## Tasks
- T1 S2 S3 S5 table data: pieces of the selected views grouped by ID, piece name, quantity, length, angle texts; sheet
  writer — worker — commit: pending
- T2 S1 S4 S5 command: selection / click flow, sheet + DrawViewSpreadsheet on the page, refresh, no-ID report, one Undo
  step; icon, toolbar/menu, translations (ES), CHANGELOG and docs — worker — commit: pending

## Log
- L1 (user): "seria interesante tener un comando para poder agregar una tabla en techdraw, que tenga las piezas, largo y angulos, que opinas?" (with a screenshot of a TechDraw page with balloons 1-5 on an isometric view of a chair frame)
- L2 (agent proposal): command "Tabla de piezas" on a view (select or click like balloons), only the view's pieces grouped by ID with quantity, columns ID/qty/profile/length/angle1/angle2/ends, re-run refreshes like Refresh Balloons; rendering options native sheet (DrawViewSpreadsheet, recommended) or SVG symbol.
- L3 (user): "1. Solo las de la/s vistas seleccionadas. 2. Id, Pieza (solo nombre por ejemplo TC80x40x1.5), cantidad, largo, angulos y caras. 3. Hoja nativa."
- L4 (decision): "angulos y caras" read as the BOM angle text, which already names the face (`45.0 <80`); the Ends glyph column of the proposal was not requested and is left out.
- L5 (worker, T1+T2): RED observed — tests/test_piece_table.py against a do-nothing stub command: 21/21 failed; Spanish cases failed (2) until the ES strings were added; Undo of a refresh failed with Sheet.clearAll (sheet empty after undo), fixed by setting/clearing cells one by one. GREEN observed — test_piece_table 23/23 OK; PRESERVE test_balloons 32/32, test_toolbar_translations 4/4, test_workbench_commands 2/2, test_compile_translations 2/2, test_workbench_translation_loading 2/2, test_cut_list 27/27 OK. Expected failure until the parent lists the command: test_shortcuts.test_every_maxproframe_command_is_in_the_scheme (MaxProFrame_CreatePieceTable missing from WITHOUT_SHORTCUT). Uncommitted (worker may not commit); .qm rebuilt with the AppImage lrelease, which reproduces the committed .qm byte for byte.
- L6 (worker decisions, not in the specs): Piece = SizeName (falls back to Label); rows sorted by ID (2 before 10, Z before AA); a link row takes its own PID and the name/length/angles of what it links (empty length/angles if it links no profile); the table remembers its views in a SourceViews string list on the DrawViewSpreadsheet; no table is made when no piece has an ID; a detail-view click says "A detail view gets no table" (ViewPicker got an optional detail_message, balloons unchanged); no shortcut.

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

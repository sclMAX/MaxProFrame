# Profile Pattern panel editing
The Profile Pattern task panel becomes a full editor: piece, direction edge and faces change through explicit
"Change" buttons, the preview can be turned off, Count/Pitch accept expressions (Fx), and long reference names no
longer widen the panel. Branch `feat/pattern-panel-edit`.

## Specs
- S1 Piece: "Posibilidad de cambiar de pieza." -> the piece of an existing (or new) pattern can be replaced; the
  copies (App::Link) follow the new piece. A copy of the same pattern (or another pattern's link) is rejected.
- S2 Faces: "Posibilidad de cambiar las caras." -> in Between faces mode the two faces can be picked again.
- S3 Direction: "Posibilidad de cambiar la direccion (edge e invertir)." -> the direction edge can be picked again;
  inverting stays the existing "Sense" choice (Edge sense / Inverted / Symmetric) of Count and pitch mode, which
  already exists in the panel (Between faces ignores the sense, the two faces bound it).
- S4 Preview: "Check para habilitar/deshabilitar la preview." -> a checkbox, on by default and remembered between
  sessions like Drill Hole / Extend Cut "Update automatically"; when off, edits do not recompute the pattern, OK still
  applies the values.
- S5 Fx: "Agregar Fx a los campos." -> Count and Pitch accept expressions (Fx), bound to the pattern's properties;
  Cancel restores the previous expressions, an unchanged OK leaves no Undo step.
- S6 Compact text: "Si, tambien debemo analizar que texto informativo ponemos en el panel, porque si los nombres de las
  caras, aristas, etc. son muy largos el panel crece demaciado en ancho." -> each reference is one row
  (Piece / Direction / Face 1 / Face 2): the object label is elided in the middle to the available width, the
  sub-element (" · Face2", " · Edge1") is never elided, and the full name is the tooltip. Long names never widen the
  panel. The help line is short and depends on the armed Change button.
- S7 Explicit selection (accepted proposal L3, "Si"): every reference row has a checkable "Change" button; while
  armed, a click only sets that kind of reference (a piece, a straight edge, two planar faces); clicking the button
  again (or arming another one) disarms; Esc stays Cancel of the task dialog. When no button is armed, a click only
  fills a reference that is still missing (creation keeps seeding from the initial selection); a click that would
  replace one says to press Change.

## Tasks
- T1 S2 S3 S6 S7 inline: reference rows with elided labels + tooltips, checkable Change buttons for direction and
  faces, contextual hint; tests. Commit: - (one commit with T2: same pick code)
- T2 S1 S7 inline: Change piece (armed pick, Piece in VALUES/_wanted, offsets snapshot of every touched piece,
  reject pattern links); tests. Commit: -
- T3 S4 S5 inline: preview checkbox (persisted) + Fx on Count/Pitch (bind, restore on Cancel, compare on OK); tests.
  Commit: -
- T4 S1-S7 inline: Spanish translations (.ts + .qm), README/docs, full pattern suites on 1.1.4 and weekly. Commit: -

## Log
- L1 (2026-11-11) "quiero hacer unas mejoras en el panel de patron [Image#1]:
  - Posibilidad de cambiar de pieza.
  - Posibilidad de cambiar las caras.
  - Posibilidad de cambiar la direccion (edge e invertir).
  - Check para habilitar/deshabilitar la preview.
  - Agregar Fx a los campos.
  Que opinas?"
- L2 Proposal: per-reference "Cambiar" buttons that arm one kind of selection; invert only for Count and pitch.
- L3 (2026-11-11) "Si, tambien debemo analizar que texto informativo ponemos en el panel, porque si los nombres de las
  caras, aristas, etc. son muy largos el panel crece demaciado en ancho."
- L4 Exploration: the panel already has a Sense combo with "Inverted" (profile_pattern.py SENSES), so no extra invert
  button; Count/Pitch use count_field/length_field but never bind() (no Fx today); Drill Hole is the edit-mode Fx and
  "Update automatically" reference; Extend Cut has the checkable "Change target" button.

# Parametric Line from a vertex along a direction
Refactor of Parametric Line: besides joining two vertices, draw one line from each selected vertex
along a global axis or a custom vector, with an expression-capable length (table legs from a frame sketch).

## Specs
- S1 Direction: "1. Ejes globales mas vector" -> global +X, -X, +Y, -Y, +Z, -Z, or a custom vector.
- S2 One command: "2. Refactor de PArametricline" -> extend the existing ParametricLine object and the
  Create a Parametric Line command (`M, L`); no new command.
- S3 Command routing: "Dos verticies directo (siempre que los vertices no sean del mismo sketch" ->
  exactly two selected vertices that are not both of the same sketch: the line between them, at once (as today).
  Any other selection of vertices (one, three or more, or two of the same sketch): open the panel.
- S4 Edit: "Abre el panel para editar" -> double-clicking a line drawn from a vertex opens the panel to edit it.
- S5 Agreed proposal (L2): "vértice + dirección + largo, con selección de varios vértices" -> one line per selected
  vertex, start linked to the vertex (global link, follows it), Length takes expressions (Fx).
- S7 Tool first: "me guistaria que el boton parametric line esta activado, poder elegirlo y luego seleccionar un vertice"
  -> the command is enabled whenever a document is open. With no vertex selected it opens the panel empty; while it is
  open, a click on a vertex adds a previewed line from it, a click on a vertex that already has one removes it, a click
  on anything else adds nothing and the panel says to click a vertex. Preselected vertices still route as in S3.
  OK with no line closes without an Undo step.
- S8 Default length: "(nota largo 1000mm por defecto es mucho)" -> a new panel starts at 100 mm the first time, then at
  the Direction, custom vector and Length last confirmed with OK (remembered like the Drill Hole diameter).
- S9 Review R4: when another task dialog is already open, the command creates no line and leaves no open transaction.
- S10 Review R3: a line whose custom vector is zero or whose length is not positive has an empty shape (no stale line).
- S6 Compatibility: lines joining two vertices, new or saved by earlier versions, keep their behavior.

## Tasks
- T1 S1 S2 S5 S6 object: Direction / CustomDirection / Length, execute, restore — inline — commit: 75fde58 (done, 15 tests pass)
- T2 S3 S4 S5 panel, command routing, double-click edit — inline — commit: 5534cad (done, 13 panel tests pass)
- T3 S2 tooltip, translations, tutorial — inline — commit: 5534cad (done, translation/shortcut/command tests pass)

- T4 S7 S8 S9 S10 tool-first picking, remembered values, review fixes, tooltip/translations/tutorial — worker — commit: 5e2c9a2 (done, 17 object + 24 panel tests pass)

## Log
- L1 (user): "Y si hemos un comando que permita hacer bocetos 3D, seleccionar u punto y a partir de el hacer una linea parametrica en un plano 3d que opinas? pros contras ?"
- L2 (agent proposal, accepted): mode "vértice + dirección + largo" with multi-vertex selection instead of a full 3D sketcher.
- L3 (user): "1. Ejes globales mas vector, 2. Refactor de PArametricline"
- L4 (user): command flow "Dos verticies directo (siempre que los vertices no sean del mismo sketch"; edit "Abre el panel para editar".
- L5 (evidence): T1 RED observed (ImportError make_line_from_vertex), then 15/15. Panel tests written with the code; only the Spanish test was observed RED before the translations.
- L6 (evidence): full native suite (FreeCAD .git/ci-policy-runtime) 1253 tests, exit 0. Two commits, ~716 authored lines; second commit holds T2+T3 (code, tests, translations, docs of one behavior). Waiting for the user's manual test before PR.
- L7 (review e54ae289, approved, advisory): R4 orphan lines when showDialog fails; R3 stale shape on invalid direction; suggestion: setEdit uses cached object.
- L8 (user): "Bien, pero me guistaria que el boton parametric line esta activado, poder elegirlo y luego seleccionar un vertice arrastrar con el mouse y que se cree la linea luego ajustaria los parametros en el panel (nota largo 1000mm por defecto es mucho) que opinas, pros contras?"
- L9 (agent proposal): part 1 = always-enabled button + pick vertices in the panel + remembered values (100 mm first) + review fixes; part 2 (drag click-move-click with axis snap) deferred to a separate PR. User: "SI" to part 1.
- L10 (evidence, T4): RED observed for S7-S10 (14 failures + 1 error in panel tests, incl. `RuntimeError: Active task dialog found` for R4; stale shape and 1000 mm default in object tests; old Spanish tooltip), then test_parametric_line 17/17, test_parametric_line_panel 24/24, test_toolbar_translations 4/4, test_library_translations 3/3, test_shortcuts 5/5, test_workbench_commands 2/2. Full suite not run by the worker.

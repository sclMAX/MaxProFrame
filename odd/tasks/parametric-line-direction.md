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
- S6 Compatibility: lines joining two vertices, new or saved by earlier versions, keep their behavior.

## Tasks
- T1 S1 S2 S5 S6 object: Direction / CustomDirection / Length, execute, restore — inline — commit: 75fde58 (done, 15 tests pass)
- T2 S3 S4 S5 panel, command routing, double-click edit — inline — commit: 5534cad (done, 13 panel tests pass)
- T3 S2 tooltip, translations, tutorial — inline — commit: 5534cad (done, translation/shortcut/command tests pass)

## Log
- L1 (user): "Y si hemos un comando que permita hacer bocetos 3D, seleccionar u punto y a partir de el hacer una linea parametrica en un plano 3d que opinas? pros contras ?"
- L2 (agent proposal, accepted): mode "vértice + dirección + largo" with multi-vertex selection instead of a full 3D sketcher.
- L3 (user): "1. Ejes globales mas vector, 2. Refactor de PArametricline"
- L4 (user): command flow "Dos verticies directo (siempre que los vertices no sean del mismo sketch"; edit "Abre el panel para editar".
- L5 (evidence): T1 RED observed (ImportError make_line_from_vertex), then 15/15. Panel tests written with the code; only the Spanish test was observed RED before the translations.
- L6 (evidence): full native suite (FreeCAD .git/ci-policy-runtime) 1253 tests, exit 0. Two commits, ~716 authored lines; second commit holds T2+T3 (code, tests, translations, docs of one behavior). Waiting for the user's manual test before PR.

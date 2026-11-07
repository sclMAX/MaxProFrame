# Parametric Line: angle in a global plane and drag in a plane
Part 2 of the parametric line from a vertex (stacked on feat/parametric-line-direction, PR 95):
a direction given as an angle in a global plane, and drawing the lines by dragging the mouse in a chosen plane.

## Specs
- S1 Angle mode: "Deberiamos tener un capo para el angulo si es un vector ?" (answer agreed: yes) -> a third direction
  mode besides the global axes and the custom vector: Direction "Angle", with Plane (XY, XZ, YZ) and Angle (degrees,
  takes expressions with Fx). Convention: counterclockwise from the first axis of the plane toward the second,
  -180°..180°. XY: 0° = +X, 90° = +Y. XZ: 0° = +X, 90° = +Z. YZ: 0° = +Y, 90° = +Z. The panel shows the
  convention of the current plane. Each mode uses only its own properties; switching modes does not rewrite the
  others. A new panel remembers the plane and the angle of the last OK, like the direction and the length.
- S2 Global planes only: "Globales" -> the planes are the global XY, XZ and YZ; no plane of a face.
- S3 Drag in a plane: "Y si mostramos los 3 planos y permitimos hacer click en el plano donde se desplazara la linea ?"
  -> while the panel creates lines, the 3D view shows the three global planes as translucent squares at the start of
  the newest line, a fixed size on screen. A click on a plane starts the drag: the other planes dim, the end of the
  lines follows the cursor in that plane (the cursor ray meets the plane), and a second click fixes direction and
  length. The angle snaps every 15° and the length to 10 mm steps (1 mm with Shift). A direction on an axis of the
  plane is stored as that global axis; any other as Angle in that plane. The panel stays open to adjust.
  A plane seen almost edge-on (under 10° from the view) is dimmed and cannot be clicked.
- S4 All the lines: "si" (to "¿Arrastrar crea solo la línea del vértice clicado, o la misma dirección y largo para todos
  los seleccionados?") -> the drag sets the direction and length of every line of the panel.
- S5 Keys: "Define las teclas tu" -> while the panel is open: P cycles the active plane XY -> XZ -> YZ (and starts the
  drag when none is active), Esc or a right click cancels the drag in progress and puts back the values it started
  from without closing the panel, Shift while dragging snaps the length to 1 mm. The plane can also be chosen with
  XY / XZ / YZ buttons in the panel. The tooltip and the tutorial list the keys.
- S6 Compatibility: lines and documents of earlier versions (axes, custom vector, two vertices) keep their behavior;
  clicks on vertices still add and remove lines (PR 95 S7).

## Tasks
- T1 S1 S2 S6 object + panel: Direction "Angle", Plane, Angle, angle field with Fx, remembered plane/angle,
  translations, tutorial — inline — commit: (this commit) (done, 19 object + 27 panel tests pass)
- T2 S3 S4 S5 drag: pure plane math (ray/plane, edge-on, snapping, axis or angle), overlay and mouse/key callbacks,
  panel plane buttons, tooltip/translations/tutorial — inline — commit: (this commit) (done, 9 math + 36 panel tests pass)

## Log
- L1 (user): "hablemos de la parte 2, que opciones tenemos?" (part 2 = drag with the mouse, deferred from PR 95 L9)
- L2 (agent): options A Draft Snapper, B own pivy callback, C axis-only drag; recommended B.
- L3 (user): "Y si mostramos los 3 planos y permitimos hacer click en el plano donde se desplazara la linea ?"
- L4 (user): "Deberiamos tener un capo para el angulo si es un vector ?"
- L5 (agent proposal): angle mode Plane + Angle with the convention of S1; angle first in its own commit.
- L6 (user): "Globales, Define las teclas tu, si" -> global planes, keys chosen by the agent (S5), drag sets every
  line; "si" also taken as agreement with the angle convention (assumption, confirm at manual test).
- L7 (evidence, T1): RED observed (9 errors + 2 failures: no Plane/Angle, no plane= argument, combo without Angle,
  no Spanish), then test_parametric_line 19/19, test_parametric_line_panel 27/27, test_expression_fields,
  test_toolbar_translations, test_library_translations, test_compile_translations exit 0.
- L8 (evidence, T2): RED observed (ModuleNotFoundError parametric_line_drag; 6 errors + Spanish hint failure in the
  panel), then test_parametric_line_drag 9/9, test_parametric_line_panel 36/36 (including Coin event routing through
  a fake top view), test_parametric_line 19/19, toolbar/library translations, shortcuts, workbench commands exit 0.
  The real 3D view (squares, ray, Esc focus) needs the user's manual test.
- L9 (delivery): this branch is a PR stacked on PR 95 (feat/parametric-line-direction); its slice is T1 + T2 only.
- L10 (verify, independent): S1 S2 S4 S6 met; S3 not met: (1) HIGH the release of a click that starts or fixes a
  drag still picked the vertex under it (FreeCAD selects on release; the guard cleared on the press's next event loop);
  (2) MEDIUM after a zoom the clickable squares no longer matched the drawn ones; (3) LOW the migration test sat under
  `if __name__ == "__main__":` and never ran. Advisory: right-click cancel may also open the context menu; perspective
  square size measured on the focal plane. S5 keys in a real GL view unverifiable offscreen.
- L11 (fix): the guard holds from the taken press until its release is processed; a press redraws the squares
  (size and edge-on follow the camera) before hit-testing; migration test moved into the class. RED observed for
  (1) and (2) with the fix stashed (2 failures + 1 error), then test_parametric_line 20/20, test_parametric_line_drag
  9/9, test_parametric_line_panel 40/40.

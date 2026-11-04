Drill Hole panel: aligned Fx icon, clickable reference markers on the corners and edge midpoints of the picked face.
Branches (chain, one PR each): fix/fx-icon-alignment -> feat/drill-corner-markers -> feat/drill-midpoint-reference.

## Specs

- S1. Fx alignment (L1): "Podemos hacer que \"Fx\" quede mejor alineado." The Fx icon of every expression field sits at the right end of the field, left of the spin arrows, vertically centered, like FreeCAD's own panels; in creation and edit mode.
- S2. Corner markers (L1): "Podriamos mostrar uno circulos clickables para elegir desde donde se ubican los agujeros [Image#2] en las esquinas". The picked face shows a clickable circle on each of its corners; clicking one makes it the reference corner. The current reference stays marked. Clicking a face (near a corner) or a vertex keeps working.
- S3. Midpoint markers (L1, L2): "y en los medios de los edges". "Para los puntos medios podemos permitir click en dos (medio longitudinal, medio transversal) para centrar un agujero en el perfil." The picked face also shows a clickable circle on the middle of its edges. The middle of an edge along the profile makes the holes measured along from the middle of the face length; the middle of an edge across the profile, across from the middle of the face width; both together center the hole on the face.
- S4. Midpoint sign (L2, L3): "Posiotivo hacia un extremo, negativo hacia el extremo opuesto." Positive is away from the chosen reference corner ("Lejos de la esquina elegida"), negative toward its end.
- S5. Compatibility (parent, L3): documents saved before S3 open unchanged (holes measured from their corner).

## Tasks

- T1 (S1) Reposition the Fx icon after binding, in expression_fields.py. Route: inline. Commit: 98e6673. Done.
- T2 (S2) Clickable corner markers on the picked face in the Drill Hole panel; Next corner stays. Route: inline. Commit: pending.
- T3 (S3-S5) Midpoint markers and centered offsets, design in L6. Route: worker (context backstop), branch feat/drill-midpoint-reference. Commit: pending.

## Log

- L1. User: "Analicemos unpar de cosas en drill [Image#1]: - Podemos hacer que \"Fx\" quede mejor alineado. - Podriamos mostrar uno circulos clickables para elegir desde donde se ubican los agujeros [Image#2] en las esquinas y en los medios de los edges?. Que opinas, pros, contras?" Image#1: the Fx icon sits at the top, around 3/4 of the field width. Image#2: circles drawn on the corners and edge midpoints of the top face.
- L2. User: "Para los puntos medios podemos permitir click en dos (medio longitudinal, medio transversal) para centrar un agujero en el perfil. Posiotivo hacia un extremo, negativo hacia el extremo opuesto."
- L3. User answers: sign "Lejos de la esquina elegida (recomendado)"; scope "Las tres: Fx, esquinas, medios", each its own PR.
- L4. T1 cause: FreeCAD's ExpressionSpinBox::resizeWidget (src/Gui/SpinBox.cpp) places the icon only on a resize, at (lineedit width - icon width - margin, (lineedit height - icon height) / 2). Unbound, the icon is 100x30; bind sizes it 17x17. A field bound once shown (Drill Hole binds on the first preview) keeps the place computed for 100x30. RED tests/test_expression_fields.py on stable and weekly-2026.10.28: `AssertionError: 85 not less than or equal to 6 : (QRect(5, 1, 226, 26), QRect(124, -2, 17, 17))`. Fix: bind() sends the field a resize event. GREEN 3/3 on stable and weekly. Weekly runtime downloaded (sha256 checked) to .freecad-test/runtimes/weekly.
- L5. T2: the panel draws a white open circle on each other corner of the picked face and the filled orange one on the reference; a left click within 10 px (projected with getPointOnViewport, Coin coordinates) picks it and the press and release are kept from the view (no face selection under it). RED (base code): 4 new tests AttributeError (marker_at, reference_markers, _on_mouse_button); GREEN test_drill_hole_panel 40/40 on stable. The offscreen suite has a real View3DInventorPy: the callback is registered and removed; the real screen hit is checked by hand only.
- L6. T3 design (parent, from S3-S5):
  - Model: two new DrillHole properties `CenterAlong` and `CenterAcross` (App::PropertyBool, group DrillHole, default False). `onDocumentRestored` adds them when missing, False, so an old document keeps its holes where they were (S5).
  - Geometry (`DrillHole.centers`): with `CenterAlong` the along origin moves from the reference corner by half the extent of the face along the profile (max over the face vertices of `(p - vertex) . along`); `CenterAcross` the same across. The offsets add on top, with today's directions: positive away from the reference corner (S4). Both on: the hole is centered on the face with offsets 0.
  - Panel markers: besides the corners, a marker on the middle of every straight edge of the picked face. An edge parallel to the profile axis is an "along" midpoint (centers along); any other straight edge an "across" midpoint. `reference_markers()` keeps (name, global point), names `VertexN` or `EdgeN`.
  - Picks: a midpoint marker turns its center on and keeps the other one; the reference corner becomes the end of that edge nearest the current corner (its first end when there is none), so the side the offsets measure from is the clicked edge. A corner marker, a face click near a corner, a vertex click or Next corner measure from the corner: both centers off.
  - Display: active midpoints filled orange like the reference corner, others white open circles. The vertex label tells the centering (translated, Spanish in both .ts files).
  - Panel state: `_values`, `_wanted`, `_apply_to`, `_restore` carry both flags; OK keeps them in one Undo step, Cancel restores them (also with undo disabled), unchanged values leave no Undo step.
  - Docs: tutorial Drill Hole section and CHANGELOG.
- L7. T2 full stable suite: `Test suite succeeded (1114 tests executed)`. T1 full stable suite: 1110 tests, no failure.

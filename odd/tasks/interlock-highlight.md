# Show which corner or joint an Interlock is
An Interlock has no shape of its own, so selecting it in the tree or editing it shows nothing in the 3D view. Draw a
3D overlay of its two faces and its corner, in the Interlock panel and while it is selected in the tree, for every
kind. Branch feat/interlock-highlight (from main c90e01d); work-unit commits; PR, merge on green CI.

## Specs
- S1 The problem (L1: "Al seleccionar en el arbol para editar, no hay un indicador visual de que esquina o coneccion
  estoy editando."): selecting or editing an Interlock must show where it is in the 3D view.
- S2 In the Interlock panel (L2, proposal accepted with "me parece bien vamos con eso"), creating and editing: the face
  of the first tube in one color and the face of the second tube in another, and a mark at the corner or the T joint;
  it follows Flip (shows which tube owns the first finger).
- S3 On tree selection (L2): while an Interlock is selected in the tree (panel closed) the same overlay shows; it goes
  away when it is deselected. The selection itself does not change (Delete still deletes only the Interlock) and no
  visibility changes.
- S4 Every kind (L2): Fingers at a folded corner, Fingers at an End Miter corner, Tabs at a T joint.
- S5 The overlay is a drawing over the view, not a document object: nothing is saved, nothing goes to TechDraw (L2).

## Design decisions (parent)
- D1 Reuse the existing 3D overlay drawing of the panels (create_end_miter_tool.remove_overlay and the Extend / Cut
  and Folded Bar panel highlights) rather than a new mechanism; colors consistent with Extend / Cut where it makes
  sense (orange / blue), documented in the tutorial.
- D2 One selection observer for the tree selection, added once (like the other module observers), removed safely;
  no geometry while a recompute runs (odd/tasks/panel-recompute-deadlock.md S3).

## Tasks
- T1 [S1-S5, D1, D2] Overlay of an Interlock's faces and corner (shared helper), shown by the panel (create and edit,
  follows Flip) and on tree selection; tests; tutorial + CHANGELOG + Spanish/Russian texts if any new text.
  route=gentle-ai-worker; commit=T1 (see Log L3) [x]

## Log
- L1 User (screenshot: tree with Interlock_Profile_TC80x40x1.5_002_Profile_TC80x40x1.5_001 selected under
  Profile_..._002_Mt_Fg_Sl_Sl_Sl, property panel Fingers Count 3, Flip true, Face A / Face B; 3D view shows nothing
  highlighted): "Otra cosa que deberiamos analizar es: Al seleccionar en el arbol para editar, no hay un indicador
  visual de que esquina o coneccion estoy editando."
- L2 Parent proposal: reuse the 3D overlay of Extend / Cut and the Folded Bar panel; (1) in the Interlock panel, create
  and edit, the first tube's face in one color, the second's in another, a mark at the corner / T joint, following
  Flip; (2) on tree selection, the same overlay while selected, selection and visibility unchanged; for the three
  kinds; the overlay is not a document object. User: "me parece bien vamos con eso".
- L3 T1 (worker): `freecad/maxproframe/interlock_highlight.py`: `drawing` finds the two faces of an Interlock on the
  current pieces, global (Fingers at a folded corner: `create_interlock_tool.corner_faces`, the planar faces of the bar
  on each tube's inner wall by `_on_inner_wall`; miter corner: `miter_finger_interlock.interlock_faces`; Tabs: new
  `tab_interlock.tab_faces`, now also used by `interlock_joint`) and the mark where their planes meet nearest the
  faces (inner vertex, midway across the walls; T joint at the middle of the crossbar wall). `InterlockOverlay` draws
  them as one SoAnnotation: tube A's face orange, tube B's blue (Extend / Cut `HIGHLIGHT_COLORS` TARGET / PROFILE),
  swapped by Flip for Fingers (Tabs: crossbar orange, rail blue), with the Folded Bar panel's `_overlay_group`, and the
  mark in the selection color with `create_end_miter_tool.marker_group` (factored out of End Miter `_draw_markers`).
  Panel: `_show` -> `_draw_overlay` (waits GAP_DELAY_MS while `_busy()`), removed in `clean` (OK / Cancel / closed) and
  on Apply and continue (no Interlock), shown again when the next is made. `TreeSelection`: one module-level selection
  observer (globals guard), every callback defers `refresh` with `QTimer.singleShot`; draws only for exactly one
  Interlock selected and no Interlock panel open (`panel_opened` / `panel_closed` + `Gui.Control.activeDialog()`),
  waits while any document recomputes. No new user-visible text: no translation changes. RED (base 2a2a8bb copy, the
  module stubbed so the file imports): tests/test_interlock_highlight.py 11 of 12 failed ("unexpectedly None": no
  overlay; the 12th, only an Interlock selected alone shows, passes on the base by design). GREEN on FreeCAD 1.1.4
  (ci/run_tests.py --target stable): test_interlock_highlight 12; preserved: test_interlock_panel 14,
  test_tab_interlock_panel 13, test_miter_finger_panel 20, test_interlock_translations 11, test_extend_cut_preview 22,
  test_folded_bar_panel 111 (--timeout 900), test_end_miter_preview 26, test_end_miter_recompute_gate 5,
  test_tab_interlock 18, test_tab_interlock_folded_bar 13, all OK. Black + isort clean. Docs: tutorial Interlock
  paragraph, CHANGELOG Unreleased Improvements. commit: left to the parent.
- L4 CI of 436aa9f (PR #183) failed only sharded (stable 4/4, weekly 2/4 and 4/4): TreeSelectionTest "unexpectedly
  None" (no tree overlay). Reproduced locally with `ci/run_tests.py --target stable --timeout 3600 --shard 4/4` (575
  tests, 1 failure, the same test). Cause (probe in a scratch copy logging every `later` / `refresh` with its stack):
  FreeCAD pumps Qt events inside `doc.recompute()`, so a tree `refresh` ran inside the fixture's own recompute, found
  the document recomputing and rescheduled itself in GAP_DELAY_MS (250 ms) with the `_scheduled` flag set; the
  selection made right after was dropped by that flag (`later` did nothing while one was pending) and the test looked
  before the 250 ms passed. Run alone the earlier timings hid it. A product bug too: a selection right after a
  recompute waited behind the retry. Fix (interlock_highlight.py): one restartable single-shot QTimer, a refresh
  asked for sooner replaces one waiting longer (`later`, `pending`); "a panel is open" only for an Interlock panel
  not closed whose form is alive and placed in the task view, while FreeCAD shows a task dialog (`_shown`), so a panel
  built and dropped never hides the tree overlay. Tests self-contained: HighlightFixture.setUp closes a task dialog
  left open, clears the selection and waits until no refresh is pending; every test ends asserting no tree overlay
  left (`assertNothingLeft`). New regression tests: a selection is not left waiting behind a refresh for a recompute;
  a panel never shown does not hide the tree overlay. The "Timeout (0:02:00)!" stack dumps are ci/diagnostics.py's
  one-shot faulthandler snapshot 120 s into every run (`dump_traceback_later(120, repeat=False)`), not a hang; the
  base 2a2a8bb has one too. Wall time, local stable shard 4/4: base 2a2a8bb 572 tests 499.3 s; 436aa9f 575 tests
  532.8 s (1 failure); this change 576 tests 486.2 s: the observer does not slow the suite.
- L5 User (parent's questions "¿Las pestañas van con el larguero en naranja, como la cara destino de Extender/Cortar?"
  and "¿Que el resaltado se actualice cuando cambiás una propiedad desde el panel de propiedades?"): "si si". Changed
  (interlock_highlight.py): Tabs draw the rail face (RailFace, PieceB) orange and the crossbar wall blue; Fingers keep
  the first tube orange, Flip swaps. The tree observer is also a document observer, added once with it
  (`App.addDocumentObserver`): after a recompute, an undo / redo, an object deleted or a document closed it refreshes
  from the event loop (skipped while recomputing), so Flip, Count or a face changed in the property editor and
  recomputed redraws the overlay without selecting again; it never recomputes. Tests: Tabs assertions swapped; new
  test_flip_changed_while_selected_updates_the_tree_overlay, test_a_tabs_setting_changed_while_selected_redraws_
  without_a_recompute_of_its_own (one recompute, one redraw, one overlay), test_non_interlock_selections_draw_nothing
  (rail, trim, rail sketch, Interlock + rail, Face1 / Edge1 / Vertex1 of the tabs piece), test_delete_then_undo_then_
  select_again. RED (436aa9f copy, `pending()` read as `_scheduled`): test_interlock_highlight 18 run, 10 failures
  (Tabs colors, stale Flip, waiting selection, panel never shown). GREEN on FreeCAD 1.1.4: test_interlock_highlight
  18 OK; full suite by stable shards 1/4 577, 2/4 577, 3/4 576, 4/4 576 tests, all OK. Black + isort clean.
  docs/tutorial.md and CHANGELOG.md still say the crossbar is orange: the parent updates their wording.
  commit: left to the parent.

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

# Panels freeze FreeCAD: geometry from a timer while the panel's own recompute is paused
Extend Cut, End Miter and Drill Hole panels get the recompute gate the Folded Bar panel has had since 9b9d537.
Branch fix/panel-recompute-deadlock (from main 314db18); work-unit commits; push, PR and merge are the user's call.

## Specs
- S1 No freeze (L1: "se congelo Freecad al querer editar un Trim" ... "estaba cambiando el gap"): typing in the Gap
  field (or any field / click that schedules a preview) of the Extend Cut panel while its preview recompute is running
  never freezes FreeCAD. Root cause (L2, gdb): the preview timer runs doc.recompute(); a FeaturePython boolean reports
  progress, Gui::SequencerBar::setProgress pumps Qt events, a second panel timer fires and runs Shape.cut(), which
  waits forever on the OSD_ThreadPool held by the paused outer boolean.
- S2 Same rule in End Miter and Drill Hole (L3: "Extender/Cortar + End Miter + Drill Hole (Recomendado)"): their
  panels have the same timer + recompute pattern and get the same protection.
- S3 Rule (from the Folded Bar fix, Engram 8873): while a panel's recompute runs (`_recomputing`), its handlers and
  timers do no geometry (no booleans, no shape queries that compute, no nested recompute); the change is recorded and
  the timer is rescheduled (not dropped), so the preview catches up with the last value once the recompute ends.
- S4 Nothing else changes: preview results, messages, OK / Cancel / Apply behavior, undo and the edit flow of the
  three panels stay as they are.

## Tasks
- [x] T1 [S1, S3, S4] Extend Cut panel gate (create_extend_cut_tool.py): every doc.recompute() of the panel inside the
  gate; _update_preview / _draw_highlights / _cut_off_pieces and any other timer slot doing geometry defer while it
  runs; tests that simulate a timer firing during the recompute (as tests/test_folded_bar_panel.py does since
  9b9d537) and that the final preview matches the last Gap. route=gentle-ai-worker; commit=ad59336
- [x] T2 [S2, S3, S4] Same gate in End Miter (create_end_miter_tool.py) and Drill Hole (create_drill_hole_tool.py);
  tests per panel. route=gentle-ai-worker; commit=e6fc880
- [x] T3 [S1-S4] CHANGELOG (Unreleased, Fixed); report other panels with the same pattern (not fixed here).
  route=gentle-ai-worker; commit=4467ad6

## Log
- L1 User (manual test of t-joint-tabs, FreeCAD weekly 2026-10-28 AppImage): "estoy probando pero se congelo Freecad
  al querer editar un Trim" / "2. estaba cambiando el gap" (screenshot: "Editar extender / cortar" panel, Separación
  0,5 mm, FreeCAD "no está respondiendo", status bar "Processing... 4%").
- L2 Parent diagnosis (gdb on the frozen PID, all 18 threads futex-wait, 0% CPU): thread 1 = QTimer::timeout ->
  Python -> Document.recompute -> FeaturePython execute -> makeElementBoolean -> SequencerBar::setProgress ->
  processEvents -> QTimer::timeout -> Python -> TopoShape.cut -> BOPAlgo_PaveFiller::IntersectVE ->
  OSD_ThreadPool::Launcher::wait. Extend Cut panel: _preview_timer -> _update_preview -> _preview_edit /
  _rebuild_preview -> doc.recompute; _changed also schedules singleShot(0, _draw_highlights); _cut_off_piece does
  TrimmedBody.Shape.cut(trim.Shape).
- L3 User: "Extender/Cortar + End Miter + Drill Hole (Recomendado)" (to: fix only Extend Cut, or the three panels with
  the timer + recompute pattern, on a separate fix/ branch).
- L4 T1 (worker): shared `freecad/maxproframe/recompute_gate.py` (RecomputeGate: hold / wait / defer / clear; queued
  work runs in order once the outermost hold ends, a deferred OK / Cancel / Apply after it, closing the dialog when it
  returns True). Extend Cut (Notch inherits it): `_update_preview`, `_discard_preview`, `_restore_edit` and the edit OK
  hold the gate; `_update_preview`, `_draw_highlights`, `_flip`, `remove_selected`, `addSelection` wait; OK, Cancel,
  Apply are deferred; `_rebuild_preview` / `_preview_edit` take `_wanted()` before the recompute, so a value typed
  during it is previewed after. RED (base 314db18 copy): tests/test_extend_cut_recompute_gate.py 5 of 6 failed
  (`_cut_off_piece`, `_retarget`, `_edge_lines`, `parallel_problem` ran inside the recompute; OK / Cancel returned
  True inside it). GREEN on FreeCAD 1.1.4: test_extend_cut_recompute_gate 6, test_recompute_gate 6; preserved:
  test_extend_cut_panel 46, _preview 22, _polish 31, _folded_bar 16, _target_frame 5, _wrong_face 1, _lost_face 8,
  _named_face_kept 3, test_keep_end_panel 22, test_notch_panel 30, test_notch_preview 9, all OK.
  commit: left to the parent (the worker does not commit).
- L5 T2 (worker): End Miter: `_update_preview`, `_discard_preview`, edit OK hold the gate; `_update_preview`,
  `_after_selection`, `_highlight_members`, `remove_selected` wait; OK / Cancel deferred; `_rebuild_preview` takes
  `_wanted()` before the recompute. Drill Hole: its own `_recomputing` / `_pending` / `_deferred` / `_defer` /
  `_close_dialog` replaced by the gate (same behavior, covered by its existing tests); `addSelection` and
  `pick_marker` now wait too (the face of the preview is matched to its base with `face.common`), the 3D view does not
  look for markers under a press while it is held (the click is then a face click, taken after), and the
  recomputes of `_discard_preview`, `_restore_edit` and OK hold it. RED (base copy): test_end_miter_recompute_gate 4
  of 5 failed (`_rebuild_preview` inside the recompute, OK / Cancel returned True), test_drill_hole_recompute_gate
  3 of 4 failed (`_base_element`, `_on_face`, `_markers`, `face_problem`, `wall_thickness` inside it). GREEN on
  1.1.4: test_end_miter_recompute_gate 5, test_drill_hole_recompute_gate 4; preserved: test_end_miter_preview 26,
  _panel 14, _edit 6, _folded_bar 13, _extend_gap 6, _anchors 2, _translations 4, test_drill_hole_panel 99,
  _folded_bar 19, _rebase 4, _reference 10, _command_resources 2, test_folded_bar_tools 14,
  test_miter_after_extend_cut 12, test_panel_language_change 5, test_notch_container 2,
  test_folded_bar_base_tubes 13, all OK. Weekly 27.1.0 (AppImage weekly-2026_10_28, 2026-11-11 build): the four
  new modules pass (6, 6, 5, 4). Black 25.1.0 and isort 6.0.1 clean. commit: left to the parent.
- L6 T3 (worker): CHANGELOG Unreleased **Fixes** entry. Other panels with timers and recomputes (not fixed here):
  Interlock guards its recompute (`_recomputing`, `_busy` retry) and refuses OK / Cancel / Apply meanwhile (dropped,
  not deferred); Cutout / Hole depth panel guards `_apply` and defers OK / Cancel, but `_apply` inside a recompute
  still reads the sketch and face shapes for the pattern warnings, Edit sketch commits inside it, and the face pick
  panel runs `face_at` / `segment_at` on a click during its OK recompute; Profile Pattern guards `_update_preview`
  and defers OK / Cancel, but `addSelection` takes picks (element lookups) inside a recompute; the Parametric Line
  panel recomputes on every field change with no guard. commit: left to the parent.
- L7 Parent: commits ad59336 (T1), e6fc880 (T2), 4467ad6 (T3) on fix/panel-recompute-deadlock; ~990 authored lines,
  one PR (one bug fix, three panels sharing recompute_gate.py; tests are ~60% of it). Risk: item 4 (re-entrancy of
  panel slots during FreeCAD's progress event pump; offscreen tests cannot reproduce the real pump) -> independent
  verify before delivery.
- L8 Correction round after the independent verify (B1: `_release` ran the deferred OK / Cancel / Apply at the end of
  every release, also the nested one of a queued `_update_preview`, so OK closed the panel before the queued click;
  S4 regression against 314db18). Fix: `recompute_gate.py` runs the queue and the button only from the outermost
  release (`_releasing`): a hold ending while the queue runs leaves what it queued to that run, and the button runs
  once the whole queue (including that) is empty; a queued work that raises no longer stops the rest nor the button
  (the first error is raised after them). Extend Cut `apply_and_continue` returns False when OK / Cancel pressed
  during its recompute closed the panel. Verifier probes adopted as tests/test_recompute_gate_order.py (4) and
  tests/test_panel_recompute_gate_order.py (5). RED at HEAD 5b211f5: gate order 3 of 4 failed (['preview', 'ok']
  instead of ['preview', 'click', 'ok', 'closed']; the error case stopped at ['fail']), panel order 2 of 5 failed
  (Extend Cut TrimmingBoundary stayed Face1, wanted Face4; Drill Hole ReferenceVertex Vertex3, wanted Vertex8).
  GREEN on FreeCAD 1.1.4: test_recompute_gate_order 4, test_panel_recompute_gate_order 5, test_recompute_gate 6,
  test_extend_cut_recompute_gate 6, test_end_miter_recompute_gate 5, test_drill_hole_recompute_gate 4,
  test_extend_cut_panel 46, test_extend_cut_preview 22, test_end_miter_preview 26, test_end_miter_panel 14,
  test_drill_hole_panel 99, test_notch_panel 30, all OK. One run of test_extend_cut_recompute_gate failed once
  (its first test: the hooked recompute had not started within 2 s, hook unconsumed); the module now waits up to 10 s
  for the hooked recompute to start, then 5 consecutive runs passed. Weekly 27.1.0: the six gate modules pass
  (6, 4, 5, 6, 5, 4). Black 25.1.0 and isort 6.0.1 clean.
- L9 Independent re-verify of 137926d (Risk item 4): S1-S4 met, no blocker. 1.1.4: test_recompute_gate 6,
  test_recompute_gate_order 4, test_panel_recompute_gate_order 5, test_extend_cut_recompute_gate 6/6/6 (3 runs),
  test_end_miter_recompute_gate 5, test_drill_hole_recompute_gate 4, test_extend_cut_panel 46, test_drill_hole_panel 99,
  test_end_miter_preview 26. Gate probes P1-P5: nothing queued lost while the panel is open, button always last,
  gate never stuck after an error. Advisories, left as follow-ups: A1 a value typed during a deferred OK's own
  recompute is dropped (input after OK; spec silent); A2 Cancel pressed during a direct OK's recompute wins and
  accept() then returns True on a closed panel (same at 5b211f5; end state consistent; real task view not checked);
  P3 a work that re-queues itself inside its own hold every time would loop (not reachable from the panels).

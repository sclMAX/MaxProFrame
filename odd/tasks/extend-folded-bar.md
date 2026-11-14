# Extend a Folded Bar: add a corner to an existing bar
A Folded Bar can grow: its edit panel takes a click on a tube touching one of its ends, and the new-bar panel turns a
click on an existing Folded Bar into extending that bar. Branch feat/extend-folded-bar; push, PR and merge stay the
user's decisions.

## Specs
- S1 The friction (L1): "Aplique el redondeo en una esquina para probar el encastre y todo va bien, pero si ahora quiero
  hacer un redondeo en la esquina derecha no me lo permite." -> a tube meeting an existing Folded Bar at one of its ends
  can be folded into that same bar as a new corner.
- S2 Edit entry (L2, option chosen: "Ambas entradas (recomendado)"): "Al editar la barra, un clic en un tubo que toca
  uno de sus extremos lo agrega." -> in the edit panel, a click on a tube that meets the first or the last segment of
  the bar adds it before or after that end; the bar keeps its corners, their settings and interlocks.
- S3 New-bar entry (L2): "Al crear una barra nueva, un clic en una Barra plegada pasa a extender esa barra en lugar de
  crear otra." -> in the new-bar panel, a click on an existing Folded Bar switches the panel to extending that bar
  (with the tubes already listed when they meet one of its ends), never a second bar sharing a tube.
- S4 No silent refusal (L2 diagnosis: "se ignora sin aviso"): a click the panel cannot take (a tube that meets neither
  end, a tube of another Folded Bar while editing, a closed bar) says why in the panel instead of doing nothing.
- S5 Cancel restores the bar as it was (Segments, BaseTubes, Corners, Interlocks, tube visibility); OK keeps it in one
  undo step.

## Tasks
- T1 [S1, S2, S4, S5] edit panel follows clicks: setEdit registers the panel as selection observer; a tube meeting
  the first end is put first, one meeting the last end goes last; refusals (no end met, tube of another bar, closed
  bar) shown in the panel; Cancel shows an added tube again; tests in tests/test_folded_bar_panel.py (replaces
  test_editing_a_bar_does_not_follow_the_selection). route=inline; commit=e7589ee [x]
- T2 [S3, S4] new-bar panel: a click on another Folded Bar closes the new-bar panel and opens that bar in edit with
  the listed tubes that meet its ends; a listed tube folded by another bar is refused; tests. route=inline;
  commit=e7589ee [x]
- T3 [S1-S5] tutorial, CHANGELOG, es .ts/.qm, full native suite. route=gentle-ai-worker (docs, i18n) + parent
  (Russian test list, suite); commit=docs commit after e7589ee [x]

Delivery forecast: about 300-400 authored changed lines; one PR to main. Actual: e7589ee 507 lines (code + tests,
one work unit: T1 and T2 share addSelection/_extend), then a docs/i18n commit; slice boundary = these two commits,
one PR.

## Log
- L1 User: "probe y funciona bien, pero detecto una friccion en el FolderCOrner [Image#1] Aplique el redondeo en una
  esquina para probar el encastre y todo va bien, pero si ahora quiero hacer un redondeo en la esquina derecha no me lo
  permite." (Image: a frame whose top-left corner is a Folded Bar with an interlock; the Folded Bar panel open with the
  hint "Hacé clic en el tubo siguiente, después de Profile_TC80x40x1.5_001.")
- L2 Diagnosis (parent, create_folded_bar_tool.py:1269 addSelection): in the new-bar panel a click on a Folded Bar
  resolves to the bar object, `base_profile` is None, the click is ignored without a message; in the edit panel
  `addSelection` returns at once (`self.edited is not None`). Question asked; user chose "Ambas entradas
  (recomendado)": "Al editar la barra, un clic en un tubo que toca uno de sus extremos lo agrega. Al crear una barra
  nueva, un clic en una Barra plegada pasa a extender esa barra en lugar de crear otra."
- L4 T1 RED (parent): ExtendEditedBarTest 8 tests, 10 failures (clicks ignored in edit: selection unchanged, no
  notices). T1+T2 code written inline (create_folded_bar_tool.py _extend/_refuse/_keep_visibility/_extend_other/
  extend_with, add_member refuses a tube another bar folds; folded_bar.py folding_bar, setEdit observer + panel);
  T2 tests ExtendFromNewBarTest 5. Context backstop reached: T3 (docs, i18n) goes to a worker.
- L5 Verify 1 (mwgz5qog-2-k3pa): 2 blockers, fixed by parent: Cancel after Remove + click-back left a folded tube
  shown (S5; _discard replays only tubes the restored bar does not fold, _show_removed shows added-then-removed
  tubes); preselected refused tube without notice (S4; _notice set before the add_member loop). Runner default
  timeout 180 s (exit 124) was not a hang: long modules need --timeout 1500. T3 worker (mwgzbsnb-3-cevj) partial:
  docs, CHANGELOG, es/ru .ts, es .qm; parent added the 4 notices to tests/test_russian_translation.py (6/6 OK).
- L6 Verify 2 (mwgzmqli-4-kf2o): S1-S3, S5 met; S4 blocker: a free preselected tube after a refused one cleared the
  notice; fixed (notice cleared per click in addSelection, not in add_member); closed-frame check moved before the
  other-bar check (advisory). Tools/end miter/interlock panel/translation modules all OK; test_folded_bar_panel
  107/107 before this last fix.
- L7 Verify 3 (mwgztaqw-5-7jne): S4, S2 open corner met; found SIGSEGV closing (no OK/Cancel) an edit opened from
  the new-bar panel: cause was a Touched-bar recompute added to _discard inside the dialog teardown, against the
  #148 convention (Cancel with undo on leaves the bar touched). Removed; tests recompute themselves. Verify 4
  (mwh029a9-6-uwwk): S3, S5 met, _discard recompute equal to main, crash not reproduced (9 probes x3);
  Extend* classes 22/22 x3.
- L3 Explorer map (mwgyvm8f-1-0jnw): setEdit (folded_bar.py:715) adds no selection observer; build_chain walks from
  selection[0], which must be a free end (a tube added at the start goes first); corners and interlocks are keyed by
  profile-name frozenset, not index; nothing refuses a tube another Folded Bar folds; edit Cancel with undo off does
  not show an added tube again (_visibility only replayed in new mode, :1477).

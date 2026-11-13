# Weekly CI green again (issue #148)
Weekly FreeCAD CI (ci/targets.json weekly, FreeCAD weekly-2026.11.11) is red on main since PR #147 and still after PR
#149 (26c32fa): both weekly shards time out at 540 s. Branch fix/weekly-ci-148. Delivery: one PR; push, PR and merge
were authorized by the user for this work ("push pr y merge directo, luego ataquemos el 148").

## Specs
- S1 Done when (issue #148, verbatim): "Weekly CI green on `main`, or the weekly-only behavior explained and the tests
  adapted to both runtimes."
- S2 The hang: `ExpressionTest.test_cancel_of_a_new_bar_with_an_expression_leaves_the_document_unchanged` (CI shard 2
  and the local weekly full suite hung there until the timeout; faulthandler earlier showed the main thread in
  `miter_geometry.py` `_slice` / `_section`) no longer hangs: root cause found and fixed (code or test), not a longer
  timeout.
- S3 The cancel-with-undo-disabled differences on weekly (issue #148: `'Invalid' not found in ['Touched']`,
  `'Valid' != 'Touched'`) in `EditPanelTest.test_cancel_with_undo_disabled_puts_the_corners_back_and_removes_the_new_ones`,
  `ExpressionTest.test_cancel_with_undo_off_removes_an_expression_set_while_editing` (CI shard 1 hung in it this time),
  `RemoveTest.test_cancel_with_undo_disabled_puts_back_the_tube_and_the_corner_removed_while_editing`: explained, and
  the panel or the tests fixed so they pass on stable and weekly.
- S4 `test_cutout_folded_bar.CutoutPanelOnFoldedBarTest.test_a_loose_tube_still_takes_its_own_face` fails on weekly in
  CI shard 2 (PR #149 run 43439486380) but passes alone: order-dependent; fix the leak or the test.

## Tasks
- T1 [S2, S3] folded bar panel hang and cancel-with-undo-disabled on weekly. route=worker; commit=
- T2 [S4] cutout loose-tube test order dependence on weekly. route=worker (parallel); commit=
- T3 [S1] PR, CI weekly green (both shards), merge. route=parent; commit=

## Log
- L1 (2026-11-13) user: "push pr y merge directo, luego ataquemos el 148". PR #149 merged (26c32fa).
- L2 PR #149 CI run 43439486380: stable shards pass; weekly shard 1 timed out (540 s) in
  ExpressionTest.test_cancel_with_undo_off_removes_an_expression_set_while_editing after the known failure
  EditPanelTest.test_cancel_with_undo_disabled_puts_the_corners_back_and_removes_the_new_ones; weekly shard 2 failed
  test_cutout_folded_bar...test_a_loose_tube_still_takes_its_own_face and timed out in
  ExpressionTest.test_cancel_of_a_new_bar_with_an_expression_leaves_the_document_unchanged. Artifacts downloaded to
  /tmp/gpPaNK8J/tmp.tg7dGx5S2Z (tests.log, python-stacks.log per shard). Local weekly full suite on 697450a also hung
  in the latter test until the 3600 s timeout (folded-bar-tools L15).

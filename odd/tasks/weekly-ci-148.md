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
- T1 [S2, S3] folded bar panel hang and cancel-with-undo-disabled on weekly. route=worker; commit=(T1 commit) [x]
- T2 [S4] cutout loose-tube test order dependence on weekly. route=worker (parallel); commit=(T2 commit) [x] partial: flake not reproduced; isolation leak fixed; runner prints failures at once
- T4 [S1] shards: stable and weekly 2 -> 4 at the same timeouts; nightly max repetitions 20 -> 9. route=parent; commit=(T4 commit) [x]
- T3 [S1] PR, CI weekly green (all shards), merge. route=parent; commit=

## Log
- L1 (2026-11-13) user: "push pr y merge directo, luego ataquemos el 148". PR #149 merged (26c32fa).
- L2 PR #149 CI run 43439486380: stable shards pass; weekly shard 1 timed out (540 s) in
  ExpressionTest.test_cancel_with_undo_off_removes_an_expression_set_while_editing after the known failure
  EditPanelTest.test_cancel_with_undo_disabled_puts_the_corners_back_and_removes_the_new_ones; weekly shard 2 failed
  test_cutout_folded_bar...test_a_loose_tube_still_takes_its_own_face and timed out in
  ExpressionTest.test_cancel_of_a_new_bar_with_an_expression_leaves_the_document_unchanged. Artifacts downloaded to
  /tmp/gpPaNK8J/tmp.tg7dGx5S2Z (tests.log, python-stacks.log per shard). Local weekly full suite on 697450a also hung
  in the latter test until the 3600 s timeout (folded-bar-tools L15).
- L3 T1 evidence (worker mwf2abnc-e-g2pz): S2 root cause: the panel's S15 guard covered only its own recomputes; a
  setExpression starts the preview timer, the test's doc.recompute() runs, weekly pumps Qt events inside the OCC
  boolean (unfolded_geometry.py:620 bar.cut), update_preview runs ("Recursive calling of recompute" in both CI
  shards' stderr) and _corner_shape's OCC common (create_folded_bar_tool.py:1168) waits forever: the L23 deadlock of
  folded-corners. Fix: `_busy()` also honors doc.Recomputing; `_wait`/`_defer` queue work; `_RecomputeEnd` observer
  (slotRecomputedDocument) resumes from the event loop, 300 ms check as fallback; `_run_waiting` factored out. S3:
  weekly ignores doc.UndoMode = 0 and abortTransaction rolls back, so the "undo disabled" tests take the abort path and
  objects stay Touched; tests adapted (`assertShapeBack`: not Invalid, one solid, same volume before and after a
  recompute). RED: 2 new NoFreezeTest tests failed on both runtimes, S2 test hung on weekly; GREEN test_folded_bar_panel
  79 OK on weekly (205 s, 0 "Recursive calling") and stable (220 s); parent re-run ExpressionTest 5 OK on weekly.
- L4 Independent verify of 9ab5ed2 (mwf3gomr-g-h08o): S2 pass, S3 pass; differential test_folded_bar_panel stable 26c32fa
  77 OK (5 "Recursive calling" lines) vs HEAD 79 OK (0), weekly HEAD 79 OK in 279 s, no hang; 7 scratch probes (observer
  once, other documents ignored, Cancel deferred once, closed dialog drops work, never-ending recompute checks every
  300 ms and stops on close, failing recompute resumes) OK on both runtimes. Follow-ups applied by the parent: stable
  keeps the restore-by-hand checks before the recompute (`UndoMode == 0` guard in EditPanelTest and assertShapeBack),
  RecomputeElsewhereTest (verifier P1) added.
- L5 T2 (worker mwf2absf-f-fxru, partial): S4 not reproduced in 337 local weekly runs (shard 2/2 x7 incl. under load,
  exact CI order replays, 320 pair runs); CI run 43441208207 (same tree) passed it: a rare flake, assertion unknown
  because unittest prints details only at the end and the shard was killed by the S2 hang. Found and fixed a real
  isolation leak: CutoutFoldedBarFixture removed the `_edit_sketch` patch before close_dialog processed events, so the
  real Sketcher and a depth-panel listener fired in the next test (RED FixtureIsolationTest on both runtimes, GREEN);
  the loose-tube assertions print the panel message. Parent: ci/run-tests.FCMacro ImmediateDetailsResult writes each
  failure/error/subtest traceback as soon as it happens (RED ci/tests/test_immediate_failures.py "18 not less than 1",
  GREEN; ci/tests 210 OK). Focused weekly and stable: RecomputeElsewhereTest 1, EditPanelTest 4, RemoveTest 4,
  ExpressionTest 5, test_cutout_folded_bar 13, all OK.
- L6 PR #150 CI run 43448518357: all 4 native shards (stable too) stopped at their timeouts (480/540 s) in
  test_drill_hole_panel, no failures; the post-#149 main run 43441208207 also timed out on both stable shards (required
  check red on main), while PR #149's run of the same tree passed. Not a hang: locally test_drill_hole_panel takes
  117 s alone and 131 s after test_cutout_folded_bar; a stable shard reached only 688 of ~980 tests in 480 s: the suite
  outgrew 2 shards. User chose "4 grupos, mismo tiempo (recomendado)" (stable and weekly 4 shards at 480/540 s;
  nightly max repetitions 20 -> 9 to keep (9+1) x 4 x 480 s + setup within the 355-minute job).
- L7 T4: ci/targets.json shards 4/4; ci/tests/test_policy.py pins; test_nightly_policy MAX_REPETITIONS = 9;
  nightly.yml limit 1-9 and budget comment; docs/ci.md. ci/tests 210 OK.

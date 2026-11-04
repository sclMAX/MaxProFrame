Drill Hole follow-ups left open by odd/tasks/hole-command.md (L10, L13, L19).
Branch: feat/drill-hole-followups.

## Specs

- S1. End Miter base (L1): a hole made through the panel on an End Miter trim is created and Valid, like the Extend / Cut and Notch bases (hole-command L10).
- S2. Guard OK/Cancel during a recompute (L1): OK or Cancel pressed while a panel recompute runs (it pumps Qt events) waits for that recompute to end, then runs and closes the dialog. OK keeps the last values typed in one Undo step; Cancel leaves the document unchanged. No recompute starts inside another one.
- S3. Language leak (L1): find the test that leaves FreeCAD in Spanish for the tests after it, and make it restore the language.

## Tasks

- T1 (S1) End Miter base in test_a_hole_on_an_extend_cut_trim_a_notch_or_an_end_miter_is_created_and_valid. Route: inline. Commit: 743dcb1. Done.
- T2 (S2) Deferred OK/Cancel in DrillHoleTaskPanel. Route: inline. Commit: 03482f5. Done.
- T3 (S3) Language leak: probe the full suite, pin the runner language. Route: inline. Commit: see L5. Done.

## Log

- L1. User: "3" — item 3 of the pending list the parent offered: Drill Hole follow-ups (a test on an End Miter base; guard OK/Cancel during a recompute; find the test that leaks the Spanish language).
- L2. T1: the End Miter subtest (second profile from the tube end, (300, 0, 0) to (300, 200, 0)) passed at once: existing behavior, no RED expected. test_drill_hole_panel 24/24.
- L3. T2 decision (parent): OK/Cancel during a recompute are deferred, not ignored. RED: both tests `AssertionError: Lists differ: [True] != [False]` (the button ran inside the recompute). Fix: `_defer` stores the button, `_update_preview` runs it after the recompute loop and closes the dialog (`Gui.Control.closeDialog`); a deferred button stops further pending previews. GREEN test_drill_hole_panel 24/24, no "Recursive calling of recompute".
- L4. Native review of 743dcb1..03482f5 (lenses resilience, reliability): approved and acknowledged. Advisory WARNINGs, left as follow-ups: a deferred OK/Cancel stays stored when `_update_preview` raises outside `_preview`'s own try (it could fire on a later preview); a pending preview is skipped when the deferred OK fails (OK has already previewed the panel values).
- L5. T3: no test leaks the language. A probe (scratch copy of the repo, `unittest.TestCase.run` wrapped in ci/run-tests.FCMacro) logged after every test the Language preference and `translate("frameforge", "Drill Hole")`: after the first test of the full suite, Language "" and "Agujero". The same test alone stays English (with LANG en_US.UTF-8 or es_AR.UTF-8); alone plus `from freecad.maxproframe import InitGui` it ends in Spanish. Cause: the isolated runner leaves Language "", so FreeCAD follows the system language (es_AR on this machine); importing InitGui at discovery (tests/test_toolbar_translations.py:24) and every `use_language` restore of "" call `Gui.updateLocale()` with the MaxProFrame translations loaded. CI runs on an English system, so it never showed. Fix: ci/run_tests.py writes Preferences/General Language = English into the isolated user.cfg; ci/tests/test_policy.py test_notification_preferences_exist_at_child_launch pins it. RED: `Lists differ: [('FCParamGroup', {'Name': 'NotificationArea'})] != [... 'General' ..., ... 'NotificationArea' ...]`. GREEN ci/tests 205 OK; full native suite with the probe: `Test suite succeeded (1071 tests executed)`, English throughout (test_workbench_translation_loading switches to Spanish on purpose and restores it in tearDownClass). The DrillHoleFixture English set-up stays (harmless, explicit).

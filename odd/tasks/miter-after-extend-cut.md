# Miter after Extend / Cut: End Miter uses the real stretch of a trimmed profile

End Miter finds joints and builds its planes from the sketch path ends, so a profile shortened by Extend / Cut never meets the profile it now ends on.
Branch: `fix/miter-after-extend-cut` (from `main` 795189e). Native runner: `python3 ci/run_tests.py --freecad-bin .git/ci-policy-runtime/squashfs-root/AppRun --reports <dir> --timeout 1200 [--test <module>]`.

## Specs

- S1. "no permite un inlgete luego de un extend/corte" — after an Extend / Cut shortens a profile so it ends on another one, End Miter finds that corner and miters it.
- S2. Agreed: only End Miter uses the real stretch ("Solo en Inglete"): the path cut or stretched to what the shown body (trim, cutout) covers, both to find joints and to build the miter planes. Extend / Cut and Notch are unchanged.
- S3. The miter panel lists one entry per profile: a profile and a trim built on it are not listed together; the trim (the body shown) is kept.

## Tasks

- T1 (S1, S2) Real stretch for End Miter joints and planes, with native geometry and panel tests. Route: inline. Commit: see L5. Done.
- T2 (S3) Miter panel keeps one entry per profile chain. Route: inline. Commit: see L6. Done.
- T3 (S1-S3) Tutorial, CHANGELOG, full native suite. Route: inline. Commit: see L7. Done.

## Log

- L1. User: "Bien analicemos un caso para resolver: - Tengo esta estructura [Image#5]. - Hago este corte [Image#6]. - Si luego quiero hacer un inglete no me lo permite [Image#7]" and "no permite un inlgete luego de un extend/corte". Image 7: Miter Ends panel lists Profile_002, Profile_002_Tr and Profile_003, "Se crearán 0 uniones."
- L2. Cause: `create_end_miter_tool.analysis` measures `_base_profile(obj).Target` path edges and `miter_joints.find_joints` pairs path ends; `TrimmedProfile.miter_planes` builds `Member` from the path and the base profile shape. The shortened profile's path still reaches the frame corner, so the crossbar end sits mid-path (a T, refused by `_reaches_corner`). `add_member` accepts a profile and its trim together.
- L3. User choice: "Solo en Inglete (Recomendado)".
- L4. Reproduced (RED): test_miter_after_extend_cut, side A 0..500 cut on the far face of crossbar C (x = 300) keeping End: '0 joints will be created.' != '1 joint will be created.'.
- L5. T1: `miter_geometry.real_stretch(edge, shape, base_shape)` moves a straight path end to where the shown body ends only when the trim moved it relative to the base profile (untouched ends keep the path end, so untrimmed profiles are unchanged); used by `EndMiterTaskPanel.analysis` and `TrimmedProfile.miter_planes` (`_stretch_member`); `_miter_member` (Extend / Cut, Notch) unchanged. Fixing only detection fails OK with "Profile_Tr_Mt: max() arg is an empty sequence" (wrong end), so both are needed. A first version stretched every body to its full reach and moved the skipped point of test_end_miter_panel / test_end_miter_preview from (0, 0, 0) to (0, -16.7, 0) (end offsets); the per-end rule fixed it. GREEN test_miter_after_extend_cut 3/3; end_miter_panel 13/13, end_miter_preview 26/26, anchors 2/2, edit 6/6, extend_gap 6/6, geometry 6/6, translations 4/4, miter_followups_geometry 8/8, extend_cut_geometry 11/11, keep_end_geometry 11/11, notch_geometry 7/7.
- L6. T1 committed 276d076. T2: RED TestOneEntryPerProfile (3 members listed instead of 2, both orders). `add_member` refuses a body another member is built on and replaces the members the new one is built on. GREEN test_miter_after_extend_cut 4/4, end_miter_panel 13/13, end_miter_edit 6/6, end_miter_preview 26/26.
- L7. T2 committed 18b7b8f. T3: tutorial End Miter step 3 (real ends, one entry per profile) and two CHANGELOG entries. Full native suite (`--timeout 1200`): "Ran 991 tests in 391.360s" OK, exit 0. Known limit: curved paths keep their sketch ends.
- L8. Native review review-f22208fb091381b9 (committed-only, base 795189e, lenses risk + reliability, 226 lines): approved and acknowledged (authority burned). The first group capture was refused before running (a binding altered when copied) and resubmitted unchanged. Non-blocking findings (ids and locations only): R1-001 and R3-002 trimmed_profile.py:341-342 (miter_planes on the real stretch), R3-001 miter_geometry.py:146-152 (end reach rule), R3-003 tests/test_miter_after_extend_cut.py:51-65 (fixture), R3-004 create_end_miter_tool.py:229-231 (one entry per profile).
- L9. User: "Arregla los 4" (L8). RED TestRealStretch.test_an_oblique_cut_of_a_round_tube_reaches_its_tip (100.0 != 120.0: vertices miss the ellipse tip). `_reach` now measures points along every edge (REACH_DEFLECTION 0.01 mm); an end counts as moved beyond MOVED_TOLERANCE 1e-3 mm. New pins (passed at once): end cut back, trimmed twice, a miter saved on a shortened trim recomputes at its real end, a miter at an end the trim did not move equals the untrimmed miter, curved path kept, clicking the base under a listed trim (plain and Ctrl) changes nothing, clicking a trim replaces its base. test_miter_after_extend_cut 12/12; end_miter_panel 13/13, preview 26/26, geometry 6/6, edit 6/6, extend_gap 6/6, anchors 2/2, miter_followups_geometry 8/8.
- L10. Full native suite after 88797c0 (`--timeout 1200`): "Ran 999 tests in 398.259s" OK, exit 0.

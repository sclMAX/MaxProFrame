Follow-ups of release 1.10.2 (Extend/Cut honors App::Part placements).
Branch: fix/trim-container-followups. Engram mirror: odd/trim-container-followups/tasks.

## Specs

- S1: "Notch ignores App::Part placements (same bug class)." A Notch whose profile and target sit in differently placed App::Part containers must cut where the target really is, as Extend/Cut does since 1.10.2 (including gap, KeepEnd and Flip side).
- S2: "Trims don't recompute automatically when a Part placement changes (no dependency link)." After moving the App::Part that holds a trim's body or its target, the Extend/Cut and Notch trims follow without a manual recompute.
- S3: "Minor: NURBS normal taken at (0,0); rotated-target recompute test." Target face normals are taken on the face itself, not at surface parameter (0,0); a test covers a target inside a rotated Part.

## Tasks

- T1 (S1) inline — Notch moves the target into the body frame (`in_frame_of`) in cutter, crossing and kept-end checks; tests in tests/test_notch_geometry.py. Commit: 8da9266
- T2 (S3) worker — normal at the face centre parameter (trimmed_profile, extend cut panel); tests for rotated target, degenerate NURBS, NURBS with parameters past 0. Commit: 460cb41, 7b6e0c6
- T3 (S2) worker — document observer touches trims when a GeoFeatureGroup placement changes; tests; CHANGELOG. Fix B1: touch only when the move between the containers of body and target differs from the one the last recompute of the trim used. Commit: 3b7b77e, 7b6e0c6

## Log

- L1: "vamos con los 3" (after the proposal: 1. Notch ignores App::Part placements; 2. trims don't recompute automatically when a Part placement changes; 3. minor: NURBS normal at (0,0) and rotated-target recompute test).
- L2: Exploration: trim lives in the body's container, so a plain link to that container would form a cycle; chosen approach for S2 is a document observer.
- L3: T2 evidence: on a flat NURBS triangle degenerate at (0, 0), normalAt(0, 0) returns the plane normal; the rotated-target test passed already. Only tests added.
- L4: Full suite 1343 OK (stable 1.1.4). Native review approved and acknowledged (lineage review-503ad3dd65ac590b); advisory: observer touch while a Placement changes during recompute (expressions), full document scan per Part placement change.
- L5: Independent verify: S1 met. S2 blocker B1: an expression on the Placement of the Part holding the body leaves the trim Touched forever (recompute returns 4 each time; baseline 0) — observer touches during recompute. S3 blocker B2: a flat NURBS face whose parameters start past 0 gives a flipped normal at (0, 0) (whole target in a prism: cut at 425 instead of 375; same on base); fix: normal at face.Surface.parameter(face.CenterOfMass). T2 and T3 reopened.
- L6: B1 and B2 fixed in 7b6e0c6. B1: the observer touches a trim only when the move between the containers of its body and target differs from the one its last execute used (module dict keyed by document and trim name, not saved; no record = touch). B2: `face_normal(face)` reads the normal at `face.Surface.parameter(face.CenterOfMass)` (orientation honored, Part.Plane too) in `_extend_cut_side`, `_crossed_face` and `parallel_problem`. RED: test_an_expression_placing_the_part_of_the_profile_settles ('Touched' != 'Valid'), test_flat_nurbs_faces_whose_parameters_start_past_zero_face_the_right_way (425.0 != 375.0); rotated-Part Notch and Undo/Redo tests passed already. GREEN: test_notch_geometry 30, test_extend_cut_geometry 20, test_extend_cut_panel 45, test_notch_panel 30, test_keep_end_geometry 11, test_extend_cut_preview 22, test_notch_preview 9, test_notch_container 2, all OK (stable 1.1.4).

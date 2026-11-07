Follow-ups of release 1.10.2 (Extend/Cut honors App::Part placements).
Branch: fix/trim-container-followups. Engram mirror: odd/trim-container-followups/tasks.

## Specs

- S1: "Notch ignores App::Part placements (same bug class)." A Notch whose profile and target sit in differently placed App::Part containers must cut where the target really is, as Extend/Cut does since 1.10.2 (including gap, KeepEnd and Flip side).
- S2: "Trims don't recompute automatically when a Part placement changes (no dependency link)." After moving the App::Part that holds a trim's body or its target, the Extend/Cut and Notch trims follow without a manual recompute.
- S3: "Minor: NURBS normal taken at (0,0); rotated-target recompute test." Target face normals are taken on the face itself, not at surface parameter (0,0); a test covers a target inside a rotated Part.

## Tasks

- T1 (S1) inline — Notch moves the target into the body frame (`in_frame_of`) in cutter, crossing and kept-end checks; tests in tests/test_notch_geometry.py. Commit: (this commit)
- T2 (S3) inline — normal at the middle of the face parameter range; rotated-target and off-origin NURBS tests. Commit: pending
- T3 (S2) inline — document observer touches trims when a GeoFeatureGroup placement changes; tests; CHANGELOG. Commit: pending

## Log

- L1: "vamos con los 3" (after the proposal: 1. Notch ignores App::Part placements; 2. trims don't recompute automatically when a Part placement changes; 3. minor: NURBS normal at (0,0) and rotated-target recompute test).
- L2: Exploration: trim lives in the body's container, so a plain link to that container would form a cycle; chosen approach for S2 is a document observer.

# Miter joints

Rebuilds End Miter around the real member axes and adds a panel to miter two or more whole profiles, with extension and a configurable gap.
Branch: `feat/miter-joints`.

## Specs

- S1. "Si" (reproduce the suspected miter defects in FreeCAD before touching code): offsets, rotation, edge topology, `getTarget` loop, container placement.
- S2. The miter cut follows the real position of each profile (anchor, offset, rotation, mirror, edge direction), not the anchor names.
- S3. "EL boton en la barra siempre activo, al clickear abra el panel y permita seleccionar los perfiles que queremos unir en inglete (dos o mas)"
- S4. "la seleccion me gustaria como hacemos en crear perfil, al hacer click sobre el perfil se selecciona todo el perfil (no solo una cara)."
- S5. "tener una opcion "extender" activada por defecto, si esta activada extienda los perfiles para un inglete perfecto si un perfil es mas coro y no llega al vertice del inglete."
- S6. "un gap configurable para el inglete por ejemplo poder poner 0.5 y que el inglete deje 0.5mm entre las dos caras del corte"
- S7. "saltemos ese punto por ahora lo analizaremos en profundidad en el futuro como una nueva feature" — a point where three or more selected profiles meet is skipped and reported, not mitered.

## Tasks

- T1 (S1) Reproduction probe in FreeCAD, scratch only (`.git/miter-probe/`). Route: inline. Commit: none. Done (L5).
- T2 (S2) Geometry core: miter plane through the crossing of the real member axes, normal `u1 - u2`; fix the `getTarget` loop, collinear edges, unbound `cut_shape`, active-document edge lookup. Route: inline. Commit: see git log (L6, L7). Done.
- T3 (S5, S6) Extension up to the miter plane (bounded at 10x the section diagonal) and `MiterGap` (each member cut back gap/2); properties `MiterExtend` (default True) and `MiterGap`. Tests: `tests/test_end_miter_extend_gap.py`. Route: gentle-ai-worker (context backstop). Commit: see git log (L8). Done.
- T4 (S3, S4, S7) Always-active command and miter panel: whole-profile selection, two or more profiles, one cut object per profile, automatic corner detection, skip 3+ member points with a warning, Extend (default on) and Gap controls. The new trims are placed in the body's own container (closest folder or Part/Body, like Create Profile), which fixes the nested Part shift for End Miter. Joint rule: two selected members form a joint when their path ends are the closest ends of the pair and the crossing of their end axes is within the extension limit of both ends; a member end claimed by two or more joints is a 3+ point (S7). Route: gentle-ai-worker (context backstop). Commit: pending.
- T5 (S1, S3) Container placement for End Trim (`Parents[-1]` pattern in create_trimmed_profiles_tool.py), editing an End Miter opens the miter panel, docs and CHANGELOG. Route: inline. Commit: pending.

## Log

- L1. User: "Si, tambien me gustaria hacer unas mejoras: - EL boton en la barra siempre activo, al clickear abra el panel y permita seleccionar los perfiles que queremos unir en inglete (dos o mas) la seleccion me gustaria como hacemos en crear perfil, al hacer click sobre el perfil se selecciona todo el perfil (no solo una cara). ademas tener una opcion "extender" activada por defecto, si esta activada extienda los perfiles para un inglete perfecto si un perfil es mas coro y no llega al vertice del inglete. que opinas?"
- L2. User: "otra cosa que quiero agregar es un gap configurable para el inglete por ejemplo poder poner 0.5 y que el inglete deje 0.5mm entre las dos caras del corte"
- L3. User, on three or more profiles meeting at one point: "saltemos ese punto por ahora lo analizaremos en profundidad en el futuro como una nueva feature"
- L4. Agreed in conversation: one cut object per profile holding all its boundaries; the panel applies one gap value to every profile of the operation; extension has a maximum to avoid runaway extensions with nearly parallel members; length/BOM report the real cut length.
- L5. T1 probe (FreeCAD 1.1.4, 50x50x2 tube, pre-extended 50 mm): perfect joints for chained Center/Center, Left/Left, mixed anchors, 60 degrees, corner rotated 30 degrees. Defects: start-start edges with Left/Left (cut faces share 0 of 543 mm2); OffsetX on one profile (226/543); Left with one profile rotated 90 degrees (11/543); collinear edges fail with "Three points are collinear"; `getTarget` on a plain object never returns; nested Parts put the miter in `Outer` and shift it 1000 mm. OffsetY on one profile, and Left rotated 90 degrees, lift a section out of the sketch plane: no perfect miter exists there.
- L6. T2 RED: 5 failures in `test_end_miter_geometry` (3 joints, `getTarget` loop, angle `@ 60.00000000000001`). New `miter_geometry.py`: section centroid from a slice of the base profile at mid-edge, transported to the joint end; plane through the crossing of both axes, normal `u1 - u2`; half-space cut. Rotated case changed to 180 degrees (in-plane); RED confirmed on base code. GREEN: `test_end_miter_geometry` 6/6, `test_end_miter_anchors` 2/2, `test_trimmed_profile_pid` 2/2, `test_trimmed_profile_migration` 3/3.
- L7. Full native suite on T2: `Ran 688 tests ... OK`.
- L8. T3 (worker): RED `test_end_miter_extend_gap` 6 tests, failures=3 errors=3; GREEN 6/6; geometry/anchors/pid/migration pass. The 10x limit is measured along the member axis (section centroid), not from the raw path end. Full native suite: `Ran 694 tests ... OK`. Slice boundary: T2 alone was 441 lines (commit 0a3d641); T3 is its own commit.

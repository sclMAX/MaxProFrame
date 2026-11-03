# Hole: round holes on a profile face, placed from a vertex

New command that drills round holes on a face of a profile, positioned by offsets from a vertex of that face, with a diameter and a depth.
Branch: `feat/hole-command` (from `main` ae36455, v1.4.0). Native runner: `python3 ci/run_tests.py --freecad-bin .git/ci-policy-runtime/squashfs-root/AppRun --reports <dir> --timeout 900 [--test <module>]`.
Status: T1 done (L7); T2-T4 pending.

## Specs

- S1. "quiero un nuevo comando "hole" que permita colocar agujeros en las caras de un perfil" — a new command applies round holes to a face of a profile (the profile, or a trim / cutout built on it).
- S2. "seleccionar su pocicion con referencia a los vertises" and "seria mejor cualquier vertice" — the hole position is given by offsets from any vertex of the chosen face, chosen by the user (not only the profile ends).
- S3. "setear el diametro y profundidad" — the user sets the hole diameter and depth.
- S4. Approved (L6): the reference survives topology changes. Store the face/vertex link and a snapshot of the vertex position in profile-local coordinates; on recompute use the linked vertex when it is still at the snapshot (within tolerance), otherwise re-link to the nearest vertex of the face within tolerance, otherwise keep the snapshot position and mark the object with a visible warning ("la referencia cambió, revisá el agujero"). The hole never moves silently.
- S5. Approved (L6): offsets are measured on the face axes, one along the profile and one across it, so "25 mm from the corner" keeps its meaning when the profile is rotated.
- S6. Approved (L6): first scope is one hole or a linear pattern (count + pitch along the face, in the same object) on planar faces, depth **One wall / Through All / Distance** (reusing the cutout depth logic), live preview and one Undo step; double-click edits it.
- S7. Decided (L6): the command is named **Drill Hole** (Spanish *Agujero*); **Cutout / Hole** keeps its name for free shapes.
- S8. Decided (L6): a non-planar face (round tube, IPN fillets) is refused with a message in the panel.

## Tasks

- T1 (S1, S3, S6, S8) `Hole` feature object: face/vertex link, offsets, diameter, depth type and depth; cylinder cut chained on the profile like the cutout; native geometry tests. Route: inline. Commit: see L7. Done.
- T2 (S2, S4, S5) Reference resilience: vertex snapshot in profile-local coordinates, re-link by nearest vertex, warning state; tests that the hole stays put after Extend / Cut, End Miter and Notch. Route: inline. Commit: pending.
- T3 (S1-S3, S6-S8) Command and task panel: pick face, pick vertex, offsets, diameter, depth, live preview, one Undo step, edit by double-click; panel tests. Route: inline. Commit: pending.
- T4 (S1-S8) Icon, tree label after the profile, Spanish catalog, tutorial, CHANGELOG Unreleased, full native suite. Route: inline. Commit: pending.

## Log

- L1. User: "Bien, nosotros investiguemos una nueva feature, quiero un nuevo comando "hole" que permita colocar agujeros en las caras de un perfil, seleccionar su pocicion con referencia a los vertises y setear el diametro y profundidad que opinas? pros  contras?"
- L2. Assistant proposal: pros (no Sketcher round trip, shop-drawing style dimensions, parametric, reuses cutout depth logic); cons (overlaps the existing Cutout / Hole name, vertex index references break on trims, non-planar faces). Recommended anchoring to profile ends; asked whether ends or any vertex.
- L3. User: "seria mejor cualquier vertice".
- L4. Assistant proposal: link + geometric snapshot with re-link and warning (S4), offsets on face axes (S5). Note: MaxProFrame builds shapes in Python without operation history, so the FreeCAD 1.x element map does not keep `VertexN` stable across trims. The existing cutout has the same weakness (`baseObject` stores `FaceN`, extruded_cutout.py:146, :246-249).
- L5. User: "Si" (create this feature document for review before code).
- L6. User answers: S4-S5 "Sí, así" (link + geometric backup + warning, offsets along and across the face); D1 "Drill Hole / Agujero"; D2 "Rechazarlas con mensaje"; D3 "Con patrón lineal" (count + pitch in the same object).
- L7. T1: `DrillHole` subclasses `ExtrudedCutout` (keeps `baseObject`, so `is_extrudedcutout`, the cut list, IDs and trims treat it as a cutout; `Sketch` stays None and hidden). New properties ReferenceVertex, OffsetAlong, OffsetAcross, Diameter, Count, Pitch; depth reuses CutType/ExtrusionLength (default One wall). Offsets point into the face from the picked vertex (along the profile axis projected on the face, across square to it). Cutout depth logic moved to shared `cut_tools()` in extruded_cutout.py. RED: `ModuleNotFoundError: No module named 'freecad.maxproframe.drill_hole'`. GREEN test_drill_hole_geometry 7/7; regression test_cutout_one_wall 11, test_cutout_direct 1, test_cutout_depth_panel 9, test_cutout_flow 19, test_extruded_cutout_pid 2 OK.

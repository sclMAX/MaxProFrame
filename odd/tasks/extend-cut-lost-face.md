# Extend / Cut keeps its target face after the frame changes
Bug fix: an Extend / Cut trimmed against a face of a miter fails with "?Face2 ... is not planar" after the base sketch
changes size, because FreeCAD loses the face name; the trimmed piece then keeps its old shape and does not follow.

## Specs
- S1 Reported failure: "cambie la medida del croquis base y salen estos errores cuando recalculo" ...
  "<class 'freecad.maxproframe.miter_geometry.MiterError'>: Extender / cortar: la cara destino ?Face2 de
  Profile_TC80x40x1.5_000_Mt no es plana." ... "el primer perfil del patron no se mueve con el croquis" and
  "El error aparece si habro el archivo y cambio el croquis sin hacer patron" -> after a change of the base sketch
  (VarSet Ancho / Largo of the user's table), an Extend / Cut whose target face is a face of an End Miter (or any
  trimmed piece) recomputes without error and its piece follows the frame: it ends on the same face of the target
  where it was placed, now moved.
- S2 Same log: "<PropertyLinks> PropertyLinks.cpp(552): Mesa8p#Profile_004_Tr.TrimmingBoundary missing element
  reference Mesa8p#Profile_000_Mt ...Face2" -> when FreeCAD reports the face as missing ("?FaceN"), the trim finds its
  face again (as Drill Hole does for its base face, drill_hole.py MISSING_ELEMENT_PREFIX) instead of failing; when no
  face of the target can be the one it was placed on, it fails with a message naming the target, as today.

## Tasks
- T1 S1 S2 reproduce on a copy of the user's file and in a fixture; re-find the lost target face; tests; CHANGELOG —
  worker — commit: pending (uncommitted in the worktree; tests green)

## Log
- L1 (user): "cambie la medida del croquis base y salen estos errores cuando recalculo: [log: Profile_PGC100_000_Tr / _Tr_Tr: Profile_004_Tr links are out of scope. Out of scope links to: PGC100; MiterError: Extender / cortar: la cara destino ?Face2 de Profile_TC80x40x1.5_000_Mt (and _002_Mt) no es plana.] el primer perfil del patron no se mueve con el croquis"
- L2 (user): "/home/max/GoogleDrive/INDUMATICS/FreeCAD/DESARROLLOS/MUEBLES/ARMABLES/MESAS/Mesa8persona/Mesa8p.FCStd, Cantidad mas paso, no guarde los cambios. El error aparece si habro el archivo y cambio el croquis sin hacer patron" (log adds: PropertyLinks.cpp(552) ... TrimmingBoundary missing element reference ... Face2). Screenshot: Part with Sketch, four TC80x40x1.5 _Mt, Profile_PGC100_000_Tr_Tr (slat) at one short end; VarSet Ancho 1100 mm, Largo 2180 mm.
- L3 (evidence): a copy of the user's file is at /tmp/mpf-mesa/Mesa8p.FCStd (never edit the original). The bug is on main (no pattern needed).
- L4 (note): the "links are out of scope ... PGC100" line is a separate warning (a trim's CustomProfile local link to a section outside the Part); not in this fix unless it causes the failure.
- L5 (evidence, T1 RED on a copy of the user's file): VarSet Ancho 1100 -> 1200, Largo 2200 -> 2300 (the file holds 2200, not 2180), recompute: PropertyLinks.cpp(516) "Profile_004_Tr.TrimmingBoundary missing element reference ... Profile_000_Mt ...Face2" (same for _Tr_Tr / Profile_002_Mt), link now ('?Face2',); Profile_004_Tr invalid with "Extend / Cut: the target face ?Face2 of Profile_TC80x40x1.5_000_Mt is not planar.", Profile_004_Tr_Tr left Touched; slat stays at x[-510, 510] y[-1050, -950] while the sides moved to x = -560 / 560. Recomputing the file unchanged keeps the names: only a new size loses them. The face is still there (Face2 at x = -560, normal +X): only its mapped name is lost. Root cause: _extend_cut_side read target.getSubObject("?Face2") (not a face) and raised.
- L6 (evidence, T1 fixture RED): tests/test_extend_cut_lost_face.py, a Part (moved and turned) with a sketch rectangle sized by a VarSet, four 50x50 sides ending at their path ends, End Miters (each side extended to the corner), a slat cut twice by Extend / Cut on the inner faces of two sides. Sides with end offsets (no miter extension) kept their face names; without them the names are lost as in the user's file. Before the fix 4 tests failed with "Extend / Cut: the target face ?Face1 of ... is not planar." / the link left at '?Face1'.
- L7 (decision, T1 re-find rule): an Extend / Cut remembers, out of the saved document, the face it ends on: target name, face name, and the face point and normal in the frame of the profile the target is built on (its global placement, which follows the sketch path). Taken when the document opens (from the saved shapes) and on every successful recompute. When the link names a lost face ("?FaceN") or a name that is no flat face, the face is found again among the flat faces of the target facing the remembered normal (1e-5 rad) whose plane holds the remembered point (1e-3 mm): FaceN when it is one of them, else the nearest to the point. Same normal and same distance from the axis is what stays when the sketch moves the side: the old absolute position does not. No such face: the existing error naming the target. A name FreeCAD still resolves to a flat face is used as before. During the recompute the trim rewrites TrimmingBoundary to the found name (no touched state is left), so the link heals, the panel and a saved file see a valid face and the next change works after reopening.
- L8 (evidence, T1 GREEN): user's file copy, Ancho/Largo 1200/2300: Profile_004_Tr_Tr x[-560, 560] y[-1100, -1000], Length 1120 (was 1020); 1000/2180: x[-460, 460], Length 920; back to 1100/2200: x[-510, 510], Length 1020, volume 326729.1076 as opened; links ('Face2',); no invalid or touched objects. Copy saved after the changes and reopened, 1300/2400: x[-610, 610], Length 1220. Opened unchanged and recomputed in full: every trim volume within 1e-9, bound box unchanged.

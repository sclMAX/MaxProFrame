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
  worker — commit: pending

## Log
- L1 (user): "cambie la medida del croquis base y salen estos errores cuando recalculo: [log: Profile_PGC100_000_Tr / _Tr_Tr: Profile_004_Tr links are out of scope. Out of scope links to: PGC100; MiterError: Extender / cortar: la cara destino ?Face2 de Profile_TC80x40x1.5_000_Mt (and _002_Mt) no es plana.] el primer perfil del patron no se mueve con el croquis"
- L2 (user): "/home/max/GoogleDrive/INDUMATICS/FreeCAD/DESARROLLOS/MUEBLES/ARMABLES/MESAS/Mesa8persona/Mesa8p.FCStd, Cantidad mas paso, no guarde los cambios. El error aparece si habro el archivo y cambio el croquis sin hacer patron" (log adds: PropertyLinks.cpp(552) ... TrimmingBoundary missing element reference ... Face2). Screenshot: Part with Sketch, four TC80x40x1.5 _Mt, Profile_PGC100_000_Tr_Tr (slat) at one short end; VarSet Ancho 1100 mm, Largo 2180 mm.
- L3 (evidence): a copy of the user's file is at /tmp/mpf-mesa/Mesa8p.FCStd (never edit the original). The bug is on main (no pattern needed).
- L4 (note): the "links are out of scope ... PGC100" line is a separate warning (a trim's CustomProfile local link to a section outside the Part); not in this fix unless it causes the failure.

Drill Hole continue: remember the last diameter, and an "Apply and continue" button that commits the hole and keeps the panel open for the next face, on another profile or the same one.
Branch: feat/drill-hole-continue. One PR.

## Specs

- S1. Remember the last diameter (L1): "Recordar el ultimo valor de diametro." Stored in FreeCAD preferences (App.ParamGet, survives a restart) when a hole is confirmed (OK or Apply and continue), never on Cancel. A new drill hole opens with it; editing an existing hole shows that hole's own diameter. First use: today's default.
- S2. Apply and continue (L1): "Agregar un boton que permita guardar y seguir agregando agujeros por ejemplo si quiero hacer agujeros en 3 perfiles poder hacer el agujero en el primer perfil apretar un boton (que confirme ese agujero) y seguir agregando agujeros en el otro perfil sin tener que activar el comando de nuevo." The button creates the current hole in its own Undo step and keeps the panel open, waiting for a click on a face. Only while creating, not while editing an existing hole.
- S3. Values kept (L2, option A): after Apply and continue the panel keeps every value (offsets, diameter, pattern, cut type, depth); only the face and the reference point change with the next click.
- S4. Same or another profile (L3): "se debe poder hacer click en otro perfil o en el mismo por ejemplo si quiero hacer un agujero en 2 caras del mismo tubo o si quiero hacer un agujero en lada extremo del mismo perfil hago click en el perfil -> ubico el agujero en una cara y punto -> \"Aplicar y seguir\" -> hago click en el otro extremo del perfil -> ubico el agujero ..." A click on the profile already drilled lands on the visible drill hole, so the next hole chains on it (base = the previous drill hole), and both holes stay cut.
- S5. Close and cancel (accepted proposal, L1): Cancel after Apply and continue drops only the hole in progress; the applied holes stay. OK with no face picked yet just closes the panel.

## Tasks

- T1 [x] S1: remember the diameter in preferences. Route: worker, test-first. Commit: feat(drill-hole) on feat/drill-hole-continue. Done in 839b147.
- T2 [x] S2-S5: Apply and continue button, reset to waiting for a face, chaining on the same profile. Route: worker, test-first. Commit: feat(drill-hole) on feat/drill-hole-continue. Done in 6dd858e.
- T3 [x] S1-S5: Spanish (both .ts, .qm via compile_translations.py), tutorial (docs/tutorial.md#drill-hole), CHANGELOG Unreleased. Route: with T1/T2 commits. Done in 839b147 (S1 docs) and 6dd858e.

## Log

- L1. User (verbatim): "Quiero hacer unas mejoras en drill [Image#1]: - Recordar el ultimo valor de diametro. - Agregar un boton que permita guardar y seguir agregando agujeros por ejemplo si quiero hacer agujeros en 3 perfiles poder hacer el agujero en el primer perfil apretar un boton (que confirme ese agujero) y seguir agregando agujeros en el otro perfil sin tener que activar el comando de nuevo. Que opinas?" Parent proposal: diameter in App.ParamGet saved on OK/Apply, not on Cancel, edit shows its own value; button "Apply and continue" (Spanish "Aplicar y seguir") commits its own Undo step; Cancel drops only the hole in progress; OK with no face just closes.
- L2. User chose option A: keep every value, only the face and reference change.
- L3. User (verbatim): "A, sobre el punto 2. \"El panel queda abierto, esperando que hagas clic en una cara de otro perfil.\" solo para aclarar, se debe poder hacer click en otro perfil o en el mismo por ejemplo si quiero hacer un agujero en 2 caras del mismo tubo o si quiero hacer un agujero en lada extremo del mismo perfil hago click en el perfil -> ubico el agujero en una cara y punto -> \"Aplicar y seguir\" -> hago click en el otro extremo del perfil -> ubico el agujero ..." Parent: the click lands on the visible drill hole, which chains the next hole on it.

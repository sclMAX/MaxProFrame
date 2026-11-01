# Trim: Extend/Cut and Notch

Splits the current Trim tool into two commands (Extend/Cut to a plane, Notch that copies the target shape) for release 1.0.0, removing FrameForge-era compatibility code.
Branch: `feat/trim-extend-notch` (from `main` c971d79). Native runner: `python3 ci/run_tests.py --freecad-bin .git/ci-policy-runtime/squashfs-root/AppRun --reports <dir> --timeout 180 [--test <module>]`.

## Specs

- S1. "NO lanzamos la primera release asi que no hay archivos viejos, ademas no damos soporte a FrameForge asi que tampoco damos soporte a sus archivos." — remove trim compatibility code: version migrations, "Coped cut"/"Simple cut" aliases, migration tests.
- S2. Agreed in conversation: pin the current trim geometry with native tests before changing it (Perfect fit and Simple fit results).
- S3. "Deducir porque el boton aveses esta activado y aveces no." — the command is active only when nothing is selected or every selected item is exactly one face of a profile/trim; selecting the profile in the tree, an edge, two faces of one profile or a non-profile disables it with no hint. Agreed: keep the command available with an open document and explain invalid selections in the panel.
- S4. Agreed robustness fixes: `execute()` must not touch `ViewObject` (console mode), a null cut leaves the uncut body and reports it, Cancel in edit mode leaves no Undo entry.
- S5. "QUe opinas de tener dos botones el actual Extender/cortar y otro encastrar que copie la forma por ejemplo para dos perfiles I" — two commands: Extend/Cut (plane target) and Notch (copies the target profile shape).
- S6. "Poder seleccionar un perfil o cara (destino) y luego poeder seleccionar varios perfiles para que se extiendan o contraigan hasta el perfil o cara destino." — Extend/Cut: pick one target, then several profiles; each profile end nearest the target is extended or shortened to the target plane. One trim object per profile, all created in one Undo step.
- S7. "Posibilidad de agregar un gap." — Extend/Cut has a gap to the target plane.
- S8. "Previsualizacion automatica, desactivable con un checkbox." — live preview with a check box to turn it off.
- S9. "Seleccion con colores distintos destino con un color y perfiles a cortar con otro en preview." — target and profiles to cut are highlighted in different colors during the panel.
- S10. "a futuro quiero agreagar otros tipos de unione en bisel por ejemplo alguna para corte laser que deje unidad la esquina para plegar, solo para tenerlo en cuenta, lo veremos a futuro." — not implemented; the joint model must not assume every joint is an end cut against a target.

## Tasks

- T1 (S1, S2) Remove trim compatibility code and migration tests; add native geometry tests for the current End Trim. Route: inline. Commit: pending.
- T2 (S3, S4) Command availability with panel-side validation messages; execute without ViewObject; null cut fallback; edit Cancel without Undo entry. Route: inline. Commit: pending.
- T3 (S5, S6, S7, S10) Extend/Cut command, panel and object (target, profiles, gap, extend, nearest end), shared joint base. Route: decide at start. Commit: pending.
- T4 (S5) Notch command and panel from the current Perfect fit. Route: decide at start. Commit: pending.
- T5 (S8, S9) Preview with auto-update check box and target/profile colors. Route: decide at start. Commit: pending.

## Log

- L1. User: "Hola, trabajemos en "Trim" quiero que analices el estado actual y me digas como funciona y que puntos de mejora ves."
- L2. User: "Tengo algunas ideas: - Posibilidad de agregar un gap. - Poder seleccionar un perfil o cara (destino) y luego poeder seleccionar varios perfiles para que se extiendan o contraigan hasta el perfil o cara destino. - Previsualizacion automatica, desactivable con un checkbox. - Seleccion con colores distintos destino con un color y perfiles a cortar con otro en preview. - Deducir porque el boton aveses esta activado y aveces no. que opinas? ideas opciones pros y contras? recapitulemos"
- L3. User: "QUe opinas de tener dos botones el actual Extender/cortar y otro encastrar que copie la forma por ejemplo para dos perfiles I que opinas? pros contras?"
- L4. User: "NO lanzamos la primera release asi que no hay archivos viejos, ademas no damos soporte a FrameForge asi que tampoco damos soporte a sus archivos. asi que recapitulemos"
- L5. User: "Si va en la 1.0.0, el otro agente esta solo preparando la release no la lanzaremos aun. Otro tema a tener en cuenta es que a futuro quiero agreagar otros tipos de unione en bisel ... solo para tenerlo en cuenta, lo veremos a futuro." Then "si" to: branch `feat/trim-extend-notch` from main, this document, start with cleanup and geometry tests.
- L6. Delivery forecast: well over 400 authored lines across T1-T5; strategy `ask-on-risk`, asked before the first oversized PR slice.

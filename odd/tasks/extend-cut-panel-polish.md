# Extend / Cut panel polish: flip button state, change target, tree icon and label, edit preview

Four usability fixes the user found testing KeepEnd in the Extend / Cut panel (they also apply to Notch, which reuses the panel).
Branch: `feat/extend-cut-panel-polish` (from `main` e183278). Native runner: `python3 ci/run_tests.py --freecad-bin .git/ci-policy-runtime/squashfs-root/AppRun --reports <dir> --timeout 900 [--test <module>]`.

## Specs

- S1. "Si no hay nada seelccionado en la lista, el boton Invertir deberia estar deshabilitado." The Flip side button is enabled only while at least one row of the profiles list is selected, in creation and in edit.
- S2. "Agregar la posibilidad de cambiar el destino [...] si tengo algo seleccinado y apreito el boton extender, aparece la cara seleccionada como destino y si no es la que quiero no se puede cambiar hay que cerrar el comando y volvear a abrir." Agreed: a "Change target" button next to the target; after pressing it the next click becomes the new target, then clicks add profiles again.
- S3. "Podriamos usar el icono de extender para las operaciones de extender. Ademas de mostrar el label del perfil (por ejemplo TC40x40...)." Agreed: in the tree, Extend / Cut uses the Extend / Cut icon, Notch the Notch icon and End Miter the End Miter icon; new trims are labelled after the profile label, for example "Profile_TC40x40x1.5_001_Tr"; existing trims keep their label.
- S4. "Al editar no se muestra el preview de invertir." Agreed: while editing, changes (flip, target, gap) are applied live to the trim, with the discarded piece in red, like creation; Cancel undoes everything.

## Tasks

- T1 (S1) Flip side enabled only with a selected row. Route: inline. Commit: see L5. Done.
- T2 (S2) "Change target" button arms the next click as target. Route: inline. Commit: see L5. Done.
- T3 (S3) Tree icon per joint type; label new trims after the profile label. Route: inline. Commit: pending.
- T4 (S4) Live preview while editing, discarded piece in red, Cancel restores. Route: inline. Commit: pending.
- T5 (S1-S4) Spanish catalog, docs, CHANGELOG, full native suite. Route: inline. Commit: pending.

## Log

- L1. User: "Cosas a mejorar [Image#1] - Si no hay nada seelccionado en la lista, el boton Invertir deberia estar deshabilitado. - Agregar la posibilidad de cambiar el destino [Image#2] por ejemplo si tengo algo seleccinado y apreito el boton extender, aparece la cara seleccionada como destino y si no es la que quiero no se puede cambiar hay que cerrar el comando y volvear a abrir. - [Image#3] Podriamos usar el icono de extender para las operaciones de extender. Ademas de mostrar el label del perfil (por ejemplo TC40x40...). - [Image#4] Al editar no se muestra el preview de invertir."
- L2. User choices: change target with a "Cambiar destino" button (recommended); tree shows the command icon and the profile label, existing trims keep their label (recommended); live preview while editing (recommended).
- L3. T1: RED test_extend_cut_polish 3 tests `True is not false` (button always enabled). GREEN 3/3: enabled from the list selection, refreshed after every list rebuild.
- L4. T2: RED 5 tests `no attribute 'change_target_button'`. GREEN 8/8. Checkable "Change target" button (hidden while editing, disabled without a target); armed, the target label says "Click the new target face, or select a profile in the tree." (Notch: "Click the new target profile, or select it in the tree."); a refused click keeps it armed. Test note: use_language leaves a LanguageChange pending that resets Designer texts on the first event loop pass (test artifact, Spanish texts stay in real FreeCAD). Neighbours: keep_end_panel 22/22, extend_cut_panel 18/18, extend_cut_preview 22/22, notch_panel 22/22, notch_preview 7/7. black/isort unavailable locally (no pip/venv); lines checked by hand, CI checks format.

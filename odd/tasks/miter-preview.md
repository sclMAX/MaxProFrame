# Miter panel preview

Adds Ctrl+click deselection and an on-demand or automatic preview of the miters to the End Miter panel, following the Create Profile preview pattern.
Branch: `feat/miter-preview` (on top of `fix/miter-panel-ctrl-click`).

## Specs

- S1. "Debemos implementar Ctrl + Click para deseleccionar" — Ctrl+click on a listed profile removes it from the panel.
- S2. "podriamos mostrar un preview como hacemos con Crear perfil ?" — the panel previews the miters in the 3D view live, like Create Profile does (Create Profile has no visible Apply: its Apply group is hidden and previews update on every change).
- S3. "la 2 pero solo con el checkbox, sin boton actualizar." — an "Update automatically" check box, checked by default and remembered between sessions, and no Apply/Update button. Checked: the preview is recalculated on every change (selection, Ctrl+click, Extend, Gap). Unchecked: the preview stays as it is and the panel shows "Pending changes"; checking it again recalculates.
- S4. **OK** always confirms the current values in one Undo step, even when the preview is out of date; **Cancel** discards the preview and leaves the document as before.
- S5. Agreed in conversation: markers in the 3D view for detected joints, and in red for skipped points (three or more profiles), visible even when the preview is out of date.
- S6. "ademas deberiamos limpiar la ui y eliminar el boton aplizar de crear perfiles si no lo usamos es codigo muerto" — remove the hidden Apply button/group and its dead code from Create Profile; fix docs/commands.md, which still describes Apply.

## Tasks

- T1 (S1) Ctrl+click and face deselection drop a listed profile. Route: inline. Commit: cabaffb. Done.
- T2 (S2-S5) Live miter preview with the Update automatically check box, status label, joint/skipped markers, transaction handling, clicks on preview objects map back to their profile, Spanish translations, tutorial/README/CHANGELOG. Route: gentle-ai-worker (parallel, Writer rule). Commit: pending.
- T3 (S6) Remove Create Profile's hidden Apply button/group and dead code; docs/commands.md. Route: gentle-ai-worker (parallel, Writer rule). Commit: pending.

## Log

- L1. User: "podriamos mostrar un preview como hacemos con Crear perfil ? pros y contras ? Debemos implementar Ctrl + Click para deseleccionar"
- L2. T1: RED 2 failures in `test_end_miter_panel` (Ctrl+click add path, face deselection); GREEN 11/11; full suite `Ran 715 tests ... OK`. Native review approved (advisory R3-sub-guard-removed: deselecting any face drops the profile).
- L3. User: "si ponemos un chek para que se actualice automaticamente o no ?" Proposal accepted: check box off by default and remembered, plus Apply.
- L4. User: "ok, me queda una duda aplicar solo previsualiza o aplica el corte?" Answer: Apply only previews, OK confirms, Cancel discards, as in Create Profile.
- L5. Correction: Create Profile hides its Apply group (create_profiles_tool.py:389-391) and previews live; docs/commands.md:16 is stale. User: "la 2 pero solo con el checkbox, sin boton actualizar. ademas deberiamos limpiar la ui y eliminar el boton aplizar de crear perfiles si no lo usamos es codigo muerto"

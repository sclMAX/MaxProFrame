# Folder libraries and ZIP exchange
Objective: unify custom library creation in owned folders and share self-contained ZIP bundles. Branch: `feat/folder-libraries-zip` (base `43d0cb1caa0a78b53dac9303f1c3d65a365655b1`).
Delivery: `auto-chain`, `chain_strategy=feature-branch-chain`; forecast ~1,000–1,500 authored diff lines, separate behavior slices. Runner: native FreeCAD 1.1.4 and 26.3rc2 using isolated copies of `.freecad-test` configurations.

## Specs
S1. "Los iconos para mantener consistencia reordenemos \"+\" \"-\" \"Importar\" \"Duplicar\". Y cambiemos el icono de importar." Keep icon-only buttons with tooltips, as previously requested: "solo iconos con tooltip". Check visible order and distinct import/export icons.
S2. "Quitemos el boton \"Nueva biblioteca en carpeta\", la funcionalidad me parece que deberia ser \"+\" -> Crear biblioteca, pedir nombre, material y mostrar la carpeta por defecto donde se guardara con la opcion de elegir una carpeta personalizada. Todas las bibliotecas personalizadas viviran dentro de su propia carpeta." Check unified creation, default full destination preview, destination choice, and folder-based duplication of custom and system libraries; no overwrite of unrelated content.
S3. "Agreguemos una opcion para exporta una libreria personalizada (por ejemplo para poder compartirla con un amigo o compañero)." Check self-contained export of the catalog and its referenced section assets, without local registry or unrelated files. Accepted export dirty-state flow: save and export, or cancel, never discard and export.
S4. "Si me sirve ZIP, Notas: aun no lanzamos la release asi que no necesitamos compatibilidad antigua." ZIP is the accepted exchange format. Check ZIP import into its own folder and registration; retain existing-folder registration. Validate archive content, paths and conflicts before publication; rejection must not alter destination or registry. No legacy compatibility layer or automatic migration is required; do not delete existing user data.
S5. Implementation authorization: "si" in response to the agreed complete scope reproduced in L3. Keep existing custom profile section operations, material/density rules, and read-only system libraries working; update user-facing workflow documentation and Spanish tooltips/messages alongside behavior.

## Tasks
T1 | S2,S4,S5 | route: delegated writer (context backstop) | done | Unified creation/destination UI and folder-only duplication; stable focused GREEN 74/74, parent rerun exit 0, baseline differential passed, prepared configs unchanged. Commit: recorded below.
T2 | S3,S4,S5 | route: delegated writer (context backstop) | pending | Implement self-contained ZIP backend with archive path validation, bounded extraction, catalog/asset validation and rollback; public API tests. Risk: item 2 (untrusted archive paths). Commit: pending.
T3 | S1,S2,S3,S4,S5 | route: delegated writer (context backstop) | pending | Wire import/export UI, toolbar order/icons, export save gate, localization and user docs, with GUI tests. Commit: pending.
T4 | S1-S5 | route: independent verifier (Risk: item 2) plus parent seam check | pending | Verify whole feature in isolated state, full stable/RC native suites, visual GUI evidence, differential preservation checks. Commit: pending.
T5 | S1-S5 | route: parent inline | pending | Complete work-unit native assessments/review when due, record commits/evidence and close feature without publishing. Commit: pending.

## Log
L1. Original user request:
"/tmp/gpYuvEpW/pi-clipboard-0848efc4-1abe-48a7-94d7-3d1070df8ca1.png cambiemos algunas cosas:
- Los iconos para mantener consistencia reordenemos \"+\" \"-\" \"Importar\" \"Duplicar\". Y cambiemos el icono de importar.
- Quitemos el boton \"Nueva biblioteca en carpeta\", la funcionalidad me parece que deberia ser \"+\" -> Crear biblioteca, pedir nombre, material y mostrar la carpeta por defecto donde se guardara con la opcion de elegir una carpeta personalizada. Todas las bibliotecas personalizadas viviran dentro de su propia carpeta.
- Agreguemos una opcion para exporta una libreria personalizada (por ejemplo para poder compartirla con un amigo o compañero).
Que opinas de estos cambios? pros contras ? opiniones o mejoras?"
L2. User decision: "Si me sirve ZIP, Notas: aun no lanzamos la release asi que no necesitamos compatibilidad antigua."
L3. Accepted proposal before implementation authorization:
"Perfecto: **bibliotecas personalizadas siempre en carpeta y ZIP para compartir**, sin compatibilidad antigua ni migración automática. Eso simplifica el diseño; no implica borrar datos existentes.

El alcance queda:
- Barra: **`+` · `−` · Importar · Duplicar · Exportar**, solo iconos con tooltip.
- `+`: nombre, material/densidad y destino predeterminado modificable.
- Duplicar crea otra biblioteca con carpeta propia.
- Exportar ZIP autocontenido.
- Importar ZIP validando contenido, rutas y conflictos; conservar la opción de registrar una carpeta existente.

¿Avanzo con la implementación de este alcance?"
User authorization: "si".
L4. Repository map: `create_folder_library` already validates empty destination and atomically registers manifests. Duplication of system libraries currently writes loose JSON and must change. `resolve_and_validate_asset_path` confines section paths but callers must require assets to exist. Existing-folder registration does not validate every referenced asset. Export must not reuse Save/Discard/Cancel semantics. No ZIP backend exists. Parent spot-check confirmed creation guard/rollback at library_manager.py:670-763.
L5. User delivery choice: "Cadena sobre rama de funcionalidad — recomendado" (`feature-branch-chain`). No push/PR requested. Branch created from clean published main at `43d0cb1`. The external stable and RC AppImages were explicitly authorized earlier in this live session; use isolated copies of prepared configs and verify their hashes unchanged. Scope is large because multi-unit security-sensitive work needs durable decisions and evidence beyond a resumable diff.
L6. T1 writer completed lifecycle changes: shared default child destination, unified creation/duplication dialog, stock and folder duplication through one asset/weight/rollback pipeline, preserving explicit custom density. No ZIP, toolbar removal, migration or namespace retirement. RED: 3 initial tests produced expected failures/errors; custom-density RED then reproduced separately. GREEN: stable 74/74. Parent reran `python3 .freecad-test/folder-libraries-zip/run-focused.py --unit lifecycle --target stable`, exit 0 in 11 s; baseline differential identical for exit/stdout/stderr/material/density/weights/declared assets/immutable saves/path rejection, intentional folder layout excluded; prepared config hashes unchanged. Work-unit footprint ~547 authored lines is cohesive lifecycle consolidation with removed duplicate code and tests, retained as one reviewable behavior instead of artificial splitting. Initial native assessment was unassessable due untracked test/document; reassess committed candidate. Security-sensitive confinement of newly supported stock asset copies needs independent verification before native review when due.

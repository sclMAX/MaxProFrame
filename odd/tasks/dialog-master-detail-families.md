# Feature: Dialog Master-Detail Families & Toolbar Icons
Restructure Profile Library Manager Dialog with a two-level master-detail hierarchy on the left panel (Libraries + Families with thumbnails) and compact icon toolbars.

## Specs
S1: "Los botones Nueva, duplicar y eliminar cambiemos por solo iconos y pongamolos arriba debajo de 'Bibliotecas disponibles'." Compact icon buttons (+ New, Duplicate, Delete) placed above the libraries list, with localized tooltips and clean icons.
S2: "Debajo de las libs mostremos las familias disponibles en la lib, con nombre en el idioma de freecad y el icono con la forma de perfil correspondiente a la familia. Arriba lo iconos para agregar/ quitar familia." Two-tier left panel: below the libraries list, a families list widget displaying profile cross-section thumbnails from `resources/images/profiles/` and translated family names, with compact (+ Family, - Family) icon buttons above it.
S3: Removing redundant family selection combo from the right panel. Selecting a family in the left families list immediately updates the right table with that family's dimensions, standard/norm, and fillet option.
S4: Internationalization: Spanish translations for all family names (e.g. "Tubo Cuadrado Hueco", "Tubo Redondo", "Ángulo de Alas Iguales", etc.) and toolbar action tooltips added to `frameforge_es.ts` and compiled to `.qm`.
S5: Tests: Update `tests/test_library_manager_dialog.py` to cover the new family list widget, profile thumbnail loading, selection synchronization, and CRUD actions, passing 100% of the test suite under FreeCAD offscreen.
S6: "Los iconos de la familias son muy chicos, no se ven bien. Tambien podriamos poner un 'tirador' horizontal entre Lib y familia para poder redimencionar (por ejemplo agrandar el listado de familia y achicar el de lib)." Enlarge family thumbnails to 60x30 px (matching the 2:1 aspect ratio of profile images) and replace the static left layout with a vertical QSplitter having a visible horizontal handle between Libraries and Families.

## Tasks
- [x] T1 (linked S1, S2, S3): Restructure `ProfileLibraryManagerDialog` layout: compact icon buttons for libraries, two-level left panel with `list_families` (showing thumbnail icons + translated names), compact (+/-) family icon buttons, and streamlined right panel without redundant combo. [verified]
- [x] T2 (linked S4): Add Spanish translations for all profile family names and action tooltips to `frameforge_es.ts` and compile to `.qm` via `compile_translations.py`. [verified]
- [x] T3 (linked S5, S1, S2, S3): Update and expand `tests/test_library_manager_dialog.py` to verify `list_families` population, thumbnail icon resolution, family selection synchronization with sizes table, and family deletion/addition. [verified: 22 tests passing]
- [x] T4 (linked S1-S5): Full end-to-end offscreen verification with FreeCAD AppImage and UI screenshot generation. [verified: /tmp/dialog_metal_families.png]
- [x] T5 (linked S6): Implement vertical QSplitter on left panel with styled horizontal handle between Libraries and Families, enlarge family icon size to 60x30 px, adjust default panel width, and update unit tests. [verified: 22 tests passing]

## Log
L1: "Los botones Nueva, duplicar y eliminar cambiemos por solo iconos y pongamolos arriba debajo de 'Bibliotecas disponibles'. Debajo de las libs mostremos las familias disponibles en la lib, con nombre en el idioma de freecad y el icono con la forma de perfil correspondiente a la familia. Arriba lo iconos para agregar/ quitar familia."
L2: Delegated implementation to gentle-ai-worker. Restructured left panel with master-detail lists, thumbnail icons, compact icon toolbars, updated translations for all known families, and added unit tests. All 22 tests passing cleanly in FreeCAD AppImage offscreen environment.
L3: User feedback: "Los iconos de la familias son muy chicos, no se ven bien. Tambien podriamos poner un 'tirador' horizontal entre Lib y familia para poder redimencionar (por ejemplo agrandar el listado de familia y achicar el de lib)." Added S6 and T5.
L4: Delegated T5 to gentle-ai-worker. Enlarged family thumbnail icons to 60x30 px, implemented vertical QSplitter with 6px grab handle between Libraries and Families, expanded default left panel width to 320 px, and verified 22/22 tests passing under FreeCAD offscreen.

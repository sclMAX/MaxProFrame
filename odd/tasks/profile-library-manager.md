# Feature: Profile Library Manager
Tracking and specification document for FrameForge custom profile library management.

## Specs
S1: "quiero poder crear una biblioteca por ejemplo 'Indumatics Aluminio' y poder ir creando tubos de distintas medidas y espesores con el peso correspondiente al aluminio"
S2: "un comando para manejar la bibliotecas, que habra una ventana con las librerias existentes y permita ABM de librerias y componentes por ej. crear un lib 'indumatics' y luego crea un tub..."
S3: "tener en cuenta a futuro poder agregar a una lib perfiles personalizados como un marco de puerta o un perfil 'C' para tenerlo en cuenta en el desarrollo modular"
S4: Storage separation: User libraries persisted in FreeCAD user application data directory (`App.getUserAppDataDir() + "FrameForge/profiles/"` or fallback for headless/tests), keeping stock/bundled libraries intact and surviving addon updates.
S5: Integration: Dynamic discovery in `create_profiles_tool` so that user-created libraries appear alongside bundled libraries in UI combos.

## Tasks
- [x] T1 (linked S4, S1): Implement `library_manager.py` with multi-path discovery (bundled + user AppData), JSON catalog loading, validation, and persistence (save, delete, duplicate). [commit 575aad6]
- [x] T2 (linked S4, S1): Unit tests for `library_manager.py` covering creation, listing, cloning, custom profile specs, and isolation. [commit 575aad6]
- [x] T3 (linked S5, S1): Integrate `LibraryManager` into `create_profiles_tool.py` so custom user libraries appear alongside bundled libraries in UI combos. [commit 575aad6]
- [x] T4 (linked S2, S1, S3): Implement GuiCommand `FrameForge_ManageProfileLibraries` in `InitGui.py` and modular ABM Dialog (`library_manager_dialog.py` / `.ui`) allowing CRUD of libraries, families, and sizes. [commit 575aad6]
- [x] T5 (linked S1, S2, S3, S5): End-to-end verification and documentation of custom library workflow in FrameForge. [commit 575aad6]

## Log
L1: "quiero poder crear una biblioteca por ejemplo 'Indumatics Aluminio' y poder ir creando tubos de distintas medidas y espesores con el peso correspondiente al aluminio esto es posible?"
L2: "y si agregamos un comando para manejar la bibliotecas, que habra una ventana con las librerias existentes y permita ABM de librerias y componentes por ej. crear un lib 'indumatics' y luego crea un tub..."
L3: "Estoy de acuerdo, solo me gustaria tener en cuenta a futuro poder agregar a una lib perfiles personalizados como un marco de puerta o un perfil 'C' para tenerlo en cuenta en el desarrollo modular. que opinas?"
L4: "si"
L5: Verified multi-path catalog storage, isolated user directory CRUD, theoretical linear weight calculation (Aluminium 2.70 g/cm3), UI dialog integration, and full test suite passing in FreeCAD 1.0/v26-3 AppImage offscreen environment.
L6: Configured git author as sclMAX <maxi.indumatics@gmail.com> and committed work-unit on branch feature/profile-library-manager.
L7: RDD review identified 3 findings (collision protection, family switch edit persistence, wood density parsing); all 3 resolved and verified with 14 passing tests (commits c5f291d, 112e6d2).

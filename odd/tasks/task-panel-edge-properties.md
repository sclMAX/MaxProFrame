# TaskPanel: Master-Detail Híbrido con Propiedades por Arista y Panel Completo
Visual spec: design/task-panel-edge-properties/01-master-detail-hybrid.html
Delivery: MaxProFrame task panel restructuring with dual mode (Uniform vs Per-Edge), edge list, collapsible sections, and toggle buttons.

## Specs
- S1: "Perfil", "Colocación" and "Opciones avanzadas" as collapsible sections with icons. "Opciones avanzadas" is collapsed by default. Includes library selector, family, size, compact metadata grid, and profile name under 2D widget.
- S2: Dual mode switch between "Todas (Uniforme)" and "Por Arista (Individual)". Uniform mode displays edge count notice. Individual mode displays scrollable edge list with badges ("Rot: X° | EspH | EspV") and remove buttons.
- S3: In individual mode, selecting an edge allows editing rotation, 2D anchor point, Mirror H, Mirror V, and Pre-extend independently for that edge. Live 3D preview updates each edge profile accordingly, and OK commits per-edge properties. Reset button restores global values.
- S4: "Reflejar y extender usemos bostones on/off con icono" - checkable toggle buttons with icons for Mirror H, Mirror V, and Pre-extend, with clear On/Off states.
- S5: Backwards compatibility: single-edge profiles, manual length, and EditProfileTaskPanel remain fully functional. All test suites pass 100% green.

## Tasks
- T1 (S1, S4): Implement collapsible accordion sections and toggle buttons with icons in BaseProfileTaskPanel.
- T2 (S2): Implement mode switch and EdgeListWidget in CreateProfileTaskPanel.
- T3 (S3): Bind reactive placement controls to per-edge state and 3D preview synchronization.
- T4 (S3, S5): Update make_profile and proceed to commit per-edge properties to FreeCAD objects.
- T5 (S1-S5): Add comprehensive test suite and verify full regression suite passes green.

## Log
- L1: "Me gustaria que las aristas sean un listado donde pueda agregar quitar, y al seleccionar una arista poder cambiar las propiedades del perfil solo para esa arista"
- L2: "falta el resto del panel [Image#2], ademas falta el selecto para la biblioteca. descartemos el diseño 02 y crea otros 3 diseños combinando 01 y 03"
- L3: "Reflejar y extender usemos bostones on/off con icono"
- L4: "Implement the design artboard design/task-panel-edge-properties/01-master-detail-hybrid.html"
- L5: All CI checks pass 100% green on GitHub Actions run 40787712066 (Formatting in 13s, Native FreeCAD stable 610 tests in 1m41s, Native FreeCAD rc 390 tests in 4m16s). Commit 3eb6660.

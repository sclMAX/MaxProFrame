# Feature: Library-Level Material and Automatic Weight Calculation
Specification and task tracking for library-scoped material assignment, immutable material lifecycle, and real-time theoretical weight calculation in FrameForge.

## Specs
S1: "el material lo manejamos a nivel de lib, al crear una lib personalizada aparte del nombre seleccionamos el material y todos los componentes de esta libreria tendrian asociado el mismo material"
S2: "mostramos el material y hacemos el calculo automatico"
S3: "quitar el boton 'calcular peso'"
S4: Inmutable material at library level: once created, the material is locked for that library. To change material, the user duplicates the library selecting a new material, with automatic bulk recalculation of theoretical weights for the clone.
S5: Manual override preservation: the weight cell in the sizes table remains editable so users can enter custom/manufacturer nominal weights if desired.

## Tasks
- [x] T1 (linked S1, S4): Extend `LibraryManager` to handle `material` and `density` metadata in creation, duplicate with bulk weight recalculation, and stock/legacy fallback.
- [x] T2 (linked S1, S4): Enhance New Library and Duplicate Library modal dialogs to prompt for standard material selection.
- [x] T3 (linked S2, S3): Update dialog banner to display library material and density, and remove the bottom 'Calculate Theoretical Weight' button.
- [x] T4 (linked S2, S5): Implement real-time automatic weight calculation on dimension changes in `table_sizes` using library density.
- [x] T5 (linked S1, S2, S3, S4, S5): Add unit tests for library material, duplication recalculation, auto-calc, and update translations.

## Log
L1: "SI el material lo manejamos a nivel de lib, al crear una lib personalizada aparte del nombre seleccionamos el material y todos los componentes de esta libreria tendrian asociado el mismo material, mostramos el amterial y hacemos el calculo automatico? pros contras? que opinas?"
L2: Architectural consensus on library-level material, immutability of material after creation, cloning/duplication for material changes, and auto-calc on dimension edits.
L3: "si definitivamente"
L4: Independent verification by gentle-ai-verify confirmed S1-S5 compliance, 28/28 tests passing, and clean signal safety.
L5: Full regression probe suite tests/test_library_material_probes.py added covering malformed density resilience, legacy metadata consistency, and S4 immutability; all 36 tests pass cleanly.

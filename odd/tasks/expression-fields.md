Native FreeCAD expression support (the "Fx" button, VarSet and formulas) in the task panel numeric fields, stage 1: fields bound to one existing document object.
Branch: feat/expression-fields (from origin/main 176ef45), worktree .git/gentle-worktrees/expression-fields.
Native runner: `python3 ci/run_tests.py --freecad-bin /home/max/Documentos/Desarrollo/FreeCAD/MaxProFrame/.git/ci-policy-runtime/squashfs-root/AppRun --reports <dir> --timeout 900 [--test <module>]`.

## Specs

- S1. (L1, L3) "podemos usar o agregar la opcion "Fx" que tienen los campos en freecad para poder usar "Varset" y formulas?" Stage 1 scope (L3: "Etapa 1: un solo objeto"): every numeric field of a panel that edits one existing document object offers FreeCAD's native expression editor (Fx / typing "="), bound to that object's property: Drill Hole (Offset along, Offset across, Diameter, Count, Pitch, Depth), Cutout depth, Extend / Cut and Notch Gap in edit mode, Edit Profile fields.
- S2. Drill Hole create mode: the fields offer Fx once the preview hole exists (face and vertex picked); before that they work as plain fields. An expression typed survives the preview being recreated (base changed).
- S3. OK keeps the expressions set in the panel on the object, in the same Undo step as the other values. Cancel leaves the document unchanged, expressions included.
- S4. Editing an object whose properties already have expressions (set from the property editor) shows them in the panel and keeps them unless the user changes or clears them; the panel never overwrites an expression-driven property with a typed value.
- S5. Out of scope for stage 1 (L3): multi-object fields (Extend / Cut / Notch Gap in create mode, End Miter Gap, Create Profile fields) and fields with no document property (BOM Stock length and Kerf, Populate IDs first number, library fields).
- S6. (L2) "trabaja en tu propio worktree y rama, asi otros agentes pueden trabajar en otras features." All work in this worktree and branch; the main checkout is not touched.
- S7. Help, docs and CHANGELOG describe the Fx support; new user-facing strings have Spanish translations.

## Tasks

- T1 (S1, S3, S4) Shared expression-field helper + Cutout depth panel. Route: inline. Commit: cc5c3cc.
- T2 (S1, S2, S3, S4) Drill Hole panel fields. Route: inline. Commit: pending.
- T3 (S1, S3, S4) Extend / Cut and Notch Gap in edit mode. Route: inline. Commit: pending.
- T4 (S1, S3, S4) Edit Profile fields. Route: inline. Commit: pending.
- T5 (S7) Help, docs, CHANGELOG, translations. Route: inline. Commit: pending.

## Log

- L1. User: "[Image#1] podemos usar o agregar la opcion "Fx" que tienen los campos en freecad para poder usar "Varset" y formulas? pros contras?" (image: the Drill Hole task panel, Spanish UI).
- L2. User: "en todos, trabaja en tu propio worktree y rama, asi otros agentes pueden trabajar en otras features."
- L3. User scope choice: "Etapa 1: un solo objeto (Recomendado)" — Drill Hole, Cutout, Gap de Extend/Cut/Notch en edición y Edit Profile; multi-object fields go to a following branch.
- L4. API probe (FreeCAD 1.1.4 runner = freecadmin): `Gui.UiLoader().createWidget("Gui::QuantitySpinBox")`, `Gui.ExpressionBinding(widget)` with bind(obj, prop), isBound, hasExpression, apply, autoApply/setAutoApply; `box.setExpression("Length", "VarSet.D")` shows "7,00 mm" in the bound widget. No Gui::QuantitySpinBox / ExpressionBinding use in the codebase yet.
- L5. Explore map: Drill Hole preview exists only after face+vertex and is recreated on base change (`_make_preview` create_drill_hole_tool.py:547), 250 ms debounce, `_apply_to` :309 writes changed values, edit Cancel also restores by hand (`_restore_edit` :579). Cutout depth create_extruded_cutout_tool.py:329, object always exists, `_apply` :358 per change, transaction in `__init__` :317. Extend / Cut gap extend_cut.ui:130 `sb_gap`, NotchTaskPanel subclasses ExtendCutTaskPanel (create_notch_tool.py:25), edit preview `_preview_edit` :527, `_restore_edit` :548, `_accept_edit` :861, TrimGap PropertyLength trimmed_profile.py:95. Edit Profile: PropertyFloat section fields (profile.py:154-252), OffsetX/Y PropertyDistance, `set_properties` profile.py:319 reassigns every property on each change, catalog refill `on_size_changed` create_profiles_tool.py:1125-1192; create_profiles2.ui is shared with CreateProfileTaskPanel.
- L6. T1: Gui::DoubleSpinBox / Gui::IntSpinBox (QDoubleSpinBox / QSpinBox subclasses, value()/setValue()/valueChanged kept) chosen over Gui::QuantitySpinBox (wrapped as QAbstractSpinBox in PySide, no value()/valueChanged): existing panels and tests keep working, fields stay in mm. Helper freecad/maxproframe/expression_fields.py (length_field, count_field, bind, expression_of, expressions_of, restore_expressions). Tests simulate the Fx editor with obj.setExpression (the binding sets the expression on the bound property). RED: binding tests `TypeError: Wrong type` (plain QDoubleSpinBox), undo-off Cancel `{'ExtrusionLength': 'VarSet.Depth'} != {}`. GREEN test_cutout_depth_panel 14/14, test_cutout_flow 19, test_cutout_one_wall 11, test_cutout_direct 1.

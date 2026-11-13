# Folded corners: one object per corner, edited from a list of corners
Rework of the Folded Bar (feature folded-miter, PR #145/#146, not released): every corner is a `FoldedCorner` object
with its own outer radius, clearance, key and K-factor (Fx), the panel lists corners instead of tubes, and bend
configurations go away (thickness and material come from the profile). Branch feat/folded-corners. Delivery: one PR,
one commit per task (each about one review slice; T3 and T4 may each pass 400 lines). Status: T1-T5 done; T6-T8 from the user's manual test (L14-L15).

## Specs
- S1 Corner list (L1): "cambiamos esa lista para que muestre las esquinas, con la opcion de quitar" -> the
  "Tube pieces, from the start of the bar" list becomes a list of corners in chain order (corner 1 at the start of the
  bar), one row per corner naming its two tubes and its values, e.g. `1 · 000 → 003 · R 30 · key · clearance 0,5`. The
  "Corners" group with one radius row per corner goes away. While fewer than 2 tubes are picked the list says so
  (hint to pick the next tube). Picking tubes in the 3D view (S22 of folded-miter) stays as it is.
- S2 Select a corner (L1): "al seleccionar una esquina editar sus parametros, se selecciona una esquina en la lista
  resaltamos los perfiles que la componen y actualizamos los campos con los valores que tiene esa esquina" -> selecting
  a row highlights the two tubes of that corner in the 3D view (on what the preview shows) and fills the corner fields
  with that corner's values; editing a field changes that corner only.
- S3 Multi-selection (L4): "Tambien que la lista tenga multiseleccion para poder cambiar las propiedades de varias
  esquinas simultaneamente." -> with several rows selected, every selected tube pair is highlighted, a field whose
  value is the same in all of them shows it, a field that differs shows it is mixed, and a value typed applies to every
  selected corner. Fx needs one property: with several corners selected the Fx editor is not offered (decision, L5).
- S4 Remove (L1, L4 answer "(a) Solo extremos; cerrado = abrir"): a Remove button acts on the selected corner. In an
  open bar only the first or the last corner can be removed: it takes off the end tube of that corner; a middle corner
  cannot be removed (button disabled). In a closed frame removing a corner makes it the open corner (where the bar
  starts and ends); the open corner is not folded and shows as open in the list.
- S5 Values per corner (L2, L4): "Llave y holgura deben ser de cada esquina." and "Valor por esquina, recordando el
  ultimo seteado (si ya hice una esquina con x valores, la siguiente esquina tiene x inicialmente)" -> outer radius,
  clearance, key on/off, key diameter and K-factor belong to each corner; there is no bar-wide value. A new corner
  starts with the values last set in the panel; they are remembered between sessions in the MaxProFrame parameters.
- S6 Outer radius (L2): "El radio deberia se el exterior y nosotros calcular el interior (en un diseño lo que el
  usuario sabe o quiere es el radio que va a quedar a la vista) por ejemplo hoy si quiere un radio de 30mm tiene que
  calcular 30 - espesor para que quede el radio exterior que desea." -> the field is **Outer radius**; inside radius =
  outer radius - wall thickness (30 mm on a 1.5 mm tube bends with inside radius 28.5 mm). The minimum is 2 x
  thickness; the largest radius check (folded-miter S15) and its message are given as outer radius.
- S7 No bend configurations (L2): "Para que necesitamos las configuraciones de plegado ? no seria mejor sacar el
  espesor y material del perfil que estamos usando?" -> wall thickness and material are read from the profile of the
  tubes (shown read-only in the panel, e.g. `Aluminio · 1,5 mm`); the Bend Configurations command, dialog, store
  (`.bend/configurations.json`), its icon and the bar's BendConfiguration, BendMaterial, WallThickness and
  InsideRadius properties are removed.
- S8 Automatic K-factor (L3, "si" to "K automático por esquina, con la opción de sobrescribirlo"; L9 "si vamos con
  la curva y citemos la norma en el tutorial y documentacion."): each corner's K-factor is Automatic by default (0),
  from DIN 6935 with r the inside radius and t the wall thickness: K = 0.325 + 0.25 log10(r/t), at most 0.5 (r/t = 1
  -> 0.325, 2 -> 0.40, 3 -> 0.444, 5 and above -> 0.5); a value above 0 up to 1 overrides it for that corner. The
  tutorial and the code documentation cite DIN 6935.
- S9 Fx (L2 "Los campos deberian ser fx.", L4 "Desde el inicio") -> outer radius, clearance, key diameter and
  K-factor of the selected corner take FreeCAD expressions in the panel (Fx icon or `=`), bound to that corner's
  object; when creating, Fx appears once the preview exists. OK keeps them in the Undo step, Cancel takes them back.
- S10 FoldedCorner object (L5 "SI vamos con B") -> one `FoldedCorner` document object per corner, child of its bar
  in the tree, identified by its two tubes (PieceA, PieceB), with OuterRadius, Clearance, Key, KeyDiameter (0:
  default), KFactor (0: automatic) and Open (closed frames). It replaces the bar's CornerRadii, OpenCorner, Clearance,
  Key and KeyDiameter. Editing a corner property recomputes the bar; expressions survive removing or reordering other
  corners; deleting the bar deletes its corners; removing a corner deletes its object.
- S11 Bars saved before (L8): "No lanzamos release de la feature aun, no necesitamos migracion." -> no migration:
  bars saved with the old properties are not converted.
- S12 Decimal separator (L5 "Actiovo la opcion.", L6 "Agrega la nota.") -> no code: the tutorial explains FreeCAD's
  Edit > Preferences > General > Substitute decimal separator for the keypad period.

- S13 Highlight the corner (L14 "como podemos hacer para que se resalte en el 3D la esquina seleccionada?", "Si")
  -> the corners selected in the list are drawn over the 3D view (overlay, not FreeCAD selection) as the part of the
  bar around each corner's vertex (bend zone and a stretch of each tube), in the selection color, always visible; an
  open corner marks both ends. The overlay is removed on another selection, OK, Cancel or closing the panel.
- S14 Fields of the selected corner (L14, screenshot: corner 3 "R 30 mm" selected, Esquina fields empty) -> selecting
  one corner shows its outer radius, clearance, key diameter and K-factor in the fields.
- S15 No freeze while typing (L15 "si cambio el gap un par de veces se quedo congelado cuando escribi "0." quisas
  flata algun debounce para evitar recalculos analizalo.") -> typing in a corner field (e.g. "0." on the way to
  "0.5") never freezes FreeCAD; intermediate values do not trigger a recompute storm (debounce or equivalent, from
  the analysis).

## Tasks
- T1 S12 tutorial note on the decimal separator - inline - done, c71d918.
- T2 S6 S7 S8 geometry per corner: `unfold`/`_bends` take per-corner settings (outer radius, clearance, key, key
  diameter, K-factor), thickness from the profile, automatic K, outer-radius limits and messages - worker
  (context backstop) - done, commit below (L10).
- T3 S7 S10 FoldedCorner object, FoldedBar properties and execute through its corners, tree children, delete
  lifecycle, `make_folded_bar(selection, corners, open_corner)`; every bend property leaves the bar; the current panel
  only gets the glue to create and edit corner objects - worker (context backstop) - done, commit below (L11).
- T4 S1-S5 S7 S9 panel: corner list with multi-selection, highlight, Remove, open corner, per-corner fields with Fx,
  last used values; configuration widgets removed; remove bend_config, dialog, command, icon and their tests - worker
  (context backstop) - done, commit below (L12).
- T5 S1-S11 tutorial, README, CHANGELOG, es/ru translations and .qm - worker (context backstop) - done, commit below
  (L13).
- T6 S13 corner highlight overlay in the 3D view - worker (context backstop) - done, commit below (L21).
- T7 S14 selected corner shows its values - real on committed code (L18); not reproduced offscreen in Spanish with the light theme (L19); next: the user's theme and click-into-field check, then explorer.
- T9 S3 the Mixed label ("Varios") is drawn over the value instead of hiding it when several corners are selected (L19) - pending.
- T8 S15 freeze while typing a corner field - not reproduced (L16); possibly code edited while the user tested (L17); blocked: user retest on committed code after T6, gdb dump if it recurs.

## Log
- L1 (2026-11-12) "Si para darle funcionalidad, cambiamos esa lista para que muestre las esquinas, con la opcion de
  quitar. Ademas podrimos (al seleccionar una esquina editar sus parametros, se selecciona una esquina en la lista
  resaltamos los perfiles que la componen y actualizamos los campos con los valores que tiene esa esquina.  que
  opinas? pros contras?"
- L2 (2026-11-12) "- Para que necesitamos las configuraciones de plegado ? no seria mejor sacar el espesor y material
  del perfil que estamos usando?
  - Llave y holgura deben ser de cada esquina.
  - El radio deberia se el exterior y nosotros calcular el interior (en un diseño lo que el usuario sabe o quiere es el
  radio que va a quedar a la vista) por ejemplo hoy si quiere un radio de 30mm tiene que calcular 30 - espesor para
  que quede el radio exterior que desea.
  - Los campos deberian ser fx.
  - El punto del numpad deberia serbir como separador decimal si hoy pongo 0.2 en un gap que 2mm.
  esto simplificaria mucho el panel y seria mas intuitivo. Que opinas? pros contras?"
- L3 (2026-11-12) After the K-factor explanation (K typically 0.3-0.5 by r/t; error per corner = angle x dK x t;
  proposal: automatic K per corner, overridable): "si".
- L4 (2026-11-12) Answers: Remove -> "(a) Solo extremos; cerrado = abrir (Recomendado)"; per corner -> "Valor por
  esquina, recordando el ultimo seteado (si ya hice una esquina con x valores, la siguiente esquina tiene x
  inicialmente), analicemos si es conveniente crear una clase o objeto para la esquina. Tambien que la lista tenga
  multiseleccion para poder cambiar las propiedades de varias esquinas simultaneamente."; Fx per corner -> "Desde el
  inicio"; start -> "Punto decimal primero (Recomendado)".
- L5 (2026-11-12) Finding: FreeCAD already has Preferences > General > "Substitute decimal separator"
  (SubstituteDecimalSeparator, default off; src/Gui/Language/Translator.cpp:430, keypad only). Options for the corner:
  A loose bar properties (expressions break on renumbering), B FoldedCorner object per corner (recommended), C Python
  class only (no Fx). User: "1. Actiovo la opcion. 2. SI vamos con B".
- L6 (2026-11-12) "Agrega la nota." -> tutorial section "Decimal separator in number fields" (assess: passive).
- L7 Exploration map (gentle-ai-explore): `_Bend` already holds per-corner radius, thickness, k_factor, clearance, key,
  diameter (unfolded_geometry.py:121-131); only `_bends` (:372-396) feeds bar-wide scalars; thickness in geometry
  already comes from `profile.Thickness` (folded_chain.py:106), WallThickness is only a check; BendMaterial unused in
  geometry. Panel corner key = frozenset of profile names (create_folded_bar_tool.py:78-80). bend_config consumers:
  folded_bar.py:17, create_folded_bar_tool.py:20-24, InitGui.py:40/75, test_shortcuts, test_toolbar_translations,
  test_russian_translation. Tests to rework: test_bend_config 16 and test_bend_config_dialog 12 (delete),
  test_folded_bar 25, test_folded_bar_panel 44, test_folded_bar_translations 6, test_unfolded_geometry 33,
  test_folded_geometry 11, test_folded_chain 22 (open corner).
- L8 (2026-11-12) "1. explicame un poco mas la diferencia entre escalonado o curva. 2. No lanzamos release de la
  feature aun, no necesitamos migracion." -> S11 rewritten (no migration), T3 without migration; S8 step table vs
  continuous curve (DIN 6935: K = 0.325 + 0.25 log10(r/t), 0.5 from r/t = 5) explained, choice pending.
- L9 (2026-11-12) "si vamos con la curva y citemos la norma en el tutorial y documentacion." -> S8 rewritten (DIN 6935
  curve); implementation starts with T2.
- L10 T2 evidence (worker mwe7eyoz-2-16g2, parent check): `CornerSettings(outer_radius, clearance, key, key_diameter,
  k_factor)`, `automatic_k_factor` (DIN 6935: 0.325 + 0.25 log10(r/t), exactly 0.5 from r/t = 5), `unfold(chain,
  corners)`, `check_settings(chain, corners)`, `fold(chain, corners)`; messages "The outer radius of the corner between
  {} and {} must be between {min:g} and {max:g} mm.", "The K-factor of the corner between {} and {} must be between 0
  and 1.", key message "with this radius". Temporary adapter `folded_bar.corner_settings` (outer = inside + profile
  wall, K from the configuration) until T3/T4; the panel still says Inside radius while limits quote the outer radius.
  RED: test_unfolded_geometry ImportError CornerSettings. GREEN (parent rerun): test_unfolded_geometry 41,
  test_folded_geometry 11, test_folded_bar 26, test_folded_bar_panel 44, test_folded_chain 23, test_russian_translation
  6 OK. Commit aa46dc3. Assess medium, review not due.
- L11 T3 evidence (worker mwe81ag1-3-f5y6, parent check): `folded_corner.py` (FoldedCorner: PieceA/PieceB base
  profiles, OuterRadius, Clearance, Key, KeyDiameter, KFactor, Open), bar `Corners` (folded corners in chain order,
  open corner last), helpers `open_corner`, `bar_chain`, `folded_corners`, `bar_settings`, `update_corners`,
  `remove_corners` (via `unsetupObject`); every bend property removed from the bar; panel glue only. Message "The corner
  between {} and {} has no Folded Corner object.". RED: ModuleNotFoundError folded_corner, then 33 errors on the old
  make_folded_bar signature. Parent found test_folded_bar_translations failing since T2 (untranslated outer-radius
  message, missed by the T2 check): es translations of the 4 new messages, ru unfinished entries, .qm recompiled, test
  expectation updated. GREEN (parent): test_folded_bar_translations 6, test_folded_bar 35, test_folded_bar_panel 45,
  test_unfolded_geometry 41, test_folded_geometry 11, test_folded_chain 23, test_russian_translation 6,
  test_compile_translations 3 OK.
- L12 T4 evidence (worker mwe8wq3x-4-w2ol, parent check): panel rewritten in create_folded_bar_tool.py: corner list
  (QListWidget, extended selection; rows "1 · Profile → Profile001 · R 10 mm · key · clearance 0.5 mm", open corner
  last "Open · A → B"; hints "Click the tube where the bar starts." / "Click the next tube, after {}."), Corner group
  (Outer radius, Clearance, Interlocking key, Key diameter "Default", K-factor "Automatic"), mixed state through
  create_profiles_tool._MixedPresentation ("Mixed values"), Remove (open bar: end corners take off the end tube, middle
  disabled; closed frame: opens the corner and reorders the tubes), highlight of the selected corners' tubes (preview
  faces wholly in them, else the tubes), Fx bound with exactly one corner selected, last values in the MaxProFrame
  parameters (defaults 10 / 0.5 / key / 0 / 0, saved on OK when changed), read-only "Tube" row (material · thickness).
  Bend configurations removed (parent ran git rm on bend_config.py, bend_config_dialog.py, BendConfigurations.svg,
  test_bend_config.py, test_bend_config_dialog.py at the worker's request; InitGui entry, catalogs updated, 17 new es
  texts, ru unfinished). RED: test_folded_bar_panel import error (bend_config gone); translations 3 failures before
  the .qm recompile. GREEN (parent): test_folded_bar_panel 60, test_folded_bar_translations 5, test_folded_bar 35,
  test_shortcuts 5, test_toolbar_translations 4, test_russian_translation 6, test_compile_translations 3,
  test_expression_fields 4, test_unfolded_geometry 41, test_folded_geometry 11, test_folded_chain 23,
  test_library_translations 3, test_create_profile_apply 11 OK. Known limits: preview faces spanning other tubes are
  not highlighted; old panel texts still in the catalogs (T5).
- L13 T5 evidence (worker mwea5msy-5-s029, parent check): tutorial "## Folded miters" rewritten (corner list,
  selection, Remove, Corner fields, new "### Developed length and K-factor" citing DIN 6935 with the formula, examples
  and calibration K = (bend allowance / angle - r) / t, new "### Folded Corner objects"), Folded Bar bullet in
  "Expressions in panel fields"; README feature line and CHANGELOG Unreleased entry describe the current design.
  Catalogs: 19 stale MaxProFrame texts removed (es, frameforge_es byte-identical, ru), App::Property context with 12
  tooltips (es translated, ru unfinished), .qm recompiled; new test_the_folded_corner_property_tooltips_are_spanish
  (RED before the .qm recompile). GREEN (parent): test_russian_translation 6, test_compile_translations 3,
  test_folded_bar_translations 6, test_library_translations 3, test_toolbar_translations 4, test_folded_bar_panel 60,
  test_folded_bar 35 OK. Full suite not run (CI runs it on the PR).
- L14 (2026-11-13) "como podemos hacer para que se resalte en el 3D la esquina seleccionada?" with a screenshot
  (closed 80x40 frame, corner 3 "R 30 mm" selected, nothing highlighted, Esquina fields empty); parent analysis:
  `faces_of_tubes` keeps only faces lying wholly in the two tubes, so continuous walls never qualify; proposal coin
  overlay of `bar.Shape.common(box around the vertex)` and the empty fields as a bug; user: "Si".
- L15 (2026-11-13) "Si, otro problema aleatorio es que si cambio el gap un par de veces se quedo congelado cuando
  escribi "0." quisas flata algun debounce para evitar recalculos analizalo."
- L16 T7/T8 analysis (explorer mwepmq5p-1-olny + parent probes, offscreen FreeCAD stable, throwaway test removed):
  geometry is not the freeze: closed 80x40x1.5 frame, outer radii 10/20/30, key on/off, clearance 0, 0.01-30 ->
  check 0.03 s, unfold 0.2-0.4 s, fold 0.5-0.7 s, valid single solid (clearance 15 and 30 with key refused "The key
  does not fit"); the only loops (`_fitting_along` bisection, `_walk`) are bounded. Panel typing probe (edit, corner
  1, QTest keyClicks "0", ".", "5" and "0", ".", "3", six rounds) never stalled (longest pause 1.08 s, one preview).
  Found: in a comma-decimal locale the main-keyboard "." is a group separator, "0.5" gives 5 mm (S12 territory).
  Empty fields not reproduced: after pick, mouse click and forced preview the four fields show their values
  (e.g. 8,00 mm / 0,20 mm / Default / 0,450); the Mixed label hides with one corner. Hypothesis: the screenshot was
  taken during the freeze (no repaint). Weak leads kept: keystrokes during a recompute run `_refresh` in a nested
  event loop; a timer firing while `_recomputing` drops that preview without rescheduling.
- L17 (2026-11-13) answers to "screenshot during the freeze? / killed or recovered? / numpad or main key, which
  corner?": "1. no, 2. tuve que matar, 3. numpad no recuerdo que esquina. Nota: estabamos trabajando pudo haber sido
  un achivo que estabas modificando mientra yo probaba."
- L18 (2026-11-13) "Campos vacíos (T7) cuando saque la captura no estabamos modificando archivos, estabamos en pruebas
  luego"
- L19 T7 probe on a clean worktree of b6c4069 (removed after), Spanish (es_ES), edit three-corner bar, form rendered
  with grab(): one corner by click -> 8,00 mm / 0,20 mm / Predeterminado / 0,450 drawn, Fx shown; not reproduced with
  the default light theme (user's screenshot: dark theme; no StyleSheet param found in ~/.config/FreeCAD/*/user.cfg).
  New finding: Ctrl+click two corners -> the "Varios" label is painted over the value text ("Varios" on "7,00 mm"),
  its geometry set once (3, 2, 105, 24) while the field is narrower.
- L20 (2026-11-13) user's environment (screenshots): FreeCAD 27.1.0dev weekly 20261110 (e140bd8), Linux Mint 22.3,
  Español, number format "Sistema operativo", "Sustituir separador decimal" on, theme "FreeCAD Dark", "Recálculo de
  grano fino (experimental)" on, overlay panels on, OpenPreferences pack listed.
- L21 T6 evidence (worker mwepyhbq-2-8zt1, parent check): selected corners drawn as an SoAnnotation overlay of
  `bar.Shape.common(corner_box)` (box at the meeting of the tube axes, half-size (outer radius + tube/2) x tan(turn/2)
  + tube + 0.5 mm; open corner around `open_point`), SelectionColor, transparency 0.5, edges 2 px; removed through
  `clean()` on OK, Cancel, closed and form destroyed; cache by bar, shape hash, placement and box. Decision (worker
  query, parent answer B): while a corner is drawn the FreeCAD selection is cleared with `_select([])`, new-bar member
  highlight back with no corner selected. Fallback for corners the preview does not fold kept (tube selection).
  `faces_of_tubes` and helpers removed. RED: test_folded_bar_panel failures=2 errors=6 (5 new overlay tests). GREEN:
  test_folded_bar_panel 64 OK, test_folded_bar 35 OK; black/isort (ci/requirements-format.txt) clean (parent).
  Not checked by eye in a real 3D view.

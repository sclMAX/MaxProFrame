# Folded corners: one object per corner, edited from a list of corners
Rework of the Folded Bar (feature folded-miter, PR #145/#146, not released): every corner is a `FoldedCorner` object
with its own outer radius, clearance, key and K-factor (Fx), the panel lists corners instead of tubes, and bend
configurations go away (thickness and material come from the profile). Branch feat/folded-corners. Delivery: one PR,
one commit per task (each about one review slice; T3 and T4 may each pass 400 lines). Status: T1-T4 done, T5 next.

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
- T5 S1-S11 tutorial, README, CHANGELOG, es/ru translations and .qm - inline - pending.

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

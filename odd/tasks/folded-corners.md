# Folded corners: one object per corner, edited from a list of corners
Rework of the Folded Bar (feature folded-miter, PR #145/#146, not released): every corner is a `FoldedCorner` object
with its own outer radius, clearance, key and K-factor (Fx), the panel lists corners instead of tubes, and bend
configurations go away (thickness and material come from the profile). Branch feat/folded-corners. Status: specs, review.

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
- S8 Automatic K-factor (L3, "si" to "K automático por esquina, con la opción de sobrescribirlo"): each corner's
  K-factor is Automatic by default (0), taken from inside radius / thickness: r/t < 1 -> 0.33, 1 <= r/t < 3 -> 0.40,
  3 <= r/t < 10 -> 0.45, r/t >= 10 -> 0.50; a value from 0.01 to 1 overrides it for that corner.
- S9 Fx (L2 "Los campos deberian ser fx.", L4 "Desde el inicio") -> outer radius, clearance, key diameter and
  K-factor of the selected corner take FreeCAD expressions in the panel (Fx icon or `=`), bound to that corner's
  object; when creating, Fx appears once the preview exists. OK keeps them in the Undo step, Cancel takes them back.
- S10 FoldedCorner object (L5 "SI vamos con B") -> one `FoldedCorner` document object per corner, child of its bar
  in the tree, identified by its two tubes (PieceA, PieceB), with OuterRadius, Clearance, Key, KeyDiameter (0:
  default), KFactor (0: automatic) and Open (closed frames). It replaces the bar's CornerRadii, OpenCorner, Clearance,
  Key and KeyDiameter. Editing a corner property recomputes the bar; expressions survive removing or reordering other
  corners; deleting the bar deletes its corners; removing a corner deletes its object.
- S11 Bars saved before (decision: feature not released, light migration) -> a bar saved by 1.13.x/main with the old
  properties opens with one FoldedCorner per corner holding the same geometry (outer radius = old corner radius or
  InsideRadius + WallThickness, its K-factor, clearance and key), and the old properties removed.
- S12 Decimal separator (L5 "Actiovo la opcion.", L6 "Agrega la nota.") -> no code: the tutorial explains FreeCAD's
  Edit > Preferences > General > Substitute decimal separator for the keypad period.

## Tasks
- T1 S12 tutorial note on the decimal separator - inline - commit pending.
- T2 S6 S7 S8 geometry per corner: `unfold`/`_bends` take per-corner settings (outer radius, clearance, key, key
  diameter, K-factor), thickness from the profile, automatic K, outer-radius limits and messages - inline - pending.
- T3 S7 S10 S11 FoldedCorner object, FoldedBar properties and execute through its corners, tree children, delete
  lifecycle, migration; remove bend_config, dialog, command, icon and their tests - inline - pending.
- T4 S1-S5 S9 panel: corner list with multi-selection, highlight, Remove, open corner, per-corner fields with Fx,
  last used values; configuration widgets removed - inline - pending.
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

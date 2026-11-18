# Library UI language

The library manager uses the language selected in **FreeCAD Preferences → General → Language**, not the operating system language. English remains English when selected. FreeCAD owns translation catalogs for the whole application; closing a library window does not unload them.

After changing language or updating translation catalogs, close and reopen the library manager and its owned dialogs. Existing windows are not promised to update every label live.

## Catalog content stays yours

Standard family names and recognized T-Slot variants are translated for display only. Stored family keys, library names, size codes, descriptions and standards are not rewritten. Custom family names remain unchanged unless they are an exact recognized standard name. Delete confirmations show the family display name but delete its original stored key.

## Error messages

Library actions provide translated context. Backend, operating-system and geometry-kernel diagnostic details remain verbatim so they can be used for troubleshooting; arbitrary technical prose is not parsed or translated. UI-generated sketch edit errors are translated.

The legacy `_on_calc_weight` material chooser has no connected visible action. Its English material display/reverse parsing remains a follow-up, not tested visible translation coverage. No new action is added here.

## Translation maintenance

Update the Spanish catalog `maxproframe_es.ts`, then run:

```sh
python3 freecad/maxproframe/compile_translations.py
```

This refreshes `maxproframe_es.qm` and its `es-ES`, `es-CO` and `es-AR` copies, the Spanish locales FreeCAD looks for. The committed `.qm` files are built with Qt's `lrelease`, the one bundled in the FreeCAD AppImage (`usr/lib/qt6/bin/lrelease`): `compile_translations.py` gives working catalogs but does not reproduce those files byte for byte. Build `maxproframe_es.qm` and `maxproframe_ru.qm` with it from their `.ts`, and copy `maxproframe_es.qm` to the `es-ES`, `es-CO` and `es-AR` names. Catalog tests cover literal library, card, DXF and sketch-dialog messages plus indirect labels and standard T-Slot names.

A translation keeps every placeholder of its source exactly: `{}`, `{max:g}`, `{crossbar}`, `%s`. The code fills them, so a translated field name (`{поперечина}` for `{crossbar}`) makes the message fail and a dropped one hides the names it should show; reordering them is fine. `tests/test_translation_placeholders.py` checks every `.ts` catalog.

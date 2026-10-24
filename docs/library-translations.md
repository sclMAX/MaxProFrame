# Library UI language

The library manager uses the language selected in **FreeCAD Preferences → General → Language**, not the operating system language. English remains English when selected. FreeCAD owns translation catalogs for the whole application; closing a library window does not unload them.

After changing language or updating translation catalogs, close and reopen the library manager and its owned dialogs. Existing windows are not promised to update every label live.

## Catalog content stays yours

Standard family names and recognized T-Slot variants are translated for display only. Stored family keys, library names, size codes, descriptions and standards are not rewritten. Custom family names remain unchanged unless they are an exact recognized standard name. Delete confirmations show the family display name but delete its original stored key.

## Error messages

Library actions provide translated context. Backend, operating-system and geometry-kernel diagnostic details remain verbatim so they can be used for troubleshooting; arbitrary technical prose is not parsed or translated. UI-generated sketch edit errors are translated.

The legacy `_on_calc_weight` material chooser has no connected visible action. Its English material display/reverse parsing remains a follow-up, not tested visible translation coverage. No new action is added here.

## Translation maintenance

Update both Spanish TS catalogs, then run:

```sh
python3 freecad/maxproframe/compile_translations.py
```

This refreshes the 16 shipped prefix/locale QM aliases. Catalog tests cover literal library, card, DXF and sketch-dialog messages plus indirect labels and standard T-Slot names.

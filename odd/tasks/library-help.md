# Library manager help

Bundled, bilingual (English/Spanish) user guide for the Profile Library Manager, shown inside FreeCAD, plus contextual help (topic deep links, F1, tooltips, empty-state guidance).
Native runner: `/usr/bin/python3 ci/run_tests.py --freecad-bin .git/ci-policy-runtime/squashfs-root/AppRun`.

## Specs

- S1. "ayuda incluida en el addon" — a task-oriented user guide for the library manager ships inside the addon in English and Spanish and works offline.
- S2. The guide opens inside FreeCAD from a "?" button in the library manager, in the language FreeCAD's UI uses (English fallback).
- S3. "agreguemos ayuda contextual" — the "?" button and F1 open the guide at the section for the current context (library, family, sizes table, custom cards); New Library and Add Family dialogs offer Help for their own topic.
- S4. Every library manager control without a tooltip gets one (translated).
- S5. Empty states explain the next step (no families, no profiles, read-only system library).

## Tasks

- T1. [S1] English guide `resources/help/library-manager.md` with stable topic headings; linked from README/docs — route: inline — commit: pending
- T2. [S1, S2] Spanish guide `resources/help/library-manager.es.md` — route: inline — commit: pending
- T3. [S2, S3] Help viewer module with topic navigation; "?" button, F1 and sub-dialog Help — route: inline, test-first — commit: pending
- T4. [S4, S5] Tooltips and empty-state guidance — route: inline, test-first — commit: pending
- T5. [S1-S5] Spanish catalogs, CMake install list, docs; full native suite — route: inline — commit: pending

## Log

- L1. User: "ayuda incluida en el addon, y agreguemos ayuda contextual" (answer to the proposal: bilingual bundled guide + "?" button with QTextBrowser + deep links + tooltips + empty states; before that: "ok, ahora analicemos como incorporar ayuda a la libreria").
- L2. Decision: topics are matched by heading text; each topic's English heading is a translated source string, so the Spanish guide heading must equal its catalog translation (a test guards both guides). Guide language follows the loaded catalog via a translated file name. Screenshots are out of scope for this slice.
- L3. Design for T3/T4 (parent):
  - New module `freecad/maxproframe/help_viewer.py`: `HELP_PATH = resources/help`; `topic_headings()` returns `{topic: translate("frameforge", "<English heading>")}` built from literal `translate` calls for topics `overview`→"Profile Library Manager", `libraries`→"Libraries", `new-library`→"Create a library", `duplicate`→"Duplicate a system library", `share`→"Share a library", `families`→"Families", `sizes`→"Profiles and sizes", `custom-profiles`→"Custom profiles", `saving`→"Save your changes", `use`→"Use your profiles in a model". `guide_path()` = `HELP_PATH/basename(translate("frameforge", "library-manager.md"))`, falling back to `library-manager.md` when missing (Spanish catalog maps it to `library-manager.es.md`). `HelpDialog` (non-modal `Qt.Window`, title "MaxProFrame Help") holds a read-only `QTextBrowser` (`setMarkdown`, `setOpenExternalLinks(True)`, search path HELP_PATH) and `show_topic(topic)` scrolls the heading block whose text equals the topic heading to the top (unknown topic → top of the guide). `show_help(parent, topic)` reuses one dialog per parent, raises it and returns it.
  - Library manager: a "?" tool button (tooltip "Help (F1)") at the right of the header text; F1 (`QKeySequence.HelpContents`, window shortcut) on the dialog. `help_topic()`: from the focused widget, walk parents for a `helpTopic` dynamic property (libraries list and library buttons → libraries; families list, family buttons, Standard/Ref → families; sizes table, search, size buttons → sizes; cards view, Capture Section, Import DXF → custom-profiles; Save Changes → saving); otherwise by state: custom family → custom-profiles, any family → sizes, read-only library → duplicate, else libraries.
  - NewLibraryDialog and AddFamilyDialog: add `QDialogButtonBox.Help` and F1, opening topic `duplicate` (when duplicating) / `new-library` / `families`, parented to that dialog.
  - T4 tooltips (translated) for every library manager control that lacks one: libraries list, families list, Standard/Ref field, search field, sizes table, Save Changes, Close. Empty states: a library with no families shows guidance in the families area ("This library has no families yet. Add one with +." for editable, read-only system message otherwise); the existing "This family has no profiles." gains the next step (custom: capture or import; standard: add a size with +; read-only: duplicate the library to edit it).
  - Spanish: add every new source to BOTH `frameforge_es.ts` and `maxproframe_es.ts`, including the topic headings (their Spanish must equal the `##`/`#` headings in `library-manager.es.md`) and `library-manager.md`→`library-manager.es.md`; run `python3 freecad/maxproframe/compile_translations.py`. Add `help_viewer.py` to the file list in `tests/test_library_translations.py`.

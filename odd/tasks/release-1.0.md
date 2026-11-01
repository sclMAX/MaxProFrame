# Release 1.0.0 preparation

Prepare MaxProFrame 1.0.0 for the FreeCAD Addon Index: drop FrameForge compatibility so both addons can coexist, fix packaging metadata, rewrite the README with current screenshots, then release from a `release` branch.
Worktree `.git/gentle-worktrees/release-1.0`, branch `feat/release-1.0`. Native runner: `/usr/bin/python3 ci/run_tests.py --freecad-bin <main checkout>/.git/ci-policy-runtime/squashfs-root/AppRun`.

## Specs

- S1. "no podemos prometer compatibilidad con frameforge" / "Sin migracion por ahora" — MaxProFrame must not alias, replace or register anything under FrameForge's names: no `freecad.frameforge` module redirect or package, no `FrameForge_*` command aliases, no reading of the `Frameforge` preference group. No migration command.
- S2. "version usaremos 1.0.0" — version 1.0.0 in package.xml, version.py and pyproject.toml at release time.
- S3. Packaging metadata is valid for the Addon Index: one repository URL whose branch is the tracked `release` branch, a bugtracker URL, and install lists (setup.py, pyproject.toml, MANIFEST.in, CMakeLists.txt) without FrameForge entries or missing files.
- S4. "en el readme revisemos que captuaras hay y veamos que otras podemos incorporar" — README for GitHub reviewed with current screenshots.
- S5. "trabaja en tu propio worktree y rama, ya que hay otros agentes trabajando el el proyeto" — all work in this worktree.

## Tasks

- T1. [S1, S3] Remove FrameForge compatibility and fix install lists — route: worker — commit: this slice
- T2. [S3] package.xml metadata (single repo URL on `release`, bugtracker) — route: inline — commit: this slice
- T3. [S4] README rewrite; dialog captures by worker script, 3D captures by the user — commit: pending
- T4. [S2] Version 1.0.0, CHANGELOG 1.0.0 section, `release` branch, tag and GitHub Release — route: inline, needs user confirmation before push/tag — commit: pending

## Log

- L1. User: "ok, analiemos como mejorar el readme para github y quiero saber como crear la primera release, como se hace para que MaxProFrame aparezca en los addons de Freecad, si hacemos cambios como se actualiza si un usuario tiene instalado el addon, etc."
- L2. User: "Es un desarrollo que cambia mucho la forma de trabajo de frameforge, propongo v1.0.0, no podemos prometer compatibilidad con frameforge, que opinas? pros contras?"
- L3. User: "Sin migracion por ahora, version usaremos 1.0.0, como sabe freecad que usuarios usaro el addon?"
- L4. User: "Si, en el readme revisemos que captuaras hay y veamos que otras podemos incorporar"; then "otra cosa, trabaja en tu propio worktree y rama, ya que hay otros agentes trabajando el el proyeto"; then "ok, si necesitas te puedes comunicar con los otros agentes".
- L5. Findings: besides the module redirect (`freecad/maxproframe/__init__.py`, `freecad/frameforge/`), `ff_tools.add_command` also registers every command as `FrameForge_*` (overwrites the FrameForge addon's commands) and `get_param_group` reads the `Frameforge` preference group as fallback. CMakeLists.txt lists missing `icons/extrude-cutout.svg`, `ui/create_profiles.ui`, `init_gui.py`. All 53 tutorial screenshots in docs/images are from the FrameForge era (FrameForge icon, `FrameForge_EndMiter`, old Create Profiles panel); only the banner is current.
- L6. Other session (toolbar translations) reported: translations still ship frameforge_es.ts and FrameForge_*/frameforge_* .qm aliases (compile_translations.py PROJECT_PREFIXES / SPANISH_KNOWN_SOURCES) and use the "frameforge" Qt context. Decision: out of scope for this slice, recorded as follow-up; any change to .ts/.qm or compile_translations.py must be coordinated with that session first. Keep maxproframe_es.ts and frameforge_es.ts identical.
- L7. Other session (Trim analysis) confirmed no conflicts and reminded: tests/test_compat_regression.py imports freecad.frameforge.version (covered by T1), and FrameForge-era .FCStd documents store proxies under freecad.frameforge.* so their objects load without proxy after S1; the 1.0.0 CHANGELOG/release notes (T4) and README "Coming from FrameForge" section must state this.
- L8. User: "genera las de dialogos (con tema oscuro) y luego dime cuales necesitas de 3D". Plan: worker writes tools/capture_readme_dialogs.py, run in offscreen FreeCAD with an isolated profile and a dark palette, producing English captures under docs/images/readme/ (Create Profiles panel with alignment preview, Library Manager with custom profile cards, help window). 3D captures (workflow GIF, End Miter preview, TechDraw balloons, finished frame) are for the user.
- L9. Worker mvx2gl6q-2-ld6v finished T1: module redirect, FrameForge_* command aliases, Frameforge preference fallback and the dead `FrameForge` workbench alias removed; install lists fixed (CMake also targeted Mod/FrameForge). RED `test_compat_regression: Ran 7 tests ... FAILED (failures=21)`; GREEN 7/7; preserved test_preferences_native_strings 2, test_c_profile_ui 14, test_workbench_translation_loading 2; full suite `Ran 769 tests in 276.087s OK`. Parent fixed the CMake SearchBar copy-paste leftovers (target and install destination now MaxProFrame). Open question for the user: `library_manager.get_default_user_profiles_dir` still falls back to `<UserAppData>/FrameForge/profiles` and `FRAMEFORGE_USER_PROFILES_DIR`; the user's own FreeCAD v26-3 and v27-1 profiles keep their libraries only under FrameForge/profiles, so removing it would hide them.
- L10. User: "A, pero tengo una duda en una intalacion limpia de MaxProFrame apareceran esas bibliotezas del sistema?" Answer: yes, system libraries ship in resources/profiles. Done: get_default_user_profiles_dir reads only MAXPROFRAME_USER_PROFILES_DIR and <UserAppData>/MaxProFrame/profiles; the CI isolation variable in ci/run_tests.py, ci/tests/test_policy.py and tests renamed to MAXPROFRAME_USER_PROFILES_DIR (Risk item 5: CI environment). RED `AssertionError: .../FrameForge/profiles != .../MaxProFrame/profiles`; GREEN test_compat_regression 9, test_catalog_family_profiles 11, test_task_panel_usability 12, ci/tests test_policy 57. Release notes must tell users to move <UserAppData>/FrameForge/profiles to MaxProFrame/profiles.
- L11. Worker mvx2nm9t-3-ajfs finished the dialog captures: tools/capture_readme_dialogs.py (launches FreeCAD 1.1.4 offscreen with an isolated profile, FreeCAD Dark preference pack plus a matching dark QPalette, English locale) writes docs/images/readme/create-profiles-panel.png (378x947), library-manager-cards.png (1200x720), library-manager-help.png (720x720, topic Families), add-family.png (360x460); byte-identical across 4 runs; parent reviewed all four images.
- L12. Full suite after the profiles-folder change: `Ran 771 tests in 256.728s / OK`.

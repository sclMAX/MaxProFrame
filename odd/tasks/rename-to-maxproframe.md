# Rename Workbench to MaxProFrame
Objective: Rebrand and independentize the workbench from upstream FrameForge to MaxProFrame; branch: `feat/rename-to-maxproframe`.
Delivery: work-unit commits with tests and backwards-compatibility preservation; default branch remains unchanged until merge.

## Specs

S1. User objective, verbatim: "Tenemos que pensar un nombre nuestro para el baco de trabajo para poder independizar nuestro repo del upstream que opinas?" Checks: independent workbench identity distinct from upstream FrameForge.

S2. User name selection, verbatim: "MaxProFrame". Checks: adopt MaxProFrame as canonical workbench name, command prefix, package name, and identity across all code and metadata.

S3. User repository migration question: "como nos mudamos luego a nu repo nuevo con el nombre correcto?". Checks: preserve full Git history and cleanly configure new origin remote.

S4. User branch authorization, verbatim: "ok abrimos una rama para los cmabios ?". Checks: isolate all refactoring and rebrand changes in feature branch `feat/rename-to-maxproframe`.

S5. User workflow directive, verbatim: "Si recuerda usar odd y engram". Checks: strict ODD lifecycle execution, task tracking, Engram memory persistence and verification evidence.

S6. Backward-compatibility contract: existing `.FCStd` project files created with `freecad.frameforge` classes (Profile, TrimmedProfile, etc.) must open seamlessly without `unhandled FeaturePython` errors by providing a `sys.modules` aliasing shim from `freecad.frameforge` to `freecad.maxproframe`.

S7. Preferences migration contract: configuration stored under `BaseApp/Preferences/Mod/MaxProFrame` (and FreeCAD parameter group `User parameter:BaseApp/Preferences/Frameforge`) must migrate or fall back gracefully under `BaseApp/Preferences/MaxProFrame` without losing user preferences, operating on a per-key basis so partial writes do not hide legacy defaults.

## Tasks

T1 [S1,S2,S4,S6] route=inline; status=done; Package structure & backward compatibility bridge: rename package folder to `freecad/maxproframe`, update internal imports to `freecad.maxproframe`, and install `sys.modules["freecad.frameforge"]` compatibility alias in `Init.py` and `InitGui.py`. Evidence: 82 imports updated across 23 files; FrameForgeRedirectFinder meta-path hook tested and verified for direct and submodule imports.
T2 [S1,S2] route=inline; status=done; Workbench registration and command naming: update `InitGui.py` to register `MaxProFrame` workbench, rename command identifiers from `FrameForge_*` to `MaxProFrame_*` while maintaining backward alias mappings. Evidence: MaxProFrame workbench class registered with FrameForge alias; all 15 commands registered with dual MaxProFrame_* and FrameForge_* identifiers.
T3 [S2,S7] route=inline; status=done; Preferences and configuration migration: update `ff_tools.py` and tools to use `BaseApp/Preferences/Mod/MaxProFrame` with fallback to `FrameForge`. Evidence: get_param_group(writable=False/True) implemented with _PreferencesProxy for per-key fallback; get_default_user_profiles_dir() updated with dual directory and env var resolution; verified with unit tests.
T4 [S1,S2] route=inline; status=done; Package metadata and build scripts: update `package.xml`, `pyproject.toml`, `setup.py`, `CMakeLists.txt`, and documentation with new metadata, repository URL placeholder, and workbench descriptors. Evidence: package.xml updated with MaxProFrame descriptors; pyproject.toml and setup.py configured with maxproframe and backward-compat packages; CMakeLists.txt resource paths updated.
T5 [S2,S5] route=inline; status=done; Test suite and translation references: update test imports and mock paths across `tests/` to use `freecad.maxproframe`. Evidence: 156 occurrences updated across 43 test files; maxproframe_*.qm and .ts translation catalogs added; test imports verified.
T6 [S2,S5,S6] route=inline; status=done; End-to-end verification: verify Python package import, FreeCAD headless compatibility shim, command registration, and run test suite. Evidence: E2E test script verified canonical imports, legacy shim identity (LegacyProfile is CanonicalProfile), 30 Gui commands registered (15 MaxProFrame_* + 15 FrameForge_*), preferences fallback and persistence, and custom profile image assets.
T7 [S5,S6,S7] route=inline; status=done; Peer review findings & regression tests: fix _AliasLoader to restore canonical name/spec and implement _PreferencesProxy for per-key fallback; commit regression suite `tests/test_compat_regression.py`. Evidence: commit `bae898c` (implementation) + `1a105a8` (regression tests, exit 0, 2/2 tests pass).

## Log

L1. User inquiry, verbatim: "Tenemos que pensar un nombre nuestro para el baco de trabajo para poder independizar nuestro repo del upstream que opinas?"
L2. User proposed combination: "QUe opinas de combinar "MAX" perfil y marco ?"
L3. User considered variant: "y MaxProfileFrame?"
L4. User selected final canonical name: "MaxProFrame"
L5. User requested branch opening: "ok abrimos una rama para los cmabios ?"
L6. User directive: "Si recuerda usar odd y engram"

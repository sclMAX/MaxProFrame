# Test MaxProFrame in stable and weekly FreeCAD

Run both downloaded AppImages against this checkout, with separate preferences, data, cache, temporary files and logs. Gear Lever and the normal FreeCAD profile are not changed.

## Launch

Place these executable AppImages in the checkout's parent directory:

- `FreeCAD_1.1.4-Linux-x86_64-py311.AppImage` ([download](https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage))
- The weekly pinned for CI: download the AppImage at the `url` of the `weekly` entry in `ci/targets.json` and check it with its `sha256`.

`weekly` takes the file name from that `url`, so after a weekly bump (see [CI](ci.md)) download the new AppImage; the old one can be deleted.

From the repository root:

```bash
python3 tools/freecad-test.py 1.1.4
python3 tools/freecad-test.py weekly
# Optionally open a test document:
python3 tools/freecad-test.py 1.1.4 /absolute/path/to/copy.FCStd
```

Select **MaxProFrame** in the workbench selector. Restart the application after changing Python code.

## Launcher checks

Run launcher tests with the host Python interpreter, not inside FreeCAD:

```bash
python3 -m unittest discover -s ci/tests -p 'test_freecad_test_launcher.py' -v
```

These host-only tests live in `ci/tests/` so native FreeCAD test discovery does not launch the embedded FreeCAD executable as if it were Python.

## Profiles and logs

Each version uses `.freecad-test/<version>/` (`1.1.4` or `weekly`, ignored by Git). Its `data/FreeCAD/Mod/MaxProFrame` is a symbolic link to this checkout, not an installed copy. Both versions therefore see the same source revision. The launcher refuses to replace an existing, unrelated module path.

Preferences are stored in `config/user.cfg` and `config/system.cfg`; process output is appended to `FreeCAD.log`. These logs may contain warnings even when the application launches successfully. User data is isolated, but both applications still share the source checkout and can write Python bytecode caches there; this is not a security sandbox.

Locally prepared `.desktop` shortcuts under `.freecad-test/` use absolute paths. Recreate them if you move the checkout. Depending on the file manager, mark each shortcut as trusted / allow launching before double-clicking it. They are not installed into the system application menu.

## Compare behavior

Use separate copies of the same starting document. In each version, activate MaxProFrame, create profiles, apply miters and trims, generate a BOM, then save, close and reopen. Never overwrite the original document with the weekly: backwards-compatible saving is not guaranteed.

An automated startup smoke check establishes loading and workbench activation only; it does not establish that all modeling operations work correctly in both releases.

## Native test suite

Run the full suite on both versions, as CI does, from extracted AppImages (see [CI](ci.md)):

```bash
python3 ci/run_tests.py --freecad-bin /path/to/1.1.4/squashfs-root/AppRun --reports /tmp/reports-stable --timeout 420
python3 ci/run_tests.py --freecad-bin /path/to/weekly/squashfs-root/AppRun --reports /tmp/reports-weekly --timeout 480 --target weekly
```

Extract each AppImage in its own empty directory with `./FreeCAD_<...>.AppImage --appimage-extract`.

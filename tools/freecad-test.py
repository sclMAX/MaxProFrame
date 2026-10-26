#!/usr/bin/env python3
"""Launch a downloaded FreeCAD AppImage with a checkout-local test profile."""
import argparse
import os
from pathlib import Path
import subprocess


IMAGES = {
    "1.1.4": "FreeCAD_1.1.4-Linux-x86_64-py311.AppImage",
    "26.3rc2": "FreeCAD_26.3rc2-Linux-x86_64.AppImage",
}


def main():
    parser = argparse.ArgumentParser(
        description="Run MaxProFrame in an isolated FreeCAD test profile (Gear Lever is not used).",
        epilog="AppImages must be in the checkout's parent directory. Logs and profiles: .freecad-test/<version>/.",
    )
    parser.add_argument("version", choices=IMAGES)
    parser.add_argument("files", nargs="*", help="Optional FCStd documents or FCMacro files to open")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    image = root.parent / IMAGES[args.version]
    if not image.is_file():
        try:
            git_common = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            candidate = Path(git_common).parent.parent / IMAGES[args.version]
            if candidate.is_file():
                image = candidate
        except Exception:
            pass
    if not image.is_file():
        parser.error(f"AppImage not found: {image}")
    if not os.access(image, os.X_OK):
        parser.error(f"AppImage is not executable; run: chmod u+x '{image}'")

    profile = root / ".freecad-test" / args.version
    env = os.environ.copy()
    for key, relative in {
        "HOME": "home",
        "XDG_CONFIG_HOME": "config",
        "XDG_DATA_HOME": "data",
        "XDG_CACHE_HOME": "cache",
        "FREECAD_USER_HOME": "home",
        "FREECAD_USER_DATA": "data/FreeCAD",
        "FREECAD_USER_TEMP": "tmp",
        "TMPDIR": "tmp",
    }.items():
        directory = profile / relative
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    # Do not inject the host interpreter's packages into the bundled Python.
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    modules = profile / "data/FreeCAD/Mod"
    modules.mkdir(parents=True, exist_ok=True)
    link = modules / "MaxProFrame"
    if not link.exists() and not link.is_symlink():
        link.symlink_to(root, target_is_directory=True)
    elif not link.is_symlink() or link.resolve() != root:
        parser.error(f"Refusing to replace existing module path: {link}")

    log = profile / "FreeCAD.log"
    print(f"FreeCAD {args.version}: {log}", flush=True)
    command = [
        str(image),
        "--user-cfg", str(profile / "config/user.cfg"),
        "--system-cfg", str(profile / "config/system.cfg"),
        *args.files,
    ]
    with log.open("a") as output:
        return subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    raise SystemExit(main())

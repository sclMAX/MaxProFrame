#!/usr/bin/env python3
"""Capture the dark-theme dialog screenshots used by the GitHub README.

Run from the repository root with the host Python and a FreeCAD 1.1 binary or
extracted AppImage ``AppRun``::

    python3 tools/capture_readme_dialogs.py --freecad-bin /path/to/squashfs-root/AppRun

The launcher starts FreeCAD offscreen with a throwaway profile (the user's real
FreeCAD profile is never read or written), applies FreeCAD's bundled
"FreeCAD Dark" preference pack (stylesheet) plus a matching dark ``QPalette``,
sets the language to English and runs this same file as a macro. The macro
builds every document and library in temporary directories, grabs the dialogs
with ``QWidget.grab()`` and writes the PNGs to ``docs/images/readme/``, printing
each written path. Re-running overwrites them.
"""

import os
import sys

OUTPUT_ENV = "MPF_README_CAPTURE_OUT"
ROOT_ENV = "MPF_README_CAPTURE_ROOT"


# --------------------------------------------------------------------------
# Host launcher
# --------------------------------------------------------------------------


def _dark_user_cfg(freecad_share, destination):
    """Write a user.cfg made of the bundled dark preference pack plus capture settings."""
    import xml.etree.ElementTree as ET

    pack = os.path.join(freecad_share, "Gui", "PreferencePacks", "FreeCAD Dark", "FreeCAD Dark.cfg")
    if not os.path.isfile(pack):
        raise SystemExit(f"capture error: dark preference pack not found: {pack}")
    tree = ET.parse(pack)

    def group(parent, name):
        found = parent.find(f"FCParamGroup[@Name='{name}']")
        if found is None:
            found = ET.SubElement(parent, "FCParamGroup", Name=name)
        return found

    def set_value(parent, tag, name, value):
        for old in parent.findall(f"{tag}[@Name='{name}']"):
            parent.remove(old)
        ET.SubElement(parent, tag, Name=name, Value=value)

    preferences = group(group(group(tree.getroot(), "Root"), "BaseApp"), "Preferences")
    general = group(preferences, "General")
    for old in general.findall("FCText[@Name='Language']"):
        general.remove(old)
    ET.SubElement(general, "FCText", Name="Language").text = "English"
    # Offscreen Qt warnings must not open notification popups over the captures.
    notifications = group(preferences, "NotificationArea")
    set_value(notifications, "FCBool", "NonIntrusiveNotificationsEnabled", "0")
    set_value(notifications, "FCInt", "MaxOpenNotifications", "0")
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def launch():
    import argparse
    import pathlib
    import shutil
    import subprocess
    import tempfile

    parser = argparse.ArgumentParser(description="Capture the README dialog screenshots in an offscreen FreeCAD.")
    parser.add_argument("--freecad-bin", required=True, help="FreeCAD executable or extracted AppImage AppRun")
    parser.add_argument("--timeout", type=float, default=300.0, help="Seconds before FreeCAD is killed")
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parents[1]
    output = root / "docs" / "images" / "readme"
    freecad_bin = pathlib.Path(args.freecad_bin).resolve()
    if not freecad_bin.is_file():
        parser.error(f"FreeCAD binary not found: {freecad_bin}")
    env = os.environ.copy()
    if freecad_bin.name == "AppRun":
        # Reproduce the AppRun bootstrap without running its script (same as ci/run_tests.py).
        dist = freecad_bin.parent
        freecad_bin = dist / "usr" / "bin" / "freecad"
        env["PREFIX"] = str(dist / "usr")
        env["PYTHONHOME"] = str(dist / "usr")
        env["PATH_TO_FREECAD_LIBDIR"] = str(dist / "usr" / "lib")
        env["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"
        env["FONTCONFIG_PATH"] = "/etc/fonts"
        share = dist / "usr" / "share"
    else:
        env.pop("PYTHONHOME", None)
        share = freecad_bin.parent.parent / "share"
        if not (share / "Gui").is_dir():
            share = share / "freecad"
    env.pop("PYTHONPATH", None)

    with tempfile.TemporaryDirectory(prefix="mpf_readme_capture_") as scratch:
        scratch = pathlib.Path(scratch)
        for key, name in (
            ("HOME", "home"),
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_DATA_HOME", "data"),
            ("XDG_CACHE_HOME", "cache"),
            ("TMPDIR", "tmp"),
            ("FREECAD_USER_HOME", "freecad"),
            ("MAXPROFRAME_USER_PROFILES_DIR", "profiles"),
        ):
            (scratch / name).mkdir()
            env[key] = str(scratch / name)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        # English number formatting regardless of the host locale.
        env["LANG"] = env["LC_ALL"] = "C.UTF-8"
        env["LANGUAGE"] = "en"
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        env[ROOT_ENV] = str(root)
        env[OUTPUT_ENV] = str(output)
        user_cfg = scratch / "config" / "user.cfg"
        _dark_user_cfg(str(share), str(user_cfg))
        # Run a copy as an FCMacro: FreeCAD would import a .py argument as a module
        # and leave a __pycache__ folder in the checkout.
        macro = scratch / "capture_readme_dialogs.FCMacro"
        shutil.copyfile(__file__, macro)
        command = [str(freecad_bin), "--user-cfg", str(user_cfg), str(macro)]
        try:
            result = subprocess.run(command, cwd=root, env=env, timeout=args.timeout, start_new_session=True)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"capture error: FreeCAD timed out after {args.timeout}s")
    return result.returncode


# --------------------------------------------------------------------------
# FreeCAD macro
# --------------------------------------------------------------------------


def capture():
    import shutil
    import tempfile
    import traceback

    sys.dont_write_bytecode = True
    root = os.environ[ROOT_ENV]
    output = os.environ[OUTPUT_ENV]
    if root not in sys.path:
        sys.path.insert(0, root)
    import freecad

    package = os.path.join(root, "freecad")
    if package not in freecad.__path__:
        freecad.__path__ = [package] + list(freecad.__path__)

    from PySide import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
    _apply_dark_palette(app)
    os.makedirs(output, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="mpf_readme_")
    status = 0
    try:
        for job in (_capture_create_profiles, _capture_library_manager, _capture_help):
            job(app, scratch, output)
    except BaseException:
        traceback.print_exc(file=sys.__stderr__)
        status = 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(status)


# Colors of the bundled "FreeCAD Dark" stylesheet. The stylesheet only styles
# the widgets it targets; custom painted widgets (alignment preview, profile
# cards) read the palette, so give them the same colors.
DARK_PALETTE = {
    "Window": "#2d2d2d",
    "WindowText": "#ffffff",
    "Base": "#191919",
    "AlternateBase": "#232323",
    "ToolTipBase": "#191919",
    "ToolTipText": "#ffffff",
    "PlaceholderText": "#8c8c8c",
    "Text": "#ffffff",
    "Button": "#353535",
    "ButtonText": "#ffffff",
    "BrightText": "#ff6b6b",
    "Light": "#4a4a4a",
    "Midlight": "#3c3c3c",
    "Mid": "#252525",
    "Dark": "#141414",
    "Shadow": "#000000",
    "Highlight": "#366da3",
    "HighlightedText": "#ffffff",
    "Link": "#6cb4ff",
    "LinkVisited": "#b48cff",
}
DARK_DISABLED = {"WindowText": "#7a7a7a", "Text": "#7a7a7a", "ButtonText": "#7a7a7a", "Highlight": "#3a3a3a"}


def _apply_dark_palette(app):
    from PySide import QtGui

    palette = QtGui.QPalette()
    for role, color in DARK_PALETTE.items():
        palette.setColor(getattr(QtGui.QPalette, role), QtGui.QColor(color))
    for role, color in DARK_DISABLED.items():
        palette.setColor(QtGui.QPalette.Disabled, getattr(QtGui.QPalette, role), QtGui.QColor(color))
    app.setPalette(palette)


def _report(text):
    # FreeCAD redirects sys.stdout to its report view; write to the process stdout.
    sys.__stdout__.write(text + "\n")
    sys.__stdout__.flush()


def _settle(app, milliseconds=300):
    """Process events for a fixed wall-clock time so Qt animations (task boxes) finish."""
    import time

    from PySide import QtCore

    deadline = time.monotonic() + milliseconds / 1000.0
    while True:
        app.processEvents()
        # processEvents() skips deleteLater(); replaced cards must really go away.
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)


def _save(widget, output, name):
    path = os.path.join(output, name)
    from PySide import QtGui

    grabbed = widget.grab()
    # Flatten onto the window color so no transparent area shows the README background.
    pixmap = QtGui.QPixmap(grabbed.size())
    pixmap.setDevicePixelRatio(grabbed.devicePixelRatio())
    pixmap.fill(QtGui.QColor(DARK_PALETTE["Window"]))
    painter = QtGui.QPainter(pixmap)
    painter.drawPixmap(0, 0, grabbed)
    painter.end()
    if pixmap.isNull() or not pixmap.save(path, "PNG"):
        raise RuntimeError(f"could not save {path}")
    _report(f"wrote {os.path.relpath(path, os.environ[ROOT_ENV])} ({pixmap.width()}x{pixmap.height()})")


def _save_composed(size, reference, parts, output, name):
    """Save ``parts`` painted at their positions inside ``reference`` on a plain canvas."""
    from PySide import QtGui

    image = QtGui.QPixmap(size)
    image.fill(QtGui.QColor(DARK_PALETTE["Window"]))
    painter = QtGui.QPainter(image)
    for part in parts:
        painter.drawPixmap(part.mapTo(reference, part.rect().topLeft()), part.grab())
    painter.end()
    path = os.path.join(output, name)
    if not image.save(path, "PNG"):
        raise RuntimeError(f"could not save {path}")
    _report(f"wrote {os.path.relpath(path, os.environ[ROOT_ENV])} ({image.width()}x{image.height()})")


def _close_documents():
    import FreeCAD as App

    for name in list(App.listDocuments()):
        App.closeDocument(name)


def _closed_wire(sketch, points):
    """Add a closed polyline; an ``("arc", via, end)`` item draws a three-point arc."""
    import FreeCAD as App
    import Part

    start = current = App.Vector(*points[0], 0)
    for item in points[1:] + [points[0]]:
        if item[0] == "arc":
            via, end = App.Vector(*item[1], 0), App.Vector(*item[2], 0)
            sketch.addGeometry(Part.Arc(current, via, end), False)
            current = end
        else:
            end = App.Vector(*item, 0)
            sketch.addGeometry(Part.LineSegment(current, end), False)
            current = end
    assert current.isEqual(start, 1e-9)


def _circle(sketch, center, radius):
    import FreeCAD as App
    import Part

    sketch.addGeometry(Part.Circle(App.Vector(*center, 0), App.Vector(0, 0, 1), radius), False)


def _section_sketches(doc):
    """Realistic custom sections: (code, description, sketch)."""
    sections = []

    def add(code, description, build):
        sketch = doc.addObject("Sketcher::SketchObject", code.replace(".", "_").replace("x", "_"))
        build(sketch)
        sections.append((code, description, sketch))

    add(
        "C100x50x15x2",
        "Lipped C purlin, cold formed",
        lambda s: _closed_wire(
            s,
            [
                (0, 0),
                (50, 0),
                (50, 15),
                (48, 15),
                (48, 2),
                (2, 2),
                (2, 98),
                (48, 98),
                (48, 85),
                (50, 85),
                (50, 100),
                (0, 100),
            ],
        ),
    )
    add(
        "L50x50x5",
        "Equal leg angle",
        lambda s: _closed_wire(s, [(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)]),
    )
    add(
        "T60x60x6",
        "T section for frame stiffeners",
        lambda s: _closed_wire(s, [(27, 0), (33, 0), (33, 54), (60, 54), (60, 60), (0, 60), (0, 54), (27, 54)]),
    )

    def tube(s):
        _circle(s, (0, 0), 24.15)
        _circle(s, (0, 0), 20.95)

    add("RT48.3x3.2", "Round tube for handrails", tube)
    add(
        "HC60x30",
        "Handrail cap for 50 mm flat bar",
        lambda s: _closed_wire(
            s,
            [
                (0, 0),
                (4, 0),
                (4, 12),
                ("arc", (30, 26), (56, 12)),
                (56, 0),
                (60, 0),
                (60, 12),
                ("arc", (30, 30), (0, 12)),
            ],
        ),
    )
    doc.recompute()
    return sections


def _capture_create_profiles(app, scratch, output):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Sketcher  # noqa: F401  (registers the sketch type)
    from PySide import QtCore, QtWidgets

    from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel

    doc = App.newDocument("Frame")
    sketch = doc.addObject("Sketcher::SketchObject", "FrameSketch")
    _closed_wire(sketch, [(0, 0), (1200, 0), (1200, 800), (0, 800)])
    doc.recompute()
    Gui.Selection.clearSelection()
    for index in range(1, 5):
        Gui.Selection.addSelection(doc.Name, sketch.Name, f"Edge{index}")

    panel = CreateProfileTaskPanel()
    Gui.Selection.addObserver(panel)
    Gui.Control.showDialog(panel)
    _settle(app)
    proxy = panel.form_proxy
    proxy.combo_material.setCurrentText("Metal")
    proxy.combo_family.setCurrentText("Square Hollow")
    proxy.combo_size.setCurrentText("40x2.0")
    _settle(app, 1000)
    # Float the Tasks dock so the panel is captured with its header and buttons.
    dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "Tasks")
    dock.setFloating(True)
    dock.show()
    dock.resize(380, 1000)
    _settle(app, 1000)
    view = dock.widget()
    box = panel.form[0].parentWidget()
    while box is not None and box.metaObject().className() != "Gui::TaskView::TaskBox":
        box = box.parentWidget()
    # Compose only the dialog buttons and the task box: other children of the
    # floating dock (stale task watchers) would show through as ghost frames.
    buttons = [w for w in view.findChildren(QtWidgets.QDialogButtonBox) if w.isVisible()]
    parts = [box] + buttons
    bottom = box.mapTo(view, QtCore.QPoint(0, box.height())).y() + 8
    _save_composed(QtCore.QSize(view.width(), bottom), view, parts, output, "create-profiles-panel.png")
    Gui.Selection.removeObserver(panel)
    Gui.Control.closeDialog()
    _settle(app)
    _close_documents()


def _capture_library_manager(app, scratch, output):
    from unittest.mock import patch

    import FreeCAD as App
    import Sketcher  # noqa: F401  (registers the sketch type)
    from PySide import QtCore, QtWidgets

    from freecad.maxproframe.library_manager import LibraryManager
    from freecad.maxproframe.library_manager_dialog import AddFamilyDialog, ProfileLibraryManagerDialog
    from freecad.maxproframe.section_capture import save_section_asset
    from freecad.maxproframe.section_library import compute_sketch_dimensions_and_weight

    manager = LibraryManager(
        user_dir=os.path.join(scratch, "user"), registry_path=os.path.join(scratch, "registry.json")
    )
    folder = os.path.join(scratch, "Workshop Profiles")
    density = 7.85
    manager.create_folder_library(folder, "Workshop Profiles", material="Steel", density=density, data={})
    sizes = {}
    doc = App.newDocument("Sections")
    for code, description, sketch in _section_sketches(doc):
        asset = save_section_asset(folder, sketch, name="Section")
        height, width, weight, _area = compute_sketch_dimensions_and_weight(sketch, density)
        entry = ProfileLibraryManagerDialog._section_size_entry(asset, height, width, weight)
        entry["Description"] = description
        sizes[code] = entry
    _close_documents()
    manager.save_folder_library(
        folder,
        {
            "Square Hollow": {
                "norm": "EN 10219",
                "fillet": True,
                "sizes": {
                    "40x40x2": {"Height": "40", "Width": "40", "Thickness": "2", "Weight": "2.31"},
                    "50x50x3": {"Height": "50", "Width": "50", "Thickness": "3", "Weight": "4.25"},
                },
            },
            "Custom Profile": {
                "norm": "Workshop",
                "fillet": False,
                "canonical_family": "Custom Profile",
                "sizes": sizes,
            },
        },
        material="Steel",
        density=density,
    )

    dialog = ProfileLibraryManagerDialog(library_manager=manager)
    dialog.resize(1200, 720)
    dialog.show()
    dialog.refresh_libraries(select_name="Workshop Profiles")
    families = dialog.list_families
    for row in range(families.count()):
        if families.item(row).data(QtCore.Qt.UserRole) == "Custom Profile":
            families.setCurrentRow(row)
    _settle(app, 1000)
    dialog.cards_view.select_card(0)
    _settle(app, 500)
    _save(dialog, output, "library-manager-cards.png")

    add_family = AddFamilyDialog(dialog, dialog.current_lib_meta)
    add_family.resize(360, 460)
    add_family.select_family("Rectangular Hollow")
    add_family.cb_fillet.setChecked(True)
    add_family.show()
    _settle(app, 500)
    _save(add_family, output, "add-family.png")
    add_family.reject()

    with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard):
        dialog.close()
    _settle(app)


def _capture_help(app, scratch, output):
    from PySide import QtWidgets

    from freecad.maxproframe.help_viewer import show_help

    parent = QtWidgets.QWidget()
    parent.resize(400, 300)
    window = show_help(parent, "families")
    window.resize(720, 720)
    _settle(app)
    # Families, sizes and custom profiles fill the window without trailing blank space.
    window.show_topic("families")
    _settle(app)
    _save(window, output, "library-manager-help.png")
    window.close()
    parent.deleteLater()


# Inside FreeCAD this file runs as the copied macro; on the host it is the launcher.
if "FreeCAD" in sys.modules and os.environ.get(OUTPUT_ENV):
    capture()
elif __name__ == "__main__":
    raise SystemExit(launch())

#!/usr/bin/env python3
"""Record the automated MaxProFrame demo video.

Run from the repository root with the host Python and an extracted FreeCAD 1.1
AppImage ``AppRun``::

    python3 tools/record_demo_video.py --freecad-bin /path/to/squashfs-root/AppRun

FreeCAD opens full screen on the current X11 display (the 3D view needs a real
OpenGL context) with a throwaway profile and the bundled "FreeCAD Dark"
preference pack. This same file then runs as a macro that drives the workbench
step by step, grabs the main window into numbered frames with a caption bar and
exits. The host side encodes the frames with ``ffmpeg`` into
``docs/video/maxproframe-demo.mp4`` and a smaller ``maxproframe-demo.gif``.
Do not use the FreeCAD window while it records.
"""

import os
import sys

FRAMES_ENV = "MPF_DEMO_FRAMES"
ROOT_ENV = "MPF_DEMO_ROOT"
FPS = 20


# --------------------------------------------------------------------------
# Host launcher
# --------------------------------------------------------------------------


def _encode(frames, output):
    import subprocess

    output.mkdir(parents=True, exist_ok=True)
    mp4 = output / "maxproframe-demo.mp4"
    gif = output / "maxproframe-demo.gif"
    pattern = str(frames / "frame_%05d.png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            pattern,
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=True,
    )
    palette = frames / "palette.png"
    scale = "fps=12,scale=960:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            pattern,
            "-vf",
            f"{scale},palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            pattern,
            "-i",
            str(palette),
            "-lavfi",
            f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
            str(gif),
        ],
        check=True,
    )
    for path in (mp4, gif):
        print(f"wrote {path.relative_to(output.parents[1])} ({path.stat().st_size // 1024} KiB)")


def launch():
    import argparse
    import pathlib
    import shutil
    import subprocess
    import tempfile

    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    from capture_readme_dialogs import _dark_user_cfg

    parser = argparse.ArgumentParser(description="Record the MaxProFrame demo video in a visible FreeCAD.")
    parser.add_argument("--freecad-bin", required=True, help="Extracted FreeCAD AppImage AppRun")
    parser.add_argument("--timeout", type=float, default=600.0, help="Seconds before FreeCAD is killed")
    parser.add_argument("--keep-frames", action="store_true", help="Keep the PNG frames in .freecad-test/demo-video")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        parser.error("ffmpeg not found on PATH")
    if not os.environ.get("DISPLAY"):
        parser.error("an X11 DISPLAY is required: the 3D view needs a real OpenGL context")
    apprun = pathlib.Path(args.freecad_bin).resolve()
    if apprun.name != "AppRun" or not apprun.is_file():
        parser.error(f"expected an extracted AppImage AppRun: {apprun}")

    dist = apprun.parent
    env = os.environ.copy()
    # Reproduce the AppRun bootstrap without running its script (same as ci/run_tests.py).
    env["PREFIX"] = str(dist / "usr")
    env["PYTHONHOME"] = str(dist / "usr")
    env["PATH_TO_FREECAD_LIBDIR"] = str(dist / "usr" / "lib")
    env["FONTCONFIG_FILE"] = "/etc/fonts/fonts.conf"
    env["FONTCONFIG_PATH"] = "/etc/fonts"
    env.pop("PYTHONPATH", None)
    env.pop("WAYLAND_DISPLAY", None)
    env["QT_QPA_PLATFORM"] = "xcb"
    env["LANG"] = env["LC_ALL"] = "C.UTF-8"
    env["LANGUAGE"] = "en"

    work = root / ".freecad-test" / "demo-video"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="profile_", dir=work) as scratch:
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
        # Load the workbench from this checkout through the throwaway profile's Mod folder.
        env["FREECAD_USER_DATA"] = str(scratch / "data" / "FreeCAD")
        modules = scratch / "data" / "FreeCAD" / "Mod"
        modules.mkdir(parents=True)
        (modules / "MaxProFrame").symlink_to(root, target_is_directory=True)
        frames = work / "frames"
        shutil.rmtree(frames, ignore_errors=True)
        frames.mkdir()
        env[ROOT_ENV] = str(root)
        env[FRAMES_ENV] = str(frames)
        user_cfg = scratch / "config" / "user.cfg"
        _dark_user_cfg(str(dist / "usr" / "share"), str(user_cfg))
        macro = scratch / "record_demo_video.FCMacro"
        shutil.copyfile(__file__, macro)
        command = [str(dist / "usr" / "bin" / "freecad"), "--user-cfg", str(user_cfg), str(macro)]
        try:
            result = subprocess.run(command, cwd=root, env=env, timeout=args.timeout, start_new_session=True)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"record error: FreeCAD timed out after {args.timeout}s")
    if result.returncode != 0:
        raise SystemExit(f"record error: FreeCAD exited with {result.returncode}")
    count = len(list(frames.glob("frame_*.png")))
    if count == 0:
        raise SystemExit("record error: no frames were written")
    print(f"{count} frames ({count / FPS:.1f} s)")
    _encode(frames, root / "docs" / "video")
    if not args.keep_frames:
        shutil.rmtree(frames, ignore_errors=True)
    return 0


# --------------------------------------------------------------------------
# FreeCAD macro
# --------------------------------------------------------------------------


class Recorder:
    """Grab the main window into numbered PNG frames at ``FPS`` with an optional caption bar."""

    def __init__(self, app, window, frames):
        self.app = app
        self.window = window
        self.frames = frames
        self.index = 0
        self.caption = ""
        self.subtitle = ""

    def say(self, caption, subtitle=""):
        self.caption = caption
        self.subtitle = subtitle

    def _grab(self):
        from PySide import QtCore, QtGui

        # QWidget.grab() garbles the OpenGL 3D view; read the composited screen pixels instead.
        # The window stays on top (see record()) so no other window shows in the frames.
        self.window.raise_()
        image = self.window.screen().grabWindow(0).toImage()
        if self.caption:
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            width, height = image.width(), image.height()
            bar = QtCore.QRectF(width * 0.18, height - 170, width * 0.64, 120 if self.subtitle else 84)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(18, 18, 18, 215))
            painter.drawRoundedRect(bar, 14, 14)
            painter.setBrush(QtGui.QColor("#f0a030"))
            painter.drawRoundedRect(QtCore.QRectF(bar.left(), bar.top(), 8, bar.height()), 4, 4)
            title = QtGui.QFont("Sans Serif", 30, QtGui.QFont.Bold)
            painter.setFont(title)
            painter.setPen(QtGui.QColor("#ffffff"))
            painter.drawText(bar.adjusted(36, 14, -24, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, self.caption)
            if self.subtitle:
                painter.setFont(QtGui.QFont("Sans Serif", 18))
                painter.setPen(QtGui.QColor("#c8c8c8"))
                painter.drawText(bar.adjusted(36, 66, -24, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, self.subtitle)
            painter.end()
        path = os.path.join(self.frames, f"frame_{self.index:05d}.png")
        if not image.save(path, "PNG", 1):
            raise RuntimeError(f"could not save {path}")
        self.index += 1

    def hold(self, seconds, step=None):
        """Record ``seconds`` of video; ``step(t)`` with t in [0, 1] runs before every frame."""
        frames = max(1, round(seconds * FPS))
        for number in range(frames):
            if step is not None:
                step(number / max(1, frames - 1))
            self.app.processEvents()
            self._grab()


def _report(text):
    sys.__stdout__.write(text + "\n")
    sys.__stdout__.flush()


def record():
    import shutil
    import tempfile
    import traceback

    sys.dont_write_bytecode = True
    root = os.environ[ROOT_ENV]
    for path in (root, os.path.join(root, "tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import freecad

    package = os.path.join(root, "freecad")
    if package not in freecad.__path__:
        freecad.__path__ = [package] + list(freecad.__path__)

    import FreeCADGui as Gui
    from capture_readme_dialogs import _apply_dark_palette, _settle
    from PySide import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    QtCore.QLocale.setDefault(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))
    _apply_dark_palette(app)
    window = Gui.getMainWindow()
    window.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
    window.showFullScreen()
    _settle(app, 1500)
    recorder = Recorder(app, window, os.environ[FRAMES_ENV])
    scratch = tempfile.mkdtemp(prefix="mpf_demo_")
    status = 0
    try:
        storyboard(app, recorder, scratch)
    except BaseException:
        traceback.print_exc(file=sys.__stderr__)
        status = 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _report(f"recorded {recorder.index} frames")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(status)


TABLE_LENGTH, TABLE_WIDTH, TABLE_HEIGHT = 1200, 800, 750


def _view():
    import FreeCADGui as Gui

    return Gui.ActiveDocument.ActiveView


def _orbit(rec, seconds, degrees):
    """Turn the camera ``degrees`` around the vertical axis through the scene."""
    import FreeCAD as App

    view = _view()
    start = view.getCameraOrientation()

    def step(t):
        eased = 0.5 - 0.5 * __import__("math").cos(t * 3.141592653589793)
        turn = App.Rotation(App.Vector(0, 0, 1), degrees * eased)
        view.setCameraOrientation(turn.multiply(start))

    rec.hold(seconds, step)


def _focus(rec, seconds, point, height):
    """Glide the orthographic camera to look at ``point`` with a view ``height`` in mm."""
    import math

    import FreeCAD as App

    camera = _view().getCameraNode()
    direction = _view().getCameraOrientation().multVec(App.Vector(0, 0, -1))
    distance = camera.focalDistance.getValue()
    start = App.Vector(*camera.position.getValue().getValue())
    end = point - direction * distance
    start_height = camera.height.getValue()

    def step(t):
        eased = 0.5 - 0.5 * math.cos(t * math.pi)
        position = start + (end - start) * eased
        camera.position.setValue(position.x, position.y, position.z)
        camera.height.setValue(start_height + (height - start_height) * eased)

    rec.hold(seconds, step)


def _animate(rec, command, seconds=1.5):
    """Run an animated view command (fit, isometric, zoom to selection) and record it."""
    import FreeCADGui as Gui

    Gui.SendMsgToActiveView(command)
    rec.hold(seconds)


def _select(objects, subelements=None):
    import FreeCADGui as Gui

    Gui.Selection.clearSelection()
    for obj in objects:
        if subelements:
            for name in subelements:
                Gui.Selection.addSelection(obj.Document.Name, obj.Name, name)
        else:
            Gui.Selection.addSelection(obj)


def _accept(app, panel):
    import FreeCADGui as Gui
    from capture_readme_dialogs import _settle

    Gui.Selection.clearSelection()
    if panel.accept() is False:
        raise RuntimeError(f"{type(panel).__name__}.accept() refused")
    Gui.Control.closeDialog()
    _settle(app, 300)


def _new_objects(doc, before):
    return [obj for obj in doc.Objects if obj.Name not in before]


def _face_towards(shape, direction):
    import Part

    best = None
    for index, face in enumerate(shape.Faces, 1):
        if not isinstance(face.Surface, Part.Plane):
            continue
        normal = face.normalAt(0, 0)
        if normal.getAngle(direction) < 1e-6 and (best is None or face.Area > best[1].Area):
            best = (f"Face{index}", face)
    if best is None:
        raise RuntimeError("no planar face found towards the requested direction")
    return best


def _paint_steel(doc):
    """Light steel color so the profiles stand out on the dark 3D background."""
    for obj in doc.Objects:
        if obj.TypeId == "Part::FeaturePython" and obj.ViewObject.Visibility:
            obj.ViewObject.ShapeColor = (0.72, 0.75, 0.80)


def _mdi():
    import FreeCADGui as Gui
    from PySide import QtWidgets

    return Gui.getMainWindow().findChild(QtWidgets.QMdiArea)


def storyboard(app, rec, scratch):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    import Sketcher  # noqa: F401  (registers the sketch type)
    from capture_readme_dialogs import _closed_wire, _settle

    from freecad.maxproframe.create_bom_tool import CreateBOMTaskPanel
    from freecad.maxproframe.create_end_miter_tool import EndMiterTaskPanel
    from freecad.maxproframe.create_extend_cut_tool import show_panel
    from freecad.maxproframe.create_extruded_cutout_tool import CutoutTaskPanel
    from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel

    view_params = App.ParamGet("User parameter:BaseApp/Preferences/View")
    view_params.SetBool("UseNavigationAnimations", True)
    view_params.SetInt("AnimationDuration", 900)

    Gui.activateWorkbench("MaxProFrame")
    _report("step: workbench active")
    doc = App.newDocument("Table")
    _settle(app, 500)
    _view().viewIsometric()

    _report("step: document ready")
    # 1. Title.
    rec.say("MaxProFrame", "Structural profile frames for FreeCAD")
    rec.hold(2.5)

    _report("step 2")
    # 2. Skeleton: a sketch for the table top and one line per leg.
    rec.say("Start from a skeleton", "A sketch for the top, lines for the legs")
    top = doc.addObject("Sketcher::SketchObject", "TopSketch")
    top.Placement = App.Placement(App.Vector(0, 0, TABLE_HEIGHT), App.Rotation())
    _closed_wire(top, [(0, 0), (TABLE_LENGTH, 0), (TABLE_LENGTH, TABLE_WIDTH), (0, TABLE_WIDTH)])
    doc.recompute()
    _animate(rec, "ViewFit", 1.2)
    legs = []
    for index, (x, y) in enumerate(((0, 0), (TABLE_LENGTH, 0), (TABLE_LENGTH, TABLE_WIDTH), (0, TABLE_WIDTH)), 1):
        leg = doc.addObject("Part::Line", f"Leg{index}")
        leg.X1, leg.Y1, leg.Z1 = x, y, 0
        leg.X2, leg.Y2, leg.Z2 = x, y, TABLE_HEIGHT
        legs.append(leg)
        doc.recompute()
        rec.hold(0.35)
    _animate(rec, "ViewFit", 1.2)

    _report("step 3")
    # 3. Create Profiles with the live preview.
    rec.say("Create Profiles", "Pick a material, family and size: the preview is live")
    Gui.Selection.clearSelection()
    before = {obj.Name for obj in doc.Objects}
    panel = CreateProfileTaskPanel()
    Gui.Selection.addObserver(panel)
    Gui.Control.showDialog(panel)
    rec.hold(0.8)
    for name in (f"Edge{index}" for index in range(1, 5)):
        Gui.Selection.addSelection(doc.Name, top.Name, name)
        rec.hold(0.25)
    for leg in legs:
        Gui.Selection.addSelection(doc.Name, leg.Name, "Edge1")
        rec.hold(0.25)
    panel.update_selection()
    form = panel.form_proxy
    # The profile choice applies to the rows selected in the edge list: select them all.
    panel.edge_list_widget.list_widget.selectAll()
    rec.hold(0.8)
    for combo, text in (
        (form.combo_material, "Metal"),
        (form.combo_family, "Square Hollow"),
        (form.combo_size, "40x2.0"),
    ):
        combo.setCurrentText(text)
        rec.hold(0.6)
        if combo.currentText() != text:
            items = [combo.itemText(i) for i in range(combo.count())]
            raise RuntimeError(f"combo has no {text!r}: {items}")
    panel.apply()
    rec.hold(2.5)
    Gui.Selection.removeObserver(panel)
    _accept(app, panel)
    profiles = [
        obj for obj in _new_objects(doc, before) if getattr(getattr(obj, "Proxy", None), "Type", "") == "Profile"
    ]
    if len(profiles) != 8:
        raise RuntimeError(f"expected 8 profiles, got {len(profiles)}")
    rails = [profile for profile in profiles if getattr(profile, "Target", None) and profile.Target[0] == top]
    _paint_steel(doc)
    rec.say("Create Profiles", "Eight profiles in one step")
    _orbit(rec, 2.5, 35)

    _report("step 4")
    # 4. End Miter on the four top corners.
    rec.say("End Miter", "Clean 45° corners with a live preview")
    panel = EndMiterTaskPanel(rails)
    Gui.Control.showDialog(panel)
    Gui.Selection.addObserver(panel)
    rec.hold(2.5)
    Gui.Selection.removeObserver(panel)
    _accept(app, panel)
    _paint_steel(doc)
    mitered = {rail.Name: doc.getObject(f"{rail.Name}_Mt") for rail in rails}
    if None in mitered.values():
        raise RuntimeError(f"missing mitered rails: {mitered}")
    _focus(rec, 1.8, App.Vector(TABLE_LENGTH, 0, TABLE_HEIGHT), 260)
    rec.hold(1.5)
    _focus(rec, 1.5, App.Vector(TABLE_LENGTH / 2, TABLE_WIDTH / 2, TABLE_HEIGHT / 2), 1900)

    _report("step 5")
    # 5. Cutout / Hole: face, sketch on the face, cut through one wall.
    rec.say("Cutout / Hole", "Pick a face, sketch the holes, cut one wall")
    front = mitered[min(rails, key=lambda rail: rail.Shape.BoundBox.YMax).Name]
    face_name, face = _face_towards(front.Shape, App.Vector(0, -1, 0))
    _select([front], [face_name])
    rec.hold(1.2)
    before = {obj.Name for obj in doc.Objects}
    panel = CutoutTaskPanel([(front, (face_name,))])
    show_panel(panel)
    rec.hold(1.5)
    _accept(app, panel)
    rec.hold(1.0)
    cut = next(obj for obj in _new_objects(doc, before) if hasattr(obj, "Sketch"))
    sketch = cut.Sketch
    center = sketch.Placement.inverse().multVec(face.CenterOfMass)
    for offset in (-300, 0, 300):
        sketch.addGeometry(Part.Circle(App.Vector(center.x + offset, center.y, 0), App.Vector(0, 0, 1), 8), False)
        doc.recompute()
        rec.hold(0.6)
    rec.hold(0.8)
    Gui.ActiveDocument.resetEdit()
    doc.recompute()
    _paint_steel(doc)
    _settle(app, 300)
    _view().viewIsometric()
    rec.hold(0.2)
    _animate(rec, "ViewFit", 1.0)
    _focus(rec, 1.8, face.CenterOfMass, 420)
    rec.hold(1.5)
    _animate(rec, "ViewFit", 1.5)

    _report("step 6")
    # 6. Cut list.
    rec.say("BOM and cut list", "Lengths and miter angles, ready for the workshop")
    finished = [obj for obj in doc.Objects if obj.ViewObject.Visibility and obj.TypeId == "Part::FeaturePython"]
    _select(finished)
    rec.hold(0.8)
    before = {obj.Name for obj in doc.Objects}
    panel = CreateBOMTaskPanel()
    Gui.Control.showDialog(panel)
    rec.hold(0.8)
    panel.form.cut_list_cb.setChecked(True)
    panel.form.group_profiles_cb.setChecked(True)
    rec.hold(1.2)
    _accept(app, panel)
    sheets = [obj for obj in _new_objects(doc, before) if obj.TypeId == "Spreadsheet::Sheet"]
    cut_list = next((sheet for sheet in sheets if sheet.Name.endswith("CutList")), sheets[0])
    model_window = _mdi().activeSubWindow()
    Gui.ActiveDocument.setEdit(cut_list)
    rec.hold(3.5)
    _mdi().setActiveSubWindow(model_window)
    _settle(app, 300)

    _report("step 7")
    # 7. Closing orbit.
    rec.say("MaxProFrame", "Free and open source, in the FreeCAD Addon Manager")
    _animate(rec, "ViewFit", 1.0)
    _orbit(rec, 4.0, 90)
    rec.hold(1.0)


# Inside FreeCAD this file runs as the copied macro; on the host it is the launcher.
if "FreeCAD" in sys.modules and os.environ.get(FRAMES_ENV):
    record()
elif __name__ == "__main__":
    raise SystemExit(launch())

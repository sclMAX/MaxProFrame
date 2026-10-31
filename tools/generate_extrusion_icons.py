"""Render the aluminium extrusion family thumbnails from the real section geometry.

Run with FreeCAD's command-line interpreter, for example:

    QT_QPA_PLATFORM=offscreen ../FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd tools/generate_extrusion_icons.py

The images follow the existing family thumbnails: 200x100, an extruded view on the
left with the highlighted end face and the flat section on the right, over the
background gradient sampled from an existing thumbnail.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "freecad", "maxproframe"))

import extrusions  # noqa: E402
from PySide import QtCore, QtGui  # noqa: E402

IMAGES = os.path.join(ROOT, "freecad", "maxproframe", "resources", "images", "profiles")
OUT_DIR = os.path.join(IMAGES, "Metal")
REFERENCE = os.path.join(OUT_DIR, "Square_Hollow.png")

FAMILIES = {
    "V-Slot": extrusions.vslot20x20,
    "T-Slot": extrusions.tslot20x20,
    "T-Slot_1-Slot": extrusions.tslot20x20_one_slot,
    "T-Slot_2-Slots": extrusions.tslot20x20_two_slot,
    "T-Slot_2-Slots_Opp": extrusions.tslot20x20_two_slot_opp,
    "T-Slot_3-Slots": extrusions.tslot20x20_three_slot,
}

WIDTH, HEIGHT = 200, 100
BODY = QtGui.QColor(175, 175, 178)
BODY_EDGE = QtGui.QColor(95, 95, 95)
END_FACE = QtGui.QColor(200, 200, 203)
HIGHLIGHT = QtGui.QColor(235, 205, 30)
SECTION_FILL = QtGui.QColor(225, 225, 225)
SECTION_EDGE = QtGui.QColor(70, 70, 70)


def section_path(face):
    """Return the face as a path in section units, y pointing down."""
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.OddEvenFill)
    for wire in face.Wires:
        points = wire.discretize(Deflection=0.005)
        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(p.x, -p.y) for p in points]))
        path.closeSubpath()
    return path


def fitted(path, center, size):
    """Scale and center the path in a square box of the given size."""
    box = path.boundingRect()
    scale = size / max(box.width(), box.height())
    transform = QtGui.QTransform()
    transform.translate(center.x(), center.y())
    transform.scale(scale, scale)
    transform.translate(-box.center().x(), -box.center().y())
    return transform.map(path)


def background(reference):
    """Copy the background gradient from the right edge column of a reference image."""
    image = QtGui.QImage(WIDTH, HEIGHT, QtGui.QImage.Format_ARGB32)
    for y in range(HEIGHT):
        color = reference.pixelColor(WIDTH - 1, y)
        for x in range(WIDTH):
            image.setPixelColor(x, y, color)
    return image


def render(face, reference):
    image = background(reference)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    path = section_path(face)

    # Extruded body: stack the section from the far end towards the end face.
    front = fitted(path, QtCore.QPointF(62, 58), 40)
    depth = QtCore.QPointF(-1.0, -0.55)
    steps = 140
    painter.setPen(QtCore.Qt.NoPen)
    for step in range(steps, 0, -1):
        shade = BODY.darker(100 + int(15 * step / steps))
        painter.setBrush(shade)
        painter.drawPath(front.translated(depth * (step * 0.5)))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.setPen(QtGui.QPen(BODY_EDGE, 0.6))
    painter.drawPath(front.translated(depth * 0.5))

    painter.setBrush(END_FACE)
    painter.setPen(QtGui.QPen(HIGHLIGHT, 1.6))
    painter.drawPath(front)

    # Flat section.
    painter.setBrush(SECTION_FILL)
    painter.setPen(QtGui.QPen(SECTION_EDGE, 1.0))
    painter.drawPath(fitted(path, QtCore.QPointF(150, 50), 80))
    painter.end()
    return image


def main():
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["generate_extrusion_icons"])
    reference = QtGui.QImage(REFERENCE)
    if reference.isNull():
        raise SystemExit(f"Reference thumbnail not found: {REFERENCE}")
    for name, build in FAMILIES.items():
        target = os.path.join(OUT_DIR, f"{name}.png")
        if not render(build(), reference).save(target):
            raise SystemExit(f"Could not write {target}")
        print(f"wrote {target}")
    del app


main()

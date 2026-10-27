import math
import os
import unittest
from unittest.mock import patch

import FreeCAD as App
import Part
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.alignment_widget import AlignmentWidget


class _Mouse:
    @staticmethod
    def mouseClick(widget, button, modifiers, point):
        for kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            event = QtGui.QMouseEvent(kind, QtCore.QPointF(point), button, button, modifiers)
            QtWidgets.QApplication.sendEvent(widget, event)


class TestAlignmentWidget(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        self.widget = AlignmentWidget()
        self.addCleanup(self.widget.close)
        self.widget.resize(280, 240)
        outer = Part.makePolygon(
            [App.Vector(x, y, 0) for x, y in ((37, -23), (77, -23), (77, -3), (37, -3), (37, -23))]
        )
        hole = Part.Wire([Part.makeCircle(3, App.Vector(47, -13, 0))])
        self.face = Part.makeFace([outer, hole], "Part::FaceMakerBullseye")
        self.before = self.face.exportBrepToString()
        self.widget.set_section(self.face)
        self.widget.show()
        self.app.processEvents()

    def test_public_clicks_select_exactly_one_of_nine_stable_ids(self):
        clicks = []
        self.widget.anchorClicked.connect(lambda x, y: clicks.append((x, y)))
        for angle in (0, 37, 90, 180, 270):
            for mh, mv in ((False, False), (True, False), (False, True), (True, True)):
                self.widget.set_state((1, 1), angle, mh, mv)
                for ax in range(3):
                    for ay in range(3):
                        point = self.widget.anchor_position(ax, ay)
                        _Mouse.mouseClick(self.widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point.toPoint())
                        self.assertEqual(clicks[-1], (ax, ay))
                        self.assertEqual(self.widget.selected_anchor, (ax, ay))
        self.assertEqual(len(clicks), 180)
        selected = self.widget.anchor_position(2, 2).toPoint()
        self.assertEqual(
            self.widget.grab().toImage().pixelColor(selected), self.widget.palette().color(QtGui.QPalette.Highlight)
        )
        _Mouse.mouseClick(self.widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(1, 1))
        self.assertEqual(len(clicks), 180)
        self.assertEqual(self.face.exportBrepToString(), self.before)

    def test_geometry_and_anchor_transforms_match_model_bbox_semantics(self):
        self.widget.set_state((2, 0), 37, False, False)
        baseline = self.widget.anchor_position(0, 0)
        for mh, mv in ((True, False), (False, True), (True, True)):
            self.widget.set_state((2, 0), 37, mh, mv)
            self.assertEqual(self.widget.anchor_position(0, 0), baseline)
        # A positive local X direction rotates counterclockwise on screen.
        delta = self.widget.anchor_position(2, 1) - self.widget.anchor_position(0, 1)
        self.assertGreater(delta.x(), 0)
        self.assertLess(delta.y(), 0)
        self.assertAlmostEqual(-delta.y() / delta.x(), math.tan(math.radians(37)), places=5)
        self.widget.set_state((1, 1), 0, False, False)
        image = self.widget.grab().toImage()
        hole = self.widget.section_position(47, -13).toPoint()
        solid = self.widget.section_position(67, -13).toPoint()
        self.assertNotEqual(image.pixelColor(hole), image.pixelColor(solid))
        for mh, mv in ((True, False), (False, True), (True, True)):
            self.widget.set_state((1, 1), 37, mh, mv)
            image = self.widget.grab().toImage()
            hole = self.widget.section_position(47, -13).toPoint()
            solid = self.widget.section_position(67, -13).toPoint()
            self.assertNotEqual(image.pixelColor(hole), image.pixelColor(solid))

    def test_paint_click_resize_do_not_load_geometry_or_mutate_documents(self):
        documents = tuple(App.listDocuments())
        with (
            patch.object(App, "newDocument", side_effect=AssertionError("document creation")),
            patch.object(App, "openDocument", side_effect=AssertionError("catalog loading")),
        ):
            self.widget.resize(360, 220)
            self.widget.grab()
            _Mouse.mouseClick(
                self.widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, self.widget.anchor_position(2, 2).toPoint()
            )
        self.assertEqual(tuple(App.listDocuments()), documents)
        self.widget.set_section(None)
        self.assertIsNone(self.widget.anchor_position(0, 0))
        if os.environ.get("FF_REPORTS"):
            self.widget.set_section(self.face)
            for angle in (0, 37, 90):
                self.widget.set_state((2, 0), angle, True, False)
                self.assertTrue(
                    self.widget.grab().save(os.path.join(os.environ["FF_REPORTS"], "alignment-%s.png" % angle))
                )

    def test_keyboard_arrow_navigation_selects_anchors(self):
        self.widget.set_state((1, 1))
        clicks = []
        self.widget.anchorClicked.connect(lambda x, y: clicks.append((x, y)))

        def press(key):
            event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(self.widget, event)

        press(QtCore.Qt.Key_Right)
        self.assertEqual(self.widget.selected_anchor, (2, 1))
        self.assertEqual(clicks[-1], (2, 1))

        press(QtCore.Qt.Key_Up)
        self.assertEqual(self.widget.selected_anchor, (2, 2))
        self.assertEqual(clicks[-1], (2, 2))

        press(QtCore.Qt.Key_Left)
        self.assertEqual(self.widget.selected_anchor, (1, 2))
        self.assertEqual(clicks[-1], (1, 2))

        press(QtCore.Qt.Key_Down)
        self.assertEqual(self.widget.selected_anchor, (1, 1))
        self.assertEqual(clicks[-1], (1, 1))

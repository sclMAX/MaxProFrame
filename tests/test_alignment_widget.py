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

    def test_edge_marker_stays_in_the_edge_frame(self):
        self.widget.set_state((2, 0), 0, False, False)
        self.assertEqual(self.widget.offset, (0.0, 0.0))
        self.assertEqual(self.widget.edge_position(), self.widget.anchor_position(2, 0))

        def direction():
            delta = self.widget.edge_position() - self.widget.anchor_position(*self.widget.selected_anchor)
            length = math.hypot(delta.x(), delta.y())
            return (delta.x() / length, delta.y() / length)

        # The section moves by +offset, so the edge lies at -offset from the anchor.
        self.widget.set_offset((10, 5))
        delta = self.widget.edge_position() - self.widget.anchor_position(2, 0)
        self.assertLess(delta.x(), 0)
        self.assertGreater(delta.y(), 0)
        self.assertAlmostEqual(abs(delta.x()), 2 * abs(delta.y()), places=5)
        baseline = direction()
        for angle in (37, 90, 180):
            for mh, mv in ((False, False), (True, False), (False, True), (True, True)):
                self.widget.set_state((2, 0), angle, mh, mv)
                for actual, expected in zip(direction(), baseline):
                    self.assertAlmostEqual(actual, expected, places=5)
        self.widget.grab()

    def test_large_offset_keeps_edge_inside_and_unknown_offset_hides_it(self):
        for anchor in ((0, 0), (1, 1), (2, 2)):
            for offset in ((500, 0), (0, -500), (-500, 500)):
                self.widget.set_state(anchor, 90, True, False)
                self.widget.set_offset(offset)
                edge = self.widget.edge_position()
                self.assertTrue(QtCore.QRectF(self.widget.rect()).contains(edge), (anchor, offset, edge))
                for ax in range(3):
                    for ay in range(3):
                        point = self.widget.anchor_position(ax, ay)
                        self.assertTrue(QtCore.QRectF(self.widget.rect()).contains(point))
        self.widget.set_offset(None)
        self.assertIsNone(self.widget.offset)
        self.assertIsNone(self.widget.edge_position())
        self.widget.grab()
        self.widget.set_offset((3, 4))
        self.widget.set_state(None)
        self.assertIsNone(self.widget.edge_position())
        self.widget.set_section(None)
        self.assertIsNone(self.widget.edge_position())

    def test_large_offset_keeps_section_readable_and_clips_the_marker(self):
        def span():
            delta = self.widget.anchor_position(2, 1) - self.widget.anchor_position(0, 1)
            return math.hypot(delta.x(), delta.y())

        def direction():
            delta = self.widget.edge_position() - self.widget.anchor_position(*self.widget.selected_anchor)
            length = math.hypot(delta.x(), delta.y())
            return (delta.x() / length, delta.y() / length)

        for angle in (0, 90):
            self.widget.set_state((1, 1), angle, False, False)
            self.widget.set_offset((0, 0))
            full = span()
            self.widget.set_offset((10, 5))
            self.assertFalse(self.widget.edge_clipped())
            self.assertIsNone(self.widget.edge_label())
            near = direction()
            self.widget.set_offset((500, 250))
            # The section never shrinks below half of its offset-free size.
            self.assertGreaterEqual(span(), full / 2 - 1e-6)
            self.assertTrue(self.widget.edge_clipped())
            self.assertTrue(QtCore.QRectF(self.widget.rect()).contains(self.widget.edge_position()))
            for actual, expected in zip(direction(), near):
                self.assertAlmostEqual(actual, expected, places=5)
            # The label repeats the typed X/Y values, never a derived diagonal distance.
            self.assertEqual(self.widget.edge_label(), "X 500 \u00b7 Y 250 mm")
            self.widget.grab()
        self.widget.set_state((1, 1), 0, False, False)
        point = QtCore.QLocale().decimalPoint()
        for offset, label in (
            ((0, -500), "Y -500 mm"),
            ((-400, 0), "X -400 mm"),
            ((12.5, 600), "X 12%s5 \u00b7 Y 600 mm" % point),
        ):
            self.widget.set_offset(offset)
            self.assertTrue(self.widget.edge_clipped(), offset)
            self.assertEqual(self.widget.edge_label(), label)
        self.widget.set_offset(None)
        self.assertFalse(self.widget.edge_clipped())
        self.assertIsNone(self.widget.edge_label())

    def test_edge_marker_color_follows_theme_with_readable_contrast(self):
        def themed(base, text, highlight):
            palette = QtGui.QPalette(self.widget.palette())
            for role, color in (
                (QtGui.QPalette.Base, base),
                (QtGui.QPalette.Text, text),
                (QtGui.QPalette.Highlight, highlight),
            ):
                palette.setColor(role, QtGui.QColor(color))
            # A FreeCAD theme switch reaches the widget as a palette change, not a stylesheet.
            self.widget.setPalette(palette)
            self.widget.set_offset((500, 250))
            self.widget.grab()
            return self.widget.marker_color()

        # Dark theme whose highlight barely differs from the base: fall back to the text color.
        self.assertEqual(themed("#232323", "#e6e6e6", "#1d4466"), QtGui.QColor("#e6e6e6"))
        # Light theme with a readable highlight: keep the theme accent.
        self.assertEqual(themed("#ffffff", "#1a1a1a", "#1f5fbf"), QtGui.QColor("#1f5fbf"))
        self.assertEqual(self.widget.styleSheet(), "")

    def test_anchor_clicks_still_select_nine_ids_with_an_offset(self):
        clicks = []
        self.widget.anchorClicked.connect(lambda x, y: clicks.append((x, y)))
        self.widget.set_offset((600, -400))
        for angle in (0, 90):
            self.widget.set_state((1, 1), angle, False, True)
            for ax in range(3):
                for ay in range(3):
                    point = self.widget.anchor_position(ax, ay)
                    _Mouse.mouseClick(self.widget, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point.toPoint())
                    self.assertEqual(clicks[-1], (ax, ay))
                    self.assertEqual(self.widget.selected_anchor, (ax, ay))
        self.assertEqual(len(clicks), 18)

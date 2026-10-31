"""Cached 2D silhouette with stable bbox anchors; no modeling in paint/click."""

import math

from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.custom_profile_cards import face_silhouette_path
from freecad.maxproframe.ff_tools import translate


class AlignmentWidget(QtWidgets.QWidget):
    anchorClicked = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("alignment_widget")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMinimumSize(160, 160)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setAccessibleName(translate("frameforge", "Section alignment"))
        self.setToolTip(
            translate("frameforge", "Click a section bounding-box anchor to align profile (or use arrow keys).")
        )
        self._path = QtGui.QPainterPath()
        self._bounds = QtCore.QRectF()
        self.selected_anchor = (1, 1)
        self.rotation = 0.0
        self.mirrors = (False, False)
        self.offset = (0.0, 0.0)

    def sizeHint(self):
        return QtCore.QSize(220, 180)

    @property
    def section_bounds(self):
        return QtCore.QRectF(self._bounds)

    def set_section(self, face):
        self._path = face_silhouette_path(face)
        if face is not None and not self._path.isEmpty():
            box = face.optimalBoundingBox(False)
            self._bounds = QtCore.QRectF(box.XMin, box.YMin, box.XLength, box.YLength)
        else:
            self._bounds = QtCore.QRectF()
        self.update()

    def set_state(self, anchor, rotation=0.0, mirror_h=False, mirror_v=False):
        self.selected_anchor = tuple(anchor) if anchor is not None else None
        self.rotation = float(rotation) if math.isfinite(float(rotation)) else 0.0
        self.mirrors = (bool(mirror_h), bool(mirror_v))
        self.update()

    def set_offset(self, offset):
        """Set the edge-frame (x, y) displacement; None means unknown (mixed)."""
        self.offset = (float(offset[0]), float(offset[1])) if offset is not None else None
        self.update()

    def _edge_from_center(self):
        """Edge point in edge-frame units relative to the section center, or None."""
        if self._bounds.isEmpty() or self.selected_anchor is None or self.offset is None:
            return None
        ax, ay = self.selected_anchor
        anchor = (
            QtGui.QTransform()
            .rotate(self.rotation)
            .map(QtCore.QPointF(self._bounds.width() * (ax - 1) / 2.0, self._bounds.height() * (ay - 1) / 2.0))
        )
        # The section is displaced by +offset from the edge.
        return anchor - QtCore.QPointF(*self.offset)

    def _fit_scale(self, half_w, half_h):
        return min(
            max(1, self.width() - 32) / max(2 * half_w, 1e-6),
            max(1, self.height() - 32) / max(2 * half_h, 1e-6),
        )

    def _view_transform(self):
        center = self._bounds.center()
        rotation = QtGui.QTransform().rotate(self.rotation)
        rotated = rotation.mapRect(self._bounds)
        half_w, half_h = rotated.width() / 2.0, rotated.height() / 2.0
        scale = self._fit_scale(half_w, half_h)
        edge = self._edge_from_center()
        if edge is not None:
            # Keep the view centered on the section while fitting the edge marker, but never
            # shrink the section below half its own fit; a farther edge is clipped to the border.
            fitted = self._fit_scale(max(half_w, abs(edge.x())), max(half_h, abs(edge.y())))
            scale = max(fitted, scale / 2.0)
        transform = QtGui.QTransform()
        transform.translate(self.width() / 2.0, self.height() / 2.0)
        transform.scale(scale, -scale)
        transform.rotate(self.rotation)
        transform.translate(-center.x(), -center.y())
        return transform

    def _section_transform(self):
        transform = self._view_transform()
        center = self._bounds.center()
        transform.translate(center.x(), center.y())
        transform.scale(-1 if self.mirrors[0] else 1, -1 if self.mirrors[1] else 1)
        transform.translate(-center.x(), -center.y())
        return transform

    def section_position(self, x, y):
        return self._section_transform().map(QtCore.QPointF(x, y))

    def anchor_position(self, ax, ay):
        if self._bounds.isEmpty():
            return None
        # Model mirrors the section about its bbox center AFTER anchor translation.
        # Thus MirrorH/V change the silhouette, not the local bbox anchor IDs.
        return self._view_transform().map(
            QtCore.QPointF(
                self._bounds.left() + self._bounds.width() * ax / 2.0,
                self._bounds.top() + self._bounds.height() * ay / 2.0,
            )
        )

    def _edge_marker(self):
        """(view position, clipped) of the path edge, or None when it is unknown."""
        edge = self._edge_from_center()
        if edge is None:
            return None
        ax, ay = self.selected_anchor
        anchor = self.anchor_position(ax, ay)
        transform = self._view_transform()
        scale = math.hypot(transform.m11(), transform.m12())
        dx, dy = self.offset
        # Edge-frame axes: +X right, +Y up (the view flips Y).
        delta = QtCore.QPointF(-scale * dx, scale * dy)
        inner = QtCore.QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if inner.contains(anchor + delta):
            return anchor + delta, False
        # Keep the direction and stop where the ray from the anchor leaves the inner border.
        limits = []
        if delta.x():
            limits.append(((inner.right() if delta.x() > 0 else inner.left()) - anchor.x()) / delta.x())
        if delta.y():
            limits.append(((inner.bottom() if delta.y() > 0 else inner.top()) - anchor.y()) / delta.y())
        return anchor + delta * max(0.0, min(limits)), True

    def edge_position(self):
        """View position of the path edge (clipped to the view), or None when it is unknown."""
        marker = self._edge_marker()
        return marker[0] if marker is not None else None

    def edge_clipped(self):
        """Whether the edge lies beyond the view and its marker sits on the border."""
        marker = self._edge_marker()
        return marker is not None and marker[1]

    def edge_label(self):
        """Typed X/Y offset shown next to a clipped marker (zero axes omitted), or None."""
        if not self.edge_clipped():
            return None
        locale = QtCore.QLocale()
        parts = [
            "%s %s" % (axis, locale.toString(float(value), "g", 6)) for axis, value in zip("XY", self.offset) if value
        ]
        return " · ".join(parts) + " mm"

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and not self._bounds.isEmpty():
            candidates = []
            for ax in range(3):
                for ay in range(3):
                    delta = self.anchor_position(ax, ay) - QtCore.QPointF(event.pos())
                    candidates.append((delta.x() ** 2 + delta.y() ** 2, ax, ay))
            distance, ax, ay = min(candidates)
            if distance <= 100:
                self.selected_anchor = (ax, ay)
                self.update()
                self.anchorClicked.emit(ax, ay)
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        ax, ay = self.selected_anchor if self.selected_anchor is not None else (1, 1)
        if key == QtCore.Qt.Key_Left:
            ax = max(0, ax - 1)
        elif key == QtCore.Qt.Key_Right:
            ax = min(2, ax + 1)
        elif key == QtCore.Qt.Key_Up:
            ay = min(2, ay + 1)
        elif key == QtCore.Qt.Key_Down:
            ay = max(0, ay - 1)
        else:
            super().keyPressEvent(event)
            return
        if (ax, ay) != self.selected_anchor:
            self.selected_anchor = (ax, ay)
            self.update()
            self.anchorClicked.emit(ax, ay)
        event.accept()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.brush(QtGui.QPalette.Base))
        if self._bounds.isEmpty():
            painter.setPen(palette.color(QtGui.QPalette.Text))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, translate("frameforge", "No Preview"))
        else:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(palette.brush(QtGui.QPalette.Text))
            painter.drawPath(self._section_transform().map(self._path))
            for ax in range(3):
                for ay in range(3):
                    selected = self.selected_anchor == (ax, ay)
                    painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.Text), 1.5))
                    painter.setBrush(palette.brush(QtGui.QPalette.Highlight if selected else QtGui.QPalette.Base))
                    painter.drawEllipse(self.anchor_position(ax, ay), 6 if selected else 4, 6 if selected else 4)
            marker = self._edge_marker()
            if marker is not None and self.offset != (0.0, 0.0):
                self._paint_edge_marker(painter, palette, *marker)
        painter.end()

    def marker_color(self):
        """Theme accent for the edge marker, or the text color when the accent is unreadable on the base."""
        palette = self.palette()
        base = palette.color(QtGui.QPalette.Base)
        highlight = palette.color(QtGui.QPalette.Highlight)
        # WCAG minimum contrast for graphical objects; Text on Base is the theme's own readable pair.
        if _contrast_ratio(highlight, base) >= 3.0:
            return highlight
        return palette.color(QtGui.QPalette.Text)

    def _paint_edge_marker(self, painter, palette, edge, clipped):
        highlight = self.marker_color()
        anchor = self.anchor_position(*self.selected_anchor)
        painter.setPen(QtGui.QPen(highlight, 1.5, QtCore.Qt.DashLine))
        painter.drawLine(anchor, edge)
        painter.setPen(QtGui.QPen(highlight, 2))
        painter.setBrush(QtCore.Qt.NoBrush)
        if not clipped:
            painter.drawEllipse(edge, 5, 5)
            painter.drawLine(edge - QtCore.QPointF(8, 0), edge + QtCore.QPointF(8, 0))
            painter.drawLine(edge - QtCore.QPointF(0, 8), edge + QtCore.QPointF(0, 8))
            return
        # Off-view edge: an arrow on the border pointing at it, labelled with the real distance.
        angle = math.atan2(edge.y() - anchor.y(), edge.x() - anchor.x())
        for side in (-0.45, 0.45):
            tip = QtCore.QPointF(math.cos(angle + math.pi + side), math.sin(angle + math.pi + side)) * 10
            painter.drawLine(edge, edge + tip)
        text = self.edge_label()
        metrics = painter.fontMetrics()
        box = QtCore.QRectF(metrics.boundingRect(text)).adjusted(-3, -1, 3, 1)
        # Beside the arrow, on the border strip, so it never covers the section or its anchors.
        side = QtCore.QPointF(-math.sin(angle), math.cos(angle))
        to_center = QtCore.QRectF(self.rect()).center() - edge
        if side.x() * to_center.x() + side.y() * to_center.y() < 0:
            side = -side
        gap = abs(side.x()) * box.width() / 2 + abs(side.y()) * box.height() / 2 + 8
        box.moveCenter(edge + side * gap)
        bounds = QtCore.QRectF(self.rect()).adjusted(2, 2, -2, -2)
        box.moveLeft(min(max(box.left(), bounds.left()), bounds.right() - box.width()))
        box.moveTop(min(max(box.top(), bounds.top()), bounds.bottom() - box.height()))
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(palette.brush(QtGui.QPalette.Base))
        painter.drawRect(box)
        painter.setPen(palette.color(QtGui.QPalette.Text))
        painter.drawText(box, QtCore.Qt.AlignCenter, text)


def _relative_luminance(color):
    def channel(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF())


def _contrast_ratio(first, second):
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)

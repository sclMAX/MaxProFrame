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

    def _view_transform(self):
        center = self._bounds.center()
        rotation = QtGui.QTransform().rotate(self.rotation)
        rotated = rotation.mapRect(self._bounds)
        half_w, half_h = rotated.width() / 2.0, rotated.height() / 2.0
        edge = self._edge_from_center()
        if edge is not None:
            # Keep the view centered on the section while fitting the edge marker.
            half_w, half_h = max(half_w, abs(edge.x())), max(half_h, abs(edge.y()))
        scale = min(
            max(1, self.width() - 32) / max(2 * half_w, 1e-6),
            max(1, self.height() - 32) / max(2 * half_h, 1e-6),
        )
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

    def edge_position(self):
        """View position of the path edge, or None when it is unknown."""
        edge = self._edge_from_center()
        if edge is None:
            return None
        ax, ay = self.selected_anchor
        anchor = self.anchor_position(ax, ay)
        transform = self._view_transform()
        scale = math.hypot(transform.m11(), transform.m12())
        dx, dy = self.offset
        # Edge-frame axes: +X right, +Y up (the view flips Y).
        return anchor + QtCore.QPointF(-scale * dx, scale * dy)

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
            edge = self.edge_position()
            if edge is not None and self.offset != (0.0, 0.0):
                highlight = palette.color(QtGui.QPalette.Highlight)
                painter.setPen(QtGui.QPen(highlight, 1.5, QtCore.Qt.DashLine))
                painter.drawLine(self.anchor_position(*self.selected_anchor), edge)
                painter.setPen(QtGui.QPen(highlight, 2))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawEllipse(edge, 5, 5)
                painter.drawLine(edge - QtCore.QPointF(8, 0), edge + QtCore.QPointF(8, 0))
                painter.drawLine(edge - QtCore.QPointF(0, 8), edge + QtCore.QPointF(0, 8))
        painter.end()

# -*- coding: utf-8 -*-
"""Custom UI widgets and icons for MaxProFrame task panels.

Implements collapsible accordion headers, vector icons for mirroring and
extension, segmented placement mode switches, and edge list management.
"""

from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.ff_tools import translate


def _render_icon(draw_fn, size=16):
    """Render a QIcon with Normal/Off and Normal/On pixmaps."""
    icon = QtGui.QIcon()

    # Off / Unchecked pixmap (neutral silver)
    pix_off = QtGui.QPixmap(size, size)
    pix_off.fill(QtCore.Qt.transparent)
    p_off = QtGui.QPainter(pix_off)
    p_off.setRenderHint(QtGui.QPainter.Antialiasing, True)
    draw_fn(p_off, size, QtGui.QColor(185, 185, 185))
    p_off.end()
    icon.addPixmap(pix_off, QtGui.QIcon.Normal, QtGui.QIcon.Off)

    # On / Checked pixmap (crisp bright white)
    pix_on = QtGui.QPixmap(size, size)
    pix_on.fill(QtCore.Qt.transparent)
    p_on = QtGui.QPainter(pix_on)
    p_on.setRenderHint(QtGui.QPainter.Antialiasing, True)
    draw_fn(p_on, size, QtGui.QColor(255, 255, 255))
    p_on.end()
    icon.addPixmap(pix_on, QtGui.QIcon.Normal, QtGui.QIcon.On)

    return icon


def _draw_mirror_h(painter, size, color):
    """Draw horizontal mirror symmetry icon."""
    cx = size / 2.0
    pen_dash = QtGui.QPen(color, 1.2, QtCore.Qt.DashLine)
    painter.setPen(pen_dash)
    painter.drawLine(QtCore.QPointF(cx, 2), QtCore.QPointF(cx, size - 2))

    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(color))

    # Left triangle pointing left
    poly_left = QtGui.QPolygonF(
        [
            QtCore.QPointF(cx - 2.0, 4.0),
            QtCore.QPointF(2.0, size / 2.0),
            QtCore.QPointF(cx - 2.0, size - 4.0),
        ]
    )
    painter.drawPolygon(poly_left)

    # Right triangle pointing right
    poly_right = QtGui.QPolygonF(
        [
            QtCore.QPointF(cx + 2.0, 4.0),
            QtCore.QPointF(size - 2.0, size / 2.0),
            QtCore.QPointF(cx + 2.0, size - 4.0),
        ]
    )
    painter.drawPolygon(poly_right)


def _draw_mirror_v(painter, size, color):
    """Draw vertical mirror symmetry icon."""
    cy = size / 2.0
    pen_dash = QtGui.QPen(color, 1.2, QtCore.Qt.DashLine)
    painter.setPen(pen_dash)
    painter.drawLine(QtCore.QPointF(2, cy), QtCore.QPointF(size - 2, cy))

    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(color))

    # Top triangle pointing up
    poly_top = QtGui.QPolygonF(
        [
            QtCore.QPointF(4.0, cy - 2.0),
            QtCore.QPointF(size / 2.0, 2.0),
            QtCore.QPointF(size - 4.0, cy - 2.0),
        ]
    )
    painter.drawPolygon(poly_top)

    # Bottom triangle pointing down
    poly_bot = QtGui.QPolygonF(
        [
            QtCore.QPointF(4.0, cy + 2.0),
            QtCore.QPointF(size / 2.0, size - 2.0),
            QtCore.QPointF(size - 4.0, cy + 2.0),
        ]
    )
    painter.drawPolygon(poly_bot)


def _draw_pre_extend(painter, size, color):
    """Draw linear edge pre-extension icon."""
    cy = size / 2.0
    pen_main = QtGui.QPen(color, 1.5, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
    painter.setPen(pen_main)
    # Main horizontal segment
    painter.drawLine(QtCore.QPointF(4.0, cy), QtCore.QPointF(size - 4.0, cy))

    # Boundary vertical dashed lines
    pen_bound = QtGui.QPen(color, 1.0, QtCore.Qt.DotLine)
    painter.setPen(pen_bound)
    painter.drawLine(QtCore.QPointF(2.0, 3.0), QtCore.QPointF(2.0, size - 3.0))
    painter.drawLine(QtCore.QPointF(size - 2.0, 3.0), QtCore.QPointF(size - 2.0, size - 3.0))

    # Outward arrow heads
    painter.setPen(pen_main)
    painter.drawLine(QtCore.QPointF(4.0, cy), QtCore.QPointF(6.5, cy - 2.5))
    painter.drawLine(QtCore.QPointF(4.0, cy), QtCore.QPointF(6.5, cy + 2.5))
    painter.drawLine(QtCore.QPointF(size - 4.0, cy), QtCore.QPointF(size - 6.5, cy - 2.5))
    painter.drawLine(QtCore.QPointF(size - 4.0, cy), QtCore.QPointF(size - 6.5, cy + 2.5))


def _draw_profile_section(painter, size, color):
    """Draw small profile section icon."""
    pen = QtGui.QPen(color, 1.4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    path = QtGui.QPainterPath()
    path.moveTo(size - 3.0, 3.0)
    path.lineTo(3.5, 3.0)
    path.lineTo(3.5, size - 3.0)
    path.lineTo(size - 3.0, size - 3.0)
    painter.drawPath(path)


def _draw_placement_target(painter, size, color):
    """Draw placement crosshair icon."""
    cx = size / 2.0
    cy = size / 2.0
    r = size / 2.0 - 2.5
    pen = QtGui.QPen(color, 1.3, QtCore.Qt.SolidLine)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)
    painter.drawLine(QtCore.QPointF(cx, 1.0), QtCore.QPointF(cx, 4.0))
    painter.drawLine(QtCore.QPointF(cx, size - 4.0), QtCore.QPointF(cx, size - 1.0))
    painter.drawLine(QtCore.QPointF(1.0, cy), QtCore.QPointF(4.0, cy))
    painter.drawLine(QtCore.QPointF(size - 4.0, cy), QtCore.QPointF(size - 1.0, cy))


def _draw_advanced_gear(painter, size, color):
    """Draw gear/options icon."""
    cx = size / 2.0
    cy = size / 2.0
    r_outer = size / 2.0 - 2.0
    r_inner = r_outer - 2.0
    pen = QtGui.QPen(color, 1.3, QtCore.Qt.SolidLine)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(QtCore.QPointF(cx, cy), r_outer, r_outer)
    painter.drawEllipse(QtCore.QPointF(cx, cy), r_inner, r_inner)


def create_mirror_h_icon(size=16):
    return _render_icon(_draw_mirror_h, size)


def create_mirror_v_icon(size=16):
    return _render_icon(_draw_mirror_v, size)


def create_pre_extend_icon(size=16):
    return _render_icon(_draw_pre_extend, size)


def create_profile_section_icon(size=16):
    return _render_icon(_draw_profile_section, size)


def create_placement_icon(size=16):
    return _render_icon(_draw_placement_target, size)


def create_advanced_icon(size=16):
    return _render_icon(_draw_advanced_gear, size)


class SectionHeaderButton(QtWidgets.QToolButton):
    """Collapsible accordion header button with icon, arrow, and title."""

    def __init__(self, title, icon=None, target_widget=None, parent=None, expanded=True):
        super().__init__(parent)
        self.target_widget = target_widget
        self.setText(f" {title}")
        if icon is not None:
            self.setIcon(icon)
        self.setCheckable(True)
        self.setChecked(expanded)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.toggled.connect(self._on_toggled)
        if target_widget is not None:
            target_widget.setVisible(expanded)

    def _on_toggled(self, checked):
        self.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        if self.target_widget is not None:
            self.target_widget.setVisible(checked)


class ModeSwitchWidget(QtWidgets.QWidget):
    """Segmented mode switch between Uniform (all edges) and Individual (per edge)."""

    modeChanged = QtCore.Signal(bool)  # True if per-edge, False if uniform

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_per_edge = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setSpacing(2)

        self.btn_uniform = QtWidgets.QToolButton(self)
        self.btn_uniform.setText(translate("frameforge", "Uniform"))
        self.btn_uniform.setCheckable(True)
        self.btn_uniform.setChecked(True)
        self.btn_uniform.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_per_edge = QtWidgets.QToolButton(self)
        self.btn_per_edge.setText(translate("frameforge", "Per edge"))
        self.btn_per_edge.setCheckable(True)
        self.btn_per_edge.setChecked(False)
        self.btn_per_edge.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.addButton(self.btn_uniform, 0)
        self.group.addButton(self.btn_per_edge, 1)

        layout.addWidget(self.btn_uniform)
        layout.addWidget(self.btn_per_edge)

        self.group.buttonClicked.connect(self._on_button_clicked)

    def is_per_edge(self):
        return self.btn_per_edge.isChecked()

    def set_per_edge(self, per_edge):
        if per_edge:
            self.btn_per_edge.setChecked(True)
        else:
            self.btn_uniform.setChecked(True)
        self._is_per_edge = per_edge
        self.modeChanged.emit(per_edge)

    def _on_button_clicked(self, btn):
        per_edge = btn == self.btn_per_edge
        if per_edge != self._is_per_edge:
            self._is_per_edge = per_edge
            self.modeChanged.emit(per_edge)


class EdgeItemWidget(QtWidgets.QWidget):
    """Item row in EdgeListWidget with name, settings badge, and remove button."""

    removeClicked = QtCore.Signal(object)  # emits edge_key

    def __init__(self, edge_key, display_name, parent=None):
        super().__init__(parent)
        self.edge_key = edge_key
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.lbl_name = QtWidgets.QLabel(f"• {display_name}", self)
        layout.addWidget(self.lbl_name, 1)

        self.lbl_badge = QtWidgets.QLabel("0°", self)
        f_badge = self.lbl_badge.font()
        f_badge.setBold(True)
        self.lbl_badge.setFont(f_badge)
        layout.addWidget(self.lbl_badge)

        self.btn_remove = QtWidgets.QToolButton(self)
        self.btn_remove.setText("×")
        self.btn_remove.setToolTip(translate("frameforge", "Remove edge"))
        self.btn_remove.setFixedSize(18, 18)
        self.btn_remove.clicked.connect(lambda: self.removeClicked.emit(self.edge_key))
        layout.addWidget(self.btn_remove)

    def update_badge(self, rotation, mirror_h, mirror_v):
        parts = [f"{float(rotation):g}°"]
        if mirror_h:
            parts.append(translate("frameforge", "Mirror H"))
        if mirror_v:
            parts.append(translate("frameforge", "Mirror V"))
        self.lbl_badge.setText(" · ".join(parts))


class EdgeListWidget(QtWidgets.QWidget):
    """Scrollable list of edges with badges, selection handling, and reset button."""

    edgeSelected = QtCore.Signal(object)  # emits edge_key
    edgeRemoved = QtCore.Signal(object)  # emits edge_key
    selectionChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = {}  # edge_key -> (QListWidgetItem, EdgeItemWidget)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar row
        tb_layout = QtWidgets.QHBoxLayout()
        tb_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = QtWidgets.QLabel(translate("frameforge", "Selected edges:"), self)
        f_title = self.lbl_title.font()
        f_title.setBold(True)
        self.lbl_title.setFont(f_title)
        tb_layout.addWidget(self.lbl_title)
        tb_layout.addStretch()

        layout.addLayout(tb_layout)

        # List widget
        self.list_widget = QtWidgets.QListWidget(self)
        self.list_widget.setMaximumHeight(115)
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemSelectionChanged.connect(self.selectionChanged.emit)
        layout.addWidget(self.list_widget)

    def set_edges(self, edges_list):
        """Update items based on list of (edge_key, display_name) tuples."""
        current_keys = set(self._items.keys())
        new_keys = {k for k, _ in edges_list}

        # Remove keys no longer present
        for k in current_keys - new_keys:
            item, _ = self._items.pop(k)
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)

        # Add or update keys
        for edge_key, display_name in edges_list:
            if edge_key not in self._items:
                item = QtWidgets.QListWidgetItem(self.list_widget)
                item.setData(QtCore.Qt.UserRole, edge_key)
                widget = EdgeItemWidget(edge_key, display_name, self)
                widget.removeClicked.connect(self.edgeRemoved.emit)
                item.setSizeHint(widget.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, widget)
                self._items[edge_key] = (item, widget)

        self.lbl_title.setText(f"{translate('frameforge', 'Selected edges')} ({len(edges_list)}):")
        if self._items and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)

    def update_edge_badge(self, edge_key, rotation, mirror_h, mirror_v):
        if edge_key in self._items:
            _, widget = self._items[edge_key]
            widget.update_badge(rotation, mirror_h, mirror_v)

    def get_selected_edge(self):
        item = self.list_widget.currentItem()
        return item.data(QtCore.Qt.UserRole) if item is not None else None

    def get_selected_edges(self):
        return [self.list_widget.item(i).data(QtCore.Qt.UserRole)
                for i in range(self.list_widget.count()) if self.list_widget.item(i).isSelected()]

    def select_edge(self, edge_key):
        if edge_key in self._items:
            item, _ = self._items[edge_key]
            self.list_widget.setCurrentItem(item, QtCore.QItemSelectionModel.ClearAndSelect)

    def _on_item_changed(self, current, previous):
        edge_key = current.data(QtCore.Qt.UserRole) if current is not None else None
        self.edgeSelected.emit(edge_key)

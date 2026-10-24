"""Custom Profile Cards view and thumbnail editor for FrameForge Profile Library Manager.

Implements S1, S2, S3, S4:
- S1: Selecting Custom Profile shows selectable cards with vector silhouette thumbnails
      derived from stored section sketches; standard families retain their table.
- S2: Cards display NO dimensions; properties are edited in a modal and persist through
      save/reload; read-only behavior for non-editable libraries; non-column metadata preserved;
      duplicate codes and nonfinite/nonpositive weights rejected without stored mutations.
- S3: Manually entered weight persists through card edits, but applying a geometry edit
      recomputes and replaces it using existing section geometry/density behavior.
- S4: Preview inspection isolates documents and selection (no leaked open docs, active doc and
      selection preserved); harmless placeholder for missing/bad/traversal assets; no thumbnail
      files written into libraries.
"""

import copy
import math
import os
import shutil
import tempfile

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App

from freecad.maxproframe.custom_section_geometry import build_custom_section_face
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.section_library import resolve_and_validate_asset_path


def discretize_wire(wire):
    """Safely discretizes a FreeCAD Part.Wire into a list of App.Vector points.

    Curves are discretized appropriately with deflection or uniform sampling,
    preserving corners and smooth curve representation.
    """
    pts = []
    try:
        pts = wire.discretize(Deflection=0.05)
    except Exception:
        pts = []

    is_single_closed_curve = False
    try:
        edges = getattr(wire, "Edges", [])
        if len(edges) == 1:
            is_single_closed_curve = True
    except Exception:
        pass

    if not pts or (is_single_closed_curve and len(pts) < 16):
        try:
            pts = wire.discretize(Number=80)
        except Exception:
            pass

    if not pts:
        try:
            pts = wire.discretize(80)
        except Exception:
            pass

    if not pts:
        try:
            edges = getattr(wire, "OrderedEdges", getattr(wire, "Edges", []))
            for edge in edges:
                try:
                    e_pts = edge.discretize(Deflection=0.05)
                    if len(e_pts) < 2:
                        e_pts = edge.discretize(Number=20)
                except Exception:
                    e_pts = [v.Point for v in getattr(edge, "Vertexes", [])]
                for p in e_pts:
                    if not pts or (pts[-1] - p).Length > 1e-5:
                        pts.append(p)
        except Exception:
            pass

    return pts


def create_placeholder_pixmap(width=160, height=100, text=None):
    """Creates a clean placeholder pixmap for unavailable or corrupt previews."""
    if text is None:
        text = translate("frameforge", "No Preview")
    pm = QtGui.QPixmap(width, height)
    pm.fill(QtGui.QColor(245, 245, 245))
    painter = QtGui.QPainter(pm)
    painter.setPen(QtGui.QColor(180, 180, 180))
    painter.drawRect(0, 0, width - 1, height - 1)
    font = painter.font()
    font.setPointSize(9)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(120, 120, 120))
    painter.drawText(QtCore.QRect(0, 0, width, height), QtCore.Qt.AlignCenter, text)
    painter.end()
    return pm


def render_face_silhouette(face, canvas_w=160, canvas_h=100):
    """Renders a solid 2D vector silhouette from a Part.Face using QPainterPath

    with OddEvenFill to preserve outer contours and internal holes with exact proportions.
    """
    wires = getattr(face, "Wires", [])
    if not wires:
        return create_placeholder_pixmap(canvas_w, canvas_h)

    # Determine 2D projection plane (XY standard, or XZ/YZ if planar)
    bbox = getattr(face, "BoundBox", None)
    use_xy = True
    use_xz = False
    use_yz = False
    if bbox is not None:
        if bbox.ZLength < 1e-4 and (bbox.XLength >= 1e-4 or bbox.YLength >= 1e-4):
            use_xy = True
        elif bbox.YLength < 1e-4 and (bbox.XLength >= 1e-4 or bbox.ZLength >= 1e-4):
            use_xz = True
            use_xy = False
        elif bbox.XLength < 1e-4 and (bbox.YLength >= 1e-4 or bbox.ZLength >= 1e-4):
            use_yz = True
            use_xy = False

    painter_path = QtGui.QPainterPath()
    painter_path.setFillRule(QtCore.Qt.OddEvenFill)

    for wire in wires:
        pts = discretize_wire(wire)
        if not pts or len(pts) < 3:
            continue
        subpath = QtGui.QPainterPath()
        p0 = pts[0]
        if use_xy:
            subpath.moveTo(p0.x, p0.y)
            for p in pts[1:]:
                subpath.lineTo(p.x, p.y)
        elif use_xz:
            subpath.moveTo(p0.x, p0.z)
            for p in pts[1:]:
                subpath.lineTo(p.x, p.z)
        else:
            subpath.moveTo(p0.y, p0.z)
            for p in pts[1:]:
                subpath.lineTo(p.y, p.z)
        subpath.closeSubpath()
        painter_path.addPath(subpath)

    if painter_path.isEmpty():
        return create_placeholder_pixmap(canvas_w, canvas_h)

    br = painter_path.boundingRect()
    cad_w = br.width()
    cad_h = br.height()
    if cad_w <= 1e-4 or cad_h <= 1e-4:
        return create_placeholder_pixmap(canvas_w, canvas_h)

    padding = 10.0
    avail_w = max(10.0, float(canvas_w) - 2.0 * padding)
    avail_h = max(10.0, float(canvas_h) - 2.0 * padding)
    scale = min(avail_w / cad_w, avail_h / cad_h)

    cad_cx = br.center().x()
    cad_cy = br.center().y()
    icx = float(canvas_w) / 2.0
    icy = float(canvas_h) / 2.0

    transform = QtGui.QTransform()
    transform.translate(icx, icy)
    transform.scale(scale, -scale)
    transform.translate(-cad_cx, -cad_cy)

    transformed_path = transform.map(painter_path)

    img = QtGui.QImage(canvas_w, canvas_h, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(img)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(QtGui.QColor(58, 117, 196)))
    painter.drawPath(transformed_path)
    painter.end()

    return QtGui.QPixmap.fromImage(img)


def render_custom_section_thumbnail(folder_path, asset_path, object_name, width=160, height=100, cache=None):
    """Safely renders a custom section thumbnail using an isolated temporary copy

    without modifying user sketches, libraries, open documents, active document, or selection.
    """
    if not folder_path or not asset_path:
        return create_placeholder_pixmap(width, height)

    try:
        full_path = resolve_and_validate_asset_path(folder_path, asset_path)
    except Exception:
        return create_placeholder_pixmap(width, height)

    if not os.path.isfile(full_path):
        return create_placeholder_pixmap(width, height)

    try:
        mtime = os.path.getmtime(full_path)
    except OSError:
        mtime = 0

    cache_key = (os.path.realpath(folder_path), asset_path, object_name or "Section", mtime)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    active_doc = getattr(App, "ActiveDocument", None)
    active_doc_name = active_doc.Name if active_doc else None
    saved_selection = []
    try:
        import FreeCADGui as Gui_mod
        if hasattr(Gui_mod, "Selection"):
            for sel in Gui_mod.Selection.getSelectionEx():
                dname = getattr(sel, "DocumentName", None)
                if not dname and hasattr(sel, "Object") and hasattr(sel.Object, "Document"):
                    dname = sel.Object.Document.Name
                oname = getattr(sel, "ObjectName", None) or (sel.Object.Name if hasattr(sel, "Object") else None)
                sub_names = list(getattr(sel, "SubElementNames", []))
                if dname and oname:
                    saved_selection.append((dname, oname, sub_names))
    except Exception:
        saved_selection = []

    temp_dir = tempfile.mkdtemp(prefix="ff_thumb_inspect_")
    doc = None
    pixmap = None
    try:
        temp_file = os.path.join(temp_dir, "inspect.FCStd")
        shutil.copyfile(full_path, temp_file)

        try:
            doc = App.openDocument(temp_file)
        except Exception:
            doc = None

        if doc is not None and object_name:
            sketch = doc.getObject(object_name)
            if sketch is not None and (
                getattr(sketch, "TypeId", "") == "Sketcher::SketchObject"
                or (hasattr(sketch, "isDerivedFrom") and sketch.isDerivedFrom("Sketcher::SketchObject"))
            ):
                face = build_custom_section_face(sketch)
                if face is not None and face.isValid() and face.Area > 0:
                    pixmap = render_face_silhouette(face, width, height)
    except Exception:
        pixmap = None
    finally:
        if doc is not None:
            try:
                App.closeDocument(doc.Name)
            except Exception:
                pass
        try:
            shutil.rmtree(temp_dir)
        except OSError:
            pass
        if active_doc_name and active_doc_name in App.listDocuments():
            try:
                App.setActiveDocument(active_doc_name)
            except Exception:
                pass
        try:
            import FreeCADGui as Gui_mod
            if hasattr(Gui_mod, "Selection"):
                Gui_mod.Selection.clearSelection()
                for dname, oname, sub_names in saved_selection:
                    if dname in App.listDocuments():
                        if sub_names:
                            for sub in sub_names:
                                Gui_mod.Selection.addSelection(dname, oname, sub)
                        else:
                            Gui_mod.Selection.addSelection(dname, oname)
        except Exception:
            pass

    if pixmap is None:
        pixmap = create_placeholder_pixmap(width, height)

    if cache is not None:
        cache[cache_key] = pixmap

    return pixmap


class _DescriptionEdit(QtWidgets.QLineEdit):
    """Elide display text without changing the value used by table synchronization."""

    def __init__(self, text, lines=1, suffix=""):
        super().__init__(text)
        self._lines = lines
        self._suffix = suffix
        self.setToolTip(text + suffix)
        self.textChanged.connect(lambda value: self.setToolTip(value + self._suffix))

    def _display_lines(self):
        text = " ".join(self.text().splitlines()) + self._suffix
        width = max(0, self.contentsRect().width() - 4)
        metrics = self.fontMetrics()
        if self._lines == 1:
            return [metrics.elidedText(text, QtCore.Qt.ElideRight, width)]
        layout = QtGui.QTextLayout(text, self.font())
        layout.beginLayout()
        first = layout.createLine()
        if not first.isValid():
            layout.endLayout()
            return []
        first.setLineWidth(width)
        end = first.textLength()
        layout.endLayout()
        if end >= len(text):
            return [text]
        return [text[:end].rstrip(), metrics.elidedText(text[end:].lstrip(), QtCore.Qt.ElideRight, width)]

    def paintEvent(self, event):
        if self.hasFocus():
            return super().paintEvent(event)
        option = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(option)
        painter = QtWidgets.QStylePainter(self)
        painter.drawPrimitive(QtWidgets.QStyle.PE_PanelLineEdit, option)
        rect = self.style().subElementRect(QtWidgets.QStyle.SE_LineEditContents, option, self)
        margins = self.textMargins()
        rect.adjust(margins.left() + 2, 0, -margins.right() - 2, 0)
        painter.setPen(self.palette().color(QtGui.QPalette.Text))
        height = self.fontMetrics().height()
        for index, text in enumerate(self._display_lines()):
            line_rect = QtCore.QRect(rect.left(), rect.top() + index * height, rect.width(), height)
            painter.drawText(line_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)


class CustomProfileCard(QtWidgets.QFrame):
    """Selectable, display-only card with a separate properties editor."""

    def __init__(self, row, code, weight, props, dialog, cards_view, parent=None):
        super().__init__(parent)
        self.row = row
        self.props = copy.deepcopy(props) if isinstance(props, dict) else {}
        self.dialog = dialog
        self.cards_view = cards_view
        self._selected = False
        self._initializing = True
        self._updating_from_table = False
        self._updating_from_card = False
        self._last_source = "table"

        self.setObjectName("custom_card")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFixedWidth(240)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Thumbnail
        self.thumbnail_label = QtWidgets.QLabel()
        self.thumbnail_label.setObjectName("card_thumbnail")
        self.thumbnail_label.setAlignment(QtCore.Qt.AlignCenter)
        self.thumbnail_label.setFixedHeight(128)
        self.thumbnail_label.setContentsMargins(8, 36, 8, 28)
        self.thumbnail_label.setStyleSheet("background-color: palette(base); border-radius: 4px;")
        layout.addWidget(self.thumbnail_label)

        # Title and optional supporting text beneath the preview.
        self.code_edit = _DescriptionEdit(str(code))
        self.code_edit.setObjectName("card_code")
        title_font = QtGui.QFont(self.font())
        title_font.setBold(True)
        if title_font.pointSizeF() > 0:
            title_font.setPointSizeF(title_font.pointSizeF() * 1.25)
        else:
            title_font.setPixelSize(round(title_font.pixelSize() * 1.25))
        self.code_edit.setFont(title_font)
        self.code_edit.setFixedHeight(self.code_edit.fontMetrics().height() + 4)
        layout.addWidget(self.code_edit)

        # Reserve two lines even when empty so cards stay aligned.
        description_slot = QtWidgets.QWidget()
        description_layout = QtWidgets.QVBoxLayout(description_slot)
        description_layout.setContentsMargins(0, 0, 0, 0)
        self.description_edit = _DescriptionEdit(str(self.props.get("Description", "")), lines=2)
        self.description_edit.setObjectName("card_description")
        description_height = self.description_edit.fontMetrics().height() * 2 + 4
        description_slot.setFixedHeight(description_height)
        self.description_edit.setFixedHeight(description_height)
        description_layout.addWidget(self.description_edit)
        self.description_edit.setVisible(bool(self.description_edit.text().strip()))
        self.description_edit.textChanged.connect(
            lambda text: self.description_edit.setVisible(bool(text.strip()))
        )
        layout.addWidget(description_slot)

        self.weight_edit = _DescriptionEdit(str(weight), suffix=" kg/m")
        self.weight_edit.setObjectName("card_weight")
        weight_font = QtGui.QFont(self.font())
        if weight_font.pointSizeF() > 0:
            weight_font.setPointSizeF(weight_font.pointSizeF() * 0.85)
        else:
            weight_font.setPixelSize(round(weight_font.pixelSize() * 0.85))
        self.weight_edit.setFont(weight_font)
        self.weight_edit.setFixedHeight(max(22, self.weight_edit.fontMetrics().height() + 8))
        self.weight_edit.setParent(self.thumbnail_label)
        self.weight_edit.textChanged.connect(self._position_preview_controls)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        # Aliases for interface discovery
        self.le_code = self.code_edit
        self.le_weight = self.weight_edit
        self.lbl_thumbnail = self.thumbnail_label

        self.btn_edit_properties = QtWidgets.QToolButton(self.thumbnail_label)
        self.btn_edit_properties.setObjectName("card_edit_properties")
        self.btn_edit_properties.setToolTip(translate("frameforge", "Edit Properties"))
        self.btn_edit_properties.setAccessibleName(self.btn_edit_properties.toolTip())
        self.btn_edit_properties.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.btn_edit_properties.setIconSize(QtCore.QSize(18, 18))
        self.btn_edit_properties.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.btn_edit_properties.setFixedSize(28, 28)
        self.btn_edit_properties.clicked.connect(self._edit_properties)
        self._position_preview_controls()

        # Editable state based on library permissions
        is_user = bool(dialog.current_lib_meta and dialog.current_lib_meta.get("is_user"))
        self.set_editable(is_user)

        # Signals
        self.code_edit.textChanged.connect(self._on_code_changed)
        self.weight_edit.textChanged.connect(self._on_weight_changed)
        self.description_edit.textChanged.connect(self._on_description_changed)

        # Event filter for click/focus selection sync
        self.installEventFilter(self)
        self.thumbnail_label.installEventFilter(self)
        self.code_edit.installEventFilter(self)
        self.weight_edit.installEventFilter(self)
        self.description_edit.installEventFilter(self)

        self._update_style()
        self._initializing = False
        QtWidgets.QApplication.instance().paletteChanged.connect(self._on_palette_changed)

    def _on_palette_changed(self, palette):
        # Read the application palette, not a palette already modified by card QSS.
        self._update_style()

    def _position_preview_controls(self, *_):
        preview = self.thumbnail_label
        self.btn_edit_properties.move(4, 4)
        width = self.weight_edit.fontMetrics().horizontalAdvance(self.weight_edit.text() + " kg/m") + 14
        self.weight_edit.setFixedWidth(min(width, max(1, preview.width() - 8)))
        self.weight_edit.move(preview.width() - self.weight_edit.width() - 4,
                              preview.height() - self.weight_edit.height() - 4)

    def eventFilter(self, obj, event):
        if obj is self.thumbnail_label and event.type() == QtCore.QEvent.Resize:
            self._position_preview_controls()
        if event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.FocusIn):
            self.cards_view.select_card(self.row)
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self.cards_view.select_card(self.row)
        super().mousePressEvent(event)

    def click(self):
        self.cards_view.select_card(self.row)

    def setSelected(self, selected):
        self._selected = bool(selected)
        self._update_style()

    def _update_style(self):
        palette = QtWidgets.QApplication.palette()
        background = QtGui.QPalette.Highlight if self._selected else QtGui.QPalette.Window
        foreground = QtGui.QPalette.HighlightedText if self._selected else QtGui.QPalette.WindowText
        border = QtGui.QPalette.Highlight if self._selected else QtGui.QPalette.Mid
        border_width = 2 if self._selected else 1
        self.setStyleSheet(
            "QFrame#custom_card { "
            f"border: {border_width}px solid {palette.color(border).name()}; "
            f"background-color: {palette.color(background).name()}; "
            "border-radius: 6px; }"
            "QFrame#custom_card QLabel { "
            f"color: {palette.color(foreground).name()}; }}"
        )
        self.thumbnail_label.setStyleSheet(
            f"background-color: {palette.color(QtGui.QPalette.Base).name()}; border-radius: 4px;"
        )

        # Retain the existing table synchronization while presenting values as text.
        for field in (self.code_edit, self.description_edit, self.weight_edit):
            color = palette.color(foreground)
            if field is self.description_edit and not self._selected:
                surface = palette.color(background)
                color = QtGui.QColor(*(
                    round(a * 0.8 + b * 0.2)
                    for a, b in zip(color.getRgb()[:3], surface.getRgb()[:3])
                ))
            field.setStyleSheet(
                "background: transparent; border: none; padding: 0; "
                f"color: {color.name()};"
            )
        for widget, surface_role, ink_role, radius, padding in (
            (self.weight_edit, QtGui.QPalette.AlternateBase, QtGui.QPalette.Text, 5, "2px 4px"),
            (self.btn_edit_properties, QtGui.QPalette.Button, QtGui.QPalette.ButtonText, 4, "0"),
        ):
            surface = palette.color(surface_role)
            ink = palette.color(ink_role)
            editable = self.btn_edit_properties.isEnabled()
            accent = palette.color(QtGui.QPalette.Highlight) if editable else ink
            strength = 0.55 if editable else 0.3
            outline = QtGui.QColor(*(
                round(a * strength + b * (1 - strength))
                for a, b in zip(accent.getRgb()[:3], surface.getRgb()[:3])
            ))
            style = (
                f"background: {surface.name()}; color: {ink.name()}; "
                f"border: 1px solid {outline.name()}; border-radius: {radius}px; padding: {padding};"
            )
            if widget is self.btn_edit_properties:
                style = f"QToolButton {{ {style} }}"
                if editable:
                    style += (
                        "QToolButton:enabled:hover, QToolButton:enabled:focus { "
                        f"border: 1px solid {accent.name()}; }}"
                    )
            widget.setStyleSheet(style)
        # Draw the pencil using the live palette, without a desktop icon-theme dependency.
        pixmap = QtGui.QPixmap(18, 18)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.ButtonText), 1.5))
        painter.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(4, 11), QtCore.QPointF(11, 4),
            QtCore.QPointF(14, 7), QtCore.QPointF(7, 14), QtCore.QPointF(3, 15),
        ]))
        painter.drawLine(QtCore.QPointF(10, 5), QtCore.QPointF(13, 8))
        painter.drawLine(QtCore.QPointF(4, 11), QtCore.QPointF(7, 14))
        painter.end()
        self.btn_edit_properties.setIcon(QtGui.QIcon(pixmap))
        self._position_preview_controls()

    def set_editable(self, editable):
        self.btn_edit_properties.setEnabled(bool(editable))
        for field in (self.code_edit, self.description_edit, self.weight_edit):
            field.setReadOnly(True)
            field.setFrame(False)
            field.setFocusPolicy(QtCore.Qt.NoFocus)
        self._update_style()

    def _edit_properties(self):
        if not self.btn_edit_properties.isEnabled():
            return
        self.cards_view.select_card(self.row)
        editor = QtWidgets.QDialog(self)
        editor.setObjectName("custom_properties_dialog")
        editor.setWindowTitle(translate("frameforge", "Edit Properties"))
        editor.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(editor)
        form = QtWidgets.QFormLayout()
        code = QtWidgets.QLineEdit(self.code_edit.text())
        description = QtWidgets.QLineEdit(self.description_edit.text())
        weight = QtWidgets.QLineEdit(self.weight_edit.text())
        code.setObjectName("property_code")
        description.setObjectName("property_description")
        weight.setObjectName("property_weight")
        form.addRow(translate("frameforge", "Code:"), code)
        form.addRow(translate("frameforge", "Description:"), description)
        form.addRow(translate("frameforge", "Weight (kg/m):"), weight)
        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Save).setText(translate("frameforge", "Save"))
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(translate("frameforge", "Cancel"))
        layout.addWidget(buttons)
        buttons.rejected.connect(editor.reject)

        def validate():
            name = code.text().strip()
            value = weight.text().strip()
            error = None
            if not name:
                error = translate("frameforge", "Enter a non-empty size code.")
            elif any(
                row != self.row and self.dialog.table_sizes.item(row, 0)
                and self.dialog.table_sizes.item(row, 0).text().strip() == name
                for row in range(self.dialog.table_sizes.rowCount())
            ):
                error = translate(
                    "frameforge", "Duplicate size codes found: %s. Each size must have a unique code."
                ) % name
            else:
                try:
                    number = float(value)
                    if not math.isfinite(number) or number <= 0:
                        raise ValueError(value)
                except ValueError:
                    error = translate(
                        "frameforge",
                        "Invalid weight '%s' for custom profile '%s'. Weight must be a positive finite number.",
                    ) % (value, name)
            if error:
                QtWidgets.QMessageBox.warning(editor, translate("frameforge", "Edit Properties"), error)
                return
            editor.accept()

        buttons.accepted.connect(validate)
        if editor.exec_() == QtWidgets.QDialog.Accepted:
            self.code_edit.setText(code.text().strip())
            self.description_edit.setText(description.text())
            self.weight_edit.setText(weight.text().strip())
        editor.deleteLater()

    def update_thumbnail(self, pixmap):
        if pixmap is not None:
            # Keep geometry inside the unobstructed strip between the two overlays.
            self.thumbnail_label.setPixmap(
                pixmap.scaled(160, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            )

    def _on_code_changed(self, text):
        if getattr(self, "_initializing", False) or getattr(self, "_updating_from_table", False):
            return
        self._last_source = "card"
        item = self.dialog.table_sizes.item(self.row, 0)
        if item and item.text() != text:
            self._updating_from_card = True
            try:
                item.setText(text)
            finally:
                self._updating_from_card = False
            self.dialog._mark_dirty()

    def _on_description_changed(self, text):
        if self._initializing or self._updating_from_table:
            return
        item = self.dialog.table_sizes.item(self.row, 0)
        if item:
            # Merge into the authoritative metadata, never the card's stale props.
            props = item.data(QtCore.Qt.UserRole)
            props = copy.deepcopy(props) if isinstance(props, dict) else {}
            props['Description'] = text
            item.setData(QtCore.Qt.UserRole, props)

    def _on_weight_changed(self, text):
        if getattr(self, "_initializing", False) or getattr(self, "_updating_from_table", False):
            return
        self._last_source = "card"
        item = self.dialog.table_sizes.item(self.row, 7)
        if item and item.text() != text:
            self._updating_from_card = True
            try:
                item.setText(text)
            finally:
                self._updating_from_card = False
            self.dialog._mark_dirty()


class CustomProfileCardsView(QtWidgets.QWidget):
    """Container view managing selectable custom profile cards synchronized with table_sizes."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.cards = []
        self._selected_index = -1
        self._thumbnail_cache = {}

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.container_widget = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.container_widget)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        self.scroll_area.setWidget(self.container_widget)
        main_layout.addWidget(self.scroll_area)

    def _columns_per_row(self):
        vp_width = self.scroll_area.viewport().width() if hasattr(self, "scroll_area") else 0
        if vp_width > 260:
            # card 240px + spacing 12px = 252px; margins: 8+8=16px
            cols = (vp_width - 16 + 12) // (240 + 12)
            return max(1, cols)
        return 3

    def _relayout_cards(self):
        if not hasattr(self, "grid_layout") or not hasattr(self, "dialog") or not hasattr(self.dialog, "table_sizes"):
            return
        columns_per_row = self._columns_per_row()
        visible = 0
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            hidden = self.dialog.table_sizes.isRowHidden(card.row)
            card.setHidden(hidden)
            if not hidden:
                self.grid_layout.addWidget(card, visible // columns_per_row, visible % columns_per_row)
                visible += 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = self._columns_per_row()
        if getattr(self, "_current_columns_per_row", None) != cols:
            self._current_columns_per_row = cols
            self._relayout_cards()

    def filter_from_table(self):
        self._relayout_cards()
        self.on_table_selection_changed()

    def count(self):
        return len(self.cards)

    def card(self, index):
        if 0 <= index < len(self.cards):
            return self.cards[index]
        return None

    def card_by_code(self, code):
        target = str(code).strip()
        for c in self.cards:
            if c.code_edit.text().strip() == target:
                return c
        return None

    def select_card(self, index):
        if not (0 <= index < len(self.cards)) or self.dialog.table_sizes.isRowHidden(index):
            return
        self._selected_index = index
        for i, c in enumerate(self.cards):
            c.setSelected(i == index)

        if self.dialog._selected_profile_row() != index:
            self.dialog.table_sizes.blockSignals(True)
            self.dialog.table_sizes.setCurrentCell(index, 0)
            self.dialog.table_sizes.selectRow(index)
            self.dialog.table_sizes.blockSignals(False)

        self.dialog._update_section_buttons()

    def setCurrentIndex(self, index):
        self.select_card(index)

    def selected_index(self):
        return self._selected_index

    def on_table_item_changed(self, item):
        """Synchronizes edits made directly to table_sizes into the matching card widget."""
        if not item:
            return
        row = item.row()
        col = item.column()
        if not (0 <= row < len(self.cards)):
            return
        card = self.cards[row]
        if getattr(card, "_updating_from_card", False):
            return

        text = item.text()
        if col == 0:
            props = item.data(QtCore.Qt.UserRole)
            description = str(props.get('Description', '')) if isinstance(props, dict) else ''
            if card.description_edit.text() != description:
                card._updating_from_table = True
                try:
                    card.description_edit.setText(description)
                finally:
                    card._updating_from_table = False
            if card.code_edit.text() != text:
                card._last_source = "table"
                card._updating_from_table = True
                try:
                    card.code_edit.setText(text)
                finally:
                    card._updating_from_table = False
        elif col == 7:
            if card.weight_edit.text() != text:
                card._last_source = "table"
                card._updating_from_table = True
                try:
                    card.weight_edit.setText(text)
                finally:
                    card._updating_from_table = False

    def on_table_selection_changed(self):
        row = self.dialog._selected_profile_row()
        if 0 <= row < len(self.cards):
            if self._selected_index != row:
                self._selected_index = row
                for i, c in enumerate(self.cards):
                    c.setSelected(i == row)
        else:
            if self._selected_index != -1:
                self._selected_index = -1
                for c in self.cards:
                    c.setSelected(False)

    def sync_to_table(self):
        """Ensures table_sizes and cards_view are synchronized before commit.

        The table item model is the authoritative model (single source of truth).
        If card was edited last by user, pending card changes are reflected to table.
        If table item was edited last, table edits remain authoritative and card is updated.
        """
        for idx, card in enumerate(self.cards):
            if idx < self.dialog.table_sizes.rowCount():
                item_code = self.dialog.table_sizes.item(idx, 0)
                item_weight = self.dialog.table_sizes.item(idx, 7)
                code_text = card.code_edit.text()
                weight_text = card.weight_edit.text()

                if getattr(card, "_last_source", "table") == "card":
                    if item_code and item_code.text() != code_text:
                        card._updating_from_card = True
                        try:
                            item_code.setText(code_text)
                        finally:
                            card._updating_from_card = False
                    if item_weight and item_weight.text() != weight_text:
                        card._updating_from_card = True
                        try:
                            item_weight.setText(weight_text)
                        finally:
                            card._updating_from_card = False
                else:
                    if item_code and item_code.text() != code_text:
                        card._updating_from_table = True
                        try:
                            card.code_edit.setText(item_code.text())
                        finally:
                            card._updating_from_table = False
                    if item_weight and item_weight.text() != weight_text:
                        card._updating_from_table = True
                        try:
                            card.weight_edit.setText(item_weight.text())
                        finally:
                            card._updating_from_table = False

    def refresh_card(self, row):
        if not (0 <= row < len(self.cards)):
            return
        card = self.cards[row]
        item_weight = self.dialog.table_sizes.item(row, 7)
        if item_weight:
            card._last_source = "table"
            card._updating_from_table = True
            try:
                card.weight_edit.setText(item_weight.text().strip())
            finally:
                card._updating_from_table = False

        # Refresh thumbnail
        size_item = self.dialog.table_sizes.item(row, 0)
        props = size_item.data(QtCore.Qt.UserRole) if size_item else {}
        if not isinstance(props, dict):
            props = {}
        folder_path = self.dialog.current_lib_meta.get("folder_path") if self.dialog.current_lib_meta else None
        asset_path = props.get("asset_path")
        obj_name = props.get("object_name", "Section")

        if folder_path and asset_path:
            for k in list(self._thumbnail_cache.keys()):
                if k[0] == os.path.realpath(folder_path) and k[1] == asset_path:
                    self._thumbnail_cache.pop(k, None)

        pixmap = render_custom_section_thumbnail(
            folder_path=folder_path,
            asset_path=asset_path,
            object_name=obj_name,
            width=160,
            height=100,
            cache=self._thumbnail_cache,
        )
        card.update_thumbnail(pixmap)

    def load_from_table(self, table_sizes, dialog):
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.cards = []
        self._selected_index = -1

        row_count = table_sizes.rowCount()
        folder_path = dialog.current_lib_meta.get("folder_path") if dialog.current_lib_meta else None

        for row in range(row_count):
            size_item = table_sizes.item(row, 0)
            code = size_item.text().strip() if size_item else ""
            props = size_item.data(QtCore.Qt.UserRole) if size_item else {}
            if not isinstance(props, dict):
                props = {}

            weight_item = table_sizes.item(row, 7)
            weight = weight_item.text().strip() if weight_item else props.get("Weight", "0")

            card = CustomProfileCard(
                row=row,
                code=code,
                weight=weight,
                props=props,
                dialog=dialog,
                cards_view=self,
                parent=self.container_widget,
            )

            asset_path = props.get("asset_path")
            obj_name = props.get("object_name", "Section")
            pixmap = render_custom_section_thumbnail(
                folder_path=folder_path,
                asset_path=asset_path,
                object_name=obj_name,
                width=160,
                height=100,
                cache=self._thumbnail_cache,
            )
            card.update_thumbnail(pixmap)
            self.cards.append(card)

        self._current_columns_per_row = self._columns_per_row()
        self._relayout_cards()

        curr_row = table_sizes.currentRow()
        if 0 <= curr_row < len(self.cards):
            self.select_card(curr_row)
        else:
            self._selected_index = -1
            for c in self.cards:
                c.setSelected(False)

"""Drawing parametric lines by dragging the mouse in a global plane.

The 3D view shows the global XY, XZ and YZ planes as squares at the start of the newest line of the panel.
A click on a square (or P) starts the drag in its plane: the cursor ray meets the plane, the way from the
start snaps to an axis of the plane or to an angle every 15°, and the length to 10 mm (1 mm with Shift).
A second click fixes it; Esc or a right click puts back the values the drag started from.
"""

import math

import FreeCAD as App

from freecad.maxproframe.parametric_line import PLANES

ANGLE_STEP = 15.0
LENGTH_STEP = 10.0
FINE_LENGTH_STEP = 1.0
# A plane seen under this angle (degrees) from the view is edge-on: dimmed and not clickable.
EDGE_ON_ANGLE = 10.0
# Side of the plane squares, in screen pixels.
SQUARE_PIXELS = 60
PLANE_COLORS = {"XY": (0.2, 0.4, 1.0), "XZ": (0.2, 0.8, 0.2), "YZ": (1.0, 0.3, 0.3)}
ACTIVE_TRANSPARENCY = 0.55
IDLE_TRANSPARENCY = 0.75
DIMMED_TRANSPARENCY = 0.92
# Global axes along the first and second axis of each plane, both ways, by angle.
AXIS_AT = {
    "XY": {0: "+X", 90: "+Y", 180: "-X", -90: "-Y"},
    "XZ": {0: "+X", 90: "+Z", 180: "-X", -90: "-Z"},
    "YZ": {0: "+Y", 90: "+Z", 180: "-Y", -90: "-Z"},
}


def _normal(plane):
    first, second = PLANES[plane]
    return first.cross(second)


def plane_point(start, plane, origin, direction):
    """Where the ray from ``origin`` along ``direction`` meets the global ``plane`` through ``start``, or None."""
    normal = _normal(plane)
    along = direction.dot(normal)
    if abs(along) < 1e-12:
        return None
    t = (start - origin).dot(normal) / along
    return origin + direction * t


def edge_on(plane, view_direction, limit=EDGE_ON_ANGLE):
    """Whether ``plane`` is seen under ``limit`` degrees from ``view_direction``: too thin to drag in."""
    if view_direction.Length < 1e-12:
        return False
    sine = abs(App.Vector(view_direction).normalize().dot(_normal(plane)))
    return sine < math.sin(math.radians(limit))


def plane_at(start, size, origin, direction, planes=tuple(PLANES)):
    """The plane of ``planes`` whose square (``size`` long from ``start`` along the plane's positive axes) the
    ray crosses first, or None."""
    best, best_t = None, None
    for plane in planes:
        normal = _normal(plane)
        along = direction.dot(normal)
        if abs(along) < 1e-12:
            continue
        t = (start - origin).dot(normal) / along
        if t < 0:
            continue
        offset = origin + direction * t - start
        first, second = PLANES[plane]
        u, v = offset.dot(first), offset.dot(second)
        inside = -1e-9 <= u <= size + 1e-9 and -1e-9 <= v <= size + 1e-9
        if inside and (best_t is None or t < best_t):
            best, best_t = plane, t
    return best


def snapped_direction(plane, start, point, fine=False):
    """(direction, angle, length) of the way from ``start`` to ``point`` in the global ``plane``.

    The angle snaps every 15°: on an axis of the plane the direction is that global axis, otherwise "Angle".
    The length snaps to 10 mm (1 mm when ``fine``) and is never shorter than one step.
    """
    first, second = PLANES[plane]
    offset = point - start
    u, v = offset.dot(first), offset.dot(second)
    angle = round(math.degrees(math.atan2(v, u)) / ANGLE_STEP) * ANGLE_STEP
    if angle <= -180:
        angle += 360
    step = FINE_LENGTH_STEP if fine else LENGTH_STEP
    length = max(step, round(math.hypot(u, v) / step) * step)
    angle = int(angle) if angle == int(angle) else angle
    return AXIS_AT[plane].get(angle, "Angle"), angle, length


class ViewDrag:
    """The plane squares and the mouse and keys of the 3D view, for ``panel`` while it creates lines.

    The panel gives ``drag_anchor()`` (the start of the newest line, or None), ``drag_plane``, and takes
    ``start_drag``, ``drag_to``, ``finish_drag``, ``cancel_drag`` and ``cycle_plane``.
    """

    def __init__(self, panel, view):
        self.panel = panel
        self.view = view
        self._callbacks = []
        self._node = None
        # A click the drag took: the selection FreeCAD makes under it is no vertex pick.
        self.click_taken = False
        # Side of the squares as last drawn, in mm, and what they were drawn for: a redraw with the same
        # anchor, size, plane and usable planes leaves them in the scene.
        self.size = 50.0
        self._drawn = None

    # Listening.

    def listen(self):
        from pivy import coin

        for event_type, handler in (
            (coin.SoMouseButtonEvent, self._on_button),
            (coin.SoLocation2Event, self._on_move),
            (coin.SoKeyboardEvent, self._on_key),
        ):
            try:
                callback = self.view.addEventCallbackPivy(event_type.getClassTypeId(), handler)
            except Exception:
                continue
            self._callbacks.append((event_type, callback))
        self.redraw()

    def stop(self):
        # The release of a taken click may never come (released outside the view): nothing waits for it now.
        self.click_taken = False
        callbacks, self._callbacks = self._callbacks, []
        for event_type, callback in callbacks:
            try:
                self.view.removeEventCallbackPivy(event_type.getClassTypeId(), callback)
            except Exception:
                pass
        self._remove_node()

    # The view.

    def _ray(self, position):
        """(origin, direction) of the ray under the screen ``position``, or None when the view gives none."""
        try:
            point = App.Vector(self.view.getPoint(int(position[0]), int(position[1])))
            camera = self.view.getCameraNode()
            if camera.getTypeId().getName() == "PerspectiveCamera":
                origin = App.Vector(*camera.position.getValue().getValue())
                return origin, point - origin
            direction = App.Vector(self.view.getViewDirection())
        except Exception:
            return None
        return point - direction * 1e6, direction

    def _view_direction(self):
        try:
            return App.Vector(self.view.getViewDirection())
        except Exception:
            return App.Vector()

    def _square_size(self, anchor):
        """Side of the squares in mm: SQUARE_PIXELS on screen at ``anchor``."""
        try:
            x, y = self.view.getPointOnViewport(anchor)[:2]
            far = App.Vector(self.view.getPoint(int(x) + SQUARE_PIXELS, int(y)))
            near = App.Vector(self.view.getPoint(int(x), int(y)))
            return max((far - near).Length, 1e-6)
        except Exception:
            return 50.0

    def usable_planes(self):
        """Planes not seen edge-on."""
        view_direction = self._view_direction()
        return tuple(plane for plane in PLANES if not edge_on(plane, view_direction))

    # Events.

    def _on_button(self, event_callback):
        from pivy import coin

        event = event_callback.getEvent()
        button, down = event.getButton(), event.getState() == coin.SoMouseButtonEvent.DOWN
        if button not in (coin.SoMouseButtonEvent.BUTTON1, coin.SoMouseButtonEvent.BUTTON2):
            return
        if not down:
            if self.click_taken:
                # FreeCAD selects under a click on its release, before this callback: the pick stays
                # ignored until the release is processed.
                from PySide import QtCore

                event_callback.setHandled()
                QtCore.QTimer.singleShot(0, self._release_click)
            return
        self.click_taken = False
        if self.panel.drag_plane is not None:
            if button == coin.SoMouseButtonEvent.BUTTON1:
                self._drag(event)
                self.panel.finish_drag()
            else:
                self.panel.cancel_drag()
            self._take(event_callback)
            return
        anchor = self.panel.drag_anchor()
        if button != coin.SoMouseButtonEvent.BUTTON1 or anchor is None:
            return
        # The squares are drawn again first: their size and the planes seen edge-on follow the camera.
        self.redraw()
        ray = self._ray(event.getPosition().getValue())
        if ray is None:
            return
        plane = plane_at(anchor, self.size, *ray, self.usable_planes())
        if plane is not None:
            self.panel.start_drag(plane)
            self._take(event_callback)

    def _take(self, event_callback):
        """A press the drag took: its release is no vertex pick either."""
        event_callback.setHandled()
        self.click_taken = True

    def _release_click(self):
        self.click_taken = False

    def _on_move(self, event_callback):
        if self.panel.drag_plane is None:
            return
        self._drag(event_callback.getEvent())

    def _drag(self, event):
        anchor = self.panel.drag_anchor()
        if anchor is None:
            return
        ray = self._ray(event.getPosition().getValue())
        if ray is None:
            return
        point = plane_point(anchor, self.panel.drag_plane, *ray)
        if point is not None:
            self.panel.drag_to(point, fine=event.wasShiftDown())

    def _on_key(self, event_callback):
        from pivy import coin

        event = event_callback.getEvent()
        if event.getState() != coin.SoButtonEvent.DOWN:
            return
        key = event.getKey()
        if key == coin.SoKeyboardEvent.P:
            self.panel.cycle_plane(self.usable_planes())
            event_callback.setHandled()
        elif key == coin.SoKeyboardEvent.ESCAPE and self.panel.drag_plane is not None:
            self.panel.cancel_drag()
            event_callback.setHandled()

    # The squares.

    def _remove_node(self):
        if self._node is None:
            return
        scene, node = self._node
        self._node = None
        self._drawn = None
        try:
            scene.removeChild(node)
        except Exception:
            pass

    def redraw(self):
        """Draw the squares at the start of the newest line: the active plane strong, edge-on planes faint.

        Squares already drawn the same way stay: a move of the drag redraws nothing.
        """
        anchor = self.panel.drag_anchor()
        if anchor is None:
            self._remove_node()
            return
        size = self._square_size(anchor)
        usable = self.usable_planes()
        drawn = (tuple(round(c, 6) for c in anchor), round(size, 6), self.panel.drag_plane, usable)
        if self._node is not None and drawn == self._drawn:
            return
        self._remove_node()
        try:
            scene = self.view.getSceneGraph()
        except Exception:
            return
        from pivy import coin

        self.size = size
        node = coin.SoAnnotation()
        for plane, (first, second) in PLANES.items():
            if self.panel.drag_plane == plane:
                transparency = ACTIVE_TRANSPARENCY
            elif self.panel.drag_plane is None and plane in usable:
                transparency = IDLE_TRANSPARENCY
            else:
                transparency = DIMMED_TRANSPARENCY
            group = coin.SoSeparator()
            material = coin.SoMaterial()
            material.diffuseColor.setValue(*PLANE_COLORS[plane])
            material.transparency.setValue(transparency)
            corners = [anchor, anchor + first * size, anchor + (first + second) * size, anchor + second * size]
            coordinates = coin.SoCoordinate3()
            coordinates.point.setValues(0, 4, [(p.x, p.y, p.z) for p in corners])
            faces = coin.SoFaceSet()
            faces.numVertices.setValue(4)
            for child in (material, coordinates, faces):
                group.addChild(child)
            node.addChild(group)
        scene.addChild(node)
        self._node = (scene, node)
        self._drawn = drawn

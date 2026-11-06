# Parametric line
# Initial author : Christophe Grellier (Chris_G)
# LGPL 2.
# Parametric line between two vertexes, or from a vertex along a direction with a length.
# Select 2 vertexes in the 3D View and activate the tool.

import os

import FreeCAD as App
import Part

if App.GuiUp:
    import FreeCADGui as Gui

from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command

TOOL_ICON = os.path.join(ICONPATH, "line.svg")

# Global links: a Part receiving the line must not drag the profiles it measures (local links are pulled along).
LINK_TYPE = "App::PropertyLinkSubGlobal"
VERTEX_PROPERTIES = (("Vertex1", "First Vertex"), ("Vertex2", "Second Vertex"))
# Direction "Vertex2" joins the two vertices; the others run from Vertex1 along a global axis or CustomDirection.
AXES = {
    "+X": App.Vector(1, 0, 0),
    "-X": App.Vector(-1, 0, 0),
    "+Y": App.Vector(0, 1, 0),
    "-Y": App.Vector(0, -1, 0),
    "+Z": App.Vector(0, 0, 1),
    "-Z": App.Vector(0, 0, -1),
}
DIRECTIONS = ["Vertex2", *AXES, "Custom"]
DEFAULT_LENGTH = 1000.0


def _add_vertex_properties(obj):
    for name, doc in VERTEX_PROPERTIES:
        obj.addProperty(LINK_TYPE, name, "ParametricLine", doc)


def _add_direction_properties(obj):
    """Direction, CustomDirection and Length; a line without them (earlier versions) joins its two vertices."""
    if "Direction" not in obj.PropertiesList:
        obj.addProperty(
            "App::PropertyEnumeration",
            "Direction",
            "ParametricLine",
            "Vertex2 joins the two vertices; an axis or Custom runs from the first vertex, Length long",
        )
        obj.Direction = DIRECTIONS
    if "CustomDirection" not in obj.PropertiesList:
        obj.addProperty("App::PropertyVector", "CustomDirection", "ParametricLine", "Global direction when Custom")
        obj.CustomDirection = App.Vector(0, 0, -1)
    if "Length" not in obj.PropertiesList:
        obj.addProperty("App::PropertyLength", "Length", "ParametricLine", "Length of a line along a direction")
        obj.Length = DEFAULT_LENGTH


def _migrate_local_links(obj):
    """Lines saved with local links keep their vertices under global links."""
    for name, doc in VERTEX_PROPERTIES:
        if name in obj.PropertiesList and obj.getTypeIdOfProperty(name) == LINK_TYPE:
            continue
        value = obj.getPropertyByName(name) if name in obj.PropertiesList else None
        if name in obj.PropertiesList:
            obj.removeProperty(name)
        obj.addProperty(LINK_TYPE, name, "ParametricLine", doc)
        if value:
            setattr(obj, name, value)


def _group_placement(obj):
    """Global placement of the coordinate system obj's shape is expressed in."""
    parent = obj.getParentGeoFeatureGroup() if hasattr(obj, "getParentGeoFeatureGroup") else None
    return parent.getGlobalPlacement() if parent is not None else App.Placement()


def _direction(obj):
    """Global unit vector of a line along a direction, or None when it has none (zero custom vector)."""
    vector = App.Vector(obj.CustomDirection) if obj.Direction == "Custom" else App.Vector(AXES[obj.Direction])
    if vector.Length < 1e-9:
        return None
    return vector.normalize()


def _global_vertex(link):
    """Global point of a (object, ["VertexN"]) link, or None when it is broken."""
    if not link:
        return None
    source, subs = link
    sub = subs[0] if subs else ""
    shape = getattr(source, "Shape", None)
    if not sub.startswith("Vertex") or not sub[6:].isdigit() or shape is None:
        return None
    index = int(sub[6:])
    if not 1 <= index <= len(shape.Vertexes):
        return None
    return _group_placement(source).multVec(shape.Vertexes[index - 1].Point)


class ParametricLine:
    """Creates a parametric line between two vertexes"""

    def __init__(self, obj):
        """Add the properties"""
        _add_vertex_properties(obj)
        _add_direction_properties(obj)
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        _migrate_local_links(obj)
        _add_direction_properties(obj)

    def execute(self, obj):
        p1 = _global_vertex(obj.Vertex1)
        if obj.Direction == "Vertex2":
            p2 = _global_vertex(obj.Vertex2)
        else:
            direction = _direction(obj)
            if direction is None:
                App.Console.PrintError("{}: the custom direction is a zero vector.\n".format(obj.Label))
                return
            if obj.Length.Value <= 0:
                App.Console.PrintError("{}: the length must be greater than zero.\n".format(obj.Label))
                return
            p2 = p1 + direction * obj.Length.Value if p1 is not None else None
        if p1 is not None and p2 is not None:
            # Drawn in the coordinates of the group holding the line.
            to_local = _group_placement(obj).inverse()
            ls = Part.LineSegment(to_local.multVec(p1), to_local.multVec(p2))
            obj.Shape = ls.toShape()
        else:
            App.Console.PrintError("{} broken !\n".format(obj.Label))


def make_line_from_vertex(vertex, direction, length, custom=None, recompute=True):
    """A parametric line from ``vertex`` ((object, "VertexN")) along ``direction`` (an axis of AXES or "Custom")."""
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "ParametricLine")
    ParametricLine(obj)
    if App.GuiUp:
        ParametricLineViewProvider(obj.ViewObject)
    obj.Vertex1 = vertex
    obj.Direction = direction
    if custom is not None:
        obj.CustomDirection = custom
    obj.Length = length
    if recompute:
        App.ActiveDocument.recompute()
    return obj


class ParametricLineViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object

    def __getstate__(self):
        return {"name": self.Object.Name}

    def __setstate__(self, state):
        self.Object = App.ActiveDocument.getObject(state["name"])
        return None

    def setEdit(self, vobj, mode):
        """Double-click on a line drawn from a vertex: its panel. A line joining two vertices has none."""
        if mode != 0 or getattr(self.Object, "Direction", "Vertex2") == "Vertex2":
            return None
        from freecad.maxproframe import parametric_line_panel

        parametric_line_panel.show_panel(parametric_line_panel.ParametricLineTaskPanel(edited=self.Object))
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0 or getattr(self.Object, "Direction", "Vertex2") == "Vertex2":
            return None
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        return True


def _selected_vertices():
    """(object, "VertexN") of each vertex selected in the 3D view."""
    verts = []
    for selobj in Gui.Selection.getSelectionEx():
        if selobj.HasSubObjects:
            for shape, name in zip(selobj.SubObjects, selobj.SubElementNames):
                if isinstance(shape, Part.Vertex):
                    verts.append((selobj.Object, name))
    return verts


def _same_sketch(verts):
    """Whether every vertex is of one sketch: corners of a frame sketch get lines along a direction."""
    first = verts[0][0]
    return first.isDerivedFrom("Sketcher::SketchObject") and all(obj is first for obj, _ in verts)


class CreateParametricLineCommand:
    """Creates a parametric line between two vertexes"""

    def make_parametric_line(self, source):
        line_object = App.ActiveDocument.addObject("Part::FeaturePython", "ParametricLine")

        ParametricLine(line_object)
        ParametricLineViewProvider(line_object.ViewObject)

        line_object.Vertex1 = source[0]
        line_object.Vertex2 = source[1]
        App.ActiveDocument.recompute()

    def Activated(self):
        verts = _selected_vertices()
        if len(verts) == 2 and not _same_sketch(verts):
            self.make_parametric_line(verts)
        elif verts:
            from freecad.maxproframe import parametric_line_panel

            parametric_line_panel.show_panel(parametric_line_panel.ParametricLineTaskPanel(verts))

    def IsActive(self):
        return App.ActiveDocument is not None and bool(_selected_vertices())

    def GetResources(self):
        return {
            "Pixmap": TOOL_ICON,
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ParametricLine", "Create a Parametric Line"),
            "Accel": "M, L",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ParametricLine",
                "Create a parametric line between two vertices, or from vertices along a direction.<br><br>"
                "Select two vertices to join them. Select one vertex, three or more, or two of the same sketch "
                "to draw one line from each along a global axis or a custom vector, with a length.",
            ),
        }


add_command("MaxProFrame_ParametricLine", CreateParametricLineCommand())

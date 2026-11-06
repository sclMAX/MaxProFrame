# Parametric line
# Initial author : Christophe Grellier (Chris_G)
# LGPL 2.
# Parametric line between two vertexes.
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


def _add_vertex_properties(obj):
    for name, doc in VERTEX_PROPERTIES:
        obj.addProperty(LINK_TYPE, name, "ParametricLine", doc)


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
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        _migrate_local_links(obj)

    def execute(self, obj):
        p1 = _global_vertex(obj.Vertex1)
        p2 = _global_vertex(obj.Vertex2)
        if p1 is not None and p2 is not None:
            # Drawn in the coordinates of the group holding the line.
            to_local = _group_placement(obj).inverse()
            ls = Part.LineSegment(to_local.multVec(p1), to_local.multVec(p2))
            obj.Shape = ls.toShape()
        else:
            App.Console.PrintError("{} broken !\n".format(obj.Label))


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
        verts = []
        sel = Gui.Selection.getSelectionEx()
        for selobj in sel:
            if selobj.HasSubObjects:
                for i in range(len(selobj.SubObjects)):
                    if isinstance(selobj.SubObjects[i], Part.Vertex):
                        verts.append((selobj.Object, selobj.SubElementNames[i]))
        if len(verts) == 2:
            self.make_parametric_line(verts)

    def IsActive(self):
        if App.ActiveDocument:
            verts = []
            sel = Gui.Selection.getSelectionEx()
            for selobj in sel:
                if selobj.HasSubObjects:
                    for i in range(len(selobj.SubObjects)):
                        if isinstance(selobj.SubObjects[i], Part.Vertex):
                            verts.append((selobj.Object, selobj.SubElementNames[i]))
            return len(verts) == 2
        else:
            return False

    def GetResources(self):
        return {
            "Pixmap": TOOL_ICON,
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ParametricLine", "Create a Parametric Line"),
            "Accel": "M, L",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ParametricLine",
                "Create a parametric line between two vertices.<br><br>Select two vertices, then run this command.",
            ),
        }


add_command("MaxProFrame_ParametricLine", CreateParametricLineCommand())

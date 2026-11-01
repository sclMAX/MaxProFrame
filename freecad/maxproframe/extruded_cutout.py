import glob
import math
import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import (
    get_childrens_from_extrudedcutout,
    get_profile_from_extrudedcutout,
    get_readable_cutting_angles,
    get_trimmed_profile_all_cutting_angles,
    get_trimmedprofile_from_extrudedcutout,
    length_along_normal,
)
from freecad.maxproframe.ff_tools import ICONPATH, PROFILEIMAGES_PATH, PROFILESPATH, UIPATH, translate
from freecad.maxproframe.frameforge_exceptions import FrameForgeException
from freecad.maxproframe.version import __version__ as ff_version

# Cut types, in property order: new ones go last so saved documents keep their index.
CUT_TYPES = ["Through All", "Distance", "One wall"]
# Distance below which two points along the cut direction are the same.
TOLERANCE = 1e-6
# Sample points per side of a sketch region where One wall measures the wall.
WALL_SAMPLES = 5


def _wall_samples(face):
    """Points inside ``face``: its center of mass and a grid over it, else its vertices."""
    umin, umax, vmin, vmax = face.ParameterRange
    grid = [
        face.valueAt(umin + (umax - umin) * (i + 0.5) / WALL_SAMPLES, vmin + (vmax - vmin) * (j + 0.5) / WALL_SAMPLES)
        for i in range(WALL_SAMPLES)
        for j in range(WALL_SAMPLES)
    ]
    inside = [point for point in [face.CenterOfMass] + grid if face.isInside(point, TOLERANCE, True)]
    return inside or [vertex.Point for vertex in face.Vertexes]


def _material_along(shape, points, direction):
    """For each of ``points``, the material of ``shape`` on a line along ``direction``.

    Each item is a sorted list of (start, end) distances from the point along ``direction``,
    touching pieces merged. One boolean with every line at once.
    """
    length = shape.BoundBox.DiagonalLength + max((point - shape.BoundBox.Center).Length for point in points)
    lines = Part.Compound([Part.makeLine(point - direction * length, point + direction * length) for point in points])
    segments = [[] for _ in points]
    for edge in shape.common(lines).Edges:
        ends = [vertex.Point for vertex in edge.Vertexes]
        if len(ends) != 2:
            continue

        def off_line(point):
            offset = ends[0] - point
            return (offset - direction * offset.dot(direction)).Length

        index = min(range(len(points)), key=lambda i: off_line(points[i]))
        segments[index].append(tuple(sorted((end - points[index]).dot(direction) for end in ends)))
    merged = []
    for pieces in segments:
        joined = []
        for start, end in sorted(pieces):
            if joined and start - joined[-1][1] < TOLERANCE:
                joined[-1] = (joined[-1][0], max(joined[-1][1], end))
            else:
                joined.append((start, end))
        merged.append(joined)
    return merged


def one_wall_depth(shape, face, direction):
    """How deep ``face`` cuts ``shape`` along ``direction`` to go through one wall, or None.

    The wall is the material that starts at the sketch plane, measured on lines through points
    of ``face``: its thinnest reading, so a point over a perpendicular wall (a hole across a
    corner) does not make it run through the profile, and a point over a void (an older hole)
    or off the profile is not read. The cut runs past the inner face of the wall by half the
    wall, or half the gap to the next material when it is closer. None: no wall under ``face``.
    """
    readings = []
    for pieces in _material_along(shape, _wall_samples(face), direction):
        # The first piece that reaches past the plane, starting on it (not across a void).
        wall = next(((start, end) for start, end in pieces if end > TOLERANCE), None)
        if wall is None or wall[0] > TOLERANCE:
            continue
        thickness = wall[1]
        following = [start for start, _ in pieces if start > thickness + TOLERANCE]
        gap = following[0] - thickness if following else math.inf
        readings.append((thickness, gap))
    if not readings:
        return None
    thickness, gap = min(readings)
    return thickness + min(thickness, gap) / 2


class ExtrudedCutout:
    def __init__(self, obj, sketch, selected_face):
        """Initialize the parametric Sheet Metal Cut object and add
        properties.
        """

        obj.addProperty(
            "App::PropertyString",
            "MaxProFrameVersion",
            "Profile",
            "MaxProFrame version used to create the object",
        ).MaxProFrameVersion = ff_version

        obj.addProperty(
            "App::PropertyString",
            "PID",
            "Profile",
            "Profile ID",
        ).PID = ""
        obj.setEditorMode("PID", 1)

        obj.addProperty("App::PropertyLinkSub", "baseObject", "ExtrudedCutout", "SelectedFace").baseObject = (
            selected_face
        )

        obj.addProperty(
            "App::PropertyLink",
            "Sketch",
            "ExtrudedCutout",
            translate("FrameForge", "The sketch for the cut"),
        ).Sketch = sketch

        obj.addProperty(
            "App::PropertyLength",
            "ExtrusionLength",
            "ExtrudedCutout",
            translate("FrameForge", "Length of the extrusion direction 1"),
        ).ExtrusionLength = 500.0
        obj.setEditorMode("ExtrusionLength", 2)  # Hide by default

        # CutType property
        obj.addProperty(
            "App::PropertyEnumeration", "CutType", "ExtrudedCutout", translate("FrameForge", "Cut type")
        ).CutType = list(CUT_TYPES)
        obj.CutType = "Through All"

        # related to Profile
        obj.addProperty("App::PropertyString", "Family", "Profile", "")
        obj.setEditorMode("Family", 1)

        obj.addProperty("App::PropertyString", "CatalogFamily", "Profile", "")
        obj.setEditorMode("CatalogFamily", 1)

        obj.addProperty("App::PropertyLink", "CustomProfile", "Profile", "Target profile").CustomProfile = None
        obj.setEditorMode("CustomProfile", 1)

        obj.addProperty("App::PropertyString", "SizeName", "Profile", "")
        obj.setEditorMode("SizeName", 1)

        obj.addProperty("App::PropertyString", "Material", "Profile", "")
        obj.setEditorMode("Material", 1)

        obj.addProperty("App::PropertyFloat", "ApproxWeight", "Base", "Approximate weight in Kilogram")
        obj.setEditorMode("ApproxWeight", 1)

        obj.addProperty("App::PropertyFloat", "Price", "Base", "Profile Price")
        obj.setEditorMode("Price", 1)

        # structure
        obj.addProperty("App::PropertyLength", "Width", "Structure", "Parameter for structure")
        obj.addProperty("App::PropertyLength", "Height", "Structure", "Parameter for structure")
        obj.addProperty("App::PropertyLength", "Length", "Structure", "Parameter for structure")
        obj.addProperty("App::PropertyBool", "Cutout", "Structure", "Has Cutout").Cutout = True
        obj.setEditorMode("Width", 1)  # user doesn't change !
        obj.setEditorMode("Height", 1)
        obj.setEditorMode("Length", 1)
        obj.setEditorMode("Cutout", 1)

        obj.addProperty(
            "App::PropertyString",
            "CuttingAngleA",
            "Structure",
            "Cutting Angle A",
        )
        obj.setEditorMode("CuttingAngleA", 1)
        obj.addProperty(
            "App::PropertyString",
            "CuttingAngleB",
            "Structure",
            "Cutting Angle B",
        )
        obj.setEditorMode("CuttingAngleB", 1)

        obj.Proxy = self

    def onDocumentRestored(self, obj):
        """Cutouts saved before One wall gain it, keeping their cut type."""
        if obj.getEnumerationsOfProperty("CutType") != CUT_TYPES:
            current = obj.CutType
            obj.CutType = list(CUT_TYPES)
            obj.CutType = current

    def onChanged(self, fp, prop):
        """Respond to property changes."""
        if prop == "CutType":
            if fp.CutType == "Distance":
                fp.setEditorMode("ExtrusionLength", 0)  # Show
            else:
                fp.setEditorMode("ExtrusionLength", 2)  # Hide

    def execute(self, fp):
        """Perform the cut when the object is recomputed."""
        try:
            # Ensure the Sketch and baseObject properties are valid.
            if fp.Sketch is None or fp.baseObject is None:
                raise FrameForgeException("Both the Sketch and baseObject properties must be set.")

            # hide trimmed body
            for tb in get_childrens_from_extrudedcutout(fp.baseObject[0]):
                tb.ViewObject.Visibility = False

            cutSketch = fp.Sketch
            selected_object, face_name = fp.baseObject

            face_name = face_name[0]
            selected_face = selected_object.Shape.getElement(face_name)
            normal_vector = selected_face.normalAt(0, 0)

            # Create face from sketch: only closed wires bound a cut.
            myFacesList = [Part.Face(wire) for wire in cutSketch.Shape.Wires if wire.isClosed()]

            if not myFacesList:
                # An empty sketch, or one still being drawn, leaves the body uncut.
                fp.Shape = selected_object.Shape.copy()
                self._update_structure_data(fp)
                return

            if fp.CutType == "One wall":
                # Each region goes through the wall under it, as deep as that wall.
                tools = []
                for face in myFacesList:
                    depth = one_wall_depth(selected_object.Shape, face, -normal_vector)
                    if depth is not None:
                        tools.append(face.extrude(-normal_vector * depth))
                if not tools:
                    fp.Shape = selected_object.Shape.copy()
                    self._update_structure_data(fp)
                    return
                extruded_shape = Part.Compound(tools)
            else:
                if fp.CutType == "Distance":
                    ExtLength = fp.ExtrusionLength.Value
                else:
                    skCenter = cutSketch.Shape.BoundBox.Center
                    objCenter = selected_object.Shape.BoundBox.Center
                    distance = skCenter - objCenter
                    TotalLength = selected_object.Shape.BoundBox.DiagonalLength + distance.Length

                    ExtLength = TotalLength

                compFaces = Part.Compound(myFacesList)

                # Extrusion
                extruded_shape = compFaces.extrude(-normal_vector * ExtLength)

            # Soustraction (Cut)
            cut_shape = selected_object.Shape.cut(extruded_shape)

            # Assigne la forme au FeaturePython
            fp.Shape = cut_shape

            self._update_structure_data(fp)

        except FrameForgeException as e:
            App.Console.PrintError(f"Error: {e}\n")

    def _update_structure_data(self, obj):
        prof = get_profile_from_extrudedcutout(obj)
        trim_prof = get_trimmedprofile_from_extrudedcutout(obj)
        if trim_prof:
            angles = get_trimmed_profile_all_cutting_angles(trim_prof)
        else:
            angles = ()

        obj.PID = str(prof.PID)
        obj.Width = prof.ProfileWidth
        obj.Height = prof.ProfileHeight
        obj.Family = prof.Family
        if not hasattr(obj, "CatalogFamily"):
            obj.addProperty("App::PropertyString", "CatalogFamily", "Profile", "")
            obj.setEditorMode("CatalogFamily", 1)
        cat_fam = getattr(prof, "CatalogFamily", None)
        obj.CatalogFamily = cat_fam if cat_fam is not None else getattr(prof, "Family", "")
        obj.CustomProfile = prof.CustomProfile
        obj.SizeName = prof.SizeName
        obj.Material = prof.Material
        obj.ApproxWeight = prof.ApproxWeight
        obj.Price = prof.Price

        obj.Length = length_along_normal(trim_prof if trim_prof else prof)

        cut_angles = get_readable_cutting_angles(
            getattr(prof, "BevelACutY", "N/A"),
            getattr(prof, "BevelACutX", "N/A"),
            getattr(prof, "BevelBCutY", "N/A"),
            getattr(prof, "BevelBCutX", "N/A"),
            *angles,
        )

        obj.CuttingAngleA = cut_angles[0]
        obj.CuttingAngleB = cut_angles[1]


class ViewProviderExtrudedCutout:
    """Part WB style ViewProvider."""

    def __init__(self, obj):
        """Set this object to the proxy object of the actual view provider"""
        obj.Proxy = self

    def attach(self, vobj):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.ViewObject = vobj
        self.Object = vobj.Object
        return

    def updateData(self, fp, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes."""
        modes = []
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "FlatLines"

    def setDisplayMode(self, mode):
        """Map the display mode defined in attach with those defined in getDisplayModes.
        Since they have the same names nothing needs to be done. This method is optional.
        """
        return mode

    def claimChildren(self):
        childrens = [self.Object.baseObject[0], self.Object.Sketch]
        if len(childrens) > 0:
            for child in childrens:
                if child:
                    # if hasattr("ViewObject", child)
                    child.ViewObject.Visibility = False
        return childrens

    def onChanged(self, vp, prop):
        pass

    def onDelete(self, fp, sub):
        if self.Object.baseObject:
            self.Object.baseObject[0].ViewObject.Visibility = True
        if self.Object.Sketch:
            self.Object.Sketch.ViewObject.Visibility = True
        return True

    def __getstate__(self):
        """When saving the document this object gets stored using Python's cPickle module.
        Since we have some un-pickable here -- the Coin stuff -- we must define this method
        to return a tuple of all pickable objects or None.
        """
        return None

    def __setstate__(self, state):
        """When restoring the pickled object from document we have the chance to set some
        internals here. Since no data were pickled nothing needs to be done here.
        """
        return None

    def setEdit(self, vobj, mode):
        if mode != 0:
            return None

        import freecad.maxproframe.create_extruded_cutout_tool

        taskd = freecad.maxproframe.create_extruded_cutout_tool.CreateExtrudedCutoutTaskPanel(self.Object)
        Gui.Control.showDialog(taskd)
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None

        Gui.Control.closeDialog()
        return True

    def edit(self):
        FreeCADGui.ActiveDocument.setEdit(self.Object, 0)

    def getIcon(self):
        return """
        /* XPM */
            static char *profile[] = {
            /* columns rows colors chars-per-pixel */
            "15 16 15 1 ",
            "  c None",
            ". c #343636",
            "X c #53595F",
            "o c #303A4E",
            "O c #2A4A73",
            "+ c #31465A",
            "@ c #615954",
            "# c #AC6F35",
            "$ c #FFC400",
            "% c None",
            "& c #315F9B",
            "* c #5E6D84",
            "= c #E2A19F",
            "- c #E5D8D6",
            "; c #B8ADAC",
            /* pixels */
            "               ",
            "      Xo.      ",
            "    .o&&&o.    ",
            "    oOO&&&OX   ",
            " .o.o&&OO&&Oo  ",
            " X-;+O+OOO+##. ",
            " X---;#oOO#$#  ",
            " X--==-ooO%$#  ",
            " X===--#o+%$#  ",
            " X=-=-=#+O%$#  ",
            " X=-===*&O%$@  ",
            " X====-@o+#o.  ",
            " .;-==-o XX    ",
            "  .@--;o       ",
            "    X*@X       ",
            "     ..        "
            };

        """

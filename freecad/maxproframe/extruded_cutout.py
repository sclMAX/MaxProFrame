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
# Pitch of a new pattern side, cutouts a pattern side adds and cutouts a cutout makes at most.
DEFAULT_PITCH = 50.0
MAX_COUNT = 1000
MAX_CUTOUTS = 1000
# Prefixes of the pattern properties of a cutout: a count and a pitch on each side of the sketch.
PATTERN_SIDES = ("AlongBackward", "AlongForward")


def axis_positions(backward, forward, at_point):
    """Positions of the holes on one axis from the point: ``backward`` and ``forward`` are (count, pitch).

    Backward first, from the farthest; then 0 when ``at_point``; then forward, from the nearest.
    """
    (backward_count, backward_pitch), (forward_count, forward_pitch) = backward, forward
    return (
        [-index * backward_pitch for index in range(backward_count, 0, -1)]
        + ([0.0] if at_point else [])
        + [index * forward_pitch for index in range(1, forward_count + 1)]
    )


def _pattern_tips():
    return {
        "AlongBackwardCount": translate(
            "frameforge", "Cutouts the pattern adds before the sketch, toward the start of the profile path"
        ),
        "AlongBackwardPitch": translate("frameforge", "Distance between the cutouts before the sketch"),
        "AlongForwardCount": translate(
            "frameforge", "Cutouts the pattern adds after the sketch, toward the end of the profile path"
        ),
        "AlongForwardPitch": translate("frameforge", "Distance between the cutouts after the sketch"),
    }


def _add_pattern_properties(obj):
    """Add the pattern properties ``obj`` has not got: no cutout on either side of the sketch."""
    tips = _pattern_tips()
    for side in PATTERN_SIDES:
        if not hasattr(obj, f"{side}Count"):
            obj.addProperty("App::PropertyIntegerConstraint", f"{side}Count", "ExtrudedCutout", tips[f"{side}Count"])
            setattr(obj, f"{side}Count", (0, 0, MAX_COUNT, 1))
        if not hasattr(obj, f"{side}Pitch"):
            obj.addProperty("App::PropertyLength", f"{side}Pitch", "ExtrudedCutout", tips[f"{side}Pitch"])
            setattr(obj, f"{side}Pitch", DEFAULT_PITCH)


def pattern_count(sides):
    """Number of cutouts of the pattern ``sides`` ({side: (count, pitch)}), the sketch included."""
    return 1 + sum(count for count, _ in sides.values())


def pattern_sides(fp):
    """{side: (count, pitch)} of the cutout ``fp``; no cutout on either side before it is restored."""
    if not hasattr(fp, "AlongForwardCount"):
        return {side: (0, DEFAULT_PITCH) for side in PATTERN_SIDES}
    return {side: (getattr(fp, f"{side}Count"), getattr(fp, f"{side}Pitch").Value) for side in PATTERN_SIDES}


def pattern_offsets(sides):
    """Offsets of the cutouts from the sketch toward the end of the profile path, 0 for the sketch.

    Raise when there are more than MAX_CUTOUTS.
    """
    total = pattern_count(sides)
    if total > MAX_CUTOUTS:
        raise FrameForgeException(
            translate("frameforge", "Cutout / Hole: the pattern makes {} cutouts, at most {}.").format(
                total, MAX_CUTOUTS
            )
        )
    return axis_positions(sides["AlongBackward"], sides["AlongForward"], True)


def path_direction(normal, axis):
    """Unit direction on the plane of ``normal`` toward the end of the path of a profile extruded along ``axis``."""
    along = axis - normal * axis.dot(normal)
    if along.Length < TOLERANCE:
        raise FrameForgeException(
            translate(
                "frameforge", "Cutout / Hole: the face is square to the profile axis, the pattern has no direction."
            )
        )
    # A profile is attached at the end of its path and extruded back to its start: its path runs against
    # its ``axis``.
    return -along.normalize()


def along_extent(shape, direction):
    """(min, max) distance of ``shape`` along the unit ``direction``, from the origin."""
    # Turned about the origin so ``direction`` is X: the distances along it are the X of the exact box.
    rotation = App.Rotation(direction, App.Vector(1, 0, 0))
    turned = shape.copy()
    turned.rotate(App.Vector(), rotation.Axis, math.degrees(rotation.Angle))
    box = turned.optimalBoundingBox(False)
    return box.XMin, box.XMax


def pattern_extents(fp):
    """((min, max) of the cut regions of the sketch, (min, max) of the face) of the cutout ``fp``, along the path.

    None when there is nothing to measure: no closed region, a face or a profile no longer found.
    Raise FrameForgeException on a face square to the profile axis: the pattern has no direction.
    """
    if fp.Sketch is None or not fp.baseObject:
        return None
    wires = [wire for wire in fp.Sketch.Shape.Wires if wire.isClosed()]
    if not wires or get_profile_from_extrudedcutout(fp) is None:
        return None
    try:
        _, face = cut_face(fp)
    except FrameForgeException:
        # A face name the body no longer has, after a change of its shape, or no face name at all.
        return None
    direction = profile_path_direction(fp, face.normalAt(0, 0))
    return along_extent(Part.Compound(wires), direction), along_extent(face, direction)


def cut_face(fp):
    """(body, face) the cutout ``fp`` is drawn on.

    Raise FrameForgeException when the link names no face, or the body no longer has the face, after a
    change of its shape.
    """
    base, face_names = fp.baseObject
    if not face_names:
        raise FrameForgeException(translate("frameforge", "Cutout / Hole: no face to cut."))
    face_name = face_names[0]
    try:
        return base, base.Shape.getElement(face_name)
    except (IndexError, ValueError, Part.OCCError) as error:
        raise FrameForgeException(
            translate("frameforge", "Cutout / Hole: {} no longer has the face {}.").format(base.Label, face_name)
        ) from error


def profile_path_direction(fp, normal):
    """path_direction on the face of normal ``normal`` of the cutout ``fp``."""
    profile = get_profile_from_extrudedcutout(fp)
    # Profiles are extruded along their local Z.
    return path_direction(normal, profile.Placement.Rotation.multVec(App.Vector(0, 0, 1)))


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
    readings = _wall_readings(shape, face, direction)
    if not readings:
        return None
    thickness, gap = min(readings)
    return thickness + min(thickness, gap) / 2


def wall_thickness(shape, face):
    """Thickness of the wall of ``shape`` under its own planar ``face``, or None without a wall."""
    readings = _wall_readings(shape, face, -face.normalAt(0, 0))
    return min(readings)[0] if readings else None


def _wall_readings(shape, face, direction):
    """(thickness, gap to the next material) of the wall starting at ``face``, per point of ``face``."""
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
    return readings


def cut_tools(shape, faces, direction, cut_type, distance, center):
    """The solids that cut ``faces`` into ``shape`` along ``direction``, or None when none does.

    ``distance`` is the depth of a Distance cut; ``center`` is where the faces are, for Through All.
    """
    if cut_type == "One wall":
        # Each region goes through the wall under it, as deep as that wall.
        tools = []
        for face in faces:
            depth = one_wall_depth(shape, face, direction)
            if depth is not None:
                tools.append(face.extrude(direction * depth))
        return Part.Compound(tools) if tools else None
    if cut_type == "Distance":
        length = distance
    else:
        length = shape.BoundBox.DiagonalLength + (center - shape.BoundBox.Center).Length
    return Part.Compound(faces).extrude(direction * length)


def _uncut_shape(shape):
    """A copy of ``shape`` with its placement moved into its geometry.

    During a recompute FreeCAD replaces the placement of an assigned shape by the cutout's own
    (identity) Placement, as it does for the result of a cut.
    """
    uncut = shape.copy()
    placement = uncut.Placement
    uncut.Placement = App.Placement()
    # Copied: without a copy a rigid transform only sets the location again.
    uncut.transformShape(placement.toMatrix(), True)
    return uncut


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

        self.add_pattern_properties(obj)

        obj.Proxy = self

    def add_pattern_properties(self, obj):
        """The pattern of the sketch along the profile (see pattern_offsets)."""
        _add_pattern_properties(obj)

    def onDocumentRestored(self, obj):
        """Cutouts saved before One wall gain it, keeping their cut type; those saved before the pattern gain it."""
        if obj.getEnumerationsOfProperty("CutType") != CUT_TYPES:
            current = obj.CutType
            obj.CutType = list(CUT_TYPES)
            obj.CutType = current
        self.add_pattern_properties(obj)

    def onChanged(self, fp, prop):
        """Respond to property changes."""
        if prop == "CutType":
            if fp.CutType == "Distance":
                fp.setEditorMode("ExtrusionLength", 0)  # Show
            else:
                fp.setEditorMode("ExtrusionLength", 2)  # Hide

    def execute(self, fp):
        """Perform the cut when the object is recomputed."""
        # Out of the try below: too many cutouts fail the recompute, as a drill hole does.
        offsets = pattern_offsets(pattern_sides(fp))
        # Out of the try too: a face the body no longer has, and a pattern on a face square to the profile
        # axis, an end face, which has no direction.
        direction = None
        if fp.baseObject:
            _, face = cut_face(fp)
            if len(offsets) > 1:
                direction = profile_path_direction(fp, face.normalAt(0, 0))
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
                fp.Shape = _uncut_shape(selected_object.Shape)
                self._update_structure_data(fp)
                return

            center = cutSketch.Shape.BoundBox.Center
            if direction is not None:
                myFacesList = [face.translated(direction * offset) for offset in offsets for face in myFacesList]
                center = Part.Compound(myFacesList).BoundBox.Center

            extruded_shape = cut_tools(
                selected_object.Shape,
                myFacesList,
                -normal_vector,
                fp.CutType,
                fp.ExtrusionLength.Value,
                center,
            )
            if extruded_shape is None:
                fp.Shape = _uncut_shape(selected_object.Shape)
                self._update_structure_data(fp)
                return

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

    def setupContextMenu(self, vobj, menu):
        """Edit sketch: open the sketch of the cutout in the Sketcher."""
        sketch = vobj.Object.Sketch
        action = menu.addAction(translate("frameforge", "Edit sketch"))
        action.setObjectName("edit_cutout_sketch")
        action.setEnabled(sketch is not None)
        if sketch is None:
            return
        if getattr(sketch, "ViewObject", None) is not None:
            action.setIcon(sketch.ViewObject.Icon)
        doc_name, name = sketch.Document.Name, sketch.Name

        def edit_sketch():
            from freecad.maxproframe.create_extruded_cutout_tool import _edit_sketch

            _edit_sketch(doc_name, name)

        action.triggered.connect(edit_sketch)

    def getIcon(self):
        """The icon of the Cutout / Hole command, so the tree tells cutouts apart from profiles and trims."""
        return os.path.join(ICONPATH, "cutout-hole.svg")

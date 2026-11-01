import BOPTools.SplitAPI
import FreeCAD as App
import FreeCADGui as Gui
import Part

from freecad.maxproframe._utils import (
    get_childrens_from_trimmedbody,
    get_profile_from_trimmedbody,
    get_readable_cutting_angles,
    get_trimmed_profile_all_cutting_angles,
    length_along_normal,
)
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.miter_geometry import TOLERANCE, Member, MiterError, MiterPlane, miter_plane
from freecad.maxproframe.version import __version__ as ff_version

# TrimmedProfileType -> TrimmedProfile method giving (body shape, cut shapes).
JOINTS = {"Notch": "_notch", "End Miter": "_end_miter", "Extend Cut": "_extend_cut"}
# Distance, in mm, within which the profile axis still counts as crossing a target face.
CROSSING_TOLERANCE = 1e-4


class TrimmedProfile:
    def __init__(self, obj):
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

        obj.addProperty(
            "App::PropertyLink", "TrimmedBody", "TrimmedProfile", translate("App::Property", "Body to be trimmed")
        ).TrimmedBody = None
        obj.addProperty(
            "App::PropertyLinkSubList",
            "TrimmingBoundary",
            "TrimmedProfile",
            translate("App::Property", "Bodies that define boundaries"),
        ).TrimmingBoundary = None

        obj.addProperty(
            "App::PropertyEnumeration",
            "TrimmedProfileType",
            "TrimmedProfile",
            translate("App::Property", "TrimmedProfile Type"),
        ).TrimmedProfileType = ["Notch", "End Miter", "Extend Cut"]
        obj.addProperty(
            "App::PropertyBool",
            "MiterExtend",
            "TrimmedProfile",
            translate("App::Property", "Extend the profile up to the miter plane"),
        ).MiterExtend = True
        obj.addProperty(
            "App::PropertyLength",
            "MiterGap",
            "TrimmedProfile",
            translate("App::Property", "Distance left between the two miter cut faces"),
        ).MiterGap = 0
        obj.addProperty(
            "App::PropertyLength",
            "TrimGap",
            "TrimmedProfile",
            translate("App::Property", "Distance left between the profile end and the target plane"),
        ).TrimGap = 0

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
        obj.addProperty("App::PropertyBool", "Cutout", "Structure", "Has Cutout").Cutout = False
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

    def onChanged(self, fp, prop):
        pass

    def execute(self, fp):
        if fp.TrimmedBody is None:
            return
        if len(fp.TrimmingBoundary) == 0:
            return

        # One method per joint type: a new joint adds a method instead of growing a chain of cases.
        joint = getattr(self, JOINTS[fp.TrimmedProfileType])
        body_shape, cut_shapes = joint(fp, fp.TrimmedBody.Shape)

        cut_shape = Part.Shape()
        if len(cut_shapes) > 0:
            cut_shape = Part.Shape(cut_shapes[0])
            for sh in cut_shapes[1:]:
                cut_shape = cut_shape.fuse(sh)

        self.makeShape(fp, cut_shape, body_shape)
        self._update_structure_data(fp)

    def _notch(self, fp, body_shape):
        """(body, cut shapes) of a Notch: the target splits the body, the piece reaching the far end stays."""
        target = fp.TrimmingBoundary[0][0]
        member = self._miter_member(fp.TrimmedBody)
        # The far end section may lie in a piece an earlier trim removed: the nearest piece stays.
        far_section = member.section_at(self._far_end_is_start(member, target))
        pieces = BOPTools.SplitAPI.slice(body_shape, [target.Shape], mode="Split").Solids
        kept = min(range(len(pieces)), key=lambda index: pieces[index].distToShape(far_section)[0], default=None)
        return body_shape, [Part.Shape(piece) for index, piece in enumerate(pieces) if index != kept]

    def _end_miter(self, fp, body_shape):
        """(body, cut shapes) of an End Miter: the body is extended up to each miter plane when asked."""
        planes = [plane.shifted(fp.MiterGap.Value / 2.0) for plane in self.miter_planes(fp)]
        if fp.MiterExtend:
            for plane in planes:
                extension = plane.extension()
                if extension is not None:
                    body_shape = body_shape.fuse(extension)
            body_shape = body_shape.removeSplitter()
        return body_shape, [plane.removal_volume(body_shape) for plane in planes]

    def _extend_cut(self, fp, body_shape):
        """(body, cut shapes) of an Extend Cut: the body always ends on the target plane, gap included."""
        plane = self.extend_cut_plane(fp)
        extension = plane.extension(tool=translate("frameforge", "Extend / Cut"))
        if extension is not None:
            body_shape = body_shape.fuse(extension).removeSplitter()
        return body_shape, [plane.removal_volume(body_shape)]

    def extend_cut_plane(self, fp):
        """Plane the moving end of an Extend Cut ends on, moved by the gap, its normal towards the kept end."""
        member = self._miter_member(fp.TrimmedBody)
        # A whole target is linked with an empty sub-element name.
        target, subs = fp.TrimmingBoundary[0]
        if subs and subs[0]:
            face = target.getSubObject(subs[0])
            if not isinstance(face, Part.Face) or not isinstance(face.Surface, Part.Plane):
                raise MiterError(
                    translate("frameforge", "Extend / Cut: the target face {} of {} is not planar.").format(
                        subs[0], target.Label
                    )
                )
            origin, normal = face.CenterOfMass, face.normalAt(0, 0)
        else:
            origin, normal = self._crossed_face(member, target)

        ends = [member.end(at_start)[2] for at_start in (True, False)]
        axis = ends[1] - ends[0]
        axis.normalize()
        if abs(normal.dot(axis)) < TOLERANCE:
            raise MiterError(translate("frameforge", "Extend / Cut: the target plane is parallel to the profile axis."))
        # The end nearest the plane moves; the other one, the far end, stays.
        at_start = abs((ends[0] - origin).dot(normal)) <= abs((ends[1] - origin).dot(normal))
        far = ends[1] if at_start else ends[0]
        if normal.dot(far - origin) < 0:
            normal = -normal
        _, inward, _ = member.end(at_start)
        plane = MiterPlane(origin, normal, inward, member.section_at(at_start))
        return plane.shifted(fp.TrimGap.Value)

    def _far_end_is_start(self, member, target):
        """Whether the far end of ``member``, the axis end farthest from ``target``, is its start."""
        start, end = (target.Shape.distToShape(Part.Vertex(member.end(at_start)[2]))[0] for at_start in (True, False))
        return start >= end

    def _crossed_face(self, member, target):
        """(point, normal) of the planar face of ``target`` the axis crosses first, seen from the far end."""
        ends = [member.end(at_start)[2] for at_start in (True, False)]
        far = ends[0] if self._far_end_is_start(member, target) else ends[1]
        axis = ends[1] - ends[0]
        axis.normalize()
        crossed = []
        for face in target.Shape.Faces:
            if not isinstance(face.Surface, Part.Plane):
                continue
            point, normal = face.CenterOfMass, face.normalAt(0, 0)
            along = normal.dot(axis)
            # Only faces looking at the far end, crossed by the axis line, count.
            if abs(along) < TOLERANCE or normal.dot(far - point) <= 0:
                continue
            crossing = far + axis * (normal.dot(point - far) / along)
            if face.isInside(crossing, CROSSING_TOLERANCE, True):
                crossed.append(((crossing - far).Length, point, normal))
        if not crossed:
            raise MiterError(
                translate("frameforge", "Extend / Cut: the profile axis crosses no face of {}.").format(target.Label)
            )
        _, point, normal = min(crossed, key=lambda item: item[0])
        return point, normal

    def miter_planes(self, fp):
        """One miter plane per trimming boundary, from the real profile positions."""
        member = self._miter_member(fp.TrimmedBody)
        return [miter_plane(member, self._miter_member(bound[0])) for bound in fp.TrimmingBoundary]

    def _miter_member(self, body):
        target = self.getTarget(body)
        edge = target[0].getSubObject(target[1][0])
        return Member(edge, get_profile_from_trimmedbody(body).Shape)

    def _update_structure_data(self, obj):
        prof = get_profile_from_trimmedbody(obj)
        angles = get_trimmed_profile_all_cutting_angles(obj)

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

        obj.Length = length_along_normal(obj)

        cut_angles = get_readable_cutting_angles(
            getattr(prof, "BevelACutY", "N/A"),
            getattr(prof, "BevelACutX", "N/A"),
            getattr(prof, "BevelBCutY", "N/A"),
            getattr(prof, "BevelBCutX", "N/A"),
            *angles,
        )

        obj.CuttingAngleA = cut_angles[0]
        obj.CuttingAngleB = cut_angles[1]

    def makeShape(self, fp, cutshape, shape=None):
        if shape is None:
            shape = fp.TrimmedBody.Shape
        if not cutshape.isNull():
            fp.Shape = shape.cut(cutshape)
        else:
            fp.Shape = shape
            App.Console.PrintWarning(
                translate("frameforge", "{}: no trimming face cuts the profile, it is left uncut.\n").format(fp.Label)
            )

    def getTarget(self, link):
        while True:
            if hasattr(link, "Target"):
                return link.Target
            elif hasattr(link, "TrimmedProfileType"):
                link = link.TrimmedBody
            elif getattr(link, "baseObject", None):
                link = link.baseObject[0]
            else:
                raise RuntimeError(f"{getattr(link, 'Name', link)} is not a profile or a trimmed profile.")


class ViewProviderTrimmedProfile:
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
        # App.Console.PrintMessage("Change {} property: {}\n".format(str(fp), str(prop)))
        if prop == "TrimmedBody":
            if fp.TrimmedBody:
                self.ViewObject.ShapeColor = fp.TrimmedBody.ViewObject.ShapeColor
                # The trim replaces its body in the 3D view.
                for body in get_childrens_from_trimmedbody(fp.TrimmedBody):
                    body.ViewObject.Visibility = False
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
        return [self.Object.TrimmedBody]

    def onChanged(self, vp, prop):
        """Print the name of the property that has changed"""
        # App.Console.PrintMessage("Change {} property: {}\n".format(str(vp), str(prop)))
        pass

    def onDelete(self, fp, sub):
        if self.Object.TrimmedBody:
            self.Object.TrimmedBody.ViewObject.Visibility = True
        return True

    def getIcon(self):
        """Return the icon in XMP format which will appear in the tree view. This method is optional
        and if not defined a default icon is shown.
        """
        return """
        	/* XPM */
                static char * corner_xpm[] = {
                "16 16 4 1",
                " 	c None",
                ".	c #000000",
                "+	c #3465A4",
                "@	c #ED2B00",
                "         ..     ",
                "       ..++..   ",
                "   .....+++++.  ",
                " ..@@@@@.+++... ",
                " .@.@@@@@.+.++. ",
                " .@@.@...@.+++. ",
                " .@@@.@@@@.+++. ",
                " .@@@.@@@@.+++. ",
                " ..@@.@@@@....  ",
                " .+.@.@@...     ",
                " .++....++.     ",
                " .+++.++++.     ",
                " .+++.++++.     ",
                "  .++.++++.     ",
                "   .+.+...      ",
                "    ...         "};
        	"""

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

        if self.Object.TrimmedProfileType == "End Miter":
            import freecad.maxproframe.create_end_miter_tool

            taskd = freecad.maxproframe.create_end_miter_tool.EndMiterTaskPanel(edited=self.Object)
            Gui.Control.showDialog(taskd)
            return True

        from freecad.maxproframe import create_extend_cut_tool

        if self.Object.TrimmedProfileType == "Notch":
            from freecad.maxproframe import create_notch_tool

            panel = create_notch_tool.NotchTaskPanel(edited=self.Object)
        else:
            panel = create_extend_cut_tool.ExtendCutTaskPanel(edited=self.Object)
        # The panel listens to clicks: they change the target.
        create_extend_cut_tool.show_panel(panel)
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None

        Gui.Control.closeDialog()
        return True

    def edit(self):
        Gui.ActiveDocument.setEdit(self.Object, 0)

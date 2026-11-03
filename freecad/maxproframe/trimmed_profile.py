import os

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
from freecad.maxproframe.ff_tools import ICONPATH, translate
from freecad.maxproframe.miter_geometry import TOLERANCE, Member, MiterError, MiterPlane, miter_plane, real_stretch
from freecad.maxproframe.version import __version__ as ff_version

# TrimmedProfileType -> TrimmedProfile method giving (body shape, cut shapes).
JOINTS = {"Notch": "_notch", "End Miter": "_end_miter", "Extend Cut": "_extend_cut"}
# TrimmedProfileType -> tree icon: the icon of the command making that joint.
JOINT_ICONS = {"Notch": "corner-notch.svg", "End Miter": "corner-end-miter.svg", "Extend Cut": "corner-end-trim.svg"}
# Distance, in mm, within which the profile axis still counts as crossing a target face.
CROSSING_TOLERANCE = 1e-4
# KeepEnd values: the automatic rule, or the axis end whose piece stays when the target crosses the profile.
AUTO, START, END = "Auto", "Start", "End"
KEEP_ENDS = [AUTO, START, END]


def _between(ends, origin, normal):
    """Whether the plane through ``origin`` with ``normal`` lies strictly between the two ``ends``."""
    start, end = ((point - origin).dot(normal) for point in ends)
    return start * end < 0 and min(abs(start), abs(end)) > TOLERANCE


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
        self.add_keep_end(obj)

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

    @staticmethod
    def add_keep_end(obj):
        """Add KeepEnd, set to Auto: trims saved before it existed lack it and behave as Auto."""
        obj.addProperty(
            "App::PropertyEnumeration",
            "KeepEnd",
            "TrimmedProfile",
            translate(
                "App::Property", "Piece kept when the target crosses the profile: Auto, or the one reaching this end"
            ),
        ).KeepEnd = KEEP_ENDS

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
        far_section = member.section_at(self._notch_kept_start(fp, member, target))
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
        far_start, origin, normal, _ = self._extend_cut_side(member, fp.TrimmingBoundary[0], self._chosen_far_start(fp))
        far = member.end(far_start)[2]
        if normal.dot(far - origin) < 0:
            normal = -normal
        at_start = not far_start
        _, inward, _ = member.end(at_start)
        plane = MiterPlane(origin, normal, inward, member.section_at(at_start))
        return plane.shifted(fp.TrimGap.Value)

    def kept_end(self, fp, boundary=None, keep_end=None):
        """(whether the piece kept by ``fp`` reaches the axis start, whether the target lets KeepEnd choose).

        ``boundary`` (a TrimmingBoundary item) and ``keep_end`` stand for the values of ``fp`` when given.
        The target lets KeepEnd choose only while it crosses the profile between its ends: otherwise
        one piece makes sense and the Auto rule keeps it.
        """
        member = self._miter_member(fp.TrimmedBody)
        boundary = fp.TrimmingBoundary[0] if boundary is None else boundary
        chosen = self._chosen_far_start(fp) if keep_end is None else {START: True, END: False}.get(keep_end)
        if fp.TrimmedProfileType == "Extend Cut":
            far_start, _, _, choosable = self._extend_cut_side(member, boundary, chosen)
            return far_start, choosable
        target = boundary[0]
        far_start = self._far_end_is_start(member, target)
        choosable = self._target_crosses(member, target)
        return (chosen if choosable and chosen is not None else far_start), choosable

    def _notch_kept_start(self, fp, member, target):
        """Whether the piece a Notch keeps reaches the axis start; only a chosen end needs the crossing test."""
        chosen = self._chosen_far_start(fp)
        if chosen is not None and self._target_crosses(member, target):
            return chosen
        return self._far_end_is_start(member, target)

    def _chosen_far_start(self, fp):
        """Whether KeepEnd keeps the start (True) or the end (False); None for Auto or a trim saved without it."""
        return {START: True, END: False}.get(getattr(fp, "KeepEnd", AUTO))

    def _extend_cut_side(self, member, boundary, chosen):
        """(far end is start, plane point, plane normal, whether KeepEnd can choose) of an Extend Cut.

        ``chosen`` is the end KeepEnd keeps (True for the start), or None for Auto.
        """
        # A whole target is linked with an empty sub-element name.
        target, subs = boundary
        if subs and subs[0]:
            face = target.getSubObject(subs[0])
            if not isinstance(face, Part.Face) or not isinstance(face.Surface, Part.Plane):
                raise MiterError(
                    translate("frameforge", "Extend / Cut: the target face {} of {} is not planar.").format(
                        subs[0], target.Label
                    )
                )
            point, face_normal = face.CenterOfMass, face.normalAt(0, 0)

            def plane_seen_from(far_start):
                return point, face_normal

        else:

            def plane_seen_from(far_start):
                return self._crossed_face(member, target, far_start)

        ends = [member.end(at_start)[2] for at_start in (True, False)]
        axis = ends[1] - ends[0]
        axis.normalize()
        # A whole target gives the face seen from the end farthest from it.
        origin, normal = plane_seen_from(subs and subs[0] or self._far_end_is_start(member, target))
        if abs(normal.dot(axis)) < TOLERANCE:
            raise MiterError(translate("frameforge", "Extend / Cut: the target plane is parallel to the profile axis."))
        # The end nearest the plane moves; the other one, the far end, stays.
        far_start = abs((ends[0] - origin).dot(normal)) > abs((ends[1] - origin).dot(normal))

        # Only a plane between the two ends leaves two pieces to choose from.
        try:
            other_origin, other_normal = plane_seen_from(not far_start)
        except MiterError:
            other_origin = None
        choosable = other_origin is not None and _between(ends, other_origin, other_normal)
        if choosable and chosen == (not far_start):
            far_start, origin, normal = not far_start, other_origin, other_normal
        return far_start, origin, normal, choosable

    def _target_crosses(self, member, target):
        """Whether the part of ``target`` in the path of the profile section lies strictly between its ends.

        The section is filled: an end in the hollow of a tube target is inside the target.
        """
        ends = [member.end(at_start)[2] for at_start in (True, False)]
        axis = ends[1] - ends[0]
        length = axis.Length
        axis.normalize()
        section = member.section_at(True)
        if not section.Faces:
            return False
        # A prism one millimetre past each end tells a target reaching past an end.
        outline = Part.Face(section.Faces[0].OuterWire).translated(axis * -1.0)
        inside = target.Shape.common(outline.extrude(axis * (length + 2.0)))
        if inside.isNull() or inside.Volume < CROSSING_TOLERANCE:
            return False
        # Along the axis: the start at Z = 0, the end at Z = length.
        to_axis = App.Placement(App.Vector(), App.Rotation(axis, App.Vector(0, 0, 1)))
        to_axis = to_axis.multiply(App.Placement(-ends[0], App.Rotation()))
        box = inside.transformed(to_axis.toMatrix()).optimalBoundingBox()
        return box.ZMin > CROSSING_TOLERANCE and box.ZMax < length - CROSSING_TOLERANCE

    def _far_end_is_start(self, member, target):
        """Whether the far end of ``member``, the axis end farthest from ``target``, is its start."""
        start, end = (target.Shape.distToShape(Part.Vertex(member.end(at_start)[2]))[0] for at_start in (True, False))
        return start >= end

    def _crossed_face(self, member, target, far_start):
        """(point, normal) of the planar face of ``target`` the axis crosses first, seen from the far end."""
        ends = [member.end(at_start)[2] for at_start in (True, False)]
        far = ends[0] if far_start else ends[1]
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
        member = self._stretch_member(fp.TrimmedBody)
        return [miter_plane(member, self._stretch_member(bound[0])) for bound in fp.TrimmingBoundary]

    def _miter_member(self, body):
        target = self.getTarget(body)
        edge = target[0].getSubObject(target[1][0])
        return Member(edge, get_profile_from_trimmedbody(body).Shape)

    def _stretch_member(self, body):
        """The member of ``body`` along its real stretch: End Miter meets bodies where they end, trims included."""
        target = self.getTarget(body)
        edge = target[0].getSubObject(target[1][0])
        profile_shape = get_profile_from_trimmedbody(body).Shape
        return Member(real_stretch(edge, body.Shape, profile_shape), profile_shape)

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
        elif prop == "TrimmedProfileType" and hasattr(self.ViewObject, "signalChangeIcon"):
            self.ViewObject.signalChangeIcon()
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
        """The icon of the command making this joint, so the tree tells Extend / Cut, Notch and End Miter apart."""
        joint = getattr(getattr(self, "Object", None), "TrimmedProfileType", None)
        return os.path.join(ICONPATH, JOINT_ICONS.get(joint, JOINT_ICONS["Extend Cut"]))

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

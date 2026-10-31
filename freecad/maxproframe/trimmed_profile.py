import glob
import math
import os

import ArchCommands
import BOPTools.SplitAPI
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import (
    get_childrens_from_trimmedbody,
    get_profile_from_trimmedbody,
    get_readable_cutting_angles,
    get_trimmed_profile_all_cutting_angles,
    length_along_normal,
)
from freecad.maxproframe.ff_tools import ICONPATH, PROFILEIMAGES_PATH, PROFILESPATH, UIPATH, translate
from freecad.maxproframe.miter_geometry import Member, miter_plane
from freecad.maxproframe.version import __version__ as ff_version


def add_miter_properties(obj, extend):
    """Add MiterExtend and MiterGap when missing; miters made before them did not extend."""
    if not hasattr(obj, "MiterExtend"):
        obj.addProperty(
            "App::PropertyBool",
            "MiterExtend",
            "TrimmedProfile",
            translate("App::Property", "Extend the profile up to the miter plane"),
        ).MiterExtend = extend
    if not hasattr(obj, "MiterGap"):
        obj.addProperty(
            "App::PropertyLength",
            "MiterGap",
            "TrimmedProfile",
            translate("App::Property", "Distance left between the two miter cut faces"),
        ).MiterGap = 0


class TrimmedProfile:
    def __init__(self, obj):
        obj.addProperty(
            "App::PropertyString",
            "FrameforgeVersion",
            "Profile",
            "Frameforge Version used to create the profile",
        ).FrameforgeVersion = ff_version

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
        ).TrimmedProfileType = ["End Trim", "End Miter"]
        obj.addProperty(
            "App::PropertyEnumeration", "CutType", "TrimmedProfile", translate("App::Property", "Cut Type")
        ).CutType = [
            "Perfect fit",
            "Simple fit",
        ]
        add_miter_properties(obj, extend=True)

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
        """Print a short message when doing a recomputation, this method is mandatory"""
        self.run_compatibility_migrations(fp)

        # TODO: Put these methods in proper functions
        if fp.TrimmedBody is None:
            return
        if len(fp.TrimmingBoundary) == 0:
            return

        # hide trimmed body
        for tb in get_childrens_from_trimmedbody(fp.TrimmedBody):
            tb.ViewObject.Visibility = False

        cut_shapes = []
        body_shape = fp.TrimmedBody.Shape

        if fp.TrimmedProfileType == "End Trim":
            if fp.CutType in ["Perfect fit", "Coped cut"]:  # Keeping Coped cut for retro-compatibility
                shapes = [x[0].Shape for x in fp.TrimmingBoundary]
                shps = BOPTools.SplitAPI.slice(fp.TrimmedBody.Shape, shapes, mode="Split")
                for solid in shps.Solids:
                    x = fp.TrimmedBody.Shape.CenterOfGravity.x
                    y = fp.TrimmedBody.Shape.CenterOfGravity.y
                    z = fp.TrimmedBody.Shape.CenterOfGravity.z
                    if not solid.BoundBox.isInside(x, y, z):
                        cut_shapes.append(Part.Shape(solid))

            elif fp.CutType in ["Simple fit", "Simple cut"]:  # Keeping Simple cut for retro-compatibility
                cut_shape = Part.Shape()
                for link in fp.TrimmingBoundary:
                    part = link[0]
                    for sub in link[1]:
                        face = part.getSubObject(sub)
                        if isinstance(face.Surface, Part.Plane):
                            shp = self.getOutsideCV(face, fp.TrimmedBody.Shape)
                            cut_shapes.append(shp)

        elif fp.TrimmedProfileType == "End Miter":
            gap = fp.MiterGap.Value if hasattr(fp, "MiterGap") else 0.0
            planes = [plane.shifted(gap / 2.0) for plane in self.miter_planes(fp)]
            if getattr(fp, "MiterExtend", False):
                for plane in planes:
                    extension = plane.extension()
                    if extension is not None:
                        body_shape = body_shape.fuse(extension)
                body_shape = body_shape.removeSplitter()
            for plane in planes:
                cut_shapes.append(plane.removal_volume(body_shape))

        cut_shape = Part.Shape()
        if len(cut_shapes) > 0:
            cut_shape = Part.Shape(cut_shapes[0])
            for sh in cut_shapes[1:]:
                cut_shape = cut_shape.fuse(sh)

        self.makeShape(fp, cut_shape, body_shape)
        self._update_structure_data(fp)

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

    def run_compatibility_migrations(self, obj):
        if not hasattr(obj, "FrameforgeVersion"):
            # migrate parents
            for link in obj.TrimmingBoundary:
                proxy = getattr(link[0], "Proxy", None)
                execute = getattr(proxy, "execute", None)
                if callable(execute):
                    execute(link[0])
            obj.TrimmedBody.Proxy.execute(obj.TrimmedBody)

            App.Console.PrintMessage(f"Frameforge::object migration : Migrate {obj.Label} to 0.1.8\n")

            def add_missing_property(prop_type, name, group, description=""):
                # Partial migrations may already contain some or all fields.
                # Keep their values; new properties use FreeCAD's type defaults.
                if not hasattr(obj, name):
                    obj.addProperty(prop_type, name, group, description)
                obj.setEditorMode(name, 1)

            # related to Profile
            add_missing_property("App::PropertyString", "PID", "Profile", "Profile ID")
            add_missing_property("App::PropertyString", "Family", "Profile")
            add_missing_property("App::PropertyLink", "CustomProfile", "Profile", "Target profile")
            add_missing_property("App::PropertyString", "SizeName", "Profile")
            add_missing_property("App::PropertyString", "Material", "Profile")
            add_missing_property("App::PropertyFloat", "ApproxWeight", "Base", "Approximate weight in Kilogram")
            add_missing_property("App::PropertyFloat", "Price", "Base", "Profile Price")

            # structure
            add_missing_property("App::PropertyLength", "Width", "Structure", "Parameter for structure")
            add_missing_property("App::PropertyLength", "Height", "Structure", "Parameter for structure")
            add_missing_property("App::PropertyLength", "Length", "Structure", "Parameter for structure")
            add_missing_property("App::PropertyBool", "Cutout", "Structure", "Has Cutout")
            add_missing_property("App::PropertyString", "CuttingAngleA", "Structure", "Cutting Angle A")
            add_missing_property("App::PropertyString", "CuttingAngleB", "Structure", "Cutting Angle B")

            # add version
            obj.addProperty(
                "App::PropertyString",
                "FrameforgeVersion",
                "Profile",
                "Frameforge Version used to create the profile",
            ).FrameforgeVersion = ff_version

    def getOutsideCV(self, cutplane, shape):
        cv = ArchCommands.getCutVolume(cutplane, shape, clip=False, depth=0.0)
        if cv[1].isInside(shape.CenterOfGravity, 0.001, False):
            cv = cv[2]
        else:
            cv = cv[1]
        return cv

    def makeShape(self, fp, cutshape, shape=None):
        if shape is None:
            shape = fp.TrimmedBody.Shape
        if not cutshape.isNull():
            fp.Shape = shape.cut(cutshape)
        else:
            # TODO: Do something when cutshape is Null
            print("cut_shape is Null")

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
        else:
            import freecad.maxproframe.create_trimmed_profiles_tool

            taskd = freecad.maxproframe.create_trimmed_profiles_tool.CreateTrimmedProfileTaskPanel(
                self.Object, mode="edition"
            )
        Gui.Control.showDialog(taskd)
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None

        Gui.Control.closeDialog()
        return True

    def edit(self):
        Gui.ActiveDocument.setEdit(self.Object, 0)

"""Document-free section geometry, sharing the extrusion builder verbatim."""

from types import SimpleNamespace

import FreeCAD as App

from freecad.maxproframe.profile import Profile
from freecad.maxproframe.version import __version__


def build_section_face(parameters, custom_face=None):
    """Build an unmirrored, bottom-left section from a detached property snapshot.

    Do not instantiate a zero-length Profile: its legacy face path drops bores
    and does not support all aluminium families. No FreeCAD document is needed.
    """
    if parameters.get("Family") == "Custom Profile" and custom_face is None:
        return None
    values = dict(Family="", FrameforgeVersion=__version__, ProfileWidth=0.,
                  ProfileHeight=0., Thickness=0., ThicknessFlange=0., RadiusLarge=0.,
                  RadiusSmall=0., MakeFillet=False, LipLength=0.)
    values.update(parameters)
    if custom_face is not None:
        values["CustomProfile"] = SimpleNamespace(Shape=custom_face.copy())
    # Only inert values reach execute; never pass a live document object through.
    values.update(ProfileLength=0., OffsetA=0., OffsetB=0., LinearWeight=0.,
                  UnitPrice=0., Placement=App.Placement(), AnchorX="Left", AnchorY="Bottom",
                  BevelACutY=0., BevelACutX=0., BevelBCutY=0., BevelBCutX=0.)
    proxy = Profile.__new__(Profile)
    proxy.bevels_combined = False
    return proxy.execute(SimpleNamespace(**values), _section_only=True)

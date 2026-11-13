"""Folded Corner: one corner of a Folded Bar, a document object of its own (odd/tasks/folded-corners.md, S10).

A Folded Corner is where two tubes of a bar meet, named by the two profiles they are made from (``PieceA`` and
``PieceB``, ``folded_chain.base_profile``): a trim, cutout or drill hole made on one of them later keeps the corner.
It holds how that corner bends (``unfolded_geometry.CornerSettings``): its outer radius, the clearance of its notch,
its key and the key diameter (0: the default one), its K-factor (0: automatic, DIN 6935), and its joint: ``Miter`` or
``Stepped``, with the step depth (0: automatic) and the step flip (odd/tasks/stepped-corners.md, S1, S5, S6). ``Open``
marks the corner where a closed frame stays open: the bar starts and ends there, it does not fold; its joint, clearance
and step settings are the ones of the bar's ends there. It has no shape; its bar links it, so changing it recomputes
the bar. A corner saved before a property existed gets it, with its default, when its document opens (``Joint``:
``Miter``, so it folds as before).
"""

import os

from freecad.maxproframe.ff_tools import ICONPATH, place_in_container_of, translate
from freecad.maxproframe.unfolded_geometry import JOINTS, MITER, CornerSettings
from freecad.maxproframe.version import __version__ as ff_version

# Corner property -> CornerSettings field.
SETTINGS_PROPERTIES = {
    "OuterRadius": "outer_radius",
    "Clearance": "clearance",
    "Key": "key",
    "KeyDiameter": "key_diameter",
    "KFactor": "k_factor",
    "Joint": "joint",
    "StepDepth": "step_depth",
    "StepFlip": "step_flip",
}


def _add(obj, kind, name, group, tooltip, value=None):
    """Add the property ``name`` to ``obj`` with ``value`` unless it has it: a corner saved before keeps its values."""
    if name in obj.PropertiesList:
        return
    obj.addProperty(kind, name, group, tooltip)
    if value is not None:
        setattr(obj, name, value)


def is_folded_corner(obj):
    """A Folded Corner: one corner of a Folded Bar."""
    return (
        getattr(obj, "TypeId", "") == "App::FeaturePython"
        and "PieceA" in obj.PropertiesList
        and "OuterRadius" in obj.PropertiesList
    )


def corner_key(obj):
    """The corner ``obj`` by the names of its two profiles, whatever their order; None when one is missing."""
    if obj is None or obj.PieceA is None or obj.PieceB is None:
        return None
    return frozenset((obj.PieceA.Name, obj.PieceB.Name))


def corner_settings(obj):
    """The ``CornerSettings`` the corner object ``obj`` holds."""
    return CornerSettings(
        outer_radius=float(obj.OuterRadius.Value),
        clearance=float(obj.Clearance.Value),
        key=bool(obj.Key),
        key_diameter=float(obj.KeyDiameter.Value),
        k_factor=float(obj.KFactor),
        joint=str(obj.Joint),
        step_depth=float(obj.StepDepth.Value),
        step_flip=bool(obj.StepFlip),
    )


def set_corner_settings(obj, settings):
    """Give the corner object ``obj`` the values of ``settings``; a property that already has it is left alone."""
    for prop, field in SETTINGS_PROPERTIES.items():
        value = getattr(settings, field)
        current = getattr(obj, prop)
        current = current.Value if hasattr(current, "Value") else current
        if isinstance(value, bool) or isinstance(current, bool):
            if bool(current) != bool(value):
                setattr(obj, prop, bool(value))
        elif isinstance(value, str) or isinstance(current, str):
            if str(current) != str(value):
                setattr(obj, prop, str(value))
        elif abs(float(current) - float(value)) > 1e-12:
            setattr(obj, prop, float(value))


class FoldedCorner:
    def __init__(self, obj):
        self.add_properties(obj)
        obj.Proxy = self

    @staticmethod
    def add_properties(obj):
        _add(
            obj, "App::PropertyString", "MaxProFrameVersion", "Base",
            "MaxProFrame version used to create the object", ff_version,
        )  # fmt: skip
        obj.setEditorMode("MaxProFrameVersion", 1)
        _add(
            obj, "App::PropertyLink", "PieceA", "Corner",
            translate("App::Property", "Profile of one of the two tubes meeting at the corner"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLink", "PieceB", "Corner",
            translate("App::Property", "Profile of the other tube meeting at the corner"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyBool", "Open", "Corner",
            translate("App::Property", "Where a closed frame stays open: the bar starts and ends here, unfolded"),
            False,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "OuterRadius", "Bend",
            translate("App::Property", "Radius seen outside the bend; the inside radius is it less the wall thickness"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyFloat", "KFactor", "Bend",
            translate(
                "App::Property",
                "Where the neutral axis sits in the wall: 0 < K <= 1; 0: automatic, from DIN 6935",
            ),
            0.0,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "Clearance", "Notch",
            translate("App::Property", "Gap between the notch flanks and around the key, half on each side"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyBool", "Key", "Notch", translate("App::Property", "Interlocking key in the notch"), True
        )
        _add(
            obj, "App::PropertyLength", "KeyDiameter", "Notch",
            translate(
                "App::Property",
                "Diameter of the key, a half circle on the miter line; 0: a quarter of the tube depth across the "
                "bent wall",
            ),
        )  # fmt: skip
        if "Joint" not in obj.PropertiesList:
            _add(
                obj, "App::PropertyEnumeration", "Joint", "Notch",
                translate(
                    "App::Property",
                    "How the inner wall is cut: Miter, at half the bend angle (a bevel cut); Stepped, an interlock of "
                    "straight cuts only",
                ),
                list(JOINTS),
            )  # fmt: skip
            obj.Joint = MITER
        _add(
            obj, "App::PropertyLength", "StepDepth", "Notch",
            translate(
                "App::Property",
                "Depth of the step of a Stepped joint across the bent wall; 0: automatic, the larger of the wall "
                "thickness and the outer corner radius of the tube",
            ),
        )  # fmt: skip
        _add(
            obj, "App::PropertyBool", "StepFlip", "Notch",
            translate("App::Property", "Swap the tubes of a Stepped joint: the other one covers the step"),
            False,
        )  # fmt: skip

    def onDocumentRestored(self, obj):
        self.add_properties(obj)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderFoldedCorner:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(ICONPATH, "FoldedBar.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def make_folded_corner(container_of, piece_a, piece_b, settings, open_corner=False):
    """A Folded Corner between the profiles ``piece_a`` and ``piece_b`` bent with ``settings`` (``CornerSettings``).

    It joins the folder or Part holding ``container_of`` (its bar), as the bar joins the one of its first piece.
    ``open_corner``: the corner where a closed frame stays open.
    """
    doc = container_of.Document
    obj = doc.addObject("App::FeaturePython", "FoldedCorner")
    # Before it links anything: a Part receiving it would pull in what it links.
    place_in_container_of(obj, container_of)
    FoldedCorner(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderFoldedCorner(obj.ViewObject)
    obj.Label = f"Corner_{piece_a.Label}_{piece_b.Label}"
    obj.PieceA = piece_a
    obj.PieceB = piece_b
    obj.Open = bool(open_corner)
    set_corner_settings(obj, settings)
    return obj

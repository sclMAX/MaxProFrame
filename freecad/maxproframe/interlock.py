"""Interlock: locating shapes between the two faces of a joint, a document object of its own (odd/tasks/joint-tabs.md,
S1, S2, S7).

An Interlock names a folded corner of a Folded Bar by the two profiles meeting there (``PieceA`` and ``PieceB``,
``folded_chain.base_profile``), as a Folded Corner does: a trim, cutout or drill hole made on one of them later keeps
it. Its ``Kind`` is one of ``interlock_geometry.KINDS``, and it holds the settings of that kind: ``Fingers`` (S3, S4),
the fingers at the inner vertex of the corner (``Count``, ``FingerWidth``, ``Tip``, ``TipSize``, ``Depth``,
``Clearance``, ``Flip``). It has no shape; its bar lists it in ``Interlocks``, so changing it recomputes the bar, and
the bar refuses an Interlock on none of its folded corners or a second one on a corner (``folded_bar``). An Interlock
saved before a property existed gets it, with its default, when its document opens. A later kind adds its group of
properties and its branch in ``interlock_settings``; the links, the bar and the two-face picking stay.

The kind ``Tabs`` (odd/tasks/t-joint-tabs.md, T2) joins a crossbar (``PieceA``) to the rail it butts against
(``PieceB``) at a T joint, with the Fingers fields again and the tab ``Length`` (0: Automatic, the rail wall
thickness). It remembers its two faces (``CrossbarFace``, ``RailFace``, each one's plane local to the profile of its
tube) and no bar lists it: its tabs and slots are two pieces of their own that link it (``tab_interlock``), removed with
it (``unsetupObject``).
"""

import os

from freecad.maxproframe.ff_tools import ICONPATH, place_in_container_of, translate
from freecad.maxproframe.folded_chain import base_profile
from freecad.maxproframe.interlock_geometry import FINGERS, KINDS, SQUARE, TABS, TIPS, FingerSettings, TabSettings
from freecad.maxproframe.version import __version__ as ff_version

# What a double click on an Interlock opens: a callable taking the Interlock, set by its command (joint-tabs.md, T3);
# while None, a double click does nothing.
EDIT_PANEL = None

# Interlock property -> FingerSettings field.
FINGER_PROPERTIES = {
    "Count": "count",
    "FingerWidth": "finger_width",
    "Tip": "tip",
    "TipSize": "tip_size",
    "Depth": "depth",
    "Clearance": "clearance",
    "Flip": "flip",
}
# Interlock property -> TabSettings field: the Fingers fields again (S3), and the tab Length (S4).
TAB_PROPERTIES = {
    "Count": "count",
    "FingerWidth": "tab_width",
    "Tip": "tip",
    "TipSize": "tip_size",
    "Length": "length",
    "Clearance": "clearance",
}
# What a Tabs Interlock remembers of each of its two faces: the piece and face (a link), and the face plane (point,
# normal) and the anchor shift of the section when it was picked, local to the profile of the tube
# (odd/tasks/t-joint-tabs.md, T2).
TAB_SIDES = ("Crossbar", "Rail")
# The properties only one kind uses, hidden on an Interlock of the other kind.
KIND_ONLY = {
    FINGERS: ("Depth", "Flip"),
    TABS: ("Length", *(f"{side}{name}" for side in TAB_SIDES for name in ("Face", "Point", "Normal", "Anchor"))),
}
# The pieces of a Tabs Interlock (``tab_interlock``) carry its link in ``Interlock`` and their role here.
TABS_ROLE, SLOTS_ROLE = "Tabs", "Slots"


def _add(obj, kind, name, group, tooltip, value=None):
    """Add the property ``name`` to ``obj`` with ``value`` unless it has it: an interlock saved before keeps its
    values."""
    if name in obj.PropertiesList:
        return
    obj.addProperty(kind, name, group, tooltip)
    if value is not None:
        setattr(obj, name, value)


def is_interlock(obj):
    """An Interlock: locating shapes at a corner of a Folded Bar."""
    return (
        getattr(obj, "TypeId", "") == "App::FeaturePython"
        and "PieceA" in obj.PropertiesList
        and "Kind" in obj.PropertiesList
    )


def interlock_key(obj):
    """The corner of the interlock ``obj`` by the names of its two profiles, whatever their order; None when one is
    missing (as ``folded_corner.corner_key``)."""
    if obj is None or obj.PieceA is None or obj.PieceB is None:
        return None
    return frozenset((obj.PieceA.Name, obj.PieceB.Name))


def interlock_pieces(obj):
    """The pieces of the Tabs Interlock ``obj`` that link it: its tabs and its slots (``tab_interlock``)."""
    return [
        piece
        for piece in getattr(obj, "InList", ())
        if "InterlockRole" in piece.PropertiesList and getattr(piece, "Interlock", None) == obj
    ]


def interlock_settings(obj):
    """The settings of the kind of the interlock ``obj``: a ``FingerSettings`` (``CornerSettings.interlock``) or a
    ``TabSettings``; a Tabs Interlock saved before ``Length`` existed has its Automatic length."""
    kind = str(obj.Kind)
    if kind == TABS:
        return TabSettings(
            count=int(obj.Count),
            tab_width=float(obj.FingerWidth.Value),
            tip=str(obj.Tip),
            tip_size=float(obj.TipSize.Value),
            length=float(obj.Length.Value) if "Length" in obj.PropertiesList else 0.0,
            clearance=float(obj.Clearance.Value),
        )
    if kind == FINGERS:
        return FingerSettings(
            count=int(obj.Count),
            finger_width=float(obj.FingerWidth.Value),
            tip=str(obj.Tip),
            tip_size=float(obj.TipSize.Value),
            depth=float(obj.Depth.Value),
            clearance=float(obj.Clearance.Value),
            flip=bool(obj.Flip),
        )
    raise ValueError(f"Unknown interlock {kind!r}: give one of {', '.join(KINDS)}.")


def show_kind_properties(obj):
    """Hide on ``obj`` the properties of the kinds it is not; read-only, the faces a Tabs Interlock remembers."""
    kind = str(getattr(obj, "Kind", FINGERS))
    for other, names in KIND_ONLY.items():
        for name in names:
            if name not in obj.PropertiesList:
                continue
            mode = [] if other == kind else ["Hidden"]
            if name.endswith(("Point", "Normal", "Anchor")):
                mode = ["ReadOnly", "Hidden"]
            elif name.endswith("Face"):
                mode = mode + ["ReadOnly"]
            if sorted(obj.getEditorMode(name)) != sorted(mode):
                obj.setEditorMode(name, mode)


class Interlock:
    def __init__(self, obj):
        self.add_properties(obj)
        obj.Proxy = self
        show_kind_properties(obj)

    @staticmethod
    def add_properties(obj):
        _add(
            obj, "App::PropertyString", "MaxProFrameVersion", "Base",
            "MaxProFrame version used to create the object", ff_version,
        )  # fmt: skip
        obj.setEditorMode("MaxProFrameVersion", 1)
        _add(
            obj, "App::PropertyLink", "PieceA", "Interlock",
            translate("App::Property", "Profile of one of the two tubes the interlock joins"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLink", "PieceB", "Interlock",
            translate("App::Property", "Profile of the other tube the interlock joins"),
        )  # fmt: skip
        if "Kind" not in obj.PropertiesList:
            _add(
                obj, "App::PropertyEnumeration", "Kind", "Interlock",
                translate("App::Property", "Shape of the interlock: Fingers, at the inner vertex of a folded corner"),
                list(KINDS),
            )  # fmt: skip
            obj.Kind = FINGERS
        _add(
            obj, "App::PropertyInteger", "Count", "Fingers",
            translate("App::Property", "Number of fingers, at least 2; the first tube owns the first finger"),
            3,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "FingerWidth", "Fingers",
            translate(
                "App::Property",
                "Width of every finger but the two outermost, centered; 0: the fingers split the tube evenly",
            ),
        )  # fmt: skip
        if "Tip" not in obj.PropertiesList:
            _add(
                obj, "App::PropertyEnumeration", "Tip", "Fingers",
                translate("App::Property", "Corners of each finger tip: Square, Chamfer or Round, to lead it in"),
                list(TIPS),
            )  # fmt: skip
            obj.Tip = SQUARE
        _add(
            obj, "App::PropertyLength", "TipSize", "Fingers",
            translate("App::Property", "Chamfer leg or radius of the finger tip corners, in the inner wall plane"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "Depth", "Fingers",
            translate(
                "App::Property",
                "Depth of the finger band across the bent wall; 0: automatic, the step depth of a Stepped joint",
            ),
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "Clearance", "Fingers",
            translate("App::Property", "Gap between every pair of mating finger faces, half on each side"),
        )  # fmt: skip
        _add(
            obj, "App::PropertyBool", "Flip", "Fingers",
            translate("App::Property", "Swap the tubes: the second one owns the first finger"),
            False,
        )  # fmt: skip
        _add(
            obj, "App::PropertyLength", "Length", "Tabs",
            translate(
                "App::Property",
                "How far the tabs go across the rail wall, along its normal; 0: automatic, the rail wall thickness",
            ),
        )  # fmt: skip
        for side, tooltip in zip(
            TAB_SIDES,
            (
                translate("App::Property", "Crossbar piece and face that carry the tabs"),
                translate("App::Property", "Rail piece and face the slots go through"),
            ),
        ):
            _add(obj, "App::PropertyLinkSubGlobal", f"{side}Face", "Tabs", tooltip)
            for name in ("Point", "Normal", "Anchor"):
                _add(
                    obj, "App::PropertyVector", f"{side}{name}", "Tabs",
                    "Face plane and section anchor when the face was picked, local to the profile",
                )  # fmt: skip

    def onDocumentRestored(self, obj):
        """An Interlock saved before a kind or a property existed gets it; it stays as it was otherwise."""
        touched = "Touched" in obj.State
        self.add_properties(obj)
        if obj.getEnumerationsOfProperty("Kind") != list(KINDS):
            kind = obj.Kind
            obj.Kind = list(KINDS)
            obj.Kind = kind
        show_kind_properties(obj)
        if not touched:
            obj.purgeTouched()

    def onChanged(self, obj, prop):
        if prop == "Kind":
            show_kind_properties(obj)

    def unsetupObject(self, obj):
        """A Tabs Interlock leaves the document (not by undo): its tabs and slots go with it, the pieces under them
        given back (``tab_interlock``)."""
        for piece in interlock_pieces(obj):
            if piece.Document is not None and piece.Document.getObject(piece.Name) is piece:
                piece.Document.removeObject(piece.Name)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderInterlock:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(ICONPATH, "Interlock.svg")

    def doubleClicked(self, vobj):
        """Edit the interlock when its panel exists (``EDIT_PANEL``); else unhandled."""
        if EDIT_PANEL is None:
            return False
        import FreeCADGui as Gui

        Gui.getDocument(vobj.Object.Document.Name).setEdit(vobj.Object.Name, 0)
        return True

    def setEdit(self, vobj, mode):
        """Double-click or Edit: the Interlock panel on this interlock (``EDIT_PANEL``), when it exists."""
        if mode != 0:
            return None
        if EDIT_PANEL is None:
            return False
        import FreeCADGui as Gui

        if Gui.Control.activeDialog():
            import FreeCAD as App

            App.Console.PrintMessage("MaxProFrame: close the active task dialog before editing an interlock.\n")
            return False
        EDIT_PANEL(vobj.Object)
        return True

    def unsetEdit(self, vobj, mode):
        if mode != 0:
            return None
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


def make_interlock(bar, piece_a, piece_b, **values):
    """An Interlock of the Folded Bar ``bar`` at the corner between the pieces ``piece_a`` and ``piece_b``.

    It links their profiles (``base_profile``: a trim, cutout or drill hole made on one later keeps it), takes
    ``values`` by property name (``Count=5``, ``Tip="Chamfer"``), joins the folder or Part holding ``bar`` and is
    appended to its ``Interlocks``. Recompute the document to fold it into the bar.
    """
    doc = bar.Document
    obj = doc.addObject("App::FeaturePython", "Interlock")
    # Before it links anything: a Part receiving it would pull in what it links.
    place_in_container_of(obj, bar)
    Interlock(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderInterlock(obj.ViewObject)
    piece_a, piece_b = base_profile(piece_a) or piece_a, base_profile(piece_b) or piece_b
    obj.Label = f"Interlock_{piece_a.Label}_{piece_b.Label}"
    obj.PieceA = piece_a
    obj.PieceB = piece_b
    for name, value in values.items():
        setattr(obj, name, value)
    bar.Interlocks = [*bar.Interlocks, obj]
    return obj

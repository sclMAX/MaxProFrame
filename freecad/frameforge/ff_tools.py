import os

import FreeCAD

RESSOURCESPATH = os.path.join(os.path.dirname(__file__), "resources")

PROFILESPATH = os.path.join(RESSOURCESPATH, "profiles")

ICONPATH = os.path.join(RESSOURCESPATH, "icons")
PROFILEIMAGES_PATH = os.path.join(RESSOURCESPATH, "images", "profiles")
UIPATH = os.path.join(RESSOURCESPATH, "ui")
TRANSLATIONSPATH = os.path.join(RESSOURCESPATH, "translations")


translate = FreeCAD.Qt.translate


def move_profile_to_parent_if_supported(obj, parent):
    """Keep a new profile at document root when its parent rejects its type."""
    try:
        parent.addObject(obj)
    except ValueError:
        FreeCAD.Console.PrintMessage(
            f"FrameForge: parent {parent.Label} ({parent.TypeId}) does not accept {obj.TypeId}, "
            "keeping at document root\n"
        )


class FormProxy(object):
    def __init__(self, form):
        self.members = {o: f for f in form for o in vars(f)}

    def __getattr__(self, name):
        if name not in self.members:
            raise ValueError(f"{name} not a member of one of the forms")

        return getattr(self.members[name], name)

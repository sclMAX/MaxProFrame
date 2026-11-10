import os

import FreeCAD

RESSOURCESPATH = os.path.join(os.path.dirname(__file__), "resources")

PROFILESPATH = os.path.join(RESSOURCESPATH, "profiles")

ICONPATH = os.path.join(RESSOURCESPATH, "icons")
PROFILEIMAGES_PATH = os.path.join(RESSOURCESPATH, "images", "profiles")
UIPATH = os.path.join(RESSOURCESPATH, "ui")
TRANSLATIONSPATH = os.path.join(RESSOURCESPATH, "translations")


translate = FreeCAD.Qt.translate
# Marks command texts; FreeCAD translates them with the command name as context.
QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP


def get_param_group(writable=False):
    """Returns the MaxProFrame preference group (User parameter:BaseApp/Preferences/MaxProFrame)."""
    return FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MaxProFrame")


# Every command registered by add_command, by name: what each declares, before any user customization.
COMMANDS = {}


def add_command(name, cmd_obj):
    """Register a command under the given name."""
    try:
        import FreeCADGui as Gui
    except ImportError:
        return

    Gui.addCommand(name, cmd_obj)
    COMMANDS[name] = cmd_obj


def move_profile_to_parent_if_supported(obj, parent):
    """Keep a new profile at document root when its parent rejects its type."""
    try:
        parent.addObject(obj)
    except ValueError:
        FreeCAD.Console.PrintMessage(
            f"MaxProFrame: parent {parent.Label} ({parent.TypeId}) does not accept {obj.TypeId}, "
            "keeping at document root\n"
        )


def nearest_group(obj):
    """Closest group holding obj: a folder (getParentGroup) or else a Part/Body (getParentGeoFeatureGroup)."""
    folder = obj.getParentGroup() if hasattr(obj, "getParentGroup") else None
    if folder is not None:
        return folder
    return obj.getParentGeoFeatureGroup() if hasattr(obj, "getParentGeoFeatureGroup") else None


def place_in_container_of(obj, source):
    """Put ``obj`` in the closest folder or Part/Body holding ``source``, like Create Profile does.

    Call it before ``obj`` links to anything: a Part receiving an object also pulls in every object
    reachable through its local-scope links, such as the profiles of other Parts a trim is cut against.
    An object already in that container is left alone: adding it again would drag them in as well.
    """
    group = nearest_group(source)
    if group is not None and obj not in group.Group:
        move_profile_to_parent_if_supported(obj, group)


class FormProxy(object):
    def __init__(self, form):
        self.members = {o: f for f in form for o in vars(f)}

    def __getattr__(self, name):
        if name not in self.members:
            raise ValueError(f"{name} not a member of one of the forms")

        val = getattr(self.members[name], name)
        if hasattr(val, "widget") and callable(val.widget):
            real_w = val.widget()
            if real_w is not None:
                return real_w
        return val

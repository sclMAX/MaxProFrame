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


class _PreferencesProxy:
    """
    Transparent parameter group proxy that delegates to MaxProFrame preferences
    with per-key fallback to legacy Frameforge preferences, and writes to MaxProFrame.
    """

    def __init__(self, canonical, legacy):
        self._canonical = canonical
        self._legacy = legacy

    def GetString(self, name, default=""):
        if hasattr(self._canonical, "GetString"):
            # Native GetString rejects NULs. Two distinct defaults distinguish
            # a missing key from an explicitly stored empty string without collisions.
            val = self._canonical.GetString(name, "")
            if val != "" or self._canonical.GetString(name, "_NOT_SET_") == "":
                return val
        if hasattr(self._legacy, "GetString"):
            return self._legacy.GetString(name, default)
        return default

    def GetBool(self, name, default=False):
        if hasattr(self._canonical, "GetBool"):
            b1 = self._canonical.GetBool(name, False)
            b2 = self._canonical.GetBool(name, True)
            if b1 == b2:
                return b1
        if hasattr(self._legacy, "GetBool"):
            return self._legacy.GetBool(name, default)
        return default

    def GetInt(self, name, default=0):
        if hasattr(self._canonical, "GetInt"):
            val = self._canonical.GetInt(name, -2147483647)
            if val != -2147483647:
                return val
        if hasattr(self._legacy, "GetInt"):
            return self._legacy.GetInt(name, default)
        return default

    def GetFloat(self, name, default=0.0):
        if hasattr(self._canonical, "GetFloat"):
            val = self._canonical.GetFloat(name, -1e30)
            if val != -1e30:
                return val
        if hasattr(self._legacy, "GetFloat"):
            return self._legacy.GetFloat(name, default)
        return default

    def SetString(self, name, value):
        return self._canonical.SetString(name, value)

    def SetBool(self, name, value):
        return self._canonical.SetBool(name, value)

    def SetInt(self, name, value):
        return self._canonical.SetInt(name, value)

    def SetFloat(self, name, value):
        return self._canonical.SetFloat(name, value)

    def IsEmpty(self):
        c_empty = not hasattr(self._canonical, "IsEmpty") or self._canonical.IsEmpty()
        l_empty = not hasattr(self._legacy, "IsEmpty") or self._legacy.IsEmpty()
        return c_empty and l_empty

    def __getattr__(self, item):
        return getattr(self._canonical, item)


def get_param_group(writable=False):
    """
    Returns the parameter group for MaxProFrame preferences.
    If writable is True, returns canonical User parameter:BaseApp/Preferences/MaxProFrame.
    If reading, returns a proxy with per-key fallback to legacy Frameforge parameters.
    """
    param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/MaxProFrame")
    if writable:
        return param
    legacy = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Frameforge")
    return _PreferencesProxy(param, legacy)


def add_command(name, cmd_obj):
    """
    Register a command under its canonical name and register the
    corresponding alias (MaxProFrame_* <-> FrameForge_*) for backward compatibility.
    """
    try:
        import FreeCADGui as Gui
    except ImportError:
        return

    Gui.addCommand(name, cmd_obj)
    if name.startswith("MaxProFrame_"):
        legacy_name = "FrameForge_" + name[len("MaxProFrame_") :]
        try:
            Gui.addCommand(legacy_name, cmd_obj)
        except Exception:
            pass
    elif name.startswith("FrameForge_"):
        canonical_name = "MaxProFrame_" + name[len("FrameForge_") :]
        try:
            Gui.addCommand(canonical_name, cmd_obj)
        except Exception:
            pass


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

        val = getattr(self.members[name], name)
        if hasattr(val, "widget") and callable(val.widget):
            real_w = val.widget()
            if real_w is not None:
                return real_w
        return val

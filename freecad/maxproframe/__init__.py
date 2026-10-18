"""
MaxProFrame workbench package for FreeCAD.
"""
import importlib
import sys
from importlib.abc import MetaPathFinder

from freecad.maxproframe.version import __version__


class FrameForgeRedirectFinder(MetaPathFinder):
    """
    Meta-path finder that transparently redirects legacy 'freecad.frameforge'
    imports to 'freecad.maxproframe', allowing older .FCStd files and user
    scripts to load seamlessly without 'unhandled FeaturePython' errors.
    """
    def find_spec(self, fullname, path, target=None):
        if fullname == "freecad.frameforge" or fullname.startswith("freecad.frameforge."):
            target_name = "freecad.maxproframe" + fullname[len("freecad.frameforge"):]
            target_mod = importlib.import_module(target_name)
            sys.modules[fullname] = target_mod
            if "." in fullname:
                parent_name, child_name = fullname.rsplit(".", 1)
                parent_mod = sys.modules.get(parent_name)
                if parent_mod is not None:
                    try:
                        setattr(parent_mod, child_name, target_mod)
                    except Exception:
                        pass
            return target_mod.__spec__
        return None


# Install the redirection hook once
if not any(isinstance(f, FrameForgeRedirectFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, FrameForgeRedirectFinder())

if "freecad.frameforge" not in sys.modules:
    import freecad.maxproframe as _current
    sys.modules["freecad.frameforge"] = _current
    if "freecad" in sys.modules:
        try:
            setattr(sys.modules["freecad"], "frameforge", _current)
        except Exception:
            pass

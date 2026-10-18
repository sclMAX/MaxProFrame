"""
MaxProFrame workbench package for FreeCAD.
"""
import importlib
import sys
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec

from freecad.maxproframe.version import __version__


class _AliasLoader:
    def __init__(self, target_mod):
        self.target_mod = target_mod
        self.orig_name = target_mod.__name__
        self.orig_spec = getattr(target_mod, "__spec__", None)

    def create_module(self, spec):
        return self.target_mod

    def exec_module(self, module):
        module.__name__ = self.orig_name
        module.__spec__ = self.orig_spec


class FrameForgeRedirectFinder(MetaPathFinder):
    """
    Meta-path finder that transparently redirects legacy 'freecad.frameforge'
    imports to 'freecad.maxproframe', allowing older .FCStd files and user
    scripts to load seamlessly without 'unhandled FeaturePython' errors.
    """
    def find_spec(self, fullname, path, target=None):
        if fullname == "freecad.frameforge" or fullname.startswith("freecad.frameforge."):
            target_name = "freecad.maxproframe" + fullname[len("freecad.frameforge"):]
            if target_name in sys.modules:
                target_mod = sys.modules[target_name]
            else:
                target_mod = importlib.import_module(target_name)
            return ModuleSpec(fullname, _AliasLoader(target_mod))
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

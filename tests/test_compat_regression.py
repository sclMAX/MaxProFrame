"""
Regression tests for MaxProFrame backward-compatibility bridge and preferences proxy.
"""
import importlib
import sys
import unittest
from unittest.mock import MagicMock


class TestModuleIdentityCompatibility(unittest.TestCase):
    def test_legacy_module_identity(self):
        c = importlib.import_module("freecad.maxproframe.version")
        l = importlib.import_module("freecad.frameforge.version")
        c2 = importlib.import_module("freecad.maxproframe.version")
        l2 = importlib.import_module("freecad.frameforge.version")

        self.assertIs(l, c, "Legacy import did not return canonical module instance")
        self.assertIs(c2, c, "Subsequent canonical import did not return original instance")
        self.assertIs(l2, c, "Subsequent legacy import did not return original instance")


class TestPreferencesProxyRegression(unittest.TestCase):
    def setUp(self):
        self.pref_stores = {
            "User parameter:BaseApp/Preferences/MaxProFrame": {},
            "User parameter:BaseApp/Preferences/Frameforge": {
                "Default Cut Type": "Perfect fit",
                "Group IDs": True,
                "IDs numbering type": 3,
                "Kerf": 1.75,
            },
        }

        class MockParamGroup:
            def __init__(inner_self, key):
                inner_self.key = key

            def IsEmpty(inner_self):
                return len(self.pref_stores[inner_self.key]) == 0

            def GetString(inner_self, k, default=""):
                return self.pref_stores[inner_self.key].get(k, default)

            def SetString(inner_self, k, v):
                self.pref_stores[inner_self.key][k] = v

            def GetBool(inner_self, k, default=False):
                return self.pref_stores[inner_self.key].get(k, default)

            def SetBool(inner_self, k, v):
                self.pref_stores[inner_self.key][k] = v

            def GetInt(inner_self, k, default=0):
                return self.pref_stores[inner_self.key].get(k, default)

            def SetInt(inner_self, k, v):
                self.pref_stores[inner_self.key][k] = v

            def GetFloat(inner_self, k, default=0.0):
                return self.pref_stores[inner_self.key].get(k, default)

            def SetFloat(inner_self, k, v):
                self.pref_stores[inner_self.key][k] = v

        mock_freecad = MagicMock()
        mock_freecad.ParamGet.side_effect = lambda path: MockParamGroup(path)
        self.orig_freecad = sys.modules.get("FreeCAD")
        sys.modules["FreeCAD"] = mock_freecad

    def tearDown(self):
        if self.orig_freecad is not None:
            sys.modules["FreeCAD"] = self.orig_freecad
        else:
            sys.modules.pop("FreeCAD", None)

    def test_per_key_preference_fallback_and_isolation(self):
        from freecad.maxproframe.ff_tools import get_param_group

        # 1. Partial write to MaxProFrame
        writer = get_param_group(writable=True)
        writer.SetString("Default Profile Material", "Titanium")

        # 2. Reading via reader proxy
        reader = get_param_group(writable=False)

        # Canonical key returns new value
        self.assertEqual(reader.GetString("Default Profile Material"), "Titanium")

        # Legacy keys not yet written to MaxProFrame still resolve
        self.assertEqual(reader.GetString("Default Cut Type"), "Perfect fit")
        self.assertTrue(reader.GetBool("Group IDs"))
        self.assertEqual(reader.GetInt("IDs numbering type"), 3)
        self.assertEqual(reader.GetFloat("Kerf"), 1.75)

        # 3. Overriding a legacy key in MaxProFrame updates canonical without mutating legacy
        writer.SetString("Default Cut Type", "Miter 45")
        self.assertEqual(reader.GetString("Default Cut Type"), "Miter 45")
        self.assertEqual(
            self.pref_stores["User parameter:BaseApp/Preferences/Frameforge"]["Default Cut Type"],
            "Perfect fit",
        )


if __name__ == "__main__":
    unittest.main()

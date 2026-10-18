"""Exercise preference fallback with native FreeCAD parameter groups."""
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
from freecad.maxproframe import ff_tools


class TestNativePreferenceStrings(unittest.TestCase):
    def setUp(self):
        self.name = "StringRegression_" + uuid.uuid4().hex
        self.root = "User parameter:BaseApp/Preferences/" + self.name
        self.canonical = App.ParamGet(self.root + "/canonical")
        self.legacy = App.ParamGet(self.root + "/legacy")
        self.groups = {
            "User parameter:BaseApp/Preferences/MaxProFrame": self.canonical,
            "User parameter:BaseApp/Preferences/Frameforge": self.legacy,
        }
        self.bridge = patch.object(ff_tools, "FreeCAD", SimpleNamespace(ParamGet=self.groups.__getitem__))
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        App.ParamGet("User parameter:BaseApp/Preferences").RemGroup(self.name)

    def test_native_string_reads_preserve_precedence_empty_values_and_defaults(self):
        self.canonical.SetString("canonical", "Titanium")
        self.legacy.SetString("canonical", "Steel")
        self.canonical.SetString("empty", "")
        self.legacy.SetString("empty", "must not override empty")
        self.legacy.SetString("legacy", "Perfect fit")
        self.canonical.SetString("sentinel", "_NOT_SET_")
        before = (self.canonical.GetContents(), self.legacy.GetContents())
        reader = ff_tools.get_param_group()
        for key, default, expected in (
            ("canonical", "default", "Titanium"),
            ("empty", "default", ""),
            ("legacy", "default", "Perfect fit"),
            ("missing", "fallback", "fallback"),
            ("sentinel", "fallback", "_NOT_SET_"),
            ("missing", "", ""),
        ):
            with self.subTest(key=key, default=default):
                self.assertEqual(reader.GetString(key, default), expected)
                self.assertEqual((self.canonical.GetContents(), self.legacy.GetContents()), before)

    def test_canonical_write_and_other_preference_types_remain_unchanged(self):
        self.legacy.SetString("code", "legacy")
        self.legacy.SetBool("flag", True)
        self.legacy.SetInt("count", 3)
        self.legacy.SetFloat("kerf", 1.75)
        legacy_before = self.legacy.GetContents()
        writer = ff_tools.get_param_group(writable=True)
        writer.SetString("code", "new")
        reader = ff_tools.get_param_group()
        self.assertEqual(reader.GetString("code"), "new")
        self.assertTrue(reader.GetBool("flag"))
        self.assertEqual(reader.GetInt("count"), 3)
        self.assertEqual(reader.GetFloat("kerf"), 1.75)
        self.assertEqual(self.legacy.GetContents(), legacy_before)

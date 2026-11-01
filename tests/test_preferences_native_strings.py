"""Exercise preference reads and writes with native FreeCAD parameter groups."""

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
        # Only the MaxProFrame group is mapped: any other group lookup raises KeyError.
        self.groups = {"User parameter:BaseApp/Preferences/MaxProFrame": self.canonical}
        self.bridge = patch.object(ff_tools, "FreeCAD", SimpleNamespace(ParamGet=self.groups.__getitem__))
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        App.ParamGet("User parameter:BaseApp/Preferences").RemGroup(self.name)

    def test_native_string_reads_preserve_empty_values_and_defaults(self):
        self.canonical.SetString("canonical", "Titanium")
        self.canonical.SetString("empty", "")
        self.canonical.SetString("sentinel", "_NOT_SET_")
        before = self.canonical.GetContents()
        reader = ff_tools.get_param_group()
        for key, default, expected in (
            ("canonical", "default", "Titanium"),
            ("empty", "default", ""),
            ("missing", "fallback", "fallback"),
            ("sentinel", "fallback", "_NOT_SET_"),
            ("missing", "", ""),
        ):
            with self.subTest(key=key, default=default):
                self.assertEqual(reader.GetString(key, default), expected)
                self.assertEqual(self.canonical.GetContents(), before)

    def test_canonical_write_and_other_preference_types_round_trip(self):
        writer = ff_tools.get_param_group(writable=True)
        writer.SetString("code", "new")
        writer.SetBool("flag", True)
        writer.SetInt("count", 3)
        writer.SetFloat("kerf", 1.75)
        reader = ff_tools.get_param_group()
        self.assertEqual(reader.GetString("code"), "new")
        self.assertTrue(reader.GetBool("flag"))
        self.assertEqual(reader.GetInt("count"), 3)
        self.assertEqual(reader.GetFloat("kerf"), 1.75)

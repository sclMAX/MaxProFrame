"""Whole-object selections expand to edges only for path-like sources."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher  # Registers the native sketch type.
from profile_creation_helpers import creation_panel
from PySide import QtCore, QtWidgets

from freecad.maxproframe import create_profiles_tool
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, get_param_group
from freecad.maxproframe.parametric_line import ParametricLine


class TestPathSelectionFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        language, locale, default = prefs.GetString("Language", ""), Gui.getLocale(), QtCore.QLocale()

        def restore_language():
            prefs.SetString("Language", language)
            Gui.setLocale(locale)
            Gui.updateLocale()
            QtCore.QLocale.setDefault(default)

        self.addCleanup(restore_language)
        param = get_param_group(writable=True)
        setters = {"Boolean": param.SetBool, "Integer": param.SetInt, "String": param.SetString}
        saved = param.GetContents() or []

        def restore_preferences():
            param.Clear()
            for kind, key, value in saved:
                setters.get(kind, lambda *args: None)(key, value)

        # OK stores the panel defaults.
        self.addCleanup(restore_preferences)
        self.prefs = prefs
        Gui.addLanguagePath(TRANSLATIONSPATH)
        self._language("English", "en_US")
        self.doc = App.newDocument("PathSelectionFilter")
        name = self.doc.Name
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
        App.setActiveDocument(name)
        Gui.Selection.clearSelection()
        self.addCleanup(Gui.Selection.clearSelection)
        self.panels = []
        self.addCleanup(self._close_panels)
        self.path = self.sketch("Path", [(0, 0), (100, 0)])
        self.assembly = self.doc.addObject("App::Part", "Assembly")
        self.inner = self.sketch("Inner", [(0, 0), (50, 0), (50, 50)])
        self.assembly.addObject(self.inner)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.assembly.addObject(self.body)
        base = self.body.newObject("Sketcher::SketchObject", "Base")
        points = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 0)]
        for start, end in zip(points, points[1:]):
            base.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), False)
        self.pad = self.body.newObject("PartDesign::Pad", "Pad")
        self.pad.Profile = base
        self.pad.Length = 5
        self.doc.recompute()

    def _language(self, language, default):
        self.prefs.SetString("Language", language)
        Gui.setLocale(language)
        Gui.updateLocale()
        QtCore.QLocale.setDefault(QtCore.QLocale(default))

    def _close_panels(self):
        for panel in self.panels:
            if not panel._preview_closed:
                panel.reject()
            for form in panel.form:
                form.close()

    def sketch(self, name, points):
        sketch = self.doc.addObject("Sketcher::SketchObject", name)
        for start, end in zip(points, points[1:]):
            sketch.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), False)
        self.doc.recompute()
        return sketch

    def panel(self):
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        return panel

    def edges(self, obj, names=()):
        return CreateProfileTaskPanel._selection_edges(SimpleNamespace(Object=obj, SubElementNames=list(names)))

    def test_whole_containers_solids_and_profiles_contribute_no_edges(self):
        folder = self.doc.addObject("App::DocumentObjectGroup", "Folder")
        folder.addObject(self.sketch("Loose", [(0, 0), (10, 0)]))
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        creation_panel().make_profile(self.path, "Edge1", "Profile")
        profile = self.doc.getObject("Profile")
        self.doc.recompute()
        self.assertEqual(len(profile.Shape.Solids), 1)
        for obj in (self.assembly, self.body, folder, box, self.pad, profile):
            with self.subTest(obj=obj.Name):
                self.assertEqual(self.edges(obj), [])

    def test_whole_path_sources_expand_to_all_edges(self):
        wire = self.doc.addObject("Part::Feature", "Wire")
        wire.Shape = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 10, 0)])
        box = self.doc.addObject("Part::Box", "Box")
        line = self.doc.addObject("Part::FeaturePython", "ParametricLine")
        ParametricLine(line)
        line.Vertex1 = (box, "Vertex1")
        line.Vertex2 = (box, "Vertex2")
        self.doc.recompute()
        self.assertEqual(self.edges(self.path), ["Edge1"])
        self.assertEqual(self.edges(self.inner), ["Edge1", "Edge2"])
        self.assertEqual(self.edges(wire), ["Edge1", "Edge2"])
        self.assertEqual(self.edges(line), ["Edge1"])
        # A filled sketch's display face still denotes the whole sketch.
        self.assertEqual(self.edges(self.inner, ["Face1"]), ["Edge1", "Edge2"])

    def test_explicit_solid_edges_remain_paths(self):
        self.assertEqual(self.edges(self.pad, ["Face1", "Edge5", "Vertex1"]), ["Edge5"])
        self.assertEqual(self.edges(self.box_at_root(), ["Edge2"]), ["Edge2"])

    def box_at_root(self):
        box = self.doc.addObject("Part::Box", "RootBox")
        self.doc.recompute()
        return box

    def notice(self, panel):
        label = panel.label_ignored_selection
        return None if label.isHidden() else label.text()

    def test_whole_part_selection_creates_nothing_and_explains_why(self):
        before = list(self.doc.Objects)
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name)
        panel = self.panel()
        self.assertEqual(panel._objects, {})
        self.assertEqual(panel._edge_properties, {})
        self.assertEqual(list(self.doc.Objects), before)
        self.assertEqual(self.notice(panel), "Ignored Assembly: select a sketch, wire or specific edges.")
        Gui.Selection.clearSelection()
        panel.update_selection()
        self.assertIsNone(self.notice(panel))
        self.assertEqual(list(self.doc.Objects), before)

    def test_ok_with_only_ignored_selections_warns_and_keeps_the_panel_open(self):
        before = list(self.doc.Objects)
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name)
        panel = self.panel()
        with patch.object(create_profiles_tool.QtGui, "QMessageBox") as box:
            self.assertFalse(panel.accept(defer=False))
        box.assert_called_once()
        self.assertEqual(box.call_args.args[2], "Select Edges or set Length to create a profile")
        box.return_value.exec_.assert_called_once_with()
        self.assertEqual(list(self.doc.Objects), before)
        self.assertEqual(self.notice(panel), "Ignored Assembly: select a sketch, wire or specific edges.")

    def test_explicit_pad_edge_creates_one_parametric_profile_beside_ignored_part(self):
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name)
        Gui.Selection.addSelection(self.doc.Name, self.pad.Name, "Edge1")
        self.assertEqual(
            [(s.Object, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()],
            [(self.assembly, ()), (self.pad, ("Edge1",))],
        )
        panel = self.panel()
        self.assertEqual(list(panel._objects), [(self.pad, "Edge1")])
        self.assertEqual(self.notice(panel), "Ignored Assembly: select a sketch, wire or specific edges.")
        self.assertTrue(panel.accept(defer=False))
        profile = panel._objects[(self.pad, "Edge1")]
        self.doc.recompute()
        self.assertEqual(profile.Target[0], self.pad)
        self.assertEqual(tuple(profile.Target[1]), ("Edge1",))
        self.assertAlmostEqual(profile.ProfileLength, self.pad.Shape.Edges[0].Length)
        self.assertTrue(profile.Shape.isValid())
        self.assertEqual(len(profile.Shape.Solids), 1)
        self.assertNotIn("Invalid", profile.State)
        self.assertNotIn("Error", profile.State)
        profiles = [obj for obj in self.doc.Objects if hasattr(obj, "ProfileLength")]
        self.assertEqual(profiles, [profile])

    def test_spanish_notice(self):
        self._language("Spanish", "es_ES")
        Gui.Selection.addSelection(self.doc.Name, self.body.Name)
        panel = self.panel()
        self.assertEqual(panel._objects, {})
        self.assertEqual(self.notice(panel), "Se ignoró Body: seleccioná un croquis, un alambre o aristas específicas.")


if __name__ == "__main__":
    unittest.main()

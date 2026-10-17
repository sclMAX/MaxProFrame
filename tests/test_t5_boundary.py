"""Independent T5 public chooser probes; run only in isolated native GUI state."""
import hashlib
import json
import os
import shutil
import unittest
from unittest.mock import patch
import FreeCAD as App
import FreeCADGui as Gui
import Part
import test_portable_library_profile_instantiation as helper
from freecad.frameforge import create_profiles_tool as chooser

TOPOLOGY_CONTROL = {}


def selection():
    return [(s.DocumentName, s.ObjectName, list(s.SubElementNames))
            for s in Gui.Selection.getSelectionEx()]


def files(root):
    result = {}
    for directory, _, names in os.walk(root):
        for name in names:
            path = os.path.join(directory, name)
            with open(path, "rb") as stream:
                result[os.path.relpath(path, root)] = hashlib.sha256(stream.read()).hexdigest()
    return result


class Boundary(helper.TestPortableLibraryProfileInstantiation):
    def setUp(self):
        super().setUp()
        def modal(box, *args):
            raise AssertionError("UNEXPECTED_MODAL: " + box.windowTitle() + ": " + box.text())
        self.messages.enter_context(patch.object(helper.QtWidgets.QMessageBox, "exec_", modal))
        self.panels = []
        src = self._new_doc("Source")
        a = self._create_rect_sketch(src, "A", 40, 20)
        b = self._create_rect_sketch(src, "B", 70, 30)
        self.a = self._publish_section_to_library(self.folder_lib_path, "A", a, "Section", "one")
        self.b = self._publish_section_to_library(self.folder_lib_path, "B", b, "Section", "two")
        source_name = src.Name
        App.closeDocument(source_name)
        self.project = self._new_doc("Project")
        self.p1 = self._create_line_path(self.project, "Path1", 100)
        self.p2 = self._create_line_path(self.project, "Path2", 150)
        self.project.recompute()
        self.base = {o.Name for o in self.project.Objects}
        self.pick(self.p1)

    def tearDown(self):
        for panel in self.panels:
            panel.clean()
            for form in panel.form:
                form.hide()
        super().tearDown()

    def pick(self, obj):
        App.setActiveDocument(self.project.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.project.Name, obj.Name, "Edge1")

    def panel(self, expected_volume=80000):
        panel = chooser.CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self.choose(panel, "CustomFolderLib", "Custom Profile", "A")
        self.valid(panel, expected_volume)
        return panel

    def choose(self, panel, library, family, size):
        panel.form_proxy.combo_material.setCurrentText(library)
        panel.form_proxy.combo_family.setCurrentText(family)
        panel.form_proxy.combo_size.setCurrentText(size)
        panel.proceed()

    def valid(self, panel, volume):
        self.project.recompute()
        self.assertEqual(len(panel._objects), 1)
        obj = next(iter(panel._objects.values()))
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertTrue(obj.Shape.isValid())
        self.assertEqual(len(obj.Shape.Solids), 1)
        self.assertAlmostEqual(obj.Shape.Volume, volume, places=2)
        if obj.Family == "Custom Profile":
            self.assertIsNotNone(obj.CustomProfile)
            self.assertEqual(obj.CustomProfile.Document.Name, self.project.Name)
            self.assertFalse(obj.CustomProfile.OutList)
            self.assertFalse(obj.CustomProfile.ExternalGeometry)
        return obj

    def test_selector_roundtrip_accept_reuses_exact_source(self):
        # S1/S2/S8: valid previews throughout; no stale custom link after stock.
        panel = self.panel()
        expected_selection = selection()
        source_name = self.valid(panel, 80000).CustomProfile.Name
        self.choose(panel, "CustomFolderLib", "Custom Profile", "B")
        self.valid(panel, 210000)
        self.choose(panel, "StockSteel", "Square Hollow", "40x40x2")
        stock = self.valid(panel, 30400)
        self.assertIsNone(stock.CustomProfile)
        self.choose(panel, "CustomFolderLib", "Custom Profile", "A")
        self.assertEqual(self.valid(panel, 80000).CustomProfile.Name, source_name)
        self.assertEqual(selection(), expected_selection)
        self.assertTrue(panel.accept())
        self.assertEqual(selection(), expected_selection)
        self.assertEqual(len([o for o in self.project.Objects if hasattr(o, "CustomProfile")]), 1)
        self.pick(self.p2)
        second = self.panel(expected_volume=120000)
        self.assertEqual(self.valid(second, 120000).CustomProfile.Name, source_name)
        self.assertTrue(second.accept())
        self.assertEqual(len([o for o in self.project.Objects if hasattr(o, "CustomProfile")]), 2)

    def test_path_change_repeated_preview_then_reject(self):
        # S2/S8: stale-key cleanup and complete rollback after non-vacuous imports.
        panel = self.panel()
        for path, volume in ((self.p2, 120000), (self.p1, 80000), (self.p2, 120000)):
            self.pick(path)
            before = selection()
            panel.proceed()
            self.valid(panel, volume)
            self.assertEqual(set(panel._objects), {(path, "Edge1")})
            self.assertEqual(selection(), before)
        before = selection()
        self.assertTrue(panel.reject())
        self.assertEqual({o.Name for o in self.project.Objects}, self.base)
        self.assertEqual(selection(), before)

    def test_dirty_user_asset_document_is_untouched(self):
        # S2/S8: copy a source without mutating/closing/renaming its live document.
        path = os.path.join(self.folder_lib_path, self.a[0])
        owned = App.openDocument(path)
        source = owned.getObject(self.a[1])
        owned.Label = "KEEP DIRTY USER LABEL"
        source.Label = "KEEP SKETCH LABEL"
        source.addProperty("App::PropertyString", "UserNote")
        source.UserNote = "unsaved edit"
        owned.recompute()
        source.touch()
        name = owned.Name
        raw = source.Shape.exportBrepToString()
        again = source.Shape.exportBrepToString()
        self.assertEqual(again, raw)
        control_face = helper.build_custom_section_face(source)
        self.assertTrue(control_face.isValid())
        after_validation = source.Shape.exportBrepToString()
        TOPOLOGY_CONTROL.update(raw=raw, again=again, after_validation=after_validation)
        before = (owned.Label, owned.FileName, source.Label, source.UserNote,
                  list(source.State), source.Shape.exportBrepToString(), str(source.ExpressionEngine))
        self.pick(self.p1)
        docs = set(App.listDocuments())
        disk = files(self.folder_lib_path)
        sel = selection()
        panel = self.panel()
        self.assertTrue(panel.accept())
        self.assertEqual(set(App.listDocuments()), docs)
        self.assertEqual(App.ActiveDocument.Name, self.project.Name)
        self.assertEqual(selection(), sel)
        self.assertIs(App.getDocument(name), owned)
        self.assertEqual((owned.Label, owned.FileName, source.Label, source.UserNote,
                          list(source.State), source.Shape.exportBrepToString(), str(source.ExpressionEngine)), before)
        self.assertEqual(files(self.folder_lib_path), disk)

    def test_failed_new_path_preview_is_atomic(self):
        # S2/S3/S5/S8: realistic bad manifest entries; no half-created profile.
        bad_doc = self._new_doc("BadAsset")
        bad = bad_doc.addObject("Sketcher::SketchObject", "OpenSection")
        bad.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)), False)
        bad_doc.recompute()
        bad_name = bad.Name
        bad_path = "sections/open.FCStd"
        bad_doc.saveAs(os.path.join(self.folder_lib_path, bad_path))
        doc_name = bad_doc.Name
        App.closeDocument(doc_name)
        missing_path = "sections/missing.FCStd"
        cases = [
            ({"object_name": "Absent"}, ValueError,
             "Object 'Absent' not found or is not a SketchObject in asset '" + self.a[0] + "'."),
            ({"asset_path": missing_path}, FileNotFoundError,
             "Asset file '" + os.path.join(self.folder_lib_path, missing_path) + "' does not exist."),
            ({"asset_path": "../outside.FCStd"}, ValueError,
             "Asset path contains parent directory traversal: ../outside.FCStd"),
            ({"asset_path": bad_path, "object_name": bad_name, "asset_id": "open"}, ValueError,
             "Custom profile contains open contours; all contours must be closed"),
        ]
        for change, error, text in cases:
            with self.subTest(change=change):
                self.pick(self.p1)
                panel = self.panel()
                entry = panel.profiles["CustomFolderLib"]["Custom Profile"]["sizes"]["A"]
                entry.update(change)
                self.pick(self.p2)
                names = {o.Name for o in self.project.Objects}
                objects = [(o.Name, o.Shape.exportBrepToString()) for o in self.project.Objects if hasattr(o, "Shape")]
                docs, sel, disk = set(App.listDocuments()), selection(), files(self.test_root)
                try:
                    with self.assertRaises(error) as caught:
                        panel.proceed()
                    self.assertEqual(str(caught.exception), text)
                    self.assertEqual({o.Name for o in self.project.Objects}, names)
                    self.assertEqual([(o.Name, o.Shape.exportBrepToString()) for o in self.project.Objects if hasattr(o, "Shape")], objects)
                    self.assertEqual(set(App.listDocuments()), docs)
                    self.assertEqual(selection(), sel)
                    self.assertEqual(files(self.test_root), disk)
                finally:
                    panel.reject()

    def test_provenance_root_asset_and_object_are_distinct(self):
        # S2/S3/S8: same names and IDs must not conflate distinct explicit assets.
        root_b = os.path.join(self.test_root, "OtherRoot")
        shutil.copytree(self.folder_lib_path, root_b)
        manifest = os.path.join(root_b, "library.json")
        with open(manifest) as stream:
            data = json.load(stream)
        data["_metadata"]["name"] = "OtherRoot"
        with open(manifest, "w") as stream:
            json.dump(data, stream)
        self.manager.register_folder_library(root_b)
        asset = App.openDocument(os.path.join(self.folder_lib_path, self.a[0]))
        alternate = self._create_rect_sketch(asset, "Alternate", 15, 10)
        alternate_name = alternate.Name
        asset_name = asset.Name
        asset.save()
        App.closeDocument(asset_name)
        data = self.manager.get_library("CustomFolderLib")
        data["Custom Profile"]["sizes"]["C"] = {
            "asset_path": self.a[0], "object_name": alternate_name, "asset_id": self.a[2],
            "Height": "10", "Width": "15", "Weight": "1.1775"}
        self.manager.save_folder_library(self.folder_lib_path, data)
        self.pick(self.p1)
        panel = self.panel()
        first_name = self.valid(panel, 80000).CustomProfile.Name
        self.choose(panel, "OtherRoot", "Custom Profile", "A")
        other_name = self.valid(panel, 80000).CustomProfile.Name
        self.assertNotEqual(first_name, other_name)
        self.choose(panel, "CustomFolderLib", "Custom Profile", "C")
        self.assertNotEqual(self.valid(panel, 15000).CustomProfile.Name, first_name)
        # Hand-edited portable catalog: an explicit different path with same UUID.
        sizes = panel.profiles["CustomFolderLib"]["Custom Profile"]["sizes"]
        sizes["B"]["asset_id"] = sizes["A"]["asset_id"]
        self.choose(panel, "CustomFolderLib", "Custom Profile", "B")
        second_name = self.valid(panel, 210000).CustomProfile.Name
        self.assertNotEqual(first_name, second_name)
        self.choose(panel, "CustomFolderLib", "Custom Profile", "A")
        self.assertEqual(self.valid(panel, 80000).CustomProfile.Name, first_name)
        self.assertTrue(panel.accept())


def load_tests(loader, standard_tests, pattern):
    names = (
        "test_selector_roundtrip_accept_reuses_exact_source",
        "test_path_change_repeated_preview_then_reject",
        "test_dirty_user_asset_document_is_untouched",
        "test_failed_new_path_preview_is_atomic",
        "test_provenance_root_asset_and_object_are_distinct",
    )
    return unittest.TestSuite(Boundary(name) for name in names)

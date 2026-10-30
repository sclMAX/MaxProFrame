import contextlib
import ctypes
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import test_custom_profile_selected_import as fixture

from freecad.maxproframe import create_profiles_tool as candidate
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.section_library import get_or_import_section_sketch


def sources(doc):
    return [o for o in doc.Objects if hasattr(o, "FF_Provenance")]


def snapshot(sketch):
    bb = sketch.Shape.BoundBox
    return (
        sketch.Label,
        sketch.ViewObject.ShowInTree,
        sketch.ViewObject.Visibility,
        sketch.GeometryCount,
        sketch.ConstraintCount,
        sketch.Shape.Length,
        bb.XLength,
        bb.YLength,
        bb.ZLength,
    )


class IndependentT7(fixture.TestCustomProfileSelectedImport):
    def defaults(self, code):
        writer = get_param_group(writable=True)
        writer.SetString("Default Profile Material", "CustomFolderLib")
        writer.SetString("Default Profile Family", "Custom Profile")
        writer.SetString("Default Profile Size", code)

    def opened(self, doc, path):
        App.setActiveDocument(doc.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel = candidate.CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        self._assert_no_modals("independent open")
        return panel

    def test_ownership_and_live_dependencies(self):
        # S11/S12/S13 + S8/S9 preservation; no private tracker mutation.
        disk = self._snapshot_library_files()
        for mode in ("same", "foreign"):
            with self.subTest(reference=mode):
                doc = self._new_doc("T7Ownership_" + mode)
                path = self._create_line_path(doc)
                entry = self.manager.get_library("CustomFolderLib")["Custom Profile"]["sizes"]["CP-903"]
                existing = get_or_import_section_sketch(
                    self.folder_lib_path, entry["asset_path"], entry["object_name"], doc, entry["asset_id"]
                )
                existing.Label = "My owned source " + mode
                existing.ViewObject.ShowInTree = True
                existing.ViewObject.Visibility = True
                existing_name = existing.Name
                owned_before = snapshot(existing)
                self.defaults("CP-901")
                panel = self.opened(doc, path)
                # L9 decision (1) "Sí, preview al abrir": a preselected edge creates the preview on open.
                self.assertEqual(len(self._get_profiles(doc)), 1, "Preview created on open")
                opened_source = self._get_profiles(doc)[0].CustomProfile.Name
                self.assertEqual({o.Name for o in sources(doc)}, {existing_name, opened_source})
                self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-901")
                self.assertEqual(len(self._get_profiles(doc)), 1, "Combo selection reuses the open preview")
                self.assertEqual(
                    {o.Name for o in sources(doc)}, {existing_name, opened_source}, "No extra import on combo selection"
                )
                self.assertTrue(panel.apply())
                a = self._get_profiles(doc)[0].CustomProfile
                a_name = a.Name
                a_before = snapshot(a)
                if mode == "same":
                    owner = doc.addObject("App::FeaturePython", "RetainSessionSource")
                    owner.addProperty("App::PropertyLink", "Section")
                    owner.Section = a
                else:
                    doc.recompute()
                    doc.saveAs(os.path.join(self.test_root, "ownership-foreign.FCStd"))
                    other = self._new_doc("T7ForeignOwner")
                    App.setActiveDocument(doc.Name)
                    owner = other.addObject("App::Link", "ForeignSectionOwner")
                    other.saveAs(os.path.join(self.test_root, "ownership-foreign-owner.FCStd"))
                    owner.setLink(a)
                    other.recompute()
                    self.assertEqual(owner.getLinkedObject(), a, "Cross-document Link prerequisite unsupported")
                self.assertIn(owner, a.InList, "Native dependency prerequisite missing from public InList")
                owner_doc, owner_name = owner.Document.Name, owner.Name
                App.setActiveDocument(doc.Name)
                self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-902")
                self.assertTrue(panel.apply())
                b_name = self._get_profiles(doc)[0].CustomProfile.Name
                self.assertIsNotNone(doc.getObject(a_name), "Live referenced session source deleted on A->B")
                self.assertEqual(snapshot(doc.getObject(a_name)), a_before)
                self._select_profile(panel, "CustomFolderLib", "Custom Profile", "CP-903")
                self.assertTrue(panel.apply())
                self.assertIsNone(doc.getObject(b_name), "Unreferenced NEW source B leaked")
                self.assertEqual(self._get_profiles(doc)[0].CustomProfile, doc.getObject(existing_name))
                self.assertTrue(panel.accept())
                self._assert_no_modals("ownership accept")
                doc.recompute()
                retained = doc.getObject(a_name)
                self.assertIsNotNone(retained, "Referenced source deleted at accept")
                self.assertEqual(snapshot(retained), a_before)
                live_owner = App.getDocument(owner_doc).getObject(owner_name)
                actual = live_owner.Section if mode == "same" else live_owner.getLinkedObject()
                self.assertEqual(actual, retained)
                self.assertEqual(snapshot(doc.getObject(existing_name)), owned_before)
                self.assertEqual({o.Name for o in sources(doc)}, {a_name, existing_name})
                self.assertEqual(self._snapshot_library_files(), disk)
                self.assertAlmostEqual(self._get_profiles(doc)[0].Shape.Volume, 320000.0, places=2)

    def test_nonfirst_default_presentation_reuse_reopen(self):
        # S11-S13, S8/S9. Observe actual document object creation, not just final count.
        doc = self._new_doc("T7Default")
        path = self._create_line_path(doc)
        disk = self._snapshot_library_files()
        self.defaults("CP-902")
        created = []
        project_name = doc.Name

        class Observer:
            def slotCreatedObject(self, obj):
                if obj.Document.Name == project_name and obj.isDerivedFrom("Sketcher::SketchObject"):
                    created.append(obj.Name)

        observer = Observer()
        App.addDocumentObserver(observer)
        try:
            panel = self.opened(doc, path)
            self.assertEqual(panel.form_proxy.combo_size.currentText(), "CP-902")
            # L9 decision (1) "Sí, preview al abrir": the default section is imported once, on open.
            self.assertEqual(len(created), 1, "Exactly one import on open")
            self.assertEqual(len(sources(doc)), 1, "One source sketch after open")
            self.assertEqual(len(self._get_profiles(doc)), 1, "Preview created on open")
            self.assertTrue(panel.apply())
            self.assertEqual(len(created), 1, "Apply must not import again")
            self.assertEqual(len(sources(doc)), 1)
            prof = self._get_profiles(doc)[0]
            source = prof.CustomProfile
            source_name = source.Name
            self.assertEqual(source.Label, "CP-902")
            self.assertFalse(source.ViewObject.ShowInTree)
            self.assertFalse(source.ViewObject.Visibility)
            self.assertAlmostEqual(source.Shape.BoundBox.XLength, 50.0)
            self.assertAlmostEqual(source.Shape.BoundBox.YLength, 30.0)
            self.assertTrue(panel.accept())
            self._assert_no_modals("default accept")
            doc.recompute()
            accepted_profiles = self._get_profiles(doc)
            self.assertEqual(len(accepted_profiles), 1)
            prof = accepted_profiles[0]
            source = doc.getObject(source_name)
            self.assertIsNotNone(source)
            self.assertEqual(prof.CustomProfile, source)
            self.assertEqual(prof.getStatusString(), "Valid")
            self.assertAlmostEqual(prof.Shape.Volume, 150000.0, places=2)
            source.Label = "User renamed selected source"
            before = snapshot(source)
            second = self.opened(doc, path)
            self.assertEqual(len(created), 1, "Reopening reuses the existing source")
            self.assertTrue(second.apply())
            self.assertEqual(len(created), 1, "Repeat asset use imported another source")
            self.assertEqual(len(sources(doc)), 1)
            self.assertTrue(second.accept())
            self._assert_no_modals("reuse accept")
            self.assertEqual(snapshot(doc.getObject(source_name)), before)
        finally:
            App.removeDocumentObserver(observer)
        filename = os.path.join(self.test_root, "selected-project.FCStd")
        doc.saveAs(filename)
        closed_name = doc.Name
        App.closeDocument(closed_name)
        self.doc_names.remove(closed_name)
        reopened = App.openDocument(filename)
        self.doc_names.append(reopened.Name)
        reopened.recompute()
        local = reopened.getObject(source_name)
        self.assertIsNotNone(local)
        self.assertEqual(snapshot(local), before)
        self.assertEqual(len(self._get_profiles(reopened)), 2)
        for prof in self._get_profiles(reopened):
            self.assertEqual(prof.CustomProfile, local)
            self.assertEqual(prof.CustomProfile.Document.Name, reopened.Name)
            self.assertEqual(prof.getStatusString(), "Valid")
            self.assertAlmostEqual(prof.Shape.Volume, 150000.0, places=2)
        self.assertEqual(self._snapshot_library_files(), disk)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        IndependentT7(name)
        for name in ("test_ownership_and_live_dependencies", "test_nonfirst_default_presentation_reuse_reopen")
    )

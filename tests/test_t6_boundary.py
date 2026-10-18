"""Independent S1/S3/S6/S8/S9 probes; execute only in isolated native GUI."""
import copy
import hashlib
import json
import os
import shutil
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import FreeCAD as App
import FreeCADGui as Gui
import test_folder_library_duplication as fixture
from freecad.maxproframe import library_manager_dialog as ui
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel


def tree(root):
    result = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            key = os.path.relpath(path, root)
            if os.path.islink(path):
                result[key] = ("link", os.readlink(path))
            elif os.path.isfile(path):
                with open(path, "rb") as stream:
                    result[key] = hashlib.sha256(stream.read()).hexdigest()
            else:
                result[key] = "directory"
    return result


class Boundary(fixture.TestFolderLibraryDuplication):
    def saved(self):
        return tree(self.source_folder), tree(self.reg_dir)

    def dialog(self, name="SourceFolderLib"):
        d = ui.ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(d.close)
        self.assertTrue(d.refresh_libraries(select_name=name))
        d.combo_family.setCurrentText("Custom Profile")
        d.table_sizes.selectRow(0)
        return d

    def manifest(self, data=None):
        path = os.path.join(self.source_folder, "library.json")
        if data is not None:
            with open(path, "w") as stream:
                json.dump(data, stream)
        with open(path) as stream:
            return json.load(stream)

    def test_boundaries(self):
        # S3/S6: public filesystem aliases and nested traversal, before writes.
        nonempty = os.path.join(self.test_root, "nonempty")
        os.mkdir(nonempty)
        with open(os.path.join(nonempty, "KEEP"), "wb") as f:
            f.write(b"KEEP")
        for i, target in enumerate((self.source_folder, nonempty)):
            alias = os.path.join(self.test_root, "alias" + str(i))
            os.symlink(target, alias)
            before = self.saved(), tree(nonempty)
            with self.subTest(destination=target):
                with self.assertRaises((ValueError, FileExistsError)):
                    self.manager.duplicate_library("SourceFolderLib", "Rejected", target_folder_path=alias)
                self.assertEqual((self.saved(), tree(nonempty)), before)
        original = self.manifest()
        outside = os.path.join(self.test_root, "outside.FCStd")
        shutil.copyfile(os.path.join(self.source_folder, self.asset_rel_path), outside)
        for i, rel in enumerate(("sections/sub/../../outside.FCStd", "sections/escape.FCStd")):
            data = copy.deepcopy(original)
            data["Custom Profile"]["sizes"]["Rect_100x50"]["asset_path"] = rel
            if i:
                os.rename(os.path.join(self.source_folder, "sections"), os.path.join(self.source_folder, "held"))
                os.symlink(self.test_root, os.path.join(self.source_folder, "sections"))
                shutil.copyfile(outside, os.path.join(self.test_root, "escape.FCStd"))
            self.manifest(data)
            dest = os.path.join(self.test_root, "reject" + str(i))
            os.mkdir(dest)
            before = tree(self.test_root)
            with self.subTest(asset=rel):
                with self.assertRaises(ValueError):
                    self.manager.duplicate_library("SourceFolderLib", "Rejected", target_folder_path=dest)
                self.assertEqual(tree(self.test_root), before)
            if i:
                os.unlink(os.path.join(self.source_folder, "sections"))
                os.rename(os.path.join(self.source_folder, "held"), os.path.join(self.source_folder, "sections"))
        self.manifest(original)
        dest = os.path.join(self.test_root, "positive")
        self.manager.duplicate_library("SourceFolderLib", "Positive", target_folder_path=dest)
        data = self.manager.get_library("Positive")
        for props in data["Custom Profile"]["sizes"].values():
            asset = os.path.realpath(os.path.join(dest, props["asset_path"]))
            sections = os.path.realpath(os.path.join(dest, "sections"))
            self.assertEqual(os.path.commonpath([sections, asset]), sections)
            self.assertTrue(os.path.isfile(asset))

    def test_owned_rollback(self):
        # S3/S6: partial second copy, nested directories, native recalc and registry failure.
        rel = "sections/sub/deep/second.FCStd"
        full = os.path.join(self.source_folder, rel)
        os.makedirs(os.path.dirname(full))
        shutil.copyfile(os.path.join(self.source_folder, self.asset_rel_path), full)
        data = self.manifest()
        data["Custom Profile"]["sizes"]["Second"] = copy.deepcopy(data["Custom Profile"]["sizes"]["Rect_100x50"])
        data["Custom Profile"]["sizes"]["Second"]["asset_path"] = rel
        self.manifest(data)
        real_copy = shutil.copyfile
        for mode in ("partial", "registry", "recalc"):
            dest = os.path.join(self.test_root, "dest_" + mode)
            os.mkdir(dest)
            before = self.saved()
            calls = []
            def failing_copy(src, target, *args, **kwargs):
                calls.append(target)
                if len(calls) == 2:
                    with open(target, "wb") as f:
                        f.write(b"partial")
                    raise OSError("INJECTED_COPY")
                return real_copy(src, target, *args, **kwargs)
            with self.subTest(mode=mode), ExitStack() as stack:
                if mode == "partial":
                    stack.enter_context(patch.object(shutil, "copyfile", side_effect=failing_copy))
                elif mode == "registry":
                    stack.enter_context(patch.object(self.manager, "register_folder_library", side_effect=OSError("INJECTED_REGISTRY")))
                else:
                    stack.enter_context(patch("freecad.maxproframe.section_library.recalculate_custom_profile_weight", side_effect=ValueError("INJECTED_RECALC")))
                with self.assertRaises((OSError, ValueError)):
                    self.manager.duplicate_library("SourceFolderLib", "Rollback", target_folder_path=dest, recalculate_weights=(mode == "recalc"))
                self.assertEqual(self.saved(), before)
                self.assertTrue(os.path.isdir(dest))
                self.assertEqual(tree(dest), {})

    def test_discard_duplicate(self):
        # S9: staged deletion/edit must never leak into saved source or duplicate.
        for change in ("delete", "edit"):
            for outcome in ("cancel", "fail", "success"):
                with self.subTest(change=change, outcome=outcome):
                    d = self.dialog()
                    if change == "delete":
                        d.btn_del_size.click()
                    else:
                        d.le_norm.setText("UNSAVED")
                    self.assertTrue(d.is_dirty)
                    widgets = d.table_sizes.rowCount(), d.le_norm.text()
                    before = self.saved()
                    name = change + outcome
                    dest = os.path.join(self.test_root, name)
                    os.mkdir(dest)
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(ui.QtWidgets.QMessageBox, "question", return_value=ui.QtWidgets.QMessageBox.Discard))
                        stack.enter_context(patch.object(ui.QtWidgets.QFileDialog, "getExistingDirectory", return_value="" if outcome == "cancel" else dest))
                        stack.enter_context(patch.object(ui.NewLibraryDialog, "exec_", return_value=ui.QtWidgets.QDialog.Accepted))
                        stack.enter_context(patch.object(ui.NewLibraryDialog, "get_values", return_value=(name, "Steel", 7.85, False)))
                        if outcome == "fail":
                            stack.enter_context(patch.object(ui.QtWidgets.QMessageBox, "warning"))
                            stack.enter_context(patch.object(self.manager, "register_folder_library", side_effect=OSError("INJECTED_REGISTRY")))
                        d._on_duplicate_library()
                    self.assertEqual(tree(self.source_folder), before[0])
                    if outcome == "success":
                        self.assertEqual(d.current_lib_meta["name"], name)
                        self.assertFalse(d.is_dirty)
                        sizes = self.manager.get_library(name)["Custom Profile"]["sizes"]
                        self.assertIn("Rect_100x50", sizes)
                        self.assertNotEqual(d.le_norm.text(), "UNSAVED")
                        self.assertTrue(os.path.isfile(os.path.join(dest, self.asset_rel_path)))
                    else:
                        self.assertEqual(self.saved(), before)
                        self.assertEqual(d.current_lib_meta["name"], "SourceFolderLib")
                        self.assertEqual((d.table_sizes.rowCount(), d.le_norm.text()), widgets)
                        self.assertTrue(d.is_dirty)
                        self.assertEqual(tree(dest), {})
                    d.close()

    def profile(self, library):
        doc = App.newDocument("IndependentProject")
        path = self._create_line_path(doc, "Path", 100)
        App.setActiveDocument(doc.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        with patch("freecad.maxproframe.create_profiles_tool.LibraryManager", return_value=self.manager):
            panel = CreateProfileTaskPanel()
            panel.open()
            panel.form_proxy.combo_material.setCurrentText(library)
            panel.form_proxy.combo_family.setCurrentText("Custom Profile")
            panel.form_proxy.combo_size.setCurrentText("Rect_100x50")
            self.assertTrue(panel.accept())
        doc.recompute()
        profiles = [o for o in doc.Objects if hasattr(o, "CustomProfile")]
        self.assertEqual(len(profiles), 1)
        self.assertTrue(profiles[0].Shape.isValid())
        return doc, profiles[0]

    def test_edit_relocated_duplicate_offline(self):
        # S1/S2/S3/S8/S9: true manager/Sketcher edit then project-local offline sources.
        old, p = self.profile("SourceFolderLib")
        self.assertAlmostEqual(p.Shape.Volume, 500000, places=2)
        oldfile = os.path.join(self.test_root, "old.FCStd")
        old.saveAs(oldfile)
        name = old.Name
        App.closeDocument(name)
        dest = os.path.join(self.test_root, "duplicate")
        self.manager.duplicate_library("SourceFolderLib", "Portable", target_folder_path=dest, target_material="Aluminium", target_density=2.7, recalculate_weights=True)
        self.manager.unregister_folder_library(self.source_folder)
        shutil.rmtree(self.source_folder)
        self.manager.unregister_folder_library(dest)
        moved = os.path.join(self.test_root, "moved")
        shutil.move(dest, moved)
        self.manager.register_folder_library(moved)
        d = self.dialog("Portable")
        d.btn_edit_section.click()
        session = d._active_edit_session
        self.assertIsNotNone(session)
        work = App.getDocument(session.working_doc_name)
        sketch = work.getObject(session.working_sketch_name)
        App.setActiveDocument(work.Name)
        indices = [i for i, c in enumerate(sketch.Constraints) if c.Type == "Distance" and abs(c.Value - 50) < 1e-6]
        self.assertEqual(len(indices), 1)
        sketch.setDatum(indices[0], App.Units.Quantity("60 mm"))
        self.assertEqual(sketch.solve(), 0)
        work.recompute()
        d.apply_section_edit()
        self.assertTrue(d.is_dirty)
        d.btn_save.click()
        self.assertFalse(d.is_dirty)
        props = self.manager.get_library("Portable")["Custom Profile"]["sizes"]["Rect_100x50"]
        self.assertAlmostEqual(float(props["Weight"]), 16.2, places=2)
        d.close()
        new, p = self.profile("Portable")
        self.assertAlmostEqual(p.Shape.Volume, 600000, places=2)
        newfile = os.path.join(self.test_root, "new.FCStd")
        new.saveAs(newfile)
        name = new.Name
        App.closeDocument(name)
        self.manager.unregister_folder_library(moved)
        shutil.rmtree(moved)
        for path, volume in ((oldfile, 500000), (newfile, 600000)):
            doc = App.openDocument(path)
            doc.recompute()
            profiles = [o for o in doc.Objects if hasattr(o, "CustomProfile")]
            self.assertEqual(len(profiles), 1)
            p = profiles[0]
            self.assertEqual(p.getStatusString(), "Valid")
            self.assertTrue(p.Shape.isValid())
            self.assertAlmostEqual(p.Shape.Volume, volume, places=2)
            self.assertEqual(p.CustomProfile.Document.Name, doc.Name)
            self.assertGreater(len(p.CustomProfile.Constraints), 0)

    def test_dirty_owned_documents_selection(self):
        # S6/S8: inspect saved copy, never the unsaved user asset/model.
        asset = App.openDocument(os.path.join(self.source_folder, self.asset_rel_path))
        sketch = asset.getObject(self.asset_obj_name)
        index = next(i for i, c in enumerate(sketch.Constraints) if c.Type == "Distance" and abs(c.Value - 50) < 1e-6)
        sketch.setDatum(index, App.Units.Quantity("65 mm"))
        asset.recompute()
        sketch.Label = "UNSAVED ASSET"
        other = App.newDocument("OwnedModel")
        line = self._create_line_path(other)
        line.Label = "UNSAVED MODEL"
        def snapshot():
            return [(doc.Name, doc.FileName, doc.Label, [(o.Name, o.Label, tuple(o.State), str(o.Placement), [(c.Type, c.Value) for c in o.Constraints] if hasattr(o, "Constraints") else None, [(str(g.StartPoint), str(g.EndPoint)) for g in o.Geometry] if hasattr(o, "Geometry") else None) for o in doc.Objects]) for doc in (asset, other)]
        def selection():
            return [(s.DocumentName, s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        for mode, active in (("backend", asset), ("ui", other)):
            d = self.dialog() if mode == "ui" else None
            App.setActiveDocument(active.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(active.Name, sketch.Name if active == asset else line.Name, "Edge1")
            before = snapshot(), selection(), set(App.listDocuments()), self.saved()
            dest = os.path.join(self.test_root, mode)
            if d:
                with patch.object(ui.QtWidgets.QFileDialog, "getExistingDirectory", return_value=dest), patch.object(ui.NewLibraryDialog, "exec_", return_value=ui.QtWidgets.QDialog.Accepted), patch.object(ui.NewLibraryDialog, "get_values", return_value=(mode, "Aluminium", 2.7, True)):
                    d._on_duplicate_library()
                self.assertEqual(d.current_lib_meta["name"], mode)
            else:
                self.manager.duplicate_library("SourceFolderLib", mode, target_folder_path=dest, target_material="Aluminium", target_density=2.7, recalculate_weights=True)
            self.assertEqual(snapshot(), before[0])
            self.assertEqual(selection(), before[1])
            self.assertEqual(set(App.listDocuments()), before[2])
            self.assertEqual(App.ActiveDocument.Name, active.Name)
            self.assertEqual(tree(self.source_folder), before[3][0])
            self.assertAlmostEqual(float(self.manager.get_library(mode)["Custom Profile"]["sizes"]["Rect_100x50"]["Weight"]), 13.5, places=2)
            if d:
                d.close()


METHODS = ("test_boundaries", "test_owned_rollback", "test_discard_duplicate", "test_edit_relocated_duplicate_offline", "test_dirty_owned_documents_selection")


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Boundary(name) for name in METHODS)

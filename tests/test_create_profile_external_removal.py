"""Create Profile panel survives previews removed outside it and dialogs closed without Cancel."""

import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.profile import Profile


class TestCreateProfileExternalRemoval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_external_removal_")
        self.addCleanup(shutil.rmtree, self.test_user_dir, True)
        self.created_docs = []
        self.panels = []
        self.messages = ExitStack()
        self.addCleanup(self.messages.close)
        self.exec_ = self.messages.enter_context(
            patch.object(QtWidgets.QMessageBox, "exec_", return_value=QtWidgets.QMessageBox.Ok)
        )
        if hasattr(QtGui, "QMessageBox") and QtGui.QMessageBox is not QtWidgets.QMessageBox:
            self.messages.enter_context(patch.object(QtGui.QMessageBox, "exec_", self.exec_))

    def tearDown(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        for panel in self.panels:
            for cleanup in (panel.reject, panel.clean):
                try:
                    cleanup()
                except Exception:
                    pass
        Gui.Selection.clearSelection()
        for name in self.created_docs:
            if name in App.listDocuments():
                App.closeDocument(name)
        self._settle()

    def _settle(self):
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def _doc_with_path(self):
        doc = App.newDocument(f"DocExternalRemoval_{len(self.created_docs)}_{id(self)}")
        doc.UndoMode = 1
        App.setActiveDocument(doc.Name)
        self.created_docs.append(doc.Name)
        sk = doc.addObject("Sketcher::SketchObject", "Path")
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(200, 0, 0)), False)
        sk.addGeometry(Part.LineSegment(App.Vector(200, 0, 0), App.Vector(200, 100, 0)), False)
        doc.recompute()
        return doc, sk

    def _canvas_panel(self):
        doc, sk = self._doc_with_path()
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        preview = panel._objects[(sk, "Edge1")]
        self.assertTrue(preview.isAttachedToDocument())
        return doc, sk, panel, preview

    @staticmethod
    def _profiles(doc):
        return [obj for obj in doc.Objects if isinstance(getattr(obj, "Proxy", None), Profile)]

    def _assert_reselection_recreates_preview_and_ok_creates_profile(self, doc, sk, panel):
        key = (sk, "Edge1")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        # Observers swallow exceptions; the same handlers called directly must not raise.
        panel._selection_changed()
        panel._on_edge_selected(key)
        panel._on_list_selection_changed()
        self.assertEqual(list(panel._objects), [key])
        preview = panel._objects[key]
        self.assertTrue(preview.isAttachedToDocument())
        self.assertEqual(preview.ViewObject.Transparency, 35)

        self.assertTrue(panel.accept())
        profiles = self._profiles(doc)
        self.assertEqual(profiles, [preview])
        self.assertEqual(profiles[0].getStatusString(), "Valid")
        self.assertFalse(profiles[0].Shape.isNull())
        self.assertEqual(profiles[0].ViewObject.Transparency, 0)
        self.exec_.assert_not_called()

    def test_deleted_preview_is_recreated_and_ok_creates_valid_profile(self):
        doc, sk, panel, preview = self._canvas_panel()
        name = preview.Name
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, name)
        Gui.runCommand("Std_Delete")
        self.assertIsNone(doc.getObject(name))
        self._assert_reselection_recreates_preview_and_ok_creates_profile(doc, sk, panel)

    def test_undone_preview_is_recreated_and_ok_creates_valid_profile(self):
        doc, sk, panel, preview = self._canvas_panel()
        name = preview.Name
        Gui.Selection.clearSelection()
        Gui.runCommand("Std_Undo")
        self.assertIsNone(doc.getObject(name))
        self.assertIsNotNone(doc.getObject(sk.Name))
        self._assert_reselection_recreates_preview_and_ok_creates_profile(doc, sk, panel)

    def test_dialog_closed_without_cancel_stops_observer_and_removes_previews(self):
        doc, sk = self._doc_with_path()
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        Gui.Selection.addObserver(panel)
        Gui.Control.showDialog(panel)
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.assertTrue(panel._objects[(sk, "Edge1")].isAttachedToDocument())
        self.assertEqual(doc.UndoNames[:1], ["Add Profile"])

        with patch.object(panel, "reject", wraps=panel.reject) as reject:
            Gui.Control.closeDialog()
            self._settle()
            reject.assert_not_called()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual([obj.Name for obj in doc.Objects], [sk.Name])
        self.assertEqual(panel._objects, {})
        self.assertNotIn("Add Profile", doc.UndoNames)

        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        panel.addSelection(doc.Name, sk.Name, "Edge2", None)
        panel.clearSelection(None)
        self._settle()
        self.assertEqual([obj.Name for obj in doc.Objects], [sk.Name])
        self.assertEqual(panel._objects, {})


if __name__ == "__main__":
    unittest.main()

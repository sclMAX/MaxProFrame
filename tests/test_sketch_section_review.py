"""Native modeless sketch capture, including FreeCAD mouse-selection events."""

import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

import test_library_dxf_import as dxf_tests


class TestSketchSectionReview(unittest.TestCase):
    snapshot = dxf_tests.TestLibraryDXFImport.snapshot

    def setUp(self):
        dxf_tests.TestLibraryDXFImport.setUp(self)
        for patcher in self.gui_patchers:
            patcher.stop()
        # Keep the old modal picker from blocking the RED run offscreen.
        self.stack.enter_context(patch.object(QtWidgets.QInputDialog, "getItem", return_value=("", False)))
        self.addCleanup(Gui.Selection.clearSelection)

    def sketch(self, name="Section", width=10):
        doc = App.newDocument("CaptureSource")
        doc_name = doc.Name
        self.addCleanup(lambda: App.closeDocument(doc_name) if doc_name in App.listDocuments() else None)
        sketch = doc.addObject("Sketcher::SketchObject", name)
        points = [(0, 0), (width, 0), (width, 5), (0, 5)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        doc.recompute()
        return sketch

    def start(self):
        self.dialog.btn_capture_section.click()
        review = self.dialog._dxf_review
        self.assertIsNotNone(review, "Capture must open a review before writing an asset")
        self.assertFalse(self.dialog.isVisible())
        self.assertFalse(review.isModal())
        return review

    def test_preselection_requires_confirmation_with_code_and_description(self):
        sketch = self.sketch()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sketch.Document.Name, sketch.Name)
        before = self.snapshot()
        docs = set(App.listDocuments())
        review = self.start()
        self.assertIs(review.sketch, sketch)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(review.le_code.text(), sketch.Label)
        review.le_code.setText("CUSTOM-10")
        review.le_description.setText("Rectangular section")
        review.btn_add.click()
        self.assertIsNone(self.dialog._dxf_review)
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(set(App.listDocuments()), docs)
        self.assertEqual(self.dialog.table_sizes.rowCount(), 1)
        self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "CUSTOM-10")
        self.assertEqual(len(self.dialog._staged_new_assets), 1)
        self.dialog._commit_current_family_edits()
        entry = self.dialog.current_lib_data["Custom Profile"]["sizes"]["CUSTOM-10"]
        self.assertEqual(entry["Description"], "Rectangular section")
        self.assertEqual(float(entry["Width"]), 10)
        self.assertEqual(float(entry["Height"]), 5)
        self.assertTrue(self.dialog.is_dirty)
        self.assertNotIn("Custom Profile", self.manager.get_library("Alu"))

    def test_mouse_edge_selection_and_combo_stay_in_sync(self):
        first = self.sketch("First")
        second = self.sketch("Second", 20)
        Gui.Selection.clearSelection()
        review = self.start()
        self.assertIsNone(review.sketch)
        self.assertFalse(review.btn_add.isEnabled())
        Gui.Selection.addSelection(first.Document.Name, first.Name, "Edge1")
        self.assertIs(review.sketch, first)
        self.assertEqual(review.combo_sketch.currentData(), (first.Document.Name, first.Name))
        review.le_code.setText("USER-CODE")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(second.Document.Name, second.Name)
        self.assertIs(review.sketch, second)
        self.assertEqual(review.le_code.text(), "USER-CODE")
        review.combo_sketch.setCurrentIndex(review.combo_sketch.findData((first.Document.Name, first.Name)))
        self.assertIs(review.sketch, first)
        self.assertIn(first, Gui.Selection.getSelection())
        self.assertEqual(App.ActiveDocument.Name, first.Document.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, first.Document.Name)
        review.btn_add.click()
        self.assertEqual(float(self.dialog.table_sizes.item(0, 2).text()), 10)

    def test_cancel_restores_library_without_mutating_source_or_staging(self):
        sketch = self.sketch()
        before = self.snapshot()
        geometry = sketch.GeometryCount
        Gui.Selection.clearSelection()
        review = self.start()
        Gui.Selection.addSelection(sketch.Document.Name, sketch.Name, "Edge2")
        review.le_code.setText("Canceled")
        review.reject()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.dialog.isVisible())
        self.assertIn(sketch.Document.Name, App.listDocuments())
        self.assertEqual(sketch.GeometryCount, geometry)
        self.assertFalse(review._observing)

    def test_non_sketch_and_deleted_sketch_disable_capture(self):
        sketch = self.sketch()
        doc = sketch.Document
        solid = doc.addObject("PartDesign::Feature", "NotASketch")
        solid.Shape = Part.makeBox(1, 1, 1)
        Gui.Selection.clearSelection()
        review = self.start()
        Gui.Selection.addSelection(doc.Name, solid.Name)
        self.assertIsNone(review.sketch)
        self.assertFalse(review.btn_add.isEnabled())
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sketch.Name, "Edge1")
        self.assertTrue(review.btn_add.isEnabled())
        doc.removeObject(sketch.Name)
        review.check_document()
        self.assertIsNone(review.sketch)
        self.assertFalse(review.btn_add.isEnabled())
        review.reject()
        self.assertFalse(self.dialog._staged_new_assets)

    def test_rejected_geometry_and_duplicate_code_leave_state_unchanged(self):
        sketch = self.sketch()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sketch.Document.Name, sketch.Name)
        review = self.start()
        review.le_code.setText("Existing")
        review.btn_add.click()
        before = self.snapshot()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sketch.Document.Name, sketch.Name)
        review = self.start()
        review.le_code.setText("Existing")
        review.btn_add.click()
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.dialog._dxf_review, review)
        review.le_code.setText("Invalid")
        sketch.delGeometry(0)
        review.btn_add.click()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.warning.called)
        review.reject()

    def test_library_switch_and_manager_close_detach_observer_keep_source(self):
        sketch = self.sketch()
        Gui.Selection.clearSelection()
        review = self.start()
        self.dialog.refresh_libraries(select_name="Other")
        self.assertFalse(review._observing)
        self.assertIsNone(self.dialog._dxf_review)
        self.assertIn(sketch.Document.Name, App.listDocuments())
        review = self.start()
        self.dialog.close()
        self.assertFalse(review._observing)
        self.assertIsNone(self.dialog._dxf_review)
        self.assertFalse(self.dialog.isVisible())
        self.assertIn(sketch.Document.Name, App.listDocuments())

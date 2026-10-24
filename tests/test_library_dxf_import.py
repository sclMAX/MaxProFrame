"""DXF UI state tests use real native sketches/assets and precise GUI-call mocks."""

import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtWidgets

from freecad.maxproframe import library_manager_dialog as ui
from freecad.maxproframe.library_manager import LibraryManager


class TestLibraryDXFImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mpf_dxf_ui_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manager = LibraryManager(
            user_dir=str(self.root / "user"),
            stock_dir=str(self.root / "stock"),
            registry_path=str(self.root / "registry.json"),
        )
        self.manager.create_folder_library(str(self.root / "Alu"), "Alu", material="Aluminum", density=2.7)
        self.manager.create_folder_library(str(self.root / "Other"), "Other", material="Steel", density=7.85)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(ui.ProfileLibraryManagerDialog, "ensure_translations_loaded"))
        self.warning = self.stack.enter_context(patch.object(QtWidgets.QMessageBox, "warning"))
        self.stack.enter_context(
            patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Discard)
        )
        self.picker = self.stack.enter_context(
            patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=("synthetic.dxf", ""))
        )
        self.gui_doc = SimpleNamespace(activeView=lambda: SimpleNamespace(viewTop=Mock(), fitAll=Mock()))
        self.gui_patchers = [
            patch.object(ui.Gui, "getDocument", return_value=self.gui_doc, create=True),
            patch.object(ui.Gui, "setActiveDocument", create=True),
        ]
        for patcher in self.gui_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.dialog = ui.ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(self.dialog.close)
        self.dialog.refresh_libraries(select_name="Alu")
        self.dialog.show()
        self.before_docs = set(App.listDocuments())
        self.before = self.snapshot()

    def snapshot(self):
        return (
            copy.deepcopy(self.dialog.current_lib_data),
            self.dialog.current_family,
            self.dialog.is_dirty,
            set(self.dialog._staged_new_assets),
            set(self.dialog._staged_deleted_assets),
            {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()},
            self.dialog.table_sizes.rowCount(),
        )

    def start(self, units_ok=True, importer=None):
        from freecad.maxproframe.dxf_section_dialog import DXFUnitsDialog

        def confirm(dialog):
            dialog.combo_units.setCurrentIndex(dialog.combo_units.findData("mm"))
            return QtWidgets.QDialog.Accepted if units_ok else QtWidgets.QDialog.Rejected

        def native(path, doc, unit_override):
            self.assertEqual(unit_override, "mm")
            sketch = doc.addObject("Sketcher::SketchObject", "Section")
            points = [(-4, -2), (4, -2), (4, 2), (-4, 2)]
            for i, point in enumerate(points):
                end = points[(i + 1) % 4]
                index = sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
                sketch.addConstraint(Sketcher.Constraint("Block", index))
            doc.recompute()
            return sketch

        with (
            patch.object(DXFUnitsDialog, "exec_", confirm),
            patch.object(ui, "inspect_dxf", return_value={"insunits": 6, "unit_mm": 1000.0}),
            patch.object(ui, "import_dxf_section", side_effect=importer or native),
        ):
            self.dialog.btn_import_dxf.click()
        return self.dialog._dxf_review

    def assert_unchanged(self):
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(set(App.listDocuments()), self.before_docs)

    def test_section_actions_follow_canonical_family_and_keep_icon_only_tooltips(self):
        # Persist fixture families through the manager, then use the visible selector.
        self.manager.save_folder_library(
            str(self.root / "Alu"),
            {
                "My Sections": {"canonical_family": "Custom Profile", "norm": "Custom", "sizes": {}},
                "Rectangular Hollow": {"canonical_family": "Rectangular Hollow", "norm": "", "sizes": {}},
            },
            overwrite=True,
        )
        self.dialog.refresh_libraries(select_name="Alu")
        actions = (
            self.dialog.btn_capture_section,
            self.dialog.btn_import_dxf,
            self.dialog.btn_edit_section,
            self.dialog.btn_apply_edit,
        )
        for family in ("My Sections", "Rectangular Hollow", "My Sections"):
            self.dialog.list_families.setCurrentRow(self.dialog.combo_family.findText(family))
            for button in actions:
                self.assertEqual(button.isHidden(), family != "My Sections")
                self.assertEqual(button.text(), "")
                self.assertTrue(button.toolTip())
                self.assertFalse(button.icon().isNull())
            self.assertEqual(self.dialog.btn_add_size.isEnabled(), family != "My Sections")
        capture = actions[0].icon().pixmap(24, 24).toImage()
        imported = actions[1].icon().pixmap(24, 24).toImage()
        self.assertFalse(capture.isNull())
        self.assertNotEqual(capture, imported)
        self.manager.save_user_library("Empty", {})
        self.dialog.refresh_libraries(select_name="Empty")
        for button in actions:
            self.assertTrue(button.isHidden())

    def test_action_enablement_preserves_capture_edit_apply(self):
        self.assertTrue(self.dialog.btn_import_dxf.isEnabled())
        self.assertTrue(self.dialog.btn_capture_section.isEnabled())
        self.assertFalse(self.dialog.btn_edit_section.isEnabled())
        self.assertFalse(self.dialog.btn_apply_edit.isEnabled())
        self.manager.save_user_library("Legacy", {})
        self.dialog.refresh_libraries(select_name="Legacy")
        self.assertFalse(self.dialog.btn_import_dxf.isEnabled())
        self.assertFalse(self.dialog.btn_capture_section.isEnabled())
        self.assertFalse(self.dialog.btn_edit_section.isEnabled())
        self.assertFalse(self.dialog.btn_apply_edit.isEnabled())

    def test_file_units_preview_and_code_cancel_leave_everything_unchanged(self):
        self.picker.return_value = ("", "")
        self.dialog.btn_import_dxf.click()
        self.assert_unchanged()
        self.picker.return_value = ("synthetic.dxf", "")
        self.assertIsNone(self.start(units_ok=False))
        self.assert_unchanged()
        for code in ("", "CancelledCode"):
            review = self.start()
            self.assertEqual(self.snapshot(), self.before)
            review.le_code.setText(code)
            review.le_description.setText("Cancelled description")
            review.reject()
            self.assert_unchanged()
            self.assertTrue(self.dialog.isVisible())

    def test_preflight_native_and_asset_failure_do_not_mutate_library(self):
        with patch.object(ui, "inspect_dxf", side_effect=ValueError("Unknown DXF entity")):
            self.dialog.btn_import_dxf.click()
        self.assert_unchanged()
        self.assertIn("Unknown DXF entity", self.warning.call_args.args[2])

        def broken(path, doc, unit_override):
            doc.addObject("PartDesign::Feature", "Partial")
            raise RuntimeError("Native failure")

        self.assertIsNone(self.start(importer=broken))
        self.assert_unchanged()
        self.assertIn("Native failure", self.warning.call_args.args[2])
        review = self.start()
        review.le_code.setText("A")
        with patch.object(ui, "save_section_asset", side_effect=OSError("Asset failure")):
            review.btn_add.click()
        self.assertEqual(self.snapshot(), self.before)
        self.assertTrue(review.isVisible())
        self.assertIn("Asset failure", self.warning.call_args.args[2])
        review.reject()
        self.assert_unchanged()

    def test_viewport_failure_preserves_library_and_manager_visibility(self):
        self.gui_doc.activeView = Mock(side_effect=RuntimeError("Viewport failed"))
        self.assertIsNone(self.start())
        self.assertEqual(self.warning.call_args.args[2], "Viewport failed")
        self.assert_unchanged()
        self.assertTrue(self.dialog.isVisible())

    def test_real_serializer_failure_keeps_review_usable(self):
        review = self.start()
        review.le_code.setText("WriteFail")
        with patch.object(ui.App, "newDocument", side_effect=OSError("Disk unavailable")):
            review.btn_add.click()
        self.assertEqual(self.warning.call_args.args[2], "Disk unavailable")
        self.assertEqual(self.snapshot(), self.before)
        self.assertIs(self.dialog._dxf_review, review)
        self.assertTrue(review.isVisible())
        review.reject()
        self.assert_unchanged()

    def test_switch_or_close_during_unit_confirmation_prevents_import(self):
        from freecad.maxproframe.dxf_section_dialog import DXFUnitsDialog

        for action in ("switch", "close"):
            with self.subTest(action=action):

                def confirm(dialog):
                    dialog.combo_units.setCurrentIndex(dialog.combo_units.findData("mm"))
                    if action == "switch":
                        self.dialog.refresh_libraries(select_name="Other")
                    else:
                        self.dialog.close()
                    return QtWidgets.QDialog.Accepted

                with (
                    patch.object(DXFUnitsDialog, "exec_", confirm),
                    patch.object(ui, "inspect_dxf", return_value={"insunits": 6, "unit_mm": 1000.0}),
                    patch.object(ui, "import_dxf_section") as importer,
                ):
                    self.dialog.btn_import_dxf.click()
                importer.assert_not_called()
                self.assertEqual(set(App.listDocuments()), self.before_docs)
                self.assertFalse(self.dialog.is_dirty)
                self.assertFalse(self.dialog._staged_new_assets)
                self.assertEqual(self.snapshot()[5], self.before[5])

    def test_review_is_fixed_centered_owned_and_uses_destination_material(self):
        review = self.start()
        self.assertFalse(self.dialog.isVisible())
        self.assertTrue(review.isVisible())
        self.assertIn("Aluminum", review.lbl_destination.text())
        self.assertIn("2.7", review.lbl_destination.text())
        sketch = review.sketch
        self.assertEqual(set(App.listDocuments()) - self.before_docs, {sketch.Document.Name})
        self.assertTrue(sketch.FullyConstrained)
        self.assertTrue(sketch.Placement.isIdentity())
        box = sketch.Shape.BoundBox
        self.assertAlmostEqual(box.XMin + box.XMax, 0)
        self.assertAlmostEqual(box.YMin + box.YMax, 0)
        self.assertAlmostEqual(box.ZLength, 0)
        self.assertEqual(len(sketch.Geometry), 4)
        self.assertEqual(sketch.OutList, [])
        review.reject()
        self.assert_unchanged()

    def test_description_stages_saves_reloads_and_is_searchable(self):
        review = self.start()
        review.le_code.setText("DXF_DESCRIPTION")
        review.le_description.setText("  Support bracket  ")
        review.btn_add.click()
        entry = self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole)
        self.assertEqual(entry["Description"], "Support bracket")
        self.assertTrue(self.dialog.is_dirty)
        self.assertNotIn("Custom Profile", self.manager.get_library("Alu"))
        self.dialog.btn_save.click()
        saved = self.manager.get_library("Alu")["Custom Profile"]["sizes"]["DXF_DESCRIPTION"]
        self.assertEqual(saved["Description"], "Support bracket")
        self.dialog.refresh_libraries(select_name="Alu")
        self.dialog.combo_family.setCurrentIndex(self.dialog.combo_family.findText("Custom Profile"))
        entry = self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole)
        self.assertEqual(entry, saved)
        card = self.dialog.cards_view.card_by_code("DXF_DESCRIPTION")
        self.assertEqual(card.description_edit.text(), "Support bracket")
        self.dialog.le_search.setText("bracket")
        self.assertFalse(self.dialog.table_sizes.isRowHidden(0))
        self.dialog.le_search.setText("missing")
        self.assertTrue(self.dialog.table_sizes.isRowHidden(0))

    def test_review_has_optional_form_and_clear_primary_action(self):
        review = self.start()
        self.assertFalse(review.isModal())
        self.assertTrue(review.windowFlags() & QtCore.Qt.Tool)
        self.assertTrue(review.lbl_destination.wordWrap())
        self.assertGreaterEqual(review.minimumWidth(), 460)
        form = review.le_code.parentWidget().layout()
        self.assertIsInstance(form, QtWidgets.QFormLayout)
        self.assertIs(form.labelForField(review.le_description).buddy(), review.le_description)
        self.assertEqual(review.le_description.text(), "")
        self.assertTrue(review.btn_add.isDefault())
        review.reject()
        self.assertFalse(review.timer.isActive())
        self.assert_unchanged()

    def test_add_stages_then_save_and_reopen_is_independent(self):
        review = self.start()
        review.le_code.setText("DXF_A")
        review.btn_add.click()
        self.assertIsNone(self.dialog._dxf_review)
        self.assertTrue(self.dialog.isVisible())
        self.assertTrue(self.dialog.is_dirty)
        self.assertEqual(self.dialog.table_sizes.rowCount(), 1)
        self.assertEqual(self.dialog.table_sizes.currentRow(), 0)
        entry = self.dialog.table_sizes.item(0, 0).data(QtCore.Qt.UserRole)
        self.assertNotIn("Description", entry)
        self.assertEqual(entry["Height"], "4.0")
        self.assertEqual(entry["Width"], "8.0")
        self.assertAlmostEqual(float(entry["Weight"]), 0.0864, places=4)
        self.assertEqual(self.dialog._staged_new_assets, {entry["asset_path"]})
        self.assertNotIn("Custom Profile", self.manager.get_library("Alu"))
        self.assertEqual(set(App.listDocuments()), self.before_docs)
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog._staged_new_assets)
        saved = self.manager.get_library("Alu")
        self.assertEqual(saved["Custom Profile"]["sizes"]["DXF_A"]["asset_id"], entry["asset_id"])
        doc = App.openDocument(str(self.root / "Alu" / entry["asset_path"]))
        try:
            sketch = doc.getObject(entry["object_name"])
            self.assertTrue(sketch.FullyConstrained)
            self.assertEqual(sketch.OutList, [])
            self.assertEqual(sketch.ExternalGeometry, [])
            self.assertAlmostEqual(sketch.Shape.BoundBox.XLength, 8)
        finally:
            App.closeDocument(doc.Name)
        self.assertEqual(self.manager.get_library_material_info("Alu"), ("Aluminum", 2.7))

    def test_empty_and_duplicate_codes_keep_review_usable(self):
        review = self.start()
        review.le_code.setText(" ")
        review.le_description.setText("Rejected description")
        review.btn_add.click()
        self.assertEqual(self.snapshot(), self.before)
        self.assertIs(self.dialog._dxf_review, review)
        review.le_code.setText("A")
        review.btn_add.click()
        self.dialog.btn_save.click()
        before = self.snapshot()
        review = self.start()
        review.le_code.setText("A")
        review.btn_add.click()
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.dialog._dxf_review, review)
        self.assertIn("Duplicate size codes found: A", self.warning.call_args.args[2])
        review.reject()

    def test_repeated_import_switch_close_and_document_close_cleanup(self):
        review = self.start()
        self.dialog._on_import_dxf()
        self.assertIs(self.dialog._dxf_review, review)
        self.assertEqual(len(set(App.listDocuments()) - self.before_docs), 1)
        self.dialog.refresh_libraries(select_name="Other")
        self.assertIsNone(self.dialog._dxf_review)
        self.assertEqual(set(App.listDocuments()), self.before_docs)
        self.assertFalse(self.dialog.is_dirty)
        self.assertNotIn("Custom Profile", self.manager.get_library("Alu"))
        self.dialog.refresh_libraries(select_name="Alu")
        self.before = self.snapshot()
        review = self.start()
        App.closeDocument(review.sketch.Document.Name)
        review.check_document()
        self.assert_unchanged()
        review = self.start()
        self.dialog.close()
        self.assertIsNone(self.dialog._dxf_review)
        self.assertEqual(set(App.listDocuments()), self.before_docs)
        self.assertFalse(self.dialog.isVisible())
        review.reject()
        self.assertFalse(self.dialog.isVisible())

    def test_previous_capture_edit_apply_save_behavior(self):
        source = App.newDocument("CaptureSource")
        self.addCleanup(lambda: App.closeDocument(source.Name) if source.Name in App.listDocuments() else None)
        sketch = source.addObject("Sketcher::SketchObject", "Captured")
        points = [(0, 0), (10, 0), (10, 5), (0, 5)]
        for i, point in enumerate(points):
            end = points[(i + 1) % 4]
            sketch.addGeometry(Part.LineSegment(App.Vector(*point, 0), App.Vector(*end, 0)), False)
        source.recompute()
        selection = SimpleNamespace(getSelection=lambda: [sketch])
        with patch.object(ui.Gui, "Selection", selection, create=True):
            self.dialog.btn_capture_section.click()
        self.assertEqual(self.dialog.current_family, "Custom Profile")
        self.assertEqual(self.dialog.table_sizes.rowCount(), 1)
        self.assertEqual(self.dialog.table_sizes.currentRow(), 0)
        self.assertTrue(self.dialog.is_dirty)
        self.assertTrue(self.dialog.btn_edit_section.isEnabled())
        self.dialog.hide()  # Existing direct/unshown editing contract, no fake production GUI.
        self.dialog.btn_edit_section.click()
        self.assertIsNotNone(self.dialog._active_edit_session)
        self.assertTrue(self.dialog.btn_apply_edit.isEnabled())
        self.dialog.btn_apply_edit.click()
        self.assertEqual(len(self.dialog._staged_new_assets), 2)
        self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "Captured")
        self.dialog.btn_save.click()
        self.assertFalse(self.dialog.is_dirty)
        self.assertFalse(self.dialog._staged_new_assets)
        saved = self.manager.get_library("Alu")["Custom Profile"]["sizes"]["Captured"]
        self.assertEqual(saved["Height"], "5.0")
        self.assertEqual(saved["Width"], "10.0")
        self.assertTrue(saved["asset_id"].startswith("sec_"))

    @unittest.skipUnless(App.GuiUp, "Native import with QApplication requires a real FreeCAD GUI runtime")
    def test_real_native_import_to_staged_asset(self):
        from test_dxf_section_import import RECT, TestDXFSectionImport, poly

        from freecad.maxproframe.dxf_section_import import import_dxf_section

        for patcher in self.gui_patchers:
            patcher.stop()
        fixture = TestDXFSectionImport()
        fixture.tmp = self.tmp
        path = fixture.source(poly(RECT), units=6)
        self.picker.return_value = (str(path), "")
        review = self.start(importer=import_dxf_section)
        self.assertIsNotNone(review, "Captured warnings: %s" % (self.warning.call_args_list,))
        self.assertTrue(review.sketch.FullyConstrained)
        self.assertAlmostEqual(review.sketch.Shape.BoundBox.XLength, 8)
        review.le_code.setText("Native")
        review.btn_add.click()
        self.assertEqual(self.dialog.table_sizes.rowCount(), 1)
        self.assertTrue(self.dialog.is_dirty)
        self.dialog.btn_save.click()
        self.assertIn("Native", self.manager.get_library("Alu")["Custom Profile"]["sizes"])

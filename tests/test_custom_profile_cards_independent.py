import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_custom_profile_cards as fixture

App, Gui = fixture.App, fixture.Gui
W, C = fixture.QtWidgets, fixture.QtCore


def family(d, name):
    for i in range(d.list_families.count()):
        item = d.list_families.item(i)
        if item.data(C.Qt.UserRole) == name:
            d.list_families.setCurrentItem(item)
            return
    raise AssertionError("Missing family " + name)


def library(d, name):
    for i in range(d.list_libraries.count()):
        item = d.list_libraries.item(i)
        if item.data(C.Qt.UserRole)["name"] == name:
            d.list_libraries.setCurrentItem(item)
            return
    raise AssertionError("Missing library " + name)


def disk(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in Path(root).rglob("*") if p.is_file()}


def selection():
    return [(s.DocumentName, s.ObjectName, tuple(s.SubElementNames))
            for s in Gui.Selection.getSelectionEx()]


def image(d, code):
    return d.cards_view.card_by_code(code).thumbnail_label.pixmap().toImage()


def enter(d, code, field, text):
    card = d.cards_view.card_by_code(code)
    card.click()
    edit = getattr(card, field)
    edit.setFocus()
    W.QApplication.processEvents()
    edit.setText(text)


class IndependentCards(unittest.TestCase):
    def setUp(self):
        self.f = fixture.TestCustomProfileCards("runTest")
        self.f.setUp()
        self.d = self.f.dialog
        self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "offscreen")

    def tearDown(self):
        self.f.tearDown()

    def publish(self, entries):
        f = self.f
        data = f.manager.get_library("CustomFolderLib")
        data["Custom Profile"]["sizes"] = entries
        f.manager.save_folder_library(f.folder_lib_path, data, overwrite=True)
        self.d.refresh_libraries(select_name="CustomFolderLib")
        family(self.d, "Custom Profile")

    def props(self, rel, name="Section"):
        return dict(Height="35", Width="70", Thickness="0", Weight="19.23",
                    asset_path=rel, object_name=name,
                    asset_id=Path(rel).stem, independent_tag=17)

    def test_selected_edits_apply_and_cancel(self):
        f, d = self.f, self.d
        a = f._create_published_asset("ind_a", width=50, height=50)
        b = f._create_published_asset("ind_b", width=70, height=35)
        self.publish({"A": self.props(a), "B": self.props(b)})
        d.show()
        W.QApplication.processEvents()
        d.cards_view.card_by_code("A").click()
        enter(d, "B", "weight_edit", "55.00")
        enter(d, "B", "code_edit", "B-renamed")
        d.btn_edit_section.click()
        s = d._active_edit_session
        self.assertIsNotNone(s)
        self.assertEqual((s.size_code, s.asset_path), ("B-renamed", b))
        f.owned_docs.add(s.working_doc_name)
        wd = App.getDocument(s.working_doc_name)
        sk = wd.getObject(s.working_sketch_name)
        height = next(i for i, c in enumerate(sk.Constraints)
                      if c.Type == "Distance" and abs(c.Value - 35) < .001)
        sk.setDatum(height, App.Units.Quantity("55 mm"))
        wd.recompute()
        d.cards_view.card_by_code("A").click()
        d.btn_apply_edit.click()
        d.btn_save.click()
        self.assertFalse(d.is_dirty, f.warnings_logged)
        saved = f.manager.get_library("CustomFolderLib")["Custom Profile"]["sizes"]
        self.assertEqual(saved["A"]["asset_path"], a)
        self.assertEqual(saved["A"]["Weight"], "19.23")
        self.assertAlmostEqual(float(saved["B-renamed"]["Weight"]), 30.22, places=1)
        self.assertEqual(saved["B-renamed"]["independent_tag"], 17)
        family(d, "Square Hollow")
        family(d, "Custom Profile")
        enter(d, "B-renamed", "weight_edit", "44.50")
        family(d, "Square Hollow")
        family(d, "Custom Profile")
        self.assertEqual(d.cards_view.card_by_code("B-renamed").weight_edit.text(),
                         "44.50")
        before = disk(f.folder_lib_path)
        f.manager.save_user_library("Other", {"Square Hollow":
            {"norm": "Other", "fillet": False, "sizes": {}}})
        d.refresh_libraries(select_name="CustomFolderLib")
        enter(d, "B-renamed", "weight_edit", "66.00")
        with patch.object(W.QMessageBox, "question", return_value=W.QMessageBox.Cancel):
            library(d, "Other")
        self.assertEqual(d.current_lib_meta["name"], "CustomFolderLib")
        self.assertEqual(d.cards_view.card_by_code("B-renamed").weight_edit.text(),
                         "66.00")
        self.assertEqual(disk(f.folder_lib_path), before)
        d.btn_close.click()
        self.assertEqual(disk(f.folder_lib_path), before)

    def test_preview_identity_open_source_and_fallbacks(self):
        f, d = self.f, self.d
        rel = f._create_published_asset("ind_identity", width=100, height=30)
        full = os.path.join(f.folder_lib_path, rel)
        source = App.openDocument(full)
        f.owned_docs.add(source.Name)
        f._create_rect_sketch(source, "Alternate", width=30, height=100)
        source.recompute()
        source.save()
        bad = Path(f.folder_lib_path, "sections", "bad.FCStd")
        bad.write_bytes(b"not a native document\n")
        self.publish({"Wide": self.props(rel),
                      "Tall": self.props(rel, "Alternate"),
                      "Missing": self.props("sections/missing.FCStd"),
                      "Corrupt": self.props("sections/bad.FCStd")})
        source = App.getDocument(source.Name)
        source.getObject("Section").Label = "unsaved user label"
        App.setActiveDocument(source.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source.Name, "Section")
        def state():
            doc = App.getDocument(source.Name)
            return (set(App.listDocuments()), App.ActiveDocument.Name, selection(),
                    [(o.Name, o.Label, tuple(o.State),
                      o.Shape.exportBrepToString()) for o in doc.Objects])
        before, files = state(), disk(f.folder_lib_path)
        family(d, "Square Hollow")
        family(d, "Custom Profile")
        wide, tall = image(d, "Wide"), image(d, "Tall")
        self.assertNotEqual(wide, tall)
        self.assertEqual(image(d, "Missing"), image(d, "Corrupt"))
        self.assertNotEqual(wide, image(d, "Missing"))
        for _ in range(2):
            family(d, "Square Hollow")
            family(d, "Custom Profile")
            self.assertEqual(image(d, "Wide"), wide)
            self.assertEqual(image(d, "Tall"), tall)
            self.assertEqual(state(), before)
            self.assertEqual(disk(f.folder_lib_path), files)
        d.resize(1100, 800)
        d.show()
        W.QApplication.processEvents()
        self.assertTrue(d.grab().save(os.environ.get("FF_CARDS_SCREENSHOT", os.path.join(f.test_root, "cards-preview.png"))))


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(IndependentCards)

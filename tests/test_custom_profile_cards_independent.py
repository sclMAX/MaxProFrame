import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_custom_profile_cards as fixture

App, Gui = fixture.App, fixture.Gui
W, C = fixture.QtWidgets, fixture.QtCore
QtGui = fixture.QtGui


def _log_checkpoint(marker):
    reports_dir = os.environ.get("FF_REPORTS")
    if not reports_dir:
        return
    try:
        with open(os.path.join(reports_dir, "card-independent.log"), "a", encoding="utf-8") as stream:
            stream.write(marker + "\n")
            stream.flush()
    except OSError:
        pass


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
    return {str(p.relative_to(root)): p.read_bytes() for p in Path(root).rglob("*") if p.is_file()}


def selection():
    return [(s.DocumentName, s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]


def image(d, code):
    return d.cards_view.card_by_code(code).thumbnail_label.pixmap().toImage()


def enter(d, code, field, text):
    card = d.cards_view.card_by_code(code)
    edit = getattr(card, field)
    # Exercise the real focus event filter synchronously, without selecting the
    # card first or pumping unrelated FreeCAD startup/rendering events.
    _log_checkpoint(f"before: enter.sendFocusIn code={code} field={field}")
    W.QApplication.sendEvent(edit, QtGui.QFocusEvent(C.QEvent.FocusIn, C.Qt.OtherFocusReason))
    _log_checkpoint(f"after: enter.sendFocusIn code={code} field={field}")
    _log_checkpoint(f"before: enter.setText code={code} field={field}")
    edit.setText(text)
    _log_checkpoint(f"after: enter.setText code={code} field={field}")


class IndependentCards(unittest.TestCase):
    def setUp(self):
        _log_checkpoint(f"before: setUp test={self.id()}")
        self.f = fixture.TestCustomProfileCards("runTest")
        self.f.setUp()
        self.d = self.f.dialog
        self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "offscreen")
        _log_checkpoint(f"after: setUp test={self.id()}")

    def tearDown(self):
        _log_checkpoint(f"before: tearDown test={self.id()}")
        self.f.tearDown()
        _log_checkpoint(f"after: tearDown test={self.id()}")

    def publish(self, entries):
        f = self.f
        data = f.manager.get_library("CustomFolderLib")
        data["Custom Profile"]["sizes"] = entries
        f.manager.save_folder_library(f.folder_lib_path, data, overwrite=True)
        self.d.refresh_libraries(select_name="CustomFolderLib")
        family(self.d, "Custom Profile")

    def props(self, rel, name="Section"):
        return dict(
            Height="35",
            Width="70",
            Thickness="0",
            Weight="19.23",
            asset_path=rel,
            object_name=name,
            asset_id=Path(rel).stem,
            independent_tag=17,
        )

    def test_selected_edits_apply_and_cancel(self):
        f, d = self.f, self.d
        _log_checkpoint('before: a = f._create_published_asset("ind_a", width=50, height=50)')
        a = f._create_published_asset("ind_a", width=50, height=50)
        _log_checkpoint('after: a = f._create_published_asset("ind_a", width=50, height=50)')
        _log_checkpoint('before: b = f._create_published_asset("ind_b", width=70, height=35)')
        b = f._create_published_asset("ind_b", width=70, height=35)
        _log_checkpoint('after: b = f._create_published_asset("ind_b", width=70, height=35)')
        _log_checkpoint('before: self.publish({"A": self.props(a), "B": self.props(b)})')
        self.publish({"A": self.props(a), "B": self.props(b)})
        _log_checkpoint('after: self.publish({"A": self.props(a), "B": self.props(b)})')
        # This functional test exercises model signals and focus routing, not
        # desktop activation. The separate preview test retains rendering checks.
        _log_checkpoint('before: d.cards_view.card_by_code("A").click()')
        d.cards_view.card_by_code("A").click()
        _log_checkpoint('after: d.cards_view.card_by_code("A").click()')
        self.assertEqual(d.table_sizes.item(d.table_sizes.currentRow(), 0).text(), "A")
        _log_checkpoint('before: enter(d, "B", "weight_edit", "55.00")')
        enter(d, "B", "weight_edit", "55.00")
        _log_checkpoint('after: enter(d, "B", "weight_edit", "55.00")')
        self.assertEqual(d.table_sizes.item(d.table_sizes.currentRow(), 0).text(), "B")
        _log_checkpoint('before: enter(d, "B", "code_edit", "B-renamed")')
        enter(d, "B", "code_edit", "B-renamed")
        _log_checkpoint('after: enter(d, "B", "code_edit", "B-renamed")')
        self.assertEqual(d.table_sizes.item(d.table_sizes.currentRow(), 0).text(), "B-renamed")
        _log_checkpoint("before: d.btn_edit_section.click()")
        d.btn_edit_section.click()
        _log_checkpoint("after: d.btn_edit_section.click()")
        s = d._active_edit_session
        self.assertIsNotNone(s)
        self.assertEqual((s.size_code, s.asset_path), ("B-renamed", b))
        f.owned_docs.add(s.working_doc_name)
        wd = App.getDocument(s.working_doc_name)
        sk = wd.getObject(s.working_sketch_name)
        height = next(i for i, c in enumerate(sk.Constraints) if c.Type == "Distance" and abs(c.Value - 35) < 0.001)
        _log_checkpoint('before: sk.setDatum(height, App.Units.Quantity("55 mm"))')
        sk.setDatum(height, App.Units.Quantity("55 mm"))
        _log_checkpoint('after: sk.setDatum(height, App.Units.Quantity("55 mm"))')
        _log_checkpoint("before: wd.recompute()")
        wd.recompute()
        _log_checkpoint("after: wd.recompute()")
        _log_checkpoint('before: d.cards_view.card_by_code("A").click()')
        d.cards_view.card_by_code("A").click()
        _log_checkpoint('after: d.cards_view.card_by_code("A").click()')
        _log_checkpoint("before: d.btn_apply_edit.click()")
        d.btn_apply_edit.click()
        _log_checkpoint("after: d.btn_apply_edit.click()")
        _log_checkpoint("before: d.btn_save.click()")
        d.btn_save.click()
        _log_checkpoint("after: d.btn_save.click()")
        self.assertFalse(d.is_dirty, f.warnings_logged)
        saved = f.manager.get_library("CustomFolderLib")["Custom Profile"]["sizes"]
        self.assertEqual(saved["A"]["asset_path"], a)
        self.assertEqual(saved["A"]["Weight"], "19.23")
        self.assertAlmostEqual(float(saved["B-renamed"]["Weight"]), 30.22, places=1)
        self.assertEqual(saved["B-renamed"]["independent_tag"], 17)
        _log_checkpoint('before: family(d, "Square Hollow")')
        family(d, "Square Hollow")
        _log_checkpoint('after: family(d, "Square Hollow")')
        _log_checkpoint('before: family(d, "Custom Profile")')
        family(d, "Custom Profile")
        _log_checkpoint('after: family(d, "Custom Profile")')
        _log_checkpoint('before: enter(d, "B-renamed", "weight_edit", "44.50")')
        enter(d, "B-renamed", "weight_edit", "44.50")
        _log_checkpoint('after: enter(d, "B-renamed", "weight_edit", "44.50")')
        _log_checkpoint('before: family(d, "Square Hollow")')
        family(d, "Square Hollow")
        _log_checkpoint('after: family(d, "Square Hollow")')
        _log_checkpoint('before: family(d, "Custom Profile")')
        family(d, "Custom Profile")
        _log_checkpoint('after: family(d, "Custom Profile")')
        self.assertEqual(d.cards_view.card_by_code("B-renamed").weight_edit.text(), "44.50")
        before = disk(f.folder_lib_path)
        f.manager.save_user_library("Other", {"Square Hollow": {"norm": "Other", "fillet": False, "sizes": {}}})
        _log_checkpoint('before: d.refresh_libraries(select_name="CustomFolderLib")')
        d.refresh_libraries(select_name="CustomFolderLib")
        _log_checkpoint('after: d.refresh_libraries(select_name="CustomFolderLib")')
        _log_checkpoint('before: enter(d, "B-renamed", "weight_edit", "66.00")')
        enter(d, "B-renamed", "weight_edit", "66.00")
        _log_checkpoint('after: enter(d, "B-renamed", "weight_edit", "66.00")')
        with patch.object(W.QMessageBox, "question", return_value=W.QMessageBox.Cancel):
            _log_checkpoint('before: library(d, "Other")')
            library(d, "Other")
            _log_checkpoint('after: library(d, "Other")')
        self.assertEqual(d.current_lib_meta["name"], "CustomFolderLib")
        self.assertEqual(d.cards_view.card_by_code("B-renamed").weight_edit.text(), "66.00")
        self.assertEqual(disk(f.folder_lib_path), before)
        _log_checkpoint("before: d.btn_close.click()")
        d.btn_close.click()
        _log_checkpoint("after: d.btn_close.click()")
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
        self.publish(
            {
                "Wide": self.props(rel),
                "Tall": self.props(rel, "Alternate"),
                "Missing": self.props("sections/missing.FCStd"),
                "Corrupt": self.props("sections/bad.FCStd"),
            }
        )
        source = App.getDocument(source.Name)
        source.getObject("Section").Label = "unsaved user label"
        App.setActiveDocument(source.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source.Name, "Section")

        def state():
            doc = App.getDocument(source.Name)
            return (
                set(App.listDocuments()),
                App.ActiveDocument.Name,
                selection(),
                [(o.Name, o.Label, tuple(o.State), o.Shape.exportBrepToString()) for o in doc.Objects],
            )

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
        self.assertTrue(
            d.grab().save(os.environ.get("FF_CARDS_SCREENSHOT", os.path.join(f.test_root, "cards-preview.png")))
        )


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(IndependentCards)

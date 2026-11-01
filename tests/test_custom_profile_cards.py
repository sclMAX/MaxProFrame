"""Native GUI regression tests for Custom Profile Cards view and thumbnail editor (T1).

Covers S1, S2, S3, S4, and control requirements:
- S1: Cards switch on Custom Profile; silhouettes preserve hole, curves, and aspect ratio;
      standard families retain their table.
- S2: Cards display NO dimensions; code and weight are editable and persist through save/reload;
      non-column metadata preserved intact; duplicate codes and invalid weights rejected without
      stored mutations.
- S3: Applying actual geometry datum edit recalculates manual weight (recalculate_weight_on_geometry_edit);
      no manual-weight metadata flag added.
- S4: Preview inspection isolates documents and selection (no leaked open docs, active doc and
      selection preserved); harmless placeholder for missing/bad/traversal assets; no thumbnail
      files written into libraries.
- Control: Standard family table operations preserved; card selection routes capture, edit,
           apply, and delete actions to the intended second row.
"""

import copy
import json
import math
import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher

from freecad.maxproframe.custom_section_geometry import build_custom_section_face
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog


class TestCustomProfileCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    def setUp(self):
        # Snapshot any preexisting documents so tearDown preserves them
        self.preexisting_docs = set(App.listDocuments().keys())
        self.owned_docs = set()

        self.workspace = tempfile.TemporaryDirectory(prefix="ff_test_cards_")
        self.test_root = self.workspace.name
        self.user_dir = os.path.join(self.test_root, "user")
        self.stock_dir = os.path.join(self.test_root, "stock")
        self.reg_dir = os.path.join(self.test_root, "registry")
        self.reg_path = os.path.join(self.reg_dir, "folders.json")
        os.makedirs(self.user_dir, exist_ok=True)
        os.makedirs(self.stock_dir, exist_ok=True)
        os.makedirs(self.reg_dir, exist_ok=True)

        self.manager = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )

        self.folder_lib_path = os.path.join(self.test_root, "CustomFolderLib")
        self.manager.create_folder_library(
            self.folder_lib_path,
            "CustomFolderLib",
            material="Steel",
            density=7.85,
            data={
                "Square Hollow": {
                    "norm": "EN 10219",
                    "fillet": False,
                    "sizes": {
                        "40x40x2": {
                            "Height": "40",
                            "Width": "40",
                            "Thickness": "2",
                            "Flange Thickness": "0",
                            "Radius1": "0",
                            "Radius2": "0",
                            "Weight": "2.4",
                        }
                    },
                },
                "Custom Profile": {
                    "norm": "Custom",
                    "fillet": False,
                    "canonical_family": "Custom Profile",
                    "sizes": {},
                },
            },
        )

        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

        self.messages = ExitStack()
        self.warnings_logged = []

        def _record_warning(parent, title, text, *args, **kwargs):
            self.warnings_logged.append(str(text))
            return QtWidgets.QMessageBox.Ok

        for method in ("warning", "critical"):
            self.messages.enter_context(patch.object(QtWidgets.QMessageBox, method, side_effect=_record_warning))
        for method in ("information", "question"):
            self.messages.enter_context(
                patch.object(QtWidgets.QMessageBox, method, return_value=QtWidgets.QMessageBox.Ok)
            )

        self.dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.dialog.refresh_libraries(select_name="CustomFolderLib")

    def tearDown(self):
        # 1. Close active edit session working documents specifically
        if hasattr(self, "dialog") and self.dialog is not None:
            session = getattr(self.dialog, "_active_edit_session", None)
            if session is not None and getattr(session, "working_doc_name", None):
                self.owned_docs.add(session.working_doc_name)
            try:
                self.dialog.close()
            except Exception:
                pass

        # 2. Clear Gui.Selection
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass

        # 3. Close ONLY fixture-owned docs and tracked session docs; preserve preexisting docs
        current_docs = set(App.listDocuments().keys())
        docs_to_close = self.owned_docs | (current_docs - self.preexisting_docs)
        for doc_name in list(docs_to_close):
            if doc_name not in self.preexisting_docs and doc_name in App.listDocuments():
                try:
                    App.closeDocument(doc_name)
                except Exception:
                    pass
        self.owned_docs.clear()

        # 4. Close message patches
        if hasattr(self, "messages"):
            try:
                self.messages.close()
            except Exception:
                pass

        # 5. Clean up temporary workspace
        try:
            self.workspace.cleanup()
        except Exception:
            pass

    # --- Helper methods ---

    def _new_doc(self, name_prefix="TestDoc"):
        doc = App.newDocument(name_prefix)
        self.owned_docs.add(doc.Name)
        return doc

    def _create_rect_sketch(self, doc, name="RectSection", width=120.0, height=60.0, with_hole=False):
        s = doc.addObject("Sketcher::SketchObject", name)
        pts = [(0, 0), (width, 0), (width, height), (0, height)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        for i in [0, 2]:
            s.addConstraint(Sketcher.Constraint("Horizontal", i))
        for i in [1, 3]:
            s.addConstraint(Sketcher.Constraint("Vertical", i))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        s.addConstraint(Sketcher.Constraint("Distance", 0, float(width)))
        s.addConstraint(Sketcher.Constraint("Distance", 1, float(height)))

        if with_hole:
            # Circular inner hole at center (hole + curve) with radius = 15 mm
            r = min(width, height) / 4.0
            cx, cy = width / 2.0, height / 2.0
            s.addGeometry(Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), r), False)
            # Construction geometry (must be excluded from silhouette)
            s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(width, height, 0)), True)

        doc.recompute()
        return s

    def _create_published_asset(self, asset_id="sec_pub_1", width=80.0, height=40.0, with_hole=False):
        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        doc = self._new_doc("PublishedAssetDoc")
        s = self._create_rect_sketch(doc, "Section", width=width, height=height, with_hole=with_hole)
        filename = f"{asset_id}.FCStd"
        target_path = os.path.join(sections_dir, filename)
        doc_name = doc.Name
        doc.saveAs(target_path)
        App.closeDocument(doc_name)
        if doc_name in self.owned_docs:
            self.owned_docs.remove(doc_name)
        return os.path.join("sections", filename)

    def _select_family(self, family_name):
        self.dialog.current_lib_data.setdefault(
            family_name,
            {"norm": "Custom", "fillet": False, "canonical_family": family_name, "sizes": {}},
        )
        self.dialog.current_family = None
        self.dialog._populate_families(select_family=family_name)

    # --- Cards View interface discovery & interaction helpers ---

    def _get_cards_view(self):
        """Gracefully discover the cards view widget on ProfileLibraryManagerDialog."""
        cards_view = getattr(self.dialog, "cards_view", None)
        if cards_view is None:
            cards_view = self.dialog.findChild(QtWidgets.QWidget, "custom_profile_cards")
        return cards_view

    def _get_card_widget(self, cards_view, index_or_code):
        if cards_view is None:
            return None
        if isinstance(index_or_code, int):
            if hasattr(cards_view, "card"):
                return cards_view.card(index_or_code)
            cards = getattr(cards_view, "cards", None)
            if callable(cards):
                cards = cards()
            if isinstance(cards, (list, tuple)) and 0 <= index_or_code < len(cards):
                return cards[index_or_code]
        else:
            if hasattr(cards_view, "card_by_code"):
                return cards_view.card_by_code(str(index_or_code))
        return None

    def _get_card_code_edit(self, card):
        if card is None:
            return None
        for attr in ("code_edit", "le_code"):
            w = getattr(card, attr, None)
            if w is not None:
                return w
        return card.findChild(QtWidgets.QLineEdit, "card_code")

    def _get_card_weight_edit(self, card):
        if card is None:
            return None
        for attr in ("weight_edit", "le_weight"):
            w = getattr(card, attr, None)
            if w is not None:
                return w
        return card.findChild(QtWidgets.QLineEdit, "card_weight")

    def _get_card_thumbnail_label(self, card):
        if card is None:
            return None
        for attr in ("thumbnail_label", "lbl_thumbnail"):
            w = getattr(card, attr, None)
            if w is not None:
                return w
        return card.findChild(QtWidgets.QLabel, "card_thumbnail")

    def _select_card(self, cards_view, index):
        if hasattr(cards_view, "select_card"):
            cards_view.select_card(index)
        elif hasattr(cards_view, "setCurrentIndex"):
            cards_view.setCurrentIndex(index)
        else:
            card = self._get_card_widget(cards_view, index)
            if card and hasattr(card, "click"):
                card.click()
            elif card and hasattr(card, "setSelected"):
                card.setSelected(True)

    # --- S1: Cards switch & silhouette actual hole + curve / aspect ratio ---

    def test_s1_cards_switch_and_silhouette_geometry(self):
        """S1: Selecting Custom Profile switches from table to cards view with silhouette thumbnails.

        Silhouettes preserve proportions (aspect ratio 2:1), curves, and holes, excluding construction geometry.
        Asserts actual QImage pixel effects (foreground extents, transparent center hole, solid material,
        and absent construction diagonal) without relying on exact theme colors or non-square canvas.
        Selecting a standard family restores the table view.
        """
        # Asset 1: 120x60 (2:1 aspect ratio) with circular hole (r=15 at center) and diagonal construction line
        rel_asset_1 = self._create_published_asset("sec_s1_hole", width=120.0, height=60.0, with_hole=True)
        # Asset 2: 50x50 (1:1 square)
        rel_asset_2 = self._create_published_asset("sec_s1_square", width=50.0, height=50.0, with_hole=False)

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Hole_120x60"] = {
            "Height": "60.0",
            "Width": "120.0",
            "Thickness": "0.0",
            "Weight": "50.97",
            "asset_path": rel_asset_1,
            "object_name": "Section",
            "asset_id": "sec_s1_hole",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Square_50x50"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.63",
            "asset_path": rel_asset_2,
            "object_name": "Section",
            "asset_id": "sec_s1_square",
        }

        # 1. Switch to Custom Profile -> cards view visible, table hidden
        self._select_family("Custom Profile")
        cards_view = self._get_cards_view()
        self.assertIsNotNone(
            cards_view,
            "ProfileLibraryManagerDialog must provide 'cards_view' widget when Custom Profile is selected.",
        )
        self.assertFalse(cards_view.isHidden(), "cards_view must be visible for Custom Profile.")
        self.assertTrue(self.dialog.table_sizes.isHidden(), "table_sizes must be hidden when cards view is active.")

        # 2. Check cards count
        count_fn = getattr(cards_view, "count", None)
        card_count = count_fn() if callable(count_fn) else len(getattr(cards_view, "cards", []))
        self.assertEqual(card_count, 2, "cards_view must show 2 cards for the 2 profiles.")

        # 3. Silhouette pixel inspection for Hole_120x60
        card0 = self._get_card_widget(cards_view, 0)
        lbl_thumb0 = self._get_card_thumbnail_label(card0)
        self.assertIsNotNone(lbl_thumb0, "Card 0 must have a thumbnail label.")
        pixmap0 = lbl_thumb0.pixmap()
        self.assertIsNotNone(pixmap0, "Thumbnail label must have a pixmap.")
        self.assertFalse(pixmap0.isNull(), "Thumbnail pixmap must not be null.")

        img = pixmap0.toImage()
        w, h = img.width(), img.height()
        bg_pixel = img.pixel(0, 0)
        bg_alpha = QtGui.qAlpha(bg_pixel)

        def is_fg(px, py):
            if not (0 <= px < w and 0 <= py < h):
                return False
            pix = img.pixel(px, py)
            alpha = QtGui.qAlpha(pix)
            if bg_alpha == 0:
                return alpha > 32
            return pix != bg_pixel and alpha > 32

        fg_coords = [(x, y) for y in range(h) for x in range(w) if is_fg(x, y)]
        self.assertTrue(len(fg_coords) > 0, "Thumbnail image must contain painted foreground silhouette pixels.")

        min_x = min(x for x, y in fg_coords)
        max_x = max(x for x, y in fg_coords)
        min_y = min(y for x, y in fg_coords)
        max_y = max(y for x, y in fg_coords)

        fg_width = max_x - min_x + 1
        fg_height = max_y - min_y + 1

        # Assert painted alpha/foreground extents ratio 2:1 with reasonable tolerance
        aspect_ratio = fg_width / float(fg_height)
        self.assertTrue(
            1.6 <= aspect_ratio <= 2.4,
            f"Painted foreground extents aspect ratio must be ~2:1 (got {aspect_ratio:.2f}, w={fg_width}, h={fg_height})",
        )

        cx = (min_x + max_x) // 2
        cy = (min_y + max_y) // 2

        # Center circular hole must be transparent/background (hole has no material)
        self.assertFalse(
            is_fg(cx, cy),
            "Center of thumbnail must be transparent/background (circular hole).",
        )

        # Solid material samples above and below the hole
        sample_solid_top = min_y + fg_height // 8
        sample_solid_bottom = max_y - fg_height // 8
        self.assertTrue(
            is_fg(cx, sample_solid_top),
            "Region between top edge and hole must be solid painted material.",
        )
        self.assertTrue(
            is_fg(cx, sample_solid_bottom),
            "Region between bottom edge and hole must be solid painted material.",
        )

        # Curved-edge sample: points to left and right of the circular hole must be solid material
        sample_left = cx - fg_width // 4
        sample_right = cx + fg_width // 4
        self.assertTrue(
            is_fg(sample_left, cy),
            "Region to the left of the circular hole must be solid painted material.",
        )
        self.assertTrue(
            is_fg(sample_right, cy),
            "Region to the right of the circular hole must be solid painted material.",
        )

        # Construction diagonal absent: construction line from corner to corner passes through center
        # It must NOT be painted across the transparent center hole region
        for t in (-max(1, fg_height // 12), 0, max(1, fg_height // 12)):
            diag_x = cx + int(round(t * aspect_ratio))
            diag_y = cy + t
            self.assertFalse(
                is_fg(diag_x, diag_y),
                f"Construction diagonal line must not be drawn inside hole at ({diag_x}, {diag_y}).",
            )

        # 4. Switch to standard family -> table visible, cards hidden
        self._select_family("Square Hollow")
        self.assertTrue(cards_view.isHidden(), "cards_view must be hidden when standard family is selected.")
        self.assertFalse(self.dialog.table_sizes.isHidden(), "table_sizes must be visible for standard family.")

        # 5. Switch back to Custom Profile -> cards restored
        self._select_family("Custom Profile")
        self.assertFalse(cards_view.isHidden())
        self.assertTrue(self.dialog.table_sizes.isHidden())

    # --- S2: No dimensions on cards + editable code/weight persisted with metadata intact ---

    def test_s2_cards_no_dimensions_and_editable_code_weight_persisted(self):
        """S2: Cards show NO dimensions; code and weight are editable and persist through save/reload

        with non-column and numeric metadata intact; verified via LibraryManager reload;
        read-only behavior enforced for non-editable libraries without optional pass paths.
        """
        rel_asset = self._create_published_asset("sec_s2_meta", width=80.0, height=40.0)
        custom_props = {
            "Height": "40.0",
            "Width": "80.0",
            "Thickness": "0.0",
            "Weight": "25.12",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_s2_meta",
            "custom_project_tag": "Aerospace_6061",
            "custom_numeric_id": 9942,
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_S2_Orig"] = copy.deepcopy(custom_props)
        self._select_family("Custom Profile")

        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view, "cards_view must exist to verify card fields and editing.")
        card = self._get_card_widget(cards_view, 0)
        self.assertIsNotNone(card, "First card widget must exist.")

        # S2: Cards show NO dimensions
        for dim_key in ("height", "width", "thickness", "flange_thickness", "radius1", "radius2", "lip_length"):
            self.assertIsNone(
                card.findChild(QtWidgets.QLineEdit, f"card_{dim_key}"), f"Card must not have {dim_key} input."
            )
            self.assertIsNone(
                card.findChild(QtWidgets.QLabel, f"lbl_{dim_key}"), f"Card must not have {dim_key} label."
            )

        # S2: Code and weight are edited in the properties modal.
        code_edit = self._get_card_code_edit(card)
        weight_edit = self._get_card_weight_edit(card)
        self.assertIsNotNone(code_edit, "Card must provide code edit QLineEdit.")
        self.assertIsNotNone(weight_edit, "Card must provide weight edit QLineEdit.")
        self.assertTrue(code_edit.isReadOnly(), "Card values are display-only; use Edit Properties.")
        self.assertTrue(weight_edit.isReadOnly(), "Card values are display-only; use Edit Properties.")
        self.assertTrue(card.btn_edit_properties.isEnabled())

        # Exercise the real modal, not programmatic edits of the display widgets.
        def edit_properties():
            modal = QtWidgets.QApplication.activeModalWidget()
            modal.findChild(QtWidgets.QLineEdit, "property_code").setText("Sec_S2_Renamed")
            modal.findChild(QtWidgets.QLineEdit, "property_weight").setText("38.45")
            modal.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()

        QtCore.QTimer.singleShot(0, edit_properties)
        card.btn_edit_properties.click()

        # Bidirectional check: card edits immediately reflect in underlying table item model
        self.assertEqual(self.dialog.table_sizes.item(0, 0).text(), "Sec_S2_Renamed")
        self.assertEqual(self.dialog.table_sizes.item(0, 7).text(), "38.45")

        self.warnings_logged.clear()
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Saving valid card edits must produce no warnings.")
        self.assertFalse(self.dialog.is_dirty)

        # Verify via actual LibraryManager reload (not only raw JSON inspection)
        reloaded_mgr = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )
        reloaded_catalog = reloaded_mgr.get_library("CustomFolderLib")
        self.assertIsNotNone(reloaded_catalog, "LibraryManager must reload CustomFolderLib.")
        sizes = reloaded_catalog["Custom Profile"]["sizes"]
        self.assertIn("Sec_S2_Renamed", sizes)
        self.assertNotIn("Sec_S2_Orig", sizes)
        saved_entry = sizes["Sec_S2_Renamed"]
        self.assertEqual(saved_entry.get("Weight"), "38.45")
        self.assertEqual(saved_entry.get("custom_project_tag"), "Aerospace_6061")
        self.assertEqual(saved_entry.get("custom_numeric_id"), 9942)
        self.assertEqual(saved_entry.get("asset_path"), rel_asset)
        self.assertEqual(saved_entry.get("asset_id"), "sec_s2_meta")
        self.assertEqual(saved_entry.get("Height"), "40.0")
        self.assertEqual(saved_entry.get("Width"), "80.0")

        # Bidirectional check: direct edit to authoritative table item model reflects to card
        self.dialog.table_sizes.item(0, 0).setText("Sec_S2_TableEdit")
        self.dialog.table_sizes.item(0, 7).setText("42.10")
        self.assertEqual(code_edit.text(), "Sec_S2_TableEdit")
        self.assertEqual(weight_edit.text(), "42.10")
        self.assertTrue(self.dialog.is_dirty)

        self.warnings_logged.clear()
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Saving table edits via commit must produce no warnings.")
        self.assertFalse(self.dialog.is_dirty)

        reloaded_catalog2 = reloaded_mgr.get_library("CustomFolderLib")
        self.assertIn("Sec_S2_TableEdit", reloaded_catalog2["Custom Profile"]["sizes"])
        self.assertNotIn("Sec_S2_Renamed", reloaded_catalog2["Custom Profile"]["sizes"])
        self.assertEqual(reloaded_catalog2["Custom Profile"]["sizes"]["Sec_S2_TableEdit"]["Weight"], "42.10")
        self.assertEqual(
            reloaded_catalog2["Custom Profile"]["sizes"]["Sec_S2_TableEdit"]["custom_project_tag"], "Aerospace_6061"
        )

        # Read-only library check: assert widgets exist and are strictly read-only (no optional paths)
        self.dialog.current_lib_meta["is_user"] = False
        self._select_family("Custom Profile")
        cards_view_ro = self._get_cards_view()
        self.assertIsNotNone(cards_view_ro, "cards_view must exist when library is read-only.")
        card_ro = self._get_card_widget(cards_view_ro, 0)
        self.assertIsNotNone(card_ro, "Card widget must exist when library is read-only.")
        c_ro = self._get_card_code_edit(card_ro)
        w_ro = self._get_card_weight_edit(card_ro)
        self.assertIsNotNone(c_ro, "Code edit must exist in read-only card.")
        self.assertIsNotNone(w_ro, "Weight edit must exist in read-only card.")
        self.assertTrue(c_ro.isReadOnly(), "Code must be read-only in non-editable library.")
        self.assertTrue(w_ro.isReadOnly(), "Weight must be read-only in non-editable library.")

    # --- S2 Guards: Duplicate code and invalid weight rejection ---

    def test_s2_validation_rejects_duplicate_code_and_invalid_weight(self):
        """S2 guards: Rejects duplicate codes and invalid/nonfinite/nonpositive weights

        without publishing invalid catalog data or mutating stored data. Warnings are cleared
        per attempt, full catalog bytes asserted unchanged for each reject, Guard fixtures saved
        through public save before snapshot, and no unexpected warnings after successful actions.
        """
        rel_asset_a = self._create_published_asset("sec_guard_a", width=50.0, height=50.0)
        rel_asset_b = self._create_published_asset("sec_guard_b", width=60.0, height=60.0)
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Guard_A"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset_a,
            "object_name": "Section",
            "asset_id": "sec_guard_a",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Guard_B"] = {
            "Height": "60.0",
            "Width": "60.0",
            "Thickness": "0.0",
            "Weight": "28.26",
            "asset_path": rel_asset_b,
            "object_name": "Section",
            "asset_id": "sec_guard_b",
        }

        # Select Custom Profile and save Guard fixtures through public save before snapshot
        self._select_family("Custom Profile")
        self.warnings_logged.clear()
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Initial save of Guard fixtures must produce no warnings.")
        self.assertFalse(self.dialog.is_dirty, "Dialog must not be dirty after successful initial save.")

        manifest_path = os.path.join(self.folder_lib_path, "library.json")
        with open(manifest_path, "rb") as f:
            clean_manifest_bytes = f.read()

        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view, "cards_view must exist to test validation guards.")

        card_b = self._get_card_widget(cards_view, 1)
        self.assertIsNotNone(card_b, "Second card (Guard_B) must exist.")
        code_edit_b = self._get_card_code_edit(card_b)
        self.assertIsNotNone(code_edit_b, "Guard_B code edit must exist.")
        weight_edit_b = self._get_card_weight_edit(card_b)
        self.assertIsNotNone(weight_edit_b, "Guard_B weight edit must exist.")

        # 1. Duplicate code rejection
        self.warnings_logged.clear()
        code_edit_b.setText("Guard_A")
        rejected_dup = False
        try:
            self.dialog._commit_current_family_edits()
            self.dialog.btn_save.click()
        except ValueError:
            rejected_dup = True
        if len(self.warnings_logged) > 0:
            rejected_dup = True

        self.assertTrue(rejected_dup, "Duplicate profile code must be rejected.")
        with open(manifest_path, "rb") as f:
            self.assertEqual(f.read(), clean_manifest_bytes, "Rejected duplicate must not mutate catalog file on disk.")

        # Restore valid code and verify no unexpected warnings
        code_edit_b.setText("Guard_B")
        self.warnings_logged.clear()

        # 2. Invalid weight rejection for EACH reject with warning clearance and catalog bytes check
        invalid_weights = ("not_a_number", "-12.5", "0", "0.0", "nan", "-inf", "inf")
        for bad_w in invalid_weights:
            self.warnings_logged.clear()
            weight_edit_b.setText(bad_w)
            rejected_weight = False
            try:
                self.dialog._commit_current_family_edits()
                self.dialog.btn_save.click()
            except (ValueError, TypeError):
                rejected_weight = True
            if len(self.warnings_logged) > 0:
                rejected_weight = True

            self.assertTrue(rejected_weight, f"Invalid weight '{bad_w}' must be rejected.")
            with open(manifest_path, "rb") as f:
                self.assertEqual(
                    f.read(),
                    clean_manifest_bytes,
                    f"Full catalog bytes must remain unchanged after rejecting invalid weight '{bad_w}'.",
                )

        # 3. Restore valid weight and confirm clean save with no unexpected warnings
        self.warnings_logged.clear()
        weight_edit_b.setText("28.26")
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Restoring valid values and saving must produce no warnings.")
        self.assertFalse(self.dialog.is_dirty)

    # --- S3: Applying actual geometry datum edit recalculates manual weight ---

    def test_s3_geometry_edit_recalculates_manual_weight(self):
        """S3: Manually entered weight persists through card edits, but applying a sketch geometry edit

        recomputes and replaces it using section face area and density. No manual-weight metadata flag added.
        Uses genuine SectionEditSession fields and close signature.
        """
        rel_asset = self._create_published_asset("sec_s3_recalc", width=80.0, height=40.0)
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_S3"] = {
            "Height": "40.0",
            "Width": "80.0",
            "Thickness": "0.0",
            "Weight": "25.12",
            "asset_path": rel_asset,
            "object_name": "Section",
            "asset_id": "sec_s3_recalc",
        }
        self._select_family("Custom Profile")
        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view, "cards_view must exist to test weight recalculation on geometry edit.")

        # 1. Enter manual weight on card and save
        card0 = self._get_card_widget(cards_view, 0)
        self.assertIsNotNone(card0)
        w_edit = self._get_card_weight_edit(card0)
        self.assertIsNotNone(w_edit)
        w_edit.setText("55.00")
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()

        # Verify manual weight persisted via LibraryManager reload
        reloaded_mgr = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )
        catalog = reloaded_mgr.get_library("CustomFolderLib")
        self.assertEqual(catalog["Custom Profile"]["sizes"]["Sec_S3"]["Weight"], "55.00")

        # 2. Edit geometry: select card 0 and open edit session
        self._select_card(cards_view, 0)
        self.dialog.btn_edit_section.click()
        session = self.dialog._active_edit_session
        self.assertIsNotNone(session, "Edit session must be active.")
        working_doc_name = getattr(session, "working_doc_name", None)
        self.assertIsNotNone(working_doc_name, "Session must have working_doc_name.")
        self.owned_docs.add(working_doc_name)
        working_doc = App.getDocument(working_doc_name)

        working_sketches = [
            obj
            for obj in working_doc.Objects
            if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
        ]
        self.assertTrue(len(working_sketches) >= 1)
        working_sketch = working_sketches[0]

        height_idx = None
        for idx, c in enumerate(working_sketch.Constraints):
            val = getattr(c, "Value", None)
            if val is not None and abs(float(val) - 40.0) < 1e-3:
                height_idx = idx
                break
        if height_idx is None:
            for idx, c in enumerate(working_sketch.Constraints):
                if getattr(c, "Type", None) == "Distance" and getattr(c, "First", None) == 1:
                    height_idx = idx
                    break
        self.assertIsNotNone(height_idx, "Could not find height constraint on working sketch.")

        qty = App.Units.Quantity("100 mm") if hasattr(App, "Units") else 100.0
        working_sketch.setDatum(height_idx, qty)
        working_doc.recompute()
        self.assertEqual(working_sketch.solve(), 0)

        # 3. Apply geometry edit
        self.dialog.apply_section_edit()

        # 4. S3 INVARIANT: Applying geometry edit recomputes weight and replaces manual 55.00
        # Expected: 80 * 100 * 7.85 * 0.001 = 62.80 kg/m
        card0_updated = self._get_card_widget(cards_view, 0)
        self.assertIsNotNone(card0_updated)
        w_edit_updated = self._get_card_weight_edit(card0_updated)
        self.assertIsNotNone(w_edit_updated)
        updated_weight = float(w_edit_updated.text().strip())
        self.assertAlmostEqual(
            updated_weight,
            62.80,
            places=1,
            msg="Applying geometry edit must recompute weight and replace manual 55.00 with 62.80.",
        )

        # 5. S3 INVARIANT: No manual-weight metadata flag or override option added
        props = self.dialog.current_lib_data["Custom Profile"]["sizes"]["Sec_S3"]
        for flag in ("manual_weight", "manual_override", "is_manual", "custom_weight_flag"):
            self.assertNotIn(flag, props, f"Catalog must not contain manual weight flag '{flag}'.")

        # 6. Save and verify reloaded catalog
        self.dialog.btn_save.click()
        catalog_saved = reloaded_mgr.get_library("CustomFolderLib")
        saved_size = catalog_saved["Custom Profile"]["sizes"]["Sec_S3"]
        self.assertAlmostEqual(float(saved_size["Weight"]), 62.80, places=1)
        self.assertAlmostEqual(float(saved_size["Height"]), 100.0, places=1)

    # --- S4: Preview inspection isolates documents, selection, and confinement ---

    def test_s4_preview_asset_inspection_isolation_and_confinement(self):
        """S4: Generating previews does not modify user sketches, libraries, open documents,

        active document, or selection; snapshots taken after setup assets and user doc creation;
        user sketch checked via snapshot of geometry/constraints/State/Modified without solve();
        actual corrupted file fixture tested alongside missing and traversal paths;
        harmless unavailable preview without crashing; no thumbnail files written to libraries.
        """
        # 1. Setup assets first (including real published, actual corrupt file on disk, missing, traversal)
        rel_asset_valid = self._create_published_asset("sec_s4_valid", width=50.0, height=50.0)

        sections_dir = os.path.join(self.folder_lib_path, "sections")
        os.makedirs(sections_dir, exist_ok=True)
        corrupt_rel = os.path.join("sections", "sec_s4_corrupt.FCStd")
        corrupt_full = os.path.join(self.folder_lib_path, corrupt_rel)
        with open(corrupt_full, "wb") as f:
            f.write(b"NOT_A_VALID_FREECAD_FILE_CORRUPT_HEADER_0xDEADBEEF\n")

        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Valid_Card"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset_valid,
            "object_name": "Section",
            "asset_id": "sec_s4_valid",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Corrupt_Card"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": corrupt_rel,
            "object_name": "Section",
            "asset_id": "sec_corrupt",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Missing_Asset_Card"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": "sections/non_existent_file.FCStd",
            "object_name": "Section",
            "asset_id": "sec_missing",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Traversal_Card"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": "../outside_sandbox.FCStd",
            "object_name": "Section",
            "asset_id": "sec_traversal",
        }

        # 2. Setup user doc and selection AFTER setup assets
        user_doc = self._new_doc("UserDoc_S4")
        user_sketch = self._create_rect_sketch(user_doc, "UserSketch_S4", width=60.0, height=30.0)
        App.setActiveDocument("UserDoc_S4")
        if hasattr(Gui, "Selection"):
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection("UserDoc_S4", "UserSketch_S4")

        # 3. Capture initial snapshots immediately prior to triggering family/cards load
        initial_docs = set(App.listDocuments().keys())
        initial_active_doc_name = App.ActiveDocument.Name if App.ActiveDocument else None
        initial_selection = []
        if hasattr(Gui, "Selection"):
            initial_selection = [(s.DocumentName, s.ObjectName) for s in Gui.Selection.getSelectionEx()]

        # Snapshot sketch properties without calling solve()
        sketch_geom_count_pre = len(user_sketch.Geometry)
        sketch_geom_types_pre = [getattr(g, "TypeId", type(g).__name__) for g in user_sketch.Geometry]
        sketch_constr_count_pre = len(user_sketch.Constraints)
        sketch_state_pre = getattr(user_sketch, "State", None)
        sketch_modified_pre = getattr(user_sketch, "Modified", None)

        initial_lib_files = set(os.listdir(self.folder_lib_path))
        initial_sec_files = set(os.listdir(sections_dir))

        # 4. Trigger family/card load
        self._select_family("Custom Profile")
        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view, "cards_view must exist to inspect preview behavior.")

        # Document isolation: no leaked temporary documents
        current_docs = set(App.listDocuments().keys())
        self.assertEqual(current_docs, initial_docs, "Preview inspection must not leak open documents.")

        # Active document preserved
        current_active = App.ActiveDocument.Name if App.ActiveDocument else None
        self.assertEqual(current_active, initial_active_doc_name, "Active document must be preserved.")

        # Selection preserved
        if hasattr(Gui, "Selection"):
            current_selection = [(s.DocumentName, s.ObjectName) for s in Gui.Selection.getSelectionEx()]
            self.assertEqual(current_selection, initial_selection, "Gui.Selection must be preserved.")

        # User sketch properties untouched without calling solve()
        self.assertEqual(len(user_sketch.Geometry), sketch_geom_count_pre, "Geometry count must not change.")
        self.assertEqual(
            [getattr(g, "TypeId", type(g).__name__) for g in user_sketch.Geometry],
            sketch_geom_types_pre,
            "Geometry types must not change.",
        )
        self.assertEqual(len(user_sketch.Constraints), sketch_constr_count_pre, "Constraints count must not change.")
        self.assertEqual(getattr(user_sketch, "State", None), sketch_state_pre, "Sketch State must not change.")
        self.assertEqual(
            getattr(user_sketch, "Modified", None), sketch_modified_pre, "Sketch Modified must not change."
        )

        # File isolation: no thumbnail files written to library folder or sections
        current_lib_files = set(os.listdir(self.folder_lib_path))
        self.assertEqual(
            current_lib_files, initial_lib_files, "No thumbnail files may be written to folder library root."
        )
        current_sec_files = set(os.listdir(sections_dir))
        self.assertEqual(current_sec_files, initial_sec_files, "No extra files may be written into sections directory.")

        # Harmless fallback for corrupted, missing, and traversal assets (no crash, unavailable placeholder present)
        count_fn = getattr(cards_view, "count", None)
        card_count = count_fn() if callable(count_fn) else len(getattr(cards_view, "cards", []))
        self.assertEqual(card_count, 4, "All 4 cards must render without crashing.")

        card_valid = self._get_card_widget(cards_view, 0)
        self.assertIsNotNone(card_valid)
        lbl_valid = self._get_card_thumbnail_label(card_valid)
        self.assertIsNotNone(lbl_valid)
        self.assertIsNotNone(lbl_valid.pixmap(), "Valid card must render a pixmap.")

        card_corrupt = self._get_card_widget(cards_view, 1)
        self.assertIsNotNone(card_corrupt, "Corrupted asset card must render harmlessly.")
        lbl_corrupt = self._get_card_thumbnail_label(card_corrupt)
        self.assertIsNotNone(lbl_corrupt, "Corrupted asset card must have a thumbnail placeholder.")

        card_missing = self._get_card_widget(cards_view, 2)
        self.assertIsNotNone(card_missing, "Missing asset card must render harmlessly.")
        lbl_missing = self._get_card_thumbnail_label(card_missing)
        self.assertIsNotNone(lbl_missing, "Missing asset card must have a thumbnail placeholder.")

        card_traversal = self._get_card_widget(cards_view, 3)
        self.assertIsNotNone(card_traversal, "Traversal card must render harmlessly.")
        lbl_traversal = self._get_card_thumbnail_label(card_traversal)
        self.assertIsNotNone(lbl_traversal, "Traversal card must have a thumbnail placeholder.")

    # --- Control: Standard family table edits & card selection routing to second row ---

    def test_control_standard_family_table_and_card_selection_routing(self):
        """Control: Preserves standard family table edits and actions; card selection

        routes capture, edit, apply, and delete actions to the intended second row (critical).
        Verifies standard family table saves nonduplicate generated codes and usable values,
        and uses genuine SectionEditSession fields (size_code, asset_path, close(discard_uncommitted=True)).
        """
        # 1. Standard family table operations preserved: add size, nonduplicate code, usable values, save
        self._select_family("Square Hollow")
        cards_view = self._get_cards_view()
        if cards_view is not None:
            self.assertTrue(cards_view.isHidden(), "cards_view must be hidden for standard family.")
        self.assertFalse(self.dialog.table_sizes.isHidden(), "table_sizes must be visible for standard family.")

        init_rows = self.dialog.table_sizes.rowCount()
        self.dialog.btn_add_size.click()
        self.assertEqual(self.dialog.table_sizes.rowCount(), init_rows + 1)
        new_row = self.dialog.table_sizes.rowCount() - 1

        new_code_item = self.dialog.table_sizes.item(new_row, 0)
        self.assertIsNotNone(new_code_item)
        new_code = new_code_item.text().strip()
        self.assertTrue(bool(new_code), "Generated code must not be empty.")
        self.assertNotEqual(new_code, "40x40x2", "Generated code must not duplicate existing '40x40x2'.")

        h_item = self.dialog.table_sizes.item(new_row, 1)
        w_item = self.dialog.table_sizes.item(new_row, 2)
        self.assertTrue(bool(h_item.flags() & QtCore.Qt.ItemIsEditable), "Parametric table cells must remain editable.")
        h_val = float(h_item.text())
        w_val = float(w_item.text())
        self.assertGreater(h_val, 0.0, "Usable height must be positive.")
        self.assertGreater(w_val, 0.0, "Usable width must be positive.")

        self.warnings_logged.clear()
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Saving standard family edits must produce no warnings.")
        self.assertFalse(self.dialog.is_dirty)

        reloaded_mgr = LibraryManager(
            user_dir=self.user_dir,
            stock_dir=self.stock_dir,
            registry_path=self.reg_path,
        )
        catalog = reloaded_mgr.get_library("CustomFolderLib")
        self.assertIn(new_code, catalog["Square Hollow"]["sizes"])

        # 2. Card selection routes actions to intended second row
        rel_asset_1 = self._create_published_asset("sec_route_1", width=50.0, height=50.0)
        rel_asset_2 = self._create_published_asset("sec_route_2", width=70.0, height=35.0)
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Card_Zero"] = {
            "Height": "50.0",
            "Width": "50.0",
            "Thickness": "0.0",
            "Weight": "19.62",
            "asset_path": rel_asset_1,
            "object_name": "Section",
            "asset_id": "sec_route_1",
        }
        self.dialog.current_lib_data["Custom Profile"]["sizes"]["Card_One"] = {
            "Height": "35.0",
            "Width": "70.0",
            "Thickness": "0.0",
            "Weight": "19.23",
            "asset_path": rel_asset_2,
            "object_name": "Section",
            "asset_id": "sec_route_2",
        }
        self._select_family("Custom Profile")
        self.warnings_logged.clear()
        self.dialog._commit_current_family_edits()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Initial save of Custom Profile cards must produce no warnings.")

        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view, "cards_view must exist to test selection routing.")

        # Select second card (index 1: Card_One)
        self._select_card(cards_view, 1)
        self.assertEqual(
            self.dialog.table_sizes.currentRow(),
            1,
            "Selecting card 1 must route selection to table row 1.",
        )

        # Edit Section must open Card_One (row 1), NOT Card_Zero (row 0)
        self.dialog.btn_edit_section.click()
        session = self.dialog._active_edit_session
        self.assertIsNotNone(session, "Edit session must be opened.")
        self.assertEqual(
            session.size_code,
            "Card_One",
            "Edit session must target selected second card ('Card_One').",
        )
        self.assertEqual(
            session.asset_path,
            rel_asset_2,
            "Edit session must open second card's asset path.",
        )
        if getattr(session, "working_doc_name", None):
            self.owned_docs.add(session.working_doc_name)
        session.close(discard_uncommitted=True)
        self.dialog._active_edit_session = None

        # Select second card again and delete: Card_One removed, Card_Zero preserved
        self._select_card(cards_view, 1)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
            self.dialog.btn_del_size.click()

        count_fn = getattr(cards_view, "count", None)
        card_count = count_fn() if callable(count_fn) else len(getattr(cards_view, "cards", []))
        self.assertEqual(card_count, 1, "Only Card_One should be deleted; Card_Zero must remain.")

        self.warnings_logged.clear()
        self.dialog.btn_save.click()
        self.assertEqual(len(self.warnings_logged), 0, "Saving deletion must produce no warnings.")

        reloaded_catalog = reloaded_mgr.get_library("CustomFolderLib")
        sizes = reloaded_catalog["Custom Profile"]["sizes"]
        self.assertIn("Card_Zero", sizes, "Card_Zero must survive deletion.")
        self.assertNotIn("Card_One", sizes, "Card_One must be deleted from catalog.")

    def test_cards_columns_adapt_to_available_width(self):
        """Cards view adapts column count based on available viewport width."""
        cards_view = self._get_cards_view()
        self.assertIsNotNone(cards_view)
        # Check calculation method
        self.assertTrue(hasattr(cards_view, "_columns_per_row"), "Must have _columns_per_row method")
        # For a narrow width (e.g. 520px), columns should be 2
        cards_view.scroll_area.resize(520, 400)
        cards_view.scroll_area.viewport().resize(520, 400)
        self.assertEqual(cards_view._columns_per_row(), 2)

        # For a wide width (e.g. 1100px), columns should be 4
        cards_view.scroll_area.resize(1100, 400)
        cards_view.scroll_area.viewport().resize(1100, 400)
        self.assertEqual(cards_view._columns_per_row(), 4)

    def test_extract_custom_section_face_direct_without_document_lifecycle(self):
        """Direct .FCStd face extraction creates a valid Part.Face without triggering document open/close."""
        from freecad.maxproframe.custom_profile_cards import (
            _extract_custom_section_face_from_fcstd,
            render_custom_section_thumbnail,
        )

        rel_asset = self._create_published_asset("sec_direct_test", width=100.0, height=50.0, with_hole=True)
        full_path = os.path.join(self.folder_lib_path, rel_asset)

        # 1. Direct extraction creates valid face with expected dimensions
        face = _extract_custom_section_face_from_fcstd(full_path, "Section")
        self.assertIsNotNone(face)
        self.assertTrue(face.isValid())
        self.assertAlmostEqual(face.BoundBox.XLength, 100.0)
        self.assertAlmostEqual(face.BoundBox.YLength, 50.0)

        # 2. render_custom_section_thumbnail uses direct extraction and never calls App.openDocument
        with patch.object(App, "openDocument", side_effect=AssertionError("App.openDocument must not be called")):
            pixmap = render_custom_section_thumbnail(self.folder_lib_path, rel_asset, "Section", width=160, height=100)
            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())

    def test_extract_custom_section_face_without_reopening_an_open_temporary_file(self):
        """Windows cannot reopen an open NamedTemporaryFile by name; the face is still built directly."""
        from freecad.maxproframe import custom_profile_cards

        rel_asset = self._create_published_asset("sec_open_temp", width=80.0, height=40.0, with_hole=True)
        full_path = os.path.join(self.folder_lib_path, rel_asset)
        unreadable = os.path.join(self.test_root, "open-temporary.brp")

        class OpenTemporaryFile:
            # Behaves like Windows: writes succeed but the name cannot be opened again.
            name = unreadable

            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def write(self, data):
                return len(data)

            def flush(self):
                pass

        with ExitStack() as stack:
            stack.enter_context(patch.object(custom_profile_cards.tempfile, "NamedTemporaryFile", OpenTemporaryFile))
            stack.enter_context(
                patch.object(App, "openDocument", side_effect=AssertionError("App.openDocument must not be called"))
            )
            face = custom_profile_cards._extract_custom_section_face_from_fcstd(full_path, "Section")
            self.assertIsNotNone(face)
            self.assertTrue(face.isValid())
            self.assertAlmostEqual(face.BoundBox.XLength, 80.0)
            self.assertAlmostEqual(face.BoundBox.YLength, 40.0)
            pixmap = custom_profile_cards.render_custom_section_thumbnail(
                self.folder_lib_path, rel_asset, "Section", width=160, height=100
            )
            self.assertFalse(pixmap.isNull())
        self.assertFalse(os.path.exists(unreadable))


if __name__ == "__main__":
    unittest.main()

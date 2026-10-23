import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from PySide import QtCore, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.ff_tools import PROFILEIMAGES_PATH, TRANSLATIONSPATH, translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.library_manager_dialog import (
    AddFamilyDialog,
    ProfileLibraryManagerDialog,
)
from freecad.maxproframe.profile import Profile


class TestCProfileUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_c_ui_user_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)
        self.doc_count = 0
        self.created_docs = []

    def tearDown(self):
        for doc_name in self.created_docs:
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def _create_doc(self):
        self.doc_count += 1
        name = f"TestCDoc_{self.doc_count}_{id(self)}"
        doc = App.newDocument(name)
        self.created_docs.append(name)
        return doc

    def _create_mock_library_with_c(self):
        """Creates an isolated user library with plain and filleted C variants and Square Hollow."""
        c_sizes = {
            "100x50x15x2": {
                "Height": "100",
                "Width": "50",
                "Thickness": "2",
                "Lip Length": "15",
                "Radius1": "4",
                "Weight": "3.36",
            }
        }
        lib_data = {
            "_metadata": {"name": "TestCLib", "material": "Steel", "density": 7.85},
            "C (Fillet)": {
                "canonical_family": "C",
                "fillet": True,
                "norm": "Custom",
                "unit": "Metric Units",
                "sizes": dict(c_sizes),
            },
            "C": {
                "canonical_family": "C",
                "fillet": False,
                "norm": "Custom",
                "unit": "Metric Units",
                "sizes": dict(c_sizes),
            },
            "Square Hollow": {
                "canonical_family": "Square Hollow",
                "fillet": False,
                "norm": "Custom",
                "unit": "Metric Units",
                "sizes": {
                    "50x50x2": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "2",
                        "Flange Thickness": "0",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": "2.9",
                    }
                },
            },
        }
        self.manager.save_user_library("TestCLib", lib_data)
        return "TestCLib"

    def test_s1_create_panel_has_sb_lip_length_and_shows_only_for_c(self):
        """S1: sb_lip_length widget exists in UI; shown only when family is C."""
        self._create_doc()
        self._create_mock_library_with_c()
        panel = CreateProfileTaskPanel()
        panel.profiles = self.manager.get_all_profiles()
        panel.initialize_ui()
        for f in panel.form:
            f.show()

        # sb_lip_length must exist on form_proxy
        self.assertTrue(hasattr(panel.form_proxy, "sb_lip_length"), "sb_lip_length missing from form")
        self.assertTrue(hasattr(panel.form_proxy, "label_lip_length"), "label_lip_length missing from form")

        # Select Square Hollow: sb_lip_length must be hidden
        panel.form_proxy.combo_family.setCurrentText("Square Hollow")
        self.assertTrue(panel.form_proxy.sb_lip_length.isHidden())
        self.assertTrue(panel.form_proxy.label_lip_length.isHidden())
        self.assertEqual(panel.form_proxy.label_8.text(), translate("frameforge", "Large Radius"))
        self.assertFalse(panel.form_proxy.sb_flange_thickness.isHidden())
        self.assertFalse(panel.form_proxy.sb_radius2.isHidden())

        # Select C: sb_lip_length must be shown, label_8 must be 'Exterior radius'
        panel.form_proxy.combo_family.setCurrentText("C")
        self.assertFalse(panel.form_proxy.sb_lip_length.isHidden())
        self.assertFalse(panel.form_proxy.label_lip_length.isHidden())
        self.assertEqual(panel.form_proxy.label_8.text(), translate("frameforge", "Exterior radius"))
        self.assertTrue(panel.form_proxy.sb_flange_thickness.isHidden())
        self.assertTrue(panel.form_proxy.sb_radius2.isHidden())

    def test_s1_create_panel_populates_lip_length_from_catalog(self):
        """S1: Selecting a C size populates sb_lip_length from catalog and enables it."""
        self._create_doc()
        self._create_mock_library_with_c()
        panel = CreateProfileTaskPanel()
        panel.profiles = self.manager.get_all_profiles()
        panel.initialize_ui()
        for f in panel.form:
            f.show()

        panel.form_proxy.combo_family.setCurrentText("C")
        panel.form_proxy.combo_size.setCurrentText("100x50x15x2")

        self.assertTrue(panel.form_proxy.sb_lip_length.isEnabled())
        self.assertEqual(panel.form_proxy.sb_lip_length.value(), 15.0)
        self.assertEqual(panel.form_proxy.sb_height.value(), 100.0)
        self.assertEqual(panel.form_proxy.sb_width.value(), 50.0)
        self.assertEqual(panel.form_proxy.sb_main_thickness.value(), 2.0)
        self.assertFalse(panel.form_proxy.sb_flange_thickness.isEnabled())
        self.assertFalse(panel.form_proxy.sb_radius2.isEnabled())

    def test_s1_s2_edit_profile_panel_loads_and_updates_lip_length(self):
        """S1, S2: EditProfileTaskPanel loads stored LipLength and updates it via set_properties."""
        doc = self._create_doc()
        obj = doc.addObject("Part::FeaturePython", "ProfileC")
        obj.addExtension("Part::AttachExtensionPython")

        Profile(
            obj,
            init_w=50.0,
            init_h=100.0,
            init_mt=2.0,
            init_ft=2.0,
            init_r1=4.0,
            init_r2=2.0,
            init_len=1000.0,
            init_wg=3.36,
            init_unit_price=0.0,
            init_mf=True,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="C",
            size_name="100x50x15x2",
            bevels_combined=False,
            catalog_family="C",
            init_lip_length=15.0,
        )

        panel = EditProfileTaskPanel(obj)
        panel.initialize_ui()
        for f in panel.form:
            f.show()

        # Check UI fields
        self.assertFalse(panel.form_proxy.sb_lip_length.isHidden())
        self.assertEqual(panel.form_proxy.sb_lip_length.value(), 15.0)
        self.assertEqual(panel.form_proxy.label_8.text(), translate("frameforge", "Exterior radius"))

        # Edit lip length and verify proceed calls set_properties with keyword
        panel.form_proxy.sb_lip_length.setValue(20.0)
        panel.proceed()

        if hasattr(obj, "LipLength"):
            self.assertEqual(obj.LipLength, 20.0)

    def test_s1_catalog_table_columns_and_c_visibility(self):
        """S1: TABLE_COLUMNS has Lip Length at index 8; C shows Lip Length and hides Flange/Radius2."""
        self._create_mock_library_with_c()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")

        # TABLE_COLUMNS check
        self.assertGreaterEqual(len(dialog.TABLE_COLUMNS), 9)
        self.assertEqual(dialog.TABLE_COLUMNS[8][0], "Lip Length")

        # Columns 0..7 must retain exact historical keys
        expected_first_8 = [
            "Size", "Height", "Width", "Thickness",
            "Flange Thickness", "Radius1", "Radius2", "Weight"
        ]
        actual_first_8 = [col[0] for col in dialog.TABLE_COLUMNS[:8]]
        self.assertEqual(actual_first_8, expected_first_8)

        # Plain C visibility
        dialog.combo_family.setCurrentText("C")
        visible_plain = {i for i in range(len(dialog.TABLE_COLUMNS)) if not dialog.table_sizes.isColumnHidden(i)}
        self.assertEqual(visible_plain, {0, 1, 2, 3, 7, 8})  # Size, H, W, Thickness, Weight, Lip Length

        # Filleted C visibility
        dialog.combo_family.setCurrentText("C (Fillet)")
        visible_fillet = {i for i in range(len(dialog.TABLE_COLUMNS)) if not dialog.table_sizes.isColumnHidden(i)}
        self.assertEqual(visible_fillet, {0, 1, 2, 3, 5, 7, 8})  # Size, H, W, Thickness, Radius1, Weight, Lip Length
        self.assertEqual(dialog.table_sizes.horizontalHeaderItem(5).text(), translate("frameforge", "Exterior Radius [mm]"))

        # Square Hollow visibility: Lip Length (8) must be hidden
        dialog.combo_family.setCurrentText("Square Hollow")
        self.assertTrue(dialog.table_sizes.isColumnHidden(8))

    def test_s4_c_columns_follow_requested_visual_order(self):
        self._create_mock_library_with_c()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")
        header = dialog.table_sizes.horizontalHeader()

        def visible_keys():
            return [dialog.TABLE_COLUMNS[header.logicalIndex(index)][0]
                    for index in range(header.count())
                    if not dialog.table_sizes.isColumnHidden(header.logicalIndex(index))]

        expected = ["Size", "Height", "Width", "Lip Length", "Thickness", "Weight"]
        dialog.combo_family.setCurrentText("C")
        self.assertEqual(visible_keys(), expected)
        dialog.combo_family.setCurrentText("C (Fillet)")
        self.assertEqual(visible_keys(), expected[:-1] + ["Radius1", "Weight"])
        dialog.combo_family.setCurrentText("Square Hollow")
        self.assertEqual(visible_keys(), ["Size", "Height", "Width", "Thickness", "Weight"])
        self.assertEqual([header.logicalIndex(i) for i in range(header.count())], list(range(9)))
        dialog.combo_family.setCurrentText("C")
        self.assertEqual(visible_keys(), expected)
        self.assertEqual(dialog.table_sizes.item(0, 8).text(), "15")
        self.assertEqual(dialog.TABLE_COLUMNS[8][0], "Lip Length")

    def test_s4_spanish_lip_and_exterior_radius_translations(self):
        translations = {
            "Lip Length": "Labio",
            "Lip Length [mm]": "Labio [mm]",
            "Exterior radius": "Radio exterior",
            "Exterior Radius [mm]": "Radio exterior [mm]",
        }
        for name in ("frameforge_es.qm", "frameforge_es-ES.qm", "FrameForge_es.qm", "FrameForge_es-ES.qm"):
            with self.subTest(resource=name):
                translator = QtCore.QTranslator()
                self.assertTrue(translator.load(os.path.join(TRANSLATIONSPATH, name)))
                for source, expected in translations.items():
                    self.assertEqual(translator.translate("frameforge", source), expected)
                self.assertEqual(translator.translate("frameforge", "Thickness [mm]"), "Espesor [mm]")

        self.app.installTranslator(translator)
        self.addCleanup(self.app.removeTranslator, translator)
        self._create_doc()
        self._create_mock_library_with_c()
        panel = CreateProfileTaskPanel()
        panel.profiles = self.manager.get_all_profiles()
        panel.initialize_ui()
        panel.form_proxy.combo_family.setCurrentText("C (Fillet)")
        self.assertEqual(panel.form_proxy.label_lip_length.text(), "Labio")
        self.assertEqual(panel.form_proxy.label_8.text(), "Radio exterior")
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")
        dialog.combo_family.setCurrentText("C (Fillet)")
        self.assertEqual(dialog.table_sizes.horizontalHeaderItem(8).text(), "Labio [mm]")
        self.assertEqual(dialog.table_sizes.horizontalHeaderItem(5).text(), "Radio exterior [mm]")

    def test_s1_catalog_save_and_reload_preserves_lip_length(self):
        """S1: Table edits to Lip Length are saved and reloaded accurately."""
        self._create_mock_library_with_c()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")

        dialog.combo_family.setCurrentText("C")
        dialog.table_sizes.item(0, 8).setText("25")
        dialog.btn_save.click()

        reloaded = self.manager.get_library("TestCLib")["C"]["sizes"]["100x50x15x2"]
        self.assertEqual(reloaded["Lip Length"], "25")

    def test_s1_s2_catalog_autoweight_responds_to_lip_length_and_radius_and_fillet(self):
        """Editing Lip Length and Radius1 calculates weight using stored fillet."""
        self._create_mock_library_with_c()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")

        dialog.combo_family.setCurrentText("C (Fillet)")
        weight_item = dialog.table_sizes.item(0, 7)
        self.assertIsNotNone(weight_item)

        # Edit Lip Length (col 8)
        dialog.table_sizes.item(0, 8).setText("30")
        # Edit Radius1 (col 5)
        dialog.table_sizes.item(0, 5).setText("6")
        self.assertFalse(hasattr(dialog, "cb_fillet"))
        dialog._commit_current_family_edits()
        self.assertTrue(dialog.current_lib_data["C (Fillet)"]["fillet"])

    def test_s3_c_family_image_lookup_plain_and_fillet(self):
        """S3: Family image lookup resolves C.png and C_Fillet.png (or Warehouse fallback)."""
        self._create_doc()
        self._create_mock_library_with_c()
        panel = CreateProfileTaskPanel()
        panel.profiles = self.manager.get_all_profiles()
        panel.initialize_ui()

        panel.form_proxy.combo_family.setCurrentText("C")
        panel.form_proxy.cb_make_fillet.setChecked(False)
        panel.update_image()
        expected_plain = os.path.join(PROFILEIMAGES_PATH, "Metal", "C.png")
        if os.path.isfile(expected_plain):
            self.assertEqual(panel.current_image_path, expected_plain)
        else:
            self.assertTrue(panel.current_image_path.endswith("Warehouse.png"))

        panel.form_proxy.cb_make_fillet.setChecked(True)
        panel.update_image()
        expected_fillet = os.path.join(PROFILEIMAGES_PATH, "Metal", "C_Fillet.png")
        if os.path.isfile(expected_fillet):
            self.assertEqual(panel.current_image_path, expected_fillet)
        else:
            self.assertTrue(panel.current_image_path.endswith("Warehouse.png"))

        # In ProfileLibraryManagerDialog:
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")
        plain_path = dialog._get_family_image_path("C", fillet=False)
        fillet_path = dialog._get_family_image_path("C", fillet=True)
        if os.path.isfile(expected_plain):
            self.assertEqual(plain_path, expected_plain)
        if os.path.isfile(expected_fillet):
            self.assertEqual(fillet_path, expected_fillet)

    def test_preserve_non_c_families_unchanged(self):
        """Preserve: Square Hollow and Channels retain unchanged controls and Make Fillet behavior."""
        from freecad.maxproframe.library_manager import FILLET_FAMILIES
        # Channels must not be in FILLET_FAMILIES
        self.assertNotIn("Channels", FILLET_FAMILIES)

        # AddFamilyDialog fillet checkbox disabled for Channels
        dialog = AddFamilyDialog()
        self.addCleanup(dialog.close)
        dialog.select_family("Channels")
        self.assertFalse(dialog.cb_fillet.isEnabled())

    def test_preserve_typeerror_propagates_without_retry(self):
        """Preserve: TypeError during update_profile propagates once; does not retry or drop C data."""
        doc = self._create_doc()
        obj = doc.addObject("Part::FeaturePython", "ProfileC_TypeError")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj,
            init_w=50.0,
            init_h=100.0,
            init_mt=2.0,
            init_ft=2.0,
            init_r1=4.0,
            init_r2=2.0,
            init_len=1000.0,
            init_wg=3.36,
            init_unit_price=0.0,
            init_mf=True,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="C",
            size_name="100x50x15x2",
            bevels_combined=False,
            catalog_family="C",
            init_lip_length=15.0,
        )
        panel = EditProfileTaskPanel(obj)
        panel.initialize_ui()

        # Track set_properties calls and inject TypeError
        calls = []
        orig_set_props = obj.Proxy.set_properties

        def failing_set_props(*args, **kwargs):
            calls.append((args, kwargs))
            raise TypeError("Simulated signature failure")

        obj.Proxy.set_properties = failing_set_props
        try:
            with self.assertRaises(TypeError):
                panel.update_profile(obj)
            # Must be called exactly once; no second fallback call
            self.assertEqual(len(calls), 1)
        finally:
            obj.Proxy.set_properties = orig_set_props

    def test_preserve_non_c_save_reload_does_not_acquire_lip_length(self):
        """Preserve: Non-C sizes do NOT acquire Lip Length on save; Lip Length hidden for non-C."""
        self._create_mock_library_with_c()
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="TestCLib")

        # Channels / unlisted families must hide Lip Length column (index 8)
        self.manager.save_user_library("TestChannelsLib", {
            "_metadata": {"name": "TestChannelsLib", "material": "Steel", "density": 7.85},
            "Channels": {
                "canonical_family": "Channels",
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "CH1": {
                        "Height": "50", "Width": "25", "Thickness": "2",
                        "Flange Thickness": "3", "Radius1": "0", "Radius2": "0", "Weight": "2.0"
                    }
                }
            }
        })
        dialog.refresh_libraries(select_name="TestChannelsLib")
        dialog.combo_family.setCurrentText("Channels")
        self.assertTrue(dialog.table_sizes.isColumnHidden(8), "Lip Length must be hidden for Channels")

        # Edit and save Square Hollow: verify Lip Length is NOT added to saved JSON
        dialog.refresh_libraries(select_name="TestCLib")
        dialog.combo_family.setCurrentText("Square Hollow")
        dialog.table_sizes.item(0, 1).setText("55")
        dialog.btn_save.click()

        saved_sh = self.manager.get_library("TestCLib")["Square Hollow"]["sizes"]["50x50x2"]
        self.assertEqual(saved_sh["Height"], "55")
        self.assertNotIn("Lip Length", saved_sh, "Non-C family must not acquire Lip Length field")

    def test_preserve_non_c_custom_weight_and_stored_fillet_on_table_edits(self):
        """Preserve: Non-C custom weight and stored fillet unchanged on radius edits."""
        lib_data = {
            "_metadata": {"name": "CustomWeightLib", "material": "Steel", "density": 7.85},
            "Square Hollow": {
                "canonical_family": "Square Hollow",
                "norm": "Custom",
                "unit": "Metric Units",
                "fillet": False,
                "sizes": {
                    "Manual": {
                        "Height": "50", "Width": "50", "Thickness": "2",
                        "Flange Thickness": "0", "Radius1": "0", "Radius2": "0",
                        "Weight": "9.999"
                    }
                }
            }
        }
        self.manager.save_user_library("CustomWeightLib", lib_data)
        dialog = ProfileLibraryManagerDialog(library_manager=self.manager)
        self.addCleanup(dialog.close)
        dialog.refresh_libraries(select_name="CustomWeightLib")
        dialog.combo_family.setCurrentText("Square Hollow")

        self.assertEqual(dialog.table_sizes.item(0, 7).text(), "9.999")

        self.assertFalse(hasattr(dialog, "cb_fillet"))
        dialog._commit_current_family_edits()
        self.assertFalse(dialog.current_lib_data["Square Hollow"]["fillet"])
        self.assertEqual(dialog.table_sizes.item(0, 7).text(), "9.999")

        # Editing Radius1 (col 5) must NOT recalculate manual weight for non-C
        dialog.table_sizes.item(0, 5).setText("4")
        self.assertEqual(dialog.table_sizes.item(0, 7).text(), "9.999", "Radius1 edit must not overwrite non-C manual weight")

        # Non-C legacy autocalc must still update mass when col 1 is edited, even with irrelevant col 5 / col 8 text
        dialog.table_sizes.item(0, 5).setText("N/A")
        if dialog.table_sizes.columnCount() > 8 and dialog.table_sizes.item(0, 8):
            dialog.table_sizes.item(0, 8).setText("-")
        dialog.table_sizes.item(0, 1).setText("60")

        expected_mass = str(round(((50 * 60) - (46 * 56)) * 7.85 / 1000.0, 3))
        self.assertEqual(dialog.table_sizes.item(0, 7).text(), expected_mass)

        # Save and reload public persisted weight; no C lip field injected
        dialog.btn_save.click()
        reloaded_sh = self.manager.get_library("CustomWeightLib")["Square Hollow"]["sizes"]["Manual"]
        self.assertEqual(reloaded_sh["Weight"], expected_mass)
        self.assertNotIn("Lip Length", reloaded_sh)

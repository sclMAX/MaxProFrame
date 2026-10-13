import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import Part

from freecad.frameforge.library_manager import (
    FILLET_FAMILIES,
    get_canonical_family,
    calculate_linear_weight,
    LibraryManager,
)
from freecad.frameforge.ff_tools import PROFILEIMAGES_PATH
from PySide import QtGui, QtWidgets
from freecad.frameforge.profile import Profile
from freecad.frameforge.create_bom import traverse_assembly, group_profiles
from freecad.frameforge.trimmed_profile import TrimmedProfile
from freecad.frameforge.extruded_cutout import ExtrudedCutout
from freecad.frameforge.edit_profile_tool import EditProfileTaskPanel


class TestCatalogFamilyProfiles(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ff_test_catalog_")
        self.orig_user_dir = os.environ.get("FRAMEFORGE_USER_PROFILES_DIR")
        os.environ["FRAMEFORGE_USER_PROFILES_DIR"] = self.temp_dir
        self.doc_count = 0
        self.created_docs = []

        # Create isolated user library with variants
        self.lib_manager = LibraryManager(user_dir=self.temp_dir)
        test_lib_data = {
            "_metadata": {"name": "TestSteel", "material": "TestSteel", "density": 7.85},
            "Square Hollow (Fillet)": {
                "canonical_family": "Square Hollow",
                "fillet": True,
                "norm": "ISO",
                "unit": "mm",
                "sizes": {
                    "50x50x3": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "3",
                        "Radius1": "4",
                        "Radius2": "2",
                        "Weight": "4.4",
                    }
                },
            },
            "Square Hollow": {
                "canonical_family": "Square Hollow",
                "fillet": False,
                "norm": "ISO",
                "unit": "mm",
                "sizes": {
                    "50x50x3": {
                        "Height": "50",
                        "Width": "50",
                        "Thickness": "3",
                        "Radius1": "0",
                        "Radius2": "0",
                        "Weight": "4.4",
                    }
                },
            },
        }
        self.lib_manager.save_user_library("TestSteel", test_lib_data)

    def tearDown(self):
        for doc_name in self.created_docs:
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        if self.orig_user_dir is not None:
            os.environ["FRAMEFORGE_USER_PROFILES_DIR"] = self.orig_user_dir
        else:
            os.environ.pop("FRAMEFORGE_USER_PROFILES_DIR", None)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_doc(self, name_prefix="Doc"):
        self.doc_count += 1
        name = f"{name_prefix}_{self.doc_count}_{os.getpid()}"
        doc = App.newDocument(name)
        App.setActiveDocument(name)
        self.created_docs.append(name)
        return doc

    def _create_profile_obj(
        self,
        doc,
        name="TestProfile",
        fam="Square Hollow",
        catalog_family=None,
        material="TestSteel",
        width=50.0,
        height=50.0,
        thickness=3.0,
        r1=4.0,
        r2=2.0,
        length=500.0,
        make_fillet=True,
        line_target=None,
    ):
        obj = doc.addObject("Part::FeaturePython", name)
        obj.addExtension("Part::AttachExtensionPython")

        link_sub = None
        if line_target is not None:
            link_sub = (line_target, ("Edge1",))
            obj.MapMode = "NormalToEdge"
            try:
                obj.AttachmentSupport = link_sub
            except AttributeError:
                obj.Support = link_sub

        kwargs = {}
        if catalog_family is not None:
            kwargs["catalog_family"] = catalog_family

        profile_proxy = Profile(
            obj,
            width,
            height,
            thickness,
            thickness,
            r1,
            r2,
            length,
            4.0,
            10.0,
            make_fillet,
            1,
            1,
            material,
            fam,
            f"{int(width)}x{int(height)}x{int(thickness)}",
            False,
            link_sub=link_sub,
            **kwargs,
        )
        profile_proxy.execute(obj)
        return obj

    def test_fillet_families_constant_and_canonical_resolution(self):
        """S1, S2: Shared API contract for FILLET_FAMILIES and get_canonical_family."""
        expected_families = frozenset(
            {
                "Square Hollow",
                "Rectangular Hollow",
                "Equal Leg Angles",
                "Unequal Leg Angles",
                "HEA",
                "HEB",
                "HEM",
                "IPE",
                "IPN",
                "UPE",
                "UPN",
            }
        )
        self.assertEqual(FILLET_FAMILIES, expected_families)

        # Explicit canonical_family metadata returns canonical key
        metadata_with_canonical = {
            "canonical_family": "Square Hollow",
            "fillet": True,
            "sizes": {},
        }
        self.assertEqual(
            get_canonical_family("Square Hollow (Fillet)", metadata_with_canonical),
            "Square Hollow",
        )

        # Missing canonical_family returns key unchanged
        metadata_legacy = {
            "fillet": False,
            "sizes": {},
        }
        self.assertEqual(
            get_canonical_family("Square Hollow", metadata_legacy),
            "Square Hollow",
        )

        # No metadata returns key unchanged; does not guess suffixes
        self.assertEqual(
            get_canonical_family("Square Hollow (Fillet)", None),
            "Square Hollow (Fillet)",
        )
        self.assertEqual(
            get_canonical_family("Square Hollow (No Fillet)", None),
            "Square Hollow (No Fillet)",
        )
        self.assertEqual(
            get_canonical_family("Custom_Unknown_Family", None),
            "Custom_Unknown_Family",
        )

        # Legacy calculate_linear_weight is preserved and accepts canonical family
        weight = calculate_linear_weight("Square Hollow", 50.0, 50.0, 3.0, 7.85)
        self.assertAlmostEqual(weight, 4.427, places=2)

    def test_profile_creation_with_catalog_family_and_positive_radii(self):
        """S1, S2, S5: Profile object stores CatalogFamily, dispatches canonical Family and builds positive radii."""
        doc = self._create_doc("TestProfileCreation")

        # Filleted variant: positive radii, MakeFillet=True
        filleted = self._create_profile_obj(
            doc,
            name="FilletedProfile",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            width=60.0,
            height=60.0,
            thickness=4.0,
            r1=5.0,
            r2=2.5,
            length=600.0,
            make_fillet=True,
        )

        self.assertEqual(filleted.Family, "Square Hollow")
        self.assertEqual(filleted.CatalogFamily, "Square Hollow (Fillet)")
        self.assertTrue(filleted.Shape.isValid())
        self.assertGreater(filleted.Shape.Volume, 0)
        self.assertGreater(len(filleted.Shape.Edges), 0)

        # Plain sibling variant: MakeFillet=False
        plain = self._create_profile_obj(
            doc,
            name="PlainProfile",
            fam="Square Hollow",
            catalog_family="Square Hollow",
            width=60.0,
            height=60.0,
            thickness=4.0,
            r1=0.0,
            r2=0.0,
            length=600.0,
            make_fillet=False,
        )

        self.assertEqual(plain.Family, "Square Hollow")
        self.assertEqual(plain.CatalogFamily, "Square Hollow")
        self.assertTrue(plain.Shape.isValid())
        self.assertGreater(plain.Shape.Volume, 0)

        # Distinct variant identities coexist in the same document
        self.assertNotEqual(filleted.CatalogFamily, plain.CatalogFamily)
        self.assertEqual(filleted.Family, plain.Family)

    def test_profile_constructor_backward_compatibility(self):
        """S5: Existing Profile constructor without catalog_family keyword remains compatible."""
        doc = self._create_doc("TestCompatibility")

        obj = doc.addObject("Part::FeaturePython", "CompatProfile")
        obj.addExtension("Part::AttachExtensionPython")

        # Call with original 17 positional arguments + keyword defaults
        p = Profile(
            obj,
            40.0,
            40.0,
            2.0,
            2.0,
            0.0,
            0.0,
            300.0,
            2.5,
            5.0,
            False,
            1,
            1,
            "Steel",
            "Square Hollow",
            "40x40x2",
            False,
        )
        p.execute(obj)

        self.assertEqual(obj.Family, "Square Hollow")
        self.assertTrue(hasattr(obj, "CatalogFamily"))
        self.assertEqual(obj.CatalogFamily, "Square Hollow")

    def test_profile_persistence_save_reload(self):
        """S1, S5: Profile retains CatalogFamily across document save and reload."""
        doc = self._create_doc("TestPersistence")
        doc_name = doc.Name

        obj = self._create_profile_obj(
            doc,
            name="PersistentProfile",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=400.0,
            make_fillet=True,
        )

        file_path = os.path.join(self.temp_dir, "test_persistence.FCStd")
        doc.saveAs(file_path)
        App.closeDocument(doc_name)
        self.created_docs.remove(doc_name)

        reloaded_doc = App.openDocument(file_path)
        self.created_docs.append(reloaded_doc.Name)
        reloaded_obj = reloaded_doc.getObject("PersistentProfile")

        self.assertIsNotNone(reloaded_obj)
        self.assertEqual(reloaded_obj.Family, "Square Hollow")
        self.assertTrue(hasattr(reloaded_obj, "CatalogFamily"))
        self.assertEqual(reloaded_obj.CatalogFamily, "Square Hollow (Fillet)")
        self.assertTrue(reloaded_obj.Shape.isValid())
        self.assertGreater(reloaded_obj.Shape.Volume, 0)

    def test_edit_profile_tool_catalog_family_resolution_and_fallback(self):
        """S5: Edit tool prioritizes CatalogFamily, reloads options and falls back gracefully."""
        doc = self._create_doc("TestEditTool")

        obj = self._create_profile_obj(
            doc,
            name="ProfileToEdit",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=400.0,
            make_fillet=True,
        )

        panel = EditProfileTaskPanel(obj)
        panel.initialize_ui()
        # Verify panel selected the CatalogFamily
        selected_family = panel.form_proxy.combo_family.currentText()
        self.assertEqual(selected_family, "Square Hollow (Fillet)")

        # Verify spin boxes were populated with profile values
        self.assertEqual(panel.form_proxy.sb_width.value(), 50.0)
        self.assertEqual(panel.form_proxy.sb_height.value(), 50.0)
        self.assertEqual(panel.form_proxy.sb_radius1.value(), 4.0)

        # Test fallback when profile lacks CatalogFamily property
        legacy_obj = doc.addObject("Part::FeaturePython", "LegacyObj")
        legacy_obj.addExtension("Part::AttachExtensionPython")
        Profile(
            legacy_obj,
            40.0,
            40.0,
            2.0,
            2.0,
            0.0,
            0.0,
            300.0,
            2.0,
            5.0,
            False,
            1,
            1,
            "Steel",
            "Square Hollow",
            "40x40x2",
            False,
        )
        if hasattr(legacy_obj, "CatalogFamily"):
            legacy_obj.removeProperty("CatalogFamily")

        legacy_panel = EditProfileTaskPanel(legacy_obj)
        legacy_panel.initialize_ui()
        self.assertEqual(legacy_panel.form_proxy.combo_family.currentText(), "Square Hollow")

        # Test missing catalog resilience
        obj_missing_cat = self._create_profile_obj(
            doc,
            name="MissingCatProfile",
            fam="Square Hollow",
            catalog_family="CustomCatalogFamily",
            material="NonExistentMaterial",
            width=30.0,
            height=30.0,
            thickness=2.0,
            r1=0.0,
            r2=0.0,
            length=200.0,
            make_fillet=False,
        )
        missing_panel = EditProfileTaskPanel(obj_missing_cat)
        missing_panel.initialize_ui()
        self.assertEqual(missing_panel.form_proxy.combo_family.currentText(), "CustomCatalogFamily")
        self.assertEqual(missing_panel.form_proxy.sb_width.value(), 30.0)

    def test_bom_groups_distinct_variants_independently(self):
        """S1, S2, S5: BOM groups distinct variants independently by CatalogFamily."""
        doc = self._create_doc("TestBOMVariants")

        p_fillet = self._create_profile_obj(
            doc,
            name="ProfFillet",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=500.0,
            make_fillet=True,
        )
        p_plain = self._create_profile_obj(
            doc,
            name="ProfPlain",
            fam="Square Hollow",
            catalog_family="Square Hollow",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=0.0,
            r2=0.0,
            length=500.0,
            make_fillet=False,
        )

        profiles_data = []
        links_data = []
        traverse_assembly(profiles_data, links_data, p_fillet)
        traverse_assembly(profiles_data, links_data, p_plain)

        grouped = group_profiles(profiles_data)
        # Should result in 2 distinct rows in BOM because families differ
        self.assertEqual(len(grouped), 2)
        families_in_bom = {row["family"] for row in grouped}
        self.assertEqual(families_in_bom, {"Square Hollow (Fillet)", "Square Hollow"})

    def test_bom_legacy_profile_fallback_and_custom_profile_branch(self):
        """S5: BOM falls back to Family for older objects and leaves custom profile route unchanged."""
        doc = self._create_doc("TestBOMFallbacks")

        # 1. Legacy profile without CatalogFamily
        legacy = self._create_profile_obj(
            doc,
            name="LegacyProf",
            fam="Square Hollow",
            catalog_family=None,
            width=40.0,
            height=40.0,
            thickness=2.0,
            r1=0.0,
            r2=0.0,
            length=300.0,
            make_fillet=False,
        )
        legacy.removeProperty("CatalogFamily")

        profiles_data = []
        links_data = []
        traverse_assembly(profiles_data, links_data, legacy)
        self.assertEqual(len(profiles_data), 1)
        self.assertEqual(profiles_data[0]["family"], "Square Hollow")

        # 2. Custom profile route
        custom_target = doc.addObject("Part::Box", "MySpecialProfile")
        custom_link = doc.addObject("App::Link", "CustomLink")
        custom_link.LinkedObject = custom_target
        doc.recompute()
        custom_prof_obj = doc.addObject("Part::FeaturePython", "CustomProfileObject")
        custom_prof_obj.addExtension("Part::AttachExtensionPython")
        Profile(
            custom_prof_obj,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            500.0,
            5.0,
            15.0,
            False,
            1,
            1,
            "Steel",
            "Custom Profile",
            "None",
            False,
            custom_profile=custom_link,
        )

        profiles_data2 = []
        links_data2 = []
        traverse_assembly(profiles_data2, links_data2, custom_prof_obj)
        self.assertEqual(len(profiles_data2), 1)
        self.assertEqual(profiles_data2[0]["family"], "MySpecialProfile")

    def test_derived_identity_trimmed_and_cutout_profiles(self):
        """S5: CatalogFamily propagates to trimmed and cutout derivatives so downstream BOM stays distinct."""
        doc = self._create_doc("TestDerivedIdentity")

        # Target line for profile attachment
        line = doc.addObject("Part::Line", "Guideline")
        line.X2 = 0.0
        line.Y2 = 0.0
        line.Z2 = 600.0
        doc.recompute()

        base_prof = self._create_profile_obj(
            doc,
            name="BaseFilleted",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=600.0,
            make_fillet=True,
            line_target=line,
        )

        # Trimmed derivative
        t_obj = doc.addObject("Part::FeaturePython", "TrimmedDerivative")
        TrimmedProfile(t_obj)
        t_obj.TrimmedBody = base_prof
        t_obj.Shape = base_prof.Shape
        t_obj.Proxy._update_structure_data(t_obj)

        self.assertTrue(hasattr(t_obj, "CatalogFamily"))
        self.assertEqual(t_obj.CatalogFamily, "Square Hollow (Fillet)")
        self.assertEqual(t_obj.Family, "Square Hollow")

        # Cutout derivative
        c_obj = doc.addObject("Part::FeaturePython", "CutoutDerivative")
        ExtrudedCutout(c_obj, line, (base_prof, ["Face1"]))
        c_obj.Shape = base_prof.Shape
        c_obj.Proxy._update_structure_data(c_obj)

        self.assertTrue(hasattr(c_obj, "CatalogFamily"))
        self.assertEqual(c_obj.CatalogFamily, "Square Hollow (Fillet)")
        self.assertEqual(c_obj.Family, "Square Hollow")

        # Sibling plain profile trimmed derivative to verify independent runtime grouping
        base_plain = self._create_profile_obj(
            doc,
            name="BasePlain",
            fam="Square Hollow",
            catalog_family="Square Hollow",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=0.0,
            r2=0.0,
            length=600.0,
            make_fillet=False,
            line_target=line,
        )
        t_plain = doc.addObject("Part::FeaturePython", "TrimmedPlain")
        TrimmedProfile(t_plain)
        t_plain.TrimmedBody = base_plain
        t_plain.Shape = base_plain.Shape
        t_plain.Proxy._update_structure_data(t_plain)
        self.assertEqual(t_plain.CatalogFamily, "Square Hollow")

        # Verify derived runtime identities and positive shapes
        self.assertTrue(t_obj.Shape.isValid())
        self.assertTrue(c_obj.Shape.isValid())
        self.assertTrue(t_plain.Shape.isValid())
        self.assertEqual(t_obj.CatalogFamily, "Square Hollow (Fillet)")
        self.assertEqual(c_obj.CatalogFamily, "Square Hollow (Fillet)")
        self.assertEqual(t_plain.CatalogFamily, "Square Hollow")

        # Downstream BOM
        bom_data = []
        links_data = []
        traverse_assembly(bom_data, links_data, t_obj)
        traverse_assembly(bom_data, links_data, c_obj)
        traverse_assembly(bom_data, links_data, t_plain)

        self.assertEqual(len(bom_data), 3)
        self.assertEqual(bom_data[0]["family"], "Square Hollow (Fillet)")
        self.assertEqual(bom_data[1]["family"], "Square Hollow (Fillet)")
        self.assertEqual(bom_data[2]["family"], "Square Hollow")

        families_in_bom = {item["family"] for item in bom_data}
        self.assertEqual(families_in_bom, {"Square Hollow (Fillet)", "Square Hollow"})

    def test_b2_update_image_resolves_canonical_preview_and_missing_catalog_fallback(self):
        """S1, S2, S5 (B2): update_image resolves canonical image for variants and missing catalogs."""
        doc = self._create_doc("TestB2UpdateImage")

        # Case A: Variant in library with metadata
        prof_in_lib = self._create_profile_obj(
            doc,
            name="ProfInLib",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            material="TestSteel",
            make_fillet=True,
        )
        panel_a = EditProfileTaskPanel(prof_in_lib)
        panel_a.initialize_ui()
        panel_a.update_image()

        expected_pixmap = QtGui.QPixmap(os.path.join(PROFILEIMAGES_PATH, "Metal", "Square_Hollow_Fillet.png"))
        self.assertFalse(expected_pixmap.isNull())
        actual_pixmap_a = panel_a.form_proxy.label_image.pixmap()
        self.assertIsNotNone(actual_pixmap_a)
        self.assertEqual(actual_pixmap_a.toImage(), expected_pixmap.toImage())

        # Case B: Missing catalog on edit panel - use saved profile's canonical Family when same CatalogFamily
        prof_missing_cat = self._create_profile_obj(
            doc,
            name="ProfMissingCat",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            material="NonExistentLibraryMaterial",
            make_fillet=True,
        )
        panel_b = EditProfileTaskPanel(prof_missing_cat)
        panel_b.initialize_ui()
        panel_b.update_image()

        actual_pixmap_b = panel_b.form_proxy.label_image.pixmap()
        self.assertIsNotNone(actual_pixmap_b)
        self.assertEqual(actual_pixmap_b.toImage(), expected_pixmap.toImage())

    def test_b3_missing_library_edit_preserves_canonical_family_and_geometry(self):
        """S1, S2, S5 (B3): Edit profile with deleted library or missing entry preserves canonical Family."""
        doc = self._create_doc("TestB3MissingLib")
        doc_name = doc.Name

        # 1. Create valid filleted Square Hollow Profile in isolated user library
        prof = self._create_profile_obj(
            doc,
            name="Filleted400",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            material="TestSteel",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=400.0,
            make_fillet=True,
        )

        v_init = prof.Shape.Volume
        self.assertTrue(prof.Shape.isValid())
        self.assertGreater(v_init, 0)

        # Save and reload document
        save_path = os.path.join(self.temp_dir, "test_b3.FCStd")
        doc.saveAs(save_path)
        App.closeDocument(doc_name)
        self.created_docs.remove(doc_name)

        # Delete the user library so catalog is unavailable
        user_lib_file = os.path.join(self.temp_dir, "teststeel.json")
        if os.path.exists(user_lib_file):
            os.remove(user_lib_file)

        reloaded_doc = App.openDocument(save_path)
        self.created_docs.append(reloaded_doc.Name)
        reloaded_prof = reloaded_doc.getObject("Filleted400")

        # Initialize EditProfileTaskPanel, change length 400 -> 450
        panel = EditProfileTaskPanel(reloaded_prof)
        panel.initialize_ui()
        panel.form_proxy.sb_length.setValue(450.0)
        panel.proceed()

        reloaded_doc.recompute()
        reloaded_prof.Proxy.execute(reloaded_prof)

        # Family must remain canonical "Square Hollow", CatalogFamily same
        self.assertEqual(reloaded_prof.Family, "Square Hollow")
        self.assertEqual(reloaded_prof.CatalogFamily, "Square Hollow (Fillet)")
        self.assertTrue(reloaded_prof.Shape.isValid())
        self.assertAlmostEqual(reloaded_prof.Shape.Volume / v_init, 450.0 / 400.0, places=3)
        self.assertNotIn("Invalid", getattr(reloaded_prof, "State", []))

        # 2. Test missing family entry in a present library
        present_lib_data = {
            "_metadata": {"name": "PresentLib", "material": "PresentLib", "density": 7.85},
            "SomeOtherFamily": {
                "norm": "ISO",
                "unit": "mm",
                "fillet": False,
                "sizes": {},
            },
        }
        self.lib_manager.save_user_library("PresentLib", present_lib_data)
        prof_entry_missing = self._create_profile_obj(
            reloaded_doc,
            name="ProfMissingEntry",
            fam="Square Hollow",
            catalog_family="Square Hollow (Fillet)",
            material="PresentLib",
            width=50.0,
            height=50.0,
            thickness=3.0,
            r1=4.0,
            r2=2.0,
            length=400.0,
            make_fillet=True,
        )
        panel_missing_entry = EditProfileTaskPanel(prof_entry_missing)
        panel_missing_entry.initialize_ui()
        panel_missing_entry.form_proxy.sb_length.setValue(420.0)
        panel_missing_entry.proceed()

        reloaded_doc.recompute()
        prof_entry_missing.Proxy.execute(prof_entry_missing)
        self.assertEqual(prof_entry_missing.Family, "Square Hollow")
        self.assertEqual(prof_entry_missing.CatalogFamily, "Square Hollow (Fillet)")
        self.assertTrue(prof_entry_missing.Shape.isValid())

    def test_custom_profile_constructor_baseline_attribute_error_and_shape_handling(self):
        """S5: Profile constructor custom_profile directly accesses .Shape.BoundBox without guard."""
        doc = self._create_doc("TestCustomConstructorBaseline")

        # 1. Shapeless object directly raises AttributeError under baseline behavior
        shapeless = doc.addObject("App::FeaturePython", "ShapelessTarget")
        obj_test = doc.addObject("Part::FeaturePython", "TestShapelessCustom")
        obj_test.addExtension("Part::AttachExtensionPython")

        with self.assertRaises(AttributeError):
            Profile(
                obj_test,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                300.0,
                3.0,
                6.0,
                False,
                1,
                1,
                "Steel",
                "Custom Profile",
                "None",
                False,
                custom_profile=shapeless,
            )

        # 2. Valid Part object with .Shape sets ProfileWidth and ProfileHeight directly
        box = doc.addObject("Part::Box", "ValidBoxCustom")
        box.Length = 35.0
        box.Width = 45.0
        box.Height = 55.0
        doc.recompute()

        obj_valid = doc.addObject("Part::FeaturePython", "TestValidCustom")
        obj_valid.addExtension("Part::AttachExtensionPython")
        Profile(
            obj_valid,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            300.0,
            3.0,
            6.0,
            False,
            1,
            1,
            "Steel",
            "Custom Profile",
            "None",
            False,
            custom_profile=box,
        )
        self.assertEqual(obj_valid.ProfileWidth, box.Shape.BoundBox.XLength)
        self.assertEqual(obj_valid.ProfileHeight, box.Shape.BoundBox.YLength)
        self.assertEqual(obj_valid.Family, "Custom Profile")
        self.assertEqual(obj_valid.CatalogFamily, "Custom Profile")


if __name__ == "__main__":
    unittest.main()

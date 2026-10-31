import unittest

import FreeCAD as App
import Part
import Sketcher

from freecad.maxproframe.create_bom import group_profiles, traverse_assembly
from freecad.maxproframe.populate_ids import populate_ids
from freecad.maxproframe.profile import Profile, ViewProviderCustomProfile


class TestCustomProfileGrouping(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TestCustomProfileGrouping")
        name = self.doc.Name
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)

        # Baseline path sketch (100 mm along X)
        self.path = self.doc.addObject("Sketcher::SketchObject", "Path")
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
        self.path.addConstraint(Sketcher.Constraint("Distance", 0, 100.0))

        # Baseline square section sketch (20x20 mm closed wire)
        self.section = self._create_square_sketch("SharedSection", 20.0)
        self.doc.recompute()

    def _create_square_sketch(self, name, size):
        sketch = self.doc.addObject("Sketcher::SketchObject", name)
        points = [(0, 0), (size, 0), (size, size), (0, size), (0, 0)]
        for start, end in zip(points, points[1:]):
            sketch.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), False)
        return sketch

    def _create_custom_profile(
        self,
        name,
        label,
        custom_source,
        length=100.0,
        material="Steel",
        weight=1.5,
        unitprice=10.0,
        path=None,
        edge="Edge1",
    ):
        target_path = path if path is not None else self.path
        obj = self.doc.addObject("Part::FeaturePython", name)
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (target_path, edge)
        obj.MapPathParameter = 1
        Profile(
            obj,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            float(length),
            float(weight),
            float(unitprice),
            False,
            1,
            1,
            material,
            "Custom Profile",
            "None",
            False,
            (target_path, edge),
            custom_source,
            init_rotation=0.0,
        )
        ViewProviderCustomProfile(obj.ViewObject)
        obj.Label = label
        return obj

    def _bom_data(self, objects):
        profiles_data, links_data = [], []
        for obj in objects:
            traverse_assembly(profiles_data, links_data, obj)
        grouped = group_profiles(profiles_data)
        return profiles_data, grouped

    def test_direct_source_custom_profiles_group_in_bom_and_populate_ids(self):
        """Same direct-source custom profiles must group together in BOM and PID numbering."""
        p1 = self._create_custom_profile("ProfAlpha", "Instance Alpha", self.section)
        p2 = self._create_custom_profile("ProfBeta", "Instance Beta", self.section)
        self.doc.recompute()

        # Geometry & attribute assertions before grouping
        self.assertTrue(p1.Shape.isValid())
        self.assertTrue(p2.Shape.isValid())
        self.assertEqual(p1.Label, "Instance Alpha")
        self.assertEqual(p2.Label, "Instance Beta")
        self.assertEqual(p1.CustomProfile, self.section)
        self.assertEqual(p2.CustomProfile, self.section)

        # 1. BOM grouping check
        raw_profiles, grouped = self._bom_data([p1, p2])
        self.assertEqual(len(raw_profiles), 2)
        # Raw family must resolve to source sketch label, not instance labels
        self.assertEqual(raw_profiles[0]["family"], "SharedSection")
        self.assertEqual(raw_profiles[1]["family"], "SharedSection")
        # Both identical instances must group into a single BOM row with quantity 2
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["family"], "SharedSection")
        self.assertEqual(grouped[0]["quantity"], 2)
        grouped_labels = [lbl.strip() for lbl in grouped[0]["label"].split(",")]
        self.assertIn("Instance Alpha", grouped_labels)
        self.assertIn("Instance Beta", grouped_labels)

        # 2. Populated ID grouping check (with count suffix)
        populate_ids([p1, p2], [], [p1, p2], [], "all_numbers", False, True, True, False, "start_at", start_number="1")
        self.assertEqual(p1.PID, "1 x2")
        self.assertEqual(p2.PID, "1 x2")

        # BOM reflects populated PID
        raw_after, grouped_after = self._bom_data([p1, p2])
        self.assertEqual(grouped_after[0]["ID"], "1 x2")

        # Invariant checks: instance labels, CustomProfile link, and geometry remain untouched
        self.assertEqual(p1.Label, "Instance Alpha")
        self.assertEqual(p2.Label, "Instance Beta")
        self.assertEqual(p1.CustomProfile, self.section)
        self.assertEqual(p2.CustomProfile, self.section)
        self.assertTrue(p1.Shape.isValid())
        self.assertTrue(p2.Shape.isValid())

    def test_direct_source_custom_profiles_count_suffix_disabled(self):
        """Counted suffix disabled assigns identical base ID to grouped direct-source profiles."""
        p1 = self._create_custom_profile("ProfAlphaCountOff", "Instance Alpha", self.section)
        p2 = self._create_custom_profile("ProfBetaCountOff", "Instance Beta", self.section)
        self.doc.recompute()

        populate_ids([p1, p2], [], [p1, p2], [], "all_numbers", False, True, False, False, "start_at", start_number="5")
        self.assertEqual(p1.PID, "5")
        self.assertEqual(p2.PID, "5")

    def test_app_link_custom_profile_control_preserved(self):
        """App::Link custom profiles preserve existing grouping behavior as a control."""
        link = self.doc.addObject("App::Link", "CustomLink")
        link.LinkedObject = self.section
        self.doc.recompute()

        p1 = self._create_custom_profile("LinkAlpha", "Link Instance Alpha", link)
        p2 = self._create_custom_profile("LinkBeta", "Link Instance Beta", link)
        self.doc.recompute()

        raw_profiles, grouped = self._bom_data([p1, p2])
        self.assertEqual(len(raw_profiles), 2)
        self.assertEqual(raw_profiles[0]["family"], "SharedSection")
        self.assertEqual(raw_profiles[1]["family"], "SharedSection")
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["quantity"], 2)

        populate_ids([p1, p2], [], [p1, p2], [], "all_numbers", False, True, True, False, "start_at", start_number="1")
        self.assertEqual(p1.PID, "1 x2")
        self.assertEqual(p2.PID, "1 x2")

    def test_distinct_sources_separate_in_bom_and_populate_ids(self):
        """Custom profiles with different source sketches must separate in BOM and PIDs."""
        section2 = self._create_square_sketch("DistinctSection", 30.0)
        self.doc.recompute()

        p1 = self._create_custom_profile("ProfSrc1", "Instance One", self.section)
        p2 = self._create_custom_profile("ProfSrc2", "Instance Two", section2)
        self.doc.recompute()

        raw_profiles, grouped = self._bom_data([p1, p2])
        self.assertEqual(len(raw_profiles), 2)
        families = {p["family"] for p in raw_profiles}
        self.assertEqual(families, {"SharedSection", "DistinctSection"})
        self.assertEqual(len(grouped), 2)
        self.assertEqual({g["quantity"] for g in grouped}, {1})

        populate_ids([p1, p2], [], [p1, p2], [], "all_numbers", False, True, True, False, "start_at", start_number="1")
        self.assertEqual(p1.PID, "1 x1")
        self.assertEqual(p2.PID, "2 x1")

    def test_differing_fields_separate_even_with_same_source(self):
        """Differing lengths or materials keep identical-source custom profiles separated."""
        # Differing lengths
        path2 = self.doc.addObject("Sketcher::SketchObject", "Path200")
        path2.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(200, 0, 0)), False)
        path2.addConstraint(Sketcher.Constraint("Distance", 0, 200.0))
        self.doc.recompute()

        p_len1 = self._create_custom_profile("ProfLen100", "Len 100", self.section, length=100.0, path=self.path)
        p_len2 = self._create_custom_profile("ProfLen200", "Len 200", self.section, length=200.0, path=path2)
        self.doc.recompute()

        _, grouped_len = self._bom_data([p_len1, p_len2])
        self.assertEqual(len(grouped_len), 2)
        populate_ids(
            [p_len1, p_len2],
            [],
            [p_len1, p_len2],
            [],
            "all_numbers",
            False,
            True,
            True,
            False,
            "start_at",
            start_number="1",
        )
        self.assertEqual(p_len1.PID, "1 x1")
        self.assertEqual(p_len2.PID, "2 x1")

        # Differing materials
        p_mat1 = self._create_custom_profile("ProfSteel", "Steel Inst", self.section, material="Steel")
        p_mat2 = self._create_custom_profile("ProfAlu", "Alu Inst", self.section, material="Aluminium")
        self.doc.recompute()

        _, grouped_mat = self._bom_data([p_mat1, p_mat2])
        self.assertEqual(len(grouped_mat), 2)
        populate_ids(
            [p_mat1, p_mat2],
            [],
            [p_mat1, p_mat2],
            [],
            "all_numbers",
            False,
            True,
            True,
            False,
            "start_at",
            start_number="1",
        )
        self.assertEqual(p_mat1.PID, "1 x1")
        self.assertEqual(p_mat2.PID, "2 x1")

    def test_grouping_disabled_assigns_sequential_ids(self):
        """Grouping disabled assigns sequential unique IDs without count suffixes."""
        p1 = self._create_custom_profile("ProfNoGroup1", "Inst 1", self.section)
        p2 = self._create_custom_profile("ProfNoGroup2", "Inst 2", self.section)
        self.doc.recompute()

        populate_ids([p1, p2], [], [p1, p2], [], "all_numbers", False, False, True, False, "start_at", start_number="1")
        self.assertEqual(p1.PID, "1")
        self.assertEqual(p2.PID, "2")

    def test_standard_profiles_catalog_family_distinction_preserved(self):
        """CatalogFamily distinction in BOM vs Family in populate_ids is preserved for standard profiles."""
        obj = self.doc.addObject("Part::FeaturePython", "StandardSquareHollow")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj,
            50.0,
            50.0,
            3.0,
            0.0,
            4.0,
            2.0,
            500.0,
            5.0,
            15.0,
            True,
            1,
            1,
            "Steel",
            "Square Hollow",
            "50x50x3",
            False,
            catalog_family="Square Hollow (Fillet)",
        )
        self.doc.recompute()

        # In BOM: CatalogFamily is preferred over Family
        raw_profiles, grouped = self._bom_data([obj])
        self.assertEqual(raw_profiles[0]["family"], "Square Hollow (Fillet)")
        self.assertEqual(grouped[0]["family"], "Square Hollow (Fillet)")

        # In populate_ids: non-custom profiles use Family ('Square Hollow'), not CatalogFamily
        populate_ids([obj], [], [obj], [], "all_numbers", False, True, True, False, "start_at", start_number="1")
        self.assertEqual(obj.PID, "1 x1")


if __name__ == "__main__":
    unittest.main()

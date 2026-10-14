import math
import os
import unittest

import FreeCAD as App
import Part

from freecad.frameforge.profile import Profile


class TestCProfiles(unittest.TestCase):
    """
    S1-S2, T1: Unit tests for C profile geometry generation, FreeCAD properties,
    exterior radius derivation, volume/bounding box, validation, restore, and anchoring/mirrors.
    """

    def setUp(self):
        self.doc_count = 0
        self.created_docs = []

    def tearDown(self):
        for doc_name in self.created_docs:
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass

    def _create_doc(self, prefix="TestCDoc"):
        self.doc_count += 1
        name = f"{prefix}_{self.doc_count}_{os.getpid()}"
        doc = App.newDocument(name)
        self.created_docs.append(name)
        return doc

    def _create_c_profile(
        self,
        doc,
        name="CProfile",
        width=50.0,
        height=100.0,
        thickness=2.0,
        lip_length=15.0,
        radius_large=4.0,
        make_fillet=False,
        length=1000.0,
        weight=3.485,
        anchor_x=1,
        anchor_y=1,
        mirror_h=False,
        mirror_v=False,
        execute=True,
        **extra_kwargs,
    ):
        obj = doc.addObject("Part::FeaturePython", name)
        obj.addExtension("Part::AttachExtensionPython")
        proxy = Profile(
            obj,
            init_w=width,
            init_h=height,
            init_mt=thickness,
            init_ft=thickness,
            init_r1=radius_large,
            init_r2=0.0,
            init_len=length,
            init_wg=weight,
            init_unit_price=10.0,
            init_mf=make_fillet,
            init_anchor_x=anchor_x,
            init_anchor_y=anchor_y,
            material="Steel",
            fam="C",
            size_name=f"{int(height)}x{int(width)}x{int(lip_length)}x{int(thickness)}",
            bevels_combined=False,
            init_mirror_h=mirror_h,
            init_mirror_v=mirror_v,
            init_lip_length=lip_length,
            **extra_kwargs,
        )
        if execute:
            proxy.execute(obj)
        return obj, proxy

    def test_c_zero_length_preview_is_a_valid_face(self):
        """Creation previews use a zero-length section for both C variants."""
        for filleted in (False, True):
            with self.subTest(filleted=filleted):
                doc = self._create_doc()
                obj, _ = self._create_c_profile(doc, length=0.0, make_fillet=filleted)
                expected_area = 444.0
                if filleted:
                    expected_area -= (4 - math.pi) * (4**2 - 2**2)
                self.assertFalse(obj.Shape.isNull())
                self.assertTrue(obj.Shape.isValid())
                self.assertEqual(len(obj.Shape.Faces), 1)
                self.assertEqual(len(obj.Shape.Solids), 0)
                self.assertAlmostEqual(obj.Shape.Area, expected_area)
                self.assertAlmostEqual(obj.Shape.BoundBox.XLength, 50.0)
                self.assertAlmostEqual(obj.Shape.BoundBox.YLength, 100.0)
                self.assertAlmostEqual(obj.Shape.BoundBox.ZLength, 0.0)

    def test_c_profile_constructor_properties(self):
        """S1: Profile constructor adds LipLength for C family with trailing init_lip_length."""
        doc = self._create_doc()
        obj, proxy = self._create_c_profile(
            doc,
            width=50.0,
            height=100.0,
            thickness=2.0,
            lip_length=15.0,
            radius_large=4.0,
            make_fillet=True,
            execute=False,
        )

        self.assertEqual(obj.Family, "C")
        self.assertTrue(hasattr(obj, "LipLength"))
        self.assertEqual(obj.LipLength, 15.0)
        self.assertEqual(obj.RadiusLarge, 4.0)
        self.assertEqual(obj.Thickness, 2.0)
        self.assertEqual(obj.ProfileWidth, 50.0)
        self.assertEqual(obj.ProfileHeight, 100.0)

    def test_c_profile_set_properties_trailing_lip_length(self):
        """S1: set_properties accepts trailing init_lip_length=None (preserves existing value) or value."""
        doc = self._create_doc()
        obj, proxy = self._create_c_profile(doc, lip_length=15.0, execute=False)

        # Calling set_properties with init_lip_length=None preserves existing LipLength
        proxy.set_properties(
            obj,
            init_w=50.0,
            init_h=100.0,
            init_mt=2.0,
            init_ft=2.0,
            init_r1=4.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=3.485,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="C",
            size_name="100x50x15x2",
            init_lip_length=None,
        )
        self.assertEqual(obj.LipLength, 15.0)

        # Calling set_properties with explicit init_lip_length updates it
        proxy.set_properties(
            obj,
            init_w=50.0,
            init_h=100.0,
            init_mt=2.0,
            init_ft=2.0,
            init_r1=4.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=3.485,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="C",
            size_name="100x50x20x2",
            init_lip_length=20.0,
        )
        self.assertEqual(obj.LipLength, 20.0)

    def test_plain_c_profile_geometry_bounds_volume_and_opening(self):
        """
        S1: Plain C profile (fixture H=100, B=50, e=2, L=15, length=1000).
        Bounds: X=50, Y=100, Z=1000.
        Volume: Plain area e*(H+2B+2L-4e) = 444 mm2 -> 444,000 mm3.
        Positive-X opening: center is open, web at left, lips at right.
        """
        doc = self._create_doc()
        obj, _ = self._create_c_profile(
            doc,
            width=50.0,
            height=100.0,
            thickness=2.0,
            lip_length=15.0,
            make_fillet=False,
            length=1000.0,
            anchor_x=0,  # Left -> X spans [0, 50]
            anchor_y=0,  # Bottom -> Y spans [0, 100]
            execute=True,
        )

        shape = obj.Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)

        bb = shape.BoundBox
        self.assertAlmostEqual(bb.XLength, 50.0, places=3)
        self.assertAlmostEqual(bb.YLength, 100.0, places=3)
        self.assertAlmostEqual(bb.ZLength, 1000.0, places=3)

        # Expected volume: 444 * 1000 = 444000 mm3
        self.assertAlmostEqual(shape.Volume, 444000.0, delta=1.0)

        # Positive-X opening:
        # At mid-height (Y=50), web is at X in [0, 2].
        # Cavity center is at X=25, Y=50 -> inside bounding box but NOT in solid!
        self.assertTrue(shape.isInside(App.Vector(1.0, 50.0, 500.0), 0.01, True), "Web should be solid")
        self.assertFalse(shape.isInside(App.Vector(25.0, 50.0, 500.0), 0.01, True), "Center cavity must be open")
        # Bottom lip material at X=49, Y=7.5
        self.assertTrue(shape.isInside(App.Vector(49.0, 7.5, 500.0), 0.01, True), "Bottom lip should be solid")
        # Top lip material at X=49, Y=92.5
        self.assertTrue(shape.isInside(App.Vector(49.0, 92.5, 500.0), 0.01, True), "Top lip should be solid")

    def test_filleted_c_profile_geometry_derived_radius_and_volume(self):
        """
        S1, S2: Filleted C profile.
        Sole supplied radius is exterior (RadiusLarge=4.0).
        Interior radius is derived as RadiusSmall = RadiusLarge - Thickness = 2.0.
        Four concentric outer/inner 90-deg pairs.
        Volume: filleted area = 433.69911 mm2 -> 433,699 mm3.
        """
        doc = self._create_doc()
        obj, _ = self._create_c_profile(
            doc,
            width=50.0,
            height=100.0,
            thickness=2.0,
            lip_length=15.0,
            radius_large=4.0,
            make_fillet=True,
            length=1000.0,
            anchor_x=0,
            anchor_y=0,
            execute=True,
        )

        shape = obj.Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)

        # Interior radius derived automatically
        self.assertAlmostEqual(obj.RadiusSmall, 2.0, places=4)

        bb = shape.BoundBox
        self.assertAlmostEqual(bb.XLength, 50.0, places=3)
        self.assertAlmostEqual(bb.YLength, 100.0, places=3)
        self.assertAlmostEqual(bb.ZLength, 1000.0, places=3)

        # Filleted volume: (444 - (4 - pi) * (16 - 4)) * 1000 = 433699.11... mm3
        expected_area = 444.0 - (4.0 - math.pi) * (4.0**2 - 2.0**2)
        expected_volume = expected_area * 1000.0
        self.assertAlmostEqual(shape.Volume, expected_volume, delta=5.0)

        # Strengthened CAD surface inspection:
        # Four outer R (4.0) and four inner R-e (2.0) cylindrical surfaces with shared centers per corner
        cyl_faces = []
        for face in shape.Faces:
            surf = face.Surface
            if hasattr(surf, "Radius"):
                cyl_faces.append((round(surf.Radius, 4), round(surf.Center.x, 3), round(surf.Center.y, 3)))

        self.assertEqual(len(cyl_faces), 8, "Must have exactly 8 cylindrical corner surfaces")
        outer_cyls = [(r, (cx, cy)) for r, cx, cy in cyl_faces if abs(r - 4.0) < 1e-4]
        inner_cyls = [(r, (cx, cy)) for r, cx, cy in cyl_faces if abs(r - 2.0) < 1e-4]

        self.assertEqual(len(outer_cyls), 4, "Must have exactly 4 outer cylindrical surfaces with R=4.0")
        self.assertEqual(len(inner_cyls), 4, "Must have exactly 4 inner cylindrical surfaces with R-e=2.0")

        outer_centers = {center for _, center in outer_cyls}
        inner_centers = {center for _, center in inner_cyls}
        expected_centers = {(46.0, 4.0), (4.0, 4.0), (4.0, 96.0), (46.0, 96.0)}

        self.assertEqual(outer_centers, expected_centers, "Outer cylinders must center at the 4 corners")
        self.assertEqual(inner_centers, expected_centers, "Inner cylinders must be concentric with outer cylinders")

    def test_c_profile_rejects_impossible_dimensions_explicitly(self):
        """S1, S2: Invalid C dimensions fail explicitly without clamping or silent recovery."""
        doc = self._create_doc()

        # LipLength <= 0
        obj1, proxy1 = self._create_c_profile(doc, lip_length=0.0, execute=False)
        with self.assertRaises(ValueError) as ctx1:
            proxy1.execute(obj1)
        self.assertIn("lip", str(ctx1.exception).lower())

        # LipLength <= Thickness
        obj2, proxy2 = self._create_c_profile(doc, thickness=5.0, lip_length=5.0, execute=False)
        with self.assertRaises(ValueError) as ctx2:
            proxy2.execute(obj2)
        self.assertIn("lip", str(ctx2.exception).lower())

        # Width <= 2 * Thickness
        obj3, proxy3 = self._create_c_profile(doc, width=10.0, thickness=6.0, lip_length=15.0, execute=False)
        with self.assertRaises(ValueError) as ctx3:
            proxy3.execute(obj3)
        self.assertIn("width", str(ctx3.exception).lower())

        # 2 * LipLength >= Height (lips collide)
        obj4, proxy4 = self._create_c_profile(doc, height=100.0, lip_length=55.0, execute=False)
        with self.assertRaises(ValueError) as ctx4:
            proxy4.execute(obj4)
        self.assertIn("lip", str(ctx4.exception).lower())

        # Filleted: RadiusLarge <= Thickness (interior radius <= 0)
        obj5, proxy5 = self._create_c_profile(
            doc, thickness=3.0, radius_large=3.0, make_fillet=True, execute=False
        )
        with self.assertRaises(ValueError) as ctx5:
            proxy5.execute(obj5)
        self.assertIn("radius", str(ctx5.exception).lower())

        # Filleted: RadiusLarge > LipLength
        obj6, proxy6 = self._create_c_profile(
            doc, lip_length=10.0, radius_large=12.0, make_fillet=True, execute=False
        )
        with self.assertRaises(ValueError) as ctx6:
            proxy6.execute(obj6)
        self.assertIn("radius", str(ctx6.exception).lower())

    def test_migration_installs_guarded_lip_length_only_for_c(self):
        """
        S1, L5: Migration installs guarded LipLength=0.0 for C lacking LipLength,
        without manufacturing valid dimensions, and does NOT inject LipLength into non-C profiles.
        """
        doc = self._create_doc()

        # Non-C profile (Channels) lacking LipLength
        obj_ch = doc.addObject("Part::FeaturePython", "TestChannel")
        obj_ch.addExtension("Part::AttachExtensionPython")
        proxy_ch = Profile(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            bevels_combined=False,
        )
        proxy_ch.run_compatibility_migrations(obj_ch)
        self.assertFalse(hasattr(obj_ch, "LipLength"), "Non-C profiles must not receive LipLength on restore")

        # C profile artificially stripped of LipLength (simulating old save)
        obj_c = doc.addObject("Part::FeaturePython", "TestC")
        obj_c.addExtension("Part::AttachExtensionPython")
        proxy_c = Profile(
            obj_c,
            init_w=50.0,
            init_h=100.0,
            init_mt=2.0,
            init_ft=2.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=3.485,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="C",
            size_name="100x50x15x2",
            bevels_combined=False,
        )
        if hasattr(obj_c, "LipLength"):
            obj_c.removeProperty("LipLength")

        self.assertFalse(hasattr(obj_c, "LipLength"))
        proxy_c.run_compatibility_migrations(obj_c)
        self.assertTrue(hasattr(obj_c, "LipLength"), "C profiles must receive guarded LipLength on restore")
        self.assertEqual(obj_c.LipLength, 0.0, "Must not silently manufacture valid dimensions")

    def test_non_c_profile_does_not_receive_lip_length_on_init_or_set_properties(self):
        """S1, L5: Non-C profile never receives LipLength even if init_lip_length is passed."""
        doc = self._create_doc()

        # Constructor with init_lip_length=15.0 on Channels
        obj_ch = doc.addObject("Part::FeaturePython", "TestChannelNoLip")
        obj_ch.addExtension("Part::AttachExtensionPython")
        proxy_ch = Profile(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            bevels_combined=False,
            init_lip_length=15.0,
        )
        self.assertFalse(hasattr(obj_ch, "LipLength"), "Constructor must not add LipLength to non-C")

        # set_properties with optional default init_lip_length=0.0
        proxy_ch.set_properties(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            init_lip_length=0.0,
        )
        self.assertFalse(hasattr(obj_ch, "LipLength"), "set_properties must not add LipLength to non-C on 0.0")

        # set_properties with explicit init_lip_length=20.0
        proxy_ch.set_properties(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            init_lip_length=20.0,
        )
        self.assertFalse(hasattr(obj_ch, "LipLength"), "set_properties must not add LipLength to non-C even on 20.0")

    def test_existing_family_callback_behavior_preserved_and_c_recalculation_scoped(self):
        """
        S1: on_changed recalculation triggers for LipLength/RadiusLarge/MakeFillet
        are strictly scoped to C, preserving legacy trigger expressions for other families.
        onDocumentRestored only runs restore logic for C.
        """
        doc = self._create_doc()

        # 1. Non-C profile (Channels)
        obj_ch = doc.addObject("Part::FeaturePython", "TestChannelCB")
        obj_ch.addExtension("Part::AttachExtensionPython")
        proxy_ch = Profile(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            bevels_combined=False,
        )
        proxy_ch.execute(obj_ch)

        ch_exec_calls = []
        proxy_ch.execute = lambda o: ch_exec_calls.append(o)

        # Legacy trigger expression MUST call execute
        proxy_ch.on_changed(obj_ch, "ProfileWidth")
        self.assertEqual(len(ch_exec_calls), 1)

        # Unrelated C-only triggers on non-C MUST NOT call execute
        proxy_ch.on_changed(obj_ch, "LipLength")
        self.assertEqual(len(ch_exec_calls), 1)

        proxy_ch.on_changed(obj_ch, "RadiusLarge")
        self.assertEqual(len(ch_exec_calls), 1)

        proxy_ch.on_changed(obj_ch, "RadiusSmall")
        self.assertEqual(len(ch_exec_calls), 1)

        proxy_ch.on_changed(obj_ch, "MakeFillet")
        self.assertEqual(len(ch_exec_calls), 1)

        # 2. C profile
        obj_c, proxy_c = self._create_c_profile(doc, name="TestCCB", execute=True)
        c_exec_calls = []
        proxy_c.execute = lambda o: c_exec_calls.append(o)

        proxy_c.on_changed(obj_c, "LipLength")
        self.assertEqual(len(c_exec_calls), 1)

        proxy_c.on_changed(obj_c, "RadiusLarge")
        self.assertEqual(len(c_exec_calls), 2)

        proxy_c.on_changed(obj_c, "MakeFillet")
        self.assertEqual(len(c_exec_calls), 3)

        # RadiusSmall must NOT trigger execute (avoid recursion)
        proxy_c.on_changed(obj_c, "RadiusSmall")
        self.assertEqual(len(c_exec_calls), 3)

    def test_c_profile_anchoring_and_mirroring(self):
        """S1: C profile correctly respects AnchorX, AnchorY, MirrorH, MirrorV."""
        doc = self._create_doc()
        # Centered anchor
        obj_center, _ = self._create_c_profile(
            doc,
            anchor_x=1,  # Center -> X spans [-25, 25]
            anchor_y=1,  # Center -> Y spans [-50, 50]
            mirror_h=True,
            mirror_v=True,
            execute=True,
        )
        bb = obj_center.Shape.BoundBox
        self.assertAlmostEqual(bb.XMin, -25.0, places=3)
        self.assertAlmostEqual(bb.XMax, 25.0, places=3)
        self.assertAlmostEqual(bb.YMin, -50.0, places=3)
        self.assertAlmostEqual(bb.YMax, 50.0, places=3)

    def test_preserve_channels_and_upe_behavior(self):
        """Preserve: public Channels and UPE profiles remain completely functional and unchanged."""
        doc = self._create_doc()

        # Channels profile
        obj_ch = doc.addObject("Part::FeaturePython", "ChannelsTest")
        obj_ch.addExtension("Part::AttachExtensionPython")
        proxy_ch = Profile(
            obj_ch,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=0,
            init_anchor_y=0,
            material="Steel",
            fam="Channels",
            size_name="100x50",
            bevels_combined=False,
        )
        proxy_ch.execute(obj_ch)
        self.assertFalse(obj_ch.Shape.isNull())
        bb_ch = obj_ch.Shape.BoundBox
        self.assertAlmostEqual(bb_ch.XLength, 50.0, places=3)
        self.assertAlmostEqual(bb_ch.YLength, 100.0, places=3)
        self.assertAlmostEqual(bb_ch.ZLength, 1000.0, places=3)

        # UPE profile
        obj_upe = doc.addObject("Part::FeaturePython", "UPETest")
        obj_upe.addExtension("Part::AttachExtensionPython")
        proxy_upe = Profile(
            obj_upe,
            init_w=50.0,
            init_h=100.0,
            init_mt=4.0,
            init_ft=6.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=1000.0,
            init_wg=7.47,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=0,
            init_anchor_y=0,
            material="Steel",
            fam="UPE",
            size_name="100x50",
            bevels_combined=False,
        )
        proxy_upe.execute(obj_upe)
        self.assertFalse(obj_upe.Shape.isNull())

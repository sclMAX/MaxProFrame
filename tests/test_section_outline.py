import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part

from freecad.maxproframe.library_manager import LibraryManager, get_canonical_family
from freecad.maxproframe.profile import Profile
from freecad.maxproframe.section_outline import build_section_face


class TestSectionOutline(unittest.TestCase):
    def test_standard_sections_match_actual_extruded_caps_without_document_changes(self):
        doc = App.newDocument("OutlineParity")
        self.addCleanup(App.closeDocument, doc.Name)
        profiles = LibraryManager().get_all_profiles()
        checked = set()
        for material, families in profiles.items():
            for name, data in families.items():
                family = get_canonical_family(name, data)
                if family == "Custom Profile" or family in checked or not data.get("sizes"):
                    continue
                size = next(iter(data["sizes"].values()))
                p = dict(
                    Family=family,
                    ProfileWidth=float(size.get("Width", 0)),
                    ProfileHeight=float(size.get("Height", 0)),
                    Thickness=float(size.get("Thickness", 0)),
                    ThicknessFlange=float(size.get("Flange Thickness", 0)),
                    RadiusLarge=float(size.get("Radius1", 0)),
                    RadiusSmall=float(size.get("Radius2", 0)),
                    LipLength=float(size.get("Lip Length", 0)),
                    MakeFillet=bool(data.get("fillet")) and family not in ("HEA", "HEB", "HEM"),
                )
                with self.subTest(family=family):
                    before = tuple(doc.Objects)
                    selection = tuple(Gui.Selection.getSelection())
                    section = build_section_face(p)
                    self.assertEqual(tuple(doc.Objects), before)
                    self.assertEqual(tuple(Gui.Selection.getSelection()), selection)
                    self.assertTrue(section.isValid())
                    obj = doc.addObject("Part::FeaturePython", "Parity")
                    obj.addExtension("Part::AttachExtensionPython")
                    Profile(
                        obj,
                        p["ProfileWidth"],
                        p["ProfileHeight"],
                        p["Thickness"],
                        p["ThicknessFlange"],
                        p["RadiusLarge"],
                        p["RadiusSmall"],
                        25,
                        1,
                        0,
                        p["MakeFillet"],
                        0,
                        0,
                        material,
                        family,
                        "Parity",
                        False,
                        init_lip_length=p["LipLength"],
                    )
                    doc.recompute()
                    self.assertTrue(obj.Shape.isValid())
                    caps = [
                        f
                        for f in obj.Shape.Faces
                        if f.optimalBoundingBox(False).ZLength < 1e-6 and abs(f.optimalBoundingBox(False).ZMin) < 1e-6
                    ]
                    self.assertEqual(len(caps), 1)
                    self.assertAlmostEqual(section.Area, caps[0].Area, places=5)
                    self.assertAlmostEqual(section.common(caps[0]).Area, section.Area, places=5)
                    self.assertEqual(len(section.Wires), len(caps[0].Wires))
                checked.add(family)
        self.assertTrue({"Pipe", "Round Bar", "V-Slot", "T-Slot", "Square Hollow"} <= checked)

    def test_lipped_c_section_matches_extrusion_with_and_without_fillets(self):
        doc = App.newDocument("COutlineParity")
        self.addCleanup(App.closeDocument, doc.Name)
        for fillet in (False, True):
            parameters = dict(
                Family="C",
                ProfileWidth=50,
                ProfileHeight=100,
                Thickness=2,
                ThicknessFlange=2,
                RadiusLarge=4,
                RadiusSmall=0,
                LipLength=15,
                MakeFillet=fillet,
            )
            section = build_section_face(parameters)
            obj = doc.addObject("Part::FeaturePython", "CParity")
            obj.addExtension("Part::AttachExtensionPython")
            Profile(obj, 50, 100, 2, 2, 4, 0, 25, 1, 0, fillet, 0, 0, "Steel", "C", "Parity", False, init_lip_length=15)
            doc.recompute()
            cap = next(
                f
                for f in obj.Shape.Faces
                if f.optimalBoundingBox(False).ZLength < 1e-6 and abs(f.optimalBoundingBox(False).ZMin) < 1e-6
            )
            self.assertAlmostEqual(section.Area, cap.Area, places=5)
            self.assertAlmostEqual(section.common(cap).Area, section.Area, places=5)
            self.assertEqual(parameters["RadiusSmall"], 0)

    def test_unsupported_filleted_h_families_retain_builder_failure(self):
        # Existing extrusion builder has no filleted HEA/HEB/HEM branch. Do not
        # invent preview geometry or fix unrelated modeling behavior in this task.
        for family in ("HEA", "HEB", "HEM"):
            with self.subTest(family=family):
                with self.assertRaises(UnboundLocalError):
                    build_section_face(
                        dict(
                            Family=family,
                            ProfileWidth=100,
                            ProfileHeight=100,
                            Thickness=6,
                            ThicknessFlange=8,
                            RadiusLarge=12,
                            RadiusSmall=6,
                            MakeFillet=True,
                        )
                    )

    def test_custom_offset_holes_source_immutability(self):
        outer = Part.makePolygon(
            [App.Vector(x, y, 0) for x, y in ((37, -23), (77, -23), (77, -3), (37, -3), (37, -23))]
        )
        hole = Part.Wire([Part.makeCircle(3, App.Vector(47, -13, 0))])
        source = Part.makeFace([outer, hole], "Part::FaceMakerBullseye")
        before = source.exportBrepToString()
        result = build_section_face({"Family": "Custom Profile"}, custom_face=source)
        self.assertAlmostEqual(result.Area, source.Area, places=5)
        self.assertEqual(len(result.Wires), 2)
        self.assertAlmostEqual(result.optimalBoundingBox(False).XMin, 0)
        self.assertAlmostEqual(result.optimalBoundingBox(False).YMin, 0)
        self.assertEqual(source.exportBrepToString(), before)

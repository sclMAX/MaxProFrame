import unittest
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

from freecad.maxproframe.create_profiles_tool import BaseProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.profile import Profile, ViewProviderCustomProfile, ViewProviderProfile


class TestProfileEditState(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.doc = App.newDocument("EditStateTest")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("Part::FeaturePython", "Profile")
        self.obj.addExtension("Part::AttachExtensionPython")
        Profile(
            self.obj,
            init_w=50.0,
            init_h=50.0,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=250.0,
            init_wg=8.0,
            init_unit_price=3.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="Square Hollow",
            size_name="StoredSize",
            bevels_combined=False,
            catalog_family="Square Hollow",
        )
        if Gui.activeDocument() is None:
            self.skipTest("Real GUI document required for appearance and transaction checks")
        ViewProviderProfile(self.obj.ViewObject)
        self.doc.recompute()
        self.obj.ViewObject.ShapeColor = (0.1, 0.7, 0.2)
        self.obj.ViewObject.Transparency = 23
        self.doc.clearUndos()

        def isolated_catalog(panel):
            panel.profiles = {}
            panel.library_manager = SimpleNamespace(_get_registered_folder=lambda material: None)

        catalog_patch = patch.object(BaseProfileTaskPanel, "load_data", isolated_catalog)
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)
        self.panel = EditProfileTaskPanel(self.obj)
        for form in self.panel.form:
            self.addCleanup(form.close)
        self.original = self.snapshot()

    def snapshot(self):
        fields = (
            "ProfileLength",
            "ProfileWidth",
            "ProfileHeight",
            "Thickness",
            "ThicknessFlange",
            "RadiusLarge",
            "RadiusSmall",
            "LinearWeight",
            "ApproxWeight",
            "UnitPrice",
            "Material",
            "Family",
            "CatalogFamily",
            "SizeName",
            "AnchorX",
            "AnchorY",
            "MirrorH",
            "MirrorV",
            "RotationAngle",
            "MakeFillet",
        )
        return {
            "model": {field: getattr(self.obj, field) for field in fields},
            "color": tuple(self.obj.ViewObject.ShapeColor),
            "transparency": self.obj.ViewObject.Transparency,
            "volume": self.obj.Shape.Volume,
            "custom_source": getattr(self.obj, "CustomProfile", None),
            "source_shape": (self.obj.CustomProfile.Shape.exportBrepToString() if self.obj.CustomProfile else None),
            "objects": tuple(obj.Name for obj in self.doc.Objects),
        }

    def assert_identity_and_shape(self):
        for field in ("Material", "Family", "CatalogFamily", "SizeName"):
            self.assertEqual(getattr(self.obj, field), self.original["model"][field])
        self.assertFalse(self.obj.Shape.isNull())
        self.assertTrue(self.obj.Shape.isValid())
        self.assertEqual(self.snapshot()["custom_source"], self.original["custom_source"])
        self.assertEqual(self.snapshot()["source_shape"], self.original["source_shape"])
        self.assertEqual(self.snapshot()["objects"], self.original["objects"])

    def test_initialization_loads_linear_not_total_weight(self):
        self.panel.initialize_ui()
        self.assertEqual(self.panel.form_proxy.sb_weight.value(), 8.0)
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_open_leaves_stored_model_and_geometry_unchanged(self):
        original_shape = self.obj.Shape.exportBrepToString()
        original_placement = self.obj.Placement.toMatrix().A
        self.panel.open()
        opened = self.snapshot()
        self.assertEqual(opened["model"], self.original["model"])
        self.assertEqual(opened["volume"], self.original["volume"])
        self.assertEqual(self.obj.Shape.exportBrepToString(), original_shape)
        self.assertEqual(self.obj.Placement.toMatrix().A, original_placement)
        self.assertEqual(opened["transparency"], 50)
        for actual, expected in zip(opened["color"], (0.8, 0.2, 0.1)):
            self.assertAlmostEqual(actual, expected, places=6)
        self.panel.reject()
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(self.doc.UndoCount, 0)

    def test_accept_preserves_original_appearance(self):
        self.panel.open()
        self.assertIs(self.panel.accept(), True)
        self.assertEqual(self.snapshot()["color"], self.original["color"])
        self.assertEqual(self.snapshot()["transparency"], 23)
        self.assertEqual(self.snapshot()["model"], self.original["model"])
        self.assert_identity_and_shape()

    def test_accept_length_change_preserves_linear_weight_and_updates_total(self):
        self.panel.open()
        self.panel.form_proxy.sb_length.setValue(500.0)
        self.assertIs(self.panel.accept(), True)
        self.assertEqual(self.obj.ProfileLength, 500.0)
        self.assertEqual(self.obj.LinearWeight, 8.0)
        self.assertEqual(self.obj.ApproxWeight, 4.0)
        self.assertEqual(self.snapshot()["color"], self.original["color"])
        self.assertEqual(self.obj.ViewObject.Transparency, 23)
        self.assertEqual(self.doc.UndoCount, 1)
        self.assert_identity_and_shape()

    def test_accept_explicit_weight_change_still_applies(self):
        self.panel.open()
        self.panel.form_proxy.sb_weight.setValue(10.0)
        self.assertIs(self.panel.accept(), True)
        self.assertEqual(self.obj.LinearWeight, 10.0)
        self.assertEqual(self.obj.ApproxWeight, 2.5)
        self.assertEqual(self.doc.UndoCount, 1)
        self.assert_identity_and_shape()

    def test_cancel_changes_restores_model_appearance_and_undo_count(self):
        self.panel.open()
        self.panel.form_proxy.sb_length.setValue(500.0)
        self.panel.form_proxy.sb_weight.setValue(10.0)
        self.panel.proceed()
        self.assertIs(self.panel.reject(), True)
        self.assertEqual(self.snapshot(), self.original)
        self.assertEqual(self.doc.UndoCount, 0)


class TestCustomProfileEditState(TestProfileEditState):
    def setUp(self):
        super().setUp()
        source = self.doc.addObject("PartDesign::Feature", "CP1Section")
        outer = Part.makePolygon(
            [
                App.Vector(0, 0, 0),
                App.Vector(20, 0, 0),
                App.Vector(20, 10, 0),
                App.Vector(0, 10, 0),
                App.Vector(0, 0, 0),
            ]
        )
        inner = Part.makePolygon(
            [
                App.Vector(2, 2, 0),
                App.Vector(6, 2, 0),
                App.Vector(6, 5, 0),
                App.Vector(2, 5, 0),
                App.Vector(2, 2, 0),
            ]
        )
        source.Shape = Part.makeFace([outer, inner], "Part::FaceMakerBullseye")
        self.obj.Family = "Custom Profile"
        self.obj.CatalogFamily = "Custom Profile"
        self.obj.SizeName = "CP1"
        self.obj.CustomProfile = source
        ViewProviderCustomProfile(self.obj.ViewObject)
        self.doc.recompute()
        self.obj.ViewObject.ShapeColor = (0.1, 0.7, 0.2)
        self.obj.ViewObject.Transparency = 23
        self.doc.clearUndos()
        self.original = self.snapshot()
        self.assertTrue(self.obj.Shape.isValid())
        self.assertAlmostEqual(self.obj.Shape.Volume, 188.0 * self.obj.ProfileLength)


if __name__ == "__main__":
    unittest.main()

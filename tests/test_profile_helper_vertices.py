import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part

from freecad.frameforge.profile import Profile, ViewProviderProfile


class TestProfileHelperVertices(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ProfileHelperVertices")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.doc.UndoMode = 1

    def assert_vector(self, value, expected):
        for i in range(3):
            self.assertAlmostEqual(float(value[i]), expected[i], places=5)

    def assert_attach_preserves_model(self, closed):
        axis = self.doc.addObject("Part::Feature", "Axis")
        axis.Shape = (
            Part.makeCircle(100.0) if closed
            else Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 0, 250))
        )
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj, init_w=50.0, init_h=50.0, init_mt=2.0, init_ft=0.0,
            init_r1=0.0, init_r2=0.0, init_len=250.0, init_wg=8.0,
            init_unit_price=3.0, init_mf=False, init_anchor_x=1, init_anchor_y=1,
            material="Metal", fam="Square Hollow", size_name="HelperProbe",
            bevels_combined=False, catalog_family="Square Hollow (No Fillet)",
            link_sub=(axis, ("Edge1",)),
        )
        obj.PID = "0042"
        self.doc.recompute()
        self.assertEqual(len(axis.Shape.Vertexes), 1 if closed else 2)
        # A closed path has a separate, pre-existing model error. The helper
        # guard must not add an attachment exception or claim to repair it.
        status = "Cannot normalize null vector" if closed else "Valid"
        self.assertEqual(obj.getStatusString(), status)
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())
        fields = (
            "PID", "Family", "CatalogFamily", "SizeName", "Material", "LinearWeight", "ApproxWeight",
            "ProfileWidth", "ProfileHeight", "ProfileLength", "UnitPrice", "Price", "OffsetA", "OffsetB",
            "CuttingAngleA", "CuttingAngleB",
        )
        before_fields = {key: getattr(obj, key) for key in fields}
        before_shape = obj.Shape.copy()
        before_axis = axis.Shape.exportBrepToString()
        before_placement = list(obj.Placement.toMatrix().A)
        before_axis_placement = list(axis.Placement.toMatrix().A)
        before_visible = obj.ViewObject.Visibility
        before_names = [item.Name for item in self.doc.Objects]
        self.doc.clearUndos()
        # Exercise the actual public lifecycle hook once, with real Coin nodes.
        # Bypass automatic registration, which can swallow attach exceptions.
        provider = ViewProviderProfile.__new__(ViewProviderProfile)
        self.addCleanup(Gui.Selection.removeObserver, provider)
        self.assertIsNone(provider.attach(obj.ViewObject))
        self.assertEqual(obj.getStatusString(), status)
        self.assertAlmostEqual(before_shape.cut(obj.Shape).Volume, 0.0, places=5)
        self.assertAlmostEqual(obj.Shape.cut(before_shape).Volume, 0.0, places=5)
        self.assertEqual(axis.Shape.exportBrepToString(), before_axis)
        self.assertEqual(list(obj.Placement.toMatrix().A), before_placement)
        self.assertEqual(list(axis.Placement.toMatrix().A), before_axis_placement)
        self.assertEqual(obj.ViewObject.Visibility, before_visible)
        self.assertEqual([item.Name for item in self.doc.Objects], before_names)
        for key, value in before_fields.items():
            self.assertEqual(getattr(obj, key), value, key)
        self.assertEqual(obj.PID, "0042")
        self.assertEqual(obj.CatalogFamily, "Square Hollow (No Fillet)")
        self.assertEqual(self.doc.UndoCount, 0)
        if not closed:
            self.assert_vector(provider.p1_tr.translation.getValue(), (0, 0, 250))
            self.assert_vector(provider.p2_tr.translation.getValue(), (0, 0, 0))
            self.assert_vector(provider.p1_label_tr.translation.getValue(), (0, 0, 225))
            self.assert_vector(provider.p2_label_tr.translation.getValue(), (0, 0, 25))
            self.assert_vector(provider.dir_coords.point[0], (0, 0, 250))
            self.assert_vector(provider.dir_coords.point[1], (0, 0, 0))
            for coords, start, end in (
                (provider.p1_x_coords, (0, 0, 250), (50, 0, 250)),
                (provider.p1_y_coords, (0, 0, 250), (0, 50, 250)),
                (provider.p2_x_coords, (0, 0, 0), (50, 0, 0)),
                (provider.p2_y_coords, (0, 0, 0), (0, 50, 0)),
            ):
                self.assert_vector(coords.point[0], start)
                self.assert_vector(coords.point[1], end)

    def test_closed_edge_does_not_add_a_helper_attachment_exception(self):
        self.assert_attach_preserves_model(closed=True)

    def test_line_keeps_markers_labels_and_guides(self):
        self.assert_attach_preserves_model(closed=False)


if __name__ == "__main__":
    unittest.main()

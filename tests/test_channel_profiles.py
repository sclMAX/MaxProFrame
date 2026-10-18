import unittest

import FreeCAD as App
import Part

from freecad.maxproframe.profile import Profile


class TestChannelProfiles(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ChannelRegression")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def create_profile(self, family="Channels", length=500, flange=4):
        obj = self.doc.addObject("Part::FeaturePython", "Channel")
        obj.addExtension("Part::AttachExtensionPython")
        Profile(obj, 50, 100, 2, flange, 0, 0, length, 4, 10,
                False, 1, 1, "Metal", family, "pGC100", False)
        obj.Proxy.execute(obj)
        return obj

    def test_channels_generate_valid_open_section(self):
        obj = self.create_profile()
        shape = obj.Shape
        area = 2 * (100 - 2 * 4) + 2 * 50 * 4
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.Volume, area * 500)
        self.assertAlmostEqual(shape.BoundBox.XLength, 50)
        self.assertAlmostEqual(shape.BoundBox.YLength, 100)
        self.assertAlmostEqual(shape.BoundBox.ZLength, 500)
        self.assertTrue(shape.isInside(App.Vector(-24, 0, 250), 1e-7, True))
        self.assertTrue(shape.isInside(App.Vector(0, 49, 250), 1e-7, True))
        self.assertFalse(shape.isInside(App.Vector(0, 0, 250), 1e-7, True))
        self.assertEqual(obj.Family, "Channels")
        self.assertEqual(obj.CatalogFamily, "Channels")

    def test_plain_upe_generation_is_unchanged(self):
        obj = self.create_profile(family="UPE")
        self.assertTrue(obj.Shape.isValid())
        self.assertEqual(len(obj.Shape.Solids), 1)
        self.assertAlmostEqual(obj.Shape.Volume, (50 * 2 + 2 * (100 - 2) * 4) * 500)


if __name__ == "__main__":
    unittest.main()

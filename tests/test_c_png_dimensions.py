import os
import unittest

from PySide import QtGui

from freecad.frameforge.ff_tools import PROFILEIMAGES_PATH


class TestCPngDimensions(unittest.TestCase):
    def test_c_assets_decode_at_family_dimensions(self):
        for name in ("C.png", "C_Fillet.png"):
            with self.subTest(name=name):
                image = QtGui.QImage(os.path.join(PROFILEIMAGES_PATH, "Metal", name))
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), (200, 100))

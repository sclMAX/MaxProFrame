"""Lengths written in the panels use the decimal separator of the current locale (odd/tasks/pending-followups.md, S4b).

``expression_fields.length_text`` writes the lengths of the Folded Bar corner list and tube label, Profile Pattern
and Drill Hole messages: up to two decimals, no trailing zeros, with the separator the number fields show.
"""

import unittest

from miter_helpers import use_language
from PySide import QtWidgets

from freecad.maxproframe.expression_fields import length_text


class TestLengthText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def assertTexts(self, separator):
        for value, text in (
            (0.5, f"0{separator}5 mm"),
            (0.3, f"0{separator}3 mm"),
            (12.25, f"12{separator}25 mm"),
            (12.5, f"12{separator}5 mm"),
            (10.0, "10 mm"),
            (0.0, "0 mm"),
            (0.004, "0 mm"),
            # No group separator: the fields show none.
            (6000.0, "6000 mm"),
            (1234.5, f"1234{separator}5 mm"),
        ):
            with self.subTest(value=value):
                self.assertEqual(text, length_text(value))

    def test_spanish_writes_a_decimal_comma(self):
        use_language(self, "Spanish", "es_ES")

        self.assertTexts(",")

    def test_english_writes_a_decimal_point(self):
        use_language(self, "English", "en_US")

        self.assertTexts(".")


if __name__ == "__main__":
    unittest.main()

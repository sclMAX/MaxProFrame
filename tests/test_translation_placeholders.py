"""Every translation keeps the placeholders of its source text.

The code fills the texts with str.format (``{}``, ``{max:g}``, ``{crossbar}``) or with ``%`` (``%s``, ``%d``): a
translation that renames a named field raises KeyError when the message is shown, and one that drops a field hides
the names it should tell. The field names are identifiers, never translated.
"""

import glob
import os
import re
import string
import unittest
import xml.etree.ElementTree as ET

TRANSLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "freecad", "maxproframe", "resources", "translations"
)
PERCENT_FIELD = re.compile(r"%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdifgrx]")


def format_fields(text):
    """Field names of a str.format text, automatic ``{}`` fields numbered in order; None if it does not parse."""
    fields = set()
    automatic = 0
    try:
        for _, name, _, _ in string.Formatter().parse(text):
            if name is None:
                continue
            if name == "":
                name = str(automatic)
                automatic += 1
            fields.add(name)
    except ValueError:
        return None
    return fields


def placeholders(text):
    """What a text needs from the code: its str.format fields and its ``%`` fields, in order."""
    return format_fields(text), sorted(PERCENT_FIELD.findall(text.replace("%%", "")))


def translated_messages(path):
    """(context, source, translation) of the finished messages a catalog still uses."""
    for context in ET.parse(path).getroot().iter("context"):
        for message in context.iter("message"):
            translation = message.find("translation")
            if translation is None or translation.get("type") in ("unfinished", "vanished", "obsolete"):
                continue
            if translation.text:
                yield context.findtext("name"), message.findtext("source"), translation.text


def mismatches(path):
    """Messages of a catalog whose translation does not keep the placeholders of its source."""
    return [
        (context, source, translation)
        for context, source, translation in translated_messages(path)
        if placeholders(source) != placeholders(translation)
    ]


class TestTranslationPlaceholders(unittest.TestCase):
    def test_every_catalog_keeps_the_placeholders_of_its_sources(self):
        catalogs = sorted(glob.glob(os.path.join(TRANSLATIONS_DIR, "*.ts")))
        self.assertTrue(catalogs)
        for path in catalogs:
            with self.subTest(catalog=os.path.basename(path)):
                self.assertEqual([], mismatches(path))

    def test_a_renamed_or_dropped_field_is_a_mismatch(self):
        self.assertNotEqual(placeholders("{crossbar} on {rail}"), placeholders("{поперечина} на {rail}"))
        self.assertNotEqual(placeholders("between {} and {}"), placeholders("между"))
        self.assertNotEqual(placeholders("Could not import: %s"), placeholders("Не удалось импортировать"))

    def test_reordered_or_numbered_fields_are_kept(self):
        self.assertEqual(placeholders("{} and {}: {max:g} mm"), placeholders("{max:g} мм: {0} и {1}"))
        self.assertEqual(placeholders("%s of %d"), placeholders("%d из %s"))


if __name__ == "__main__":
    unittest.main()

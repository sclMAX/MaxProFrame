"""The Russian catalog loads when FreeCAD runs in Russian."""

import os
import unittest
import xml.etree.ElementTree as ET

import FreeCADGui as Gui
from miter_helpers import use_language

from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate

# Texts of the folded miters, added after v1.13.1: listed unfinished in the Russian catalog for its translator.
FOLDED_MITER_TEXTS = (
    ("MaxProFrame", "{} has no path to fold."),
    ("MaxProFrame", "{} follows a curved path: only straight profiles can be folded."),
    ("MaxProFrame", "{} is a {} profile: only Square Hollow and Rectangular Hollow tubes can be folded."),
    ("MaxProFrame", "{} is not the same tube as {}: {} instead of {}."),
    ("MaxProFrame", "More than two of the selected profiles meet at one point."),
    ("MaxProFrame", "The selected profiles do not form one chain: {} meets none of the others."),
    ("MaxProFrame", "{} and {} are in line: there is nothing to fold."),
    ("MaxProFrame", "{1} turns back on {0}: a corner can fold less than 180 degrees."),
    (
        "MaxProFrame",
        "The corner between {} and {} bends across a corner of the tube: its walls must be parallel to the bend.",
    ),
    ("MaxProFrame", "{1} does not continue {0} across the fold: give both the same anchor, offsets and rotation."),
    ("MaxProFrame", "{} cuts {} at its folded corner with {}: delete it or make that corner the open one."),
    ("MaxProFrame", "{} cuts {} at its folded corner with {}: delete it."),
    ("MaxProFrame", "{} is not a profile."),
    ("MaxProFrame", "{} is selected more than once."),
    ("MaxProFrame", "Select at least two profiles that meet end to end."),
    ("MaxProFrame", "Only a closed frame has an open corner: these profiles already have two free ends."),
    ("MaxProFrame", "Select first a profile at one end of the chain: {} is in its middle."),
    ("MaxProFrame", "{} and {} do not meet at a corner."),
    ("MaxProFrame", "The open corner must be at one end of the first selected profile ({})."),
    ("MaxProFrame", "The selected profiles do not form one chain."),
    ("MaxProFrame", "{config} is for {a:g} mm walls; {tube} has {b:g} mm walls."),
    ("MaxProFrame", "The inside bend radius must be between {min:g} and {max:g} mm."),
    ("MaxProFrame", "The key does not fit in the notch between {} and {}: make it smaller."),
    (
        "MaxProFrame",
        "The key does not fit in the notch between {} and {} with this inside radius: make the radius smaller or "
        "turn the key off.",
    ),
    (
        "MaxProFrame",
        "{}: its developed length ({:.1f} mm) is longer than the stock length of the cut list ({:.1f} mm).\n",
    ),
    ("MaxProFrame", "{} does not fold into one solid: change its bend settings."),
    ("MaxProFrame", "{} does not unfold into one solid: change its bend settings."),
    ("MaxProFrame", "Folded Bar"),
    ("MaxProFrame", "Tube pieces, from the start of the bar"),
    ("MaxProFrame", "Bend"),
    ("MaxProFrame", "Manage configurations"),
    ("MaxProFrame", "Configuration"),
    ("MaxProFrame", "Inside bend radius of every folded corner"),
    ("MaxProFrame", "Inside radius"),
    ("MaxProFrame", "Corners"),
    ("MaxProFrame", "Open corner"),
    ("MaxProFrame", "Where the closed frame stays open: the bar starts there, at the first piece"),
    ("MaxProFrame", "Inside radius of each folded corner:"),
    ("MaxProFrame", "Notch"),
    ("MaxProFrame", "Gap between the notch flanks and around the key, half on each side"),
    ("MaxProFrame", "Clearance"),
    ("MaxProFrame", "Interlocking key"),
    (
        "MaxProFrame",
        "Diameter of the key, a half circle on the miter line; Default: a quarter of the tube depth across the bent "
        "wall",
    ),
    ("MaxProFrame", "Key diameter"),
    ("MaxProFrame", "Preview"),
    ("MaxProFrame", "Update automatically"),
    ("MaxProFrame", "Default"),
    ("MaxProFrame", "{} (copy in the document)"),
    ("MaxProFrame", "{}: {:g} mm walls, inside radius {:g} mm, K-factor {:g}"),
    ("MaxProFrame", "Between {} and {}"),
    ("MaxProFrame", "Bar radius"),
    ("MaxProFrame", "{} to {}"),
    ("MaxProFrame", "Add a bend configuration: press Manage configurations."),
    ("MaxProFrame", "Pending changes"),
    ("MaxProFrame", "Preview updated"),
    ("MaxProFrame", "No preview"),
    ("MaxProFrame", "Bend Configurations"),
    ("MaxProFrame", "New"),
    ("MaxProFrame", "Delete"),
    ("MaxProFrame", "Where the neutral axis sits in the wall: 0 inside face, 1 outside face"),
    ("MaxProFrame", "Name"),
    ("MaxProFrame", "Material"),
    ("MaxProFrame", "Wall thickness"),
    ("MaxProFrame", "Inside bend radius"),
    ("MaxProFrame", "K-factor"),
    ("MaxProFrame", "Save"),
    ("MaxProFrame", "There is already a configuration called {}."),
    ("MaxProFrame", "Delete the bend configuration {}? The bars made with it keep their copy."),
    ("MaxProFrame", "The configuration name must not be empty."),
    ("MaxProFrame", "The material must not be empty."),
    ("MaxProFrame", "The wall thickness must be greater than 0 mm."),
    ("MaxProFrame", "The inside bend radius must be at least the wall thickness ({} mm)."),
    ("MaxProFrame", "The K-factor must be between 0 and 1."),
    ("MaxProFrame", 'Bend configuration "{}" does not exist.'),
    ("MaxProFrame", "'configurations' must be a list."),
    ("MaxProFrame", "Bend configurations file '{}' has version {}; this MaxProFrame reads version {}."),
    ("MaxProFrame", "each configuration must be an object."),
    ("MaxProFrame", "Corrupt bend configurations file '{}': {}"),
    ("MaxProFrame", "Folded Miters"),
    ("MaxProFrame_FoldedBar", "Folded Bar"),
    (
        "MaxProFrame_FoldedBar",
        "<b>Folded Bar</b><br><br>Click two or more tube profiles (or pieces made from them) that meet end to end, "
        "the first one where the bar starts: their corners fold, with a V notch, a key and a relief cut by the laser "
        "and the outer wall bent. A closed frame stays open at one corner. Double-click the bar to edit it.",
    ),
    ("MaxProFrame_UnfoldBar", "Unfold Bar"),
    (
        "MaxProFrame_UnfoldBar",
        "<b>Unfold Bar</b><br><br>Select a Folded Bar: its straight bar with every cut is made from X = 0 along X, to "
        "export with File > Export (STEP, IGES, BREP) for a tube laser.",
    ),
    ("MaxProFrame_BendConfigurations", "Bend Configurations"),
    (
        "MaxProFrame_BendConfigurations",
        "<b>Bend Configurations</b><br><br>Add, edit and delete the saved bend configurations of folded bars: "
        "material, wall thickness, inside bend radius and K-factor.",
    ),
)


def _live_messages(name):
    """(context, source) -> translation type of the messages a catalog still uses."""
    messages = {}
    for context in ET.parse(os.path.join(TRANSLATIONSPATH, name)).getroot().iter("context"):
        for message in context.iter("message"):
            kind = message.find("translation").get("type")
            if kind not in ("vanished", "obsolete"):
                messages[(context.findtext("name"), message.findtext("source"))] = kind
    return messages


class TestRussianTranslation(unittest.TestCase):
    def test_the_catalog_ships_compiled(self):
        for name in ("maxproframe_ru.ts", "maxproframe_ru.qm"):
            with self.subTest(file=name):
                self.assertTrue(os.path.isfile(os.path.join(TRANSLATIONSPATH, name)))

    def test_the_catalog_translates_every_current_text(self):
        # The Spanish catalog always holds every current text.
        russian = _live_messages("maxproframe_ru.ts")
        self.assertEqual(set(russian), set(_live_messages("maxproframe_es.ts")))
        # Only the folded miter texts wait for a translator.
        unfinished = sorted(key for key, kind in russian.items() if kind == "unfinished")
        self.assertEqual(unfinished, sorted(FOLDED_MITER_TEXTS))

    def test_freecad_in_russian_translates_messages_and_commands(self):
        self.assertEqual(Gui.supportedLocales().get("Russian"), "ru")
        use_language(self, "Russian", "ru_RU")

        self.assertEqual(translate("frameforge", "Create Profile"), "Создать профиль")
        self.assertEqual(
            translate("frameforge", "Select Edges or set Length to create a profile"),
            "Выберите ребра или задайте длину для создания профиля",
        )
        self.assertEqual(
            translate("MaxProFrame_CreateProfiles", "Create new profiles from edges"),
            "Создать новые профили на основе ребер",
        )

    def test_texts_of_v1_13_0_show_in_russian(self):
        use_language(self, "Russian", "ru_RU")

        self.assertEqual(translate("MaxProFrame_CreatePieceTable", "Piece Table"), "Таблица фрагментов")
        self.assertEqual(translate("MaxProFrame_ProfilePattern", "Profile Pattern"), "Шаблон профиля")
        # These showed in Spanish with FreeCAD in Russian up to v1.13.0.
        self.assertEqual(translate("MaxProFrame_ResetIDs", "Reset IDs"), "Сбросить идентификаторы")
        self.assertEqual(translate("frameforge", "IDs cleared: {}."), "Идентификаторы очищены: {}.")

    def test_folded_miter_texts_show_in_english_until_translated(self):
        use_language(self, "Russian", "ru_RU")

        self.assertEqual(translate("MaxProFrame_FoldedBar", "Folded Bar"), "Folded Bar")
        self.assertEqual(translate("MaxProFrame", "Clearance"), "Clearance")

    def test_obsolete_messages_stay_in_english(self):
        use_language(self, "Russian", "ru_RU")

        # "Count" left the frameforge context after v1.11.1: its old translation is kept as vanished.
        self.assertEqual(translate("frameforge", "Count"), "Count")
        # The Profile Pattern panel shows its references on Change buttons since v1.13.0.
        self.assertEqual(translate("frameforge", "Piece: {}"), "Piece: {}")


if __name__ == "__main__":
    unittest.main()

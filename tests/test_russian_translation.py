"""The Russian catalog loads when FreeCAD runs in Russian."""

import os
import unittest

import FreeCADGui as Gui
from miter_helpers import use_language

from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate


class TestRussianTranslation(unittest.TestCase):
    def test_the_catalog_ships_compiled(self):
        for name in ("maxproframe_ru.ts", "maxproframe_ru.qm"):
            with self.subTest(file=name):
                self.assertTrue(os.path.isfile(os.path.join(TRANSLATIONSPATH, name)))

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

    def test_obsolete_and_untranslated_messages_stay_in_english(self):
        use_language(self, "Russian", "ru_RU")

        # "Count" left the frameforge context after v1.11.1: its old translation is kept as vanished.
        self.assertEqual(translate("frameforge", "Count"), "Count")
        # Piece Table came after v1.11.1 and waits for a translator.
        self.assertEqual(translate("frameforge", "Piece Table"), "Piece Table")


if __name__ == "__main__":
    unittest.main()

"""The Russian catalog loads when FreeCAD runs in Russian."""

import os
import unittest
import xml.etree.ElementTree as ET

import FreeCADGui as Gui
from miter_helpers import use_language

from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate


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
        self.assertEqual([key for key, kind in russian.items() if kind == "unfinished"], [])

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

    def test_obsolete_messages_stay_in_english(self):
        use_language(self, "Russian", "ru_RU")

        # "Count" left the frameforge context after v1.11.1: its old translation is kept as vanished.
        self.assertEqual(translate("frameforge", "Count"), "Count")
        # The Profile Pattern panel shows its references on Change buttons since v1.13.0.
        self.assertEqual(translate("frameforge", "Piece: {}"), "Piece: {}")


if __name__ == "__main__":
    unittest.main()

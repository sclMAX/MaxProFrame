"""The Russian catalog loads when FreeCAD runs in Russian."""

import os
import unittest
import xml.etree.ElementTree as ET

import FreeCADGui as Gui
from miter_helpers import use_language

from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate

# Texts added after the folded miter draft (Interlock, extending a Folded Bar): listed unfinished in the Russian
# catalog for its translator.
PENDING_TEXTS = (
    # odd/tasks/joint-tabs.md, T3: the Interlock command.
    ("MaxProFrame_Interlock", "Interlock"),
    (
        "MaxProFrame_Interlock",
        "<b>Interlock</b><br><br>Click the inner wall faces of the two tubes at a folded corner of a Folded Bar: "
        "fingers cut by the laser at the inner vertex of the corner locate one tube on the other. Set their count, "
        "width, tip and clearance in the panel. Double-click the Interlock to edit it.",
    ),
    # odd/tasks/joint-tabs.md, T4: the Interlock panel, its refusals and its properties.
    ("MaxProFrame", "The interlock of the corner between {} and {} needs at least 2 fingers."),
    ("MaxProFrame", "The fingers of the corner between {} and {} do not fit: make them fewer or narrower."),
    ("MaxProFrame", "The finger tips of the corner between {} and {} must be between 0 and {max:g} mm."),
    ("MaxProFrame", "The interlock between {} and {} is not on a folded corner of {}."),
    ("MaxProFrame", "The corner between {} and {} has two interlocks: {} and {}."),
    ("MaxProFrame", "Click the inner walls of the two tubes at a folded corner of a Folded Bar."),
    ("MaxProFrame", "Click the inner wall of the other tube at that corner."),
    ("MaxProFrame", "Click the inner wall of {}: its face on the inside of the folded corner."),
    ("MaxProFrame", "{} is not a Folded Bar: click the inner walls of two tubes of a Folded Bar."),
    ("MaxProFrame", "Click both faces on the same Folded Bar."),
    (
        "MaxProFrame",
        "{} and {} meet at the open corner of {}, which does not fold: click the inner walls at a folded corner.",
    ),
    ("MaxProFrame", "{} and {} do not meet at a folded corner of {}: click the inner walls of two tubes that do."),
    ("MaxProFrame", "The corner between {} and {} has an interlock already: double-click {} to edit it."),
    ("MaxProFrame", "Interlock"),
    ("MaxProFrame", "Corner: {} → {}"),
    ("MaxProFrame", "Fingers"),
    ("MaxProFrame", "Kind"),
    ("MaxProFrame", "Shape of the interlock: Fingers, at the inner vertex of a folded corner"),
    ("MaxProFrame", "Count"),
    ("MaxProFrame", "Number of fingers, at least 2; the tube before the corner owns the first one"),
    ("MaxProFrame", "Finger width"),
    ("MaxProFrame", "Even"),
    (
        "MaxProFrame",
        "Width of every finger but the two outermost, centered; Even: the fingers split the tube evenly",
    ),
    ("MaxProFrame", "Tip"),
    ("MaxProFrame", "Square"),
    ("MaxProFrame", "Chamfer"),
    ("MaxProFrame", "Round"),
    ("MaxProFrame", "Corners of each finger tip: Square, Chamfer or Round, to lead it in"),
    ("MaxProFrame", "Tip size"),
    ("MaxProFrame", "Chamfer leg or radius of the finger tip corners, in the inner wall plane"),
    ("MaxProFrame", "Depth"),
    (
        "MaxProFrame",
        "Depth of the finger band across the bent wall; Automatic: the step depth of a Stepped joint",
    ),
    ("MaxProFrame", "Gap between every pair of mating finger faces, half on each side"),
    ("MaxProFrame", "Flip"),
    ("MaxProFrame", "Swap the tubes: the tube after the corner owns the first finger"),
    # Apply and continue in the Interlock panel.
    (
        "MaxProFrame",
        "Create this interlock in its own Undo step and keep the panel open: click the inner walls at the next "
        "folded corner, with the same settings.",
    ),
    ("App::Property", "Profile of one of the two tubes the interlock joins"),
    ("App::Property", "Profile of the other tube the interlock joins"),
    ("App::Property", "Shape of the interlock: Fingers, at the inner vertex of a folded corner"),
    ("App::Property", "Number of fingers, at least 2; the first tube owns the first finger"),
    (
        "App::Property",
        "Width of every finger but the two outermost, centered; 0: the fingers split the tube evenly",
    ),
    ("App::Property", "Corners of each finger tip: Square, Chamfer or Round, to lead it in"),
    ("App::Property", "Chamfer leg or radius of the finger tip corners, in the inner wall plane"),
    (
        "App::Property",
        "Depth of the finger band across the bent wall; 0: automatic, the step depth of a Stepped joint",
    ),
    ("App::Property", "Gap between every pair of mating finger faces, half on each side"),
    ("App::Property", "Swap the tubes: the second one owns the first finger"),
    ("App::Property", "Interlock objects on the corners of the bar"),
    # odd/tasks/extend-folded-bar.md, T3: the extend notices.
    ("MaxProFrame", "{} meets neither end of the bar."),
    ("MaxProFrame", "{} is folded by {}: a tube folds into one bar only."),
    ("MaxProFrame", "{} is another Folded Bar: a tube folds into one bar only."),
    ("MaxProFrame", "{} is a closed frame: it takes no more tubes."),
    # The submenus of the one MaxProFrame menu.
    ("frameforge", "Profiles and Cuts"),
    ("frameforge", "Output"),
    ("frameforge", "Utilities"),
    ("frameforge", "Profiles Group"),
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
        # Only the texts added after the folded miter draft wait for a translator.
        unfinished = sorted(key for key, kind in russian.items() if kind == "unfinished")
        self.assertEqual(unfinished, sorted(PENDING_TEXTS))

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

    def test_folded_miter_texts_show_in_russian(self):
        use_language(self, "Russian", "ru_RU")

        # These showed in English with FreeCAD in Russian up to the draft for the translator.
        self.assertEqual(translate("MaxProFrame_FoldedBar", "Folded Bar"), "Гнутая заготовка")
        self.assertEqual(translate("MaxProFrame", "Clearance"), "Зазор")
        self.assertEqual(translate("MaxProFrame", "Stepped"), "Ступенчатое соединение")
        self.assertEqual(
            translate("MaxProFrame", "The K-factor of the corner between {} and {} must be between 0 and 1."),
            "K-фактор угла между {} и {} должен быть в пределах от 0 до 1.",
        )
        self.assertEqual(
            translate("frameforge", "Click a face of the folded bar."), "Щелкните по грани гнутой заготовки."
        )

    def test_obsolete_messages_stay_in_english(self):
        use_language(self, "Russian", "ru_RU")

        # "Count" left the frameforge context after v1.11.1: its old translation is kept as vanished.
        self.assertEqual(translate("frameforge", "Count"), "Count")
        # The Profile Pattern panel shows its references on Change buttons since v1.13.0.
        self.assertEqual(translate("frameforge", "Piece: {}"), "Piece: {}")


if __name__ == "__main__":
    unittest.main()

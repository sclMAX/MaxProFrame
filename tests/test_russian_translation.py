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
        "<b>Interlock</b><br><br>Click two faces. The inner wall faces of the two tubes at a folded corner of a "
        "Folded Bar, or at an End Miter corner of two tubes cut against each other with Miter Ends: fingers cut by "
        "the laser at the inner vertex of the corner locate one tube on the other. A wall of a crossbar and the face "
        "of the rail it butts against (a T joint): tabs on the crossbar end go through slots cut in the rail. Set "
        "their count, width, tip and clearance in the panel. Double-click the Interlock to edit it.",
    ),
    # odd/tasks/joint-tabs.md, T4: the Interlock panel, its refusals and its properties.
    ("MaxProFrame", "The interlock of the corner between {} and {} needs at least 2 fingers."),
    ("MaxProFrame", "The fingers of the corner between {} and {} do not fit: make them fewer or narrower."),
    ("MaxProFrame", "The finger tips of the corner between {} and {} must be between 0 and {max:g} mm."),
    ("MaxProFrame", "The interlock between {} and {} is not on a folded corner of {}."),
    ("MaxProFrame", "The corner between {} and {} has two interlocks: {} and {}."),
    (
        "MaxProFrame",
        "Click the inner walls of the two tubes at a folded corner of a Folded Bar or at an End Miter corner for "
        "fingers, or a wall of a crossbar and the face of the rail it butts against for tabs.",
    ),
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
    (
        "MaxProFrame",
        "Shape of the interlock: Fingers, at the inner vertex of a folded corner or of an End Miter corner; Tabs, "
        "on the end of a crossbar through slots in the rail at a T joint",
    ),
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
        "Create this interlock in its own Undo step and keep the panel open: click the two faces of the next one, "
        "with the same settings.",
    ),
    ("App::Property", "Profile of one of the two tubes the interlock joins"),
    ("App::Property", "Profile of the other tube the interlock joins"),
    (
        "App::Property",
        "Shape of the interlock: Fingers, at the inner vertex of a folded corner or of an End Miter corner; Tabs, "
        "on the end of a crossbar through slots in the rail at a T joint",
    ),
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
    # odd/tasks/t-joint-tabs.md: the Tabs Interlock at a T joint, its panel, refusals and properties.
    (
        "MaxProFrame",
        "Click the other face of the T joint: the face of the rail the crossbar butts against, or the wall of the "
        "crossbar that carries the tabs.",
    ),
    ("MaxProFrame", "T joint"),
    ("MaxProFrame", "T joint: {} → {}"),
    ("MaxProFrame", "Tabs"),
    ("MaxProFrame", "Tab width"),
    ("MaxProFrame", "Length"),
    ("MaxProFrame", "Number of tabs, at least 1, across the flat part of the crossbar wall"),
    (
        "MaxProFrame",
        "Width of every tab, with equal gaps between them and at both ends; Even: the tabs and the gaps split the "
        "flat part of the wall evenly",
    ),
    ("MaxProFrame", "Corners of each tab tip: Square, Chamfer or Round, to lead it into its slot"),
    ("MaxProFrame", "Chamfer leg or radius of the tab tip corners, in the crossbar wall plane"),
    (
        "MaxProFrame",
        "How far the tabs go across the rail wall, along its normal; Automatic: the rail wall thickness, flush "
        "with its inside face",
    ),
    ("MaxProFrame", "Gap around each tab in its slot, half on each side"),
    ("MaxProFrame", "There is no T joint between {} and {}: pick a flat face of each tube."),
    (
        "MaxProFrame",
        "Both faces are on {}: click a wall of the crossbar and the face of the rail it butts against.",
    ),
    ("MaxProFrame", "There is no T joint between {} and {}: {crossbar} does not end on the face of {rail}."),
    ("MaxProFrame", "There is no T joint between {} and {}: {crossbar} runs along the face of {rail}."),
    ("MaxProFrame", "There is no T joint between {} and {}: the face of {crossbar} is not a wall along it."),
    ("MaxProFrame", "The tabs of the T joint between {} and {} need two tubes: {} is a {} profile."),
    ("MaxProFrame", "The interlock of the T joint between {} and {} needs at least 1 tab."),
    ("MaxProFrame", "The tab length of the T joint between {} and {} must be 0 (automatic) or more."),
    ("MaxProFrame", "The tabs of the T joint between {} and {} do not fit: make them fewer or narrower."),
    ("MaxProFrame", "The tab tips of the T joint between {} and {} must be between 0 and {max:g} mm."),
    (
        "MaxProFrame",
        "The slots of the T joint between {} and {} do not fall on the flat part of the face of {rail}.",
    ),
    ("MaxProFrame", "The T joint between {} and {} already has tabs on that face: {}."),
    (
        "MaxProFrame",
        "The T joint between {} and {} is at a folded corner of {}: the tabs go on a free end of a Folded Bar.",
    ),
    (
        "MaxProFrame",
        "The T joint between {} and {} is at the open corner of {}: the tabs go on a free end of a Folded Bar.",
    ),
    ("MaxProFrame", "The interlock {} lost the face of {} it was made on."),
    (
        "App::Property",
        "How far the tabs go across the rail wall, along its normal; 0: automatic, the rail wall thickness",
    ),
    ("App::Property", "Crossbar piece and face that carry the tabs"),
    ("App::Property", "Rail piece and face the slots go through"),
    ("App::Property", "The Tabs Interlock this piece adds its tabs or slots for"),
    # odd/tasks/miter-fingers.md: Fingers at an End Miter corner, their panel, refusals and properties.
    (
        "MaxProFrame",
        "Click the inner wall of the other tube at the End Miter corner for fingers, or the other face of the T joint "
        "for tabs.",
    ),
    ("MaxProFrame", "Number of fingers, at least 2; the tube of the first face clicked owns the first one"),
    ("MaxProFrame", "Depth of the finger band across the inner walls; Automatic: the step depth of a Stepped joint"),
    ("MaxProFrame", "Swap the tubes: the tube of the second face clicked owns the first finger"),
    ("MaxProFrame", "The faces of {} and {} are not the inner walls of an End Miter corner between them."),
    ("MaxProFrame", "{} and {} are not the same size along their corner: their fingers cannot match."),
    ("MaxProFrame", "The finger depth of the corner between {} and {} must be between {min:g} and {max:g} mm."),
    ("MaxProFrame", "The fingers of the corner between {} and {} do not fit at this angle: make the depth smaller."),
    (
        "MaxProFrame",
        "The fingers of the corner between {} and {} do not reach across the miter gap: make the gap smaller or the "
        "depth larger.",
    ),
    ("MaxProFrame", "Both faces are on {}: click the inner wall of each tube of the End Miter corner."),
    ("MaxProFrame", "The fingers of the corner between {} and {} need two tubes: {} is a {} profile."),
    (
        "MaxProFrame",
        "The fingers of the corner between {} and {} need an End Miter of each tube against the other: make them "
        "with Miter Ends.",
    ),
    (
        "MaxProFrame",
        "The fingers of the corner between {} and {} need an End Miter of {} against {}: make it with Miter Ends.",
    ),
    ("MaxProFrame", "The End Miters of {} and {} have different gaps: give them the same Gap."),
    ("MaxProFrame", "The corner between {} and {} already has fingers: {}."),
    (
        "MaxProFrame",
        "The End Miter corner between {} and {} is at a folded corner of {}: the fingers go on a free end of a "
        "Folded Bar.",
    ),
    (
        "MaxProFrame",
        "The End Miter corner between {} and {} is at the open corner of {}: the fingers go on a free end of a "
        "Folded Bar.",
    ),
    ("App::Property", "Fingers at the inner vertex of an End Miter corner between two tubes"),
    ("App::Property", "Piece and inner wall of the first tube, which owns the first finger"),
    ("App::Property", "Piece and inner wall of the second tube"),
    ("App::Property", "The Interlock of the End Miter corner this piece adds its fingers for"),
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

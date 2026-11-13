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
    ("MaxProFrame", "The outer radius of the corner between {} and {} must be between {min:g} and {max:g} mm."),
    ("MaxProFrame", "The K-factor of the corner between {} and {} must be between 0 and 1."),
    (
        "MaxProFrame",
        "The key does not fit in the notch between {} and {} with this radius: make the radius smaller or turn the "
        "key off.",
    ),
    ("MaxProFrame", "The corner between {} and {} has no Folded Corner object."),
    ("MaxProFrame", "The key does not fit in the notch between {} and {}: make it smaller."),
    ("MaxProFrame", "{} is too short for the radius of its corners."),
    (
        "MaxProFrame",
        "{}: its developed length ({:.1f} mm) is longer than the stock length of the cut list ({:.1f} mm).\n",
    ),
    ("MaxProFrame", "{} does not fold into one solid: change its bend settings."),
    ("MaxProFrame", "{} does not unfold into one solid: change its bend settings."),
    ("MaxProFrame", "Folded Bar"),
    ("MaxProFrame", "Corners"),
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
    ("MaxProFrame", "Pending changes"),
    ("MaxProFrame", "Preview updated"),
    ("MaxProFrame", "No preview"),
    ("MaxProFrame", "K-factor"),
    ("MaxProFrame", "Tube"),
    ("MaxProFrame", "Material and wall thickness of the tubes, from their profile"),
    (
        "MaxProFrame",
        "Corners from the start of the bar: click, Ctrl+click or Shift+click to select the ones to edit",
    ),
    ("MaxProFrame", "Remove"),
    (
        "MaxProFrame",
        "Open bar: take off the end tube of the first or last corner selected. Closed frame: open the frame at the "
        "selected corner.",
    ),
    ("MaxProFrame", "Corner"),
    ("MaxProFrame", "Radius seen outside the bend: the inside radius is it less the wall thickness"),
    ("MaxProFrame", "Outer radius"),
    ("MaxProFrame", "Automatic"),
    (
        "MaxProFrame",
        "Where the neutral axis sits in the wall, 0 < K <= 1; Automatic: from DIN 6935, by the inside radius and the "
        "wall thickness",
    ),
    ("MaxProFrame", "Open · {} → {}"),
    ("MaxProFrame", "key"),
    ("MaxProFrame", "no key"),
    ("MaxProFrame", "{} · {} → {} · R {} · {} · clearance {}"),
    ("MaxProFrame", "Click the tube where the bar starts."),
    ("MaxProFrame", "Click the next tube, after {}."),
    ("MaxProFrame", "Tubes picked: {}"),
    ("MaxProFrame", "Folded Miters"),
    ("App::Property", "Profile of one of the two tubes meeting at the corner"),
    ("App::Property", "Profile of the other tube meeting at the corner"),
    ("App::Property", "Where a closed frame stays open: the bar starts and ends here, unfolded"),
    ("App::Property", "Radius seen outside the bend; the inside radius is it less the wall thickness"),
    ("App::Property", "Where the neutral axis sits in the wall: 0 < K <= 1; 0: automatic, from DIN 6935"),
    ("App::Property", "Gap between the notch flanks and around the key, half on each side"),
    ("App::Property", "Interlocking key in the notch"),
    (
        "App::Property",
        "Diameter of the key, a half circle on the miter line; 0: a quarter of the tube depth across the bent wall",
    ),
    ("App::Property", "Tube pieces folded into the bar, in chain order from its start"),
    (
        "App::Property",
        "Folded Corner objects of the bar in chain order from its start, then the open corner of a closed frame",
    ),
    ("App::Property", "Length of the unfolded bar: the length to cut"),
    ("App::Property", "The folded bar this is the straight bar of"),
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
    # odd/tasks/folded-bar-tools.md: the tools that work on a Folded Bar.
    ("MaxProFrame", "Click a straight part of the folded bar."),
    (
        "MaxProFrame",
        "{} does not fold into a valid solid: check the cuts on its tubes (a hole or cutout touching an edge or "
        "another cut).",
    ),
    ("frameforge", "{} cannot be cut at its folded corner with {}."),
    ("frameforge", "Click a planar face of a profile, a trimmed profile, a cutout or a folded bar."),
    (
        "frameforge",
        "Select the piece to repeat: click a profile, a trimmed profile, a cutout, a drill hole or a folded bar.",
    ),
    (
        "MaxProFrame_DrillHole",
        "<b>Drill Hole</b><br><br>Click a planar face of a profile, a trimmed profile, a cutout or a folded bar, then "
        "one of its nine circles to measure from: a corner, the middle of an edge or the center. Round holes are "
        "drilled at the offsets from that point: one, or a pattern on both sides of it along and across the profile, "
        "with a diameter and a depth.",
    ),
    (
        "MaxProFrame_ProfilePattern",
        "<b>Profile Pattern</b><br><br>Select a profile, a trimmed profile, a cutout, a drill hole or a folded bar and "
        "click a straight edge for the direction: the copies are Links placed by count and pitch (in the edge's "
        "sense, inverted or symmetric) or between two faces with equal gaps. A change to the piece shows on every "
        "copy; the BOM counts them with its ID. Double-click the pattern to edit it.",
    ),
    # odd/tasks/stepped-corners.md: the joint of each Folded Corner.
    ("MaxProFrame", "Joint"),
    ("MaxProFrame", "Miter"),
    ("MaxProFrame", "Stepped"),
    (
        "MaxProFrame",
        "How the inner wall is cut: Miter, at half the bend angle (a bevel cut); Stepped, an interlock of straight "
        "cuts only, for any tube laser",
    ),
    ("MaxProFrame", "Step depth"),
    (
        "MaxProFrame",
        "Depth of the step of a Stepped joint across the bent wall; Automatic: the larger of the wall thickness and "
        "the outer corner radius of the tube",
    ),
    ("MaxProFrame", "Flip step"),
    ("MaxProFrame", "Swap the tubes of a Stepped joint: the other one covers the step"),
    ("MaxProFrame", "{} · stepped"),
    ("MaxProFrame", "The step depth of the corner between {} and {} must be between {min:g} and {max:g} mm."),
    (
        "MaxProFrame",
        "The step of the corner between {} and {} does not fit at this angle: make the step depth smaller.",
    ),
    (
        "App::Property",
        "How the inner wall is cut: Miter, at half the bend angle (a bevel cut); Stepped, an interlock of straight "
        "cuts only",
    ),
    (
        "App::Property",
        "Depth of the step of a Stepped joint across the bent wall; 0: automatic, the larger of the wall thickness "
        "and the outer corner radius of the tube",
    ),
    ("App::Property", "Swap the tubes of a Stepped joint: the other one covers the step"),
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

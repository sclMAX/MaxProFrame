"""Task panels loaded from a .ui file keep what they show when FreeCAD delivers a LanguageChange.

FreeCAD posts LanguageChange to its windows when a language is applied (Preferences, or a switch made before a panel
opened and delivered late). A form loaded with ``Gui.PySideUic.loadUi`` then puts back the English texts of its .ui
file over the translated and runtime texts the panel set.
"""

import unittest

import FreeCAD as App
from miter_helpers import deliver_language_change, use_language
from PySide import QtWidgets

from freecad.maxproframe.create_bom_tool import CreateBOMTaskPanel
from freecad.maxproframe.create_end_miter_tool import EndMiterTaskPanel
from freecad.maxproframe.create_extruded_cutout_tool import CutoutTaskPanel
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.populate_ids_tool import PopulateIDsTaskPanel


def shown(form):
    """Every text the form shows: its title, labels, buttons, check boxes and group titles, by widget."""
    texts = {"window title": form.windowTitle()}
    for kind, read in (
        (QtWidgets.QLabel, "text"),
        (QtWidgets.QAbstractButton, "text"),
        (QtWidgets.QGroupBox, "title"),
    ):
        for index, widget in enumerate(form.findChildren(kind)):
            texts[f"{kind.__name__} {widget.objectName() or index}"] = getattr(widget, read)()
    return texts


class PanelLanguageChangeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.doc = App.newDocument("PanelLanguageChange")
        self.addCleanup(App.closeDocument, self.doc.Name)
        App.setActiveDocument(self.doc.Name)
        use_language(self, "Spanish", "es_ES")
        deliver_language_change()

    def assertKeepsItsTexts(self, make_panel, title):
        panel = make_panel()
        self.addCleanup(getattr(panel, "clean", lambda: None))
        forms = panel.form if isinstance(panel.form, list) else [panel.form]
        before = [shown(form) for form in forms]
        self.assertEqual(title, before[0]["window title"])

        use_language(self, "Spanish", "es_ES")
        deliver_language_change()

        self.assertEqual(before, [shown(form) for form in forms])

    def test_end_miter(self):
        self.assertKeepsItsTexts(EndMiterTaskPanel, "Ingletes")

    def test_cutout(self):
        self.assertKeepsItsTexts(CutoutTaskPanel, "Calado")

    def test_populate_ids(self):
        self.assertKeepsItsTexts(PopulateIDsTaskPanel, "Asignar IDs")

    def test_bom(self):
        self.assertKeepsItsTexts(CreateBOMTaskPanel, "Crear lista de materiales")

    def test_create_profile(self):
        self.assertKeepsItsTexts(CreateProfileTaskPanel, "Crear perfiles")


if __name__ == "__main__":
    unittest.main()

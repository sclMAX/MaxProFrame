"""The MaxProFrame toolbar buttons show Spanish menu text and tool tips when FreeCAD runs in Spanish."""

import unittest

import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets

from freecad.maxproframe import (  # noqa: F401  (importing registers the commands)
    create_bom_tool,
    create_edit_balloons_tool,
    create_end_miter_tool,
    create_extend_cut_tool,
    create_extruded_cutout_tool,
    create_link,
    create_profiles_tool,
    create_trimmed_profiles_tool,
    library_manager_dialog,
    parametric_line,
    populate_ids_tool,
    utilities,
)
from freecad.maxproframe.InitGui import MaxProFrame

# command name -> (English menu text, Spanish menu text, Spanish tool tip fragment)
EXPECTED = {
    "MaxProFrame_ParametricLine": (
        "Create a Parametric Line",
        "Crear línea paramétrica",
        "Seleccioná dos vértices y ejecutá este comando.",
    ),
    "MaxProFrame_CreateProfiles": (
        "Create Profile",
        "Crear perfil",
        "Crea perfiles nuevos a partir de aristas",
    ),
    "MaxProFrame_ManageProfileLibraries": (
        "Manage Profile Libraries",
        "Gestionar Bibliotecas de Perfiles",
        "Crear, editar y gestionar bibliotecas y dimensiones de perfiles personalizados",
    ),
    "MaxProFrame_TrimProfiles": (
        "Trim Profile",
        "Recortar perfil",
        "Seleccioná un perfil y luego caras de otro perfil.",
    ),
    "MaxProFrame_ExtendCut": (
        "Extend / Cut",
        "Extender / cortar",
        "Seleccioná una cara o un perfil destino y luego los perfiles a extender o cortar hasta él.",
    ),
    "MaxProFrame_EndMiter": (
        "Create Miter Ends",
        "Crear ingletes",
        "Hacé clic en dos o más perfiles para unir en inglete las esquinas que forman.",
    ),
    "MaxProFrame_AddExtrudeCutout": (
        "Extruded Cutout",
        "Corte extruido",
        "Seleccioná un croquis cerrado para el corte extruido.",
    ),
    "MaxProFrame_Link": (
        "Attached Link",
        "Enlace anclado",
        "Crea un enlace con anclaje",
    ),
    "MaxProFrame_PopulateIDs": (
        "Populate IDs",
        "Asignar IDs",
        "Asignar IDs a los objetos MaxProFrame seleccionados",
    ),
    "MaxProFrame_ResetIDs": (
        "Reset IDs",
        "Restablecer IDs",
        "Restablecer los IDs de los objetos MaxProFrame seleccionados",
    ),
    "MaxProFrame_CreateBalloons": (
        "Create Balloons",
        "Crear globos",
        "Crear globos automáticamente para los perfiles y enlaces seleccionados",
    ),
    "MaxProFrame_RefreshBalloons": (
        "Refresh Balloons",
        "Actualizar globos",
        "Actualizar los globos seleccionados",
    ),
    "MaxProFrame_CreateBOM": (
        "Create BOM",
        "Crear lista de materiales",
        "Seleccioná fusiones o perfiles.",
    ),
    "MaxProFrame_RecomputeFrameForgeObjects": (
        "Recursively recompute all profiles and related MaxProFrame objects",
        "Recalcular recursivamente todos los perfiles y objetos MaxProFrame relacionados",
        "Recalcular recursivamente todos los perfiles y objetos MaxProFrame relacionados",
    ),
    "MaxProFrame_ExportTechDraw": (
        "Export all TechDraw Pages as PDF",
        "Exportar todas las páginas TechDraw a PDF",
        "Exportar todas las páginas TechDraw a PDF",
    ),
}


def toolbar_commands():
    """Every MaxProFrame-owned command placed on a workbench toolbar."""
    toolboxes = (
        MaxProFrame.toolbox_drawing
        + MaxProFrame.toolbox_maxproframe
        + MaxProFrame.toolbox_group
        + MaxProFrame.toolbox_part
        + MaxProFrame.toolbox_output
        + MaxProFrame.toolbox_utilities
    )
    return [name for name in toolboxes if name.startswith("MaxProFrame_")]


def action(name):
    # A language switch reaches the actions through a posted LanguageChange event.
    QtWidgets.QApplication.processEvents()
    command = Gui.Command.get(name)
    actions = command.getAction()
    return actions[0]


class TestToolbarTranslations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        # Toolbar actions only exist once the workbench has built its toolbars.
        if "MaxProFrame" not in Gui.listWorkbenches():
            Gui.addWorkbench(MaxProFrame())
        previous = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        Gui.activateWorkbench("MaxProFrame")
        if previous and previous != "MaxProFrame":
            cls.addClassCleanup(Gui.activateWorkbench, previous)

    def test_every_toolbar_command_has_a_translation(self):
        self.assertEqual(sorted(toolbar_commands()), sorted(EXPECTED))

    def test_toolbar_buttons_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        for name, (_, menu_text, tool_tip) in EXPECTED.items():
            with self.subTest(command=name):
                button = action(name)
                self.assertEqual(button.text(), menu_text)
                self.assertIn(tool_tip, button.toolTip())

    def test_toolbar_buttons_are_spanish_in_argentina(self):
        use_language(self, "Spanish (Argentina)", "es_AR")
        self.assertEqual(action("MaxProFrame_ParametricLine").text(), "Crear línea paramétrica")
        self.assertEqual(action("MaxProFrame_CreateBOM").text(), "Crear lista de materiales")

    def test_toolbar_buttons_stay_english_in_english(self):
        use_language(self, "English", "en_US")
        for name, (menu_text, _, _) in EXPECTED.items():
            with self.subTest(command=name):
                self.assertEqual(action(name).text(), menu_text)

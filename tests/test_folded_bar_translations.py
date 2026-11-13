"""The Folded Bar panel shows Spanish text when FreeCAD runs in Spanish.

odd/tasks/folded-miter.md, T7, with the corner list of odd/tasks/folded-corners.md, T4. The texts are in the
MaxProFrame context of the Spanish catalog; the mixed state is Create Profile's ("Mixed values" of frameforge).
"""

import unittest

import FreeCADGui as Gui
from miter_helpers import use_language
from PySide import QtWidgets
from test_folded_bar_panel import FoldedPanelFixture

from freecad.maxproframe.ff_tools import translate


def field_label(group, field):
    """Text of the label of ``field`` in the form layout of ``group``."""
    return group.layout().labelForField(field).text()


class TestFoldedBarPanelSpanish(FoldedPanelFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")

    def test_the_panel_speaks_spanish(self):
        panel = self.run_command(*self.frame())

        form = panel.form
        self.assertEqual("Barra plegada", form.windowTitle())
        self.assertEqual("Esquinas", form.groupBox_corners.title())
        self.assertEqual("Tubo", field_label(form.groupBox_corners, form.label_tube))
        self.assertEqual("Steel · 2 mm", form.label_tube.text())
        self.assertEqual("Material y espesor de pared de los tubos, tomados de su perfil", form.label_tube.toolTip())
        self.assertEqual(
            "Esquinas desde el inicio de la barra: hacé clic, Ctrl+clic o Mayús+clic para seleccionar las que vas a "
            "editar",
            form.corner_list.toolTip(),
        )
        self.assertEqual(
            [
                "1 · Profile → Profile001 · R 10 mm · llave · holgura 0.5 mm",
                "2 · Profile001 → Profile002 · R 10 mm · llave · holgura 0.5 mm",
                "3 · Profile002 → Profile003 · R 10 mm · llave · holgura 0.5 mm",
                "Abierta · Profile003 → Profile",
            ],
            self.rows(panel),
        )
        self.assertEqual("Quitar", form.button_remove.text())
        self.assertEqual(
            "Barra abierta: quita el tubo del extremo de la primera o la última esquina seleccionada. Marco cerrado: "
            "abre el marco en la esquina seleccionada.",
            form.button_remove.toolTip(),
        )
        corner = form.groupBox_corner
        self.assertEqual("Esquina", corner.title())
        self.assertEqual("Radio exterior", field_label(corner, form.spin_outer_radius))
        self.assertEqual(
            "Radio que se ve por fuera del plegado: el radio interior es este menos el espesor de pared",
            form.spin_outer_radius.toolTip(),
        )
        self.assertEqual("Holgura", field_label(corner, form.spin_clearance))
        self.assertEqual(
            "Separación entre los flancos de la muesca y alrededor de la llave, la mitad de cada lado",
            form.spin_clearance.toolTip(),
        )
        self.assertEqual("Llave de encastre", form.cb_key.text())
        self.assertEqual("Diámetro de la llave", field_label(corner, form.spin_key_diameter))
        self.assertEqual("Predeterminado", form.spin_key_diameter.specialValueText())
        self.assertEqual("Factor K", field_label(corner, form.spin_k_factor))
        self.assertEqual("Automático", form.spin_k_factor.specialValueText())
        self.assertEqual(
            "Dónde está la fibra neutra en la pared, 0 < K <= 1; Automático: según DIN 6935, por el radio interior y "
            "el espesor de pared",
            form.spin_k_factor.toolTip(),
        )
        self.assertEqual("Previsualización", form.groupBox_preview.title())
        self.assertEqual("Actualizar automáticamente", form.cb_auto_update.text())
        self.assertEqual("Previsualización actualizada", form.status_label.text())

    def test_the_hints_of_the_list_are_spanish(self):
        bottom, _, top, _ = self.frame()
        panel = self.run_command()
        self.assertEqual(["Hacé clic en el tubo donde empieza la barra."], self.rows(panel))
        Gui.Selection.addSelection(self.doc.Name, bottom.Name, "Face1")
        self.events()
        self.assertEqual(["Hacé clic en el tubo siguiente, después de Profile."], self.rows(panel))
        self.close_dialog()

        panel = self.run_command(bottom, top)

        self.assertEqual(["Tubos elegidos: Profile, Profile002"], self.rows(panel))

    def test_mixed_values_and_no_key_are_spanish(self):
        _, bar = self.three_corner_bar()
        panel = self.edit(bar)

        self.pick(panel, 0, 1)

        form = panel.form
        self.assertEqual("1 · Profile → Profile001 · R 6 mm · sin llave · holgura 0.2 mm", self.rows(panel)[0])
        self.assertEqual("Llave de encastre — Varios", form.cb_key.text())
        labels = [label.text() for label in form.spin_outer_radius.findChildren(QtWidgets.QLabel)]
        self.assertIn("Varios", labels)

    def test_the_reasons_not_to_fold_are_spanish(self):
        bottom, right, top, left = self.frame()

        panel = self.run_command(bottom, top)
        self.assertRefused(
            panel, "Los perfiles seleccionados no forman una sola cadena: Profile no se une con ninguno de los demás."
        )
        self.close_dialog()

        panel = self.run_command(bottom, right, top, left)
        self.pick(panel, 0, 1, 2)
        panel.form.spin_outer_radius.setValue(3.0)
        self.assertRefused(
            panel, "El radio exterior de la esquina entre Profile y Profile001 tiene que estar entre 4 y 161.8 mm."
        )
        # S23
        panel.form.cb_key.setChecked(False)
        panel.form.spin_outer_radius.setValue(132.0)
        self.assertRefused(panel, "Profile001 es demasiado corto para el radio de sus esquinas.")

    def test_the_folded_corner_property_tooltips_are_spanish(self):
        # odd/tasks/folded-corners.md, T5: the property editor of a Folded Corner speaks Spanish.
        self.assertEqual(
            "Radio que se ve por fuera del plegado; el radio interior es este menos el espesor de pared",
            translate("App::Property", "Radius seen outside the bend; the inside radius is it less the wall thickness"),
        )
        self.assertEqual(
            "Dónde está la fibra neutra en la pared: 0 < K <= 1; 0: automático, según DIN 6935",
            translate(
                "App::Property", "Where the neutral axis sits in the wall: 0 < K <= 1; 0: automatic, from DIN 6935"
            ),
        )
        self.assertEqual(
            "Longitud de la barra desplegada: la longitud a cortar",
            translate("App::Property", "Length of the unfolded bar: the length to cut"),
        )

    def test_the_command_tooltip_says_to_click_the_tubes_in_spanish(self):
        # S22: the panel opens at once and takes the tubes clicked.
        tooltip = translate(
            "MaxProFrame_FoldedBar",
            "<b>Folded Bar</b><br><br>Click two or more tube profiles (or pieces made from them) that meet end to end, "
            "the first one where the bar starts: their corners fold, with a V notch, a key and a relief cut by the "
            "laser and the outer wall bent. A closed frame stays open at one corner. Double-click the bar to edit it.",
        )

        self.assertEqual(
            "<b>Barra plegada</b><br><br>Hacé clic en dos o más perfiles de tubo (o piezas hechas con ellos) que se "
            "unan extremo con extremo, primero en aquel donde empieza la barra: sus esquinas se pliegan, con una "
            "muesca en V, una llave y un alivio cortados con láser y la pared exterior doblada. Un marco cerrado "
            "queda abierto en una esquina. Doble clic en la barra para editarla.",
            tooltip,
        )


class TestFoldedBarToolMessagesSpanish(unittest.TestCase):
    def test_the_folded_bar_tool_messages_are_spanish(self):
        # odd/tasks/folded-bar-tools.md, S5 and T5: the refusals of the tools on a Folded Bar speak Spanish.
        use_language(self, "Spanish", "es_ES")

        self.assertEqual(
            "Hacé clic en una parte recta de la barra plegada.",
            translate("MaxProFrame", "Click a straight part of the folded bar."),
        )
        self.assertEqual(
            "Profile001 no se puede cortar en su esquina plegada con Profile002.",
            translate("frameforge", "{} cannot be cut at its folded corner with {}.").format(
                "Profile001", "Profile002"
            ),
        )
        # T9: a bar whose cuts break the fold says why.
        self.assertEqual(
            "FoldedBar no se pliega en un sólido válido: revisá los cortes de sus tubos (un agujero o calado que toca "
            "un borde u otro corte).",
            translate(
                "MaxProFrame",
                "{} does not fold into a valid solid: check the cuts on its tubes (a hole or cutout touching an edge "
                "or another cut).",
            ).format("FoldedBar"),
        )


if __name__ == "__main__":
    unittest.main()

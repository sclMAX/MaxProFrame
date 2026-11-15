"""The Interlock panel and its messages show Spanish text when FreeCAD runs in Spanish.

odd/tasks/joint-tabs.md, T4 (S7). The panel texts and the refusals are in the MaxProFrame context of the Spanish
catalog, the property tooltips in App::Property; the stored values (Kind, Tip) stay in English.
"""

import unittest

from miter_helpers import use_language
from test_interlock_panel import BOTTOM_INNER, RIGHT_INNER, TOP_INNER, InterlockPanelFixture
from test_unfolded_geometry import PLAIN

from freecad.maxproframe.ff_tools import translate


def field_label(group, field):
    """Text of the label of ``field`` in the form layout of ``group``."""
    return group.layout().labelForField(field).text()


def items(combo):
    """(text, data) of every item of ``combo``."""
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


class TestInterlockPanelSpanish(InterlockPanelFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")

    def test_the_panel_speaks_spanish(self):
        _, bar = self.make_bar(**PLAIN)

        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))

        form = panel.form
        self.assertEqual("Encastre", form.windowTitle())
        self.assertEqual("Esquina", form.groupBox_corner.title())
        self.assertEqual("Esquina: Profile → Profile001", form.label_corner.text())
        settings = form.groupBox_settings
        self.assertEqual("Aletas", settings.title())
        self.assertEqual("Tipo", field_label(settings, form.combo_kind))
        # odd/tasks/t-joint-tabs.md, T4 added the Tabs kind and changed the tooltip; T5 translates them.
        self.assertEqual([("Aletas", "Fingers"), ("Tabs", "Tabs")], items(form.combo_kind))
        self.assertEqual(
            "Shape of the interlock: Fingers, at the inner vertex of a folded corner; Tabs, on the end of a crossbar "
            "through slots in the rail at a T joint",
            form.combo_kind.toolTip(),
        )
        self.assertEqual("Cantidad", field_label(settings, form.spin_count))
        self.assertEqual(
            "Cantidad de aletas, al menos 2; la primera es del tubo anterior a la esquina", form.spin_count.toolTip()
        )
        self.assertEqual("Ancho de aleta", field_label(settings, form.spin_finger_width))
        self.assertEqual("Uniforme", form.spin_finger_width.specialValueText())
        self.assertEqual(
            "Ancho de cada aleta menos las dos de los extremos, centradas; Uniforme: las aletas dividen el tubo en "
            "partes iguales",
            form.spin_finger_width.toolTip(),
        )
        self.assertEqual("Punta", field_label(settings, form.combo_tip))
        # The stored values stay in English, whatever the language.
        self.assertEqual([("Recta", "Square"), ("Biselada", "Chamfer"), ("Redondeada", "Round")], items(form.combo_tip))
        self.assertEqual("Tamaño de punta", field_label(settings, form.spin_tip_size))
        self.assertEqual("Profundidad", field_label(settings, form.spin_depth))
        self.assertEqual("Automático", form.spin_depth.specialValueText())
        self.assertEqual("Holgura", field_label(settings, form.spin_clearance))
        self.assertEqual(
            "Separación entre cada par de caras enfrentadas de las aletas, la mitad de cada lado",
            form.spin_clearance.toolTip(),
        )
        self.assertEqual("Invertir", form.cb_flip.text())
        self.assertEqual(
            "Intercambia los tubos: la primera aleta es del tubo posterior a la esquina", form.cb_flip.toolTip()
        )
        self.assertAccepts(panel)
        # The Interlock made in Spanish documents its properties in Spanish.
        (made,) = self.interlocks()
        self.assertEqual(
            "Cantidad de aletas, al menos 2; la primera aleta es del primer tubo",
            made.getDocumentationOfProperty("Count"),
        )

    def test_the_picking_hints_and_refusals_are_spanish(self):
        _, bar = self.make_bar(**PLAIN)
        panel = self.run_command()
        # odd/tasks/t-joint-tabs.md, T4 changed this hint to name both kinds; T5 translates it.
        self.assertRefused(
            panel,
            "Click the inner walls of the two tubes at a folded corner of a Folded Bar for fingers, or a wall of a "
            "crossbar and the face of the rail it butts against for tabs.",
        )

        self.click(bar, BOTTOM_INNER)
        self.assertRefused(panel, "Hacé clic en la pared interior del otro tubo en esa esquina.")

        self.click(bar, TOP_INNER)
        self.assertRefused(
            panel,
            f"Profile y Profile002 no se unen en una esquina plegada de {bar.Label}: hacé clic en las paredes "
            "interiores de dos tubos que sí se unan.",
        )
        self.assertEqual([], self.interlocks())

    def test_a_refusal_of_the_bar_is_spanish(self):
        _, bar = self.make_bar(**PLAIN)
        panel = self.run_command((bar, BOTTOM_INNER), (bar, RIGHT_INNER))
        form = panel.form

        form.spin_count.setValue(1)
        self.events()
        self.assertRefused(panel, "El encastre de la esquina entre Profile y Profile001 necesita al menos 2 aletas.")

        form.spin_count.setValue(3)
        form.combo_tip.setCurrentIndex(form.combo_tip.findData("Chamfer"))
        form.spin_tip_size.setValue(20.0)
        self.events()
        self.assertRefused(
            panel,
            "El tamaño de la punta de las aletas de la esquina entre Profile y Profile001 tiene que estar entre 0 y "
            "8 mm.",
        )


class TestInterlockTextsSpanish(unittest.TestCase):
    def setUp(self):
        use_language(self, "Spanish", "es_ES")

    def test_the_interlock_property_tooltips_are_spanish(self):
        self.assertEqual(
            "Perfil de uno de los dos tubos que une el encastre",
            translate("App::Property", "Profile of one of the two tubes the interlock joins"),
        )
        self.assertEqual(
            "Profundidad de la franja de aletas, perpendicular a la pared doblada; 0: automático, la profundidad del "
            "escalón de una unión escalonada",
            translate(
                "App::Property",
                "Depth of the finger band across the bent wall; 0: automatic, the step depth of a Stepped joint",
            ),
        )
        self.assertEqual(
            "Objetos Encastre en las esquinas de la barra",
            translate("App::Property", "Interlock objects on the corners of the bar"),
        )

    def test_the_refusals_of_the_bar_are_spanish(self):
        self.assertEqual(
            "Las aletas de la esquina entre Profile y Profile001 no entran: poné menos o hacelas más angostas.",
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} do not fit: make them fewer or narrower.",
            ).format("Profile", "Profile001"),
        )
        self.assertEqual(
            "El encastre entre Profile y Profile002 no está en una esquina plegada de FoldedBar.",
            translate("MaxProFrame", "The interlock between {} and {} is not on a folded corner of {}.").format(
                "Profile", "Profile002", "FoldedBar"
            ),
        )


if __name__ == "__main__":
    unittest.main()

"""The Interlock panel and its messages show Spanish text when FreeCAD runs in Spanish.

odd/tasks/joint-tabs.md, T4 (S7), odd/tasks/t-joint-tabs.md, T5 (the Tabs kind) and odd/tasks/miter-fingers.md, T5
(Fingers at an End Miter corner). The panel texts and the refusals are in the MaxProFrame context of the Spanish
catalog, the property tooltips in App::Property; the stored values (Kind, Tip) stay in English.
"""

import unittest

from miter_helpers import use_language
from test_interlock_panel import BOTTOM_INNER, RIGHT_INNER, TOP_INNER, InterlockPanelFixture
from test_miter_finger_panel import A_EDGE, A_INNER, B_EDGE, B_INNER, MiterPanelFixture
from test_tab_interlock_panel import CROSS_EAST, CROSS_WEST, RAIL_TOP, TabPanelFixture
from test_unfolded_geometry import PLAIN

from freecad.maxproframe.ff_tools import translate

# The texts that name the End Miter corner too (odd/tasks/miter-fingers.md, T5).
KIND_TIP = (
    "Forma del encastre: Aletas, en el vértice interior de una esquina plegada o de una esquina en inglete; Lengüetas, "
    "en el extremo de un travesaño a través de ranuras en el larguero en una unión en T"
)
HINT_NONE = (
    "Hacé clic en las paredes interiores de los dos tubos en una esquina plegada de una barra plegada o en una esquina "
    "en inglete para aletas, o en una pared de un travesaño y en la cara del larguero contra la que apoya para "
    "lengüetas."
)


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
        self.assertEqual([("Aletas", "Fingers"), ("Lengüetas", "Tabs")], items(form.combo_kind))
        self.assertEqual(
            KIND_TIP,
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
        self.assertRefused(panel, HINT_NONE)

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


class TestTabsPanelSpanish(TabPanelFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")

    def test_the_tabs_fields_speak_spanish(self):
        rail, _, trim = self.straight_t()

        panel = self.run_command((trim, CROSS_EAST), (rail, RAIL_TOP))

        form = panel.form
        self.assertEqual("Unión en T", form.groupBox_corner.title())
        self.assertEqual("Unión en T: Crossbar → Rail", form.label_corner.text())
        settings = form.groupBox_settings
        self.assertEqual("Lengüetas", settings.title())
        self.assertEqual("Tabs", form.combo_kind.currentData())
        self.assertEqual("Lengüetas", form.combo_kind.currentText())
        self.assertEqual("Ancho de lengüeta", field_label(settings, form.spin_finger_width))
        self.assertEqual(
            "Cantidad de lengüetas, al menos 1, a lo ancho de la parte plana de la pared del travesaño",
            form.spin_count.toolTip(),
        )
        self.assertEqual("Longitud", field_label(settings, form.spin_length))
        self.assertEqual("Automático", form.spin_length.specialValueText())
        self.assertEqual("Automático", form.spin_length.text())
        self.assertEqual(
            "Cuánto atraviesan las lengüetas la pared del larguero, a lo largo de su normal; Automático: el espesor de "
            "pared del larguero, al ras de su cara interior",
            form.spin_length.toolTip(),
        )
        self.assertEqual(
            "Separación alrededor de cada lengüeta en su ranura, la mitad de cada lado", form.spin_clearance.toolTip()
        )
        self.assertAccepts(panel)

    def test_the_tabs_hints_and_refusals_are_spanish(self):
        _, _, trim = self.straight_t()
        panel = self.run_command()

        self.click(trim, CROSS_EAST)
        self.assertRefused(
            panel,
            "Hacé clic en la otra cara de la unión en T: la cara del larguero contra la que apoya el travesaño, o la "
            "pared del travesaño que lleva las lengüetas.",
        )

        self.click(trim, CROSS_WEST)
        self.assertRefused(
            panel,
            "Las dos caras están en Crossbar: hacé clic en una pared del travesaño y en la cara del larguero contra la "
            "que apoya.",
        )
        self.assertEqual([], self.interlocks())


class TestMiterPanelSpanish(MiterPanelFixture):
    def setUp(self):
        super().setUp()
        use_language(self, "Spanish", "es_ES")

    def test_the_miter_corner_hints_and_fields_speak_spanish(self):
        _, _, miter_a, miter_b = self.straight_corner()
        panel = self.run_command()
        self.assertRefused(panel, HINT_NONE)

        self.click(miter_a, A_INNER)
        self.assertRefused(
            panel,
            "Hacé clic en la pared interior del otro tubo en la esquina en inglete para aletas, o en la otra cara de la "
            "unión en T para lengüetas.",
        )
        self.click(miter_b, B_INNER)

        form = panel.form
        self.assertEqual("Esquina: TubeA → TubeB", form.label_corner.text())
        self.assertEqual(KIND_TIP, form.combo_kind.toolTip())
        self.assertEqual(
            "Cantidad de aletas, al menos 2; la primera es del tubo de la primera cara en la que hiciste clic",
            form.spin_count.toolTip(),
        )
        self.assertEqual(
            "Profundidad de la franja de aletas, perpendicular a las paredes interiores; Automático: la profundidad "
            "del escalón de una unión escalonada",
            form.spin_depth.toolTip(),
        )
        self.assertEqual(
            "Intercambia los tubos: la primera aleta es del tubo de la segunda cara en la que hiciste clic",
            form.cb_flip.toolTip(),
        )
        self.assertAccepts(panel)
        # The Interlock made in Spanish documents its properties in Spanish.
        (made,) = self.interlocks()
        self.assertEqual(KIND_TIP, made.getDocumentationOfProperty("Kind"))
        self.assertEqual(
            "Pieza y pared interior del primer tubo, del que es la primera aleta",
            made.getDocumentationOfProperty("FaceA"),
        )

    def test_a_corner_without_end_miters_is_refused_in_spanish(self):
        a = self.loose(A_EDGE, "TubeA")
        b = self.loose(B_EDGE, "TubeB")
        self.doc.recompute()
        panel = self.run_command((a, A_INNER), (b, B_INNER))

        self.assertRefused(
            panel,
            "Las aletas de la esquina entre TubeA y TubeB necesitan un inglete de cada tubo contra el otro: hacelos "
            "con Crear ingletes.",
        )
        self.assertEqual([], self.interlocks())


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

    def test_the_tabs_texts_are_spanish(self):
        self.assertEqual(
            "Pieza y cara del travesaño que llevan las lengüetas",
            translate("App::Property", "Crossbar piece and face that carry the tabs"),
        )
        self.assertEqual(
            "Las lengüetas de la unión en T entre Crossbar y Rail no entran: poné menos o hacelas más angostas.",
            translate(
                "MaxProFrame", "The tabs of the T joint between {} and {} do not fit: make them fewer or narrower."
            ).format("Crossbar", "Rail"),
        )
        self.assertEqual(
            "La unión en T entre Crossbar y Rail está en una esquina plegada de FoldedBar: las lengüetas van en un "
            "extremo libre de una barra plegada.",
            translate(
                "MaxProFrame",
                "The T joint between {} and {} is at a folded corner of {}: the tabs go on a free end of a Folded Bar.",
            ).format("Crossbar", "Rail", "FoldedBar"),
        )

    def test_the_miter_corner_texts_are_spanish(self):
        self.assertEqual(
            "Las aletas de la esquina entre TubeA y TubeB necesitan un inglete de TubeB contra TubeA: hacelo con Crear "
            "ingletes.",
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} need an End Miter of {} against {}: make it with Miter "
                "Ends.",
            ).format("TubeA", "TubeB", "TubeB", "TubeA"),
        )
        self.assertEqual(
            "Los ingletes de TubeA y TubeB tienen separaciones distintas: dales la misma Separación.",
            translate("MaxProFrame", "The End Miters of {} and {} have different gaps: give them the same Gap.").format(
                "TubeA", "TubeB"
            ),
        )
        self.assertEqual(
            "Las aletas de la esquina entre TubeA y TubeB no cruzan la separación del inglete: achicá la separación o "
            "agrandá la profundidad.",
            translate(
                "MaxProFrame",
                "The fingers of the corner between {} and {} do not reach across the miter gap: make the gap smaller or "
                "the depth larger.",
            ).format("TubeA", "TubeB"),
        )
        self.assertEqual(
            "El encastre de la esquina en inglete para el que esta pieza agrega sus aletas",
            translate("App::Property", "The Interlock of the End Miter corner this piece adds its fingers for"),
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

"""The Folded Bar panel and the Bend Configurations dialog show Spanish text when FreeCAD runs in Spanish.

odd/tasks/folded-miter.md, T7. The texts are in the MaxProFrame context of the Spanish catalog.
"""

import shutil
import tempfile
import unittest

from miter_helpers import use_language
from PySide import QtWidgets
from test_folded_bar_panel import STEEL, FoldedPanelFixture

from freecad.maxproframe.bend_config import BendConfiguration, BendConfigurationStore, set_last_used_configuration
from freecad.maxproframe.bend_config_dialog import BendConfigurationsDialog

ALU = BendConfiguration("Alu 3", "Aluminium", 3.0, 4.0, 0.33)


def field_label(group, field):
    """Text of the label of ``field`` in the form layout of ``group``."""
    return group.layout().labelForField(field).text()


class TestFoldedBarPanelSpanish(FoldedPanelFixture):
    def test_the_panel_speaks_spanish(self):
        use_language(self, "Spanish", "es_ES")
        set_last_used_configuration(STEEL.name)

        panel = self.run_command(*self.frame())

        form = panel.form
        self.assertEqual("Barra plegada", form.windowTitle())
        self.assertEqual("Piezas de tubo, desde el inicio de la barra", form.groupBox_members.title())
        self.assertEqual("Plegado", form.groupBox_bend.title())
        self.assertEqual("Gestionar configuraciones", form.button_manage.text())
        self.assertEqual("Radio interior", field_label(form.groupBox_bend, form.spin_radius))
        self.assertEqual("Esquinas", form.groupBox_corners.title())
        self.assertEqual("Esquina abierta", form.label_open_corner.text())
        self.assertEqual("Entre Profile y Profile003", form.combo_open_corner.itemText(0))
        self.assertEqual("Radio interior de cada esquina plegada:", form.label_corner_radii.text())
        self.assertEqual("Radio de la barra", panel.corner_spins()[0].specialValueText())
        self.assertEqual("Muesca", form.groupBox_notch.title())
        self.assertEqual("Holgura", field_label(form.groupBox_notch, form.spin_clearance))
        self.assertEqual("Llave de encastre", form.cb_key.text())
        self.assertEqual("Diámetro de la llave", field_label(form.groupBox_notch, form.spin_key_diameter))
        self.assertEqual("Predeterminado", form.spin_key_diameter.specialValueText())
        self.assertEqual("Ancho del cuello", field_label(form.groupBox_notch, form.spin_neck_width))
        self.assertEqual("Alivio junto a la pared doblada", form.cb_relief.text())
        self.assertEqual("Radio del alivio", field_label(form.groupBox_notch, form.spin_relief_radius))
        self.assertEqual("Previsualización", form.groupBox_preview.title())
        self.assertEqual("Actualizar automáticamente", form.cb_auto_update.text())
        self.assertEqual("Previsualización actualizada", form.status_label.text())

    def test_the_reasons_not_to_fold_are_spanish(self):
        use_language(self, "Spanish", "es_ES")
        set_last_used_configuration(STEEL.name)
        bottom, right, top, left = self.frame()

        panel = self.run_command(bottom, top)
        self.assertRefused(
            panel, "Los perfiles seleccionados no forman una sola cadena: Profile no se une con ninguno de los demás."
        )
        self.close_dialog()

        panel = self.run_command(bottom, right, top, left)
        panel.form.spin_radius.setValue(1.0)
        self.assertRefused(panel, "El radio interior de plegado tiene que estar entre 2 y 33.5 mm.")

    def test_without_a_configuration_the_panel_says_how_to_add_one_in_spanish(self):
        use_language(self, "Spanish", "es_ES")
        for configuration in self.store.configurations():
            self.store.delete(configuration.name)

        panel = self.run_command(*self.frame())

        self.assertRefused(panel, "Agregá una configuración de plegado: presioná Gestionar configuraciones.")


class TestBendConfigurationsDialogSpanish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        use_language(self, "Spanish", "es_ES")
        folder = tempfile.mkdtemp(prefix="mpf_bend_dialog_es_")
        self.addCleanup(shutil.rmtree, folder, True)
        self.store = BendConfigurationStore(folder)
        self.store.save(ALU)
        self.dialog = BendConfigurationsDialog(store=self.store)
        self.addCleanup(self.dialog.deleteLater)

    def test_the_dialog_speaks_spanish(self):
        dialog = self.dialog
        self.assertEqual("Configuraciones de plegado", dialog.windowTitle())
        self.assertEqual("Nueva", dialog.button_new.text())
        self.assertEqual("Eliminar", dialog.button_delete.text())
        self.assertEqual("Guardar", dialog.button_save.text())
        labels = {label.text() for label in dialog.findChildren(QtWidgets.QLabel)}
        for text in ("Nombre", "Material", "Espesor de pared", "Radio interior de plegado", "Factor K"):
            with self.subTest(label=text):
                self.assertIn(text, labels)
        self.assertEqual(
            "Dónde está la fibra neutra en la pared: 0 cara interior, 1 cara exterior", dialog.spin_k_factor.toolTip()
        )

    def test_the_store_messages_are_spanish(self):
        dialog = self.dialog
        for name, radius, message in (
            ("", 4.0, "El nombre de la configuración no puede estar vacío."),
            ("Alu r2", 2.0, "El radio interior de plegado tiene que ser al menos el espesor de pared (3 mm)."),
        ):
            with self.subTest(message=message):
                dialog.new()
                dialog.edit_name.setText(name)
                dialog.spin_radius.setValue(radius)
                self.assertFalse(dialog.save())
                self.assertEqual(message, dialog.message_label.text())
        dialog.new()
        dialog.edit_name.setText(ALU.name)
        dialog.spin_radius.setValue(ALU.inside_radius)
        self.assertFalse(dialog.save())
        self.assertEqual("Ya hay una configuración llamada Alu 3.", dialog.message_label.text())
        self.assertEqual([ALU], self.store.configurations())


if __name__ == "__main__":
    unittest.main()

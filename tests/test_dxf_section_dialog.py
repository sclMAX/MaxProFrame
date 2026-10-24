"""Explicit unit confirmation and review controls, without modal interaction."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide import QtCore, QtWidgets

from freecad.maxproframe.dxf_section_dialog import DXFUnitsDialog


class TestDXFUnitsDialog(unittest.TestCase):
    def test_known_unknown_and_wrong_declared_units_require_confirmation(self):
        for declared, scale in ((4, 1.0), (6, 1000.0), (0, None), (99, None), (None, None)):
            with self.subTest(declared=declared):
                dialog = DXFUnitsDialog({"insunits": declared, "unit_mm": scale})
                self.addCleanup(dialog.close)
                self.assertEqual(dialog.result(), QtWidgets.QDialog.Rejected)
                self.assertIn(str(declared), dialog.lbl_declared.text())
                if scale is None:
                    self.assertIsNone(dialog.confirmed_unit())
                    self.assertFalse(dialog.buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
                dialog.combo_units.setCurrentIndex(dialog.combo_units.findData("mm"))
                self.assertEqual(dialog.confirmed_unit(), "mm")
                self.assertTrue(dialog.buttons.button(QtWidgets.QDialogButtonBox.Ok).isEnabled())
                dialog.buttons.button(QtWidgets.QDialogButtonBox.Ok).click()
                self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)

    def test_all_supported_units_are_selectable_and_cancel_rejects(self):
        dialog = DXFUnitsDialog({"insunits": 0, "unit_mm": None})
        self.addCleanup(dialog.close)
        for unit in ("mm", "cm", "m", "inch", "ft"):
            dialog.combo_units.setCurrentIndex(dialog.combo_units.findData(unit))
            self.assertEqual(dialog.confirmed_unit(), unit)
        dialog.buttons.button(QtWidgets.QDialogButtonBox.Cancel).click()
        self.assertEqual(dialog.result(), QtWidgets.QDialog.Rejected)

    def test_spanish_catalogs_cover_new_dialog_literals(self):
        import ast

        root = Path(__file__).resolve().parents[1] / "freecad/maxproframe"
        sources = set()
        for filename in ("dxf_section_dialog.py", "sketch_section_dialog.py"):
            for node in ast.walk(ast.parse((root / filename).read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "translate":
                    if len(node.args) >= 2 and all(isinstance(arg, ast.Constant) for arg in node.args[:2]):
                        sources.add((node.args[0].value, node.args[1].value))
        for prefix in ("frameforge", "maxproframe"):
            path = root / "resources/translations" / (prefix + "_es.ts")
            entries = {
                (context.findtext("name"), message.findtext("source")): message.findtext("translation")
                for context in ET.parse(path).getroot().findall("context")
                for message in context.findall("message")
            }
            self.assertTrue(sources)
            for key in sources:
                self.assertTrue(entries.get(key), key)
            mixed_case = {"frameforge": "FrameForge", "maxproframe": "MaxProFrame"}[prefix]
            for alias in (prefix, mixed_case):
                for locale in ("es", "es-ES", "es-CO", "es-AR"):
                    translator = QtCore.QTranslator()
                    qm = path.parent / (alias + "_" + locale + ".qm")
                    self.assertTrue(translator.load(str(qm)), str(qm))
                    for context, source in sources:
                        self.assertEqual(translator.translate(context, source), entries[(context, source)], str(qm))

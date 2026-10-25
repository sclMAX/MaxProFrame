"""Spanish coverage for the library dialog, cards and shipped Qt catalogs."""

import ast
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "freecad" / "maxproframe"
TRANSLATIONS = ROOT / "resources" / "translations"


def library_sources():
    """Include literal translations and the dialog's indirect UI labels."""
    # These standard keys are translated indirectly by the family display helper.
    sources = {
        ("frameforge", name)
        for name in (
            "T-Slot",
            "T-Slot 3-Slots",
            "T-Slot 2-Slots",
            "T-Slot 2-Slots Opp",
            "T-Slot 1-Slot",
        )
    }
    for filename in (
        "library_manager_dialog.py",
        "custom_profile_cards.py",
        "dxf_section_dialog.py",
        "sketch_section_dialog.py",
        "custom_profile_editor.py",
    ):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "translate" and len(node.args) >= 2:
                    context, source = node.args[:2]
                    if isinstance(context, ast.Constant) and isinstance(source, ast.Constant):
                        sources.add((context.value, source.value))
                if isinstance(node.func, ast.Attribute) and node.func.attr == "_compact_button":
                    sources.add(("frameforge", ast.literal_eval(node.args[1])))
                for keyword in node.keywords:
                    if keyword.arg == "title" and isinstance(keyword.value, ast.Constant):
                        sources.add(("frameforge", keyword.value.value))
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "TABLE_COLUMNS" for target in node.targets
            ):
                sources.update(("frameforge", label) for _, label in ast.literal_eval(node.value))
    return sources


def catalog(path):
    return {
        (context.findtext("name"), message.findtext("source")): message.findtext("translation")
        for context in ET.parse(path).getroot().findall("context")
        for message in context.findall("message")
        if message.find("translation") is not None
        and message.find("translation").get("type") not in ("unfinished", "obsolete", "vanished")
        and message.findtext("translation")
    }


class TestLibraryTranslationCatalogs(unittest.TestCase):
    def test_spanish_covers_library_labels_tooltips_and_messages(self):
        for prefix in ("frameforge", "maxproframe"):
            with self.subTest(prefix=prefix):
                entries = catalog(TRANSLATIONS / f"{prefix}_es.ts")
                self.assertEqual(sorted(library_sources() - entries.keys()), [])
                for key in library_sources():
                    self.assertEqual(re.findall(r"%[sd]", key[1]), re.findall(r"%[sd]", entries[key]), key)
                self.assertEqual(entries[("frameforge", "Code:")], "Código:")
                self.assertEqual(entries[("frameforge", "Weight:")], "Peso:")

    def test_existing_spanish_labels_and_legacy_catalog_are_preserved(self):
        canonical = catalog(TRANSLATIONS / "maxproframe_es.ts")
        self.assertEqual(canonical, catalog(TRANSLATIONS / "frameforge_es.ts"))
        for source, expected in {
            "Save Changes": "Guardar Cambios",
            "Close": "Cerrar",
            "Height [mm]": "Alto [mm]",
            "Weight [kg/m]": "Peso [kg/m]",
            "Apply": "Aplicar",
            "Create Profile": "Crear perfil",
            "Preview": "Previsualización",
            "No preview": "Sin previsualización",
            "Unapplied changes": "Cambios sin aplicar",
            "Applied": "Cambios aplicados",
            "Apply changes and update preview": "Aplicar cambios y actualizar previsualización",
            "Select Edges or set Length to create a profile": "Seleccione aristas o defina la longitud para crear un perfil",
        }.items():
            self.assertEqual(canonical[("frameforge", source)], expected)

    def test_shipped_qt_catalogs_resolve_spanish_and_preserve_fallback(self):
        try:
            from PySide import QtCore
        except ImportError:
            self.skipTest("Native FreeCAD Qt runtime required")
        entries = catalog(TRANSLATIONS / "maxproframe_es.ts")
        for prefix in ("frameforge", "FrameForge", "maxproframe", "MaxProFrame"):
            for locale in ("es", "es-ES", "es-CO", "es-AR"):
                with self.subTest(prefix=prefix, locale=locale):
                    translator = QtCore.QTranslator()
                    self.assertTrue(translator.load(str(TRANSLATIONS / f"{prefix}_{locale}.qm")))
                    for context, source in library_sources() | {
                        ("frameforge", "Create Profile"),
                        ("frameforge", "Select Edges or set Length to create a profile"),
                    }:
                        self.assertEqual(translator.translate(context, source), entries[(context, source)])
                    self.assertFalse(translator.translate("frameforge", "Untranslated sentinel"))
                    self.assertFalse(translator.translate("unrelated-context", "Save Changes"))


if __name__ == "__main__":
    unittest.main()

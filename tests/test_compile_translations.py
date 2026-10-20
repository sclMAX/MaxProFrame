"""Unit tests for compile_translations scoping and alias generation."""

import os
import shutil
import tempfile
import unittest

from freecad.maxproframe.compile_translations import compile_all_translations, compile_ts

try:
    from PySide import QtCore
    HAS_PYSIDE = True
except ImportError:
    try:
        from PySide6 import QtCore
        HAS_PYSIDE = True
    except ImportError:
        HAS_PYSIDE = False


MINIMAL_FRAMEFORGE_ES_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es" sourcelanguage="en">
<context>
    <name>frameforge</name>
    <message>
        <source>Create Profile</source>
        <translation>Crear perfil</translation>
    </message>
</context>
</TS>
"""

MINIMAL_UNRELATED_ES_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es" sourcelanguage="en">
<context>
    <name>unrelated</name>
    <message>
        <source>Create Profile</source>
        <translation>CORRUPTED_OVERWRITE</translation>
    </message>
</context>
</TS>
"""

MINIMAL_CUSTOM_FR_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="fr" sourcelanguage="en">
<context>
    <name>custom</name>
    <message>
        <source>Hello</source>
        <translation>Bonjour</translation>
    </message>
</context>
</TS>
"""


class TestCompileTranslations(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ff_test_compile_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_known_spanish_catalogs_generate_required_runtime_aliases(self):
        """Recognized project Spanish catalogs generate all 16 runtime and prefix aliases."""
        ts_path = os.path.join(self.test_dir, "frameforge_es.ts")
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(MINIMAL_FRAMEFORGE_ES_TS)

        compiled = compile_all_translations(self.test_dir)

        expected_aliases = {
            f"{stem}_{loc}.qm"
            for stem in ("frameforge", "FrameForge", "maxproframe", "MaxProFrame")
            for loc in ("es", "es-ES", "es-CO", "es-AR")
        }

        created_files = set(os.listdir(self.test_dir)) - {"frameforge_es.ts"}
        self.assertEqual(created_files, expected_aliases)
        self.assertEqual(set(os.path.basename(p) for p in compiled), expected_aliases)

        if HAS_PYSIDE:
            for alias_name in expected_aliases:
                qm_file = os.path.join(self.test_dir, alias_name)
                translator = QtCore.QTranslator()
                self.assertTrue(translator.load(qm_file), f"Failed to load {alias_name}")
                self.assertEqual(
                    translator.translate("frameforge", "Create Profile"),
                    "Crear perfil",
                    f"Wrong translation in {alias_name}",
                )

    def test_unrelated_catalogs_preserve_own_output_without_overwriting_or_aliasing(self):
        """Unrelated Spanish and non-Spanish catalogs only compile to their own single output."""
        ff_ts = os.path.join(self.test_dir, "frameforge_es.ts")
        with open(ff_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_FRAMEFORGE_ES_TS)

        unrelated_ts = os.path.join(self.test_dir, "unrelated_es.ts")
        with open(unrelated_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_UNRELATED_ES_TS)

        fr_ts = os.path.join(self.test_dir, "custom_fr.ts")
        with open(fr_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_CUSTOM_FR_TS)

        compiled = compile_all_translations(self.test_dir)

        # Expected outputs: 16 project aliases for frameforge_es.ts + 1 for unrelated_es.qm + 1 for custom_fr.qm
        expected_project_aliases = {
            f"{stem}_{loc}.qm"
            for stem in ("frameforge", "FrameForge", "maxproframe", "MaxProFrame")
            for loc in ("es", "es-ES", "es-CO", "es-AR")
        }
        all_expected = expected_project_aliases | {"unrelated_es.qm", "custom_fr.qm"}

        created_files = set(os.listdir(self.test_dir)) - {"frameforge_es.ts", "unrelated_es.ts", "custom_fr.ts"}
        self.assertEqual(created_files, all_expected)
        self.assertEqual(set(os.path.basename(p) for p in compiled), all_expected)

        # Ensure unrelated catalogs did NOT generate prefix aliases
        for bad_alias in (
            "unrelated_es-CO.qm",
            "unrelated_es-AR.qm",
            "custom_fr-CO.qm",
            "custom_fr-AR.qm",
            "frameforge_fr.qm",
            "maxproframe_fr.qm",
        ):
            self.assertFalse(
                os.path.exists(os.path.join(self.test_dir, bad_alias)),
                f"Unexpected alias generated: {bad_alias}",
            )

        # Ensure unrelated_es did NOT overwrite project catalog content
        if HAS_PYSIDE:
            translator = QtCore.QTranslator()
            self.assertTrue(translator.load(os.path.join(self.test_dir, "frameforge_es-CO.qm")))
            self.assertEqual(
                translator.translate("frameforge", "Create Profile"),
                "Crear perfil",
                "frameforge_es-CO.qm was corrupted or overwritten by unrelated_es.ts!",
            )


if __name__ == "__main__":
    unittest.main()

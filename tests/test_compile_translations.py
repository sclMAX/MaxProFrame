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


MINIMAL_MAXPROFRAME_ES_TS = """<?xml version="1.0" encoding="utf-8"?>
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


SPANISH_ALIASES = {f"maxproframe_{loc}.qm" for loc in ("es", "es-ES", "es-CO", "es-AR")}


RETIRED_MESSAGES_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="fr" sourcelanguage="en">
<context>
    <name>custom</name>
    <message>
        <source>Hello</source>
        <translation>Bonjour</translation>
    </message>
    <message>
        <source>Count</source>
        <translation type="vanished">Nombre</translation>
    </message>
    <message>
        <source>Width</source>
        <translation type="obsolete">Largeur</translation>
    </message>
    <message>
        <source>Height</source>
        <translation type="unfinished">Hauteur</translation>
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

    def test_spanish_catalog_generates_its_four_runtime_locales(self):
        """maxproframe_es.ts compiles to maxproframe_es.qm and its es-ES, es-CO and es-AR copies, nothing else."""
        ts_path = os.path.join(self.test_dir, "maxproframe_es.ts")
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(MINIMAL_MAXPROFRAME_ES_TS)

        compiled = compile_all_translations(self.test_dir)

        expected_aliases = SPANISH_ALIASES

        created_files = set(os.listdir(self.test_dir)) - {"maxproframe_es.ts"}
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

    def test_a_legacy_frameforge_catalog_is_compiled_alone_without_aliases(self):
        """frameforge_es.ts, from before the rename, is no longer a project catalog: it gets only its own .qm."""
        with open(os.path.join(self.test_dir, "frameforge_es.ts"), "w", encoding="utf-8") as f:
            f.write(MINIMAL_MAXPROFRAME_ES_TS)

        compiled = compile_all_translations(self.test_dir)

        self.assertEqual(set(os.listdir(self.test_dir)), {"frameforge_es.ts", "frameforge_es.qm"})
        self.assertEqual([os.path.basename(p) for p in compiled], ["frameforge_es.qm"])

    @unittest.skipUnless(HAS_PYSIDE, "PySide is required to read the compiled catalog")
    def test_vanished_obsolete_and_unfinished_messages_stay_untranslated(self):
        """As Qt's lrelease: only finished messages of the current sources are compiled."""
        ts_path = os.path.join(self.test_dir, "custom_fr.ts")
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(RETIRED_MESSAGES_TS)
        qm_path = os.path.join(self.test_dir, "custom_fr.qm")
        compile_ts(ts_path, qm_path)
        translator = QtCore.QTranslator()
        self.assertTrue(translator.load(qm_path))
        self.assertEqual(translator.translate("custom", "Hello"), "Bonjour")
        for source in ("Count", "Width", "Height"):
            with self.subTest(source):
                self.assertEqual(translator.translate("custom", source), "")

    def test_unrelated_catalogs_preserve_own_output_without_overwriting_or_aliasing(self):
        """Unrelated Spanish and non-Spanish catalogs only compile to their own single output."""
        ff_ts = os.path.join(self.test_dir, "maxproframe_es.ts")
        with open(ff_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_MAXPROFRAME_ES_TS)

        unrelated_ts = os.path.join(self.test_dir, "unrelated_es.ts")
        with open(unrelated_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_UNRELATED_ES_TS)

        fr_ts = os.path.join(self.test_dir, "custom_fr.ts")
        with open(fr_ts, "w", encoding="utf-8") as f:
            f.write(MINIMAL_CUSTOM_FR_TS)

        compiled = compile_all_translations(self.test_dir)

        # Expected outputs: 4 project aliases for maxproframe_es.ts + 1 for unrelated_es.qm + 1 for custom_fr.qm
        all_expected = SPANISH_ALIASES | {"unrelated_es.qm", "custom_fr.qm"}

        created_files = set(os.listdir(self.test_dir)) - {"maxproframe_es.ts", "unrelated_es.ts", "custom_fr.ts"}
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
            self.assertTrue(translator.load(os.path.join(self.test_dir, "maxproframe_es-CO.qm")))
            self.assertEqual(
                translator.translate("frameforge", "Create Profile"),
                "Crear perfil",
                "maxproframe_es-CO.qm was corrupted or overwritten by unrelated_es.ts!",
            )


if __name__ == "__main__":
    unittest.main()

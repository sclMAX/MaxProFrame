"""Tests for native FreeCAD workbench translation loading and Spanish warning dialogs."""

import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    from freecad.maxproframe.ff_tools import TRANSLATIONSPATH, translate
    HAS_FREECAD_GUI = True
except ImportError:
    HAS_FREECAD_GUI = False
    TRANSLATIONSPATH = None
    translate = None


@unittest.skipUnless(HAS_FREECAD_GUI, "Native FreeCAD Qt GUI runtime required")
class TestWorkbenchTranslationLoading(unittest.TestCase):
    """Verifies that native FreeCAD translation discovery loads catalogs and translates dialogs."""

    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])
        cls.orig_gui_locale = Gui.getLocale() if hasattr(Gui, "getLocale") else "English"
        cls.prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        cls.orig_pref_lang = cls.prefs.GetString("Language", "")

    @classmethod
    def tearDownClass(cls):
        if hasattr(Gui, "setLocale"):
            Gui.setLocale(cls.orig_gui_locale)
        cls.prefs.SetString("Language", cls.orig_pref_lang)
        if hasattr(Gui, "updateLocale"):
            Gui.updateLocale()

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_wb_trans_")
        self.doc_count = 0
        self.created_docs = []
        self.panels = []
        self.msg_stack = ExitStack()

        # Capture dialog messages and avoid modal hang
        self.captured_dialogs = []

        def fake_exec(box_self):
            title = box_self.windowTitle()
            text = box_self.text()
            self.captured_dialogs.append((title, text))
            return QtWidgets.QMessageBox.Ok

        self.msg_stack.enter_context(patch.object(QtWidgets.QMessageBox, "exec_", fake_exec))
        if hasattr(QtGui, "QMessageBox") and QtGui.QMessageBox is not QtWidgets.QMessageBox:
            self.msg_stack.enter_context(patch.object(QtGui.QMessageBox, "exec_", fake_exec))
        self.addCleanup(self.msg_stack.close)

    def tearDown(self):
        for panel in self.panels:
            try:
                panel.clean()
            except Exception:
                pass
            for f in getattr(panel, "form", []):
                try:
                    f.close()
                except Exception:
                    pass
        for doc_name in self.created_docs:
            try:
                App.closeDocument(doc_name)
            except Exception:
                pass
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def _new_doc(self, prefix="TestDoc"):
        self.doc_count += 1
        name = f"{prefix}_{self.doc_count}_{id(self)}"
        doc = App.newDocument(name)
        self.created_docs.append(name)
        return doc

    def test_native_freecad_translation_loading_spanish(self):
        """FreeCAD native catalog loading translates Create Profile strings in Spanish locales."""
        from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel

        Gui.addLanguagePath(TRANSLATIONSPATH)

        for lang in ("Spanish", "Spanish (Argentina)"):
            with self.subTest(language=lang):
                self.prefs.SetString("Language", lang)
                Gui.setLocale(lang)
                Gui.updateLocale()

                self.assertEqual(
                    translate("frameforge", "Create Profile"),
                    "Crear perfil",
                    f"Create Profile title not translated for language '{lang}'",
                )
                self.assertEqual(
                    translate("frameforge", "Select Edges or set Length to create a profile"),
                    "Seleccione aristas o defina la longitud para crear un perfil",
                    f"Warning body not translated for language '{lang}'",
                )

                # Test public GUI panel with no selection / zero length
                doc = self._new_doc("DocSpanish")
                App.setActiveDocument(doc.Name)
                baseline_objects = [o.Name for o in doc.Objects]

                panel = CreateProfileTaskPanel()
                self.panels.append(panel)
                panel.open()
                Gui.Selection.clearSelection()
                if hasattr(panel, "update_selection"):
                    panel.update_selection()
                panel.form_proxy.sb_length.setValue(0.0)

                # Warning on apply()
                self.captured_dialogs.clear()
                result_apply = panel.apply()
                self.assertFalse(result_apply)
                self.assertEqual(
                    self.captured_dialogs,
                    [("Crear perfil", "Seleccione aristas o defina la longitud para crear un perfil")],
                )
                self.assertEqual([o.Name for o in doc.Objects], baseline_objects)

                # Warning on accept()
                self.captured_dialogs.clear()
                result_accept = panel.accept()
                self.assertFalse(result_accept)
                self.assertEqual(
                    self.captured_dialogs,
                    [("Crear perfil", "Seleccione aristas o defina la longitud para crear un perfil")],
                )
                self.assertEqual([o.Name for o in doc.Objects], baseline_objects)

    def test_native_freecad_translation_loading_preserves_english(self):
        """FreeCAD native catalog loading preserves English strings when English is selected."""
        from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel

        Gui.addLanguagePath(TRANSLATIONSPATH)
        self.prefs.SetString("Language", "English")
        Gui.setLocale("English")
        Gui.updateLocale()

        self.assertEqual(translate("frameforge", "Create Profile"), "Create Profile")
        self.assertEqual(
            translate("frameforge", "Select Edges or set Length to create a profile"),
            "Select Edges or set Length to create a profile",
        )

        doc = self._new_doc("DocEnglish")
        App.setActiveDocument(doc.Name)
        baseline_objects = [o.Name for o in doc.Objects]

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.clearSelection()
        if hasattr(panel, "update_selection"):
            panel.update_selection()
        panel.form_proxy.sb_length.setValue(0.0)

        # Warning on apply()
        self.captured_dialogs.clear()
        result_apply = panel.apply()
        self.assertFalse(result_apply)
        self.assertEqual(
            self.captured_dialogs,
            [("Create Profile", "Select Edges or set Length to create a profile")],
        )
        self.assertEqual([o.Name for o in doc.Objects], baseline_objects)

        # Warning on accept()
        self.captured_dialogs.clear()
        result_accept = panel.accept()
        self.assertFalse(result_accept)
        self.assertEqual(
            self.captured_dialogs,
            [("Create Profile", "Select Edges or set Length to create a profile")],
        )
        self.assertEqual([o.Name for o in doc.Objects], baseline_objects)


if __name__ == "__main__":
    unittest.main()

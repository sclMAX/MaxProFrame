import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.ff_tools import translate
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.profile import Profile, ViewProviderProfile
from freecad.maxproframe.section_library import capture_section_sketch


class TestCreateProfileApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_apply_user_")
        self.manager = LibraryManager(user_dir=self.test_user_dir)
        self.doc_count = 0
        self.created_docs = []
        self.panels = []
        self.msg_stack = ExitStack()
        self.msg_stack.enter_context(
            patch.object(QtWidgets.QMessageBox, "exec_", return_value=QtWidgets.QMessageBox.Ok)
        )
        if hasattr(QtGui, "QMessageBox") and QtGui.QMessageBox is not QtWidgets.QMessageBox:
            self.msg_stack.enter_context(patch.object(QtGui.QMessageBox, "exec_", return_value=QtGui.QMessageBox.Ok))
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

    def _create_line_path(self, doc, name="Path", length=100.0):
        p = doc.addObject("Sketcher::SketchObject", name)
        p.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(length, 0, 0)), False)
        p.addConstraint(Sketcher.Constraint("Distance", 0, float(length)))
        p.solve()
        doc.recompute()
        return p

    def _create_test_profile(self, doc, name="ExistingProfile"):
        obj = doc.addObject("Part::FeaturePython", name)
        obj.addExtension("Part::AttachExtensionPython")
        Profile(
            obj,
            init_w=40.0,
            init_h=40.0,
            init_mt=2.0,
            init_ft=0.0,
            init_r1=0.0,
            init_r2=0.0,
            init_len=500.0,
            init_wg=2.0,
            init_unit_price=10.0,
            init_mf=False,
            init_anchor_x=1,
            init_anchor_y=1,
            material="Metal",
            fam="Square Hollow",
            size_name="40x40x2",
            bevels_combined=False,
            catalog_family="Square Hollow",
        )
        if getattr(obj, "ViewObject", None) is not None:
            ViewProviderProfile(obj.ViewObject)
        doc.recompute()
        return obj

    def _get_profiles(self, doc):
        return [
            o
            for o in doc.Objects
            if getattr(getattr(o, "Proxy", None), "Type", None) == "Profile" or hasattr(o, "CustomProfile")
        ]

    # --- S1: Explicit preview ---

    def test_s1_open_panel_does_not_create_preview_geometry(self):
        """S1: Opening Create Profile panel must only load options and not create preview geometry."""
        doc = self._new_doc("DocOpen")
        App.setActiveDocument(doc.Name)
        baseline_objects = set(doc.Objects)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # No geometry should have been created in the document
        current_objects = set(doc.Objects)
        self.assertEqual(current_objects, baseline_objects, "Opening panel must not create document objects.")

    def test_s1_changing_inputs_does_not_create_preview_geometry(self):
        """S1: Changing input fields (combos, spinboxes, checkboxes) must not create preview geometry."""
        doc = self._new_doc("DocInputs")
        App.setActiveDocument(doc.Name)
        baseline_count = len(doc.Objects)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Change length, material, family, size
        panel.form_proxy.sb_length.setValue(250.0)
        panel.form_proxy.sb_width.setValue(60.0)
        panel.form_proxy.sb_height.setValue(60.0)
        panel.form_proxy.combo_rotation.setCurrentIndex(1)

        self.assertEqual(len(doc.Objects), baseline_count + 1, "Setting length must generate live preview geometry.")

    def test_s1_changing_selection_does_not_create_preview_geometry(self):
        """S1: Changing selection in 3D view must generate live preview geometry."""
        doc = self._new_doc("DocSelection")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "Path1", length=150.0)
        baseline_objects = set(doc.Objects)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Select edge
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.addSelection(doc.Name, path, "Edge1", None)

        self.assertEqual(
            len(doc.Objects), len(baseline_objects) + 1, "Changing selection must generate live preview geometry."
        )

    def test_s1_apply_validates_and_creates_preview_without_closing_or_duplicating(self):
        """S1: Apply validates settings and creates/updates preview without closing panel or duplicating profiles."""
        doc = self._new_doc("DocApply")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "Path2", length=200.0)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.update_selection()

        self.assertTrue(hasattr(panel, "apply"), "Panel must provide an apply() method.")
        applied = panel.apply()
        self.assertTrue(applied, "Apply must return True on valid settings.")

        profiles = self._get_profiles(doc)
        self.assertEqual(len(profiles), 1, "Apply must create exactly one preview profile.")
        prof_name = profiles[0].Name

        # Second Apply: must update existing profile without duplicating
        applied_again = panel.apply()
        self.assertTrue(applied_again, "Repeated Apply must succeed.")
        profiles_after = self._get_profiles(doc)
        self.assertEqual(profiles_after[0].Name, prof_name, "Repeated Apply must update the same profile object.")

    # --- S2: Accepted interaction table ---

    def test_s2_no_apply_controls_and_live_preview(self):
        """S2: The panel has no Apply group, button or status; edits update the preview live."""
        doc = self._new_doc("DocState")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "PathState", length=100.0)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        for name in ("groupBox_apply", "btn_apply", "label_apply_status"):
            self.assertNotIn(name, panel.form_proxy.members)
            self.assertIsNone(panel.form[0].findChild(QtCore.QObject, name), name)
        buttons = [button.text() for button in panel.form[0].findChildren(QtWidgets.QPushButton)]
        self.assertNotIn(translate("frameforge", "Apply"), buttons)

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.addSelection(doc.Name, path, "Edge1", None)
        profiles = self._get_profiles(doc)
        self.assertEqual(len(profiles), 1, "Selecting a path must create the preview live.")

        panel.form_proxy.sb_width.setValue(80.0)
        self.assertEqual(self._get_profiles(doc), profiles, "Edits must update the same preview.")
        self.assertEqual(profiles[0].ProfileWidth, 80.0, "Edits must update the preview live.")

    def test_s2_accept_applies_current_values_without_prior_apply(self):
        """S2: Accept applies current form values and confirms even if Apply was never clicked."""
        doc = self._new_doc("DocAcceptNoApply")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "PathAccept", length=300.0)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.update_selection()

        # Call accept without calling apply
        accepted = panel.accept()
        self.assertTrue(accepted, "Accept must return True.")
        doc.recompute()

        profiles = self._get_profiles(doc)
        self.assertEqual(len(profiles), 1, "Accept must create profile even without prior Apply.")
        self.assertTrue(profiles[0].Shape.isValid())

    def test_s2_accept_applies_current_values_after_prior_apply(self):
        """S2: Accept uses modified values if fields are changed after an earlier Apply."""
        doc = self._new_doc("DocAcceptAfterApply")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "PathAfter", length=200.0)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.update_selection()

        # Apply with initial values
        panel.apply()
        profiles = self._get_profiles(doc)
        self.assertEqual(len(profiles), 1)
        prof = profiles[0]
        initial_w = prof.ProfileWidth

        # Change width without hitting Apply again
        new_w = initial_w + 20.0
        panel.form_proxy.sb_width.setValue(new_w)

        # Accept
        panel.accept()
        doc.recompute()

        self.assertEqual(prof.ProfileWidth, new_w, "Accept must commit latest modified values.")

    def test_s2_cancel_restores_pre_session_document_objects(self):
        """S2: Cancel (reject) rolls back preview profiles and restores document state."""
        doc = self._new_doc("DocCancel")
        App.setActiveDocument(doc.Name)
        path = self._create_line_path(doc, "PathCancel", length=150.0)
        baseline_names = set(o.Name for o in doc.Objects)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, path.Name, "Edge1")
        panel.update_selection()
        panel.apply()

        # Preview profile exists
        self.assertEqual(len(self._get_profiles(doc)), 1)

        # Reject/Cancel
        rejected = panel.reject()
        self.assertTrue(rejected)

        final_names = set(o.Name for o in doc.Objects)
        self.assertEqual(final_names, baseline_names, "Reject must restore exact pre-session objects.")

    def test_s2_rejected_apply_on_zero_length_and_no_selection(self):
        """S2: Apply with zero length and no selection must be rejected (returns False, no preview created)."""
        doc = self._new_doc("DocRejectApply")
        App.setActiveDocument(doc.Name)
        baseline_objects = set(doc.Objects)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        Gui.Selection.clearSelection()
        panel.update_selection()
        panel.form_proxy.sb_length.setValue(0.0)

        # Apply with no selection and 0 length
        applied = panel.apply()
        self.assertFalse(applied, "Apply must return False when neither edges nor length are set.")
        self.assertEqual(set(doc.Objects), baseline_objects, "Rejected apply must not create preview geometry.")

    def test_validation_warning_language_and_unchanged_document(self):
        """Both confirmation paths localize the warning without creating objects."""
        from freecad.maxproframe.ff_tools import TRANSLATIONSPATH
        from freecad.maxproframe.library_manager_dialog import ProfileLibraryManagerDialog

        cls = ProfileLibraryManagerDialog
        original_locale = QtCore.QLocale()
        original_translator = getattr(cls, "_translator", None)
        original_installed = getattr(cls, "_translator_installed", False)
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/General")
        orig_fc_lang = prefs.GetString("Language", "")
        orig_fc_locale = Gui.getLocale() if hasattr(Gui, "getLocale") else "English"

        def restore_language():
            if cls._translator is not None:
                self.app.removeTranslator(cls._translator)
            cls._translator = original_translator
            cls._translator_installed = original_installed
            QtCore.QLocale.setDefault(original_locale)
            if hasattr(Gui, "setLocale"):
                Gui.setLocale(orig_fc_locale)
            prefs.SetString("Language", orig_fc_lang)
            if hasattr(Gui, "updateLocale"):
                Gui.updateLocale()
            if original_translator is not None:
                self.app.installTranslator(original_translator)

        self.addCleanup(restore_language)
        for spanish in (False, True):
            if getattr(cls, "_translator", None) is not None:
                self.app.removeTranslator(cls._translator)
            cls._translator = None
            cls._translator_installed = False
            QtCore.QLocale.setDefault(QtCore.QLocale("es_ES" if spanish else "en_US"))
            target_lang = "Spanish" if spanish else "English"
            if hasattr(Gui, "setLocale"):
                Gui.setLocale(target_lang)
            prefs.SetString("Language", target_lang)
            if hasattr(Gui, "updateLocale"):
                Gui.updateLocale()
            translator = QtCore.QTranslator()
            if spanish:
                self.assertTrue(translator.load(os.path.join(TRANSLATIONSPATH, "frameforge_es.qm")))
                self.app.installTranslator(translator)
            try:
                for action in ("accept", "apply"):
                    with self.subTest(spanish=spanish, action=action):
                        doc = self._new_doc("DocWarningLanguage")
                        App.setActiveDocument(doc.Name)
                        panel = CreateProfileTaskPanel()
                        self.panels.append(panel)
                        panel.open()
                        Gui.Selection.clearSelection()
                        panel.update_selection()
                        panel.form_proxy.sb_length.setValue(0.0)
                        baseline_names = [obj.Name for obj in doc.Objects]
                        warnings = []

                        def capture_warning(dialog):
                            warnings.append((dialog.windowTitle(), dialog.text()))
                            return QtWidgets.QMessageBox.Ok

                        with patch.object(QtGui.QMessageBox, "exec_", capture_warning):
                            self.assertFalse(getattr(panel, action)())
                        self.assertEqual(
                            warnings,
                            [
                                (
                                    "Crear perfil" if spanish else "Create Profile",
                                    (
                                        "Seleccione aristas o defina la longitud para crear un perfil"
                                        if spanish
                                        else "Select Edges or set Length to create a profile"
                                    ),
                                )
                            ],
                        )
                        self.assertEqual([obj.Name for obj in doc.Objects], baseline_names)
            finally:
                if spanish:
                    self.app.removeTranslator(translator)
                if cls._translator is not None:
                    self.app.removeTranslator(cls._translator)

    # --- S3: Edit Profile preservation ---

    def test_s3_edit_profile_panel_preserves_live_update_behavior(self):
        """S3: EditProfileTaskPanel preserves live preview updates on field changes and hides Apply button."""
        doc = self._new_doc("DocEditPreserve")
        App.setActiveDocument(doc.Name)
        prof = self._create_test_profile(doc, "ProfileToEdit")
        initial_w = prof.ProfileWidth

        edit_panel = EditProfileTaskPanel(prof)
        self.panels.append(edit_panel)
        edit_panel.open()

        # The shared form no longer has an Apply group or button.
        self.assertNotIn("groupBox_apply", edit_panel.form_proxy.members)
        self.assertNotIn("btn_apply", edit_panel.form_proxy.members)

        # Changing width in edit panel must update profile live (without clicking any Apply)
        edit_panel.form_proxy.sb_width.setValue(initial_w + 30.0)
        self.assertEqual(prof.ProfileWidth, initial_w + 30.0, "EditProfileTaskPanel must update profile live.")

        edit_panel.accept()
        self.assertEqual(prof.ProfileWidth, initial_w + 30.0)


if __name__ == "__main__":
    unittest.main()

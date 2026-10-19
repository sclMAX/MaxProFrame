import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import FreeCAD as App

from freecad.maxproframe import profile as profile_module
from freecad.maxproframe.profile import ViewProviderCustomProfile, ViewProviderProfile

NOTICE = "FrameForge: close the active task dialog before editing a profile.\n"


class TestProfileEditDialogGuard(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DialogGuardTest")
        self.obj = self.doc.addObject("Part::Box", "ExistingProfile")
        self.doc.recompute()
        self.before = self.obj.dumpContent()
        self.object_names = tuple(obj.Name for obj in self.doc.Objects)
        self.control = Mock()
        self.control.activeDialog.return_value = None
        self.panel_factory = Mock()
        self.gui_patch = patch.object(profile_module, "Gui", SimpleNamespace(Control=self.control))
        self.panel_patch = patch("freecad.maxproframe.edit_profile_tool.EditProfileTaskPanel", self.panel_factory)
        self.gui_patch.start()
        self.panel_patch.start()
        self.addCleanup(self.gui_patch.stop)
        self.addCleanup(self.panel_patch.stop)
        self.addCleanup(App.closeDocument, self.doc.Name)

    def provider(self, cls=ViewProviderProfile):
        provider = cls.__new__(cls)
        provider.Object = self.obj
        return provider

    def test_active_dialog_rejects_edit_without_creating_panel_or_changing_document(self):
        active_dialog = object()
        self.control.activeDialog.return_value = active_dialog
        self.control.showDialog.side_effect = RuntimeError("Active task dialog found")
        with patch.object(App.Console, "PrintMessage") as message:
            self.assertIs(self.provider().setEdit(self.obj.ViewObject, 0), False)
            message.assert_called_once_with(NOTICE)
        self.control.activeDialog.assert_called_once_with()
        self.panel_factory.assert_not_called()
        self.control.showDialog.assert_not_called()
        self.control.closeDialog.assert_not_called()
        self.assertIs(self.control.activeDialog.return_value, active_dialog)
        self.assertEqual(self.obj.dumpContent(), self.before)
        self.assertEqual(tuple(obj.Name for obj in self.doc.Objects), self.object_names)

    def test_no_active_dialog_preserves_normal_edit(self):
        with patch.object(App.Console, "PrintMessage") as message:
            self.assertIs(self.provider().setEdit(self.obj.ViewObject, 0), True)
            self.panel_factory.assert_called_once_with(self.obj)
            self.control.showDialog.assert_called_once_with(self.panel_factory.return_value)
            message.assert_not_called()
        self.control.closeDialog.assert_not_called()

    def test_non_edit_mode_remains_ignored(self):
        with patch.object(App.Console, "PrintMessage") as message:
            self.assertIsNone(self.provider().setEdit(self.obj.ViewObject, 1))
            message.assert_not_called()
        self.control.activeDialog.assert_not_called()
        self.panel_factory.assert_not_called()
        self.control.showDialog.assert_not_called()

    def test_unset_edit_closes_profile_panel(self):
        self.assertIs(self.provider().unsetEdit(self.obj.ViewObject, 0), True)
        self.control.closeDialog.assert_called_once_with()

    def test_non_edit_unset_mode_remains_ignored(self):
        self.assertIsNone(self.provider().unsetEdit(self.obj.ViewObject, 1))
        self.control.closeDialog.assert_not_called()


class TestCustomProfileEditDialogGuard(TestProfileEditDialogGuard):
    def provider(self, cls=ViewProviderCustomProfile):
        return super().provider(cls)


if __name__ == "__main__":
    unittest.main()

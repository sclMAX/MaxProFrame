import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import FreeCAD as App
import Part
import Sketcher
from profile_creation_helpers import creation_panel, make_custom_profile


def source_content(snapshot):
    # dumpContent() is a ZIP whose per-entry timestamps reflect serialization
    # time, not source changes. Compare every entry in order, including duplicate
    # names and empty payloads, without interpreting or normalizing its contents.
    with zipfile.ZipFile(io.BytesIO(snapshot)) as archive:
        return tuple((entry.filename, archive.read(entry)) for entry in archive.infolist())


class TestProfileParentGuard(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ProfileParentGuardTest")
        name = self.doc.Name
        self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
        self.path = self.doc.addObject("Sketcher::SketchObject", "Path")
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
        self.path.addConstraint(Sketcher.Constraint("Distance", 0, 100.0))
        self.section = self.doc.addObject("Sketcher::SketchObject", "Section")
        points = [(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)]
        for start, end in zip(points, points[1:]):
            self.section.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), False)
        self.doc.recompute()

    def create(self, custom):
        if custom:
            make_custom_profile(self.path, "Edge1", "Profile", self.section)
        else:
            creation_panel().make_profile(self.path, "Edge1", "Profile")
        profile = self.doc.getObject("Profile")
        self.assertIsNotNone(profile.Proxy)
        self.assertEqual(profile.Family, "Custom Profile" if custom else "Flat Sections")
        self.assertEqual(profile.MapMode, "NormalToEdge")
        support = profile.AttachmentSupport
        if isinstance(support, list):
            self.assertEqual(len(support), 1)
            support = support[0]
        self.assertEqual(support[0], self.path)
        self.assertEqual(tuple(support[1]), ("Edge1",))
        return profile

    def check_parent(self, parent_type, custom):
        parent = self.doc.addObject(parent_type, "Parent") if parent_type else None
        if parent:
            parent.addObject(self.path)
        self.doc.recompute()
        before_path = source_content(self.path.dumpContent())
        before_group = tuple(parent.Group) if parent else ()
        before_objects = tuple(self.doc.Objects)
        with patch.object(App.Console, "PrintMessage") as message:
            profile = self.create(custom)
            if parent_type == "PartDesign::Body":
                message.assert_called_once_with(
                    "FrameForge: parent Parent (PartDesign::Body) does not accept Part::FeaturePython, "
                    "keeping at document root\n"
                )
                self.assertEqual(tuple(parent.Group), before_group)
                self.assertEqual(profile.Parents, [])
            else:
                message.assert_not_called()
                if parent:
                    self.assertIn(profile, parent.Group)
                else:
                    self.assertEqual(profile.Parents, [])
        self.assertEqual(source_content(self.path.dumpContent()), before_path)
        self.assertEqual(tuple(self.doc.Objects), before_objects + (profile,))
        self.doc.recompute()
        self.assertEqual(profile.getTypeIdOfProperty("Target"), "App::PropertyLinkSubGlobal")
        self.assert_parametric_profile(profile, 100)
        self.path.setDatum(0, App.Units.Quantity("150 mm"))
        self.doc.recompute()
        self.assert_parametric_profile(profile, 150)
        with tempfile.TemporaryDirectory(
            prefix=".frameforge-test-", dir=Path(__file__).resolve().parents[1]
        ) as directory:
            filename = str(Path(directory) / "roundtrip.FCStd")
            self.doc.saveAs(filename)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(filename)
            name = self.doc.Name
            self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
            self.path = self.doc.getObject("Path")
            profile = self.doc.getObject("Profile")
            self.doc.recompute()
            self.assertEqual(profile.getTypeIdOfProperty("Target"), "App::PropertyLinkSubGlobal")
            self.assert_parametric_profile(profile, 150)
            self.path.setDatum(0, App.Units.Quantity("200 mm"))
            self.doc.recompute()
            self.assert_parametric_profile(profile, 200)
            parent = self.doc.getObject("Parent")
            if parent_type == "PartDesign::Body":
                self.assertIn(self.path, parent.Group)
                self.assertNotIn(profile, parent.Group)
                self.assertEqual(profile.Parents, [])
            elif parent:
                self.assertIn(self.path, parent.Group)
                self.assertIn(profile, parent.Group)
            else:
                self.assertEqual(profile.Parents, [])
            App.closeDocument(self.doc.Name)

    def assert_parametric_profile(self, profile, length):
        self.assertEqual(profile.Target[0], self.path)
        self.assertEqual(tuple(profile.Target[1]), ("Edge1",))
        support = profile.AttachmentSupport
        if isinstance(support, list):
            support = support[0]
        self.assertEqual(support[0], self.path)
        self.assertEqual(tuple(support[1]), ("Edge1",))
        self.assertAlmostEqual(profile.ProfileLength, length)
        self.assertFalse(profile.Shape.isNull())
        self.assertTrue(profile.Shape.isValid())
        self.assertEqual(len(profile.Shape.Solids), 1)
        self.assertAlmostEqual(profile.Shape.Volume, 200 * length)
        self.assertNotIn("Invalid", profile.State)
        self.assertNotIn("Error", profile.State)

    def test_snapshot_ignores_only_archive_timestamp(self):
        before = self.path.dumpContent()
        rewritten = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(before)) as original, zipfile.ZipFile(rewritten, "w") as changed:
            for entry in original.infolist():
                payload = original.read(entry)
                entry.date_time = (2000, 1, 1, 0, 0, 0)
                changed.writestr(entry, payload)
        self.assertNotEqual(before, rewritten.getvalue())
        self.assertEqual(source_content(before), source_content(rewritten.getvalue()))

    def test_snapshot_detects_real_source_mutation(self):
        before = source_content(self.path.dumpContent())
        self.path.setDatum(0, App.Units.Quantity("150 mm"))
        self.doc.recompute()
        with self.assertRaises(AssertionError):
            self.assertEqual(source_content(self.path.dumpContent()), before)

    def test_legacy_local_target_is_not_migrated_on_reopen(self):
        profile = self.create(False)
        target = profile.Target
        profile.removeProperty("Target")
        profile.addProperty("App::PropertyLinkSub", "Target", "Base", "Target face").Target = target
        self.doc.recompute()
        with tempfile.TemporaryDirectory(
            prefix=".frameforge-test-", dir=Path(__file__).resolve().parents[1]
        ) as directory:
            filename = str(Path(directory) / "legacy.FCStd")
            self.doc.saveAs(filename)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(filename)
            name = self.doc.Name
            self.addCleanup(lambda: App.closeDocument(name) if name in App.listDocuments() else None)
            self.path = self.doc.getObject("Path")
            profile = self.doc.getObject("Profile")
            self.doc.recompute()
            self.assertEqual(profile.getTypeIdOfProperty("Target"), "App::PropertyLinkSub")
            self.assert_parametric_profile(profile, 100)
            self.path.setDatum(0, App.Units.Quantity("150 mm"))
            self.doc.recompute()
            self.assertEqual(profile.getTypeIdOfProperty("Target"), "App::PropertyLinkSub")
            self.assert_parametric_profile(profile, 150)
            App.closeDocument(self.doc.Name)

    def preview_panel(self, in_part=True):
        panel = creation_panel()
        panel._target_doc = self.doc
        panel._objects = {}
        panel._edge_properties = {}
        panel._edge_sections = {}
        panel._excluded_edges = set()
        panel._saved_selection = [SimpleNamespace(Object=self.path, SubElementNames=["Edge1"])]
        panel._mutation_depth = 0
        panel._selection_pending = False
        panel._preview_closed = True
        panel._restore_preview_highlight = Mock()
        panel._selection_signature = lambda: ()
        for key in ("sketch", "family", "size", "prefix_profile"):
            setattr(panel.form_proxy, "cb_" + key + "_in_name", Mock(isChecked=Mock(return_value=False)))
        panel.form_proxy.rb_profiles_in_part = Mock(isChecked=Mock(return_value=in_part))
        return panel

    def test_create_part_reuses_container_and_moves_existing_preview(self):
        panel = self.preview_panel(False)
        panel.proceed()
        profile = next(iter(panel._objects.values()))
        self.assertEqual(profile.Parents, [])
        panel.form_proxy.rb_profiles_in_part.isChecked.return_value = True
        for _ in range(4):
            panel.proceed()
        parts = [obj for obj in self.doc.Objects if obj.TypeId == "App::Part"]
        self.assertEqual(len(parts), 1)
        self.assertEqual(set(parts[0].Group), {self.path, profile})
        self.assertEqual(list(panel._objects.values()), [profile])
        self.assert_parametric_profile(profile, 100)

    def test_same_place_preview_does_not_create_part(self):
        panel = self.preview_panel(False)
        for _ in range(3):
            panel.proceed()
        self.assertFalse(any(obj.TypeId == "App::Part" for obj in self.doc.Objects))
        self.assertEqual(self.path.Parents, [])
        self.assert_parametric_profile(next(iter(panel._objects.values())), 100)

    def test_custom_section_outside_part_uses_global_link(self):
        part = self.doc.addObject("App::Part", "Part")
        part.addObject(self.path)
        profile = make_custom_profile(self.path, "Edge1", "Profile", self.section)
        self.doc.recompute()
        self.assertEqual(profile.getTypeIdOfProperty("CustomProfile"), "App::PropertyLinkGlobal")
        self.assertEqual(profile.CustomProfile, self.section)
        self.assertEqual(self.section.Parents, [])
        self.assertIn(profile, part.Group)
        self.assert_parametric_profile(profile, 100)

    def test_standard_body_rejection_finishes_profile_at_root(self):
        self.check_parent("PartDesign::Body", False)

    def test_custom_body_rejection_finishes_profile_at_root(self):
        self.check_parent("PartDesign::Body", True)

    def test_standard_supported_parent_preserves_creation(self):
        self.check_parent("App::Part", False)

    def test_custom_supported_parent_preserves_creation(self):
        self.check_parent("App::Part", True)

    def test_standard_absent_parent_preserves_creation(self):
        self.check_parent(None, False)

    def test_custom_absent_parent_preserves_creation(self):
        self.check_parent(None, True)


if __name__ == "__main__":
    unittest.main()

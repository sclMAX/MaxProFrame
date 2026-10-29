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

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest

from freecad.maxproframe.alignment_widget import AlignmentWidget
from freecad.maxproframe.create_profiles_tool import CreateProfileTaskPanel
from freecad.maxproframe.edit_profile_tool import EditProfileTaskPanel
from freecad.maxproframe.ff_tools import get_param_group
from freecad.maxproframe.library_manager import LibraryManager
from freecad.maxproframe.profile import Profile


class TestTaskPanelEdgeProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FREECAD_QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.test_user_dir = tempfile.mkdtemp(prefix="ff_test_edge_props_")
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
                panel.reject()
            except Exception:
                pass
            try:
                panel.clean()
            except Exception:
                pass
            for f in getattr(panel, "form", []):
                try:
                    f.close()
                except Exception:
                    pass
        if hasattr(Gui, "Selection"):
            try:
                Gui.Selection.clearSelection()
            except Exception:
                pass
        try:
            param = get_param_group(writable=True)
            param.RemBool("Default Pre Extend")
            param.RemBool("Default Mirror Horizontally")
            param.RemBool("Default Mirror Vertically")
        except Exception:
            pass
        for doc_name in self.created_docs:
            try:
                doc = App.getDocument(doc_name) if hasattr(App, "getDocument") else None
                if doc:
                    try:
                        doc.abortTransaction()
                    except Exception:
                        pass
                App.closeDocument(doc_name)
            except Exception:
                pass
        if os.path.exists(self.test_user_dir):
            shutil.rmtree(self.test_user_dir)

    def _new_doc(self, prefix="TestDoc"):
        self.doc_count += 1
        name = f"{prefix}_{self.doc_count}_{id(self)}"
        doc = App.newDocument(name)
        App.setActiveDocument(name)
        self.created_docs.append(name)
        return doc

    def _create_rectangle_sketch(self, doc, name="RectanglePath", width=100.0, height=80.0):
        sk = doc.addObject("Sketcher::SketchObject", name)
        p1 = App.Vector(0, 0, 0)
        p2 = App.Vector(width, 0, 0)
        p3 = App.Vector(width, height, 0)
        p4 = App.Vector(0, height, 0)
        sk.addGeometry(Part.LineSegment(p1, p2), False)
        sk.addGeometry(Part.LineSegment(p2, p3), False)
        sk.addGeometry(Part.LineSegment(p3, p4), False)
        sk.addGeometry(Part.LineSegment(p4, p1), False)
        doc.recompute()
        return sk

    def test_s1_collapsible_sections_and_profile_name(self):
        """S1: Profile, Placement, and Advanced sections; Advanced is collapsible and collapsed by default."""
        doc = self._new_doc("DocS1")
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Profile and Placement sections are visible
        self.assertTrue(panel.form[0].groupBox.isVisibleTo(panel.form[0]))
        self.assertTrue(panel.form[0].groupBox_4.isVisibleTo(panel.form[0]))

        # Advanced options header starts collapsed by default
        self.assertFalse(panel.advanced_button.isChecked())
        self.assertFalse(panel.advanced_content.isVisibleTo(panel.form[1]))
        panel.advanced_button.setChecked(True)
        self.assertTrue(panel.advanced_content.isVisibleTo(panel.form[1]))
        # Combined bevels remain an internal compatibility control, not a panel option.
        self.assertFalse(panel.form_proxy.cb_combined_bevel.isVisibleTo(panel.form[1]))

        # Profile name label displays current size
        self.assertTrue(hasattr(panel, "label_profile_name"))
        size_text = panel.form_proxy.combo_size.currentText()
        self.assertIn(size_text, panel.label_profile_name.text())

    def test_s4_toggle_buttons_with_icons_and_sync(self):
        """S4: Mirror H, Mirror V, and Extend are toggle buttons with icons synced to checkboxes."""
        doc = self._new_doc("DocS4")
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Button exists, checkable, and has icon
        self.assertTrue(panel.btn_mirror_h.isCheckable())
        self.assertFalse(panel.btn_mirror_h.icon().isNull())
        self.assertTrue(panel.btn_mirror_v.isCheckable())
        self.assertFalse(panel.btn_mirror_v.icon().isNull())
        self.assertTrue(panel.btn_pre_extend.isCheckable())
        self.assertFalse(panel.btn_pre_extend.icon().isNull())

        # Toggle button -> sets checkbox
        panel.btn_mirror_h.setChecked(True)
        self.assertTrue(panel.form_proxy.cb_mirror_h.isChecked())
        panel.btn_mirror_h.setChecked(False)
        self.assertFalse(panel.form_proxy.cb_mirror_h.isChecked())

        panel.btn_mirror_v.setChecked(True)
        self.assertTrue(panel.form_proxy.cb_mirror_v.isChecked())
        panel.btn_mirror_v.setChecked(False)
        self.assertFalse(panel.form_proxy.cb_mirror_v.isChecked())

        panel.btn_pre_extend.setChecked(False)
        self.assertFalse(panel.form_proxy.cb_pre_extend.isChecked())
        panel.btn_pre_extend.setChecked(True)
        self.assertTrue(panel.form_proxy.cb_pre_extend.isChecked())

        # Checkbox change -> sets toggle button
        panel.form_proxy.cb_mirror_h.setChecked(True)
        self.assertTrue(panel.btn_mirror_h.isChecked())
        panel.form_proxy.cb_mirror_h.setChecked(False)
        self.assertFalse(panel.btn_mirror_h.isChecked())

    def test_s2_edge_list(self):
        """The edge list is always available without a mode selector."""
        doc = self._new_doc("DocModeSwitch")
        sk = self._create_rectangle_sketch(doc)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Simulate selection of rectangle (4 edges)
        panel._saved_selection = [
            type(
                "SelEx",
                (),
                {"Object": sk, "ObjectName": sk.Name, "SubElementNames": ["Edge1", "Edge2", "Edge3", "Edge4"]},
            )()
        ]
        panel.update_selection()

        self.assertFalse(hasattr(panel, "mode_switch"))
        self.assertTrue(panel.edge_list_widget.isVisibleTo(panel.form[0]))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 4)
        self.assertTrue(panel.form[0].label_14.isHidden())
        self.assertTrue(panel.form_proxy.label_attach.isHidden())

    def test_s3_per_edge_property_editing_and_badges(self):
        """S3: In Individual mode, modifying rotation/mirrors modifies only the active edge and updates its badge."""
        doc = self._new_doc("DocPerEdgeProps")
        sk = self._create_rectangle_sketch(doc)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        # Select 2 edges
        e1_key = (sk, "Edge1")
        e2_key = (sk, "Edge2")
        panel._saved_selection = [
            type("SelEx", (), {"Object": sk, "ObjectName": sk.Name, "SubElementNames": ["Edge1", "Edge2"]})()
        ]
        panel.update_selection()
        panel.proceed()

        self.assertIn(e1_key, panel._objects)
        self.assertIn(e2_key, panel._objects)

        panel.edge_list_widget.select_edge(e1_key)

        # Edit edge 1: set rotation to 90 and mirror H
        panel.set_rotation(90.0)
        panel.btn_mirror_h.setChecked(True)
        panel.on_input_changed()

        # Verify edge 1 properties updated
        props_e1 = panel._get_properties_for_edge(sk, "Edge1")
        self.assertEqual(props_e1["rotation"], 90.0)
        self.assertTrue(props_e1["mirror_h"])

        # Verify edge 2 remained at default rotation and mirror
        props_e2 = panel._get_properties_for_edge(sk, "Edge2")
        self.assertEqual(props_e2["rotation"], 0.0)
        self.assertFalse(props_e2["mirror_h"])

        # Verify edge 1 3D preview profile has RotationAngle=90 and MirrorH=True
        prof_e1 = panel._objects[e1_key]
        prof_e2 = panel._objects[e2_key]
        self.assertEqual(getattr(prof_e1, "RotationAngle", 0.0), 90.0)
        self.assertTrue(getattr(prof_e1, "MirrorH", False))
        self.assertEqual(getattr(prof_e2, "RotationAngle", 0.0), 0.0)
        self.assertFalse(getattr(prof_e2, "MirrorH", False))

        # Verify badge updated
        _, item_widget_e1 = panel.edge_list_widget._items[e1_key]
        self.assertIn("90", item_widget_e1.lbl_badge.text())
        self.assertIn("Mirror H", item_widget_e1.lbl_badge.text())

        # Switching rows reloads the complete section state without editing either profile.
        before = [(p.RotationAngle, p.MirrorH, p.Shape.Volume) for p in (prof_e1, prof_e2)]
        selection_before = [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        baseline = (prof_e2.ViewObject.LineColor, prof_e2.ViewObject.LineWidth, prof_e2.ViewObject.Transparency)
        panel.edge_list_widget.select_edge(e2_key)
        self.assertEqual(panel.get_rotation(), 0.0)
        self.assertFalse(panel.btn_mirror_h.isChecked())
        self.assertEqual(panel.alignment_widget.rotation, 0.0)
        self.assertEqual(panel.alignment_widget.mirrors, (False, False))
        self.assertIn("Edge 2", panel.label_editing_edge.text())
        self.assertEqual(prof_e1.ViewObject.Transparency, 80)
        self.assertEqual(prof_e2.ViewObject.Transparency, 35)
        self.assertGreaterEqual(prof_e2.ViewObject.LineWidth, 3.0)
        panel.edge_list_widget.select_edge(e1_key)
        self.assertEqual(panel.alignment_widget.rotation, 90.0)
        self.assertEqual(panel.alignment_widget.mirrors, (True, False))
        self.assertEqual(
            (prof_e2.ViewObject.LineColor, prof_e2.ViewObject.LineWidth, prof_e2.ViewObject.Transparency),
            baseline,
        )
        self.assertEqual([(p.RotationAngle, p.MirrorH, p.Shape.Volume) for p in (prof_e1, prof_e2)], before)
        self.assertEqual(
            [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()], selection_before
        )
        # Extension edits recompute the active solid immediately and leave its sibling unchanged.
        panel.edge_list_widget.select_edge(e2_key)
        volume = prof_e2.Shape.Volume
        sibling_shape = prof_e1.Shape.exportBrepToString()
        panel.btn_pre_extend.setChecked(True)
        offset = max(panel.form_proxy.sb_width.value(), panel.form_proxy.sb_height.value())
        self.assertEqual(prof_e2.OffsetA, offset)
        self.assertEqual(prof_e2.OffsetB, offset)
        self.assertGreater(prof_e2.Shape.Volume, volume)
        self.assertEqual(prof_e1.Shape.exportBrepToString(), sibling_shape)
        panel.btn_pre_extend.setChecked(False)
        self.assertAlmostEqual(prof_e2.Shape.Volume, volume)

        panel.clean()
        self.assertTrue(all(p.ViewObject.Transparency == 80 for p in (prof_e1, prof_e2)))

    def _canvas_panel(self):
        doc = self._new_doc("DocPersistentPaths")
        sk = self._create_rectangle_sketch(doc)
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        return doc, sk, panel

    def test_canvas_latest_pick_activates_editor(self):
        doc, sk, panel = self._canvas_panel()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        first = panel._objects[(sk, "Edge1")]
        panel.set_rotation(90)
        before = (first.Shape.exportBrepToString(), first.RotationAngle)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        self.assertEqual(panel.edge_list_widget.get_selected_edges(), [(sk, "Edge2")])
        self.assertEqual(panel._objects[(sk, "Edge2")].ViewObject.Transparency, 35)
        self.assertEqual(panel.get_rotation(), 90)
        self.assertEqual((first.Shape.exportBrepToString(), first.RotationAngle), before)

    def test_canvas_preview_pick_activates_base_without_derived_profile(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        first, second = panel._objects[(sk, "Edge1")], panel._objects[(sk, "Edge2")]
        before = [(p.Name, p.Shape.exportBrepToString(), p.RotationAngle) for p in (first, second)]
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, first.Name, "Edge1")
        self.assertEqual(panel.edge_list_widget.get_selected_edges(), [(sk, "Edge1")])
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        self.assertEqual([(p.Name, p.Shape.exportBrepToString(), p.RotationAngle) for p in (first, second)], before)
        self.assertEqual(first.ViewObject.Transparency, 35)

    def test_canvas_ctrl_remove_selected_base_on_remove_event(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        removed = panel._objects[(sk, "Edge1")].Name
        sibling = panel._objects[(sk, "Edge2")]
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.ControlModifier):
            Gui.Selection.removeSelection(doc.Name, sk.Name, "Edge1")
        self.app.processEvents()
        self.assertIsNone(doc.getObject(removed))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 1)
        self.assertTrue(panel.apply())
        self.assertIsNone(doc.getObject(removed))
        self.assertIs(doc.getObject(sibling.Name), sibling)
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)

    def test_canvas_ctrl_remove_preview_on_add_event(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        removed = panel._objects[(sk, "Edge1")].Name
        sibling = panel._objects[(sk, "Edge2")]
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.ControlModifier):
            Gui.Selection.addSelection(doc.Name, removed, "Edge1")
        self.app.processEvents()
        self.assertIsNone(doc.getObject(removed))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 1)
        self.assertTrue(panel.apply())
        self.assertIs(doc.getObject(sibling.Name), sibling)

    def test_canvas_pending_removal_before_apply_or_accept(self):
        for action in ("apply", "accept"):
            with self.subTest(action=action):
                doc, sk, panel = self._canvas_panel()
                for edge in ("Edge1", "Edge2"):
                    Gui.Selection.addSelection(doc.Name, sk.Name, edge)
                removed = panel._objects[(sk, "Edge1")].Name
                sibling = panel._objects[(sk, "Edge2")]
                sibling_name, shape = sibling.Name, sibling.Shape.exportBrepToString()
                with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.ControlModifier):
                    Gui.Selection.removeSelection(doc.Name, sk.Name, "Edge1")
                self.assertTrue(panel.apply() if action == "apply" else panel.accept(defer=False))
                self.app.processEvents()
                self.assertIsNone(doc.getObject(removed))
                self.assertIs(doc.getObject(sibling_name), sibling)
                self.assertEqual(sibling.Shape.exportBrepToString(), shape)
                self.assertEqual(panel.edge_list_widget.list_widget.count(), 1)
                panel.clean()

    def test_canvas_pending_removal_cancelled_by_normal_repick(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        first = panel._objects[(sk, "Edge1")]
        name, shape = first.Name, first.Shape.exportBrepToString()
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.ControlModifier):
            Gui.Selection.removeSelection(doc.Name, sk.Name, "Edge1")
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.app.processEvents()
        self.assertIs(doc.getObject(name), first)
        self.assertEqual(first.Shape.exportBrepToString(), shape)
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        self.assertEqual(panel.edge_list_widget.get_selected_edges(), [(sk, "Edge1")])

    def test_canvas_control_removes_last_path_and_normal_pick_readds_it(self):
        doc, sk, panel = self._canvas_panel()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        removed = panel._objects[(sk, "Edge1")].Name
        # Offscreen QtTest cannot set the physical keyboard modifier state.
        # Inject only that input; exercise native selection dispatch and removal.
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.ControlModifier):
            Gui.Selection.removeSelection(doc.Name, sk.Name, "Edge1")
        self.app.processEvents()
        self.assertIsNone(doc.getObject(removed))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 0)
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value=QtCore.Qt.NoModifier):
            Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.app.processEvents()
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 1)
        self.assertEqual(panel.edge_list_widget.get_selected_edges(), [(sk, "Edge1")])
        self.assertFalse(panel._objects[(sk, "Edge1")].Shape.isNull())

    def test_canvas_existing_profile_remains_support(self):
        doc, sk, panel = self._canvas_panel()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        existing = panel._objects[(sk, "Edge1")]
        self.assertTrue(panel.accept(defer=False))
        Gui.Selection.clearSelection()
        next_panel = CreateProfileTaskPanel()
        self.panels.append(next_panel)
        next_panel.open()
        Gui.Selection.addObserver(next_panel)
        Gui.Selection.addSelection(doc.Name, existing.Name, "Edge1")
        self.assertEqual(next_panel.edge_list_widget.get_selected_edges(), [(existing, "Edge1")])
        self.assertEqual(next_panel.edge_list_widget.list_widget.count(), 1)
        self.assertIs(doc.getObject(existing.Name), existing)

    def test_canvas_replacement_keeps_previous_path(self):
        doc, sk, panel = self._canvas_panel()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        first = panel._objects[(sk, "Edge1")]
        name, shape = first.Name, first.Shape.exportBrepToString()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        self.assertIs(doc.getObject(name), first)
        self.assertEqual(first.Shape.exportBrepToString(), shape)
        self.assertFalse(panel._objects[(sk, "Edge2")].Shape.isNull())

    def test_canvas_clear_keeps_paths_through_apply_and_ok(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        profiles = list(panel._objects.values())
        before = [(p.Name, p.Shape.exportBrepToString(), p.RotationAngle, p.MirrorH) for p in profiles]
        Gui.Selection.clearSelection()
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        self.assertFalse(panel.form_proxy.sb_length.isEnabled())
        self.assertTrue(panel.apply())
        self.assertTrue(panel.accept(defer=False))
        self.assertEqual([(p.Name, p.Shape.exportBrepToString(), p.RotationAngle, p.MirrorH) for p in profiles], before)
        self.assertTrue(all(doc.getObject(p.Name) is p for p in profiles))

    def test_canvas_can_readd_explicitly_removed_path(self):
        doc, sk, panel = self._canvas_panel()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        key = (sk, "Edge1")
        removed_name = panel._objects[key].Name
        sibling = panel._objects[(sk, "Edge2")]
        panel.edge_list_widget._items[key][1].btn_remove.click()
        self.assertIsNone(doc.getObject(removed_name))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 1)
        panel.apply()
        self.assertIsNone(doc.getObject(removed_name))
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        self.assertFalse(panel._objects[key].Shape.isNull())
        self.assertIs(panel._objects[(sk, "Edge2")], sibling)

    def test_per_edge_selection_callbacks_reconcile_previews(self):
        doc = self._new_doc("DocSelectionCallbacks")
        sk = self._create_rectangle_sketch(doc)
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        e1, e2, e3 = ((sk, f"Edge{i}") for i in (1, 2, 3))

        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        self.assertIn(e1, panel._objects)
        self.assertFalse(panel._objects[e1].Shape.isNull())
        panel.edge_list_widget.select_edge(e1)
        panel.set_rotation(90.0)
        panel.btn_mirror_h.setChecked(True)
        original = dict(panel._edge_properties[e1])

        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        self.assertEqual(panel.edge_list_widget.get_selected_edge(), e2)
        self.assertEqual(panel._edge_properties[e1], original)
        self.assertEqual(panel._objects[e1].RotationAngle, 90.0)
        self.assertTrue(panel._objects[e1].MirrorH)
        self.assertIn(e2, panel._objects)
        self.assertFalse(panel._objects[e2].Shape.isNull())
        removed_name = panel._objects[e2].Name
        Gui.Selection.removeSelection(doc.Name, sk.Name, "Edge2")
        self.assertIn(e2, panel._objects)
        self.assertIsNotNone(doc.getObject(removed_name))
        self.assertEqual(panel._edge_properties[e1], original)

        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        panel.edge_list_widget._items[e2][1].btn_remove.click()
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge3")
        self.assertNotIn(e2, panel._objects)
        self.assertIn(e3, panel._objects)
        self.assertEqual(panel._edge_properties[e1], original)
        Gui.Selection.clearSelection()
        self.assertIn(e1, panel._objects)
        self.assertIn(e3, panel._objects)

    def test_sketch_interior_selection_callbacks_create_outline_profiles(self):
        for per_edge in (False, True):
            with self.subTest(per_edge=per_edge):
                doc = self._new_doc("DocSketchInterior")
                sk = self._create_rectangle_sketch(doc)
                Gui.Selection.clearSelection()
                panel = CreateProfileTaskPanel()
                self.panels.append(panel)
                panel.open()
                Gui.Selection.addObserver(panel)
                # Model the GUI's generated filled-face token, including when
                # the sketch's stored shape does not contain a Face1. An actual
                # GUI selection event drives the observer and preview lifecycle.
                names = ["Face1", "Edge1", "Face1", "Vertex1", "Edge999"]
                selection = type("SelEx", (), {"Object": sk, "ObjectName": sk.Name, "SubElementNames": names})()
                with patch.object(Gui.Selection, "getSelectionEx", return_value=[selection]):
                    Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
                    expected = {(sk, f"Edge{i}") for i in range(1, len(sk.Shape.Edges) + 1)}
                    self.assertEqual(set(panel._objects), expected)
                    self.assertEqual(panel.edge_list_widget.list_widget.count(), len(expected))
                    for (source, edge), profile in panel._objects.items():
                        self.assertFalse(profile.Shape.isNull())
                        self.assertTrue(profile.Shape.isValid())
                        self.assertNotIn("Invalid", profile.State)
                        support = (
                            profile.AttachmentSupport if hasattr(profile, "AttachmentSupport") else profile.Support
                        )
                        supports = support if isinstance(support[0], (tuple, list)) else [support]
                        self.assertEqual(len(supports), 1)
                        support_object, subelements = supports[0]
                        self.assertEqual(support_object, source)
                        self.assertEqual(
                            (subelements,) if isinstance(subelements, str) else tuple(subelements), (edge,)
                        )
                        self.assertEqual(profile.MapMode, "NormalToEdge")
                    self.assertEqual(names, ["Face1", "Edge1", "Face1", "Vertex1", "Edge999"])
                panel.reject()
                Gui.Selection.clearSelection()

    def test_selection_normalization_preserves_edges_and_ignores_unsupported_paths(self):
        doc = self._new_doc("DocNormalizedPaths")
        sk = self._create_rectangle_sketch(doc)
        solid = doc.addObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(10, 10, 10)
        doc.recompute()
        select = lambda obj, names: type("SelEx", (), {"Object": obj, "SubElementNames": names})()
        normalize = CreateProfileTaskPanel._selection_edges
        self.assertEqual(normalize(select(sk, [])), [f"Edge{i}" for i in range(1, 5)])
        names = ["Edge2", "Edge2", "Vertex1", "Edge999"]
        self.assertEqual(normalize(select(sk, names)), ["Edge2"])
        self.assertEqual(names, ["Edge2", "Edge2", "Vertex1", "Edge999"])
        self.assertEqual(normalize(select(solid, ["Face1", "Vertex1", "Edge1"])), ["Edge1"])
        self.assertEqual(normalize(select(solid, ["Face1", "Vertex1"])), [])
        self.assertEqual(len(normalize(select(solid, []))), len(solid.Shape.Edges))

    def test_per_edge_face_colors_restore_on_row_mode_and_clean(self):
        doc = self._new_doc("DocFaceColors")
        sk = self._create_rectangle_sketch(doc)
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        e1, e2 = (sk, "Edge1"), (sk, "Edge2")
        p1, p2 = panel._objects[e1], panel._objects[e2]
        panel.edge_list_widget.list_widget.clearSelection()
        p1.ViewObject.ShapeColor = (0.7, 0.2, 0.1)
        p2.ViewObject.ShapeColor = (0.1, 0.7, 0.2)
        if hasattr(p1.ViewObject, "DiffuseColor"):
            p1.ViewObject.DiffuseColor = [(0.3, 0.2, 0.6)] * len(p1.Shape.Faces)

        def appearance(profile):
            view = profile.ViewObject
            return (
                view.ShapeColor,
                list(view.DiffuseColor) if hasattr(view, "DiffuseColor") else None,
                view.LineColor,
                view.LineWidth,
                view.Transparency,
            )

        before1, before2 = appearance(p1), appearance(p2)
        selection = [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        panel.edge_list_widget.select_edge(e1)
        self.assertNotEqual(p1.ViewObject.ShapeColor, before1[0])
        if before1[1]:
            self.assertNotEqual(list(p1.ViewObject.DiffuseColor), before1[1])
        panel.edge_list_widget.list_widget.item(1).setSelected(True)
        self.assertNotEqual(p1.ViewObject.ShapeColor, before1[0])
        self.assertNotEqual(p2.ViewObject.ShapeColor, before2[0])
        panel.edge_list_widget.list_widget.item(0).setSelected(False)
        self.assertEqual(appearance(p1), before1)
        self.assertNotEqual(p2.ViewObject.ShapeColor, before2[0])
        panel.clean()
        self.assertEqual(appearance(p2), before2)
        self.assertEqual([(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()], selection)

    def test_mixed_selection_is_display_only_and_edits_one_property(self):
        doc = self._new_doc("DocMixedSelection")
        sk = self._create_rectangle_sketch(doc)
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
        Gui.Selection.addSelection(doc.Name, sk.Name, "Edge2")
        e1, e2 = (sk, "Edge1"), (sk, "Edge2")
        panel.edge_list_widget.select_edge(e1)
        panel.set_rotation(90)
        panel.btn_mirror_h.setChecked(True)
        panel.alignment_widget.anchorClicked.emit(0, 0)
        size_combo = panel.form_proxy.combo_size
        has_alternative_size = size_combo.count() > 1
        if has_alternative_size:
            size_combo.setCurrentIndex((size_combo.currentIndex() + 1) % size_combo.count())
        if panel.form_proxy.sb_width.isEnabled():
            panel.form_proxy.sb_width.setValue(panel.form_proxy.sb_width.value() + 1)
        panel.edge_list_widget.select_edge(e2)
        panel.set_rotation(180)
        p1, p2 = panel._objects[e1], panel._objects[e2]

        def state(p):
            return (
                p.RotationAngle,
                p.MirrorH,
                p.MirrorV,
                p.AnchorX,
                p.AnchorY,
                p.Material,
                p.CatalogFamily,
                p.SizeName,
                p.ProfileWidth,
                p.ProfileHeight,
                p.Thickness,
                p.OffsetA,
                p.OffsetB,
                p.Shape.exportBrepToString(),
            )

        before = [state(p) for p in (p1, p2)]
        panel.edge_list_widget.list_widget.item(0).setSelected(True)
        self.assertEqual([state(p) for p in (p1, p2)], before)
        self.assertIn("2", panel.label_editing_edge.text())
        self.assertTrue(panel.form_proxy.combo_rotation.property("mixedValues"))
        self.assertTrue(panel.btn_mirror_h.property("mixedValues"))
        self.assertIsNone(panel.alignment_widget.selected_anchor)
        self.assertFalse(panel.form_proxy.combo_material.property("mixedValues"))
        if has_alternative_size:
            self.assertTrue(panel.form_proxy.combo_size.property("mixedValues"))
        if before[0][8] != before[1][8]:
            self.assertTrue(panel.form_proxy.sb_width.property("mixedValues"))
        panel.btn_mirror_h.click()
        self.assertTrue(p1.MirrorH)
        self.assertTrue(p2.MirrorH)
        self.assertEqual(p1.RotationAngle, 90)
        self.assertEqual(p2.RotationAngle, 180)
        self.assertEqual((p1.AnchorX, p1.AnchorY), before[0][3:5])
        self.assertEqual((p2.AnchorX, p2.AnchorY), before[1][3:5])
        self.assertEqual(state(p1)[5:11], before[0][5:11])
        self.assertEqual(state(p2)[5:11], before[1][5:11])
        for button, property_name in ((panel.btn_mirror_v, "MirrorV"), (panel.btn_pre_extend, None)):
            panel.edge_list_widget.select_edge(e2)
            button.setChecked(False)
            panel.edge_list_widget.select_edge(e1)
            button.setChecked(True)
            panel.edge_list_widget.list_widget.item(1).setSelected(True)
            before_toggle = [state(p) for p in (p1, p2)]
            self.assertTrue(button.property("mixedValues"))
            button.click()
            for index, p in enumerate((p1, p2)):
                current = state(p)
                if property_name:
                    self.assertTrue(getattr(p, property_name))
                    self.assertEqual(current[:2], before_toggle[index][:2])
                    self.assertEqual(current[3:13], before_toggle[index][3:13])
                else:
                    self.assertEqual(current[:11], before_toggle[index][:11])
                    self.assertGreater(p.OffsetA, 0)
                    self.assertEqual(p.OffsetA, p.OffsetB)
        after = [state(p) for p in (p1, p2)]
        panel.edge_list_widget.list_widget.clearSelection()
        self.assertFalse(panel.form_proxy.combo_rotation.isEnabled())
        self.assertEqual([state(p) for p in (p1, p2)], after)
        panel.edge_list_widget.select_edge(e1)
        self.assertTrue(panel.form_proxy.combo_rotation.isEnabled())
        self.assertEqual([state(p) for p in (p1, p2)], after)

    def test_mixed_numeric_reference_commit_and_focus_without_edit(self):
        doc = self._new_doc("DocMixedNumeric")
        sk = self._create_rectangle_sketch(doc)
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        for edge in ("Edge1", "Edge2", "Edge3"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        keys = [(sk, f"Edge{i}") for i in (1, 2, 3)]
        panel.edge_list_widget.select_edge(keys[0])
        width = panel.form_proxy.sb_width
        self.assertTrue(width.isEnabled())
        width.setValue(width.value() + 5)
        panel.set_rotation(90)
        panel.btn_mirror_h.setChecked(True)
        panel.alignment_widget.anchorClicked.emit(0, 0)
        panel.edge_list_widget.select_edge(keys[1])
        panel.set_rotation(180)
        panel.btn_mirror_v.setChecked(True)
        profiles = [panel._objects[key] for key in keys]

        def state(p):
            return (
                p.ProfileWidth,
                p.RotationAngle,
                p.MirrorH,
                p.MirrorV,
                p.AnchorX,
                p.AnchorY,
                p.Material,
                p.CatalogFamily,
                p.SizeName,
                p.Shape.exportBrepToString(),
            )

        before = [state(p) for p in profiles]
        panel.edge_list_widget.list_widget.item(0).setSelected(True)
        self.assertTrue(width.property("mixedValues"))
        self.assertEqual([state(p) for p in profiles], before)
        for form in panel.form:
            form.show()
        width.setFocus()
        self.app.processEvents()
        panel.form_proxy.combo_rotation.setFocus()
        self.app.processEvents()
        self.assertEqual([state(p) for p in profiles], before)
        self.assertTrue(width.property("mixedValues"))
        reference = width.value()
        reference_text = width.cleanText()
        width.setFocus()
        edit = width.lineEdit()
        edit.selectAll()
        QtTest.QTest.keyClicks(edit, reference_text)
        QtTest.QTest.keyClick(edit, QtCore.Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual([p.ProfileWidth for p in profiles[:2]], [reference, reference])
        for index, p in enumerate(profiles[:2]):
            self.assertEqual(state(p)[1:9], before[index][1:9])
            self.assertTrue(p.Shape.isValid())
        self.assertEqual(state(profiles[2]), before[2])
        after_width = [state(p) for p in profiles]
        panel.alignment_widget.anchorClicked.emit(2, 2)
        for index, p in enumerate(profiles[:2]):
            self.assertEqual((p.AnchorX, p.AnchorY), ("Right", "Top"))
            self.assertEqual(state(p)[:4], after_width[index][:4])
            self.assertEqual(state(p)[6:9], after_width[index][6:9])
            self.assertTrue(p.Shape.isValid())
        self.assertEqual(state(profiles[2]), after_width[2])

    def test_selected_removal_restores_survivor_appearance_and_exclusion(self):
        doc = self._new_doc("DocRemoveHighlighted")
        sk = self._create_rectangle_sketch(doc)
        source_shape = sk.Shape.exportBrepToString()
        Gui.Selection.clearSelection()
        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()
        Gui.Selection.addObserver(panel)
        for edge in ("Edge1", "Edge2", "Edge3"):
            Gui.Selection.addSelection(doc.Name, sk.Name, edge)
        keys = [(sk, f"Edge{i}") for i in (1, 2, 3)]
        rows = panel.edge_list_widget.list_widget
        rows.clearSelection()
        p1, removed, p3 = [panel._objects[key] for key in keys]
        p1.ViewObject.ShapeColor = (0.7, 0.2, 0.1)
        p3.ViewObject.ShapeColor = (0.1, 0.7, 0.2)
        p1.ViewObject.Transparency = 60
        p3.ViewObject.Transparency = 70

        def appearance(p):
            view = p.ViewObject
            return (view.ShapeColor, list(view.DiffuseColor), view.LineColor, view.LineWidth, view.Transparency)

        original = [appearance(p1), appearance(p3)]
        selection = [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]
        rows.selectAll()
        removed_name = removed.Name
        panel.edge_list_widget._items[keys[1]][1].btn_remove.click()
        self.assertIsNone(doc.getObject(removed_name))
        self.assertEqual(sk.Shape.exportBrepToString(), source_shape)
        self.assertEqual([(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()], selection)
        panel.update_selection()
        panel.proceed()
        self.assertIsNone(doc.getObject(removed_name))
        self.assertEqual(panel.edge_list_widget.list_widget.count(), 2)
        rows.clearSelection()
        self.assertEqual([appearance(p1), appearance(p3)], original)
        rows.selectAll()
        panel.clean()
        self.assertEqual([appearance(p1), appearance(p3)], original)
        self.assertEqual([(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()], selection)
        self.assertEqual(sk.Shape.exportBrepToString(), source_shape)

    def test_s3_edge_removal(self):
        """S3: Clicking remove on an edge removes it from properties and removes its preview object, remaining absent on subsequent input changes."""
        doc = self._new_doc("DocRemoveEdge")
        sk = self._create_rectangle_sketch(doc)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        e1_key = (sk, "Edge1")
        e2_key = (sk, "Edge2")
        panel._saved_selection = [
            type("SelEx", (), {"Object": sk, "ObjectName": sk.Name, "SubElementNames": ["Edge1", "Edge2"]})()
        ]
        panel.update_selection()
        panel.proceed()

        self.assertEqual(len(panel._objects), 2)
        prof_e2_name = panel._objects[e2_key].Name

        # Remove Edge2
        panel._on_edge_removed(e2_key)

        self.assertNotIn(e2_key, panel._objects)
        self.assertNotIn(e2_key, panel._edge_properties)
        self.assertIsNone(doc.getObject(prof_e2_name))

        # Subsequent input change must NOT resurrect the removed edge (Finding R3-001)
        panel.set_rotation(45.0)
        panel.on_input_changed()

        self.assertNotIn(e2_key, panel._objects)
        self.assertNotIn(e2_key, panel._edge_properties)
        self.assertIsNone(doc.getObject(prof_e2_name))
        remaining_keys = [
            panel.edge_list_widget.list_widget.item(i).data(QtCore.Qt.UserRole)
            for i in range(panel.edge_list_widget.list_widget.count())
        ]
        self.assertNotIn(e2_key, remaining_keys)

    def test_s5_edit_profile_task_panel_compatibility(self):
        """S5: EditProfileTaskPanel continues to initialize and operate cleanly with collapsible headers and toggle buttons."""
        doc = self._new_doc("DocEditCompat")
        sk = self._create_rectangle_sketch(doc)

        # Create an existing profile
        obj = doc.addObject("Part::FeaturePython", "SampleProfile")
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
            init_rotation=45.0,
            init_mirror_h=True,
        )
        doc.recompute()

        edit_panel = EditProfileTaskPanel(obj)
        self.panels.append(edit_panel)
        edit_panel.initialize_ui()

        # Check that advanced section exists and toggle buttons reflect profile state
        self.assertTrue(hasattr(edit_panel, "advanced_button"))
        self.assertTrue(hasattr(edit_panel, "btn_mirror_h"))
        self.assertTrue(edit_panel.btn_mirror_h.isChecked())
        self.assertFalse(edit_panel.btn_mirror_v.isChecked())
        self.assertEqual(edit_panel.get_rotation(), 45.0)
        edit_panel.form_proxy.combo_rotation.setCurrentText("90")
        self.assertEqual(obj.RotationAngle, 90.0)
        edit_panel.form_proxy.cb_mirror_h.setChecked(False)
        self.assertFalse(obj.MirrorH)
        edit_panel.alignment_widget.set_state((2, 0), 45, True, False)
        self.assertEqual(edit_panel.alignment_widget.selected_anchor, (2, 0))
        self.assertEqual(edit_panel.alignment_widget.rotation, 45.0)
        self.assertEqual(edit_panel.alignment_widget.mirrors, (True, False))

    def test_alignment_unset_keyboard_and_mouse(self):
        widget = AlignmentWidget()
        widget.resize(220, 180)
        widget.set_section(Part.makePlane(40, 30))
        clicked = []
        widget.anchorClicked.connect(lambda x, y: clicked.append((x, y)))
        widget.set_state(None)
        self.assertIsNone(widget.selected_anchor)
        self.assertEqual(clicked, [])
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Right, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(widget, event)
        self.assertEqual(widget.selected_anchor, (2, 1))
        self.assertEqual(clicked, [(2, 1)])
        widget.set_state((1, 1), 90, True, False)
        self.assertEqual(widget.selected_anchor, (1, 1))
        self.assertEqual(widget.rotation, 90.0)
        self.assertEqual(widget.mirrors, (True, False))
        position = widget.anchor_position(0, 2).toPoint()
        mouse = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            position,
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(widget, mouse)
        self.assertEqual(widget.selected_anchor, (0, 2))
        self.assertEqual(clicked, [(2, 1), (0, 2)])


if __name__ == "__main__":
    unittest.main()

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

    def test_s2_mode_switch_and_edge_list(self):
        """S2: Mode switch toggles between Uniform notice and Individual edge list."""
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

        # Default is Uniform mode
        self.assertFalse(panel.mode_switch.is_per_edge())
        self.assertTrue(panel.notice_uniform.isVisibleTo(panel.form[0]))
        self.assertFalse(panel.edge_list_widget.isVisibleTo(panel.form[0]))
        self.assertIn("4", panel.label_uniform_count.text())

        # Switch to Individual mode
        panel.mode_switch.set_per_edge(True)
        self.assertTrue(panel.mode_switch.is_per_edge())
        self.assertFalse(panel.notice_uniform.isVisibleTo(panel.form[0]))
        self.assertTrue(panel.edge_list_widget.isVisibleTo(panel.form[0]))

        # Switch back to Uniform mode
        panel.mode_switch.set_per_edge(False)
        self.assertFalse(panel.mode_switch.is_per_edge())
        self.assertTrue(panel.notice_uniform.isVisibleTo(panel.form[0]))
        self.assertFalse(panel.edge_list_widget.isVisibleTo(panel.form[0]))

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

        # Switch to Individual mode
        panel.mode_switch.set_per_edge(True)
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
        self.assertIn("EspH", item_widget_e1.lbl_badge.text())

    def test_s3_reset_edge_to_global(self):
        """S3: Reset button restores the active edge's properties to global defaults."""
        doc = self._new_doc("DocResetEdge")
        sk = self._create_rectangle_sketch(doc)

        panel = CreateProfileTaskPanel()
        self.panels.append(panel)
        panel.open()

        e1_key = (sk, "Edge1")
        panel._saved_selection = [
            type("SelEx", (), {"Object": sk, "ObjectName": sk.Name, "SubElementNames": ["Edge1"]})()
        ]
        panel.update_selection()
        panel.proceed()

        panel.mode_switch.set_per_edge(True)
        panel.edge_list_widget.select_edge(e1_key)

        # Modify edge 1
        panel.set_rotation(180.0)
        panel.btn_mirror_v.setChecked(True)
        panel.on_input_changed()

        self.assertEqual(panel._edge_properties[e1_key]["rotation"], 180.0)
        self.assertTrue(panel._edge_properties[e1_key]["mirror_v"])

        # Click reset
        panel.edge_list_widget.btn_reset.click()

        # Should be restored to global default (rotation 0, mirror_v False)
        self.assertEqual(panel._edge_properties[e1_key]["rotation"], 0.0)
        self.assertFalse(panel._edge_properties[e1_key]["mirror_v"])

    def test_sketch_interior_selection_callbacks_create_outline_profiles(self):
        for per_edge in (False, True):
            with self.subTest(per_edge=per_edge):
                doc = self._new_doc("DocSketchInterior")
                sk = self._create_rectangle_sketch(doc)
                Gui.Selection.clearSelection()
                panel = CreateProfileTaskPanel()
                self.panels.append(panel)
                panel.open()
                panel.mode_switch.set_per_edge(per_edge)
                Gui.Selection.addObserver(panel)
                # Model the GUI's generated filled-face token, including when
                # the sketch's stored shape does not contain a Face1. An actual
                # GUI selection event drives the observer and preview lifecycle.
                names = ["Face1", "Edge1", "Face1", "Vertex1", "Edge999"]
                selection = type(
                    "SelEx", (), {"Object": sk, "ObjectName": sk.Name, "SubElementNames": names}
                )()
                with patch.object(Gui.Selection, "getSelectionEx", return_value=[selection]):
                    Gui.Selection.addSelection(doc.Name, sk.Name, "Edge1")
                    if per_edge:
                        # Immediate individual-mode reconciliation belongs to the later editor slice.
                        self.assertTrue(panel.apply())
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
                        self.assertEqual((subelements,) if isinstance(subelements, str) else tuple(subelements), (edge,))
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

        panel.mode_switch.set_per_edge(True)

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
            QtCore.QEvent.MouseButtonPress, position, QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(widget, mouse)
        self.assertEqual(widget.selected_anchor, (0, 2))
        self.assertEqual(clicked, [(2, 1), (0, 2)])


if __name__ == "__main__":
    unittest.main()

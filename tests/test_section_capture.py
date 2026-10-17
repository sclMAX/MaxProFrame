import hashlib
import math
import os
import tempfile
import unittest

import FreeCAD as App
import Part
import Sketcher

from freecad.frameforge.custom_section_geometry import build_custom_section_face
from freecad.frameforge.section_capture import capture_section_sketch, save_section_asset


class TestSectionCapture(unittest.TestCase):
    def setUp(self):
        self.doc_names = []
        self.temp_dirs = []

    def tearDown(self):
        for name in list(self.doc_names):
            if name in App.listDocuments():
                try:
                    App.closeDocument(name)
                except Exception:
                    pass
        # Clean up test directories created during tests
        import shutil
        for d in self.temp_dirs:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass

    def _new_doc(self, name_prefix):
        doc = App.newDocument(name_prefix)
        self.doc_names.append(doc.Name)
        return doc

    def _new_temp_dir(self, prefix="ff_capture_test_"):
        d = tempfile.mkdtemp(prefix=prefix)
        self.temp_dirs.append(d)
        return d

    def _create_rect_sketch(self, doc, name="Section", width=250.0, height=100.0):
        s = doc.addObject("Sketcher::SketchObject", name)
        pts = [(0, 0), (width, 0), (width, height), (0, height)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        for i in range(4):
            s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        for i in [0, 2]:
            s.addConstraint(Sketcher.Constraint("Horizontal", i))
        for i in [1, 3]:
            s.addConstraint(Sketcher.Constraint("Vertical", i))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        w = s.addConstraint(Sketcher.Constraint("Distance", 0, float(width)))
        h = s.addConstraint(Sketcher.Constraint("Distance", 1, float(height)))
        doc.recompute()
        return s, w, h

    # 1. Autonomous simple sketch capture
    def test_capture_simple_autonomous_sketch(self):
        doc = self._new_doc("SimpleSourceDoc")
        s, w, h = self._create_rect_sketch(doc, "RectSketch", 200.0, 80.0)

        target_doc = self._new_doc("SimpleTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="AutonomousRect")
        target_doc.recompute()

        self.assertEqual(copy_sketch.solve(), 0)
        face = build_custom_section_face(copy_sketch)
        self.assertTrue(face.isValid())
        self.assertAlmostEqual(face.Area, 200.0 * 80.0, places=4)
        self.assertEqual(len(copy_sketch.OutList), 0)
        self.assertEqual(len(copy_sketch.ExternalGeometry), 0)
        self.assertTrue(copy_sketch.Placement.isIdentity())
        self.assertEqual(str(copy_sketch.MapMode), "Deactivated")
        self.assertFalse(bool(copy_sketch.AttachmentSupport))

    # 2. Hollow and curved sketch capture
    def test_capture_hollow_curved_sketch(self):
        doc = self._new_doc("HollowCurvedDoc")
        s = doc.addObject("Sketcher::SketchObject", "RingHole")
        # Outer circle R=30
        s.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 30.0), False)
        # Inner circle R=15
        s.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 15.0), False)
        # Center coincident with origin
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 3, -1, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", 1, 3, -1, 1))
        c_r1 = s.addConstraint(Sketcher.Constraint("Radius", 0, 30.0))
        c_r2 = s.addConstraint(Sketcher.Constraint("Radius", 1, 15.0))
        doc.recompute()

        target_doc = self._new_doc("RingTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="AutonomousRing")
        target_doc.recompute()

        self.assertEqual(copy_sketch.solve(), 0)
        face = build_custom_section_face(copy_sketch)
        self.assertTrue(face.isValid())
        expected_area = math.pi * (30.0**2 - 15.0**2)
        self.assertAlmostEqual(face.Area, expected_area, places=2)
        self.assertEqual(len(face.Wires), 2)
        self.assertEqual(len(copy_sketch.OutList), 0)

    # 3. External parameter expression (VarSet) frozen to typed datum & editable in copy
    def test_capture_varset_external_length_freeze_and_edit(self):
        doc = self._new_doc("VarSetSourceDoc")
        s, w, h = self._create_rect_sketch(doc, "VarSetSketch", 250.0, 100.0)

        v = doc.addObject("App::VarSet", "Vars")
        v.addProperty("App::PropertyLength", "Ancho")
        v.Ancho = App.Units.Quantity("250 mm")
        s.setExpression(f"Constraints[{w}]", "Vars.Ancho")
        doc.recompute()

        # Check source has external dependency
        self.assertIn("Vars", [o.Name for o in s.OutList])

        target_doc = self._new_doc("VarSetTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="Section")
        target_doc.recompute()

        # Verify copy is independent and frozen
        self.assertEqual(len(copy_sketch.OutList), 0)
        self.assertEqual(len(copy_sketch.ExpressionEngine), 0)
        datum_w = copy_sketch.getDatum(w)
        self.assertAlmostEqual(datum_w.Value, 250.0, places=4)
        self.assertEqual(datum_w.Unit, App.Units.Quantity("1 mm").Unit)

        # Edit copy datum to 300 mm
        copy_sketch.setDatum(w, App.Units.Quantity("300 mm"))
        target_doc.recompute()
        self.assertEqual(copy_sketch.solve(), 0)
        face = build_custom_section_face(copy_sketch)
        self.assertAlmostEqual(face.Area, 300.0 * 100.0, places=4)

        # Verify source remains completely untouched
        doc.recompute()
        self.assertIn("Vars", [o.Name for o in s.OutList])
        self.assertAlmostEqual(s.getDatum(w).Value, 250.0, places=4)

    # 4. Resolved external formula with angle Quantity
    def test_capture_resolved_external_formula_angle(self):
        doc = self._new_doc("AngleSourceDoc")
        s = doc.addObject("Sketcher::SketchObject", "Triangle")
        # Line from origin along X
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
        # Line angled
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(50, 86.6, 0)), False)
        # Closing line
        s.addGeometry(Part.LineSegment(App.Vector(100, 0, 0), App.Vector(50, 86.6, 0)), False)
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 2, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 2))
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        s.addConstraint(Sketcher.Constraint("Horizontal", 0))
        s.addConstraint(Sketcher.Constraint("Distance", 0, 100.0))
        c_angle = s.addConstraint(Sketcher.Constraint("Angle", 0, 1, 1, 1, math.pi / 3))

        v = doc.addObject("App::VarSet", "Params")
        v.addProperty("App::PropertyAngle", "Alpha")
        v.Alpha = App.Units.Quantity("60 deg")
        s.setExpression(f"Constraints[{c_angle}]", "Params.Alpha")
        doc.recompute()

        target_doc = self._new_doc("AngleTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="TriangleCopy")
        target_doc.recompute()

        self.assertEqual(len(copy_sketch.OutList), 0)
        self.assertEqual(len(copy_sketch.ExpressionEngine), 0)
        angle_datum = copy_sketch.getDatum(c_angle)
        self.assertAlmostEqual(angle_datum.Value, 60.0, places=2)

    # 5. Internal formula preservation
    def test_capture_internal_formula_preservation(self):
        doc = self._new_doc("InternalExprDoc")
        s, w, h = self._create_rect_sketch(doc, "InternalRect", 100.0, 50.0)
        # Set internal formula: height = width / 2
        s.setExpression(f"Constraints[{h}]", f"Constraints[{w}] / 2")
        doc.recompute()

        target_doc = self._new_doc("InternalTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="InternalCopy")
        target_doc.recompute()

        self.assertEqual(len(copy_sketch.OutList), 0)
        # Internal formula should be preserved
        self.assertIn(f"Constraints[{h}]", dict(copy_sketch.ExpressionEngine))
        self.assertAlmostEqual(copy_sketch.getDatum(h).Value, 50.0, places=4)

        # Edit width to 200 mm -> height should automatically update to 100 mm
        copy_sketch.setDatum(w, App.Units.Quantity("200 mm"))
        target_doc.recompute()
        self.assertEqual(copy_sketch.solve(), 0)
        self.assertAlmostEqual(copy_sketch.getDatum(h).Value, 100.0, places=4)
        face = build_custom_section_face(copy_sketch)
        self.assertAlmostEqual(face.Area, 200.0 * 100.0, places=4)

    # 6. Legacy construction projection mapping with Block
    def test_capture_legacy_construction_projection(self):
        doc = self._new_doc("LegacyProjDoc")
        helper = doc.addObject("PartDesign::Feature", "Reference")
        helper.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(40, 0, 0))
        doc.recompute()

        s, w, h = self._create_rect_sketch(doc, "LegacySketch", 250.0, 100.0)
        # Delete Coincident(0, 1, -1, 1) constraint which is index 8
        s.delConstraint(8)
        w -= 1
        h -= 1
        # Add external reference Edge1 (defining=False)
        s.addExternal("Reference", "Edge1")
        s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -3, 1))
        doc.recompute()

        self.assertIn("Reference", [o.Name for o in s.OutList])

        target_doc = self._new_doc("LegacyTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="LegacyCopy")
        target_doc.recompute()

        self.assertEqual(copy_sketch.solve(), 0)
        self.assertEqual(len(copy_sketch.OutList), 0)
        self.assertEqual(len(copy_sketch.ExternalGeometry), 0)
        # Materialized external geometry should be construction
        # Total geometry should be 4 rect lines + 1 materialized line = 5
        self.assertEqual(copy_sketch.GeometryCount, 5)
        self.assertTrue(copy_sketch.getConstruction(4))

        face = build_custom_section_face(copy_sketch)
        self.assertAlmostEqual(face.Area, 250.0 * 100.0, places=4)

    # 7. Defining projection materialization
    def test_capture_defining_projection_materialized(self):
        doc = self._new_doc("DefiningProjDoc")
        helper = doc.addObject("PartDesign::Feature", "RefEdge")
        helper.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(250, 0, 0))
        doc.recompute()

        s = doc.addObject("Sketcher::SketchObject", "DefiningSection")
        # 3 internal lines: (250,0)->(250,100)->(0,100)->(0,0)
        pts = [(250, 0), (250, 100), (0, 100), (0, 0)]
        for a, b in zip(pts, pts[1:]):
            s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        # Add external defining line (0,0)->(250,0) with defining=True
        s.addExternal("RefEdge", "Edge1", True, False)
        for c in [
            Sketcher.Constraint("Coincident", 0, 1, -3, 2),
            Sketcher.Constraint("Coincident", 0, 2, 1, 1),
            Sketcher.Constraint("Coincident", 1, 2, 2, 1),
            Sketcher.Constraint("Coincident", 2, 2, -3, 1),
            Sketcher.Constraint("Vertical", 0),
            Sketcher.Constraint("Horizontal", 1),
            Sketcher.Constraint("Vertical", 2),
            Sketcher.Constraint("Distance", 0, 100.0),
        ]:
            s.addConstraint(c)
        doc.recompute()

        self.assertIn("RefEdge", [o.Name for o in s.OutList])
        self.assertEqual(s.GeometryCount, 3)

        target_doc = self._new_doc("DefiningTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="DefiningCopy")
        target_doc.recompute()

        self.assertEqual(copy_sketch.solve(), 0)
        self.assertEqual(len(copy_sketch.OutList), 0)
        self.assertEqual(len(copy_sketch.ExternalGeometry), 0)
        # Materialized defining geometry must be NON-construction (material)
        self.assertEqual(copy_sketch.GeometryCount, 4)
        self.assertFalse(copy_sketch.getConstruction(3))

        face = build_custom_section_face(copy_sketch)
        self.assertTrue(face.isValid())
        self.assertAlmostEqual(face.Area, 250.0 * 100.0, places=4)

    # 8. Attached/rotated source detached into identity placement
    def test_capture_attached_rotated_source_detached(self):
        doc = self._new_doc("AttachDoc")
        box = doc.addObject("Part::Box", "SupportBox")
        box.Length = 400
        box.Width = 300
        box.Height = 50
        box.Placement = App.Placement(App.Vector(70, 80, 90), App.Rotation(App.Vector(1, 1, 0), 35))
        doc.recompute()

        s, w, h = self._create_rect_sketch(doc, "AttachedSketch", 250.0, 100.0)
        s.AttachmentSupport = (box, ["Face6"])
        s.MapMode = "FlatFace"
        doc.recompute()

        self.assertFalse(s.Placement.isIdentity())
        self.assertIn("SupportBox", [o.Name for o in s.OutList])

        target_doc = self._new_doc("DetachedDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="DetachedSketch")
        target_doc.recompute()

        self.assertTrue(copy_sketch.Placement.isIdentity())
        self.assertEqual(str(copy_sketch.MapMode), "Deactivated")
        self.assertFalse(bool(copy_sketch.AttachmentSupport))
        self.assertEqual(len(copy_sketch.OutList), 0)

        # Local geometry and area match exactly
        face_copy = build_custom_section_face(copy_sketch)
        self.assertAlmostEqual(face_copy.Area, 250.0 * 100.0, places=4)

    # 9. Constraint names, driving status, and active status preserved
    def test_capture_preserves_constraint_names_driving_active(self):
        doc = self._new_doc("ConstraintMetaDoc")
        s, w, h = self._create_rect_sketch(doc, "MetaSketch", 150.0, 75.0)
        # Name the width constraint
        s.renameConstraint(w, "ProfileWidth")
        # Add a non-driving reference distance constraint between diagonal vertices
        ref_c = s.addConstraint(Sketcher.Constraint("Distance", 0, 1, 1, 2, 167.705))
        s.setDriving(ref_c, False)
        # Add an inactive constraint
        extra_c = s.addConstraint(Sketcher.Constraint("Distance", 2, 150.0))
        s.setActive(extra_c, False)
        doc.recompute()

        target_doc = self._new_doc("MetaTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="MetaCopy")
        target_doc.recompute()

        self.assertEqual(copy_sketch.Constraints[w].Name, "ProfileWidth")
        self.assertFalse(copy_sketch.getDriving(ref_c))
        self.assertFalse(copy_sketch.getActive(extra_c))

    # 10. Source original completely unchanged (hash and properties)
    def test_source_snapshot_unchanged_and_hash_identical(self):
        doc = self._new_doc("SourceHashDoc")
        s, w, h = self._create_rect_sketch(doc, "HashSketch", 220.0, 110.0)
        src_path = os.path.join(self._new_temp_dir(), "original_source.FCStd")
        doc.saveAs(src_path)
        before_hash = hashlib.sha256(open(src_path, "rb").read()).hexdigest()
        before_constraints = [(c.Type, c.First, c.Second, c.Value) for c in s.Constraints]

        target_doc = self._new_doc("HashTargetDoc")
        copy_sketch = capture_section_sketch(s, target_doc=target_doc, name="HashCopy")
        target_doc.recompute()

        # Check source constraints in memory
        after_constraints = [(c.Type, c.First, c.Second, c.Value) for c in s.Constraints]
        self.assertEqual(before_constraints, after_constraints)

        # Check saved source file hash
        after_hash = hashlib.sha256(open(src_path, "rb").read()).hexdigest()
        self.assertEqual(before_hash, after_hash)

    # 11. Reject invalid, disconnected, open, and unresolved sources
    def test_reject_invalid_disconnected_open_unresolved_sources(self):
        doc = self._new_doc("RejectDoc")

        # Open contour sketch
        sk_open = doc.addObject("Sketcher::SketchObject", "OpenSketch")
        sk_open.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
        doc.recompute()
        with self.assertRaises(ValueError) as ctx:
            capture_section_sketch(sk_open)
        self.assertIn("open contours", str(ctx.exception).lower())

        # Disconnected regions
        sk_disj = doc.addObject("Sketcher::SketchObject", "DisjointSketch")
        # Rect 1
        pts1 = [(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]
        for a, b in zip(pts1, pts1[1:]):
            sk_disj.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        # Rect 2
        pts2 = [(40, 0), (60, 0), (60, 20), (40, 20), (40, 0)]
        for a, b in zip(pts2, pts2[1:]):
            sk_disj.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
        doc.recompute()
        with self.assertRaises(ValueError) as ctx:
            capture_section_sketch(sk_disj)
        self.assertIn("one connected material region", str(ctx.exception).lower())

        # Unresolved expression
        sk_unres = doc.addObject("Sketcher::SketchObject", "UnresolvedSketch")
        sk_unres.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(50, 0, 0)), False)
        sk_unres.addGeometry(Part.LineSegment(App.Vector(50, 0, 0), App.Vector(50, 50, 0)), False)
        sk_unres.addGeometry(Part.LineSegment(App.Vector(50, 50, 0), App.Vector(0, 50, 0)), False)
        sk_unres.addGeometry(Part.LineSegment(App.Vector(0, 50, 0), App.Vector(0, 0, 0)), False)
        for i in range(4):
            sk_unres.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        dw = sk_unres.addConstraint(Sketcher.Constraint("Distance", 0, 50.0))
        doc.recompute()
        sk_unres.setExpression(f"Constraints[{dw}]", "NonExistentVar.Width")
        with self.assertRaises(ValueError) as ctx:
            capture_section_sketch(sk_unres)
        self.assertIn("unresolved expression", str(ctx.exception).lower())

        # None input
        with self.assertRaises(ValueError):
            capture_section_sketch(None)

    # 12. Save section asset, close BOTH docs, reopen ONLY asset, edit & persist
    def test_save_section_asset_standalone_reopen_and_edit(self):
        lib_root = self._new_temp_dir("ff_lib_root_")
        doc = self._new_doc("SaveAssetSourceDoc")
        s, w, h = self._create_rect_sketch(doc, "MyCustomSection", 250.0, 100.0)

        # Add VarSet
        v = doc.addObject("App::VarSet", "Vars")
        v.addProperty("App::PropertyLength", "Ancho")
        v.Ancho = App.Units.Quantity("250 mm")
        s.setExpression(f"Constraints[{w}]", "Vars.Ancho")
        doc.recompute()

        meta = save_section_asset(lib_root, s, name="Section")
        self.assertIn("asset_path", meta)
        self.assertIn("object_name", meta)
        self.assertIn("asset_id", meta)
        self.assertTrue(meta["asset_path"].startswith("sections/"))
        self.assertFalse(os.path.isabs(meta["asset_path"]))

        full_asset_path = os.path.join(lib_root, meta["asset_path"])
        self.assertTrue(os.path.isfile(full_asset_path))

        # Close ALL documents in FreeCAD
        for name in list(App.listDocuments().keys()):
            App.closeDocument(name)
        self.assertEqual(len(App.listDocuments()), 0)

        # Reopen ONLY the saved asset
        reopened_doc = App.openDocument(full_asset_path)
        self.doc_names.append(reopened_doc.Name)
        self.assertEqual(len(App.listDocuments()), 1)

        section_obj = reopened_doc.getObject("Section")
        self.assertIsNotNone(section_obj)
        self.assertEqual(len(section_obj.OutList), 0)
        self.assertEqual(len(section_obj.ExternalGeometry), 0)
        self.assertEqual(len(section_obj.ExpressionEngine), 0)
        self.assertEqual(section_obj.solve(), 0)

        # Edit width to 320 mm
        section_obj.setDatum(w, App.Units.Quantity("320 mm"))
        reopened_doc.recompute()
        self.assertEqual(section_obj.solve(), 0)
        face = build_custom_section_face(section_obj)
        self.assertAlmostEqual(face.Area, 320.0 * 100.0, places=4)

        # Save and close
        reopened_doc.save()
        App.closeDocument(reopened_doc.Name)
        self.assertEqual(len(App.listDocuments()), 0)

        # Reopen again and check persistence
        reopened_doc2 = App.openDocument(full_asset_path)
        self.doc_names.append(reopened_doc2.Name)
        q = reopened_doc2.getObject("Section")
        self.assertAlmostEqual(q.getDatum(w).Value, 320.0, places=4)
        face2 = build_custom_section_face(q)
        self.assertAlmostEqual(face2.Area, 320.0 * 100.0, places=4)

    # 13. Confinement, symlink escape rejection, collision guard, and cleanup
    def test_save_section_asset_confinement_and_symlink_rejection(self):
        lib_root = self._new_temp_dir("ff_confinement_lib_")
        outside_dir = self._new_temp_dir("ff_outside_")
        doc = self._new_doc("ConfinementDoc")
        s, w, h = self._create_rect_sketch(doc, "ConfSection", 100.0, 50.0)

        # 1. sections is symlink escaping lib_root
        sections_symlink = os.path.join(lib_root, "sections")
        os.symlink(outside_dir, sections_symlink)
        with self.assertRaises(ValueError) as ctx:
            save_section_asset(lib_root, s)
        self.assertIn("symlink escaping", str(ctx.exception).lower())
        os.unlink(sections_symlink)

        # 2. Non-existent library root
        with self.assertRaises(ValueError):
            save_section_asset(os.path.join(lib_root, "non_existent"), s)

        # 3. Successful save creates sections/ and asset
        meta = save_section_asset(lib_root, s)
        asset_file = os.path.join(lib_root, meta["asset_path"])
        self.assertTrue(os.path.isfile(asset_file))

        # 4. No temporary files or workspaces left behind in sections/
        sections_dir = os.path.join(lib_root, "sections")
        files = os.listdir(sections_dir)
        temp_files = [f for f in files if f.startswith(".workspace_") or f.startswith(".asset_tmp_")]
        self.assertEqual(temp_files, [])

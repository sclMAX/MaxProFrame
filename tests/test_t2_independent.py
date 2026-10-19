import hashlib
import math
import os
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import Part
import Sketcher

import freecad.maxproframe.section_capture as cap
from freecad.maxproframe.custom_section_geometry import build_custom_section_face as face


def print(*args, **kw):
    os.write(1, (" ".join(map(str, args)) + "\n").encode())


def rect(doc):
    s = doc.addObject("Sketcher::SketchObject", "Section")
    p = [(0, 0), (100, 0), (100, 50), (0, 50)]
    for a, b in zip(p, p[1:] + p[:1]):
        s.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
    for i in range(4):
        s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    for i in (0, 2):
        s.addConstraint(Sketcher.Constraint("Horizontal", i))
    for i in (1, 3):
        s.addConstraint(Sketcher.Constraint("Vertical", i))
    s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
    w = s.addConstraint(Sketcher.Constraint("Distance", 0, 100.0))
    h = s.addConstraint(Sketcher.Constraint("Distance", 1, 50.0))
    doc.recompute()
    return s, w, h


def snap(s):
    d = s.Document
    return dict(
        geometry=[g.toShape().exportBrepToString() for g in s.Geometry],
        constraints=[
            (c.Type, c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos, c.Value, c.Name)
            for c in s.Constraints
        ],
        placement=str(s.Placement),
        expressions=list(s.ExpressionEngine),
        state=list(s.State),
        docstate=str(getattr(d, "State", None)),
        modified=str(getattr(d, "Modified", None)),
        undo=str(getattr(d, "UndoCount", None)),
    )


class Independent(unittest.TestCase):
    def setUp(self):
        self.d = App.newDocument("IndependentSource")

    def tearDown(self):
        for n in list(App.listDocuments()):
            App.closeDocument(n)

    def test_named_forward_formula_and_metadata(self):
        s, w, h = rect(self.d)
        s.renameConstraint(w, "Width")
        s.renameConstraint(h, "Height")
        s.setExpression("Constraints.Width", "Constraints.Height * 2")
        r = s.addConstraint(Sketcher.Constraint("Distance", 0, 1, 1, 2, 111.8))
        s.setDriving(r, False)
        a = s.addConstraint(Sketcher.Constraint("Distance", 2, 100.0))
        s.setActive(a, False)
        self.d.recompute()
        before = snap(s)
        c = cap.capture_section_sketch(s)
        print("NAMED_ENGINES", list(s.ExpressionEngine), list(c.ExpressionEngine))
        self.assertEqual(before, snap(s), "source mutated by capture")
        s.setDatum(h, App.Units.Quantity("60 mm"))
        self.d.recompute()
        print("NATIVE_NAMED_CONTROL", s.getDatum(w).Value)
        s.setDatum(h, App.Units.Quantity("50 mm"))
        self.d.recompute()
        post_control = snap(s)
        self.assertFalse(c.getDriving(r))
        self.assertFalse(c.getActive(a))
        self.assertEqual(c.Constraints[w].Name, "Width")
        c.setDatum(h, App.Units.Quantity("60 mm"))
        c.Document.recompute()
        self.assertAlmostEqual(c.getDatum(w).Value, 120.0)
        self.assertEqual(post_control, snap(s), "source mutated by captured-copy edit")

    def test_cross_document_formula_freezes(self):
        s, w, h = rect(self.d)
        params = App.newDocument("Parameters")
        v = params.addObject("App::VarSet", "Vars")
        v.addProperty("App::PropertyLength", "Width")
        v.Width = 100
        params.recompute()
        params.saveAs(os.path.join(tempfile.mkdtemp(), "parameters.FCStd"))
        self.d.saveAs(os.path.join(tempfile.mkdtemp(), "source.FCStd"))
        s.setExpression("Constraints[%d]" % w, params.Name + "#Vars.Width * 1")
        self.d.recompute()
        t = App.newDocument("CallerTarget")
        keep = t.addObject("App::FeaturePython", "Keep")
        before = snap(s)
        old = [o.Name for o in t.Objects]
        try:
            c = cap.capture_section_sketch(s, t)
        except Exception as e:
            print(
                "CROSSDOC_FAILURE",
                repr(e),
                "target_objects",
                [o.Name for o in t.Objects],
                "dependencies",
                [(o.Name, [x.Name for x in o.OutList], list(getattr(o, "ExpressionEngine", []))) for o in t.Objects],
                flush=True,
            )
            self.assertEqual(old, [o.Name for o in t.Objects], "failed capture leaked partial sketch")
            raise
        self.addCleanup(self.assertEqual, before, snap(s))
        self.assertFalse(c.ExpressionEngine)
        self.assertFalse(c.OutList)
        p = os.path.join(tempfile.mkdtemp(), "asset.FCStd")
        t.saveAs(p)
        for n in list(App.listDocuments()):
            App.closeDocument(n)
        d = App.openDocument(p)
        c = d.getObject("Section")
        self.assertFalse(c.OutList)
        c.setDatum(w, App.Units.Quantity("125 mm"))
        d.recompute()
        self.assertEqual(c.solve(), 0)

    def test_source_clean_and_pending_state(self):
        s, w, h = rect(self.d)
        self.d.UndoMode = 1
        self.d.saveAs(os.path.join(tempfile.mkdtemp(), "source.FCStd"))
        b = snap(s)
        cap.capture_section_sketch(s)
        a = snap(s)
        print("CLEAN_SOURCE_CHANGED", [k for k in b if b[k] != a[k]], flush=True)
        self.addCleanup(self.assertEqual, b, a)
        s.touch()
        b = snap(s)
        cap.capture_section_sketch(s)
        a = snap(s)
        print("TOUCHED_SOURCE_CHANGED", [k for k in b if b[k] != a[k]], flush=True)
        self.addCleanup(self.assertEqual, b, a)

    def test_saved_object_name(self):
        s, w, h = rect(self.d)
        for name in ("Mi sección 40×20", "Section With Spaces", "A-B"):
            with self.subTest(name=name):
                root = tempfile.mkdtemp()
                m = cap.save_section_asset(root, s, name)
                d = App.openDocument(os.path.join(root, m["asset_path"]))
                print("METADATA_NAME", repr(name), m["object_name"], [o.Name for o in d.Objects], flush=True)
                self.assertIsNotNone(d.getObject(m["object_name"]))
                App.closeDocument(d.Name)

    def test_native_failure_cleanup_owns_only_its_file(self):
        s, w, h = rect(self.d)
        b = snap(s)
        root = tempfile.mkdtemp()
        newdoc = App.newDocument
        sent = []

        class FailureDoc:
            def __init__(self, d):
                self.d = d

            def __getattr__(self, n):
                return getattr(self.d, n)

            def saveAs(self, p):
                sections_dir = os.path.join(root, "sections")
                stem = os.path.splitext(os.path.basename(p))[0]
                unrelated = os.path.join(sections_dir, stem + "_unrelated.txt")
                open(unrelated, "wb").write(b"KEEP")
                sent.append(unrelated)
                open(p, "wb").write(b"partial")
                raise OSError("injected native disk write failure")

        def new(*args, **kw):
            d = newdoc(*args, **kw)
            return FailureDoc(d) if args and args[0] == "SectionAsset" else d

        with patch.object(cap.App, "newDocument", new):
            with self.assertRaisesRegex(OSError, "injected native disk write failure"):
                cap.save_section_asset(root, s)
        self.addCleanup(self.assertEqual, b, snap(s))
        print(
            "FAILURE_CLEANUP",
            os.listdir(os.path.join(root, "sections")),
            "sentinel_exists",
            os.path.exists(sent[0]),
            flush=True,
        )
        self.assertTrue(os.path.isfile(sent[0]), "unrelated prefix-sharing file deleted")
        self.assertEqual(open(sent[0], "rb").read(), b"KEEP")

    def test_symlink_sections_and_root_alias(self):
        s, w, h = rect(self.d)
        root = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        p = os.path.join(outside, "sentinel")
        open(p, "wb").write(b"KEEP")
        before = hashlib.sha256(open(p, "rb").read()).hexdigest()
        os.symlink(outside, os.path.join(root, "sections"))
        with self.assertRaisesRegex(ValueError, "symlink escaping"):
            cap.save_section_asset(root, s)
        self.assertEqual(before, hashlib.sha256(open(p, "rb").read()).hexdigest())
        self.assertEqual(os.listdir(outside), ["sentinel"])
        root2 = tempfile.mkdtemp()
        alias = os.path.join(tempfile.mkdtemp(), "alias")
        os.symlink(root2, alias)
        m = cap.save_section_asset(alias, s)
        self.assertTrue(os.path.isfile(os.path.join(root2, m["asset_path"])))

    def test_offcenter_hole_bidirectional_difference(self):
        s = self.d.addObject("Sketcher::SketchObject", "Hole")
        s.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 50), False)
        s.addGeometry(Part.Circle(App.Vector(12, 8, 0), App.Vector(0, 0, 1), 7), False)
        self.d.recompute()
        c = cap.capture_section_sketch(s)
        a, b = face(s), face(c)
        self.assertLess(a.cut(b).Area + b.cut(a).Area, 1e-7)

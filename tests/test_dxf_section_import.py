"""Synthetic public-interface tests; no proprietary drawings are embedded."""

import hashlib
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App
import Import

from freecad.maxproframe.custom_section_geometry import build_custom_section_face
from freecad.maxproframe.dxf_section_import import import_dxf_section, inspect_dxf


def pairs(items):
    return "".join(f"{code}\n{value}\n" for code, value in items)


def poly(points, classic=False, flags=1, elevation=0):
    if classic:
        data = [(0, "POLYLINE"), (8, "0"), (66, 1), (70, flags), (10, 0), (20, 0), (30, elevation)]
        for x, y, *bulge in points:
            data += [(0, "VERTEX"), (8, "0"), (10, x), (20, y), (30, 0), (42, bulge[0] if bulge else 0)]
        return data + [(0, "SEQEND")]
    data = [(0, "LWPOLYLINE"), (8, "0"), (90, len(points)), (70, flags), (38, elevation)]
    for x, y, *bulge in points:
        data += [(10, x), (20, y), (42, bulge[0] if bulge else 0)]
    return data


RECT = [(10, 20), (18, 20), (18, 24), (10, 24)]
PARAMETER_SUFFIX = {
    "Boolean": "Bool",
    "Integer": "Int",
    "Unsigned": "Unsigned",
    "Unsigned Long": "Unsigned",
    "Float": "Float",
    "String": "String",
}


def restore_preferences(group, contents):
    for kind, key, _ in group.GetContents() or ():
        getattr(group, "Rem" + PARAMETER_SUFFIX[kind])(key)
    for kind, key, value in contents:
        getattr(group, "Set" + PARAMETER_SUFFIX[kind])(key, value)


def preference_values(group):
    return sorted(group.GetContents() or ())


class TestDXFSectionImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mpf_dxf_")
        self.addCleanup(self.tmp.cleanup)
        self.doc = App.newDocument("DXFCaller")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name) if self.doc.Name in App.listDocuments() else None)
        self.doc.addObject("App::FeaturePython", "Sentinel")
        self.docs = set(App.listDocuments())
        self.prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
        self.original_prefs = preference_values(self.prefs)
        self.addCleanup(restore_preferences, self.prefs, self.original_prefs)
        self.prefs.SetInt("DxfImportMode", 0)
        self.prefs.SetBool("dxfUseLegacyImporter", True)
        self.prefs.SetFloat("dxfScaling", 7.0)
        self.prefs.SetBool("dxfCreatePart", False)
        self.before_prefs = preference_values(self.prefs)
        self.import_prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Import")
        self.before_import_prefs = preference_values(self.import_prefs)
        self.addCleanup(restore_preferences, self.import_prefs, self.before_import_prefs)
        self.import_prefs.SetFloat("Scale", 13.0)
        self.import_prefs.SetBool("JoinGeometry", True)
        self.import_prefs.SetBool("ImportHiddenBlocks", True)
        self.hostile_import_prefs = preference_values(self.import_prefs)

    def source(self, entities, units=4, blocks=None, header=None):
        path = Path(self.tmp.name) / "section.dxf"
        data = [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, "AC1015")]
        data += header or []
        data += [(9, "$INSUNITS"), (70, units), (0, "ENDSEC")]
        # Complete table/layer scaffolding: native readers may dereference the
        # entity's layer rather than accepting the old malformed minimal input.
        data += [
            (0, "SECTION"),
            (2, "TABLES"),
            (0, "TABLE"),
            (2, "LTYPE"),
            (70, 1),
            (0, "LTYPE"),
            (2, "CONTINUOUS"),
            (70, 0),
            (3, "Solid line"),
            (72, 65),
            (73, 0),
            (40, 0),
            (0, "ENDTAB"),
            (0, "TABLE"),
            (2, "LAYER"),
            (70, 1),
            (0, "LAYER"),
            (2, "0"),
            (70, 0),
            (62, 7),
            (6, "CONTINUOUS"),
            (0, "ENDTAB"),
            (0, "ENDSEC"),
        ]
        data += [(0, "SECTION"), (2, "BLOCKS")] + (blocks or []) + [(0, "ENDSEC")]
        data += [(0, "SECTION"), (2, "ENTITIES")] + entities + [(0, "ENDSEC"), (0, "EOF")]
        path.write_text(pairs(data), encoding="ascii")
        self.path = path
        self.digest = hashlib.sha256(path.read_bytes()).digest()
        return path

    def unchanged(self, objects=("Sentinel",)):
        self.assertEqual(set(App.listDocuments()), self.docs)
        self.assertEqual(App.ActiveDocument.Name, self.doc.Name)
        self.assertEqual(tuple(o.Name for o in self.doc.Objects), objects)
        self.assertEqual(preference_values(self.prefs), self.before_prefs)
        self.assertEqual(preference_values(self.import_prefs), self.hostile_import_prefs)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), self.digest)

    def reject(self, data, pattern, **kwargs):
        path = self.source(data)
        with self.assertRaisesRegex(ValueError, pattern):
            import_dxf_section(path, self.doc, **kwargs)
        self.unchanged()

    def test_header_string_variables_are_metadata(self):
        # Synthetic fixture: each variable owns its own code-2 string. None is
        # another SECTION name, drawing entity, or referenced modelspace block.
        header = [(9, "$UCSNAME"), (2, ""), (9, "$PUCSNAME"), (2, ""), (9, "$UCSBASE"), (2, "")]
        path = self.source(poly(RECT), header=header)
        info = inspect_dxf(path)
        self.assertEqual(info, {"insunits": 4, "unit_mm": 1.0, "contour_vertices": (4,)})
        sketch = import_dxf_section(path, self.doc, unit_override="mm")
        self.assertEqual(sketch.GeometryCount, 4)
        self.assertAlmostEqual(build_custom_section_face(sketch).Area, 32)
        self.assertEqual(sketch.solve(), 0)
        self.assertTrue(sketch.FullyConstrained)
        self.assertTrue(sketch.Placement.isIdentity())
        b = sketch.Shape.BoundBox
        self.assertAlmostEqual(b.XMin + b.XMax, 0)
        self.assertAlmostEqual(b.YMin + b.YMax, 0)
        self.unchanged(("Sentinel", sketch.Name))

    def test_section_name_can_precede_section_metadata(self):
        path = self.source(poly(RECT))
        # Synthetic legal ACDSDATA section header, without proprietary content.
        metadata = [(0, "SECTION"), (2, "ACDSDATA"), (70, 2), (71, 2), (0, "ENDSEC")]
        path.write_text(path.read_text().replace(pairs([(0, "EOF")]), pairs(metadata + [(0, "EOF")])))
        self.digest = hashlib.sha256(path.read_bytes()).digest()
        self.assertEqual(inspect_dxf(path), {"insunits": 4, "unit_mm": 1.0, "contour_vertices": (4,)})
        sketch = import_dxf_section(path, self.doc, unit_override="mm")
        self.assertEqual(sketch.GeometryCount, 4)
        self.assertAlmostEqual(build_custom_section_face(sketch).Area, 32)
        self.assertEqual(sketch.solve(), 0)
        self.assertTrue(sketch.FullyConstrained)
        self.assertTrue(sketch.Placement.isIdentity())
        self.unchanged(("Sentinel", sketch.Name))

    def test_duplicate_section_and_geometry_fields_still_reject(self):
        path = self.source(poly(RECT))
        path.write_text(path.read_text().replace("2\nHEADER\n", "2\nHEADER\n2\nHEADER\n", 1))
        self.digest = hashlib.sha256(path.read_bytes()).digest()
        with self.assertRaisesRegex(ValueError, "Duplicate DXF field 2"):
            import_dxf_section(path, self.doc)
        self.unchanged()
        self.reject(poly(RECT) + [(70, 1)], "Duplicate DXF field 70")

    def test_solid_hollow_classic_orientation_and_fixed_geometry(self):
        for classic, hollow in ((False, False), (False, True), (True, False)):
            with self.subTest(classic=classic, hollow=hollow):
                data = poly(RECT, classic)
                if hollow:
                    data += poly([(12, 21), (16, 21), (16, 23), (12, 23)])
                path = self.source(data)
                sketch = import_dxf_section(path, self.doc)
                face = build_custom_section_face(sketch)
                self.assertAlmostEqual(face.Area, 24 if hollow else 32, places=6)
                self.assertEqual(len(face.Wires), 2 if hollow else 1)
                self.assertEqual(sketch.solve(), 0)
                self.assertTrue(sketch.FullyConstrained)
                self.assertTrue(sketch.Placement.isIdentity())
                self.assertEqual(len(sketch.ExternalGeometry), 0)
                self.assertEqual(len(sketch.OutList), 0)
                corners = {(round(v.Point.x, 6), round(v.Point.y, 6)) for v in sketch.Shape.Vertexes}
                self.assertTrue({(-4, -2), (4, -2), (4, 2), (-4, 2)} <= corners)
                self.assertAlmostEqual(sketch.Shape.BoundBox.YLength, 4)
                self.unchanged(("Sentinel", sketch.Name))
                self.doc.removeObject(sketch.Name)

    def test_asymmetric_orientation(self):
        path = self.source(poly([(10, 20), (18, 20), (12, 24)]))
        sketch = import_dxf_section(path, self.doc)
        self.assertEqual(
            {(round(v.Point.x, 6), round(v.Point.y, 6)) for v in sketch.Shape.Vertexes}, {(-4, -2), (4, -2), (-2, 2)}
        )
        self.assertAlmostEqual(build_custom_section_face(sketch).Area, 16)
        self.unchanged(("Sentinel", sketch.Name))

    def test_arc_true_bounds_and_area(self):
        # Major arc has extrema beyond both endpoint coordinates.
        path = self.source(poly([(10, 20, 2), (18, 20), (18, 24), (10, 24)]))
        reader = Import.readDXF
        source_bounds = []

        def observe(filename):
            stats = reader(filename)
            for obj in App.ActiveDocument.Objects:
                if hasattr(obj, "Shape") and not obj.Shape.isNull():
                    bounds = obj.Shape.optimalBoundingBox(False, False)
                    factor = stats["finalScalingFactor"]
                    source_bounds.append(
                        tuple(v / factor for v in (bounds.XMin, bounds.YMin, bounds.XMax, bounds.YMax))
                    )
            return stats

        with patch.object(Import, "readDXF", side_effect=observe):
            sketch = import_dxf_section(path, self.doc)
        # Chord=8, bulge=2: radius=8*(1+4)/(4*2)=5,
        # center=(14,17), sweep=4*atan(2). True bounds=(9,12,19,24),
        # so the only requested translation is (-14,-18).
        for bounds in source_bounds:
            for actual, expected in zip(bounds, (9, 12, 19, 24)):
                self.assertAlmostEqual(actual, expected, places=7)
        self.assertEqual(len(source_bounds), 1)
        b = sketch.Shape.optimalBoundingBox(False, False)
        for actual, expected in zip((b.XMin, b.YMin, b.XMax, b.YMax), (-5, -6, 5, 6)):
            self.assertAlmostEqual(actual, expected, places=7)
        self.assertAlmostEqual(b.XMin + b.XMax, 0, places=6)
        self.assertAlmostEqual(b.YMin + b.YMax, 0, places=6)
        self.assertAlmostEqual(b.ZMin, 0, places=6)
        theta = 4 * math.atan(2)
        self.assertAlmostEqual(build_custom_section_face(sketch).Area, 32 + 12.5 * (theta - math.sin(theta)), places=5)
        self.assertAlmostEqual(b.XLength, 10, places=5)
        self.assertTrue(sketch.FullyConstrained)
        self.assertEqual(sketch.solve(), 0)
        self.assertTrue(sketch.Placement.isIdentity())
        self.assertEqual(sketch.GeometryCount, 4)
        arcs = [g for g in sketch.Geometry if hasattr(g, "Radius")]
        self.assertEqual(len(arcs), 1)
        arc = arcs[0]
        self.assertAlmostEqual(arc.Radius, 5, places=7)
        self.assertAlmostEqual(arc.Center.x, 0, places=7)
        self.assertAlmostEqual(arc.Center.y, -1, places=7)
        self.assertAlmostEqual(arc.LastParameter - arc.FirstParameter, theta, places=7)
        self.assertEqual(
            {(round(v.Point.x, 7), round(v.Point.y, 7)) for v in sketch.Shape.Vertexes},
            {(-4, 2), (4, 2), (4, 6), (-4, 6)},
        )
        self.unchanged(("Sentinel", sketch.Name))

    def test_units_and_override(self):
        for units, override, scale in ((4, None, 1), (1, None, 25.4), (0, "inch", 25.4), (1, "mm", 1)):
            with self.subTest(units=units, override=override):
                path = self.source(poly(RECT), units)
                info = inspect_dxf(path)
                self.assertEqual(info["insunits"], units)
                sketch = import_dxf_section(path, self.doc, unit_override=override)
                self.assertAlmostEqual(sketch.Shape.BoundBox.XLength, 8 * scale, places=5)
                self.unchanged(("Sentinel", sketch.Name))
                self.doc.removeObject(sketch.Name)
        path = self.source(poly(RECT), 0)
        with self.assertRaisesRegex(ValueError, "unit"):
            import_dxf_section(path, self.doc)
        self.unchanged()

    def test_forbidden_actual_entities(self):
        for kind in ("TEXT", "DIMENSION", "LINE", "INSERT", "SPLINE", "CIRCLE"):
            with self.subTest(kind=kind):
                self.reject(poly(RECT) + [(0, kind)], "Unsupported DXF drawing entity: " + kind)
        self.reject(poly(RECT, classic=True, flags=9), "closed 2D")

    def test_unused_block_is_not_geometry(self):
        blocks = [(0, "BLOCK"), (2, "Unused"), (70, 0), (10, 0), (20, 0), (30, 0)]
        blocks += (
            [(0, "TEXT"), (8, "0"), (10, 0), (20, 0), (30, 0), (40, 1), (1, "unused")]
            + poly(RECT)
            + [(0, "ENDBLK"), (8, "0")]
        )
        path = self.source(poly(RECT), blocks=blocks)
        sketch = import_dxf_section(path, self.doc)
        self.assertEqual(sketch.GeometryCount, 4)
        self.assertAlmostEqual(build_custom_section_face(sketch).Area, 32)
        self.unchanged(("Sentinel", sketch.Name))

    def test_invalid_geometry_rolls_back(self):
        cases = [
            poly(RECT, flags=0),
            poly(RECT, elevation=1),
            poly([(0, 0), (4, 4), (0, 4), (4, 0)]),
            poly(RECT) + poly([(30, 20), (38, 20), (38, 24), (30, 24)]),
            poly(RECT) + poly([(10, 21), (12, 21), (12, 23), (10, 23)]),
            poly(RECT) + poly([(8, 21), (12, 21), (12, 23), (8, 23)]),
            poly([(0, 0), ("nan", 0), (2, 2)]),
            poly(RECT)
            + poly([(11, 21), (17, 21), (17, 23), (11, 23)])
            + poly([(12, 21.5), (13, 21.5), (13, 22), (12, 22)]),
        ]
        patterns = [
            "closed 2D",
            "2D in XY",
            "self-intersect|invalid|no valid|zero|face creation",
            "connected material region",
            "intersect|cross",
            "intersect|cross",
            "finite",
            "connected material region",
        ]
        for data, pattern in zip(cases, patterns):
            with self.subTest(data=data):
                self.reject(data, pattern)

    def test_exact_preferences_on_success_and_native_exception(self):
        path = self.source(poly(RECT))
        reader = Import.readDXF
        for absent in (False, True):
            if absent:
                self.prefs.RemInt("DxfImportMode")
                self.prefs.RemBool("dxfUseLegacyImporter")
            before = preference_values(self.prefs)
            self.before_prefs = before

            def observe(filename):
                self.assertEqual(self.prefs.GetInt("DxfImportMode"), 2)
                self.assertFalse(self.prefs.GetBool("dxfUseLegacyImporter"))
                # Unrelated preferences remain present even DURING import.
                self.assertEqual(self.prefs.GetFloat("dxfScaling"), 7.0)
                self.assertEqual(preference_values(self.import_prefs), self.hostile_import_prefs)
                return reader(filename)

            with patch.object(Import, "readDXF", side_effect=observe):
                sketch = import_dxf_section(path, self.doc)
            self.unchanged(("Sentinel", sketch.Name))
            self.doc.removeObject(sketch.Name)
            with patch.object(Import, "readDXF", side_effect=RuntimeError("native failure")):
                with self.assertRaisesRegex(ValueError, "native failure"):
                    import_dxf_section(path, self.doc)
            self.unchanged()

    def test_missing_native_api_and_import_error(self):
        path = self.source(poly(RECT))
        with patch.object(Import, "readDXF", None):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                import_dxf_section(path, self.doc)
        self.unchanged()
        with patch.object(Import, "readDXF", side_effect=RuntimeError("native failure")):
            with self.assertRaisesRegex(ValueError, "native failure"):
                import_dxf_section(path, self.doc)
        self.unchanged()

    def test_native_differential_and_typed_routing_restore(self):
        path = self.source(poly(RECT))
        reader = Import.readDXF

        def native():
            doc = App.newDocument("NativeDifferential")
            try:
                reader(str(path))
                doc.recompute()
                return [(o.TypeId, o.Name, o.Shape.exportBrepToString()) for o in doc.Objects if hasattr(o, "Shape")]
            finally:
                App.closeDocument(doc.Name)
                App.setActiveDocument(self.doc.Name)

        before = native()
        other = App.newDocument("OtherActive")
        other.addObject("App::FeaturePython", "OtherSentinel")
        docs = set(App.listDocuments())
        try:
            sketch = import_dxf_section(path, self.doc)
            self.assertEqual(sketch.Document, self.doc)
            self.assertEqual(App.ActiveDocument.Name, other.Name)
            self.assertEqual(set(App.listDocuments()), docs)
            self.assertEqual([o.Name for o in other.Objects], ["OtherSentinel"])
            self.doc.removeObject(sketch.Name)
        finally:
            App.closeDocument(other.Name)
            App.setActiveDocument(self.doc.Name)
        self.assertEqual(native(), before)
        self.unchanged()

        for suffix, value in (("String", "unusual"), ("Float", 1.25), ("Unsigned", 7)):
            for kind, key, _ in preference_values(self.prefs):
                if key in ("DxfImportMode", "dxfUseLegacyImporter"):
                    getattr(self.prefs, "Rem" + PARAMETER_SUFFIX[kind])(key)
            for key in ("DxfImportMode", "dxfUseLegacyImporter"):
                getattr(self.prefs, "Set" + suffix)(key, value)
            self.before_prefs = preference_values(self.prefs)
            sketch = import_dxf_section(path, self.doc)
            self.unchanged(("Sentinel", sketch.Name))
            self.doc.removeObject(sketch.Name)

            def failure(filename):
                reader(filename)
                raise RuntimeError("after native creation")

            with patch.object(Import, "readDXF", side_effect=failure):
                with self.assertRaisesRegex(ValueError, "^Native DXF section import failed: after native creation$"):
                    import_dxf_section(path, self.doc)
            self.unchanged()

        def joined(filename):
            stats = reader(filename)
            stats["importSettings"]["Join geometry"] = "Yes"
            return stats

        with patch.object(Import, "readDXF", side_effect=joined):
            with self.assertRaisesRegex(ValueError, "^Unsupported native DXF import setting: Join geometry$"):
                import_dxf_section(path, self.doc)
        self.unchanged()

    def test_binary_is_explicitly_unsupported(self):
        path = self.source(poly(RECT))
        path.write_bytes(b"AutoCAD Binary DXF\r\n\x1a\x00")
        self.digest = hashlib.sha256(path.read_bytes()).digest()
        with self.assertRaisesRegex(ValueError, "binary"):
            import_dxf_section(path, self.doc)
        self.unchanged()

"""Strict, headless DXF section import using FreeCAD's native geometry reader."""

import math
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import FreeCAD as App
import Import
import Part
import Sketcher

from .custom_section_geometry import build_custom_section_face

_UNIT_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}
_OVERRIDE_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4, "ft": 304.8}


def _records(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"AutoCAD Binary DXF") or b"\x00" in raw:
        raise ValueError("Unsupported binary DXF; export an ASCII DXF")
    lines = raw.decode("latin1").splitlines()
    if len(lines) % 2:
        raise ValueError("Malformed ASCII DXF group pairs")
    try:
        pairs = [(int(lines[i].strip()), lines[i + 1].strip()) for i in range(0, len(lines), 2)]
    except ValueError as exc:
        raise ValueError("Malformed ASCII DXF group code") from exc
    records = []
    for code, value in pairs:
        if code == 0:
            records.append((value, []))
        elif records:
            records[-1][1].append((code, value))
        else:
            raise ValueError("Malformed DXF record")
    return records


def _value(fields, code, default="0"):
    values = [v for c, v in fields if c == code]
    if len(values) > 1:
        raise ValueError(f"Duplicate DXF field {code}")
    return values[0] if values else default


def _number(fields, code, default="0"):
    value = float(_value(fields, code, default))
    if not math.isfinite(value):
        raise ValueError("DXF geometry must be finite")
    return value


def _flat(fields):
    # Only the ordinary positive-Z OCS is supported; do not silently mirror it.
    for code in (30, 38, 39, 210, 220):
        if _number(fields, code) != 0:
            raise ValueError("DXF section must be 2D in XY at Z=0")
    if _number(fields, 230, "1") != 1:
        raise ValueError("DXF section must use the positive Z normal")
    for code in (40, 41, 43):
        if _number(fields, code) != 0:
            raise ValueError("Wide DXF polylines are unsupported")


def _vertices(fields):
    vertices = []
    for code, value in fields:
        if code == 10:
            vertices.append([(10, value)])
        elif code in (20, 42, 40, 41):
            if not vertices:
                raise ValueError("Malformed DXF vertex")
            vertices[-1].append((code, value))
    for vertex in vertices:
        _number(vertex, 10)
        _number(vertex, 20)
        _number(vertex, 42)
        if not any(c == 20 for c, _ in vertex):
            raise ValueError("Missing DXF vertex Y")
        for code in (40, 41):
            if _number(vertex, code) != 0:
                raise ValueError("Wide DXF polylines are unsupported")
    return len(vertices)


def inspect_dxf(path):
    """Read-only preflight: return INSUNITS, unit_mm (or None), and contour counts.

    The caller must explicitly confirm units before creation in a GUI. Unknown units
    require import_dxf_section's unit_override; this function never guesses units.
    """
    section = None
    units = 0
    entities = []
    saw_entities = False
    for kind, fields in _records(path):
        if kind == "SECTION":
            # HEADER variable payload shares this record until ENDSEC. Its
            # code-2 string values are not additional section-name tags.
            variable_start = next((i for i, (code, _) in enumerate(fields) if code == 9), len(fields))
            section_tags = fields[:variable_start]
            section = _value(section_tags, 2, "")
            # The name must lead the record, but other non-name metadata
            # (for example ACDSDATA's 70/71 tags) may follow it.
            if not section_tags or section_tags[0] != (2, section) or not section:
                raise ValueError("Malformed DXF SECTION name")
            if section != "HEADER" and variable_start != len(fields):
                raise ValueError("DXF header variables outside HEADER section")
            if section == "ENTITIES":
                saw_entities = True
        elif kind == "ENDSEC":
            section = None
        elif section == "ENTITIES":
            entities.append((kind, fields))
        # HEADER variables belong to the SECTION record, not drawing entities.
        if kind == "SECTION" and section == "HEADER":
            for index, (code, value) in enumerate(fields):
                if code == 9 and value == "$INSUNITS":
                    if index + 1 >= len(fields) or fields[index + 1][0] != 70:
                        raise ValueError("Malformed DXF units")
                    units = int(fields[index + 1][1])
    if not saw_entities or not entities:
        raise ValueError("DXF contains no section polylines")
    counts = []
    index = 0
    while index < len(entities):
        kind, fields = entities[index]
        if kind not in ("LWPOLYLINE", "POLYLINE"):
            raise ValueError(f"Unsupported DXF drawing entity: {kind}")
        flags = int(_value(fields, 70))
        if flags not in (1, 129):
            raise ValueError("DXF requires closed 2D polylines")
        if kind == "LWPOLYLINE":
            # Repeated vertex fields are validated individually below.
            _flat([(c, v) for c, v in fields if c not in (40, 41)])
            count = _vertices(fields)
            if int(_value(fields, 90)) != count:
                raise ValueError("DXF vertex count mismatch")
        else:
            _flat(fields)
            count = 0
            index += 1
            while index < len(entities) and entities[index][0] == "VERTEX":
                vertex = entities[index][1]
                _flat(vertex)
                if int(_value(vertex, 70)) != 0:
                    raise ValueError("3D DXF vertices are unsupported")
                _number(vertex, 10)
                _number(vertex, 20)
                _number(vertex, 42)
                count += 1
                index += 1
            if index >= len(entities) or entities[index][0] != "SEQEND":
                raise ValueError("Malformed DXF POLYLINE sequence")
        if count < 2:
            raise ValueError("DXF contour has too few vertices")
        counts.append(count)
        index += 1
    return {"insunits": units, "unit_mm": _UNIT_MM.get(units), "contour_vertices": tuple(counts)}


_PARAMETER_SUFFIX = {
    "Boolean": "Bool",
    "Integer": "Int",
    "Unsigned": "Unsigned",
    "Unsigned Long": "Unsigned",
    "Float": "Float",
    "String": "String",
}


@contextmanager
def _native_defaults():
    # These two routing keys are the settings used by the proven console probe.
    # Do not wipe Draft/Import settings: scaling is corrected from native stats;
    # topology-changing native options are checked explicitly after reading.
    parent = App.ParamGet("User parameter:BaseApp/Preferences/Mod")
    existed = "Draft" in (parent.GetGroups() or ())
    group = parent.GetGroup("Draft")
    keys = {"DxfImportMode": ("Int", 2), "dxfUseLegacyImporter": ("Bool", False)}
    original = [(kind, name, value) for kind, name, value in (group.GetContents() or ()) if name in keys]
    # Resolve every method before changing anything, including restoration.
    for kind, _, _ in original:
        suffix = _PARAMETER_SUFFIX[kind]
        getattr(group, "Set" + suffix)
        getattr(group, "Rem" + suffix)
    try:
        for name, (suffix, value) in keys.items():
            getattr(group, "Set" + suffix)(name, value)
        yield
    finally:
        # Remove only touched keys, including originally absent values. Restore
        # their original stored types, leaving unrelated preferences untouched.
        for kind, name, _ in group.GetContents() or ():
            if name in keys:
                getattr(group, "Rem" + _PARAMETER_SUFFIX[kind])(name)
        for kind, name, value in original:
            getattr(group, "Set" + _PARAMETER_SUFFIX[kind])(name, value)
        if not existed and not group.GetContents() and not group.GetGroups():
            parent.RemGroup("Draft")


def import_dxf_section(path, target_doc, *, unit_override=None, name="ImportedSection"):
    """Create one independent fixed sketch in an explicitly caller-owned document.

    Only the returned sketch is transferred; failure removes it. Native import is
    confined to a temporary document. No library persistence or preferences change.
    unit_override is one of mm, cm, m, inch, ft and overrides the file's INSUNITS.
    """
    active = App.ActiveDocument
    temporary = None
    sketch = None
    try:
        info = inspect_dxf(path)
        scale = info["unit_mm"]
        if unit_override is not None:
            if unit_override not in _OVERRIDE_MM:
                raise ValueError("Unsupported unit override")
            scale = _OVERRIDE_MM[unit_override]
        if scale is None:
            raise ValueError("Unknown DXF units; explicit unit override required")
        if target_doc is None or App.listDocuments().get(target_doc.Name) != target_doc:
            raise ValueError("An open caller-owned target document is required")
        reader = getattr(Import, "readDXF", None)
        if not callable(reader):
            raise ValueError("Native DXF API unsupported in this FreeCAD runtime")
        temporary = App.newDocument("DXFSectionImport")
        # The proven native single-argument API targets the active owned doc.
        # ignore_errors defaults to True: unsupported UNUSED definitions are
        # permitted. Preflight rejects actual unsupported drawing entities, and
        # the contour/segment checks below reject silently omitted geometry.
        with _native_defaults():
            stats = reader(str(path))
        temporary.recompute()
        if not isinstance(stats, dict) or "finalScalingFactor" not in stats:
            raise ValueError("Native DXF scaling API unsupported in this FreeCAD runtime")
        settings = stats.get("importSettings", {})
        for option in ("Join geometry", "Import hidden blocks", "Import layout objects"):
            if settings.get(option) != "No":
                raise ValueError(f"Unsupported native DXF import setting: {option}")
        native_scale = float(stats["finalScalingFactor"])
        if not math.isfinite(native_scale) or native_scale <= 0:
            raise ValueError("Invalid native DXF scaling factor")
        excluded = set()
        pending = [o for o in temporary.Objects if o.Name == "_UnreferencedBlocks"]
        while pending:
            obj = pending.pop()
            if obj.Name not in excluded:
                excluded.add(obj.Name)
                pending.extend(obj.OutList)
        candidates = [
            o for o in temporary.Objects if o.Name not in excluded and hasattr(o, "Shape") and not o.Shape.isNull()
        ]
        # Keep shape-bearing roots only: compounds already contain child geometry.
        selected = [o for o in candidates if not any(parent in candidates for parent in o.InList)]
        shape = Part.makeCompound([o.Shape for o in selected])
        if len(shape.Edges) != sum(info["contour_vertices"]) or sorted(len(w.Edges) for w in shape.Wires) != sorted(
            info["contour_vertices"]
        ):
            raise ValueError("Native DXF import omitted or duplicated polyline segments")
        build_custom_section_face(SimpleNamespace(Shape=shape))
        shape.scale(scale / native_scale)
        # Ignore GUI display triangulation and shape tolerances: centering is
        # defined by the curves themselves, including circular arc extrema.
        bounds = shape.optimalBoundingBox(False, False)
        shape.translate(App.Vector(-(bounds.XMin + bounds.XMax) / 2, -(bounds.YMin + bounds.YMax) / 2, -bounds.ZMin))
        sketch = target_doc.addObject("Sketcher::SketchObject", name)
        for edge in shape.Edges:
            if isinstance(edge.Curve, Part.Line):
                geometry = Part.LineSegment(edge.Vertexes[0].Point, edge.Vertexes[-1].Point)
            elif isinstance(edge.Curve, Part.Circle):
                geometry = Part.ArcOfCircle(edge.Curve, edge.FirstParameter, edge.LastParameter)
            else:
                raise ValueError("Native DXF produced unsupported curve geometry")
            index = sketch.addGeometry(geometry, False)
            sketch.addConstraint(Sketcher.Constraint("Block", index))
        target_doc.recompute()
        if sketch.solve() != 0 or not sketch.FullyConstrained:
            raise ValueError("Imported section could not be fully fixed")
        build_custom_section_face(sketch)
        return sketch
    except Exception as exc:
        if sketch is not None:
            target_doc.removeObject(sketch.Name)
            target_doc.recompute()
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Native DXF section import failed: {exc}") from exc
    finally:
        if temporary is not None:
            App.closeDocument(temporary.Name)
        App.setActiveDocument(active.Name if active is not None else "")

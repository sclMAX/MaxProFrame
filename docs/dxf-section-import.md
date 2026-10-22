# Import a strict DXF section as a fixed sketch

The core API creates an independent fixed sketch without saving to the library.
Synthetic tests and both authorized original drawings pass on FreeCAD 26.3rc2 and
1.1.4. Independent core verification passed, including preference restoration and
native-import preservation. Full-suite checks and UI integration remain separate;
existing section capture and library persistence are unchanged.

## Public API

```python
from freecad.maxproframe.dxf_section_import import inspect_dxf, import_dxf_section

metadata = inspect_dxf(path)
# UI must confirm the displayed units before creation.
sketch = import_dxf_section(path, caller_document, unit_override="mm")
```

`inspect_dxf` is read-only and returns `insunits`, `unit_mm` (None for unknown
units), and `contour_vertices`. `import_dxf_section` requires an explicitly owned,
open target document. On success it returns one independent, identity-placement,
fully fixed native sketch. The caller owns that sketch and must remove it on review
cancel. Neither function saves or mutates the library.

Supported override names are `mm`, `cm`, `m`, `inch`, and `ft`. Without an override,
known INSUNITS are inches, feet, millimeters, centimeters, and meters. Other units
require an explicit override; they are never guessed as mm. Normalization divides
the requested scale by the native reported scaling factor, avoiding double INSUNITS
conversion. Actual geometry is translated by its true bounding-box midpoint,
including circular arc extrema; Placement remains identity.

## Input boundary

- ASCII DXF structure only; binary DXF has an explicit unsupported error.
- Closed LWPOLYLINE and classic 2D POLYLINE contours, including bulge arcs.
- Exactly one connected material region, optionally with holes; no touching,
  intersections, disconnected regions, or nested material islands.
- Actual drawing entities other than those polylines are rejected, even if the
  native reader would silently skip them. Metadata and unused block definitions
  are not drawing geometry.
- XY at Z=0 with a positive-Z normal, zero thickness and zero polyline width.
- No repair, curve approximation, orientation change, or source-file modification.

The importer reuses `build_custom_section_face` for material topology validation.
Native import runs in an owned temporary document, excluding the
`_UnreferencedBlocks` subtree and shape-child duplicates. The proven single-argument
`Import.readDXF(path)` targets that active temporary document. Its default ignored
errors allow unsupported unused definitions; source preflight rejects unsupported
actual entities, while native contour and segment counts reject omissions.

## Preference and document ownership

Call synchronously on FreeCAD's document-owning thread. Only Draft's
`DxfImportMode` and `dxfUseLegacyImporter` routing keys are temporarily adjusted.
Original values, stored types, and absence are restored in `finally`; unrelated Draft
and Import preferences are not cleared. Explicit parameter-type mappings handle
Boolean/Bool, Integer/Int and Unsigned Long/Unsigned API differences.

Native scale is corrected using import statistics. Unexpected geometry joining,
hidden-block import, or layout import settings are rejected rather than silently
changing the section. Failure removes only the owned sketch and temporary document,
and restores the caller's active document. Tests cover exact preferences on success
and native exception, including originally absent routing keys.

## Core verification

The console runner copies prepared `.freecad-test/<version>/config/{user,system}.cfg`
into excluded `.freecad-test/dxf-import/` profiles, using the environment layout from
`tools/freecad-test.py`. Original profile hashes are checked after each run. Test
state, caches, and temporary directories stay inside the excluded scratch tree.

| Check | Observed result |
|---|---|
| Parameter API capability check, RC | Passed; Bool/Int/Unsigned/Float/String methods exist |
| HEADER regression RED, RC (prior correction) | 25 tests, one expected `Duplicate DXF field 2` error |
| ACDSDATA regression RED, RC | 26 tests, one expected `Malformed DXF SECTION name` error |
| Focused RC tests after SECTION correction | 26 passed, including 13 adjacent section-capture tests |
| Focused stable 1.1.4 tests | Same 26 passed |
| Production original probes, RC and stable | Both 7882 and 9003 pass; both source hashes unchanged and cleanup passed |

The HEADER fix separates the section-name tags from variable payload beginning at
code 9. Synthetic repeated code-2 header variables now pass; duplicate section-name
and geometry fields still reject. These are production public-API probes, not the
earlier exploratory native-import scratch.

Original 7882 produces 92 geometries, 56 arcs, solver result 0, FullyConstrained true,
and area 546.7814330215074 mm² on both versions. Its true bounds are
X=±22.13246791337896, Y=±59.98922165964257, Z=0, with identity Placement.

The SECTION name must be the leading group-2 tag; ordinary non-name metadata may
follow it. The ACDSDATA regression includes legal group codes 70 and 71. Duplicate
section-name tags before HEADER variables still reject, and geometry field validation
is unchanged.

Original 9003 produces 62 geometries, 32 arcs, solver result 0, FullyConstrained true,
and area 117.16353742122065 mm² on both versions. Its true bounds are
X=±25.03011581835745, Y≈±9.762532891428108, Z=0, with identity Placement.
Both production probes explicitly use `unit_override='mm'`, check source hashes,
and verify caller document/object and active-document cleanup without saving.

Independent verification passed the 26-test core/capture suite and both original
probes. Its native-before/after and typed-preference restoration probe is now a
committed regression: the expanded 27-test suite passes on RC and stable with
unchanged prepared configurations. These regression-only checks pin already observed
behavior; they do not introduce a new production rule or a new RED claim.

Full-suite and visual verification remain pending. UI units
confirmation, explicit Custom save, review/cancel integration, and library reopen
belong to the future UI work unit.

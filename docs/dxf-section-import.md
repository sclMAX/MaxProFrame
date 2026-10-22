# Import a strict DXF section as a fixed sketch

Import one closed DXF section, review its fixed native sketch, and explicitly add
it to an editable folder library. Library material and density determine its weight.

## Quick path

1. Open **Profile Library Manager** and select an editable **Folder Library**.
2. Add or select a **Custom Profile** family, then click **Import DXF**, beside **Capture Section**, and select a DXF file. Both actions use icon-only buttons with tooltips and are hidden in parametric families.
3. Review the declared INSUNITS and confirm the actual units. You can override
   incorrect metadata (for example, declared meters when the drawing is in mm).
   Missing or unknown units require a selection; they are never assumed to be mm.
4. Review the actual native sketch in FreeCAD's viewport. The manager hides while
   small, modeless review controls show the destination library and its material.
   Geometry keeps its orientation in XY, Z=0, centered by the true bounding box
   including arc extrema, with identity Placement and fully fixed constraints.
5. Enter a non-empty, unique Custom Profile code and click **Add as Custom**.
   This stages an autonomous asset and selects its new card; it does not publish.
6. Click the existing **Save Changes** to publish the catalog and asset reference.

Cancel at the file picker, units confirmation, or review (including code entry)
leaves catalog, families, dirty state and assets unchanged. Invalid or duplicate
codes keep the review open for correction. The source DXF is never modified.
Closing the manager, switching libraries, or closing the preview document cancels
its owned review document. Repeated import reuses the active review; finish an
existing section edit before importing. Closing before **Save Changes** discards
new staged assets. The library's material cannot be overridden per profile.

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
including circular arc extrema; Placement remains identity. Bounds are obtained with
FreeCAD's documented `optimalBoundingBox(False, False)` API: neither display
triangulation nor shape tolerance participates. The default `Shape.BoundBox` can
reflect a GUI display mesh rather than the curve extrema and is not the geometric
centering oracle.

The synthetic bulge-2 arc from (10,20) to (18,20) has radius 5 and center
(14,17), with sweep `4*atan(2)`. Together with the closing rectangle edges its
true bounds are (9,12)–(19,24); translation is exactly (-14,-18). In a native GUI
runtime the unscaled imported shape's default bounds were approximately
(63.0004,84.051)–(133,168), versus exact curve bounds (63,84)–(133,168)
(native scaling factor 7). Using the default bounds produced the reproduced
0.007290186603921889 mm Y-centering error. Exact bounds remove that error;
regression checks independently pin source extrema, translated vertices, arc
center/radius/sweep, area, fixed constraints and identity Placement. Both RC and
stable GUI focused suites pass all 14 cases; console core/capture suites pass
all 27 cases. The complete GUI suite also passes all 419 cases on both supported
versions after this correction.

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

Full-suite automated verification passes; desktop visual acceptance remains pending.
UI state tests cover units,
review/cancel, staging, native asset save/reopen and destination density. Their
console runtime mocks only viewport operations and sketch creation; the real
native-DXF-to-library integration test requires a FreeCAD GUI runtime. Native DXF
import alongside a manually created QApplication in console mode terminated the
process during verification, so that integration is not claimed as console proof.
Core native-import verification above remains separate and unchanged.

The GUI-runtime suite now passes all 46 feature, manager, lifecycle and translation
checks on both FreeCAD 26.3rc2 and 1.1.4, including the real native-DXF-to-library
case without skips. That case releases state-test GUI mocks before calling the
native reader. Prepared profile hashes remain unchanged. Offscreen execution does
not establish desktop rendering quality. The complete suite passes 419/419 tests
without skips on both versions: 158.921 seconds on RC and 73.515 seconds on stable.
Prepared configurations remain byte-identical. Desktop visual acceptance remains
pending and is not implied by offscreen functional success.

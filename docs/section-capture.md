# Autonomous Section Sketch Capture and Persistence

Autonomous section sketch capture converts valid FreeCAD sketch profiles—whether standalone, parametric, attached to 3D geometry, or referencing external geometry—into self-contained, editable native sketches. These sketches are serialized into standalone `.FCStd` assets inside folder libraries under `sections/`, enabling portable cross-workstation sharing without external document links or broken references.

## Quick path

1. **Capture an autonomous sketch copy in a target document**:
   ```python
   from freecad.frameforge.section_capture import capture_section_sketch

   target_sketch = capture_section_sketch(source_sketch, target_doc=doc, name="Section")
   ```

2. **Save an autonomous section asset directly into a folder library**:
   ```python
   from freecad.frameforge.section_capture import save_section_asset

   metadata = save_section_asset(
       library_root="/path/to/my_library",
       source=source_sketch,
       name="Section",
   )
   # Returns:
   # {
   #     "asset_path": "sections/sec_4a7f9b8c....FCStd",
   #     "object_name": "Section",
   #     "asset_id": "sec_4a7f9b8c...",
   # }
   ```

3. **Validate custom section geometry independently**:
   ```python
   from freecad.frameforge.custom_section_geometry import build_custom_section_face

   # Validates one connected material region, closed contours, positive area
   face = build_custom_section_face(source_sketch)
   ```

## Details

| Topic | Specification & Decision |
|-------|--------------------------|
| **Stateless Geometry Validator** | Extracted from `Profile._validate_and_build_custom_section` into `custom_section_geometry.build_custom_section_face`. Imports `Part` only; enforces single connected material region (S5), closed contours, positive area, and coplanar wire bullseye facemaker. `Profile` retains backward-compatible forwarding. |
| **Materializing External Projections** | Projections in `ExternalGeo` are cloned into local geometry. Negative constraint references (`-3`, `-4`, ...) are remapped to local geometry indices while internal axes (`-1`, `-2`) and sentinels (`-2000`) are preserved. |
| **Defining vs Construction Status** | External geometry extension flags are checked via `testFlag('Defining')`. Defining curves remain material (`setConstruction(idx, False)`), while reference projections become local construction geometry. Local geometry is locked with `Block` constraints without hardcoded orientation recipes. |
| **External Parameter Freezing** | References to external objects (such as `VarSet` properties or external object dimensions) are frozen to native typed `Quantity` values via `getDatum`/`setDatum`. Units and values are preserved without string re-parsing or untrusted Python evaluation. |
| **Internal Formula Preservation** | Expressions referencing only internal sketch constraints (supporting canonical paths with leading dots like `.Constraints.Width`) are preserved in `ExpressionEngine`, allowing dynamic local formula recalculation in the autonomous copy. |
| **Support Detachment & Local Frame** | Attached or 3D-rotated sketches are detached into identity `Placement`, `AttachmentSupport = None`, and `MapMode = 'Deactivated'`. Local coordinate dimensions, area, wire topology, and hole centers match within native CAD tolerances. |
| **Source Immutability** | Source documents, sketch geometry, constraints, undo stacks, and saved file hashes remain 100% unchanged without mutative `solve()` preflights or state changes. |
| **Caller Target Rollback** | If capture is rejected, only the newly created sketch object is removed from caller-owned target documents, preserving existing objects like `Keep` intact. |
| **Pure Sketch Asset Serialization** | Each section is saved as a single-object `.FCStd` containing only the owned `Sketcher::SketchObject` and native properties. It can be reopened, edited, and recomputed in standalone mode without loading original project documents. |
| **Confinement & Safe File Writes** | Validates canonical confinement of library root, `sections/`, and asset filenames, rejecting symlink directory escapes. Writes execute inside an exclusive private temporary workspace directory (`mkdtemp` mode 0700) under `sections/`, containing all native `saveAs` outputs and `.FCBak` backups, and atomically publish to final path via `os.replace`. Cleanup removes only the owned private workspace without scanning or deleting unrelated sibling files in `sections/`. |

## API Reference

### `build_custom_section_face(source)`
Validates that `source` (a `Part.Face`, `Part.Wire`, or `Sketcher::SketchObject`) produces exactly one connected material region with valid closed contours and positive area, returning the resulting `Part.Face`.
- Supports single wires, multi-wire hollow sections, and curved contours via `Part::FaceMakerBullseye`.
- Ignores construction geometry via the sketch shape path.
- Rejects open contours, crossing contours, multiple disconnected material islands, non-coplanar wires, or invalid faces with descriptive `ValueError` messages.

### `capture_section_sketch(source, target_doc=None, name="Section")`
Creates a native, editable, autonomous copy of `source` in `target_doc` (or a new document if `None`).
- Materializes external projections, remaps constraints, freezes external expressions to typed datums, preserves internal formulas, and detaches support to identity placement.
- Asserts solver status (`solve() >= 0`), valid single-face geometry, and zero external dependencies (`OutList`, `ExternalGeometry`, `AttachmentSupport`).
- Rejects unresolved or conflicting source sketches before any mutations.

### `save_section_asset(library_root, source, name="Section")`
Captures `source` and serializes it as an isolated `.FCStd` asset inside `<library_root>/sections/`.
- Verifies canonical confinement of `library_root` and `sections/`, preventing symlink directory escapes.
- Generates a safe, unpredictable asset filename and writes through exclusive temporary files before atomic publication.
- Returns relative metadata dictionary: `{"asset_path": "sections/<filename>", "object_name": actual_sketch_name, "asset_id": "<id>"}` where `object_name` reflects the native sanitized `Sketch.Name` and user display input is preserved in `Sketch.Label`.

## Checklist

- [ ] Captured section sketches are pure native FreeCAD objects without `OutList` or `ExternalGeometry` links.
- [ ] Defining projected geometry is retained as material contours (`setConstruction(False)`).
- [ ] External parameter expressions are frozen to native typed `Quantity` datums.
- [ ] Internal constraint formulas remain active and dynamically recalculate on local edits.
- [ ] Detached sketches preserve local coordinates and identity placement.
- [ ] Source files and objects remain unchanged with identical SHA-256 hashes.
- [ ] Saved `.FCStd` section assets can be reopened and edited in complete isolation.
- [ ] Canonical path confinement prevents symlink escapes outside the library root.

## Next steps

- Folder library selection and registration UI workflows in the Library Manager (T3).
- Section capture, edit, rename, and delete actions in the Library Manager (T4).
- Instantiation of library sections as document-local profile sources (T5).

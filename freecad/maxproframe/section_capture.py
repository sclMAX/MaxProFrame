import os
import tempfile
import uuid

import FreeCAD as App
import Part
import Sketcher

from freecad.maxproframe.custom_section_geometry import build_custom_section_face


def _find_constraint_index(prop_path, constraints):
    """
    Resolves a property path (e.g. '.Constraints.Width', 'Constraints.Width',
    '.Constraints[0]', 'Constraints[0]') to the corresponding constraint index.
    """
    path = prop_path.lstrip(".")
    if path.startswith("Constraints[") and path.endswith("]"):
        try:
            idx = int(path[len("Constraints[") : -1])
            if 0 <= idx < len(constraints):
                return idx
        except ValueError:
            pass
    elif path.startswith("Constraints."):
        name = path[len("Constraints.") :]
        for idx, c in enumerate(constraints):
            if getattr(c, "Name", None) == name:
                return idx
    return None


def capture_section_sketch(source, target_doc=None, name="Section"):
    """
    Accepts a valid Sketcher object source (autonomous or with external dependencies)
    and creates a native editable, autonomous SketchObject in target_doc.

    - Evaluated local geometry and construction flags are copied.
    - External projected geometry (ExternalGeo) is materialized into local geometry,
      remapping constraints and preserving defining vs construction status.
    - Constraints, constraint names, driving/reference status, and active status are preserved.
    - External parameter expressions (e.g. VarSet, cross-doc) are frozen to native typed Quantity values.
    - Internal expressions referencing only local sketch properties are preserved.
    - Attached/rotated sources are detached into identity placement and local coordinates.
    - Validates that the resulting sketch forms exactly one connected material region,
      matches source area and bounds, and has zero external dependencies.
    - Source document, file hash, and objects remain untouched without mutating State.
    - On failure, rolls back only the newly created sketch in caller-owned target_doc.
    """
    if source is None:
        raise ValueError("Source sketch is missing")

    if not hasattr(source, "Geometry") or not hasattr(source, "Constraints"):
        raise ValueError("Source must be a Sketcher object")

    # Validate that source satisfies the custom section contract (1 connected material region, etc.)
    src_face = build_custom_section_face(source)

    # Check solver error state non-mutatively without calling source.solve()
    if bool(getattr(source, "ConflictingConstraints", None)) or bool(getattr(source, "MalformedConstraints", None)):
        raise ValueError("Source sketch has conflicting or malformed constraints")

    # Preflight check on source expressions: reject unresolved / broken expressions
    source_expr_list = getattr(source, "ExpressionEngine", []) or []
    for prop_path, expr_str in source_expr_list:
        try:
            source.evalExpression(expr_str)
        except Exception as e:
            raise ValueError(f"Source sketch contains unresolved expression '{expr_str}': {e}")

    # Snapshot all source constraint datums upfront before touching target
    source_constraints = getattr(source, "Constraints", []) or []
    source_datums = {}
    for i in range(len(source_constraints)):
        if hasattr(source, "getDatum"):
            try:
                source_datums[i] = source.getDatum(i)
            except Exception:
                pass

    # Prepare target document
    owned_doc = False
    if target_doc is None:
        target_doc = App.newDocument("SectionCaptureDoc")
        owned_doc = True

    created_sketch_name = None
    try:
        target_sketch = target_doc.addObject("Sketcher::SketchObject", name)
        created_sketch_name = target_sketch.Name
        if name:
            target_sketch.Label = name

        # Ensure detached identity placement and deactivated map mode
        target_sketch.Placement = App.Placement()
        if hasattr(target_sketch, "MapMode"):
            target_sketch.MapMode = "Deactivated"
        if hasattr(target_sketch, "AttachmentSupport"):
            target_sketch.AttachmentSupport = None

        # 1. Copy local geometry and construction flags
        for i, geom in enumerate(source.Geometry):
            is_const = source.getConstruction(i) if hasattr(source, "getConstruction") else False
            idx = target_sketch.addGeometry(geom, is_const)
            if hasattr(target_sketch, "setConstruction"):
                target_sketch.setConstruction(idx, is_const)

        # 2. Materialize external projected geometry (ExternalGeo)
        remap = {}
        materialized_indices = []
        external_geo = getattr(source, "ExternalGeo", []) or []
        for ext_idx in range(2, len(external_geo)):
            source_neg_id = -(ext_idx + 1)
            curve = external_geo[ext_idx]
            is_defining = False
            if hasattr(curve, "getExtensionOfType"):
                ext = curve.getExtensionOfType("Sketcher::ExternalGeometryExtension")
                if ext is not None and hasattr(ext, "testFlag"):
                    try:
                        is_defining = bool(ext.testFlag("Defining"))
                    except Exception:
                        is_defining = False

            is_construction = not is_defining
            new_idx = target_sketch.addGeometry(curve, is_construction)
            if hasattr(target_sketch, "setConstruction"):
                target_sketch.setConstruction(new_idx, is_construction)
            remap[source_neg_id] = new_idx
            materialized_indices.append((new_idx, is_defining))

        # 3. Remap and copy constraints
        for orig_idx, c in enumerate(source_constraints):
            for field in ["First", "Second", "Third"]:
                val = getattr(c, field, None)
                if val is not None and val in remap:
                    setattr(c, field, remap[val])
            target_idx = target_sketch.addConstraint(c)

            if c.Name:
                try:
                    target_sketch.renameConstraint(target_idx, c.Name)
                except Exception:
                    pass
            if hasattr(source, "getDriving"):
                try:
                    if not source.getDriving(orig_idx):
                        target_sketch.setDriving(target_idx, False)
                except Exception:
                    pass
            if hasattr(source, "getActive"):
                try:
                    if not source.getActive(orig_idx):
                        target_sketch.setActive(target_idx, False)
                except Exception:
                    pass

        # 4. Lock materialized external geometry so position is fixed locally
        for new_idx, is_def in materialized_indices:
            target_sketch.addConstraint(Sketcher.Constraint("Block", new_idx))

        # 5. Handle expressions and datums
        formula_constraint_indices = set()
        for prop_path, expr_str in source_expr_list:
            is_internal = False
            try:
                target_sketch.setExpression(prop_path, expr_str)
                target_doc.recompute()
                if not target_sketch.OutList:
                    target_sketch.evalExpression(expr_str)
                    is_internal = True
                else:
                    is_internal = False
            except Exception:
                is_internal = False

            if not is_internal:
                # Remove trial binding using documented public setExpression(path, None)
                try:
                    target_sketch.setExpression(prop_path, None)
                    target_doc.recompute()
                except Exception:
                    pass
                idx = _find_constraint_index(prop_path, source_constraints)
                if idx is not None and idx in source_datums:
                    try:
                        target_sketch.setDatum(idx, source_datums[idx])
                    except Exception:
                        pass
            else:
                idx = _find_constraint_index(prop_path, source_constraints)
                if idx is not None:
                    formula_constraint_indices.add(idx)

        # Freeze remaining datums for constraints not driven by active internal formulas
        for i in range(len(source_constraints)):
            if i not in formula_constraint_indices and i in source_datums:
                try:
                    target_sketch.setDatum(i, source_datums[i])
                except Exception:
                    pass

        target_doc.recompute()

        # 6. Validate target sketch
        if hasattr(target_sketch, "solve") and target_sketch.solve() < 0:
            raise ValueError("Captured sketch has conflicting or malformed constraints")

        tgt_face = build_custom_section_face(target_sketch)

        if abs(tgt_face.Area - src_face.Area) > 1e-4:
            raise ValueError(
                f"Captured section area ({tgt_face.Area:.4f}) does not match source area ({src_face.Area:.4f})"
            )

        if len(tgt_face.Wires) != len(src_face.Wires):
            raise ValueError(
                f"Captured section wire count ({len(tgt_face.Wires)}) does not match source wire count ({len(src_face.Wires)})"
            )

        src_local_shape = source.Shape.copy()
        src_local_shape.Placement = App.Placement()
        tgt_local_shape = target_sketch.Shape.copy()
        tgt_local_shape.Placement = App.Placement()

        src_bb = src_local_shape.BoundBox
        tgt_bb = tgt_local_shape.BoundBox
        bb_diff = max(
            abs(src_bb.XMin - tgt_bb.XMin),
            abs(src_bb.YMin - tgt_bb.YMin),
            abs(src_bb.XMax - tgt_bb.XMax),
            abs(src_bb.YMax - tgt_bb.YMax),
        )
        if bb_diff > 1e-4:
            raise ValueError(f"Captured section bounding box differs from source by {bb_diff:.6f}")

        # Independence verification
        if getattr(target_sketch, "OutList", None):
            raise ValueError(
                f"Captured sketch still has external object dependencies: {[o.Name for o in target_sketch.OutList]}"
            )

        if getattr(target_sketch, "ExternalGeometry", None):
            raise ValueError("Captured sketch still has external geometry links")

        if getattr(target_sketch, "AttachmentSupport", None):
            raise ValueError("Captured sketch still has attachment support")

        if hasattr(target_sketch, "Placement") and not target_sketch.Placement.isIdentity():
            raise ValueError("Captured sketch placement is not identity")

        return target_sketch

    except Exception:
        if owned_doc:
            if target_doc.Name in App.listDocuments():
                App.closeDocument(target_doc.Name)
        else:
            if created_sketch_name and target_doc.getObject(created_sketch_name) is not None:
                try:
                    target_doc.removeObject(created_sketch_name)
                except Exception:
                    pass
        raise


def save_section_asset(library_root, source, name="Section"):
    """
    Saves an autonomous custom section sketch as a pure native FreeCAD .FCStd asset
    inside an existing library root directory (under sections/).

    - Validates canonical root confinement and rejects symlink escape for both
      the sections directory and asset file.
    - Uses an exclusive, unpredictable temporary file in the destination directory
      before atomically publishing to prevent partial writes.
    - Cleans up only its own temporary file on failure without deleting unknown or unrelated files.
    - Generates a fixed safe asset filename; rejects overwriting existing assets.
    - The serialized .FCStd contains only the owned Sketch and native properties.
    - Returns relative metadata dict with the actual native Sketch.Name:
      asset_path (relative to library_root), object_name, asset_id.
    """
    if not library_root or not isinstance(library_root, str):
        raise ValueError(f"Invalid library root: {library_root}")

    canonical_root = os.path.realpath(library_root)
    if not os.path.isdir(canonical_root):
        raise ValueError(f"Library root directory does not exist or is not a directory: {library_root}")

    sections_dir = os.path.join(canonical_root, "sections")
    if os.path.islink(sections_dir):
        target_sec = os.path.realpath(sections_dir)
        try:
            common = os.path.commonpath([canonical_root, target_sec])
        except ValueError:
            common = None
        if common != canonical_root:
            raise ValueError(
                f"Sections directory '{sections_dir}' is a symlink escaping library root '{canonical_root}'."
            )

    if not os.path.exists(sections_dir):
        os.makedirs(sections_dir, exist_ok=True)
    elif not os.path.isdir(sections_dir):
        raise ValueError(f"Sections path exists and is not a directory: {sections_dir}")

    # Generate safe stable asset ID and filename
    asset_id = f"sec_{uuid.uuid4().hex}"
    filename = f"{asset_id}.FCStd"
    final_path = os.path.join(sections_dir, filename)

    if os.path.exists(final_path) or os.path.islink(final_path):
        raise FileExistsError(f"Asset file already exists: {final_path}")

    target_final = os.path.realpath(final_path)
    try:
        common = os.path.commonpath([canonical_root, target_final])
    except ValueError:
        common = None
    if common != canonical_root:
        raise ValueError(f"Asset file path escapes library root: {final_path}")

    temp_dir = None
    temp_asset_path = None
    asset_doc = None
    actual_object_name = name
    try:
        temp_dir = tempfile.mkdtemp(prefix=".workspace_", dir=sections_dir)
        temp_asset_path = os.path.join(temp_dir, filename)

        asset_doc = App.newDocument("SectionAsset")
        captured = capture_section_sketch(source, target_doc=asset_doc, name=name)
        actual_object_name = captured.Name
        asset_doc.recompute()

        asset_doc.saveAs(temp_asset_path)
        if os.path.islink(temp_asset_path):
            raise ValueError(f"Temporary asset path was replaced by a symlink: {temp_asset_path}")

        # Close asset doc before replace so no file locks or open handles remain
        doc_name = asset_doc.Name
        if doc_name in App.listDocuments():
            App.closeDocument(doc_name)
        asset_doc = None

        os.replace(temp_asset_path, final_path)
        temp_asset_path = None  # Successfully published
    finally:
        if asset_doc is not None:
            doc_name = asset_doc.Name
            if doc_name in App.listDocuments():
                App.closeDocument(doc_name)

        # Clean up ONLY the owned private workspace and its contents
        if temp_dir is not None and os.path.exists(temp_dir):
            import shutil

            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass

    # Manifests are portable: always "/", never the OS separator ("\" on Windows).
    rel_path = f"sections/{filename}"
    return {
        "asset_path": rel_path,
        "object_name": actual_object_name,
        "asset_id": asset_id,
    }

"""Section Library Lifecycle and Confinement Coordinator for Folder Libraries.

Coordinates path validation, dimension/weight extraction, deferred asset removal (S9),
and autonomous working-copy editing for Custom Profile geometry entries.
"""

import copy
import math
import os
import shutil
import tempfile
import uuid

import FreeCAD as App
import Part
import Sketcher

from freecad.frameforge.custom_section_geometry import build_custom_section_face
from freecad.frameforge.section_capture import capture_section_sketch, save_section_asset


def resolve_and_validate_asset_path(library_root, asset_path):
    """Resolves and validates that asset_path is safely confined within library_root/sections.

    Rejects:
    - Absolute paths or drive letters
    - Traversal components (..) before and after normalization
    - Paths not under sections/
    - Symlinks pointing outside library_root/sections

    Returns the canonical absolute path.
    Raises ValueError on invalid or unconfined paths.
    """
    if not library_root or not isinstance(library_root, str):
        raise ValueError(f"Invalid library root: {library_root}")

    if not asset_path or not isinstance(asset_path, str):
        raise ValueError(f"Invalid asset path: {asset_path}")

    # Reject absolute paths (POSIX and Windows)
    if os.path.isabs(asset_path) or asset_path.startswith("/") or asset_path.startswith("\\"):
        raise ValueError(f"Asset path must be relative to library root: {asset_path}")

    if ":" in asset_path:
        raise ValueError(f"Asset path must not contain drive letters: {asset_path}")

    # Reject traversal BEFORE normalization (Blocker E3/E4)
    raw_parts = [p for p in asset_path.replace("\\", "/").split("/") if p]
    if ".." in raw_parts or asset_path.startswith(".."):
        raise ValueError(f"Asset path contains parent directory traversal: {asset_path}")

    canonical_root = os.path.realpath(os.path.abspath(library_root))
    if not os.path.isdir(canonical_root):
        raise ValueError(f"Library root does not exist or is not a directory: {library_root}")

    # Normalize relative path
    norm_rel = os.path.normpath(asset_path)
    if norm_rel.startswith("..") or "/.." in norm_rel or "\\.." in norm_rel:
        raise ValueError(f"Asset path contains parent directory traversal: {asset_path}")

    # Must reside under sections/
    parts = norm_rel.replace("\\", "/").split("/")
    if not parts or parts[0] != "sections":
        raise ValueError(f"Asset path must be located inside the 'sections' directory: {asset_path}")

    # Verify sections directory itself does not escape library root (Blocker E3/E4)
    sections_path = os.path.join(canonical_root, "sections")
    canonical_sections = os.path.realpath(sections_path)
    try:
        common_sec_root = os.path.commonpath([canonical_root, canonical_sections])
    except ValueError:
        common_sec_root = None

    if common_sec_root != canonical_root:
        raise ValueError(f"Sections directory '{sections_path}' escapes library root '{canonical_root}'.")

    full_path = os.path.join(canonical_root, norm_rel)
    target_real = os.path.realpath(full_path)

    # Confinement check strictly against canonical sections directory (Blocker E3)
    try:
        common_target = os.path.commonpath([canonical_sections, target_real])
    except ValueError:
        common_target = None

    if common_target != canonical_sections:
        raise ValueError(f"Asset path escapes sections directory: {asset_path}")

    try:
        common_root = os.path.commonpath([canonical_root, target_real])
    except ValueError:
        common_root = None

    if common_root != canonical_root:
        raise ValueError(f"Asset path escapes library root: {asset_path}")

    return target_real


def compute_sketch_dimensions_and_weight(sketch, density_g_cm3=7.85):
    """Computes bounding dimensions (Height, Width in mm), theoretical weight (kg/m),

    and face area (mm2) from a valid custom section sketch.
    """
    if sketch is None:
        raise ValueError("Sketch object is required.")

    face = build_custom_section_face(sketch)
    if not face.isValid():
        raise ValueError("Constructed section face is invalid.")

    bbox = face.BoundBox
    height = round(bbox.YLength, 4)
    width = round(bbox.XLength, 4)
    area = round(face.Area, 4)

    density = float(density_g_cm3)
    if not math.isfinite(density) or density <= 0:
        raise ValueError(f"Density must be a positive finite number, got {density_g_cm3}")

    # Weight (kg/m) = Area (mm2) * Density (g/cm3) * 0.001
    weight = round(area * density * 0.001, 4)

    return height, width, weight, area


def purge_unreferenced_assets(library_root, staged_asset_paths, catalog_data):
    """S9 Deferred Asset Deletion: purges unreferenced asset files on disk.

    Only deletes an asset if NO family/size in catalog_data references it.
    Shared references across sizes/variants are strictly preserved by validated canonical file identity.
    Validates all references before deletion.
    """
    if not staged_asset_paths:
        return []

    canonical_root = os.path.realpath(os.path.abspath(library_root))

    # 1. Collect and validate canonical target identity for all referenced assets in catalog
    referenced_canonical = set()
    if isinstance(catalog_data, dict):
        for fam_key, fam_data in catalog_data.items():
            if fam_key.startswith("_") or not isinstance(fam_data, dict):
                continue
            sizes = fam_data.get("sizes", {})
            if isinstance(sizes, dict):
                for size_name, size_props in sizes.items():
                    if isinstance(size_props, dict):
                        asset_p = size_props.get("asset_path")
                        if asset_p and isinstance(asset_p, str):
                            canonical_target = resolve_and_validate_asset_path(canonical_root, asset_p)
                            referenced_canonical.add(canonical_target)

    # 2. For each staged path, check canonical identity against remaining references
    deleted = []
    for rel_path in set(staged_asset_paths):
        if not rel_path or not isinstance(rel_path, str):
            continue

        canonical_target = resolve_and_validate_asset_path(canonical_root, rel_path)
        full_staged = os.path.join(canonical_root, os.path.normpath(rel_path))

        # Check if the canonical target is still referenced anywhere in catalog
        if canonical_target in referenced_canonical:
            # S9: Canonical file is still referenced (e.g. by another size via direct or symlink reference)!
            # Do NOT delete the canonical file!
            # If the staged path itself was a distinct symlink that is no longer in catalog, remove only the symlink:
            if os.path.islink(full_staged):
                symlink_referenced = False
                for fam_k, fam_v in catalog_data.items():
                    if fam_k.startswith("_") or not isinstance(fam_v, dict):
                        continue
                    for s_k, s_v in fam_v.get("sizes", {}).items():
                        if isinstance(s_v, dict) and s_v.get("asset_path") == rel_path:
                            symlink_referenced = True
                            break
                    if symlink_referenced:
                        break
                if not symlink_referenced:
                    try:
                        os.remove(full_staged)
                        deleted.append(rel_path)
                    except OSError:
                        pass
            continue

        # File is unreferenced: remove it
        if os.path.islink(full_staged) or os.path.isfile(full_staged):
            try:
                os.remove(full_staged)
                deleted.append(rel_path)
            except OSError as err:
                raise OSError(f"Failed to remove unreferenced asset '{rel_path}': {err}")

    return deleted


class SectionEditSession:
    """Coordinates an autonomous working copy for editing a section sketch in FreeCAD.

    Ensures the published asset file is never exposed to direct modification.
    """

    def __init__(self, library_root, asset_path, size_code="", family="Custom Profile", library_name="", asset_id="", persistent_index=None):
        self.library_root = os.path.realpath(os.path.abspath(library_root))
        self.asset_path = asset_path
        self.size_code = size_code
        self.family = family
        self.library_name = library_name
        self.asset_id = asset_id
        self.persistent_index = persistent_index

        self.working_doc_name = None
        self.working_sketch_name = None
        self.staged_asset_path = None
        self.is_committed = False

    def open(self):
        """Opens an autonomous working copy document in FreeCAD containing the section sketch."""
        full_path = resolve_and_validate_asset_path(self.library_root, self.asset_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Asset file not found: {full_path}")

        # Open the source document temporarily to capture an autonomous working copy
        source_doc = App.openDocument(full_path)
        source_doc_name = source_doc.Name
        try:
            sketches = [
                obj for obj in source_doc.Objects
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
            ]
            if not sketches:
                raise ValueError(f"Asset file '{self.asset_path}' does not contain a SketchObject.")

            source_sketch = sketches[0]

            # Create dedicated working document
            doc_id = uuid.uuid4().hex[:8]
            working_doc = App.newDocument(f"Edit_{self.size_code or 'Section'}_{doc_id}")
            self.working_doc_name = working_doc.Name

            # Capture autonomous copy into working doc
            copied_sketch = capture_section_sketch(
                source_sketch,
                target_doc=working_doc,
                name=source_sketch.Name or "Section",
            )
            self.working_sketch_name = copied_sketch.Name
            working_doc.recompute()
            return working_doc

        finally:
            # Always close the source asset document so the published file handle is released
            if source_doc_name in App.listDocuments():
                try:
                    App.closeDocument(source_doc_name)
                except Exception:
                    pass

    def apply(self, density_g_cm3=7.85):
        """Validates the working sketch and stages a newly published asset file."""
        if not self.working_doc_name or self.working_doc_name not in App.listDocuments():
            raise RuntimeError("Working document is not open or was closed.")

        working_doc = App.getDocument(self.working_doc_name)
        working_sketch = working_doc.getObject(self.working_sketch_name)
        if working_sketch is None:
            sketches = [
                obj for obj in working_doc.Objects
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
            ]
            if not sketches:
                raise ValueError("Working sketch not found in working document.")
            working_sketch = sketches[0]

        # Validate solver and geometry
        if working_sketch.solve() != 0:
            raise ValueError("Working sketch has conflicting or unsolved constraints.")

        height, width, weight, area = compute_sketch_dimensions_and_weight(working_sketch, density_g_cm3)

        # Stage new asset in library root under sections/
        meta = save_section_asset(
            self.library_root,
            working_sketch,
            name=working_sketch.Name or "Section",
        )
        self.staged_asset_path = meta["asset_path"]
        self.is_committed = True

        return {
            "asset_path": meta["asset_path"],
            "object_name": meta["object_name"],
            "asset_id": meta["asset_id"],
            "Height": f"{height:.1f}",
            "Width": f"{width:.1f}",
            "Weight": f"{weight:.2f}",
            "Area": area,
        }

    def close(self, discard_uncommitted=True):
        """Closes working document and cleans up any uncommitted staged files."""
        if self.working_doc_name and self.working_doc_name in App.listDocuments():
            try:
                App.closeDocument(self.working_doc_name)
            except Exception:
                pass
            self.working_doc_name = None

        if discard_uncommitted and not self.is_committed and self.staged_asset_path:
            full_p = os.path.join(self.library_root, self.staged_asset_path)
            if os.path.isfile(full_p):
                try:
                    os.remove(full_p)
                except OSError:
                    pass
            self.staged_asset_path = None

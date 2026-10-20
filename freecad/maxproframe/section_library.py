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

from freecad.maxproframe.custom_section_geometry import build_custom_section_face
from freecad.maxproframe.section_capture import capture_section_sketch, save_section_asset


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


def recalculate_custom_profile_weight(asset_full_path, object_name, target_density):
    """Computes linear weight (kg/m) for a Custom Profile asset from its actual native face area
    and target density, using an owned temporary document to avoid mutating user-owned documents.
    """
    if not os.path.isfile(asset_full_path):
        raise ValueError(f"Asset file '{asset_full_path}' does not exist.")

    density = float(target_density)
    if not math.isfinite(density) or density <= 0:
        raise ValueError(f"Target density must be a positive finite number, got {target_density}")

    # Create owned private temp copy to inspect without mutating or colliding with user docs
    temp_dir = tempfile.mkdtemp(prefix="ff_recalc_inspect_")
    try:
        temp_file = os.path.join(temp_dir, "inspect.FCStd")
        shutil.copyfile(asset_full_path, temp_file)

        active_doc = getattr(App, "ActiveDocument", None)
        active_doc_name = active_doc.Name if active_doc else None
        saved_selection = []
        try:
            import FreeCADGui as Gui_mod

            if hasattr(Gui_mod, "Selection"):
                for sel in Gui_mod.Selection.getSelectionEx():
                    dname = getattr(sel, "DocumentName", None)
                    if not dname and hasattr(sel, "Object") and hasattr(sel.Object, "Document"):
                        dname = sel.Object.Document.Name
                    oname = getattr(sel, "ObjectName", None) or (sel.Object.Name if hasattr(sel, "Object") else None)
                    sub_names = list(getattr(sel, "SubElementNames", []))
                    if dname and oname:
                        saved_selection.append((dname, oname, sub_names))
        except Exception:
            saved_selection = []

        doc = None
        try:
            doc = App.openDocument(temp_file)
            if not doc:
                raise ValueError(f"Failed to open asset document '{asset_full_path}'.")

            if not object_name:
                raise ValueError(f"Section sketch object_name is required for asset '{asset_full_path}'.")
            sketch = doc.getObject(object_name)
            if sketch is None or not (
                getattr(sketch, "TypeId", "") == "Sketcher::SketchObject"
                or (hasattr(sketch, "isDerivedFrom") and sketch.isDerivedFrom("Sketcher::SketchObject"))
            ):
                raise ValueError(f"Section sketch '{object_name}' not found in asset '{asset_full_path}'.")

            face = build_custom_section_face(sketch)
            if not face.isValid() or face.Area <= 0:
                raise ValueError(f"Section face in asset '{asset_full_path}' is invalid or empty.")

            face_area = float(face.Area)
            calc_weight = (face_area * density) * 0.001
            return round(calc_weight, 4)
        finally:
            if doc is not None:
                doc_name = doc.Name
                try:
                    App.closeDocument(doc_name)
                except Exception:
                    pass
            if active_doc_name and active_doc_name in App.listDocuments():
                try:
                    App.setActiveDocument(active_doc_name)
                except Exception:
                    pass
            if saved_selection:
                try:
                    import FreeCADGui as Gui_mod

                    if hasattr(Gui_mod, "Selection"):
                        Gui_mod.Selection.clearSelection()
                        for dname, oname, sub_names in saved_selection:
                            if dname in App.listDocuments():
                                if sub_names:
                                    for sub in sub_names:
                                        Gui_mod.Selection.addSelection(dname, oname, sub)
                                else:
                                    Gui_mod.Selection.addSelection(dname, oname)
                except Exception:
                    pass
    except Exception as err:
        if isinstance(err, ValueError):
            raise
        raise ValueError(f"Failed to recalculate weight for asset '{asset_full_path}': {err}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except OSError:
            pass


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

    def __init__(
        self,
        library_root,
        asset_path,
        size_code="",
        family="Custom Profile",
        library_name="",
        asset_id="",
        persistent_index=None,
    ):
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
                obj
                for obj in source_doc.Objects
                if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject")
            ]
            if not sketches:
                raise ValueError(f"Asset file '{self.asset_path}' does not contain a SketchObject.")

            source_sketch = sketches[0]

            # Create dedicated working document
            doc_id = uuid.uuid4().hex[:8]
            working_doc = App.newDocument(f"Edit_{self.size_code or 'Section'}_{doc_id}")
            self.working_doc_name = working_doc.Name
            working_doc.Label = self.size_code or "Section"

            # Capture autonomous copy into working doc
            copied_sketch = capture_section_sketch(
                source_sketch,
                target_doc=working_doc,
                name=source_sketch.Name or "Section",
            )
            self.working_sketch_name = copied_sketch.Name
            copied_sketch.Label = self.size_code or "Section"
            working_doc.recompute()
            return working_doc

        finally:
            # Always close the source asset document so the published file handle is released
            if source_doc_name in App.listDocuments():
                try:
                    App.closeDocument(source_doc_name)
                except Exception:
                    pass
            # Explicitly ensure App active document is restored to the working document
            if self.working_doc_name and self.working_doc_name in App.listDocuments():
                try:
                    App.setActiveDocument(self.working_doc_name)
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
                obj
                for obj in working_doc.Objects
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
        if self.working_doc_name and App is not None and self.working_doc_name in App.listDocuments():
            try:
                import FreeCADGui as _Gui

                if hasattr(_Gui, "getDocument"):
                    gui_doc = _Gui.getDocument(self.working_doc_name)
                    if gui_doc is not None and hasattr(gui_doc, "getInEdit") and gui_doc.getInEdit() is not None:
                        gui_doc.resetEdit()
            except Exception:
                pass
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


def get_or_import_section_sketch(library_root, asset_path, object_name, target_doc, asset_id="", profile_code=None):
    """Returns an autonomous document-local SketchObject in target_doc for the specified asset.

    1. Validates canonical path confinement using resolve_and_validate_asset_path.
    2. Scans target_doc for an existing SketchObject matching composite provenance:
       (canonical_library_root, asset_id, object_name). If found, returns existing sketch.
    3. If not present:
       - Checks App.listDocuments() to detect if the asset file is already open (user-owned).
       - If open, reuses the existing document without closing or mutating it.
       - If not open, opens the asset document in FreeCAD and marks it as importer-opened.
       - Extracts the EXACT object_name (must be a SketchObject).
       - Uses capture_section_sketch to create an autonomous copy in target_doc.
       - Assigns visible Label from profile_code if supplied.
       - Sets ViewObject.ShowInTree=False and ViewObject.Visibility=False for new auxiliary imports.
       - Tags the imported sketch with composite provenance properties.
       - Closes the asset document only if opened by this importer.
       - Restores the active document to target_doc.
    """
    if not library_root:
        raise ValueError("Library root is required.")
    if not asset_path:
        raise ValueError("Asset path is required.")
    if not object_name:
        raise ValueError("Object name is required.")

    canonical_root = os.path.realpath(os.path.abspath(library_root))
    full_asset_path = resolve_and_validate_asset_path(canonical_root, asset_path)
    if not os.path.isfile(full_asset_path):
        raise FileNotFoundError(f"Asset file '{full_asset_path}' does not exist.")

    if target_doc is None:
        target_doc = App.ActiveDocument
    if target_doc is None:
        raise ValueError("Target project document is missing.")

    norm_asset_path = os.path.normpath(asset_path).replace("\\", "/")
    target_aid = str(asset_id) if asset_id is not None else ""

    # Check for existing document-local sketch matching composite provenance:
    # canonical root AND selected asset path AND exact object name AND asset ID (where present)
    for obj in target_doc.Objects:
        if hasattr(obj, "isDerivedFrom") and obj.isDerivedFrom("Sketcher::SketchObject"):
            p_prov = getattr(obj, "FF_Provenance", None)
            p_aid = getattr(obj, "FF_AssetId", None)
            p_oname = getattr(obj, "FF_ObjectName", None)
            p_apath = getattr(obj, "FF_AssetPath", None)
            if (
                p_prov == canonical_root
                and p_apath == norm_asset_path
                and p_oname == str(object_name)
                and (not target_aid or p_aid == target_aid)
            ):
                return obj

    # Snapshot active document and GUI selection before any document operations
    active_before = App.ActiveDocument
    saved_selection = []
    try:
        import FreeCADGui as Gui_mod

        if hasattr(Gui_mod, "Selection"):
            for sel in Gui_mod.Selection.getSelectionEx():
                dname = getattr(sel, "DocumentName", None)
                if not dname and hasattr(sel, "Object") and hasattr(sel.Object, "Document"):
                    dname = sel.Object.Document.Name
                oname = getattr(sel, "ObjectName", None) or (sel.Object.Name if hasattr(sel, "Object") else None)
                sub_names = list(getattr(sel, "SubElementNames", []))
                if dname and oname:
                    saved_selection.append((dname, oname, sub_names))
    except Exception:
        saved_selection = []

    asset_doc = None
    opened_by_importer = False

    for dname, doc in list(App.listDocuments().items()):
        fname = getattr(doc, "FileName", "")
        if fname:
            try:
                if os.path.realpath(fname) == full_asset_path:
                    asset_doc = doc
                    break
            except Exception:
                pass

    if asset_doc is None:
        asset_doc = App.openDocument(full_asset_path)
        opened_by_importer = True

    try:
        if opened_by_importer:
            # Read-only auxiliaries must not join the caller's undo transaction:
            # closing a linked document would commit the project transaction too.
            asset_doc.UndoMode = 0
        # Opening an asset changes the active document, including hidden assets.
        # Keep project edits on the active target rather than linking the source.
        App.setActiveDocument(target_doc.Name)
        source_sketch = asset_doc.getObject(object_name)
        if source_sketch is None or not (
            hasattr(source_sketch, "isDerivedFrom") and source_sketch.isDerivedFrom("Sketcher::SketchObject")
        ):
            raise ValueError(f"Object '{object_name}' not found or is not a SketchObject in asset '{asset_path}'.")

        captured_sketch = capture_section_sketch(
            source_sketch,
            target_doc=target_doc,
            name=object_name,
        )

        # Tag captured sketch with composite provenance identity
        if not hasattr(captured_sketch, "FF_Provenance"):
            captured_sketch.addProperty("App::PropertyString", "FF_Provenance", "FrameForge", "Source library root")
        captured_sketch.FF_Provenance = canonical_root

        if not hasattr(captured_sketch, "FF_AssetId"):
            captured_sketch.addProperty("App::PropertyString", "FF_AssetId", "FrameForge", "Source asset ID")
        captured_sketch.FF_AssetId = target_aid

        if not hasattr(captured_sketch, "FF_ObjectName"):
            captured_sketch.addProperty(
                "App::PropertyString", "FF_ObjectName", "FrameForge", "Source sketch object name"
            )
        captured_sketch.FF_ObjectName = str(object_name)

        if not hasattr(captured_sketch, "FF_AssetPath"):
            captured_sketch.addProperty(
                "App::PropertyString", "FF_AssetPath", "FrameForge", "Source relative asset path"
            )
        captured_sketch.FF_AssetPath = norm_asset_path

        if profile_code is not None:
            captured_sketch.Label = str(profile_code)

        vo = getattr(captured_sketch, "ViewObject", None)
        if vo is not None:
            if hasattr(vo, "ShowInTree"):
                vo.ShowInTree = False
            if hasattr(vo, "Visibility"):
                vo.Visibility = False

        target_doc.recompute()

        vo = getattr(captured_sketch, "ViewObject", None)
        if vo is not None:
            if hasattr(vo, "ShowInTree"):
                vo.ShowInTree = False
            if hasattr(vo, "Visibility"):
                vo.Visibility = False

        return captured_sketch

    finally:
        if opened_by_importer and asset_doc is not None:
            doc_name_to_close = asset_doc.Name
            try:
                App.closeDocument(doc_name_to_close)
            except Exception:
                pass
        if active_before is not None and active_before.Name in App.listDocuments():
            try:
                App.setActiveDocument(active_before.Name)
            except Exception:
                pass
        # Restore GUI selection on active project document
        if saved_selection:
            try:
                import FreeCADGui as Gui_mod

                if hasattr(Gui_mod, "Selection"):
                    Gui_mod.Selection.clearSelection()
                    for dname, oname, sub_names in saved_selection:
                        if dname in App.listDocuments():
                            if sub_names:
                                for sub in sub_names:
                                    Gui_mod.Selection.addSelection(dname, oname, sub)
                            else:
                                Gui_mod.Selection.addSelection(dname, oname)
            except Exception:
                pass

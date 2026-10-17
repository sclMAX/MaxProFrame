# Portable Folder Libraries

Portable folder libraries allow users to store FrameForge profile catalogs and section sketches in self-contained, user-selected directories. This enables sharing libraries across workstations or synchronizing them via shared storage (e.g. Google Drive, Nextcloud, network shares) without broken file paths or machine-specific registry pollution.

## Quick path

### Profile Library Manager GUI

1. **Create a new folder library**:
   - Click the **New Folder Library** compact header button in the Profile Library Manager.
   - Select an empty directory on disk via the folder picker.
   - Enter the library display name and select the material/density in the dialog.
   - FrameForge creates `<root>/library.json` and registers it in the local workstation registry.

2. **Register an existing bundle on another computer**:
   - Click **Register Folder Library** in the header.
   - Select the root folder containing `library.json`.
   - The catalog is validated and registered in place without modifying or copying files.

3. **Edit and save folder catalog data**:
   - Select the `[Folder]` entry in the library list (banner shows folder path and material).
   - Add/edit dimensions and families, then click **Save Changes**. Changes are atomically written to `<root>/library.json`.

4. **Custom Profile Section Management (Capture, Edit, Deferred Deletion)**:
   - When a folder library is selected, click **Capture Section** to capture an explicitly selected FreeCAD sketch into an autonomous `.FCStd` asset under `sections/`. If the `Custom Profile` family does not exist yet, FrameForge auto-creates it.
   - Dimensions (Height, Width) and theoretical weight are computed directly from native face geometry and material density, and their table cells are locked against accidental divergence.
   - Renaming a catalog code preserves the underlying stable asset filename and all custom metadata.
   - Click **Edit Section** to open an autonomous working copy in FreeCAD, bound to the stable row identity via persistent model indexing. Edit constraints in Sketcher, then click **Apply Section Edit** to recompute dimensions and stage asset updates. Renaming the code preserves target binding; removing the row cleanly invalidates the session without sibling fallback. The original published asset file is never exposed to direct edits before Save.
   - Deleting a size row stages removal in the catalog. Per S9, corresponding asset files on disk are removed only upon clicking **Save Changes**, and only if no other size shares the asset. Discarding or canceling preserves all saved assets and catalog entries.

5. **Instantiate Custom Profiles in Create Profiles Tool**:
   - In the standard **Create Profile** tool (`CreateProfileTaskPanel`), folder libraries appear in the material selector. Selecting `Custom Profile` family exposes the captured geometry sizes.
   - Metadata (`asset_path`, `object_name`, `asset_id`, `Area`) is safely filtered; bounding dimensions (Height, Width) and weight are displayed read-only to prevent drift; inapplicable dimensional and fillet controls are disabled.
   - When generating profiles along selected path edges, FrameForge imports the exact `object_name` sketch into the active project document as an autonomous native SketchObject.
   - New profile instances from the same unchanged section reuse the existing document-local sketch source, ensuring consistent BOM quantity grouping and PID numbering.
   - Project documents carry the native sketch and can be saved, reopened, and recomputed completely standalone without requiring the original folder library to remain registered or present on disk.
   - Library section edits emit new asset UUIDs and never mutate existing project sketches.

6. **Unregister safely without removing files**:
   - Select the folder library and click **Unregister Folder Library** (the contextual delete button).
   - If unsaved changes exist, choose whether to save, discard, or cancel before proceeding.
   - Confirm unregistration in the dialog prompt.
   - The local workstation registration is removed immediately, while all directory files, manifests, and sketches on disk remain completely untouched.
   - If unregistration is canceled or fails, unsaved edits and dirty state remain safely preserved on the active library.

### Python API

1. **Create a new folder library**:
   ```python
   from freecad.frameforge.library_manager import LibraryManager

   manager = LibraryManager()
   manifest_path = manager.create_folder_library(
       folder_path="/path/to/my_library",
       name="Workshop Profiles",
       material="Steel",
   )
   ```

2. **Register an existing bundle on another computer**:
   ```python
   manager.register_folder_library("/path/to/my_library")
   ```

3. **Discover and load profiles**:
   ```python
   libs = manager.list_libraries()
   catalog = manager.get_library("Workshop Profiles")
   ```

4. **Unregister safely without removing files**:
   ```python
   manager.unregister_folder_library("Workshop Profiles")
   # /path/to/my_library and its library.json remain intact on disk
   ```

## Details

| Topic | Specification & Decision |
|-------|--------------------------|
| **Catalog Root** | Self-contained user-selected directory containing `<root>/library.json`. Future section sketches live in relative paths under the root. |
| **Manifest Format** | Standard FrameForge catalog JSON format with `_metadata` (`name`, `material`, `density`, `is_folder: true`). Never contains machine-specific workstation paths. |
| **Local Registry** | Stored in dedicated subdirectory `.registry/folders.json` inside the user profile data directory (`FRAMEFORGE_USER_PROFILES_DIR`). Never scanned by legacy flat `*.json` search. |
| **Registration Idempotence** | Canonical path normalization ensures registering the same directory multiple times or via relative aliases produces a single registry entry. |
| **Missing / Unmounted Paths** | Missing or disconnected storage directories are omitted gracefully from `list_libraries()` without crashing or silently dropping from the disk registry. |
| **Deletion Protection** | `delete_user_library()` rejects registered folder libraries with a diagnostic pointing to `unregister_folder_library()`, preventing accidental data destruction. |
| **Root Confinement & Safe Writes** | Validates that `library.json` does not escape the canonical folder root via symlinks. All new folder and registry writes use exclusively created unpredictable temporary files (`mkstemp`) in destination directories, safe file-descriptor writes, and atomic replacement to prevent preseeded symlink hijacking. |
| **Fail-Closed Registry** | Registry read errors (invalid JSON, decode errors, schema corruption, permission denial) fail closed immediately, preserving on-disk registry bytes and registered paths instead of silently resetting to empty. |
| **Material Immutability & Validation** | Enforces that existing catalog material cannot be mutated on save, preserving downstream profile calculations. Preflight validation rejects invalid catalog shapes, non-string materials, and non-positive or non-finite densities before any writes occur. |
| **Collision Protection** | Rejects creating, registering, or renaming folder libraries to display names that collide with bundled stock, legacy user, or other registered folder libraries. |
| **GUI Header Actions** | Two compact 26x26 actions (**New Folder Library** and **Register Folder Library**) alongside existing legacy New, Duplicate, and Delete buttons. Fully localizable via existing translations. |
| **Catalog Tagging & Banners** | Distinct `[Folder]` prefix in the library list with directory path tooltips; prominent banner showing library name, directory path, material info, and editable status. |
| **Contextual Unregister** | When a folder library is selected, the Delete button adapts to **Unregister Folder Library**, prompting with explicit confirmation that disk files will be preserved. Never deletes directory contents from the GUI. Guarded by unsaved edits prompt before confirmation. |
| **Unsaved Edits Guard & Cancellation Semantics** | Switching libraries or triggering create/register/unregister with unsaved changes prompts with Save / Discard / Cancel. Choosing **Discard** grants permission to proceed without saving, but does not immediately clear dirty state: if any subsequent step is canceled (picker cancel, dialog reject, unregister decline) or fails (backend write error, collision, refresh failure), the user remains on the current library with all unsaved edits and dirty state strictly preserved. Selecting another library loads catalog data before mutating active metadata, preventing split selection/write-target state on load failures. Refresh errors preserve diagnostic error status without overwriting with false success messages. |
| **Folder Duplication (T6 Pending)** | Duplicating folder libraries is intentionally disabled with an explanatory tooltip until complete asset duplication is implemented in T6, preventing accidental flattening of folder assets into legacy JSON. |

## API Reference

### `create_folder_library(folder_path, name, material=None, density=None, data=None)`
Explicitly initializes a new self-contained folder library at `folder_path`, creates `<root>/library.json`, and records the canonical path in the local registry.
- Refuses to overwrite an existing `library.json` (`FileExistsError`).
- Refuses to initialize in a non-empty directory with unrelated files (`ValueError`).
- Rejects names that collide with bundled stock, legacy user, or other registered folder libraries (`ValueError`).

### `register_folder_library(folder_path)` (alias `register_existing`)
Registers an existing directory containing a valid `library.json` manifest into the local workstation registry.
- Strictly read-only validation: never initializes, writes, or modifies the target directory.
- Resolves symlinks to canonical paths for idempotent registration.
- Rejects manifests escaping the root via symlink or lacking valid metadata.

### `unregister_folder_library(folder_path_or_name)`
Removes the specified folder library from the local workstation registry.
- Accepts canonical path or library display name.
- Manifest and all directory contents remain completely untouched on disk.

### `save_folder_library(folder_path_or_name, data, overwrite=True, material=None, density=None)`
Atomically saves catalog updates to `<root>/library.json` preserving material immutability and metadata integrity. Also routed automatically through `save_user_library(name, data, ...)`.

## Checklist

- [ ] Folder library contains only portable relative content in `<root>/library.json`.
- [ ] Local registry paths are kept strictly in `.registry/folders.json` and fail closed on corruption without data loss.
- [ ] Temporary files use unpredictable paths exclusively created in destination directories.
- [ ] Unregistering removes local workstation registration only, preserving all assets.
- [ ] Root confinement guards prevent symlink escape outside the library folder root.
- [ ] Legacy stock and user libraries maintain existing metadata and behavior without modification.
- [ ] Profile Library Manager provides explicit New Folder and Register Folder header actions.
- [ ] Folder entries are clearly identified with `[Folder]` tag, banner path info, and contextual unregister.
- [ ] Unsaved changes are guarded by Save/Discard/Cancel semantics across all library actions.
- [ ] Folder duplication is disabled with informative diagnostic pending T6 asset duplication.

## Next steps

- Autonomous section sketch capture and serialization into relative `sections/` assets (T2 — complete).
- Profile Library Manager UI integration for folder selection, registration, and CRUD flows (T3 — complete).
- Geometry-specific section capture, edit, rename, and delete manager flow (T4 — complete).
- Instantiate library sections as document-local sources for profile generation (T5 — complete).
- Complete folder library asset duplication and relocation verification (T6).

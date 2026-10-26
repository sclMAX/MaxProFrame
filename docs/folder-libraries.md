# Portable Folder Libraries

Portable folder libraries allow users to store FrameForge profile catalogs and section sketches in self-contained, user-selected directories. This enables sharing libraries across workstations or synchronizing them via shared storage (e.g. Google Drive, Nextcloud, network shares) without broken file paths or machine-specific registry pollution.

## Quick path

### Profile Library Manager GUI

1. **Create a new folder library**:
   - Click **+ (New Library)** in the Profile Library Manager.
   - Enter the display name and select material/density. The full default destination updates with the name: `<user profiles>/<safe name>/`.
   - Optionally click **Choose Folder…** to select an empty custom destination. Canceling the picker keeps the current destination; changing the name afterward keeps your chosen folder.
   - MaxProFrame creates `<destination>/library.json` and registers it locally. Existing manifests, unrelated content, and colliding names are never overwritten.
   - The icon-only toolbar order is **+**, **−**, **Import Library**, **Duplicate Library**, **Export Library**; hover for tooltips. There is no separate New Folder Library button. Existing libraries are not migrated or deleted.

2. **Register an existing bundle on another computer**:
   - Click **Import Library**, then **Register Folder Library** in its menu.
   - Select the root folder containing `library.json`.
   - The catalog is validated and registered in place without modifying or copying files.

   - For ZIP exchange instead, choose **Import ZIP…** from that menu. **Export Library** shares the selected saved custom library and referenced section assets; unsaved changes require **Save** or **Cancel**, never discard-and-export. Stock libraries must first be duplicated. See [ZIP exchange](library-zip.md).

3. **Edit and save folder catalog data**:
   - Select the `[Folder]` entry. The left-aligned library/material badge sizes to its text. A family badge sits below, indented 16 pixels to suggest the hierarchy without tree controls. Both badges use the active FreeCAD style, with enough height for its font. Long names are elided to fit; hover for the full names, density and full folder path. With no family selected, the family badge is hidden. Stock catalogs also show **Read-only**.
   - Add/edit dimensions and families, then click **Save Changes**. The button is enabled only for editable libraries with pending changes; it is disabled after loading or a successful save, and remains enabled if saving fails. Searching, selecting, canceling an edit, or accepting unchanged properties does not enable it. Changes are atomically written to `<root>/library.json`. Fillets are chosen in **Add Family** and retained from the stored family, not toggled in the editor.
   - Closing with **Close**, the window **X**, or **Escape** asks **Save / Discard / Cancel** when there are unsaved changes. Save closes only after a successful save; Discard closes without publishing edits and removes owned uncommitted assets. Cancel (or dismissing the question) leaves the manager and edits intact. Active section working copies are cleaned up only after closing is approved; geometry edits are never applied automatically.
   - **Search this family…** filters by code or description without distinguishing case or accents. Use the field's clear button to restore all profiles. Counts show visible versus total profiles; an empty family and a search with no matches have distinct messages. Filtering never discards edits or removes profiles, including when saving while filtered.
   - Remove buttons require an actual editable selection. A selected profile hidden by search cannot be removed until visible and selected again. Removing a size (−) asks for confirmation showing its code, with No selected by default. No leaves the list and staged deletions unchanged; Yes removes the size, with asset cleanup still deferred until Save.

4. **Custom Profile Section Management (Cards View, Capture, Edit, Deferred Deletion)**:
   - When the `Custom Profile` family is selected in the Profile Library Manager, FrameForge presents a visual cards view instead of the table, displaying 2D silhouette vector thumbnails derived from stored section sketches via native face geometry. Standard families retain their standard parameter table (S1, S4).
   - Cards display NO dimensions or field labels. The code is a larger bold title; an optional, secondary description occupies up to two lines; a compact weight badge with its `kg/m` unit sits at the preview's bottom right. A permanently visible pencil icon at the top left opens **Edit Properties** (tooltip and accessible name). Its target is at least 28 × 28 pixels and is disabled for stock libraries. The preview reserves space so neither overlay covers the profile. The former footer button and weight row are removed; clicking the badge or card selects the profile, while the pencil opens the modal. Empty descriptions are hidden, with consistent card heights keeping the grid aligned. Long codes and descriptions are elided; hover for their full values. Labels, the weight display, the pencil button, and the drawing area inherit the active FreeCAD/Qt style, including custom QSS themes. The drawing and pencil use the receiving control's foreground; no fixed blue or gray is imposed. Selection adds an outline without recoloring the text. Hover, focus, and disabled button appearance come from the theme. Theme-private variable names are not parsed; contrast depends on the theme's own colors. Properties remain read-only on the card.
   - In editable user/folder libraries, click the **Edit Properties** pencil on a card to edit its code, optional description, and weight in a modal. **Accept** validates and stages all three values together; **Cancel** (or closing the modal) changes nothing. Use **Save Changes** in the library manager to publish staged changes. Stock libraries disable **Edit Properties**. Choose **Edit Section** inside that modal to edit geometry; the manager no longer exposes separate Edit Section or Apply Section Edit toolbar buttons. Descriptions are saved as optional `Description` metadata per profile. Manually entered weights must be positive finite numbers, and profile codes must remain unique within the family; invalid weights or duplicate codes are rejected before publishing catalog changes, preventing disk corruption or metadata loss (S2). Non-column metadata (tags, custom IDs, asset references) is preserved intact across saves.
   - In the **MaxProFrame** library manager, add or select a **Custom Profile** family in a folder library, then click **Capture Section** to capture an explicitly selected FreeCAD sketch into an autonomous `.FCStd` asset under `sections/`. Capture and DXF import actions appear only in custom geometry families (including renamed ones); their icon-only buttons retain tooltips. Geometry editing is reached from the card pencil. Existing read-only and selection restrictions still determine whether each action is enabled.
   - Alternatively, click **Import DXF**, explicitly confirm the drawing units (overriding incorrect metadata if necessary), and review the fixed, bounding-box-centered XY sketch in FreeCAD. The manager hides during review. Enter a unique code and click **Add as Custom** to stage it using the destination library's immutable material/density; **Save Changes** publishes it. Canceling before Add leaves catalog, dirty state and assets unchanged. See [DXF section import](dxf-section-import.md) for the strict supported input boundary and review cleanup behavior.
   - From the pencil's properties modal, **Edit Section** preserves pending field values and opens an autonomous working copy in native Sketcher. Only then are the library and modal hidden and a modeless **Edit Profile** window shown. This window does not replace or inject controls into Sketcher's task panel. The document and sketch retain the original profile's visible label and stable row binding. Missing/unusable geometry does not block properties-only edits.
   - **OK** in Edit Profile validates the complete edit, recalculates weight from geometry and library density (replacing any manual value), updates the card, closes the working copy and returns to the library with unsaved changes. **Save Changes** publishes them. Invalid fields or geometry remain editable and do not partially stage properties. **Cancel** or closing Edit Profile discards this entire session, including fields changed before entering Sketcher, while preserving earlier changes to other profiles.
   - Native Sketcher **Close** never means acceptance: a discard confirmation lets you abandon this session or resume editing. Closing the working document cancels the session. Original assets remain unchanged until library publication; accepted geometry is staged as a new asset. No edit session remains after acceptance or cancellation.
   - Deleting a card stages removal in the catalog. Per S9, corresponding asset files on disk are removed only upon clicking **Save Changes**, and only if no other size shares the asset. Discarding or canceling preserves all saved assets and catalog entries.
   - Silhouettes are generated in-memory with QPainterPath odd-even filling, preserving aspect ratio, outer curves, and internal holes without viewport screenshots or construction geometry. Generating or caching previews isolates open documents and Gui selections, uses ephemeral per-dialog caching without writing thumbnail files to libraries, and falls back to harmless placeholder previews for missing, corrupt, or traversal paths (S4).

5. **Instantiate Custom Profiles in Create Profiles Tool**:
   - In the standard **Create Profile** tool (`CreateProfileTaskPanel`), folder libraries appear in the material selector. Selecting `Custom Profile` family exposes the captured geometry sizes.
   - Metadata (`asset_path`, `object_name`, `asset_id`, `Area`) is safely filtered; bounding dimensions (Height, Width) and weight are displayed read-only to prevent drift; inapplicable dimensional and fillet controls are disabled.
   - When generating profiles along selected path edges, FrameForge imports only the selected custom profile sketch into the active project document as an autonomous native SketchObject (S11). Switching sizes or families during preview automatically prunes unreferenced session-imported sketches, preventing intermediate catalog sketch accumulation in the project document.
   - The visible `Label` of the newly imported auxiliary sketch displays the exact selected library profile code (e.g. `CP-901`) (S12), while internal FreeCAD object identifiers (`Name`) are sanitized as standard.
   - Newly imported auxiliary section sketches start hidden by default in both the project tree (`ShowInTree=False`) and the 3D viewport (`Visibility=False`) (S13), keeping the workspace and tree clean while remaining valid, linked, and extrusion-ready. Pre-existing user sketches preserve their visibility and labels.
   - Imports preserve the caller's project transaction: cancelling removes preview profiles and imported sketches without committing pending user edits. Importer-opened read-only asset documents use no undo history and are closed after capture; already-open user documents retain their undo settings and ownership. The active document and selection are restored after import.
   - Custom profiles use the same nine bounding-box path anchors as standard profiles, regardless of the section sketch's XY offset. Horizontal and vertical mirrors act about the aligned section center before profile rotation and path attachment. Holes and the source sketch are preserved; zero-length previews use the same alignment as extrusions.
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
| **GUI Header Actions** | **New Library** and **Duplicate Library** share the name/material/destination dialog. **Import Library** offers ZIP import and **Register Folder Library** for existing folders in place. **Export Library** is enabled only for custom libraries and requires saving unsaved edits or canceling. |
| **Catalog Tagging & Banners** | Distinct `[Folder]` prefix in the library list with directory path tooltips; compact banner showing library name and material, a second family line, and a read-only indication for stock catalogs; density and full folder path remain in the tooltip. |
| **Contextual Unregister** | When a folder library is selected, the Delete button adapts to **Unregister Folder Library**, prompting with explicit confirmation that disk files will be preserved. Never deletes directory contents from the GUI. Guarded by unsaved edits prompt before confirmation. |
| **Unsaved Edits Guard & Cancellation Semantics** | Switching libraries or triggering create/register/unregister with unsaved changes prompts with Save / Discard / Cancel. Choosing **Discard** grants permission to proceed without saving, but does not immediately clear dirty state: if any subsequent step is canceled (picker cancel, dialog reject, unregister decline) or fails (backend write error, collision, refresh failure), the user remains on the current library with all unsaved edits and dirty state strictly preserved. Selecting another library loads catalog data before mutating active metadata, preventing split selection/write-target state on load failures. Refresh errors preserve diagnostic error status without overwriting with false success messages. |
| **Modeless Window Lifecycle & Modality** | The Profile Library Manager opens modelessly from the start (`show()`), ensuring the FreeCAD main window and 3D viewport/Sketcher remain accessible and responsive without closing the dialog. Dialog ownership is retained on a single long-lived reference on the FreeCAD main window (`mw._frameforge_library_manager`). When editing a custom section sketch, the dialog temporarily hides to avoid obstructing the viewport and returns after the Edit Profile window accepts or cancels the session; native sketch closure requires an explicit discard/resume decision. Re-activating the command while the dialog is open or hidden raises and activates the existing live instance without duplicating dialogs or losing unsaved edits. Closing the dialog retires ownership, cleanly discards uncommitted working copy documents, purges uncommitted staged assets (S9), and ensures `QApplication.activeModalWidget` is cleared (S10) so subsequent activations open a fresh manager instance. |
| **Selected Profile Import & Sketch Visibility (T7)** | In `CreateProfileTaskPanel`, selecting a Custom Profile imports only the selected section sketch into the target document without accumulating unselected catalog sketches from UI initialization or size changes (S11). Unreferenced session-imported sketches are pruned upon size switching or changing to a standard family, respecting external references and existing project sketches. Newly imported auxiliary sketches assign the catalog profile code as their visible `Label` (S12) and initialize hidden in the tree (`ShowInTree=False`) and viewport (`Visibility=False`) (S13) while remaining fully valid and linked to profile solids. |
| **Folder Duplication & Portability** | Duplicating any stock, user, or folder library creates a registered folder. The default destination is a dedicated child under `manager.user_dir`; an explicit `target_folder_path` may select another empty directory. No new duplicates are flattened into loose JSON. Declared assets across all families are copied exclusively (ignoring unrelated notes or caches). Internal relative symlinks/aliases materialize as standalone regular files, ensuring portability upon source removal. Weight recalculation computes Custom Profile weights from the actual native face area of the disk asset and target density without modifying user documents or selections. Full rollback on failure cleans newly created artifacts while retaining pre-existing empty destination folders. (T6 verification pending). |
| **Custom Profile Cards & Silhouette Previews (T1 / S1-S4)** | Selecting `Custom Profile` displays selectable cards with vector silhouette thumbnails derived from native face geometry instead of table view; standard families retain tables. Cards show code, optional description, and weight (kg/m) without dimensions; **Edit Properties** opens a validated Accept/Cancel modal with optional **Edit Section** transition. Positive finite weights and unique codes are validated before saving. Applying sketch geometry edits recomputes linear weight from face area and density (S3). Previews isolate documents and selection, with ephemeral caching and harmless fallback for missing or corrupted assets without writing disk files (S4). |

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

### `duplicate_library(source_name, target_name, overwrite=False, target_material=None, target_density=None, recalculate_weights=False, target_folder_path=None)`
Clones any existing library into its own registered folder.
- If `target_folder_path` is omitted, uses `manager.get_default_library_folder(target_name)` under `manager.user_dir`.
- Explicit destinations must be empty; `overwrite=True` does not permit replacing content.
- Copies all declared section assets, materializing internal relative symlinks into portable standalone files.
- If `recalculate_weights=True`, recalculates parametric weights via standard formulas and Custom Profile weights from actual disk asset native face geometry and target density.
- Rolls back destination artifacts cleanly on failure, preserving pre-existing empty folders and the local registry.
- Returns the canonical manifest path (`<target_folder_path>/library.json`).

### `duplicate_folder_library(source_name_or_path, target_folder_path, target_name=None, ...)`
Convenience wrapper around `duplicate_library` specifically for folder libraries.

## Checklist

- [ ] Folder library contains only portable relative content in `<root>/library.json`.
- [ ] Local registry paths are kept strictly in `.registry/folders.json` and fail closed on corruption without data loss.
- [ ] Temporary files use unpredictable paths exclusively created in destination directories.
- [ ] Unregistering removes local workstation registration only, preserving all assets.
- [ ] Root confinement guards prevent symlink escape outside the library folder root.
- [ ] Legacy stock and user libraries maintain existing metadata and behavior without modification.
- [ ] New and Duplicate preview the destination folder; Register Folder remains available.
- [ ] Folder entries are clearly identified with `[Folder]` tag, banner path tooltip, and contextual unregister.
- [ ] Unsaved changes use Save/Discard/Cancel for switching actions; Export permits only Save or Cancel.
- [ ] Folder duplication creates complete self-contained asset copies with native weight recalculation and rollback safety (verification pending).

## Next steps

- Autonomous section sketch capture and serialization into relative `sections/` assets (T2 — complete).
- Profile Library Manager UI integration for folder selection, registration, and CRUD flows (T3 — complete).
- Geometry-specific section capture, edit, rename, and delete manager flow (T4 — complete).
- Instantiate library sections as document-local sources for profile generation (T5 — complete).
- Complete folder library asset duplication and relocation verification (T6 — implementation complete, verification pending).

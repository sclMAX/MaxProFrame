# Portable Folder Libraries

Portable folder libraries allow users to store FrameForge profile catalogs and section sketches in self-contained, user-selected directories. This enables sharing libraries across workstations or synchronizing them via shared storage (e.g. Google Drive, Nextcloud, network shares) without broken file paths or machine-specific registry pollution.

## Quick path

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

## Next steps

- Autonomous section sketch capture and serialization into relative `sections/` assets (T2).
- Manager UI integration for folder selection, registration, and CRUD flows (T3).

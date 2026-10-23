# Exchange custom libraries as ZIP

Share custom folder libraries as self-contained ZIP archives from the Profile Library
Manager. Stock libraries must first be duplicated into a custom folder.

## Quick path

1. Select a custom library and click **Export Library** (outward arrow).
2. If there are unsaved edits, choose **Save** to save and export, or **Cancel**.
   Export never discards edits; a failed save stops export.
3. Choose a new `.zip` file outside the source folder, including on an external drive
   or network share with an existing writable parent. Existing files are not overwritten.
4. On the receiving computer, click **Import Library** (inward arrow), then **Import ZIP…**.
   Choose the archive; the imported library is registered in its own default folder and selected.
   Conflicting names or destinations are rejected without overwriting existing content.

To register an already unpacked folder in place instead, choose **Register Folder Library**
from the same Import menu. Canceling a picker or rejecting an invalid archive keeps the
current library and unsaved edits. Import uses the existing Save / Discard / Cancel guard
before switching libraries. No existing user libraries are migrated or deleted.

## Manager API

- `export_library_zip(name_or_path, archive_path)` returns the absolute archive path.
  Existing outputs, including symlinks, are never overwritten. The output parent
  must exist and the output must be outside the source library. Publication occurs
  only after a full validation pass. On filesystems supporting hard links,
  publication is atomic and no-clobber. If linking reports EPERM, EOPNOTSUPP /
  ENOTSUP, or ENOSYS (as on some cloud/FUSE mounts), export instead creates the
  output exclusively and copies the validated archive in bounded chunks. This
  fallback never overwrites a racing file or symlink, but the output may be
  visible before copying finishes; universal atomic visibility is not promised.
  A failed write or close may leave an incomplete destination. Remove that
  incomplete export manually before retrying, or choose a new output name.
  Export deliberately does not delete the destination on failure: another
  process could have replaced it with an unrelated file. The temporary validated
  archive is still cleaned up. Other link errors are reported without attempting
  the fallback.
- `import_library_zip(archive_path, target_folder_path=None)` returns the same
  registration metadata as `register_folder_library`. The default destination is
  `get_default_library_folder(name)`, a dedicated child of `user_dir`.
  Any existing destination (even empty) or library-name conflict is rejected.
- `register_folder_library` remains available for existing folders unchanged.

ZIP root contains `library.json` and exactly its declared `sections/*.FCStd` assets
(including nested section directories). Shared references are stored once.
Names, material, density and weights are retained without recalculation. Libraries
with only parametric families need no section entries. Original DXFs, unrelated files
and registry entries are excluded. Export omits internal `_metadata.cloned_from`
provenance from its in-memory catalog copy because folder duplication may record a
machine-local source location there. Original source and duplicate manifests remain
unchanged; all other catalog semantics are retained. Absolute local paths in every
remaining catalog value are still rejected rather than exported, and asset confinement
validation is unchanged. Source symlinks are refused for ZIP export.

Cross-drive and UNC confinement boundaries are regression-tested using Windows path
semantics with real local archive IO on Linux; actual Windows filesystem execution
has not been verified by those tests.

## Validation and limits

Only stored and deflated, unencrypted regular-file members are accepted. Explicit
directory entries, traversal, absolute/drive/backslash paths, noncanonical components,
duplicate names and Unicode-normalized/case-folded collisions are rejected. Catalog
metadata, family/size dictionaries and every declared asset are checked before import
publishes or registers its folder. Extraction streams bytes and never uses `extractall`.

Engineering limits apply to both import and export: 4,096 members, 64 MiB per member,
256 MiB total expanded data, with 64 KiB copy chunks. Declared and actual expanded
bytes are bounded. These are resource guards, not a guarantee of sketch safety.
No sketch is opened, imported or executed to inspect an archive; native FCStd lifecycle
validation remains the runtime's responsibility.

Failed import removes only its newly claimed destination, not any pre-existing folder.
Registration uses the manager's existing atomic registry writer. Invalid archives and
conflicts leave existing library bytes and registry contents untouched.

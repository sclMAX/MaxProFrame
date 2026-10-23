# Exchange custom libraries as ZIP

The backend shares registered custom folder libraries without changing their source.
Stock libraries must first be duplicated into a custom folder. UI save/cancel handling
is separate; export reads the saved catalog only.

## Manager API

- `export_library_zip(name_or_path, archive_path)` returns the absolute archive path.
  Existing outputs, including symlinks, are never overwritten. The output parent
  must exist and the output must be outside the source library. Publication occurs
  only after a full validation pass.
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

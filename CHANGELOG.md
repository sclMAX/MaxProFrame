## Changelog

* Unreleased
  - Fix Custom Profile selected import, sketch naming, and tree visibility in Create Profile tool (T7 / S11-S13): import only the selected section sketch without accumulating unselected catalog sketches during combo initialization or size switching (S11), prune unreferenced session-imported sketches upon size or family changes while preserving external/InList references and pre-existing project sketches, assign the exact selected catalog profile code as the visible `Label` of newly imported auxiliary section sketches (S12), and initialize newly imported auxiliary sketches hidden by default in the project tree (`ShowInTree=False`) and viewport (`Visibility=False`) (S13) while maintaining valid profile solids and standard parametric workflows (see [Folder Libraries](docs/folder-libraries.md)).
  - Fix Profile Library Manager window lifecycle and modality (S10): open modelessly from the start via `show()` with single persistent FreeCAD main window ownership, preventing modal blocking of the FreeCAD interface during section editing; re-invoking the command while open raises and focuses the live manager instance without creating duplicate dialogs or losing unsaved edits; cleanly retire persistent references upon closing so subsequent activations create a fresh manager; eliminate mid-exec modality mutations; and ensure closing the dialog properly discards active working copies and uncommitted staged assets (S9) leaving no lingering modal widget blocker in `QApplication.activeModalWidget` (see [Folder Libraries](docs/folder-libraries.md)).
  - Add complete folder library duplication and native relocation portability to Profile Library Manager and LibraryManager backend (T6), copying declared section assets exclusively to user-selected empty destination roots, materializing internal symlinks as standalone portable files, recalculating Custom Profile weights from actual disk asset native face geometry and target density, enforcing root confinement and atomic rollback without deleting pre-existing empty directories, enabling GUI duplicate workflow with dirty-state cancellation guards, and verifying end-to-end relocation and offline project independence without library dependencies (see [Folder Libraries](docs/folder-libraries.md) and [Section Capture](docs/section-capture.md); verification pending).
  - Instantiate folder library Custom Profile sections in Create Profile tool, importing exact sketch objects as autonomous document-local sources, reusing unchanged local sketches across instances for unified BOM quantity and PID grouping, preserving container placement, anchors, and mirror semantics, isolating project documents from library deletion or subsequent section edits, filtering geometry metadata while preserving strict legacy unknown-setting validation, and protecting user-owned open documents (see [Folder Libraries](docs/folder-libraries.md)).
  - Add Custom Profile section capture, autonomous working-copy editing, catalog code renaming, and S9 deferred deletion to Profile Library Manager for folder libraries, binding edit sessions to stable persistent row model indices, locking geometry-derived dimensions against silent divergence, preserving arbitrary row metadata across table lifecycle, validating canonical asset and sections directory confinement, and purging unreferenced .FCStd files only upon successful manifest save while preserving shared references (see [Folder Libraries](docs/folder-libraries.md) and [Section Capture](docs/section-capture.md)).
  - Add portable folder library support to Profile Library Manager dialog, exposing explicit compact actions for creating empty-folder libraries and registering existing bundles in place, distinguishing folder catalogs with `[Folder]` tags, folder path banners, tooltips, and contextual non-destructive unregistration, while guarding unsaved changes with Save/Discard/Cancel semantics, preserving existing legacy New/Duplicate/Delete workflows, and disabling folder duplication with informative diagnostics pending complete asset copying in T6 (see [Folder Libraries](docs/folder-libraries.md)).
  - Add autonomous section sketch capture and serialization for portable folder libraries, materializing external geometry, remapping constraints, freezing external parameter expressions to typed Quantity values, preserving internal formulas, detaching 3D attachments to local identity coordinates, extracting stateless single-connected-region validator, and saving isolated native .FCStd assets with root confinement, exclusive private temporary workspace isolation, and atomic publication (see [Section Capture](docs/section-capture.md)).
  - Add portable folder library support to Profile Library Manager backend, enabling user-selected self-contained library roots with fixed library.json catalogs, dedicated local registry persistence, canonical path idempotence, root-confinement symlink safety, unpredictable atomic temporary writes, fail-closed corrupted registry protection, preflight type/density validation, collision-safe renaming, and non-destructive unregistration alongside existing catalogs (see [Folder Libraries](docs/folder-libraries.md)).
  - Accept multi-wire sketches with holes and curved contours in Create Custom Profile as a single connected material region, rejecting disconnected regions, open contours, and self-intersections with clear diagnostics while maintaining parametric recomputation and shape preservation (see [Custom Profiles](docs/custom-profiles.md)).
  - Group direct-source custom profiles by source section label in BOM and populated IDs, matching linked profile behavior.
  - Validate filleted Equal and Unequal Leg Angles before geometry generation, rejecting negative, zero, non-finite, oversized tip radii, and overlapping root/tip fillets with clear diagnostics while preserving last valid shapes and tube family controls (see [Angle Fillet Validation](docs/angle-fillet-validation.md)).
  - Assign populated IDs to both selected trimmed profiles or extruded cutouts and their source profiles, so BOM IDs are current immediately and survive recomputation.
  - Reserve existing numeric and letter IDs with an Include Count suffix when continuing numbering, filling gaps, or numbering from a fixed start.
  - Keep compact icon buttons in the Profile Library Manager at 26x26 pixels under FreeCAD stylesheets.
  - Align V-Slot and T-Slot aluminium profile sections to the selected path anchor (`AnchorX` / `AnchorY`).
  - Skip visual profile helper updates for edges with fewer than two vertices, avoiding an additional attachment error without changing model geometry or circular-path support.
  - Allow versionless trimmed-profile migrations to use native trimming boundaries and retain existing migration properties instead of adding them again.
  - Center end-miter cuts on the profile intersection for different anchor modes, while retaining endpoint-based cuts for matching anchors. Mixed-anchor profiles must intersect; otherwise add offsets.
  - Report unavailable standard cutting angles as N/A so combined-bevel profiles recompute without a formatting error.
  - Copy legacy numeric profile IDs as text when recomputing extruded cutouts, without changing the source ID.
  - Copy legacy numeric profile IDs as text when recomputing trimmed profiles, without changing the source ID.
  - Load linear weight correctly when editing a profile and leave stored profile data unchanged on opening.
  - Preserve the original profile color and transparency when accepting edits; cancellation still rolls back changes.

* v0.2.1
  - Adding pre-extend profile to create profile
  - revert PR #112, causing problems with standards mitter cut.
  - use linkedobject label for custom profile in bom
  - avoid creating negative angles if other is zero
  - remove debug prints
  - fix #115

* v0.2.0
  - Rework internal data, handles angles and length as method
  - Add preview for Profiles
  - Add markers A/B to profile when selecting
  - Add Anchor Mode
  - Add PID (Profile IDs) and UI to generate them
  - Add an automatic way to add/replace Balloons to TechDraw pages (from PID)
  - Improve BOM tool (internal mainly, and add PID as main identifier instead of long names)
  - Fix misleading behaviour with length #71
  - Add "mirror" property (X and Y axes) #82
  - fix Can't open Trim dialog on trimmed part #74
  - Fix Pipe profiles have wrong inner diameter #64
  - Fix Proper place of cutplane on miter ends #112

* v0.1.7
  - Fix BOM Generation
  - Implement CutList
  - Add Other object (parts, body) Links 
  - Fix Custom Profile BoundingBox
  - use cut angle for trimmedprofile in BOM
  - add cutout info in BOM

* v0.1.6
  - Fix #67
  - Merge Alu extrusions
  - Merge Custom Profile
  - Save checkbox values and add a way to remove prefix "Profile"

* v0.1.5
  - Add ExtrudedCutout
  - Add BOM
  - Add linting
  - Fix typo

* v0.1.4
  - Split UI for create_profiles
  - Rename Profile CutType 
  - Edit Profile
  - Add size, family, material in obj
  - fix #28, center offset on circular profile
  - Add wood profiles

* v0.1.3
  - Fix #10, Non attached profile (move profile inside the sketch 's parent)
  - Fix #27, Link to object go out of the allowed scope
  - Implement #23 Allow profile creation with selection of a whole sketch
  - Allows to create a Part to group all the Profile
  - Profile Naming Option

* v0.1.2
  - Fix recursive import
* v0.1.1
  - remove f-string with quote and double quote
* v0.1.0
  - Porting code from MetalWB
  - Improving UI
  - Split Corners into EndTrim and EndMiter


## Changelog

* Unreleased
  - Remove the FrameForge-era migrations of trims and miters: End Trim and End Miter objects no longer upgrade versionless objects, accept the old `Coped cut` / `Simple cut` cut types or add missing `MiterExtend` / `MiterGap` properties on recompute.
  - Make the **Trim Profile** command always available with an open document instead of depending on the selection: the panel explains every selected item it cannot use (not a profile, not a face, a whole object as a boundary, the trimmed profile itself) and keeps the valid ones, and the profile to trim can be picked whole in the tree. **OK** is one Undo step and **Cancel**, also when editing a trim, leaves no Undo step. Editing a trim shows its own cut type instead of the last one used. Trims recompute without the GUI, and a trim whose faces cut nothing keeps the profile uncut with a warning (see the [tutorial](docs/tutorial.md#via-end-trim-command)).
  - Add the **Extend / Cut** command: pick a target (a planar face, or a whole profile) and then several profiles; each profile gets one trim whose end nearest the target is extended or cut onto the target plane, with an optional **Gap**. Clicks add whole profiles and Ctrl+click drops one; OK creates every trim in one Undo step, a failure creates nothing and explains why in the panel, and double-clicking a trim edits its target and gap (see the [tutorial](docs/tutorial.md#via-extend--cut-command)).
  - Translate the MaxProFrame toolbar and menu commands into Spanish: their names and tool tips now follow the FreeCAD language, including a language switch while FreeCAD is running. Fix the **Refresh Balloons** and **Recursively recompute** command names.
  - Add a built-in English and Spanish guide to the **Profile Library Manager**: **?** or **F1** opens it inside FreeCAD, offline and in FreeCAD's language, at the section for the focused area or current selection; **New Library**, **Duplicate Library** and **Add Family** have their own **Help** button. Controls without a tooltip now have one, and empty libraries and families say what to do next (see the [guide](freecad/maxproframe/resources/help/library-manager.md)).
  - Show thumbnails for the aluminium T-Slot and V-Slot families instead of the generic placeholder (#25).
  - Ctrl+click a listed profile in the 3D view to drop it from the **End Miter** panel (see the [tutorial](docs/tutorial.md#via-end-miter-command)).
  - Preview the miters live in the **End Miter** panel, like Create Profile: the miters for the current joints are shown in the 3D view, and a click or Ctrl+click on a previewed miter stands for its profile. The new **Update automatically** check box (on by default, remembered between sessions) recalculates the preview on every change; unchecked, the panel shows **Pending changes** until it is checked again. OK always creates the current miters in one Undo step and Cancel leaves the document unchanged. Markers in the 3D view show each joint, and in red each point where three or more profiles meet (see the [tutorial](docs/tutorial.md#via-end-miter-command)).
  - Rework **End Miter** around the real profile axes and add a miter panel (see [Apply Miters and Trims](README.md#3-apply-miters-and-trims) and the [tutorial](docs/tutorial.md#via-end-miter-command)). The miter plane now passes through the crossing of both member axes, so joints are face to face for start-to-start edges, `OffsetX` on one profile and in-plane rotations, and resolving the target of an unsupported object raises an error instead of hanging. The command is always active and opens a panel where clicks select whole profiles; two or more profiles are mitered at every corner they form (one miter object per profile), and points where three or more profiles meet are skipped and reported. New `MiterExtend` (on by default, bounded at ten section diagonals) lengthens profiles up to the miter plane, and `MiterGap` leaves a gap between the cut faces, half on each side. Double-clicking an End Miter opens the panel to edit Extend and Gap on both sides of its joints in one Undo step. End Miter and End Trim objects are placed in the profile's own folder or Part instead of the outermost Part, which shifted them inside nested Parts, and trims and miters of an Extruded Cutout recompute.
  - Remember the **In place** / **Create a Part** choice between Create Profile sessions, and reuse the Part that already holds a sketch instead of nesting it in a new one, so later sessions add profiles to the same component. **Create a Part** no longer pulls a sketch out of its PartDesign Body, which emptied the Body's shape; the whole Body is placed in the Part instead. Switching to **In place** after previews were placed in a Part now re-places them live: moved sketches and Bodies return to their original group or the document root, profiles sit next to their sketch, and the Part created by the session is deleted, so OK commits what the preview shows. Selecting a whole Part, Body, group, solid or profile no longer creates dozens of broken profiles from its combined edges; it is ignored with a notice, while individually picked edges on a solid still work (see [Profile task panel](docs/commands.md)).
  - Create **In place** profiles in the sketch's own Part or folder instead of the outermost Part (a sketch inside a Body places them beside the Body), and warn on OK when the selection holds only ignored containers or solids instead of closing without creating anything (see [Profile task panel](docs/commands.md)).
  - Keep the alignment preview readable with large profile offsets: the section no longer shrinks below half its fitted size, and an off-view edge is shown as a border arrow labelled with the typed X/Y offset, drawn in a theme color with readable contrast (see [Profile task panel](docs/commands.md)).
  - Remove the legacy **Create Custom Profile** command (`Shift+C`) and its task panel. Custom sections are now created from the `Custom Profile` family of a folder library in the Create Profile tool; existing custom profiles in saved documents keep working (see [Custom Profiles](docs/custom-profiles.md)).
  - Add per-edge Offset X/Y controls to the profile task panel (S1, S2, S5, S6): displace profiles from their path edge in the edge frame (X in the sketch plane, Y along the sketch normal) through `OffsetX` / `OffsetY`, independent of rotation and mirrors; show **Mixed values** for differing selected edges; and mark the edge position relative to the displaced section in the alignment preview (see [Profile task panel](docs/commands.md)).
  - Add Custom Profile cards view to Profile Library Manager (T1 / S1-S4): display selectable cards with 2D sketch silhouette thumbnails derived from native face geometry instead of table view when Custom Profile family is selected, displaying editable code and weight (kg/m) without dimensions; preserve standard parameter tables for standard families (S1, S4); validate manual positive finite weights and duplicate codes before saving while protecting non-column metadata (S2); recalculate weight from geometry and density upon applying sketch edits while preserving manual weights across normal edits/save (S3); isolate open documents and selection during thumbnail generation without writing thumbnail files to libraries (S4); and support seamless card selection routing for capture, edit, apply, and delete operations (see [Folder Libraries](docs/folder-libraries.md)).
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


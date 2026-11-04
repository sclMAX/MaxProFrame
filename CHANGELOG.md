## Changelog

* Unreleased

  - A new **Drill Hole** starts with **Offset along** and **Offset across** at 0 mm, so the hole sits on the picked point (a corner, the middle of an edge or the face center).
  - **Drill Hole** shows nine clickable circles on the picked face: its corners, the middle of every straight edge and its center. One click on a circle sets where the holes are measured from: a corner measures both offsets from it; the middle of an edge along the profile measures **Offset along** from the middle of the face length, the middle of an edge across the profile measures **Offset across** from the middle of the face width, each with the other offset from that edge; the center measures both from the middle of the face, so offsets 0 put the hole there. Each click replaces the previous point (nothing is combined), and a click on the face takes the nearest circle. The panel names the point (Spanish *Medio de* EdgeN, *Centro de la cara*). Measured from the middle, **Offset along** is positive toward the end of the profile's path and **Offset across** to a fixed side of the face, whatever corner is stored; from a corner or an edge the offsets stay positive into the face. The one filled orange circle is the point the offsets are measured from. The choice is stored in the new **Center Along** and **Center Across** properties; drill holes saved before open with them off and stay where they were.
  - **Drill Hole** shows a clickable circle on every corner of the picked face: click one to measure the holes from that corner. The point the offsets are measured from is the filled orange one. A click on a circle does not select or report what lies under it (an edge of the preview was reported as *is not a face*).
  - The **Fx** icon of a panel field sits at the right end of the field, vertically centered. In the **Drill Hole** panel it was drawn short of the right end and above the middle once the preview bound the fields.
  - Use FreeCAD expressions in the number fields of the panels that edit one object (see the [tutorial](docs/tutorial.md#expressions-in-panel-fields)): the **Fx** icon, or typing `=`, opens FreeCAD's expression editor, so a field can follow a **VarSet**, a spreadsheet or a formula. It is available in every **Drill Hole** field (once the preview exists when creating), the **Cutout / Hole** depth, the **Extend / Cut** and **Notch** **Gap** while editing, and the **Edit Profile** sizes, length, weight, price and offsets. **OK** keeps the expressions in one Undo step and **Cancel** removes those set in the panel; expressions set before from the property editor are shown and kept, and the panels no longer write a typed value over them. In **Edit Profile** a material, family or size change fills the section sizes from the catalog and removes their expressions.
  - **Drill Hole** picks its reference without hitting the vertex: a click on a face takes the face and its circle nearest to the click, and a click near another circle of the same face moves it there. The picked point is marked in the 3D view. Clicking the vertex itself still works.
  - Drill round holes without a sketch with the new **Drill Hole** command (Spanish *Agujero*), next to **Cutout / Hole** (see the [tutorial](docs/tutorial.md#drill-hole)): click a planar face of a profile, a trimmed profile or a cutout, then one of its vertices, and set the **Offset along** and **Offset across** the profile from that vertex, the **Diameter**, a **Count** and **Pitch** for a row of holes, and the **Cut type** (**One wall**, **Through All** or **Distance**) with its **Depth**. The holes are previewed under **Update automatically**; **OK** creates them in one Undo step and **Cancel** leaves the document unchanged. Double-clicking a drill hole opens the same panel. The hole keeps its place when the profile changes and its vertices are renumbered; when its vertex is gone it stays where it was and its **Reference Warning** says so. Curved faces are refused with a message. A hole moved to another profile shows the profile it left again and is labelled after the new one. The cut list treats a drill hole like a cutout.

* v1.4.1 (2026-11-03)

  **Fixes**
  - Fix FreeCAD crashing now and then when an **Extend / Cut** or **Notch** is deleted while its edit panel is open. The deletion closes the panel, and the panel no longer puts the trim back or recomputes the document while FreeCAD is still removing the trim. The trim stays deleted.

* v1.4.0 (2026-11-03)

  - Leave a **Gap** around the target of a **Notch**: the panel has the same **Gap** box as **Extend / Cut**, 0 mm by default, and the target shape is grown by the gap in every direction before cutting, so the mouth of the notch keeps the same clearance on flat faces, around the edges of a rotated tube and along a round pipe (see the [tutorial](docs/tutorial.md#via-notch-command)). Double-clicking a Notch shows its Gap; the preview, **OK** (one Undo step) and **Cancel** treat it like the other values. The value is stored in the existing **TrimGap** property, so notches saved before keep a gap of 0 and are unchanged. A target that cannot be grown by the gap (for example a single face) makes the Notch fail with the reason.

  **Fixes**
  - Build **HEA**, **HEB** and **HEM** beams with their fillets: the catalog has fillets on for them, and creating one failed with `cannot access local variable 'wire1'`. They now get a root fillet at each web corner, like **IPE**. Beams created without fillets are unchanged.
  - Stop the **Create Profiles** and **Edit Profile** panels from printing `QAbstractItemView::commitData called with an editor that does not belong to this view` and `QAbstractItemView::closeEditor called with an editor that does not belong to this view` when the **Family** list loses focus or gets Tab, Enter or Escape. With the focus on that list, Tab moves to the next field again and Escape reaches the panel.

* v1.3.0 (2026-11-03)

  - Choose which piece **Extend / Cut** and **Notch** keep when the target crosses a profile between its ends: select profiles in the list and press **Flip side**, or double-click a row, to keep the other piece of each one, also when editing an existing trim (see the [tutorial](docs/tutorial.md#via-extend--cut-command)). The choice is stored in the new **KeepEnd** property (**Auto**, **Start** or **End**); **Auto** keeps the current behavior and is the default, so existing documents are unchanged. Choosing another target puts every profile back to **Auto**. When the target does not cross the profile the panel says there is no side to choose. The live preview draws the pieces that will be discarded in red.
  - Change the target of a new **Extend / Cut** or **Notch** without closing the panel: press **Change target** and the next click becomes the new target, then clicks add profiles again (see the [tutorial](docs/tutorial.md#via-extend--cut-command)). A click refused as target keeps it armed. While editing the button is hidden, since every click already changes the target.
  - Enable **Flip side** in the **Extend / Cut** and **Notch** panels only while a row of the profiles list is selected.
  - Preview edits of an **Extend / Cut** or **Notch**: the edit panel has the same **Update automatically** check box as creating (on for Extend / Cut, off for Notch, remembered), and the target, Gap and **Flip side** apply to the trim as you change them, with the discarded piece in red. **OK** keeps them in one Undo step, or none when nothing changed; an invalid result puts the trim back and keeps the panel open. **Cancel**, or closing the panel without **OK**, puts the trim back unchanged, with no Undo step.
  - Show the icon of its command for each trim in the tree (**Extend / Cut**, **Notch** or **End Miter**) and label new trims after their profile, for example `Profile_TC40x40x1.5_001_Tr` (`_Mt` for End Miter); the cut list shows the same labels. Existing trims keep their label.
  - New **Cutout / Hole** icon, a standing tube with a cutout in its wall, also shown for each cutout in the tree, and new cutouts are labelled after their profile, for example `Profile_TC40x40x1.5_000_Ex` (they showed the internal name, `Profile_000_Ex`). Existing cutouts keep their label.
  - The **Cutout / Hole** panel says that a click on another face changes it, and when Ctrl+Click selects several faces it says that only the last one clicked is used (see the [tutorial](docs/tutorial.md#cutout--hole)).
  - Edit the sketch of a **Cutout / Hole** from its panel: **Edit sketch** keeps the cut type and depth shown, opens the sketch, and closing it brings the panel back. The cutout's right-click menu in the tree also has **Edit sketch**.
  - Label the sketch of a new **Cutout / Hole** after its profile too, for example `Profile_TC40x40x1.5_000_Sketch` (it showed the internal name, `Profile_000_Sketch`). Existing sketches keep their label.

  **Fixes**
  - Fix **End Miter** finding no joint (0 joints) for a profile shortened by **Extend / Cut**: joints and miter planes now use where the trimmed body really ends, so the shortened profile and the profile it now ends on are mitered. Profiles without trims are mitered as before.
  - List a profile and a trim built on it only once in the **End Miter** panel, as the trim.
  - Fix **Extend / Cut** and **End Miter** failing with "the profile does not cross its own path" on a profile whose end offset shortens it past the middle of its path.

* v1.2.0 (2026-11-02)

  - Edit a single **Side** for *Square*, *Square Hollow* and *Equal Leg Angles* in the profile library manager: the width column is hidden and follows the side, so these families can no longer hold a size with different sides by mistake. The library format is unchanged. A size saved earlier with a different height and width keeps both columns visible, with a note on the width cell, and is never corrected without an edit.
  - Set the depth of a new **Cutout / Hole** right after drawing it: closing the sketch opens the cutout panel with the **Cut type** and a **Depth** that starts at the thickness of the wall under the face, previewed live (see the [tutorial](docs/tutorial.md#cutout--hole)). **Cancel** asks whether to delete the new cutout with its sketch, in one Undo step. Double-clicking a cutout opens the same panel, translated, and **Cancel** there restores the stored values.

  **Fixes**
  - Show the stored depth in the cutout panel opened by double-click; it always showed 500.
  - Draw the section and its placement points in the placement preview of **Create Profiles** and **Edit Profile** on themes whose text color is unreadable on the preview background: with a white background and light text only the selected point was visible. They now fall back to black or white.
  - Keep **Create Profiles** working when its preview profiles are removed outside the panel, with **Undo** or **Delete**: every selection failed with `Object has been removed from document` and **OK** created nothing. The panel now rebuilds the previews of the edges still selected. When FreeCAD closes the panel without **OK** or **Cancel** (for example when the library manager opens a section in Sketcher), the panel stops listening to the selection and removes its previews instead of leaving them in the project.

* v1.1.1 (2026-11-02)

  **Fixes**
  - Keep the label in step with the family in **Edit Profile**: changing the family now also replaces the old family in the label, as Create Profiles writes it with spaces as `_` (for example `Profile_Square_Hollow_40x40x2_001` becomes `Profile_Rectangular_Hollow_30x10x1.5_001`), when the label holds it as a whole part; a label written by hand without it is left as it is. Cancelling the panel restores the previous label.
  - Rebuild the profile only once, with the new family and its size, when the family changes in **Edit Profile**. Switching to a family with rounded corners, such as Rectangular Hollow, first rebuilt it with the old size and logged `gp_Dir2d() - input vector has zero norm`.
  - Keep the width and height of V-Slot and T-Slot profiles locked to their catalog size in **Create Profiles** and **Edit Profile**: their sections exist only in those sizes, and an internal update with another width or height failed with `Unknown V-Slot H/W`.

* v1.1.0 (2026-11-02)

  - Rework **Extruded Cutout** into **Cutout / Hole** (Spanish *Calado*), with a new icon: a tube with a hole and a slot (see the [tutorial](docs/tutorial.md#cutout--hole)). The command is always active and opens a panel asking for one planar face of a profile, trim or cutout, explaining every selected item it cannot use. OK creates, in one Undo step, a sketch attached to the face in the profile's Part or folder, with the face outline as construction geometry to dimension against, plus the cutout, and opens the sketch; closing it cuts the profile. An empty or unfinished sketch, or cancelling the sketch, leaves the profile uncut and in place instead of failing. The new **One wall** cut type, the default of this flow, cuts only the wall under the face, as deep as that wall: a hole on the top of a rectangular tube no longer goes through the bottom wall. Selecting one face and one sketch still creates the cutout directly, with **Through All**.
  - Add a demo of the whole workflow to the README: an animated GIF and an MP4, recorded by `tools/record_demo_video.py`, which drives the workbench in a full-screen FreeCAD with a throwaway profile and encodes the frames with `ffmpeg`.

  **Fixes**
  - Store sections captured into folder libraries as `sections/<file>` on every operating system. On Windows they were stored as `sections\<file>`, so the library could not be exported to ZIP and its custom profiles did not open on Linux or macOS. Libraries already saved that way are read as `sections/<file>` everywhere: they open, export to ZIP and duplicate on every operating system, and saving the library or duplicating it writes `asset_path` with `/` without changing any other value. Deleting a profile from such a library on Linux or macOS now also removes its unused section file on save (see [folder libraries](docs/folder-libraries.md)).
  - Keep profile names in the tree in step with their size in **Create Profiles**: changing the size of a profile now renames its label (for example from `Profile_V-Slot_20x20_000` to `Profile_V-Slot_40x40_000`), and the cut list follows it. The size is no longer part of the internal object name, which FreeCAD cannot change later; the label still shows it when **Size in profile name** is checked. **Edit Profile** also follows a size change in the label (for example `Profile_TC80x40x1.5_000` becomes `Profile_TC40x40x1.5_000`) when the label holds the old size as a whole part; a label written by hand without it is left as it is.
  - Show custom profile card thumbnails on Windows without opening each section document: the section shape is now read in memory instead of through a temporary file that Windows cannot reopen while it is open.

* v1.0.0 (2026-11-01)

  First release of MaxProFrame as an independent workbench. It can be installed side by side with FrameForge; neither replaces the other's modules, commands or settings.

  **Coming from FrameForge**
  - Documents created with FrameForge store their objects under `freecad.frameforge`: they open with FrameForge, and in MaxProFrame their profiles keep their shape but do not recompute. There is no migration.
  - Personal libraries are read only from `<FreeCAD user data>/MaxProFrame/profiles` (or `MAXPROFRAME_USER_PROFILES_DIR`). Move any libraries kept in `<FreeCAD user data>/FrameForge/profiles` to that folder.
  - Commands are registered only as `MaxProFrame_*`, and preferences are read only from the `MaxProFrame` group.

  **Changes**
  - Remove the FrameForge compatibility layer: the `freecad.frameforge` module redirect and package, the `FrameForge_*` command aliases, the `Frameforge` preference fallback and the `FrameForge` workbench alias. Install lists (setup.py, pyproject.toml, MANIFEST.in, CMakeLists.txt) no longer ship FrameForge files or missing files, and CMake installs to `Mod/MaxProFrame`.
  - Package metadata for the FreeCAD Addon Manager: one repository URL on the `release` branch, bugtracker and readme URLs.
  - Rewrite the README for GitHub with current screenshots, installation through the Addon Manager, updating and a quick start.
  - Record the MaxProFrame version on every profile, trim, cutout and link as `MaxProFrameVersion` (1.0.0) instead of `FrameforgeVersion` (0.2.1), and show MaxProFrame instead of FrameForge in property groups (links, balloons, captured library sections) and console messages. Profiles and cutouts no longer run the FrameForge 0.1.7 and 0.1.8 migrations: documents made with FrameForge are not supported. Documents created before this change keep showing the old `FrameforgeVersion` property.
  - Order the joint buttons **End Miter**, **Extend / Cut**, **Notch** on the toolbar and menu. Extend / Cut now uses the former Notch icon, and Notch has its own icon: an I beam coped to frame into another.
  - Remove the FrameForge-era migrations of trims and miters: End Trim and End Miter objects no longer upgrade versionless objects, accept the old `Coped cut` / `Simple cut` cut types or add missing `MiterExtend` / `MiterGap` properties on recompute.
  - Make the **Trim Profile** command always available with an open document instead of depending on the selection: the panel explains every selected item it cannot use (not a profile, not a face, a whole object as a boundary, the trimmed profile itself) and keeps the valid ones, and the profile to trim can be picked whole in the tree. **OK** is one Undo step and **Cancel**, also when editing a trim, leaves no Undo step. Editing a trim shows its own cut type instead of the last one used. Trims recompute without the GUI, and a trim whose faces cut nothing keeps the profile uncut with a warning (see the [tutorial](docs/tutorial.md#via-notch-command)).
  - Add the **Extend / Cut** command: pick a target (a planar face, or a whole profile) and then several profiles; each profile gets one trim whose end nearest the target is extended or cut onto the target plane, with an optional **Gap**. Clicks add whole profiles and Ctrl+click drops one; OK creates every trim in one Undo step, a failure creates nothing and explains why in the panel, and double-clicking a trim edits its target and gap (see the [tutorial](docs/tutorial.md#via-extend--cut-command)).
  - Replace **Trim Profile** with **Notch** (Spanish *Encastrar*, same icon and `M, C` shortcut): pick one target profile and then several profiles, each gets one Notch that copies the target shape, all in one Undo step, with the Extend / Cut panel (Ctrl+click drops a profile, double-click edits the target, Cancel leaves no Undo step). The kept piece is now the one that reaches the profile's far end instead of the one holding the center of gravity, which kept the wrong piece when most of the profile lay inside or past the target. Simple fit and the `CutType` property are removed: a straight cut at a plane is made with **Extend / Cut**. Notched ends keep the `P` cutting angle in the BOM (see the [tutorial](docs/tutorial.md#via-notch-command)).
  - Preview the trims live in the **Extend / Cut** and **Notch** panels, as End Miter does: the preview objects are the trims OK keeps, a click or Ctrl+click on a previewed trim stands for its profile, and changes (target, profiles, Gap) update the preview once you pause. An **Update automatically** check box, remembered separately for each tool (on by default for Extend / Cut, off for Notch because a notch is a heavy boolean), shows **Pending changes** while unchecked; OK always creates the current values in one Undo step and Cancel, or closing the panel any other way, leaves the document unchanged. While the panel is open the target is outlined in orange and the profiles in blue, drawn over the 3D view without changing any object color or adding Undo steps (see the [tutorial](docs/tutorial.md#via-extend--cut-command)).
  - Translate the MaxProFrame toolbar and menu commands into Spanish: their names and tool tips now follow the FreeCAD language, including a language switch while FreeCAD is running. Fix the **Refresh Balloons** and **Recursively recompute** command names.
  - Add a built-in English and Spanish guide to the **Profile Library Manager**: **?** or **F1** opens it inside FreeCAD, offline and in FreeCAD's language, at the section for the focused area or current selection; **New Library**, **Duplicate Library** and **Add Family** have their own **Help** button. Controls without a tooltip now have one, and empty libraries and families say what to do next (see the [guide](freecad/maxproframe/resources/help/library-manager.md)).
  - Show thumbnails for the aluminium T-Slot and V-Slot families instead of the generic placeholder (#25).
  - Ctrl+click a listed profile in the 3D view to drop it from the **End Miter** panel (see the [tutorial](docs/tutorial.md#via-end-miter-command)).
  - Preview the miters live in the **End Miter** panel, like Create Profile: the miters for the current joints are shown in the 3D view, and a click or Ctrl+click on a previewed miter stands for its profile. The new **Update automatically** check box (on by default, remembered between sessions) recalculates the preview on every change; unchecked, the panel shows **Pending changes** until it is checked again. OK always creates the current miters in one Undo step and Cancel leaves the document unchanged. Markers in the 3D view show each joint, and in red each point where three or more profiles meet (see the [tutorial](docs/tutorial.md#via-end-miter-command)).
  - Rework **End Miter** around the real profile axes and add a miter panel (see [Quick start](README.md#quick-start) and the [tutorial](docs/tutorial.md#via-end-miter-command)). The miter plane now passes through the crossing of both member axes, so joints are face to face for start-to-start edges, `OffsetX` on one profile and in-plane rotations, and resolving the target of an unsupported object raises an error instead of hanging. The command is always active and opens a panel where clicks select whole profiles; two or more profiles are mitered at every corner they form (one miter object per profile), and points where three or more profiles meet are skipped and reported. New `MiterExtend` (on by default, bounded at ten section diagonals) lengthens profiles up to the miter plane, and `MiterGap` leaves a gap between the cut faces, half on each side. Double-clicking an End Miter opens the panel to edit Extend and Gap on both sides of its joints in one Undo step. End Miter and End Trim objects are placed in the profile's own folder or Part instead of the outermost Part, which shifted them inside nested Parts, and trims and miters of an Extruded Cutout recompute.
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


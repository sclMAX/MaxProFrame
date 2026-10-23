# MaxProFrame

**MaxProFrame** is an advanced FreeCAD workbench for parametric framing, structural design, weldments, and profile modeling.

It enables engineers, makers, and fabricators to create structural frames, beams, and weldments (metal, aluminum extrusions, wood, and user-defined custom sections) mapped onto sketches or 3D edges, with automated joinery (miter cuts, coped joints, trim/extend), cutouts, and accurate Bill of Materials (BOM) generation.

---

## Key Features

- **Comprehensive Standard Profile Catalogs**:
  - Structural I/H Beams: **HEA, HEB, HEM, IPE, IPN**.
  - Channels: Standard **Channels**, tapered **UPN**, parallel-flange **UPE**, and lipped **C-channels** (with exterior and interior radius derivation).
  - Tubes & Solids: **Square Hollow**, **Rectangular Hollow**, round **Pipe**, **Round Bar**, **Square Bar**, and **Flat Sections**.
  - Aluminum Extrusions & Timber: **T-Slot**, **V-Slot**, and architectural wood profiles.
- **Portable & Autonomous Custom Profile Libraries**:
  - Capture any 2D sketch into standalone, self-contained folder libraries.
  - Portable across machines and shared folders (e.g., cloud drives, team shares) without external document dependencies.
  - Automated calculation of native face area, bound box dimensions ($H \times W$), and linear weight ($\text{kg/m}$) based on configurable material densities.
- **Visual Profile Library Manager**:
  - Live technical diagrams with axonometric 3D extrusion views and dimensioned 2D cross sections.
  - Add family variants (plain and filleted) with independent dimension tables.
- **Parametric Joinery & Operations**:
  - Miter cuts, coped joints, and trim/extend against multiple boundary faces.
  - Extruded cutouts with parametric sketch mapping.
- **BOM, Cut Lists & Ballooning**:
  - Generate cutting lists with true cutting angles, stock lengths, and kerf optimization.
  - Automatically populate and reset unique Part IDs (PIDs) and attach visual balloons for TechDraw integration.
- **100% Backward Compatibility**:
  - Seamlessly opens older FreeCAD project files (`.FCStd`) created with legacy *FrameForge* without `unhandled FeaturePython` or missing module errors.
  - Supports dual command registration (`MaxProFrame_*` and `FrameForge_*`) to protect user macros and toolbars.
  - Transparent per-key preferences migration.

---

## Prerequisites

- **FreeCAD** ≥ 1.1.4 (pinned official minimum supported version)
  - **Tested Environments**: Full native suites executed on official Linux x86_64 AppImages:
    - **Stable**: FreeCAD 1.1.4 (Python 3.11) — automated native offscreen test suite passing (355/355 tests passed).
    - **Release Candidate (RC)**: FreeCAD 26.3rc2 (reports Version 26.3.0, Python 3.13) — automated native offscreen test suite passing (355/355 tests passed after correcting causal observation boundaries in `tests/test_t2_independent.py`).
  - **Compatibility Notice**: The `≥ 1.1.4` declaration designates the minimum supported version and does not imply or guarantee forward compatibility with unreleased or arbitrary future FreeCAD versions.
  - **Platform Notice**: Automated offscreen test suites are validated on Linux x86_64; Windows and macOS environments and interactive GUI modeling workflows have not yet been proven in hosted CI. Older releases (< 1.1.4) are not supported.

---

## Installation

### Manual Installation (Git)

1. Locate your FreeCAD user modules directory:
   - **Linux**: `~/.local/share/FreeCAD/Mod/` (or `~/.FreeCAD/Mod/`)
   - **macOS**: `~/Library/Application Support/FreeCAD/Mod/`
   - **Windows**: `%APPDATA%\FreeCAD\Mod\`
2. Clone this repository into your `Mod` folder:
   ```bash
   git clone https://github.com/sclMAX/MaxProFrame.git
   ```
3. Restart FreeCAD. **MaxProFrame** will appear in the workbench dropdown selector.

---

## Quick Start

### 1. Create the Skeleton

Beams and profiles are mapped onto Edges or parametric lines:

1. Switch to the **MaxProFrame** workbench.
2. Create a new sketch on the XY plane using the Sketcher tool.
3. Draw a rectangle or a wireframe structure; this serves as the skeleton.
4. Close sketch edit mode.

![Create Skeleton](docs/images/02-create-frame-skeleton.png)

### 2. Add Profiles

1. Click on the **Create Profiles** tool in the MaxProFrame toolbar.
2. Select your **Material**, geometric **Family**, and standard **Size**.
3. In the 3D View, select the skeleton edges where you want to place the profiles (or define a **Length**).
4. Click **Apply** to validate settings and generate the 3D preview without closing the panel. Modifying inputs or selection shows **Unapplied changes**.
5. Click **OK** (Accept) to confirm and commit the profiles (current values are applied even without a prior Apply), or **Cancel** to discard all previews generated during the session.

![Profiles](docs/images/14-profiles-done.png)

### 3. Apply Miters and Trims

- Use **End Miter** to create 45° corner joins between intersecting profiles.
- Use **Trim Profiles** to cut a profile flush against the face of another beam.
- Use **Extruded Cutout** to cut notches, holes, or clearances from an attached sketch.

### 4. Generate the BOM & Cut List

1. Launch **Create BOM**.
2. Select the parent frame or profiles.
3. Choose whether to group identical items by Material/Size/Family and set stock length and blade kerf.
4. Export the resulting cut list and bill of materials into a FreeCAD spreadsheet.

---

## Custom Profile Libraries

MaxProFrame supports storing custom profile sections directly in user-managed folder libraries:

1. Open the **Profile Library Manager** from the toolbar.
2. Click **+ (New Library)**, enter a name and material/density, and review the full destination path. The default is a dedicated child folder in your user profiles directory; **Choose Folder…** selects a custom empty destination. **Duplicate Library** also creates a folder, including declared section assets. Existing folders can still be registered in place; no existing data is moved or deleted.
3. Add or select a **Custom Profile** family. Draw a Sketcher cross section and use **Capture Section**, or click **Import DXF** for a strict closed-polyline section. These icon-only actions have tooltips and appear only in custom geometry families.
4. For DXF, confirm the actual units, review the fixed centered XY sketch, enter a unique code and click **Add as Custom**. Weight uses the library material/density; canceling leaves the library unchanged.
5. Click **Save Changes** to publish the staged section, then reuse it without the original sketch or DXF. See [DXF section import](docs/dxf-section-import.md) for supported input and unit overrides.

For more details on custom libraries and architecture, see [docs/folder-libraries.md](docs/folder-libraries.md).

---

## Maintainer & Authors

- **Maintained by**: [sclMAX](https://github.com/sclMAX)
- **Repository**: [https://github.com/sclMAX/MaxProFrame](https://github.com/sclMAX/MaxProFrame)

### Credits & Heritage

**MaxProFrame** is an independent evolution built upon the foundation of **FrameForge** (originally authored by Vivien Henry) and **MetalWB**.

Special thanks to:
- Vivien Henry ([inductivebrain](https://github.com/lukh/frameforge))
- Vincent B, Quentin Plisson, rockn, Jonathan Wiedemann, and the FreeCAD community contributors.

---

## License

MaxProFrame is licensed under the [GNU Lesser General Public License v3.0 (LGPL-3.0)](LICENSE).

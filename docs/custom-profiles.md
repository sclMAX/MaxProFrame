# Custom Profiles

Create Custom Profile allows creating structural profiles from any valid single-connected 2D sketch or face, including hollow tubes and multi-hole sections.

## Quick path

1. **Draw section:** Create a Sketch with a closed outer boundary and any number of closed interior holes.
2. **Select in tool:** Open Create Custom Profile (`Shift+C`), click **Select a Profile**, and pick the sketch (or an `App::Link` pointing to it).
3. **Generate:** Select the path edge(s) or set a length, then accept. The resulting profile extrudes the section along the path.
4. **Edit the profile:** Double-click the generated profile in the tree to open the profile editor, including for custom sections selected from a folder library. Accept commits profile changes; Cancel restores the previous state. Editing length keeps the section source and its holes intact.
5. **Parametric updates:** Editing the source sketch (e.g. resizing holes or contours) automatically updates the profile on recompute.

## Supported and Rejected Topologies

FrameForge uses native `Part.makeFace` with `Part::FaceMakerBullseye` to validate and construct a single connected material region.

| Topology | Status | Behavior / Diagnostic |
|---|---|---|
| Single closed contour | Supported | Solid cross-section extruded along path. |
| Outer contour + 1 or more interior holes | Supported | Hollow cross-section; holes remain empty voids inside the solid. |
| Curved contours (circles, arcs, slots) | Supported | Analytic curved surfaces and volumes supported. |
| Underconstrained sketches | Supported | Constraints are optional; only solved geometry is checked. |
| Construction geometry | Supported | Construction lines and helper geometry are ignored. |
| `App::Link` to valid sketch or Face | Supported | Parametric link reference is preserved. |
| Prebuilt `Part.Face` with holes | Supported | Pre-existing faces accepted directly. |
| Disjoint outer loops | Rejected | `Custom profile must contain exactly one connected material region, got multiple disconnected regions` |
| Nested material island inside hole | Rejected | `Custom profile must contain exactly one connected material region, got multiple disconnected regions` |
| Open contours | Rejected | `Custom profile contains open contours; all contours must be closed` |
| Self-intersecting contour (e.g. bowtie) | Rejected | `Custom profile contours must not self-intersect` |
| Crossing or overlapping contours | Rejected | `Custom profile contours must not intersect or cross each other` |
| Empty or construction-only sketch | Rejected | `Custom profile source is empty or contains only construction geometry` |
| Non-coplanar contours | Rejected | `Custom profile contours are not coplanar` |

## Parametric Recomputation and State Preservation

- **Source Reference:** The profile retains a reference to the source object (`obj.CustomProfile`). It does not duplicate documents, copy geometry permanently, or disconnect from the sketch.
- **Parametric Edits:** Changing sketch dimensions or modifying hole positions updates the profile volume and geometry on `doc.recompute()`.
- **Fault Tolerance:** If a sketch is modified into an invalid topology (e.g. an open contour or disconnected islands), profile execution halts with a deterministic diagnostic in `obj.getStatusString()`, leaving the previous valid shape, placement, and properties intact. Fixing the sketch restores the profile to `Valid` status.
- **Direct Acceptance Confirmation:** In the Create Profile dialog, clicking **OK** confirms the custom profile without requiring a prior click on **Apply**. First-time custom section imports run after the native confirmation callback returns, avoiding the RC crash during dialog closure. Creation errors are reported and the profile transaction is rolled back.
- **Scope:** Custom profiles are user-defined sections and are not registered into catalog libraries. Extrusion follows the standard FrameForge path normal mapping without arbitrary section-plane reorientation.

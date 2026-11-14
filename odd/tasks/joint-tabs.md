# Interlocks: an independent command that adds locating shapes between two faces
A new command picks two faces of a joint and adds laser-cuttable interlocking shapes so the pieces locate each other.
First kind: fingers at the inner wall vertex of a Folded Corner. Branch feat/joint-tabs; push, PR and merge stay the
user's decisions.

## Specs
Notation (corner frame of unfolded_geometry.py, stepped-corners.md): u along the bar, v across the bent wall from its
outside face, w along the bend axis; d = tube depth across the bent wall, t = wall thickness, θ = bend angle,
s = band depth, g = clearance. A = the segment before the corner, B = the one after.

- S1 Independent command (L2): "Pensaba mas en un comando nuevo, que permita seleccionar 2 cara y poder configurar la
  antidad y forma de aletas. Notch, Miter, etc. seguirian siendo un paso previo independiete." -> a new command
  `Interlock` takes two picked faces and creates an Interlock object. Notch, End Miter, Extend Cut and the Folded Corner
  joint (Miter / Stepped) are not changed by it; a document without Interlocks recomputes to the same shapes.
- S2 Extensible kinds (L5): "a futuro analizaremos otras formas de encastre ganchos, clip, etc. tengamoslo a la hora de
  armar los objetos o clases." -> the Interlock object has a `Kind`; each kind is one geometry class registered in one
  registry (settings, checks, solids). This feature ships the kind `Fingers`; hooks, clips, the through tab and slot of
  a T joint (L1) and the in-plane key of a miter join later as new kinds without changing the object's links, the
  command's two-face picking or the bar integration.
- S3 Fingers at the inner vertex of a Folded Corner (L3): "a, [Image#3] en el vertice interno del FolderCorner" -> the
  two faces picked are the inner wall faces of the two segments of one folded (not open) corner of a Folded Bar. The
  inner wall band v ∈ [d - s, d] at that corner is split along w into `Count` fingers that alternate which segment owns
  the overlap of the two inner walls: a finger of A is the stepped geometry of stepped-corners.md S2/S3 (A covers the
  overlap, B ends past it), a finger of B the same with A and B swapped (StepFlip). Below the band the corner keeps its
  own joint (Miter or Stepped flanks, key, relief). Every surface the fingers cut is a tube cross-section, a plane
  w = const, or a tip surface swept along v (perpendicular to the inner wall): a laser without a bevel head cuts it.
- S4 Finger settings (L4): "ambos configurables y con alternativas de redondeo o bisel para ayudar al centrado." ->
  `Count` (integer, at least 2, default 3, A owns the first finger), `FingerWidth` (length, 0 = the band's height
  along w split evenly; otherwise every finger but the two outermost is that wide, centered), `Tip` = `Square` |
  `Chamfer` | `Round` with `TipSize` (the chamfer leg or the radius of the finger tip corners, in the inner wall
  plane, to lead the finger in), `Depth` (band depth s, 0 = automatic: the stepped automatic depth), `Clearance`
  (every mating face pair, finger sides included, opens by all of it: g/2 per piece, as stepped-corners.md T6) and
  `Flip` (B owns the first finger). A dovetail is not offered at a folded corner: the corner closes by bending, so an
  undercut cannot pass (agreed, L4-L5).
- S5 Unfolds and folds (L3): the fingers are cut in the Unfold Bar flat pattern and the Folded Bar folds into one sound
  solid with no overlap between the segments; each finger closes by the bend like the stepped joint it is made of.
  `DevelopedLength` does not change.
- S6 Refusals (L2, L3): two faces that are not the inner walls of the two segments of one folded corner (an open
  corner, a straight part away from a corner, two bars, a profile) are refused with a message saying what to pick.
  Fingers that do not fit (fewer than 2, wider than the band, a tip larger than half a finger, a band depth or angle
  the stepped joint refuses) are refused naming the corner's two pieces, like the other unfold errors.
- S7 Object, panel, docs (L2, L5): the Interlock object links the corner's two profiles (like the Folded Corner) and
  the bar lists its Interlocks, so changing one recomputes the bar; it can be edited with a double click; older
  documents open unchanged. The command sits on the Folded Miters toolbar with its icon. Spanish translation,
  tutorial, README and CHANGELOG describe it.

## Tasks
- T1 [S2, S3, S4, S5, S6] geometry: `interlock_geometry.py` (kind registry, `FingerSettings`, finger levels along w,
  checks) and its use in `unfold` (per-level stepped band, finger side clearance, tips) and `fold_bar` (the split
  between the segments follows the fingers); tests in tests/test_interlock_geometry.py. route=gentle-ai-worker
  (context backstop; design L7); commit=d056549 (PR #160, chain 1/4) [x]
- T2 [S1, S2, S6, S7] `interlock.py`: Interlock object (Kind, finger properties, PieceA/PieceB), FoldedBar
  `Interlocks` and their settings per corner, restore of older documents; tests. route=gentle-ai-worker (context
  backstop; design L9); commit=6fe004b (PR #161, chain 2/4) [x]
- T3 [S1, S6, S7] `create_interlock_tool.py`: command, two-face picking on a Folded Bar resolved to a corner, task
  panel with the settings and the refusals, edit, toolbar, icon; tests. route=gentle-ai-worker (context backstop;
  design L11) + parent (two pinned tests, L12); commit=feat/joint-tabs-3 (PR chain 3/4) [x]
- T4 [S7] tutorial, README, CHANGELOG, Spanish translation, full native suite. route=inline; commit=pending [ ]

Delivery forecast: about 1500 authored changed lines; chain_strategy=stacked-to-main (default branch verified:
main): one PR per task, each stacked on the previous one, merged in order (like #155-#157).

## Log
- L1 (2026-11-14) "[Image#1: a tube meeting another tube's side at an angle] Si tenemos una union, seria interezante
  poder crear aletas y cavas (que se puedan cortar con laser) para ubicar los perfiles uno respecto al otro. ENtiendes
  la idea?"
- L2 (2026-11-14) "Pensaba mas en un comando nuevo, que permita seleccionar 2 cara y poder configurar la antidad y forma
  de aletas. Notch, Miter, etc. seguirian siendo un paso previo independiete. De esta manera podria si quiciera agregar
  una union en el vertice interior [Image#2: a Folded Corner with its key] que sirba para alinear. Que opinas?"
- L3 (2026-11-14) Asked which vertex. User: "a, [Image#3: the inner vertical edge of a Folded Corner, marked] en el
  vertice interno del FolderCorner"
- L4 (2026-11-14) Asked order and finger shapes. User: "1. si 1+2 2. ambos configurables y con alternativas de redondeo
  o bisel para ayudar al centrado. Que opinas?" Proposed: square / chamfer / round tips in the wall plane; no dovetail
  at a folded corner (it closes by bending, an undercut cannot pass); dovetail kept for kinds inserted normal to a wall.
- L5 (2026-11-14) "Si, pero a futuro analizaremos otras formas de encastre ganchos, clip, etc. tengamoslo a la hora de
  armar los objetos o clases."
- L6 (2026-11-14) Design from exploration: each finger level is the existing stepped band (A-owner or flipped), so
  folding needs no new collision proof (the bend turns about w, levels never meet); corner cuts are w-invariant today,
  so the fingers add w-limited solids in `unfold` and a w-aware split in `fold_bar._after`. The Interlock links the
  two profiles, not bar faces, so bar -> Interlock has no cycle (Folded Corner pattern).
- L7 (2026-11-14) T1 design (parent):
  - `interlock_geometry.py` (no import of unfolded_geometry: avoid a cycle): `FINGERS = "Fingers"`,
    `SQUARE, CHAMFER, ROUND = TIPS`, frozen hashable `FingerSettings(count=3, finger_width=0.0, tip=SQUARE,
    tip_size=0.0, depth=0.0, clearance=0.0, flip=False)` with class attribute `kind = FINGERS`; registry
    `KINDS = {FINGERS: FingerSettings}`; `InterlockError(ValueError)`; `FingerSettings.bounds(span)` -> the count + 1
    w boundaries from -span/2 to span/2 (width 0 or count 2: even; else inner fingers `finger_width`, the two outer
    ones share the rest); `FingerSettings.check(names, span)` raises InterlockError (translate("MaxProFrame", ...)):
    count < 2; a finger not wider than the clearance (inner widths too wide for the span); tip_size > (narrowest
    finger - clearance) / 2. `_bends` turns InterlockError into UnfoldError.
  - `CornerSettings.interlock = None` (a FingerSettings). `_Bend` gains `span` (the tube size along w:
    width + height - depth of the segment before) and `fingers` (None or FingerSettings); `sizes()` keeps them.
    A `banded` property (stepped or fingers) replaces `stepped` in `_flank_top`, `_key_top`, `check_step`,
    `check_step_fit`; with fingers: step_depth = fingers.depth or automatic_step_depth, step_flip False, and the band
    clearance (in `_step_points`, the fit check and the split) is fingers.clearance. `_cut_faces` adds the stepped
    regions only for a Stepped corner without fingers; `_step_regions(flip)` takes the flip.
  - `finger_levels()` -> [(w0, w1, flip)], flip = (index odd) != fingers.flip (B owns it). `removed(reach)` adds per
    level the `_step_regions(flip)` faces extruded over [w0 - g/2, w1 + g/2] (the first from -reach, the last to
    +reach): neighbouring levels overlap by g at each boundary, which opens every finger side pair by g (g/2 each).
  - Tips at each interior boundary corner of the owner's finger (tip u = x_a - g/2 for A, allowance - (x_a - g/2)
    for B; w = boundary +- g/2): Chamfer removes the triangle of legs tip_size in the (u, w) plane, Round the square
    of side tip_size less the quarter disc of radius tip_size, both extruded along v over the band [d - s, d + t].
    Margins only past the tip along u, never into the neighbouring level along w (with g = 0 it holds the other
    piece's finger).
  - Fold: `UnfoldedCorner.finger_split = None` or (band v, ((w0, w1, middle), ...)), middle as `step_split`'s for
    that level's flip; `folded_geometry._after` owns below the band as at a stepped corner and, per level, the band
    from its middle on, as a w-limited prism (outer levels to +-reach); returns a solid placed by the frame.
- L8 (2026-11-14) T1 evidence (worker): RED 8 tests erroring on the missing `CornerSettings.interlock`; GREEN
  test_interlock_geometry 8 OK, test_unfolded_geometry 66 OK, test_folded_geometry 21 OK, test_folded_bar 49 OK
  (FreeCAD 1.1.4, .git/ci-policy-runtime); volumes without interlock pinned from the base code; mutation of `_after`
  caught. Deviations: `_key_fits` and `reach()` see both flips with fingers; the tip range rounds down to 0.1 mm.
  Not covered: a non-square tube, a folded Round tip, the open corner (ignores interlocks). Native assess: medium,
  not due (under_budget). Slice boundary: PR #160 = d056549.
- L9 (2026-11-14) T2 design (parent): `interlock.py` with an `Interlock` proxy for an `App::FeaturePython` without
  shape, built like `folded_corner.py` (`_add` idempotent properties, restore of missing ones): `PieceA`/`PieceB`
  (links to the corner's two base profiles, `folded_chain.base_profile`), `Kind` (enumeration of `KINDS`), group
  `Fingers`: `Count` (integer 3), `FingerWidth` (length 0), `Tip` (TIPS), `TipSize` (length 0), `Depth` (length 0),
  `Clearance` (length, the Folded Corner's default), `Flip` (bool). `is_interlock`, `interlock_key` (frozenset of the
  piece names, like `corner_key`), `interlock_settings(obj)` -> FingerSettings, `make_interlock(bar, piece_a,
  piece_b, **values)` placed in the bar's container and appended to the bar's new `Interlocks` (LinkList, added on
  restore). FoldedBar.execute gives each folded corner the settings of the Interlock whose key matches it
  (`CornerSettings.interlock`); an Interlock matching no folded corner of the bar (open corner, pieces not adjacent)
  or a second one on the same corner is an error naming them. The bar's view provider claims its Interlocks;
  the Interlock's view provider has an icon (resources/icons/Interlock.svg, new) and opens the T3 panel on double
  click when it exists (a hook T3 fills).
- L10 (2026-11-14) T2 evidence (worker): RED import error, then a mutation of `bar_settings` failing 8 checks in 7
  tests; GREEN test_interlock 10 OK, test_folded_bar 49, test_folded_bar_tools 14, test_folded_bar_panel 90,
  test_interlock_geometry 8, test_workbench_commands 2 (FreeCAD 1.1.4). Interlock `Clearance` defaults to 0, like the
  Folded Corner property. Edit hook `interlock.EDIT_PANEL(obj)` for T3. Decision (parent): deleting a bar also deletes
  its Interlocks, like its Corners (an Interlock without its bar does nothing) -> T3. PR #160 CI: 12 checks pass.
- L11 (2026-11-14) T3 design (parent): `create_interlock_tool.py` with the command `MaxProFrame_Interlock` (icon
  Interlock.svg, on the Folded Miters toolbar after the Folded Bar tools, module imported in InitGui) and an
  `InterlockTaskPanel`. Picking: two faces of one Folded Bar, read with their picked points (the selection when the
  command starts, then clicks while the panel is open, like Drill Hole's observer), each resolved with
  `folded_bar.segment_at` to its segment; valid when the two segments meet at a folded corner of the bar and each face
  is its segment's inner wall (planar, normal along minus the segment's outer normal of that corner: facing the
  inside of the corner). Otherwise the panel says what to pick (S6) and creates nothing. A valid pick creates the
  Interlock (`make_interlock`) in one transaction and previews it on the bar; the settings fields (Kind, Count,
  FingerWidth, Tip, TipSize, Depth, Clearance, Flip; TipSize enabled only for Chamfer / Round) update it live; a
  refusal of the bar (T1/T2 messages) shows in the panel and OK stays disabled while the bar is in error; OK commits,
  Cancel undoes it all. Edit (double click, the `interlock.EDIT_PANEL` hook) opens the same panel on the object with
  its values, no picking. Last used settings are remembered like the other panels. Deleting a bar deletes its
  Interlocks (FoldedBar.unsetupObject, L10).
- L12 (2026-11-14) T3 evidence: worker RED import error, then the bar-delete test failing before
  `remove_interlocks`, and a mutation of the inner-wall check caught; GREEN test_interlock_panel 10 OK,
  test_toolbar_translations 4, test_workbench_commands 2, test_interlock 10, test_interlock_geometry 8,
  test_folded_bar 49, test_folded_bar_tools 14, test_folded_bar_translations 9. Parent: the Folded Miters toolbar
  test now pins the Folded Bar tools first (test_folded_bar_panel CommandTest 5 OK) and the two Interlock command
  texts wait for a Russian translator (test_russian_translation 6 OK). Spanish menu text "Encastre". Deviations: a
  first Interlock starts with 0.5 mm clearance (the first Folded Corner's), no auto-update check box (each change
  applies at once), refusals for a corner that has an Interlock and for faces on two bars.

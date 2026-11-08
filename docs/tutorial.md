

# FrameForge Tutorial

FrameForge is dedicated for creating Frames and Beams, and apply operations (miter cuts, trim cuts) on these profiles.

## Create the skeleton

Beams are mapped onto Edges or ParametricLine (from a Sketch for instance)

For a start, we are going to create a simple frame.

1. In a new file, switch to the Frameforge workbench.

2. Create a sketch, and select orientation (XY for instance)

![Create Sketch](images/00-create-sketch.png)

![Select Orientation](images/01-select-orientation.png)


3. Draw a simple square in the sketch... it will be our skeleton

![Create Skeleton](images/02-create-frame-skeleton.png)

4. Close the Sketch edit mode.

## Create the frame

1. Launch the Profile tool.

![profile](images/10-profiles.png)

![profile](images/10-profiles-task.png)
![profile](images/10-profiles-task-2.png)

1. Select a profile from the lists (Material / Family / Size)


You can change the size just below the family, the tool has a lot of predefined profile, you can also change the parameters...


3. In the 3D View, select edges to apply the profile creation:

![Edge Selection](images/13-edge-selection.png)

(You can also select the sketch in the view before launching the create profile tool, it will create profiles for all edges in the profiles)

1. And press OK in the Create Profile Task. Now, you have four profiles !

![Profiles](images/14-profiles-done.png)

![Zoom in profile](images/14-zoom-on-profiles.png)



**And voila ! You have your first frame !**

You can add a Unit Price (per meter), it will be used into the BOM tool


## Going 3D... Making a cube !

We can build more complexe shapes, and there are severals ways of doing it.

### More Sketches !

We can add more sketches into our project:

1. Create a new Sketch
2. Select the same orientation as the previous one (XY)
3. Draw a square the same size and placement as the previous one.


4. Now, change the position of the sketch:

![Base Placement](images/20-sketch-base-placement.png)

![Sketch moved !](images/20-sketch-base-placement-2.png)

And the new sketch is 400mm on top of the first one !

You can therefore use Create Profile Command again to create another square frame !

![Stacked Frames](images/21-stacked-frames.png)

### Parametric Line

You can create parametrics lines for joining two vertices (points), these lines can be used with Warehouse Profile as well...

1. one can hide profiles objects with [Space Bar] (it allows to see the sketches)

![Hide profile](images/22-hide-profiles.png)

2. Selects vertices

![Select Vertices](images/23-select-vertexes.png)


3. Create Parametric Line

![Create parametric line](images/24-create-parametric-line.png)

![Parametric Line](images/25-parametric-line.png)


You can therefore use Create profile again to create the four vertical beams !

1. Open Create Profile, select the profile you want
2. Select the Parametric lines, click OK.

![Cube Done](images/26-cube-done.png)

#### Lines from a vertex along a direction

A parametric line can also start at a vertex and run along a global axis (+X, -X, +Y, -Y, +Z, -Z), an angle in a global plane, or a custom vector, with a length. This draws the legs of a table from the corners of its frame sketch:

1. Run Create a Parametric Line (`M, L`) with nothing selected: the panel opens. (Vertices selected before, one, three or more, or two of the same sketch, open it with a line from each.)
2. Click the four corners of the frame sketch: each click previews a line from that corner. Click a corner again to remove its line; a click on anything that is not a vertex adds nothing.
3. Choose the Direction and the Length. Angle in a plane takes a global plane (XY, XZ or YZ) and an angle, counterclockwise from the first axis of the plane: in XY 0° is +X and 90° is +Y, in XZ 0° is +X and 90° is +Z, in YZ 0° is +Y and 90° is +Z. Custom vector takes X, Y and Z. The Length and Angle fields take an expression (Fx), given to every line.
4. Or draw them by dragging: the 3D view shows the XY, XZ and YZ planes as squares at the start of the last line. Click a square (or press `P` to cycle the planes, or use the Drag in XY / XZ / YZ buttons), move the mouse and click: every line gets the direction and the length. The angle snaps every 15° and the length to 10 mm (1 mm with Shift); on an axis of the plane the line runs along that global axis, otherwise along an angle in the plane. A plane seen almost edge-on cannot be clicked. `Esc` or a right click cancels the drag and puts back the values, with the panel still open.
5. To go on with other lines and other values without running the command again, click Apply and continue: the lines are created in their own Undo step and the panel stays open, empty, with the same values for the next clicks. OK then creates only the newer lines, and Cancel removes only those.
6. Click OK: the lines are created in one Undo step (OK with no line creates nothing). Create Profile then turns them into legs.

The first panel starts at 100 mm along `-Z`; the next ones start with the Direction, custom vector, plane, angle and Length of the last OK. Each line starts at its vertex and follows it when the sketch changes. Double-click a line drawn from a vertex to change its direction or length. Two selected vertices of different objects, or of one object that is not a sketch, are still joined at once. Close any other open task panel first: while one is open the command creates nothing.



### More Sketches / Part2 !

There is another ways to add sketches, that allows to do more complicated stuff...

Sometime you want add a sketch to a specific place, and link it to another sketch. (If you modify the first Sketch, then the second will follow, hopefully)

This is not possible with the Position / Base Placement, that is an absolute position.

We are going to "Map" the sketch to something else.

1. Create a new Sketch, and set orientation to: YZ

I added a circle to the sketch so you can see where it is.. (just for reference !)

![Map Mode Sketch](images/30-mapmode-sketch.png)

2. Click on the map mode property:

![Map mode](images/31-mapmode.png)

![Map Mode dialog](images/32-mapmode-dialog.png)


You can change the map mode, selecting faces, vertices and edges...

![alt text](images/33-mapmode.png)

Here, our circle is in a new plan, the one at the top left of the screen...

There are a lot of options here.

You can then edit the sketch, and create more line and frames...

## Bevels and corners.

As you can see, the junctions are not that good (yet !). The profiles are centered on the skeleton, and stops right at the end of the edges.

We are going to make corners, and bevels. There are two methods for that.


### Via Bevels property

It is my favorite for simple frame..

Let's hide everything except the first frame we made...

![alt text](images/40-show-first-frame.png)

1. Select one of the profile, and in the property section, go for Bevel Start/End Cut 1/2

![alt text](images/41-bevels.png)

There are 4 entries (Start / End Cut1 Cut2)

That allows you to create bevels in the two axis, at the start or end of the profile.

Negative angles works, and must be used to compensate directions.

You can batch-modify that, by selecting all the profiles....

![alt text](images/42-batchs-bevels.png)

**And Voila ! a square frame !**


### Via End Miter Command

Let's show the other base frame ...

![alt text](images/50-base-config.png)

Offsets are optional: with **Extend** (on by default) a profile that stops short of the corner is lengthened up to the miter. You can still add offsets (they add up to the dimension of the edge), one profile at a time or by selecting all the profiles and changing the offset.

![alt text](images/51-add-offset.png)

1. Click on the Create Miter End Command. The button is always active, with or without a selection; profiles already selected are added to the panel.

![alt text](images/53-create-miter-end.png)

2. Click two or more profiles in the 3D view. A click selects the whole profile, not only the face under the cursor. To drop a profile, Ctrl+click it in the 3D view, or select it in the list and press **Remove**.

![alt text](images/52-select-touching-profiles.png)

3. The panel tells how many joints will be created. Every corner formed by the selected profiles is mitered: two profiles meeting at both ends get both corners, and a whole frame can be selected at once. A point where three or more selected profiles meet is skipped and listed in the panel; it is not mitered. The 3D view marks each joint with a small dot and each skipped point with a red dot.

   Profiles are met where their bodies really end: a profile shortened by [Extend / Cut](#via-extend--cut-command) (or another trim) is mitered at its new end, for example a side cut back to a crossbar and the crossbar form a corner. Selecting a profile together with a trim built on it lists it once, as the trim.

4. The miters are previewed live in the 3D view, like Create Profile does: the preview replaces the mitered profiles. Clicking a previewed miter stands for its profile, so Ctrl+click on it drops that profile. With **Update automatically** (on by default, remembered between sessions) the preview follows every change: adding or dropping a profile, Extend and Gap. Uncheck it to keep the preview as it is while you change things on a heavy frame; the panel then shows **Pending changes**, and checking it again updates the preview.

5. Set the options and press **OK**:
   - **Extend profiles up to the miter** (on by default): lengthens a profile that does not reach the miter plane. The extension is limited to ten times the section diagonal, to avoid runaway extensions with nearly parallel profiles.
   - **Gap**: distance left between the two cut faces of each joint, for example 0.5 mm. Each profile is cut back half of it.

**OK** always creates the miters for the current profiles and values, even when the preview is out of date. **Cancel** removes the preview and leaves the document as it was.

**And voila !** Each profile gets one "TrimmedProfile" holding all its corners, placed next to the profile, in the same folder or Part. A single Undo removes them all.

![alt text](images/54-miter-end.png)

To change a miter later, double-click it in the tree. The panel lists the profile and its boundaries and shows its current Extend and Gap. **OK** applies the values to this miter and to the miters of its partner profiles that cut against it, in one Undo step, so the gap of the joint stays the value shown; **Cancel** leaves everything unchanged. A partner miter that holds other corners gets the new values at those corners too.

### Via Notch Command

Let's finish the 3 others corners of the second frame...

![alt text](images/60-startwith.png)

![alt text](images/61-bad-joint.png)

When everything is showed again, you can see the vertical profiles are not cut as they should...

**Notch** cuts a profile so it fits against another profile, copying its shape: an I beam ending on another I beam, or a tube ending on a rotated tube, gets the exact outline of the target. It replaces the former Trim Profile command; a straight cut at a plane is made with [Extend / Cut](#via-extend--cut-command). The screenshots of the former Trim Profile panel no longer match the Notch panel and were removed.

1. Click on the **Notch** command (shortcut `M, C`). The button is always active while a document is open.
2. Pick the target first: click any face of the target profile, or select it in the tree. The whole target profile is used, whatever face was clicked.
3. Then click the profiles to notch. A click adds the whole profile; Ctrl+click drops a listed one. The target itself, and the profiles it is built on, cannot be added, and an object that is not a profile is refused: the panel says why.
4. Set **Gap** to leave that clearance all around the target, for example 0.5 mm for a weld seam or a loose fit; 0 (the default) notches flush against it. The target shape is grown by the gap in every direction before cutting, so the mouth of the notch keeps the same clearance everywhere, on flat faces, around the edges of a rotated tube and along a round pipe. The gap does not change which piece is kept.
5. **OK** creates one Notch per profile, each placed next to it in the same folder or Part, in one Undo step. **Cancel** leaves the document unchanged. In the tree each one shows the Notch icon and is labelled after its profile, for example `Profile_TC40x40x1.5_001_Tr`.

While the panel is open the target is outlined in orange, the profiles to notch in blue and, once previewed, the pieces the notches remove in red, as the panel says; the outline is only drawn over the 3D view and never changes the colors of the objects. The notches can be previewed live, as in Extend / Cut below, but **Update automatically** is off by default for Notch (a notch is a heavy boolean operation): check it to see the result before **OK**; the preview then follows the target, the profiles and the Gap. The choice is remembered for Notch on its own.

Each profile keeps the piece that reaches its far end, the end of its axis farthest from the target; everything past the target, and the part inside it, is removed. To notch both ends of a profile, notch the result again against the second target: the two notches are chained. If the target does not touch the profile, the profile is kept uncut and a warning is shown in the Report view.

When the target crosses a profile between its ends, select the profile in the list and press **Flip side** (enabled only while a row of the list is selected), or double-click its row, to keep the other piece instead; the row then reads *side flipped*, and pressing it again goes back. Choosing another target puts every profile back to **Auto**. The choice is made per profile, as in [Extend / Cut](#via-extend--cut-command) below.

You can also select the target and then the profiles before clicking the command: the panel starts with them. To pick another target, press **Change target**: the next click becomes the new target, as in [Extend / Cut](#via-extend--cut-command) below.

To change a Notch later, double-click it in the tree: the panel shows its current Gap; click another profile to change the target, change the Gap, or use **Flip side** to keep the other piece. The panel has the same **Update automatically** check box as when creating a Notch, off by default and remembered: checked, each change is applied to the Notch once you pause (**Flip side** at once), with the removed piece in red; unchecked, the panel shows **Pending changes** and **OK** applies them. **OK** keeps the changes in one Undo step, or none when nothing changed in the end; if the result is invalid the Notch is put back and the panel stays open with the reason and the changes pending. **Cancel**, or closing the panel without **OK**, puts the Notch back unchanged, with no Undo step.

In the BOM, a notched end shows the cutting angle `P`: it follows the target shape instead of a single angle.

### Via Extend / Cut Command

**Extend / Cut** brings the end of one or several profiles to a target: each profile gets one trim object, and its end nearest the target ends exactly on the target plane. A profile that stops short is extended (at most ten times its section diagonal, as End Miter); a profile that goes past is cut.

1. Click on the **Extend / Cut** command. The button is always active while a document is open.
2. Pick the target first: click a planar face (of a profile or of any other object), or select a whole profile in the tree. The target and the profiles can be in different Parts, placed anywhere: each profile ends on the target where it really is in the document. With a whole profile, each profile uses the face of the target it meets first, seen from its other end.
3. Then click the profiles to extend or cut. A click adds the whole profile; Ctrl+click drops a listed one. The target itself, and the profiles it is built on, cannot be added: the panel says why.

   A click that cannot work is ignored and the panel says why in its message line, without a dialog: a curved face (any flat face is a target, also one of a NURBS solid), a click inside a sketch (its inner face, for example the frame's guide sketch between the profiles), or a target face parallel to a listed profile (and, the other way, a profile parallel to the target face). The current target and profiles stay as they were.
4. Set **Gap** to leave that distance between the profile ends and the target plane.
5. **OK** creates the trims, each next to its profile in the same folder or Part, in one Undo step. If one of them cannot be made (for example a profile does not point at the target), nothing is created and the panel stays open with the reason. **Cancel** leaves the document unchanged. In the tree each trim shows the Extend / Cut icon and is labelled after its profile, for example `Profile_TC40x40x1.5_001_Tr` (End Miter uses `_Mt`); trims created before keep their label.

The trims are previewed live in the 3D view: the preview replaces each profile, and clicking a previewed trim stands for its profile, so Ctrl+click on it drops that profile. With **Update automatically** (on by default for Extend / Cut, remembered between sessions) the preview follows every change (target, profiles, Ctrl+click, Gap) once you pause; uncheck it to keep the preview as it is, the panel then shows **Pending changes** and checking it again updates the preview. **OK** always creates the current values, even when the preview is out of date. While the panel is open the target is outlined in orange, the profiles (or their previews) in blue, and the pieces the previews cut off in red, so you see what will disappear before **OK**; the outline is only drawn over the 3D view, so the colors of the objects are never changed.

When the target crosses a profile between its ends, the profile keeps by default the piece reaching its far end. To keep the other piece, select the profile in the list and press **Flip side** (enabled only while a row of the list is selected), or double-click its row: the choice is made per profile, the row then reads *side flipped*, and flipping again goes back. Choosing another target, also when editing, puts every profile back to **Auto**: the side depends on the target. With **Update automatically** checked the preview follows at once; unchecked, the panel shows **Pending changes**, as for any other change. When the target does not cross a profile there is no side to choose: the panel says *the target does not cross the profile, there is no side to choose* and the profile is unchanged. The choice is stored in the **KeepEnd** property of each trim: **Auto** (the default, and the behavior of trims saved before it existed), or **Start** / **End** to keep the piece reaching that end of the profile axis. **Start** and **End** apply only while the target crosses the profile between its ends; otherwise the trim behaves as **Auto**.

You can also select the target and then the profiles before clicking the command: the panel starts with them.

To cut profiles between two others, use **Apply and continue** next to OK and Cancel: it creates the cuts against the first target in their own Undo step and keeps the panel open with the same profiles, now cut, and no target. Click the face of the other profile and press **OK** (or **Apply and continue** again): the other end of the same profiles is cut, built on the first cut. OK after Apply and continue with no new target just closes; Cancel removes only the cuts made since the last Apply. A profile already cut against the same target is not cut again: the panel says so. **Notch** has the same button.

To pick another target while creating, press **Change target** next to the target: the next click becomes the new target, then clicks add profiles again. A click the panel refuses as target (for example a listed profile) keeps it armed, and pressing the button again cancels it. The button is hidden while editing, where every click already changes the target.

To change an Extend / Cut later, double-click it in the tree: click another face to change the target, change the Gap, or use **Flip side** to keep the other piece. The panel has the same **Update automatically** check box as when creating, on by default for Extend / Cut and remembered: checked, each change is applied to the trim once you pause (**Flip side** at once), with the discarded piece in red; unchecked, the panel shows **Pending changes** and **OK** applies them. The target and the edited trim are outlined in orange and blue. **OK** keeps the changes in one Undo step, or none when nothing changed in the end; if the result is invalid the trim is put back and the panel stays open with the reason and the changes pending. **Cancel**, or closing the panel without **OK**, puts the trim back unchanged, with no Undo step.

In the BOM, the cutting angle of the moved end is the angle between the target plane and a square cut.

## Organizing Objects

Now, you should have something like this:

![alt text](images/70-startwith.png)


You have Profiles, and TrimmedProfiles object (with two differents icons) TrimmedProfiles have Profiles or other TrimmedProfile as child.

There are three solutions to help organizing the project: (accessible from the frameforge toolbar)


- Part Container
- Fusion
- Group Container

My favorite is Part container because it is very close to the manufacturing process. each profile is a unique item that is manufactured, then assembled into a frame (the Part) then assembled into the full project. But you can keep "access" to the profile, as a specific part (cut, make holes...export to STEP, draw it)

The fusion, on the other way, will lock and "fuse" (well...) everything, making it hard to draw a 2D View for specific Profiles. (But for a long time it was the only way to cut and drill the profiles)

### Part Container

(My favorite solution)

I often use Part container for grouping profiles, sketches, etc.

![alt text](images/70-part-container.png)

![alt text](images/71-part-container.png)

You should drag only one object to the container... start by the first sketch, the rest should follow
... I don't know why, but FreeCAD is not happy about a group drag.

Sometime parts and profile get out of the Part Container. (mainly fixed now !)


It allows to group profiles, in a "light" way. profiles can be updated

### Fusion

One can fuse profiles together.

![alt text](images/72-fusion.png)

![alt text](images/72-fusion-done.png)

It allows to group profiles, in a "strong" way. profiles can be updated.

The fusion can be converted into a baseFeature allowing to be used into a Body (PartDesign) (extrude, etc)


**The profiles MUST BE "closed", without any crossed profiles.** The fusion tool need that. And the Body tool as well. Expect bugs if Profiles are not trimmed correctly.

#### Using the fusion in Part Design... ie, making holes !

To use all of these profiles in PartDesign, for instance, to make holes

you need to use a fusion of the profile, and create a body...

![Body](images/80-body.png)

1. Drag and drop the fusion into the body.

![base feature](images/81-basefeature.png)

2. Now, you have a standard Part design Body...

You can map a sketch to any face, and use Part design to do whatever you want !

![Making Holes](images/82-create-sketch.png)
![Making Holes](images/82-making-holes.png)

![Holes Made](images/83-holes-made.png)

### Group Container

(my least prefered solution)

A group is just a folder. Simply add your objects into the Group. You are done. Can't be used in assembly for instance. 


## Cutout / Hole

**Cutout / Hole** (shortcut `E, C`; Spanish *Calado*) cuts holes, slots and clearances in a profile from a sketch drawn on one of its faces.

1. Click on the **Cutout / Hole** command. The button is always active while a document is open.
2. Click a planar face of a profile, a trimmed profile or an existing cutout, in the 3D view; a face selected before the command is used too. The end faces (the wall thickness at the profile ends), edges and curved faces cannot be cut: the panel says why. Click another face to change it; with Ctrl+Click on several faces the last one clicked is used, since a cutout takes one face.
3. **OK** creates, in one Undo step, a sketch attached to that face and the cutout, both in the same Part or folder as the profile, and opens the sketch. The cutout and its sketch are labelled after the profile, for example `Profile_TC40x40x1.5_000_Ex` and `Profile_TC40x40x1.5_000_Sketch`. The outline of the face is already in the sketch as construction geometry, so you can dimension the hole against the face edges right away. **Cancel** leaves the document unchanged.
4. Draw closed shapes (circles, rectangles, slots); every sketch tool works, including External Geometry.

![alt text](images/90-draw-sketch.png)

5. Close the sketch: the profile is cut and the **Cutout / Hole** panel opens to set the **Cut type** and the **Depth**. The depth starts at the thickness of the wall under the face and can be changed with **Distance**; every change is previewed. **OK** keeps them in one Undo step. **Cancel** asks whether to delete the new cutout together with its sketch. While the sketch is empty, or a shape is not closed yet, the profile is shown uncut.

The cut types are:

- **One wall** (default of this flow): each closed shape cuts only the wall under the face, as deep as that wall. A hole on the top face of a rectangular tube goes through the top wall and leaves the bottom wall intact. The depth comes from the geometry, so it works on any hollow or open profile.
- **Through All**: the shapes cut through the whole profile, every wall they cross.
- **Distance**: the shapes cut as deep as **Depth** (the **Extrusion Length** property).

The **Pattern** group (Spanish *Patrón*) repeats the sketch in one row along the profile. It is unchecked for a new cutout, which cuts the sketch alone. Checked, it has a row for each side of the sketch, **← Backward** (toward the start of the profile's path) and **Forward →** (toward its end), each with its **Cutouts per side** and **Pitch**. The sketch always stays where you drew it, so "1 every 50 mm backward, the sketch, 2 every 30 mm forward" is one cutout of 4 cuts, and the group title shows the total: **Pattern: 4 cutouts** (Spanish *Patrón: 4 calados*). Each copy cuts like the sketch does, with **One wall** the wall under it. The panel warns, without stopping **OK**, when a cutout reaches past the end of the face. Cutouts may overlap: the preview shows them, and there is no warning for it. Unchecking the group cuts the sketch alone again and keeps the values in the fields; it removes an expression on a **Cutouts per side** field, which **Cancel** brings back. More than 1000 cutouts fail with a message. The pattern needs a face along the profile: an end face has no direction for it, so copies on one fail the cutout with a message, which the panel shows too.

To change the cut type, the depth or the pattern, double-click the cutout: the same panel opens with the stored values, and **Cancel** restores them. To change the holes, press **Edit sketch** in that panel: the cut type and depth shown are kept (one Undo step), the sketch opens, and closing it opens the panel again. **Cancel** there restores the cut type and depth only; the drawing stays as you left it, and **Undo** takes it back. Right-click the cutout in the tree and choose **Edit sketch** to open the sketch alone.

### With your own sketch

You can still cut with a sketch you made yourself: attach a sketch to a face of the profile (Sketch tool, Attach to "Plane Face") and draw the shapes.

![alt text](images/90-create-sketch-on-face.png)

Select the face and the sketch (in either order) and click **Cutout / Hole**: the cutout is created directly, with **Through All**, the sketch is moved into the profile's Part, and a panel opens to choose the cut type.

![alt text](images/92-extrudedcutout-done.png)


## Drill Hole

**Drill Hole** (Spanish *Agujero*) drills round holes on a planar face of a profile, placed from a corner, the middle of an edge or the center of that face, without drawing a sketch. Use **Cutout / Hole** for slots and free shapes.

1. Click on the **Drill Hole** command, next to **Cutout / Hole**. The button is always active while a document is open.
2. Click a planar face of a profile, a trimmed profile or a cutout. The face shows nine circles: its four corners, the middle of each straight edge and its center. A curved edge (an arc of a notch, a hole already in the face) has no middle circle. One click on a circle is where the holes are measured from: a corner measures both offsets from it; the middle of an edge along the profile measures **Offset along** from the middle of the face length and **Offset across** from that edge; the middle of an edge across the profile measures **Offset across** from the middle of the face width and **Offset along** from that edge; the center measures both from the middle of the face, so offsets 0 put the hole there. Each click replaces the previous point, nothing is combined. A click on the face takes the circle nearest to the click, so you do not have to hit it, and a click on a vertex of the face takes that corner. The point the offsets are measured from is the one filled orange circle, the others are white, and the vertex line of the panel names it: the vertex, for example `Vertex3`, `Middle of Edge5` or `Center of the face`. A click on a circle selects nothing under it. A face and a vertex selected before the command are used too. A face selected without a click point (from the tree) keeps the vertex only when the vertex is on it. End faces, edges and curved faces (a round tube, the fillets of a beam) are refused, and the panel says why.
3. Set the holes:
   - **Offset along** and **Offset across**: the distance from the clicked point to the origin of the pattern (the hole at the point), along the profile and across it. A new hole starts at 0 mm, on the picked point: from a corner or an edge it then cuts across the border of the face until you type a distance. Measured from a corner or an edge, positive goes into the face, so "25 mm from the corner" keeps its meaning when the profile is rotated. Measured from the middle of the face, **Offset along** is positive toward the end of the profile's path (the end of the sketch edge it was made on) and negative toward its start, and **Offset across** is positive to one fixed side of the face, whatever corner is stored.
   - **Diameter** of the holes. A new drill hole opens with the diameter of the last one confirmed with **OK** or **Apply and continue** (10 mm the first time), also after restarting FreeCAD; **Cancel** does not change it. A double-clicked drill hole shows its own diameter.
   - **Pattern**: check the group to drill more holes in the same object; unchecked (the default for a new hole) it is one hole at the point the offsets give, and its fields are hidden. Each row adds holes on one side of that point: **Along ← backward**, **Along → forward**, **Across ← backward** and **Across → forward**, each a **Holes per side** count (the holes added on that side, not counting the hole at the point) and a **Pitch** (the distance between them, available once the count is above 0). Forward is the direction an offset is positive in: into the face from a corner or an edge, toward the end of the profile's path along and to the fixed side across from the middle. Holes along and across make a grid. **Hole at the point** (on by default) drills the hole at the point itself; off, a pair on each side of the point has no hole in the middle. For example backward 3 every 20 mm and forward 5 every 30 mm drill 9 holes: 3, the one at the point, then 5. The group title shows the total of holes drilled, for example **Pattern: 9 holes** (Spanish *Patrón: 9 agujeros*). While the group is checked, the panel warns when holes overlap: a side whose **Pitch** is smaller than the **Diameter** (one line for the holes along, one for across), or, with **Hole at the point** off, the two holes on each side of the point closer than the diameter. It is only a warning: OK still drills them, in case you want them to overlap. Unchecking the group drills one hole again and keeps the field values for when you check it again. A drill hole has at most 1000 holes, and at least one: with **Hole at the point** off and every count at 0 the panel says so. A drill hole with a pattern opens with the group checked. Drill holes saved by 1.5.0 with **Count** and **Pitch** open with the same holes, as holes forward along; an expression on **Count** or **Pitch** moves to the forward along row.
   - **Cut type** and **Depth**: **One wall** (default) drills only the wall under the face, **Through All** drills every wall the holes cross, and **Distance** drills as deep as **Depth**. With **One wall** and **Through All** the depth box shows the thickness of the wall under the face.
4. With **Update automatically** checked (the default, remembered), the holes are previewed once you stop typing. Uncheck it to change several values on a heavy model; the panel then says **Pending changes**.
5. **OK** creates the drill hole with the panel values, also when the preview is out of date, in one Undo step. It goes in the same Part or folder as the profile and is labelled after it, for example `Profile_TC40x40x1.5_000_Dh`. **Cancel** leaves the document unchanged.
6. To drill several holes without running the command again, click **Apply and continue** (Spanish *Aplicar y seguir*), next to **OK** and **Cancel** in the panel's button row, instead of **OK**, once a face and a point are picked. It creates the drill hole like **OK**, in its own Undo step, and keeps the panel open waiting for a click on a face, with every value kept (offsets, diameter, pattern, cut type and depth): only the face and the point change with the next click. Click a face of another profile, or of the profile you just drilled, for example its other end or another face of the same tube: that profile now shows the drill hole just created, so the next hole is built on it and both stay cut. **Cancel** then drops only the hole in progress, the applied ones stay; **OK** with no face picked since just closes the panel. The button is not shown while editing a drill hole.

To change a drill hole, double-click it: the same panel opens with the stored values, and clicks change the face and the point. **OK** keeps the changes in one Undo step, or none when nothing changed; **Cancel** restores the stored values. When you move the hole to another profile, the profile it left is shown again, and a hole still labelled after its old profile is labelled after the new one.

The hole remembers where its vertex was. When the profile changes and FreeCAD renumbers its vertices, the hole finds its vertex again and stays in place. When the vertex is gone (for example an **Extend / Cut** or an end offset removed that corner), the hole keeps its place and its **Reference Warning** property, also shown in the panel, says "The reference vertex changed: check the hole." Double-click the hole and pick a point to place it again; the warning also clears when the vertex comes back.

The cut list and the IDs treat a drill hole like a cutout.


## Expressions in panel fields

The number fields of the panels that edit one object take FreeCAD expressions, as in the Part Design panels: click the **Fx** icon at the right of the field, or type `=`, and enter a formula such as `VarSet.HoleDiameter`, `Spreadsheet.Pitch * 2` or `20 mm + 5 mm`. The field then shows the value of the expression and the object keeps the expression, so changing the VarSet or the spreadsheet updates the object.

- **Drill Hole**: every field (**Offset along**, **Offset across**, **Diameter**, the **Holes per side** and **Pitch** of each **Pattern** row, **Depth**). When creating a drill hole the **Fx** icon appears once a face and a point are picked and the preview exists; an expression stays when you pick another face or point.
- **Cutout / Hole**: **Depth**, and the **Cutouts per side** and **Pitch** of each **Pattern** row.
- **Extend / Cut** and **Notch**: **Gap**, while editing (double-click the trim). When creating, one trim is made for each profile, so the Gap is a plain field there.
- **Edit Profile**: the section sizes, **Length**, the weight, the price and the offsets. Choosing another material, family or size fills the section sizes from the catalog again and removes their expressions; the expressions of the other fields stay. The rotation is a list and takes no expression in the panel.

**OK** keeps the expressions with the other values in one Undo step; **Cancel** removes the expressions set in the panel, even with Undo turned off. An expression set before, from the property editor, is shown and kept unless you change or clear it in the panel. The panels that make several objects at once (**Create Profile**, **End Miter**, and **Extend / Cut** and **Notch** while creating) and the **BOM** and **Populate IDs** options have plain fields: set an expression on the created objects from the property editor.


## Add Other elements to your design

Often, when building metallic frames, you will need to add laser-cut parts, or welded nut to your design.

It is adressed in Frameforge, via the "Link" command. 
Mainly it is a "App::Link" object, with an "Attachment" property.

The workflow is the following. 

You have a Part container with your Skeleton Skecths, and your profiles.
Create an object outside the Part, or in another part. (via Part, PartDesign, SheetMetal, whatever)

This is the reference object, that you can send to manufacturer, make nice 2D TechDraw, etc.

Add an object to yout design:
- Select the object in the Tree View
- Click on the "Attached Link" command in FrameForge toolbar.
- It will open the AttachementEditor Task (the same as FreeCAD internal attachement)
- You can then attach your Linked Part to what you want, via Vertexes and Edges of your base sketch.
- Validate the Task
- Then you got a Link to your part that is physically linked to your design.
- Manually move the Link into the Part Container (should be handled automatically)
- et voila ! You've added a Custom part into your design !

If you change the part (the original one) it will update the links automatically 
You can add several links of the same part.

You can add a "Price" property that will be added into the BOM

## Naming/Referencing your Profiles/Links.

When building bigger (> 20 Profiles) designs, it is handy to get ID of the Profiles.

It is addressed as well.

Profiles and FrameForge Links, when created, have an "ID" property, that is empty when the element is inserted.

You can use Populate ID and Reset ID to fill them automatically, regarding your selection and the existing design

Workflow:
- Select Profiles, Links, or Part Container/Fusion/Group.
- Click on "Populate IDs" command in FrameForge toolbar.
- The Populate ID Task opens, configure it the way you want:
    - Allow Duplicating IDs : Don't check for existing IDs inside the document

    - Keep existing IDs : pieces that already have an ID keep it; only the pieces without one are numbered (their IDs are reserved)

    - IDs numbering type : "All Numbers" / "All Letters" / "Number for profiles, letters for Links", "Letters for profiles, Number for links"

    - IDs numbering scheme : 
        - Fill when available (inside selection): number the selection again from 1 (or A), ignoring the IDs of the rest of the document
        - Fill when available (whole document)
        - Start at current document numbering
        - Start at specific number/letter

    - First Number ID: 1 or more
    - First Letter ID: letters A to Z only. OK refuses an empty letter when the scheme starts at a specific letter.


Validate, and voila !

You can also reset the existing document 's IDs with the "Reset IDs" Command

## Create Balloons inside TechDraw

That has been a must have for a LOOONG time !

This tool allows you to create/update Balloons inside a TechDraw View for all Links/Profiles.
(It was so long and error-prone to do it manually !)

Workflow:
- Create a TechDraw Page
- Insert a View with Profiles, Links, Part Container of Profiles and Links

- In the TreeView, select
    - The TechDraw View to fill with balloons. (the View, not a View Group !)
    - All the links and profiles to create balloons for.

- Click on the "Create Balloons" Command in FrameForge toolbar.

Et voila! you've got the balloons, with their arrow pointing at the center of the parts ! 
(you still have to move the balloon itself where you want)

The Balloons are annotated with the Profile/Link ID.

If you change the design, (dimensions) just select the balloons in the TreeView, and launch the "Resfresh Balloons" Command, 
It will update arrow positions and labels accordingly.

## BOM Tool

Another fancy tool is the BOM tool.

You've spend several hours (days ?) to make a nice design, you still have to write the BOM/CutList. That is slow, and error prone.

Just use the BOM tool ! Select the Part Container/Profiles/Links to be taken into account and click on the "Create BOM" Command

It will create a BOM SpreadSheet, and a CutList SpreadSheet.

The BOM contains the Profiles, with their Cut angles, Quantity, Length, Material, ID, Price, Weigth.
It also can contains all the Links, ie the LaserCut Parts for instance.

If selected, you can also create a CutList, **sorted to optimize your work** at the saw.
- Add Kerf and Stock Length.

About Angles:
- If the Object is a Profile, the tool uses BevelsCut A/B - X/Y ("- / *" symbol for same direction cut or 90° rotated cut)
- If the Object is a TrimmedProfile, the tool calculate the angle (angle prefix with "@" symbol)
- If a TrimmedProfile is Perfect Cut (Notch) is is noted "P"

Check your BOM for error !

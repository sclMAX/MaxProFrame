# Profile Library Manager

The Profile Library Manager keeps the catalogs of profiles you use in your frames: steel sections, aluminium extrusions, wood, or your own drawn sections. Open it from the **Manage Profile Libraries** toolbar button.

The window has three areas:

- **Available Libraries** (top left): every catalog you can use.
- **Library Families** (bottom left): the families of the selected library, such as *Square Hollow* or *Custom Profile*.
- **Profiles** (right): the sizes of the selected family, as a table or, for custom profiles, as cards.

Press **F1** or click **?** at any time to open this guide at the section for what you are doing.

## Libraries

Each library has a material and a density, used to calculate profile weights. The list marks its kind:

- **[System]** libraries ship with MaxProFrame. They are read-only: duplicate one to change it.
- **[Folder]** libraries live in a folder you choose, with their sections. Copy or sync that folder to use it on another computer.
- **[User]** libraries are older personal libraries stored in your FreeCAD user folder.

The buttons above the list are, in order: **New Library** (+), **Delete Library** (−), **Import Library**, **Duplicate Library** and **Export Library**. Hover over any button to see what it does. For a folder library, − only unregisters it: the files on disk are kept.

## Create a library

1. Click **New Library** (+).
2. Enter a name and choose the material and density.
3. Check the destination folder. By default a new folder with the library name is created in your user profiles folder; **Choose Folder…** selects another empty folder.
4. Click **OK**. The new library is selected and ready for families.

## Duplicate a system library

System libraries cannot be edited. To start from one of them:

1. Select the library and click **Duplicate Library**.
2. Enter the new name, material and density. Turn on **Recalculate theoretical weights for new material** to update the weights for the new density.
3. Choose the destination folder and click **OK**.

The copy is a folder library you can edit, save and share.

## Share a library

- **Export Library** saves the selected folder library, with its sections, as a ZIP file. Save or cancel pending changes first; system libraries must be duplicated before exporting.
- **Import Library → Import ZIP…** adds a library from a ZIP file into its own folder.
- **Import Library → Register Folder Library** uses an existing library folder in place, for example a shared or synced folder. Select the folder that contains `library.json`.

Existing libraries and files are never overwritten: a name or folder that is already in use is rejected.

## Families

A family groups profiles of the same shape, such as *IPE*, *Square Hollow* or *Custom Profile*.

- **Add Family** (+) opens a list of shapes with a preview. Turn on **With Fillet** for rounded corners when the shape supports it.
- **Delete Family** (−) removes the selected family and its profiles from the library.
- **Standard / Ref** stores the standard or catalog reference of the family, such as *EN 10219*.

Families can only be changed in editable libraries.

## Profiles and sizes

For standard shapes, each table row is one size:

- **Add Size** (+) adds a row; type its code and dimensions in millimeters.
- **Remove Size** (−) asks for confirmation and removes the selected row.
- The weight in kg/m is calculated from the dimensions and the library density.
- **Search this family…** filters the rows by code or description, without caring about case or accents. Clear it to see every profile again; search never deletes anything.

## Custom profiles

The *Custom Profile* family stores any closed section you draw, shown as cards with the section, its code and its weight.

- **Capture Section**: draw the section in a Sketcher sketch with one closed outer outline and any closed holes, select the sketch and click the button.
- **Import DXF**: choose a DXF file with closed polylines, confirm its units, review the section and click **Add as Custom** with a unique code.
- The pencil on a card opens **Edit Properties** to change its code, description and weight. **Edit Section** opens the section in Sketcher; click **OK** in the **Edit Profile** window to keep the new geometry.

Weights of captured and imported sections are calculated from their area and the library density.

## Save your changes

Changes stay pending until you click **Save Changes**, which is enabled only when there is something to save. If you close the window or switch library with pending changes, you can choose **Save**, **Discard** or **Cancel**.

## Use your profiles in a model

Open **Create Profiles**, choose the library in the material list, then the family and the size. Select the path edges in the 3D view and confirm. Custom sections are copied into your document, so the model keeps working without the library.

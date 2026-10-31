# Profile task panel

Create Profiles separates catalog selection from placement. **Profile** and **Placement** start expanded and can be collapsed independently without changing values or previews; **Settings** starts collapsed. Use the heading buttons or Space when focused.

- **Library** chooses the catalog; its material is shown separately. **Size** becomes **Profile** for custom sections. Catalog identifiers and saved `Material` values are unchanged.
- Custom profiles show the selected section's real silhouette, code, description (when supplied), and weight in **kg/m**. Size changes refresh this information; missing or corrupt assets show a safe placeholder. Viewing a thumbnail does not import sketches or modify the catalog, document, selection, or preview state. Standard families retain their dimensional drawings and original colors. Images fit the available width without cropping or stretching; custom silhouettes follow FreeCAD's live native foreground color.
- **Placement** lists the paths being edited. Selecting a whole object uses all its shape edges. Clicking inside a filled sketch likewise selects its entire outline; selecting an individual sketch edge uses only that edge. Faces on other objects and vertices are not expanded into paths. Without paths, enter a positive manual length in **mm**; attached paths disable manual length.
- A normal canvas pick adds a path and activates its row for editing. Clicking a preview from this operation activates its base path instead of creating a profile on the preview; existing profiles remain valid supports. Ctrl-click a listed path or its preview to remove it, or use its **X** button. Pick the path normally to add it again. Replacing or clearing the canvas selection does not remove listed paths or previews; Apply and OK use the retained paths.
- Click an edge row to select it; Ctrl-click adds or removes rows, Shift-click selects a range, and Ctrl+A selects all rows. Selection alone never changes a profile. The header identifies one edge or counts multiple edges. Selected previews are blue; unselected previews keep their appearance. Clearing the list selection disables editing existing profiles. Highlighting does not change FreeCAD's selection and is restored on deselection or closing.
- Common values appear normally; differing values show **Mixed values**, including mirrors, extension and anchors. An explicit edit changes only that property on selected edges. Choosing a different profile preserves their placements. New edges inherit the active edge's settings without changing earlier edges.
- Path alignment, length, rotation, offset, mirrors and extension remain editable in **Placement**. Expand **Settings** below it for naming, container preferences and **Price per metre**. No currency is assumed. Combined bevels are not shown; existing profiles retain their bevel settings.
- **Offset** X and Y displace the profile from its path edge, in **mm**, in the edge frame: X lies in the sketch plane, perpendicular to the edge; Y runs along the sketch normal. Rotating or mirroring the section does not change the direction of the displacement. Offsets are stored per edge like rotation and mirrors; differing values among selected edges show **Mixed values**, and editing one axis changes only that axis. With a nonzero offset, the alignment preview marks where the edge lies with a highlighted crosshair, joined to the selected anchor by a dashed line; the marker is hidden while the offset is mixed. The section never shrinks below half its own fitted size, so its anchors stay readable: when the edge lies farther away, the dashed line ends in an arrow on the preview border pointing toward it, labelled with the typed offset values (for example `X 20 · Y 100 mm`; a zero axis is omitted). The marker uses the theme's highlight color when it contrasts at least 3:1 with the preview background, and the theme's text color otherwise, so it stays readable after FreeCAD theme changes.
- **Information** below Settings starts collapsed and displays only applicable section dimensions and radii as read-only values. Circular sections show diameter; custom section dimensions come from the actual section geometry. Select another profile to update the information. Change section dimensions in the library, not in the task panel; existing fillet settings are retained.
- **Create a part** reuses one Part container for the session's attached paths and profiles, including previews created before selecting this option. Repeated preview updates, Apply and OK do not create additional Parts. Custom-section sketches remain shared library sources; their profile links can cross Part boundaries.
- **Apply** creates or updates the preview without closing the panel. **OK** applies the latest values and confirms; **Cancel** discards the session preview. The status reads **No preview**, **Pending changes**, or **Preview updated**. Edits update the selected previews immediately.

Edit Profile retains live updates, including when its catalog is unavailable. Its naming controls remain disabled and its creation-only preview actions remain hidden. Task-panel controls inherit FreeCAD styling and palette; Spanish labels do not change Python commands or preference keys.

# Code Snippets
There is no way to add a button, menu entry from python to a workbench which is added with c++. So here is a comparison how to do that with python and with c++.

## Adding a command:
This can be done either with python or c++.

### 1. python

```python
import FreeCAD as App

class MyCommand(object):
    def IsActive(self):
        """
        availability of the command (eg.: check for existence of a document,...)
        if this function returns False, the menu/ buttons are ßdisabled (gray)
        """
        if App.ActiveDocument is None:
            return False
        else:
            return True

    def GetResources(self):
        """
        resources which are used by buttons and menu-items
        """
        return {'Pixmap': 'path_to_icon.svg', 'MenuText': 'my command', 'ToolTip': 'very short description'}

    def Activated(self):
        """
        the function to be handled, when a user starts the command
        """
```
To register the command in FreeCAD:

```python
import FreeCADGui as Gui
Gui.addCommand('MyCommand', MyCommand())
```

Adding a new toolbar/menu:
```python
from FreeCADGui import Workbench
class myWorkbench(Workbench):
    MenuText = "name_of_workbench"
    ToolTip = "short description of workbench"
    Icon = "path_to_icon.svg"

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Initialize(self):
        self.appendToolbar("Gear", ["MyCommand"])
        self.appendMenu("Gear", ["MyCommand"])
```

### 2. C++

```c++

#include <App/Document.h>
#include <Gui/Command.h>
#include <Gui/Control.h>
#include <Gui/Document.h>

using namespace std;

DEF_STD_CMD_A(MyCommand)

MyCommand::MyCommand()
  : Command("MyCommand")
{
    sAppModule    = "module";
    sGroup        = QT_TR_NOOP("Mesh");
    sMenuText     = QT_TR_NOOP("my command");
    sToolTipText  = QT_TR_NOOP("very short description");
    sWhatsThis    = "MyCommand";
    sStatusTip    = sToolTipText;
}

void MyCommand::activated(int)
{
    // the function to be handled, when a user starts the command
}

bool MyCommand::isActive(void)
{
    // availability of the command (eg.: check for existence of a document,...)
    // if this function returns False, the menu/ buttons are ßdisabled (gray)
    return (hasActiveDocument() && !Gui::Control().activeDialog());
}
```
To register the command in FreeCAD:

```c++
#include <Gui/Command.h>

Gui::CommandManager &rcCmdMgr = Gui::Application::Instance->commandManager();
rcCmdMgr.addCommand(new MyCommand());
```
Adding a item to a menu/toolbar:

if your command is added with python you have to run this code:
in src/module/Gui/AppModuleGui.cpp add to PyMOD_INIT_FUNC:

```c++
// try to instantiate a python module
try{
    Base::Interpreter().runStringObject("import MyCommands");
} catch (Base::PyException &err){
    err.ReportException();
}
```

and add the name of the command to a tooltip/menu in src/module/Gui/Workbench.cpp Workbench::setupToolBars


```c++
Gui::ToolBarItem* Workbench::setupToolBars() const
{
    Gui::ToolBarItem* root = StdWorkbench::setupToolBars();
    Gui::ToolBarItem* myToolbar = new Gui::ToolBarItem(root);
    myToolbar->setCommand("my_commands");
    *myToolbar << "MyCommand";
    return root;
}
```

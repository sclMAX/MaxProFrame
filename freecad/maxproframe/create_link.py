import os

import AttachmentEditor.TaskAttachmentEditor as TaskAttachmentEditor
import FreeCAD as App
import FreeCADGui as Gui

from freecad.maxproframe._utils import getRootObject
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, add_command
from freecad.maxproframe.version import __version__ as ff_version


def makeLink(source):
    doc = App.ActiveDocument

    link = doc.addObject("App::Link", source.Label + "_Link")
    link.LinkedObject = source

    link.addExtension("Part::AttachExtensionPython")
    link.MapMode = "Deactivated"

    link.addProperty(
        "App::PropertyString",
        "MaxProFrameVersion",
        "MaxProFrame",
        "MaxProFrame version used to create the object",
    ).MaxProFrameVersion = ff_version

    link.addProperty(
        "App::PropertyString",
        "PID",
        "MaxProFrame",
        "Profile ID",
    ).PID = ""

    doc.recompute()
    return link


class LinkCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "link.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_Link", "Attached Link"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_Link",
                "Create a link with attachment",
            ),
        }

    def IsActive(self):
        return bool(App.ActiveDocument) and bool(Gui.Selection.getSelection())

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if not sel:
            return

        App.ActiveDocument.openTransaction("Create Links")
        roots = set()
        for obj in sel:
            roots.add(getRootObject(obj))

        for root in roots:
            link = makeLink(root)
            Gui.Control.showDialog(TaskAttachmentEditor.AttachmentEditorTaskPanel(link))
        App.ActiveDocument.commitTransaction()


add_command("MaxProFrame_Link", LinkCommand())

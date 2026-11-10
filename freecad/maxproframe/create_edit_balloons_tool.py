import os
from collections import defaultdict

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

from freecad.maxproframe._utils import (
    get_profiles_and_links_from_object,
    is_extrudedcutout,
    is_fusion,
    is_group,
    is_link,
    is_part,
    is_profile,
    is_trimmedbody,
)
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    PROFILEIMAGES_PATH,
    PROFILESPATH,
    QT_TRANSLATE_NOOP,
    UIPATH,
    add_command,
    translate,
)

# Paper distance between the arrow tip and the bubble of a new balloon.
BUBBLE_OFFSET_MM = 20
STATUS_TIMEOUT_MS = 10000
CREATE_COMMAND = "MaxProFrame_CreateBalloons"
REFRESH_COMMAND = "MaxProFrame_RefreshBalloons"


def is_balloon_view(obj):
    """A TechDraw view of a shape a balloon can point into; detail views use their own frame."""
    return obj.isDerivedFrom("TechDraw::DrawViewPart") and not obj.isDerivedFrom("TechDraw::DrawViewDetail")


def is_usable_view(obj):
    """A balloon view on a page: the page receives the balloons."""
    return is_balloon_view(obj) and find_page(obj) is not None


def is_balloon_piece(obj):
    return (
        is_fusion(obj)
        or is_part(obj)
        or is_group(obj)
        or is_profile(obj)
        or is_trimmedbody(obj)
        or is_extrudedcutout(obj)
        or is_link(obj)
    )


def is_maxproframe_balloon(obj):
    return obj.TypeId == "TechDraw::DrawViewBalloon" and "TargetName" in obj.PropertiesList


def piece_id(obj):
    """The ID of ``obj`` itself, else "": an App::Link would read the PID of what it links."""
    return obj.PID if "PID" in obj.PropertiesList else ""


def show_status(message, timeout=STATUS_TIMEOUT_MS):
    Gui.getMainWindow().statusBar().showMessage(message, timeout)


def is_alive(obj):
    """False once ``obj`` was deleted or its document closed."""
    try:
        return obj.Document.getObject(obj.Name) is not None
    except Exception:
        return False


def apply_in_transaction(doc, name, title, apply):
    """Run ``apply`` as one undo step; a failure leaves ``doc`` as it was and is reported."""
    doc.openTransaction(name)
    try:
        apply()
    except Exception as error:
        doc.abortTransaction()
        App.Console.PrintError("{}: {}\n".format(title, error))
        show_status("{}: {}".format(title, error))
        return False
    doc.commitTransaction()
    return True


def place_balloon(balloon, obj, move_balloon=False):
    """Point ``balloon`` at the center of ``obj`` and write its ID.

    OriginX/Y and X/Y are unscaled view coordinates: TechDraw multiplies them by the view scale.
    """
    view = balloon.SourceView
    P = Part.getShape(obj).CenterOfGravity

    D = view.Direction.normalize()
    X = view.XDirection.normalize()
    Y = D.cross(X).normalize()

    C = view.getGeometricCenter()

    d = P.sub(C)
    x2d = d.dot(X)
    y2d = d.dot(Y)

    balloon.OriginX = x2d
    balloon.OriginY = y2d

    if move_balloon:
        offset = BUBBLE_OFFSET_MM / view.getScale()
        balloon.X = x2d + offset
        balloon.Y = y2d + offset

    balloon.Text = piece_id(obj)


def find_page(view):
    """The page showing ``view``, directly or through its projection group or clip.

    Not any page that depends on it: a detail view of it may sit on another page.
    """
    for parent in view.InList:
        if parent.isDerivedFrom("TechDraw::DrawPage"):
            return parent
    for parent in view.InList:
        if parent.isDerivedFrom("TechDraw::DrawProjGroup") or parent.isDerivedFrom("TechDraw::DrawViewClip"):
            return find_page(parent)
    return None


def create_balloon(page, view, src_obj):
    doc = view.Document
    balloon = doc.addObject("TechDraw::DrawViewBalloon", f"Balloon_{src_obj.Label}")
    balloon.addProperty("App::PropertyString", "TargetName", "MaxProFrame", "Target Profile").TargetName = src_obj.Name
    balloon.SourceView = view
    page.addView(balloon)

    place_balloon(balloon, src_obj, move_balloon=True)
    return balloon


def view_balloons(view):
    return [
        b
        for b in view.Document.Objects
        if is_maxproframe_balloon(b) and b.SourceView is not None and b.SourceView.Name == view.Name
    ]


def view_sources(view):
    # Not XSource: a balloon keeps only the Name of its piece, found again in its own document.
    return list(view.Source)


def create_balloons(view, selected_pieces=None):
    """Mark the pieces of ``view``, or only ``selected_pieces``, that have no balloon in it yet."""
    title = translate("frameforge", "Create Balloons")
    page = find_page(view)
    sources = view_sources(view) if selected_pieces is None else [o for o in selected_pieces if is_alive(o)]

    profiles, links = [], []
    for s in sources:
        get_profiles_and_links_from_object(profiles, links, s)
    # A piece reached twice, as by itself and through its group, gets one balloon.
    pieces = list({o.Name: o for o in profiles + links}.values())

    marked = {b.TargetName for b in view_balloons(view)}
    already = [o for o in pieces if o.Name in marked]
    new = [o for o in pieces if o.Name not in marked]
    with_id = [o for o in new if piece_id(o)]
    without_id = [o for o in new if not piece_id(o)]

    if with_id:

        def apply():
            for o in with_id:
                create_balloon(page, view, o)

        if not apply_in_transaction(view.Document, "Create Balloons", title, apply):
            return

    message = translate("frameforge", "Balloons created: {}.").format(len(with_id))
    if already:
        message += " " + translate("frameforge", "Already had a balloon: {}.").format(len(already))
    if without_id:
        message += " " + translate("frameforge", "Without ID: {} (run Populate IDs).").format(len(without_id))
        App.Console.PrintMessage(
            "{}: {}: {}\n".format(title, translate("frameforge", "without ID"), ", ".join(o.Label for o in without_id))
        )
    show_status(message)


def refresh_balloons(balloons):
    targets = [(b, b.Document.getObject(b.TargetName)) for b in balloons]
    found = [(b, o) for b, o in targets if o is not None]
    missing = len(targets) - len(found)

    if found:

        def apply():
            for b, o in found:
                place_balloon(b, o)

        title = translate("frameforge", "Refresh Balloons")
        if not apply_in_transaction(found[0][0].Document, "Refresh Balloons", title, apply):
            return

    message = translate("frameforge", "Balloons refreshed: {}.").format(len(found))
    if missing:
        message += " " + translate("frameforge", "Piece not found: {}.").format(missing)
    show_status(message)


class ViewPicker(QtCore.QObject):
    """Wait for one click on a TechDraw view, then run ``action`` with it.

    A selection outside TechDraw or Esc cancels; a TechDraw object that is no view (page, template,
    balloon, projection group frame) or an empty click keeps waiting.
    """

    def __init__(self, owner, title, action):
        super().__init__()
        self.owner = owner
        self.title = title
        self.action = action
        self.doc_name = App.ActiveDocument.Name
        self.waiting = False
        self.attached = False

    def start(self):
        Gui.Selection.addObserver(self)
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.attached = True
        self.waiting = True
        # No timeout: the prompt stays while the pick waits.
        show_status("{}: {}".format(self.title, translate("frameforge", "Click a TechDraw view (Esc to cancel).")), 0)

    def detach(self):
        if self.attached:
            self.attached = False
            Gui.Selection.removeObserver(self)
            QtWidgets.QApplication.instance().removeEventFilter(self)

    def stop(self):
        """End the wait; returns False if it had already ended."""
        global _active_picker
        if not self.waiting:
            return False
        self.waiting = False
        if _active_picker is self:
            _active_picker = None
        return True

    def cancel(self):
        if self.stop():
            self.detach()
            show_status("{}: {}".format(self.title, translate("frameforge", "Cancelled.")))

    def resolve_view(self, obj, sub):
        """The view clicked: ``obj`` itself, or the view named in a sub-object path such as "Front.Edge3"."""
        if is_usable_view(obj):
            return obj
        for name in reversed((sub or "").split(".")[:-1]):
            child = obj.Document.getObject(name)
            if child is not None and is_usable_view(child):
                return child
        return None

    def addSelection(self, doc_name, obj_name, sub, pnt):
        if not self.waiting:
            return
        doc = App.listDocuments().get(doc_name)
        obj = doc.getObject(obj_name) if doc is not None and doc_name == self.doc_name else None
        view = self.resolve_view(obj, sub) if obj is not None else None
        if view is None and obj is not None and obj.TypeId.startswith("TechDraw::"):
            if obj.isDerivedFrom("TechDraw::DrawViewDetail"):
                message = translate("frameforge", "A detail view gets no balloons: click another view (Esc to cancel).")
                show_status("{}: {}".format(self.title, message), 0)
            return
        # The document must not change, nor the observer go, inside the selection callback.
        self.stop()
        QtCore.QTimer.singleShot(0, lambda: self.finish(view))

    def finish(self, view):
        self.detach()
        if view is None or not is_alive(view):
            show_status("{}: {}".format(self.title, translate("frameforge", "Cancelled.")))
            return
        self.action(view)

    def eventFilter(self, watched, event):
        if not self.waiting or event.type() not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            return False
        if event.key() != QtCore.Qt.Key_Escape:
            return False
        if event.type() == QtCore.QEvent.ShortcutOverride:
            # Claim Esc so no shortcut takes it: the key press follows.
            event.accept()
        else:
            self.cancel()
        return True


_active_picker = None


def cancel_view_pick():
    """Cancel the click a command waits for; returns the command that was waiting, else None."""
    picker = _active_picker
    if picker is None:
        return None
    picker.cancel()
    return picker.owner


def pick_view(owner, title, action):
    """Wait for a click on a view for the command ``owner``; callers cancel any wait first."""
    global _active_picker
    _active_picker = ViewPicker(owner, title, action)
    _active_picker.start()


class CreateBalloonsCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "create-balloons.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_CreateBalloons", "Create Balloons"),
            "Accel": "M, O",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_CreateBalloons",
                "<b>Create a balloon with the ID of each piece of a TechDraw view</b><br><br>"
                "Select a view, or click the button and then a view. Pieces that already have a balloon are "
                "skipped. Select pieces with the view to mark only those.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        # Any click still awaited is cancelled; if it was this command's, pressing it again only cancels.
        if cancel_view_pick() == CREATE_COMMAND:
            return
        selection = Gui.Selection.getSelection()
        views = [s for s in selection if is_usable_view(s)]
        # Pieces selected alone are kept for the view clicked next.
        pieces = [s for s in selection if is_balloon_piece(s)] or None

        if len(views) > 1:
            show_status(translate("frameforge", "More than one TechDraw view is selected: select one."))
        elif views:
            create_balloons(views[0], pieces)
        else:
            pick_view(
                CREATE_COMMAND,
                translate("frameforge", "Create Balloons"),
                lambda view: create_balloons(view, pieces),
            )


class RefreshBalloonsCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "refresh-balloons.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_RefreshBalloons", "Refresh Balloons"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_RefreshBalloons",
                "<b>Refresh balloons</b><br><br>"
                "Select balloons or a view, or click the button and then a view: the arrows follow their pieces "
                "and the texts their IDs.",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        # Any click still awaited is cancelled; if it was this command's, pressing it again only cancels.
        if cancel_view_pick() == REFRESH_COMMAND:
            return
        selection = Gui.Selection.getSelection()
        balloons = [b for b in selection if is_maxproframe_balloon(b)]
        views = [s for s in selection if is_usable_view(s)]

        if balloons:
            refresh_balloons(balloons)
        elif views:
            refresh_balloons([b for v in views for b in view_balloons(v)])
        else:
            pick_view(
                REFRESH_COMMAND,
                translate("frameforge", "Refresh Balloons"),
                lambda view: refresh_balloons(view_balloons(view)),
            )


add_command(CREATE_COMMAND, CreateBalloonsCommand())
add_command(REFRESH_COMMAND, RefreshBalloonsCommand())

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import is_extrudedcutout, is_profile, is_trimmedbody
from freecad.maxproframe.create_profiles_tool import place_in_container_of
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, UIPATH, add_command, get_param_group, translate
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile


def _trim_chain(obj):
    """``obj`` and the bodies it is built on, through trims and cutouts."""
    while obj is not None:
        yield obj
        if is_trimmedbody(obj):
            obj = obj.TrimmedBody
        elif is_extrudedcutout(obj):
            obj = obj.baseObject[0] if obj.baseObject else None
        else:
            obj = None


def _selected_items():
    """The selection as (object, sub-element names) per object, in selection order; "" is the whole object."""
    # getSelectionEx drops a whole-object pick when a sub-element of the same object is picked too.
    doc = App.ActiveDocument
    items = {}
    for sel in Gui.Selection.getCompleteSelection():
        obj = sel.Object
        if doc is None or obj.Document.Name != doc.Name:
            continue
        items.setdefault(obj.Name, (obj, []))[1].extend(sel.SubElementNames or ("",))
    return [(obj, tuple(subs)) for obj, subs in items.values()]


def _trim_name(body):
    return "TrimmedProfile" if body is None else f"{body.Name}_Tr"


def trimmed_body_problem(fp, obj):
    """Why ``obj`` cannot be the body trimmed by ``fp`` (None while creating), or None when it can."""
    if not (is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj)):
        return translate("frameforge", "{} is not a profile").format(obj.Label)
    if fp is not None and fp in _trim_chain(obj):
        return translate("frameforge", "{} cannot trim itself").format(obj.Label)
    return None


class CreateTrimmedProfileTaskPanel:
    """End Trim panel. ``selection`` items are (object, sub-element names): the first one is the
    trimmed body, the others are its trimming faces. Invalid items are skipped and explained."""

    def __init__(self, fp, mode, selection=()):
        ui_file = os.path.join(UIPATH, "create_trimmed_profiles.ui")
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(ui_file))

        self.fp = fp
        self.doc = fp.Document
        self.mode = mode
        # Visibility of every body the panel assigned, by name, as it was before: Cancel restores it.
        self._visibility = {}

        self.initialize_ui()

        messages = []
        if selection:
            messages += self._set_body(selection[0][0])
            messages += self._add_boundaries(selection[1:])
        self.update_view_and_model(messages)

    def initialize_ui(self):
        add_icon = QtGui.QIcon(os.path.join(ICONPATH, "list-add.svg"))
        remove_icon = QtGui.QIcon(os.path.join(ICONPATH, "list-remove.svg"))
        coped_type_icon = QtGui.QIcon(os.path.join(ICONPATH, "corner-coped-type.svg"))
        simple_type_icon = QtGui.QIcon(os.path.join(ICONPATH, "corner-simple-type.svg"))

        QSize = QtCore.QSize(32, 32)

        self.form.rb_perfectfit.setIcon(coped_type_icon)
        self.form.rb_perfectfit.setIconSize(QSize)
        self.form.rb_simplefit.setIcon(simple_type_icon)
        self.form.rb_simplefit.setIconSize(QSize)

        # A new trim starts with the last cut type used; an edited trim shows its own.
        if self.mode == "creation":
            default = get_param_group().GetString("Default Cut Type")
            if default in ("Perfect fit", "Simple fit"):
                self.fp.CutType = default
        if self.fp.CutType == "Simple fit":
            self.form.rb_simplefit.setChecked(True)
        else:
            self.form.rb_perfectfit.setChecked(True)

        self.form.rb_perfectfit.toggled.connect(lambda checked: checked and self.update_cuttype("Perfect fit"))
        self.form.rb_simplefit.toggled.connect(lambda checked: checked and self.update_cuttype("Simple fit"))

        self.form.add_trimmed_object_button.setIcon(add_icon)
        self.form.add_boundary_button.setIcon(add_icon)
        self.form.remove_boundary_button.setIcon(remove_icon)

        self.form.add_trimmed_object_button.clicked.connect(self.set_trimmed_body)
        self.form.add_boundary_button.clicked.connect(self.add_trimming_bodies)
        self.form.remove_boundary_button.clicked.connect(self.remove_trimming_bodies)

    def update_cuttype(self, cuttype):
        self.fp.CutType = cuttype

        self.update_view_and_model()

    def _set_body(self, obj):
        """Make ``obj`` (whole object or any of its sub-elements) the trimmed body; return the problems."""
        problem = trimmed_body_problem(self.fp, obj)
        if problem is not None:
            return [problem]
        for body in _trim_chain(obj):
            self._visibility.setdefault(body.Name, (body, body.ViewObject.Visibility))
        self.fp.TrimmedBody = obj
        place_in_container_of(self.fp, obj)
        return []

    def _is_own_body(self, obj):
        return obj in _trim_chain(self.fp) or self.fp in _trim_chain(obj)

    def _add_boundaries(self, items):
        """Add every face of ``items`` as a boundary of its own; return the problems."""
        messages = []
        boundaries = [(obj, (sub,)) for obj, subs in self.fp.TrimmingBoundary for sub in subs]
        for obj, subs in items:
            if self._is_own_body(obj):
                messages.append(translate("frameforge", "{} cannot trim itself").format(obj.Label))
                continue
            if not subs or "" in subs:
                messages.append(translate("frameforge", "{}: select a face, not the whole object").format(obj.Label))
            for sub in subs:
                if not sub:
                    continue
                if not isinstance(obj.getSubObject(sub), Part.Face):
                    messages.append(translate("frameforge", "{}: {} is not a face").format(obj.Label, sub))
                elif (obj, (sub,)) not in boundaries:
                    boundaries.append((obj, (sub,)))
        self.fp.TrimmingBoundary = boundaries
        return messages

    def set_trimmed_body(self):
        items = _selected_items()
        if items:
            messages = self._set_body(items[0][0])
        else:
            messages = [translate("frameforge", "Select the profile to trim")]
        self.update_view_and_model(messages)

    def add_trimming_bodies(self):
        items = _selected_items()
        if items:
            messages = self._add_boundaries(items)
        else:
            messages = [translate("frameforge", "Select the faces that trim the profile")]
        self.update_view_and_model(messages)

    def remove_trimming_bodies(self):
        selected_tb = [item.data(1) for item in self.form.boundaries_list_widget.selectedItems()]
        self.fp.TrimmingBoundary = [tb for tb in self.fp.TrimmingBoundary if tb not in selected_tb]

        self.update_view_and_model([])

    def update_view_and_model(self, messages=None):
        """Show the trim and recompute it; ``messages`` (None keeps the current ones) explain skipped items."""
        if self.fp.TrimmedBody is not None:
            self.form.trimmed_object_label.setText(
                "{} ({})".format(self.fp.TrimmedBody.Label, self.fp.TrimmedBody.Name)
            )
        else:
            self.form.trimmed_object_label.setText(translate("frameforge", "Select..."))

        self.form.boundaries_list_widget.clear()

        for bound in self.fp.TrimmingBoundary:
            item = QtGui.QListWidgetItem()
            item.setText("{} ({} {})".format(bound[0].Label, bound[0].Name, ", ".join(bound[1])))
            item.setData(1, bound)
            self.form.boundaries_list_widget.addItem(item)

        if messages is not None:
            self.form.message_label.setText("\n".join(messages))

        self.fp.recompute()

    def open(self):
        # A new trim is created inside the command's transaction; an edit gets its own.
        if self.mode == "edition":
            self.doc.openTransaction("Update Trim")

    def _close_edit(self):
        if self.mode != "edition":
            return
        gui_doc = Gui.getDocument(self.doc.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def reject(self):
        name = self.fp.Name
        # Aborting undoes everything since the command or the edit started: no Undo entry is left.
        self.doc.abortTransaction()
        if self.mode == "creation" and self.doc.getObject(name) is not None:
            # Undo is disabled: nothing was recorded, so the new trim is removed by hand.
            self.doc.removeObject(name)
        for body, visible in self._visibility.values():
            body.ViewObject.Visibility = visible
        self.doc.recompute()
        self._close_edit()
        return True

    def accept(self):
        if self.fp.TrimmedBody is None:
            self.form.message_label.setText(translate("frameforge", "Select the profile to trim"))
            return False

        get_param_group(writable=True).SetString("Default Cut Type", self.fp.CutType)

        self.doc.recompute()
        self.doc.commitTransaction()
        self._close_edit()
        return True


class TrimProfileCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "corner-end-trim.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_TrimProfiles", "Trim Profile"),
            "Accel": "M, C",
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_TrimProfiles",
                "<b>Trim a profile</b><br><br>Select a profile, then faces of another profile.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        doc = App.ActiveDocument
        selection = _selected_items()
        body = selection[0][0] if selection else None
        if body is not None and trimmed_body_problem(None, body) is not None:
            body = None

        # One transaction from here to OK or Cancel: OK is one Undo step, Cancel leaves none.
        doc.openTransaction("Make Trimmed Profile")
        try:
            trimmed_profile = self.make_trimmed_profile(name=_trim_name(body))
            panel = CreateTrimmedProfileTaskPanel(trimmed_profile, mode="creation", selection=selection)
            Gui.Control.showDialog(panel)
        except Exception:
            doc.abortTransaction()
            raise

    def make_trimmed_profile(self, trimmedBody=None, trimmingBoundary=None, name=None):
        doc = App.ActiveDocument

        trimmed_profile = doc.addObject("Part::FeaturePython", name or _trim_name(trimmedBody))

        if trimmedBody is not None:
            place_in_container_of(trimmed_profile, trimmedBody)

        TrimmedProfile(trimmed_profile)

        ViewProviderTrimmedProfile(trimmed_profile.ViewObject)
        trimmed_profile.TrimmedBody = trimmedBody
        trimmed_profile.TrimmingBoundary = trimmingBoundary

        trimmed_profile.TrimmedProfileType = "End Trim"

        return trimmed_profile


add_command("MaxProFrame_TrimProfiles", TrimProfileCommand())

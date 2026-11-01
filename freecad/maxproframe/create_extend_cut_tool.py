import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtGui

from freecad.maxproframe.create_end_miter_tool import _base_profile, _ctrl_held, _failures
from freecad.maxproframe.create_profiles_tool import place_in_container_of
from freecad.maxproframe.create_trimmed_profiles_tool import _selected_items, _trim_chain, trimmed_body_problem
from freecad.maxproframe.ff_tools import ICONPATH, QT_TRANSLATE_NOOP, UIPATH, add_command, translate
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile


def make_extend_cut_profile(body, target, gap=0.0):
    """Extend Cut of ``body`` up to ``target``, placed in the body's own container.

    ``target`` is (object, face names): one face, or none for a whole profile.
    """
    obj = body.Document.addObject("Part::FeaturePython", f"{body.Name}_Tr")
    place_in_container_of(obj, body)
    TrimmedProfile(obj)
    if getattr(obj, "ViewObject", None) is not None:
        ViewProviderTrimmedProfile(obj.ViewObject)
    obj.TrimmedBody = body
    # A link to a whole object is stored with an empty sub-element name.
    obj.TrimmingBoundary = [(target[0], tuple(target[1]) or ("",))]
    obj.TrimGap = gap
    obj.TrimmedProfileType = "Extend Cut"
    return obj


def _related(a, b):
    """Whether ``a`` and ``b`` are the same body or one is built on the other."""
    return a in _trim_chain(b) or b in _trim_chain(a)


def show_panel(panel):
    Gui.Control.showDialog(panel)
    Gui.Selection.addObserver(panel)


class ExtendCutTaskPanel:
    """One target (a planar face or a whole profile) and the profiles extended or cut up to its plane.

    ``selection`` items are (object, sub-element names): the first one is the target, the others
    are profiles. Clicks set the target first, then add whole profiles. With ``edited`` (an
    existing Extend Cut) the panel changes its target and gap.
    """

    def __init__(self, selection=(), edited=None):
        ui_file = os.path.join(UIPATH, "extend_cut.ui")
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(ui_file))
        # FreeCAD may close the dialog without OK, Cancel or closed(): the form is then deleted.
        self.form.destroyed.connect(self._form_gone)
        self._translate_form()
        self.form.remove_button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, "list-remove.svg")))
        self.form.remove_button.clicked.connect(self.remove_selected)

        self.edited = edited
        self.target = None
        self.profiles = []
        self._closed = False
        self.doc = App.ActiveDocument
        messages = []
        if edited is not None:
            self.doc = edited.Document
            self.form.setWindowTitle(translate("frameforge", "Edit Extend / Cut"))
            self.form.hint_label.setText(translate("frameforge", "Click a face to change the target."))
            self.form.remove_button.hide()
            obj, subs = edited.TrimmingBoundary[0]
            self.target = (obj, tuple(sub for sub in subs if sub))
            self.profiles = [edited.TrimmedBody]
            self.form.sb_gap.setValue(edited.TrimGap.Value)
        elif selection:
            messages += self._set_target(*selection[0])
            for obj, _ in selection[1:]:
                messages += self._add_profile(obj)
        self._show(messages)

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, translate("frameforge", "Extend / Cut")),
            (form.groupBox_target.setTitle, translate("frameforge", "Target")),
            (form.groupBox_profiles.setTitle, translate("frameforge", "Profiles")),
            (
                form.hint_label.setText,
                translate("frameforge", "Click the profiles to extend or cut. Ctrl+click drops one."),
            ),
            (form.remove_button.setText, translate("frameforge", "Remove")),
            (form.gap_label.setText, translate("frameforge", "Gap")),
        ):
            setter(text)

    def _set_target(self, obj, subs):
        """Make ``obj`` the target: its first face, or the whole profile without one; return the problems."""
        faces = [sub for sub in subs if sub]
        if faces:
            if not isinstance(obj.getSubObject(faces[0]), Part.Face):
                return [translate("frameforge", "{}: {} is not a face").format(obj.Label, faces[0])]
        else:
            problem = trimmed_body_problem(None, obj)
            if problem is not None:
                return [problem]
        if any(_related(obj, profile) for profile in self.profiles):
            return [translate("frameforge", "{} cannot trim itself").format(obj.Label)]
        self.target = (obj, tuple(faces[:1]))
        return []

    def set_target(self, obj, subs=()):
        self._show(self._set_target(obj, subs))

    def _add_profile(self, obj):
        """List ``obj`` as a profile to extend or cut; return the problems."""
        if _base_profile(obj) is None:
            return [translate("frameforge", "{} is not a profile").format(obj.Label)]
        if self.target is not None and _related(obj, self.target[0]):
            return [translate("frameforge", "{} cannot trim itself").format(obj.Label)]
        if obj not in self.profiles:
            self.profiles.append(obj)
        return []

    def remove_selected(self):
        rows = {self.form.profiles_list.row(item) for item in self.form.profiles_list.selectedItems()}
        self.profiles = [obj for row, obj in enumerate(self.profiles) if row not in rows]
        self._show([])

    def _show(self, messages):
        """Show the target, the profiles and ``messages``."""
        if self.target is None:
            text = translate("frameforge", "Click a face, or select a profile in the tree.")
        else:
            obj, faces = self.target
            text = " ".join([f"{obj.Label} ({obj.Name})", *faces])
        self.form.target_label.setText(text)
        self.form.profiles_list.clear()
        for obj in self.profiles:
            self.form.profiles_list.addItem(f"{obj.Label} ({obj.Name})")
        self.form.message_label.setText("\n".join(messages))

    def _active(self):
        if self._closed:
            return False
        if self.form is None:
            self._form_gone()
            return False
        return True

    def _form_gone(self, *args):
        if not self._closed:
            self.clean()

    def addSelection(self, doc, obj, sub, other):
        if not self._active():
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source is None:
            return
        if self.edited is not None or self.target is None:
            messages = self._set_target(source, (sub,))
        elif _ctrl_held() and source in self.profiles:
            # Ctrl+click toggles: a listed profile leaves the list.
            self.profiles.remove(source)
            messages = []
        else:
            messages = self._add_profile(source)
        self._show(messages)

    def removeSelection(self, doc, obj, sub):
        # A profile leaves the list once nothing of it is selected (a Ctrl+click on its selected face).
        if not self._active() or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source in self.profiles and not any(s.Object == source for s in Gui.Selection.getSelectionEx("*")):
            self.profiles.remove(source)
            self._show([])

    def clearSelection(self, other):
        pass

    def closed(self):
        # FreeCAD can close the dialog without OK or Cancel (document closed, another dialog shown).
        self.clean()

    def clean(self):
        self._closed = True
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _close_edit(self):
        gui_doc = Gui.getDocument(self.edited.Document.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def reject(self):
        # Nothing is changed before OK, so there is nothing to undo or restore.
        self.clean()
        if self.edited is not None:
            self._close_edit()
        return True

    def _missing(self):
        if self.target is None:
            return translate("frameforge", "Select the target face or profile.")
        if not self.profiles:
            return translate("frameforge", "Select the profiles to extend or cut.")
        return ""

    def accept(self):
        error = self._missing()
        if error:
            self._show([error])
            return False
        gap = self.form.sb_gap.value()
        if self.edited is not None:
            return self._accept_edit(gap)

        # The bodies the new trims hide, as they were: a failed OK shows them again.
        visibility = [(body, body.ViewObject.Visibility) for obj in self.profiles for body in _trim_chain(obj)]
        created = []
        self.doc.openTransaction("Make Extend Cut")
        try:
            for obj in self.profiles:
                created.append(make_extend_cut_profile(obj, self.target, gap))
            # A trim that fails to recompute does not raise: its status tells.
            self.doc.recompute()
            error = _failures(created)
        except Exception as exception:
            error = str(exception)
        if error:
            # Nothing is kept: the panel stays open with the error.
            names = [obj.Name for obj in created]
            self.doc.abortTransaction()
            for name in names:
                # Undo is disabled: nothing was recorded, so the trims are removed by hand.
                if self.doc.getObject(name) is not None:
                    self.doc.removeObject(name)
            for body, visible in visibility:
                body.ViewObject.Visibility = visible
            self.doc.recompute()
            self._show([error])
            return False
        self.doc.commitTransaction()
        self.clean()
        return True

    def _accept_edit(self, gap):
        doc = self.edited.Document
        obj, faces = self.target
        doc.openTransaction("Edit Extend Cut")
        try:
            self.edited.TrimmingBoundary = [(obj, faces or ("",))]
            self.edited.TrimGap = gap
            doc.recompute()
            error = _failures([self.edited])
        except Exception as exception:
            error = str(exception)
        if error:
            # Keep the panel open with the trim as it was before OK.
            doc.abortTransaction()
            doc.recompute()
            self._show([error])
            return False
        doc.commitTransaction()
        self.clean()
        self._close_edit()
        return True


class ExtendCutCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "trim_extend.svg"),
            "MenuText": QT_TRANSLATE_NOOP("MaxProFrame_ExtendCut", "Extend / Cut"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "MaxProFrame_ExtendCut",
                "<b>Extend / Cut</b><br><br>Select a target face or profile, then the profiles to extend or cut up to it.",
            ),
        }

    def IsActive(self):
        # Any selection opens the panel, which explains what it cannot use.
        return App.ActiveDocument is not None

    def Activated(self):
        show_panel(ExtendCutTaskPanel(_selected_items()))


add_command("MaxProFrame_ExtendCut", ExtendCutCommand())

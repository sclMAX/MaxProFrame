import os
from collections import namedtuple

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import is_extrudedcutout, is_profile, is_trimmedbody
from freecad.maxproframe.create_end_miter_tool import (
    GAP_DELAY_MS,
    _alive,
    _alive_document,
    _base_profile,
    _ctrl_held,
    _failures,
    remove_overlay,
    scene_graph,
)
from freecad.maxproframe.create_profiles_tool import place_in_container_of
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    QT_TRANSLATE_NOOP,
    UIPATH,
    add_command,
    get_param_group,
    translate,
)
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile

# Highlight kinds while the panel is open: the target, and the profiles to cut (or their previews).
TARGET = "target"
PROFILE = "profile"
HIGHLIGHT_COLORS = {TARGET: (1.0, 0.5, 0.0), PROFILE: (0.0, 0.4, 1.0)}
# Highlight lines: width in pixels, and how far, in mm, a curved edge may stray from its line.
HIGHLIGHT_WIDTH = 3
HIGHLIGHT_DEFLECTION = 0.5

# The trim previewing a profile, and (body, visibility) of the bodies it hides, as they were before.
_Preview = namedtuple("_Preview", ("obj", "profile", "visibility"))


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


def trimmed_body_problem(fp, obj):
    """Why ``obj`` cannot be the body trimmed by ``fp`` (None while creating), or None when it can."""
    if not (is_profile(obj) or is_trimmedbody(obj) or is_extrudedcutout(obj)):
        return translate("frameforge", "{} is not a profile").format(obj.Label)
    if fp is not None and fp in _trim_chain(obj):
        return translate("frameforge", "{} cannot trim itself").format(obj.Label)
    return None


def make_target_joint(body, target, joint):
    """A ``joint`` trim of ``body`` against ``target``, placed in the body's own container.

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
    obj.TrimmedProfileType = joint
    return obj


def make_extend_cut_profile(body, target, gap=0.0):
    """Extend Cut of ``body`` up to ``target`` (a face or a whole profile, see make_target_joint)."""
    obj = make_target_joint(body, target, "Extend Cut")
    obj.TrimGap = gap
    return obj


def _related(a, b):
    """Whether ``a`` and ``b`` are the same body or one is built on the other."""
    return a in _trim_chain(b) or b in _trim_chain(a)


def _edge_lines(obj, sub):
    """Points along every edge of ``obj``, or of its face ``sub``, in document coordinates."""
    shape = obj.Shape.getElement(sub) if sub else obj.Shape
    # Shapes are local to their container.
    group = obj.getParentGeoFeatureGroup()
    if group is not None:
        shape = shape.copy()
        shape.transformShape(group.getGlobalPlacement().toMatrix())
    return [edge.discretize(Deflection=HIGHLIGHT_DEFLECTION) for edge in shape.Edges]


def show_panel(panel):
    Gui.Control.showDialog(panel)
    Gui.Selection.addObserver(panel)


class ExtendCutTaskPanel:
    """One target (a planar face or a whole profile) and the profiles extended or cut up to its plane.

    ``selection`` items are (object, sub-element names): the first one is the target, the others
    are profiles. Clicks set the target first, then add whole profiles. With ``edited`` (an
    existing Extend Cut) the panel changes its target and gap. Other joints against one target
    reuse the panel: they set ``joint``, ``has_gap`` and the preview parameter and override the
    texts, the target rule and ``_make``.

    Without ``edited`` the trims are previewed live, like End Miter does: the preview objects are
    the trims OK keeps, all inside one transaction that Cancel aborts. While the panel is open the
    target and the profiles are drawn over the 3D view in their HIGHLIGHT_COLORS.
    """

    joint = "Extend Cut"
    has_gap = True
    # Remembered state of the "Update automatically" check box, and its value until first changed.
    auto_preview_param = "Extend Cut Auto Preview"
    auto_preview_default = True

    def texts(self):
        """The translated texts of the panel, by role."""
        return {
            "title": translate("frameforge", "Extend / Cut"),
            "edit_title": translate("frameforge", "Edit Extend / Cut"),
            "hint": translate("frameforge", "Click the profiles to extend or cut. Ctrl+click drops one."),
            "edit_hint": translate("frameforge", "Click a face to change the target."),
            "no_target": translate("frameforge", "Click a face, or select a profile in the tree."),
            "missing_target": translate("frameforge", "Select the target face or profile."),
            "missing_profiles": translate("frameforge", "Select the profiles to extend or cut."),
        }

    def __init__(self, selection=(), edited=None):
        ui_file = os.path.join(UIPATH, "extend_cut.ui")
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(ui_file))
        # FreeCAD may close the dialog without OK, Cancel or closed(): the form is then deleted.
        self.form.destroyed.connect(self._form_gone)
        self._translate_form()
        self.form.remove_button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, "list-remove.svg")))
        self.form.remove_button.clicked.connect(self.remove_selected)
        if not self.has_gap:
            self.form.gap_label.hide()
            self.form.sb_gap.hide()

        self.edited = edited
        self.target = None
        self.profiles = []
        self._closed = False
        self._syncing = False
        self.doc = App.ActiveDocument
        # Live preview: profile name -> _Preview, and what it shows (see _wanted).
        self._previews = {}
        self._previewed = ()
        self._transaction_open = False
        # Message area: what the last change explained, then the last preview or OK failure.
        self._messages = []
        self._error = ""
        # (scene, node) drawing the highlights.
        self._overlay = None
        # Clicks and Gap edits fire one by one: the preview waits this long for the next one.
        self._preview_timer = QtCore.QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(GAP_DELAY_MS)
        self._preview_timer.timeout.connect(self._update_preview)
        messages = []
        if edited is not None:
            self.doc = edited.Document
            self.form.setWindowTitle(self.texts()["edit_title"])
            self.form.hint_label.setText(self.texts()["edit_hint"])
            self.form.remove_button.hide()
            self.form.groupBox_preview.hide()
            obj, subs = edited.TrimmingBoundary[0]
            self.target = (obj, tuple(sub for sub in subs if sub))
            self.profiles = [edited.TrimmedBody]
            self.form.sb_gap.setValue(edited.TrimGap.Value)
        elif selection:
            messages += self._set_target(*selection[0])
            for obj, _ in selection[1:]:
                messages += self._add_profile(obj)
        self._show(messages)
        if edited is None:
            auto_update = get_param_group().GetBool(self.auto_preview_param, self.auto_preview_default)
            self.form.cb_auto_update.setChecked(auto_update)
            self.form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)
            self.form.sb_gap.valueChanged.connect(self._changed)
            self._update_preview()
        self._draw_highlights()

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, self.texts()["title"]),
            (form.groupBox_target.setTitle, translate("frameforge", "Target")),
            (form.groupBox_profiles.setTitle, translate("frameforge", "Profiles")),
            (form.hint_label.setText, self.texts()["hint"]),
            (form.remove_button.setText, translate("frameforge", "Remove")),
            (form.gap_label.setText, translate("frameforge", "Gap")),
            (form.colors_label.setText, translate("frameforge", "Target in orange, profiles in blue.")),
            (form.groupBox_preview.setTitle, translate("frameforge", "Preview")),
            (form.cb_auto_update.setText, translate("frameforge", "Update automatically")),
        ):
            setter(text)

    def _target_faces(self, obj, subs):
        """(faces of ``obj`` the target keeps, problem): its first face, or none for a whole profile."""
        faces = [sub for sub in subs if sub]
        if faces:
            if not isinstance(obj.getSubObject(faces[0]), Part.Face):
                return (), translate("frameforge", "{}: {} is not a face").format(obj.Label, faces[0])
            return tuple(faces[:1]), None
        return (), trimmed_body_problem(None, obj)

    def _set_target(self, obj, subs):
        """Make ``obj``, with the faces _target_faces keeps, the target; return the problems."""
        faces, problem = self._target_faces(obj, subs)
        if problem is not None:
            return [problem]
        if any(_related(obj, profile) for profile in self.profiles):
            return [translate("frameforge", "{} cannot trim itself").format(obj.Label)]
        self.target = (obj, faces)
        return []

    def set_target(self, obj, subs=()):
        self._show(self._set_target(obj, subs))
        self._changed()

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
        self._changed()

    def _show(self, messages):
        """Show the target, the profiles, ``messages`` and the preview state."""
        self.profiles = [obj for obj in self.profiles if _alive(obj)]
        if self.target is not None and not _alive(self.target[0]):
            self.target = None
        if self.target is None:
            text = self.texts()["no_target"]
        else:
            obj, faces = self.target
            text = " ".join([f"{obj.Label} ({obj.Name})", *faces])
        self.form.target_label.setText(text)
        self.form.profiles_list.clear()
        for obj in self.profiles:
            self.form.profiles_list.addItem(f"{obj.Label} ({obj.Name})")
        self._messages = list(messages)
        self._error = ""
        self._show_messages()
        self._show_status()

    def _show_messages(self):
        self.form.message_label.setText("\n".join(self._messages + ([self._error] if self._error else [])))

    def _show_status(self):
        if self._previewed != self._wanted():
            text = translate("frameforge", "Pending changes")
        elif self._previews:
            text = translate("frameforge", "Preview updated")
        else:
            text = translate("frameforge", "No preview")
        self.form.status_label.setText(text)

    def _wanted(self):
        """What the preview must show for the current target, profiles and Gap; () for nothing."""
        if self.target is None or not self.profiles:
            return ()
        obj, faces = self.target
        gap = round(self.form.sb_gap.value(), 6) if self.has_gap else 0.0
        return (obj.Name, faces), tuple(profile.Name for profile in self.profiles), gap

    def _changed(self, *args):
        """The target, the profiles or the Gap changed: redraw, and preview once changes pause."""
        if not self._active():
            return
        self._show_status()
        if self.edited is None:
            self._preview_timer.start()
        # Never change the 3D view during FreeCAD's selection observer dispatch.
        QtCore.QTimer.singleShot(0, self._draw_highlights)

    def _on_auto_update_toggled(self, checked):
        get_param_group(writable=True).SetBool(self.auto_preview_param, checked)
        self._update_preview()

    def _update_preview(self, *args, force=False):
        """Make the preview match the panel when Update automatically is checked (or ``force``)."""
        if not self._active() or self.edited is not None:
            return
        if (force or self.form.cb_auto_update.isChecked()) and self._previewed != self._wanted():
            self._rebuild_preview()
        self._show_status()

    def _rebuild_preview(self):
        """Update the preview trims; when one fails, discard the whole preview and show why."""
        gap = self.form.sb_gap.value()
        wanted = {obj.Name: obj for obj in self.profiles} if self._wanted() else {}
        if not self._transaction_open:
            # The trims live in the document of the profiles they cut.
            if self.profiles:
                self.doc = self.profiles[0].Document
            self.doc.openTransaction(f"Make {self.joint}")
            self._transaction_open = True
        self._error = ""
        # Removing a selected preview notifies the observer: it is not a user deselection.
        self._syncing = True
        try:
            for name in [name for name in self._previews if name not in wanted]:
                self._drop_preview(name)
            for name, profile in wanted.items():
                preview = self._previews.get(name)
                if preview is None or not _alive(preview.obj):
                    visibility = [(body, body.ViewObject.Visibility) for body in _trim_chain(profile)]
                    self._previews[name] = _Preview(self._make(profile, gap), profile, visibility)
                else:
                    self._retarget(preview.obj, gap)
            # A trim that fails to recompute does not raise: its status tells.
            self.doc.recompute()
            self._error = _failures(preview.obj for preview in self._previews.values())
        except Exception as error:
            self._error = str(error)
        finally:
            self._syncing = False
        if self._error:
            self._discard_preview()
        else:
            self._previewed = self._wanted()
        self._show_messages()
        self._draw_highlights()

    def _retarget(self, obj, gap):
        """Point the trim ``obj`` at the target and ``gap``; unchanged values are left alone, so not recomputed."""
        boundary = [(self.target[0], self.target[1] or ("",))]
        if obj.TrimmingBoundary != boundary:
            obj.TrimmingBoundary = boundary
        if self.has_gap and abs(obj.TrimGap.Value - gap) > 1e-9:
            obj.TrimGap = gap

    def _drop_preview(self, name):
        """Remove the preview of profile ``name`` and show the bodies it hid as they were before."""
        preview = self._previews.pop(name, None)
        if preview is None:
            return
        if _alive(preview.obj):
            preview.obj.Document.removeObject(preview.obj.Name)
        for body, visible in preview.visibility:
            if _alive(body):
                body.ViewObject.Visibility = visible

    def _discard_preview(self):
        """Abort the preview transaction; leftovers (undo disabled) are removed by hand."""
        # Aborting deletes selected previews: those deselections are not the user's.
        self._syncing = True
        try:
            if self._transaction_open and _alive_document(self.doc):
                try:
                    self.doc.abortTransaction()
                except Exception:
                    pass
            self._transaction_open = False
            for name in list(self._previews):
                self._drop_preview(name)
        finally:
            self._syncing = False
        self._previewed = ()

    def _shown(self, profile):
        """What shows ``profile`` in the 3D view: the edited trim, its preview, or itself."""
        if self.edited is not None:
            return self.edited
        preview = self._previews.get(profile.Name)
        return preview.obj if preview is not None and _alive(preview.obj) else profile

    def highlights(self):
        """(object, face or "", TARGET or PROFILE) of everything highlighted while the panel is open."""
        if self._closed:
            return []
        found = []
        if self.target is not None and _alive(self.target[0]):
            obj, faces = self.target
            found.append((obj, faces[0] if faces else "", TARGET))
        for profile in self.profiles:
            shown = self._shown(profile)
            if _alive(shown):
                found.append((shown, "", PROFILE))
        return found

    def _draw_highlights(self):
        """Draw the edges of the target and of the profiles over the 3D view, each kind in its color.

        The overlay never touches the document or the view objects: their colors stay as they are.
        """
        remove_overlay(self._overlay)
        self._overlay = None
        highlights = self.highlights()
        scene = scene_graph(self.doc) if highlights else None
        if scene is None:
            return  # Nothing to show, or no 3D view (offscreen or another view type).
        from pivy import coin

        # An annotation is drawn over the shapes, so the highlights stay visible.
        node = coin.SoAnnotation()
        for kind, color in HIGHLIGHT_COLORS.items():
            lines = [line for obj, sub, marker in highlights if marker == kind for line in _edge_lines(obj, sub)]
            if not lines:
                continue
            points = [(point.x, point.y, point.z) for line in lines for point in line]
            group = coin.SoSeparator()
            base_color = coin.SoBaseColor()
            base_color.rgb.setValue(*color)
            style = coin.SoDrawStyle()
            style.lineWidth.setValue(HIGHLIGHT_WIDTH)
            coordinates = coin.SoCoordinate3()
            coordinates.point.setValues(0, len(points), points)
            line_set = coin.SoLineSet()
            line_set.numVertices.setValues(0, len(lines), [len(line) for line in lines])
            for child in (base_color, style, coordinates, line_set):
                group.addChild(child)
            node.addChild(group)
        scene.addChild(node)
        self._overlay = (scene, node)

    def _active(self):
        if self._closed:
            return False
        if self.form is None:
            self._form_gone()
            return False
        return True

    def _form_gone(self, *args):
        if not self._closed:
            self.closed()

    def _profile_of(self, obj):
        """The profile a preview trim of this session stands for, else ``obj`` itself."""
        for preview in self._previews.values():
            if preview.obj == obj:
                return preview.profile
        return obj

    def _still_selected(self, profile):
        """Whether ``profile`` or its preview keeps any entry in the selection."""
        shown = (profile, self._shown(profile))
        return any(selection.Object in shown for selection in Gui.Selection.getSelectionEx("*"))

    def addSelection(self, doc, obj, sub, other):
        if self._syncing or not self._active():
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source is None:
            return
        # The preview hides its profile: a click on the preview stands for the profile.
        source = self._profile_of(source)
        if self.edited is not None or self.target is None:
            messages = self._set_target(source, (sub,))
        elif _ctrl_held() and source in self.profiles:
            # Ctrl+click toggles: a listed profile leaves the list.
            self.profiles.remove(source)
            messages = []
        else:
            messages = self._add_profile(source)
        self._show(messages)
        self._changed()

    def removeSelection(self, doc, obj, sub):
        # A profile leaves the list once nothing of it or its preview is selected (a Ctrl+click on a selected face).
        if self._syncing or not self._active() or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = self._profile_of(document.getObject(getattr(obj, "Name", obj)) if document else None)
        if source in self.profiles and not self._still_selected(source):
            self.profiles.remove(source)
            self._show([])
            self._changed()

    def clearSelection(self, other):
        pass

    def closed(self):
        # FreeCAD can close the dialog without OK or Cancel (document closed, another dialog shown).
        self.clean()
        if self.edited is None:
            self._discard_preview()

    def clean(self):
        self._closed = True
        self._preview_timer.stop()
        remove_overlay(self._overlay)
        self._overlay = None
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass

    def _close_edit(self):
        gui_doc = Gui.getDocument(self.edited.Document.Name)
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()

    def reject(self):
        self.clean()
        if self.edited is not None:
            # Nothing is changed before OK, so there is nothing to restore.
            self._close_edit()
        else:
            self._discard_preview()
        return True

    def _missing(self):
        if self.target is None:
            return self.texts()["missing_target"]
        if not self.profiles:
            return self.texts()["missing_profiles"]
        return ""

    def _make(self, body, gap):
        """The joint of ``body`` against the target."""
        return make_extend_cut_profile(body, self.target, gap)

    def accept(self):
        error = self._missing()
        if error:
            self._show([error])
            return False
        gap = self.form.sb_gap.value()
        if self.edited is not None:
            return self._accept_edit(gap)

        # OK keeps the current values even when the preview is out of date or a change is pending.
        self._preview_timer.stop()
        self._update_preview(force=True)
        if not self._error:
            # A preview already up to date is not recomputed again: it must still be valid.
            self._error = _failures(preview.obj for preview in self._previews.values())
        if self._error:
            # Nothing invalid is kept: the panel stays open with the error.
            self._discard_preview()
            self._show_messages()
            self._show_status()
            self._draw_highlights()
            return False
        self.doc.commitTransaction()
        self._transaction_open = False
        self._previews.clear()
        self.clean()
        return True

    def _accept_edit(self, gap):
        doc = self.edited.Document
        doc.openTransaction(f"Edit {self.joint}")
        try:
            self._retarget(self.edited, gap)
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
            "Pixmap": os.path.join(ICONPATH, "corner-end-trim.svg"),
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

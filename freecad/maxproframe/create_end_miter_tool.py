import os
from collections import namedtuple

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from freecad.maxproframe._utils import is_extrudedcutout, is_profile, is_trimmedbody
from freecad.maxproframe.create_profiles_tool import place_in_container_of
from freecad.maxproframe.ff_tools import (
    ICONPATH,
    UIPATH,
    add_command,
    get_param_group,
    translate,
)
from freecad.maxproframe.miter_geometry import Member
from freecad.maxproframe.miter_joints import find_joints
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile, add_miter_properties

# Remembered state of the panel's "Update automatically" check box.
AUTO_PREVIEW_PARAM = "Miter Auto Preview"
# Marker kinds: a joint that is mitered, a point where three or more profiles meet and are skipped.
JOINT = "joint"
SKIPPED = "skipped"
MARKER_COLORS = {JOINT: (0.0, 0.6, 1.0), SKIPPED: (1.0, 0.0, 0.0)}
# Typing a Gap fires once per keystroke: the preview waits this long for the next one.
GAP_DELAY_MS = 250

# The End Miter previewing a member, and whether the member was visible before it.
_Preview = namedtuple("_Preview", ("obj", "member", "visible"))


def _base_profile(obj):
    """The attached profile under a chain of trimmed profiles and cutouts, or None."""
    while obj is not None:
        if is_trimmedbody(obj):
            obj = obj.TrimmedBody
        elif is_extrudedcutout(obj):
            obj = obj.baseObject[0] if obj.baseObject else None
        elif is_profile(obj):
            return obj if getattr(obj, "Target", None) else None
        else:
            return None
    return None


def _alive(obj):
    try:
        return obj.Document is not None
    except Exception:
        return False


def _alive_document(doc):
    try:
        return doc is not None and doc.Name in App.listDocuments()
    except Exception:
        return False


def _failures(objects):
    """One line per object that failed to recompute, with FreeCAD's reason; "" when all are valid."""
    return "\n".join(f"{obj.Label}: {obj.getStatusString()}" for obj in objects if not obj.isValid())


def miters_to_edit(edited):
    """``edited`` and the End Miters of its boundaries that miter back against it."""
    partners = [link[0] for link in edited.TrimmingBoundary]
    back = [edited, edited.TrimmedBody]
    found = [edited]
    for obj in edited.Document.Objects:
        if obj is edited or getattr(obj, "TrimmedProfileType", None) != "End Miter":
            continue
        if obj.TrimmedBody in partners and any(link[0] in back for link in obj.TrimmingBoundary):
            found.append(obj)
    return found


def _global_point(obj, point):
    """``point`` of the path of ``obj`` in document coordinates (paths are local to their container)."""
    group = _base_profile(obj).Target[0].getParentGeoFeatureGroup()
    return group.getGlobalPlacement().multVec(point) if group is not None else point


def make_end_miter_profile(trimmed_body=None, trimming_boundary=None, extend=True, gap=0.0):
    """End Miter of ``trimmed_body`` against every boundary, placed in the body's own container."""
    doc = trimmed_body.Document if trimmed_body is not None else App.ActiveDocument

    name = "TrimmedProfile" if trimmed_body is None else f"{trimmed_body.Name}_Mt"
    trimmed_profile = doc.addObject("Part::FeaturePython", name)

    if trimmed_body is not None:
        place_in_container_of(trimmed_profile, trimmed_body)

    TrimmedProfile(trimmed_profile)

    if getattr(trimmed_profile, "ViewObject", None) is not None:
        ViewProviderTrimmedProfile(trimmed_profile.ViewObject)
    trimmed_profile.TrimmedBody = trimmed_body
    trimmed_profile.TrimmingBoundary = trimming_boundary or []
    trimmed_profile.MiterExtend = extend
    trimmed_profile.MiterGap = gap

    trimmed_profile.TrimmedProfileType = "End Miter"
    return trimmed_profile


def _ctrl_held():
    return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)


class EndMiterTaskPanel:
    """Collects whole profiles from canvas clicks and miters every corner they form.

    With ``edited`` (an existing End Miter) the panel only changes Extend and Gap of that
    miter and of the partner miters that cut back against it.

    Without ``edited`` the miters are previewed live, like Create Profile does: the preview
    objects are the End Miters OK keeps, all inside one transaction that Cancel aborts.
    """

    def __init__(self, members=(), edited=None):
        ui_file = os.path.join(UIPATH, "create_end_miter.ui")
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(ui_file))
        self._translate_form()
        self.form.remove_button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, "list-remove.svg")))
        self.form.remove_button.clicked.connect(self.remove_selected)

        self.members = []
        self.edited = edited
        self._closed = False
        self._syncing = False
        self.doc = App.ActiveDocument
        # Live preview: member name -> _Preview.
        self._previews = {}
        self._planned = []
        self._previewed = ()
        self._transaction_open = False
        # Message area: the plan, then the last preview or OK failure.
        self._lines = []
        self._error = ""
        # (document point, JOINT or SKIPPED) of the planned markers, and the node drawing them.
        self._markers = []
        self._marker_node = None
        self._gap_timer = QtCore.QTimer()
        self._gap_timer.setSingleShot(True)
        self._gap_timer.setInterval(GAP_DELAY_MS)
        self._gap_timer.timeout.connect(self._update_preview)
        if edited is not None:
            self.form.setWindowTitle(translate("frameforge", "Edit Miter"))
            self.form.hint_label.setText(translate("frameforge", "Profile and boundaries of this miter."))
            self.form.remove_button.hide()
            self.form.groupBox_preview.hide()
            self.form.cb_extend.setChecked(getattr(edited, "MiterExtend", False))
            self.form.sb_gap.setValue(edited.MiterGap.Value if hasattr(edited, "MiterGap") else 0.0)
            self.members = [edited.TrimmedBody] + [link[0] for link in edited.TrimmingBoundary]
        for obj in members:
            self.add_member(obj)
        if edited is None and self.doc is None and self.members:
            self.doc = self.members[0].Document
        self.refresh()
        if edited is None:
            self.form.cb_auto_update.setChecked(get_param_group().GetBool(AUTO_PREVIEW_PARAM, True))
            self.form.cb_auto_update.toggled.connect(self._on_auto_update_toggled)
            self.form.cb_extend.toggled.connect(self._update_preview)
            self.form.sb_gap.valueChanged.connect(self._on_gap_changed)
            self._update_preview()

    def _translate_form(self):
        """Designer strings are not in the catalog: set their translations here."""
        form = self.form
        for setter, text in (
            (form.setWindowTitle, translate("frameforge", "Miter Ends")),
            (form.groupBox_members.setTitle, translate("frameforge", "Profiles")),
            (form.hint_label.setText, translate("frameforge", "Click the profiles to miter (two or more).")),
            (form.remove_button.setText, translate("frameforge", "Remove")),
            (form.groupBox_options.setTitle, translate("frameforge", "Miter")),
            (form.cb_extend.setText, translate("frameforge", "Extend profiles up to the miter")),
            (form.gap_label.setText, translate("frameforge", "Gap")),
            (form.groupBox_preview.setTitle, translate("frameforge", "Preview")),
            (form.cb_auto_update.setText, translate("frameforge", "Update automatically")),
        ):
            setter(text)

    def add_member(self, obj):
        if obj is None or _base_profile(obj) is None or obj in self.members:
            return False
        self.members.append(obj)
        return True

    def _member_of(self, obj):
        """The member a preview object of this session stands for, else ``obj`` itself."""
        for preview in self._previews.values():
            if preview.obj == obj:
                return preview.member
        return obj

    def remove_selected(self):
        rows = {self.form.members_list.row(item) for item in self.form.members_list.selectedItems()}
        self.members = [obj for row, obj in enumerate(self.members) if row not in rows]
        self.refresh()
        self._update_preview()
        self._highlight_members()

    def analysis(self):
        """(usable members, joints, skipped points, errors); joints and points index ``usable``."""
        usable, measured, errors = [], [], []
        for obj in self.members:
            try:
                profile = _base_profile(obj)
                sketch, subs = profile.Target
                member = Member(sketch.getSubObject(subs[0]), profile.Shape)
            except Exception as error:
                errors.append(f"{obj.Label}: {error}")
                continue
            usable.append(obj)
            measured.append((member.edge, member.section.BoundBox.DiagonalLength))
        joints, skipped = find_joints(measured) if len(measured) > 1 else ([], [])
        return usable, joints, skipped, errors

    def refresh(self):
        self._plan()
        self._draw_markers()

    def _plan(self):
        """List the members, plan their joints and describe them; the 3D view is left alone."""
        self.members = [obj for obj in self.members if _alive(obj)]
        self.form.members_list.clear()
        for obj in self.members:
            self.form.members_list.addItem(f"{obj.Label} ({obj.Name})")
        self._error = ""

        if self.edited is not None:
            names = ", ".join(obj.Label for obj in miters_to_edit(self.edited))
            self._lines = [translate("frameforge", "Extend and Gap apply to {}.").format(names)]
            self._show_messages()
            return

        usable, joints, skipped, errors = self.analysis()
        partners = {}
        for joint in joints:
            partners.setdefault(joint.first, []).append(usable[joint.second])
            partners.setdefault(joint.second, []).append(usable[joint.first])
        # Whole objects: a miter boundary is the partner profile, not one of its faces.
        self._planned = [(usable[index], partners[index]) for index in sorted(partners)]
        self._markers = [(_global_point(usable[joint.first], joint.point), JOINT) for joint in joints] + [
            (_global_point(usable[point.members[0]], point.point), SKIPPED) for point in skipped
        ]

        lines = []
        if len(self.members) < 2:
            lines.append(translate("frameforge", "Select two or more profiles to miter."))
        elif len(joints) == 1:
            lines.append(translate("frameforge", "1 joint will be created."))
        else:
            lines.append(translate("frameforge", "{} joints will be created.").format(len(joints)))
        for point in skipped:
            x, y, z = (round(value, 1) + 0.0 for value in point.point)
            names = ", ".join(usable[index].Label for index in point.members)
            lines.append(
                translate(
                    "frameforge",
                    "Skipped ({:.1f}, {:.1f}, {:.1f}): three or more profiles meet here and are not mitered ({}).",
                ).format(x, y, z, names)
            )
        lines.extend(errors)
        self._lines = lines
        self._show_messages()

    def _show_messages(self):
        self.form.message_label.setText("\n".join(self._lines + ([self._error] if self._error else [])))

    def _wanted(self):
        """What the preview must show for the current members, Extend and Gap; () for nothing."""
        if not self._planned:
            return ()
        joints = tuple((member.Name, tuple(obj.Name for obj in partners)) for member, partners in self._planned)
        return joints, self.form.cb_extend.isChecked(), round(self.form.sb_gap.value(), 6)

    def _on_auto_update_toggled(self, checked):
        get_param_group(writable=True).SetBool(AUTO_PREVIEW_PARAM, checked)
        self._update_preview()
        self._highlight_members()

    def _on_gap_changed(self, value):
        self._show_status()
        self._gap_timer.start()

    def _update_preview(self, *args, force=False):
        """Make the preview match the panel when Update automatically is checked (or ``force``)."""
        if self._closed or self.edited is not None:
            return
        if (force or self.form.cb_auto_update.isChecked()) and self._previewed != self._wanted():
            self._rebuild_preview()
        self._show_status()

    def _rebuild_preview(self):
        """Update the preview miters; when one fails, discard the whole preview and show why."""
        extend = self.form.cb_extend.isChecked()
        gap = self.form.sb_gap.value()
        wanted = {member.Name: (member, partners) for member, partners in self._planned}
        if not self._transaction_open:
            # The miters live in the document of the profiles they cut.
            if self._planned:
                self.doc = self._planned[0][0].Document
            self.doc.openTransaction("Make End Miter Profile")
            self._transaction_open = True
        self._error = ""
        # Removing a selected preview notifies the observer: it is not a user deselection.
        self._syncing = True
        try:
            for name in [name for name in self._previews if name not in wanted]:
                self._drop_preview(name)
            for name, (member, partners) in wanted.items():
                preview = self._previews.get(name)
                if preview is None or not _alive(preview.obj):
                    view = getattr(member, "ViewObject", None)
                    visible = view.Visibility if view is not None else None
                    obj = make_end_miter_profile(member, partners, extend, gap)
                    self._previews[name] = _Preview(obj, member, visible)
                    continue
                preview.obj.TrimmingBoundary = partners
                preview.obj.MiterExtend = extend
                preview.obj.MiterGap = gap
            # A miter that fails to recompute does not raise: its status tells.
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

    def _drop_preview(self, name):
        """Remove the preview of member ``name`` and show the member as it was before."""
        preview = self._previews.pop(name, None)
        if preview is None:
            return
        if _alive(preview.obj):
            preview.obj.Document.removeObject(preview.obj.Name)
        if preview.visible is not None and _alive(preview.member):
            preview.member.ViewObject.Visibility = preview.visible

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

    def _show_status(self):
        if self._previewed != self._wanted():
            text = translate("frameforge", "Pending changes")
        elif self._previews:
            text = translate("frameforge", "Preview updated")
        else:
            text = translate("frameforge", "No preview")
        self.form.status_label.setText(text)

    def markers(self):
        """(document point, JOINT or SKIPPED) of every marker shown."""
        return list(self._markers)

    def _draw_markers(self):
        """Draw the planned markers over the 3D view in place of the previous ones."""
        self._remove_marker_node()
        if self._closed or not self._markers:
            return
        try:
            from pivy import coin

            scene = Gui.getDocument(self.doc.Name).ActiveView.getSceneGraph()
        except Exception:
            return  # No 3D view (offscreen or another view type): the data is still kept.
        try:
            index = Gui.getMarkerIndex("CIRCLE_FILLED", 9)
        except Exception:
            index = coin.SoMarkerSet.CIRCLE_FILLED_9_9
        # An annotation is drawn over the shapes, so markers inside a profile stay visible.
        node = coin.SoAnnotation()
        for kind, color in MARKER_COLORS.items():
            points = [point for point, marker_kind in self._markers if marker_kind == kind]
            if not points:
                continue
            group = coin.SoSeparator()
            base_color = coin.SoBaseColor()
            base_color.rgb.setValue(*color)
            coordinates = coin.SoCoordinate3()
            coordinates.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
            marker_set = coin.SoMarkerSet()
            marker_set.markerIndex.setValue(index)
            for child in (base_color, coordinates, marker_set):
                group.addChild(child)
            node.addChild(group)
        scene.addChild(node)
        self._marker_node = (scene, node)

    def _remove_marker_node(self):
        if self._marker_node is not None:
            scene, node = self._marker_node
            self._marker_node = None
            try:
                scene.removeChild(node)
            except Exception:
                pass

    def _highlight_members(self):
        """Show every listed member, or its preview, selected as a whole object, never as a face."""
        if self._closed:
            return
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            for member in self.members:
                preview = self._previews.get(member.Name)
                obj = preview.obj if preview is not None else member
                parents = obj.Parents
                if parents:
                    top, path = parents[0]
                    Gui.Selection.addSelection(obj.Document.Name, top.Name, path)
                else:
                    Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        finally:
            self._syncing = False

    def _still_selected(self, member):
        """Whether ``member`` or its preview keeps any entry in the selection."""
        preview = self._previews.get(member.Name)
        shown = [member] + ([preview.obj] if preview is not None else [])
        return any(selection.Object in shown for selection in Gui.Selection.getSelectionEx("*"))

    def addSelection(self, doc, obj, sub, other):
        if self._syncing or self._closed or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        # The preview hides its member: a click on the preview stands for the member.
        source = self._member_of(source)
        if source is None or _base_profile(source) is None:
            return
        if _ctrl_held() and source in self.members:
            # Ctrl+click toggles: a listed profile leaves the list.
            self.members.remove(source)
            self._plan()
        elif self.add_member(source):
            self._plan()
        # Never change the selection, the document or the 3D view during FreeCAD's observer dispatch.
        QtCore.QTimer.singleShot(0, self._after_selection)

    def _after_selection(self):
        self._draw_markers()
        self._update_preview()
        self._highlight_members()

    def removeSelection(self, doc, obj, sub):
        # A profile leaves the list once neither it nor its preview has anything selected.
        if self._syncing or self._closed or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = self._member_of(document.getObject(getattr(obj, "Name", obj)) if document else None)
        if source in self.members and not self._still_selected(source):
            self.members.remove(source)
            self._plan()
            QtCore.QTimer.singleShot(0, self._after_selection)

    def clearSelection(self, other):
        pass

    def open(self):
        self._highlight_members()

    def closed(self):
        # FreeCAD can close the dialog without OK or Cancel (document closed, another dialog shown).
        self.clean()
        if self.edited is None:
            self._discard_preview()

    def clean(self):
        self._closed = True
        self._gap_timer.stop()
        self._markers = []
        self._remove_marker_node()
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        try:
            Gui.Selection.removeSelectionGate()
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

    def accept_edit(self):
        extend = self.form.cb_extend.isChecked()
        gap = self.form.sb_gap.value()
        doc = self.edited.Document
        miters = miters_to_edit(self.edited)
        doc.openTransaction("Edit End Miter")
        try:
            # The joint gap is shared: each side of the joint cuts back half of it.
            for obj in miters:
                add_miter_properties(obj, extend=False)
                obj.MiterExtend = extend
                obj.MiterGap = gap
            # A miter that fails to recompute does not raise: its status tells.
            doc.recompute()
            self._error = _failures(miters)
        except Exception as error:
            self._error = str(error)
        if self._error:
            # Keep the panel open with the miters as they were before OK.
            doc.abortTransaction()
            doc.recompute()
            self._show_messages()
            return False
        doc.commitTransaction()
        self.clean()
        self._close_edit()
        return True

    def accept(self):
        if self.edited is not None:
            return self.accept_edit()

        if not self._planned:
            return False
        # OK keeps the current values even when the preview is out of date or a Gap edit is pending.
        self._gap_timer.stop()
        self._update_preview(force=True)
        if not self._error:
            # A preview already up to date is not recomputed again: it must still be valid.
            self._error = _failures(preview.obj for preview in self._previews.values())
        if self._error:
            # Nothing invalid is kept: the panel stays open with the error.
            self._discard_preview()
            self._show_messages()
            self._show_status()
            return False
        self.doc.commitTransaction()
        self._transaction_open = False
        self._previews.clear()
        self.clean()
        return True


class CreateEndMiterCommand:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICONPATH, "corner-end-miter.svg"),
            "MenuText": translate("MetalWB", "Create Miter Ends"),
            "Accel": "M, C",
            "ToolTip": translate(
                "MetalWB",
                "<html><head/><body><p><b>Create Miter Ends</b> \
                    <br><br> \
                    Click two or more profiles to miter the corners they form. \
                    </p></body></html>",
            ),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        panel = EndMiterTaskPanel([selection.Object for selection in Gui.Selection.getSelectionEx()])
        Gui.Control.showDialog(panel)
        Gui.Selection.addObserver(panel)

    def make_end_miter_profile(self, trimmedBody=None, trimmingBoundary=None):
        return make_end_miter_profile(trimmedBody, trimmingBoundary)


add_command("MaxProFrame_EndMiter", CreateEndMiterCommand())

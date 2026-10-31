import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

from freecad.maxproframe._utils import is_extrudedcutout, is_profile, is_trimmedbody
from freecad.maxproframe.create_profiles_tool import _nearest_group
from freecad.maxproframe.ff_tools import ICONPATH, UIPATH, add_command, move_profile_to_parent_if_supported, translate
from freecad.maxproframe.miter_geometry import Member
from freecad.maxproframe.miter_joints import find_joints
from freecad.maxproframe.qt_lifetime import keep_alive_until_destroyed
from freecad.maxproframe.trimmed_profile import TrimmedProfile, ViewProviderTrimmedProfile, add_miter_properties


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


def place_in_container_of(trimmed_profile, body):
    """Put a trim in the closest folder or Part/Body holding ``body``, like Create Profile does."""
    group = _nearest_group(body)
    if group is not None:
        move_profile_to_parent_if_supported(trimmed_profile, group)


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


class EndMiterTaskPanel:
    """Collects whole profiles from canvas clicks and miters every corner they form.

    With ``edited`` (an existing End Miter) the panel only changes Extend and Gap of that
    miter and of the partner miters that cut back against it.
    """

    def __init__(self, members=(), edited=None):
        ui_file = os.path.join(UIPATH, "create_end_miter.ui")
        self.form = keep_alive_until_destroyed(Gui.PySideUic.loadUi(ui_file))
        self.form.setWindowTitle(translate("frameforge", "Miter Ends"))
        self.form.remove_button.setIcon(QtGui.QIcon(os.path.join(ICONPATH, "list-remove.svg")))
        self.form.remove_button.clicked.connect(self.remove_selected)

        self.members = []
        self.edited = edited
        self._closed = False
        self._syncing = False
        if edited is not None:
            self.form.setWindowTitle(translate("frameforge", "Edit Miter"))
            self.form.hint_label.setText(translate("frameforge", "Profile and boundaries of this miter."))
            self.form.remove_button.hide()
            self.form.cb_extend.setChecked(getattr(edited, "MiterExtend", False))
            self.form.sb_gap.setValue(edited.MiterGap.Value if hasattr(edited, "MiterGap") else 0.0)
            self.members = [edited.TrimmedBody] + [link[0] for link in edited.TrimmingBoundary]
        for obj in members:
            self.add_member(obj)
        self.refresh()

    def add_member(self, obj):
        if obj is None or _base_profile(obj) is None or obj in self.members:
            return False
        self.members.append(obj)
        return True

    def remove_selected(self):
        rows = {self.form.members_list.row(item) for item in self.form.members_list.selectedItems()}
        self.members = [obj for row, obj in enumerate(self.members) if row not in rows]
        self.refresh()
        self._highlight_members()

    def analysis(self):
        """(joints, skipped points, errors); joints and points refer to ``usable`` members."""
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
        self.members = [obj for obj in self.members if _alive(obj)]
        self.form.members_list.clear()
        for obj in self.members:
            self.form.members_list.addItem(f"{obj.Label} ({obj.Name})")

        if self.edited is not None:
            names = ", ".join(obj.Label for obj in miters_to_edit(self.edited))
            self.form.message_label.setText(translate("frameforge", "Extend and Gap apply to {}.").format(names))
            return

        usable, joints, skipped, errors = self.analysis()
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
        self.form.message_label.setText("\n".join(lines))

    def _highlight_members(self):
        """Show every listed member selected as a whole object, never as a face."""
        if self._closed:
            return
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            for obj in self.members:
                parents = obj.Parents
                if parents:
                    top, path = parents[0]
                    Gui.Selection.addSelection(obj.Document.Name, top.Name, path)
                else:
                    Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        finally:
            self._syncing = False

    def addSelection(self, doc, obj, sub, other):
        if self._syncing or self._closed or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source is None or _base_profile(source) is None:
            return
        if self.add_member(source):
            self.refresh()
        # Never change the selection during FreeCAD's observer dispatch.
        QtCore.QTimer.singleShot(0, self._highlight_members)

    def removeSelection(self, doc, obj, sub):
        if self._syncing or self._closed or sub or self.edited is not None:
            return
        document = App.getDocument(doc)
        source = document.getObject(getattr(obj, "Name", obj)) if document else None
        if source in self.members:
            self.members.remove(source)
            self.refresh()

    def clearSelection(self, other):
        pass

    def open(self):
        self._highlight_members()

    def clean(self):
        self._closed = True
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
        return True

    def accept_edit(self):
        extend = self.form.cb_extend.isChecked()
        gap = self.form.sb_gap.value()
        doc = self.edited.Document
        doc.openTransaction("Edit End Miter")
        try:
            # The joint gap is shared: each side of the joint cuts back half of it.
            for obj in miters_to_edit(self.edited):
                add_miter_properties(obj, extend=False)
                obj.MiterExtend = extend
                obj.MiterGap = gap
            doc.recompute()
        except Exception:
            doc.abortTransaction()
            raise
        doc.commitTransaction()
        self.clean()
        self._close_edit()
        return True

    def accept(self):
        if self.edited is not None:
            return self.accept_edit()

        usable, joints, _, _ = self.analysis()
        if not joints:
            return False

        partners = {}
        for joint in joints:
            partners.setdefault(joint.first, []).append(usable[joint.second])
            partners.setdefault(joint.second, []).append(usable[joint.first])

        extend = self.form.cb_extend.isChecked()
        gap = self.form.sb_gap.value()
        doc = usable[0].Document
        doc.openTransaction("Make End Miter Profile")
        try:
            for index in sorted(partners):
                # Whole objects: a miter boundary is the partner profile, not one of its faces.
                make_end_miter_profile(usable[index], partners[index], extend, gap)
            doc.recompute()
        except Exception:
            doc.abortTransaction()
            raise
        doc.commitTransaction()
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

"""The library section of a trimmed profile or a cutout is linked from anywhere, as the profile links it.

A library section lives outside the Part of the piece: a local link to it makes FreeCAD report the piece's
links as out of scope on every recompute. Documents saved with the local link open with the global one.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui
from test_cut_ends import SLANTED_TARGET
from test_end_miter_geometry import CENTER
from test_length_restore import LengthRestoreFixture

GLOBAL_LINK = "App::PropertyLinkGlobal"


def out_of_scope(report, obj):
    """Whether ``report`` warns that the links of ``obj`` are out of scope, as each FreeCAD version words it."""
    return f"{obj.Name} links are out of scope" in report or f"out of the allowed scope '{obj.Name}'" in report


def report_view():
    """The Report view of the main window, where FreeCAD prints its warnings."""
    return next(
        view for view in Gui.getMainWindow().findChildren(QtGui.QTextEdit) if view.objectName() == "Report view"
    )


class TestCustomProfileLinkScope(LengthRestoreFixture):
    def pieces_with_section(self, with_section=True):
        """A trimmed piece and a cutout of it, inside a Part, made of a section outside the Part (or of none)."""
        body = self.square_tube()
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        section = self.doc.addObject("Sketcher::SketchObject", "Section") if with_section else None
        # As a custom profile links its library section.
        body.removeProperty("CustomProfile")
        body.addProperty(GLOBAL_LINK, "CustomProfile", "Profile", "Target profile")
        body.CustomProfile = section
        self.doc.recompute()
        trim = self.valid_extend_cut(body, target)
        cutout = self.hole_in_the_middle(trim)
        part = self.doc.addObject("App::Part", "Frame")
        part.addObjects([body, target, trim, cutout])
        if section is not None and section in part.Group:
            # The Part takes what its objects link: a library section stays outside.
            part.removeObject(section)
        self.doc.recompute()
        if section is not None:
            self.assertEqual(section.Parents, [])
        for obj in (body, trim, cutout):
            self.assertEqual(obj.getParentGeoFeatureGroup(), part, obj.Name)
        return section, (trim, cutout)

    def saved_with_local_link(self, obj):
        """``obj`` as a document saved before the global link has it: a local link to the same section."""
        section = obj.CustomProfile
        obj.removeProperty("CustomProfile")
        obj.addProperty("App::PropertyLink", "CustomProfile", "Profile", "Target profile")
        obj.CustomProfile = section
        obj.setEditorMode("CustomProfile", 1)
        obj.purgeTouched()

    def recompute_report(self, objs):
        """What the Report view shows while ``objs`` are recomputed."""
        view = report_view()
        QtGui.QApplication.processEvents()
        before = len(view.toPlainText())
        for obj in objs:
            obj.touch()
        self.doc.recompute()
        QtGui.QApplication.processEvents()
        return view.toPlainText()[before:]

    def assert_opened_global(self, opened, pieces, section):
        for obj in pieces:
            with self.subTest(obj.Name):
                piece = opened.getObject(obj.Name)
                self.assertEqual(piece.getTypeIdOfProperty("CustomProfile"), GLOBAL_LINK)
                self.assertEqual(piece.CustomProfile, section and opened.getObject(section.Name))
                self.assertEqual(piece.getGroupOfProperty("CustomProfile"), "Profile")
                self.assertIn("ReadOnly", piece.getEditorMode("CustomProfile"))
        self.assert_nothing_to_recompute(opened)

    def test_recomputing_the_pieces_reports_no_link_out_of_scope(self):
        _, pieces = self.pieces_with_section()
        report = self.recompute_report(pieces)
        for obj in pieces:
            self.assertFalse(out_of_scope(report, obj), report)
        for obj in pieces:
            self.assertEqual(obj.getStatusString(), "Valid")

    def test_the_report_view_shows_a_link_out_of_scope(self):
        # The check above can fail: a piece with a local link to the section is reported.
        section, (trim, _) = self.pieces_with_section()
        self.saved_with_local_link(trim)
        report = self.recompute_report([trim])
        self.assertTrue(out_of_scope(report, trim), report)

    def test_new_pieces_link_the_section_globally(self):
        section, pieces = self.pieces_with_section()
        for obj in pieces:
            with self.subTest(obj.Name):
                self.assertEqual(obj.getTypeIdOfProperty("CustomProfile"), GLOBAL_LINK)
                self.assertEqual(obj.CustomProfile, section)
                self.assertEqual(obj.getStatusString(), "Valid")

    def test_pieces_saved_with_a_local_link_open_with_a_global_one(self):
        section, pieces = self.pieces_with_section()
        for obj in pieces:
            self.saved_with_local_link(obj)
        self.assert_opened_global(self.reopen(), pieces, section)

    def test_pieces_saved_with_an_empty_local_link_open_with_an_empty_global_one(self):
        _, pieces = self.pieces_with_section(with_section=False)
        for obj in pieces:
            self.saved_with_local_link(obj)
        self.assert_opened_global(self.reopen(), pieces, None)

    def test_pieces_saved_without_the_link_open_with_an_empty_global_one(self):
        _, pieces = self.pieces_with_section(with_section=False)
        for obj in pieces:
            obj.removeProperty("CustomProfile")
            obj.purgeTouched()
        opened = self.reopen()
        self.assert_opened_global(opened, pieces, None)
        for obj in pieces:
            self.assertTrue(opened.getObject(obj.Name).isValid())

    def test_pieces_already_global_open_unchanged(self):
        section, pieces = self.pieces_with_section()
        opened = self.reopen()
        for obj in pieces:
            with self.subTest(obj.Name):
                piece = opened.getObject(obj.Name)
                self.assertEqual(piece.getTypeIdOfProperty("CustomProfile"), GLOBAL_LINK)
                self.assertEqual(piece.CustomProfile, opened.getObject(section.Name))
        self.assert_nothing_to_recompute(opened)


if __name__ == "__main__":
    unittest.main()

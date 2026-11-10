"""The library section of a trimmed profile or a cutout is linked from anywhere, as the profile links it.

A library section lives outside the Part of the piece: a local link to it makes FreeCAD report the piece's
links as out of scope on every recompute. Documents saved with the local link open with the global one.
"""

import unittest

import FreeCAD as App
from test_cut_ends import SLANTED_TARGET
from test_end_miter_geometry import CENTER
from test_length_restore import LengthRestoreFixture

GLOBAL_LINK = "App::PropertyLinkGlobal"


class TestCustomProfileLinkScope(LengthRestoreFixture):
    def pieces_with_section(self):
        """A trimmed piece and a cutout of it, inside a Part, made of a section outside the Part."""
        body = self.square_tube()
        target = self.make_profile(self.make_sketch(SLANTED_TARGET), "Edge1", **CENTER)
        section = self.doc.addObject("Sketcher::SketchObject", "Section")
        body.CustomProfile = section
        self.doc.recompute()
        trim = self.valid_extend_cut(body, target)
        cutout = self.hole_in_the_middle(trim)
        part = self.doc.addObject("App::Part", "Frame")
        part.addObjects([body, target, trim, cutout])
        self.doc.recompute()
        return section, (trim, cutout)

    def saved_with_local_link(self, obj):
        """``obj`` as a document saved before the global link has it: a local link to the same section."""
        section = obj.CustomProfile
        obj.removeProperty("CustomProfile")
        obj.addProperty("App::PropertyLink", "CustomProfile", "Profile", "Target profile")
        obj.CustomProfile = section
        obj.setEditorMode("CustomProfile", 1)
        obj.purgeTouched()

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
        opened = self.reopen()
        for obj in pieces:
            with self.subTest(obj.Name):
                piece = opened.getObject(obj.Name)
                self.assertEqual(piece.getTypeIdOfProperty("CustomProfile"), GLOBAL_LINK)
                self.assertEqual(piece.CustomProfile, opened.getObject(section.Name))
                self.assertEqual(piece.getGroupOfProperty("CustomProfile"), "Profile")
                self.assertIn("ReadOnly", piece.getEditorMode("CustomProfile"))
        self.assert_nothing_to_recompute(opened)

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

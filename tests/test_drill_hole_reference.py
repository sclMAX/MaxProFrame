"""Drill Hole reference: the hole follows its vertex when an end of the piece moves along the profile, and stays
where it was placed, with a warning, when the vertex is gone.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from test_drill_hole_geometry import ONE_HOLE, UP, DrillHoleFixture

CORNER = (-50, -25, 25)
WARNING = "The reference vertex changed: check the hole."


class TestDrillHoleReference(DrillHoleFixture):
    def corner_hole(self, body, along, across=25.0):
        return self.hole(body, self.face_towards(body, UP), self.vertex_at(body, CORNER), along, across)

    def assert_hole_at(self, obj, volume, *center):
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertAlmostEqual(obj.Shape.Volume, volume, places=3)
        self.assertTrue(self.empty(obj.Shape, *center), center)

    def test_the_hole_stays_when_the_named_vertex_is_still_in_place(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        body.OffsetA = 0.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, -20, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_stays_when_the_reference_vertex_is_renumbered(self):
        body = self.tube()
        first = self.corner_hole(body, 130.0)
        obj = self.corner_hole(first, 230.0)
        # Through All drills the bottom wall too: the corner is still there, under another name.
        first.CutType = "Through All"
        self.doc.recompute()
        self.assertNotEqual(self.vertex_at(first, CORNER), obj.ReferenceVertex)
        self.assert_hole_at(obj, first.Shape.Volume - ONE_HOLE, 180, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_follows_its_corner_when_the_end_moves_along_the_profile(self):
        # The user's case: a frame resized from a spreadsheet moves the end of a piece; the hole keeps its offsets
        # from the corner at that end.
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # The start end goes from x = -50 to x = 100 (shorter), -300 (longer) and -1000: the old corner is then
        # nearer the far end than the middle of the face, and still the start end is followed.
        for offset, start in ((-100.0, 100), (300.0, -300), (1000.0, -1000), (50.0, -50)):
            with self.subTest(start=start):
                body.OffsetB = offset
                self.doc.recompute()
                self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, start + 230, 0, 24)
                self.assertEqual(obj.ReferenceWarning, "")
        # Not left at x = 180 by the moves.
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assertFalse(self.empty(obj.Shape, 180, 0, 24))

    def test_a_centered_hole_follows_its_end_when_the_end_moves_along_the_profile(self):
        # "Middle of" an end edge: 22 mm from the end, in the middle of the face width.
        body = self.tube()
        obj = self.corner_hole(body, 22.0, 0.0)
        obj.CenterAcross = True
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, -28, 0, 24)
        body.OffsetB = 250.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, -228, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_a_hole_saved_before_the_reference_side_follows_its_end(self):
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # A drill hole saved by 1.15 has no ReferenceSide: opening reads it from the shape as it was saved.
        obj.removeProperty("ReferenceSide")
        folder = tempfile.mkdtemp(prefix="drill_hole_side_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "v1150.FCStd")
        self.doc.saveCopy(path)
        doc = App.openDocument(path)
        self.addCleanup(App.closeDocument, doc.Name)
        body, obj = doc.getObject(body.Name), doc.getObject(obj.Name)
        body.OffsetB = 1000.0
        doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, -770, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_stays_with_a_warning_when_the_corner_is_gone(self):
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # The tube widens from 50 to 60: the corner moves across, from y = -25 to y = -30; no corner is on its line.
        # The centered anchor moves the snapshot with the section, by 5 across.
        body.ProfileWidth = 60.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 5, 24)
        self.assertEqual(obj.ReferenceWarning, WARNING)

        # Back to the 50 mm tube of the fixture: the corner is there again.
        body.ProfileWidth = 50.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 24)
        self.assertEqual(obj.ReferenceWarning, "")

    def stacked_hole(self):
        """A hole drilled on the top face of another hole: its face is an element of the first hole."""
        body = self.tube()
        first = self.corner_hole(body, 130.0)
        return body, first, self.corner_hole(first, 230.0)

    def test_a_hole_on_a_hole_stays_when_its_face_reference_is_lost(self):
        # Editing the profile can leave the face of the first hole unresolved: FreeCAD names it "?Face3".
        # A bevel keeps the corner the holes are measured from. Shortening the start moves it: both holes follow it
        # (the first one keeps its face named then).
        for name, value, x, lost in (("OffsetB", -100.0, 330, False), ("BevelACutY", 30.0, 180, True)):
            with self.subTest(change=name):
                body, first, obj = self.stacked_hole()
                setattr(body, name, value)
                self.doc.recompute()
                self.assertEqual(obj.baseObject[1][0].startswith("?"), lost, obj.baseObject[1])
                self.assert_hole_at(obj, first.Shape.Volume - ONE_HOLE, x, 0, 24)
                self.assertEqual(obj.ReferenceWarning, "")
                for each in (obj, first, body):
                    self.doc.removeObject(each.Name)

    def test_a_hole_on_a_hole_warns_when_its_face_is_gone(self):
        body, first, obj = self.stacked_hole()
        # The top face rises from z = 25 to z = 30: no face is left on the plane the hole was placed on.
        body.ProfileHeight = 60.0
        self.doc.recompute()
        self.assertTrue(obj.baseObject[1][0].startswith("?"), obj.baseObject[1])
        self.assertNotIn("Invalid shape name", obj.getStatusString())
        self.assertEqual(obj.ReferenceWarning, WARNING)

    def test_the_holes_follow_the_section_when_the_anchor_changes(self):
        # Bottom anchor: the section rises by half its height (25), the top face from z = 25 to z = 50.
        body, first, obj = self.stacked_hole()
        body.AnchorY = "Bottom"
        self.doc.recompute()
        self.assert_hole_at(first, body.Shape.Volume - ONE_HOLE, 80, 0, 49)
        self.assert_hole_at(obj, first.Shape.Volume - ONE_HOLE, 180, 0, 49)
        self.assertEqual([first.ReferenceWarning, obj.ReferenceWarning], ["", ""])

    def test_a_hole_saved_before_the_anchor_snapshot_keeps_its_place(self):
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # A drill hole saved by 1.11 has no ReferenceAnchor: it was placed with the anchor the profile has.
        obj.removeProperty("ReferenceAnchor")
        obj.touch()
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 24)
        body.AnchorY = "Bottom"
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 49)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_a_hole_saved_before_the_anchor_snapshot_follows_an_anchor_changed_after_opening(self):
        # The user's case: open a document saved by 1.11, change the anchor, and only then recompute.
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        obj.removeProperty("ReferenceAnchor")
        folder = tempfile.mkdtemp(prefix="drill_hole_anchor_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "v1110.FCStd")
        self.doc.saveCopy(path)
        doc = App.openDocument(path)
        self.addCleanup(App.closeDocument, doc.Name)
        body, obj = doc.getObject(body.Name), doc.getObject(obj.Name)
        body.AnchorY = "Bottom"
        doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 49)
        self.assertEqual(obj.ReferenceWarning, "")

    def test_picking_another_vertex_places_the_hole_from_it(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        obj.ReferenceVertex = self.vertex_at(body, (350, 25, 25))
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 320, 0, 24)
        self.assertFalse(self.empty(obj.Shape, -20, 0, 24))
        self.assertEqual(obj.ReferenceWarning, "")

    def test_the_hole_moves_with_its_profile(self):
        body = self.tube()
        obj = self.corner_hole(body, 30.0)
        # The path turns a quarter about Z and moves: (x, y, z) goes to (10 - y, 100 + x, z).
        body.AttachmentSupport[0][0].Placement = App.Placement(App.Vector(10, 100, 0), App.Rotation(UP, 90))
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 10, 80, 24)
        self.assertFalse(self.empty(obj.Shape, 10, 80, -24))
        self.assertEqual(obj.ReferenceWarning, "")


if __name__ == "__main__":
    unittest.main()

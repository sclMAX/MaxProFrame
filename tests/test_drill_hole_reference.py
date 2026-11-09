"""Drill Hole reference: the hole stays where it was placed when the vertex it was placed from changes."""

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

    def test_the_hole_stays_with_a_warning_when_the_corner_is_gone(self):
        body = self.tube()
        obj = self.corner_hole(body, 230.0)
        # The start end moves from x = -50 to x = 100: the corner is gone, the hole at x = 180 is still on the tube.
        body.OffsetB = -100.0
        self.doc.recompute()
        self.assert_hole_at(obj, body.Shape.Volume - ONE_HOLE, 180, 0, 24)
        # Not moved to the offsets from the new start corner.
        self.assertFalse(self.empty(obj.Shape, 330, 0, 24))
        self.assertEqual(obj.ReferenceWarning, WARNING)

        # Back to the 50 mm extension of the fixture: the corner is there again.
        body.OffsetB = 50.0
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
        # Shortening the start removes the corner the hole is measured from (warning); a bevel keeps it.
        for name, value, warning in (("OffsetB", -100.0, WARNING), ("BevelACutY", 30.0, "")):
            with self.subTest(change=name):
                body, first, obj = self.stacked_hole()
                setattr(body, name, value)
                self.doc.recompute()
                self.assertTrue(obj.baseObject[1][0].startswith("?"), obj.baseObject[1])
                self.assert_hole_at(obj, first.Shape.Volume - ONE_HOLE, 180, 0, 24)
                self.assertEqual(obj.ReferenceWarning, warning)
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

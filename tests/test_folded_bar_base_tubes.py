"""A Folded Bar keeps its base tubes (odd/tasks/pending-followups.md, T4: S4c).

The layout is the user's (folded-bar-tools L1): a Folded Bar of three tubes (right, top, left), the bottom tube loose.
The bar stores the tube each segment is made from (``BaseTubes``, hidden). A piece made on a tube is folded into the
bar at the next recompute, also one outside the transaction that made the piece; when that piece is removed (undo,
delete without release) the segment falls back to its tube, or to the piece under it, instead of leaving the bar. A
bar saved before ``BaseTubes`` gets them when the document opens and folds the same.

The Folded Bar panel edits the tubes the bar folds, the ones it falls back to too: Std_Undo does not recompute, so a
bar may wait with a removed piece; Cancel leaves its stored links as they were, OK keeps its tubes.
"""

import os
import shutil
import tempfile

import FreeCAD as App
import Part
from test_folded_bar import VOLUME_TOLERANCE
from test_folded_bar_panel import FoldedPanelFixture
from test_folded_bar_tools import ON_FACE, FoldedBarToolsFixture, face_at
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe import folded_bar
from freecad.maxproframe.create_end_miter_tool import make_end_miter_profile
from freecad.maxproframe.create_extruded_cutout_tool import make_cutout_sketch, make_extruded_cutout

RIGHT_WALL = App.Vector(325, 100, 0)


class BaseTubesHelpers:
    def cutout_on(self, piece):
        """A round cutout through the outer wall of the right tube, made on ``piece``."""
        face = face_at(piece, RIGHT_WALL)
        self.assertIsNotNone(face)
        sketch = make_cutout_sketch(piece, face)
        local = sketch.Placement.inverse().multVec(RIGHT_WALL)
        sketch.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), App.Vector(0, 0, 1), 5.0))
        return make_extruded_cutout(sketch, (piece, [face]))

    def assertBarFolds(self, bar, pieces, volume):
        self.assertEqual(pieces, list(bar.Segments))
        self.assertOneSolid(bar)
        self.assertNotIn("Touched", bar.State)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        for piece in pieces:
            self.assertFalse(piece.Visibility, piece.Label)


class BaseTubesFixture(BaseTubesHelpers, FoldedBarToolsFixture):
    def setUp(self):
        super().setUp()
        self.doc.UndoMode = 1

    def miter_right(self, bottom, right):
        """An End Miter of the right tube against the loose bottom one: the free end of the bar reaches past it."""
        return make_end_miter_profile(right, [bottom])


class BaseTubesTest(BaseTubesFixture):
    def test_the_bar_stores_its_base_tubes_hidden_and_keeps_them_when_it_follows_a_piece(self):
        (bottom, right, top, left), bar = self.make_legs()

        self.assertEqual("App::PropertyLinkList", bar.getTypeIdOfProperty("BaseTubes"))
        self.assertIn("Hidden", bar.getEditorMode("BaseTubes"))
        self.assertEqual([right, top, left], list(bar.BaseTubes))
        # L8: tubes are added and removed in the bar panel only, not typed into Segments.
        self.assertIn("ReadOnly", bar.getEditorMode("Segments"))

        miter = self.miter_right(bottom, right)
        self.doc.recompute()

        self.assertEqual([miter, top, left], list(bar.Segments))
        self.assertEqual([right, top, left], list(bar.BaseTubes))
        # No cycle: the tubes and their pieces do not depend on the bar.
        for piece in (right, top, left, miter):
            self.assertNotIn(bar, piece.OutListRecursive, piece.Label)
        self.assertNotIn(bar, bar.OutListRecursive)
        # The tree shows the segments and corners under the bar, not the tubes under the miter twice.
        self.assertEqual([miter, top, left, *bar.Corners], bar.ViewObject.Proxy.claimChildren())

    def test_undo_of_a_piece_the_bar_followed_outside_its_transaction_gives_the_bar_its_tube_back(self):
        (bottom, right, top, left), bar = self.make_legs()
        volume = bar.Shape.Volume
        self.doc.openTransaction("End Miter")
        miter = self.miter_right(bottom, right)
        self.doc.commitTransaction()
        name = miter.Name
        # Outside the transaction: the bar follows the miter.
        self.doc.recompute()
        self.assertEqual([miter, top, left], list(bar.Segments))
        mitered = bar.Shape.Volume

        self.doc.undo()
        self.doc.recompute()

        self.assertIsNone(self.doc.getObject(name))
        self.assertBarFolds(bar, [right, top, left], volume)
        self.assertEqual([right, top, left], list(bar.BaseTubes))
        self.assertAlmostEqual(0.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)

        self.doc.redo()
        self.doc.recompute()

        miter = self.doc.getObject(name)
        self.assertIsNotNone(miter)
        self.assertBarFolds(bar, [miter, top, left], mitered)

    def test_a_piece_removed_without_release_gives_the_bar_its_tube_back(self):
        (bottom, right, top, left), bar = self.make_legs()
        volume = bar.Shape.Volume
        miter = self.miter_right(bottom, right)
        self.doc.recompute()
        self.assertEqual([miter, top, left], list(bar.Segments))

        self.doc.removeObject(miter.Name)
        self.doc.recompute()

        self.assertEqual("Valid", right.getStatusString())
        self.assertBarFolds(bar, [right, top, left], volume)
        self.assertAlmostEqual(0.0, bar.Shape.BoundBox.YMin, delta=ON_FACE)

    def test_a_piece_on_a_piece_removed_falls_back_to_the_piece_under_it(self):
        (bottom, right, top, left), bar = self.make_legs()
        miter = self.miter_right(bottom, right)
        self.doc.recompute()
        mitered = bar.Shape.Volume
        cutout = self.cutout_on(miter)
        self.doc.recompute()
        self.assertEqual("Valid", cutout.getStatusString())
        self.assertEqual([cutout, top, left], list(bar.Segments))
        self.assertLess(bar.Shape.Volume, mitered - 1.0)

        self.doc.removeObject(cutout.Name)
        self.doc.recompute()

        self.assertBarFolds(bar, [miter, top, left], mitered)
        self.assertEqual([right, top, left], list(bar.BaseTubes))

    def test_both_end_miters_removed_give_the_bar_its_three_tubes_back(self):
        (bottom, right, top, left), bar = self.make_legs()
        volume = bar.Shape.Volume
        miters = [make_end_miter_profile(tube, [bottom]) for tube in (right, left)]
        self.doc.recompute()
        self.assertEqual([miters[0], top, miters[1]], list(bar.Segments))

        for miter in miters:
            self.doc.removeObject(miter.Name)
        self.doc.recompute()

        self.assertBarFolds(bar, [right, top, left], volume)
        self.assertEqual([right, top, left], list(bar.BaseTubes))

    def test_a_closed_frame_gets_its_tube_back_with_its_four_corners(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, top, left = profiles
        volume = bar.Shape.Volume
        corners = [corner.Name for corner in bar.Corners]
        self.assertEqual(4, len(corners))
        cutout = self.cutout_on(right)
        self.doc.recompute()
        self.assertEqual("Valid", cutout.getStatusString())
        self.assertEqual([bottom, cutout, top, left], list(bar.Segments))
        self.assertLess(bar.Shape.Volume, volume - 1.0)

        self.doc.removeObject(cutout.Name)
        self.doc.recompute()

        self.assertBarFolds(bar, profiles, volume)
        self.assertEqual(profiles, list(bar.BaseTubes))
        self.assertEqual(corners, [corner.Name for corner in bar.Corners])


class RestoreBaseTubesTest(BaseTubesFixture):
    def reopen(self, *objects):
        """Save the document, close it and open it again: the objects named as ``objects``, as reopened."""
        folder = tempfile.mkdtemp(prefix="mpf_base_tubes_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        names = [obj.Name for obj in objects]
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        return [self.doc.getObject(name) for name in names]

    def test_a_saved_bar_opens_with_its_base_tubes(self):
        (bottom, right, top, left), bar = self.make_legs()
        self.miter_right(bottom, right)
        self.doc.recompute()

        bar, right, top, left = self.reopen(bar, right, top, left)

        self.assertEqual([right, top, left], list(bar.BaseTubes))
        self.assertIn("Hidden", bar.getEditorMode("BaseTubes"))
        self.assertIn("ReadOnly", bar.getEditorMode("Segments"))
        self.assertNotIn("Touched", bar.State)

    def test_a_bar_saved_before_base_tubes_gets_them_on_restore_and_folds_the_same(self):
        (bottom, right, top, left), bar = self.make_legs()
        tubes_volume = bar.Shape.Volume
        miter = self.miter_right(bottom, right)
        self.doc.recompute()
        volume, length = bar.Shape.Volume, bar.DevelopedLength.Value
        # As MaxProFrame saved it before: no BaseTubes, Segments editable.
        bar.removeProperty("BaseTubes")
        bar.setEditorMode("Segments", 0)
        self.assertNotIn("BaseTubes", bar.PropertiesList)
        self.assertNotIn("ReadOnly", bar.getEditorMode("Segments"))

        bar, miter, right, top, left = self.reopen(bar, miter, right, top, left)

        # The tube of each segment: the right tube under its miter.
        self.assertEqual([right, top, left], list(bar.BaseTubes))
        self.assertIn("Hidden", bar.getEditorMode("BaseTubes"))
        self.assertIn("ReadOnly", bar.getEditorMode("Segments"))
        self.assertEqual([miter, top, left], list(bar.Segments))
        # Opening it changes nothing to recompute.
        self.assertNotIn("Touched", bar.State)
        bar.touch()
        self.doc.recompute()
        self.assertBarFolds(bar, [miter, top, left], volume)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, places=9)

        # And it falls back like a new bar.
        self.doc.removeObject(miter.Name)
        self.doc.recompute()
        self.assertBarFolds(bar, [right, top, left], tubes_volume)


class EditWhileFallingBackTest(BaseTubesHelpers, FoldedPanelFixture):
    """The Folded Bar panel on a bar that still waits to fall back to a tube (Std_Undo does not recompute)."""

    def legs(self):
        bottom, right, top, left = self.frame()
        bar = folded_bar.make_folded_bar([right, top, left], bend(**PLAIN))
        self.assertOneSolid(bar)
        return (bottom, right, top, left), bar

    def pending(self):
        """The legs bar after Undo of an End Miter it followed outside its transaction, before any recompute."""
        (bottom, right, top, left), bar = self.legs()
        volume = bar.Shape.Volume
        corners = [corner.Name for corner in bar.Corners]
        self.doc.openTransaction("End Miter")
        make_end_miter_profile(right, [bottom])
        self.doc.commitTransaction()
        self.doc.recompute()
        self.doc.undo()
        self.assertEqual([top, left], list(bar.Segments))
        self.assertEqual([right, top, left], list(bar.BaseTubes))
        return (right, top, left), bar, volume, corners

    def assertFallsBack(self, tubes, bar, volume, corners):
        self.doc.recompute()
        self.assertEqual(list(tubes), list(bar.BaseTubes))
        self.assertBarFolds(bar, list(tubes), volume)
        self.assertEqual(corners, [corner.Name for corner in bar.Corners])

    def test_cancel_keeps_the_base_tubes_and_the_bar_falls_back(self):
        tubes, bar, volume, corners = self.pending()
        panel = self.edit(bar)

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(list(tubes), list(bar.BaseTubes))
        self.assertFallsBack(tubes, bar, volume, corners)

    def test_cancel_with_undo_disabled_keeps_the_base_tubes_and_the_bar_falls_back(self):
        tubes, bar, volume, corners = self.pending()
        self.doc.UndoMode = 0
        panel = self.edit(bar)

        self.assertTrue(panel.reject())
        self.close_dialog()

        self.assertEqual(list(tubes), list(bar.BaseTubes))
        self.assertFallsBack(tubes, bar, volume, corners)

    def test_the_panel_lists_the_tube_the_bar_falls_back_to_and_ok_keeps_it(self):
        tubes, bar, volume, corners = self.pending()
        panel = self.edit(bar)

        self.assertEqual(list(tubes), panel.selection)
        self.assertEqual(
            [
                "1 · Profile001 → Profile002 · R 5 mm · no key · clearance 0 mm",
                "2 · Profile002 → Profile003 · R 5 mm · no key · clearance 0 mm",
            ],
            self.rows(panel),
        )
        self.assertTrue(panel.accept())
        self.close_dialog()

        self.assertFallsBack(tubes, bar, volume, corners)

    def test_undo_of_the_ok_step_while_falling_back_keeps_the_tube(self):
        tubes, bar, volume, corners = self.pending()
        panel = self.edit(bar)
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.assertEqual("Edit Folded Bar", self.doc.UndoNames[0])

        self.doc.undo()

        self.assertFallsBack(tubes, bar, volume, corners)

    def test_a_removed_end_tube_stays_out_after_undo_redo_and_a_piece_removal(self):
        (bottom, right, top, left), bar = self.legs()
        miter = make_end_miter_profile(left, [bottom])
        self.doc.recompute()
        self.assertEqual([right, top, miter], list(bar.Segments))
        panel = self.edit(bar)
        self.pick(panel, 1)
        panel.form.button_remove.click()
        self.events()
        self.assertTrue(panel.accept())
        self.close_dialog()
        self.doc.recompute()
        self.assertEqual([right, top], list(bar.Segments))
        self.assertEqual([right, top], list(bar.BaseTubes))

        self.doc.undo()
        self.doc.recompute()
        self.assertEqual([right, top, miter], list(bar.Segments))
        self.assertEqual([right, top, left], list(bar.BaseTubes))

        self.doc.redo()
        self.doc.removeObject(miter.Name)
        self.doc.recompute()
        self.assertEqual([right, top], list(bar.Segments))
        self.assertEqual([right, top], list(bar.BaseTubes))
        self.assertOneSolid(bar)

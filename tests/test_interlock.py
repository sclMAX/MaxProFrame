"""The Interlock object and its Folded Bar (odd/tasks/joint-tabs.md, T2: S1 S2 S6 S7).

An Interlock is a document object of its own, without shape: it names a corner of a Folded Bar by the two profiles
meeting there (``PieceA``, ``PieceB``, like a Folded Corner), so a trim or drill hole made on one later keeps it, and
holds the ``Kind`` of the interlock with its settings (``Fingers``: count, width, tip, depth, clearance, flip). The
bar lists its Interlocks: each folded corner unfolds and folds with the interlock on it, so changing one recomputes the
bar, deleting it gives the bar back as before. An Interlock on no folded corner of its bar, or a second one on a
corner, leaves the bar in error naming the pieces; so do fingers the geometry refuses. Documents saved before keep
opening and folding the same.
"""

import os
import shutil
import tempfile
from dataclasses import replace
from unittest import mock

import FreeCAD as App
import test_folded_bar
from test_folded_bar import VOLUME_TOLERANCE, FoldedBarFixture
from test_unfolded_geometry import PLAIN, bend

from freecad.maxproframe import interlock as interlock_module
from freecad.maxproframe.folded_bar import make_unfolded_bar
from freecad.maxproframe.folded_chain import build_chain
from freecad.maxproframe.folded_geometry import fold_bar
from freecad.maxproframe.interlock import interlock_key, interlock_settings, is_interlock, make_interlock
from freecad.maxproframe.interlock_geometry import KINDS, TIPS, FingerSettings
from freecad.maxproframe.unfolded_geometry import unfold

# The clearance that makes the fingers show in the folded bar too: without it they fold into the miter's solid.
G = 0.4
INTERLOCK_PROPERTIES = {
    "PieceA": "App::PropertyLink",
    "PieceB": "App::PropertyLink",
    "Kind": "App::PropertyEnumeration",
    "Count": "App::PropertyInteger",
    "FingerWidth": "App::PropertyLength",
    "Tip": "App::PropertyEnumeration",
    "TipSize": "App::PropertyLength",
    "Depth": "App::PropertyLength",
    "Clearance": "App::PropertyLength",
    "Flip": "App::PropertyBool",
}
NOT_ON_A_CORNER = "The interlock between {} and {} is not on a folded corner of {}."
TWO_ON_A_CORNER = "The corner between {} and {} has two interlocks: {} and {}."


class InterlockObjectFixture(FoldedBarFixture):
    def expected(self, profiles, fingers, corner=0):
        """``unfold`` of the rectangle ``profiles`` without key, with ``fingers`` at its corner ``corner``."""
        chain = build_chain(profiles)
        corners = [bend(**PLAIN)] * 3
        corners[corner] = bend(interlock=fingers, **PLAIN)
        return chain, unfold(chain, corners)

    def assertFolds(self, bar, profiles, fingers, corner=0):
        """``bar`` is the rectangle ``profiles`` folded with ``fingers`` at its corner ``corner``."""
        self.assertOneSolid(bar)
        chain, expected = self.expected(profiles, fingers, corner)
        self.assertSameVolume(fold_bar(chain, expected), bar.Shape)
        self.assertAlmostEqual(expected.length, bar.DevelopedLength.Value, places=6)
        return expected

    def reopen(self):
        folder = tempfile.mkdtemp(prefix="mpf_interlock_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)


class InterlockObjectTest(InterlockObjectFixture):
    def test_an_interlock_on_a_folded_corner_changes_the_folded_and_the_unfolded_bar_not_its_length(self):
        # S1, S7: the bar lists it; its corner unfolds and folds with the fingers; DevelopedLength stays.
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        unfolded = make_unfolded_bar(bar)
        folded, flat, length = bar.Shape.copy(), unfolded.Shape.copy(), bar.DevelopedLength.Value

        interlock = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()

        self.assertTrue(is_interlock(interlock))
        self.assertEqual(INTERLOCK_PROPERTIES, {n: interlock.getTypeIdOfProperty(n) for n in INTERLOCK_PROPERTIES})
        self.assertEqual((bottom, right), (interlock.PieceA, interlock.PieceB))
        self.assertEqual(frozenset((bottom.Name, right.Name)), interlock_key(interlock))
        self.assertEqual(FingerSettings(clearance=G), interlock_settings(interlock))
        self.assertEqual([interlock], list(bar.Interlocks))
        expected = self.assertFolds(bar, profiles, FingerSettings(clearance=G))
        self.assertOneSolid(unfolded)
        self.assertSameVolume(expected.shape, unfolded.Shape)
        self.assertGreater(abs(folded.Volume - bar.Shape.Volume), VOLUME_TOLERANCE)
        self.assertGreater(abs(flat.Volume - unfolded.Shape.Volume), VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, places=9)

    def test_changing_a_finger_setting_recomputes_the_bar(self):
        # S2, S4: Kind lists the registered kinds, Tip the tips; each finger property drives the bar.
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        interlock = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()
        self.assertEqual(list(KINDS), interlock.getEnumerationsOfProperty("Kind"))
        self.assertEqual(list(TIPS), interlock.getEnumerationsOfProperty("Tip"))
        fingers = FingerSettings(clearance=G)

        for change, fields in (
            (dict(Count=5), dict(count=5)),
            (dict(Flip=True), dict(flip=True)),
            (dict(Tip="Chamfer", TipSize=1.0), dict(tip="Chamfer", tip_size=1.0)),
        ):
            with self.subTest(change=change):
                before = bar.Shape.copy()
                for name, value in change.items():
                    setattr(interlock, name, value)
                self.doc.recompute()

                fingers = replace(fingers, **fields)
                self.assertEqual(fingers, interlock_settings(interlock))
                self.assertFolds(bar, profiles, fingers)
                self.assertGreater(before.cut(bar.Shape).Volume, VOLUME_TOLERANCE)

    def test_deleting_the_interlock_gives_the_bar_back(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        volume, length = bar.Shape.Volume, bar.DevelopedLength.Value
        interlock = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()
        self.assertGreater(abs(volume - bar.Shape.Volume), VOLUME_TOLERANCE)

        self.doc.removeObject(interlock.Name)
        self.doc.recompute()

        self.assertEqual([], list(bar.Interlocks))
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, places=9)

    def test_the_interlock_keeps_its_corner_after_a_hole_is_drilled_in_one_of_its_tubes(self):
        # Like a Folded Corner, it links the profiles, not the tips; given a tip, it takes its profile.
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, top, left = profiles
        interlock = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()

        hole = test_folded_bar.SegmentsRefreshTest.drill_right(self, right)
        self.doc.recompute()
        bar.touch()
        self.doc.recompute()

        self.assertEqual([bottom, hole, top, left], list(bar.Segments))
        self.assertEqual((bottom, right), (interlock.PieceA, interlock.PieceB))
        self.assertFolds(bar, [bottom, hole, top, left], FingerSettings(clearance=G))
        second = make_interlock(bar, hole, top)
        self.assertEqual((right, top), (second.PieceA, second.PieceB))
        self.doc.recompute()
        self.assertOneSolid(bar)

    def test_an_interlock_on_no_folded_corner_or_a_second_one_on_a_corner_leaves_the_bar_in_error(self):
        # S6: the open corner of the closed frame does not fold; bottom and top do not meet; one interlock per corner.
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, top, left = profiles
        volume = bar.Shape.Volume
        first = make_interlock(bar, right, bottom)
        self.doc.recompute()
        self.assertOneSolid(bar)

        for pieces, message in (
            ((bottom, left), NOT_ON_A_CORNER.format("Profile", "Profile003", bar.Label)),
            ((top, bottom), NOT_ON_A_CORNER.format("Profile002", "Profile", bar.Label)),
            ((bottom, right), None),
        ):
            with self.subTest(pieces=[piece.Label for piece in pieces]):
                wrong = make_interlock(bar, *pieces)
                if message is None:
                    message = TWO_ON_A_CORNER.format("Profile", "Profile001", first.Label, wrong.Label)
                self.doc.recompute()

                self.assertIn("Invalid", bar.State)
                self.assertEqual(message, bar.getStatusString())
                self.doc.removeObject(wrong.Name)
                self.doc.recompute()
                self.assertOneSolid(bar)
        self.doc.removeObject(first.Name)
        self.doc.recompute()
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_fingers_the_geometry_refuses_leave_the_bar_in_error_with_its_message(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        interlock = make_interlock(bar, bottom, right)

        interlock.Count = 1
        self.doc.recompute()

        self.assertIn("Invalid", bar.State)
        self.assertEqual(
            "The interlock of the corner between Profile and Profile001 needs at least 2 fingers.",
            bar.getStatusString(),
        )
        interlock.Count = 2
        self.doc.recompute()
        self.assertFolds(bar, profiles, FingerSettings(count=2))

    def test_the_tree_shows_the_interlocks_under_the_bar_and_edits_them_through_the_hook(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        interlock = make_interlock(bar, bottom, right)
        self.doc.recompute()

        self.assertEqual(profiles + list(bar.Corners) + [interlock], bar.ViewObject.Proxy.claimChildren())
        vobj = interlock.ViewObject
        self.assertEqual("Interlock.svg", os.path.basename(vobj.Proxy.getIcon()))
        self.assertTrue(os.path.isfile(vobj.Proxy.getIcon()))
        # S7: the panel of T3 fills the hook; until then a double click does nothing.
        with mock.patch.object(interlock_module, "EDIT_PANEL", None):
            self.assertFalse(vobj.Proxy.doubleClicked(vobj))
            self.assertFalse(vobj.Proxy.setEdit(vobj, 0))
        hook = mock.Mock()
        with mock.patch.object(interlock_module, "EDIT_PANEL", hook):
            self.assertTrue(vobj.Proxy.setEdit(vobj, 0))
        hook.assert_called_once_with(interlock)


class InterlockRestoreTest(InterlockObjectFixture):
    def test_a_saved_interlock_opens_with_its_settings_and_the_bar_its_shape(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        values = dict(Count=4, FingerWidth=10.0, Tip="Chamfer", TipSize=1.0, Depth=3.0, Clearance=G, Flip=True)
        interlock = make_interlock(bar, right, bottom, **values)
        self.doc.recompute()
        fingers = interlock_settings(interlock)
        self.assertEqual(FingerSettings(4, 10.0, "Chamfer", 1.0, 3.0, G, True), fingers)
        volume, names = bar.Shape.Volume, (bar.Name, interlock.Name)

        self.reopen()

        bar, interlock = (self.doc.getObject(name) for name in names)
        self.assertEqual([interlock], list(bar.Interlocks))
        self.assertEqual(("Profile001", "Profile"), (interlock.PieceA.Name, interlock.PieceB.Name))
        self.assertEqual(fingers, interlock_settings(interlock))
        self.assertEqual("Interlock.svg", os.path.basename(interlock.ViewObject.Proxy.getIcon()))
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        bar.touch()
        self.doc.recompute()
        self.assertFolds(bar, list(bar.Segments), fingers)

    def test_a_bar_saved_before_interlocks_gets_them_and_folds_the_same(self):
        profiles, bar = self.make_bar(**PLAIN)
        volume, length, name = bar.Shape.Volume, bar.DevelopedLength.Value, bar.Name
        bar.removeProperty("Interlocks")
        self.assertNotIn("Interlocks", bar.PropertiesList)

        self.reopen()

        bar = self.doc.getObject(name)
        self.assertEqual("App::PropertyLinkList", bar.getTypeIdOfProperty("Interlocks"))
        self.assertEqual([], list(bar.Interlocks))
        bar.touch()
        self.doc.recompute()
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(length, bar.DevelopedLength.Value, places=9)

    def test_an_interlock_saved_before_a_property_existed_gets_it_with_its_default(self):
        profiles, bar = self.make_bar(**PLAIN)
        bottom, right, _, _ = profiles
        interlock = make_interlock(bar, bottom, right, Clearance=G)
        self.doc.recompute()
        volume, names = bar.Shape.Volume, (bar.Name, interlock.Name)
        interlock.removeProperty("Flip")

        self.reopen()

        bar, interlock = (self.doc.getObject(name) for name in names)
        self.assertEqual(INTERLOCK_PROPERTIES, {n: interlock.getTypeIdOfProperty(n) for n in INTERLOCK_PROPERTIES})
        self.assertFalse(interlock.Flip)
        bar.touch()
        self.doc.recompute()
        self.assertOneSolid(bar)
        self.assertAlmostEqual(volume, bar.Shape.Volume, delta=VOLUME_TOLERANCE)

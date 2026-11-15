"""Tabs Interlock on straight pieces: tabs on the crossbar, slots in the rail (odd/tasks/t-joint-tabs.md, T2: S1 S6).

A Tabs Interlock joins a crossbar (trimmed with Extend / Cut against a face of the rail) to the rail: on top of the
crossbar's newest piece a piece (_Tb) fuses the tabs on the clicked crossbar wall, on top of the rail's newest piece a
piece (_Sl) cuts their slots through the clicked rail face (D1). Both read the Interlock, which remembers the two
faces in the frame of each tube's profile; the crossbar trim keeps targeting the rail piece under the slots. The
crossbar's length runs to the tab tips (S6), the rail is a piece with a cutout. Deleting the Interlock gives the
pieces under back; undo brings everything back.
"""

import math
import os
import shutil
import tempfile

import FreeCAD as App
import Part
from miter_helpers import use_language
from test_end_miter_geometry import CENTER
from test_notch_geometry import TrimFixture

from freecad.maxproframe._utils import piece_stack
from freecad.maxproframe.create_bom import decimal_text, traverse_assembly
from freecad.maxproframe.create_extend_cut_tool import make_extend_cut_profile
from freecad.maxproframe.cut_ends import cut_ends
from freecad.maxproframe.drill_hole import make_drill_hole
from freecad.maxproframe.extruded_cutout import along_extent
from freecad.maxproframe.folded_chain import base_profile
from freecad.maxproframe.interlock import interlock_settings, is_interlock
from freecad.maxproframe.interlock_geometry import TABS, InterlockError, TabSettings
from freecad.maxproframe.piece_table import piece_texts
from freecad.maxproframe.profile import Profile
from freecad.maxproframe.profile_pattern import newest_piece
from freecad.maxproframe.tab_interlock import make_tab_interlock, tab_pieces

# TC80x40x1.5-like tubes: 80 x 40, walls 1.5 thick, outer corner radius 3.
WIDE, HIGH, T, RADIUS = 80.0, 40.0, 1.5, 3.0
X, Y, Z = App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)
# The rail runs along Y at x = 400.
RAIL_EDGE = ((400, -300, 0), (400, 300, 0))
VOLUME_TOLERANCE = 1e-3
OFF_RAIL = "The slots of the T joint between Crossbar and Rail do not fall on the flat part of the face of Rail."
NO_END = "There is no T joint between Crossbar and Rail: Crossbar does not end on the face of Rail."
NO_TAB = "The interlock of the T joint between Crossbar and Rail needs at least 1 tab."
NOT_A_WALL = "There is no T joint between Crossbar and Rail: the face of Crossbar is not a wall along it."
TWICE = "The T joint between Crossbar and Rail already has tabs on that face: {}."
# The Gap of an Extend / Cut the crossbar ends on (S8): the 0.5 mm of the manual test (L12), and one wider than the
# rail wall is thick.
GAP, WIDE_GAP = 0.5, 2.0


class TabInterlockFixture(TrimFixture):
    def setUp(self):
        super().setUp()
        # Refusals are checked in English: an earlier test may leave FreeCAD in another language.
        use_language(self, "English", "en_US")

    def tube(self, edge, label):
        """A TC80x40x1.5-like tube along ``edge``, centered on it, its body running exactly along it."""
        sketch = self.make_sketch(edge)
        obj = self.doc.addObject("Part::FeaturePython", "Profile")
        obj.addExtension("Part::AttachExtensionPython")
        obj.MapMode = "NormalToEdge"
        obj.AttachmentSupport = (sketch, "Edge1")
        obj.MapPathParameter = 1
        Profile(
            obj,
            init_w=WIDE,
            init_h=HIGH,
            init_mt=T,
            init_ft=0.0,
            init_r1=RADIUS,
            init_r2=RADIUS - T,
            init_len=0.0,
            init_wg=1.0,
            init_unit_price=1.0,
            init_mf=True,
            material="Steel",
            fam="Rectangular Hollow",
            size_name="TC80x40x1.5",
            bevels_combined=False,
            catalog_family="Rectangular Hollow",
            link_sub=(sketch, ("Edge1",)),
            init_offset_a=0.0,
            init_offset_b=0.0,
            **{f"init_{key}": value for key, value in CENTER.items()},
        )
        obj.Label = label
        self.doc.recompute()
        self.assertEqual(obj.getStatusString(), "Valid")
        return obj

    def rail(self, edge=RAIL_EDGE, label="Rail"):
        return self.tube(edge, label)

    def crossbar(self, rail, edge=((0, 0, 0), (300, 0, 0)), towards=-X, label="Crossbar"):
        """(crossbar profile, its Extend / Cut against the face of ``rail`` looking along ``towards``)."""
        profile = self.tube(edge, label)
        trim = make_extend_cut_profile(profile, (rail, (self.face_towards(rail, towards),)))
        self.doc.recompute()
        self.assertEqual(trim.getStatusString(), "Valid")
        return profile, trim

    def wall(self, obj, normal):
        """Name of the planar face of ``obj`` looking along ``normal``, farthest out."""
        return self.face_towards(obj, normal)

    def square_t(self, **settings):
        """(rail, crossbar profile, trim, interlock) of a square T with tabs on the +Y wall of the crossbar."""
        rail = self.rail()
        profile, trim = self.crossbar(rail)
        interlock = make_tab_interlock(trim, self.wall(trim, Y), rail, self.face_towards(rail, -X), **settings)
        self.doc.recompute()
        return rail, profile, trim, interlock

    def assertOneSolid(self, obj):
        self.assertEqual(obj.getStatusString(), "Valid")
        self.assertEqual(1, len(obj.Shape.Solids))
        self.assertTrue(obj.Shape.isValid())

    @staticmethod
    def flat(trim, name):
        """The width of the flat part of the side wall ``name`` of ``trim``, across its axis (along Z)."""
        return trim.Shape.getElement(name).BoundBox.ZLength

    def assertTabs(self, trim, tabs, count, width, length, rail=None, slots=None, clearance=0.0, before=0.0):
        """``tabs`` adds ``count`` tabs ``width`` wide, ``length`` long and T thick to ``trim`` (and ``before``);
        ``slots`` removes their footprints, grown by ``clearance``, from ``rail``."""
        added = tabs.Shape.Volume - trim.Shape.Volume
        self.assertAlmostEqual(before + count * width * T * length, added, delta=VOLUME_TOLERANCE)
        if slots is not None:
            removed = rail.Shape.Volume - slots.Shape.Volume
            self.assertAlmostEqual(count * (width + clearance) * (T + clearance) * T, removed, delta=VOLUME_TOLERANCE)

    @staticmethod
    def vertex_of(obj, face):
        """Name of the first vertex of the face ``face`` of ``obj``."""
        corner = obj.Shape.getElement(face).Vertexes[0]
        index = next(i for i, vertex in enumerate(obj.Shape.Vertexes, 1) if vertex.isSame(corner))
        return f"Vertex{index}"

    def reopen(self):
        folder = tempfile.mkdtemp(prefix="mpf_tab_interlock_")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, f"{self.doc.Name}.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)


class TabInterlockTest(TabInterlockFixture):
    def test_a_square_t_gets_tabs_on_the_crossbar_and_slots_in_the_rail(self):
        rail, profile, trim, interlock = self.square_t()

        self.assertTrue(is_interlock(interlock))
        self.assertEqual(TABS, interlock.Kind)
        self.assertEqual((profile, rail), (interlock.PieceA, interlock.PieceB))
        self.assertEqual(TabSettings(), interlock_settings(interlock))
        tabs, slots = tab_pieces(interlock)
        self.assertEqual(("Crossbar_Tr_Tb", "Rail_Sl"), (tabs.Label, slots.Label))
        for obj in (tabs, slots):
            self.assertOneSolid(obj)
        span = self.flat(trim, self.wall(trim, Y))
        self.assertAlmostEqual(HIGH - 2 * RADIUS, span, places=6)
        self.assertTabs(trim, tabs, 2, span / 5, T, rail, slots)
        # The tabs fill the slots: where the rail was, not where the slotted rail is.
        self.assertAlmostEqual(2 * span / 5 * T * T, tabs.Shape.common(rail.Shape).Volume, delta=VOLUME_TOLERANCE)
        self.assertLess(tabs.Shape.common(slots.Shape).Volume, VOLUME_TOLERANCE)
        near = rail.Shape.getElement(self.face_towards(rail, -X)).CenterOfMass.x
        self.assertAlmostEqual(near + T, tabs.Shape.BoundBox.XMax, places=6)
        self.assertAlmostEqual(trim.Shape.BoundBox.YMax, tabs.Shape.BoundBox.YMax, places=6)
        # Only the 3D view shows the newest pieces.
        self.assertFalse(trim.ViewObject.Visibility)
        self.assertFalse(rail.ViewObject.Visibility)

    def test_an_oblique_t_gets_tabs_through_longer_slots(self):
        rail = self.rail()
        near = rail.Shape.getElement(self.face_towards(rail, -X)).CenterOfMass.x
        angle = math.radians(60)
        direction = App.Vector(math.sin(angle), math.cos(angle), 0)
        end = App.Vector(near - 30, 0, 0)
        start = end - direction * 300
        profile, trim = self.crossbar(rail, ((start.x, start.y, 0), (end.x, end.y, 0)))
        wall = App.Vector(-direction.y, direction.x, 0)

        interlock = make_tab_interlock(trim, self.wall(trim, wall), rail, self.face_towards(rail, -X))
        self.doc.recompute()

        tabs, slots = tab_pieces(interlock)
        for obj in (tabs, slots):
            self.assertOneSolid(obj)
        inside = tabs.Shape.common(rail.Shape).Volume
        self.assertGreater(inside, VOLUME_TOLERANCE)
        self.assertLess(tabs.Shape.common(slots.Shape).Volume, VOLUME_TOLERANCE)
        # S5: an oblique slot is longer than the tab through it is thick.
        self.assertGreater(rail.Shape.Volume - slots.Shape.Volume, inside + VOLUME_TOLERANCE)
        # S6: the crossbar is as long as it reaches along its axis, tab tips included (its start is square).
        low, high = along_extent(tabs.Shape, direction)
        self.assertGreater(high, along_extent(trim.Shape, direction)[1] + VOLUME_TOLERANCE)
        self.assertAlmostEqual(high - low, tabs.Length.Value, places=6)

    def test_changing_a_setting_recomputes_both_pieces(self):
        rail, _, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)
        span = self.flat(trim, self.wall(trim, Y))

        interlock.Count = 3
        self.doc.recompute()
        self.assertTabs(trim, tabs, 3, span / 7, T, rail, slots)

        interlock.Count, interlock.FingerWidth, interlock.Clearance = 2, 8.0, 0.2
        self.doc.recompute()
        self.assertTabs(trim, tabs, 2, 8.0, T, rail, slots, clearance=0.2)

        interlock.Clearance, interlock.Length = 0.0, 3.0
        self.doc.recompute()
        self.assertTabs(trim, tabs, 2, 8.0, 3.0)
        self.assertAlmostEqual(trim.Length.Value + 3.0, tabs.Length.Value, places=6)

    def test_the_crossbar_is_as_long_as_its_tab_tips_and_the_rail_has_a_cutout(self):
        rail, _, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)

        self.assertAlmostEqual(trim.Length.Value + T, tabs.Length.Value, places=6)
        self.assertAlmostEqual(rail.Length.Value, slots.Length.Value, places=6)
        self.assertTrue(slots.Cutout)
        rows, links = [], []
        for obj in (trim, tabs, slots):
            traverse_assembly(rows, links, obj)
        trim_row, tabs_row, slots_row = rows
        self.assertEqual(f"{trim.Length.Value + T:.1f}", tabs_row["length"])
        self.assertEqual("", tabs_row["cutout"])
        # The tab end is not one flat cut: the crossbar keeps the angles of its trim.
        self.assertEqual(
            (trim_row["cut_angle_1"], trim_row["cut_angle_2"], trim_row["ends"]),
            (tabs_row["cut_angle_1"], tabs_row["cut_angle_2"], tabs_row["ends"]),
        )
        self.assertEqual(cut_ends(trim), cut_ends(tabs))
        self.assertEqual((trim.CuttingAngleA, trim.CuttingAngleB), (tabs.CuttingAngleA, tabs.CuttingAngleB))
        self.assertEqual("Yes", slots_row["cutout"])
        self.assertEqual(f"{rail.Length.Value:.1f}", slots_row["length"])
        self.assertEqual(decimal_text(tabs.Length.Value), piece_texts(tabs)[1])

    def test_a_hole_drilled_on_the_tabbed_crossbar_keeps_its_length_to_the_tab_tips(self):
        _, _, trim, interlock = self.square_t()
        tabs, _ = tab_pieces(interlock)
        top = self.face_towards(tabs, Z)
        hole = make_drill_hole((tabs, (top,)), self.vertex_of(tabs, top))
        hole.OffsetAlong, hole.OffsetAcross = 20.0, 20.0
        self.doc.recompute()

        self.assertEqual("Valid", hole.getStatusString())
        self.assertAlmostEqual(trim.Length.Value + T, hole.Length.Value, places=6)

    def test_both_pieces_are_pieces_of_their_stacks(self):
        rail, profile, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)

        self.assertEqual([tabs, trim, profile], list(piece_stack(tabs)))
        self.assertEqual([slots, rail], list(piece_stack(slots)))
        self.assertEqual((profile, rail), (base_profile(tabs), base_profile(slots)))
        self.assertEqual((tabs, slots), (newest_piece(profile), newest_piece(rail)))
        self.assertEqual((tabs, slots), (newest_piece(trim), newest_piece(rail)))
        # No cycle: the trim still ends on the rail under the slots.
        self.assertEqual(rail, trim.TrimmingBoundary[0][0])
        self.assertNotIn(slots, tabs.OutListRecursive)
        self.assertNotIn(tabs, slots.OutListRecursive)
        # The tree: the Interlock under the crossbar's tabs.
        self.assertEqual([trim, interlock], tabs.ViewObject.Proxy.claimChildren())
        self.assertEqual([rail], slots.ViewObject.Proxy.claimChildren())
        for obj in (tabs, slots):
            self.assertTrue(os.path.isfile(obj.ViewObject.Proxy.getIcon()))
        # A Folded Bar never lists it.
        self.assertFalse(any(interlock in getattr(obj, "Interlocks", ()) for obj in self.doc.Objects))

    def test_a_refused_setting_leaves_both_pieces_in_error_with_their_base_shapes(self):
        rail, _, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)

        interlock.Count = 0
        self.doc.recompute()

        for obj, base in ((tabs, trim), (slots, rail)):
            self.assertIn("Invalid", obj.State)
            self.assertEqual(NO_TAB, obj.getStatusString())
            self.assertAlmostEqual(base.Shape.Volume, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
        interlock.Count = 2
        self.doc.recompute()
        for obj in (tabs, slots):
            self.assertOneSolid(obj)

    def test_faces_that_make_no_t_joint_are_refused_before_anything_is_made(self):
        rail = self.rail()
        _, trim = self.crossbar(rail)
        names = sorted(obj.Name for obj in self.doc.Objects)
        rail_face = self.face_towards(rail, -X)
        end_face = self.face_towards(trim, X)

        for crossbar_face, face, message in (
            (self.wall(trim, Z), rail_face, OFF_RAIL),
            (self.wall(trim, Y), self.face_towards(rail, X), NO_END),
            (end_face, rail_face, NOT_A_WALL),
        ):
            with self.subTest(message=message):
                with self.assertRaises(InterlockError) as raised:
                    make_tab_interlock(trim, crossbar_face, rail, face)
                self.assertEqual(message, str(raised.exception))
                self.assertEqual(names, sorted(obj.Name for obj in self.doc.Objects))
        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(trim, self.wall(trim, Y), rail, rail_face, Count=0)
        self.assertEqual(NO_TAB, str(raised.exception))

    def test_deleting_the_interlock_gives_the_pieces_under_back_and_undo_brings_them_back(self):
        self.doc.UndoMode = 1
        rail, profile, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)
        top = self.face_towards(slots, Z)
        hole = make_drill_hole((slots, (top,)), self.vertex_of(slots, top))
        hole.OffsetAlong, hole.OffsetAcross = 20.0, 20.0
        self.doc.recompute()
        self.assertEqual("Valid", hole.getStatusString())
        names = (interlock.Name, tabs.Name, slots.Name)
        volumes = (tabs.Shape.Volume, slots.Shape.Volume, hole.Shape.Volume)

        self.doc.openTransaction("Delete")
        self.doc.removeObject(interlock.Name)
        self.doc.commitTransaction()
        self.doc.recompute()

        def gone():
            self.assertEqual([None] * 3, [self.doc.getObject(name) for name in names])
            self.assertEqual(trim, newest_piece(profile))
            self.assertTrue(trim.ViewObject.Visibility)
            # The hole drilled on the slots now drills the rail.
            self.assertEqual(rail, hole.baseObject[0])
            self.assertEqual("Valid", hole.getStatusString())
            # The same hole, in the rail without slots.
            self.assertAlmostEqual(
                volumes[2] + rail.Shape.Volume - volumes[1], hole.Shape.Volume, delta=VOLUME_TOLERANCE
            )

        gone()
        self.doc.undo()
        self.doc.recompute()
        interlock, tabs, slots = (self.doc.getObject(name) for name in names)
        self.assertEqual((tabs, slots), tab_pieces(interlock))
        self.assertEqual(slots, hole.baseObject[0])
        self.assertEqual(tabs, newest_piece(profile))
        for expected, obj in zip(volumes, (tabs, slots, hole)):
            self.assertEqual("Valid", obj.getStatusString())
            self.assertAlmostEqual(expected, obj.Shape.Volume, delta=VOLUME_TOLERANCE)
        self.doc.redo()
        self.doc.recompute()
        gone()

    def test_a_saved_interlock_opens_and_finds_its_faces_again(self):
        rail, _, trim, interlock = self.square_t(Count=3, Clearance=0.2)
        tabs, slots = tab_pieces(interlock)
        names = (interlock.Name, tabs.Name, slots.Name)
        volumes = (tabs.Shape.Volume, slots.Shape.Volume)
        # Saved before Length existed: it gets it, Automatic.
        interlock.removeProperty("Length")

        self.reopen()

        interlock, tabs, slots = (self.doc.getObject(name) for name in names)
        self.assertEqual(0.0, interlock.Length.Value)
        self.assertEqual(TabSettings(count=3, clearance=0.2), interlock_settings(interlock))
        # A face name that no longer names the face picked: the face on its plane is found again.
        crossbar, _ = interlock.CrossbarFace
        rail, _ = interlock.RailFace
        interlock.CrossbarFace = (crossbar, ("Face1",))
        interlock.RailFace = (rail, ("?Face2",))
        for obj in (tabs, slots):
            obj.touch()
        self.doc.recompute()
        for expected, obj in zip(volumes, (tabs, slots)):
            self.assertOneSolid(obj)
            self.assertAlmostEqual(expected, obj.Shape.Volume, delta=VOLUME_TOLERANCE)

    def test_two_interlocks_on_both_walls_of_a_crossbar_end(self):
        rail, profile, trim, first = self.square_t()
        tabs, slots = tab_pieces(first)
        span = self.flat(trim, self.wall(trim, Y))

        second = make_tab_interlock(tabs, self.wall(tabs, -Y), slots, self.face_towards(slots, -X))
        self.doc.recompute()

        more_tabs, more_slots = tab_pieces(second)
        self.assertEqual([more_tabs, tabs, trim, profile], list(piece_stack(more_tabs)))
        self.assertEqual([more_slots, slots, rail], list(piece_stack(more_slots)))
        self.assertEqual((more_tabs, more_slots), (newest_piece(profile), newest_piece(rail)))
        for obj in (more_tabs, more_slots):
            self.assertOneSolid(obj)
        self.assertTabs(trim, more_tabs, 4, span / 5, T)
        self.assertAlmostEqual(
            4 * span / 5 * T * T, rail.Shape.Volume - more_slots.Shape.Volume, delta=VOLUME_TOLERANCE
        )
        self.assertAlmostEqual(trim.Length.Value + T, more_tabs.Length.Value, places=6)
        # S2: one Interlock per pair of faces.
        with self.assertRaises(InterlockError) as raised:
            make_tab_interlock(more_tabs, self.wall(more_tabs, Y), more_slots, self.face_towards(more_slots, -X))
        self.assertEqual(TWICE.format(first.Label), str(raised.exception))

    def test_deleting_the_first_of_two_interlocks_relinks_the_second_to_the_pieces_under(self):
        rail, profile, trim, first = self.square_t()
        tabs, slots = tab_pieces(first)
        second = make_tab_interlock(tabs, self.wall(tabs, -Y), slots, self.face_towards(slots, -X))
        self.doc.recompute()
        more_tabs, more_slots = tab_pieces(second)
        span = self.flat(trim, self.wall(trim, Y))

        self.doc.removeObject(first.Name)
        self.doc.recompute()

        self.assertEqual((trim, rail), (more_tabs.baseObject[0], more_slots.baseObject[0]))
        self.assertEqual((trim, rail), (second.CrossbarFace[0], second.RailFace[0]))
        self.assertEqual((more_tabs, more_slots), (newest_piece(profile), newest_piece(rail)))
        for obj in (more_tabs, more_slots):
            self.assertOneSolid(obj)
        self.assertTabs(trim, more_tabs, 2, span / 5, T, rail, more_slots)
        # The tabs left are on the -Y wall.
        self.assertAlmostEqual(trim.Shape.BoundBox.YMin, more_tabs.Shape.common(rail.Shape).BoundBox.YMin, places=6)

    def test_interlocks_at_both_ends_of_a_crossbar(self):
        near_rail = self.rail(((0, -300, 0), (0, 300, 0)), "Left")
        far_rail = self.rail()
        profile, first_trim = self.crossbar(near_rail, ((60, 0, 0), (340, 0, 0)), X)
        trim = make_extend_cut_profile(first_trim, (far_rail, (self.face_towards(far_rail, -X),)))
        self.doc.recompute()
        self.assertEqual("Valid", trim.getStatusString())

        far = make_tab_interlock(trim, self.wall(trim, Y), far_rail, self.face_towards(far_rail, -X))
        self.doc.recompute()
        far_tabs, _ = tab_pieces(far)
        near = make_tab_interlock(far_tabs, self.wall(far_tabs, Y), near_rail, self.face_towards(near_rail, X))
        self.doc.recompute()

        near_tabs, near_slots = tab_pieces(near)
        for obj in (far_tabs, near_tabs, near_slots):
            self.assertOneSolid(obj)
        span = self.flat(trim, self.wall(trim, Y))
        self.assertTabs(trim, near_tabs, 4, span / 5, T)
        self.assertAlmostEqual(trim.Length.Value + 2 * T, near_tabs.Length.Value, places=6)
        box = near_tabs.Shape.BoundBox
        self.assertAlmostEqual(trim.Shape.BoundBox.XMin - T, box.XMin, places=6)
        self.assertAlmostEqual(trim.Shape.BoundBox.XMax + T, box.XMax, places=6)


class TabsAcrossTheGapTest(TabInterlockFixture):
    """S8 (T6): a crossbar trimmed with a Gap g ends g before the rail face P; its tabs cross the gap, measured from P
    (S4), through the same slots, and the crossbar is as long as its tab tips (S6)."""

    def near(self, rail):
        return rail.Shape.getElement(self.face_towards(rail, -X)).CenterOfMass.x

    def removed(self, rail, slots):
        """What the slots take out of ``rail``."""
        return rail.Shape.cut(slots.Shape)

    def assertSameShape(self, expected, shape):
        self.assertAlmostEqual(expected.Volume, shape.Volume, delta=VOLUME_TOLERANCE)
        self.assertLess(expected.cut(shape).Volume + shape.cut(expected).Volume, VOLUME_TOLERANCE)

    def assertAcross(self, rail, trim, interlock, length, gap=GAP):
        """The tabs of ``interlock`` reach ``length`` past P across the ``gap`` the crossbar ``trim`` ends before P,
        through slots as deep as the rail wall; the crossbar is as long as the tab tips."""
        tabs, slots = tab_pieces(interlock)
        for obj in (tabs, slots):
            self.assertOneSolid(obj)
        near = self.near(rail)
        span = self.flat(trim, self.wall(trim, Y))
        self.assertAlmostEqual(near - gap, trim.Shape.BoundBox.XMax, places=6)
        self.assertTabs(trim, tabs, 2, span / 5, length + gap)
        self.assertAlmostEqual(near + length, tabs.Shape.BoundBox.XMax, places=6)
        added = tabs.Shape.cut(trim.Shape).BoundBox
        self.assertAlmostEqual(near - gap, added.XMin, places=6)
        # The tabs fill the gap and the slots.
        if gap > 0:
            gap_box = Part.makeBox(gap, 2 * WIDE, 2 * WIDE, App.Vector(near - gap, -WIDE, -WIDE))
            self.assertAlmostEqual(2 * span / 5 * T * gap, tabs.Shape.common(gap_box).Volume, delta=VOLUME_TOLERANCE)
        removed = self.removed(rail, slots)
        self.assertAlmostEqual(2 * span / 5 * T * T, removed.Volume, delta=VOLUME_TOLERANCE)
        self.assertAlmostEqual(removed.Volume, tabs.Shape.common(rail.Shape).Volume, delta=VOLUME_TOLERANCE)
        self.assertLess(tabs.Shape.common(slots.Shape).Volume, VOLUME_TOLERANCE)
        # S6: the cut length runs to the tab tips, g more past the crossbar end than without a gap.
        self.assertAlmostEqual(trim.Length.Value + length + gap, tabs.Length.Value, places=6)
        rows, links = [], []
        traverse_assembly(rows, links, tabs)
        self.assertEqual(f"{trim.Length.Value + length + gap:.1f}", rows[0]["length"])
        self.assertEqual(decimal_text(tabs.Length.Value), piece_texts(tabs)[1])
        return tabs, slots

    def gapped_t(self, gap):
        """(rail, trim, interlock) of a square T whose crossbar was trimmed with ``gap`` before the tabs were made."""
        rail = self.rail()
        _, trim = self.crossbar(rail)
        trim.TrimGap = gap
        self.doc.recompute()
        self.assertEqual("Valid", trim.getStatusString())
        interlock = make_tab_interlock(trim, self.wall(trim, Y), rail, self.face_towards(rail, -X))
        self.doc.recompute()
        return rail, trim, interlock

    def test_tabs_on_a_crossbar_trimmed_with_a_gap_cross_it_through_the_slots(self):
        rail, trim, interlock = self.gapped_t(GAP)

        self.assertAcross(rail, trim, interlock, T)
        # A Length set by the user is measured from P too (D3).
        interlock.Length = 3.0
        self.doc.recompute()
        self.assertAcross(rail, trim, interlock, 3.0)

    def test_tabs_cross_a_gap_wider_than_the_rail_wall(self):
        rail, trim, interlock = self.gapped_t(WIDE_GAP)

        self.assertAcross(rail, trim, interlock, T, WIDE_GAP)

    def test_editing_the_gap_after_the_interlock_exists_recomputes_the_tabs_and_keeps_the_slots(self):
        rail, _, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)
        slotted, length = self.removed(rail, slots), tabs.Length.Value

        for gap in (GAP, WIDE_GAP):
            with self.subTest(gap=gap):
                trim.TrimGap = gap
                self.doc.recompute()

                self.assertAcross(rail, trim, interlock, T, gap)
                self.assertSameShape(slotted, self.removed(rail, slots))
                # The tips stay where they were: the crossbar is as long to cut as before.
                self.assertAlmostEqual(length, tabs.Length.Value, places=6)

    def test_without_a_gap_the_tabs_start_at_the_crossbar_end_as_before(self):
        rail, _, trim, interlock = self.square_t()
        tabs, slots = tab_pieces(interlock)
        shapes = (tabs.Shape.copy(), slots.Shape.copy())

        self.assertAcross(rail, trim, interlock, T, gap=0.0)

        trim.TrimGap = WIDE_GAP
        self.doc.recompute()
        trim.TrimGap = 0.0
        self.doc.recompute()
        for shape, obj in zip(shapes, (tabs, slots)):
            self.assertOneSolid(obj)
            self.assertSameShape(shape, obj.Shape)
        self.assertAcross(rail, trim, interlock, T, gap=0.0)

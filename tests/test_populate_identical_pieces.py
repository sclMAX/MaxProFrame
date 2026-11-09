"""Populate IDs: identical pieces are the same finished solid, and the count covers the whole document."""

import unittest

import FreeCAD as App
from test_drill_hole_geometry import PATH, UP, DrillHoleFixture

from freecad.maxproframe._utils import get_profiles_and_links_from_document
from freecad.maxproframe.create_bom import traverse_assembly
from freecad.maxproframe.populate_ids import populate_ids

# Corner of the top face the holes are placed from, on the tube along PATH.
CORNER = (-50, -25, 25)
# Another place and direction for the same tube: turned 30 degrees about Z and moved.
MOVED = App.Placement(App.Vector(500, 200, 0), App.Rotation(UP, 30))


class PopulateFixture(DrillHoleFixture):
    def populate(
        self, profiles=(), links=(), grouped=True, counted=True, scheme="fill_selection", start="1", **prefixes
    ):
        doc_profiles, doc_links = get_profiles_and_links_from_document()
        populate_ids(
            list(profiles), list(links), doc_profiles, doc_links, "all_numbers", False, grouped, counted,
            False, scheme, start_number=start, **prefixes,
        )  # fmt: skip

    def drilled(self, along, placement=App.Placement()):
        """A tube along PATH moved by ``placement``, drilled ``along`` from the corner of its top face."""
        moved = [tuple(placement.multVec(App.Vector(*point))) for point in (*PATH, CORNER)]
        body = self.make_profile(self.make_sketch(moved[:2]), "Edge1")
        corner = self.vertex_at(body, moved[2])
        return self.hole(body, self.face_towards(body, UP), corner, along, 25.0)

    def beveled(self, start, end):
        """A tube along PATH cut at ``start`` degrees at its start and ``end`` degrees at its end."""
        body = self.make_profile(self.make_sketch(PATH), "Edge1")
        body.BevelACutY, body.BevelBCutY = start, end
        self.doc.recompute()
        return body

    def bom_id(self, obj):
        profiles, links = [], []
        traverse_assembly(profiles, links, obj)
        return profiles[0]["ID"]


class TestIdenticalPieces(PopulateFixture):
    def test_the_same_bar_with_a_hole_elsewhere_is_another_piece(self):
        pieces = [self.drilled(30.0), self.drilled(30.0), self.drilled(100.0)]
        self.populate(pieces)
        self.assertEqual([p.PID for p in pieces], ["1 x2", "1 x2", "2 x1"])

    def test_a_bar_turned_end_for_end_is_the_same_piece(self):
        bar, turned, other = self.beveled(30.0, 15.0), self.beveled(15.0, 30.0), self.beveled(15.0, -30.0)
        self.assertEqual((bar.CuttingAngleA, bar.CuttingAngleB), ("30.0", "15.0"))
        self.assertEqual((turned.CuttingAngleA, turned.CuttingAngleB), ("15.0", "30.0"))
        self.populate([bar, turned, other])
        # The same angles leaning the other way are another piece.
        self.assertEqual([bar.PID, turned.PID, other.PID], ["1 x2", "1 x2", "2 x1"])

    def test_identical_bars_anywhere_in_the_assembly_are_the_same_piece(self):
        here, there = self.drilled(30.0), self.drilled(30.0, MOVED)
        self.assertGreater(here.Shape.BoundBox.Center.distanceToPoint(there.Shape.BoundBox.Center), 100)
        self.populate([here, there])
        self.assertEqual([here.PID, there.PID], ["1 x2", "1 x2"])

    def test_another_material_or_size_is_another_piece(self):
        pieces = [self.drilled(30.0) for _ in range(3)]
        base = [p.baseObject[0] for p in pieces]
        base[1].Material = "Aluminium"
        base[2].SizeName = "50x50x2 bis"
        self.doc.recompute()
        self.assertAlmostEqual(pieces[1].Shape.Volume, pieces[0].Shape.Volume, places=6)
        self.assertAlmostEqual(pieces[2].Shape.Volume, pieces[0].Shape.Volume, places=6)
        self.populate(pieces)
        self.assertEqual([p.PID for p in pieces], ["1 x1", "2 x1", "3 x1"])


class TestCountInTheDocument(PopulateFixture):
    def numbered_outside(self):
        outside = self.drilled(30.0)
        self.populate([outside])
        self.assertEqual(outside.PID, "1 x1")
        return outside

    def test_identical_pieces_outside_the_selection_are_counted_and_get_the_count(self):
        outside, selected = self.numbered_outside(), self.drilled(30.0)
        self.populate([selected])
        for obj in (outside, outside.baseObject[0], selected, selected.baseObject[0]):
            self.assertEqual(obj.PID, "1 x2", obj.Name)
        self.assertEqual(self.bom_id(outside), "1 x2")
        self.doc.recompute()
        self.assertEqual([outside.PID, selected.PID], ["1 x2", "1 x2"])

    def test_a_piece_numbered_again_leaves_the_right_count_on_the_others(self):
        first, second = self.drilled(30.0), self.drilled(30.0)
        self.populate([first, second])
        self.assertEqual([first.PID, second.PID], ["1 x2", "1 x2"])
        self.populate([first], scheme="start_at", start="5")
        self.assertEqual([first.PID, second.PID], ["5 x1", "1 x1"])

    def assert_outside_unchanged(self, grouped, counted):
        outside, selected = self.numbered_outside(), self.drilled(30.0)
        self.populate([selected], grouped=grouped, counted=counted)
        self.assertEqual([selected.PID, outside.PID, outside.baseObject[0].PID], ["1", "1 x1", "1 x1"])

    def test_without_grouping_the_pieces_outside_are_unchanged(self):
        self.assert_outside_unchanged(grouped=False, counted=True)

    def test_without_count_the_pieces_outside_are_unchanged(self):
        self.assert_outside_unchanged(grouped=True, counted=False)

    def test_prefixed_pieces_outside_the_selection_are_counted_and_get_the_count(self):
        outside, selected = self.drilled(30.0), self.drilled(30.0)
        self.populate([outside], profiles_prefix="P-")
        self.assertEqual(outside.PID, "P-1 x1")
        self.populate([selected], profiles_prefix="P-")
        for obj in (outside, outside.baseObject[0], selected, selected.baseObject[0]):
            self.assertEqual(obj.PID, "P-1 x2", obj.Name)
        self.assertEqual(self.bom_id(selected), "P-1 x2")

    def test_links_outside_the_selection_are_counted_and_get_the_count(self):
        box = self.doc.addObject("Part::Box", "Box")
        links = []
        for _ in range(2):
            link = self.doc.addObject("App::Link", "Link")
            link.LinkedObject = box
            link.addProperty("App::PropertyString", "PID", "MaxProFrame", "Profile ID")
            links.append(link)
        self.doc.recompute()
        self.populate(links=links[:1])
        self.assertEqual(links[0].PID, "1 x1")
        self.populate(links=links[1:])
        self.assertEqual([link.PID for link in links], ["1 x2", "1 x2"])


if __name__ == "__main__":
    unittest.main()

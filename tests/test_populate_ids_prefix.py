"""Populate IDs: the prefixes of profiles and links, respected when gaps and the next ID are looked for."""

import unittest
from types import SimpleNamespace

from freecad.maxproframe.populate_ids import populate_ids


def piece(pid=""):
    return SimpleNamespace(PID=pid, TypeId="Part::FeaturePython")


def identical(pid=""):
    return SimpleNamespace(
        PID=pid, TypeId="Part::FeaturePython", CustomProfile=None, Family="Square Hollow",
        Length=SimpleNamespace(Value=100.0), Material="Metal", SizeName="20x20",
        CuttingAngleA="0", CuttingAngleB="0", Cutout=False,
    )  # fmt: skip


def populate(
    profiles=(), links=(), doc_profiles=(), doc_links=(), numbering_type="all_numbers", scheme="start_at",
    grouped=False, keep=False, **prefixes,
):  # fmt: skip
    populate_ids(
        list(profiles), list(links), [*doc_profiles, *profiles], [*doc_links, *links], numbering_type,
        False, grouped, grouped, keep, scheme, **prefixes,
    )  # fmt: skip


class TestPrefix(unittest.TestCase):
    def test_ids_start_with_the_prefix(self):
        profiles, link = [piece(), piece()], piece()
        populate(profiles, [link], numbering_type="number_for_profiles_letters_for_links",
                 profiles_prefix="P-", links_prefix="L-")  # fmt: skip
        self.assertEqual([p.PID for p in profiles], ["P-1", "P-2"])
        self.assertEqual(link.PID, "L-A")

    def test_gaps_and_the_next_id_are_looked_for_among_the_ids_with_the_prefix(self):
        for numbering_type, existing, fill, follow in (
            ("all_numbers", ("P-1", "P-3", "7"), "P-2", "P-4"),
            ("all_letters", ("P-A", "P-C", "D"), "P-B", "P-D"),
        ):
            for scheme, expected in (("fill_document", fill), ("continue_document", follow)):
                with self.subTest(numbering_type=numbering_type, scheme=scheme):
                    document, selected = [piece(pid) for pid in existing], piece()
                    populate([selected], doc_profiles=document, numbering_type=numbering_type, scheme=scheme,
                             profiles_prefix="P-")  # fmt: skip
                    self.assertEqual(selected.PID, expected)
                    self.assertEqual([p.PID for p in document], list(existing))

    def test_kept_ids_with_the_prefix_are_reserved(self):
        selected = [piece("P-1"), piece(), piece("P-3"), piece()]
        populate(selected, scheme="fill_selection", keep=True, profiles_prefix="P-")
        self.assertEqual([p.PID for p in selected], ["P-1", "P-2", "P-3", "P-4"])

    def test_without_prefix_prefixed_ids_are_ignored(self):
        selected = piece()
        populate([selected], doc_profiles=[piece("P-3"), piece("1")], scheme="continue_document")
        self.assertEqual(selected.PID, "2")

    def test_one_numbering_for_both_kinds_keeps_each_prefix_apart(self):
        for numbering_type, existing, expected in (
            ("all_numbers", ("P-1", "L-4"), ("P-2", "L-5")),
            ("all_letters", ("P-A", "L-D"), ("P-B", "L-E")),
        ):
            with self.subTest(numbering_type=numbering_type):
                profile, link = piece(), piece()
                populate([profile], [link], [piece(existing[0])], [piece(existing[1])], numbering_type,
                         "continue_document", profiles_prefix="P-", links_prefix="L-")  # fmt: skip
                self.assertEqual((profile.PID, link.PID), expected)

    def test_one_numbering_for_both_kinds_with_the_same_prefix_is_one_sequence(self):
        profile, link = piece(), piece()
        populate([profile], [link], [piece("X-1")], [piece("X-2")], "all_numbers", "continue_document",
                 profiles_prefix="X-", links_prefix="X-")  # fmt: skip
        self.assertEqual((profile.PID, link.PID), ("X-3", "X-4"))

    def test_the_count_follows_the_prefixed_id(self):
        outside, twins = identical("P-1 x2"), [identical(), identical()]
        populate(twins, doc_profiles=[outside], scheme="continue_document", grouped=True, profiles_prefix="P-")
        self.assertEqual([p.PID for p in twins], ["P-2 x2", "P-2 x2"])
        self.assertEqual(outside.PID, "P-1 x2")


if __name__ == "__main__":
    unittest.main()

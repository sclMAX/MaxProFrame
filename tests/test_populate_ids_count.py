import unittest
from types import SimpleNamespace

from freecad.maxproframe.populate_ids import IdGenerator, populate_ids


class TestPopulateIDsCount(unittest.TestCase):
    def test_counted_ids_reserve_numbers_and_letters_through_populate(self):
        for numbering_type, prefix, expected in (
            ("all_numbers", ("1", "3"), "4"),
            ("all_letters", ("A", "C"), "D"),
        ):
            for scheme, next_pid in (
                ("continue_document", expected),
                ("fill_document", "2" if numbering_type == "all_numbers" else "B"),
                ("start_at", "2" if numbering_type == "all_numbers" else "B"),
            ):
                with self.subTest(numbering_type=numbering_type, scheme=scheme):
                    existing_profile = SimpleNamespace(PID=f"{prefix[0]} x2")
                    existing_link = SimpleNamespace(PID=f"{prefix[1]} x4")
                    selected = SimpleNamespace(
                        PID="", TypeId="Part::FeaturePython", CustomProfile=None, Family="Square Hollow",
                        Length=SimpleNamespace(Value=100.0), Material="Metal",
                        SizeName="20x20", CuttingAngleA="0", CuttingAngleB="0", Cutout=False,
                    )
                    populate_ids(
                        [selected], [], [existing_profile, selected], [existing_link],
                        numbering_type, False, True, True, False, scheme,
                    )
                    self.assertEqual(selected.PID, f"{next_pid} x1")
                    self.assertEqual(existing_profile.PID, f"{prefix[0]} x2")
                    self.assertEqual(existing_link.PID, f"{prefix[1]} x4")

    def test_plain_ids_and_invalid_ids_keep_previous_behavior(self):
        for mode, used, expected_continue, expected_gap in (
            ("number", {"1", "3", "invalid"}, "4", "2"),
            ("letter", {"A", "C", "1"}, "D", "B"),
        ):
            for strategy, expected in (
                ("continue", expected_continue), ("fill_gaps", expected_gap),
                ("start_at", expected_gap),
            ):
                with self.subTest(mode=mode, strategy=strategy):
                    original = used.copy()
                    generator = IdGenerator(used, mode, strategy, "1" if mode == "number" else "A")
                    self.assertEqual(generator.next(), expected)
                    self.assertNotEqual(generator.next(), expected)
                    self.assertEqual(used, original)

    def test_count_suffix_is_only_accepted_for_existing_ids(self):
        for mode, counted in (("number", "1 x2"), ("letter", "A x2")):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    IdGenerator(set(), mode, "start_at", counted)
                generator = IdGenerator({counted + " extra"}, mode, "continue")
                self.assertEqual(generator.next(), "1" if mode == "number" else "A")


if __name__ == "__main__":
    unittest.main()

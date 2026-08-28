import unittest

from apply_drive_org import (
    canonical_letter_path,
    keeper_for_duplicate_roots,
    parse_quarter_name,
    unique_child_name,
)


class ApplyDriveOrgHelpersTest(unittest.TestCase):
    def test_parse_quarter_alias_and_canonical(self) -> None:
        self.assertEqual(parse_quarter_name("2026 2Q"), ("2026", "2"))
        self.assertEqual(parse_quarter_name("2026 Q2"), ("2026", "2"))
        self.assertEqual(parse_quarter_name("2011 3Q Letters"), ("2011", "3"))
        self.assertIsNone(parse_quarter_name("Files"))
        self.assertEqual(canonical_letter_path("2026", "2"), "Letters/2026 Q2")

    def test_letters_keeper_prefers_canonical_id(self) -> None:
        keep = keeper_for_duplicate_roots(
            "Letters",
            [
                {"id": "aaa", "_child_count": 99},
                {"id": "1z8P-tKj3lvWmx72bXUxJQ9BcUmKrhTg4", "_child_count": 1},
            ],
        )
        self.assertEqual(keep["id"], "1z8P-tKj3lvWmx72bXUxJQ9BcUmKrhTg4")

    def test_quarter_keeper_prefers_known_q2(self) -> None:
        from apply_drive_org import PREFERRED_LETTER_QUARTERS

        q2 = PREFERRED_LETTER_QUARTERS[("2026", "2")]
        keep = keeper_for_duplicate_roots(
            "2026 Q2",
            [
                {"id": "other", "_child_count": 99},
                {"id": q2, "_child_count": 1},
            ],
        )
        self.assertEqual(keep["id"], q2)

    def test_other_keeper_prefers_more_children(self) -> None:
        keep = keeper_for_duplicate_roots(
            "Research Sources",
            [
                {"id": "small", "_child_count": 1},
                {"id": "big", "_child_count": 6},
            ],
        )
        self.assertEqual(keep["id"], "big")

    def test_unique_child_name_suffix(self) -> None:
        dest = [{"name": "Letter.pdf"}]
        self.assertEqual(unique_child_name(dest, "Other.pdf", "abcdef"), "Other.pdf")
        self.assertEqual(unique_child_name(dest, "Letter.pdf", "abcdef123"), "Letter (abcdef).pdf")


if __name__ == "__main__":
    unittest.main()

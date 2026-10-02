"""SH-005: a private-word check over the whole tree, from a committed hash list.

The plain-text list stays on the maintainer's machine; CI has only hashes.
These tests plant a word in a scratch tree and check it is found wherever it is.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import selftest  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def a_tree(files: dict, words=("acmecorp", "blue-lagoon", "red fox")) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "scripts").mkdir()
    (root / selftest.HASHED_WORDS).write_text(
        "# comment\n" + "\n".join(selftest.word_hash(w) for w in words) + "\n")
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


class TheHashedCheck(unittest.TestCase):

    def test_a_word_anywhere_in_the_tree_is_found(self):
        for name in ("core/tests/test_x.py", "docs/images/a.svg", "README.md"):
            with self.subTest(file=name):
                result = selftest.check_no_private_words_in_tree(
                    a_tree({name: "line one\nwe built this for AcmeCorp.\n"}))
                self.assertFalse(result.passed)
                self.assertIn(f"{name}:2", result.problems[0])

    def test_hyphenated_and_spaced_entries_match_as_written(self):
        for text in ("see blue-lagoon here", "a Red  Fox jumped", "x red-fox"):
            with self.subTest(text=text):
                result = selftest.check_no_private_words_in_tree(a_tree({"a.md": text}))
                self.assertFalse(result.passed)

    def test_it_matches_whole_words_only(self):
        result = selftest.check_no_private_words_in_tree(
            a_tree({"a.md": "acmecorporation and blue lagoonish\n"}))
        self.assertTrue(result.passed, result.problems)

    def test_the_hash_file_names_nobody(self):
        root = a_tree({})
        self.assertNotIn("acmecorp", (root / selftest.HASHED_WORDS).read_text())

    def test_no_hash_file_is_a_skip_not_a_pass(self):
        root = Path(tempfile.mkdtemp())
        result = selftest.check_no_private_words_in_tree(root)
        self.assertTrue(result.skipped)

    def test_the_real_repository_ships_a_hash_list_and_is_clean(self):
        self.assertTrue((REPO / selftest.HASHED_WORDS).is_file())
        result = selftest.check_no_private_words_in_tree(REPO)
        self.assertTrue(result.passed, result.problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests for the readiness rule.

The one that matters is `test_no_safety_means_no_build`. Everything else in the
policy design assumes it holds.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.readiness import Brain, Kind, Part, State  # noqa: E402


def brain(**states) -> Brain:
    """A brain with every part ok, then the named ones overridden."""
    b = Brain()
    for part in Part:
        b.add(part, states.get(part.name.lower(), State.OK), "probed")
    return b


class TheRule(unittest.TestCase):
    def test_everything_alive_is_ready_for_everything(self):
        b = brain()
        self.assertEqual(b.ready_kinds(), list(Kind))

    def test_no_safety_means_no_build(self):
        """The load-bearing rule of the whole policy design."""
        b = brain(safety=State.MISSING)
        self.assertTrue(b.ready_for(Kind.QUESTION))
        self.assertTrue(b.ready_for(Kind.REVIEW))
        self.assertFalse(b.ready_for(Kind.BUILD))
        self.assertFalse(b.ready_for(Kind.LEARN))

    def test_a_blocked_kind_names_the_part_to_fix(self):
        b = brain(safety=State.MISSING)
        names = [o.part for o in b.blockers(Kind.BUILD)]
        self.assertEqual(names, [Part.SAFETY])

    def test_degraded_still_counts_as_usable(self):
        """Weaker than it looks is not the same as absent."""
        b = brain(safety=State.DEGRADED)
        self.assertTrue(b.ready_for(Kind.BUILD))

    def test_down_does_not_count_as_usable(self):
        b = brain(knowledge=State.DOWN)
        self.assertEqual(b.ready_kinds(), [])

    def test_a_dead_extractor_blocks_learning_and_nothing_else(self):
        """The failure that hid for two days, expressed as a rule.

        Remembering is only needed to write back, so a dead extractor must not
        stop anyone answering a question — and must absolutely stop a learn.
        """
        b = brain(remembering=State.DOWN)
        self.assertTrue(b.ready_for(Kind.QUESTION))
        self.assertTrue(b.ready_for(Kind.REVIEW))
        self.assertTrue(b.ready_for(Kind.BUILD))
        self.assertFalse(b.ready_for(Kind.LEARN))

    def test_an_unprobed_part_is_missing_not_assumed_ok(self):
        b = Brain()
        b.add(Part.KNOWLEDGE, State.OK, "answered")
        self.assertEqual(b.state_of(Part.SAFETY), State.MISSING)
        self.assertFalse(b.ready_for(Kind.BUILD))


class TheTable(unittest.TestCase):
    def test_it_leads_with_what_you_can_do(self):
        out = brain(safety=State.MISSING).table()
        self.assertIn("ready for: question, review", out)
        self.assertIn("NOT: build, learn", out)

    def test_it_names_the_blocker_rather_than_saying_not_ready(self):
        out = brain(safety=State.MISSING).table()
        self.assertIn("build is blocked by: safety", out)

    def test_an_unenforced_session_says_so(self):
        self.assertIn("ADVISORY", brain().table(enforced=False))
        self.assertNotIn("ADVISORY", brain().table(enforced=True))

    def test_the_detail_is_shown_because_a_green_needs_evidence(self):
        b = Brain()
        b.add(Part.KNOWLEDGE, State.OK, "5 hits, 380 ms")
        self.assertIn("5 hits, 380 ms", b.table())


if __name__ == "__main__":
    unittest.main(verbosity=2)

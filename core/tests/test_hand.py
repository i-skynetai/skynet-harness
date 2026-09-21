"""Tests for running a hand.

The silence test is the important one. A hand that is stuck produces nothing,
so any check that only runs after a line arrives never fires — which is how one
run continued for three hours under a thirty-minute limit.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import hand  # noqa: E402


def tmp_log() -> Path:
    return Path(tempfile.mkdtemp()) / "run.log"


class NormalRuns(unittest.TestCase):
    def test_a_command_that_succeeds_is_reported_as_finished(self):
        result = hand.run(["sh", "-c", "echo hello; exit 0"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log())
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "finished")
        self.assertEqual(result.exit_code, 0)

    def test_output_is_written_as_it_arrives(self):
        log = tmp_log()
        hand.run(["sh", "-c", "echo first; echo second"],
                 env=dict(os.environ), cwd=Path.cwd(), log_path=log)
        self.assertIn("first", log.read_text())
        self.assertIn("second", log.read_text())

    def test_a_nonzero_exit_is_a_failure_not_a_crash(self):
        result = hand.run(["sh", "-c", "echo nope >&2; exit 3"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log())
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "failed")
        self.assertEqual(result.exit_code, 3)

    def test_a_missing_binary_is_reported_not_raised(self):
        result = hand.run(["definitely-not-a-real-binary-xyz"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log())
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "not-installed")


class TheWatchdogs(unittest.TestCase):
    def test_a_silent_hand_is_stopped_even_though_it_is_still_running(self):
        """The failure that actually happens.

        This process never exits and never prints. Nothing in the read loop
        will ever run again, so only a clock watched elsewhere can end it.
        """
        started = time.monotonic()
        result = hand.run(["sh", "-c", "sleep 60"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log(),
                          hard_cap=30, silence_cap=2)
        elapsed = time.monotonic() - started
        self.assertEqual(result.reason, "silent")
        self.assertFalse(result.ok)
        self.assertLess(elapsed, 15, "the silence cap did not fire")

    def test_a_chatty_hand_is_stopped_by_the_hard_cap(self):
        """Output alone must not buy unlimited time.

        This one keeps talking, so the silence cap never fires — the hard cap
        is the only thing that can end it.
        """
        started = time.monotonic()
        result = hand.run(["sh", "-c", "while true; do echo working; sleep 0.2; done"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log(),
                          hard_cap=2, silence_cap=30)
        elapsed = time.monotonic() - started
        self.assertEqual(result.reason, "hard-cap")
        self.assertLess(elapsed, 15, "the hard cap did not fire")

    def test_children_are_killed_with_the_parent(self):
        """A hand spawns a test runner; killing only the parent orphans it."""
        marker = Path(tempfile.mkdtemp()) / "child-still-alive"
        script = (f"sh -c 'sleep 30; touch {marker}' & "
                  f"wait")
        hand.run(["sh", "-c", script], env=dict(os.environ), cwd=Path.cwd(),
                 log_path=tmp_log(), hard_cap=30, silence_cap=2)
        time.sleep(2)
        self.assertFalse(marker.exists(),
                         "a child outlived the group kill and kept working")


class TheEnvironment(unittest.TestCase):
    def test_the_hand_gets_only_what_it_is_given(self):
        log = tmp_log()
        hand.run(["sh", "-c", "echo ${SECRET_FROM_PARENT:-absent}"],
                 env={"PATH": os.environ["PATH"]}, cwd=Path.cwd(), log_path=log)
        self.assertIn("absent", log.read_text())

    def test_stdin_is_closed_so_a_prompt_cannot_hang_the_run(self):
        """An inherited terminal is how a run waits forever for nobody."""
        started = time.monotonic()
        result = hand.run(["sh", "-c", "read line; echo got"],
                          env=dict(os.environ), cwd=Path.cwd(), log_path=tmp_log(),
                          hard_cap=20, silence_cap=15)
        self.assertLess(time.monotonic() - started, 10,
                        "the run waited on stdin instead of finding it closed")
        self.assertNotEqual(result.reason, "silent")


if __name__ == "__main__":
    unittest.main(verbosity=2)

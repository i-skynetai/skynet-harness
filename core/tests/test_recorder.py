"""Tests for the run record.

Both of these are review findings: a race that a threaded reproduction hit, and
a constant bound at import that made the suite write into the real home.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import recorder  # noqa: E402


class ConcurrentRuns(unittest.TestCase):
    def test_two_hundred_threads_get_two_hundred_directories(self):
        """Creation is the claim. Check-then-create left a window."""
        root = Path(tempfile.mkdtemp()) / "runs"
        results, errors = [], []

        def start() -> None:
            try:
                results.append(recorder.Run.start(
                    role="developer", task="t", kb="k", agent_id="a", root=root).run_id)
            except Exception as exc:                      # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=start) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"{len(errors)} run(s) collided")
        self.assertEqual(len(set(results)), 200, "two runs shared an id")


class TheStateDirectory(unittest.TestCase):
    def test_it_is_read_when_called_not_when_imported(self):
        """Bound at import, a late SKY_STATE_DIR is ignored — and the suite
        wrote into the developer's real home."""
        tmp = Path(tempfile.mkdtemp())
        saved = os.environ.get("SKY_STATE_DIR")
        os.environ["SKY_STATE_DIR"] = str(tmp)
        try:
            self.assertEqual(recorder.state_dir(), tmp)
            run = recorder.Run.start(role="developer", task="t", kb="k", agent_id="a")
            self.assertTrue(str(run.directory).startswith(str(tmp)),
                            f"wrote to {run.directory}, outside {tmp}")
        finally:
            if saved is None:
                os.environ.pop("SKY_STATE_DIR", None)
            else:
                os.environ["SKY_STATE_DIR"] = saved


class TheRecord(unittest.TestCase):
    def test_a_field_called_kind_does_not_collide_with_the_event_name(self):
        """It did, and raised instead of recording — in an audit log."""
        root = Path(tempfile.mkdtemp())
        run = recorder.Run.start(role="developer", task="t", kb="k",
                                 agent_id="a", root=root)
        run.event("run.refused", kind="build", why="not ready")
        text = (run.directory / "events.jsonl").read_text()
        # The event name survives...
        self.assertIn('"kind": "run.refused"', text)
        # ...and so does the caller's field, under a name that cannot collide.
        self.assertIn('"field_kind": "build"', text)
        self.assertIn('"why": "not ready"', text)



if __name__ == "__main__":
    unittest.main(verbosity=2)

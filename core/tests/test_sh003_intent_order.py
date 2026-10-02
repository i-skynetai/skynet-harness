"""SH-003: `sky ship` lists intents in the order they were made.

Intent files once had random names and were read back sorted by name, so six
pushes recorded as steps 1 to 6 came out as 5, 1, 6, 2, 3, 4 — under a heading
that says "run them yourself, in this order".
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import broker  # noqa: E402
from sky.cli import main  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TenIntentsComeBackInOrder(unittest.TestCase):

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("SKY_RUN_ID", "SKY_AGENT_ID")}
        os.environ["SKY_RUN_ID"], os.environ["SKY_AGENT_ID"] = "r1", "nova"
        self.root = Path(tempfile.mkdtemp())
        for step in range(1, 11):
            code, _, err = run("intent", "--kind", "push",
                               "--summary", f"step {step}",
                               "--branch", f"fix/step-{step:02d}",
                               "--directory", str(self.root))
            self.assertEqual(code, 0, err)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_each_intent_is_sealed_with_when_it_was_made(self):
        for path in self.root.glob("*.json"):
            self.assertRegex(json.loads(path.read_text())["created_at"],
                             r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_read_pending_returns_them_in_creation_order(self):
        got = [i["summary"] for i in broker.read_pending(self.root)]
        self.assertEqual(got, [f"step {n}" for n in range(1, 11)])

    def test_ship_prints_them_in_creation_order(self):
        code, out, err = run("ship", "--directory", str(self.root))
        self.assertEqual(code, 0, err)
        positions = [out.index(f"fix/step-{n:02d}") for n in range(1, 11)]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""SH-010: the docs promise nothing the code does not do.

Six promises had no code behind them: a `brain:` line that picks the KB,
`$SKY_KB_MAP`, a commit trailer the broker checks, the plugin's own `.mcp.json`
as a second tool spelling, `docs/gates.md` and `docs/onboarding.md`. They were
removed for 2.1.2. This keeps them out of everything a reader or an agent reads.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[2]

PROMISES = ("brain:` line", "a `brain:` line", "SKY_KB_MAP", "commit trailer",
            "SKY-Agent:", "plugin's own `.mcp.json`", "mcp__plugin_sky_kb__kb_",
            "docs/gates.md", "docs/onboarding.md")


def shipped_text():
    """README, docs, CHANGELOG and the plugin a host loads (not its vendored code)."""
    paths = [REPO / "README.md", REPO / "CHANGELOG.md", REPO / "CONTRIBUTING.md"]
    paths += sorted((REPO / "docs").rglob("*.md"))
    paths += sorted(p for p in (REPO / "plugin").rglob("*")
                    if p.suffix in (".md", ".yaml", ".json")
                    and "runtime" not in p.parts)
    for path in paths:
        yield path, path.read_text(encoding="utf-8")


class NoPromiseWithoutCode(unittest.TestCase):

    def test_none_of_the_six_is_promised(self):
        for path, text in shipped_text():
            for promise in PROMISES:
                with self.subTest(file=str(path.relative_to(REPO)), promise=promise):
                    self.assertNotIn(promise, text)

    def test_the_trailer_method_is_gone_too(self):
        from sky import recorder
        self.assertFalse(hasattr(recorder.Run, "trailer"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

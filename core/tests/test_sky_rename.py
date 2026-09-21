"""The v2 identity is one contract, not a collection of labels.

This file names-retired-vocabulary-on-purpose: it lists the words the rename
retired, which means containing them.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path


#: A file may exempt itself by carrying this line. Some files have to contain
#: the old vocabulary — the table of retired names, and every test that proves
#: an entry actually bites. A hand-kept list of filenames needs editing each
#: time one is added and is therefore forgotten; a marker inside the file says
#: so where somebody reading that file will see it.
EXEMPT_MARKER = "names-retired-vocabulary-on-purpose"

#: Files that predate the marker, or are generated.
DEFINES_THE_RULES = {"selftest.py", "CHANGELOG.md"}

REPO = Path(__file__).resolve().parents[2]


class SkynetHarnessIdentity(unittest.TestCase):
    def test_marketplace_plugin_command_and_runtime_are_sky(self):
        marketplace = json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text())
        manifest = json.loads(
            (REPO / "plugin" / ".claude-plugin" / "plugin.json").read_text())

        self.assertEqual(marketplace["name"], "sky")
        self.assertEqual(marketplace["plugins"][0]["name"], "sky")
        self.assertEqual(manifest["name"], "sky")
        # The version is whatever the plugin says it is; this test is about
        # the NAME. Pinning "2.0.0" here failed the very next release and
        # proved nothing about the rename.
        self.assertRegex(manifest["version"], r"^2\.\d+\.\d+$")
        self.assertTrue((REPO / "core" / "bin" / "sky").is_file())
        self.assertTrue((REPO / "plugin" / "bin" / "sky").is_file())
        self.assertTrue((REPO / "core" / "sky" / "__main__.py").is_file())
        self.assertTrue((REPO / "plugin" / "runtime" / "sky" / "__main__.py").is_file())

    def test_shipped_surfaces_do_not_keep_the_old_namespace(self):
        old = "v" + "ai"
        roots = ("core", "plugin", "hosts", "schemas", "scripts")
        forbidden = (f"/{old}:", f"{old}_", f"{old}-harness", f"import {old}")
        problems = []

        for root_name in roots:
            root = REPO / root_name
            for path in root.rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                if old in path.name.lower():
                    problems.append(f"old name in path: {path.relative_to(REPO)}")
                    continue
                try:
                    raw = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if path.name in DEFINES_THE_RULES or EXEMPT_MARKER in raw:
                    # The table of retired names, and the tests that prove each
                    # entry bites, have to contain the old words — that is what
                    # they are for. Exempting them by name keeps the check from
                    # forbidding its own enforcement.
                    continue
                try:
                    body = raw.lower()
                except UnicodeDecodeError:                   # pragma: no cover
                    continue
                for token in forbidden:
                    if token in body:
                        problems.append(
                            f"{token!r} in {path.relative_to(REPO)}")

        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

"""SH-007: the KB map in the documents works as written.

The documents once gave the wrong path and an entry missing two required
fields, so pasting it failed. This loads each documented example as it is.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import kbmap  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DOCS = ("docs/getting-started.md", "docs/knowledge-port.md")


def example(doc: str) -> str:
    text = (REPO / doc).read_text()
    blocks = re.findall(r"```json\n(.*?)```", text, re.S)
    found = [b for b in blocks if '"mcp_url"' in b]
    assert found, f"{doc} has no KB map example"
    return found[0]


class TheDocumentedMapLoads(unittest.TestCase):

    def test_each_example_loads_as_written(self):
        for doc in DOCS:
            with self.subTest(doc=doc):
                path = Path(tempfile.mkdtemp()) / "kb-map.json"
                path.write_text(example(doc))
                self.assertTrue(list(kbmap.KBMap.load(path)))

    def test_each_document_names_the_path_the_code_reads(self):
        real = f"~/.config/sky/{kbmap.MAP_FILE}"
        for doc in DOCS:
            with self.subTest(doc=doc):
                text = (REPO / doc).read_text()
                self.assertIn(real, text)
                self.assertNotRegex(text, r"(?<![./])config/kb-map\.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)

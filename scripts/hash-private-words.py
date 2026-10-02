#!/usr/bin/env python3
"""Write scripts/private-words.sha256 from the local, plain-text word list.

The plain list (`~/.config/sky/selftest-words`, or $SKY_SELFTEST_WORDS) is never
committed: it names the organisations the project must not mention. This writes
only their salted hashes, which `sky selftest` checks over the whole tree, so CI
can run the check without the list.

    python3 scripts/hash-private-words.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from sky import selftest  # noqa: E402


def main() -> int:
    words = selftest.load_words()
    if not words:
        print(f"no local word list at {selftest.WORDS_FILE}; nothing written")
        return 1
    too_long = [w for w in words if len(w.split()) > selftest.MAX_PHRASE]
    if too_long:
        print(f"{len(too_long)} entries are longer than {selftest.MAX_PHRASE} words")
        return 1
    out = ROOT / selftest.HASHED_WORDS
    lines = ["# Salted SHA-256 of each private word. Written by "
             "scripts/hash-private-words.py.",
             "# Names nobody: the plain list stays on the maintainer's machine."]
    lines += sorted({selftest.word_hash(w) for w in words})
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines) - 2} hashes to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

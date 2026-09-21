#!/usr/bin/env python3
"""Copy the runtime into the plugin, so a plugin-only install actually works.

**The problem this solves.** The plugin shipped skills, agents, a policy and
three helper scripts — and no `sky`. So after `claude plugin install sky@sky`
and nothing else, `setup`, `doctor`, `build`, `stamp`, `ship`, the guard and
the ledger all did nothing, and the guard's fail-open branch made that
*invisible*: commands were allowed with a line on stderr nobody reads.

**Why vendoring rather than a package.** `core/` is standard library only, and
Ethan depends on that being true. A pip dependency would add one to both, and
an install step is an install step people skip. Fifty kilobytes of Python
copied into the plugin makes the plugin self-contained, which is what a person
who typed one install command is entitled to expect.

**One source of truth.** `core/sky/` is it. This script copies; it never
merges. `sky selftest` fails when the copy has drifted, the same way it fails
when a published schema has drifted, so the copy cannot quietly go stale.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "core" / "sky"
TARGET = ROOT / "plugin" / "runtime" / "sky"


def vendor(write: bool = True) -> list[str]:
    """Copy every module. Returns what differs (empty when in step)."""
    wanted = {p.name: p.read_text(encoding="utf-8")
              for p in sorted(SOURCE.glob("*.py"))}
    have = {p.name: p.read_text(encoding="utf-8")
            for p in sorted(TARGET.glob("*.py"))} if TARGET.is_dir() else {}

    drift = [f"{n} is missing from the plugin" for n in wanted if n not in have]
    drift += [f"{n} has drifted" for n in wanted
              if n in have and have[n] != wanted[n]]
    drift += [f"{n} is in the plugin and not in core" for n in have
              if n not in wanted]

    if write and drift:
        if TARGET.exists():
            shutil.rmtree(TARGET)
        TARGET.mkdir(parents=True)
        for name, body in wanted.items():
            (TARGET / name).write_text(body, encoding="utf-8")
    return drift


if __name__ == "__main__":
    found = vendor(write="--check" not in sys.argv)
    if "--check" in sys.argv:
        for line in found:
            print(f"  {line}")
        print("in step" if not found else
              f"{len(found)} difference(s) — run scripts/vendor-runtime.py")
        sys.exit(1 if found else 0)
    print(f"copied {len(list(SOURCE.glob('*.py')))} modules into {TARGET}")

#!/usr/bin/env python3
"""Render a diagram to SVG and PNG, and report what it could not do.

**Why this is a file and not a step in a skill.** Three skills need a rendered
diagram. Asked to "render the diagram", a run writes the conversion itself
every time — a different script each run, a different result, and tokens spent
rediscovering something that already worked. This is that script, saved once.

**What it will not do is pretend.** A document whose diagram exists only as a
fenced code block is not finished, and neither is one whose PNG silently never
appeared. Every failure is named, and the exit code says whether the caller may
claim a rendered diagram.

    render-diagram.py <input.mmd|input.svg> --out-dir images [--name flow]

Mermaid needs `mmdc` (`npm i -g @mermaid-js/mermaid-cli`). SVG input needs
nothing. PNG comes from `mmdc` when it rendered, else `qlmanage` on macOS, else
`rsvg-convert`/`inkscape` — and if none is present it says so rather than
leaving a caller to assume one appeared.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PNG_WIDTH = 1800


def run(argv: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return 127, f"{argv[0]} is not on PATH"
    except subprocess.TimeoutExpired:
        return 124, f"{argv[0]} did not finish within {timeout}s"
    return out.returncode, (out.stderr or out.stdout).strip()


def to_svg(source: Path, svg: Path) -> str:
    """Returns "" on success, or why it could not be done."""
    if source.suffix.lower() == ".svg":
        svg.write_bytes(source.read_bytes())
        return ""
    if not shutil.which("mmdc"):
        return ("mermaid input needs `mmdc` — install it with "
                "`npm i -g @mermaid-js/mermaid-cli`, or hand me an SVG")
    code, said = run(["mmdc", "-i", str(source), "-o", str(svg),
                      "-b", "transparent"])
    if code != 0 or not svg.is_file():
        return f"mmdc failed: {said[:200]}"
    return ""


def to_png(svg: Path, png: Path) -> str:
    """First converter that exists wins. Absence is reported, not hidden."""
    if shutil.which("rsvg-convert"):
        code, said = run(["rsvg-convert", "-w", str(PNG_WIDTH),
                          "-o", str(png), str(svg)])
        if code == 0 and png.is_file():
            return ""
        return f"rsvg-convert failed: {said[:160]}"
    if shutil.which("qlmanage"):
        # Writes <name>.svg.png into the output directory; rename it after.
        code, said = run(["qlmanage", "-t", "-s", str(PNG_WIDTH),
                          "-o", str(png.parent), str(svg)])
        produced = png.parent / (svg.name + ".png")
        if produced.is_file():
            produced.replace(png)
            return ""
        return f"qlmanage produced nothing: {said[:160]}"
    if shutil.which("inkscape"):
        code, said = run(["inkscape", str(svg), "--export-type=png",
                          f"--export-filename={png}", f"--export-width={PNG_WIDTH}"])
        if code == 0 and png.is_file():
            return ""
        return f"inkscape failed: {said[:160]}"
    return ("no SVG-to-PNG converter found (looked for rsvg-convert, qlmanage, "
            "inkscape). The SVG is fine; there is no PNG.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="a .mmd/.mermaid file, or an .svg")
    ap.add_argument("--out-dir", default="images")
    ap.add_argument("--name", help="base name (default: the source's)")
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_file():
        print(f"no such file: {source}", file=sys.stderr)
        return 2
    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    base = args.name or source.stem
    svg, png = out / f"{base}.svg", out / f"{base}.png"

    problem = to_svg(source, svg)
    if problem:
        print(f"SVG: {problem}", file=sys.stderr)
        return 1
    print(f"svg  {svg}")

    problem = to_png(svg, png)
    if problem:
        # Not fatal: an SVG is the required artifact and a PNG is the extra.
        # Exit 3 so a caller can tell "both" from "only the SVG" without
        # parsing text, and must not claim a PNG it does not have.
        print(f"png  not produced — {problem}", file=sys.stderr)
        return 3
    print(f"png  {png}")
    print("\nNow LOOK at the PNG before using the diagram. A render that "
          "succeeded and is unreadable is still a broken diagram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
nothing. PNG comes from `rsvg-convert`, else a headless Chrome, else
`inkscape`, else `qlmanage` — and if none is present it says so rather than
leaving a caller to assume one appeared.

**Why qlmanage is last.** It is a thumbnailer, not a renderer: it returns a
square image and crops a wide diagram to fit, with a zero exit code. A cropped
diagram that reports success is the exact failure this file exists to prevent,
so the aspect ratio of every PNG is checked against its source and a crop is
reported as a failure.
"""
from __future__ import annotations

import argparse
import re
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


CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
)


def chrome() -> str:
    """The first Chrome-family binary that exists, or ""."""
    for candidate in CHROME_PATHS:
        if "/" in candidate:
            if Path(candidate).is_file():
                return candidate
        elif shutil.which(candidate):
            return shutil.which(candidate)
    return ""


def svg_size(svg: Path) -> tuple[float, float] | None:
    """The source's intended width and height, or None if it does not say."""
    head = svg.read_text(errors="replace")[:4000]
    box = re.search(r'viewBox\s*=\s*"([^"]+)"', head)
    if box:
        parts = re.split(r"[\s,]+", box.group(1).strip())
        if len(parts) == 4:
            try:
                _, _, w, h = (float(v) for v in parts)
                if w > 0 and h > 0:
                    return w, h
            except ValueError:
                pass
    w = re.search(r'\bwidth\s*=\s*"([\d.]+)', head)
    h = re.search(r'\bheight\s*=\s*"([\d.]+)', head)
    if w and h and float(w.group(1)) > 0 and float(h.group(1)) > 0:
        return float(w.group(1)), float(h.group(1))
    return None


def png_size(png: Path) -> tuple[int, int] | None:
    """Width and height from the PNG header, without a third-party library."""
    try:
        raw = png.read_bytes()[:24]
    except OSError:
        return None
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def cropped(svg: Path, png: Path) -> str:
    """"" if the PNG keeps the source's shape, else why it does not."""
    want, got = svg_size(svg), png_size(png)
    if not want or not got or got[1] == 0:
        return ""                      # cannot tell; do not invent a failure
    wanted, actual = want[0] / want[1], got[0] / got[1]
    if abs(wanted - actual) / wanted <= 0.02:
        return ""
    return (f"the PNG is {got[0]}x{got[1]} but the source is "
            f"{want[0]:g}x{want[1]:g} — it was cropped, not scaled")


def by_chrome(binary: str, svg: Path, png: Path) -> str:
    """Chrome honours the viewBox, so a wide diagram stays wide."""
    size = svg_size(svg) or (PNG_WIDTH, PNG_WIDTH)
    width, height = int(round(size[0])), int(round(size[1]))
    scale = max(1.0, min(4.0, PNG_WIDTH / max(width, height)))
    page = png.parent / f".{png.stem}.render.html"
    page.write_text(
        '<!doctype html><meta charset="utf-8">'
        "<style>html,body{margin:0;padding:0;background:#fff}"
        f"img{{display:block;width:{width}px;height:{height}px}}</style>"
        f'<img src="{svg.resolve().as_uri()}">'
    )
    try:
        code, said = run([binary, "--headless", "--disable-gpu", "--no-sandbox",
                          f"--screenshot={png}", f"--window-size={width},{height}",
                          f"--force-device-scale-factor={scale:g}",
                          "--allow-file-access-from-files", page.resolve().as_uri()])
    finally:
        page.unlink(missing_ok=True)
    if not png.is_file():
        return f"chrome produced nothing: {said[:160]}"
    return cropped(svg, png)


def to_png(svg: Path, png: Path) -> str:
    """First converter that exists wins. Absence is reported, not hidden.

    Order is by fidelity, not convenience: a converter that keeps the shape of
    the diagram comes before one that only usually does.
    """
    if shutil.which("rsvg-convert"):
        code, said = run(["rsvg-convert", "-w", str(PNG_WIDTH),
                          "-o", str(png), str(svg)])
        if code == 0 and png.is_file():
            return cropped(svg, png)
        return f"rsvg-convert failed: {said[:160]}"
    binary = chrome()
    if binary:
        return by_chrome(binary, svg, png)
    if shutil.which("inkscape"):
        code, said = run(["inkscape", str(svg), "--export-type=png",
                          f"--export-filename={png}", f"--export-width={PNG_WIDTH}"])
        if code == 0 and png.is_file():
            return cropped(svg, png)
        return f"inkscape failed: {said[:160]}"
    if shutil.which("qlmanage"):
        # A thumbnailer, so it is the last resort: it writes
        # <name>.svg.png and squares anything that is not already square.
        code, said = run(["qlmanage", "-t", "-s", str(PNG_WIDTH),
                          "-o", str(png.parent), str(svg)])
        produced = png.parent / (svg.name + ".png")
        if produced.is_file():
            produced.replace(png)
            problem = cropped(svg, png)
            if problem:
                png.unlink(missing_ok=True)
                return f"qlmanage: {problem}"
            return ""
        return f"qlmanage produced nothing: {said[:160]}"
    return ("no SVG-to-PNG converter found (looked for rsvg-convert, Chrome, "
            "inkscape, qlmanage). The SVG is fine; there is no PNG.")


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

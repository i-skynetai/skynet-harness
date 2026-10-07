#!/usr/bin/env python3
"""Render every docs/images/*.mmd to SVG and PNG with mermaid-cli.

The documentation standard keeps Mermaid as the source, under a "Diagram sources"
appendix, and puts a rendered PNG on the page. This script is the one way those PNGs
are produced, so a figure is never hand-edited.

It needs Node and `@mermaid-js/mermaid-cli` (`npm install -g @mermaid-js/mermaid-cli`)
and a Chrome or Chromium for puppeteer. On Windows the `mmdc.cmd` shim breaks under
Git Bash, so the CLI is called through `node` directly, and Chrome is pointed at
through a puppeteer config when `--chrome` is given or the usual install exists.

    python scripts/render-mermaid.py                 # all of docs/images/*.mmd
    python scripts/render-mermaid.py docs/images/org-loop.mmd

Exit 0 only when every requested figure has both an SVG and a PNG newer than its
source. A missing tool is a named failure, not a silent skip.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def find_cli() -> list[str] | None:
    """The command that runs mermaid-cli, or None with the reason printed."""
    mmdc = shutil.which("mmdc")
    if mmdc and os.name != "nt":
        return [mmdc]
    node = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if os.name == "nt" else None)
    appdata = os.environ.get("APPDATA", "")
    cli = Path(appdata) / "npm" / "node_modules" / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    if node and cli.is_file() and Path(node).is_file():
        return [node, str(cli)]
    if mmdc:
        return [mmdc]
    print("render-mermaid: mermaid-cli not found — npm install -g @mermaid-js/mermaid-cli",
          file=sys.stderr)
    return None


def puppeteer_config(chrome: str | None) -> str | None:
    path = chrome or next((c for c in CHROME_CANDIDATES if Path(c).is_file()), None)
    if path is None:
        return None
    cfg = Path(tempfile.gettempdir()) / "sky-puppeteer.json"
    cfg.write_text(json.dumps({"executablePath": path.replace("\\", "/")}), encoding="utf-8")
    return str(cfg)


def render(cli: list[str], source: Path, cfg: str | None, scale: int) -> bool:
    ok = True
    for suffix, extra in ((".svg", []), (".png", ["-s", str(scale)])):
        out = source.with_suffix(suffix)
        cmd = cli + ["-i", str(source), "-o", str(out), "-b", "white"] + extra
        if cfg:
            cmd += ["-p", cfg]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if proc.returncode != 0 or not out.is_file():
            tail = " ".join((proc.stderr or proc.stdout or "").split())[-300:]
            print(f"FAIL {source.name} -> {out.name}: {tail}", file=sys.stderr)
            ok = False
        else:
            print(f"ok   {out.relative_to(ROOT)}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sources", nargs="*", help="Mermaid files; default docs/images/*.mmd")
    ap.add_argument("--chrome", help="path to a Chrome/Chromium binary for puppeteer")
    ap.add_argument("--scale", type=int, default=2, help="PNG scale factor (default 2)")
    args = ap.parse_args()
    sources = [Path(s).resolve() for s in args.sources] or sorted(IMAGES.glob("*.mmd"))
    if not sources:
        print("render-mermaid: no .mmd files under docs/images", file=sys.stderr)
        return 1
    cli = find_cli()
    if cli is None:
        return 2
    cfg = puppeteer_config(args.chrome)
    results = [render(cli, s, cfg, args.scale) for s in sources]
    return 0 if all(results) else 3


if __name__ == "__main__":
    sys.exit(main())

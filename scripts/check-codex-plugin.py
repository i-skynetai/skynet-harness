#!/usr/bin/env python3
"""Exercise the real Codex installer and skill discovery without a model call.

Use an isolated CODEX_HOME; never install over the person's configuration.
Requires Codex CLI with plugin and debug prompt-input commands (tested 0.160.0).
An install/discovery pass does not establish authenticated execution or governance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    executable = shutil.which("codex")
    if not executable:
        parser.exit(2, "Codex CLI is required; no installer check ran.\n")
    with tempfile.TemporaryDirectory(prefix="sky-plugin-check-") as directory:
        env = dict(os.environ, CODEX_HOME=directory)

        def run(*arguments: str) -> str:
            result = subprocess.run([executable, *arguments], cwd=root, env=env,
                                    capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=60)
            if result.returncode:
                raise RuntimeError(f"codex {' '.join(arguments)} failed: "
                                   f"{result.stderr.strip()}")
            return result.stdout

        print(run("--version").strip())
        run("plugin", "marketplace", "add", str(root), "--json")
        installed = json.loads(run("plugin", "add", "sky@sky", "--json"))
        listing = json.loads(run("plugin", "list", "--marketplace", "sky", "--json"))
        entries = listing.get("installed", [])
        if not any(x.get("pluginId") == "sky@sky" and x.get("installed")
                   and x.get("enabled") for x in entries):
            raise RuntimeError("sky@sky was not listed installed and enabled")
        cache = Path(installed["installedPath"])
        if not cache.resolve().is_relative_to(Path(directory).resolve()):
            raise RuntimeError("installer wrote outside the isolated Codex home")
        for kind in ("code", "review"):
            for path in (cache / "codex-skills" / kind / "SKILL.md",
                         cache / "skills" / kind / "SKILL.md"):
                if not path.is_file():
                    raise RuntimeError(f"installed skill reference missing: {path.name}")
        if not (cache / "bin" / "sky").is_file():
            raise RuntimeError("installed bundled runtime entry point is missing")
        manifest = json.loads((cache / ".codex-plugin" / "plugin.json").read_text())
        mapping = json.loads((cache / manifest["mcpServers"]).read_text())
        dispatch = mapping["mcpServers"]["sky_dispatch"]
        if dispatch["cwd"] != "." or dispatch["args"] != ["bin/sky-codex-dispatch.py"]:
            raise RuntimeError("dispatch must use installed-package-relative paths")
        if dispatch.get("tool_timeout_sec") != 1800:
            raise RuntimeError("dispatch timeout differs from the runtime hard cap")
        for path in (cache / dispatch["args"][0],
                     cache / "runtime" / "sky" / "codexdispatch.py",
                     cache / "runtime" / "sky" / "codexcontroller.py"):
            if not path.is_file():
                raise RuntimeError(f"installed dispatch file missing: {path.name}")
        prompt = run("debug", "prompt-input", "Use $sky:code and $sky:review")
        for name in ("sky:code:", "sky:review:"):
            if name not in prompt:
                raise RuntimeError(f"installed skill absent from model catalog: {name}")
        print("PASS: marketplace, install, enabled state, cached references, local dispatch and skill discovery")
        print("No authenticated model run or governed developer launch was tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

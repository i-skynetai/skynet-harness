#!/usr/bin/env python3
"""Authenticated SH-011 integration check; NOT run by unit tests or CI.

Uses a logged-in Claude CLI and temporary files to reproduce the maintainer's
three headless cases. This consumes model calls. Tool reports are model reports;
the file states are independently observed by this script. A failed or absent
login, unavailable CLI, inconclusive report or unexpected file state exits 1.
Usage: python scripts/check-role-boundary.py --out record.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PROMPT = (
    "Use the Edit tool to replace the word original with changed in the file "
    "note.txt in the current directory. Do not use Bash, PowerShell or any other "
    "substitute if Edit is unavailable. Then print exactly two lines: "
    "TOOLS=<every tool you have available> and EDIT=<succeeded|unavailable|denied>."
)
AGENT = (
    "---\nname: ro\ndescription: Read-only test agent for SH-011. Use for nothing else.\n"
    "tools: Read\n---\nYou are a test agent. Do exactly what the prompt asks, using "
    "tools, and report precisely which tool calls succeeded or were unavailable.\n"
)


def find_claude() -> str | None:
    """PATH as in core/sky/probes.py, then the Windows desktop bundle."""
    binary = shutil.which("claude")
    if binary:
        return binary
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        root = Path(os.environ["APPDATA"]) / "Claude" / "claude-code"
        found = sorted(root.glob("*/*/claude.exe"), key=lambda p: p.stat().st_mtime)
        if found:
            return str(found[-1])
    return None


def invoke(command, cwd=None, timeout=180):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)


def check_case(binary, root, name, flags, expected):
    folder = root / name
    (folder / ".claude" / "agents").mkdir(parents=True)
    note = folder / "note.txt"
    note.write_text("original", encoding="utf-8")
    (folder / ".claude" / "agents" / "ro.md").write_text(AGENT, encoding="utf-8")
    row = {"case": name, "flags": flags, "expected_file_state": expected,
           "tools_reported": None, "edit_reported": None, "ok": False}
    try:
        # Prompt before the variadic --allowedTools option, as in the launcher.
        out = invoke([binary, "-p", PROMPT, "--permission-mode", "acceptEdits",
                      "--output-format", "json", "--max-turns", "8", *flags], cwd=folder)
        row["exit_code"] = out.returncode
        body = json.loads(out.stdout)
        result = body.get("result", "")
        tools = re.search(r"(?m)^TOOLS=(.+)$", result)
        edit = re.search(r"(?m)^EDIT=(succeeded|unavailable|denied)\s*$", result)
        row["tools_reported"] = tools.group(1).strip() if tools else None
        row["edit_reported"] = edit.group(1) if edit else None
        row["permission_denials"] = body.get("permission_denials", [])
        row["ok"] = (out.returncode == 0 and not body.get("is_error")
                     and tools is not None and edit is not None
                     and row["edit_reported"] == ("unavailable" if name == "agent" else "succeeded"))
        if tools:
            reported = {t.strip() for t in tools.group(1).split(",")}
            row["ok"] = row["ok"] and (
                reported == {"Read"} if name == "agent" else "Edit" in reported)
        if not row["ok"]:
            row["error"] = "CLI failed or the tool/edit report was inconclusive; check login and host support"
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError, TypeError) as exc:
        row["error"] = f"could not complete case: {exc}"
    row["file_state"] = note.read_text(encoding="utf-8")
    row["ok"] = row["ok"] and row["file_state"] == expected
    if not row["ok"] and "error" not in row:
        row["error"] = "observed file state differs from expected state"
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    record = {"date": datetime.now(timezone.utc).isoformat(), "host_version": None,
              "cases": [], "ok": False}
    try:
        binary = find_claude()
        if not binary:
            raise RuntimeError("Claude CLI is absent: install it or put it on PATH")
        version = invoke([binary, "--version"], timeout=20)
        record["host_version"] = (version.stdout or version.stderr).strip()
        if version.returncode or not record["host_version"]:
            raise RuntimeError("Claude CLI could not report its version")
        print(record["host_version"], flush=True)
        auth = invoke([binary, "auth", "status"], timeout=30)
        try:
            logged_in = json.loads(auth.stdout).get("loggedIn") is True
        except (ValueError, AttributeError):
            logged_in = False
        if auth.returncode or not logged_in:
            raise RuntimeError("Claude CLI is not logged in, or auth status could not verify login; run claude auth login")
        with tempfile.TemporaryDirectory(prefix="sky-role-boundary-") as scratch:
            for name, flags, expected in (
                ("agent", ["--agent", "ro"], "original"),
                ("control", [], "changed"),
                ("allowed-tools", ["--allowedTools", "Read"], "changed"),
            ):
                row = check_case(binary, Path(scratch), name, flags, expected)
                record["cases"].append(row)
                print(f"{name}: {'PASS' if row['ok'] else 'FAIL'}; file={row['file_state']!r}", flush=True)
                if not row["ok"]:
                    print(row["error"], file=sys.stderr)
        record["ok"] = all(row["ok"] for row in record["cases"])
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        record["error"] = str(exc)
        print(f"role boundary check failed: {exc}", file=sys.stderr)
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"could not write record: {exc}", file=sys.stderr)
        return 1
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

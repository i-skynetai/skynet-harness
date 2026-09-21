#!/usr/bin/env python3
"""Publish the plugin's skills into the shared catalogue.

This is the **publish** half of the skill pipeline (D-18): a skill becomes
*findable* by being ingested here, and *runnable* only by being installed on a
machine as a file. The two are deliberately separate — anyone who can write to
the catalogue could otherwise put instructions into everyone's agents.

Three things it does that a plain loop would not:

**Every document passes the redaction gate first.** The same gate that guards
any knowledge-base write (`core/sky/redaction.py`), refusing rather than
scrubbing. A skill that carries a credential is not published and says so.

**It reads the entity count for each one.** An ingest that reports COMPLETED
having extracted nothing is the failure that hid for two days on this platform;
the count is in `jobs.output`, not `jobs.status`. A skill that lands with zero
entities is reported as a problem, not a success.

**It is re-runnable, and says plainly when it did nothing.** The platform
deduplicates by content hash: an unchanged skill is skipped with zero chunks and
zero entities, which is *not* a failure and must not be reported as one. There is
no force flag on the ingest tool — **a skill is re-extracted only when its text
changes**, so a change to the ontology does not retroactively re-parse what is
already there.

    export SKY_CATALOGUE_PAT=…            # a token for the catalogue tenant
    python3 scripts/publish-skills.py \\
        --url https://<host>/mcp/ --tenant DEMO0002 [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from sky import redaction  # noqa: E402

ONTOLOGY = "sky_skill"
LAYER = "project"          # the only tenant-isolated layer


def provenance(path: Path, body: str) -> dict:
    """Who published this skill, from which commit, and of what exactly.

    D-18 says a skill is found here and *installed* as a reviewed file. That
    review needs something to review against: without a commit and a checksum,
    "the catalogue says this is the impact skill" is a claim with nothing
    behind it, and a catalogue anyone can write to is exactly where that
    matters. The checksum is of the bytes that were ingested, so a later copy
    can be compared rather than trusted.
    """
    def git(*args: str) -> str:
        try:
            out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                                 text=True, timeout=15)
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    version = git("describe", "--tags", "--always", "--dirty") or "unknown"
    return {
        "skill_name": path.parent.name,
        "owner": git("config", "user.email") or git("config", "user.name") or "unknown",
        "version": version,
        "source_commit": git("rev-parse", "HEAD") or "unknown",
        "checksum": "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest(),
        # A dirty tree means the published text is not any commit. Say so in
        # the record rather than implying a provenance that does not exist.
        "reproducible": not version.endswith("-dirty"),
    }


def rpc(url: str, token: str, name: str, arguments: dict, timeout: int = 120):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json, text/event-stream")
    request.add_header("Authorization", f"Bearer {token}")
    raw = urllib.request.urlopen(request, timeout=timeout).read().decode()
    for line in raw.splitlines():                      # unwrap SSE framing
        if line.startswith("data: "):
            raw = line[6:]
            break
    outer = json.loads(raw)
    if "error" in outer:
        raise RuntimeError(outer["error"])
    result = outer["result"]
    if result.get("isError"):
        raise RuntimeError(" ".join(c.get("text", "") for c in result.get("content", [])))
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except ValueError:
                return item["text"]
    return {}


def wait_for(url: str, token: str, tenant: str, job: str, limit: int = 240) -> dict:
    """Poll to completion, then read the OUTPUT — the status carries no count."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        status = rpc(url, token, "kb.jobs.status",
                     {"tenant_code": tenant, "job_id": job})
        state = str(status.get("status", "")).upper()
        if state in ("COMPLETED", "FAILED", "ERROR"):
            if state != "COMPLETED":
                return {"status": state, "entities": 0,
                        "error": str(status.get("errors") or "")[:200]}
            out = rpc(url, token, "kb.jobs.output",
                      {"tenant_code": tenant, "job_id": job})
            body = out.get("output") or {}
            return {"status": state, "entities": body.get("entities"),
                    "relations": body.get("relations"),
                    "chunks": body.get("chunks"),
                    "document_id": body.get("document_id"),
                    "was_duplicate": body.get("was_duplicate"),
                    "existing_uploaded_at": body.get("existing_uploaded_at")}
        time.sleep(3)
    return {"status": "TIMEOUT", "entities": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True, help="the catalogue's MCP endpoint")
    ap.add_argument("--tenant", required=True, help="the catalogue tenant code")
    ap.add_argument("--pat-env", default="SKY_CATALOGUE_PAT")
    ap.add_argument("--skills", default=str(ROOT / "plugin" / "skills"))
    ap.add_argument("--dry-run", action="store_true",
                    help="gate every document and report; ingest nothing")
    args = ap.parse_args()

    token = os.environ.get(args.pat_env, "")
    if not token and not args.dry_run:
        print(f"{args.pat_env} is not set", file=sys.stderr)
        return 2

    files = sorted(Path(args.skills).glob("*/SKILL.md"))
    if not files:
        print(f"no skills under {args.skills}", file=sys.stderr)
        return 2

    print(f"{len(files)} skills → tenant {args.tenant}, ontology {ONTOLOGY}"
          + ("   (dry run)" if args.dry_run else "") + "\n")

    problems = 0
    for path in files:
        skill = path.parent.name
        body = path.read_text(encoding="utf-8")

        # The gate first, always. A refusal here is the point of the gate.
        try:
            redaction.gate(body)
        except redaction.WouldLeak as leak:
            print(f"  {skill:<10} REFUSED — {len(leak.findings)} possible secret(s)")
            for finding in leak.findings:
                print(f"             {finding}")
            problems += 1
            continue

        if args.dry_run:
            print(f"  {skill:<10} ok, {len(body):>5} bytes — gate passed, not ingested")
            continue

        try:
            started = rpc(args.url, token, "kb.documents.ingest", {
                "tenant_code": args.tenant, "text": body,
                "filename": f"{skill}.SKILL.md",
                "ontology": ONTOLOGY, "layer": LAYER,
                "metadata": provenance(path, body)})
            job = started.get("job_id") or started.get("id")
            if not job:
                print(f"  {skill:<10} FAILED — no job id: {str(started)[:90]}")
                problems += 1
                continue
            done = wait_for(args.url, token, args.tenant, job)
        except Exception as exc:
            print(f"  {skill:<10} FAILED — {type(exc).__name__}: {str(exc)[:110]}")
            problems += 1
            continue

        entities = done.get("entities")
        if done["status"] != "COMPLETED":
            print(f"  {skill:<10} {done['status']} — {done.get('error','')[:80]}")
            problems += 1
        elif done.get("was_duplicate"):
            # Unchanged content is skipped by sha256 — 0 chunks, 0 entities, and
            # NOT a failure. Reading that as "stored but not learned" is a false
            # alarm, and a publish tool that cries wolf on every re-run is one
            # nobody re-runs. The earlier extraction still stands.
            print(f"  {skill:<10} unchanged — already published "
                  f"{str(done.get('existing_uploaded_at') or '')[:10]}, not re-extracted")
        elif not entities:
            # COMPLETED, genuinely new, and nothing learned. The whole reason
            # the count is read at all.
            print(f"  {skill:<10} ZERO ENTITIES — stored but not learned "
                  f"({done.get('chunks')} chunks)")
            problems += 1
        else:
            print(f"  {skill:<10} {entities:>3} entities, "
                  f"{done.get('relations') or 0:>2} relations, "
                  f"{done.get('chunks')} chunks")

    print()
    if problems:
        print(f"{len(files) - problems}/{len(files)} published; {problems} need attention.")
        return 1
    print(f"all {len(files)} published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

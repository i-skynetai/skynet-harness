#!/usr/bin/env python3
"""Check every tool a role agent is allowed to call actually exists.

A role agent's authority is its `tools:` line: a tool that is not listed is
not visible to it. That makes the line load-bearing, and it makes a typo
silent — the agent simply cannot do something, and nobody finds out until a
task fails halfway. So this runs against the live servers, not a fixture.

It also enforces the rule the design rests on: no write-capable tool may
appear in a read-only role's allowlist. The boundary is what the role can
see, not what it is asked not to do.

Reads the same three variables the plugin itself reads:

    SKY_KB_URL    the knowledge endpoint  (.../mcp/)
    SKY_CODE_URL  the code endpoint       (.../mcp-internal/)
    SKY_KB_PAT    your own token

Exit 0 = every allowlist is sound. Exit 1 = a problem worth blocking on.
Part of `sky-setup selftest`; safe to run on its own.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import urllib.request

# Tools a read-only role must never be able to see. Substring match on the
# tool's own name, deliberately broad: a false positive costs one review, a
# false negative hands a reviewer the ability to change the thing it reviews.
WRITE_MARKERS = (
    "ingest", "create", "update", "delete", "transition", "add_comment",
    "assign", "link", "unlink", "upload", "publish", "set_", "run_",
    "execute", "merge", "push", "import", "bulk_",
)

#: Helper agents a skill delegates to. They are not roles in `policy.yaml`, so
#: the policy cannot say whether they may write — this is where that is said.
HELPER_ROLES_READ_ONLY = {"context-retriever"}
HELPER_ROLES_MAY_WRITE = {"validator"}          # runs the repository's tests


def read_only_roles(policy_path: str = "") -> set[str]:
    """Which agents must hold no write-capable tool.

    Derived from `policy.yaml` rather than written down again here: a role that
    cannot `repo.edit` is a role that must not hold a tool that writes. A second
    hand-maintained list is a second policy, and the looser one wins on the day
    they differ.
    """
    names = set(HELPER_ROLES_READ_ONLY)
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
        from sky.policy import Policy
        policy = Policy.load(policy_path or None)
    except Exception as exc:
        # This script has to keep working without core importable — it is run
        # on its own as well as from selftest. Say what was lost, rather than
        # silently checking less than the caller thinks.
        print(f"note: could not read the policy ({exc}).")
        print("      Falling back to the four role names; a role renamed in "
              "policy.yaml would not be noticed here.")
        return names | {"reviewer", "architect", "security"}
    for role in policy.roles_named():
        if not policy.decide(role, "repo.edit").allowed:
            names.add(role)
    return names


def server_tools(url: str, token: str) -> set[str]:
    """Tool names as the CLIENT will spell them.

    The server names tools with dots (`kb.jobs.status`); the host turns
    those into underscores when it builds the tool id an allowlist has to
    match. Comparing raw server names against allowlist entries reports
    every single tool as missing, which is a confusing way to learn this.
    """
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": "tools/list", "params": {}}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    # Streamable HTTP needs both, or the request hangs rather than failing.
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {token}")
    raw = urllib.request.urlopen(req, timeout=60).read().decode()
    for line in raw.splitlines():
        if line.startswith("data: "):
            raw = line[6:]
            break
    payload = json.loads(raw)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return {t["name"].replace(".", "_") for t in payload["result"]["tools"]}


def allowlists(directory: str = "agents") -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))):
        text = open(path, encoding="utf-8").read()
        match = re.search(r"^tools: (.+)$", text, flags=re.M)
        if not match:
            continue
        role = os.path.basename(path)[:-3]
        out[role] = {t.strip() for t in match.group(1).split(",") if t.strip()}
    return out


def main() -> int:
    directory = sys.argv[1] if len(sys.argv) > 1 else "agents"
    read_only = read_only_roles()
    print(f"read-only agents (from the policy): {', '.join(sorted(read_only))}\n")

    token = os.environ.get("SKY_KB_PAT", "")
    kb_url = os.environ.get("SKY_KB_URL", "")
    code_url = os.environ.get("SKY_CODE_URL", "")
    if not (token and kb_url):
        print("SKY_KB_PAT and SKY_KB_URL must be set — run `sky-setup init` first.")
        return 1

    rosters = {"mcp__kb__": server_tools(kb_url, token)}
    if code_url:
        rosters["mcp__code__"] = server_tools(code_url, token)
    else:
        print("note: SKY_CODE_URL is unset, so code-tool references are not checked.")

    for prefix, names in rosters.items():
        print(f"live roster {prefix}* : {len(names)} tools")

    problems = 0
    found = allowlists(directory)
    if not found:
        print(f"no agent files found under {directory}/ — nothing checked.")
        return 1
    for role, tools in found.items():
        mcp = {t for t in tools if t.startswith("mcp__")}
        unknown, writes = [], []
        for tool in sorted(mcp):
            prefix = next((p for p in rosters if tool.startswith(p)), None)
            if prefix is None:
                unknown.append((tool, "no server with that prefix"))
                continue
            short = tool[len(prefix):]
            if short not in rosters[prefix]:
                unknown.append((tool, "not published by that server"))
            if role in read_only and any(m in short for m in WRITE_MARKERS):
                writes.append(tool)

        status = "ok" if not (unknown or writes) else "PROBLEM"
        print(f"\n{role}: {len(mcp)} MCP tools — {status}")
        for tool, why in unknown:
            print(f"   missing  {tool}  ({why})")
        for tool in writes:
            print(f"   WRITE TOOL in a read-only role: {tool}")
        problems += len(unknown) + len(writes)

    print()
    if problems:
        print(f"FAIL — {problems} problem(s).")
        return 1
    print("PASS — every allowed tool exists, and no read-only role can write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""SH-067: every binding, declared skill and effective role tool must exist.

Live mode reads MCP servers from .sky/context.yaml and the KB map, queries
HTTP or stdio tools/list, and records metadata in .sky/tool-inventory.json.
--offline reads that inventory without contacting servers. An unreachable
server uses its dated recorded inventory; no record is a failure.

Managed projects use their effective layered policy; otherwise the shipped
policy is checked. --policy is an explicit development override. An optional
positional agent directory retains checks of helper-agent allowlists.

Provider annotation findings use Policy.annotation_problems(inventory) through
an instance-local implementation of the existing hook. No provider annotation
claims are inferred when annotations are absent. The existing read-role tool
name heuristic remains as defence in depth. Exit 0 means no findings; 1 fails.
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


def main(argv=None) -> int:
    """Check policy, declared skills, effective roles and optional agent files."""
    import argparse
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
    from sky import inventory, project
    from sky.policy import Policy, _installed_policy, _repo_policy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", help="optional agent directory")
    parser.add_argument("--hand", default="claude")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--policy", type=Path, help="explicit development policy override")
    parser.add_argument("--kb-map", type=Path)
    args = parser.parse_args(argv)
    try:
        effective = None if args.policy else project.resolve(Path.cwd(), ignore_overrides=True)
        if effective is not None:
            policy = effective
            root = effective.root
        else:
            plugin = os.environ.get("SKY_PLUGIN_ROOT")
            source = args.policy or (Path(plugin) / "policy.yaml" if plugin else
                                     _installed_policy() or _repo_policy())
            if source is None:
                raise ValueError("no shipped policy found")
            # Explicit path bypasses project and configured single-file discovery.
            policy = Policy.load(source)
            root = project.git_root(Path.cwd()) or Path.cwd()
        if args.offline and not (root / ".sky/tool-inventory.json").exists():
            print("no inventory at .sky/tool-inventory.json — run once without --offline to record it")
            print("FAIL: 1 problem(s).")
            return 1
        if effective is not None:
            print(effective.layers_notice())
        servers = inventory.configured_servers(root, kb_map=args.kb_map)
        roster, notices, problems = inventory.collect(
            servers, root / ".sky/tool-inventory.json", offline=args.offline)
        extra = {f"agent {role}": tools for role, tools in allowlists(args.directory).items()} if args.directory else {}
        if args.directory and not extra:
            problems.append(f"no agent files found under {args.directory}")
        notes, findings = inventory.check(policy, roster, hand=args.hand, extra=extra)
        notices.extend(notes)
        problems.extend(findings)
        # Keep the pre-existing read-role name heuristic as defence in depth,
        # alongside the policy bindings and provider annotation checks.
        read_only = HELPER_ROLES_READ_ONLY | {
            role for role in policy.roles_named() if not policy.decide(role, "repo.edit").allowed}
        rosters = {role: policy.tools_for(role) for role in policy.roles_named()}
        if args.directory:
            rosters.update(allowlists(args.directory))
        for role, tools in sorted(rosters.items()):
            if role in read_only:
                for tool in sorted(tools):
                    short = tool.split("__", 2)[-1]
                    if tool.startswith("mcp__") and any(marker in short for marker in WRITE_MARKERS):
                        problems.append(f"role {role}: WRITE TOOL in a read-only role: {tool}")
        for notice in notices:
            print(notice)
        for problem in problems:
            print(problem)
        print(f"FAIL: {len(problems)} problem(s)." if problems else
              "PASS: every binding, skill and role tool exists; annotation checks passed.")
        return 1 if problems else 0
    except Exception as exc:
        print(f"FAIL: inventory check refused ({type(exc).__name__}); check policy, context and inventory configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""SH-067: provider tool inventory and annotation checks, standard library only.

Context server definitions use `servers` (or host-style `mcpServers`) mapping
names to HTTP `url`/`headers` or stdio `command`/`args`/`env`. Inventories contain
tool metadata, never server addresses, tokens or command environments.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType

from .hosts import BUILTIN_TOOLS
from .policy import PolicyError

READ_ACTIONS = {"repo.read", "kb.read", "code.index.read", "ticket.read", "pr.read", "ci.read"}


def tool_metadata(tools):
    """Normalize server names exactly as Claude MCP identifiers do."""
    result = {}
    for tool in tools:
        if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
            raise ValueError("tools/list returned an invalid tool")
        meta = {}
        if "annotations" in tool:
            if not isinstance(tool["annotations"], dict):
                raise ValueError("tool annotations must be a mapping")
            meta["annotations"] = tool["annotations"]
        result[tool["name"].replace(".", "_")] = meta
    return result


def _payload(raw, request_id):
    candidates = [raw]
    candidates.extend(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
    for candidate in candidates:
        try:
            body = json.loads(candidate)
        except ValueError:
            continue
        if body.get("id") == request_id:
            if "error" in body:
                raise ValueError("MCP request failed")
            return body.get("result", {})
    raise ValueError("MCP response has no matching result")


def query_server(spec, timeout=20):
    """Initialize MCP, list every page, then close the read-only connection."""
    process = None
    session = None
    if spec.get("url"):
        def request(method, params, request_id):
            nonlocal session
            body = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                body["id"] = request_id
            headers = dict(spec.get("headers", {}))
            if spec.get("token"):
                headers["Authorization"] = "Bearer " + spec["token"]
            headers.update({"Content-Type": "application/json",
                            "Accept": "application/json, text/event-stream"})
            if session:
                headers["Mcp-Session-Id"] = session
                headers["MCP-Protocol-Version"] = "2025-03-26"
            req = urllib.request.Request(spec["url"], json.dumps(body).encode(), headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                session = response.headers.get("Mcp-Session-Id", session)
                return _payload(response.read().decode("utf-8"), request_id) if request_id is not None else {}
    elif spec.get("command"):
        process = subprocess.Popen([spec["command"], *spec.get("args", [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, **spec.get("env", {})})
        messages = queue.Queue()

        def reader():
            for line in process.stdout:
                messages.put(line)
            messages.put(None)

        threading.Thread(target=reader, daemon=True).start()

        def request(method, params, request_id):
            body = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                body["id"] = request_id
            process.stdin.write(json.dumps(body) + "\n")
            process.stdin.flush()
            if request_id is None:
                return {}
            import time
            deadline = time.monotonic() + timeout
            while True:
                line = messages.get(timeout=max(0, deadline - time.monotonic()))
                if line is None:
                    raise ValueError("MCP server exited")
                body = json.loads(line)
                if body.get("id") == request_id:
                    return _payload(line, request_id)
    else:
        raise ValueError("server has no URL or command")
    try:
        request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "sky-tool-inventory", "version": "1"}}, 1)
        request("notifications/initialized", {}, None)
        tools, cursor, seen = [], None, set()
        while True:
            result = request("tools/list", {"cursor": cursor} if cursor else {}, 2)
            tools.extend(result["tools"])
            cursor = result.get("nextCursor")
            if not cursor:
                return tool_metadata(tools)
            if cursor in seen:
                raise ValueError("MCP pagination repeats a cursor")
            seen.add(cursor)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()


def read_inventory(path):
    if not Path(path).exists():
        return {"servers": {}}
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(body, dict) or not isinstance(body.get("servers"), dict):
        raise ValueError("tool inventory must contain a servers mapping")
    for name, server in body["servers"].items():
        if not isinstance(server, dict) or not isinstance(server.get("tools"), dict):
            raise ValueError(f"inventory server {name}: tools must be a mapping")
        for meta in server["tools"].values():
            if not isinstance(meta, dict) or ("annotations" in meta and not isinstance(meta["annotations"], dict)):
                raise ValueError(f"inventory server {name}: invalid tool metadata")
    return body


def collect(servers, path, *, offline=False, query=query_server, now=None):
    old = read_inventory(path)
    date = now or datetime.now(timezone.utc).isoformat()
    result = {"timestamp": old.get("timestamp") if offline else date, "servers": {}}
    notices, problems = [], []
    if offline:
        notices.append(f"offline: using recorded inventory from {old.get('timestamp', 'unknown date')}")
    names = sorted(set(servers) | (set(old["servers"]) if offline else set()))
    for name in names:
        cached = old["servers"].get(name)
        if offline:
            if cached is None:
                problems.append(f"server {name}: no recorded inventory (offline)")
            else:
                result["servers"][name] = cached
            continue
        try:
            tools = query(servers[name])
            result["servers"][name] = {"timestamp": date, "tools": tools}
            notices.append(f"server {name}: live inventory, {len(tools)} tools")
        except Exception:
            # Do not print transport exceptions: they may contain credentials.
            if cached is not None:
                result["servers"][name] = cached
                notices.append(f"server {name}: unreachable (inventory from {cached.get('timestamp', old.get('timestamp', 'unknown date'))})")
            else:
                problems.append(f"server {name}: unreachable with no recorded inventory")
    if not offline:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result, notices, problems


def provided_tools(inventory):
    return {f"mcp__{server}__{name}": meta
            for server, record in inventory.get("servers", {}).items()
            for name, meta in record["tools"].items()}


def annotation_problems(policy, inventory=None):
    if inventory is None:
        return []
    problems = []
    for tool, meta in sorted(provided_tools(inventory).items()):
        action_name = policy.binding(tool)
        action = policy.actions.get(action_name)
        if action is None or "annotations" not in meta:
            continue
        annotations = meta["annotations"]
        if action_name in READ_ACTIONS and annotations.get("readOnlyHint") is not True:
            problems.append(f"binding {tool}: {action_name} requires readOnlyHint: true")
        if annotations.get("destructiveHint") is True and not action.outward:
            problems.append(f"binding {tool}: destructiveHint: true requires an outward action ({action_name})")
    return problems


def install_annotation_hook(policy):
    """Wire the existing optional-inventory hook on this checker-owned instance.

    Policy loading stays offline; no global class mutation or frozen policy.py
    edit is needed. EffectivePolicy instances have the same hook signature.
    """
    policy.annotation_problems = MethodType(annotation_problems, policy)
    return policy


def check(policy, inventory, *, hand="claude", extra=None):
    builtin = BUILTIN_TOOLS.get(hand, frozenset())
    notices = []
    if not builtin:
        notices.append(f"hand {hand}: built-ins empty ({'unknown hand' if hand not in BUILTIN_TOOLS else 'no measured tool names'})")
    provided = provided_tools(inventory)
    references = {f"binding {tool}": [tool] for tool in policy.bindings}
    # EffectivePolicy keeps raw declared skills, including ungranted ones.
    skills = policy.body.get("skills", {})
    def expand(names, stack=()):
        tools = []
        for name in names:
            if name.startswith("+"):
                group = name[1:]
                if group in stack or group not in policy.body.get("tool_groups", {}):
                    raise PolicyError(f"invalid inventory tool group {group}")
                tools.extend(expand(policy.body["tool_groups"][group], (*stack, group)))
            else:
                tools.append(name)
        return tools
    for name, spec in skills.items():
        references[f"skill {name}"] = expand(spec.get("tools", []))
    for role in policy.roles_named():
        references[f"role {role}"] = policy.tools_for(role)
    references.update(extra or {})
    problems = []
    for owner, tools in sorted(references.items()):
        for tool in sorted(set(tools)):
            base = "Bash" if tool.startswith("Bash(") and tool.endswith(")") else tool
            if base not in builtin and tool not in provided:
                problems.append(f"{owner}: missing tool {tool} (no server or hand provides it)")
    install_annotation_hook(policy)
    problems.extend(policy.annotation_problems(inventory))
    return notices, problems


def configured_servers(root, *, kb_map=None):
    """Collect context servers and every KB-map entry; conflicts fail closed."""
    from . import yamlish
    from .kbmap import KBMap, CONFIG_DIR, MAP_FILE
    servers = {}
    context = Path(root) / ".sky/context.yaml"
    if context.exists():
        body = yamlish.parse(context.read_text(encoding="utf-8"))
        raw = body.get("servers", body.get("mcpServers", {}))
        if not isinstance(raw, dict):
            raise ValueError("context servers must be a mapping")
        for name, spec in raw.items():
            if not isinstance(spec, dict):
                raise ValueError(f"context server {name}: definition must be a mapping")
            servers[name] = spec
    path = Path(kb_map) if kb_map else CONFIG_DIR / MAP_FILE
    if path.exists():
        entries = list(KBMap.load(path))
        for kb in entries:
            # Default task KB uses the launcher's kb/code identities; other map
            # entries retain their distinct names, never union unrelated tools.
            name = "kb" if kb.default else kb.name
            token = os.environ.get(kb.pat_env, "")
            for server, url in ((name, kb.url), ("code" if kb.default else f"{name}_code", kb.code_url)):
                if url:
                    spec = {"url": url, "token": token}
                    if server in servers and servers[server].get("url") != url:
                        raise ValueError(f"server {server}: conflicting context and KB map definitions")
                    servers.setdefault(server, spec)
    for name, variable in (("kb", "SKY_KB_URL"), ("code", "SKY_CODE_URL")):
        if os.environ.get(variable) and name not in servers:
            servers[name] = {"url": os.environ[variable], "token": os.environ.get("SKY_KB_PAT", "")}
    return servers

"""SH-083 project context adapters and bounded, read-only capability checks.

Configuration describes protocol operations, not role authority. An adapter
never grants a model tools that its agent definition does not hold.
"""
from __future__ import annotations

import copy
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import inventory, project, yamlish
from .kbmap import KB
from .kbstore import Store, StoreError
from .policy import PolicyError

CAPABILITIES = ("search", "graph", "code", "tickets", "decisions", "ingest")
MUTATING_OPERATIONS = {"index.refresh"}  # Runtime only; never a role grant.
LOCAL_OPERATIONS = {"search.keyword": "search", "graph.neighbours": "neighbours",
                    "decisions.find": "decisions_find", "decisions.record": "decisions_record",
                    "ingest.document": "ingest"}


class ContextError(ValueError):
    """A present adapter must be valid; configuration errors never fall back."""


class NotManaged(ContextError):
    """The normal absence of opt-in governance, distinct from invalid config."""


def repository(cwd=None, explicit=None):
    if explicit is not None:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise ContextError(f"--root is not a directory: {root}")
        return root
    here = Path(cwd or Path.cwd()).resolve()
    if not any((p / ".sky/project.yaml").exists() for p in (here, *here.parents)):
        raise NotManaged("local KB requires managed: true in .sky/project.yaml; or provide --root <repo>")
    root = project.git_root(here)
    if root is None:
        raise ContextError("cannot resolve repository for .sky/project.yaml: git rev-parse failed")
    if root is not None and (root / ".sky/project.yaml").exists():
        try:
            config = project.validate_config(project.read_mapping(root / ".sky/project.yaml"), root)
        except PolicyError as exc:
            raise ContextError(str(exc)) from exc
        if config["managed"]:
            return root
    raise NotManaged("local KB requires managed: true in .sky/project.yaml; or provide --root <repo>")


def _read(root):
    path = Store(root).safe_path(".sky/context.yaml")
    if not path.exists():
        return {}
    try:
        body = yamlish.parse(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yamlish.YamlishError) as exc:
        raise ContextError(f"{path}: {exc}") from exc
    if not isinstance(body, dict):
        raise ContextError(f"{path}: must be a mapping")
    return body


@dataclass
class Context:
    root: Path
    body: dict

    @property
    def servers(self):
        return self.body.get("servers", {})

    @property
    def sources(self):
        return self.body.get("sources", {})

    @property
    def local(self):
        return "local" in self.sources

    def mappings(self, capability):
        return [(name, source["server"], operation, mapping["tool"])
                for name, source in self.sources.items()
                for operation, mapping in source.items()
                if operation != "server" and operation.split(".", 1)[0] == capability]


def load(cwd=None, *, root=None):
    if root is None:
        try:
            root = repository(cwd)
        except NotManaged:
            return None
    root = Path(root).resolve()
    try:
        body = _read(root)
    except StoreError as exc:
        raise ContextError(str(exc)) from exc
    servers, sources = body.get("servers", {}), body.get("sources", {})
    if not isinstance(servers, dict) or not isinstance(sources, dict):
        raise ContextError("context.yaml: servers and sources must be mappings")
    for name, server in servers.items():
        if not isinstance(server, dict) or bool(server.get("command")) == bool(server.get("url")):
            raise ContextError(f"context.yaml server {name}: exactly one command or url required")
        for field in ("command", "url"):
            if field in server and (not isinstance(server[field], str) or not server[field].strip()):
                raise ContextError(f"context.yaml server {name}: {field} must be a nonempty string")
        if not isinstance(server.get("args", []), list) or any(not isinstance(a, str) for a in server.get("args", [])):
            raise ContextError(f"context.yaml server {name}: args must be strings")
        if not isinstance(server.get("env", {}), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in server.get("env", {}).items()):
            raise ContextError(f"context.yaml server {name}: env must map strings to strings")
    for name, source in sources.items():
        if not isinstance(source, dict) or source.get("server") not in servers:
            raise ContextError(f"context.yaml source {name}: unknown server")
        for operation, mapping in source.items():
            if operation == "server":
                continue
            if ("." not in operation or (operation.split(".", 1)[0] not in CAPABILITIES and operation not in MUTATING_OPERATIONS) or
                    not isinstance(mapping, dict) or not isinstance(mapping.get("tool"), str) or not mapping["tool"]):
                raise ContextError(f"context.yaml source {name}: invalid operation {operation}")
    return Context(root, body)


def _yaml(body, depth=0):
    """Emit the same narrow YAML subset consumed by every shipped resolver."""
    lines = []
    for key in sorted(body):
        value = body[key]
        prefix = " " * depth + json.dumps(key, ensure_ascii=False) + ":"
        if isinstance(value, dict):
            if not value:
                raise ContextError(f"cannot preserve empty mapping {key}; remove it before writing adapter")
            lines.append(prefix)
            lines.extend(_yaml(value, depth + 2))
        elif isinstance(value, list):
            if any(isinstance(v, (dict, list)) for v in value):
                raise ContextError(f"cannot preserve nested list {key}")
            lines.append(prefix + " " + json.dumps(value, ensure_ascii=False))
        else:
            lines.append(prefix + " " + json.dumps(value, ensure_ascii=False))
    return lines


def write_adapter(root):
    root = Path(root).resolve()
    store = Store(root)
    with store.locked():
        load(root=root)  # Refuse malformed existing adapters before any write.
        body = copy.deepcopy(_read(root))
        for key in ("servers", "sources"):
            if key in body and not isinstance(body[key], dict):
                raise ContextError(f"context.yaml: {key} must be a mapping")
            body.setdefault(key, {})
        server = {"command": sys.executable,
                  "args": ["-m", "sky", "kb", "serve", "--root", str(root)],
                  "env": {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}}
        source = {"server": "sky_kb", **{op: {"tool": tool} for op, tool in LOCAL_OPERATIONS.items()}}
        # Reserved names may be updated only when already describing our local server.
        old = body["servers"].get("sky_kb")
        if old is not None and (not isinstance(old, dict) or old.get("args", [])[:4] != ["-m", "sky", "kb", "serve"]):
            raise ContextError("context.yaml: sky_kb is owned by another server")
        old_source = body["sources"].get("local")
        if old_source is not None and (not isinstance(old_source, dict) or old_source.get("server") != "sky_kb"):
            raise ContextError("context.yaml: local is owned by another source")
        body["servers"]["sky_kb"] = server
        body["sources"]["local"] = source
        text = "\n".join(_yaml(body)) + "\n"
        if yamlish.parse(text) != body:
            raise ContextError("context.yaml contains values the portable YAML reader cannot preserve")
        path = store.safe_path(".sky/context.yaml")
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            store._atomic(path, text)
    load(root=root)  # The writer's output must be readable by the resolver.
    return path


def capabilities(context, *, query=None, timeout=5):
    query = query or inventory.query_server
    inventories = {}
    rows = []
    for capability in CAPABILITIES:
        mappings = context.mappings(capability) if context else []
        if not mappings:
            rows.append((capability, "absent", "nothing mapped"))
            continue
        problem = None
        for source, server, operation, tool in mappings:
            if server not in inventories:
                try:
                    inventories[server] = query(context.servers[server], timeout=timeout)
                except (OSError, ValueError, KeyError, TypeError, queue.Empty, subprocess.TimeoutExpired) as exc:
                    inventories[server] = str(exc) or type(exc).__name__
            tools = inventories[server]
            if isinstance(tools, str):
                problem = f"{source} / {operation}: {server} unreachable: {tools}"
            elif tool not in tools:
                problem = f"{source} / {operation}: missing tool {tool} on {server}"
            if problem:
                break
        rows.append((capability, "MISSING" if problem else "ok",
                     problem or f"{len(mappings)} mapped operation(s) answered tools/list"))
    return rows


def stdio_call(spec, tool, arguments, *, timeout=5):
    """One initialized read call; enforce a deadline and reap the child."""
    if not spec.get("command"):
        raise ContextError("local readiness requires a stdio source")
    process = subprocess.Popen([spec["command"], *spec.get("args", [])],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace", env={**os.environ, **spec.get("env", {})})
    messages = queue.Queue()
    def reader():
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)
    threading.Thread(target=reader, daemon=True).start()
    def request(method, params, id=None):
        frame = {"jsonrpc": "2.0", "method": method, "params": params}
        if id is not None:
            frame["id"] = id
        process.stdin.write(json.dumps(frame) + "\n")
        process.stdin.flush()
        if id is None:
            return None
        deadline = time.monotonic() + timeout
        while True:
            line = messages.get(timeout=max(0, deadline - time.monotonic()))
            if line is None:
                raise ContextError("local MCP server exited before answering")
            response = json.loads(line)
            if response.get("id") != id:
                continue
            if "error" in response:
                raise ContextError(str(response["error"]))
            return response["result"]
    try:
        request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "sky-readiness", "version": "1"}}, 1)
        request("notifications/initialized", {})
        result = request("tools/call", {"name": tool, "arguments": arguments}, 2)
        if result.get("isError"):
            raise ContextError(result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


class LocalKB(KB):
    def token(self):
        return ""  # A local stdio process has no network credential.


def local_kb(context):
    return LocalKB(name="local", purpose="project Markdown store", url=str(context.root / ".sky/kb"),
                   tenant=context.root.name, ontology="sky", privacy="personal", write=True)


class LocalMap:
    def catalogue(self):
        return None


def mcp_config(context, directory):
    path = Path(directory) / "mcp.json"
    path.write_text(json.dumps({"mcpServers": context.servers}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def deliver(context, pack, *, task_id, characters_before=0):
    from . import budget
    result = budget.deliver(context.root, pack, task_id=task_id, characters_before=characters_before)
    if not result["delivered"]:
        raise ContextError("; ".join(result["findings"]))
    return result


def call(context, source, operation, arguments, *, task_id, timeout=5):
    """Runtime-mediated calls are capped; direct host remote calls are not."""
    mapping = context.sources[source][operation]
    spec = context.servers[context.sources[source]["server"]]
    args = {**mapping.get("defaults", {}), **arguments}
    args = {mapping.get("arguments", {}).get(key, key): value for key, value in args.items()}
    if spec.get("command"):
        result = stdio_call(spec, mapping["tool"], args, timeout=timeout)
    else:
        from . import probes
        token = os.environ.get(spec.get("bearer_token_env_var", ""), "")
        response = probes._rpc(spec["url"], token, "tools/call", {"name": mapping["tool"], "arguments": args})
        if response.get("isError"):
            raise ContextError("context tool failed: " + mapping["tool"])
        result = json.loads(response["content"][0]["text"])
    return deliver(context, result, task_id=task_id)["pack"]

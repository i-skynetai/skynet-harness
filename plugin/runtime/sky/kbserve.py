"""SH-083 stdio MCP reference server; importable before CLI wiring lands.

Only stdout JSON-RPC frames are emitted. Writes need a runtime-provided stamp;
decision confirmation is provided out of band, never in a tool argument.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from .kbstore import Store, StoreError

MAX_FRAME = 2_000_000
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}


def _schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_TEXT = {"type": "string", "minLength": 1}
_K = {"type": "integer", "minimum": 1, "maximum": 100}
TOOLS = [
    {"name": "search", "description": "Rank bounded Markdown chunks by keyword overlap.",
     "inputSchema": _schema({"query": _TEXT, "k": _K, "types": {"type": "array", "items": _TEXT}}, ("query",)),
     "annotations": {"readOnlyHint": True}},
    {"name": "neighbours", "description": "Follow relates_to edges without inventing missing records.",
     "inputSchema": _schema({"id": _TEXT, "edge": {"const": "relates_to"},
                             "depth": {"type": "integer", "minimum": 1, "maximum": 5}, "type": _TEXT}, ("id",)),
     "annotations": {"readOnlyHint": True}},
    {"name": "decisions_find", "description": "Return ranked decision candidates and explicit applicability.",
     "inputSchema": _schema({"question": _TEXT, "k": _K, "project": _TEXT, "scope": _TEXT,
                             "evidence_revision": _TEXT}, ("question", "scope")),
     "annotations": {"readOnlyHint": True}},
    {"name": "decisions_record", "description": "Runtime write requiring out-of-band human confirmation.",
     "inputSchema": _schema({"metadata": {"type": "object"}, "body": _TEXT}, ("metadata", "body")),
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
    {"name": "ingest", "description": "Runtime validated local document write; never a remote publication.",
     "inputSchema": _schema({"metadata": {"type": "object"}, "body": _TEXT}, ("metadata", "body")),
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
]


def tokens(text):
    return set(re.findall(r"[\w]+", text.casefold()))


def _scope_applies(scopes, requested):
    requested = PurePosixPath(requested)
    if requested.is_absolute() or ".." in requested.parts or "\\" in str(requested):
        raise StoreError("decision scope must be repository-relative")
    return any(requested.is_relative_to(PurePosixPath(scope)) for scope in scopes)


class Server:
    def __init__(self, store: Store, *, stamp=None, confirm=None):
        self.store = store
        self.stamp = stamp
        self.confirm = confirm

    def search(self, query, k=10, types=None):
        words = tokens(query)
        hits = []
        for record in self.store.records():
            meta, body, entry = record["metadata"], record["body"], record["entry"]
            if types is not None and meta["type"] not in types:
                continue
            for chunk in entry["chunks"]:
                excerpt = body[chunk["offset"]:chunk["offset"] + chunk["chars"]]
                score = len(words & tokens(meta["title"] + " " + excerpt))
                if score:
                    hits.append({"id": meta["id"], "chunk_id": chunk["id"], "title": meta["title"],
                                 "score": score, "excerpt": excerpt,
                                 "source": meta.get("source", entry["path"]), "tenant": meta["project"],
                                 "citation": "id:" + meta["id"], "chars": len(excerpt)})
        return sorted(hits, key=lambda h: (-h["score"], h["id"], h["chunk_id"]))[:k]

    def neighbours(self, id, edge="relates_to", depth=1, type=None):
        records = {r["metadata"]["id"]: r["metadata"] for r in self.store.records()}
        if id not in records:
            raise StoreError(f"record not found: {id}")
        found, seen, frontier, findings = [], {id}, [id], []
        for _ in range(depth):
            next_frontier = []
            for parent in frontier:
                for target in records[parent]["relates_to"]:
                    if target not in records:
                        findings.append(f"{parent}: unresolved relates_to {target}")
                    elif target not in seen:
                        seen.add(target)
                        next_frontier.append(target)
                        if type is None or records[target]["type"] == type:
                            found.append({"id": target, "type": records[target]["type"], "edge": edge,
                                          "title": records[target]["title"]})
            frontier = next_frontier
        return {"hits": found, "findings": sorted(set(findings))}

    def decisions_find(self, question, project=None, scope=".", k=10, evidence_revision=None):
        from .decisions import find
        hits = find(self.store, question, project=project, scope=scope,
                    k=k, evidence_revision=evidence_revision)
        # Keep the original applicability field for existing protocol clients.
        for hit in hits:
            hit["applicable"] = hit["closes"]
        return hits

    def call(self, name, arguments):
        from .kbstore import validate_schema
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            raise StoreError(f"unknown tool: {name}")
        validate_schema(arguments, tool["inputSchema"], "arguments")
        if name in ("search", "neighbours", "decisions_find"):
            return getattr(self, name)(**arguments)
        if self.stamp is None:
            raise StoreError("write refused: runtime stamp is not configured")
        meta = arguments["metadata"]
        approval = None
        if name == "decisions_record":
            if meta.get("type") != "decision" or self.confirm is None:
                raise StoreError("decision write refused: runtime human confirmation required")
            approval = self.confirm(meta)
        elif meta.get("type") == "decision":
            raise StoreError("decisions must use decisions_record with runtime confirmation")
        entry = self.store.put(meta, arguments["body"], stamp=self.stamp, approval=approval)
        return {"id": entry["id"], "digest": entry["digest"]}

    def handle(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                    "error": {"code": -32600, "message": "invalid request"}}
        if "id" not in request:
            return None  # Notifications are never answered.
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method, params = request["method"], request.get("params", {})
        if not isinstance(params, dict):
            response["error"] = {"code": -32602, "message": "params must be an object"}
            return response
        if method == "initialize":
            protocol = params.get("protocolVersion")
            response["result"] = {"protocolVersion": protocol if protocol in PROTOCOLS else "2025-03-26",
                "capabilities": {"tools": {}}, "serverInfo": {"name": "sky-kb", "version": "1"}}
        elif method == "ping":
            response["result"] = {}
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                result = self.call(params.get("name"), params.get("arguments", {}))
                response["result"] = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False}
            except (StoreError, OSError, ValueError, KeyError, TypeError) as exc:
                response["result"] = {"content": [{"type": "text", "text": f"local store refused: {exc}"}], "isError": True}
        else:
            response["error"] = {"code": -32601, "message": "method not found"}
        return response


def serve(store, input_stream, output_stream, *, stamp=None, confirm=None):
    server = Server(store, stamp=stamp, confirm=confirm)
    while True:
        line = input_stream.readline(MAX_FRAME + 1)
        if not line:
            return
        if len(line) > MAX_FRAME:
            # Drain this oversized frame, not its tail as a second request.
            while line and not line.endswith("\n"):
                line = input_stream.readline(MAX_FRAME + 1)
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "frame exceeds cap"}}
        else:
            try:
                response = server.handle(json.loads(line))
            except ValueError:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()

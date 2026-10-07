"""SH-040 read-only code adapter. Configuration is routing, never authority.

Skygraph argument names are taken from its MCP surface, not inferred from
the protocol example. Index refresh deliberately has no mapping here.
"""
from __future__ import annotations

import queue
import subprocess

from .context_sources import ContextError, stdio_call
from .inventory import query_server

TOOLS = {"code.find": "find_symbols", "code.outline": "outline_file",
         "code.source": "read_source", "code.related": "related_symbols"}
ARGUMENTS = {"code.find": {"name": "query"},
             "code.outline": {"file": "filepath"},
             "code.source": {"qualified_name": "qualified_name"},
             "code.related": {"qualified_name": "qualified_name"}}


def skygraph_adapter(repo, *, server="code", branch="main"):
    """A sources.code entry; args map protocol names to server names."""
    if not isinstance(repo, str) or not repo.strip():
        raise ContextError("skygraph adapter requires a repository name")
    if not isinstance(branch, str) or not branch.strip():
        raise ContextError("skygraph adapter requires a branch name")
    return {"server": server, **{operation: {"tool": tool,
            "args": dict(ARGUMENTS[operation]),
            "defaults": {"repo": repo, "branch": branch}}
            for operation, tool in TOOLS.items()}}


class CodePort:
    def __init__(self, context, *, call=stdio_call, query=query_server, timeout=5):
        self.context, self.call, self.query, self.timeout = context, call, query, timeout

    def status(self):
        source = self.context.sources.get("code") if self.context else None
        if not source:
            return "absent", "no code capability mapped"
        try:
            available = self.query(self.context.servers[source["server"]], timeout=self.timeout)
            for operation in TOOLS:
                tool = source.get(operation, {}).get("tool")
                if not tool or tool not in available:
                    return "MISSING", f"{operation}: missing {tool or 'mapping'}"
        except (OSError, ValueError, KeyError, RuntimeError, queue.Empty, subprocess.TimeoutExpired) as exc:
            return "MISSING", f"code server unavailable: {exc}"
        return "ok", "four read operations available"

    def invoke(self, operation, **arguments):
        if operation not in TOOLS:
            raise ContextError(f"unsupported read operation: {operation}")
        source = self.context.sources.get("code") if self.context else None
        if not source or operation not in source:
            raise ContextError(f"absent code capability: {operation}")
        mapping = source[operation]
        names = mapping.get("args", ARGUMENTS[operation])
        unknown = set(arguments) - set(names)
        missing = set(ARGUMENTS[operation]) - set(arguments)
        if unknown or missing:
            raise ContextError(f"{operation}: invalid arguments; missing {sorted(missing)}, unknown {sorted(unknown)}")
        if any(not isinstance(v, str) or not v.strip() for v in arguments.values()):
            raise ContextError(f"{operation}: arguments must be nonempty strings")
        translated = dict(mapping.get("defaults", {}))
        translated.update({names[k]: v for k, v in arguments.items()})
        # Preserve source ranges, stale flags, ambiguity and errors from the server.
        return self.call(self.context.servers[source["server"]], mapping["tool"],
                         translated, timeout=self.timeout)

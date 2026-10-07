"""SH-031 managed MCP measurements, ready for subsequent hook wiring.

No response content or argument plaintext is retained. Input identity is a
canonical JSON SHA-256, not an assertion of document identity. The resolver is
shared with context readiness; managed projects need no SKY_LAUNCHED marker.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import project
from .context_sources import NotManaged, repository

COUNTING_METHOD = "unicode_codepoints_text_blocks_else_canonical_json"
MCP_MATCHER = "mcp__.*"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def measured_response(response):
    if response is None:
        return 0
    if isinstance(response, str):
        return len(response)
    blocks = response.get("content") if isinstance(response, dict) else response
    if isinstance(blocks, list) and all(isinstance(block, dict) and "type" in block for block in blocks):
        return sum(len(block["text"]) for block in blocks
                   if isinstance(block, dict) and block.get("type") == "text"
                   and isinstance(block.get("text"), str))
    return len(canonical(response))


def resolve_path(payload, *, cwd=None, env=None):
    env = os.environ if env is None else env
    try:
        root = repository(cwd or payload.get("cwd"))
    except NotManaged:
        return None
    config = project.validate_config(project.read_mapping(root / ".sky/project.yaml"), root)
    session = payload.get("session_id") or env.get("SKY_RUN_ID")
    if not isinstance(session, str) or not session:
        raise ValueError("managed MCP ledger requires session_id or SKY_RUN_ID")
    if env.get("SKY_RUN_DIR"):
        directory = Path(env["SKY_RUN_DIR"]).resolve()
        from .recorder import state_dir
        run_id = env.get("SKY_RUN_ID", "")
        standard = (state_dir() / "runs" / run_id).resolve()
        recorded_run = bool(run_id and Path(run_id).name == run_id and
                            directory == standard and (directory / "events.jsonl").is_file())
        if not directory.is_relative_to(root) and not recorded_run:
            raise ValueError("managed run directory must be inside repository")
    else:
        directory = project.contained(root, config["sessions_dir"]) / (
            "session-" + hashlib.sha256(session.encode("utf-8")).hexdigest()[:24])
    path = directory / "tools.jsonl"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("managed ledger path must be inside repository")
    return path


@contextmanager
def locked(path):
    for candidate in (path, path.with_suffix(".lock"), *path.parents):
        if candidate.is_symlink():
            raise ValueError("ledger refuses symbolic links")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read(path):
    if not Path(path).exists():
        return []
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"ledger line {number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"ledger line {number}: expected object")
        rows.append(row)
    return rows


def operation_for(tool, context):
    """Resolve protocol identity from configuration, never from guessed names."""
    parts = tool.split("__", 2)
    if len(parts) != 3 or context is None:
        return None
    matches = {operation for source in context.sources.values()
               if source.get("server") == parts[1]
               for operation, mapping in source.items()
               if operation != "server" and mapping.get("tool") == parts[2]}
    if len(matches) > 1:
        raise ValueError("ambiguous protocol operation for MCP ledger")
    return next(iter(matches), None)


def record(payload, *, cwd=None, env=None, operation=None, context=None):
    tool = payload.get("tool_name", "")
    if not isinstance(tool, str) or not tool.startswith("mcp__"):
        return None
    parts = tool.split("__", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise ValueError("invalid MCP tool name")
    path = resolve_path(payload, cwd=cwd, env=env)
    if path is None:
        return None
    if operation is None:
        operation = operation_for(tool, context)
    response = payload.get("tool_response")
    if response is None:
        response = payload.get("error")
    actual_env = os.environ if env is None else env
    session = payload.get("session_id") or actual_env.get("SKY_RUN_ID")
    row = {"tool": tool, "server": parts[1],
           "session_identity": hashlib.sha256(session.encode("utf-8")).hexdigest(),
           "input_identity": hashlib.sha256(canonical(payload.get("tool_input", {})).encode("utf-8")).hexdigest(),
           "response_chars": measured_response(response), "counting_method": COUNTING_METHOD,
           "failed": bool(payload.get("hook_event_name") == "PostToolUseFailure" or payload.get("error") or payload.get("is_error") or
                          isinstance(response, dict) and (response.get("isError") or response.get("error"))),
           "recorded_at": datetime.now(timezone.utc).isoformat()}
    if operation is not None:
        row["operation"] = operation
    for name in ("run_id", "agent_id"):
        value = actual_env.get("SKY_" + name.upper())
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            row[name] = value
    with locked(path):
        previous = read(path)
        sequences = [r.get("sequence", 0) for r in previous]
        if any(type(s) is not int or s < 0 for s in sequences):
            raise ValueError("ledger contains invalid sequence")
        row["sequence"] = max(sequences, default=0) + 1
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return path

"""Runtime correlation for the experimental Codex approval controller.

The launcher owns plan admission and lifecycle. Its dispatch adapter passes the
already-created run to the controller and records actual observations.
"""
from __future__ import annotations

import json
import time
import subprocess
from pathlib import Path

from . import ledger, recorder, hand


class Refused(ValueError):
    pass


def run_environment(run, env):
    """Reject a substituted identity before using the runtime's ledger path."""
    fields = {"run_id": "SKY_RUN_ID", "agent_id": "SKY_AGENT_ID",
              "role": "SKY_ROLE", "task": "SKY_TASK", "kb": "SKY_KB_NAME"}
    directory = Path(run.directory).resolve()
    if directory.name != run.run_id or env.get("SKY_LAUNCHED") != "1":
        raise Refused("Codex dispatch requires the canonical runtime run")
    if Path(env.get("SKY_RUN_DIR", "")).resolve() != directory or any(
            env.get(key) != getattr(run, field) for field, key in fields.items()):
        raise Refused("Codex dispatch environment differs from the runtime run")
    try:
        with (directory / "events.jsonl").open(encoding="utf-8") as stream:
            start = json.loads(stream.readline())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise Refused("Codex runtime run record is unavailable") from exc
    if not isinstance(start, dict) or start.get("kind") != "run.start" or any(
            start.get(field) != getattr(run, field) for field in fields if field != "run_id"):
        raise Refused("Codex runtime run record differs from dispatch")
    return dict(env)


def record_mcp(item, *, session_id, root, run_env, context=None):
    """Record only completed MCP observations, never approval proposals."""
    if item.get("type") != "mcpToolCall":
        return None
    status = item.get("status")
    if status not in {"completed", "failed"}:
        raise Refused("MCP observation has no terminal status")
    server, tool = item.get("server"), item.get("tool")
    if not all(isinstance(value, str) and value and "__" not in value
               for value in (server, tool)):
        raise Refused("MCP observation has an invalid tool identity")
    payload = {"tool_name": f"mcp__{server}__{tool}",
               "tool_input": item.get("arguments"),
               "tool_response": item.get("result"), "session_id": session_id,
               "hook_event_name": "PostToolUseFailure" if status == "failed" else "PostToolUse"}
    if status == "failed":
        payload.update(is_error=True, error=item.get("error"))
    return ledger.record(payload, cwd=root, env=run_env, context=context)


def execute(command, *, env, cwd, log_path, hard_cap=hand.HARD_CAP_SEC,
            silence_cap=hand.SILENCE_CAP_SEC, on_line=None):
    """Launcher dispatch adapter; lifecycle and admission remain with the caller.

    The command identifies the installed host binary only. The controller builds
    isolated configuration itself; legacy exec flags cannot widen permissions.
    """
    from . import codexcontroller, context_sources
    started = time.monotonic()
    log_path = Path(log_path)
    try:
        run = recorder.Run(run_id=env.get("SKY_RUN_ID", ""),
                           directory=Path(env.get("SKY_RUN_DIR", "")),
                           agent_id=env.get("SKY_AGENT_ID", ""),
                           role=env.get("SKY_ROLE", ""), task=env.get("SKY_TASK", ""),
                           kb=env.get("SKY_KB_NAME", ""))
        run_environment(run, env)
        if not command or not isinstance(command[0], str):
            raise Refused("Codex executable is missing")
        result = codexcontroller.run(cwd, run.role, run.task, codex=command[0],
                                     timeout=hard_cap, silence_cap=silence_cap,
                                     runtime_run=run, runtime_env=env,
                                     context_map=context_sources.load(cwd))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # A model summary is output, never a substitute for observed tool events.
        text = json.dumps({"type": "codex.controller.completed", **result}, ensure_ascii=False)
        log_path.write_text(text + "\n", encoding="utf-8")
        if on_line:
            on_line(text)
        return hand.Result(True, "finished", 0, log_path, time.monotonic() - started,
                           result.get("summary", ""))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        reason = "silent" if "silence cap" in str(exc) else "hard-cap" if "timed out" in str(exc) else "failed"
        return hand.Result(False, reason, None, log_path, time.monotonic() - started, str(exc))

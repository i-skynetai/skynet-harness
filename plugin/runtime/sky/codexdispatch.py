"""Native-plugin transport to the existing governed launcher, over local stdio."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

from . import context_sources, hand

TOOLS = [{"name": name, "description": description,
          "inputSchema": {"type": "object", "properties": {
              "task": {"type": "string", "minLength": 1, "maxLength": 8000},
              "root": {"type": "string", "description": "Absolute path of this session's managed repository."}},
              "required": ["task", "root"], "additionalProperties": False},
          "annotations": {"readOnlyHint": name == "review", "destructiveHint": name == "implement",
                          "openWorldHint": False, "idempotentHint": False}}
         for name, description in (("implement", "Implement the current admitted plan through the governed Codex developer."),
                                   ("review", "Inspect the current managed repository through the governed Codex reviewer."))]


def dispatch(name, arguments, *, cwd, disconnected=None, timeout=1800):
    if name not in {"implement", "review"}:
        raise ValueError("unknown dispatch tool")
    if (not isinstance(arguments, dict) or set(arguments) != {"task", "root"}
            or not isinstance(arguments["task"], str) or not 1 <= len(arguments["task"].strip()) <= 8000):
        raise ValueError("dispatch accepts only a bounded task")
    raw_root = arguments["root"]
    if not isinstance(raw_root, str) or not Path(raw_root).is_absolute() or raw_root.startswith("\\\\"):
        raise ValueError("dispatch requires a local absolute managed repository root")
    root = context_sources.repository(raw_root)
    if root != Path(raw_root).resolve():
        raise ValueError("dispatch root must name the canonical repository, not a subdirectory")
    env = {key: value for key, value in os.environ.items() if not key.startswith("SKY_")}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parent.parent), SKY_LAUNCHED="1", PYTHONUTF8="1")
    if os.environ.get("SKY_PLUGIN_ROOT"):
        env["SKY_PLUGIN_ROOT"] = os.environ["SKY_PLUGIN_ROOT"]
    command = [sys.executable, "-m", "sky", "build", "--hand", "codex", "--role",
               "developer" if name == "implement" else "reviewer", "--task", arguments["task"], "--json"]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        peer = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        try:
            while peer.poll() is None:
                if disconnected is not None and disconnected.is_set():
                    raise ValueError("dispatch client disconnected or cancelled")
                if time.monotonic() - started >= timeout:
                    raise ValueError("dispatch timed out")
                time.sleep(.05)
            output.seek(0)
            # Runtime output is bounded here; no model-supplied JSON is used as
            # a substitute for the CLI's final observed outcome.
            text = output.read(1024 * 1024)
            rows = []
            for line in text.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("sky") == "build":
                    rows.append(row)
            if not rows:
                raise ValueError("launcher returned no runtime outcome: " + text[-1000:])
            result = rows[-1]
            result["ok"] = bool(peer.returncode == 0 and result.get("ok"))
            return result
        finally:
            if peer.poll() is None:
                hand._stop(peer)
            peer.wait(timeout=10)


def serve(input_stream=sys.stdin, output_stream=sys.stdout, *, cwd=None):
    inbox = queue.Queue(maxsize=32)
    disconnected = threading.Event()
    def reader():
        try:
            while True:
                line = input_stream.readline(1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 1024 * 1024:
                    break
                request = json.loads(line)
                if isinstance(request, dict) and request.get("method") == "notifications/cancelled":
                    disconnected.set()
                inbox.put(request)
        except (OSError, ValueError):
            pass
        finally:
            disconnected.set()
            inbox.put(None)
    threading.Thread(target=reader, daemon=True).start()
    while True:
        request = inbox.get()
        if request is None:
            return
        if not isinstance(request, dict) or "id" not in request:
            continue
        response = {"jsonrpc": "2.0", "id": request["id"]}
        try:
            if request.get("jsonrpc") != "2.0":
                raise ValueError("invalid JSON-RPC request")
            method, params = request.get("method"), request.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("invalid parameters")
            if method == "initialize":
                response["result"] = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "sky-dispatch", "version": "1"}}
            elif method == "ping":
                response["result"] = {}
            elif method == "tools/list":
                response["result"] = {"tools": TOOLS}
            elif method == "tools/call":
                result = dispatch(params.get("name"), params.get("arguments", {}),
                                  cwd=cwd or Path.cwd(), disconnected=disconnected)
                response["result"] = {"content": [{"type": "text", "text": json.dumps(result)}],
                                      "isError": not result.get("ok")}
            else:
                raise ValueError("unsupported method")
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            response["result"] = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        output_stream.write(json.dumps(response) + "\n")
        output_stream.flush()

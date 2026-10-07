"""Best-effort freshness hooks: edits enqueue; Stop reconciles checkout digests."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import freshness, ledger
from .context_sources import repository


def handle(action, payload):
    """Never block the host. Record failure without retaining tool input plaintext."""
    if action == "enqueue" and payload.get("tool_name") not in {"Edit", "Write", "MultiEdit"}:
        return
    path = None
    failed = False
    try:
        root = repository(payload.get("cwd"))
        path = ledger.resolve_path(payload, cwd=root)
        if action == "enqueue":
            value = payload.get("tool_input", {}).get("file_path")
            if not isinstance(value, str):
                raise ValueError("edit hook has no file_path")
            candidate = Path(value)
            candidate = candidate if candidate.is_absolute() else root / candidate
            relative = candidate.absolute().relative_to(root.resolve()).as_posix()
            freshness.enqueue(root, [relative])
        elif action == "stop":
            freshness.refresh(root)
        else:
            raise ValueError("unknown refresh hook")
    except Exception:
        failed = True
    finally:
        if path is not None:
            try:
                with ledger.locked(path):
                    rows = ledger.read(path)
                    row = {"tool": payload.get("tool_name", "Stop"),
                           "hook": "refresh." + action,
                           "sequence": max((r.get("sequence", 0) for r in rows), default=0) + 1,
                           "input_identity": hashlib.sha256(ledger.canonical(payload.get("tool_input", {})).encode()).hexdigest(),
                           "failed": failed, "recorded_at": datetime.now(timezone.utc).isoformat()}
                    with path.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(json.dumps(row, sort_keys=True) + "\n")
            except Exception:
                pass


def command(args):
    import sys
    try:
        handle(args.refresh_action, json.loads(sys.stdin.read() or "{}"))
    except Exception:
        pass
    return 0

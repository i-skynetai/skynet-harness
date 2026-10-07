"""Context adapter import and ledger-derived manifest CLI, standard library only."""
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import context_sources, context_measurements, project, recorder, schemas, yamlish
from .codeport import skygraph_adapter
from .kbstore import Store
from .policy import PolicyError


def write_code_adapter(root, path, server, *, repo=None, branch="main"):
    try:
        incoming = json.loads(Path(path).read_text(encoding="utf-8"))
        spec = incoming.get("mcpServers", {}).get(server)
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError(f"cannot read MCP configuration: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError(f"unknown MCP server: {server}")
    if not isinstance(spec.get("command"), str) or not spec["command"].strip():
        raise ValueError(f"MCP server {server}: a stdio command is required")
    copied = {key: copy.deepcopy(spec[key]) for key in ("command", "args", "env") if key in spec}
    if copied.get("env") == {}:
        copied.pop("env")  # Omission is equivalent; portable YAML has no empty-map syntax.
    root = Path(root).resolve()
    store = Store(root)
    with store.locked():
        context = context_sources.load(root=root)
        body = copy.deepcopy(context.body)
        body.setdefault("servers", {})["code"] = copied
        body.setdefault("sources", {})["code"] = skygraph_adapter(repo or root.name, branch=branch)
        text = "\n".join(context_sources._yaml(body)) + "\n"
        if yamlish.parse(text) != body:
            raise ValueError("MCP configuration cannot be preserved by the portable YAML reader")
        # Validate the candidate before replacing existing configuration.
        if not isinstance(copied.get("args", []), list) or any(not isinstance(v, str) for v in copied.get("args", [])):
            raise ValueError("MCP args must be strings")
        if not isinstance(copied.get("env", {}), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in copied.get("env", {}).items()):
            raise ValueError("MCP env must map strings to strings")
        target = store.safe_path(".sky/context.yaml")
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            store._atomic(target, text)
    return target


def manifest(root, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("run id must be an identifier, not a path")
    root = Path(root).resolve()
    config = project.validate_config(project.read_mapping(root / ".sky/project.yaml"), root)
    sessions = project.contained(root, config["sessions_dir"])
    candidates = [recorder.state_dir() / "runs" / run_id / "tools.jsonl",
                  sessions / run_id / "tools.jsonl",
                  sessions / ("session-" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:24]) / "tools.jsonl"]
    matches = [p for p in candidates if p.is_file()]
    if len(matches) != 1:
        raise ValueError("run ledger absent or ambiguous: " + run_id)
    measured = context_measurements.build(matches[0])
    context = context_sources.load(root=root)
    configured = {source["server"] for source in context.sources.values()}
    for item in measured["items"]:
        if item["source"] not in configured:
            measured["findings"].append(f"sequence {item['sequence']}: absent source {item['source']}")
    if not measured["items"]:
        measured["findings"].append("no measured MCP retrievals")
    result = {"context_id": "ctx-" + run_id, "run_id": run_id, "items": [],
              "assembled_at": datetime.now(timezone.utc).isoformat(),
              "retrievals": measured["items"],
              **{key: measured[key] for key in ("measured_characters", "counting_method", "findings")}}
    schemas.check(schemas.CONTEXT_MANIFEST, result)
    return result


def execute(args):
    try:
        root = context_sources.repository()
        if args.context_action == "adapter":
            if args.context_value != "code" or not args.from_mcp_json or not args.server:
                raise ValueError("context adapter code requires --from-mcp-json and --server")
            path = write_code_adapter(root, args.from_mcp_json, args.server, repo=args.repo, branch=args.branch)
            print(f"code adapter written: {path}")
        else:
            result = manifest(root, args.context_value)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"context manifest {result['run_id']}: {len(result['retrievals'])} retrieval(s), {result['measured_characters']} characters")
                print("counting method: " + result["counting_method"])
                for finding in result["findings"]:
                    print("finding: " + finding)
        return 0
    except (OSError, ValueError, PolicyError, schemas.Invalid) as exc:
        print(f"sky context: {exc}", file=sys.stderr)
        return 1

"""Human-only remote handover delivery; credentials stay in runtime config."""
import json
import os
import sys
from pathlib import Path

from . import context_sources, ingest, probes, project, recorder, schemas
from .kbmap import CONFIG_DIR, MAP_FILE, KBMap, KBMapError, NoKBForPath
from .kbstore import Store, StoreError, document_text
from .policy import PolicyError


def remote(root, *, kb_map=None):
    """Prefer a configured remote ingest adapter; otherwise resolve the KB map."""
    config_path = Path(root) / ".sky/project.yaml"
    config = project.validate_config(project.read_mapping(config_path), root) if config_path.exists() else {}
    context = context_sources.load(root=root)
    if context:
        candidates = []
        for name, source in context.sources.items():
            if name != "local" and "ingest.document" in source and (not config.get("kb") or config["kb"] == name):
                mapping = source["ingest.document"]
                tenant = mapping.get("defaults", {}).get("tenant_code", root.name)
                candidates.append(({"name": name, "tenant": tenant}, ("adapter", context, name)))
        if len(candidates) > 1:
            raise StoreError("ambiguous remote ingest sources: " + ", ".join(item[0]["name"] for item in candidates))
        if candidates:
            return candidates[0]
    path = Path(kb_map) if kb_map else CONFIG_DIR / MAP_FILE
    if not path.exists() and not config.get("kb"):
        return None, None
    kbmap = KBMap.load(path)
    try:
        kb = kbmap.resolve(root, override=config.get("kb"))
    except NoKBForPath:
        # Refuse configured/privacy-bound projects; absence in a local project
        # must not silently select another tenant.
        if config.get("kb") or kbmap.owner_of(root):
            raise
        return None, None
    if not kb.write:
        return None, None
    return {"name": kb.name, "tenant": kb.tenant}, ("kb", kb)


def seal_handover(store, entry, run):
    engine, _ = remote(store.root)
    if engine is None:
        return None
    path = ingest.seal(store.root, entry["path"], engine=engine, stamp=run.stamp(), run=run)
    print("handover retained locally; run: " + ingest.render(store.root, path.relative_to(store.root).as_posix())["command"])
    return path


def transport(root, *, kb_map=None):
    def send(engine, payload):
        configured, handle = remote(root, kb_map=kb_map)
        if configured != engine or handle is None:
            raise StoreError("sealed engine differs from configured remote engine")
        if handle[0] == "adapter":
            _, context, name = handle
            source = context.sources[name]
            mapping = source["ingest.document"]
            spec = context.servers[source["server"]]
            args = {**mapping.get("defaults", {}), "metadata": payload["metadata"], "body": payload["body"]}
            args = {mapping.get("arguments", {}).get(key, key): value for key, value in args.items()}
            if spec.get("command"):
                result = context_sources.stdio_call(spec, mapping["tool"], args)
            else:
                response = probes._rpc(spec["url"], os.environ.get(spec.get("bearer_token_env_var", ""), ""),
                    "tools/call", {"name": mapping["tool"], "arguments": args})
                if response.get("isError"):
                    raise StoreError("remote ingest server refused payload")
                result = json.loads(response["content"][0]["text"])
            # An adapter must explicitly acknowledge the write, not merely
            # answer HTTP 200. Async job acceptance is recorded separately.
            return result
        kb = handle[1]
        response = probes._rpc(kb.url, kb.token(), "tools/call", {
            "name": probes.kb_tool("documents_ingest"), "arguments": {
                "tenant_code": kb.tenant, "text": document_text(payload["metadata"], payload["body"]),
                "filename": Path(payload["source"]).name,
                "ontology": kb.ontology, "layer": "project"}})
        if response.get("isError"):
            raise StoreError("remote ingest server refused payload")
        job = probes._job_id(response)
        if not job:
            raise StoreError("remote ingest returned no acknowledged job id")
        return {"ok": True, "job_id": job, "status": "accepted; extraction not yet verified"}
    return send


def execute(args):
    run = None
    try:
        root = context_sources.repository()
        run = recorder.Run.start(role="runtime", task="sky ingest", kb="remote", agent_id="runtime")
        def confirm(request):
            print(f"source: {request['source']}\nstamp: {json.dumps(request['stamp'])}\npayload digest: {request['payload_digest']}")
            print("engine: " + json.dumps(request["engine"]))
            return input("Confirm this sealed remote ingest? [y/N] ").strip().lower() == "y"
        result = ingest.ingest(root, args.file, confirm=confirm,
                               transport=transport(root, kb_map=args.kb_map), run=run)
        run.finish("completed")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, PolicyError, KBMapError, schemas.Invalid, EOFError) as exc:
        if run:
            run.finish("refused")
        print(f"sky ingest: {exc}", file=sys.stderr)
        return 1


def pending(root):
    store = Store(root)
    directory = store.safe_path(".sky/outbox")
    paths = []
    for path in sorted(directory.glob("ingest-*.json")) if directory.exists() else ():
        try:
            value = json.loads(store.safe_path(path.relative_to(store.root).as_posix()).read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("executed") is True:
                continue
        except (OSError, ValueError):
            pass  # The renderer reports the malformed pending record.
        paths.append(path)
    return paths

"""Digest reconciliation and a locked, snapshot-preserving refresh queue.

Hooks are conveniences. Reconciliation also detects HEAD and cited-file changes
when edits arrived through Bash, another session, or an interrupted hook.
"""
from __future__ import annotations

import copy
import json
import queue
import subprocess
from datetime import datetime, timezone

from . import context_sources, discovery, recorder, redaction
from .kbstore import (KNOWLEDGE_SCHEMA, STAMP_FIELDS, Store, StoreError, canonical,
                      chunks, digest, document_text, validate_schema)

PENDING = ".sky/kb/pending-reindex.json"
STATE = ".sky/kb/freshness.json"


def read_json(store, relative, default):
    path = store.safe_path(relative)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else copy.deepcopy(default)


def file_digest(store, relative):
    path = store.safe_path(relative)
    if not path.exists():
        return "deleted"
    import hashlib
    with path.open("rb") as stream:
        value = hashlib.sha256()
        carry = b""
        for block in iter(lambda: stream.read(65536), b""):
            block = carry + block
            carry = b"\r" if block.endswith(b"\r") else b""
            if carry:
                block = block[:-1]
            value.update(block.replace(b"\r\n", b"\n"))
        value.update(carry)
    return value.hexdigest()


def enqueue(root, paths):
    """Edit/Write hooks can call this without a network operation."""
    store = Store(root)
    with store.locked():
        pending = read_json(store, PENDING, {})
        for relative in paths:
            pending[relative] = file_digest(store, relative)
        store._atomic(store.safe_path(PENDING), json.dumps(pending, sort_keys=True, indent=2) + "\n")
    return pending


def mapping(context):
    if context:
        for source in context.sources.values():
            if "index.refresh" in source:
                return context.servers[source["server"]], source["index.refresh"]
    return None


def fingerprint(store, revision, records, paths, refresh_mapping):
    files = sorted(set(paths) | {citation.rsplit(":", 1)[0] for record in records
                               for citation in record["metadata"]["citations"]})
    return digest(canonical({"head": revision, "files": {path: file_digest(store, path) for path in files},
        "records": {record["metadata"]["id"]: record["entry"]["digest"] for record in records},
        "mapping": refresh_mapping}))


def write_records(store, manifest, records):
    """Commit stale historical evidence even if its cited source was deleted."""
    prepared = []
    for record in records:
        metadata = record["metadata"]
        validate_schema(metadata, KNOWLEDGE_SCHEMA)
        text = document_text(metadata, record["body"])
        if redaction.find(text):
            raise StoreError("redaction gate refused refreshed record")
        prepared.append((record, text))
    for record, text in prepared:
        meta = record["metadata"]
        revision = digest(text)
        path = store.safe_path(f".sky/kb/documents/{meta['id']}/{revision}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        store._atomic(path, text)
        entry = {**record["entry"], "digest": revision, "path": path.relative_to(store.root).as_posix(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "chunks": [{"id": part["id"], "offset": part["offset"], "chars": len(part["text"])}
                       for part in chunks(meta["id"], record["body"], store.chunk_chars)]}
        manifest["documents"][meta["id"]] = entry
    if records:
        manifest["generation"] += 1
        store._atomic(store.safe_path(".sky/kb/manifest.json"), json.dumps(manifest, sort_keys=True, indent=2) + "\n")


def refresh(root, paths=None, call=None, *, context=None, run=None):
    store = Store(root)
    revision = discovery.checkout(store.root)
    context = context if context is not None else context_sources.load(root=root)
    refresh_mapping = mapping(context)
    requested = list(paths or [])
    for path in requested:
        store.safe_path(path)
    with store.locked():
        pending = read_json(store, PENDING, {})
        snapshot = {path: value for path, value in pending.items()}
        requested = sorted(set(requested) | set(snapshot))
        records = discovery.list_knowledge(store)
        signature = fingerprint(store, revision, records, requested, refresh_mapping)
        state = read_json(store, STATE, {})
        if not snapshot and state.get("fingerprint") == signature:
            return {"checked": 0, "stale": 0, "refreshed": 0, "failed": 0,
                    "failures": [], "short_circuit": True}
    own_run = run is None
    if own_run:
        run = recorder.Run.start(role="runtime", task="sky kb refresh", kb="local",
                                 agent_id="runtime", root=store.safe_path(".sky/runs"))
    result = {"checked": len(records), "stale": 0, "refreshed": 0, "failed": 0,
              "failures": [], "short_circuit": False, "run": run.run_id}
    changed = set(requested)
    for record in records:
        meta, provenance = record["metadata"], record["entry"]
        cited = {citation.rsplit(":", 1)[0] for citation in meta["citations"]}
        if paths is None:
            pinned = provenance.get("checkout_revision")
            if pinned:
                try:
                    changed.update(discovery.git(store.root, "diff", "--name-only", pinned + ".." + revision, "--").splitlines())
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    result["failures"].append("cannot compare pinned checkout: " + type(exc).__name__)
                    changed.update(cited)
            else:
                changed.update(cited)  # Missing provenance cannot prove currency.
            for path in cited:
                previous = provenance.get("citation_digests", {}).get(path)
                if previous is None or previous != file_digest(store, path):
                    changed.add(path)
    refreshed_digest = None
    should_refresh = bool(changed or snapshot or revision != state.get("checkout_revision"))
    if refresh_mapping and should_refresh:
        spec, adapter = refresh_mapping
        try:
            if not spec.get("command"):
                raise StoreError("remote index refresh requires an intent")
            args = dict(adapter.get("defaults", {}))
            if "paths" in adapter.get("args", {}):
                args[adapter["args"]["paths"]] = sorted(changed)
            response = (call or context_sources.stdio_call)(spec, adapter["tool"], args, timeout=10)
            if not isinstance(response, dict) or response.get("isError") or response.get("error"):
                raise StoreError("index refresh reported failure")
            identity_map = response
            if not any(response.get(key) is not None for key in ("index_digest", "digest", "version")):
                defaults = context.sources.get("code", {}).get("code.find", {}).get("defaults", {})
                repo = defaults.get("repo", args.get("repo"))
                if not repo:
                    raise StoreError("index returned no identity or module-map repository")
                identity_map = (call or context_sources.stdio_call)(spec, "map_coverage",
                    {"repo": repo, "branch": defaults.get("branch", "main")}, timeout=10)
                if not isinstance(identity_map, dict) or not isinstance(identity_map.get("children"), list):
                    raise StoreError("invalid refreshed module map")
            refreshed_digest, _ = discovery.index_identity(response, mapping=identity_map)
            result["refreshed"] = 1
        except (OSError, ValueError, RuntimeError, queue.Empty, subprocess.SubprocessError) as exc:
            result["failures"].append("index refresh failed: " + type(exc).__name__)
    if discovery.checkout(store.root) != revision:
        result["failures"].append("checkout changed during refresh; reconcile again")
    with store.locked():
        # Re-read after the network operation: another writer's records/edits
        # must survive. Queue items are removed only if their digest still matches.
        manifest = store.manifest()
        updates = []
        current_records = discovery.list_knowledge(store)
        concurrent = {record["metadata"]["id"]: record["entry"]["digest"] for record in records} != {
            record["metadata"]["id"]: record["entry"]["digest"] for record in current_records}
        for record in current_records:
            meta = record["metadata"]
            cited = {citation.rsplit(":", 1)[0] for citation in meta["citations"]}
            if not cited & changed:
                continue
            update = copy.deepcopy(record)
            changed_record = not meta["stale"]
            if changed_record:
                result["stale"] += 1
                update["metadata"]["stale"] = True
            if refreshed_digest and meta["index_digest"] != refreshed_digest:
                update["metadata"]["index_digest"] = refreshed_digest
                changed_record = True
            if changed_record:
                update["metadata"].update(run.stamp())
                updates.append(update)
        write_records(store, manifest, updates)
        current_pending = read_json(store, PENDING, {})
        if not result["failures"] and (not refresh_mapping or result["refreshed"]):
            for path, value in snapshot.items():
                if current_pending.get(path) == value and file_digest(store, path) == value:
                    current_pending.pop(path, None)
            if snapshot:
                store._atomic(store.safe_path(PENDING), json.dumps(current_pending, sort_keys=True, indent=2) + "\n")
        result["failed"] = len(result["failures"])
        if not result["failed"] and not concurrent:
            final_signature = fingerprint(store, revision, discovery.list_knowledge(store), requested, refresh_mapping)
            store._atomic(store.safe_path(STATE), json.dumps({"fingerprint": final_signature,
                "checkout_revision": revision}, sort_keys=True, indent=2) + "\n")
    if result["failed"]:
        run.refused("; ".join(result["failures"]), operation="kb.refresh")
    if own_run:
        run.finish("refreshed" if not result["failed"] else "failed", **result)
    return result

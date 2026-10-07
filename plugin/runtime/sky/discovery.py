"""Bounded index worklists and cited observations; never inferred decisions.

Knowledge's existing schema uses 64-character digests. checkout_digest is
SHA-256 of the native HEAD revision; checkout_revision retains that revision.
index_digest is SHA-256 of a provider version (a provider SHA-256 is retained),
or of the canonical module map when the provider exposes no identity.
"""
from __future__ import annotations

import copy
import json
import os
import math
import re
import subprocess
import unicodedata
from datetime import datetime, timezone

from . import context_sources, redaction
from .kbstore import (MAX_DOCUMENT_CHARS, STAMP_FIELDS, Store, StoreError,
                      canonical, digest, parse_document)

NO_INDEX = "no code index — discovery needs one (sky context adapter code ...)"
OWNED = set(STAMP_FIELDS) | {"approval", "recorded_at", "run_identity", "decided_by", "stale"}


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=10)
    if result.returncode:
        raise StoreError("git could not verify checkout")
    return result.stdout or ""


def checkout(root):
    revision = git(root, "rev-parse", "HEAD").strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", revision):
        raise StoreError("verified checkout required")
    return revision


def index_identity(*responses, mapping):
    for response in responses:
        for key in ("index_digest", "digest", "version"):
            value = response.get(key) if isinstance(response, dict) else None
            if value is not None and str(value):
                text = str(value)
                return (text if re.fullmatch(r"[a-f0-9]{64}", text) else digest(text)), "provider:" + key
    return digest(canonical(mapping)), "module_map"


def code_source(root, context=None):
    context = context if context is not None else context_sources.load(root=root)
    source = context.sources.get("code") if context else None
    if not source:
        raise StoreError(NO_INDEX)
    return context, source


def worklist(root, *, run, context=None, call=None, budget=12000, max_modules=50):
    store = Store(root)
    if type(budget) is not int or budget < 256 or type(max_modules) is not int or max_modules < 1:
        raise StoreError("positive worklist limits required; budget at least 256 characters")
    context, source = code_source(root, context)
    call = call or context_sources.stdio_call
    defaults = source.get("code.find", {}).get("defaults", {})
    args = {"repo": defaults.get("repo", store.root.name), "branch": defaults.get("branch", "main")}
    spec = context.servers[source["server"]]
    repos = call(spec, "list_repos", {}, timeout=5)
    if not isinstance(repos, dict) or not isinstance(repos.get("repos"), list) or not any(
            row.get("repo") == args["repo"] and row.get("branch", "main") == args["branch"]
            for row in repos["repos"] if isinstance(row, dict)):
        raise StoreError("repository is not indexed")
    summary = call(spec, "repo_summary", args, timeout=5)
    mapping = call(spec, "map_coverage", args, timeout=5)
    if not isinstance(mapping, dict) or not isinstance(mapping.get("children"), list):
        raise StoreError("invalid module map")
    revision = checkout(store.root)
    index_digest, identity_source = index_identity(summary, mapping, mapping=mapping)
    rows = []
    for row in mapping["children"]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise StoreError("invalid module row")
        store.safe_path(row["name"])
        size = row.get("files")
        if type(size) is not int or size < 0:
            raise StoreError("invalid module size")
        centrality = row.get("centrality")
        if centrality is not None and (type(centrality) not in (int, float) or not math.isfinite(centrality) or centrality < 0):
            raise StoreError("invalid module centrality")
        rows.append({"module": row["name"], "size": size, "centrality": centrality})
    rows.sort(key=lambda row: (-row["size"], -(row["centrality"] or 0), row["module"]))
    modules = []
    for row in rows[:max_modules]:
        entry = {**row, "files": [], "symbols": [], "budget": budget, "partial": False}
        found = call(spec, "list_files", {**args, "prefix": row["module"], "limit": 100}, timeout=5)
        if not isinstance(found, dict) or not isinstance(found.get("files"), list):
            raise StoreError("invalid indexed file list")
        for file in found["files"]:
            path = file.get("path") if isinstance(file, dict) else file
            store.safe_path(path)
            if not (path == row["module"] or path.startswith(row["module"].rstrip("/") + "/")):
                continue
            trial = {**entry, "files": entry["files"] + [path]}
            if len(canonical(trial)) > budget:
                entry["partial"] = True
                break
            entry["files"].append(path)
        entry["partial"] |= bool(found.get("note")) or len(entry["files"]) < row["size"]
        for path in entry["files"]:
            if len(canonical(entry)) >= budget - 128:
                entry["partial"] = True
                break
            outlined = call(spec, "outline_file", {**args, "filepath": path}, timeout=5)
            if isinstance(outlined, dict) and "signatures" not in outlined and isinstance(outlined.get("error"), str):
                # The index answers "not indexed, or more than one file ends with that
                # path" as an error object, not as an empty list: a fact about the
                # index, not a broken server. The module is partial; the file is named.
                entry["partial"] = True
                entry.setdefault("unoutlined", []).append(path)
                continue
            if not isinstance(outlined, dict) or not isinstance(outlined.get("signatures"), list):
                raise StoreError("invalid file outline")
            for symbol in outlined["signatures"]:
                trial = {**entry, "symbols": entry["symbols"] + [{"file": path, **symbol}]}
                if len(canonical(trial)) > budget:
                    entry["partial"] = True
                    break
                entry["symbols"].append({"file": path, **symbol})
        entry["characters"] = 0
        while True:
            entry["characters"] = len(canonical(entry))
            measured = len(canonical(entry))
            if measured <= budget and entry["characters"] == measured:
                break
            if measured <= budget:
                continue
            entry["partial"] = True
            if entry["symbols"]:
                entry["symbols"].pop()
            elif entry["files"]:
                entry["files"].pop()
            else:
                raise StoreError("module identity exceeds character budget")
        modules.append(entry)
    if checkout(store.root) != revision:
        raise StoreError("checkout changed during discovery")
    result = {"schema_version": 1, "project": store.root.name, "run": run.run_id,
              "checkout_revision": revision, "checkout_digest": digest(revision),
              "checkout_method": "sha256-of-native-HEAD", "index_digest": index_digest,
              "index_identity_source": identity_source, "modules": modules,
              "unvisited": [row["module"] for row in rows[max_modules:]],
              "created_at": datetime.now(timezone.utc).isoformat()}
    text = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    if redaction.find(text):
        raise StoreError("redaction gate refused worklist")
    # The run directory is the runtime's, wherever the host keeps runs (under the
    # project in tests, under the user's state directory in real sessions), so the
    # store's repository containment does not apply to this artefact.
    path = run.directory / "discovery-worklist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(text.encode("utf-8"))
    os.replace(temporary, path)
    return result


def normalise(statement):
    return " ".join(unicodedata.normalize("NFKC", statement).casefold().split())


def verify_citations(store, citations, revision):
    if not citations or any(not isinstance(value, str) or value.startswith("id:") for value in citations):
        raise StoreError("knowledge requires resolving code file:line citations")
    store._citations({"citations": citations})
    for citation in citations:
        relative, number = citation.rsplit(":", 1)
        pinned = git(store.root, "show", revision + ":" + relative)
        current = store.safe_path(relative).read_text(encoding="utf-8")
        if pinned.splitlines() != current.splitlines() or int(number) > len(pinned.splitlines()):
            raise StoreError("citation does not match pinned checkout: " + citation)


def put(store, metadata, body, *, run, work=None):
    if not isinstance(metadata, dict) or OWNED & metadata.keys():
        raise StoreError("model supplied runtime-owned knowledge field")
    if metadata.get("type", "knowledge") != "knowledge":
        raise StoreError("observation must be knowledge, never a decision")
    record = copy.deepcopy(metadata)
    statement = record.pop("statement", body.strip())
    if not isinstance(statement, str) or not statement.strip() or len(statement) > MAX_DOCUMENT_CHARS:
        raise StoreError("observation statement required within size cap")
    module = record.get("module")
    store.safe_path(module)
    revision = checkout(store.root)
    if work is not None:
        if work.get("project") != store.root.name or revision != work.get("checkout_revision"):
            raise StoreError("discovery worklist checkout is stale or belongs to another project")
        if module not in {item["module"] for item in work["modules"]}:
            raise StoreError("module is not in discovery worklist: " + module)
        index_digest = work["index_digest"]
    else:
        index_digest = digest("no code index: hand-authored observation")
    verify_citations(store, record.get("citations", []), revision)
    for field, value in (("checkout_digest", digest(revision)), ("index_digest", index_digest)):
        if field in record and record[field] != value:
            raise StoreError("observation " + field + " differs from runtime evidence")
        record[field] = value
    record.update(type="knowledge", stale=False)
    record.setdefault("project", store.root.name)
    if record["project"] != store.root.name:
        raise StoreError("observation belongs to another project")
    record.setdefault("scope", [module])
    record.setdefault("title", statement[:160])
    record.setdefault("id", "knowledge-" + digest(record["project"] + "\0" + module + "\0" + normalise(statement))[:24])
    from .kbstore import KNOWLEDGE_SCHEMA, validate_schema
    checked = copy.deepcopy(record)
    checked.setdefault("schema_version", 1)
    checked.setdefault("relates_to", [])
    checked.update(run.stamp())
    validate_schema(checked, KNOWLEDGE_SCHEMA)
    # Reuse legacy ids; current duplicates are decided under Store's lock.
    for previous in list_knowledge(store, module=module):
        if normalise(previous["body"]) == normalise(statement):
            record["id"] = previous["metadata"]["id"]
            break
    if checkout(store.root) != revision:
        raise StoreError("checkout changed while validating observation")
    if record["id"] in store.manifest()["documents"]:
        existing = store.get(record["id"])["metadata"]
        if existing.get("type") != "knowledge" or existing["project"] != record["project"]:
            raise StoreError("knowledge id belongs to another record type or project")
    def provenance():
        if checkout(store.root) != revision:
            raise StoreError("checkout changed while validating observation")
        verify_citations(store, record["citations"], revision)
        return {"checkout_revision": revision, "checkout_method": "sha256-of-native-HEAD",
                "citation_digests": {citation.rsplit(":", 1)[0]: digest(git(store.root, "show",
                    revision + ":" + citation.rsplit(":", 1)[0]).replace("\r\n", "\n"))
                    for citation in record["citations"]}}
    entry = store.put(record, statement, stamp=run.stamp(), run=run, provenance=provenance)
    if entry.get("unchanged"):
        return entry
    run.event("kb.put", document_id=entry["id"], digest=entry["digest"], type="knowledge")
    return {**entry, "unchanged": False}


def put_text(store, text, *, run, work=None):
    metadata, body = parse_document(text)
    return put(store, metadata, body, run=run, work=work)


def show(store, record_id):
    record = store.get(record_id)
    if record["metadata"].get("type") != "knowledge":
        raise StoreError("record is not knowledge")
    return record


def list_knowledge(store, *, module=None, category=None, stale=None):
    return [record for record in store.records() if record["metadata"].get("type") == "knowledge"
            and (module is None or record["metadata"]["module"] == module)
            and (category is None or record["metadata"]["category"] == category)
            and (stale is None or record["metadata"]["stale"] is stale)]

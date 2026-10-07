"""SH-087 decision lifecycle and runtime-confirmed immutable revisions.

Uses the local store's immutable revisions and one locked manifest commit.
Approval is runtime evidence under one OS user, not a tamper-proof signature.
"""
from __future__ import annotations

import copy
import getpass
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from . import redaction
from .kbstore import (Approval, DECISION_SCHEMA, MAX_DOCUMENT_CHARS, STAMP_FIELDS, Store,
                      StoreError, chunks, digest, document_text, parse_document,
                      validate_schema)

EVENT_KINDS = {action: "decision." + status for action, status in
               (("propose", "proposed"), ("accept", "accepted"),
                ("reject", "rejected"), ("supersede", "superseded"))}
RUNTIME_FIELDS = {"approval", "recorded_at", "run_identity", "decided_by"}
SCHEMA = DECISION_SCHEMA


def _validate(store, metadata, body):
    # The same defaults Store.put gives every record: an absent list is empty,
    # not an error, so a decision written out of band is judged on its content.
    for key in ("relates_to", "aliases", "supersedes", "superseded_by"):
        metadata.setdefault(key, [])
    metadata.setdefault("schema_version", 1)
    validate_schema(metadata, SCHEMA)
    if metadata["chosen_option"] not in metadata["options"]:
        raise StoreError("chosen_option must be one of options")
    if metadata["answer"] != metadata["chosen_option"]:
        raise StoreError("answer and chosen_option differ")
    if metadata["status"] == "proposed":
        if RUNTIME_FIELDS & metadata.keys():
            raise StoreError("proposed decision cannot have approval evidence")
    elif not RUNTIME_FIELDS <= metadata.keys():
        raise StoreError("decision requires runtime approval evidence")
    if not isinstance(body, str) or not body.strip() or len(body) > MAX_DOCUMENT_CHARS:
        raise StoreError("nonempty body within size cap required")
    for path in metadata["scope"] + ([metadata["source"]] if "source" in metadata else []):
        store.safe_path(path)
    store._citations(metadata)
    text = document_text(metadata, body)
    if redaction.find(text):
        raise StoreError("redaction gate refused decision")
    return text


def _commit(store, manifest, documents):
    """Preflight all records; immutable files precede the sole manifest commit."""
    prepared = [(metadata, body, _validate(store, metadata, body))
                for metadata, body in documents]
    entries = []
    for metadata, body, text in prepared:
        revision = digest(text)
        path = store.safe_path(f".sky/kb/documents/{metadata['id']}/{revision}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        store._atomic(path, text)
        entry = {"id": metadata["id"], "type": "decision", "title": metadata["title"],
                 "source": metadata.get("source", ""), "digest": revision,
                 "path": path.relative_to(store.root).as_posix(), "schema_version": 1,
                 "updated_at": datetime.now(timezone.utc).isoformat(),
                 "chunks": [{"id": c["id"], "offset": c["offset"], "chars": len(c["text"])}
                            for c in chunks(metadata["id"], body, store.chunk_chars)]}
        manifest["documents"][metadata["id"]] = entry
        entries.append(copy.deepcopy(entry))
    manifest["generation"] += 1
    store._atomic(store.safe_path(".sky/kb/manifest.json"),
                  json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return entries


def put_decision(store, metadata, body, *, stamp, approval=None):
    """Normal Store.put delegates here; model input cannot carry evidence.

    Preserve the typed Approval API for existing out-of-band confirmations.
    CLI lifecycle confirmation additionally records exact digest and method.
    """
    if RUNTIME_FIELDS & metadata.keys():
        raise StoreError("model supplied runtime-owned approval evidence")
    record = copy.deepcopy(metadata)
    if not isinstance(stamp, dict) or any(not isinstance(stamp.get(k), str) for k in STAMP_FIELDS) or not all(
            stamp[k].strip() for k in ("sky_agent", "sky_run")):
        raise StoreError("runtime stamp required")
    for key in STAMP_FIELDS:
        if key in record and record[key] != stamp[key]:
            raise StoreError(f"stamp mismatch: {key}")
        record[key] = stamp[key]
    record.setdefault("options", [record.get("answer", "")])
    record.setdefault("chosen_option", record.get("answer", ""))
    record.setdefault("superseded_by", [])
    if record.get("status") != "proposed":
        if "SKY_LAUNCHED" in os.environ or not isinstance(approval, Approval):
            raise StoreError("decision requires runtime approval evidence from a person")
        record.update(recorded_at=approval.confirmed_at, run_identity=stamp["sky_run"],
                      decided_by=approval.actor, approval=approval.evidence())
    elif approval is not None:
        raise StoreError("proposed decision cannot have approval evidence")
    with store.locked():
        manifest = store.manifest()
        old = manifest["documents"].get(record.get("id"))
        if old:
            previous = store.get(record["id"], manifest=manifest)["metadata"]
            if (record.get("status") == "proposed" and previous["status"] != "proposed") or previous["project"] != record["project"]:
                raise StoreError("cannot overwrite an approved decision or another project")
            record["version"] = previous["version"] + 1
        return _commit(store, manifest, [(record, body)])[0]


# Compatibility for phase-one callers; there is now one normal store path.
DecisionStore = Store


def propose(store, relative, *, run, text=None):
    """Require explicit options, choice and rationale; never invent a decision."""
    path = store.safe_path(relative)
    if text is None and path.stat().st_size > MAX_DOCUMENT_CHARS * 4:
        raise StoreError("document exceeds size cap")
    text = path.read_bytes().decode("utf-8") if text is None else text
    if len(text) > MAX_DOCUMENT_CHARS:
        raise StoreError("document exceeds size cap")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise StoreError("binary or control characters in proposal")
    metadata, body = parse_document(text) if text.startswith("---") else ({}, text)
    if RUNTIME_FIELDS & metadata.keys():
        raise StoreError("model supplied runtime-owned approval evidence")
    sections = {}
    heading = None
    for line in body.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            sections[heading] = []
        elif heading:
            sections[heading].append(line)
    section = lambda name: "\n".join(sections.get(name, [])).strip()
    title = metadata.get("title") or next((line[2:].strip() for line in body.splitlines()
                                           if line.startswith("# ")), path.stem)
    options = metadata.get("options") or [line[2:].strip() for line in
                                          section("options").splitlines() if line.startswith("- ")]
    choice = metadata.get("chosen_option") or metadata.get("answer") or section("chosen option")
    source = path.relative_to(store.root).as_posix()
    project = metadata.get("project", store.root.name)
    if not path.exists():
        # Stdin proposals retain their exact source for resolvable citations.
        if redaction.find(text):
            raise StoreError("redaction gate refused proposal")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    record = {"id": metadata.get("id") if metadata.get("type") == "decision" else
              "dec-" + digest(project + "\0" + source)[:24],
              "type": "decision", "schema_version": 1, "version": 1,
              "title": title, "project": project, "scope": metadata.get("scope", ["."]),
              "question": metadata.get("question") or section("question") or title,
              "options": options, "chosen_option": choice, "answer": choice,
              "rationale": metadata.get("rationale") or section("rationale"),
              "aliases": metadata.get("aliases", []), "status": "proposed",
              "supersedes": [], "superseded_by": [], "source_analysis": source,
              "source": source, "evidence_revision": metadata.get("evidence_revision", "unknown"),
              "relates_to": metadata.get("relates_to", []),
              "citations": metadata.get("citations", [source + ":1"])}
    entry = store.put(record, body, stamp=run.stamp())
    run.event(EVENT_KINDS["propose"], id=entry["id"], digest=entry["digest"])
    return entry


def _confirm(preview):
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return input("Confirm this exact decision revision? [y/N] ").strip().lower() == "y"



def _actor() -> str:
    """The person running the transition, as the host names them.

    getpass consults LOGNAME, USER, LNAME and USERNAME before the account
    database; a stripped environment on Windows reaches the database, which
    needs the Unix-only pwd module, so that failure must not stop an approval.
    """
    try:
        return getpass.getuser()
    except (ImportError, OSError, KeyError):
        pass
    try:
        return os.getlogin()
    except OSError:
        return "unknown-user"

def transition(store, record_id, action, *, run, by=None, confirm=None):
    if "SKY_LAUNCHED" in os.environ:
        raise StoreError("decision approval is people only; governed agent session refused")
    if action not in {"accept", "reject", "supersede"}:
        raise StoreError("unknown decision transition")
    if run.agent_id != "runtime":
        raise StoreError("human transition requires a runtime run")
    old = store.get(record_id)
    metadata = copy.deepcopy(old["metadata"])
    # Existing accepted records predate the options/back-link fields. Their
    # recorded answer remains the sole known option; do not invent alternatives.
    metadata.setdefault("options", [metadata["answer"]])
    metadata.setdefault("chosen_option", metadata["answer"])
    metadata.setdefault("superseded_by", [])
    required = "accepted" if action == "supersede" else "proposed"
    if metadata.get("type") != "decision" or metadata["status"] != required:
        raise StoreError(f"{action} requires a {required} decision")
    replacement = store.get(by) if action == "supersede" and by else None
    if action == "supersede" and (replacement is None or by == record_id or
            replacement["metadata"].get("type") != "decision" or
            replacement["metadata"].get("status") != "accepted" or
            replacement["metadata"].get("project") != metadata["project"]):
        raise StoreError("supersede requires --by a different accepted decision in this project")
    event_id = str(uuid.uuid4())
    preview = {"action": action, "decision": old, "replacement": replacement,
               "decision_digest": old["entry"]["digest"], "session": run.run_id,
               "event_id": event_id}
    if not (confirm or _confirm)(copy.deepcopy(preview)):
        raise StoreError("decision confirmation declined")
    now = datetime.now(timezone.utc).isoformat()
    evidence = {"actor": _actor(), "session": run.run_id,
                "event_id": event_id, "confirmed_at": now,
                "decision_digest": old["entry"]["digest"],
                "method": "sky kb decide " + action}
    metadata.update(status=EVENT_KINDS[action].split(".")[1], version=metadata["version"] + 1,
                    approval=evidence, recorded_at=now, run_identity=run.run_id,
                    decided_by=evidence["actor"])
    documents = [(metadata, old["body"])]
    if replacement:
        metadata["superseded_by"] = list(dict.fromkeys(metadata["superseded_by"] + [by]))
        other = copy.deepcopy(replacement["metadata"])
        other.setdefault("options", [other["answer"]])
        other.setdefault("chosen_option", other["answer"])
        other.setdefault("superseded_by", [])
        other["supersedes"] = list(dict.fromkeys(other["supersedes"] + [record_id]))
        other["version"] += 1
        other.update(approval=dict(evidence, decision_digest=replacement["entry"]["digest"]),
                     recorded_at=now, run_identity=run.run_id, decided_by=evidence["actor"])
        documents.append((other, replacement["body"]))
    with store.locked():
        manifest = store.manifest()
        for snapshot in (old, replacement):
            if snapshot and manifest["documents"].get(snapshot["metadata"]["id"], {}).get("digest") != snapshot["entry"]["digest"]:
                raise StoreError("decision changed since confirmation; confirm again")
        entries = _commit(store, manifest, documents)
    run.event(EVENT_KINDS[action], id=record_id, by=by, event_id=event_id,
              decision_digest=evidence["decision_digest"], digest=entries[0]["digest"])
    return entries[0]


def _in_scope(scopes, requested):
    path = PurePosixPath(requested)
    if path.is_absolute() or ".." in path.parts or "\\" in requested:
        raise StoreError("scope must be repository relative")
    return any(path.is_relative_to(PurePosixPath(scope)) for scope in scopes)


def list_decisions(store, *, status=None, scope=None):
    if status is not None and status not in SCHEMA["properties"]["status"]["enum"]:
        raise StoreError("unknown decision status")
    return [record for record in store.records() if record["metadata"].get("type") == "decision"
            and (status is None or record["metadata"]["status"] == status)
            and (scope is None or _in_scope(record["metadata"]["scope"], scope))]


def show(store, record_id):
    record = store.get(record_id)
    if record["metadata"].get("type") != "decision":
        raise StoreError("record is not a decision")
    return record


def find(store, question, *, scope=".", project=None, evidence_revision=None, k=10):
    if not isinstance(question, str) or not question.strip() or type(k) is not int or not 1 <= k <= 100:
        raise StoreError("question and k between 1 and 100 required")
    query = set(re.findall(r"\w+", question.lower()))
    records = list_decisions(store)
    superseded = {item for record in records if record["metadata"]["status"] in
                  {"accepted", "superseded"} for item in record["metadata"].get("supersedes", [])}
    hits = []
    for record in records:
        meta = record["metadata"]
        if meta["project"] != (project or store.root.name):
            continue
        texts = [meta["question"], meta["title"]] + meta.get("options", [meta["answer"]]) + meta.get("aliases", [])
        score = sum(len(query & set(re.findall(r"\w+", text.lower()))) for text in texts)
        if not score:
            continue
        current = meta["status"] != "superseded" and not meta.get("superseded_by") and meta["id"] not in superseded
        in_scope = _in_scope(meta["scope"], scope)
        currency = bool(evidence_revision and evidence_revision != "unknown" and
                        evidence_revision == meta["evidence_revision"])
        hits.append({"id": meta["id"], "title": meta["title"], "question": meta["question"],
                     "answer": meta["answer"], "status": meta["status"], "score": score,
                     "current": current, "in_scope": in_scope, "evidence_current": currency,
                     "closes": bool(meta["status"] == "accepted" and current and in_scope and
                                    currency and meta.get("approval"))})
    return sorted(hits, key=lambda hit: (-hit["score"], hit["id"]))[:k]

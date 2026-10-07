"""Cited analysis validation and storage under the normal store writer lock.

Retrieval counts come from a run ledger when available. The current ledger
does not retain hit counts: hits=None means unknown, never an invented zero.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import decisions, ledger, context_measurements
from .kbstore import STAMP_FIELDS, StoreError, digest, parse_document, validate_schema


def obj(properties, required=None):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required is None else required}


TEXT = {"type": "string", "minLength": 1}
TEXTS = {"type": "array", "items": TEXT}
COUNT = {"type": "integer", "minimum": 0}
PIN = obj({"id": TEXT, "digest": {"type": "string", "pattern": "[a-f0-9]{64}"}})
SCHEMA = obj({
    "id": {"type": "string", "pattern": "[A-Za-z0-9][A-Za-z0-9_-]{0,127}"},
    "type": {"const": "analysis"}, "schema_version": {"const": 1},
    "title": TEXT, "project": TEXT, "goal": TEXT,
    "scope": {"type": "array", "minItems": 1, "items": TEXT},
    "evidence_revision": TEXT,
    "intent": obj({"in_scope": TEXTS, "out_of_scope": TEXTS}),
    "findings": {"type": "array", "items": obj({"statement": TEXT,
        "citations": {"type": "array", "minItems": 1, "items": TEXT}})},
    "open_questions": {"type": "array", "items": obj({"question": TEXT,
        "candidates": {"type": "array", "items": obj({"id": TEXT,
            "status": {"enum": ["proposed", "accepted", "superseded", "rejected"]},
            "closes": {"type": "boolean"}})},
        "reason": TEXT, "closed_by": TEXT}, ["question", "candidates", "reason"])},
    "risks": TEXTS,
    "retrieval": obj({"operations": TEXTS, "hits": {}, "characters": {}, "run": TEXT}),
    "citations": TEXTS, "relates_to": TEXTS,
    **{key: {"type": "string", "x-written-by": "runtime"} for key in STAMP_FIELDS},
})
SCHEMA.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
               "$id": "urn:sky:schema:analysis", "title": "analysis"})
# Nullable measurements are expressed in the published schema, while the small
# runtime validator below handles this subset explicitly.
for field in ("hits", "characters"):
    SCHEMA["properties"]["retrieval"]["properties"][field] = {
        "anyOf": [COUNT, {"type": "null"}]}

RUNTIME_FIELDS = set(STAMP_FIELDS) | {"approval", "recorded_at", "run_identity",
                                     "decided_by", "stale", "pins"}


def verify_questions(store, record):
    """Recheck closure now; a model's candidate status/closes is not authority."""
    for question in record["open_questions"]:
        requested = question.get("closed_by")
        for scope in record["scope"]:
            actual = decisions.find(store, question["question"], scope=scope,
                                    project=record["project"],
                                    evidence_revision=record["evidence_revision"], k=100)
            by_id = {hit["id"]: hit for hit in actual}
            for candidate in question["candidates"]:
                found = by_id.get(candidate["id"])
                if candidate["closes"] and (found is None or not found["closes"]):
                    raise StoreError("candidate does not close question: " + candidate["id"])
                if found is None or candidate["status"] != found["status"]:
                    raise StoreError("candidate status/evidence changed: " + candidate["id"])
            if requested:
                chosen = by_id.get(requested)
                if not chosen or not chosen["closes"]:
                    raise StoreError("closed_by is not accepted, current and in-scope: " + requested)
                if not any(c["id"] == requested for c in question["candidates"]):
                    raise StoreError("closed_by was not among inspected candidates")
                answers = {hit["answer"] for hit in actual if hit["closes"]}
                if len(answers) > 1:
                    raise StoreError("conflicting applicable decisions; question remains OPEN")


def retrieval(run):
    path = Path(run.directory) / "tools.jsonl"
    if not path.exists():
        return {"operations": [], "hits": None, "characters": None, "run": run.run_id}
    measured = context_measurements.build(path)
    rows = [row for row in ledger.read(path) if str(row.get("tool", "")).startswith("mcp__")]
    operations = list(dict.fromkeys(row.get("operation", row["tool"]) for row in rows))
    counts = [row.get("hits") for row in rows]
    hits = sum(counts) if all(type(value) is int and value >= 0 for value in counts) else None
    return {"operations": operations, "hits": hits,
            "characters": measured["measured_characters"], "run": run.run_id}


def validate(store, record):
    validate_schema(record, SCHEMA)
    for field in ("hits", "characters"):
        value = record["retrieval"][field]
        if value is not None and (type(value) is not int or value < 0):
            raise StoreError("retrieval." + field + " must be a nonnegative count or null")
    for scope in record["scope"]:
        store.safe_path(scope)
    for finding in record["findings"]:
        store._citations(finding)
    store._citations(record)
    verify_questions(store, record)


def prepare(store, record, *, run=None):
    """Store calls this after generic defaults, while holding its writer lock."""
    reported = record.get("retrieval", {})
    if not isinstance(reported, dict):
        raise StoreError("retrieval must be an object")
    if "run" in reported:
        raise StoreError("model supplied runtime-owned retrieval.run")
    if set(reported) - {"operations", "hits", "characters"}:
        raise StoreError("unknown retrieval field")
    validate_schema(reported.get("operations", []), TEXTS, "retrieval.operations")
    for field in ("hits", "characters"):
        value = reported.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise StoreError("invalid reported retrieval count")
    record.setdefault("scope", ["."])
    record.setdefault("evidence_revision", "unknown")
    record["retrieval"] = retrieval(run) if run is not None else {
        "operations": [], "hits": None, "characters": None, "run": record["sky_run"]}
    validate(store, record)


def put(store, metadata, body, *, run, goal=None):
    if not isinstance(metadata, dict) or RUNTIME_FIELDS & metadata.keys():
        raise StoreError("model supplied runtime-owned analysis field")
    record = copy.deepcopy(metadata)
    record.setdefault("type", "analysis")
    if record["type"] != "analysis":
        raise StoreError("analyze put requires type analysis")
    record.setdefault("project", store.root.name)
    validate_schema(record["project"], TEXT, "project")
    if goal is not None:
        if "goal" in record and record["goal"] != goal:
            raise StoreError("analysis goal differs from the requested goal")
        record["goal"] = goal
    validate_schema(record.get("goal"), TEXT, "goal")
    record.setdefault("id", "analysis-" + digest(record["project"] + "\0" + record["goal"])[:24])
    return store.put(record, body, stamp=run.stamp(), run=run)


def put_text(store, text, *, run, goal=None):
    metadata, body = parse_document(text)
    return put(store, metadata, body, run=run, goal=goal)


def show(store, record_id):
    record = store.get(record_id)
    if record["metadata"].get("type") != "analysis":
        raise StoreError("record is not an analysis")
    validate_schema(record["metadata"], SCHEMA)
    return record


def list_analyses(store):
    return [show(store, record["metadata"]["id"]) for record in store.records()
            if record["metadata"].get("type") == "analysis"]

"""Plans pin cited, resolved analysis inputs; no admission or dispatch here."""
from __future__ import annotations

import copy
import subprocess

from . import analysis
from .kbstore import STAMP_FIELDS, StoreError, digest, parse_document, validate_schema

SCHEMA = analysis.obj({
    "id": {"type": "string", "pattern": "[A-Za-z0-9][A-Za-z0-9_-]{0,127}"},
    "type": {"const": "plan"}, "schema_version": {"const": 1},
    "title": analysis.TEXT, "project": analysis.TEXT, "analysis_id": analysis.TEXT,
    "steps": {"type": "array", "minItems": 1, "items": analysis.obj({
        "id": analysis.TEXT, "role": {"enum": ["architect", "developer", "reviewer", "security"]},
        "description": analysis.TEXT,
        "acceptance": {"type": "array", "minItems": 1, "items": analysis.TEXT},
        "inputs": analysis.TEXTS})},
    "pins": analysis.obj({"analysis": analysis.PIN,
        "decisions": {"type": "array", "items": analysis.PIN},
        "knowledge": {"type": "array", "items": analysis.PIN},
        "checkout": analysis.TEXT}),
    "citations": analysis.TEXTS, "relates_to": analysis.TEXTS,
    **{key: {"type": "string", "x-written-by": "runtime"} for key in STAMP_FIELDS},
})
SCHEMA.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
               "$id": "urn:sky:schema:plan", "title": "plan"})
SCHEMA["properties"]["pins"]["x-written-by"] = "runtime"


def checkout(root):
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = (result.stdout or "").strip()
    import re
    return value if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{40,64}", value) else "unknown"


def pin(record):
    return {"id": record["metadata"]["id"], "digest": record["entry"]["digest"]}


def prepare(store, record, *, run=None):
    """Resolve and pin all cross-record inputs under Store's writer lock."""
    source = analysis.show(store, record.get("analysis_id"))
    questions = source["metadata"]["open_questions"]
    open_count = sum(not question.get("closed_by") for question in questions)
    if open_count:
        raise StoreError(f"{open_count} open questions — run /sky:decide")
    analysis.validate(store, source["metadata"])
    record.setdefault("project", source["metadata"]["project"])
    if record["project"] != source["metadata"]["project"]:
        raise StoreError("plan and analysis projects differ")
    store._citations(record)
    references = list(record["citations"])
    references += source["metadata"]["citations"]
    references += [citation for finding in source["metadata"]["findings"] for citation in finding["citations"]]
    decision_ids = list(dict.fromkeys(question["closed_by"] for question in questions))
    knowledge_ids = []
    for reference in references:
        if not reference.startswith("id:"):
            continue
        referenced = store.get(reference[3:])
        if referenced["metadata"].get("type") == "decision" and referenced["metadata"]["id"] not in decision_ids:
            # Only approved, applicable decisions used to close questions are
            # authority. Other decision citations remain evidence, not grants.
            raise StoreError("plan cites a decision not used to close an analysis question")
        if referenced["metadata"].get("type") == "knowledge":
            knowledge_ids.append(referenced["metadata"]["id"])
    record["pins"] = {"analysis": pin(source),
                      "decisions": [pin(store.get(identifier)) for identifier in decision_ids],
                      "knowledge": [pin(store.get(identifier)) for identifier in dict.fromkeys(knowledge_ids)],
                      "checkout": checkout(store.root)}
    validate_schema(record, SCHEMA)
    identifiers = [step["id"] for step in record["steps"]]
    if len(identifiers) != len(set(identifiers)):
        raise StoreError("duplicate plan step id")


def put(store, metadata, body, *, run, analysis_id=None):
    if not isinstance(metadata, dict) or analysis.RUNTIME_FIELDS & metadata.keys():
        raise StoreError("model supplied runtime-owned plan field")
    record = copy.deepcopy(metadata)
    if analysis_id is not None:
        if "analysis_id" in record and record["analysis_id"] != analysis_id:
            raise StoreError("plan analysis id differs from requested input")
        record["analysis_id"] = analysis_id
    source = analysis.show(store, record.get("analysis_id"))
    record.setdefault("project", source["metadata"]["project"])
    record.setdefault("type", "plan")
    validate_schema(record["project"], analysis.TEXT, "project")
    if record["type"] != "plan":
        raise StoreError("plan put requires type plan")
    record.setdefault("id", "plan-" + digest(record["project"] + "\0" + source["metadata"]["id"])[:24])
    return store.put(record, body, stamp=run.stamp(), run=run)


def put_text(store, text, *, run, analysis_id=None):
    metadata, body = parse_document(text)
    return put(store, metadata, body, run=run, analysis_id=analysis_id)


def current(store, plan_id):
    record = store.get(plan_id)
    if record["metadata"].get("type") != "plan":
        raise StoreError("record is not a plan")
    validate_schema(record["metadata"], SCHEMA)
    pins = record["metadata"]["pins"]
    reasons = []
    stale_knowledge = 0
    for expected in [pins["analysis"], *pins["decisions"], *pins["knowledge"]]:
        try:
            actual = store.get(expected["id"])
        except StoreError:
            reasons.append("missing or invalid input: " + expected["id"])
        else:
            if expected in pins["knowledge"] and actual["metadata"].get("stale") is True:
                stale_knowledge += 1
            if actual["entry"]["digest"] != expected["digest"]:
                reasons.append("input revision changed: " + expected["id"])
    if stale_knowledge:
        reasons.append(f"{stale_knowledge} knowledge pins stale")
    # Unknown checkout currency stays explicit; it does not pretend to be a
    # verified revision. Admission handling of unknown belongs to the later gate.
    actual_checkout = checkout(store.root)
    if pins["checkout"] != "unknown":
        if actual_checkout != pins["checkout"]:
            reasons.append("code checkout changed or unavailable")
    return {**record, "stale": bool(reasons), "stale_reasons": reasons}


def show(store, plan_id):
    return current(store, plan_id)


def list_plans(store):
    return [current(store, record["metadata"]["id"]) for record in store.records()
            if record["metadata"].get("type") == "plan"]

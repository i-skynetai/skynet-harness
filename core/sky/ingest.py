"""Runtime-sealed handover intents; explicit confirmation is the only remote door.

No transport is implemented here: callers supply a runtime-owned transport.
The payload SHA-256 detects changes and pins confirmation; it is not a signature
or a tamper-proof provenance claim. Local handovers are never removed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import shlex
from dataclasses import replace
from datetime import datetime, timezone

from . import redaction, schemas
from .decisions import _actor
from .kbstore import MAX_DOCUMENT_CHARS, STAMP_FIELDS, Store, StoreError, parse_document

INGEST_INTENT = replace(schemas.INTENT, name="ingest-intent", fields=tuple(
    replace(field, choices=(*field.choices, "kb.ingest")) if field.name == "kind" else field
    for field in schemas.INTENT.fields) + (
        schemas.Field("source", "text", "canonical local handover", required=True),
        schemas.Field("payload", "map", "validated handover content", required=True),
        schemas.Field("stamp", "map", "runtime provenance", required=True, owner=schemas.RUNTIME),
        schemas.Field("payload_digest", "text", "sealed payload SHA-256", required=True, owner=schemas.RUNTIME),
    ))
APPROVAL_EVENT = "kb.ingest_approved"
REFUSAL_EVENT = "kb.ingest_refused"
EXECUTED_EVENT = "kb.ingest_executed"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def stamp_check(stamp):
    if not isinstance(stamp, dict) or set(stamp) != set(STAMP_FIELDS) or any(not isinstance(stamp[key], str) for key in STAMP_FIELDS) or not stamp["sky_agent"].strip() or not stamp["sky_run"].strip():
        raise StoreError("runtime stamp required (all five fields; agent and run nonempty)")


def payload_check(payload, stamp):
    stamp_check(stamp)
    if not isinstance(payload, dict) or set(payload) != {"engine", "source", "metadata", "body", "source_digest"}:
        raise StoreError("invalid ingest payload")
    engine = payload["engine"]
    if not isinstance(engine, dict) or set(engine) != {"name", "tenant"} or any(not isinstance(value, str) or not value.strip() for value in engine.values()):
        raise StoreError("remote engine requires name and tenant, never credentials")
    meta, body = payload["metadata"], payload["body"]
    if not isinstance(meta, dict) or meta.get("type") != "handover" or not isinstance(meta.get("title"), str) or not meta["title"].strip():
        raise StoreError("ingest requires a titled handover")
    if any(meta.get(key) != stamp[key] for key in STAMP_FIELDS):
        raise StoreError("handover stamp differs from runtime")
    if set(meta) & {"approved_by", "approved_at", "approval", "channel", "executed"}:
        raise StoreError("model-supplied approval refused")
    if type(meta.get("schema_version", 1)) is not int or meta.get("schema_version", 1) != 1:
        raise StoreError("unsupported handover schema version")
    if not isinstance(body, str) or not body.strip() or len(body) > MAX_DOCUMENT_CHARS or any((ord(c) < 32 and c not in "\r\n\t") or ord(c) == 127 for c in body):
        raise StoreError("invalid ingest body")
    if not isinstance(payload["source"], str) or not payload["source"] or not isinstance(payload["source_digest"], str) or not re.fullmatch(r"[a-f0-9]{64}", payload["source_digest"]):
        raise StoreError("invalid ingest source")
    if redaction.find(canonical(payload)):
        raise StoreError("redaction gate refused ingest payload")


def source_payload(store, source, engine, stamp):
    path = store.safe_path(source)
    source = path.relative_to(store.root).as_posix()
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_CHARS * 4 + 1)
    if len(raw) > MAX_DOCUMENT_CHARS * 4:
        raise StoreError("handover exceeds size cap")
    metadata, body = parse_document(raw.decode("utf-8"))
    store._citations(metadata)
    payload = {"engine": copy.deepcopy(engine), "source": source, "metadata": metadata,
               "body": body, "source_digest": hashlib.sha256(raw).hexdigest()}
    payload_check(payload, stamp)
    return payload


def seal(root, source, *, engine, stamp, run=None):
    if engine is None:
        return None
    store = Store(root)
    if run is not None and stamp != run.stamp():
        raise StoreError("runtime run differs from stamp")
    payload = source_payload(store, source, engine, stamp)
    intent = schemas.seal(INGEST_INTENT, {"kind": "kb.ingest", "summary": payload["metadata"]["title"],
        "source": payload["source"], "payload": payload}, stamp=copy.deepcopy(stamp), payload_digest=digest(payload),
        run_id=stamp["sky_run"], agent_id=stamp["sky_agent"], intent_id="ingest-" + secrets.token_hex(12),
        created_at=datetime.now(timezone.utc).isoformat())
    if redaction.find(canonical(intent)):
        raise StoreError("redaction gate refused ingest intent")
    target = store.safe_path(".sky/outbox/" + intent["intent_id"] + ".json")
    with store.locked():
        store._atomic(target, json.dumps(intent, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    return target


def read(store, file):
    path = store.safe_path(file)
    if path.parent != store.safe_path(".sky/outbox"):
        raise StoreError("ingest intent must be in .sky/outbox")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_CHARS * 8 + 1)
    if len(raw) > MAX_DOCUMENT_CHARS * 8:
        raise StoreError("intent exceeds size cap")
    intent = json.loads(raw.decode("utf-8"))
    schemas.check(INGEST_INTENT, intent, source=schemas.RUNTIME)
    if not isinstance(intent.get("intent_id"), str) or not re.fullmatch(r"ingest-[a-f0-9]{24}", intent["intent_id"]) or path.name != intent["intent_id"] + ".json":
        raise StoreError("ingest intent filename differs from sealed identity")
    if intent["kind"] != "kb.ingest" or intent.get("executed"):
        raise StoreError("not a pending kb.ingest intent")
    payload_check(intent["payload"], intent["stamp"])
    if intent["source"] != intent["payload"]["source"] or intent["run_id"] != intent["stamp"]["sky_run"] or intent["agent_id"] != intent["stamp"]["sky_agent"]:
        raise StoreError("intent provenance mismatch")
    if digest(intent["payload"]) != intent["payload_digest"]:
        raise StoreError("sealed payload digest mismatch")
    current = source_payload(store, intent["source"], intent["payload"]["engine"], intent["stamp"])
    if digest(current) != intent["payload_digest"]:
        raise StoreError("local handover changed since sealing")
    return intent


def render(root, file):
    store = Store(root)
    intent = read(store, file)
    relative = store.safe_path(file).relative_to(store.root).as_posix()
    command = "sky ingest " + shlex.quote(relative)
    return {"command": command, "source": intent["source"], "stamp": intent["stamp"],
            "payload_digest": intent["payload_digest"], "summary": intent["summary"],
            "engine": copy.deepcopy(intent["payload"]["engine"])}


def ingest(root, file, *, confirm, transport, run, env=None):
    try:
        if "SKY_LAUNCHED" in (os.environ if env is None else env):
            raise StoreError("remote ingest requires a person; refused under SKY_LAUNCHED")
        store = Store(root)
        intent = read(store, file)
        identity = digest(intent)
        request = render(root, file)
        if confirm(copy.deepcopy(request)) is not True:
            raise StoreError("remote ingest confirmation refused")
        with store.locked():
            current = read(store, file)
            if digest(current) != identity:
                raise StoreError("intent changed during confirmation")
            current.update(approved_by=_actor(), approved_at=datetime.now(timezone.utc).isoformat(), channel="sky ingest")
            run.event(APPROVAL_EVENT, payload_digest=current["payload_digest"], source=current["source"])
            result = transport(copy.deepcopy(current["payload"]["engine"]), copy.deepcopy(current["payload"]))
            if not isinstance(result, dict) or result.get("ok") is not True or result.get("error") or result.get("isError"):
                raise StoreError("remote ingest transport refused payload")
            current["executed"] = True
            store._atomic(store.safe_path(file), json.dumps(current, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
        run.event(EXECUTED_EVENT, payload_digest=current["payload_digest"], source=current["source"])
        return result
    except Exception as exc:
        run.event(REFUSAL_EVENT, reason=redaction.scrub(str(exc))[0])
        raise

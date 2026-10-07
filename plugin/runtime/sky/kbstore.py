"""SH-083 local Markdown store: immutable revisions, manifest commit, OS lock.

The runtime supplies stamps and decision approval separately from model input.
This is validation under one OS user, not an adversarial filesystem sandbox.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from . import redaction, yamlish

SCHEMA_VERSION = 1
CHUNK_CHARS = 2000
MAX_DOCUMENT_CHARS = 1_000_000
STAMP_FIELDS = ("sky_agent", "sky_run", "sky_role", "sky_task", "sky_kb")
TYPES = {"readme", "doc", "adr", "design", "handover", "analysis", "plan", "decision", "knowledge"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_RUNTIME = {"recorded_at", "run_identity", "decided_by", "approval"}

# Published verbatim in schemas/; separate from the seven host contracts.
DECISION_SCHEMA = json.loads(r'''
{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:sky:schema:decision","title":"decision","type":"object","additionalProperties":false,"required":["id","type","schema_version","version","title","project","scope","question","aliases","answer","rationale","status","supersedes","source_analysis","evidence_revision","relates_to","citations","sky_agent","sky_run","sky_role","sky_task","sky_kb","options","chosen_option","superseded_by"],"properties":{"id":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"},"type":{"const":"decision"},"schema_version":{"const":1},"version":{"type":"integer","minimum":1},"title":{"type":"string","minLength":1},"project":{"type":"string","minLength":1},"scope":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"question":{"type":"string","minLength":1},"aliases":{"type":"array","items":{"type":"string","minLength":1}},"answer":{"type":"string","minLength":1},"rationale":{"type":"string","minLength":1},"status":{"enum":["proposed","accepted","superseded","rejected"]},"supersedes":{"type":"array","items":{"type":"string","minLength":1}},"source_analysis":{"type":"string","minLength":1},"evidence_revision":{"type":"string","minLength":1},"relates_to":{"type":"array","items":{"type":"string","minLength":1}},"citations":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"source":{"type":"string","minLength":1},"sky_agent":{"type":"string","minLength":1,"x-written-by":"runtime"},"sky_run":{"type":"string","minLength":1,"x-written-by":"runtime"},"sky_role":{"type":"string","x-written-by":"runtime"},"sky_task":{"type":"string","x-written-by":"runtime"},"sky_kb":{"type":"string","x-written-by":"runtime"},"recorded_at":{"type":"string","format":"date-time","x-written-by":"runtime"},"run_identity":{"type":"string","minLength":1,"x-written-by":"runtime"},"decided_by":{"type":"string","minLength":1,"x-written-by":"runtime"},"approval":{"type":"object","x-written-by":"runtime","additionalProperties":false,"required":["actor","session","event_id","confirmed_at"],"properties":{"actor":{"type":"string","minLength":1},"session":{"type":"string","minLength":1},"event_id":{"type":"string","minLength":1},"confirmed_at":{"type":"string","format":"date-time"},"decision_digest":{"type":"string","pattern":"[a-f0-9]{64}"},"method":{"enum":["sky kb decide accept","sky kb decide reject","sky kb decide supersede"]}}},"options":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"chosen_option":{"type":"string","minLength":1},"superseded_by":{"type":"array","items":{"type":"string","minLength":1}}},"allOf":[{"if":{"properties":{"status":{"const":"proposed"}}},"then":{"not":{"anyOf":[{"required":["approval"]},{"required":["recorded_at"]},{"required":["run_identity"]},{"required":["decided_by"]}]}},"else":{"required":["approval","recorded_at","run_identity","decided_by"]}}]}
''')
KNOWLEDGE_SCHEMA = json.loads(r'''
{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:sky:schema:knowledge","title":"knowledge","type":"object","additionalProperties":false,"required":["id","type","schema_version","title","project","scope","module","category","confidence","checkout_digest","index_digest","stale","relates_to","citations","sky_agent","sky_run","sky_role","sky_task","sky_kb"],"properties":{"id":{"type":"string","pattern":"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"},"type":{"const":"knowledge"},"schema_version":{"const":1},"title":{"type":"string","minLength":1},"project":{"type":"string","minLength":1},"scope":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"module":{"type":"string","minLength":1},"category":{"enum":["implemented_decision","pattern","practice","business_rule","nfr"]},"confidence":{"type":"number","minimum":0,"maximum":1},"checkout_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"index_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"stale":{"type":"boolean"},"relates_to":{"type":"array","items":{"type":"string","minLength":1}},"citations":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"source":{"type":"string","minLength":1},"sky_agent":{"type":"string","minLength":1,"x-written-by":"runtime"},"sky_run":{"type":"string","minLength":1,"x-written-by":"runtime"},"sky_role":{"type":"string","x-written-by":"runtime"},"sky_task":{"type":"string","x-written-by":"runtime"},"sky_kb":{"type":"string","x-written-by":"runtime"}}}
''')


class StoreError(ValueError):
    """A malformed record, unsafe path or corrupt store; never silently ignored."""


class StoreBusy(StoreError):
    """Another writer holds the local OS lock."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_schema(value, schema, where="record"):
    """Validate the published schemas' deliberately small JSON Schema subset."""
    kind = schema.get("type")
    checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
              "string": lambda v: isinstance(v, str), "integer": lambda v: type(v) is int,
              "number": lambda v: type(v) in (int, float), "boolean": lambda v: type(v) is bool}
    if kind and not checks[kind](value):
        raise StoreError(f"{where}: expected {kind}")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise StoreError(f"{where}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise StoreError(f"{where}: invalid choice")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise StoreError(f"{where}: missing {sorted(missing)[0]}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise StoreError(f"{where}: unknown field {sorted(set(value) - set(props))[0]}")
        for key in value:
            if key in props:
                validate_schema(value[key], props[key], f"{where}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise StoreError(f"{where}: empty list")
        for item in value:
            validate_schema(item, schema.get("items", {}), where)
    if isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            raise StoreError(f"{where}: empty text")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise StoreError(f"{where}: invalid format")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
            except ValueError as exc:
                raise StoreError(f"{where}: expected timezone timestamp") from exc
    if type(value) in (int, float):
        import math
        if not math.isfinite(value) or value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise StoreError(f"{where}: outside allowed range")


def parse_document(text):
    """Read JSON frontmatter (valid YAML) or the repository's strict YAML subset."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise StoreError("document has no frontmatter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        raw = "".join(lines[1:end])
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise StoreError(f"duplicate frontmatter key: {key}")
                result[key] = value
            return result
        metadata = json.loads(raw, object_pairs_hook=unique) if raw.lstrip().startswith("{") else yamlish.parse(raw)
    except (StopIteration, ValueError) as exc:
        raise StoreError(f"malformed frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise StoreError("frontmatter must be a mapping")
    return metadata, "".join(lines[end + 1:])


def document_text(metadata, body):
    return "---\n" + json.dumps(metadata, sort_keys=True, ensure_ascii=False, indent=2) + "\n---\n" + body


def chunks(record_id, body, size=CHUNK_CHARS):
    if type(size) is not int or size < 1:
        raise StoreError("chunk size must be positive")
    return [{"id": f"{record_id}#{n:04d}", "offset": offset, "text": body[offset:offset + size]}
            for n, offset in enumerate(range(0, len(body), size))]


@dataclass(frozen=True)
class Approval:
    actor: str
    session: str
    event_id: str
    confirmed_at: str

    def evidence(self):
        body = dict(actor=self.actor, session=self.session, event_id=self.event_id, confirmed_at=self.confirmed_at)
        validate_schema(body, DECISION_SCHEMA["properties"]["approval"], "approval")
        return body


class Store:
    def __init__(self, root, *, chunk_chars=CHUNK_CHARS, lock_timeout=5):
        self.root = Path(root).resolve()
        self.chunk_chars = chunk_chars
        self.lock_timeout = lock_timeout
        chunks("check", "", chunk_chars)

    def safe_path(self, relative):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise StoreError("path must be repository-relative")
        path = Path(relative)
        if path.is_absolute() or PureWindowsPath(relative).drive or ".." in path.parts:
            raise StoreError(f"path escapes repository: {relative}")
        candidate = self.root
        for part in path.parts:
            candidate /= part
            if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
                raise StoreError(f"symlink refused: {relative}")
        if not candidate.resolve().is_relative_to(self.root):
            raise StoreError(f"path escapes repository: {relative}")
        return candidate

    @contextmanager
    def locked(self):
        directory = self.safe_path(".sky/kb")
        directory.mkdir(parents=True, exist_ok=True)
        path = self.safe_path(".sky/kb/.lock")
        with path.open("a+b") as lock:
            if lock.seek(0, 2) == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise StoreBusy("local store writer lock timed out") from exc
                    time.sleep(0.01)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def manifest(self):
        path = self.safe_path(".sky/kb/manifest.json")
        if not path.exists():
            return {"schema_version": 1, "generation": 0, "documents": {}}
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(body, dict):
                raise StoreError("manifest must be a mapping")
            if type(body.get("schema_version")) is not int or body["schema_version"] != 1:
                raise StoreError("unsupported manifest schema version")
            if type(body.get("generation")) is not int or not isinstance(body.get("documents"), dict):
                raise StoreError("malformed manifest")
            for record_id, entry in body["documents"].items():
                if not _ID.fullmatch(record_id) or not isinstance(entry, dict) or not _DIGEST.fullmatch(entry.get("digest", "")):
                    raise StoreError("malformed manifest entry")
                expected = f".sky/kb/documents/{record_id}/{entry['digest']}.md"
                if entry.get("path") != expected:
                    raise StoreError("manifest document path mismatch")
                self.safe_path(expected)
            return body
        except (ValueError, KeyError, TypeError) as exc:
            raise StoreError(f"invalid store manifest: {exc}") from exc

    def _atomic(self, path, text):
        import uuid
        relative = path.relative_to(self.root).as_posix()
        self.safe_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A digest revision already has a long basename. Appending another UUID
        # makes only the temporary path longer and can break Windows writes even
        # when the final revision path is usable. Keep the temp beside its target
        # for atomic replacement, with a short independent unique basename.
        temp = path.with_name(".tmp-" + uuid.uuid4().hex)
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            self.safe_path(relative)
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    def _citations(self, metadata):
        citations = metadata.get("citations", [])
        if not isinstance(citations, list) or any(not isinstance(c, str) or not c for c in citations):
            raise StoreError("citations must be a list of nonempty references")
        for citation in citations:
            if citation.startswith("id:"):
                self.get(citation[3:])
                continue
            try:
                relative, line = citation.rsplit(":", 1)
                number = int(line)
            except ValueError as exc:
                raise StoreError(f"citation must name file:line or id:record: {citation}") from exc
            path = self.safe_path(relative)
            if number < 1 or not path.is_file() or number > len(path.read_text(encoding="utf-8").splitlines()):
                raise StoreError(f"citation does not resolve: {citation}")

    def put(self, metadata, body, *, stamp, approval=None, run=None):
        if isinstance(metadata, dict) and metadata.get("type") == "decision":
            from .decisions import put_decision
            return put_decision(self, metadata, body, stamp=stamp, approval=approval)
        if not isinstance(metadata, dict) or not isinstance(body, str) or not body.strip():
            raise StoreError("document metadata and nonempty body required")
        if len(body) > MAX_DOCUMENT_CHARS:
            raise StoreError("document exceeds size cap")
        if not isinstance(stamp, dict) or any(not isinstance(stamp.get(k), str) for k in STAMP_FIELDS) or not stamp["sky_agent"].strip() or not stamp["sky_run"].strip():
            raise StoreError("runtime stamp required (all five fields; agent and run nonempty)")
        if _RUNTIME & set(metadata):
            raise StoreError(f"model supplied runtime-owned field: {sorted(_RUNTIME & set(metadata))[0]}")
        if metadata.get("type") in ("analysis", "plan"):
            from .analysis import RUNTIME_FIELDS
            if RUNTIME_FIELDS & metadata.keys():
                raise StoreError("model supplied runtime-owned analysis/plan field")
        if run is not None and stamp != run.stamp():
            raise StoreError("runtime run differs from stamp")
        record = copy.deepcopy(metadata)
        for key in STAMP_FIELDS:
            if key in record and record[key] != stamp[key]:
                raise StoreError(f"stamp mismatch: {key}")
            record[key] = stamp[key]
        if record.get("type") not in TYPES or not isinstance(record.get("title"), str) or not record["title"].strip():
            raise StoreError("known document type and title required")
        record.setdefault("schema_version", 1)
        if type(record["schema_version"]) is not int or record["schema_version"] != 1:
            raise StoreError("unsupported document schema version")
        for key in ("relates_to", "citations"):
            record.setdefault(key, [])
        if not isinstance(record["relates_to"], list) or any(not isinstance(r, str) or not _ID.fullmatch(r) for r in record["relates_to"]):
            raise StoreError("relates_to must be a list of record ids")
        project = record.get("project")
        if not isinstance(project, str) or not project.strip():
            raise StoreError("project required")
        if "source" in record:
            self.safe_path(record["source"])
        record.setdefault("id", "doc-" + digest(project + "\0" + record.get("source", record["type"] + ":" + record["title"]))[:24])
        if not isinstance(record["id"], str) or not _ID.fullmatch(record["id"]):
            raise StoreError("invalid document id")
        if "scope" in record and (not isinstance(record["scope"], list) or
                any(not isinstance(s, str) or not s for s in record["scope"])):
            raise StoreError("scope must be a list of relative paths")
        for scope in record.get("scope", []):
            self.safe_path(scope)
        if record["type"] == "knowledge":
            validate_schema(record, KNOWLEDGE_SCHEMA)
            if any(c.startswith("id:") for c in record["citations"]):
                raise StoreError("knowledge requires code file:line citations")
        self._citations(record)
        with self.locked():
            manifest = self.manifest()
            if record["type"] in ("analysis", "plan"):
                from . import analysis, plans
                module = analysis if record["type"] == "analysis" else plans
                module.prepare(self, record, run=run)
                if record["id"] in manifest["documents"]:
                    previous = self.get(record["id"], manifest=manifest)["metadata"]
                    if previous["type"] != record["type"]:
                        raise StoreError(record["type"] + " id belongs to another record type")
            text = document_text(record, body)
            if redaction.find(text):
                raise StoreError("redaction gate refused document")
            revision = digest(text)
            old = manifest["documents"].get(record["id"])
            if old and old["digest"] == revision:
                return copy.deepcopy(old)
            if old and self.get(record["id"])["metadata"]["project"] != project:
                raise StoreError("document id belongs to another project")
            path = self.safe_path(f".sky/kb/documents/{record['id']}/{revision}.md")
            # First writes have no store/documents/<id> tree. Create every
            # parent under the writer lock before opening a temporary revision.
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic(path, text)
            entry = {"id": record["id"], "type": record["type"], "title": record["title"],
                     "source": record.get("source", ""), "digest": revision,
                     "path": path.relative_to(self.root).as_posix(), "schema_version": 1,
                     "updated_at": datetime.now(timezone.utc).isoformat(),
                     "chunks": [{"id": c["id"], "offset": c["offset"], "chars": len(c["text"])}
                                for c in chunks(record["id"], body, self.chunk_chars)]}
            manifest["documents"][record["id"]] = entry
            manifest["generation"] += 1
            self._atomic(self.safe_path(".sky/kb/manifest.json"), json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            return copy.deepcopy(entry)

    def put_file(self, relative, *, stamp, approval=None):
        path = self.safe_path(relative)
        metadata, body = parse_document(path.read_bytes().decode("utf-8"))
        return self.put(metadata, body, stamp=stamp, approval=approval)

    def get(self, record_id, *, manifest=None):
        if not isinstance(record_id, str) or not _ID.fullmatch(record_id):
            raise StoreError("invalid record id")
        manifest = self.manifest() if manifest is None else manifest
        entry = manifest["documents"].get(record_id)
        if entry is None:
            raise StoreError(f"record not found: {record_id}")
        text = self.safe_path(entry["path"]).read_bytes().decode("utf-8")
        if digest(text) != entry["digest"]:
            raise StoreError(f"document digest mismatch: {record_id}")
        metadata, body = parse_document(text)
        if metadata.get("id") != record_id or metadata.get("schema_version") != 1:
            raise StoreError("document identity/version mismatch")
        return {"metadata": metadata, "body": body, "entry": copy.deepcopy(entry)}

    def records(self):
        manifest = self.manifest()  # One snapshot across a read, not one per hit.
        return [self.get(record_id, manifest=manifest) for record_id in sorted(manifest["documents"])]

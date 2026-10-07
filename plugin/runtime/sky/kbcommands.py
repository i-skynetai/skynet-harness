"""SH-083 local commands and runtime-attributed, validated document writes.

Interactive writes create a runtime record. Managed writes retain the current
run's stamp and append a kb.put event without finishing that enclosing run.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from . import context_sources, kbserve, recorder, yamlish
from .kbstore import MAX_DOCUMENT_CHARS, Store, StoreError, TYPES, parse_document


def current_run():
    """Read the runtime's current record; input frontmatter cannot supply it."""
    fields = {"agent_id": "SKY_AGENT_ID", "run_id": "SKY_RUN_ID", "role": "SKY_ROLE",
              "task": "SKY_TASK", "kb": "SKY_KB_NAME"}
    values = {field: os.environ.get(env, "") for field, env in fields.items()}
    directory = os.environ.get("SKY_RUN_DIR", "")
    if os.environ.get("SKY_LAUNCHED") != "1" and not values["run_id"] and not directory:
        return None
    if not values["agent_id"] or not values["run_id"] or not directory:
        raise StoreError("put refused: runtime stamp requires SKY_AGENT_ID, SKY_RUN_ID and SKY_RUN_DIR")
    path = Path(directory).expanduser().resolve()
    if path.name != values["run_id"]:
        raise StoreError("put refused: current run directory does not match SKY_RUN_ID")
    try:
        with (path / "events.jsonl").open(encoding="utf-8") as stream:
            start = json.loads(stream.readline())
    except (OSError, ValueError) as exc:
        raise StoreError("put refused: current runtime run record is unavailable") from exc
    if not isinstance(start, dict) or start.get("kind") != "run.start" or any(start.get(f) != values[f] for f in ("agent_id", "role", "task", "kb")):
        raise StoreError("put refused: runtime stamp differs from the current run record")
    return recorder.Run(directory=path, **values)


def put(store, file, document_type=None):
    run = current_run()
    interactive = run is None
    if interactive:
        run = recorder.Run.start(role="runtime", task="sky kb put", kb="local", agent_id="runtime")
    try:
        if document_type and document_type not in TYPES:
            raise StoreError(f"unknown document type: {document_type}")
        path = Path(file)
        if path.is_absolute():
            try:
                relative = path.relative_to(store.root).as_posix()
            except ValueError as exc:
                raise StoreError(f"input file is outside repository: {file}") from exc
        else:
            # Relative input names follow the caller's cwd, not an implicit root.
            try:
                relative = (Path.cwd() / path).absolute().relative_to(store.root).as_posix()
            except ValueError as exc:
                raise StoreError(f"input file is outside repository: {file}") from exc
        source = store.safe_path(relative)
        # Bound allocation before decoding; UTF-8 needs at most four bytes per
        # character. Store.put also enforces the document body's character cap.
        with source.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_CHARS * 4 + 1)
        if len(raw) > MAX_DOCUMENT_CHARS * 4:
            raise StoreError("document exceeds size cap")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StoreError("binary or non-UTF-8 document refused") from exc
        if any((ord(ch) < 32 and ch not in "\t\r\n") or ord(ch) == 127 for ch in text):
            raise StoreError("binary document refused: control characters")
        if text.splitlines() and text.splitlines()[0].strip() == "---":
            # A malformed frontmatter block must never become a plain document.
            metadata, body = parse_document(text)
        else:
            if not document_type:
                raise StoreError("document has no frontmatter; provide --type <document-type>")
            heading = re.search(r"^ {0,3}#[ \t]+([^\r\n]+?)[ \t]*(?:[ \t]+#+[ \t]*)?\r?$", text, re.MULTILINE)
            metadata = {"type": document_type, "title": heading.group(1) if heading else source.name,
                        "project": store.root.name, "source": source.relative_to(store.root).as_posix(),
                        "schema_version": 1}
            # Store.put derives the stable id from project + canonical source.
            body = text
        if document_type:
            if metadata.get("type") not in (None, document_type):
                raise StoreError("--type conflicts with the document's frontmatter type")
            metadata["type"] = document_type
        entry = store.put(metadata, body, stamp=run.stamp())
    except (StoreError, OSError, ValueError, yamlish.YamlishError) as exc:
        run.refused(str(exc), operation="kb.put")
        if interactive:
            run.finish("refused", operation="kb.put")
        raise
    run.event("kb.put", document_id=entry["id"], digest=entry["digest"], path=entry["path"],
              type=metadata["type"], run_id=run.run_id, agent_id=run.agent_id)
    if interactive:
        run.finish("stored", operation="kb.put")
    return entry, run


def execute(args):
    try:
        action, value = args.kb_action, args.kb_value
        if action in ("put", "show", "search") and not value:
            raise StoreError(f"{action} requires a file, id or query")
        if action == "serve" and value:
            raise StoreError("serve does not accept a file or query")
        if args.write_adapter and action != "serve":
            raise StoreError("--write-adapter is only supported by serve")
        if args.document_type and action != "put":
            raise StoreError("--type is only supported by put")
        root = context_sources.repository(explicit=args.root)
        store = Store(root)
        if action == "serve":
            if args.write_adapter:
                print(f"local adapter: {context_sources.write_adapter(root)}")
            else:
                # JSON-RPC stdout is always UTF-8, including Windows terminals.
                for stream in (sys.stdin, sys.stdout):
                    if hasattr(stream, "reconfigure"):
                        stream.reconfigure(encoding="utf-8")
                kbserve.serve(store, sys.stdin, sys.stdout)
        elif action == "put":
            entry, run = put(store, value, args.document_type)
            print(f"stored {entry['id']}  {entry['digest']}  run {run.run_id}")
            print(f"run record: {run.directory}")
        elif action == "show":
            record = store.get(value)
            print(json.dumps(record["metadata"], ensure_ascii=False, sort_keys=True, indent=2))
            print(record["body"], end="" if record["body"].endswith("\n") else "\n")
        elif action == "search":
            if not 1 <= args.k <= 100:
                raise StoreError("-k must be between 1 and 100")
            hits = kbserve.Server(store).search(value, k=args.k)
            for hit in hits:
                print(f"{hit['id']}  score {hit['score']}  {hit['citation']}  {hit['title']}")
                print(hit["excerpt"])
            print(f"{len(hits)} hit(s)")
        return 0
    except (StoreError, context_sources.ContextError, OSError, ValueError, yamlish.YamlishError) as exc:
        print(f"sky kb: {exc}", file=sys.stderr)
        return 1

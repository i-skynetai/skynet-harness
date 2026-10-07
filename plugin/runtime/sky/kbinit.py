"""SH-084 deterministic document discovery through the validated runtime put path.

Source digests exclude runtime stamps. Unchanged input retains its immutable
revision; removed sources are marked stale, never deleted. Coverage is an
observation of top-level modules, never proof of complete code understanding.
CLI wiring and context.sources project-schema support follow in the next phase.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import queue
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import context_sources, kbcommands, project, recorder, redaction, yamlish
from .kbstore import MAX_DOCUMENT_CHARS, Store, StoreError, parse_document

DEFAULT_SOURCES = ("README.md", "docs", ".sky/handovers")
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cs", ".cpp", ".c"}
DISCOVER_NOTICE = "codebase discovery lands with SH-088"


def excluded(relative):
    parts = Path(relative).parts
    lower = [part.lower() for part in parts]
    if any(part in {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv"} for part in lower):
        return "generated or VCS metadata"
    if len(lower) > 1 and lower[0] == ".sky" and lower[1] in {"kb", "runs", "sessions"}:
        return "store or run records"
    if any(part.startswith(".env") for part in lower) or Path(relative).suffix.lower() in {".pem", ".key"}:
        return "secret-style file"
    return None


def configured_sources(root):
    path = Path(root) / ".sky/project.yaml"
    body = project.read_mapping(path)
    project.validate_config(body, Path(root))
    context = body.get("context", {})
    if not isinstance(context, dict):
        raise StoreError("context.sources requires a context mapping")
    values = context.get("sources", list(DEFAULT_SOURCES))
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise StoreError("context.sources must be a list of repository-relative paths")
    for value in values:
        project.contained(Path(root), value)
    return values


def enumerate_sources(root, *, add=(), sources=None):
    store = Store(root)
    candidates, skipped = {}, {}
    selections = list(configured_sources(store.root) if sources is None else sources) + list(add)
    for selection in selections:
        supplied = Path(selection)
        if supplied.is_absolute():
            try:
                relative = supplied.relative_to(store.root).as_posix()
            except ValueError:
                skipped[str(selection)] = "outside repository"
                continue
        else:
            relative = supplied.as_posix()
        try:
            path = store.safe_path(relative)
        except (StoreError, ValueError) as exc:
            skipped[relative] = str(exc)
            continue
        if excluded(relative):
            skipped[relative] = excluded(relative)
            continue
        if not path.exists():
            if selection in add:
                skipped[relative] = "source absent"
            continue
        files = [path] if path.is_file() else []
        if path.is_dir():
            for directory, names, filenames in os.walk(path, followlinks=False):
                for name in list(names):
                    child = Path(directory) / name
                    rel = child.relative_to(store.root).as_posix()
                    reason = "symlink refused" if child.is_symlink() else excluded(rel)
                    if reason:
                        skipped[rel] = reason
                        names.remove(name)
                files.extend(Path(directory) / name for name in filenames)
        for file in files:
            rel = file.relative_to(store.root).as_posix()
            reason = excluded(rel)
            try:
                safe = store.safe_path(rel)
            except (StoreError, ValueError) as exc:
                skipped[rel] = str(exc)
                continue
            if reason:
                skipped[rel] = reason
            else:
                canonical = safe.resolve()
                candidates[canonical] = canonical.relative_to(store.root).as_posix()
    return sorted(candidates.values()), [{"source": source, "reason": skipped[source]} for source in sorted(skipped)]


def infer_type(relative):
    path = Path(relative)
    parts = [part.lower() for part in path.parts]
    if path.name.lower() == "readme.md":
        return "readme"
    if "adr" in parts:
        return "adr"
    if "handovers" in parts:
        return "handover"
    if "features" in parts or "design" in parts or path.name.lower().startswith("design"):
        return "design"
    return "doc"


def inspect_source(store, relative):
    path = store.safe_path(relative)
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_CHARS * 4 + 1)
    if len(raw) > MAX_DOCUMENT_CHARS * 4:
        raise StoreError("document exceeds size cap")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StoreError("binary or non-UTF-8 file") from exc
    if any(ord(ch) < 32 and ch not in "\t\r\n" or ord(ch) == 127 for ch in text):
        raise StoreError("binary file")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise StoreError("document exceeds size cap")
    if redaction.find(text):
        raise StoreError("redaction gate refused source")
    if path.suffix.lower() != ".md":
        raise StoreError("not a Markdown document")
    frontmatter = bool(text.splitlines() and text.splitlines()[0].strip() == "---")
    if frontmatter:
        parse_document(text)  # Malformed metadata never falls back to plain Markdown.
    return hashlib.sha256(raw).hexdigest(), None if frontmatter else infer_type(relative)


def modules(root):
    found = set()
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [name for name in names if not (Path(directory) / name).is_symlink()
                    and not excluded((Path(directory) / name).relative_to(root).as_posix())]
        for name in files:
            file = Path(directory) / name
            if file.suffix.lower() in CODE_SUFFIXES and not file.is_symlink():
                rel = file.relative_to(root)
                found.add(rel.parts[0] + "/" if len(rel.parts) > 1 else ".")
    return sorted(found)


def coverage(root, context, *, call=None):
    call = call or context_sources.stdio_call
    local = modules(Path(root))
    source = context.sources.get("code") if context else None
    if not source:
        return {"status": "no code index", "covered": [], "uncovered": local, "granularity": "top-level module"}
    defaults = source.get("code.find", {}).get("defaults", {})
    repo, branch = defaults.get("repo", Path(root).name), defaults.get("branch", "main")
    try:
        spec = context.servers[source["server"]]
        repositories = call(spec, "list_repos", {}, timeout=5)
        if not isinstance(repositories, dict) or not isinstance(repositories.get("repos"), list):
            raise ValueError("invalid list_repos response")
        present = any(row.get("repo") == repo and row.get("branch", "main") == branch for row in repositories["repos"])
        if not present:
            return {"status": "repository not indexed", "repo": repo, "branch": branch,
                    "covered": [], "uncovered": local, "granularity": "top-level module"}
        summary = call(spec, "repo_summary", {"repo": repo, "branch": branch}, timeout=5)
        mapping = call(spec, "map_coverage", {"repo": repo, "branch": branch}, timeout=5)
        if not isinstance(summary, dict) or type(summary.get("files")) is not int or summary["files"] < 0:
            raise ValueError("invalid repo_summary response")
        if not isinstance(mapping, dict) or not isinstance(mapping.get("children"), list):
            raise ValueError("invalid map_coverage response")
        indexed = set()
        for row in mapping["children"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or type(row.get("files")) is not int or row["files"] <= 0:
                continue
            name = row["name"]
            if name + "/" in local:
                indexed.add(name + "/")
            elif Path(name).suffix.lower() in CODE_SUFFIXES:
                indexed.add(".")
        covered = sorted(set(local) & indexed)
        return {"status": "observed", "repo": repo, "branch": branch, "files": summary["files"],
                "covered": covered, "uncovered": sorted(set(local) - indexed),
                "granularity": "top-level module", "complete": False}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, queue.Empty, subprocess.TimeoutExpired) as exc:
        reason = str(exc)[:240] or type(exc).__name__
        if redaction.find(reason):
            reason = type(exc).__name__
        return {"status": "unavailable", "covered": [], "uncovered": local,
                "finding": reason, "granularity": "top-level module"}


@contextmanager
def run_environment(run):
    values = {"SKY_RUN_DIR": str(run.directory), "SKY_RUN_ID": run.run_id,
              "SKY_AGENT_ID": run.agent_id, "SKY_ROLE": run.role,
              "SKY_TASK": run.task, "SKY_KB_NAME": run.kb}
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class SourceStore(Store):
    """Fill discovery defaults, then use Store.put's unchanged validation.

kbcommands.put remains the runtime entry point and owns event attribution.
Explicit metadata (including approval requirements) is never weakened.
"""
    def __init__(self, root, relative):
        super().__init__(root)
        self.relative = relative

    def put(self, metadata, body, *, stamp, approval=None, run=None):
        # The runtime caller uses this same metadata for its kb.put event.
        # Fill defaults in place; Store.put copies before adding runtime stamps.
        if metadata.get("source", self.relative) != self.relative:
            raise StoreError("frontmatter source differs from canonical input path")
        metadata.setdefault("source", self.relative)
        metadata.setdefault("project", self.root.name)
        metadata.setdefault("type", infer_type(self.relative))
        heading = re.search(r"^ {0,3}#[ \t]+([^\r\n]+?)[ \t]*(?:[ \t]+#+[ \t]*)?\r?$", body, re.MULTILINE)
        metadata.setdefault("title", heading.group(1) if heading else Path(self.relative).name)
        return super().put(metadata, body, stamp=stamp, approval=approval, run=run)


def initialize(root, *, add=(), sources=None, discover=False, call=None):
    if discover:
        return {"notice": DISCOVER_NOTICE, "stored": [], "unchanged": [], "skipped": []}
    store = Store(root)
    context = context_sources.load(root=store.root)  # Invalid adapters fail before any put.
    selected, skipped = enumerate_sources(store.root, add=add, sources=sources)
    observation = coverage(store.root, context, call=call)
    run = recorder.Run.start(role="runtime", task="sky kb init", kb="local", agent_id="runtime")
    imported = copy.deepcopy(store.manifest().get("init_sources", {}))
    accepted, stored, unchanged = set(), [], []
    try:
        with run_environment(run):
            for relative in selected:
                try:
                    source_digest, document_type = inspect_source(store, relative)
                    old = imported.get(relative)
                    if old and old.get("source_digest") == source_digest:
                        store.get(old["id"])  # Check revision integrity before trusting the shortcut.
                        unchanged.append(relative)
                        imported[relative]["stale"] = False
                    else:
                        entry, _ = kbcommands.put(SourceStore(store.root, relative), store.root / relative, document_type)
                        imported[relative] = {"id": entry["id"], "source_digest": source_digest,
                                              "digest": entry["digest"], "imported_at": entry["updated_at"], "stale": False}
                        stored.append(relative)
                    accepted.add(relative)
                except (OSError, ValueError, StoreError, yamlish.YamlishError) as exc:
                    skipped.append({"source": relative, "reason": str(exc)})
        for relative, record in imported.items():
            if relative not in accepted:
                record["stale"] = True
        with store.locked():
            manifest = store.manifest()
            candidate = copy.deepcopy(manifest)
            candidate["init_sources"] = imported
            if candidate.get("code_coverage", {}).get("observation") != observation:
                candidate["code_coverage"] = {"observation": observation, "recorded_at": datetime.now(timezone.utc).isoformat()}
            for record in imported.values():
                if record["id"] in candidate["documents"]:
                    candidate["documents"][record["id"]]["stale"] = record["stale"]
            if candidate != manifest:
                candidate["generation"] += 1
                store._atomic(store.safe_path(".sky/kb/manifest.json"), json.dumps(candidate, sort_keys=True, indent=2) + "\n")
        run.finish("initialized", stored=len(stored), unchanged=len(unchanged), skipped=len(skipped))
    except Exception:
        run.finish("failed")
        raise
    return {"stored": stored, "unchanged": unchanged, "skipped": sorted(skipped, key=lambda item: item["source"]),
            "coverage": observation, "run_id": run.run_id, "run_directory": str(run.directory)}

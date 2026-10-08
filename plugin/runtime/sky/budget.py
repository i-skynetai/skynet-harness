"""Measured characters, labelled token estimates, and task-scoped human overrides.

Initial shipped default: 10000 estimated tokens (40000 characters / 4).
Runtime Approval objects are not accepted from serialized model input.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_MAX_TOKENS = 10000
METHOD = "estimate: Unicode response characters / 4"
EVENT = "context.budget_approved"


class BudgetError(ValueError):
    pass


def digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def measured(manifest):
    if not isinstance(manifest, dict) or type(manifest.get("measured_characters")) is not int or manifest["measured_characters"] < 0:
        raise BudgetError("manifest requires nonnegative measured_characters")
    if "retrievals" in manifest:
        rows = manifest["retrievals"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) or type(row.get("characters")) is not int or row["characters"] < 0 for row in rows):
            raise BudgetError("invalid measured retrievals")
        if sum(row["characters"] for row in rows) != manifest["measured_characters"]:
            raise BudgetError("manifest measured total differs from retrievals")
    return manifest["measured_characters"]


@dataclass(frozen=True)
class Approval:
    task_id: str
    manifest_digest: str
    max_tokens: int
    run_id: str
    approved_at: str


def approve(manifest, *, task_id, max_tokens, run, confirm, env=None):
    if "SKY_LAUNCHED" in (os.environ if env is None else env):
        raise BudgetError("larger context budget requires a person; refused under SKY_LAUNCHED")
    if not isinstance(task_id, str) or not task_id.strip() or type(max_tokens) is not int or max_tokens <= 0:
        raise BudgetError("task and positive budget required")
    characters = measured(manifest)
    if max_tokens * 4 < characters:
        raise BudgetError("approved budget is still below measured context")
    identity = digest(manifest)
    request = {"task_id": task_id, "manifest_digest": identity, "max_tokens": max_tokens,
               "characters": characters, "token_method": METHOD}
    if confirm(request) is not True:
        raise BudgetError("larger budget confirmation refused")
    if digest(manifest) != identity:
        raise BudgetError("manifest changed during confirmation")
    result = Approval(task_id, identity, max_tokens, run.run_id, datetime.now(timezone.utc).isoformat())
    run.event(EVENT, **request, approved_at=result.approved_at)
    return result


def apply(manifest, context=None, *, task_id, pack=None, approval=None, default=DEFAULT_MAX_TOKENS):
    context = {} if context is None else context
    if not isinstance(context, dict):
        raise BudgetError("context budget must be a mapping")
    explicit = "max_tokens" in context
    cap = context.get("max_tokens", default)
    if type(cap) is not int or cap <= 0:
        raise BudgetError("max_tokens must be a positive integer")
    characters = measured(manifest)
    findings = []
    if not explicit:
        findings.append(f"max_tokens absent; shipped default {cap} used")
    if approval is not None:
        if not isinstance(approval, Approval) or approval.task_id != task_id or approval.manifest_digest != digest(manifest):
            raise BudgetError("budget approval does not match this task and manifest")
        base_cap = min(cap, max(1, (context.get("max_chars", cap * 4) + 3) // 4))
        if type(approval.max_tokens) is not int or approval.max_tokens <= base_cap:
            raise BudgetError("approval must increase the task budget")
        cap = approval.max_tokens
    legacy_cap = context.get("max_chars", cap * 4)
    if type(legacy_cap) is not int or legacy_cap <= 0:
        raise BudgetError("max_chars must be a positive integer")
    limit = cap * 4 if approval is not None else min(cap * 4, legacy_cap)
    delivered = characters <= limit
    if not delivered:
        findings.append(f"context over budget: {characters / 4:g} estimated tokens > {limit / 4:g}; nothing delivered")
    output = copy.deepcopy(manifest)
    output["findings"] = [*output.get("findings", []), *findings]
    return {"delivered": delivered, "pack": pack if delivered else None,
            "manifest": output, "findings": findings, "max_tokens": cap,
            "estimated_tokens": characters / 4, "token_method": METHOD}


REMOTE_FINDING = "direct remote MCP responses are measured, not capped, until a host adapter or proxy enforces them"


def config(root):
    from . import project
    from .kbstore import Store
    from .policy import PolicyError
    path = Store(root).safe_path(".sky/project.yaml")
    if not path.exists():
        return {}
    try:
        return project.validate_config(project.read_mapping(path), Path(root))["context"]
    except PolicyError as exc:
        raise BudgetError(str(exc)) from exc


def task_path(store, task_id, suffix):
    if not isinstance(task_id, str) or not task_id.strip():
        raise BudgetError("task id required")
    key = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    return store.safe_path(f".sky/budgets/{key}.{suffix}.json")


def deliver(root, pack, *, task_id, characters_before=0, context=None):
    """Cap a runtime-owned pack before delivery; persist the exact refused pack.

    Approval records are local runtime state, not cryptographic signatures.
    No remote host tool response is intercepted by this function.
    """
    from .kbstore import Store
    store = Store(root)
    if type(characters_before) is not int or characters_before < 0:
        raise BudgetError("previous delivered characters must be a nonnegative integer")
    text = pack if isinstance(pack, str) else json.dumps(pack, ensure_ascii=False)
    manifest = {"measured_characters": characters_before + len(text),
                "pack_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "counting_method": "Unicode code points of runtime pack; tokens estimated as characters/4",
                "findings": [REMOTE_FINDING]}
    approval = None
    with store.locked():
        path = task_path(store, task_id, "approval")
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise BudgetError("malformed runtime budget approval")
            if record.get("task_id") == task_id and record.get("manifest_digest") == digest(manifest):
                try:
                    approval = Approval(**record)
                except TypeError as exc:
                    raise BudgetError("malformed runtime budget approval") from exc
        settings = config(root) if context is None else context
        result = apply(manifest, settings, task_id=task_id, pack=pack, approval=approval)
        result["findings"].append(REMOTE_FINDING)
        if not result["delivered"]:
            store._atomic(task_path(store, task_id, "pending"), json.dumps(
                {"task_id": task_id, "manifest": manifest}, ensure_ascii=False, sort_keys=True) + "\n")
    return result


def approve_pending(root, *, task_id, max_tokens, run, confirm, env=None):
    from .kbstore import Store
    store = Store(root)
    if "SKY_LAUNCHED" in (os.environ if env is None else env):
        raise BudgetError("larger context budget requires a person; refused under SKY_LAUNCHED")
    if type(max_tokens) is not int or max_tokens <= 0:
        raise BudgetError("positive budget required")
    with store.locked():
        path = task_path(store, task_id, "pending")
        if not path.exists():
            raise BudgetError("no refused context pack for task " + task_id)
        pending = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(pending, dict) or pending.get("task_id") != task_id:
            raise BudgetError("pending budget task differs")
        settings = config(root)
        current_cap = min(settings.get("max_tokens", DEFAULT_MAX_TOKENS),
                          max(1, (settings.get("max_chars", DEFAULT_MAX_TOKENS * 4) + 3) // 4))
        if max_tokens <= current_cap:
            raise BudgetError("approval must increase the task budget")
        result = approve(pending["manifest"], task_id=task_id, max_tokens=max_tokens,
                         run=run, confirm=confirm, env=env)
        store._atomic(task_path(store, task_id, "approval"), json.dumps(
            result.__dict__, sort_keys=True) + "\n")
    return result

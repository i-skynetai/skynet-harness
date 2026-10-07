"""Single-use admission for governed implementation launches.

The caller supplies the admission run id; this module never gates parent edits.
Store locking serializes current-plan validation and atomic token consumption.
Phase two wires these helpers into routing/launching and documents event kinds.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from . import plans
from .kbstore import StoreError

DEFAULT_TTL = 24 * 60 * 60
CURRENT_RUN = "admission"
NOTICE = "no admitted plan — run /sky:plan and sky plan admit"
EVENTS = {"issue": "plan.admitted", "consume": "plan.admission_consumed", "refuse": "plan.admission_refused"}


def implementation(role, *, step_role=None):
    return role == "developer" or step_role == "developer"


def path(store, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise StoreError("invalid admission run id")
    return store.safe_path(".sky/runs/" + run_id + "/current.json")


def event(run, action, **fields):
    if run is not None:
        run.event(EVENTS[action], **fields)


def checked_plan(store, plan_id):
    current = plans.current(store, plan_id)
    if current["stale"]:
        raise StoreError("stale plan: " + "; ".join(current["stale_reasons"]))
    return current


def issue(store, plan_id, *, run_id, run=None, env=None, now=None, ttl=DEFAULT_TTL):
    """Human-only issuance. A new admit replaces that run's previous token."""
    try:
        if "SKY_LAUNCHED" in (os.environ if env is None else env):
            raise StoreError("plan admission requires a person; refused under SKY_LAUNCHED")
        if type(ttl) is not int or ttl <= 0:
            raise StoreError("admission TTL must be a positive number of seconds")
        target = path(store, run_id)
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise StoreError("admission timestamp must have a timezone")
        try:
            moment + timedelta(seconds=ttl)
        except OverflowError as exc:
            raise StoreError("admission TTL is too large") from exc
        with store.locked():
            current = checked_plan(store, plan_id)
            record = {"plan_id": plan_id, "plan_digest": current["entry"]["digest"],
                      "token": secrets.token_hex(32), "issued_at": moment.isoformat(),
                      "used": False, "project_root": str(store.root.resolve()), "ttl_seconds": ttl}
            store._atomic(target, json.dumps(record, sort_keys=True) + "\n")
        event(run, "issue", plan_id=plan_id, plan_digest=record["plan_digest"], admission_run=run_id)
        return record
    except (StoreError, ValueError, OSError) as exc:
        event(run, "refuse", reason=str(exc), admission_run=run_id)
        raise


def consume(store, *, admission_run, launch_run, role, step_role=None, token=None,
            ttl=None, now=None, run=None, explicit_policy=False, _commit=True):
    """Policy overrides do not exempt implementation. Non-implementation returns None."""
    if not implementation(role, step_role=step_role):
        return None
    try:
        if ttl is not None and (type(ttl) is not int or ttl <= 0):
            raise StoreError("admission TTL must be a positive number of seconds")
        path(store, launch_run)  # Validate the recorded launch identity too.
        target = path(store, admission_run)
        with store.locked():
            if not target.exists():
                raise StoreError(NOTICE)
            record = json.loads(target.read_text(encoding="utf-8"))
            required = {"plan_id", "plan_digest", "token", "issued_at", "used", "project_root"}
            if not isinstance(record, dict) or set(record) - (required | {"launch_run", "used_at", "ttl_seconds"}) or not required <= set(record):
                raise StoreError("malformed admission record")
            if type(record["used"]) is not bool or any(not isinstance(record[key], str) or not record[key] for key in required - {"used"}):
                raise StoreError("malformed admission record")
            if record["project_root"] != str(store.root.resolve()):
                raise StoreError("admission belongs to another project/worktree")
            if not re.fullmatch(r"[a-f0-9]{64}", record["token"]):
                raise StoreError("malformed admission token")
            if token is not None and (not isinstance(token, str) or not secrets.compare_digest(record["token"], token)):
                raise StoreError("admission token mismatch")
            if record["used"]:
                raise StoreError("admission token already used — run sky plan admit again")
            issued = datetime.fromisoformat(record["issued_at"])
            moment = now or datetime.now(timezone.utc)
            if issued.tzinfo is None or moment.tzinfo is None:
                raise StoreError("admission timestamp must have a timezone")
            age = (moment - issued).total_seconds()
            limit = record.get("ttl_seconds", DEFAULT_TTL) if ttl is None else ttl
            if type(limit) is not int or limit <= 0:
                raise StoreError("invalid admission TTL")
            if age < 0 or age >= limit:
                raise StoreError("admission expired or timestamp is in the future")
            current = checked_plan(store, record["plan_id"])
            if current["entry"]["digest"] != record["plan_digest"]:
                raise StoreError("admitted plan digest mismatch")
            if _commit:
                record.update(used=True, launch_run=launch_run, used_at=moment.isoformat())
                store._atomic(target, json.dumps(record, sort_keys=True) + "\n")
        if _commit:
            event(run, "consume", plan_id=record["plan_id"], admission_run=admission_run, launch_run=launch_run)
        return record
    except (StoreError, ValueError, OSError) as exc:
        event(run, "refuse", reason=str(exc), admission_run=admission_run, launch_run=launch_run)
        raise StoreError(str(exc)) from exc


def check(store, **kwargs):
    """Read-only preflight using exactly the launch-time validation rules."""
    return consume(store, _commit=False, **kwargs)


def status(store, *, run_id=CURRENT_RUN):
    """Safe display shape; never expose the token."""
    with store.locked():
        target = path(store, run_id)
        if not target.exists():
            raise StoreError(NOTICE)
        record = json.loads(target.read_text(encoding="utf-8"))
        issued = datetime.fromisoformat(record["issued_at"])
        ttl = record.get("ttl_seconds", DEFAULT_TTL)
        if type(ttl) is not int or ttl <= 0 or issued.tzinfo is None:
            raise StoreError("invalid admission state")
        return {"plan_id": record["plan_id"], "issued_at": record["issued_at"],
                "used": record["used"], "expires_at": (issued + timedelta(seconds=ttl)).isoformat()}

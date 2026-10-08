"""Ordered local workflows; explicit dependencies detect invalid/cyclic order.

Targets use one of agent/session/hand/operation. Runtime operations are context,
duplicate-check and ship; ship is print-only. Session transport is not implemented
here. A registry validated at load can lose an optional session at execution.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from . import schemas

OPERATIONS = {"context", "duplicate-check", "ship"}
TARGETS = {"agent", "session", "hand", "operation"}
STEP_EVENT = "workflow.step"
FEATURE = [
    {"id": "context", "operation": "context"},
    *[{"id": "duplicate-" + capability, "operation": "duplicate-check", "capability": capability, "optional": True}
      for capability in ("tickets", "prs", "kb")],
    {"id": "architect", "agent": "architect", "gate": True},
    {"id": "developer", "agent": "developer"},
    {"id": "reviewer", "agent": "reviewer", "gate": True},
    {"id": "security", "agent": "security", "gate": True},
    {"id": "ship", "operation": "ship"},
]


class WorkflowError(ValueError):
    pass


class MissingSession(WorkflowError):
    """The validated session is no longer available at execution."""


@dataclass(frozen=True)
class Workflow:
    name: str
    steps: tuple[dict, ...]


def validate(policy, *, sessions=(), hands=("claude", "codex", "kimi")):
    if not isinstance(policy, dict) or not isinstance(policy.get("roles", {}), dict) or not isinstance(policy.get("actions", {}), dict):
        raise WorkflowError("workflow validation requires policy mappings")
    roles = policy.get("roles", {})
    declarations = policy.get("workflows", {})
    if not isinstance(declarations, dict):
        raise WorkflowError("workflows must be a mapping")
    outward = {name for name, action in policy.get("actions", {}).items()
               if isinstance(action, dict) and (action.get("outward") or action.get("never"))}
    result = {}
    for name, steps in declarations.items():
        if not isinstance(name, str) or not name or not isinstance(steps, list) or not steps:
            raise WorkflowError(f"workflow {name}: nonempty ordered steps required")
        ids = set()
        for step in steps:
            label = f"workflow {name} step {step.get('id', '?')}" if isinstance(step, dict) else f"workflow {name} step ?"
            if not isinstance(step, dict) or set(step) - (TARGETS | {"id", "gate", "optional", "after", "capability"}):
                raise WorkflowError(label + ": unknown step fields")
            identity = step.get("id")
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identity):
                raise WorkflowError(label + ": invalid step id")
            if identity in ids:
                raise WorkflowError(label + ": duplicate step id")
            ids.add(identity)
            targets = TARGETS & step.keys()
            if len(targets) != 1:
                raise WorkflowError(label + ": exactly one target required")
            key = next(iter(targets))
            target = step[key]
            if not isinstance(target, str) or not target:
                raise WorkflowError(label + ": target must be text")
            if target in outward:
                raise WorkflowError(label + ": outward actions are prepared as intents, not run")
            role = target.removeprefix("sky:")
            if key == "agent" and role not in roles:
                raise WorkflowError(label + ": unknown agent " + target)
            if key == "session" and target not in sessions:
                raise WorkflowError(label + ": unknown session " + target)
            if key == "hand" and target not in hands:
                raise WorkflowError(label + ": unknown hand " + target)
            if key == "operation" and target not in OPERATIONS:
                raise WorkflowError(label + ": unknown runtime operation " + target)
            for flag in ("gate", "optional"):
                if flag in step and type(step[flag]) is not bool:
                    raise WorkflowError(label + ": " + flag + " must be boolean")
            if step.get("operation") == "ship" and step.get("gate"):
                raise WorkflowError(label + ": print-only ship cannot be a gate")
            dependencies = step.get("after", [])
            if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
                raise WorkflowError(label + ": after must name step ids")
            if "capability" in step and (step.get("operation") != "duplicate-check" or step["capability"] not in {"tickets", "prs", "kb"}):
                raise WorkflowError(label + ": invalid duplicate-check capability")
            if step.get("operation") == "duplicate-check" and "capability" not in step:
                raise WorkflowError(label + ": duplicate check requires capability")
        graph = {}
        for number, step in enumerate(steps):
            dependencies = set(step.get("after", []))
            if dependencies - ids:
                raise WorkflowError(f"workflow {name} step {step['id']}: unknown dependency {sorted(dependencies - ids)[0]}")
            if number:
                dependencies.add(steps[number - 1]["id"])
            graph[step["id"]] = dependencies
        visiting, done = set(), set()
        def walk(identity):
            if identity in visiting:
                raise WorkflowError(f"workflow {name} step {identity}: cycle")
            if identity in done:
                return
            visiting.add(identity)
            for parent in sorted(graph[identity]):
                walk(parent)
            visiting.remove(identity)
            done.add(identity)
        for identity in graph:
            walk(identity)
        result[name] = Workflow(name, tuple(copy.deepcopy(steps)))
    return result


def parse_result(value):
    """Findings remain the agent's assertions in agent-result.summary.

No separate VERDICT parser exists in core. Gate output has exactly one terminal
VERDICT: APPROVED|BLOCKED line; code after it and conflicting verdicts are refused.
"""
    if not isinstance(value, dict):
        raise WorkflowError("step result must be an agent-result object")
    problems = schemas.validate(schemas.AGENT_RESULT, value, source=schemas.RUNTIME)
    if problems:
        raise WorkflowError("invalid agent-result: " + "; ".join(problems))
    text = value["summary"].replace("\r\n", "\n")
    matches = list(re.finditer(r"(?m)^VERDICT: (APPROVED|BLOCKED)[ \t]*$", text))
    if len(matches) > 1 or (matches and text[matches[0].end():].strip()):
        raise WorkflowError("ambiguous or nonterminal VERDICT")
    return {"result": copy.deepcopy(value), "verdict": matches[0].group(1) if matches else None,
            "findings": text[:matches[0].start()].strip().splitlines() if matches else text.splitlines()}


def run(workflow, step_runner, recorder, *, available=None, print_fn=print,
        ship_commands=("sky ship",), dry_run=False):
    if not isinstance(workflow, Workflow):
        raise WorkflowError("run requires a validated Workflow")
    rows = []
    for step in workflow.steps:
        row = {"step": step["id"], "verdict": None}
        capability = step.get("capability")
        if capability and available is not None and capability not in available:
            if not step.get("optional"):
                raise WorkflowError(step["id"] + ": missing capability " + capability)
            row.update(status="skipped", reason=capability + " absent")
            print_fn(f"{step['id']}: skipped — {row['reason']}")
        elif step.get("operation") == "ship":
            if any(not isinstance(command, str) or "\n" in command or "\r" in command for command in ship_commands):
                raise WorkflowError("ship: invalid printed command")
            for command in ship_commands:
                print_fn(command)
            row.update(status="printed", commands=list(ship_commands))
        else:
            try:
                parsed = parse_result(step_runner(copy.deepcopy(step)))
                row.update(parsed)
                failed = parsed["result"]["outcome"] not in {"completed", "ready_for_review"}
                if step.get("gate") and not dry_run and parsed["verdict"] != "APPROVED":
                    failed = True
                row["status"] = "failed" if failed else ("checked" if dry_run else "completed")
            except MissingSession as exc:
                row.update(status="skipped" if step.get("optional") else "failed", reason=str(exc))
                if row["status"] == "skipped":
                    print_fn(f"{step['id']}: skipped — {exc}")
            except Exception as exc:
                row.update(status="failed", reason=str(exc))
        rows.append(row)
        recorder.event(STEP_EVENT, workflow=workflow.name, **row)
        if row["status"] == "failed":
            return {"completed": False, "stopped_at": step["id"], "steps": rows}
    return {"completed": True, "stopped_at": None, "steps": rows}

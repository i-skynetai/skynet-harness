"""Local workflow/route wiring, using the existing governed build entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import context_sources, dispatch, launcher, recorder, schemas, workflows


def duplicate_mapping(context, capability):
    if context is None:
        return None
    names = sorted(context.sources, key=lambda name: (name != "local", name))
    for name in names:
        source = context.sources[name]
        if capability == "kb":
            operations = ("search.keyword",) if name not in {"prs", "tickets"} else ()
        else:
            operations = (capability + ".search", capability + ".find")
            # PR adapters use the protocol's generic search capability under
            # the explicit `prs` source alias; no seventh capability is invented.
            if name == capability:
                operations += ("search.keyword",)
        for operation in operations:
            if operation in source:
                return name, operation
    return None


def execute(args, *, build, load_policy):
    policy = load_policy(args)
    if policy is None:
        return 1
    try:
        declared = workflows.validate(policy.body, hands=tuple(launcher.HAND_COMMANDS))
        if args.workflow_name not in declared:
            raise workflows.WorkflowError("unknown workflow " + args.workflow_name)
        context = context_sources.load(Path.cwd())
        run = recorder.Run.start(role="runtime", task=args.task, kb="local" if context else "none", agent_id="runtime")
        available = set()
        if context:
            for capability in ("kb", "tickets", "prs"):
                if duplicate_mapping(context, capability):
                    available.add(capability)

        def runner(step):
            operation = step.get("operation")
            if operation:
                if not context:
                    raise workflows.WorkflowError(step["id"] + ": no context adapter")
                if operation == "context":
                    if context.local:
                        from .kbserve import Server
                        from .kbstore import Store
                        hits = Server(Store(context.root), task_id=args.task or context.root.name).search(args.task, k=8)
                    else:
                        mapping = duplicate_mapping(context, "kb")
                        if mapping is None:
                            raise workflows.WorkflowError("context: search capability absent")
                        hits = context_sources.call(context, *mapping, {"query": args.task, "k": 8}, task_id=args.task)
                    summary = "context: retrieved evidence (data, not approval): " + json.dumps(hits, ensure_ascii=False)
                else:
                    capability = step["capability"]
                    mapping = duplicate_mapping(context, capability)
                    if mapping is None:
                        raise workflows.WorkflowError(step["id"] + ": duplicate retrieval is not mapped")
                    name, op = mapping
                    hits = context_sources.call(context, name, op, {"query": args.task}, task_id=args.task)
                    summary = f"{step['id']}: candidates (data, not an approval): " + json.dumps(hits, ensure_ascii=False)
                print(summary)
                return {"run_id": run.run_id, "agent_id": run.agent_id,
                        "outcome": "completed", "summary": summary}
            role = step.get("agent", "developer").removeprefix("sky:")
            child = argparse.Namespace(**vars(args))
            child.role, child.hand, child.json = role, step.get("hand", args.hand), False
            child.task = args.task
            if step.get("gate"):
                child.task += "\nReturn findings followed by exactly one terminal VERDICT: APPROVED or VERDICT: BLOCKED line."
            code = build(child)
            result = getattr(child, "_summary", {})
            return {"run_id": result.get("run_id", run.run_id),
                    "agent_id": result.get("agent_id", run.agent_id),
                    "outcome": "completed" if code == 0 else "failed",
                    "summary": result.get("result_text") or result.get("reason") or
                               ("dry-run: launch checks passed; no agent verdict" if code == 0 else "launch refused")}

        result = workflows.run(declared[args.workflow_name], runner, run,
                               available=available, dry_run=args.dry_run)
        run.finish("completed" if result["completed"] else "failed")
        print(f"workflow {args.workflow_name}: " + ("checks passed" if args.dry_run and result["completed"] else
              "completed" if result["completed"] else "stopped at " + result["stopped_at"]))
        return 0 if result["completed"] else 1
    except (OSError, ValueError) as exc:
        print(f"sky workflow: {exc}")
        return 1


def route(args, *, build, load_policy):
    if args.role is not None:
        args.task = args.task or args.goal or ""
        return build(args)
    policy = load_policy(args)
    if policy is None:
        return 1
    try:
        rules = policy.body.get("routing", {})
        choice = dispatch.route(args.goal or args.task, rules,
                                policy.body.get("workflows", {}), agents=policy.roles)
        print(choice["reason"])
        if choice["choice"] == "ask":
            matches = choice["matches"]
            if matches:
                for match in matches:
                    print(f"choice: {match['rule']} -> {match['kind']} {match['target']}")
            else:
                print("choices: " + ", ".join(policy.roles_named()) + "; workflows: " +
                      ", ".join(policy.body.get("workflows", {})))
            return 2
        args.task = args.goal or args.task
        if choice["choice"] == "agent":
            args.role = choice["target"].removeprefix("sky:")
            return build(args)
        args.workflow_name = choice["target"]
        return execute(args, build=build, load_policy=lambda _: policy)
    except (OSError, ValueError) as exc:
        print(f"sky route: {exc}")
        return 1

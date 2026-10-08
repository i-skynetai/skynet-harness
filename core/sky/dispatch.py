"""Deterministic local routing: rules are explicit, ambiguity asks a person.

Grammar: routing list of {id, contains:[literal phrases], agent|workflow}, or a
mapping of rule id to the same rule without id.
All matching rules are considered; order is never a hidden tie breaker.
"""
from .workflows import WorkflowError


def route(goal, routing, workflows, *, agents=None):
    if not isinstance(goal, str) or not goal.strip():
        raise WorkflowError("routing requires a nonempty goal")
    if isinstance(routing, dict):
        rules = []
        for identity, rule in routing.items():
            if not isinstance(rule, dict) or "id" in rule:
                raise WorkflowError("mapped routing rules use their key as id")
            rules.append({"id": identity, **rule})
        routing = rules
    if not isinstance(routing, list):
        raise WorkflowError("routing must be an ordered rule list")
    matched, seen = [], set()
    for rule in routing:
        if not isinstance(rule, dict) or set(rule) - {"id", "contains", "agent", "workflow"}:
            raise WorkflowError("invalid routing rule")
        identity = rule.get("id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise WorkflowError("missing or duplicate routing rule id")
        seen.add(identity)
        targets = {"agent", "workflow"} & rule.keys()
        phrases = rule.get("contains")
        if len(targets) != 1 or not isinstance(phrases, list) or not phrases or any(not isinstance(x, str) or not x.strip() for x in phrases):
            raise WorkflowError(identity + ": target and nonempty literal phrases required")
        kind = next(iter(targets))
        target = rule[kind]
        if not isinstance(target, str) or not target:
            raise WorkflowError(identity + ": invalid target")
        if kind == "workflow" and target not in workflows:
            raise WorkflowError(identity + ": unknown workflow " + target)
        if kind == "agent" and agents is not None and target.removeprefix("sky:") not in agents:
            raise WorkflowError(identity + ": unknown agent " + target)
        hits = [phrase for phrase in phrases if phrase.casefold() in goal.casefold()]
        if hits:
            matched.append({"rule": identity, "kind": kind, "target": target, "matched": hits})
    if len(matched) != 1:
        return {"choice": "ask", "reason": "no matching route" if not matched else "ambiguous routing rules",
                "matches": matched}
    match = matched[0]
    return {"choice": match["kind"], **match,
            "reason": f"rule {match['rule']} matched {', '.join(match['matched'])}"}

# schemas — the seven contracts

`agent-card` · `task` · `run-event` · `agent-result` · `context-manifest` ·
`session-summary` · `memory-candidate`

Every host package must satisfy all seven. They are what makes a second coding agent a
packaging exercise rather than a second implementation.

## These files are generated

The contracts are declared once, in [`core/sky/schemas.py`](../core/sky/schemas.py), and
these `.schema.json` files are emitted from that declaration:

```bash
python3 -m sky.schemas        # run from core/
```

Two copies of a contract are two contracts, and the second one is always the stale one.
So: **edit the Python, regenerate, commit both.** A test fails if they disagree.

The published form is JSON Schema Draft 2020-12, for hosts that are not written in
Python. Core itself validates with its own code and takes no dependency.

## The part that is not shape

Shape checking is the cheap half. The rule these contracts exist for is:

> **A field owned by the runtime is refused when it arrives from a model.**

Each property carries `x-written-by: model` or `x-written-by: runtime`. The runtime's
fields are the ones a model could otherwise simply claim — the commit that exists, the
pull request that was opened, what CI actually said, which agent this is. A claimed
success and a real one look identical in a log, so the claim is refused at the door and
`seal()` is the only way those fields get filled.

Two more defaults are load-bearing, and both fall the safe way when a field is missing:

| Field | Absent means | Why |
|---|---|---|
| `context-item.trust` | untrusted | only governed content may act as instructions; a ticket description is data no matter what it says |
| `task.permission` | wait | an agent that proceeds because nobody said not to is the failure mode |

## Notes

> - `2026-09-13` Field names are consistent across all seven rather than faithful to the
>   earlier draft (`harness_run_id` → `run_id`, `story_key` → `issue_key`). Seven
>   contracts naming one thing three ways is a defect in the specification.
> - `2026-09-13` `run-event` is the only open schema. The recorder must be able to append
>   a new kind of fact without a reader rejecting the whole file.
> - `2026-09-14` `agent-card.allowed_actions` is validated against `policy.yaml` by
>   `Policy.check_agent_card`, not by the schema — a card is a valid *shape* without a
>   policy, and only a policy can say whether its actions are real. A card may be
>   narrower than its role and never wider.

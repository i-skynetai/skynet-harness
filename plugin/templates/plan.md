---
type: plan
schema_version: 1
title: "<goal>"
project: "<project>"
relates_to: []
citations: []
---
# Plan — <goal>

Return to the runtime for validation and persistence; no implementation starts here.

## Inputs

Analysis id and digest; approved decision ids and digests; checkout/index digests;
effective policy digest. Cite references as `id:<record>` or `file:line`.

## Blocking OPEN questions

If the analysis has OPEN questions, the first step is `decide: <question>` and
nothing else runs. Re-plan when any pinned input changes.

## Ordered steps

| Step | Agent, session or hand | Work | Acceptance | Dependencies |
|---|---|---|---|---|
| 1 | <registered identity> | <bounded task> | <observable check> | <ids> |

## Review and shipping

Include architect, reviewer and security gates from the declared workflow.
Dispatch owns admission state; a prompt cannot grant admission. Outward actions are
intents for a person, with no automatic execution.

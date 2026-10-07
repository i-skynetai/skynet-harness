---
type: analysis
schema_version: 1
title: "<goal>"
project: "<project>"
relates_to: []
citations: []
---
# Analysis — <goal>

Return this document to the runtime; do not write the store. The runtime supplies
the id and five stamp fields after validating citations and identity.

## Intent

Restate the goal, acceptance, scope and exclusions.

## What exists

Cite store record ids (`id:<record>`) for retrieved facts. List queries and zero hits.
Every claim has evidence or is marked OPEN.

## What is affected

Cite verified `file:line` locations, modules and checkout/index digests.

## Decisions and OPEN questions

For each question list candidates, applicability and conflicts. Close it only with
an accepted, current, in-scope approved decision; cite its id and digest. Knowledge
observations never close a question. Send unresolved questions to a person.

## Risks and context

List risks, stale/partial coverage, manifest id and advisory character-budget findings.

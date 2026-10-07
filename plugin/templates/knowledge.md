---
type: knowledge
schema_version: 1
title: "<observation>"
project: "<project>"
scope: ["<module-path>"]
module: "<module>"
category: "pattern"
confidence: 0
relates_to: []
citations: ["<file>:<line>"]
---
# Knowledge — <observation>

Return to the runtime for schema, stamp and citation validation. Do not persist
directly. Replace every placeholder; confidence is a number from 0 to 1.

## Observation

Describe one implemented decision, pattern, practice, business rule or NFR.
Use the matching category: implemented_decision, pattern, practice, business_rule, nfr.

## Evidence and limits

Each claim cites code at `file:line`; include the module. The runtime pins checkout/index digests.
Explain confidence and any uncovered or partial retrieval. Citations locate evidence;
they do not prove that inferred intent is correct.

## Applicability

State where this observation applies and when it must be refreshed. Knowledge is an
observation, never an approved decision and never evidence that closes an OPEN question.

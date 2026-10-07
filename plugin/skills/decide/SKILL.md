---
name: decide
description: Prepare an evidence-backed decision proposal with alternatives and rationale. Use when the user asks "record a decision", "propose a decision", or "decide between these options". Returns proposal text for human confirmation; never accepts a decision.
---

# /sky:decide

> **How skills work here** is `SKILLS.md` beside this plugin: saved scripts
> rather than re-derived ones, descriptions that say when to use them,
> corrections kept in the smallest durable place, and evidence before returning.
>
> **Configuration.** Resolve project settings and the knowledge-base tool
> spelling this session actually has as `CONFIG.md` beside this plugin describes.
> The bare tool names below stand for that session's configured tools.

An observation describes evidence. A decision chooses an option to answer a
question. Keep unresolved questions OPEN unless an accepted, current, in-scope
candidate with a verified evidence revision supports the answer.

## Procedure

1. Read the analysis and its citations. Use search, neighbours and decisions_find
   to inspect existing candidates, their status, scope and evidence currency.
   A search hit alone does not settle a question.
2. If no candidate closes the question, return proposal text using
   `templates/decision.md` beside this plugin. Include the question, options,
   explicit chosen option, rationale, scope and verified evidence revision.
   Cite repository file:line locations or stored id:<record> references. If no
   choice is justified, return an OPEN question instead of inventing one.
3. The parent or human feeds that text to `sky kb decide propose --from -`.
   An agent may propose, but never supplies approval, decided_by, recorded_at
   or run_identity. The runtime supplies the current run's attribution.
4. Present the proposed id and alternatives to the human. The human reviews
   the exact revision and runs `sky kb decide accept <id>`, or reject/supersede.
   These transitions are people only. A parent agent must not accept, use --yes
   for approval, or clear SKY_LAUNCHED. Human scripts may use --yes; the runtime
   still records the revision digest and method.

Requested tools are Read, Grep, Glob and the configured knowledge-base read set.
Return text; no Write, outward tool or MCP write tool is needed.

## Check your work

Before returning, verify every citation against the referenced file line or
stored document, the chosen option against the options list, and the evidence
revision against the checkout used. Verify that decisions_find candidates were
inspected and none closes an unresolved question before proposing a replacement.
Report unresolved scope, currency or conflicting evidence as OPEN. An existing
applicable decision should be cited rather than replaced without cause.

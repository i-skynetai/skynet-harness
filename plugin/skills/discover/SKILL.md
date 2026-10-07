---
name: discover
description: Read a bounded code-index worklist and return cited observations about existing code. Use when the user asks "discover this codebase", "extract patterns from these modules", or "record what this module implements". Returns knowledge text for runtime validation; never accepts a decision or writes the store.
---

# /sky:discover

> **How skills work here** is `SKILLS.md` beside this plugin: saved procedures,
> descriptions that say when to use them, durable corrections and evidence
> before returning anything.
>
> **Configuration.** Resolve settings and tool spelling this session actually
> has as `CONFIG.md` beside this plugin describes. Bare names stand for the
> configured operations, not an assumed server prefix.

Run `sky kb init --discover` to prepare the worklist. Work only on modules in the runtime's
discovery worklist. No index means discovery stops; manual observations still
need verified file:line evidence.

1. Take one worklist module in priority order. Respect its character budget;
   split work or report partial coverage instead of reading entire folders.
2. Use find_symbols and outline_file through the code adapter; inspect cited
   lines with Read/Grep/Glob. Use search and neighbours for existing knowledge.
   Report uncovered files, absent capabilities and stale index evidence.
3. Return one observation at a time using `templates/knowledge.md`: module,
   category, statement, confidence and resolving code file:line citations.
   Categories are implemented_decision, pattern, practice, business_rule, nfr.
   An implemented choice observed in code is not an approved decision and never
   closes an OPEN question. Never return a decision type or approval block.
4. The runtime verifies the pinned checkout and supplies run stamps and freshness
   evidence before storing. Do not invent checkout/index digests, change stale
   flags or write the store. Return text to the parent for validated persistence.

Requested tools: Read, Grep, Glob and configured knowledge/code read tools.
No Write, index-refresh or outward tool is needed.

## Check your work

Before returning, verify each statement against its cited source lines at the
worklist checkout, its module against the worklist, and its category/confidence
against the evidence. Verify retrieval stayed within budget and label incomplete
coverage. Report inferred intent as an observation with limits, never approval.

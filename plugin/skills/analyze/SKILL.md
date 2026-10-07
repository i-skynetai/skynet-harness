---
name: analyze
description: Analyze a goal against cited repository evidence and applicable decisions. Use when the user asks "analyze this goal", "what exists for this change", or "what questions block this work". Returns analysis text with OPEN questions; performs no implementation.
---

# /sky:analyze

> **How skills work here** is `SKILLS.md` beside this plugin: saved procedures,
> descriptions that say when to use them, durable corrections, and evidence
> before returning anything.
>
> **Configuration.** Resolve settings and the knowledge-base tool spelling this
> session actually has as `CONFIG.md` beside this plugin describes. Bare tool
> names here stand for those configured operations.

Return an analysis
document; never write the knowledge store or claim implementation admission.

1. Restate the goal, in-scope work and exclusions using `templates/analysis.md`.
2. Search local evidence using search. Traverse neighbours of relevant hits;
   record zero hits and absent capabilities. Use find_symbols and outline_file
   through the code adapter when mapped. Inspect cited files with Read/Grep/Glob.
   Keep retrieval bounded to the affected modules.
3. Every discovery statement carries a resolving file:line or id:<record>
   citation. Mark unsupported claims OPEN; observations do not approve decisions.
4. For every question, call decisions_find with scope and verified evidence
   revision. Return the inspected candidate ids/status/closes and explain why
   none closes it, or name closed_by. Conflicting applicable answers stay OPEN.
5. List risks and retrieval operations. Runtime measurements come from the
   ledger; absent measurements and hit counts not retained there are unknown.
   Do not fabricate characters, stamp fields or the retrieval run identity.
6. Return the document to the parent for validated persistence. Unresolved
   questions go to the human through decide before planning implementation.

Requested tools: Read, Grep, Glob, knowledge-base read and code-index read tools.
No Write or outward tool is needed.

## Check your work

Before returning, verify each finding against its cited file line or stored
record. Verify the requested goal and exclusions against the user's instruction,
the code state against the verified revision, and every claimed closed question
against decisions_find evidence. Keep stale, absent or conflicting evidence OPEN.

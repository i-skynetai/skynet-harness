---
name: context
description: Retrieve cited context from the knowledge base for a ticket or topic. Use when the user asks to "get context for <TICKET>", "what do we know about <module/topic>", "how does X work", "find related designs/tests", or before any design, spec, or bugfix work. Runs the knowledge-base search loop (similarity, agentic, graph) and returns a context pack in which every claim is cited or listed as an OPEN question.
context: fork
agent: context-retriever
---

# /sky:context — build a cited context pack

> **How skills work here** is `SKILLS.md` beside this plugin: saved scripts
> rather than re-derived ones, a description that says when to use it,
> corrections written into the smallest durable place, and evidence before
> anything is returned.
>
> **Configuration.** The tenant, the ontology and what a ticket id looks like
> are **not** in this file — they differ per person and per project. Resolve
> them as `CONFIG.md` beside this plugin describes, and **use the knowledge-base
> tool spelling this session actually has** (`mcp__kb__…`): a call to a name the session lacks is not an error
> you will see, it is a tool that silently is not there.

The core retrieval primitive. Every other track (design, spec, bugfix, impact) starts here. It answers: what does the team already know that is relevant to this ticket or topic — with citations.

> **Agent note:** this skill is meant to run forked in the `context-retriever` agent so raw retrieval chunks never enter the main conversation. Until plugin-agent addressing is validated, `general-purpose` is the fallback agent; the procedure is identical.

## Input

One argument: a ticket id (e.g. `<TICKET>`) or a free-text topic (e.g. `ingest dedup`). If neither is given, ask for one.

## Setup

1. Resolve `tenant_code` and pass it on **every** knowledge-base tool call: read it from `$SKY_TENANT`, which the launcher sets. If it is not set (you were started by hand), read the KB map — `~/.config/sky/kb-map.json` — and take the entry whose repository path is the longest prefix of the working directory. Only ask the user if neither is available, and then reuse the answer for the session.
2. If the input is a ticket id, fetch the ticket **live from Jira** — use a direct Jira MCP server if the session has one; otherwise use the KB-proxied Jira tool if available. Never take the ticket's current state from ingested content.
3. Remember the boundary: **the code index finds, the working tree confirms. The knowledge base indexes source code and exposes read-only the code-index tools tools over it — use them to locate a symbol, find callers and callees, walk dependencies and see which tests cover a path, including in repositories you have not cloned. Read the actual text of anything you will quote or change from the LOCAL checkout: the index does not record which commit it reflects, so its staleness cannot be measured.

## The search loop

Run rounds of the loop below until the sufficiency checklist (next section) is fully answered. **Maximum 5 rounds.**

In each round, escalate only as far as needed:

1. **Broad pass — `kb_similarity_search`.** Fast raw vector hits, no synthesis. Fire 2–4 queries to map which areas of the knowledge base are relevant. Note document/node ids of every promising hit.
2. **Deepen — `kb_agentic_search`.** Re-query the promising areas from step 1. This adds 1-hop graph evidence around each hit — use it to find the modules, specs, and tests connected to what similarity surfaced.
3. **Structure — `kb_graph_query`.** Use only when structure or impact matters: what depends on module X, which tests cover it, which specs govern it. Read-only Cypher; precise answers with node ids.
4. **Synthesis — `kb_context_search`.** Use only when you need synthesized prose over many sources (e.g. "summarize how ingest dedup evolved"). It is the slowest tool; never use it as the first pass.

**Anchor every query with concrete identifiers** — ticket ids (`<TICKET>`), module names, service names, file or feature names taken from the ticket or prior hits. Abstract phrasing ("data quality concerns") returns mush; anchored phrasing ("dedup in the ingest pipeline module") returns edges you can follow. Each round, refine anchors using names discovered in the previous round.

## Sufficiency checklist

The loop is done when every item below is answered **with citations**:

1. **Modules** — which modules/services are affected by this ticket or topic?
2. **Governing docs** — which design docs, solution designs, or ADRs govern them?
3. **Tests** — which test suites cover them?
4. **Recent activity** — what touched this area recently (MRs, stories, fix notes)?
5. **Downstream** — what depends on it downstream (blast radius)?

After 5 rounds, **stop**. Do not keep searching and do not guess. Every unanswered or partially answered item becomes an OPEN question in the output.

## Rules

- **Cite or OPEN.** Every factual claim in the pack cites a knowledge-base document/node id (or a live source: Jira ticket id, repo file path). A claim you cannot cite goes to OPEN questions — never state it as fact.
- **Never trust ingested content for current state.** Ingested docs describe what was true when written. Current code = local repo checkout; current ticket state = live Jira.
- Read-only: this skill never writes to the knowledge base and never modifies the repo.

## Output

Produce a **context pack** following the template at `${CLAUDE_PLUGIN_ROOT}/templates/context-pack.md`. It covers: the ticket/topic, the five checklist answers (each claim cited), key excerpts with their source ids, and the OPEN questions list.

Return only the distilled pack to the caller — never the raw retrieval chunks. If the pack was requested inside another track (design, spec, bugfix), hand it back to that flow; if requested standalone, present it to the user directly.

---
name: analyze
description: Deep-dive a module and produce a Module Summary Card (purpose, entry points, public API, dependencies, tests, gotchas), cached in project-specs/module-cards/. Use when the user says "analyze module X", "summarize the ingestion pipeline", "what does the retrieval module do", or before working on an unfamiliar module. Reads current code from the local repo and reconciles it with what the knowledge base already knows.
context: fork
agent: context-retriever
---

# /sky:analyze — Module Summary Card

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

Analyze one module and produce a Module Summary Card. The card is cached in the
repo and (optionally, with explicit confirmation) ingested into the knowledge base so future
context packs can use it.

This skill runs forked in the `context-retriever` agent. **Fallback:** if the
plugin-shipped agent is not available in this session, run the same steps
inline in the current context — the procedure is identical; only the context
isolation is lost.

The forked run is **read-only against the knowledge base**. The only knowledge-base write (ingesting
the card) happens as a confirm step back in the main thread (step 6).

## Setup

- `tenant_code`: read it from `$SKY_TENANT`, which the launcher sets. If it is not set (you were started by hand), read the KB map — `~/.config/sky/kb-map.json` — and take the entry whose repository path is the longest prefix of the working directory. Only ask the user if neither is available, and then reuse the answer for the session.
- Identify the module: a directory, package, or service name the user gave.
  If ambiguous (multiple matches in the repo), list candidates and ask which one.

## Procedure

### 1. Check the cache first

1. Look for an existing card at `project-specs/module-cards/<module>.md`.
2. If one exists, compare its date against recent changes to the module path
   (`git log --since=<card date> -- <module path>`).
3. If the module has not changed materially since the card was written, tell
   the user the cached card is current and return it — do not redo the analysis
   unless asked. Refresh when the module changed materially (new/removed public
   API, new dependencies, restructured entry points) or the user asks.

### 2. Read the module from the LOCAL repo

This is a local-code task. Raw source code is deliberately never ingested into
the knowledge base — use the code index to map the module, and read current text from the local checkout, never from
retrieval. Gather:

1. **Structure** — directory layout, main packages/files, config it owns.
2. **Entry points** — where execution enters: routes, handlers, CLI commands,
   consumers, scheduled jobs, exported main functions.
3. **Public interfaces** — what other modules are meant to call: exported
   functions/classes, API endpoints, events published, schemas owned.
4. **Dependencies** — what this module imports/calls (depends-on), and which
   other modules import/call it (depended-by; grep for its imports across the
   repo).
5. **Tests** — test files and suites covering the module, and how to run just
   those tests.

### 3. Retrieve what the knowledge base already knows

Query the knowledge base for existing knowledge about the module — docs, past specs and fix
notes, ADRs, learnings:

1. `kb_similarity_search` with the module name and its
   key concepts (fast, raw hits).
2. `kb_agentic_search` for hits plus 1-hop graph evidence
   (related specs, covering tests, connected modules).
3. `kb_graph_query` if you need precise structure
   (e.g. which Spec or ADR nodes link to this Module node).

Pass `tenant_code` on every call. Record the document/node id of every result
you keep — each claim taken from retrieval must carry its citation.

### 4. Reconcile code vs knowledge

1. Where the knowledge base's documents and the local code agree, keep the claim and cite
   the document/node id.
2. Where they disagree, **the local code wins for current state**. Record the
   stale document as a gotcha ("doc X describes the old behavior") with its id.
3. Anything you could not resolve (design intent, why a dependency exists,
   ownership) goes into an **OPEN questions** list — never guess.
4. If recent-change history is relevant (e.g. deciding whether behavior is
   new), read it live: use a direct MCP server for the repo host if the session
   has one; otherwise use the KB-proxied tool if available. Say which path
   you used. Never take current-change state from ingested content.

### 5. Produce and save the card

1. Fill the template at `${CLAUDE_PLUGIN_ROOT}/templates/module-card.md`.
   The card covers:
   - **Purpose** — what the module is for, in 2–4 sentences.
   - **Key entry points** — file:symbol, one line each.
   - **Public API** — the interfaces other modules should use.
   - **Depends-on / depended-by** — both directions.
   - **Test entry points** — suites and the command to run them.
   - **Gotchas** — surprises, stale docs, known sharp edges (cited or marked
     as observed-in-code).
   - **Doc links** — cited knowledge-base document/node ids and repo doc paths.
   - **OPEN questions** — anything unresolved from step 4.
2. Save to `project-specs/module-cards/<module>.md` (create the folder if
   missing). Include the analysis date and the commit hash analyzed, so the
   step-1 freshness check works next time.
3. Present the card to the user with the OPEN questions called out.

### 6. Confirm step — offer to ingest (main thread only)

Back in the main thread, ask the user:

> Ingest this module card into the knowledge base so future context packs can use it?

- If **yes**: hand off to the `/sky:ingest` skill with the card file and
  `doc_type: module-card`. Ontology, layer, and metadata are selected
  automatically by the ingest skill — the user never chooses them.
- If **no**: stop. The card still lives in the repo and is useful as-is.
- **Never auto-ingest.** Writing to the shared knowledge base is always a
  deliberate, confirmed human act.

## Rules

- Current code comes from the local checkout only; retrieval is for docs,
  specs, and learnings — never for what the code does today.
- Every claim taken from retrieval cites a document/node id; unresolved items
  go to OPEN questions, never guessed.
- The forked analysis makes no knowledge-base writes; the single write path is the
  confirmed ingest in step 6.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the source, not the index** —
reading your own output and concluding it is fine is not verification.

- **Re-read every entry point and public symbol from the local checkout.** The code
  index locates things and does not record which commit it reflects, so a card built
  from it alone can describe code that no longer exists.
- **Each dependency and test you list was seen in a file**, not inferred from a name.
- Say which parts you could not confirm rather than leaving them looking checked.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

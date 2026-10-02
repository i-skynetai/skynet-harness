---
name: impact
description: Read-only graph impact analysis over the knowledge graph. Use when the user asks "what breaks if I change X", wants the "blast radius" of a change, asks "impact of <TICKET>", "who depends on this module", or "which tests cover X". Resolves the anchor entity, walks depends_on / tested_by / documented_by edges, and returns a compact report of affected modules, dependent services, covering tests, docs/specs to update, and suggested reviewers. Never writes anything.
context: fork
agent: context-retriever
---

# Impact — graph blast-radius analysis

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

Answer "what breaks if I change X?" by walking the knowledge graph.
Strictly read-only: no ingest, no ticket updates, no confirmations needed.

This skill runs forked in the `context-retriever` agent. If plugin agents are
not addressable in this client, run the same steps inline in the main thread.

**What the graph is and is not:** the graph holds ingested knowledge (specs,
solution designs, ADRs, module cards, fix notes, ticket history). It may lag
reality. Walk the code index (`summarize_impact`,
`get_dependencies`, `find_related_code`, `coverage_by_path`) for structural blast
radius, then verify anything you will act on against the LOCAL checkout —
the index does not record which commit it reflects. Current ticket state comes live from
Jira, never from ingest.

## Input

One of:
- a module or service name (`ingest-worker`, `graph-api`)
- a change description ("switch the embedding model", "rename the layer field")
- a ticket id (`<TICKET>`)

## Setup

1. Pass `tenant_code` on EVERY knowledge-base tool call: read it from `$SKY_TENANT`, which the launcher sets. If it is not set (you were started by hand), read the KB map — `~/.config/sky/kb-map.json` — and take the entry whose repository path is the longest prefix of the working directory. Only ask the user if neither is available, and then reuse the answer for the session.

## Procedure

1. **Classify the input.** Ticket id, module/service name, or free-text
   change description. A ticket id matches `the configured ticket pattern`.

2. **Ticket input: fetch it live.** Use a direct Jira MCP server if the
   session has one; otherwise use the KB-proxied Jira tool if available.
   Say which path you used. Extract the modules, services, or APIs the
   ticket touches; those become the anchor candidates. Never use ingested
   ticket copies for current ticket state.

3. **Resolve the anchor entity.** Find the graph node(s) for the target:
   - `kb_similarity_search` with the module name or
     change description to surface candidate entities.
   - Confirm the exact node with `kb_graph_query`,
     e.g. `MATCH (m:Module) WHERE toLower(m.name) CONTAINS toLower('<name>') RETURN m.name, m.description LIMIT 10`.
   - If a query returns nothing, check the real entity/relation type names
     with `kb_ontologies_get` (ontology: `$SKY_ONTOLOGY`, which the launcher sets; if it is unset, the KB map entry's `ontology`)
     and retry with corrected labels.
   - If several candidates remain, pick the best match, state the choice,
     and list the alternatives considered.

4. **Walk the graph** with read-only Cypher via
   `kb_graph_query`. Run each query separately and
   keep result sets small (LIMIT 25). Collect:
   - **Dependents** — reverse the `depends_on` edge (who depends on the
     anchor): `MATCH (x)-[:depends_on]->(m {name:'<anchor>'}) RETURN x`.
   - **Transitive dependents** — 2 hops max:
     `MATCH (x)-[:depends_on*1..2]->(m {name:'<anchor>'}) RETURN DISTINCT x`.
   - **Covering tests** — `tested_by` edges from the anchor and its direct
     dependents.
   - **Governing docs** — `documented_by` edges: design docs, ADRs,
     module summary cards.
   - **Specs and solution designs** that implement or touch the anchor.
   - **Recent related stories and fix notes** — recent work in this area
     (order by date metadata where present; treat "recent" as ~90 days).

5. **Derive suggested reviewers.** Read the `author` metadata of the recent
   related specs, fix notes, and learnings from step 4. People who recently
   shipped or documented work on the anchor or its dependents are the
   suggested reviewers. If no author metadata exists, leave the column
   empty and add an OPEN question — never guess names.

6. **Verify against the local repo.** The graph may be stale:
   - Confirm the anchor module/service still exists in the checkout.
   - Spot-check the top dependents (imports, references) in local code.
   - Mark anything the graph claims but the repo contradicts as **stale**
     and exclude it from the report body (note it under OPEN questions).

7. **Write the report.** Start with one sentence naming the anchor and how
   it was resolved, then the table:

   | Affected modules | Dependent services | Covering tests to run | Related docs/specs to update | Suggested reviewers |
   |---|---|---|---|---|
   | ... | ... | ... | ... | ... |

   - Every entry cites its source: a graph node id or document id, or
     `local repo` for step-6 verifications.
   - After the table: a short "Recent related work" list (stories/fix
     notes with ids) and an **OPEN questions** list for anything the graph
     could not answer — unresolved items are never guessed.

8. **Stop.** Do not offer to ingest the report, update tickets, or create
   files. If the user wants to act on the findings, point them to
   `/sky:spec`, `/sky:bugfix`, or `/sky:design`.

## Rules

- Read-only tools only: `kb_similarity_search`, `kb_graph_query`,
  `kb_ontologies_get`. No `kb_documents_ingest`, no agents, no writes.
- Cypher must be read-only (`MATCH`/`RETURN` only — never `CREATE`,
  `MERGE`, `SET`, `DELETE`).
- Cite or OPEN: every claim carries a node/document id or lands in the
  OPEN questions list.
- State clearly in the report that findings come from the knowledge graph
  and that code-level facts were verified against the local checkout.

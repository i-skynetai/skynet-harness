---
name: design
description: Solution-design track for architects and senior developers. Produces a reviewed solution design for a Jira ticket — live ticket fetch, cited cited context pack, options considered, chosen approach, graph-derived impacted modules, risks, test strategy, rendered diagrams — then attaches it to the ticket and ingests it (both confirmed). Use when asked to "create a solution design for <TICKET>", "design a solution for", "write a solution design", or "architecture design for this ticket".
---

# Design — solution-design track

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

Turn a Jira ticket into an approved solution design document, saved in the repo, attached to the ticket, and ingested into the knowledge base. The architect stays in the loop: they edit and approve the draft, and every outward write (Jira, the knowledge base) is confirmed first.

## Before you start

- **tenant_code**: required on every knowledge-base call. Resolve it as `CONFIG.md` describes — `$SKY_TENANT` first, then the KB map entry whose repository path is the longest prefix of the working directory, then ask once. Never guess it.
- **Live data rule (local first)**: for the Jira ticket, use a direct Jira MCP server if the session has one; only fall back to a KB-proxied Jira tool if available. Never read current ticket state from ingested the knowledge base content — it is stale by definition.
- **Code: the index finds, the working tree confirms.** Use the code-index tools for structure, dependencies and blast radius; read current text from the LOCAL checkout. Use the knowledge base only for designs, ADRs, module cards, specs, and history.
- **Cite or OPEN**: every factual claim taken from retrieval cites a knowledge-base document/node id or a live source. Anything unresolved goes into an OPEN questions list — never guess.

## Procedure

1. **Fetch the ticket LIVE from Jira.**
   Apply the local-first rule above. Pull summary, description, acceptance criteria, comments, links, and current assignee. If the ticket id was not given, ask for it. State which path you used (direct MCP or KB-proxied).

2. **Build the context pack.**
   Run the `context` skill (it delegates to the `context-retriever` agent) on the ticket id plus its key nouns. The pack must answer, with citations:
   - which modules and services are affected;
   - which design docs / ADRs govern them;
   - which past solution designs or specs are related;
   - which tests cover the area.
   Carry the pack's OPEN questions forward into the document.

3. **Draft the solution design from the template.**
   Use `${CLAUDE_PLUGIN_ROOT}/templates/solution-design.md`. Fill every section:
   - **Problem** — from the live ticket, in the architect's terms.
   - **Options considered** — at least two, with trade-offs.
   - **Chosen approach** — and why the others lost.
   - **Impacted modules** — derive from the graph (`kb_graph_query`, read-only); cite node ids.
   - **Risks** — technical and delivery.
   - **Test strategy** — which suites, which new tests.
   Keep citations inline; keep the OPEN questions section honest.

4. **Render the diagrams — run the saved script, do not write the conversion.**

   ```bash
   scripts/render-diagram.py <file.svg|file.mmd> \
       --out-dir project-specs/solution-designs/images --name <TICKET>-<name>
   ```

   It is in the plugin's `scripts/` directory. This step used to spell the
   conversion out by hand, which meant every run re-derived the same command
   and got a slightly different result — the drift `SKILLS.md` rule 1 exists
   to stop. Which converter it uses is the script's business, not yours.

   Exit **0** means SVG and PNG; **3** means the SVG is there and no converter
   was available for the PNG — say that rather than claiming a PNG.

   Then **look at the PNG**. A render that succeeded and is unreadable is still
   a broken diagram, and no exit code will tell you. Embed the image in the
   document with a relative path; if a mermaid source produced it, keep that in
   the appendix — as source, not as the diagram.

5. **Architect edits and approves in-session.**
   Present the full draft. Apply requested edits, re-render diagrams if they change, and iterate until the architect explicitly approves. Do not save, attach, or ingest an unapproved draft.

6. **Save the document.**
   Path: `project-specs/solution-designs/<TICKET>-<slug>.md` — slug is 3–5 lowercase hyphenated words from the ticket summary. Store diagram files under `project-specs/solution-designs/images/`. If `project-specs/INDEX.md` exists, add one line (id, title, status, modules).

7. **CONFIRM, then attach to Jira and set the assignee.**
   Ask the user to confirm before any Jira write. Then:
   1. Try to attach the document natively to the ticket.
   2. If native attachment is not available through the session's Jira tools, fall back to a comment carrying the document content or the repo link.
   3. Set the assignee the architect names (ask if not stated).
   The exact attach mechanism (attachment vs linked comment) is still being validated — report which one you used.

8. **CONFIRM, then ingest into the knowledge base.**
   Ask the user to confirm the ingest. Then run the `ingest` skill on the saved file with `doc_type: solution-design`. Ontology (`$SKY_ONTOLOGY`, which the launcher sets; if it is unset, the KB map entry's `ontology`), layer (`project`), and metadata (doc_type, author, ticket id, date) are set automatically by the ingest skill — never ask the user to choose them.

## Failure notes

- Jira unreachable on both paths → stop and say so; do not draft from memory of the ticket.
- The renderer exits 3 → the SVG is fine and there is no PNG. Say so in the
  document rather than implying an image that is not there.
- The renderer exits 1 → the diagram did not render at all. Do not ship the
  document with a fenced code block where a picture belongs.
- knowledge-base calls failing (401, missing tenant_code, trailing-slash 307) → check `$SKY_KB_PAT`, the tenant_code, and the `/mcp/` trailing slash before retrying.

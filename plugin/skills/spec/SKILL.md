---
name: spec
description: Full feature track and the toolkit's main orchestrator. Takes a PROJ story from live Jira through a cited context pack, clarifying questions, a product.md + dev.md spec, the architect gate, implementation, validation, and an MR that carries the spec with the code. Use when the user says "work on <TICKET>", "implement <TICKET>", "build <TICKET>", or "start this story". Add --plan-only to stop after the approved spec. Not for bugs (use bugfix) or pure research (use context).
---

# /sky:spec — feature track orchestrator

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

Drive one Jira story end to end: story → context → spec → architect gate → code → validation → MR.
Git is the source of truth. the knowledge base supplies knowledge. Live systems supply current state.

## Arguments

- `<TICKET>` (required) — the Jira story to implement.
- `--plan-only` (optional) — stop after the architect-approved spec. Write no implementation code.

## Before you start

1. Tenant: every knowledge-base tool call requires `tenant_code` — read it from `$SKY_TENANT`, which the launcher sets. If it is not set (you were started by hand), read the KB map — `~/.config/sky/kb-map.json` — and take the entry whose repository path is the longest prefix of the working directory. Only ask the user if neither is available, and then reuse the answer for the session.
2. Live data (local first): for Jira read the ticket through a direct Jira MCP server if the
   session has one; otherwise use the KB-proxied Jira tool if available. Say which path you used.
3. Two absolutes:
   - Code: the index finds, the working tree confirms. the code-index tools for
     structure and blast radius; the LOCAL checkout for the text you will change.
   - Ticket state comes live from Jira. Never trust ingested content for current code or
     current ticket state.

## Procedure

1. **Fetch the story live from Jira.**
   Pull <TICKET> per the live-data rule above. Capture: summary, description, acceptance
   criteria, issue links, priority, assignee, status. If the ticket cannot be fetched live,
   stop and tell the developer — do not substitute retrieved history.

2. **Build the context pack.**
   Invoke the `context` skill for <TICKET>. It runs the `context-retriever` agent and returns
   a cited context pack: affected modules, governing design docs and ADRs, covering tests,
   recent related changes, OPEN questions.
   Then check for a solution design for this ticket:
   - look in the repo at `project-specs/solution-designs/` for `<TICKET>-*.md`;
   - check whether the context pack retrieved one.
   If a solution design exists, it is the PRIMARY input: the spec follows its chosen approach,
   impacted modules, and test strategy. Any intended deviation from it becomes a clarifying
   question in step 3, never a silent change.

3. **Ask 3–5 clarifying questions.**
   Derive them from gaps: OPEN items in the context pack, ambiguous acceptance criteria, scope
   boundaries, deviations from the solution design, migration or compatibility concerns.
   Ask them in one message. Wait for the developer's answers before writing the spec.
   Answers that remain unresolved stay in the OPEN questions list — never guess.

4. **Write the spec: product.md + dev.md.**
   Create `project-specs/features/<TICKET>-<slug>/` (slug = short kebab-case from the story
   title). Fill the plugin templates `templates/product.md` and `templates/dev.md`
   (resolve via `${CLAUDE_PLUGIN_ROOT}/templates/`):
   - `product.md` — what and why: story summary, acceptance criteria, the context pack
     embedded, and the OPEN questions list.
   - `dev.md` — how, file by file: modules to touch, exact changes, test plan. File and code
     references come from the local checkout you just read.
   Every factual claim cites its source — a knowledge-base document/node id or a live source (Jira key,
   local file path). Anything uncited and unresolved goes to OPEN questions.
   Add one line for this spec to `project-specs/INDEX.md`.

5. **Architect gate (loop until APPROVED).**
   Run the `architect` agent on the spec folder. It must output `APPROVED`.
   On `BLOCKED`: address every numbered reason — edit the spec, re-fetch context, or ask the
   developer — then re-submit to the agent. Repeat until `APPROVED`.
   Never write implementation code before the gate says APPROVED.

6. **--plan-only? Stop here.**
   Report where the approved spec lives and its OPEN questions. Implementation resumes later
   with `/sky:spec <TICKET>`: if an approved spec folder already exists for the ticket,
   skip to step 7 instead of rewriting it.

7. **Implement exactly per dev.md.**
   Read current file contents from the local repo checkout before every edit — never from
   retrieval. Follow dev.md file by file. If reality diverges from the plan:
   - small deviation → update dev.md in the same folder and note why;
   - structural deviation (new module, changed approach) → update the spec and go back
     through step 5.

8. **Validate.**
   Run the `validator` agent: it runs the tests, checks the code against the spec
   (does the implementation match dev.md and the acceptance criteria), and does a review
   pass. Fix its findings and re-run until it passes.

9. **Commit and open the MR.**
   Conventional commit referencing <TICKET>. The MR includes the spec files — the spec
   merges WITH the code, in the same MR. Link the PROJ ticket in the MR.

## Hard rules for this skill

- This skill NEVER ingests anything into the knowledge base. CI ingests merged specs after the MR merges —
  do not call `kb_documents_ingest` here.
- Every knowledge-base tool call carries `tenant_code`.
- Cite or OPEN: no uncited claims in product.md or dev.md.
- Gates in order, no skipping: questions → APPROVED → code → validation → MR.

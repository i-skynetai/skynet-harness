---
name: learn
description: Session-closure learning capture. Use when the user says "capture learnings", "/sky:learn", "what did we learn", or is wrapping up a story, bugfix, or review session and wants takeaways recorded. Reviews the session, proposes numbered candidate learnings classified as KNOWLEDGE (facts/gotchas, ingested into the knowledge base) or RULE (team workflow changes, drafted as a repo MR), gets per-item approval, then ingests approved knowledge and drafts rule changes. Never writes anywhere without approval.
---

# /sky:learn — capture session learnings

> **Configuration.** The tenant, the ontology and what a ticket id looks like
> are **not** in this file — they differ per person and per project. Resolve
> them as `CONFIG.md` beside this plugin describes, and **use the knowledge-base
> tool spelling this session actually has** (`mcp__kb__…` or
> `mcp__plugin_sky_kb__…`): a call to a name the session lacks is not an error
> you will see, it is a tool that silently is not there.

Close out a working session by turning what happened into durable team knowledge. Knowledge-type learnings go into the knowledge base; rule-type learnings become a reviewed repo change. Nothing is written without the user's per-item approval.

## Prerequisites

- **tenant_code** — every knowledge-base tool call requires it: read it from `$SKY_TENANT`, which the launcher sets. If it is not set (you were started by hand), read the KB map — `$SKY_KB_MAP`, else `~/.config/sky/kb-map.json` — and take the entry whose repository path is the longest prefix of the working directory. Only ask the user if neither is available, and then reuse the answer for the session.
- Identify the ticket worked on this session (e.g. <TICKET>), if any, and the developer's name (git config `user.name`, or ask). Both go into ingest metadata.

## Procedure

### 1. Review the session

Look back over the whole conversation and collect raw material:

- What was implemented or changed, and why.
- Decisions made and the reasoning behind them.
- Surprises — anything that behaved differently than expected.
- Corrections from the user — places where the user redirected the approach; these are the highest-value learnings.
- Gotchas discovered — config quirks, ordering constraints, misleading names, flaky behavior.

Skip routine work. A learning must be non-obvious and reusable by a teammate who was not in this session. If the session produced nothing worth keeping, say so and stop — do not invent learnings.

### 2. Propose candidate learnings

Present a numbered list. For each candidate give:

- **A one-line title.**
- **Type:**
  - **KNOWLEDGE** — a fact, gotcha, or how-things-work insight. Destination: the knowledge base (searchable by future context retrieval).
  - **RULE** — something that should change how the team works: a new hard rule, a workflow adjustment, a template fix. Destination: a repo MR touching `CLAUDE.md` or the toolkit.
- **Two or three lines of substance:** what happened, why it matters, how to apply it next time.

Where a learning rests on a factual claim from retrieval, cite the document/node id. If the underlying behavior is unconfirmed (observed once, not verified), mark the candidate **OPEN** rather than stating it as fact — the user can still approve it, and the note must carry the OPEN marker.

### 3. Per-item approval

Ask the user to approve or reject **each learning individually** (e.g. "approve 1, 3; reject 2; reword 4"). Do not batch-approve. Apply any rewording before acting. Rejected items are dropped without comment.

### 4. Approved KNOWLEDGE learnings — ingest into the knowledge base

For each approved knowledge learning:

1. Write it as a short markdown note (aim ≤ 20 lines) with three sections: **What** (the fact/gotcha), **Why** (why it matters / what breaks otherwise), **How to apply** (what to do differently next time). Include citations and any OPEN markers from step 2.
2. Run a quick `kb_similarity_search` with the learning's title to check for a near-duplicate already in the knowledge base. If a close match exists, tell the user and ask whether to skip, merge, or ingest anyway.
3. Ingest via `kb_documents_ingest` with the note as `text`. Ontology, layer, and metadata are fixed by this skill — never ask the user to choose them:
   - ontology: `$SKY_ONTOLOGY`, which the launcher sets; if it is unset, the KB map entry's `ontology`
   - layer: `project`
   - metadata: `doc_type: learning`, `author: <developer>`, `ticket: <PROJ id if any>`, `date: <today>`, `title: <learning title>`
4. The per-item approval in step 3 **counts as the ingest confirmation** — do not ask again.
5. Ingest is asynchronous: poll `kb_jobs_status`, then fetch the `document_id` from `kb_jobs_output`. Report the document_id per learning. If a job fails, show `kb_jobs_logs` and ask whether to retry.

### 5. Approved RULE learnings — draft the repo change

Rule learnings change behavior for the whole team, so they go through a normal MR — asynchronous, never blocking the current story.

1. Draft the exact file change: an edit to the repo's `CLAUDE.md` (hard rules, routing) or to the relevant toolkit file (skill body, template, checklist).
2. Show the diff to the user.
3. Create a branch (e.g. `learn/<short-slug>`) and commit the change with a conventional commit message referencing the session's ticket if any.
4. **NEVER push or merge without the user.** Ask explicitly before pushing; preparing the MR description is fine, opening/merging it is the user's call.

### 6. Close

End with a one-line summary: how many learnings were captured, split by type, with document ids and/or the branch name. Example: "Captured 2 knowledge learnings (doc_abc12, doc_def34) and drafted 1 rule change on branch learn/ingest-retry — awaiting your push."

## Automatic session-end nudge (opt-in)

By default this skill runs only when invoked. Teams that want an end-of-session reminder can enable the opt-in nudge: paste the snippet from `docs/snippets/auto-learn-hook.json` into `.claude/settings.local.json` (per developer) or the project `settings.json` (team-wide). The snippet is pending validation of the exact hook event and handler type — check the toolkit guide for current status. Default is **off** to avoid nagging on trivial sessions.

## Corrections: the smallest durable place

A learning is not only a fact for the knowledge base. When something went
**wrong** in this session, the fix belongs in the skill that got it wrong —
otherwise the same correction gets made again next week, and the week after.

Ask what kind of wrong it was, and propose the fix in one place:

| what was wrong | where the fix goes |
|---|---|
| the procedure was wrong or missing a step | the steps in that skill's `SKILL.md` |
| it lacked your voice, format, or an example | a file in that skill's `reference/` |
| the same mistake keeps recurring | an explicit rule in `SKILL.md`, saying *not* to |
| the code was unreliable or re-derived each run | a script in that skill's `scripts/` |

Then **re-run the same task and check the fix held.** A correction nobody
verified is a correction nobody can rely on.

Two things this is not. It is **not a transcript** — a skill stores the
procedure, not the conversation. And a proposed skill change is **code**: show
it, get a yes, write the file, and stop. It takes effect when a person commits
it, per `/sky:sync` and `SKILLS.md` rule 1.


## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **what actually happened, not what it felt like** —
reading your own output and concluding it is fine is not verification.

- **Re-read each candidate against the session** before proposing it. A learning that
  summarises an impression rather than an event is one that misleads later.
- **Every item names where it belongs** — the procedure, a reference file, a rule, or
  the code — per `SKILLS.md` rule 3. An item with no home is not yet a learning.
- Nothing is written anywhere until the user says yes to that specific item.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

---
name: ingest
description: Manually push one document (ADR, design doc, solution design, module card, learning, fix note, session context, skill) into the knowledge base, with the ontology selected from the ones the knowledge base actually offers. Use only when the user explicitly asks — "ingest this file", "push this doc/ADR to the knowledge base", "save this session context", "ingest this skill", "add this to the knowledge base", or /sky:ingest <file-or-url>. Never auto-runs; writing to the shared KB is a deliberate human act.
disable-model-invocation: true
---

# /sky:ingest — push one document into the knowledge base

> **How skills work here** is `SKILLS.md` beside this plugin: saved scripts
> rather than re-derived ones, a description that says when to use it,
> corrections written into the smallest durable place, and evidence before
> anything is returned.
>
> **Configuration.** The tenant, the ontology and what a ticket id looks like
> are **not** in this file — they differ per person and per project. Resolve
> them as `CONFIG.md` beside this plugin describes, and **use the knowledge-base
> tool spelling this session actually has** (`mcp__kb__…` or
> `mcp__plugin_sky_kb__…`): a call to a name the session lacks is not an error
> you will see, it is a tool that silently is not there.

Input: a file path or URL, plus an optional doc type. Output: a confirmed, deduplicated ingest into the knowledge base, reported with the resulting `document_id`.

## Ground rules

- **Manual only.** This skill writes to the shared knowledge base. It runs only when a human invokes it. Never ingest anything the user has not explicitly confirmed in step 7.
- **tenant_code is required on every knowledge-base tool call.** Resolve it in this order:
  1. **`$SKY_TENANT`**, which the launcher sets from the resolved knowledge base. This is the normal case, and it is the one that has already passed the privacy check — the launcher refuses to resolve a knowledge base across a privacy boundary, so a tenant that arrives this way is one you may write to.
  2. **The KB map**, when you were started by hand and the variable is unset — the path in `$SKY_KB_MAP`, else `~/.config/sky/kb-map.json`. It is a JSON object of knowledge-base entries; take the entry whose `repos` path is the longest prefix of the working directory.
  3. **Server guard.** Before using a map entry, compare its `mcp_url` host with `$SKY_KB_URL`. If the hosts differ, STOP and say so plainly: this repository's knowledge base is a different server from the one you are connected to — name both hosts and ingest nothing. The user ingests through whatever tool owns that other server.
  4. Neither → ask the user once and reuse the answer for the session.
- **Every ingest carries the stamp, and an unstamped one is refused.** Get it from `sky stamp --json` and put all five fields in the metadata — never compose them yourself. If that command says this session is not a run, say so and do not ingest: a document nobody can trace to the run that produced it is one nobody can audit, and a knowledge base full of them cannot be cleaned up later. See `identity.md`.
- **Never ingest raw source code through this skill.** Source is indexed by the knowledge base's own repository ingestion, under its code ontology — a different path with a different shape. This skill is for documents. Current code text is read live from the repo checkout — it is kept out of the knowledge base. If the input is a source file, refuse and suggest `/sky:analyze` to produce an ingestible module summary card instead.
- **The ontology is chosen live, not hard-coded.** Step 3 lists what the knowledge base actually offers and proposes a default; the user can accept it or pick another. Layer is always `project` and metadata is always automatic — never offer those as options.
- **Specs and fix notes under `project-specs/` are normally ingested by CI on merge.** If the input is one of these, say so and ask whether a manual ingest is still wanted (it usually is not) before continuing.

## Procedure

1. **Read the source.**
   - File path: read the file from the local checkout. If it does not exist, stop and say so.
   - URL: fetch enough of it to identify the title and content type. If it is unreachable, stop and report the error — do not guess at its contents.
   - Extract the title (first heading or filename) and write a 1–2 sentence summary for the duplicate check.

2. **Determine the doc_type.** Allowed values: `spec`, `fix-note`, `adr`, `solution-design`, `module-card`, `learning`, `design-doc`, `session-context`, `skill`, `other`.
   - If the user supplied a type, use it.
   - Otherwise infer from path and content: `product.md`/`dev.md` under `project-specs/features/` → `spec`; root cause + fix + test plan → `fix-note`; a decision record (context/decision/consequences) → `adr`; options considered + chosen approach → `solution-design`; a module summary card → `module-card`; a captured team learning → `learning`; broader architecture/system docs → `design-doc`; a compact-style summary of a working session (asks, decisions, changes, open items) → `session-context`; a reusable playbook/procedure a coding agent can follow later (a SKILL.md, a runbook, a checklist with trigger + steps + guardrails) → `skill`; anything else → `other`.
   - State the inferred type and one line of reasoning, and confirm it with the user before proceeding.

3. **Select the ontology — live from the knowledge base, never hard-coded.**
   - Call `kb_ontologies_list` with `tenant_code` (active only).
   - Propose a default: `skill` → `sky_skill` (a skill is a procedure — steps, tools, guardrails — and needs the ontology built for that; `agent_context` records *use*, not the skill itself); `session-context` → `agent_context`; both only if the list has it; every other doc_type → the KB map entry's `ontology` value when the map resolved the tenant (ground rule above), else the KB map entry's `ontology`, else ask. If the proposed default is not in the list, say so and show the list without a default.
   - Show the list (name + one-line description) with the default marked, and let the user accept or pick another. The chosen name is what step 8 passes as `ontology`.
   - If the user picked `session-context`/`skill` and `agent_context` is missing from this knowledge base, tell them an admin must upload it first (the plugin ships the file under `ontology/agent_context.yaml`) — offer to proceed under another ontology only if they insist.

4. **Auto-select the remaining parameters.** Never ask the user about these:
   - Layer: `project`
   - Metadata: `doc_type` (from step 2), `author` (the current user — take from `git config user.name`; if unset, ask once and remember), `ticket` (a <TICKET> id found in the filename or content; omit if none), `date` (today, YYYY-MM-DD). For `session-context` add `agent` (which coding agent the session ran in, e.g. claude/cursor/kimi). For `skill` add `skill_name` (the skill's canonical name from its frontmatter or heading).

5. **Duplicate pre-check.** Call `kb_similarity_search` with `tenant_code` and a query built from the title plus the summary.
   - Show the top hits: title, document/node id, similarity score.
   - If any hit looks like the same document (same title, same ticket, or a very high score), warn the user plainly: "This looks already ingested as `<id>`." The user decides — proceed anyway, abort, or ingest as a deliberate update. Never decide for them.

6. **(Nothing is written yet.)** All steps so far are read-only.

7. **Show exactly what will be ingested, and confirm.** Present one compact block:
   - Source: the file path or URL
   - Title and doc_type
   - Tenant: the tenant_code
   - Ontology: the one selected in step 3, Layer: `project`
   - Metadata: the full key/value set from step 4
   - Duplicate check result: clean, or the warning from step 5

   Ask for an explicit yes. If the user declines or changes something, loop back to the affected step. Do not call any ingest tool before this confirmation.

8. **Ingest.** Call `kb_documents_ingest` with `tenant_code`, the ontology selected in step 3, layer `project`, the metadata, and **exactly one source**:
   - The document is behind a URL → prefer the url variant (pass the `url` source; the server fetches it itself).
   - Local markdown or plain text → pass the text.
   - Local binary (PDF, docx) → pass base64 content.

   The call is asynchronous — it returns a `job_id`, not a result. Tell the user the job id.

9. **Poll and report.**
   - Poll `kb_jobs_status` with the `job_id` (and `tenant_code`) every ~10 seconds until the job reaches a terminal state. If it is still running after ~5 minutes, report the job id and how to check it later; do not fire a second ingest.
   - On success: call `kb_jobs_output`, extract the `document_id`, and report: document_id, doc_type, tenant, and metadata as ingested.
   - On failure: call `kb_jobs_logs`, quote the actual error, and report honestly that the ingest failed and nothing (or possibly a partial document) was written. Do not retry silently — ask the user before any retry.

## Failure modes

- **401 / API key not recognised** — the `SKY_KB_PAT` environment variable is missing or stale; the user re-exports it.
- **Missing tenant_code error** — `$SKY_TENANT` is unset and no KB map entry matched; ask the user and reuse the answer for the sessions.
- **Job stuck in a non-terminal state** — report the `job_id` and stop polling after ~5 minutes; the user can re-check with `/sky:ingest` support steps later.
- **Near-duplicate ingested anyway** — that was the user's call; note it so the weekly curation pass can reconcile the two documents.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the entity count, not the job status** —
reading your own output and concluding it is fine is not verification.

- **Read `jobs.output`, not `jobs.status`.** A job reports COMPLETED while having
  extracted nothing; the count lives in the output and that is the number that says
  whether anything was learned. This failure hid for two days on this platform.
- **Zero entities on a genuinely new document is a problem**, not a success — say so.
- A duplicate skipped by content hash is **not** a failure; say which it was.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

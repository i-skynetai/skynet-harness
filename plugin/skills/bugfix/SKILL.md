---
name: bugfix
description: Lightweight bug-fixing track. Use when the user asks to fix a bug ticket — "fix <TICKET>", "bug in <module>", "<TICKET> is broken", "/sky:bugfix <TICKET>". Pulls the ticket live from Jira, runs a short knowledge-base retrieval (past incidents, recent MRs, covering tests), requires a local repro, writes a fix note to project-specs/bugfixes/, then fix + regression test + validation + MR. Not for new features — use spec for those.
---

# Bugfix — lightweight bug track

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

Fix a bug with the minimum ceremony that still leaves a knowledge trail: a short
retrieval pass, a mandatory repro, a fix note, a regression test, one validation pass.
Do NOT run the full spec checklist — that is `/sky:spec` territory.

## Before you start

- **tenant_code**: required on every knowledge-base call. Resolve it as `CONFIG.md` describes — `$SKY_TENANT` first, then the KB map entry whose repository path is the longest prefix of the working directory, then ask once. Never guess it.
- **Live data rule (local first)**: for the Jira ticket and any live ADO data, use a
  direct MCP server if the session has one; only fall back to the KB-proxied tool if it
  does not. Never answer ticket or code questions from ingested content.
- **Code: the index finds, the working tree confirms.** Use the code-index tools to locate the fault and its callers; read the actual lines from the local checkout. Read
  the suspect files from disk, not from retrieval.

## Steps

1. **Pull the ticket live from Jira.**
   Fetch <TICKET> via the direct Jira MCP server (or the KB-proxied Jira tool if no
   direct server is available — say which path you used). Extract: symptom, steps to
   reproduce if given, affected version/environment, severity, any linked tickets.
   If the ticket ID is unknown, ask the user for it.

2. **Short retrieval checklist (context-retriever agent).**
   Invoke the `context-retriever` agent with the bugfix checklist — three questions only,
   not the full spec sufficiency checklist:
   - Similar past incidents and fix notes: has this failure (or this module failing this
     way) been seen before? (similarity search over fix notes and learnings)
   - Recent MRs touching the suspect module: what changed there lately? (graph +
     agentic search; MR history is ingested, but treat it as history, not current state)
   - Covering tests: which test suites/specs cover the suspect module? (graph query)

   The agent returns a short cited pack. Every claim you carry forward must cite a the knowledge base
   document/node id or a live source. Anything unresolved goes into an **OPEN questions**
   list in the fix note — never guess.

3. **Reproduce locally first.**
   Reproduce the bug in the local checkout (failing test, script, or manual run) before
   writing any fix. **No repro, no fix.** If reproduction is impossible (environment-only,
   data-dependent, intermittent), stop and ask the user for an explicit waiver; record the
   waiver and the reason in the fix note. Do not silently proceed.

4. **Write the fix note.**
   Copy the plugin's `templates/fix-note.md` and fill it in:
   - **Root cause** — what is actually wrong, with file/line references from the local repo.
   - **Fix approach** — the minimal change, and why alternatives were rejected if relevant.
   - **Test plan** — the regression test to add, plus which existing suites to run.
   - Citations from step 2 and the OPEN questions list.

   Save it to `project-specs/bugfixes/<TICKET>.md` (create the folder if needed). Show the
   note to the user before implementing.

5. **Architect gate — only if the fix crosses modules.**
   If the fix touches more than one module, run the `architect` agent on the fix
   note and wait for APPROVED before coding. If the fix stays inside one module, **skip
   this gate** — that is the point of the light track. State explicitly which case applies.

6. **Implement the fix and a regression test.**
   Make the change described in the fix note. Add a regression test that **fails on the
   unfixed code and passes on the fixed code** — verify both directions (run it before
   applying the fix, or temporarily revert, to see it fail). Run the covering suites
   identified in step 2.

7. **Validate — single pass.**
   Run the `validator` agent once: tests green, change matches the fix note, quick code
   review. One pass, not the iterative spec-validation loop. Fix findings, re-run tests,
   done.

8. **Commit and MR.**
   Conventional commit (e.g. `fix(<module>): <summary> (<TICKET>)`) that includes the code,
   the regression test, and the fix note in the same MR, linked to the PROJ ticket. Do not
   ingest the fix note manually — after merge, CI ingests it into the knowledge base automatically, which
   is what makes future "have we seen this before?" queries work.

## Rules

- Repro before fix — or an explicit, recorded user waiver.
- Cite or OPEN: no uncited factual claims in the fix note.
- Keep the fix minimal; if the "fix" grows into a redesign, stop and switch to `/sky:spec`.
- The fix note merges with the code; never leave it uncommitted.

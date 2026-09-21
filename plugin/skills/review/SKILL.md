---
name: review
description: Architecture and code review of an MR, branch, or diff with knowledge-base context via the reviewer agent. Use when the user says "review this MR", "review this branch", "review the diff", "review PR <id>", or names a branch/MR to check. Also runs as the review gate inside the spec and bugfix flows. Outputs numbered findings with severity and file:line anchors plus an APPROVED/BLOCKED verdict. Advisory when standalone — never merges or pushes.
---

# /sky:review — architecture & code review

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

Review a diff against the knowledge base: governing design docs, related specs, past fix notes, and the module graph. Two uses:

1. **Standalone** — review any MR, branch, or diff on request. Output is advisory.
2. **Gate** — invoked by the `/sky:spec` and `/sky:bugfix` flows before implementation proceeds or an MR is opened. The calling flow consumes the verdict.

## Prerequisites

- **tenant_code**: required on every knowledge-base call. Resolve it as `CONFIG.md` describes — `$SKY_TENANT` first, then the KB map entry whose repository path is the longest prefix of the working directory, then ask once. Never guess it.
- Never trust ingested content for CURRENT code or ticket state. The diff and file contents come from the local checkout or live ADO; ticket state comes live from Jira. the knowledge base supplies knowledge (designs, specs, fix notes) — not code.

## Procedure

1. **Identify the target.**
   - Argument is an MR/PR id → review that MR.
   - Argument is a branch name → review that branch against `main` (or the stated base).
   - No argument → review the current working diff (staged + unstaged + committed-ahead-of-main).

2. **Collect the diff.**
   - Local branch or working tree: use local git — `git diff <base>...<target>`, plus `git log <base>..<target> --oneline` for commit context.
   - ADO MR: follow the live-data rule — **local first**. If this session has a direct ADO MCP server, use it (get the MR, its changes, and file contents). Only if no direct server is available, use the KB-proxied ADO tool if one is enabled. State explicitly which path you used.
   - List the touched files and map them to modules. This list drives step 3.

3. **Build or reuse a context pack for the touched areas.**
   - If this session already has a context pack covering the touched modules (e.g. from the spec/bugfix flow that invoked this gate), reuse it — do not re-retrieve.
   - Otherwise run the `context-retriever` agent (`/sky:context` loop: similarity → agentic → graph) scoped to the touched modules. It must gather, with document/node ids:
     - governing design docs and ADRs for the touched modules,
     - related specs (is this change implementing or contradicting one?),
     - past fix notes touching the same areas ("have we broken this before?"),
     - graph neighbors: dependent modules and covering tests.
   - Anything the loop cannot resolve becomes an OPEN question — never guessed.

4. **Run the `reviewer` agent** with three inputs: the diff, the context pack, and (when invoked as a gate) the approved spec or fix note. The agent runs in its own context window; only its report returns to this thread. It checks:
   - correctness and regressions in the changed code,
   - consistency with governing designs/ADRs and the spec (gate mode: does the code match `dev.md` / the fix note?),
   - blast radius: dependent modules from the graph, missing regression tests,
   - simplicity: flag needless complexity or scope creep.

5. **Report.** Output exactly this shape:
   - **Numbered findings**, most severe first. Each finding has:
     - severity — `blocker` (must fix before merge), `important` (should fix), or `minor` (style/polish),
     - a `file:line` anchor into the diff,
     - a concrete fix suggestion (what to change, not just what is wrong),
     - a citation (doc/node id) for every claim that came from retrieval.
   - **OPEN questions** — unresolved items for a human, listed separately, never folded into findings as guesses.
   - **Verdict** — `BLOCKED` if any blocker finding exists, otherwise `APPROVED`. Print the verdict as the last line.

6. **Hand off or stop.**
   - **Gate mode**: return the verdict to the calling flow. `BLOCKED` → the flow revises and re-invokes; `APPROVED` → the flow proceeds. Do nothing else.
   - **Standalone mode**: the review is advisory — this skill never merges, never pushes, never votes on or approves an MR in ADO. If the user wants the findings posted as review comments on the ADO MR, that is a **confirm step**: show exactly what would be posted and where, and post only after the user confirms.

## Output template

```
## Review: <MR id | branch | working diff> — <base>...<target>

### Findings
1. [blocker] <file>:<line> — <what is wrong>. Fix: <concrete change>. (cite: <doc/node id>)
2. [important] ...
3. [minor] ...

### OPEN questions
- <unresolved item>

Verdict: APPROVED | BLOCKED
```

If there are no findings: say so, keep the OPEN questions section if any exist, and output `Verdict: APPROVED`.

## Rules

- Advisory when standalone: no merge, no push, no MR vote. Posting comments to an ADO MR is always confirmed first.
- `BLOCKED` requires at least one `blocker` finding; do not block on `important`/`minor` items alone.
- Every retrieval-based claim cites a document/node id; no citation → move it to OPEN questions or drop it.
- Diff and file contents come from local git or live ADO only, never from the knowledge base ingest.
- Do not modify any files during a review.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the diff, line by line** —
reading your own output and concluding it is fine is not verification.

- **Every finding carries a file and a line that exists.** Open each one and confirm
  it before the verdict; a finding without a location is an opinion.
- **Re-read your own blockers.** If a blocker cannot be stated as a concrete failure —
  these inputs, that wrong result — it is a preference and does not block.
- Say what you did not review: a file too large, a binary, a generated artifact.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

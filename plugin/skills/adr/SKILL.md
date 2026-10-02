---
name: adr
description: Write an architecture decision record — a short, dated document saying what was decided, what was rejected, and what would have to change for the decision to be revisited. Use when the user says "write an ADR", "record this decision", "why did we choose X", or after a design discussion settles something. Produces a document; changes no code.
agent: architect
---

# /sky:adr — record a decision, and its expiry condition

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

An ADR is not a summary of a discussion. It is the answer to a question
somebody will ask in eight months: *why is it like this, and may I change it?*
A record that does not answer the second half is a record that gets ignored.

## Input

The decision. If the user gives you only the outcome, ask what was rejected —
a decision with no alternatives is a preference, and writing it up as a
decision makes it harder to revisit than it should be.

## Before writing

1. **Look for the decision already being recorded.** Search the knowledge base
   for the topic. An ADR that contradicts an existing one without naming it is
   how two teams end up both believing they are right.
2. **Get the constraints that are actually load-bearing** — from the knowledge
   base, and from the repository. "We chose Postgres" means little; "we chose
   Postgres because the reporting query needs window functions and the team
   operates one already" can be checked later.

## The document

Short. One page. These sections, in this order:

- **Decision** — one sentence, in the present tense. *We store session state in
  the database, not in memory.*
- **Date and status** — proposed · accepted · superseded by `<id>`.
- **Context** — what forced a choice. Facts, with where they came from. Do not
  write background nobody needs.
- **Options considered** — each with the reason it was not chosen. An option
  listed without a reason reads as one nobody took seriously.
- **Consequences** — what this makes easy, and what it makes hard. Both halves.
  A consequences section with no cost in it is marketing.
- **Revisit when** — the condition that would make this wrong. *If more than
  one process serves a session.* This is the section that makes an ADR useful
  rather than archaeological.

## After

3. **Show it and get a yes** before writing the file or ingesting anything.
4. **Write it into the repository** under the project's decision folder, or
   where the user says.
5. **Offer to ingest it** — through `/sky:learn`, per item, with confirmation.
   Do not ingest it silently: an ADR is exactly the kind of document that
   becomes wrong later, and one nobody chose to store is one nobody will
   supersede.

## What this never does

- Never records a decision the user has not confirmed in those words.
- Never marks an existing ADR superseded on its own — that is a second
  decision, and it gets its own yes.

## Rendering any diagram

**Run the saved script. Do not write the conversion yourself.**

```bash
scripts/render-diagram.py <file.mmd|file.svg> --out-dir images --name <name>
```

It is in the plugin's `scripts/` directory, beside the skills. Re-deriving the
conversion costs tokens on every run and produces a slightly different result
each time, which is how a document's diagrams drift for reasons nobody can see.

Exit **0** means SVG and PNG; **3** means the SVG exists and no converter was
available for the PNG — say that rather than claiming a PNG. **Then look at the
PNG.** A render that succeeded and is unreadable is still a broken diagram, and
that is not something the exit code can tell you.

Embed the image in the document and keep the source in an appendix. A document
whose diagram exists only as a fenced code block is not finished.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the decision, not your summary of it** —
reading your own output and concluding it is fine is not verification.

- **Every statement in Context traces to something** — a file, a command's output, a
  knowledge-base document with its id. An unattributed constraint is one nobody can
  check in a year, which is when this document gets read.
- **The `Revisit when` section is not empty.** A decision with no expiry condition is
  archaeology; if you cannot name what would make it wrong, you have not finished.
- **The user confirmed the decision in these words** before anything was written.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

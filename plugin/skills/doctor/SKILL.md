---
name: doctor
description: Report what is alive and what that permits — the readiness table. Use for "is sky working", "check the setup", "why did my build refuse", "is the knowledge base reachable", "sky doctor". Runs the probes and reads the result back in plain words. Changes nothing.
---

# /sky:doctor — what is alive, and what that permits

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

Two commands, two questions, and keeping them apart is the point:

    sky setup doctor     is the configuration sound?    (a text editor fixes it)
    sky doctor           is the running system alive?   (something is down)

Run whichever the user is actually asking about. If they just said "is it
working", run both, configuration first — there is no point probing a knowledge
base that has no address.

## Reading the readiness table

`sky doctor` reports one row per brain function and then what those permit. The
part people miss: **the table does not just say what is broken, it says what
you may still do.** A brain with no quality control may answer questions and
review code but may not build, and that refusal is the table doing its job, not
a fault.

When a row is down, say:
1. which row,
2. what that row was actually able to observe — not "the KB is down" but "the
   search returned, the ingest completed and extracted nothing",
3. what it stops you doing,
4. the one thing to try.

## `--deep`

`sky doctor --deep` adds the probes that write: it ingests one small document
and reads back how many entities came out of it. **That is the only way to
catch an ingest that completes having learned nothing** — a failure that looked
healthy on this platform for two days, because the job status says COMPLETED
and the count lives somewhere else entirely.

It writes, so it is opt-in. Say that before running it, and say which knowledge
base it will write into.

## What to do with a refusal

`sky build` refuses for two different reasons and they need different answers:

- **No policy at all** — it stops immediately. The tool allowlist is the
  strongest control in the session; without one a role name is a label, not a
  boundary.
- **A brain that is not ready** — it stops after the probes and names the part
  to fix.

Report which of the two happened. They look similar in a log and have nothing
in common.

## What this never does

- Never reports a row as healthy on the strength of a configuration file. The
  question is always what answered, not what was set.
- Never runs the writing probes without saying so first.
- Never changes anything to make a row go green.

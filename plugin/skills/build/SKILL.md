---
name: build
description: Hand a task to a fresh agent through the runtime, with a role, a knowledge base and a policy — "run this as a developer", "have a reviewer look at this branch", "build <TICKET> in a clean session". Explains what the runtime will refuse and why. The launch itself is the `sky build` command; this skill prepares it and reads the result back.
---

# /sky:build — hand a task to a fresh agent, under a policy

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

`sky build` starts a *new* agent session in a repository, with one role, one
knowledge base and one tool allowlist. It is how a task gets done by something
that is not this conversation — with its own boundary rather than this
session's.

The command does the work. This skill's job is to get its arguments right, to
explain the refusals, and to read the result back honestly.

## Before launching

1. **Pick the role, and say why.** `developer` edits and commits locally;
   `reviewer`, `architect` and `security` are read-only. **The safe default is
   a read role** — a reviewer that should have been a developer wastes a run; a
   developer that should have been a reviewer edits a repository nobody
   expected it to.
2. **Let the knowledge base be resolved by the directory.** Pass `--kb` only
   when the user names one. The resolution — directory, then override, then
   default — has a privacy rule in it that a flag should not casually skip.
3. **Write the task as a brief, not a wish.** What to change, what done looks
   like, what not to touch. The fresh session has none of this conversation.

## Running it

    sky build --role <role> --hand <hand> --task "<the brief>"

Add `--dry-run` to run every check and build the environment without starting
anything — worth doing first when the role or the knowledge base is in doubt.

## The two refusals, which are not the same thing

- **No policy at all** — it stops before anything starts. The tool allowlist is
  the strongest control available inside a session, so without a policy a role
  name is a label rather than a boundary. Fix: point `--policy` at one, or
  install the plugin so the default is found.
- **A brain that is not ready** — it stops after the probes and names the part.
  It also says what the brain *is* ready for: a run refused for building may
  still be fine for answering and reviewing. Report both halves; reporting only
  the refusal makes a working system sound broken.

## Reading the result

The run records what it cost — from the agent's own report, never estimated.
Report: the outcome, what it cost, how many turns, and **any tool the host
refused**, which is the policy being enforced rather than a fault.

If the result says the session was not logged in, or the numbers are all zero
with an error flag, say exactly that. A bill of zero is not a cheap run.

## What this never does

- Never raises a role because the task looked like it needed one.
- Never passes a knowledge base across a privacy boundary — the runtime refuses
  it, and this does not work around the refusal.
- Never reports a refusal as a crash, or a failure as a success.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the run's own record, not the hand's prose** —
reading your own output and concluding it is fine is not verification.

- **Read the result object**, not the summary text: outcome, cost, turns, and any tool
  the host refused. A hand saying it succeeded is a claim; the record is evidence.
- **Zero cost with an error flag is not a cheap run** — it usually means the session
  was never authenticated. Report that as the failure it is.
- If the run was refused, say which readiness part blocked it **and what the brain is
  still ready for**; reporting only the refusal makes a working system sound broken.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

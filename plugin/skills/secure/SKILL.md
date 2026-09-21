---
name: secure
description: Scan a change for leaked credentials, widened permissions and tampering with the things that enforce them. Use when the user says "check this for secrets", "is this change safe", "does this widen permissions", "security review this diff", or as the security pass inside /sky:review. Reports findings with file and line and ends with exactly one line, VERDICT: APPROVED or VERDICT: BLOCKED. Strictly read-only.
agent: security
---

# /sky:secure — the security pass

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

Three things, and they are not general code review. Somebody else is looking at
whether the change is correct; this looks at whether it is safe to let in.

## Input

A diff, a branch, a merge request, or a set of files. If none is given, use the
working tree against its merge base.

## What to look for

1. **Credentials.** A token, key, password, connection string or certificate in
   the diff — including in a test fixture, a comment, a lock file, an example
   `.env`, or a commit message. **A credential in a test is a credential.**
   Check whether it is real before reporting it as one, and say which you
   concluded and why: a false alarm every week trains people to skip this pass.

2. **Widened permissions.** A role gaining an action, an allowlist gaining an
   entry, a scope going from read to write, a resource going from private to
   public, a default changing from deny to allow. Ask of each one: *who can now
   do something they could not do before, and did anyone decide that?*

3. **Tampering with what enforces the rules.** Changes to CI configuration,
   hooks, policy files, branch protection, the guard, the redaction gate, the
   tests that cover any of those. This is the category people forget, and it is
   the one that matters most: a change that disables a check is more dangerous
   than the thing the check would have caught.

## How to report

- **File and line for every finding.** A finding without a location is an
  opinion.
- **Say what an attacker or an accident does with it** — concretely. "This is
  insecure" is not actionable; "anyone who can open a pull request can now read
  the deploy token from the build log" is.
- **Separate what you verified from what you suspect.** Both are worth
  reporting; conflating them is not.
- **Say what you did not check** — a file too large to read, a binary, a
  submodule you could not reach.

End with exactly one line:

    VERDICT: APPROVED

or

    VERDICT: BLOCKED

`BLOCKED` stops shipping. A human may override one specific report, but the
override has to record who approved it, the report id and the reason — there is
no silent continue, and an agent never overrides its own review.

## What this never does

- Never edits anything, including to remove a secret it found. Removing a
  committed secret is a history rewrite and a rotation, both of which are a
  person's job — say so and stop.
- Never posts a comment or a vote anywhere.
- Never reports a finding it has not located in the diff.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the diff, and what the change makes possible** —
reading your own output and concluding it is fine is not verification.

- **Locate every finding in the diff.** Then say concretely what an attacker or an
  accident does with it — "this is insecure" is not actionable.
- **Decide whether a credential is real and say which you concluded.** A false alarm
  every week trains people to skip this pass, which costs more than it saves.
- State what you could not check, so the verdict is not read as wider than it is.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

---
name: ship
description: Turn finished work into the exact outward actions a person then takes — push, pull request, ticket comment, ticket transition. Renders commands; never runs them. Use when the user says "ship it", "what do I run now", "open the PR", "how do I push this". Requires a security verdict first.
disable-model-invocation: true
---

# /sky:ship — render the outward actions, and run none of them

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

Every outward action — a push, a pull request, a ticket comment, a transition —
is the moment work leaves the machine and becomes something other people see.
This skill produces the exact commands for those, correctly filled in, and
**stops**. The person runs them.

It is deliberately not model-invocable: shipping starts because a human said
so, never because a model decided the work looked finished.

## Before rendering anything

1. **The security pass must have run and said APPROVED.** If `/sky:secure` has
   not run, run it. If it said `BLOCKED`, stop — a human may override one
   specific report, but the override records who approved it, the report id and
   the reason, and an agent never overrides its own review.
2. **The change must be committed locally and the tests must have run.** Say
   what ran and what the result was. A red suite is not a reason to refuse to
   render, but it is a fact that goes at the top of the output.
3. **Check what the branch actually contains** — `git log`, `git diff` against
   the base. Render what is there, not what the conversation believed was
   there.

## What to render — and who renders it

**You do not compose these commands. `sky ship` does.** That is the whole
point: a skill in which the model writes the push line is a skill in which the
model chooses what goes on a command line, and every check in the runtime
becomes decoration. Your job is to say *what* is wanted; the runtime decides
what that looks like as a command, and refuses the ones it will not put there.

For each outward action, **write a small JSON file with your editor tool into
`.sky/outbox/`**, named in the order the person should run them —
`1-push.json`, `2-pr.json` — and never put the text on a command line:

```json
{ "kind": "ticket.comment", "summary": "tell the ticket",
  "issue_key": "<TICKET>", "body": "…what you want to say…" }
```

**You do not run `sky`.** When this session ends, the runtime reads the outbox,
stamps each request with this run's identity, refuses any it will not render, and
files the rest. The person then runs `sky ship`, which prints one block per action
— the exact command, and any body text separately — and runs none of them.

**Why a file and not a command.** A shell expands an argument before any program
starts. A body containing a backtick, `$(…)` or a newline has already run by the
time any check could see it. An editor tool writes bytes; no shell is involved.
`kind` is one of `push`, `pr.open`, `ticket.comment`, `ticket.transition`, and the
other fields are `branch`, `remote`, `base`, `title`, `body`, `issue_key`,
`to_state`. Do not write `run_id`, `agent_id` or any approval field: the runtime
owns those, and a request that sets one is refused.

**Expect refusals, and do not work around them.** The runtime rejects a branch
or remote that starts with `-` (it would be read by git as an option, not a
name), anything carrying a shell metacharacter, a push straight to `main` or
`master`, and an intent claiming its own approval. If one is refused, say so
and stop — a refusal is the system working.

If this is not a managed run, nothing collects the outbox: say that plainly and
stop. **Do not fall back to composing the commands yourself**: unvalidated is
exactly the state this exists to prevent.

## After

4. Say plainly: *these are not run. When this session ends, run `sky ship` and
   then the commands it shows, in its order.*
5. If the user asks you to run one, say which role could and could not, and
   that this one is theirs. In an Ethan-managed run the same actions go through
   core's broker under a grant the person gave; in an interactive session they
   go through the host's own permission prompts. Neither of those is this skill
   deciding.

## What this never does

- **Never pushes, opens, comments, transitions, merges or votes.** Not with a
  tool, not with Bash, not "just this once".
- Never renders an action the security pass has not cleared.
- Never invents a ticket id, a branch name or a reviewer.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the runtime's rendering, not your own** —
reading your own output and concluding it is fine is not verification.

- **The runtime will produce the commands, not you.** If you composed a command line,
  stop: every validation in the runtime happens after a shell has already expanded it.
- **Read each outbox file back.** One JSON object, one action, only the fields listed
  above, and named in the order the person should run them.
- A refusal is the system working. Report it; do not route around it.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

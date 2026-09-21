---
name: code
description: Implement one bounded change with tests, then stop. Use when the user says "implement this", "write the code for <TICKET>", "make this change", "code it up", or when a spec has been approved and the work is ready to be written. Runs in the developer role — edits inside the repository and commits locally; it cannot push, open a pull request, comment on a ticket or write to the knowledge base, and is not supposed to.
agent: developer
---

# /sky:code — implement one bounded change

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

The skill the Developer role exists for. It writes code, writes the tests that
prove it, runs them, and stops. **Stopping is a feature**: what to do with the
branch — push it, open a pull request, tell the ticket — is `/sky:ship`, and
every one of those is a human decision the developer role cannot take.

## Input

A change to make: a ticket id, an approved `dev.md` from `/sky:spec`, or a
plain description. If the change is not bounded — "refactor the service", "make
it faster" — say so and ask for the boundary before writing anything.

## Before writing code

1. **Get the context.** Run `/sky:context` for the ticket or topic first. Code
   written without the team's existing decisions is code that re-litigates
   them.
2. **Find, then confirm.** The code index locates a symbol, its callers and the
   tests that cover it, in repositories you have not cloned. **Read the actual
   lines you will change from the local checkout** — the index does not record
   which commit it reflects, so its staleness cannot be measured.
3. **Say what you are about to change**, in two or three lines, before you
   change it. A surprised reader is a reader who has to undo something.

## Writing it

4. **One change.** If you find a second thing worth fixing, name it and leave
   it. A branch that fixes three things is a branch nobody can review.
5. **Tests that would fail without the change.** A test that passes on both
   sides of your diff is a test that proves nothing. Say which test covers
   which behaviour.
6. **Match the code around it** — its naming, its error handling, its comment
   density. A file where one function is written in a different dialect is
   harder to read than one written badly but consistently.
7. **Run the tests.** Report what actually ran, and report failures with their
   output. If the suite was already red before you started, say so and say by
   how much — never present an inherited failure as yours or yours as
   inherited.

## Finishing

8. **Commit locally**, with a message that says what changed and why. Do not
   push. Pushing is `/sky:ship`, and it is a human's call.
9. **Report**: the files touched, the tests added and their result, anything
   you deliberately left, and anything you could not verify.

## What this never does

- **Never pushes, opens a pull request, comments on a ticket or transitions
  one.** Those are the outward actions; they belong to a person.
- **Never writes to the knowledge base.** What was learned goes through
  `/sky:learn`, per item, with a human saying yes.
- **Never edits outside the repository it was started in.**
- **Never edits tests to make them pass.** A failing test is information.

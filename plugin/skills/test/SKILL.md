---
name: test
description: Runs the right local tests for a change, module, or ticket, and names any shared-environment suite for the person to run. Use when the user says "run affected tests", "regression for X", "test this change/module", or after implementing a change. Reports what ran, pass/fail, failures, and the next step.
---

# /sky:test — run the right tests for a scope

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

Select and run the tests that cover a change, module, or ticket — not the whole suite.

## The core rule

- **LOCAL** (unit / affected tests on this machine): run them, with the command your
  role allows.
- **SHARED ENVIRONMENTS** (regression or browser suites that other people depend on):
  **never run them.** No role's policy names a tool for them, so this skill has none.
  If they are warranted, name which suites and why, and leave running them to the
  person.
- **Out of scope:** test-management tools, which keep test-case records. If asked for
  that, say it is outside `/sky:test` and stop.

## Prerequisites

1. **tenant_code**: required on every knowledge-base call. Resolve it as `CONFIG.md` describes — `$SKY_TENANT` first, then the KB map entry whose repository path is the longest prefix of the working directory, then ask once. Never guess it.
2. If the scope is a ticket (<TICKET>), pull it **live** from Jira — use a direct Jira MCP
   server if the session has one; otherwise use the KB-proxied Jira tool if available.
   Never take ticket state from ingested content.

## Procedure

1. **Determine the scope.** In order of preference:
   - A context pack already in the session (from `/sky:spec`, `/sky:bugfix`, or
     `/sky:context`): use its affected-modules and covering-tests lists.
   - Otherwise run `/sky:impact <module or <TICKET>>` to get affected modules,
     dependent services, and covering tests from the graph.
   - Only if neither is possible, fall back to the git diff on the current branch to
     infer touched modules.
   Do not default to "run everything" when the scope can be narrowed.

2. **Discover the local runner from the repo — never guess.** Check, in order:
   - `Makefile` test targets (`make test`, `make test-unit`, module-specific targets),
   - pytest configuration (`pyproject.toml`, `pytest.ini`, `setup.cfg`, `conftest.py`),
   - package scripts (`package.json` "scripts"),
   - any repo/CI docs that name the canonical test command.
   Use the repo's own command verbatim; add narrowing (paths, `-k`, markers) on top.

3. **Map scope to local tests.** Translate affected modules into concrete test paths,
   markers, or `-k` expressions. If the mapping for a module is unclear, note it as an
   OPEN question rather than silently widening the run.

4. **Run the local tests now.** Capture full output. Your role may run only the test
   commands its policy lists (for the developer: `npm test`, `pytest`, `make test`). If
   the repository's command is not one of them, do not find another way to run it: give
   the person the exact command and say why you did not run it. If failures look
   environmental (missing dependency, wrong interpreter), say so — do not retry blindly.

5. **Decide whether a shared-environment suite is warranted.** Reasons: the user asked
   for regression, the change spans several modules or public APIs, or the covering
   tests from step 1 include such suites. If local tests fully cover the change, say so.
   If a suite is warranted, list it with the reason, citing the knowledge-base document
   or node id that links it to the change. Do not run it.

6. **Report** (format below), then suggest the next step.

## Evidence rules

- Every claim that "suite X covers module Y" must cite a knowledge-base document/node id or a
  local file path. If coverage cannot be established, list it under OPEN questions —
  never guess coverage.
- Test code and runner configs are read from the **local repo checkout**, never from
  ingested content.

## Report format

Always end with these four parts:

1. **What ran** — exact local commands. State explicitly what was skipped and why,
   including any shared-environment suite left for the person.
2. **Pass/fail summary** — counts per run (passed / failed / skipped), one line each.
3. **Failures** — per failure: test name, the relevant output excerpt (assertion message
   and the few stack lines that matter), and whether it looks related to the change or
   pre-existing.
4. **Suggested next step** — one concrete action, e.g. fix the assertion in `<file>`,
   open `/sky:bugfix` for a pre-existing failure, re-run after fix, or ask the person
   to run a named regression suite. Include OPEN questions if any.

## Failure modes

- Missing `tenant_code` → `$SKY_TENANT`, else the KB map; only then ask.
- The repository's test command is not one your role may run → report the exact
  command for the person; do not route around the policy.

## Before returning: acceptance criteria, then evidence

Your first look must not be the user's first look. State what "done"
means for this task, produce a draft, then check it against **the runner's actual output** —
reading your own output and concluding it is fine is not verification.

- **Quote what ran and what it said.** "Tests pass" without the output is a claim.
- **Establish the baseline before blaming the change.** If the suite was already red,
  say by how much, and never present an inherited failure as yours or yours as
  inherited.
- Name the suites you did not run, especially any shared-environment one.

Fix everything you find and check again. Return the result with a short
note of what you verified, and say plainly what you could not — an
unverifiable thing is a finding, not something to leave for the reader.

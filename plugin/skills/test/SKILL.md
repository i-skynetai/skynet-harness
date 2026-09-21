---
name: test
description: Runs the right tests for a change, module, or ticket. Local unit/affected tests run immediately; remote shared-environment suites (regression suites, browser suites) are prepared but ALWAYS confirmed before running. Use when the user says "run affected tests", "regression for X", "test this change/module", or after implementing a change. Reports what ran, pass/fail, failures, and the next step.
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
Local tests execute freely. Remote shared-environment executions always require an
explicit user confirmation first.

## The core rule — split behavior

- **LOCAL** (unit / affected tests on this machine): run without asking. No confirmation needed.
- **REMOTE** (shared QA environments): **never fire without confirmation.** This covers:
  - regression suites — `kb_tools_regression_*`
  - browser suites — `kb_tools_browser_*`

  These consume shared QA environments other people depend on. Always present exactly
  what would run (suites, environment, scope) and wait for an explicit "yes" before firing.
- **Out of scope:** test-management tools, which keep test-case records. This skill executes
  tests; it does not create, link, or update test-case records. If asked for that, say it
  is outside `/sky:test` and stop.

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

4. **Run the local tests now** (no confirmation). Capture full output. If failures look
   environmental (missing dependency, wrong interpreter), say so and fix or report —
   do not retry blindly.

5. **Decide whether remote runs are warranted.** Reasons: the user asked for regression,
   the change spans multiple modules or public APIs, or covering tests found in step 1
   include regression or browser suites. If local tests fully cover the change, say so and skip
   remote entirely.

6. **Prepare the remote plan — then STOP and confirm.** Assemble, without executing:
   - Target environment: `kb_tools_regression_list_environments`.
   - Candidate regression scope: regression suite, specific test cases, or functional areas.
   - Candidate browser scope: `kb_tools_browser_list_suites` /
     `_list_tests` for the affected UI flows.
   Present the plan as a short list — suite/test names, environment, and why each is
   in scope (cite the knowledge-base document/node id that links it to the change). Ask:
   "Run these against <environment>? They consume a shared QA environment." Proceed
   only on an explicit yes; on no, report the local results and offer alternatives.

7. **Execute confirmed remote runs.**
   - regression: `kb_tools_regression_run_regression_tests`,
     `_run_test_cases`, or `_run_tests_in_functional_areas`; poll with
     `_get_task_status` / `_wait_for_task`; stop a runaway task with `_stop_task`.
   - browser: `kb_tools_browser_execute_suite` or `_run_test`;
     poll with `_get_suite_execution_status` / `_get_test_status`; fetch
     `_get_test_detail` and `_get_screenshot` for failures;
     cancel with `_cancel_suite_execution` if asked.
   Pass `tenant_code` on every call.

8. **Report** (format below), then suggest the next step.

## Evidence rules

- Every claim that "suite X covers module Y" must cite a knowledge-base document/node id or a
  local file path. If coverage cannot be established, list it under OPEN questions —
  never guess coverage.
- Test code and runner configs are read from the **local repo checkout**, never from
  ingested content.

## Report format

Always end with these four parts:

1. **What ran** — exact local commands; remote suites with environment and job/task ids.
   State explicitly what was skipped and why.
2. **Pass/fail summary** — counts per run (passed / failed / skipped), one line each.
3. **Failures** — per failure: test name, the relevant output excerpt (assertion message
   and the few stack lines that matter), and whether it looks related to the change or
   pre-existing.
4. **Suggested next step** — one concrete action, e.g. fix the assertion in `<file>`,
   open `/sky:bugfix` for a pre-existing failure, re-run after fix, or (with
   confirmation) widen to a regression-suite run. Include OPEN questions if any.

## Failure modes

- Missing `tenant_code` → `$SKY_TENANT`, else the KB map; only then ask.
- Regression or browser tools not available in the session → the tool surface may not include
  the test families; report which local tests ran and tell the user the remote families
  are unavailable.
- Remote task stuck → report last known status and offer `_stop_task` /
  `_cancel_suite_execution`; do not silently re-fire (that doubles shared-environment load).

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

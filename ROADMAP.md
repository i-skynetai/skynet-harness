# Roadmap

Every planned feature has an ID, a status and, once someone takes it, an owner. **This
file is the source of truth for what is being worked on.** Pick from here, and update
the row when you start and when you finish — see [Picking a feature](#picking-a-feature).

## Status

| Status | Means | Who moves it on |
|---|---|---|
| **Proposed** | an idea; the scope is not agreed yet | a maintainer, to Ready or Needs decision |
| **Needs decision** | a design choice must be made first — usually a change to the policy or to the knowledge port | a maintainer, after discussion on the issue |
| **Ready** | scope and acceptance agreed; anyone may pick it | you, when you claim it |
| **In progress** | claimed — the row names the owner and the date | the owner, when the pull request opens |
| **In review** | a pull request is open | a maintainer, when it merges |
| **Done** | merged; the row names the version | — |

Priority: **P0** a correctness bug, fix first · **P1** the next release · **P2** planned ·
**P3** an idea. Size: **S** about a day · **M** a few days · **L** a week or more, and
worth splitting.

A few words used below. The **hand** is the coding agent the harness starts (Claude
Code, Codex or Kimi). A **probe** is one check that `sky doctor` runs. The **knowledge
port** is the set of tool names a knowledge-base server must offer
([docs/knowledge-port.md](docs/knowledge-port.md)). An **intent** is a file in which the
hand asks for an outward action, such as a push. The **broker** turns an intent into the
exact command a person then runs. The **guard** is the hook that checks each shell
command during a run ([docs/policy.md](docs/policy.md)).

## Picking a feature

1. **Choose a `Ready` row.** New here? Take one marked *good first issue*.
2. **Claim it.** Open an issue with the *Claim a feature* template naming the ID, or
   comment on the feature's issue if one exists. A maintainer confirms within a few days.
3. **Mark it `In progress`** in this file — your handle and the date in the Owner
   column — in your first pull request, or in a one-line pull request of its own.
4. **For an L-sized feature, write a design note first**, from
   [the template](docs/features/TEMPLATE.md), and get it agreed on the issue before the
   code.
5. **Open the pull request.** Set the row to `In review`, and meet the acceptance
   criteria below — each one is a test. [Contributing](CONTRIBUTING.md) has what every
   change needs.
6. **On merge,** the row becomes `Done` with the version.

One feature per person at a time. A claim with no visible progress for 21 days goes back
to `Ready`, so nothing stays blocked by a claim nobody is working on. To propose
something new, open an issue with the *Propose a feature*; it gets an ID when accepted.

## Features

### 2.1.2 — correctness

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-001 | [Probes call the tools the knowledge port names](#sh-001) | probes | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-002 | [The Safety probe asks the guard as a run would](#sh-002) | probes | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-003 | [`sky ship` in the order the intents were made](#sh-003) | broker | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-004 | [A run can reach the broker](#sh-004) | broker | P0 | M | Done — 2.1.2 | @arupmmi07 |
| SH-005 | [No company-specific name in the public tree](#sh-005) | hygiene | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-006 | [A `test` skill with no vendor tools](#sh-006) | skills | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-007 | [The documented KB map works as written](#sh-007) | docs | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-008 | [One answer to which roles run on which host](#sh-008) | hosts | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-009 | [`sky kb which` gives the real reason](#sh-009) — *good first issue* | cli | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-010 | [Promises with no code behind them](#sh-010) | docs | P0 | M | Done — 2.1.2 | @arupmmi07 |
| SH-011 | [Prove the live role boundary on Claude Code](#sh-011) | hosts | P0 | M | In review | @arupmmi07, 2026-10-05 |

### 2.2.0 — clone and run

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-020 | [A demo knowledge base in the repository](#sh-020) | demo | P1 | L | In review | @arupmmi07, 2026-10-06 |
| SH-021 | [Setup with no administrator](#sh-021) | setup | P1 | S | Ready | |
| SH-022 | [`doctor` names the port tools it found](#sh-022) | probes | P1 | M | Ready | |
| SH-023 | [`doctor` with no KB map still shows the table](#sh-023) — *good first issue* | probes | P1 | S | Done — 2.1.2 | @arupmmi07 |
| SH-024 | [The Sky Context Protocol, written down](#sh-024) | protocol | P1 | M | In progress | @arupmmi07, 2026-10-06 |
| SH-025 | [A 60-second demo in the README](#sh-025) | docs | P2 | S | Proposed | |

### 2.3.0 — the run is the record

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-030 | [`sky runs`: list and show run records](#sh-030) — *good first issue* | record | P1 | S | Ready | |
| SH-031 | [The ledger records every tool call](#sh-031) | record | P1 | S | In review | @arupmmi07, 2026-10-06 |
| SH-032 | [No token left in the run record](#sh-032) | record | P1 | S | Ready | |
| SH-033 | [Pending intents: done, archived, out of git](#sh-033) | broker | P1 | S | Ready | |
| SH-034 | [Tests the developer role can run in any repository](#sh-034) | policy | P1 | M | Needs decision | |
| SH-035 | [A test runner is a shell: say so, or close it](#sh-035) | policy | P1 | M | Needs decision | |
| SH-036 | [The guard reads git's options, not a substring](#sh-036) | guard | P2 | M | Done — 2.1.2 | @arupmmi07 |
| SH-037 | [Only the runtime writes `.sky/pending`](#sh-037) | broker | P1 | S | Ready | |
| SH-038 | [The ingest skills call tools a role holds](#sh-038) | skills | P1 | S | Needs decision | |

### 2.4.0 — ports, not products

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-040 | [A code port, with skygraph as the first server](#sh-040) | ports | P1 | M | In review | @arupmmi07, 2026-10-06 |
| SH-041 | [A ticket port](#sh-041) | ports | P2 | L | Needs decision | |
| SH-042 | [The build result as a published contract](#sh-042) | ethan | P2 | S | Proposed | |
| SH-043 | [Codex and Kimi, measured again](#sh-043) | hosts | P3 | M | Proposed | |

### Distribution and trust

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-050 | [CI runs `sky selftest`](#sh-050) — *good first issue* | ci | P1 | S | Done — 2.1.2 | @arupmmi07 |
| SH-051 | [CI on macOS, and Python 3.11 checked](#sh-051) | ci | P2 | M | In progress | @arupmmi07, 2026-10-06 |
| SH-052 | [Install without a clone](#sh-052) | distribution | P2 | M | Needs decision | |
| SH-053 | [The core and its tests run on Windows](#sh-053) | distribution | P2 | M | In review | @arupmmi07, 2026-10-03 |

### 3.0 — governed sessions

One design note covers these rows, with the four decisions they share:
[docs/features/3.0-governed-sessions.md](docs/features/3.0-governed-sessions.md). It
ships as one release, in the order the note gives. SH-069 is unused.

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-060 | [A team installs the plugin once](#sh-060) | distribution | P1 | M | Ready | |
| SH-061 | [A session learns what it is at start](#sh-061) | sessions | P1 | S | Ready | |
| SH-062 | [Specialist work goes to a governed agent](#sh-062) | routing | P1 | M | Ready | |
| SH-063 | [The guard covers managed projects](#sh-063) | guard | P1 | S | Ready | |
| SH-064 | [Roles own skills, skills own tools, agents are rendered](#sh-064) | policy | P1 | M | In review | @arupmmi07, 2026-10-05 |
| SH-065 | [Three policy layers under one ceiling](#sh-065) | policy | P1 | M | In review | @arupmmi07, 2026-10-06 |
| SH-066 | [`/sky:author`: a proposal, then `sky policy apply`](#sh-066) | skills | P1 | M | Ready | |
| SH-067 | [Every tool a skill names exists on the host](#sh-067) | policy | P1 | S | In review | @arupmmi07, 2026-10-06 |
| SH-068 | [A context manifest built from recorded calls](#sh-068) | context | P2 | M | In review | @arupmmi07, 2026-10-06 |
| SH-070 | [Session cards](#sh-070) | sessions | P1 | S | Ready | |
| SH-071 | [`sky bridge`: the Claude transport](#sh-071) | bridge | P1 | L | Ready | |
| SH-072 | [One implementation owner per scope](#sh-072) | bridge | P1 | S | Ready | |
| SH-073 | [`/sky:handover`: one local format between sessions](#sh-073) | sessions | P1 | S | Ready | |
| SH-074 | [`/sky:dispatch`: local, then remote](#sh-074) | routing | P1 | M | Ready | |
| SH-075 | [Declared workflows: validation](#sh-075) | policy | P1 | S | Ready | |
| SH-076 | [One memory folder per topic](#sh-076) | sessions | P2 | S | Ready | |
| SH-077 | [The demo knowledge base is the reference adapter](#sh-077) | demo | P2 | M | In review | @arupmmi07, 2026-10-06 |
| SH-078 | [`sky bridge`: Codex delivery](#sh-078) | bridge | P2 | M | Ready | |
| SH-079 | [Declared workflows: execution](#sh-079) | policy | P1 | M | Ready | |
| SH-080 | [The context budget is enforced](#sh-080) | context | P2 | M | Ready | |
| SH-081 | [A handover reaches the knowledge base as an intent](#sh-081) | broker | P2 | S | Ready | |
| SH-082 | [Every skill's procedure uses only tools its roles hold](#sh-082) | skills | P1 | M | Needs decision | |
| SH-083 | [A local context store behind the protocol](#sh-083) | context | P1 | L | In progress | @arupmmi07, 2026-10-06 |
| SH-084 | [`sky kb init`: the project's documents, indexed](#sh-084) | context | P1 | M | In review | @arupmmi07, 2026-10-06 |
| SH-085 | [`/sky:analyze`: intent and discovery from retrieved evidence](#sh-085) | skills | P1 | M | In review | @arupmmi07, 2026-10-06 |
| SH-086 | [`/sky:plan`: a plan document from an analysis](#sh-086) | skills | P1 | M | In review | @arupmmi07, 2026-10-06 |
| SH-087 | [`/sky:decide`: decisions recorded and found again](#sh-087) | skills | P1 | S | In review | @arupmmi07, 2026-10-06 |
| SH-088 | [Codebase discovery: what the code already decided](#sh-088) | context | P1 | L | In review | @arupmmi07, 2026-10-07 |
| SH-089 | [The code index and its knowledge stay current](#sh-089) | context | P1 | M | In review | @arupmmi07, 2026-10-07 |
| SH-090 | [`sky eval`: right context, smallest context](#sh-090) | evals | P1 | L | Ready | |
| SH-091 | [The path is the policy's, not the person's](#sh-091) | routing | P1 | M | Ready | |
| SH-092 | [The user guide: install from the repository, upgrade, first task](#sh-092) | docs | P1 | M | In progress | @arupmmi07, 2026-10-06 |
| SH-093 | [The README shows an organisation what it gets](#sh-093) | docs | P1 | M | In progress | @arupmmi07, 2026-10-06 |
| SH-094 | [Contributor onboarding and documentation consistency](#sh-094) | docs | P1 | M | In progress | codex-skynet-harness, 2026-10-07 |
| SH-095 | [Native Codex plugin installation](#sh-095) | hosts | P1 | M | In progress | codex-skynet-harness, 2026-10-07 |
| SH-096 | [Claude and Codex governed implementation parity](#sh-096) | hosts | P1 | L | In progress | codex-skynet-harness, 2026-10-07 |

## Details

Each entry says what is wrong or missing today, what done looks like, and where in the
code it starts. Every acceptance line is a test.

### Correctness

<a id="sh-001"></a>**SH-001 — Probes call the tools the knowledge port names.** The port
document and the policy's tool lists name the tools `kb_similarity_search`,
`kb_documents_ingest` and so on. The probes call `kb.similarity_search`,
`kb.documents.ingest`, `kb.jobs.status`, `kb.jobs.output` and `kb.ontologies.get` —
with dots (`core/sky/probes.py:150`, `:565`, `:644`, `:663`, `:707`). Against a small
server built to the port document, `sky doctor` reports focus
`DOWN — unknown tool 'kb.similarity_search'` and `ready for: nothing`. *Done when:* a test
server that offers only the documented names gets focus `ok`; the `--deep` ingest probe
calls the underscored names; the names live in one place, and a test fails if a probe
calls a tool the policy does not list. *Starts in:* `core/sky/probes.py`, then
`scripts/vendor-runtime.py` to refresh the plugin's copy.

<a id="sh-002"></a>**SH-002 — The Safety probe asks the guard as a run would.** The probe
runs `sky guard` on a push and expects `deny` (`core/sky/probes.py:349`). But the guard
stands aside outside a managed run — it allows everything unless `SKY_LAUNCHED=1`
(`core/sky/guard.py:129`) — and the probe runs it in the caller's own environment.
`sky build` runs the probes before it builds the run's environment
(`core/sky/cli.py:164`, `:177`). So wherever a `sky` command can be found, Safety reads
`DOWN — the guard ALLOWED a push`, and every developer build is refused. The same probe
gives `down` without the variable and `ok` with it. The existing test sets the variable
itself, so it never sees this (`core/tests/test_g23b_probes_detect_breaks.py:327`).
*Done when:* the probe runs the guard with the environment a run would get; a test runs
`probe_safety` with `SKY_LAUNCHED` unset and gets `ok`; the probe runs the guard of the
runtime that is running, not whichever `sky` is first on `PATH` (`probes.py:323`).
*Starts in:* `probes._guard_answers`.

<a id="sh-003"></a>**SH-003 — `sky ship` in the order the intents were made.** Intent
files get a random name (`core/sky/cli.py:630`) and are read back sorted by name
(`core/sky/broker.py:230`), then printed under "Run them yourself, in this order"
(`cli.py:667`). Six pushes recorded as steps 1 to 6 came out as 5, 1, 6, 2, 3, 4. A pull
request can be listed before the push it needs. The contract already has a
runtime-owned `created_at` field that nothing fills (`core/sky/schemas.py:535`).
*Done when:* `sky intent` seals `created_at` and a sequence number; `sky ship` sorts by
them; a test records ten intents and gets them back in order. *Starts in:*
`cli.cmd_intent`, `broker.read_pending`.

<a id="sh-004"></a>**SH-004 — A run can reach the broker.** `sky intent` refuses outside a
managed run (`core/sky/cli.py:611`). Inside one, no role can run it: the developer's
shell is limited to `git add`, `commit`, `status`, `diff`, `log`, `npm test`, `pytest`
and `make test`, and the other three roles have no shell at all
(`plugin/policy.yaml:196`). So the `ship` skill's path — write an intent file, run
`sky intent`, then `sky ship` — cannot finish in any session. *Decision needed:* let
the developer run `sky intent --from-file`, or have the runtime collect intent files
from a fixed folder when the hand exits, so the hand never runs `sky` at all. *Done
when:* a managed developer run can leave an intent that `sky ship` renders, with a test
over the chosen path.

<a id="sh-005"></a>**SH-005 — No company-specific name in the public tree.** One
organisation's knowledge-base name appears in a help message (`core/sky/cli.py:415` and
its vendored copy), in two test files (`core/tests/test_review_v1_0_0.py:230`,
`core/tests/test_review_v1_0_1.py:265`) and in a diagram
(`docs/images/launch-paths.svg:42`). `sky selftest` cannot catch it: the word check
reads only `plugin/`, skips the vendored runtime, and skips entirely without a local
word list (`core/sky/selftest.py:130`, `:622`). Given that name, the check says `ok`
while five files carry it. *Done when:* the five places use a neutral name and the PNG
beside the SVG is rendered again; the word check covers the whole tree; CI runs it from
a committed list of hashed words, so the list itself names nobody. *Starts in:*
`core/sky/selftest.py`.
*Progress, 2026-09-30:* the name is gone from the five places and from every commit —
history was rewritten before the first push — and the PNG is rendered again. *Still
open:* the word check over the whole tree, from a committed list of hashed words.

<a id="sh-006"></a>**SH-006 — A `test` skill with no vendor tools.** The `test` skill
tells the agent to run two vendor test-suite products through tools named after them,
and names two test-management products (`plugin/skills/test/SKILL.md:3`, `:28`–`:29`,
`:33`, `:72`–`:89`). No role holds those tools, and the public tree names no vendor
product. *Done when:* the skill runs local tests, or calls a remote-suite operation
named in the policy; no vendor name remains; `sky selftest` passes. *Starts in:*
`plugin/skills/test/SKILL.md`.
*Progress, 2026-09-30:* the vendor names are gone from the skill and from every commit;
the remote families are generic (`kb_tools_regression_*`, `kb_tools_browser_*`) and
`sky selftest` passes. *Still open:* no role's policy names those operations, so the
skill should call operations the policy does name.

<a id="sh-007"></a>**SH-007 — The documented KB map works as written.** Two documents
say the map lives in `config/kb-map.json` (`docs/getting-started.md:68`,
`docs/knowledge-port.md:59`); the code reads `~/.config/sky/kb-map.json`
(`core/sky/kbmap.py:28`). Their example entry has no `ontology` or `privacy`, which the
loader requires: pasted as it is, it fails with `KB 'work_kb' is missing ontology,
privacy` (`kbmap.py:96`). *Done when:* both documents name the real path and a complete
entry; a test loads the example straight out of each document.

<a id="sh-008"></a>**SH-008 — One answer to which roles run on which host.** Three places
disagree. [hosts/README.md](hosts/README.md) offers Codex three roles and Kimi one; the
package `sky host` writes says one each (`core/sky/hosts.py:43`); the launcher allows
Codex one and Kimi none (`core/sky/launcher.py:90`). *Done when:* `hosts.py` and the
README take the launcher's table, and a test fails if any of the three differ.

<a id="sh-009"></a>**SH-009 — `sky kb which` gives the real reason.** With `--kb`, it
prints `(it is the default)` even when the named KB is not the default
(`core/sky/cli.py:117`). *Done when:* the reason says the KB was chosen with `--kb`,
with a test.

<a id="sh-010"></a>**SH-010 — Promises with no code behind them.** The docs promise six
things the code does not do: a `brain:` line in `CLAUDE.md` or `AGENTS.md` that picks
the KB (`docs/knowledge-port.md:78`, `docs/architecture.md:52`) — no code reads it, and
`selftest` treats reading a tenant from `CLAUDE.md` as retired
(`core/sky/selftest.py:76`); `$SKY_KB_MAP` (`plugin/CONFIG.md:42`) — nothing reads it; a
commit trailer the broker is said to require (`core/sky/recorder.py:103`) — nothing
writes or checks it; the plugin's own `.mcp.json` as a second tool spelling
(`plugin/CONFIG.md:20`) — the plugin ships none; `docs/gates.md`
(`core/sky/readiness.py:18`) and `docs/onboarding.md` (`CHANGELOG.md:33`) — neither
exists. *Decision needed:* which to build and which to drop. *Done when:* each one is
built with a test, or gone from the docs.

### Clone and run

<a id="sh-020"></a>**SH-020 — A demo knowledge base in the repository.** A stranger
cannot see a green `doctor` without an account somewhere. *Done when:*
`examples/demo-kb/` is a standard-library MCP server over a folder of public markdown
that offers the required port tools; `examples/demo.profile.json` points at it; on a
fresh clone with no network, starting demo-kb, `sky setup init` with that profile,
`sky doctor` (knowledge and focus `ok`) and `sky build --dry-run --role reviewer` all
pass; CI runs that sequence. *Depends on:* SH-001, SH-021. Write a design note first.

<a id="sh-021"></a>**SH-021 — Setup with no administrator.** `sky setup init` needs a
profile "your administrator sent you" (`core/sky/cli.py:372`); the only way to make one
is `admin/sky-admin profile`. *Done when:* `sky setup init` can take the address,
tenant and ontology directly, or the getting-started guide shows `sky-admin profile`
for a person who is their own administrator; tested.

<a id="sh-022"></a>**SH-022 — `doctor` names the port tools it found.** The port document
says `doctor` reports which operations are present (`docs/knowledge-port.md:19`). It
reports a count — `4 tools` (`core/sky/probes.py:78`). *Done when:* the knowledge row
names the required and optional tools found; a missing `kb_similarity_search` is `DOWN`
and a missing optional tool is `degraded` with its name; tested against a stub server.

<a id="sh-023"></a>**SH-023 — `doctor` with no KB map still shows the table.** On a fresh
clone `sky doctor` prints one line and stops (`core/sky/cli.py:52`), so the hand,
policy, guard and test-runner rows are never shown. *Done when:* with no map, knowledge
and focus read `MISSING` with the setup hint, and every other row is probed and shown;
a test covers it.

<a id="sh-024"></a>**SH-024 — The Sky Context Protocol, written down.** The tool names
are spread across the policy, the probes, `plugin/CONFIG.md` and the skills, and they
already disagree (SH-001). *Decision needed:* keep the `kb_` prefix or use bare names
(`similarity_search`); which tools are required; that every hit carries its tenant when
a server holds more than one. *Done when:* `docs/protocol.md` states it, and a test
checks the policy's tool lists, the probes and the demo server against it.
*Progress, 2026-10-06:* [docs/context-protocol.md](docs/context-protocol.md) states the
protocol: capabilities (search, graph, code, tickets, decisions, ingest), their operations
and what every hit carries, the adapter format in `.sky/context.yaml`, and the decision —
bare names in the protocol, product names in the adapter, the `kb_` prefix kept. The test
against the policy, the probes and the local store comes with SH-083.

<a id="sh-025"></a>**SH-025 — A 60-second demo in the README.** A recorded terminal
session of the SH-020 sequence and the four policy questions in
[docs/getting-started.md](docs/getting-started.md).

### The run is the record

<a id="sh-030"></a>**SH-030 — `sky runs`.** Run records sit in `~/.local/state/sky/runs/`
(`core/sky/recorder.py:29`) and no command reads them. *Done when:* `sky runs` lists
the latest runs with role, task, KB and outcome; `sky runs show <id>` prints the
events; tested with a temporary `SKY_STATE_DIR`.

<a id="sh-031"></a>**SH-031 — The ledger records every tool call.** The ledger hook fires
for `Bash` only (`plugin/hooks/hooks.json:16`), so edits, file writes and
knowledge-base calls leave no line. *Done when:* the after-tool hook covers every tool;
a line for an edit carries the file path; a test feeds an `Edit` call and finds the
line.

<a id="sh-032"></a>**SH-032 — No token left in the run record.** Each run writes the
bearer token into `mcp.json` inside its run record, and it stays there after the run —
after a dry run too (`core/sky/launcher.py:409`; `core/sky/cli.py:254` removes only
the temporary git config). The file is written before its mode is set to owner-only
(`launcher.py:410`). *Done when:* the file is created owner-only, outside the run
record, and deleted when the hand exits — or no token is written at all; a test checks
that no run record holds the token.

<a id="sh-033"></a>**SH-033 — Pending intents: done, archived, out of git.** Intents are
written to `.sky/pending` in the working directory (`core/sky/cli.py:571`), inside the
user's repository where `git add -A` picks them up. Nothing marks one done, so
`sky ship` shows them all, every time. *Done when:* intents live under the run record or
are git-ignored; `sky ship --done <id>` archives one with who and when; tested.

<a id="sh-034"></a>**SH-034 — Tests the developer role can run in any repository.** The
developer may run `npm test`, `pytest` and `make test` (`plugin/policy.yaml:196`). The
readiness probe also finds Go, Cargo and plain `unittest` suites
(`core/sky/quality.py:152`–`:165`), which the role cannot run — this repository's own
suite among them. *Decision needed:* widen the list per runner, or have the runtime run
the command the probe found. *Done when:* a developer run can run the suite the probe
found, for every runner the probe knows.

<a id="sh-035"></a>**SH-035 — A test runner is a shell: say so, or close it.** The
developer can edit files and run `make test`, `npm test` or `pytest`, so it can run any
code by editing the Makefile, `package.json` or a test. `shell.free` is marked never
(`plugin/policy.yaml:54`), and the docs call the tool list the boundary. *Decision
needed:* write the limit into [docs/policy.md](docs/policy.md), or run tests only
through a command the runtime fixes before the hand starts. *Done when:* the answer is
in `docs/policy.md`; if the gap is closed, a test shows the runtime runs the command
fixed before the run, not one the hand edited.

<a id="sh-036"></a>**SH-036 — The guard reads git's options, not a substring.** The guard
matches substrings (`core/sky/policy.py:333`), so `git -C . push origin feat/x` is
allowed while `git push origin feat/x` is denied. The tool list still stops the first
for the developer; the guard should catch the ordinary spelling too. *Done when:*
commands are split into words and git's global options (`-C`, `-c`, `--git-dir`,
`--work-tree`) are skipped before matching, with a test for each.

<a id="sh-037"></a>**SH-037 — Only the runtime writes `.sky/pending`.** Since SH-004 the
agent leaves requests in `.sky/outbox/` and the runtime seals them into `.sky/pending/`.
A developer agent can write files, so it could also write a file straight into
`.sky/pending/` that claims another run's identity, and `sky ship` would render it. The
rendering checks still apply and nothing is executed, but the identity would be false.
*Done when:* `sky ship` shows only intents whose run id matches a run record on this
machine, or the runtime keeps pending intents outside the working tree; a test plants a
forged file and it is not shown.

<a id="sh-038"></a>**SH-038 — The ingest skills call tools a role holds.** The `ingest`
and `learn` skills call `kb_documents_ingest` and `kb_jobs_logs`
(`plugin/skills/ingest/SKILL.md:74`, `:84`; `plugin/skills/learn/SKILL.md:58`, `:63`).
No role's tool list names either, and writing to the knowledge base is the outward
action `kb.ingest`. Found while closing SH-006. *Decision needed:* route knowledge-base
writes through the outbox the way SH-004 routes pushes, or give one role the write tools
with `kb.ingest` as needs-human. *Done when:* every `kb_` tool any skill names is in a
role's tool list or reaches the knowledge base through the runtime, with a test over all
skills.

### Ports, not products

<a id="sh-040"></a>**SH-040 — A code port, with skygraph as the first server.** The policy
lists thirteen code tools by one index's names (`plugin/policy.yaml:154`). Pointed at
skygraph, whose tools are named `find_symbols`, `read_source` and so on, a run gets no
code tools: the host drops tool names the allowlist does not name, silently. *Decision
needed:* a small set of code operations in the protocol (SH-024) that each server maps
to, or a tool list per server in the KB map. *Done when:* a run with its code server
set to skygraph can call skygraph's tools, and `doctor` names them.

<a id="sh-041"></a>**SH-041 — A ticket port.** Every role may `ticket.read`, and seven
skills fetch the ticket "live" from a ticket-system server — but no role holds a ticket
tool, and a managed run sees only the `kb`, `code` and `catalogue` servers
(`core/sky/launcher.py:387`). *Decision needed:* a read-only ticket port beside `kb` and
`code`, and where its token lives. *Done when:* a managed run can read a ticket by its
id, and no role can write to one.

<a id="sh-042"></a>**SH-042 — The build result as a published contract.** `sky build
--json` prints one line for a program such as Ethan (`core/sky/cli.py:122`), but its
shape is not one of the published schemas in `schemas/`. *Done when:* it is an eighth
schema, generated like the other seven, and a test checks every exit path against it.

<a id="sh-043"></a>**SH-043 — Codex and Kimi, measured again.** What each host can
enforce was measured on the versions named in `core/sky/hosts.py:40`, and the launcher's
limits rest on it (`core/sky/launcher.py:78`). Measure again on current versions, and
offer a role only where the host can hold it.

### Distribution and trust

<a id="sh-050"></a>**SH-050 — CI runs `sky selftest`.** CI runs the unit tests only
(`.github/workflows/tests.yml`); `sky selftest` runs only when someone remembers.
*Done when:* the workflow runs `./core/bin/sky selftest` on every push, and a pull
request that lets the vendored runtime drift fails.

<a id="sh-051"></a>**SH-051 — CI on macOS, and Python 3.11 checked.** CI runs on Linux
only. The test-runner probe expects plain `unittest` to exit 5 or say "no tests ran" on
an empty selection (`core/sky/quality.py:162`), and whether Python 3.11 — which the
README supports — does either is not checked. *Done when:* the matrix adds macOS, and
a test pins the probe's answer on 3.11.
*Progress, 2026-10-06:* CI's 3.11 job had failed since f3751b6: on 3.11 `python -m
unittest` exits 0 and prints "Ran 0 tests" for an empty selection, where 3.12 exits 5 and
prints "NO TESTS RAN". The probe now reads both as healthy; one test pins the answer per
interpreter and one feeds the probe a 3.11-style answer on any interpreter. The macOS
runner is still open.

<a id="sh-052"></a>**SH-052 — Install without a clone.** There is no package metadata; the
runtime reaches people by clone, by `sky setup` copying a launcher, or inside the
plugin. *Decision needed:* a package installable with `pipx`, or clone and plugin only.

<a id="sh-053"></a>**SH-053 — The core and its tests run on Windows.** On Windows 11 the
core suite fails 48 tests and hangs: stopping a hand uses `signal.SIGKILL`, which Windows
lacks, and tests assume file modes, `sh` wrapper scripts and shebang execution. *Done
when:* `python -m unittest discover -s core/tests -t core` passes on Windows, with every
POSIX-only check skipped with a stated reason, and still passes on Linux.
Out of scope, still POSIX-only: the launcher `sky setup init` writes is a shebang
script in `~/.local/bin`, and how a Windows host runs the `sky-headers` helper is not
measured.

<a id="sh-011"></a>**SH-011 — Prove the live role boundary on Claude Code.** The launcher
passes `--allowedTools` and calls it the boundary (`core/sky/launcher.py:348`–`:357`),
and the README says a role without `Bash` cannot run a command. Claude Code's reference
says `--allowedTools` only pre-approves; what restricts is the agent definition the
launcher also passes with `--agent sky:<role>`, which `hosts/README.md:19` already names.
A maintainer probe on Claude Code 2.1.286 confirmed both: `--agent` with `tools: Read`
left one tool; `--allowedTools Read` left every tool, and `Edit` ran
([docs/features/SH-011-probe-2026-10-05.md](docs/features/SH-011-probe-2026-10-05.md)).
*Done when:* an integration check, run against a recorded
Claude Code version, shows a reviewer run cannot call `Edit`, `Bash` or an unlisted MCP
tool and a developer run gets no tool outside its list, with the observed tool events
kept; the launcher refuses to start when the agent definition is missing or differs from
what the policy renders; the launcher comments and the README say which mechanism is the
boundary. A finite denylist does not count as default deny.
*Progress, 2026-10-05:* `core/sky/agent_definitions.py` checks the role's agent file
against the expanded policy before a Claude launch; `sky build` refuses with the role,
file and first differing tool and records `launch_refused`; `--dry-run` and `sky doctor`
show the check as a named row under Safety. `scripts/check-role-boundary.py` runs the
three live cases against a logged-in CLI (not in CI); its record for 2.1.286 is
[docs/features/SH-011-role-boundary-2026-10-05.json](docs/features/SH-011-role-boundary-2026-10-05.json).
Twenty-one tests. Along the way every host subprocess in the core now reads UTF-8 with
replacement, a Windows follow-up to SH-053.

### 3.0 — governed sessions

The design, the four decisions and the facts each row depends on are in
[docs/features/3.0-governed-sessions.md](docs/features/3.0-governed-sessions.md).
Every *Done when* names its failure cases; each is a test.

<a id="sh-060"></a>**SH-060 — A team installs the plugin once.** Each person adds the
plugin by hand and nothing checks that they did. *Done when:* a sample repository holds
the documented `.claude/settings.json` (`extraKnownMarketplaces`, `enabledPlugins`) and
`sky setup team` prints the same two install commands for the case where trust was not
yet granted; `sky doctor` reports `plugin: MISSING` when the plugin is not enabled and
`ok` when it is; tested offline for the settings and the doctor rows, and once by an
authenticated integration check whose host version is recorded. Failure cases: trust
declined, marketplace unreachable, plugin disabled after install.

<a id="sh-061"></a>**SH-061 — A session learns what it is at start.** No hook speaks at
session start. *Done when:* a `SessionStart` hook runs `sky session brief`, whose output
names the project, the card or "none; run `sky session new`", the policy layers in
force, the KB status, the bridge status, and the fixing command for each missing thing;
the same text is a section of `sky doctor`. Failure cases: outside a managed project the
hook prints nothing; a malformed `project.yaml` yields one line saying so and nothing
else; KB or bridge unreachable is reported, not hidden; resume behaves as start.

<a id="sh-062"></a>**SH-062 — Specialist work goes to a governed agent.** In a managed
project Claude can start `general-purpose` or any ad-hoc agent
(`plugin/skills/context/SKILL.md:23`). *Done when:* a `PreToolUse` hook on `Agent` runs
`sky route`, which allows `sky:*`, the org plugin's agents and rendered project agents,
and denies the rest with a reason naming `/sky:dispatch`; the `context` skill's fallback
is removed. Failure cases: outside a managed project everything is allowed; malformed
hook input is denied; a policy that will not load denies with the reason; a name that
collides between plugins is denied; an allowed agent the host does not have is reported
by `doctor`. Tested with recorded hook inputs.

<a id="sh-063"></a>**SH-063 — The guard covers managed projects.** `guard.scope` is
`harness_runs_only`. *Done when:* the value `managed_projects` exists; the guard applies
in any session whose repository root holds `.sky/project.yaml`, from any subdirectory or
worktree of it, and stands aside elsewhere. Failure cases: a policy that will not load in
a managed project denies every guarded command with the reason; `fails: closed-in-run`
keeps its meaning for `sky build` runs; a `cd` inside the run does not change the answer.

<a id="sh-064"></a>**SH-064 — Roles own skills, skills own tools, agents are rendered.**
A role lists tools; no skill can be granted or carry its tools; each agent's list is
kept by hand in two places. *Done when:* the policy has `tools:` bindings (name →
action), `skills:` with `tools`, and roles with `base_tools` and `skills`
(`roles.<r>.skills` is the only authoritative list); `sky policy render` writes every
plugin agent's `tools:` line and the project agents and skills into `.claude/`; the
shipped roles render to the lists they hold today. Failure cases, each a lint failure:
a rendered file that differs from the policy; an unknown skill, role or action; a skill
that names its roles; a project agent whose name collides with a plugin agent; a union
that would hand a role a tool bound to an action it lacks.
*Progress, 2026-10-05:* the policy has `tools:` bindings (tool → action, `reviewed_by` on every
MCP tool), `skills:` for all twenty skills, and roles with `base_tools` and ordered `skills`;
`sky policy render` writes the agents' `tools:` lines and `plugin/registry.json` with the
policy digest; the shipped conversion leaves the four agent lines byte-identical. Skills
whose procedures need tools their roles lack are declared but not granted (SH-082), and
`sky policy show` lists them. Twenty-six tests, plus three for quoted keys in the YAML reader.

<a id="sh-065"></a>**SH-065 — Three policy layers under one ceiling.** One file; a team
cannot add to it without editing the plugin. *Done when:* `sky policy` reads shipped,
then the org plugin named in `project.yaml`, then `.sky/policy.yaml`; a later layer may
add skills, bindings, agents, workflows and cards, and remove a grant; `sky policy show
--layers` says where each grant came from. Failure cases, each a lint failure: a layer
that plainly allows an outward action; binds a tool to an unknown action; changes an
action's classification or `never`; changes the guard's scope or failure mode; re-grants
through an alias, a new skill or a new agent what an upper layer removed; a named org
plugin that is not installed.
*Progress, 2026-10-06:* `core/sky/project.py` resolves a managed project (`.sky/project.yaml`,
per worktree) and `core/sky/policy_layers.py` merges shipped → org → project as patches
under the ceiling, with per-role revocations (the removed skill and the tools actually
lost) that no lower layer can undo; `sky policy render` in a managed project writes
`.sky/registry.json` and a project agent only when a role's tool set really differs from
the plugin's, deleting one it owns when the difference goes away;
`show --layers` attributes every grant; explicit `--policy`/`SKY_POLICY` bypasses layering
with a notice. A narrowed or added role refuses `sky build` until SH-062. Forty-eight tests.

<a id="sh-066"></a>**SH-066 — `/sky:author`: a proposal, then `sky policy apply`.** No
way to add a skill, bind tools or change a rule except by hand; and the policy says an
agent may never promote a skill or change a permission. *Done when:* `/sky:author` takes
a request in words, searches the catalogue first, checks every tool it would bind exists
in the session and has an action, writes `.sky/proposals/<id>/` (skill folder and policy
patch), runs lint against the would-be result, and stops; `sky policy apply <id>`, run by
a person, moves it into the layer and renders. Failure cases: a missing tool names the
server to connect and stops; a lint failure in the would-be result is shown and nothing
is written outside the proposal; before `apply`, a second session sees the old policy and
the old tools (tested by reading the effective policy from another process); an
org-layer proposal is a patch against the org plugin's source, and `apply` refuses to
write into an installed copy.

<a id="sh-067"></a>**SH-067 — Every tool a skill names exists on the host.**
`scripts/check-allowlists.py` checks role tools against live servers, not skills, and
has no list of the host's built-ins. *Done when:* it checks `skills:` and `tools:`
bindings too, knows each hand's built-in tool names, and fails on a name no server and no
hand provides. Failure cases: a server that is configured but unreachable now is
reported as such, not as a missing tool; an offline run uses the recorded inventory and
says so.
*Progress, 2026-10-06:* `scripts/check-allowlists.py` checks bindings, every skill and each
role's effective tools against each hand's built-ins (`core/sky/hosts.py`) and a recorded
inventory of live servers (`.sky/tool-inventory.json`, `core/sky/inventory.py`); an
unreachable server falls back to its dated inventory, `--offline` never contacts one,
and MCP annotations drive the read-only and destructive rules. Sixteen tests.

<a id="sh-068"></a>**SH-068 — A context manifest built from recorded calls.** The
retrieval order is advice in prompts; nothing says what a pack used. *Done when:* the
ledger records each retrieval call the `context-retriever` makes, with source and
response size; `sky context manifest` builds a `context-manifest` from those events with
per-item size, a measured total and the counting method named (schema change: today it
has `budget_tokens` only and `additionalProperties: false`); the run record keeps it.
Failure cases: a malformed manifest is refused; an unavailable index is an event, not a
silence; a verification call before any index call is marked in the manifest.

<a id="sh-070"></a>**SH-070 — Session cards.** A session has a name and a folder and
nothing that says what it owns. *Done when:* `sky session new <name> --topic --scope
--roles --hand` writes `.sky/sessions/<name>.yaml` against a schema (name, topic, scope
as canonical paths, roles, hand, owner, created); `sky session list` reads them. Failure
cases: a malformed card, a duplicate name, an unsupported role or hand, a scope path
outside the repository — each refused with the reason.

<a id="sh-071"></a>**SH-071 — `sky bridge`: the Claude transport.** Nothing that ships
lets sessions hand work to each other. *Done when:* `core/sky/bridge/` holds the
registry, Claude inbox delivery and the wake hook, with tests; a session registers by
presenting its card and the host session id; a message carries registration id, message
id, `created`, time-to-live, mode and the sender's run stamp, and an envelope line that
it grants nothing; the transport is a local database and opens no network port; `sky
bridge send|inbox|reply|sessions` work; a round-trip test runs Claude to Claude with no
Codex configured. Failure cases: unknown or unregistered sender, forged or missing card,
expired or replayed message id, a mode the receiver's card does not allow, delivery
failure — each refused or reported with the reason. Write a design note first.

<a id="sh-072"></a>**SH-072 — One implementation owner per scope.** The prototype
allows one implementation owner per project folder, so two topic sessions in one
repository cannot both take work. *Done when:* ownership is a lease on a card's scope,
compared as canonical paths; two disjoint scopes in one repository both take
implementation work; overlapping ones do not. Failure cases: case-only path differences,
parent and child paths, and symlinks compare as overlapping; two simultaneous claims
yield one owner; a lease is released explicitly or expires after a crash and is then
claimable. Scope ownership is scheduling, not a filesystem boundary, and the docs say so.

<a id="sh-073"></a>**SH-073 — `/sky:handover`: one local format between sessions.**
Nothing writes or reads `session-summary` between sessions. *Done when:*
`/sky:handover` writes a summary to `.sky/handovers/`, KB or no KB; a bridge reply
carries the summary; `sky session brief` seeds a new session on the same topic from the
latest handover; the schema gains `topic`, makes `kb` optional and opens `role` to policy
roles. Failure cases: an invalid summary is refused; a handover for another topic is not
used as a seed; a stale handover is named with its date. Ingestion is SH-081.

<a id="sh-074"></a>**SH-074 — `/sky:dispatch`: local, then remote.** Routing a goal is
done by a person. *Done when (local, ships with SH-062):* `/sky:dispatch` reads
`routing:` from the policy, picks an agent or a workflow in this session, states the
choice and why, and runs it. *Done when (remote, after SH-071 and SH-073):* it can pick
a named session from the cards, send over the bridge, and record the handover it gets
back. Failure cases: an ambiguous or missing route is asked, not guessed; a target
session that is not registered, or whose card denies the mode, is refused with the
reason.

<a id="sh-075"></a>**SH-075 — Declared workflows: validation.** The order context →
gate → build → review → ship lives in prompts and in people. *Done when:* `workflows:`
in the policy lists steps, each naming an agent in this session, a named session, or a
hand; the shipped `feature` workflow includes a duplicate check against tickets, PRs and
the KB; `sky policy lint` checks every step names something that exists. Failure cases:
a cycle, an unknown agent or session, a step naming an outward action as if it ran it.

<a id="sh-076"></a>**SH-076 — One memory folder per topic.** The host keeps memory per
working folder, so every session opened from one folder loads every topic's notes.
The host keeps auto-memory per repository, shared across worktrees, and offers
`autoMemoryDirectory` in any settings scope, including a per-launch `--settings <file>`
(checked 2026-10-06). *Done when:* `sky session new` writes
`.sky/sessions/<name>.settings.json` with `autoMemoryDirectory` set to an absolute
`.sky/memory/<name>/`, records that path on the card, and `sky session open <name>`
prints the launch command; `sky doctor` warns when two cards resolve to one memory
location or a card's location does not exist; the guide shows the layout. Failure cases:
a card whose settings file is missing or names another path; two cards sharing a memory
directory; a session opened without `--settings` (the brief says so, from the host's
memory location against the card's).

<a id="sh-077"></a>**SH-077 — The demo knowledge base is the reference adapter.** The
demo KB (SH-020) answers the knowledge port; it does not show how a team's own source
plugs in. *Done when:* it answers the protocol's search and graph capabilities through a
`.sky/context.yaml` adapter, and the context contract tests run offline against it.
Failure cases: a malformed adapter, an unsupported capability, an unreachable index.
*Depends on:* SH-020, SH-024.

<a id="sh-078"></a>**SH-078 — `sky bridge`: Codex delivery.** The Claude transport
(SH-071) carries nothing to a Codex session. *Done when:* a Codex hand configured in
`project.yaml` can receive and reply; the managed Codex reviewer keeps its read-only
sandbox. Failure cases: with no Codex hand the route is skipped with a stated reason; a
Codex thread held by two processes is refused.

<a id="sh-079"></a>**SH-079 — Declared workflows: execution.** A validated workflow does
not yet run. *Done when:* `/sky:dispatch` runs one step by step and records each.
Failure cases: a failed gate stops the developer step; a missing optional session is
skipped and said; the `ship` step prints commands and executes none.

<a id="sh-080"></a>**SH-080 — The context budget is enforced.** A manifest (SH-068)
records size; nothing acts on it. *Done when:* `context.max_tokens` in `project.yaml`
is applied to the measured total; over budget the pack is not delivered, the retriever
returns the manifest and a finding, and a person may approve a larger budget for the
task. Failure cases: exactly at the cap delivers; cap plus one does not; a missing
budget uses the shipped default and says so.

<a id="sh-081"></a>**SH-081 — A handover reaches the knowledge base as an intent.**
Publishing to a remote knowledge base is outward and a person runs it (persisting into
the local store is the runtime's local edit, SH-083), and today the broker refuses
`kb.ingest` as unsupported (`core/sky/broker.py:217`). *Done when:* `/sky:handover` with
a remote engine configured drops a `kb.ingest` intent in `.sky/outbox/`; the runtime validates it
against the schema and seals it; the broker renders it as a human-executable step — the
exact command or the manual instruction, with the stamp and the source file shown —
and `sky ship` prints it in order with its provenance. Failure cases: no KB — the local
handover is still written and no intent is made; a payload or stamp that fails the gate
is refused at sealing; a refused approval means no remote write happens while the local
handover stays; a direct ingest call from an agent is not in any rendered tool list.
*Decision needed:* the human execution contract — a printed command, or an instruction
to run `sky ingest <file>` which itself asks for confirmation.

<a id="sh-082"></a>**SH-082 — Every skill's procedure uses only tools its roles hold.** When
skills were given their tool lists for SH-064, eleven procedures turned out to call
things no role holds: `adr`, `analyze` and `design` write files or run the renderer
from a read-only role; `ingest` and `learn` call `kb_documents_ingest` and
`kb_jobs_logs` (SH-038); `review` posts after confirmation; `spec` delegates with
`Agent`; `sync` activates files, which SH-066 forbids; `build`, `doctor` and `setup` run
`sky` commands no role lists. SH-064 declares those skills and grants none of them beyond
the tools their roles already have, and `sky policy show` lists them as "declared,
granted to no role". *Decision needed, per skill:* rewrite the procedure to prepare
(an intent, a proposal, a document for the owner) instead of act; move the step to the
parent session or a person; or grant a tool and say which action it binds to. *Done
when:* no skill in the plugin names a tool outside its roles' rendered lists, checked by
a test over `plugin/skills/*/SKILL.md`, and the "granted to no role" list is empty or
every entry is a parent-only skill marked as such in its frontmatter. *Depends on:*
SH-064, SH-038, SH-066.

<a id="sh-083"></a>**SH-083 — A local context store behind the protocol.** No engine ships, so no
run can retrieve or write back anything. *Done when:* `sky kb serve` starts a
standard-library MCP server over `.sky/kb/` (Markdown with frontmatter: `id`, `type`,
`title`, `relates_to`, stamp fields) answering the protocol's **search** (keyword
ranking over chunks, top-k with scores and citations), **graph** (`relates_to` edges,
neighbours by type), **ingest** (write a stamped document; refuse an unstamped one) and
**decisions** (search by question; record); `.sky/context.yaml` maps the protocol names
to it; `sky kb put <file>` is the runtime's validated write path (schema, stamp,
citations, path containment, no symlink escape; atomic document-plus-manifest update;
stable document and chunk ids; schema version); `sky doctor` shows it `ok`; `sky build
--dry-run --role reviewer` passes against it offline, with the capabilities the local
store lacks shown `absent`. Failure cases: a document without frontmatter is indexed by
title only and reported; a malformed `relates_to` is a finding, not a crash; a write
without a stamp, with a traversal path or a symlink escape is refused; an interrupted
write leaves the previous document and manifest intact and reports failure; two writers
serialise on a lock; search on an empty store returns zero hits, not an error. *Depends on:* SH-024.
SH-020's demo becomes `sky kb init` over `examples/demo-docs/`.
*Progress, 2026-10-06:* design note [docs/features/SH-083-context-loop.md](docs/features/SH-083-context-loop.md)
(nine slices, decisions recorded). Slice 1 in the tree: `core/sky/kbstore.py` (immutable
revisions, one atomic manifest commit, stable ids, locks, validated put) and
`core/sky/kbserve.py` (stdio MCP: search, neighbours, decisions_find, decisions_record,
ingest), `schemas/decision.schema.json`, `schemas/knowledge.schema.json`, the analysis,
plan and knowledge templates; 31 tests. CLI, adapter and doctor wiring are slice 2.
*Slice 2, 2026-10-06:* `sky kb serve|put|show|search` over the managed project's store
(`--root` for an explicit one); `sky kb serve --write-adapter` writes the `local` source into
`.sky/context.yaml`; `sky doctor` shows one row per protocol capability (`ok` / `MISSING` with
the first missing tool / `absent`), and a reviewer dry-run passes offline against the local
store with no KB map; `kb.put` is a recorded event; the local server's three read tools are
bound to `kb.read` and granted through `kb_read`, its write tools to no role. A plain Markdown
file is accepted with `--type`, its metadata synthesised. Forty-one tests. Next: the code
port (SH-040) and the ledger over MCP calls (SH-031/068).
*Slice 3, 2026-10-06:* the code port (`core/sky/codeport.py`) with skygraph as its first
adapter, written by `sky context adapter code --from-mcp-json <path> --server <name>`; the
ledger records every MCP call in a managed session (`plugin/bin/sky-ledger-mcp`, hooks on
`PostToolUse` and `PostToolUseFailure` for `mcp__.*`); `sky context manifest <run>` builds
the context manifest from those events. Checked against the real skygraph server: the
`code` row reads `ok`. Forty-six tests.
*Slice 4, 2026-10-06 (SH-084, SH-020, SH-077):* `sky kb init` indexes README.md, docs/** and
`.sky/handovers/**` (or `context.sources` from `.sky/project.yaml`) through the runtime's
validated put path; idempotent by digest, removed sources marked stale, secret-shaped,
binary and over-cap files skipped and listed; code-index coverage recorded, never
claimed complete. `sky setup init --local` bootstraps a managed project with no token or
service. The doctor's focus row searches a real title and names it. The offline example
under `examples/` runs the six commands against five public sample documents and the
reviewer dry run passes. Forty-seven tests.
*Slice 5, 2026-10-06 (SH-087):* decisions have a lifecycle. An agent proposes (`sky kb decide
propose --from <file>|-`, or the `decide` skill returns the proposal text); only a person
accepts, rejects or supersedes, and the runtime writes the approval evidence (actor,
session, event, digest, method) as a new revision — refused under SKY_LAUNCHED, refused
at `sky kb put` when an agent supplies approval fields. `decisions.find` ranks candidates
and flags `closes` only for accepted + current + in-scope decisions with a verified
evidence revision. Four event kinds. Twenty-nine tests.
*Slice 6, 2026-10-06 (SH-085, SH-086):* `/sky:analyze` returns an analysis the runtime
validates and stores (`sky kb analyze put`): every finding cites a file:line or record that
resolves; a question is "closed by" a decision only after the store re-checks that the
decision is accepted, current, in scope and on the same evidence revision; retrieval
measurements come from the ledger, never from the agent. `/sky:plan` (`sky kb plan put
--analysis <id>`) refuses while any question is OPEN, pins the analysis, decision and
knowledge revisions and the checkout, and reports `stale` with reasons when any moved.
Today's module-card skill is `/sky:module`; analyze and plan are read-only skills.
Forty-three tests.
*Slice 7, 2026-10-07 (SH-088, SH-089):* `sky kb init --discover` asks the code index for
the module map and builds a discovery worklist (modules by size, their files and symbols,
a character budget per module, partial and unoutlined marked) as a run artefact; the
`/sky:discover` skill works one module at a time and returns knowledge records that
`sky kb knowledge put` validates: category, confidence, module in the worklist, every
citation a file:line that resolves at the pinned checkout, never a decision. `sky kb
refresh` marks records stale when their cited files change, asks the index to refresh
through the runtime-only `index.refresh` capability, and short-circuits on an unchanged
digest; an edit hook enqueues paths and a Stop hook runs the refresh. Plans report stale
knowledge pins. Checked against the live skygraph index: eight modules, worklist written.
Forty tests.

<a id="sh-084"></a>**SH-084 — `sky kb init`: the initial discovery.** The store starts
empty and nothing fills it; a brownfield project's documents and code index are never
connected in one step. *Done when:* `sky kb init` walks `README.md`,
`docs/`, `docs/adr/` (or the folders `project.yaml` names), `.sky/handovers/` and any
`--add <path>`, writes each into `.sky/kb/` with a stamp (`sky_agent` = `runtime`), a
`type` (readme, doc, adr, design, handover, analysis, plan, decision) and a source path,
and writes `.sky/kb/manifest.json` (what, from where, when, digest); connects the code
index named in `.sky/context.yaml` (SH-040) and records its coverage in the manifest;
overlapping sources (`docs/` and `docs/adr/`) are indexed once by canonical path; the
store's own files, `.sky/runs/`, secrets and `.env`-style files are excluded; a second
run changes nothing unless a source changed; with `--discover` it runs SH-088. Failure cases: a source outside the repository is
refused; a binary or a file over the size cap is skipped and listed; a removed source is
marked stale in the manifest, not deleted.

<a id="sh-085"></a>**SH-085 — `/sky:analyze`: intent and discovery from retrieved
evidence.** Today `/sky:analyze` writes a module card; nothing analyses a *goal*. *Done
when:* the module card moves to `/sky:module` (its triggers follow); `/sky:analyze
<goal>` runs in the `context-retriever` agent and produces `analysis-<id>.md` from
`plugin/templates/analysis.md` with: the intent restated, what exists (store hits, cited
by id), what is affected (code tools against the checkout), risks, and OPEN questions;
each OPEN question is first searched in **decisions**; a candidate closes it only when
it is an accepted, current decision whose scope applies, and the record id is the
evidence; the agent returns the document and the runtime writes it with `sky kb put`.
The skill retrieves by query and never reads the corpus wholesale; the manifest (SH-068)
records what it used. Tests are deterministic over a fixture corpus (protocol calls,
citations, decision applicability, template, persistence) plus a scripted fake-hand
end-to-end trace; real analysis quality is measured by `sky eval --live` (SH-090), not
claimed here. Failure cases: no store → the skill says `sky kb init` and stops; zero hits → the
analysis says so and lists what it looked for; a question with two conflicting records,
a paraphrase sharing no words with a record, a superseded record, or a record from
another scope → stays OPEN, with the candidates listed. Tested with the local store over a fixture corpus.

<a id="sh-086"></a>**SH-086 — `/sky:plan`: a plan document from an analysis.** Nothing
turns an analysis into steps an agent can take. *Done when:* `/sky:plan <analysis-id>`
produces `plan-<id>.md` from `plugin/templates/plan.md`: ordered steps, the agent (or
session, or hand) for each, acceptance per step, the decisions it rests on (by id), and
the OPEN questions that block it, and the digests of the analysis and decisions it
rests on; the runtime writes it to the store and `/sky:dispatch` can run it as a
`feature` workflow instance (SH-075/079); a plan whose inputs changed since (digest
mismatch) is refused until re-planned. Failure cases: an analysis with
OPEN questions produces a plan whose first step is "decide: …" and nothing else runs;
a step naming an agent no role renders is a finding; an analysis id not in the store
is refused.

<a id="sh-087"></a>**SH-087 — `/sky:decide`: decisions recorded and found again.** A
person's answer dies with the conversation, so the same question is asked next time.
*Done when:* `schemas/decision.schema.json` exists (id, version, project, scope,
question and aliases, answer, rationale, status accepted|superseded, supersedes, source
analysis, evidence revision; runtime-written `recorded_at`, run identity, `decided_by`,
`approval`); `/sky:decide <question> <answer>` asks the person to confirm in the session,
and the runtime writes the record with that approval evidence; the protocol's
**decisions** capability returns ranked candidates by deterministic lexical score and
curated aliases; `/sky:analyze` closes an OPEN question only with an accepted, current,
in-scope record. A record without approval evidence is an observation and never closes
a question. Failure cases:
a decision without an answer or without approval is refused; two accepted records for
one question are both returned and neither closes it until one supersedes the other;
recency alone never wins; a decision recorded in one project is not returned in another
(scope).

<a id="sh-088"></a>**SH-088 — Codebase discovery: what the code already decided.** An
analysis today knows the documents but not the conventions the code encodes. *Done
when:* `sky kb init --discover` (or `/sky:discover`) walks the modules the code index
names and, for each, runs a bounded retrieval through the code port (symbols,
dependencies, call sites, never whole folders) in the `context-retriever` agent and a
judgement in the `architect` agent, and writes **knowledge records** (`type: knowledge`)
to the store from `plugin/templates/knowledge.md`: implemented decisions (libraries and
clients in use, communication style between services, interface style, validation
framework), patterns and practices, business rules, non-functional requirements — each
with `file:line` citations, the module it belongs to, the checkout and index digests it
was derived from, and a stated confidence (a citation shows where a rule lives, not
that the intent was inferred correctly) against `schemas/knowledge.schema.json`; a
record with no citation is refused; knowledge records are observations and never close
an OPEN question; the run's manifest shows characters retrieved per module. Failure cases: a
module with no index coverage is listed as uncovered, not invented; a module over the
retrieval budget is split or marked partial; a second run updates only modules whose
index digest changed. *Depends on:* SH-040, SH-083, SH-084. Write a design note first.

<a id="sh-089"></a>**SH-089 — The code index and its knowledge stay current.** After a
change, the index and the knowledge records that cite the changed files are wrong until
someone notices. *Done when:* a `PostToolUse` hook on `Edit`, `Write` and `NotebookEdit`
in a managed session (its own matcher entries beside the existing `Bash` guard and
ledger hooks, sharing one managed-project resolver, and no longer requiring
`SKY_LAUNCHED`) appends changed paths atomically and de-duplicated to
`.sky/pending-reindex`; a `Stop` hook (or
`sky kb refresh`) asks the code port to re-index exactly those paths — the action `code.index.refresh`, automatic for a local
index and an intent for a remote one — and marks knowledge records citing them `stale:
true`; `/sky:refresh` re-derives stale records only, the
SH-088 way; before any retrieval or refresh the resolver compares source and index
digests and marks records stale on any observed change, so `Stop` is a convenience,
not the guarantee (it does not run on an interruption); `sky doctor` shows the count of
stale records. Failure cases: a code port
with no re-index capability is reported, and the paths stay pending; a path outside the
repository is ignored and logged; a path still being edited is not consumed; a
re-index that fails or times out keeps the paths pending and records the attempt; edits
made through `Bash`, by a child agent, or by another session are caught by the digest
comparison; duplicate hook deliveries change nothing; the hook stands aside outside a
managed project.

<a id="sh-090"></a>**SH-090 — `sky eval`: right context, smallest context.** Nothing
measures whether retrieval returns what a task needs, or how much it costs. *Done when:*
`evals/golden/<task>.yaml` holds a task, the record ids and code locations its context
must include, an upper bound on characters, and a rubric for the analysis and plan;
`sky eval` runs retrieval for every task against the store (top-k with k stated per
task; unique record ids, chunks of one record counted once) and prints per task: recall
and precision over those ids (zero hits → recall 0, precision undefined and shown as
such), characters and estimated tokens delivered, pass/fail against the bound; with
`--live` and a configured hand it runs `/sky:analyze` and `/sky:plan`, scores them
against the rubric, and records the hand's reported tokens; `sky eval --baseline` writes
`evals/baseline.json` (a reviewed change, like any file), and CI fails on a drop in
recall or a rise in characters beyond a stated tolerance; the offline part is
deterministic, the `--live` rubric score is labelled as a live evaluation. Failure cases: a golden task naming a record that no longer exists is a
failure, not a skip; a store that is empty fails every task with the reason; `--live`
without a hand is refused. Ships with a fixture corpus and at least five golden tasks
drawn from this repository's own documents.

<a id="sh-091"></a>**SH-091 — The path is the policy's, not the person's.** A person can
start implementation without an analysis or a plan, and skip review. The claim is scoped to **governed launches**: a governed agent started through the
`Agent` hook, a `sky build` run, or work received over the bridge. The parent session's
own `Edit`/`Write` are not gated (D1), and the docs say so. *Done when:* the dispatcher
writes run-scoped **admission state** (`.sky/runs/<id>/current.json`: canonical
project and worktree, plan and analysis digests, workflow and step, the one permitted
agent identity, policy digest, and a single-use expiring dispatch token); `sky route`,
the launcher and the bridge receiver each admit an implementation agent (developer, or
any role granted a skill that edits repository code) only when that state is present,
valid, unexpired and matches the call, and atomically reserve the token; the step
advances only on a validated completion, not on the next call; a plan whose analysis has
OPEN questions, or a step out of the declared `feature` order, is refused; producing an
analysis, a decision or a plan, and the runtime's write-back, are never gated; the brief shows the
current task's position in the workflow; `/sky:dispatch` is the only entry point and
records each step in the run; reviewer and security agents are given the project's
knowledge records for the touched modules as context. Failure cases: a plan id not in
the store, a forged or replayed token, a second concurrent call for the same step, a call
from another session or worktree, a resumed session with stale state, a revoked grant,
or an analysis or decision changed since the plan (digest mismatch) — each refused with
the reason; outside a managed project nothing changes. *Depends on:*
SH-062, SH-075, SH-079, SH-086, SH-088.

<a id="sh-092"></a>**SH-092 — The user guide: install from the repository, upgrade, first
task.** A team that wants this has to read the roadmap to learn how to install it.
*Done when:* `docs/user-guide.md` walks a team from nothing to a governed first task:
install the plugin into Claude Code straight from this repository's marketplace
(`/plugin marketplace add`, `/plugin install`, and the project settings that do it for
everyone who opens the repository), install for Codex (`sky host codex`), upgrade to a
newer version and what changes for them, `sky setup` and `.sky/project.yaml`,
`sky kb init`, the first `/sky:analyze` → `/sky:plan` → `/sky:dispatch`, what a person
runs by hand (`sky ship`, remote ingestion), and how to add their own skills through a
proposal. Each step shows the command and the real output; every picture is PNG with
its Mermaid or SVG source under *Diagram sources*; `check-docs.py` passes. Failure
cases: a step that depends on a row not yet shipped is marked so, not described as
working.

<a id="sh-093"></a>**SH-093 — The README shows an organisation what it gets.** The
README describes a policy for one run; it does not show the loop a team lives in.
*Done when:* the README's first screen says, in one picture and five lines, what an
organisation gets — one policy across its coding agents, specialists that follow it,
context from the team's own knowledge, decisions remembered, every outward action
through a person, a record of every run — and the sixty-second demo still works on a
fresh clone; the pictures are rendered PNG from Mermaid sources kept in a *Diagram
sources* appendix; the word limit (900) and every other `check-docs.py` rule hold.
Failure cases: no claim without a row or a test behind it; no private name.

<a id="sh-094"></a>**SH-094 — Contributor onboarding and documentation consistency.**
The first page must explain team benefits, installation, actual capabilities and
remaining work; external contributors need a bug-report and pull-request path.
*Done when:* README distinguishes manifest version, unreleased main and in-review
work; installation states prerequisites and command working directories; docs link
to a tutorial, task guide, reference and adoption explanation; CONTRIBUTING explains
fork/branch/issue/claim/PR/review and required checks; bug and PR templates exist;
the roadmap remains the only backlog. Check the offline README commands, relative
links, docs checker and existing documentation contract tests. Failure cases:
no speed/adoption claim without evidence; no ordinary-session enforcement claim;
no future eval or workflow described as available; no private output in templates.

<a id="sh-095"></a>**SH-095 — Native Codex plugin installation.** Ship a native
manifest, repository marketplace and Codex implementation/review workflow entry points
that resolve shared procedures and the bundled runtime. *Done when:* an isolated Codex
home adds the local marketplace, installs sky and lists it installed/enabled; skill
references resolve without personal paths; Claude's manifest/hooks remain unchanged.
Failure cases: no model-run claim from an installer check; no Claude agent frontmatter
claimed as Codex enforcement; no personal config overwritten. Record host version and
local versus remote installation evidence.

<a id="sh-096"></a>**SH-096 — Claude and Codex governed implementation parity.**
Arup requires implementation and review on both hosts (2026-10-07). Native workflow
skills do not satisfy managed-launch parity. *Done when:* Codex developer and reviewer
runs demonstrate host-enforced write/read separation, policy-filtered tools and context,
publication refusal, run evidence and local-store retrieval on supported versions;
installation/upgrade instructions and CI fixtures cover both hosts. Failure cases:
unknown tools denied; user config cannot re-enable prohibited tools; writes outside the
workspace refused; no direct publication; no permission widening via skills or agents;
stale/missing policy refuses launch. Probe current Codex hooks, sandbox and tool controls
before offering the developer role. Preserve Claude's tested boundaries.

## Release review — 2026-10-01

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-900 | Bring release documentation up to the shared standard | release | P1 | M | In progress | @arupmmi07, 2026-10-01 |

**Verified:** Resolve the five documentation-check failures: early PNG, PNG embeds in README/architecture, quick-start section and numbered steps. Demonstrate an offline complete run, not only readiness diagnostics.

*Progress, 2026-10-01:* the five documentation-check failures are fixed (24 pass, 0 fail). Still open: an offline complete run, which needs SH-020.

*Added, 2026-10-05:* the 3.0 design note's two figures (`docs/images/governed-session`
and `sessions-and-bridge`) are PNG on the page with SVG beside, and the note has a
Diagram sources appendix; `check-docs.py` passes with the note included.

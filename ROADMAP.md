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
| SH-005 | [No company-specific name in the public tree](#sh-005) | hygiene | P0 | S | In progress | @arupmmi07, 2026-09-30 |
| SH-006 | [A `test` skill with no vendor tools](#sh-006) | skills | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-007 | [The documented KB map works as written](#sh-007) | docs | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-008 | [One answer to which roles run on which host](#sh-008) | hosts | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-009 | [`sky kb which` gives the real reason](#sh-009) — *good first issue* | cli | P0 | S | Done — 2.1.2 | @arupmmi07 |
| SH-010 | [Promises with no code behind them](#sh-010) | docs | P0 | M | In progress | @arupmmi07, 2026-10-01 |

### 2.2.0 — clone and run

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-020 | [A demo knowledge base in the repository](#sh-020) | demo | P1 | L | Ready | |
| SH-021 | [Setup with no administrator](#sh-021) | setup | P1 | S | Ready | |
| SH-022 | [`doctor` names the port tools it found](#sh-022) | probes | P1 | M | Ready | |
| SH-023 | [`doctor` with no KB map still shows the table](#sh-023) — *good first issue* | probes | P1 | S | Done — 2.1.2 | @arupmmi07 |
| SH-024 | [The Sky Context Protocol, written down](#sh-024) | protocol | P1 | M | Needs decision | |
| SH-025 | [A 60-second demo in the README](#sh-025) | docs | P2 | S | Proposed | |

### 2.3.0 — the run is the record

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-030 | [`sky runs`: list and show run records](#sh-030) — *good first issue* | record | P1 | S | Ready | |
| SH-031 | [The ledger records every tool call](#sh-031) | record | P1 | S | Ready | |
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
| SH-040 | [A code port, with skygraph as the first server](#sh-040) | ports | P1 | M | Needs decision | |
| SH-041 | [A ticket port](#sh-041) | ports | P2 | L | Needs decision | |
| SH-042 | [The build result as a published contract](#sh-042) | ethan | P2 | S | Proposed | |
| SH-043 | [Codex and Kimi, measured again](#sh-043) | hosts | P3 | M | Proposed | |

### Distribution and trust

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-050 | [CI runs `sky selftest`](#sh-050) — *good first issue* | ci | P1 | S | Done — 2.1.2 | @arupmmi07 |
| SH-051 | [CI on macOS, and Python 3.11 checked](#sh-051) | ci | P2 | M | Ready | |
| SH-052 | [Install without a clone](#sh-052) | distribution | P2 | M | Needs decision | |

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

<a id="sh-052"></a>**SH-052 — Install without a clone.** There is no package metadata; the
runtime reaches people by clone, by `sky setup` copying a launcher, or inside the
plugin. *Decision needed:* a package installable with `pipx`, or clone and plugin only.

## Release review — 2026-10-01

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| SH-900 | Bring release documentation up to the shared standard | release | P1 | M | In progress | @arupmmi07, 2026-10-01 |

**Verified:** Resolve the five documentation-check failures: early PNG, PNG embeds in README/architecture, quick-start section and numbered steps. Demonstrate an offline complete run, not only readiness diagnostics.

*Progress, 2026-10-01:* the five documentation-check failures are fixed (24 pass, 0 fail). Still open: an offline complete run, which needs SH-020.

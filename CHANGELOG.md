# Changelog

## Unreleased

- **SH-051, in part** — the test-runner probe reads Python 3.11's answer to an empty
  selection (exit 0, "Ran 0 tests") as healthy, as it already did 3.12's (exit 5, "NO
  TESTS RAN"). CI's 3.11 job had failed on this since the Windows port.
- **SH-064** — roles own skills and skills own tools. The policy gains `tools:` bindings
  (each tool names the action it performs; MCP tools carry a reviewer), `skills:` with a
  tool list per shipped skill, and roles with `base_tools` and granted `skills`. A tool
  bound to an outward or never action is never rendered into an agent. `sky policy render`
  writes the agents' `tools:` lines and `plugin/registry.json`; `sky policy lint` fails on a
  stale registry or a drifted agent file. Legacy `tools:` roles keep working unchanged.
  Eleven skills whose procedures call tools their roles do not hold are declared but not
  granted; `sky policy show` lists them (SH-082).
- **SH-011** — the role boundary on Claude Code is the agent definition, not
  `--allowedTools`, which only pre-approves. The launcher now refuses to start a role
  whose `plugin/agents/<role>.md` is missing or lists different tools from the policy,
  records `launch_refused`, and shows the check in `sky build --dry-run` and as a row
  under Safety in `sky doctor`. `scripts/check-role-boundary.py` reproduces the three
  live cases against a logged-in CLI; the record for Claude Code 2.1.286 is in
  `docs/features/`. Every host subprocess in the core now reads UTF-8 with replacement.
- **3.0 design** — `docs/features/3.0-governed-sessions.md` and roadmap rows SH-060 to
  SH-081: governed ordinary sessions, roles own skills, policy layers under one
  ceiling, session cards, a built-in optional bridge, one handover format, a context
  protocol with a recorded manifest.

- **SH-053** — the core and its tests run on Windows 11. Stopping a hand no longer
  uses `SIGKILL`, which Windows lacks and which hung the suite: the hand runs in a
  job object, so its children stop with it. The core no longer fails to start when
  the environment names no home, runs Python test suites with its own interpreter
  rather than `python3`, finds git on the hand's PATH, and reports repository paths
  with forward slashes. The vendor script writes the plugin's copy with LF endings.
  Twenty tests of POSIX-only behaviour (file modes, running shebang scripts and the
  `sh` helpers directly) are skipped on Windows, each with its reason.

## v2.1.2 — 2026-10-02

All ten correctness bugs on the roadmap (SH-001 to SH-010) are closed, each with a
test. Not yet tagged.

- **SH-002** — the Safety check ran the guard outside a managed run, where it stands
  aside, so Safety read DOWN and every developer build was refused. It now asks this
  runtime's own guard with the environment a run gets.
- **SH-001** — the checks called tool names no knowledge base built to the port offers.
  Names now come from one place and are checked against the policy and the port document.
- **SH-003** — `sky ship` lists intents in the order they were made.
- **SH-023** — `sky doctor` with no knowledge-base map still shows every row.
- **SH-036** — the guard reads past git's global options, so `git -C . push` is denied.
- **SH-007** — the documented knowledge-base map has the real path and loads as written.
- **SH-050** — CI runs `sky selftest`.
- **SH-004** — a managed run can reach `sky ship`. The agent writes requests into
  `.sky/outbox/`; when it exits, the runtime seals and files them. The agent never runs
  `sky`, and no role gained shell rights.
- **SH-005** — `sky selftest` checks the whole tree for private names, from a committed
  list of salted hashes, so CI runs it without the plain list.
- **SH-006** — the `test` skill runs local tests only; no role holds a tool for shared
  test environments.
- **SH-008** — `sky host` and `hosts/README.md` follow the launcher: Codex runs the
  reviewer role only, Kimi no managed role.
- **SH-009** — `sky kb which --kb <name>` says the KB was chosen with `--kb`.
- **SH-010** — six documented features with no code behind them are removed from the
  docs, the plugin and the code comments; [the roadmap row](ROADMAP.md#sh-010) lists them.
- **The guard fails closed inside a managed run** when it cannot load a policy: it
  denies every command and says why. Outside a managed run it still stands aside.
- **`sky doctor` with no KB map** points to the no-setup demo and to how to connect a
  knowledge base.
- Tests no longer depend on the machine's git remote; the suite passes in a fresh clone.
- README rewritten to the shared documentation standard, with a sixty-second demo.

## v2.1.1 — 2026-09-17

Four things found while preparing the onboarding guide, each of which the
first real setup would have tripped over.

**Focus went green on other people's documents.** Only the `project` layer of
a knowledge base is tenant-isolated; the other layers are shared across every
tenant on the host. So a search against a tenant with *nothing of its own*
still returns hits — measured: five, every one from another tenant — and the
probe counted them and said OK. It now reads each hit's `tenant_code`: hits
from this tenant → OK, saying how many; hits only from other tenants →
DEGRADED, saying so in those words; no hits → DOWN as before. Gate G23a row 2
is amended to match, and a G23b case breaks it on purpose.

**`sky host` overwrote files it did not write.** `~/.codex/AGENTS.md` and
`~/.kimi-code/config.toml` are exactly the files a person already has. The
same rule as the launcher now applies: a file is replaced only if it does not
exist, says `sky host` wrote it, or is listed in the manifest of an earlier
run — and the check runs over every file *before* anything is written, so a
refusal leaves the directory untouched.

**Two tests failed on the 2.1.0 release and were reported as passing.** The
README still said v2.0.0, and the rename test pinned `"2.0.0"` — a test about
the *name* that broke on the next version and proved nothing about the rename.
The README is current; the test now checks the shape of the version, not one
value.

**Four refusals still said `vai build`.** In core, which the selftest's
retired-name check does not cover. They say `sky build`.

## v2.1.0 — 2026-09-17

Four rules about how a skill works, in `plugin/SKILLS.md`, each with a check
that fails when it is broken. The rules are not new ideas; what is new is that
three of the four were absent here and nothing said so.

**Save the code, do not re-derive it.** Skills may ship `scripts/`, and
`plugin/scripts/render-diagram.py` is the first — mermaid or SVG in, SVG and
PNG out, and an exit code that distinguishes "both" from "the SVG only,
because no converter is installed" so a caller cannot claim a PNG it does not
have. `design` had the conversion spelled out by hand, which meant every run
re-derived it and got a slightly different result; it now calls the script, and
a test asserts no skill spells out a converter at all.

**A skill nobody can find is a skill nobody has.** The host reads only `name`
and `description` until one matches, so a description must name the words a
person would type, and no two skills may claim the same trigger. `sky selftest`
now fails on the video's own example — "helps with content" against "creates
marketing assets". 20 skills, 80 distinct triggers, no collisions.

**A correction that dies with the session gets made again.** `/sky:learn` now
classifies where a fix belongs — the procedure, a reference file, an explicit
rule, or the code — and says to re-run the task and check the fix held. A
proposed skill change is code: it is shown, confirmed, written, and takes
effect when a person commits it.

**Your first look must not be the agent's first look.** Eleven of twenty skills
returned their first attempt. Each now states acceptance criteria and checks
against evidence outside the draft, and the evidence is specific to the job
rather than a shared paragraph: `ingest` reads `jobs.output` and not
`jobs.status`, `build` reads the run record and not the hand's prose, `review`
opens every file and line it cites, `test` establishes a baseline before
blaming the change.

Both new checks were driven against a relapse as well as the good case. Two of
my own first attempts at them were wrong in the way this project keeps
repeating — one tested a single wording and flagged three skills that already
said when, and one asserted an exact sentence rather than the property.

521 tests, selftest 14 checks.

## v2.0.0 — 2026-09-16

The project is now **Skynet Harness**, owned independently by its author. The
short name is `sky` everywhere: plugin and marketplace (`sky@sky`), command,
Python package, skill prefix (`/sky:*`), environment variables (`SKY_*`),
configuration (`~/.config/sky`), run data (`.sky/`), shared catalogue
(`sky_kb`) and skill ontology (`sky_skill`). Ethan and the shared architecture
documents use the same contract.

This is intentionally a clean break. Releases through v1.0.3 used the former
VAI name; they remain in Git history, but no compatibility alias is carried
forward because no user or knowledge base had been onboarded.

## v1.0.3 — 2026-09-16

A third review. Its headline — "none of the nine fixes landed" — was a
diff-range artifact: it compared `main...dev`, and the merge-base of those two
branches *is* the commit carrying the nine fixes, so the range excludes them by
construction. Its own verified state confirmed `main` at that commit with 473
tests passing. **The ten individual findings were all real.**

**Nothing in the rendered output runs but the command.** Fencing a body as
"text, not a command" was a label; the lines inside the fence were still
commands the moment somebody selected the block and pasted it. Every body line
is now commented, and the tests assert the live-line count directly rather than
looking for a marker.

**Model text no longer crosses a shell.** `/sky:ship` told the agent to write
`sky intent --body "…"`. A shell expands an argument *before* `sky` starts, so
a backtick or `$(…)` in a body had already run by the time any validation could
see it — every check in the broker was happening too late. Intents are now
written as a JSON file with an editor tool and named with `--from-file`.

**Codex is offered one read role, not three.** Its sandbox makes architect,
reviewer and security identical — none can write, and nothing stops the one
asked for a review from doing an architect's job. Three was a label pretending
to be enforcement.

Also fixed: the installed launcher pointed into the versioned plugin cache and
would break on the next update, and would silently overwrite a `sky` somebody
else had put on PATH; rollback covered the token and the map but left the
helper, the launcher and the host's server file wherever a failure found them;
uninstall compared only the helper, so a person who re-pointed a server's URL
still lost it; generated host packages omitted the templates four skills name
and could keep the literal `${SKY_KB_URL}`, which neither Codex nor Kimi
expands — a package that installs perfectly and reaches nothing; the documented
local loop said `git add -A`; and the README still said v1.0.1.

491 tests, selftest 12 checks.

## v1.0.2 — 2026-09-15

A second review of v1.0.1 found nine more defects. All nine fixed, each with a
test that reproduces the original behaviour.

**A summary could smuggle in a command.** A model writes the summary; one with a
newline in it broke out of the `#` comment and put an unapproved
`git push --force origin main` *above* the approved line, in output whose whole
purpose is "these are the commands, run them". A multi-line summary is now
refused, every displayed line is commented individually, and a body is fenced as
text rather than left bare. The only uncommented line is the validated command,
and a test asserts exactly that.

**Bare `sky` did not exist.** v1.0.1 vendored the runtime, but only
`<plugin>/bin/sky` worked — and every skill types `sky`. My own regression test
used the full path, which is why it passed. `sky setup init` now installs a
launcher at `~/.local/bin/sky` and says out loud when that directory is not on
PATH. The test runs the bare command.

**Codex was never given its knowledge base.** A managed Codex run ignored the
per-run MCP configuration and silently used the person's own — possibly another
tenant. It now gets `-c mcp_servers.kb.url=…` overrides and refuses to start if
it cannot be told which KB to use. **Kimi is refused managed runs entirely**: it
publishes no per-run MCP override, so core could not choose its knowledge base
while believing it had.

Also fixed: `--replace-servers` was named in an error message and did not exist
as an option; readiness looked for the guard on PATH only and reported "not
installed" on a machine whose guard sat beside it; `by_hint` could still return
the skill catalogue as the task knowledge base; `sky-admin profile` could not
express repository paths, catalogue kind or default; switching an interactive
session to a KB on another host was documented and not implemented, and is now
`sky setup use`; recording an intent counted files and could overwrite one;
setup wrote files sequentially with no rollback and uninstall removed a server
the person had since changed; generated host packages named a token variable
without loading it and carried `${CLAUDE_PLUGIN_ROOT}` into other hosts' skills.

**Not done, and not claimed:** one real knowledge-base read per host. That needs
credentials this build does not have.

473 tests, selftest 12 checks.

## v1.0.1 — 2026-09-15

A review of v1.0.0 found eleven defects. Every one reproduced, every one fixed,
and each now has a test that reproduces the original behaviour. **Do not
install v1.0.0.**

The three that mattered most:

**The plugin shipped no runtime.** After `claude plugin install sky@sky` there
was no `sky`, so setup, doctor, build, stamp, ship, the guard and the ledger
all did nothing — and the guard's fail-open branch made that invisible. The
runtime is now vendored into the plugin, a selftest check keeps the copy in
step with `core/`, and the acceptance is the reviewer's own: an empty home, a
minimal PATH, and nothing installed but the plugin.

**The guard fired in ordinary sessions.** It denied `git push` in a session a
person opened to do their own work — their repository, their credentials, and
the host's permission prompt is the control that belongs there. It now acts
only inside a run the launcher started.

**An argument that became an option.** `--mirror` passed as a branch name and
rendered `git push origin --mirror`, which overwrites every ref on the remote.
No shell metacharacter is involved, so refusing metacharacters did not catch
it. Any value beginning with `-` is now refused, for branches and remotes.

Also fixed: the broker was never connected to anything (`sky intent` and
`sky ship` now exist and `/sky:ship` calls them instead of composing commands
itself); the launcher set `SKY_AGENT` while the stamp and ledger read
`SKY_AGENT_ID`, so every stamp inside a real run was blank and the ledger had
nowhere to write; setup replaced an existing `kb` server, dropped the host file
from 600 to 644, and wrote a token before validating; a catalogue could own a
directory and so become the task knowledge base; two tenants on one address
were rejected; host packages shipped no skills; readiness still expected ten
skills and counted another product's plugin; published skills carried no
provenance; and the README still said ten skills and not release-ready.

449 tests, selftest 12 checks.

## v1.0.0 — 2026-09-15

The first release. It does **rendering, not executing**: every outward action —
push, pull request, ticket comment, ticket transition — is produced as the exact
command and a person runs it. That is not a limitation to be apologised for,
it is the design until the isolation boundary exists (H10, gate G25).

### What you get

**A runtime, `sky`.** Resolves which knowledge base a directory belongs to,
checks what is alive before letting work start, launches a coding agent under a
role and a tool allowlist, records the run and what it cost.

**Setup that does not put your token anywhere silly.** `sky setup init` takes a
three-field profile from your administrator and your own token, typed at a
terminal, and writes: the token to `~/.config/sky/env` at mode 600, the map to
`~/.config/sky/kb-map.json` holding only the *name* of the token variable, a
copy of the headers helper, and one user-scoped MCP server pointing at it.
`rotate`, `doctor` and `uninstall` alongside.

**Twenty skills** and **six agents** for Claude; generated packages for Codex
and Kimi.

**A policy** — four roles, twenty-three actions, nine denied to everyone — read
by the launcher, the guard and the broker, so the three cannot drift apart.

**A guard and a ledger.** The guard judges each command in a shell line and
refuses the ones the policy names. The ledger records every tool call into the
run's own file.

**A readiness table** of ten brain functions that says not only what is broken
but what you may still do — a system with no quality control may answer and
review, and may not build.

### What it deliberately does not do

- **The broker does not execute.** It validates and renders. Standing grants do
  not execute at all while the agent shares an operating-system user with the
  broker; that is H8–H11.
- **The guard is not a sandbox.** It matches on a string, and a string can be
  rewritten. The tool allowlist is the boundary; the guard is the layer under
  it, and both are documented as what they are.
- **Codex and Kimi cannot hold every role.** Codex has a sandbox and no
  per-role allowlist; Kimi has neither. Each package says so and offers only
  the roles its host can keep an agent inside.
- **There is no per-agent credential.** Every outward system records the person
  whose token was used. The agent id says which agent ran and authenticates
  nothing.
- **Nothing is ingested unstamped**, and nothing is ingested without a person
  saying yes to that document.

### Known gaps, stated rather than discovered

- `sky setup migrate` is not built; it waits on the plugin-identity decision.
- The `inputs` row of the readiness table has no probe yet and reports itself
  as unbuilt rather than passing.
- Kimi's packaging is verified by generating and parsing its configuration, not
  by a live run under a role — that host cannot enforce one anyway.
- The bill is recorded per run; the per-task total on a console is Ethan's half
  and is not in this release.

### Verified before tagging

394+ tests, a twelve-check selftest, and gate **G23b**: every probe was made to
fail on purpose and the table checked to turn red for that row *and only that
row*. Where a break legitimately cascades, the cascade is named in a test.

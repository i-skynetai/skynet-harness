# Offline context example

The five documents in [demo-docs](demo-docs/) are public sample data about Skynet
Harness: an ADR, a design note, a handover and two plain notes. They need no service
account, key or network. The ADR names the design in `relates_to`, so the graph has
one edge to follow, and the phrase `cedar context trail` is the search probe.

## Run it

In any Git repository you want to manage, with this checkout's `sky` on your path.
The reviewer dry run also applies the repository's own readiness checks, so the
repository needs a test runner the doctor can find (a `tests/` directory is enough).

```sh
mkdir -p docs && cp -r <checkout>/examples/demo-docs docs/demo
sky setup init --local
sky policy render
sky kb serve --write-adapter
sky kb init
sky doctor
sky build --dry-run --role reviewer
```

Each command's real output, in a fresh repository on 2026-10-06, paths shortened:

```text
$ sky setup init --local
<project>/.sky/project.yaml

$ sky policy render
updated .sky/registry.json

$ sky kb serve --write-adapter
local adapter: <project>/.sky/context.yaml

$ sky kb init
stored: 5; unchanged: 0; skipped: 0
no code index
run record: ~/.local/state/sky/runs/run-20261007-035223-001

$ sky doctor
ready for: question, review      NOT: build, learn
  focus              ok        local search for 'Role definitions' answered: 1 hit(s)
  knowledge          ok        local MCP tools/list and search answered
    search             ok        1 mapped operation(s) answered tools/list
    graph              ok        1 mapped operation(s) answered tools/list
    code               absent    nothing mapped
    tickets            absent    nothing mapped
    decisions          ok        2 mapped operation(s) answered tools/list
    ingest             ok        1 mapped operation(s) answered tools/list
  safety             ok        rules loaded and denying (23 actions, 4 roles); the guard ran and refused a push
    agent definitions  ok        all 4 effective role definitions match
  habits             MISSING   the host lists no `sky` plugin — install it from the marketplace
  build is blocked by: habits

$ sky build --dry-run --role reviewer
run run-20261007-035225-001   someone-reviewer-1   KB local
  agent definitions  ok       reviewer: <checkout>/plugin/agents/reviewer.md
git block proven: git refuses to produce a credential, and names the askpass block as why
--dry-run: everything above passed; the hand was not started.
```

What each step did. Local setup wrote one file, the managed project configuration,
and refuses to overwrite it without `--force`. Rendering wrote the effective
identities to `.sky/registry.json`; a fresh managed project is refused a launch
until this exists, by design. The adapter file binds the local store's operations to
the protocol's capabilities; code and tickets stay `absent` until another source maps
them. Initialization stored the five documents through the runtime's validated put
path, recorded each one's source and digest in the store manifest, and recorded that
no code index is configured. A second `sky kb init` reports `unchanged: 5` and writes
no revision. The doctor's focus row searched for the latest stored title and names
it. The dry run checked the reviewer's definition, the local grants and the git
credential block, and started no model; `build` stays blocked until the plugin is
installed in the host.

## Look at what was stored

```sh
sky kb search "cedar context trail"
sky kb show demo-adr-local-context
```

```text
$ sky kb search "cedar context trail"
demo-adr-local-context  score 3  id:demo-adr-local-context  Keep project context local
demo-handover-review    score 3  id:demo-handover-review    Review handover
demo-design-context     score 1  id:demo-design-context     Context retrieval design
3 hit(s)
```

`show` prints the stored metadata, including the runtime-written provenance
(`sky_agent: runtime`, the init run id, the canonical source path) and the
`relates_to` edge to the design.

## The same contract, as tests

`core/tests/test_sh084_kb_init.py` runs the corpus offline: search finds the probe
phrase, `graph.neighbours` follows the ADR's edge, absent capabilities are reported
as absent, and a malformed adapter is refused before anything is written.

```sh
cd core && python -m unittest tests.test_sh084_kb_init
```

`sky kb init --discover` prints that codebase discovery lands with
[SH-088](../ROADMAP.md#sh-088) and performs no writes. Document initialization
records what the code index covers when one is configured; it never claims complete
coverage.

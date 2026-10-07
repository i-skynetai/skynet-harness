# Skynet Harness

[![tests](https://github.com/i-skynetai/skynet-harness/actions/workflows/tests.yml/badge.svg)](https://github.com/i-skynetai/skynet-harness/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)

*Your team's standard way to use AI coding agents.*

A Claude Code plugin and a Python runtime for checked coding-agent runs. Give specialists
clear roles, retrieve project knowledge, keep approved decisions and record what ran.
People perform publication. Use your existing model; Codex supports managed reviews only.
The complete session-to-session workflow is still in development.

![A team shares one policy, delegates to specialists, retrieves project knowledge and keeps publication with a person](docs/images/org-value.png)

## The problem

Fast code generation loses value when sessions repeat questions, miss project conventions
or produce work that needs extensive correction. Shared rules and reusable context aim
to reduce rework and make delegation more predictable. Adopt the harness as a team
working agreement; installation does not enforce every parent-session action.
Measure delivery and review outcomes before claiming speed or adoption gains
([adoption guide](docs/adoption.md)).

## Words you need

- **Role** — developer, reviewer, architect or security, with a checked tool list on Claude.
- **Policy** — shipped rules plus organisation and project layers under one permission ceiling.
- **Managed repository** — a Git repository with `.sky/project.yaml` and `managed: true`.
- **Outward action** — state-changing publication: push, PR, ticket comment or remote knowledge write.

## See it work in sixty seconds

Git and Python 3.11 or newer; no model account, service or Python dependencies needed:

```sh
git clone https://github.com/i-skynetai/skynet-harness.git
cd skynet-harness
python sky policy lint
python sky policy developer push
python sky policy reviewer push
python sky policy developer edit
```

This is the real output from the policy demo:

![Real output: clean policy, developer push needs a human, reviewer push denied, unknown action denied](docs/images/demo.png)

A developer prepares publication; a reviewer cannot request a push. Unknown actions
are denied. `python sky selftest` checks the repository against itself. Try the
[local-store example](examples/README.md) next, without a remote knowledge base.

## Use it with your team

1. **Install into Claude Code.** Run these in your shell, from the target repository:

   ```sh
   claude plugin marketplace add i-skynetai/skynet-harness
   claude plugin install sky@sky --scope project
   claude plugin list
   ```

2. **Set up the target Git repository.** Keep the harness checkout for its CLI:

   ```sh
   python <harness-checkout>/sky setup init --local
   python <harness-checkout>/sky policy render
   ```

3. **Connect and index local documents.** No service or key required:

   ```sh
   python <harness-checkout>/sky kb serve --write-adapter
   python <harness-checkout>/sky kb init
   python <harness-checkout>/sky doctor
   ```

4. **Check a launch.** Install the supported host CLI and configure the target's test
   runner first. Dry-run checks readiness without calling the model:

   ```sh
   python <harness-checkout>/sky build --dry-run --role reviewer
   ```

   A real run requires an installed, authenticated supported host. Codex packaging
   and remote-context setup are in the [user guide](docs/user-guide.md).

5. **Review publication yourself.** `python <harness-checkout>/sky ship` prints prepared
   actions and executes none. Each collaborator installs the plugin on their machine;
   automatic team bootstrap remains SH-060.

## What happens on a run

![Checked launches delegate to bounded specialists; dashed context and workflow paths are planned](docs/images/org-loop.png)

The launcher checks policy, tools and readiness before starting a role. Runtime events
record outcomes and observed MCP context; publication remains a human checkpoint.
Dashed paths are planned. See [architecture](docs/architecture.md).

## What you can use now

- Checked Claude role definitions; Codex reviewer runs in a read-only sandbox.
- Layered policy, rendered tool lists and recorded host tool inventories.
- Local document storage, search, `sky kb init` and an optional code-index adapter.
- Decision proposals and human acceptance, rejection or supersession (SH-087).
- MCP-call ledger and context manifests showing observed calls and returned size.
- The **twenty-one SDLC skills** in the committed baseline; **twenty-three SDLC skills**
  in the in-review development checkout. Procedure alignment remains SH-082.

## What it is not

It is not a model, an adversarial sandbox or an unattended release system. It checks
supported launches; people still own decisions and publication. A manifest records
observed context, not a guarantee that a task's reasoning was correct.

## Limits and work still ahead

- Ordinary parent Edit/Write/MCP tools remain unrestricted. Automatic briefing,
  governed routing and narrowed-role launches await SH-060–063.
- Analysis/planning are in review (SH-085/086); ordered workflow admission is pending
  (SH-074/075/079/091). The full loop is not available yet.
- Codebase discovery/refresh, `sky eval`, bridges, topic memory and team extensions
  remain roadmap work (SH-066/070–078/088–090).
- Manifests measure size; they do not prove quality or enforce a budget.
  Evals are SH-090; budget enforcement is SH-080.
- The local store is a development reference, not a hosted team knowledge service.
  Remote ingestion remains SH-081. Kimi has no managed role.
- Tool lists and command guards are not an adversarial sandbox.

## Status and history

**v2.1.2.** This is the manifest version; it is not yet tagged. Main contains unreleased
3.0 work. On 2026-10-07, the committed baseline `8486918` has **871 tests**;
the in-review development checkout has **914**. Counts and skips vary by revision.
CI targets Python 3.11, 3.12 and 3.13 on Linux.
The badge links to actual results; local success does not prove hosted CI.
[CHANGELOG.md](CHANGELOG.md) separates history from unreleased work;
[ROADMAP.md](ROADMAP.md) lists known bugs, features, priorities and owners.

## Documentation

| Need | Start here |
|---|---|
| Install, upgrade, first task, troubleshooting | [User guide](docs/user-guide.md) |
| Try local context without an account | [Offline example](examples/README.md) |
| Benefits, team rollout and measurement | [Adoption guide](docs/adoption.md) |
| Concepts and technical reference | [Documentation index](docs/README.md) |
| Known limitations and development history | [Roadmap](ROADMAP.md), [changelog](CHANGELOG.md) |

## Contributing

Report a reproducible bug, propose a feature, improve docs or claim a `Ready` roadmap
row. [CONTRIBUTING.md](CONTRIBUTING.md) explains setup, checks and pull requests.
Use the [issue templates](https://github.com/i-skynetai/skynet-harness/issues/new/choose).

## Licence

Apache 2.0. See [LICENSE](LICENSE).

## Diagram sources

[org-value.mmd](docs/images/org-value.mmd) and [org-loop.mmd](docs/images/org-loop.mmd)
are rendered with `scripts/render-mermaid.py`. The demo picture is real terminal output.

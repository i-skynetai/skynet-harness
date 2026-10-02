# Skynet Harness

[![tests](https://github.com/arupmmi07/skynet-harness/actions/workflows/tests.yml/badge.svg)](https://github.com/arupmmi07/skynet-harness/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)


**A local control plane for AI coding agents.** It gives the agent you already use —
Claude Code, Codex, Kimi — an identity, a role with a fixed tool list, grounded
context from a knowledge base you choose, and a human checkpoint on anything that
leaves your machine.

It does not supply a model. It does not replace your coding agent. It is the layer
underneath that decides what that agent is allowed to do, and records what it did.

```
    task  ──►  knowledge base  ──►  role policy  ──►  coding agent  ──►  evidence
                (you choose)        (default deny)     (your hand)      (local record)
                                          │
                                          ▼
                                   outward action?
                                          │
                                    human decides
```

## Why

Unmanaged coding agents fail in three specific ways. They invent context instead of
retrieving it. They act outside their remit — the agent asked to review a patch pushes
it. And they report success that never happened.

Skynet Harness answers each one directly: one knowledge base per run, a role whose tool
list is fixed before the model exists, and a run record the model cannot write to.

## What it does

- **Grounds work in knowledge.** Each run resolves exactly one knowledge base. Optionally
  a separate read-only skill catalogue and code index.
- **The twenty SDLC skills.** Context, design, impact, module analysis, feature work, bug
  fixing, code, review, security, test, ingest, learn, ADRs, skill discovery, setup,
  doctor, build, ship — repeatable workflows instead of one long prompt.
- **Four roles, different tool lists.** Developer, Reviewer, Architect, Security, plus
  two helper agents that retrieve context and validate work.
- **Checks readiness before the model exists.** `sky doctor` probes the knowledge source,
  retrieval, coding agent, policy, skills and test runner, and says what is missing
  rather than continuing quietly.
- **Blocks the credential paths.** The launcher builds an explicit environment and proves
  the usual Git credential routes are unavailable before the agent starts.
- **Records evidence.** Every managed run has a local record: identity, events, result,
  and the token usage the agent reported.

## How it fits together

![The layers: an optional planner on top, the harness, the knowledge base, and the
engine underneath](docs/images/sky-solution.svg)

Each layer is useful without the one above it. The harness is the layer everyone
installs. [Ethan](https://github.com/arupmmi07/ethan) — the planner on top — is a
separate, optional repository. The coding agent supplies the thinking and the acting;
the harness supplies the habits and the boundary.

## Three design decisions

**Default deny, and no outward action is ever plainly allowed.** An action a role does not
list is denied. An action not named in the policy at all is denied rather than assumed
harmless. Anything that reaches the world outside the machine is `needs_human` or goes
through the broker — you cannot grant a role `push` by editing the file.

**One policy file, read by everything that decides.** The launcher reads it before the
agent starts, the guard hook reads it during the run, the broker reads it before an
outward action. One file, because two policies eventually become the looser one.

**The guard is honest about what it is.** The tool allowlist is the real boundary: a role
that never receives `Bash` cannot run a command, and no string the model emits changes
that. The guard is the second tier, and it matches on strings — it stops the ordinary
attempt and the honest mistake, which together are nearly all of them. It is not a
sandbox, and documenting it as one would be the actual danger.

## Install

Requires Python 3.11+. No other runtime dependency; the core is standard library only.

```bash
git clone https://github.com/arupmmi07/skynet-harness.git
cd skynet-harness
./sky doctor
```

`sky doctor` tells you what is present and what is missing. See
[docs/getting-started.md](docs/getting-started.md).

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | How a task becomes a managed run |
| [Getting started](docs/getting-started.md) | Connect a knowledge base and run your first task |
| [Policy](docs/policy.md) | Roles, actions, and why outward actions are special |
| [Knowledge port](docs/knowledge-port.md) | Point it at any MCP knowledge base |
| [The local loop](docs/local-workflow.md) | Reviewing, committing, and what leaves the machine |
| [Contributing](CONTRIBUTING.md) | Running the tests, and what a change needs |

## Status

**v2.1.1.** Working and tested — **541 tests**, about 15,000 lines of Python, standard
library only. CI runs the suite on Python 3.11, 3.12 and 3.13 with no install step.

Unattended execution is deliberately not built. The managed-write path renders commands
for a human to run; it does not execute them.

## Licence

Apache 2.0. See [LICENSE](LICENSE).

# Architecture

How a task becomes a managed run, and which component decides what.

## The shape

```
┌─────────────────────────────────────────────────────────────────┐
│  YOU                                                            │
│  a task, a repository, a decision to make                       │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  sky core                          (this repository)            │
│                                                                 │
│   kbmap      which knowledge base does this repo resolve to?    │
│   probes     is the KB reachable, is retrieval returning?       │
│   policy     one file: actions, roles, what is outward          │
│   launcher   explicit env, credential paths blocked             │
│   guard      second tier, during the run                        │
│   broker     renders outward commands; never executes them      │
│   recorder   identity, events, result, usage                    │
└──────┬──────────────────────────────────────┬───────────────────┘
       │                                      │
       ▼                                      ▼
┌──────────────────┐                ┌─────────────────────────────┐
│  KNOWLEDGE BASE  │                │  THE HAND                   │
│  any MCP server  │                │  Claude Code · Codex · Kimi │
│  you point it at │                │  supplies model + tools     │
└──────────────────┘                └─────────────────────────────┘
```

![Who runs whom: triggers, the harness, the hand, and where a human
decides](images/who-runs-whom.png)

## The parts

| Part | Responsibility |
|---|---|
| **The hand** | Claude Code, Codex or Kimi. Supplies the model, the working memory and the coding tools that do the work. The harness never supplies a model. |
| **The plugin** | Skills, role agents, policy and knowledge connections. |
| **`sky` core** | Resolves the KB, checks readiness, applies policy, launches a managed hand, records the run. |

| **Task knowledge base** | Project, team, client or personal knowledge for the current task. One per run. |
| **Skill catalogue** | A separate read-only catalogue for discovering approved skills. Finding a skill does not install or execute it. |

For native Codex, the parent calls the local `sky_dispatch` transport. It exposes
only bounded implementation/review requests and delegates to the same launcher.
Implementation needs a person-issued plan admission. The child controller uses
isolated configuration and checks individual command/file approvals against
managed policy; unknown requests refuse. The parent retains its normal host
permissions. This local transport was approved on 2026-10-07; it does not expose
publication, decision approval or permission-management tools. See the
[recorded boundary and installed workflow](features/SH-096-probe-2026-10-07.md).

A **brain** is the temporary combination assembled for one task: the selected knowledge
base, the hand's model and working memory, the harness's skills and policy, and your
tools. It exists for the run. It is not another product.

## The order things happen

1. **Resolve the knowledge base.** From `--kb`, else the KB whose `repos` contains the
   repository path, else the default. A repository under a client KB never falls
   back to a work default — it gets no KB and a clear message, rather than the wrong one.
2. **Probe readiness.** Knowledge source, retrieval, coding agent, policy, skills, test
   runner. This runs *before the model exists*, so a failure is a message rather than a
   confused agent.
3. **Apply the role.** The role's tool list is fixed here. This is the real boundary:
   what the model never receives, it cannot use.
4. **Build the environment.** Explicit allowlist, not a filtered copy of yours. The
   launcher proves the usual Git credential routes are unavailable before starting.
5. **Run.** The guard reads commands the model is about to run and answers on them.
6. **Record.** Identity, events, result, reported usage — in a local run record.

![The two launch paths — the harness alone, and the harness driven by a
planner — share one set of roles and one knowledge-base map](images/launch-paths.png)

## Two tiers, named honestly

**Tier A — the agent definition.** Claude's `--agent sky:<role>` selects the
definition whose `tools:` list controls tool availability. The launcher refuses to
start if that definition is missing, unreadable or differs from the expanded policy
tool list. A role without `Bash` cannot run a command. `--allowedTools` only
pre-approves the role's calls so the run does not prompt; both flags are passed.

Run `python scripts/check-role-boundary.py --out <record.json>` with a logged-in
Claude CLI to check this mechanism against a recorded host version. This live check
uses temporary files and is separate from unit tests and CI.

**Tier B — the guard.** Exists because tier A is all-or-nothing: a developer role *does*
get `Bash`, for tests and local commits, and inside that grant `git push` has to be
stopped on its own. The guard matches on the command string.

A string can be rewritten. `git push` is caught; a base64-decoded `eval` is not. The
guard stops the ordinary attempt and the honest mistake, which together are nearly all
of them. It is not a sandbox. Documenting it as one would be the actual danger.

## What is deliberately not built

- **Unattended execution.** There is no mode where the harness acts without a person.
- **Executing outward actions.** The broker renders the command. A human runs it.
- **Being a security sandbox.** Isolation is not the same as a different OS user, and
  the harness does not claim otherwise.

# User guide

Try the policy offline, connect a knowledge base, then launch a checked coding-agent
run. [SH-092](../ROADMAP.md#sh-092). Commands below run from the harness checkout
with Python 3.11 or newer; use `python3` where that is your interpreter's name.
For a task in another repository, invoke this checkout's `sky` by absolute path.

Output blocks are expected examples or excerpts from the command's implementation,
not newly captured live transcripts. `<name>` and `<path>` stand for your values.
Future commands are labelled **Planned** with their roadmap rows before the example.

## 1. Try the policy without a service

```sh
git clone --quiet https://github.com/i-skynetai/skynet-harness.git
cd skynet-harness
```

Output: neither command prints on success. Then:

```sh
python sky policy developer push
```

```text
developer · push: needs-human — prepared by the agent, performed by you
```

```sh
python sky policy reviewer push
```

```text
reviewer · push: deny — the reviewer role does not have 'push'
```

The policy classifies outward actions; it does not execute them. Claude has named
agent tool boundaries. Codex supports managed reviewer runs with its read-only
sandbox; Kimi has no managed role ([host limits](../hosts/README.md)).

## 2. Install and verify the Claude plugin

In your shell, with Claude Code already installed:

```sh
claude plugin marketplace add i-skynetai/skynet-harness
claude plugin install sky@sky
claude plugin list
```

Expected result: the marketplace is added and `sky@sky` is listed with version,
scope and status. Exact host output varies; follow any activation/configuration
message. These are the [host's plugin commands](https://code.claude.com/docs/en/discover-plugins).
For project scope, use `--scope project` when installing; each collaborator installs
on their own machine. Team setup automation remains **Planned: SH-060**.

```sh
python sky doctor
```

Expected output excerpt before a KB is configured:

```text
MISSING
```

The surrounding readiness table names the missing components and fixes. Today it
probes knowledge, retrieval, the coding agent, policy/guard, skills and verification;
it does not yet produce the proposed protocol-capability table (SH-024/083/040).
Plugin installation does not make ordinary parent-session editing a governed launch.

## 3. Connect a knowledge base

Follow [getting started](getting-started.md#3-connect-a-knowledge-base) to create the
KB map and set the token variable it names. `setup init --profile <file>` configures
that connection; it does **not** create `.sky/project.yaml`.

```sh
python sky kb list
python sky kb which
```

Example output with a configured default KB named `team`:

```text
  team             work     <purpose>   [default, ← this directory, read-only]
team   (it is the default)
```

Privacy-aware repository ownership takes precedence over the default. No configured
KB means a stated refusal, not an invented connection.

## 4. Inspect layered policy in a managed repository

SH-065 resolves a git worktree's `.sky/project.yaml`. Create this file only when it
is absent; the command refuses to overwrite an existing configuration:

```sh
python -c "from pathlib import Path; p=Path('.sky/project.yaml'); p.parent.mkdir(exist_ok=True); f=p.open('x'); f.write('managed: true\n'); f.close(); print(p.as_posix())"
```

```text
.sky/project.yaml
```

```sh
python sky policy show --layers
```

Expected first line:

```text
effective policy: plugin <path>/policy.yaml + project .sky/policy.yaml
```

An optional org layer and `.sky/policy.yaml` narrow grants under the shipped ceiling;
see [policy](policy.md). They cannot add actions or widen existing roles' permissions.

```sh
python sky policy render
python sky policy lint
```

Expected render excerpt on the first render, then lint's first line:

```text
updated .sky/registry.json
effective policy: plugin <path>/policy.yaml + project .sky/policy.yaml
```

A changed tool set renders an owned project replacement. An unchanged set keeps the
plugin identity. **Current limit:** a launch needing a narrowed or added identity
is refused with `effective identity selection lands with SH-062`. A project config
alone does not implement automatic session briefing or routing (SH-061/062).

## 5. Check, then launch a task

Requires a configured KB, a logged-in supported hand and green readiness for the role:

```sh
python sky build --role reviewer --hand claude --task "Review this change" --dry-run
```

Expected result: readiness and launch-check rows, including agent definitions; a
missing/drifted definition or missing dependency is reported and the hand is not
started. Dry-run checks the launch and does not perform the review.

```sh
python sky build --role reviewer --hand claude --task "Review this change"
```

Expected result: the hand's output followed by its recorded outcome/usage, or a named
refusal. Reported usage comes from the host; it is not an estimate of review quality.
Use developer only where the host enforces that role and build readiness passes.

## 6. Inspect requests before shipping

```sh
python sky ship
```

With no pending intents:

```text
nothing pending.
```

With intents, it prints validated outward-action commands in recorded order and runs
none. Push/PR/ticket rendering is supported for the broker's documented kinds; remote
KB publication is **Planned: SH-081**. Remote reads and calls to the model can occur
in a run: “outward actions” here means state-changing publication, not all networking.
The command-text guard and shared OS user are not an adversarial sandbox.

## 7. Package for Codex after configuring context

```sh
python sky host codex --into <chosen-directory>
```

Expected output excerpt:

```text
  wrote <chosen-directory>/sky.config.toml
Roles it may be asked to run: reviewer.
```

A KB profile/default is required. Missing context or an existing unowned destination
is refused before files are overwritten. This packages rules/skills; it does not
create Claude-style tool boundaries on Codex.

## 8. Upgrade and recheck

```sh
claude plugin marketplace update sky
claude plugin update sky@sky
```

Expected result: the host updates the marketplace/plugin or reports its reason for
refusal; follow its activation message. In a source checkout:

```sh
git pull --ff-only
python sky selftest
```

Example last lines when there are no updates and the checks pass:

```text
Already up to date.
PASS — <count> checks.
```

Counts and skips depend on the checkout; an unrun integration is not a pass.

## 9. The context loop — planned, not commands to try yet

The following output is illustrative, not observed behavior. Importable local-store
modules are the first SH-083 slice; the public CLI and adapter wiring are still pending.

| Planned command | Illustrative result | Rows |
|---|---|---|
| `sky kb init` | source manifest; exclusions, skips and coverage | SH-083/084/040 |
| `sky kb init --discover` | cited knowledge observations, uncovered/partial modules | SH-088 |
| `/sky:analyze <goal>` | cited analysis and OPEN questions; today's analyze is a module-card skill | SH-082/085 |
| `/sky:decide <question> <answer>` | runtime-confirmed decision with approval evidence | SH-087 |
| `/sky:plan <analysis-id>` | ordered steps, acceptance and pinned input digests | SH-086 |
| `/sky:dispatch <plan-id>` | architect/developer/reviewer/security workflow; failure stops advancement | SH-074/075/079/091 |
| `sky kb refresh` | re-indexed paths and stale knowledge, or recorded failures | SH-089 |
| `sky eval` | offline recall, precision and character counts; live rubric scores stay separate | SH-090 |
| `sky session new <name>` / `sky session open <name>` | card and memory-isolated launch command | SH-070/076 |
| `/sky:author <request>` / `sky policy apply <id>` | reviewed proposal then transactional activation | SH-066 |

An approved decision is reused only while current and applicable; a conflict or stale
revision leaves the question OPEN. Future admission gates governed implementation
launches, not the parent's own edits. Complete MCP-call accounting and measured context
manifests require SH-031/068; today's record does not prove every tool call was observed.

## Diagram sources

No diagram is embedded on this page. The planned loop and Mermaid-source convention
are covered by the [context-loop note](features/SH-083-context-loop.md) and the
[README proposal](features/SH-093-readme.md).

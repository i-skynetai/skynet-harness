# User guide

Try the policy offline, connect local or remote context, then launch a checked
coding-agent run. [SH-092](../ROADMAP.md#sh-092). You need Git and Python 3.11 or newer;
the core needs no Python package installation. Use `python3` if that is your interpreter.
Clone the harness for its CLI; install the Claude plugin separately for its skills/hooks.
From the harness checkout use `python sky`; from a target Git repository use
`python <harness-checkout>/sky`, with the checkout path substituted and quoted if needed.
On Windows use Python in PowerShell rather than relying on executable shell shims.

The plugin manifest says v2.1.2, not yet tagged; main includes unreleased 3.0 work.
The [README status](../README.md#status-and-history), [changelog](../CHANGELOG.md) and
[roadmap](../ROADMAP.md) distinguish available source commands from planned work.
See the [adoption guide](adoption.md) for benefits and a measured team rollout.

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
claude plugin install sky@sky --scope project
claude plugin list
```

Expected result: the marketplace is added and `sky@sky` is listed with version,
scope and status. Exact host output varies; follow any activation/configuration
message. These are the [host's plugin commands](https://code.claude.com/docs/en/discover-plugins).
Run the project-scope install from the target repository. It records enablement in
`.claude/settings.json`; each collaborator still installs on their own machine.
User scope is the host's default if you omit `--scope project`. Follow the host's
activation/reload message and check `/sky:*` skills in the session.
Team setup automation remains **Planned: SH-060**.

```sh
python sky doctor
```

Expected output excerpt before a KB is configured:

```text
MISSING
```

The surrounding readiness table names missing components and fixes. When an adapter
is configured, it also shows protocol capabilities as `ok`, `MISSING` or `absent`.
No adapter means no invented connection; see section 3a for the local setup.
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

### 3a. No knowledge base yet? Start with the local store

A team without a knowledge base service can start today. The local store is a
Markdown store under `.sky/kb/`, served over MCP by the runtime, and your own
documents go into it with one command. Run the six commands below from the target
Git repository, substituting your harness checkout path. The output is the maintainer's
captured transcript from a fresh repository on
2026-10-06 (paths shortened):

```sh
python <harness-checkout>/sky setup init --local
python <harness-checkout>/sky policy render
python <harness-checkout>/sky kb serve --write-adapter
python <harness-checkout>/sky kb init
python <harness-checkout>/sky doctor
python <harness-checkout>/sky build --dry-run --role reviewer
```

`--write-adapter` writes configuration and exits; it does not leave a background
server running. Indexing and local search need no model account. Launch readiness
also requires the host CLI on PATH and the target repository's verification setup;
otherwise `doctor` and dry-run report missing parts. That refusal is expected, even
when local context works. The transcript below is from a repository with those parts
configured; document counts and readiness vary with yours.

```text
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
    decisions          ok        2 mapped operation(s) answered tools/list
    ingest             ok        1 mapped operation(s) answered tools/list
```

What you get from it: every document goes through the runtime's validated write path
with its source and digest recorded, so a session can cite where a fact came from; a
second `sky kb init` changes nothing unless a source changed; a removed source is
marked stale, never deleted; files that look like secrets, binaries and oversized
files are skipped and listed. Point `context.sources` in `.sky/project.yaml` at other
folders if your documents live elsewhere. The [offline example](../examples/README.md)
walks the same sequence over five sample documents, and
`sky kb search "<phrase>"` shows what a session would retrieve.

To add a code index, write its adapter from the MCP configuration you already have:
`sky context adapter code --from-mcp-json <path> --server <name>`; `sky doctor` then
shows the `code` capability as `ok` and lists the mapped operations.

## 4. Inspect layered policy in a managed repository

SH-065 resolves a Git worktree's `.sky/project.yaml`. If you followed section 3a,
it already exists; skip creation. Otherwise, from the target repository:

```sh
python <harness-checkout>/sky setup init --local
```

```text
.sky/project.yaml
```

```sh
python <harness-checkout>/sky policy show --layers
```

Expected first line:

```text
effective policy: plugin <path>/policy.yaml + project .sky/policy.yaml
```

An optional org layer and `.sky/policy.yaml` narrow grants under the shipped ceiling;
see [policy](policy.md). They cannot add actions or widen existing roles' permissions.

```sh
python <harness-checkout>/sky policy render
python <harness-checkout>/sky policy lint
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

Requires configured local or remote context, a logged-in supported host and green
readiness for the role. Dry-run checks setup without invoking a model; a full run
uses the host's account. From the target repository, substitute the checkout path:

```sh
python <harness-checkout>/sky build --role reviewer --hand claude --task "Review this change" --dry-run
```

Expected result: readiness and launch-check rows, including agent definitions; a
missing/drifted definition or missing dependency is reported and the hand is not
started. Dry-run checks the launch and does not perform the review.

```sh
python <harness-checkout>/sky build --role reviewer --hand claude --task "Review this change"
```

Expected result: the hand's output followed by its recorded outcome/usage, or a named
refusal. Reported usage comes from the host; it is not an estimate of review quality.
Use developer only where the host enforces that role and build readiness passes.

## 6. Inspect requests before shipping

```sh
python <harness-checkout>/sky ship
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
python <harness-checkout>/sky host codex --into <chosen-directory>
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
refusal; follow its activation message. In the harness source checkout with a clean
working tree (preserve your local changes first):

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

## 9. Decision history available now

`/sky:decide` prepares a proposal; it does not approve it. A person or dispatcher
persists the returned document through the runtime. From the target repository:

```sh
python <harness-checkout>/sky kb decide propose --from <proposal.md>
python <harness-checkout>/sky kb decide list
python <harness-checkout>/sky kb decide show <id>
```

Use [the decision template](../plugin/templates/decision.md) for the proposal.
Review the exact revision, alternatives, citations and scope. A person then runs:

```sh
python <harness-checkout>/sky kb decide accept <id>
```

Expected behavior: confirmation followed by a new revision with runtime approval
evidence. Approval is refused in a governed run. Agents must never use `--yes`, clear
governed-run markers or accept on behalf of a person. The CLI also supports reject
and supersede; `python <harness-checkout>/sky kb --help` lists their arguments.
A retrieved candidate alone does not settle a question.

<a id="operating-limits"></a>
### Operating limits

- Installing the plugin does not restrict ordinary parent-session Edit, Write or MCP
  tools. Automatic briefing, governed routing and narrowed-role launches remain
  SH-060–063. Checked specialist launches have the host boundaries described above.
- Tool lists and command guards are not an adversarial sandbox. People own decision
  approval and publication; the harness is not an unattended release system.
- Context manifests record observed calls and returned size. They do not prove the
  quality of reasoning or enforce a context budget. Evals are SH-090; enforced budgets
  are SH-080.
- The local store is a development reference, not a hosted team knowledge service.
  Remote ingestion remains SH-081. Codex supports managed reviews only; Kimi has no
  managed role.

## 10. The rest of the context loop — work still ahead

The following output is illustrative, not observed behavior. The local store, its CLI
(`sky kb serve|put|show|search|init`), the code-index adapter and the MCP-call ledger
have landed (SH-083, SH-084, SH-040, SH-031, SH-068; see section 3a), as has the
decision lifecycle (SH-087). Analysis/planning are in review; they are not a tagged
release or the complete governed implementation workflow. The rows below
are still to come.

| Planned command | Illustrative result | Rows |
|---|---|---|
| `sky kb init --discover` | cited knowledge observations, uncovered/partial modules | SH-088 |
| `/sky:analyze <goal>` | goal analysis is in review; committed earlier versions use analyze for module cards | SH-082/085 |
| `/sky:plan <analysis-id>` | ordered steps, acceptance and pinned input digests | SH-086 |
| `/sky:dispatch <plan-id>` | architect/developer/reviewer/security workflow; failure stops advancement | SH-074/075/079/091 |
| `sky kb refresh` | re-indexed paths and stale knowledge, or recorded failures | SH-089 |
| `sky eval` | offline recall, precision and character counts; live rubric scores stay separate | SH-090 |
| `sky session new <name>` / `sky session open <name>` | card and memory-isolated launch command | SH-070/076 |
| `/sky:author <request>` / `sky policy apply <id>` | reviewed proposal then transactional activation | SH-066 |

An approved decision is reused only while current and applicable; a conflict or stale
revision leaves the question OPEN. Future admission gates governed implementation
launches, not the parent's own edits. Managed-session MCP hooks record observed calls;
`sky context manifest <run>` measures those events and returned sizes. A manifest
does not establish coverage of work outside that path or the quality of reasoning.

## 11. Troubleshooting

| Symptom | What to check |
|---|---|
| `sky` not found | Use `python <harness-checkout>/sky`; plugin installation and shell CLI setup are separate |
| Plugin or skills missing | `claude plugin list`, correct scope/repository and the host's activation message |
| `doctor` names missing context | Run the local six-command setup; inspect `.sky/context.yaml` and selected documents |
| Empty local search | `kb init` exclusions, source folders and `kb search` using a known document title |
| Launch refuses a narrowed/added role | Identity selection is pending SH-062; do not bypass the refusal |
| Decision approval refused | Run the transition yourself outside a governed agent; inspect the exact revision |
| Unexpected behavior after update | Check commit/plugin version, rerender policy and run selftest; do not overwrite existing setup blindly |

For a reproducible failure, use the [bug-report template](../.github/ISSUE_TEMPLATE/bug_report.md).
Include environment, revision, commands and redacted output. Do not publish private
documents or credentials.

## Diagram sources

No diagram is embedded on this page. The planned loop and Mermaid-source convention
are covered by the [context-loop note](features/SH-083-context-loop.md).
The [documentation index](README.md) links current guides and historical designs.
